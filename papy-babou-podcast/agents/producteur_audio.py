"""Agent Producteur Audio — Génère les fichiers audio via ElevenLabs TTS."""

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class ProducteurAudio:
    """Orchestre les appels ElevenLabs pour générer les segments audio."""

    def __init__(self):
        self.api_key = config.ELEVENLABS_API_KEY
        self.caracteres_utilises: dict[str, int] = {}

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
        max_workers = min(
            config.PRODUCTION.get("max_parallel_tts", 4),
            total_segments,
        )

        fichiers: list[Path] = []

        if max_workers <= 1:
            for i, segment in enumerate(segments_voix, 1):
                logger.info(
                    "[%s] Segment %d/%d — %s : %s...",
                    episode_id, i, total_segments,
                    segment["personnage"], segment["texte"][:50],
                )
                chemin = dossier_episode / f"{segment['id']}.mp3"
                self._generer_segment(segment, chemin)
                fichiers.append(chemin)
        else:
            logger.info(
                "[%s] Génération parallèle de %d segments (max %d workers)",
                episode_id, total_segments, max_workers,
            )
            futures = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for i, segment in enumerate(segments_voix, 1):
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
        voice_id = config.VOICE_IDS.get(personnage)
        if not voice_id or voice_id == "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID":
            raise ValueError(
                f"Voice ID non configuré pour '{personnage}'. "
                "Configurez VOICE_IDS dans config.py ou les variables d'environnement."
            )

        settings = config.VOICE_SETTINGS.get(personnage, {})
        url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": segment["texte"],
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": settings.get("stability", 0.75),
                "similarity_boost": settings.get("similarity_boost", 0.80),
                "style": settings.get("style", 0.2),
                "use_speaker_boost": True,
            },
        }

        nb_chars = len(segment["texte"])
        self.caracteres_utilises[personnage] = (
            self.caracteres_utilises.get(personnage, 0) + nb_chars
        )

        max_tentatives = config.PRODUCTION["max_retry_tts"]
        for tentative in range(1, max_tentatives + 1):
            try:
                config.rate_limiter_elevenlabs.attendre()
                response = requests.post(
                    url, json=payload, headers=headers, timeout=60
                )
                response.raise_for_status()

                with open(chemin_sortie, "wb") as f:
                    f.write(response.content)

                logger.info(
                    "  → Segment %s généré (%d caractères, %.1f KB)",
                    segment["id"],
                    nb_chars,
                    len(response.content) / 1024,
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
        self.caracteres_utilises.clear()
