"""Agent Producteur Audio — Génère les fichiers audio via ElevenLabs TTS."""

import logging
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# ── Mapping ton → ajustements dynamiques voice_settings ──────────────────────
# Chaque ton modifie stability / similarity_boost / style par rapport aux
# réglages de base du personnage.  Valeurs entre -0.3 et +0.3 (additives).
TONE_VOICE_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "chaleureux":    {"stability": +0.05, "similarity_boost": 0.0,   "style": +0.05},
    "curieux":       {"stability": -0.10, "similarity_boost": 0.0,   "style": +0.10},
    "inquiet":       {"stability": -0.15, "similarity_boost": +0.05, "style": +0.15},
    "neutre":        {"stability": 0.0,   "similarity_boost": 0.0,   "style": 0.0},
    "enthousiaste":  {"stability": -0.15, "similarity_boost": 0.0,   "style": +0.20},
    "dramatique":    {"stability": +0.10, "similarity_boost": +0.05, "style": +0.15},
    "joyeux":        {"stability": -0.10, "similarity_boost": 0.0,   "style": +0.15},
    "rassurant":     {"stability": +0.10, "similarity_boost": +0.05, "style": -0.05},
    "triste":        {"stability": +0.10, "similarity_boost": +0.05, "style": +0.10},
    "chuchotant":    {"stability": +0.20, "similarity_boost": +0.10, "style": -0.15},
    "excite":        {"stability": -0.20, "similarity_boost": 0.0,   "style": +0.25},
    "mystérieux":    {"stability": +0.05, "similarity_boost": +0.05, "style": +0.10},
    "solennel":      {"stability": +0.15, "similarity_boost": +0.05, "style": -0.10},
    "espiègle":      {"stability": -0.15, "similarity_boost": 0.0,   "style": +0.20},
    "émerveillé":    {"stability": -0.10, "similarity_boost": +0.05, "style": +0.20},
    "effrayé":       {"stability": -0.20, "similarity_boost": +0.05, "style": +0.20},
    "déterminé":     {"stability": +0.10, "similarity_boost": +0.05, "style": +0.05},
    "moqueur":       {"stability": -0.15, "similarity_boost": -0.05, "style": +0.25},
    "indigné":       {"stability": -0.20, "similarity_boost": 0.0,   "style": +0.20},
    "soulagé":       {"stability": +0.05, "similarity_boost": 0.0,   "style": +0.10},
    "admiratif":     {"stability": -0.05, "similarity_boost": +0.05, "style": +0.15},
    "boudeur":       {"stability": +0.05, "similarity_boost": 0.0,   "style": +0.15},
    "impatient":     {"stability": -0.15, "similarity_boost": 0.0,   "style": +0.20},
    "ambiance":      {"stability": 0.0,   "similarity_boost": 0.0,   "style": 0.0},
}


def _appliquer_prononciation(texte: str) -> str:
    """Remplace les noms bibliques par leur prononciation phonétique pour ElevenLabs.

    Utilise le dictionnaire PRONONCIATION_BIBLIQUE de config.py pour transformer
    les noms difficiles en graphies phonétiques que la TTS prononce correctement.

    Args:
        texte: Texte du segment à transformer.

    Returns:
        Texte avec les noms remplacés par leur prononciation phonétique.
    """
    resultat = texte
    for orthographe, phonetique in config.PRONONCIATION_BIBLIQUE.items():
        # Remplacement insensible à la casse, mot entier uniquement
        pattern = r"\b" + re.escape(orthographe) + r"\b"
        resultat = re.sub(pattern, phonetique, resultat, flags=re.IGNORECASE)
    return resultat


