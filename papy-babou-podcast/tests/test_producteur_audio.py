"""Tests pour l'agent Producteur Audio."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.producteur_audio import ProducteurAudio


class TestProducteurAudioValidation:
    """Tests de validation des paramètres."""

    def test_voice_id_non_configure(self, tmp_path):
        """Un voice_id non configuré doit lever une erreur."""
        producteur = ProducteurAudio()
        segment = {
            "id": "seg_001",
            "personnage": "papy_babou",
            "texte": "Bonjour",
            "ton": "chaleureux",
            "pause_apres_ms": 0,
        }
        with pytest.raises(ValueError, match="Voice ID non configuré"):
            producteur._generer_segment(segment, tmp_path / "test.mp3")


class TestProducteurAudioCompteur:
    """Tests du compteur de caractères."""

    def test_reset_compteur(self):
        """Le compteur doit se remettre à zéro."""
        producteur = ProducteurAudio()
        producteur.caracteres_utilises = {"papy_babou": 500}
        producteur.reset_compteur()
        assert producteur.caracteres_utilises == {}


class TestProducteurAudioProduction:
    """Tests de production avec mock API."""

    @patch("agents.producteur_audio.requests.post")
    @patch("agents.producteur_audio.config.VOICE_IDS", {
        "narrateur": "voice_test_123",
        "papy_babou": "voice_test_456",
    })
    def test_generer_segment_succes(self, mock_post, tmp_path):
        """Un segment doit être généré avec succès."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake mp3 data"
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        producteur = ProducteurAudio()
        segment = {
            "id": "seg_001",
            "personnage": "narrateur",
            "texte": "Bonjour les enfants",
            "ton": "neutre",
            "pause_apres_ms": 0,
        }

        chemin = tmp_path / "seg_001.mp3"
        producteur._generer_segment(segment, chemin)

        assert chemin.exists()
        assert chemin.read_bytes() == b"fake mp3 data"
        assert producteur.caracteres_utilises["narrateur"] == len("Bonjour les enfants")

    @patch("agents.producteur_audio.requests.post")
    @patch("agents.producteur_audio.config.VOICE_IDS", {
        "narrateur": "voice_test_123",
    })
    @patch("agents.producteur_audio.time.sleep")
    def test_generer_segment_retry(self, mock_sleep, mock_post, tmp_path):
        """La génération doit réessayer en cas d'échec."""
        import requests as req

        mock_post.side_effect = [
            req.exceptions.ConnectionError("timeout"),
            MagicMock(
                status_code=200,
                content=b"fake mp3 data",
                raise_for_status=MagicMock(),
            ),
        ]

        producteur = ProducteurAudio()
        segment = {
            "id": "seg_001",
            "personnage": "narrateur",
            "texte": "Test retry",
            "ton": "neutre",
            "pause_apres_ms": 0,
        }

        chemin = tmp_path / "seg_001.mp3"
        producteur._generer_segment(segment, chemin)

        assert chemin.exists()
        assert mock_post.call_count == 2
