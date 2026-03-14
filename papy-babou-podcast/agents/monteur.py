"""Agent Monteur — Assemble les segments audio en un épisode final."""

import json
import logging
import random
import time
from pathlib import Path

import numpy as np
import requests
import soundfile as sf
from pydub import AudioSegment

import config
from utils import slug as _slug_util

logger = logging.getLogger(__name__)

# ── Prompts pour la génération automatique des assets audio ──────────────────

ELEVENLABS_SFX_URL = "https://api.elevenlabs.io/v1/sound-generation"

# Descriptions ElevenLabs pour les jingles
JINGLE_PROMPTS = {
    "intro_jingle": (
        "Warm cheerful children's podcast intro jingle, acoustic guitar "
        "and soft bells, inviting and magical, French storytelling mood"
    ),
    "outro_jingle": (
        "Gentle children's podcast outro jingle, soft music box and light "
        "harp, warm goodbye feeling, soothing and peaceful ending"
    ),
    "intro_saison": (
        "Epic and warm children's podcast season opening jingle, orchestral "
        "with gentle bells, magical adventure beginning, French fairy tale mood"
    ),
    "outro_saison": (
        "Emotional children's podcast season finale outro, gentle piano and "
        "strings, warm and nostalgic, hopeful ending, soft and magical"
    ),
}

# Descriptions ElevenLabs pour les ambiances musicales
AMBIANCE_PROMPTS = {
    "joyeux": "Happy cheerful background music loop for children's podcast, light acoustic guitar and ukulele, playful and warm",
    "dramatique": "Dramatic soft background music for children's storytelling, gentle tension with strings and low piano, not scary",
    "calme": "Calm peaceful background music for children's podcast, soft piano and nature sounds, relaxing and gentle",
    "mystere": "Mysterious gentle background music for children's storytelling, soft woodwinds and light celesta, curious and magical",
    "epique": "Epic adventure background music for children's podcast, orchestral with gentle drums and brass, heroic but not loud",
    "tendre": "Tender warm background music for children's podcast, soft strings and piano, emotional and gentle, lullaby-like",
    "humoristique": "Fun playful background music for children's podcast, pizzicato strings and light percussion, whimsical and bouncy",
    "solennel": "Solemn reverent background music for children's religious storytelling, soft organ and choir, peaceful and sacred",
    "fond_doux": "Soft gentle ambient background music for children's podcast, very quiet warm pads and light harp, barely noticeable",
}

# Constantes audio (en ms sauf mention contraire)
FADE_JINGLE_MS = 1500          # Durée du fade in/out pour les jingles
SILENCE_TRANSITION_MS = 300     # Silence entre jingle et contenu (réduit de 500)
FADE_AMBIANCE_MS = 3000         # Durée du fade in/out pour la musique de fond
FALLBACK_ASSET_DUREE_MS = 5000  # Durée du silence de remplacement d'un asset manquant
CROSSFADE_VOIX_MS = 50          # Léger crossfade entre segments voix pour transitions douces
MAX_PAUSE_MS = 2500             # Plafond de pause pour éviter les silences excessifs


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


