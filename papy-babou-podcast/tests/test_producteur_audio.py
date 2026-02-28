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
    @patch("agents.producteur_audio.random.uniform", return_value=0.5)
    def test_generer_segment_retry_avec_jitter(self, mock_random, mock_sleep, mock_post, tmp_path):
        """La génération doit réessayer avec jitter en cas d'échec."""
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
        # Vérifier que sleep est appelé avec backoff + jitter
        mock_sleep.assert_called_once()
        delai = mock_sleep.call_args[0][0]
        assert delai > 2  # 2^1 + jitter

    @patch("agents.producteur_audio.requests.post")
    @patch("agents.producteur_audio.config.VOICE_IDS", {
        "narrateur": "voice_test_123",
        "papy_babou": "voice_test_456",
    })
    @patch("agents.producteur_audio.config.PRODUCTION", {
        "max_retry_tts": 3,
        "max_parallel_tts": 2,
    })
    def test_produire_episode_parallele(self, mock_post, tmp_path):
        """La production en parallèle doit fonctionner."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake mp3 data"
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        script = {
            "episode": {
                "titre": "Test",
                "saison": 1,
                "numero": 1,
                "segments": [
                    {"id": "seg_001", "personnage": "narrateur", "texte": "Bonjour", "ton": "neutre", "pause_apres_ms": 0},
                    {"id": "seg_002", "personnage": "papy_babou", "texte": "Mes enfants", "ton": "chaleureux", "pause_apres_ms": 0},
                ],
            }
        }

        producteur = ProducteurAudio()
        fichiers = producteur.produire_episode(script, dossier_sortie=tmp_path)

        assert len(fichiers) == 2
        assert mock_post.call_count == 2
