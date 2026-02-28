"""Tests d'intégration end-to-end (skip si ffmpeg absent)."""

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

# Skip tout le module si ffmpeg est absent
pytestmark = pytest.mark.skipif(
    not config.verifier_ffmpeg(),
    reason="ffmpeg non disponible — tests d'intégration ignorés",
)


class TestIntegrationMontage:
    """Tests d'intégration du montage audio avec ffmpeg."""

    def test_assembler_episode_complet(self, tmp_path, script_avec_sfx_overlay):
        """Assemble un épisode complet avec intro, voix, SFX, outro."""
        from pydub import AudioSegment
        from agents.monteur import Monteur

        episode = script_avec_sfx_overlay["episode"]
        episode_id = f"S{episode['saison']:02d}E{episode['numero']:02d}"
        segments_dir = tmp_path / "segments" / episode_id
        segments_dir.mkdir(parents=True)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Créer des segments audio de test
        for seg in episode["segments"]:
            silence = AudioSegment.silent(duration=500)
            silence.export(str(segments_dir / f"{seg['id']}.mp3"), format="mp3")

        monteur = Monteur()
        resultat = monteur.assembler(
            script_avec_sfx_overlay,
            dossier_segments=tmp_path / "segments",
            dossier_sortie=output_dir,
        )

        assert resultat["duree_secondes"] > 0
        assert resultat["taille_bytes"] > 0
        assert Path(resultat["chemin_hq"]).exists()
        assert Path(resultat["chemin_preview"]).exists()
        assert isinstance(resultat["chapitres"], list)

    def test_export_mp3_correct(self, tmp_path, script_exemple):
        """Vérifie que l'export MP3 produit un fichier valide."""
        from pydub import AudioSegment
        from agents.monteur import Monteur

        episode = script_exemple["episode"]
        episode_id = f"S{episode['saison']:02d}E{episode['numero']:02d}"
        segments_dir = tmp_path / "segments" / episode_id
        segments_dir.mkdir(parents=True)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        for seg in episode["segments"]:
            silence = AudioSegment.silent(duration=300)
            silence.export(str(segments_dir / f"{seg['id']}.mp3"), format="mp3")

        monteur = Monteur()
        resultat = monteur.assembler(
            script_exemple,
            dossier_segments=tmp_path / "segments",
            dossier_sortie=output_dir,
        )

        # Vérifier que le fichier est un MP3 valide en le relisant
        audio = AudioSegment.from_mp3(str(resultat["chemin_hq"]))
        assert len(audio) > 0
        assert audio.channels == 2  # Stéréo


class TestIntegrationPipelineDryRun:
    """Test d'intégration du pipeline complet en dry-run."""

    @patch("agents.scripteur.anthropic.Anthropic")
    @patch("agents.reviewer.anthropic.Anthropic")
    @patch("agents.metadonnees.anthropic.Anthropic")
    def test_pipeline_dry_run_complet(
        self, mock_meta_api, mock_review_api, mock_script_api,
        tmp_path, script_exemple, review_exemple,
    ):
        """Le pipeline dry-run doit fonctionner de bout en bout."""
        from main import pipeline
        import config as cfg

        # Mock toutes les APIs
        for mock_api in (mock_script_api, mock_review_api, mock_meta_api):
            mock_client = MagicMock()
            mock_api.return_value = mock_client

        # Mock scripteur
        mock_script_client = MagicMock()
        mock_script_api.return_value = mock_script_client
        mock_script_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(script_exemple))]
        )

        # Mock reviewer
        mock_review_client = MagicMock()
        mock_review_api.return_value = mock_review_client
        mock_review_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(review_exemple))]
        )

        rapport = pipeline(
            titre="Test intégration",
            resume="Test",
            saison=99,
            numero=99,
            dry_run=True,
            auto=True,
        )

        assert rapport["episode_id"] == "S99E99"
        assert "couts" in rapport
        assert rapport["couts"]["total_estime"] >= 0
