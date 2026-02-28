"""Agent Monteur — Assemble les segments audio en un épisode final."""

import json
import logging
from pathlib import Path

import numpy as np
import soundfile as sf
from pydub import AudioSegment

import config

logger = logging.getLogger(__name__)


def _normaliser_lufs(audio: AudioSegment, cible_lufs: float = -16.0) -> AudioSegment:
    """Normalise le volume d'un AudioSegment au niveau LUFS cible.

    Args:
        audio: Segment audio à normaliser.
        cible_lufs: Niveau LUFS cible (défaut : -16.0 pour les podcasts).

    Returns:
        AudioSegment normalisé.
    """
    try:
        import pyloudnorm as pyln
    except ImportError:
        logger.warning(
            "pyloudnorm non disponible — normalisation LUFS ignorée."
        )
        return audio

    # Convertir pydub → numpy pour pyloudnorm
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    if audio.channels == 2:
        samples = samples.reshape((-1, 2))
    else:
        samples = samples.reshape((-1, 1))
    # Normaliser les échantillons dans [-1, 1]
    max_val = float(2 ** (audio.sample_width * 8 - 1))
    samples = samples / max_val

    meter = pyln.Meter(audio.frame_rate)
    loudness_actuelle = meter.integrated_loudness(samples)

    if np.isinf(loudness_actuelle) or np.isnan(loudness_actuelle):
        logger.warning("Loudness non mesurable (silence ?) — normalisation ignorée.")
        return audio

    gain_db = cible_lufs - loudness_actuelle
    logger.info(
        "Normalisation LUFS : %.1f → %.1f dB (gain: %+.1f dB)",
        loudness_actuelle,
        cible_lufs,
        gain_db,
    )

    return audio.apply_gain(gain_db)


def _appliquer_pan(audio: AudioSegment, pan: float) -> AudioSegment:
    """Applique un panoramique stéréo à un segment audio.

    Args:
        audio: Segment audio (mono ou stéréo).
        pan: Valeur de -1.0 (gauche) à 1.0 (droite). 0.0 = centre.

    Returns:
        AudioSegment stéréo avec le panoramique appliqué.
    """
    if pan == 0.0:
        if audio.channels == 1:
            return audio.set_channels(2)
        return audio

    # Convertir en stéréo si nécessaire
    if audio.channels == 1:
        audio = audio.set_channels(2)

    return audio.pan(pan)


