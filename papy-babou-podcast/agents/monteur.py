"""Agent Monteur — Assemble les segments audio en un épisode final."""

import json
import logging
import os
import random
import tempfile
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

# Prompt pour la transition sonore entre actes narratifs
TRANSITION_PROMPT = (
    "Short magical transition sound for children's storytelling podcast, "
    "soft chime and gentle harp glissando, page turning feeling, 2 seconds"
)

# Prompt pour le générique signature récurrent (identique à chaque épisode)
SIGNATURE_JINGLE_PROMPT = (
    "Very short 5-second signature jingle for children's podcast, "
    "distinctive warm melody with music box and soft bells, "
    "recognizable and catchy, French fairy tale atmosphere"
)

# Constantes audio (en ms sauf mention contraire)
FADE_JINGLE_MS = 1500          # Durée du fade in/out pour les jingles
SILENCE_TRANSITION_MS = 300     # Silence entre jingle et contenu (réduit de 500)
FADE_AMBIANCE_MS = 3000         # Durée du fade in/out pour la musique de fond
FALLBACK_ASSET_DUREE_MS = 5000  # Durée du silence de remplacement d'un asset manquant
CROSSFADE_VOIX_MS = 200         # Crossfade entre segments voix pour transitions naturelles
MAX_PAUSE_MS = 2500             # Plafond de pause pour éviter les silences excessifs
RESPIRATION_DUREE_MS = 80       # Durée micro-respiration entre certaines répliques
RESPIRATION_PROBABILITE = 0.35  # 35% des transitions voix incluent une micro-respiration
DUCKING_GAIN_DB = -6            # Atténuation voix pendant un SFX overlay (side-chain)
DUCKING_FADE_MS = 150           # Durée du fade pour l'entrée/sortie du ducking

# Volume SFX contextuel selon le ton du segment précédent
SFX_VOLUME_PAR_TON = {
    "dramatique": -3,
    "epique": -3,
    "solennel": -4,
    "mystere": -5,
    "tendre": -8,
    "calme": -9,
    "joyeux": -5,
    "humoristique": -5,
}
SFX_VOLUME_DEFAUT = -6          # Volume SFX par défaut si pas de ton contextuel

# Room tone — fond sonore continu simulant le salon de Papy Babou
ROOM_TONE_PROMPTS = {
    "defaut": (
        "Gentle cozy living room ambiance, soft fireplace crackling, "
        "distant clock ticking, very subtle warm room tone, barely audible, "
        "French countryside house atmosphere"
    ),
    "soir": (
        "Evening cozy living room ambiance, warm fireplace crackling louder, "
        "soft rain on windows, distant clock ticking, very subtle, "
        "French countryside house at night"
    ),
    "jour": (
        "Daytime cozy living room ambiance, distant birds singing softly, "
        "gentle breeze through open window, very subtle warm room tone, "
        "French countryside house in the morning"
    ),
    "orage": (
        "Cozy living room during a storm, distant thunder rumbles, "
        "rain on windows, fireplace crackling warmly, very subtle, "
        "safe and warm French countryside house"
    ),
}
# Keep backward-compatible alias
ROOM_TONE_PROMPT = ROOM_TONE_PROMPTS["defaut"]
ROOM_TONE_DB = -28              # Volume très bas pour le room tone

# Mapping ambiance → type de room tone
AMBIANCE_ROOM_TONE = {
    "calme": "soir",
    "tendre": "soir",
    "solennel": "soir",
    "dramatique": "orage",
    "epique": "jour",
    "joyeux": "jour",
    "humoristique": "jour",
    "mystere": "soir",
    "fond_doux": "defaut",
}

# EQ boost médiums — fréquences de coupure pour le filtre passe-bande (Hz)
EQ_VOICE_BOOST_LOW_HZ = 2000    # Borne basse du boost voix
EQ_VOICE_BOOST_HIGH_HZ = 5000   # Borne haute du boost voix
EQ_VOICE_BOOST_DB = 2.5         # Gain du boost en dB

