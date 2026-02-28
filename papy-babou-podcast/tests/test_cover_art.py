"""Tests pour l'agent Cover Art."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.cover_art import CoverArt


class TestCoverArtSansApiKey:
    """Tests sans clé API OpenAI."""

    def test_generer_sans_api_key(self, monkeypatch):
        """Sans API key, doit retourner None."""
        import config
        monkeypatch.setattr(config, "OPENAI_API_KEY", "")
        monkeypatch.setattr(config, "COVER_ART_CONFIG", {**config.COVER_ART_CONFIG, "enabled": False})

        agent = CoverArt()
        result = agent.generer("un mouton dans un champ", "S01E01")
        assert result is None

    def test_generer_disabled(self, monkeypatch):
        """Si désactivé, doit retourner None."""
        import config
        monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr(config, "COVER_ART_CONFIG", {**config.COVER_ART_CONFIG, "enabled": False})

        agent = CoverArt()
        result = agent.generer("test", "S01E01")
        assert result is None


class TestCoverArtAvecApiKey:
    """Tests avec clé API mockée."""

    @patch("agents.cover_art.requests.get")
    @patch("agents.cover_art.requests.post")
    def test_generer_succes(self, mock_post, mock_get, tmp_path, monkeypatch):
        """La génération doit appeler l'API et sauvegarder l'image."""
        import config
        monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr(config, "COVER_ART_CONFIG", {
            "enabled": True,
            "model": "dall-e-3",
            "size": "1024x1024",
            "quality": "standard",
            "style_prefix": "Style enfant. ",
        })
        monkeypatch.setattr(config, "COVERS_DIR", tmp_path)

        # Mock POST (génération)
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"url": "https://example.com/image.png"}]},
            raise_for_status=lambda: None,
        )

        # Mock GET (téléchargement)
        mock_get.return_value = MagicMock(
            status_code=200,
            content=b"fake-image-data",
            raise_for_status=lambda: None,
        )

        agent = CoverArt()
        result = agent.generer("Moïse devant le buisson ardent", "S01E01")

        assert result is not None
        assert result.exists()
        assert result.name == "S01E01_cover.png"
        mock_post.assert_called_once()

    @patch("agents.cover_art.requests.post")
    def test_generer_erreur_api(self, mock_post, monkeypatch):
        """Une erreur API doit retourner None (pas de crash)."""
        import config
        import requests
        monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr(config, "COVER_ART_CONFIG", {
            "enabled": True,
            "model": "dall-e-3",
            "size": "1024x1024",
            "quality": "standard",
            "style_prefix": "Style. ",
        })

        mock_post.side_effect = requests.RequestException("API error")

        agent = CoverArt()
        result = agent.generer("test", "S01E01")
        assert result is None
