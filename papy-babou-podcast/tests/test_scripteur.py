"""Tests pour l'agent Scripteur."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.scripteur import Scripteur


class TestScripteurValidation:
    """Tests de validation de la structure du script."""

    def test_valider_structure_valide(self, script_exemple):
        """Un script bien formé ne doit pas lever d'exception."""
        Scripteur._valider_structure(script_exemple)

    def test_valider_structure_sans_episode(self):
        """Un script sans clé 'episode' doit lever une erreur."""
        with pytest.raises(ValueError, match="episode"):
            Scripteur._valider_structure({"autre": {}})

    def test_valider_structure_champ_manquant(self):
        """Un script avec un champ manquant dans 'episode' doit lever une erreur."""
        script = {"episode": {"titre": "Test", "numero": 1, "saison": 1}}
        with pytest.raises(ValueError, match="segments"):
            Scripteur._valider_structure(script)

    def test_valider_structure_segments_vides(self):
        """Un script sans segment doit lever une erreur."""
        script = {
            "episode": {
                "titre": "Test",
                "numero": 1,
                "saison": 1,
                "segments": [],
            }
        }
        with pytest.raises(ValueError, match="aucun segment"):
            Scripteur._valider_structure(script)

    def test_valider_structure_personnage_inconnu(self):
        """Un personnage non reconnu doit lever une erreur."""
        script = {
            "episode": {
                "titre": "Test",
                "numero": 1,
                "saison": 1,
                "segments": [
                    {
                        "id": "seg_001",
                        "personnage": "inconnu",
                        "texte": "Texte",
                        "ton": "neutre",
                        "pause_apres_ms": 0,
                    }
                ],
            }
        }
        with pytest.raises(ValueError, match="inconnu"):
            Scripteur._valider_structure(script)

    def test_valider_structure_champ_segment_manquant(self):
        """Un segment avec un champ manquant doit lever une erreur."""
        script = {
            "episode": {
                "titre": "Test",
                "numero": 1,
                "saison": 1,
                "segments": [
                    {"id": "seg_001", "personnage": "narrateur", "texte": "Texte"}
                ],
            }
        }
        with pytest.raises(ValueError, match="ton"):
            Scripteur._valider_structure(script)


class TestScripteurComptage:
    """Tests du comptage de mots."""

    def test_compter_mots(self, script_exemple):
        """Le comptage de mots doit être correct."""
        total = Scripteur.compter_mots(script_exemple)
        assert total > 0

    def test_compter_mots_script_minimal(self):
        """Un script avec un seul mot doit compter 1."""
        script = {
            "episode": {
                "segments": [
                    {"texte": "Bonjour"},
                ]
            }
        }
        assert Scripteur.compter_mots(script) == 1


class TestScripteurSauvegarde:
    """Tests de sauvegarde du script."""

    def test_sauvegarder(self, script_exemple, tmp_path):
        """Le script doit être sauvegardé correctement en JSON."""
        scripteur = Scripteur()
        chemin = tmp_path / "test_script.json"
        scripteur.sauvegarder(script_exemple, chemin)

        assert chemin.exists()
        with open(chemin, encoding="utf-8") as f:
            data = json.load(f)
        assert data["episode"]["titre"] == "Le buisson ardent"


class TestScripteurGeneration:
    """Tests de la génération de script (avec mock API)."""

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_generer_appelle_api(self, mock_anthropic, script_exemple):
        """La génération doit appeler l'API Claude et retourner un script valide."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps(script_exemple))
        ]
        mock_client.messages.create.return_value = mock_response

        scripteur = Scripteur()
        scripteur.client = mock_client
        result = scripteur.generer(
            titre="Le buisson ardent",
            resume="Moïse et le buisson ardent",
            saison=1,
            numero=1,
        )

        assert result["episode"]["titre"] == "Le buisson ardent"
        mock_client.messages.create.assert_called_once()
