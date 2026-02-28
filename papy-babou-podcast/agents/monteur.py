"""Agent Monteur — Assemble les segments audio en un épisode final."""

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

        # 1. Charger et assembler les segments voix
        voix = self._assembler_segments(episode["segments"], segments_dir)
        logger.info("Segments voix assemblés : %.1f secondes", len(voix) / 1000.0)

        # 2. Charger les assets audio
        intro = self._charger_asset("intro_jingle")
        outro = self._charger_asset("outro_jingle")
        fond = self._charger_asset("fond_doux")

        # 3. Préparer la musique de fond
        fond_ajuste = self._preparer_fond(fond, len(voix))

        # 4. Mixer voix + fond
        voix_avec_fond = voix.overlay(fond_ajuste)

        # 5. Assembler : intro → voix+fond → outro
        episode_complet = self._assembler_final(intro, voix_avec_fond, outro)

        # 6. Normaliser LUFS
        episode_complet = _normaliser_lufs(
            episode_complet, config.PRODUCTION["lufs_cible"]
        )

        # 7. Exporter
        nom_fichier = f"{episode_id}_{self._slug(episode['titre'])}"
        chemin_hq = output_dir / f"{nom_fichier}_320k.mp3"
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

        return {
            "chemin_hq": chemin_hq,
            "chemin_preview": chemin_preview,
            "duree_secondes": duree_sec,
            "taille_bytes": chemin_hq.stat().st_size,
        }

    def _assembler_segments(
        self, segments: list[dict], dossier: Path
    ) -> AudioSegment:
        """Charge et concatène les segments audio (voix + SFX) avec les pauses."""
        resultat = AudioSegment.empty()

        for seg in segments:
            chemin = dossier / f"{seg['id']}.mp3"
            if not chemin.exists():
                raise FileNotFoundError(
                    f"Segment audio introuvable : {chemin}"
                )

            audio = AudioSegment.from_mp3(str(chemin))

            # Ajuster le volume des SFX pour ne pas couvrir les voix
            if seg["personnage"] == "sfx":
                sfx_vol = config.SFX_CONFIG["sfx_volume_db"]
                fade_ms = config.SFX_CONFIG["sfx_fade_ms"]
                audio = audio.apply_gain(sfx_vol)
                if len(audio) > fade_ms * 2:
                    audio = audio.fade_in(fade_ms).fade_out(fade_ms)

            resultat += audio

            pause_ms = seg.get("pause_apres_ms", 0)
            if pause_ms > 0:
                resultat += AudioSegment.silent(duration=pause_ms)

        return resultat

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

    def _preparer_fond(self, fond: AudioSegment, duree_voix_ms: int) -> AudioSegment:
        """Ajuste la musique de fond à la durée des voix avec le bon volume.

        La musique est mise en boucle si nécessaire et réduite en volume.
        """
        # Boucler si la musique est plus courte que les voix
        if len(fond) < duree_voix_ms:
            repetitions = (duree_voix_ms // len(fond)) + 1
            fond = fond * repetitions

        # Couper à la bonne longueur
        fond = fond[:duree_voix_ms]

        # Réduire le volume
        fond = fond + config.PRODUCTION["musique_fond_db"]

        # Fade in au début, fade out à la fin
        fond = fond.fade_in(3000).fade_out(3000)

        return fond

    def _assembler_final(
        self,
        intro: AudioSegment,
        voix_avec_fond: AudioSegment,
        outro: AudioSegment,
    ) -> AudioSegment:
        """Assemble intro + contenu + outro avec les transitions."""
        # Ajuster les durées des jingles
        intro_duree = config.PRODUCTION["intro_jingle_duree_ms"]
        outro_duree = config.PRODUCTION["outro_jingle_duree_ms"]

        if len(intro) > intro_duree:
            intro = intro[:intro_duree]
        if len(outro) > outro_duree:
            outro = outro[:outro_duree]

        # Transitions douces
        intro = intro.fade_out(1500)
        outro = outro.fade_in(1500)

        # Petite pause entre les parties
        silence_transition = AudioSegment.silent(duration=500)

        return intro + silence_transition + voix_avec_fond + silence_transition + outro

    @staticmethod
    def _slug(texte: str) -> str:
        """Convertit un texte en slug pour nom de fichier."""
        import re
        import unicodedata

        texte = unicodedata.normalize("NFKD", texte)
        texte = texte.encode("ascii", "ignore").decode("ascii")
        texte = re.sub(r"[^\w\s-]", "", texte).strip().lower()
        return re.sub(r"[-\s]+", "_", texte)