class Monteur:
    """Assemble les segments audio en un épisode final avec musique et jingles."""

    def assembler(
        self,
        script: dict,
        dossier_segments: Path | None = None,
        dossier_sortie: Path | None = None,
    ) -> dict:
        """Assemble un épisode complet à partir des segments et du script.

        Args:
            script: Script JSON validé (pour l'ordre des segments et les pauses).
            dossier_segments: Dossier contenant les segments MP3.
            dossier_sortie: Dossier de sortie pour l'épisode final.

        Returns:
            Dictionnaire avec les chemins des fichiers générés et la durée.
        """
        episode = script["episode"]
        episode_id = f"S{episode['saison']:02d}E{episode['numero']:02d}"

        segments_dir = dossier_segments or (config.SEGMENTS_DIR / episode_id)
        output_dir = dossier_sortie or config.OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Assemblage de l'épisode %s — %s", episode_id, episode["titre"])

        # 1. Charger et assembler les segments voix avec overlay SFX
        voix = self._assembler_segments(episode["segments"], segments_dir)
        logger.info("Segments voix assemblés : %.1f secondes", len(voix) / 1000.0)

        # 2. Charger les assets audio (jingles dynamiques par type d'épisode)
        type_episode = episode.get("type", "standard")
        intro = self._charger_jingle("intro", type_episode)
        outro = self._charger_jingle("outro", type_episode)

        # 3. Charger la musique de fond selon l'ambiance
        ambiance = episode.get("ambiance", "fond_doux")
        fond = self._charger_ambiance(ambiance)

        # 4. Préparer la musique de fond
        fond_ajuste = self._preparer_fond(fond, len(voix))

        # 5. Mixer voix + fond
        voix_avec_fond = voix.overlay(fond_ajuste)

        # 6. Assembler : intro → voix+fond → outro
        episode_complet = self._assembler_final(intro, voix_avec_fond, outro)

        # 7. Normaliser LUFS
        episode_complet = _normaliser_lufs(
            episode_complet, config.PRODUCTION["lufs_cible"]
        )

        # 8. Exporter
        nom_fichier = f"{episode_id}_{self._slug(episode['titre'])}"
        chemin_hq = output_dir / f"{nom_fichier}_192k.mp3"
        chemin_preview = output_dir / f"{nom_fichier}_128k.mp3"

        episode_complet.export(
            str(chemin_hq),
            format="mp3",
            bitrate=config.PRODUCTION["mp3_bitrate_final"],
        )
        episode_complet.export(
            str(chemin_preview),
            format="mp3",
            bitrate=config.PRODUCTION["mp3_bitrate_preview"],
        )

        duree_sec = len(episode_complet) / 1000.0
        logger.info("Épisode exporté : %s (%.0f sec)", chemin_hq, duree_sec)
        logger.info("Preview exporté : %s", chemin_preview)

        # 9. Générer les chapitres
        chapitres = self._generer_chapitres(episode["segments"], segments_dir)
        chemin_chapitres = config.CHAPTERS_DIR / f"{episode_id}_chapters.json"
        with open(chemin_chapitres, "w", encoding="utf-8") as f:
            json.dump(chapitres, f, ensure_ascii=False, indent=2)
        logger.info("Chapitres générés : %s", chemin_chapitres)

        return {
            "chemin_hq": chemin_hq,
            "chemin_preview": chemin_preview,
            "duree_secondes": duree_sec,
            "taille_bytes": chemin_hq.stat().st_size,
            "chapitres": chapitres,
            "chemin_chapitres": chemin_chapitres,
        }

    def _assembler_segments(
        self, segments: list[dict], dossier: Path
    ) -> AudioSegment:
        """Charge et concatène les segments audio (voix + SFX) avec les pauses.

        Gère les modes SFX :
        - "insert" : le SFX est inséré séquentiellement (ancien comportement).
        - "overlay" : le SFX est superposé aux segments voix suivants.
        """
        resultat = AudioSegment.empty()
        overlays_pending: list[AudioSegment] = []

        for seg in segments:
            chemin = dossier / f"{seg['id']}.mp3"
            if not chemin.exists():
                raise FileNotFoundError(
                    f"Segment audio introuvable : {chemin}"
                )

            audio = AudioSegment.from_mp3(str(chemin))

            if seg["personnage"] == "sfx":
                sfx_vol = config.SFX_CONFIG["sfx_volume_db"]
                fade_ms = config.SFX_CONFIG["sfx_fade_ms"]
                audio = audio.apply_gain(sfx_vol)
                if len(audio) > fade_ms * 2:
                    audio = audio.fade_in(fade_ms).fade_out(fade_ms)

                mode = seg.get("mode", "insert")
                if mode == "overlay":
                    overlays_pending.append(audio)
                    continue
                else:
                    pan = config.STEREO_PAN.get("sfx", 0.0)
                    audio = _appliquer_pan(audio, pan)
                    resultat += audio
            else:
                pan = config.STEREO_PAN.get(seg["personnage"], 0.0)
                audio = _appliquer_pan(audio, pan)

                # Appliquer les SFX overlay en attente
                if overlays_pending:
                    for sfx_overlay in overlays_pending:
                        if len(sfx_overlay) < len(audio):
                            sfx_overlay = sfx_overlay + AudioSegment.silent(
                                duration=len(audio) - len(sfx_overlay)
                            )
                        elif len(sfx_overlay) > len(audio):
                            sfx_overlay = sfx_overlay[:len(audio)]
                        sfx_overlay = _appliquer_pan(sfx_overlay, config.STEREO_PAN.get("sfx", 0.0))
                        audio = audio.overlay(sfx_overlay)
                    overlays_pending.clear()

                resultat += audio

            pause_ms = seg.get("pause_apres_ms", 0)
            if pause_ms > 0:
                resultat += AudioSegment.silent(duration=pause_ms)

        # Appliquer les overlays restants sur la fin du résultat
        if overlays_pending:
            logger.warning(
                "SFX overlay en fin de script sans segment voix suivant — "
                "insertion en séquentiel."
            )
            for sfx_overlay in overlays_pending:
                sfx_overlay = _appliquer_pan(sfx_overlay, config.STEREO_PAN.get("sfx", 0.0))
                resultat += sfx_overlay
            overlays_pending.clear()

        return resultat

    def _charger_jingle(self, position: str, type_episode: str) -> AudioSegment:
        """Charge un jingle adapté au type d'épisode.

        Cherche d'abord dans JINGLES_PAR_TYPE, puis fallback vers AUDIO_ASSETS.

        Args:
            position: "intro" ou "outro".
            type_episode: Type d'épisode (ouverture, standard, final, etc.).
        """
        jingles_type = config.JINGLES_PAR_TYPE.get(type_episode, {})
        chemin = jingles_type.get(position)
        if chemin and chemin.exists():
            logger.info("Jingle %s chargé pour type '%s' : %s", position, type_episode, chemin)
            return AudioSegment.from_mp3(str(chemin))

        # Fallback vers les jingles standards
        asset_nom = f"{position}_jingle"
        return self._charger_asset(asset_nom)

    def _charger_asset(self, nom: str) -> AudioSegment:
        """Charge un asset audio depuis le dossier assets."""
        chemin = config.AUDIO_ASSETS.get(nom)
        if not chemin or not chemin.exists():
            logger.warning(
                "Asset '%s' introuvable (%s) — utilisation d'un silence de remplacement.",
                nom,
                chemin,
            )
            duree = {
                "intro_jingle": config.PRODUCTION["intro_jingle_duree_ms"],
                "outro_jingle": config.PRODUCTION["outro_jingle_duree_ms"],
                "fond_doux": 60_000,
            }.get(nom, 5000)
            return AudioSegment.silent(duration=duree)

        return AudioSegment.from_mp3(str(chemin))

    def _charger_ambiance(self, ambiance: str) -> AudioSegment:
        """Charge la musique d'ambiance selon le type choisi par le scripteur.

        Fallback vers fond_doux si l'ambiance demandée n'existe pas.
        """
        chemin = config.AMBIANCES_MUSICALES.get(ambiance)
        if chemin and chemin.exists():
            logger.info("Ambiance musicale chargée : %s", ambiance)
            return AudioSegment.from_mp3(str(chemin))

        logger.warning(
            "Ambiance '%s' introuvable — fallback vers fond_doux.", ambiance
        )
        return self._charger_asset("fond_doux")

    def _preparer_fond(self, fond: AudioSegment, duree_voix_ms: int) -> AudioSegment:
        """Ajuste la musique de fond à la durée des voix avec le bon volume."""
        if len(fond) < duree_voix_ms:
            repetitions = (duree_voix_ms // len(fond)) + 1
            fond = fond * repetitions

        fond = fond[:duree_voix_ms]
        fond = fond + config.PRODUCTION["musique_fond_db"]
        fond = fond.fade_in(3000).fade_out(3000)

        if fond.channels == 1:
            fond = fond.set_channels(2)

        return fond

    def _assembler_final(
        self,
        intro: AudioSegment,
        voix_avec_fond: AudioSegment,
        outro: AudioSegment,
    ) -> AudioSegment:
        """Assemble intro + contenu + outro avec les transitions."""
        intro_duree = config.PRODUCTION["intro_jingle_duree_ms"]
        outro_duree = config.PRODUCTION["outro_jingle_duree_ms"]

        if len(intro) > intro_duree:
            intro = intro[:intro_duree]
        if len(outro) > outro_duree:
            outro = outro[:outro_duree]

        intro = intro.set_channels(2) if intro.channels == 1 else intro
        outro = outro.set_channels(2) if outro.channels == 1 else outro

        intro = intro.fade_out(1500)
        outro = outro.fade_in(1500)

        silence_transition = AudioSegment.silent(duration=500)

        return intro + silence_transition + voix_avec_fond + silence_transition + outro

    def _generer_chapitres(
        self, segments: list[dict], dossier: Path
    ) -> list[dict]:
        """Génère la liste de chapitres à partir des segments du script."""
        chapitres = []
        temps_courant_ms = 0

        for seg in segments:
            chemin = dossier / f"{seg['id']}.mp3"
            if chemin.exists():
                audio = AudioSegment.from_mp3(str(chemin))
                duree_ms = len(audio)
            else:
                duree_ms = seg.get("pause_apres_ms", 0)

            if seg["personnage"] == "narrateur" or not chapitres:
                chapitres.append({
                    "startTime": temps_courant_ms / 1000.0,
                    "title": seg["texte"][:80].rstrip(".") if seg["personnage"] != "sfx" else "Transition",
                })

            temps_courant_ms += duree_ms + seg.get("pause_apres_ms", 0)

        return chapitres

    @staticmethod
    def _slug(texte: str) -> str:
        """Convertit un texte en slug pour nom de fichier."""
        import re
        import unicodedata

        texte = unicodedata.normalize("NFKD", texte)
        texte = texte.encode("ascii", "ignore").decode("ascii")
        texte = re.sub(r"[^\w\s-]", "", texte).strip().lower()
        return re.sub(r"[-\s]+", "_", texte)
