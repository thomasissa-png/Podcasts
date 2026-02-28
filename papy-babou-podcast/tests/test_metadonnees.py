"""Tests pour l'agent Métadonnées."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.metadonnees import Metadonnees


class TestMetadonneesTranscript:
    """Tests de la génération de transcript."""

    def test_generer_transcript(self, script_exemple):
        """Le transcript doit inclure tous les segments avec les noms corrects."""
        transcript = Metadonnees._generer_transcript(script_exemple["episode"])
        assert "Papy Babou" in transcript
        assert "Antoine" in transcript
        assert "Noémie" in transcript
        assert "Narrateur" in transcript
        assert "Le buisson ardent" in transcript

    def test_generer_transcript_ignore_sfx(self, script_avec_sfx_overlay):
        """Le transcript ne doit pas inclure les segments SFX."""
        transcript = Metadonnees._generer_transcript(script_avec_sfx_overlay["episode"])
        assert "vent dans le desert" not in transcript
        assert "tonnerre" not in transcript


class TestMetadonneesDryRun:
    """Tests du mode dry-run."""

    def test_generer_dry_run(self, script_exemple):
        """Le dry-run doit générer des métadonnées sans appel API."""
        metadonnees = Metadonnees()
        meta = metadonnees.generer_dry_run(script_exemple)

        assert "titre" in meta
        assert "description_courte" in meta
        assert "description_longue" in meta
        assert "transcript" in meta
        assert "cover_art_prompt" in meta
        assert "cover_art_path" in meta
        assert meta["saison"] == 1
        assert meta["numero"] == 1
        assert meta["duree_secondes"] > 0
        assert len(meta["description_courte"]) <= 160

    def test_generer_dry_run_contenu(self, script_exemple):
        """Les métadonnées dry-run doivent contenir les bonnes informations."""
        metadonnees = Metadonnees()
        meta = metadonnees.generer_dry_run(script_exemple)
        assert "Papy Babou" in meta["description_courte"]

    def test_generer_dry_run_avec_morale(self, script_exemple):
        """La morale doit apparaître dans la description longue."""
        metadonnees = Metadonnees()
        meta = metadonnees.generer_dry_run(script_exemple)
        assert "Morale" in meta["description_longue"]
        assert "grandes choses" in meta["description_longue"]


class TestMetadonneesSauvegarde:
    """Tests de sauvegarde."""

    def test_sauvegarder(self, script_exemple, tmp_path):
        """Les métadonnées doivent être sauvegardées en JSON valide."""
        metadonnees = Metadonnees()
        meta = metadonnees.generer_dry_run(script_exemple)
        chemin = tmp_path / "meta.json"
        metadonnees.sauvegarder(meta, chemin)

        assert chemin.exists()
        with open(chemin, encoding="utf-8") as f:
            data = json.load(f)
        assert data["saison"] == 1


class TestMetadonneesGeneration:
    """Tests de la génération via API (mockée)."""

    @patch("agents.metadonnees.anthropic.Anthropic")
    def test_generer_appelle_api(self, mock_anthropic, script_exemple):
        """La génération doit appeler l'API Claude."""
        meta_reponse = {
            "titre": "S01E01 — Le buisson ardent | Les Histoires de Papy Babou",
            "titre_court": "Le buisson ardent",
            "description_courte": "Papy Babou raconte le buisson ardent.",
            "description_longue": "Description longue...",
            "tags": ["Moïse"],
            "categories_itunes": ["Kids & Family"],
            "sous_categories_itunes": ["Stories for Kids"],
            "cover_art_prompt": "Moïse devant le buisson ardent",
        }

        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(meta_reponse))]
        mock_client.messages.create.return_value = mock_response

        metadonnees = Metadonnees()
        metadonnees.client = mock_client
        result = metadonnees.generer(script_exemple, duree_secondes=780)

        assert result["saison"] == 1
        assert result["duree_secondes"] == 780
        assert "transcript" in result
        assert "cover_art_path" in result