def _injecter_ssml_breaks(texte: str, ton: str = "neutre") -> str:
    """Injecte des balises SSML <break> pour les pauses dramatiques intra-segment.

    ElevenLabs supporte les balises <break time="Xs"/> dans le texte.
    Cette fonction ajoute des pauses naturelles basées sur la ponctuation
    et le ton du segment.

    Args:
        texte: Texte du segment.
        ton: Ton du segment (dramatique, chuchotant, etc.).

    Returns:
        Texte enrichi avec des balises <break>.
    """
    # Pauses plus longues pour les tons dramatiques/chuchotants
    pause_ellipsis = "0.8s" if ton in ("dramatique", "mystérieux", "solennel") else "0.5s"
    pause_dash = "0.4s" if ton in ("dramatique", "mystérieux") else "0.3s"

    # Remplacer "..." par une pause SSML (sauf en début/fin de segment)
    resultat = texte.strip()

    # Points de suspension → pause dramatique
    resultat = re.sub(
        r'\.{3,}',
        f' <break time="{pause_ellipsis}"/> ',
        resultat,
    )

    # Tiret cadratin/long → courte pause
    resultat = re.sub(
        r'\s*[—–]\s*',
        f' <break time="{pause_dash}"/> ',
        resultat,
    )

    # Nettoyer les espaces multiples
    resultat = re.sub(r'\s{2,}', ' ', resultat).strip()

    return resultat