def _titre_chapitre_semantique(
    num: int,
    segment: dict,
    segments_suivants: list[dict],
    nb_total: int,
) -> str:
    """Génère un titre de chapitre sémantique basé sur le contenu narratif.

    Au lieu de tronquer le texte du segment, analyse le contexte pour
    produire un titre court et évocateur.

    Args:
        num: Numéro du chapitre (1-based).
        segment: Segment qui ouvre le chapitre.
        segments_suivants: Les 5 prochains segments pour contexte.
        nb_total: Nombre total de segments dans l'épisode.
    """
    # Premier chapitre = ouverture
    if num == 1:
        if segment["personnage"] == "papy_babou":
            # Extraire un thème de l'accroche de Papy
            texte = segment["texte"]
            if len(texte) > 60:
                # Chercher une phrase courte au début
                for sep in (".", "!", "?", "..."):
                    idx = texte.find(sep)
                    if 10 < idx < 60:
                        return texte[:idx + 1]
            return texte[:60].rstrip(" ,;")
        return "Bienvenue chez Papy Babou"

    # Analyser le contenu des segments suivants pour deviner le thème
    textes = [
        s["texte"] for s in segments_suivants
        if s["personnage"] != "sfx" and s.get("texte")
    ]
    contexte = " ".join(textes)[:200].lower()

    # Détecter des patterns narratifs
    if any(mot in contexte for mot in ("peur", "effray", "trembl", "inquiet", "danger")):
        return "L'épreuve"
    if any(mot in contexte for mot in ("miracle", "incroyable", "prodige", "merveill")):
        return "Le miracle"
    if any(mot in contexte for mot in ("pardon", "désolé", "regrette", "réconcili")):
        return "Le pardon"
    if any(mot in contexte for mot in ("voyage", "chemin", "marche", "traversé", "désert")):
        return "Le voyage"
    if any(mot in contexte for mot in ("promesse", "alliance", "serment")):
        return "La promesse"
    if any(mot in contexte for mot in ("leçon", "morale", "compris", "retenir")):
        return "La leçon de Papy"

    # Fallback : extraire le début de la première phrase pertinente
    texte = segment["texte"]
    for sep in (".", "!", "?"):
        idx = texte.find(sep)
        if 10 < idx < 60:
            return texte[:idx + 1]

    return texte[:60].rstrip(" ,;")


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
        nom_fichier = f"{episode_id}_{_slug_util(episode['titre'])}"
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
                # Remplacement par du silence au lieu de crash (BUG 11)
                if seg["personnage"] == "sfx":
                    duree_ms = int(seg.get("duree_sfx_secondes", 5.0) * 1000)
                else:
                    nb_mots = len(seg.get("texte", "").split())
                    duree_ms = max(int((nb_mots / 110) * 60 * 1000), 1000)
                logger.warning(
                    "Segment audio introuvable : %s — remplacement par %dms de silence.",
                    chemin, duree_ms,
                )
                audio = AudioSegment.silent(duration=duree_ms)
            else:
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
                            logger.warning(
                                "SFX overlay tronqué de %.1fs à %.1fs "
                                "(segment voix trop court).",
                                len(sfx_overlay) / 1000.0, len(audio) / 1000.0,
                            )
                            sfx_overlay = sfx_overlay[:len(audio)]
                        sfx_overlay = _appliquer_pan(sfx_overlay, config.STEREO_PAN.get("sfx", 0.0))
                        audio = audio.overlay(sfx_overlay)
                    overlays_pending.clear()

                # Crossfade entre segments voix pour transitions plus naturelles
                if (len(resultat) > CROSSFADE_VOIX_MS
                        and len(audio) > CROSSFADE_VOIX_MS):
                    resultat = resultat.append(audio, crossfade=CROSSFADE_VOIX_MS)
                else:
                    resultat += audio

            pause_ms = seg.get("pause_apres_ms", 0)
            # Plafonner les pauses excessives
            if pause_ms > MAX_PAUSE_MS:
                logger.debug("Pause plafonnée de %dms à %dms", pause_ms, MAX_PAUSE_MS)
                pause_ms = MAX_PAUSE_MS
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

    def _generer_asset_elevenlabs(
        self, description: str, duree_seconds: float, chemin_sortie: Path
    ) -> bool:
        """Génère un asset audio via ElevenLabs SFX API et le sauvegarde.

        Args:
            description: Prompt décrivant le son à générer.
            duree_seconds: Durée souhaitée (max 22s par appel).
            chemin_sortie: Chemin de sauvegarde du fichier MP3.

        Returns:
            True si la génération a réussi.
        """
        api_key = config.ELEVENLABS_API_KEY
        if not api_key:
            logger.warning("Clé ElevenLabs manquante — impossible de générer '%s'",
                           chemin_sortie.name)
            return False

        duree = min(duree_seconds, 22.0)
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": description,
            "duration_seconds": duree,
            "prompt_influence": 0.7,
        }

        max_tentatives = config.PRODUCTION.get("max_retry_tts", 3)

        for tentative in range(1, max_tentatives + 1):
            try:
                config.rate_limiter_elevenlabs.attendre()
                response = requests.post(
                    ELEVENLABS_SFX_URL,
                    json=payload,
                    headers=headers,
                    timeout=60,
                )
                response.raise_for_status()

                chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
                with open(chemin_sortie, "wb") as f:
                    f.write(response.content)

                logger.info(
                    "Asset audio généré via ElevenLabs : %s (%.1f KB, %.1fs)",
                    chemin_sortie.name,
                    len(response.content) / 1024,
                    duree,
                )
                return True

            except requests.RequestException as e:
                logger.warning(
                    "ElevenLabs asset tentative %d/%d échouée pour '%s' : %s",
                    tentative, max_tentatives, chemin_sortie.name, e,
                )
                if tentative < max_tentatives:
                    delai = (2 ** tentative) + random.uniform(0, 1)
                    time.sleep(delai)

        return False

    def _charger_jingle(self, position: str, type_episode: str) -> AudioSegment:
        """Charge un jingle adapté au type d'épisode.

        Cherche d'abord dans JINGLES_PAR_TYPE, puis fallback vers AUDIO_ASSETS.
        Si aucun fichier n'existe, génère automatiquement via ElevenLabs.

        Args:
            position: "intro" ou "outro".
            type_episode: Type d'épisode (ouverture, standard, final, etc.).
        """
        # 1. Chercher le jingle spécifique au type d'épisode
        jingles_type = config.JINGLES_PAR_TYPE.get(type_episode, {})
        chemin = jingles_type.get(position)
        if chemin and chemin.exists():
            logger.info("Jingle %s chargé pour type '%s' : %s", position, type_episode, chemin)
            return AudioSegment.from_mp3(str(chemin))

        # 2. Fallback vers les jingles standards
        asset_nom = f"{position}_jingle"
        chemin_standard = config.AUDIO_ASSETS.get(asset_nom)
        if chemin_standard and chemin_standard.exists():
            return AudioSegment.from_mp3(str(chemin_standard))

        # 3. Auto-génération via ElevenLabs si le fichier n'existe pas
        # Déterminer le bon prompt et le chemin de cache
        if chemin:
            # Utiliser le chemin JINGLES_PAR_TYPE comme destination
            prompt_key = f"{position}_saison" if "saison" in str(chemin) else asset_nom
        else:
            chemin = chemin_standard or (config.ASSETS_DIR / "music" / f"{asset_nom}.mp3")
            prompt_key = asset_nom

        prompt = JINGLE_PROMPTS.get(prompt_key, JINGLE_PROMPTS.get(asset_nom, ""))
        if prompt:
            duree_ms_key = f"{position}_jingle_duree_ms"
            duree_s = config.PRODUCTION.get(duree_ms_key, 10_000) / 1000.0
            if self._generer_asset_elevenlabs(prompt, duree_s, chemin):
                return AudioSegment.from_mp3(str(chemin))

        # 4. Dernier recours : silence
        logger.warning("Jingle %s introuvable et non générable — silence.", position)
        duree_fallback = config.PRODUCTION.get(
            f"{position}_jingle_duree_ms", 10_000
        )
        return AudioSegment.silent(duration=duree_fallback)

    def _charger_asset(self, nom: str) -> AudioSegment:
        """Charge un asset audio depuis le dossier assets.

        Si le fichier est absent, tente la génération via ElevenLabs.
        """
        chemin = config.AUDIO_ASSETS.get(nom)
        if chemin and chemin.exists():
            return AudioSegment.from_mp3(str(chemin))

        # Tenter la génération automatique
        prompt = JINGLE_PROMPTS.get(nom) or AMBIANCE_PROMPTS.get(nom)
        if prompt and chemin:
            duree = {
                "intro_jingle": config.PRODUCTION["intro_jingle_duree_ms"] / 1000.0,
                "outro_jingle": config.PRODUCTION["outro_jingle_duree_ms"] / 1000.0,
                "fond_doux": 22.0,  # Max ElevenLabs, sera bouclé par _preparer_fond
            }.get(nom, 10.0)
            if self._generer_asset_elevenlabs(prompt, duree, chemin):
                return AudioSegment.from_mp3(str(chemin))

        logger.warning(
            "Asset '%s' introuvable et non générable — silence de remplacement.",
            nom,
        )
        duree_ms = {
            "intro_jingle": config.PRODUCTION["intro_jingle_duree_ms"],
            "outro_jingle": config.PRODUCTION["outro_jingle_duree_ms"],
            "fond_doux": 60_000,
        }.get(nom, FALLBACK_ASSET_DUREE_MS)
        return AudioSegment.silent(duration=duree_ms)

    def _charger_ambiance(self, ambiance: str) -> AudioSegment:
        """Charge la musique d'ambiance selon le type choisi par le scripteur.

        Si le fichier est absent, génère automatiquement via ElevenLabs.
        Fallback vers fond_doux si l'ambiance demandée n'existe pas.
        """
        chemin = config.AMBIANCES_MUSICALES.get(ambiance)
        if chemin and chemin.exists():
            logger.info("Ambiance musicale chargée : %s", ambiance)
            return AudioSegment.from_mp3(str(chemin))

        # Tenter la génération automatique de l'ambiance demandée
        prompt = AMBIANCE_PROMPTS.get(ambiance)
        if prompt and chemin:
            if self._generer_asset_elevenlabs(prompt, 22.0, chemin):
                logger.info("Ambiance '%s' générée via ElevenLabs", ambiance)
                return AudioSegment.from_mp3(str(chemin))

        # Fallback vers fond_doux
        if ambiance != "fond_doux":
            logger.warning(
                "Ambiance '%s' introuvable et non générée — fallback vers fond_doux.",
                ambiance,
            )
            return self._charger_asset("fond_doux")

        # Dernier recours : silence
        logger.warning("Aucune musique de fond disponible — silence.")
        return AudioSegment.silent(duration=60_000)

    def _preparer_fond(self, fond: AudioSegment, duree_voix_ms: int) -> AudioSegment:
        """Ajuste la musique de fond à la durée des voix avec le bon volume."""
        if len(fond) == 0:
            logger.warning("Musique de fond vide — remplacement par du silence.")
            fond = AudioSegment.silent(duration=max(duree_voix_ms, 1))
        elif len(fond) < duree_voix_ms:
            repetitions = (duree_voix_ms // len(fond)) + 1
            fond = fond * repetitions

        fond = fond[:duree_voix_ms]
        fond = fond + config.PRODUCTION["musique_fond_db"]
        fond = fond.fade_in(FADE_AMBIANCE_MS).fade_out(FADE_AMBIANCE_MS)

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

        intro = intro.fade_out(FADE_JINGLE_MS)
        outro = outro.fade_in(FADE_JINGLE_MS)

        silence_transition = AudioSegment.silent(duration=SILENCE_TRANSITION_MS)

        return intro + silence_transition + voix_avec_fond + silence_transition + outro

    def _generer_chapitres(
        self, segments: list[dict], dossier: Path
    ) -> list[dict]:
        """Génère la liste de chapitres à partir des segments du script.

        Utilise des titres sémantiques basés sur la structure narrative
        plutôt que du texte tronqué.
        """
        chapitres = []
        # Offset initial : intro jingle + silence transition
        intro_ms = config.PRODUCTION["intro_jingle_duree_ms"]
        temps_courant_ms = intro_ms + SILENCE_TRANSITION_MS

        # Identifier les chapitres logiques (max 5-7 chapitres)
        nb_segments_depuis_chapitre = 0
        chapitre_num = 0

        for i, seg in enumerate(segments):
            chemin = dossier / f"{seg['id']}.mp3"
            if chemin.exists():
                audio = AudioSegment.from_mp3(str(chemin))
                duree_ms = len(audio)
            else:
                if seg["personnage"] == "sfx":
                    duree_ms = int(seg.get("duree_sfx_secondes", 5.0) * 1000)
                else:
                    nb_mots = len(seg.get("texte", "").split())
                    duree_ms = max(int((nb_mots / 110) * 60 * 1000), 1000)

            # Créer un chapitre si :
            # - C'est le premier segment
            # - C'est un narrateur ET il y a eu 8+ segments depuis le dernier chapitre
            # - Il y a eu un SFX juste avant ce narrateur
            creer_chapitre = False
            if not chapitres:
                creer_chapitre = True
            elif seg["personnage"] == "narrateur" and nb_segments_depuis_chapitre >= 8:
                creer_chapitre = True
            elif (seg["personnage"] == "narrateur"
                  and i > 0
                  and segments[i - 1]["personnage"] == "sfx"
                  and nb_segments_depuis_chapitre >= 4):
                creer_chapitre = True

            if creer_chapitre and seg["personnage"] != "sfx":
                chapitre_num += 1
                titre_chapitre = _titre_chapitre_semantique(
                    chapitre_num, seg, segments[i:i + 5], len(segments),
                )
                chapitres.append({
                    "startTime": temps_courant_ms / 1000.0,
                    "title": titre_chapitre,
                })
                nb_segments_depuis_chapitre = 0
            else:
                nb_segments_depuis_chapitre += 1

            temps_courant_ms += duree_ms + seg.get("pause_apres_ms", 0)

        return chapitres

    @staticmethod
    def _slug(texte: str) -> str:
        """Convertit un texte en slug pour nom de fichier."""
        return _slug_util(texte)
