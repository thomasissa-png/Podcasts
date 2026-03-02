"""Agent Cover Art — Génère les illustrations d'épisodes via OpenAI DALL-E 3."""

import logging
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


class CoverArt:
    """Génère des illustrations de couverture pour chaque épisode."""

    def __init__(self):
        self.api_key = config.OPENAI_API_KEY
        self.config = config.COVER_ART_CONFIG

    def generer(self, prompt: str, episode_id: str) -> Path | None:
        """Génère une illustration via DALL-E 3.

        Args:
            prompt: Description de la scène à illustrer (depuis les métadonnées).
            episode_id: Identifiant de l'épisode (ex: S01E01).

        Returns:
            Chemin de l'image générée, ou None si la génération échoue.
        """
        if not self.api_key:
            logger.warning("OPENAI_API_KEY non configurée — cover art ignoré.")
            return None

        if not self.config.get("enabled"):
            logger.info("Génération de cover art désactivée.")
            return None

        # Charger le style depuis la bible des personnages
        personnages = config.charger_personnages()
        style_config = personnages.get("style_cover_art", {})
        interdictions = style_config.get("interdictions_visuelles", [])
        elements = style_config.get("elements_recurrents", [])
        regles = style_config.get("regles_visuelles", [])
        palette = style_config.get("palette", {})

        # Construire le prompt complet avec le style de la bible
        prompt_complet = self.config["style_prefix"] + prompt

        # Injecter la palette de couleurs depuis la bible
        if palette:
            couleurs_str = ", ".join(
                f"{nom.replace('_', ' ')} ({code})"
                for nom, code in palette.items()
            )
            prompt_complet += f". Color palette: {couleurs_str}"

        # Injecter les éléments récurrents
        if elements:
            prompt_complet += ". Include: " + "; ".join(elements[:3])

        # Injecter les règles visuelles
        if regles:
            prompt_complet += ". Style rules: " + "; ".join(regles[:4])

        if interdictions:
            prompt_complet += ". DO NOT include: " + ", ".join(interdictions)

        logger.info("Génération cover art pour %s : %s", episode_id, prompt[:80])

        config.rate_limiter_openai.attendre()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config["model"],
            "prompt": prompt_complet,
            "n": 1,
            "size": self.config["size"],
            "quality": self.config["quality"],
            "response_format": "url",
        }

        try:
            response = requests.post(
                OPENAI_IMAGES_URL,
                json=payload,
                headers=headers,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

            image_url = data["data"][0]["url"]
            return self._telecharger_image(image_url, episode_id)

        except requests.RequestException as e:
            logger.error("Échec génération cover art pour %s : %s", episode_id, e)
            return None

    def _telecharger_image(self, url: str, episode_id: str) -> Path:
        """Télécharge l'image générée et la sauvegarde.

        Args:
            url: URL temporaire de l'image DALL-E.
            episode_id: Identifiant de l'épisode.

        Returns:
            Chemin du fichier image sauvegardé.
        """
        # DALL-E 3 retourne du PNG, utiliser la bonne extension
        chemin = config.COVERS_DIR / f"{episode_id}_cover.png"

        response = requests.get(url, timeout=60)
        response.raise_for_status()

        with open(chemin, "wb") as f:
            f.write(response.content)

        logger.info(
            "Cover art sauvegardé : %s (%.1f KB)",
            chemin,
            len(response.content) / 1024,
        )
        return chemin