class ProducteurAudio:
    """Orchestre les appels ElevenLabs pour générer les segments audio."""

    def __init__(self):
        self.api_key = config.ELEVENLABS_API_KEY
        self.caracteres_utilises: dict[str, int] = {}
        self._compteur_lock = threading.Lock()

    def produire_episode(self, script: dict, dossier_sortie: Path | None = None) -> list[Path]:
        """Produit tous les segments audio d'un épisode.

        Utilise un ThreadPoolExecutor pour paralléliser les appels TTS.

        Args:
            script: Script JSON validé.
            dossier_sortie: Dossier de sortie (défaut : config.SEGMENTS_DIR).

        Returns:
            Liste des chemins vers les fichiers audio générés.
        """
        dossier = dossier_sortie or config.SEGMENTS_DIR
        episode = script["episode"]
        episode_id = f"S{episode['saison']:02d}E{episode['numero']:02d}"
        dossier_episode = dossier / episode_id
        dossier_episode.mkdir(parents=True, exist_ok=True)

        segments_voix = [
            s for s in episode["segments"] if s["personnage"] != "sfx"
        ]
        total_segments = len(segments_voix)
        max_workers = max(1, min(
            config.PRODUCTION.get("max_parallel_tts", 4),
            total_segments,
        ))

        fichiers: list[Path] = []

        # Filtrer les segments déjà générés (skip-if-exists)
        # Permet de ne régénérer que les manquants sur un resume partiel
        segments_a_generer = []
        for seg in segments_voix:
            chemin = dossier_episode / f"{seg['id']}.mp3"
            if chemin.exists() and chemin.stat().st_size > 100:
                fichiers.append(chemin)  # Déjà généré
            else:
                segments_a_generer.append(seg)

        if segments_a_generer:
            nb_skip = total_segments - len(segments_a_generer)
            if nb_skip > 0:
                logger.info(
                    "[%s] %d/%d segments déjà générés — %d à (re)générer",
                    episode_id, nb_skip, total_segments, len(segments_a_generer),
                )
        else:
            logger.info("[%s] Tous les %d segments déjà générés — skip", episode_id, total_segments)
            return fichiers

        if max_workers <= 1:
            for i, segment in enumerate(segments_a_generer, 1):
                logger.info(
                    "[%s] Segment %d/%d — %s : %s...",
                    episode_id, i, len(segments_a_generer),
                    segment["personnage"], segment["texte"][:50],
                )
                chemin = dossier_episode / f"{segment['id']}.mp3"
                self._generer_segment(segment, chemin)
                fichiers.append(chemin)
        else:
            logger.info(
                "[%s] Génération parallèle de %d segments (max %d workers)",
                episode_id, len(segments_a_generer), max_workers,
            )
            futures = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for i, segment in enumerate(segments_a_generer, 1):
                    chemin = dossier_episode / f"{segment['id']}.mp3"
                    future = executor.submit(self._generer_segment, segment, chemin)
                    futures[future] = (i, segment, chemin)

                for future in as_completed(futures):
                    i, segment, chemin = futures[future]
                    try:
                        future.result()
                        fichiers.append(chemin)
                        logger.info(
                            "[%s] Segment %d/%d terminé — %s",
                            episode_id, i, total_segments, segment["id"],
                        )
                    except Exception as e:
                        logger.error(
                            "[%s] Échec segment %d/%d — %s : %s",
                            episode_id, i, total_segments, segment["id"], e,
                        )
                        raise

            # Réordonner les fichiers selon l'ordre du script
            ordre = {seg["id"]: idx for idx, seg in enumerate(segments_voix)}
            fichiers.sort(key=lambda p: ordre.get(p.stem, 0))

        self._logger_couts(episode_id)
        return fichiers

    def _generer_segment(self, segment: dict, chemin_sortie: Path) -> None:
        """Génère un fichier audio pour un segment via ElevenLabs TTS.

        Utilise un backoff exponentiel avec jitter pour les retries.

        Args:
            segment: Segment du script.
            chemin_sortie: Chemin du fichier MP3 à créer.

        Raises:
            RuntimeError: Si la génération échoue après toutes les tentatives.
        """
        personnage = segment["personnage"]
        placeholder = "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"
        voice_id = config.VOICE_IDS.get(personnage)
        if not voice_id or voice_id == placeholder:
            # Chaîne de fallback : essayer plusieurs voix configurées
            voice_id = None
            for fallback_char in config.VOICE_FALLBACK_CHAIN:
                fallback_id = config.VOICE_IDS.get(fallback_char)
                if fallback_id and fallback_id != placeholder:
                    logger.warning(
                        "Voice ID non configuré pour '%s' — fallback vers la voix '%s'.",
                        personnage, fallback_char,
                    )
                    voice_id = fallback_id
                    break
            if not voice_id:
                raise ValueError(
                    f"Voice ID non configuré pour '{personnage}' et aucune voix "
                    "de fallback disponible. Configurez VOICE_IDS dans config.py, "
                    "les variables d'environnement, ou via la commande configure-voix."
                )

        settings = config.VOICE_SETTINGS.get(personnage, {})

        # Ajuster les voice_settings selon le ton du segment
        base_stability = settings.get("stability", 0.75)
        base_similarity = settings.get("similarity_boost", 0.80)
        base_style = settings.get("style", 0.2)

        ton = segment.get("ton", "neutre")
        adjustments = TONE_VOICE_ADJUSTMENTS.get(ton, {})
        if adjustments:
            adj_stability = max(0.0, min(1.0, base_stability + adjustments.get("stability", 0.0)))
            adj_similarity = max(0.0, min(1.0, base_similarity + adjustments.get("similarity_boost", 0.0)))
            adj_style = max(0.0, min(1.0, base_style + adjustments.get("style", 0.0)))
            if ton != "neutre":
                logger.debug(
                    "  Ton '%s' → stability=%.2f, similarity=%.2f, style=%.2f",
                    ton, adj_stability, adj_similarity, adj_style,
                )
        else:
            adj_stability = base_stability
            adj_similarity = base_similarity
            adj_style = base_style

        # Appliquer le dictionnaire de prononciation pour les noms bibliques
        texte_tts = _appliquer_prononciation(segment["texte"])

        # Injecter les balises SSML <break> pour les pauses dramatiques
        texte_tts = _injecter_ssml_breaks(texte_tts, ton)

        # Utiliser la voix clonée si disponible (priorité sur la voix standard)
        cloned_id = config.VOICE_CLONED_IDS.get(personnage, "")
        if cloned_id:
            voice_id = cloned_id
            logger.debug("Utilisation de la voix clonée pour '%s'", personnage)

        # Vitesse vocale par personnage, modulée par le champ "rythme" du segment
        base_speed = config.VOICE_SPEED.get(personnage, 1.0)
        rythme = segment.get("rythme", "normal")
        rythme_factor = config.RYTHME_SPEED_FACTOR.get(rythme, 1.0)
        speed = round(base_speed * rythme_factor, 2)

        # Choisir l'endpoint : with-timestamps (speech marks) ou standard
        use_timestamps = config.SPEECH_MARKS_ENABLED
        if use_timestamps:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
        else:
            url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json" if use_timestamps else "audio/mpeg",
        }
        payload = {
            "text": texte_tts,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": adj_stability,
                "similarity_boost": adj_similarity,
                "style": adj_style,
                "use_speaker_boost": True,
            },
        }

        # Ajouter la vitesse si différente de 1.0
        if speed != 1.0:
            payload["speed"] = speed

        nb_chars = len(segment["texte"])

        max_tentatives = config.PRODUCTION["max_retry_tts"]
        for tentative in range(1, max_tentatives + 1):
            try:
                config.rate_limiter_elevenlabs.attendre()
                response = requests.post(
                    url, json=payload, headers=headers, timeout=60
                )
                response.raise_for_status()

                if use_timestamps:
                    # Endpoint with-timestamps retourne du JSON
                    import base64
                    data = response.json()
                    audio_bytes = base64.b64decode(data["audio_base64"])
                    with open(chemin_sortie, "wb") as f:
                        f.write(audio_bytes)

                    # Sauvegarder les timestamps (speech marks) en JSON
                    alignment = data.get("alignment", {})
                    if alignment:
                        chemin_timestamps = chemin_sortie.with_suffix(".timestamps.json")
                        import json
                        with open(chemin_timestamps, "w", encoding="utf-8") as f:
                            json.dump({
                                "segment_id": segment["id"],
                                "personnage": personnage,
                                "texte": segment["texte"],
                                "alignment": alignment,
                            }, f, ensure_ascii=False, indent=2)
                        logger.debug(
                            "  Speech marks sauvegardés : %s", chemin_timestamps,
                        )
                else:
                    with open(chemin_sortie, "wb") as f:
                        f.write(response.content)

                # Compter les caractères après succès uniquement
                with self._compteur_lock:
                    self.caracteres_utilises[personnage] = (
                        self.caracteres_utilises.get(personnage, 0) + nb_chars
                    )

                logger.info(
                    "  → Segment %s généré (%d caractères, %.1f KB, speed=%.2f%s)",
                    segment["id"],
                    nb_chars,
                    (len(audio_bytes) if use_timestamps else len(response.content)) / 1024,
                    speed,
                    ", +timestamps" if use_timestamps else "",
                )
                return

            except requests.RequestException as e:
                logger.warning(
                    "  ⚠ Tentative %d/%d échouée pour %s : %s",
                    tentative,
                    max_tentatives,
                    segment["id"],
                    e,
                )
                if tentative < max_tentatives:
                    delai = (2 ** tentative) + random.uniform(0, 1)
                    logger.info("  Nouvelle tentative dans %.1fs...", delai)
                    time.sleep(delai)

        raise RuntimeError(
            f"Échec de la génération audio pour le segment {segment['id']} "
            f"après {max_tentatives} tentatives."
        )

    def _logger_couts(self, episode_id: str) -> None:
        """Affiche un résumé des caractères utilisés par voix."""
        total = sum(self.caracteres_utilises.values())
        logger.info("── Coûts ElevenLabs pour %s ──", episode_id)
        for personnage, chars in sorted(self.caracteres_utilises.items()):
            logger.info("  %s : %d caractères", personnage, chars)
        logger.info("  TOTAL : %d caractères", total)

    def reset_compteur(self) -> None:
        """Remet à zéro le compteur de caractères."""
        with self._compteur_lock:
            self.caracteres_utilises.clear()