# True peak limiter — facteur d'oversampling
TRUE_PEAK_OVERSAMPLE = 4        # 4x oversampling pour détection inter-sample


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

        # ── Checkpoint intermédiaire : si un WAV pré-assemblé existe, skip étapes 1-8 ──
        # Cela permet de survivre aux recyclages de container Replit pendant le montage.
        # Après les étapes 1-8 (assemblage + master bus + LUFS), on sauvegarde un WAV
        # temporaire. Sur resume, si ce fichier existe, on va directement à l'export MP3.
        nom_fichier = f"{episode_id}_{_slug_util(episode['titre'])}"
        chemin_wav_intermediaire = output_dir / f"{nom_fichier}_pre_export.wav"

        if chemin_wav_intermediaire.exists():
            # I2: Valider l'intégrité du WAV avant de l'utiliser
            # Un container kill pendant l'export WAV laisse un fichier tronqué.
            try:
                _wav_size = chemin_wav_intermediaire.stat().st_size
                if _wav_size < 1000:  # WAV header = 44 bytes min, silence ~100KB
                    raise ValueError(f"WAV trop petit ({_wav_size} bytes)")
                episode_complet = AudioSegment.from_wav(str(chemin_wav_intermediaire))
                if len(episode_complet) < 10000:  # < 10 secondes = corrompu
                    raise ValueError(f"WAV trop court ({len(episode_complet)}ms)")
                logger.info(
                    "  WAV intermédiaire trouvé — skip étapes 1-8, reprise à l'export (%.1fs)",
                    len(episode_complet) / 1000.0,
                )
            except Exception as e_wav_load:
                logger.warning(
                    "WAV intermédiaire corrompu (%s) — régénération complète", e_wav_load,
                )
                chemin_wav_intermediaire.unlink(missing_ok=True)
                # Laisser tomber dans le else ci-dessous (pas de variable episode_complet)
                episode_complet = None

        if episode_complet is None:
            # 1. Charger et assembler les segments voix avec overlay SFX et transitions
            logger.info("  [1/9] Assemblage des %d segments voix...", len(episode["segments"]))
            transition = self._charger_transition()
            voix = self._assembler_segments(episode["segments"], segments_dir, transition)
            logger.info("  [1/9] Segments voix assemblés : %.1f secondes", len(voix) / 1000.0)

            # 2. Charger les assets audio (jingles dynamiques par type d'épisode)
            logger.info("  [2/9] Chargement des jingles...")
            type_episode = episode.get("type", "standard")
            numero_saison = episode.get("saison")
            intro = self._charger_jingle("intro", type_episode, numero_saison)
            outro = self._charger_jingle("outro", type_episode, numero_saison)

            # 3. Charger la musique de fond selon l'ambiance (dynamique par acte si dispo)
            logger.info("  [3/9] Chargement musique de fond...")
            ambiance_par_acte = episode.get("ambiance_par_acte")
            ambiance_principale = episode.get("ambiance", "fond_doux")

            if ambiance_par_acte and isinstance(ambiance_par_acte, list) and len(ambiance_par_acte) > 1:
                voix_avec_fond = self._mixer_ambiance_dynamique(
                    voix, ambiance_par_acte, episode["segments"],
                )
                logger.info(
                    "Ambiance dynamique par acte : %s",
                    " → ".join(ambiance_par_acte),
                )
            else:
                fond = self._charger_ambiance(ambiance_principale)
                fond_ajuste = self._preparer_fond(fond, len(voix))
                voix_avec_fond = voix.overlay(fond_ajuste)

            # 5. Room tone continu adapté à l'ambiance (A1 + adaptatif)
            logger.info("  [5/9] Chargement room tone...")
            room_tone = self._charger_room_tone(ambiance_principale)
            if len(room_tone) > 0:
                room_tone = room_tone.apply_gain(ROOM_TONE_DB)
                if room_tone.channels == 1:
                    room_tone = room_tone.set_channels(2)
                # Boucler le room tone sur toute la durée
                if len(room_tone) < len(voix_avec_fond):
                    repetitions = (len(voix_avec_fond) // len(room_tone)) + 1
                    room_tone = room_tone * repetitions
                room_tone = room_tone[:len(voix_avec_fond)]
                room_tone = room_tone.fade_in(2000).fade_out(2000)
                voix_avec_fond = voix_avec_fond.overlay(room_tone)
                logger.info("Room tone appliqué sur %.1fs", len(voix_avec_fond) / 1000.0)

            # 6. Assembler : intro → voix+fond → outro
            logger.info("  [6/9] Assemblage final (intro + voix + outro)...")
            episode_complet = self._assembler_final(intro, voix_avec_fond, outro)

            # 7. Traitement master bus (A4)
            logger.info("  [7/9] Traitement master bus (EQ + compression + limiter)...")
            episode_complet = self._appliquer_master_bus(episode_complet)

            # 8. Normaliser LUFS
            logger.info("  [8/9] Normalisation LUFS...")
            episode_complet = _normaliser_lufs(
                episode_complet, config.PRODUCTION["lufs_cible"]
            )

            # ── Sauvegarder le WAV intermédiaire (checkpoint montage) ──
            # I1: Export ATOMIQUE — tempfile + os.replace empêche les WAV tronqués
            # si le container est recyclé pendant l'écriture.
            logger.info("  Sauvegarde WAV intermédiaire (checkpoint montage)...")
            try:
                with tempfile.NamedTemporaryFile(
                    dir=str(output_dir), suffix=".wav", delete=False,
                ) as tmp_wav:
                    tmp_wav_path = Path(tmp_wav.name)
                episode_complet.export(str(tmp_wav_path), format="wav")
                os.replace(str(tmp_wav_path), str(chemin_wav_intermediaire))
            except Exception:
                # Nettoyer le fichier temporaire en cas d'erreur
                try:
                    tmp_wav_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise
            # Upload vers Object Storage pour survivre aux redeploys
            try:
                import persistent_storage
                persistent_storage.upload_file(
                    persistent_storage.PREFIX_MONTAGE_WAV + f"{episode_id}_pre_export.wav",
                    chemin_wav_intermediaire,
                )
                logger.info("  WAV intermédiaire uploadé en Object Storage")
            except Exception as e_wav:
                logger.warning("Upload WAV intermédiaire échoué : %s", e_wav)

        # 9. Exporter
        logger.info("  [9/9] Export MP3 HQ + preview...")
        chemin_hq = output_dir / f"{nom_fichier}_192k.mp3"
        chemin_preview = output_dir / f"{nom_fichier}_128k.mp3"

        episode_complet.export(
            str(chemin_hq),
            format="mp3",
            bitrate=config.PRODUCTION["mp3_bitrate_final"],
        )
        logger.info("  Export HQ terminé : %s", chemin_hq)
        episode_complet.export(
            str(chemin_preview),
            format="mp3",
            bitrate=config.PRODUCTION["mp3_bitrate_preview"],
        )

        duree_sec = len(episode_complet) / 1000.0
        logger.info("Épisode exporté : %s (%.0f sec)", chemin_hq, duree_sec)
        logger.info("Preview exporté : %s", chemin_preview)

        # I6: Nettoyer le WAV intermédiaire (plus nécessaire après export réussi)
        try:
            if chemin_wav_intermediaire.exists():
                chemin_wav_intermediaire.unlink()
        except OSError as e_cleanup:
            logger.warning("Nettoyage WAV intermédiaire échoué : %s", e_cleanup)

        # 10. Générer les chapitres
        type_episode = episode.get("type", "standard")
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
        self, segments: list[dict], dossier: Path,
        transition: AudioSegment | None = None,
    ) -> AudioSegment:
        """Charge et concatène les segments audio (voix + SFX) avec les pauses.

        Gère les modes SFX :
        - "insert" : le SFX est inséré séquentiellement (ancien comportement).
        - "overlay" : le SFX est superposé aux segments voix suivants.

        Insère des transitions sonores entre actes (quand papy_babou reprend
        après un bloc de 8+ segments ou un SFX marqueur).
        """
        resultat = AudioSegment.empty()
        overlays_pending: list[AudioSegment] = []
        prev_personnage: str = ""
        segments_depuis_transition: int = 0

        dernier_ton: str = ""
        total_segments = len(segments)

        for i, seg in enumerate(segments):
            # Log de progression tous les 20 segments (visible en temps réel)
            if i > 0 and i % 20 == 0:
                logger.info(
                    "  Montage segment %d/%d (%.0f%%)",
                    i, total_segments, 100.0 * i / total_segments,
                )
            # Transition sonore entre actes narratifs
            # Déclenchement : papy_babou après 8+ segments OU après un SFX marqueur
            est_transition_acte = (
                transition is not None
                and len(resultat) > 0
                and segments_depuis_transition >= 8
                and (
                    seg["personnage"] == "papy_babou"
                    or (i > 0 and segments[i - 1]["personnage"] == "sfx"
                        and seg["personnage"] != "sfx")
                )
            )
            if est_transition_acte:
                trans = transition.apply_gain(-8)  # Très discret
                if trans.channels == 1:
                    trans = trans.set_channels(2)
                resultat += trans
                segments_depuis_transition = 0
                logger.debug("Transition entre actes insérée à %.1fs", len(resultat) / 1000.0)

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
                # Volume SFX contextuel selon le ton du segment précédent (A8)
                sfx_vol = SFX_VOLUME_PAR_TON.get(dernier_ton, SFX_VOLUME_DEFAUT)
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

                # Appliquer les SFX overlay avec ducking voix (A2)
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
                        # Side-chain ducking : baisser la voix pendant le SFX
                        audio = self._appliquer_ducking(audio, sfx_overlay)
                    overlays_pending.clear()

                # Mémoriser le ton pour le volume SFX contextuel
                dernier_ton = seg.get("ton", "")

                # Micro-respiration naturelle entre certaines répliques
                if (len(resultat) > 0
                        and random.random() < RESPIRATION_PROBABILITE
                        and seg["personnage"] != prev_personnage):
                    resultat += self._generer_micro_respiration()

                # Crossfade entre segments voix pour transitions plus naturelles
                if (len(resultat) > CROSSFADE_VOIX_MS
                        and len(audio) > CROSSFADE_VOIX_MS):
                    resultat = resultat.append(audio, crossfade=CROSSFADE_VOIX_MS)
                else:
                    resultat += audio

                prev_personnage = seg["personnage"]

            # Ajuster la pause selon l'indication de rythme du segment
            rythme = seg.get("rythme", "normal")
            pause_ms = seg.get("pause_apres_ms", 0)
            if rythme == "rapide":
                pause_ms = int(pause_ms * 0.6)
            elif rythme == "lent":
                pause_ms = int(pause_ms * 1.5)

            # Plafonner les pauses excessives
            if pause_ms > MAX_PAUSE_MS:
                logger.debug("Pause plafonnée de %dms à %dms", pause_ms, MAX_PAUSE_MS)
                pause_ms = MAX_PAUSE_MS
            if pause_ms > 0:
                resultat += AudioSegment.silent(duration=pause_ms)

            segments_depuis_transition += 1

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

    def _charger_jingle(
        self, position: str, type_episode: str,
        numero_saison: int | None = None,
    ) -> AudioSegment:
        """Charge un jingle adapté au type d'épisode.

        Ordre de priorité :
        0. Jingle custom de la saison (choisi par le producteur).
        1. JINGLES_PAR_TYPE (spécifique au type d'épisode).
        2. AUDIO_ASSETS (jingle standard).
        3. Auto-génération via ElevenLabs.
        4. Silence.

        Args:
            position: "intro" ou "outro".
            type_episode: Type d'épisode (ouverture, standard, final, etc.).
            numero_saison: Numéro de saison pour chercher les jingles custom.
        """
        # 0. Jingle custom de la saison (priorité absolue)
        if numero_saison is not None:
            custom_key = f"{position}_saison"
            custom_jingles = config.jingles_saison(numero_saison)
            chemin_custom = custom_jingles.get(custom_key)
            if chemin_custom:
                logger.info(
                    "Jingle %s custom de la saison %d : %s",
                    position, numero_saison, chemin_custom,
                )
                return AudioSegment.from_mp3(str(chemin_custom))

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

    def _mixer_ambiance_dynamique(
        self,
        voix: AudioSegment,
        ambiances: list[str],
        segments: list[dict],
    ) -> AudioSegment:
        """Mixe le fond sonore en changeant d'ambiance selon les actes.

        Divise la piste voix en N sections égales (une par ambiance) et
        charge un fond différent pour chaque section avec un crossfade
        de 2 secondes entre les ambiances.
        """
        nb_actes = len(ambiances)
        duree_totale = len(voix)
        duree_par_acte = duree_totale // nb_actes
        crossfade_amb = 2000  # 2 secondes de crossfade entre ambiances

        resultat = AudioSegment.empty()
        for i, ambiance in enumerate(ambiances):
            debut = i * duree_par_acte
            fin = (i + 1) * duree_par_acte if i < nb_actes - 1 else duree_totale
            section_voix = voix[debut:fin]

            fond = self._charger_ambiance(ambiance)
            fond_ajuste = self._preparer_fond(fond, len(section_voix))
            section_mixee = section_voix.overlay(fond_ajuste)

            # Crossfade entre sections pour transition douce
            if len(resultat) > crossfade_amb and len(section_mixee) > crossfade_amb:
                resultat = resultat.append(section_mixee, crossfade=crossfade_amb)
            else:
                resultat += section_mixee

        return resultat

    def _charger_transition(self) -> AudioSegment:
        """Charge ou génère un son de transition entre actes narratifs."""
        chemin = config.ASSETS_DIR / "music" / "transition_acte.mp3"
        if chemin.exists():
            return AudioSegment.from_mp3(str(chemin))

        if self._generer_asset_elevenlabs(TRANSITION_PROMPT, 2.0, chemin):
            return AudioSegment.from_mp3(str(chemin))

        # Fallback : court silence
        logger.debug("Transition entre actes : silence de remplacement.")
        return AudioSegment.silent(duration=500)

    def _charger_signature(self) -> AudioSegment:
        """Charge ou génère le générique signature récurrent.

        Ce jingle est toujours identique d'un épisode à l'autre pour
        créer une marque sonore reconnaissable par les enfants.
        """
        chemin = config.ASSETS_DIR / "music" / "signature_jingle.mp3"
        if chemin.exists():
            return AudioSegment.from_mp3(str(chemin))

        if self._generer_asset_elevenlabs(SIGNATURE_JINGLE_PROMPT, 5.0, chemin):
            return AudioSegment.from_mp3(str(chemin))

        logger.warning("Signature jingle non disponible — silence.")
        return AudioSegment.silent(duration=3000)

    @staticmethod
    def _generer_micro_respiration() -> AudioSegment:
        """Génère un bruit léger simulant une respiration entre répliques.

        Utilise du bruit blanc très atténué au lieu d'un silence pur
        pour un effet plus naturel et immersif (A10).
        """
        duree = RESPIRATION_DUREE_MS + random.randint(-20, 20)
        duree = max(40, duree)
        # Générer du bruit blanc très léger via numpy
        nb_samples = int(44100 * duree / 1000)
        noise = np.random.normal(0, 0.005, nb_samples).astype(np.float32)
        noise = np.clip(noise, -1.0, 1.0)
        # Convertir en int16 pour pydub
        samples_int = (noise * 32767).astype(np.int16)
        respiration = AudioSegment(
            samples_int.tobytes(),
            frame_rate=44100,
            sample_width=2,
            channels=1,
        )
        # Très léger fade pour éviter les clics
        respiration = respiration.fade_in(10).fade_out(10)
        return respiration

    @staticmethod
    def _appliquer_ducking(voix: AudioSegment, sfx: AudioSegment) -> AudioSegment:
        """Applique un ducking side-chain : baisse la voix pendant le SFX overlay.

        La voix est atténuée de DUCKING_GAIN_DB pendant la durée du SFX,
        avec des fades doux pour éviter les transitions brusques (A2).
        """
        duree_sfx = len(sfx)
        duree_voix = len(voix)

        if duree_sfx >= duree_voix:
            # SFX couvre toute la voix — ducking uniforme + overlay
            voix_ducked = voix.apply_gain(DUCKING_GAIN_DB)
            return voix_ducked.overlay(sfx)

        # Découper la voix en 3 parties : avant SFX, pendant SFX, après SFX
        fade = min(DUCKING_FADE_MS, duree_sfx // 2)

        # Partie pendant le SFX — voix atténuée
        voix_pendant = voix[:duree_sfx].apply_gain(DUCKING_GAIN_DB)
        if fade > 0:
            voix_pendant = voix_pendant.fade_in(fade).fade_out(fade)
        voix_pendant = voix_pendant.overlay(sfx)

        # Recoller : voix avant (pas de ducking) + pendant (ducké) + après
        # On utilise un crossfade pour lisser la transition
        voix_apres = voix[duree_sfx:]
        resultat = voix_pendant
        if len(voix_apres) > fade and fade > 0:
            resultat = resultat.append(voix_apres, crossfade=fade)
        else:
            resultat += voix_apres

        return resultat

    def _charger_room_tone(self, ambiance: str = "fond_doux") -> AudioSegment:
        """Charge ou génère le room tone adapté à l'ambiance (A1 + adaptatif).

        Le room tone varie selon l'ambiance de l'épisode :
        - soir : cheminée + pluie (calme, tendre, solennel, mystère)
        - jour : oiseaux + brise (épique, joyeux, humoristique)
        - orage : tonnerre + pluie (dramatique)
        - defaut : cheminée + horloge
        """
        variante = AMBIANCE_ROOM_TONE.get(ambiance, "defaut")
        chemin = config.ASSETS_DIR / "music" / f"room_tone_{variante}.mp3"

        # Charger le room tone variant en priorité, puis fallback vers générique
        if chemin.exists():
            logger.info("Room tone chargé : %s (%s)", variante, ambiance)
            return AudioSegment.from_mp3(str(chemin))

        chemin_generique = config.ASSETS_DIR / "music" / "room_tone.mp3"
        if chemin_generique.exists():
            logger.info("Room tone générique utilisé (variante '%s' indisponible)", variante)
            return AudioSegment.from_mp3(str(chemin_generique))

        # Générer via ElevenLabs avec le prompt adapté
        prompt = ROOM_TONE_PROMPTS.get(variante, ROOM_TONE_PROMPTS["defaut"])
        if self._generer_asset_elevenlabs(prompt, 22.0, chemin):
            logger.info("Room tone '%s' généré via ElevenLabs", variante)
            return AudioSegment.from_mp3(str(chemin))

        # Fallback : bruit rose très léger
        logger.debug("Room tone non disponible — bruit rose de remplacement.")
        nb_samples = 44100 * 22  # 22 secondes
        noise = np.random.normal(0, 0.002, nb_samples).astype(np.float32)
        samples_int = (noise * 32767).astype(np.int16)
        return AudioSegment(
            samples_int.tobytes(),
            frame_rate=44100,
            sample_width=2,
            channels=1,
        )

    @staticmethod
    def _appliquer_master_bus(audio: AudioSegment) -> AudioSegment:
        """Applique un traitement master bus : EQ + compression + true peak limiter.

        Pipeline de mastering léger adapté aux podcasts enfants :
        1. EQ : boost 2-5 kHz (+2.5 dB) pour clarifier les voix enfantines
        2. Compression douce (ratio 2:1 au-dessus de -20 dBFS)
        3. True peak limiter avec oversampling 4x
        """
        sample_rate = audio.frame_rate
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        channels = audio.channels
        if channels == 2:
            samples = samples.reshape((-1, 2))

        max_val = float(2 ** (audio.sample_width * 8 - 1))
        normalized = samples / max_val

        # 1. EQ : boost des médiums 2-5 kHz via filtre passe-bande simple
        # Utiliser un filtre biquad IIR simplifié (résonance douce)
        try:
            from scipy.signal import butter, sosfilt
            nyquist = sample_rate / 2.0
            low = EQ_VOICE_BOOST_LOW_HZ / nyquist
            high = min(EQ_VOICE_BOOST_HIGH_HZ / nyquist, 0.99)
            if low < high:
                sos = butter(2, [low, high], btype="band", output="sos")
                boost_linear = 10 ** (EQ_VOICE_BOOST_DB / 20.0) - 1.0
                if channels == 2:
                    for ch in range(2):
                        band = sosfilt(sos, normalized[:, ch])
                        normalized[:, ch] += boost_linear * band
                else:
                    band = sosfilt(sos, normalized.flatten())
                    normalized = (normalized.flatten() + boost_linear * band).reshape(-1, 1)
                logger.info(
                    "EQ master : boost +%.1f dB sur %d-%d Hz",
                    EQ_VOICE_BOOST_DB, EQ_VOICE_BOOST_LOW_HZ, EQ_VOICE_BOOST_HIGH_HZ,
                )
        except ImportError:
            logger.warning("scipy non disponible — EQ master ignoré.")

        # 2. Compression douce (ratio ~2:1 au-dessus de -20 dBFS)
        threshold = 0.1  # ~ -20 dBFS
        ratio = 2.0
        mask = np.abs(normalized) > threshold
        if np.any(mask):
            excess = np.abs(normalized[mask]) - threshold
            compressed = threshold + excess / ratio
            normalized[mask] = np.sign(normalized[mask]) * compressed

        # 3. True peak limiter avec oversampling
        limit = 0.89  # ~ -1 dBFS
        try:
            from scipy.signal import resample_poly
            # Suréchantillonner pour détecter les crêtes inter-sample
            if channels == 2:
                upsampled = resample_poly(normalized, TRUE_PEAK_OVERSAMPLE, 1, axis=0)
            else:
                flat = normalized.flatten()
                upsampled = resample_poly(flat, TRUE_PEAK_OVERSAMPLE, 1)

            true_peak = np.max(np.abs(upsampled))
            if true_peak > limit:
                # Atténuer proportionnellement pour que le true peak = limit
                reduction = limit / true_peak
                normalized *= reduction
                logger.info(
                    "True peak limiter : crête %.3f réduite à %.3f (×%.3f)",
                    true_peak, limit, reduction,
                )
            else:
                logger.debug("True peak %.3f sous le seuil %.3f — pas de limiting.", true_peak, limit)
        except ImportError:
            # Fallback : soft clip sans oversampling
            logger.warning("scipy non disponible — fallback soft clip sans oversampling.")
            over_limit = np.abs(normalized) > limit
            if np.any(over_limit):
                normalized[over_limit] = np.sign(normalized[over_limit]) * (
                    limit + (1.0 - limit) * np.tanh(
                        (np.abs(normalized[over_limit]) - limit) / (1.0 - limit)
                    )
                )

        # Clamp final pour sécurité
        normalized = np.clip(normalized, -1.0, 1.0)

        # Reconvertir en int
        samples_out = (normalized * max_val).astype(np.int16)
        if channels == 2:
            samples_out = samples_out.flatten()

        audio_master = audio._spawn(samples_out.tobytes())
        logger.info("Traitement master bus appliqué (EQ + compression + true peak limiter).")
        return audio_master

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
        """Assemble signature + intro + contenu + outro + signature avec transitions."""
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

        # Générique signature récurrent (identique à chaque épisode)
        signature = self._charger_signature()
        if signature.channels == 1:
            signature = signature.set_channels(2)
        signature = signature.fade_in(200).fade_out(300)

        return (
            signature + silence_transition
            + intro + silence_transition
            + voix_avec_fond
            + silence_transition + outro
            + silence_transition + signature
        )

    def _generer_chapitres(
        self, segments: list[dict], dossier: Path
    ) -> list[dict]:
        """Génère la liste de chapitres à partir des segments du script.

        Utilise des titres sémantiques basés sur la structure narrative
        plutôt que du texte tronqué.
        """
        chapitres = []
        # Offset initial : signature + silence + intro jingle + silence transition
        signature_ms = 5000  # Durée signature jingle (cf. _charger_signature: 5s)
        intro_ms = config.PRODUCTION["intro_jingle_duree_ms"]
        temps_courant_ms = signature_ms + SILENCE_TRANSITION_MS + intro_ms + SILENCE_TRANSITION_MS

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
            # - C'est papy_babou ET il y a eu 8+ segments depuis le dernier chapitre
            # - Il y a eu un SFX juste avant papy_babou
            creer_chapitre = False
            if not chapitres:
                creer_chapitre = True
            elif seg["personnage"] == "papy_babou" and nb_segments_depuis_chapitre >= 8:
                creer_chapitre = True
            elif (seg["personnage"] == "papy_babou"
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
