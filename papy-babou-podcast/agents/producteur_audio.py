"""Agent Producteur Audio — Génère les fichiers audio via ElevenLabs TTS."""

import logging
import time
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

        fichiers = []
        total_segments = len(episode["segments"])

        for i, segment in enumerate(episode["segments"], 1):
            logger.info(
                "[%s] Segment %d/%d — %s : %s...",
                episode_id,
                i,
                total_segments,
                segment["personnage"],
                segment["texte"][:50],
            )

            chemin = dossier_episode / f"{segment['id']}.mp3"
            self._generer_segment(segment, chemin)
            fichiers.append(chemin)

        self._logger_couts(episode_id)
        return fichiers

    def _generer_segment(self, segment: dict, chemin_sortie: Path) -> None:
        """Génère un fichier audio pour un segment via ElevenLabs TTS.

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

        # Compteur de caractères pour le suivi des coûts
        nb_chars = len(segment["texte"])
        self.caracteres_utilises[personnage] = (
            self.caracteres_utilises.get(personnage, 0) + nb_chars
        )

        max_tentatives = config.PRODUCTION["max_retry_tts"]
        for tentative in range(1, max_tentatives + 1):
            try:
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
                    delai = 2 ** tentative
                    logger.info("  Nouvelle tentative dans %ds...", delai)
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
