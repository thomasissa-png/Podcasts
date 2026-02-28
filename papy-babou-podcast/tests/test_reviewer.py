"""Tests pour l'agent Reviewer."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.reviewer import Reviewer


class TestReviewerValidation:
    """Tests de validation de la review."""

    def test_valider_review_valide(self, review_exemple):
        """Une review bien formée ne doit pas lever d'exception."""
        Reviewer._valider_review(review_exemple)

    def test_valider_review_sans_cle(self):
        """Une review sans clé 'review' doit lever une erreur."""
        with pytest.raises(ValueError, match="review"):
            Reviewer._valider_review({"autre": {}})

    def test_valider_review_sans_score(self):
        """Une review sans score doit lever une erreur."""
        with pytest.raises(ValueError, match="score"):
            Reviewer._valider_review({
                "review": {"corrections": [], "alertes": []},
                "episode": {},
            })

    def test_valider_review_sans_episode(self):
        """Une review sans script corrigé doit lever une erreur."""
        with pytest.raises(ValueError, match="episode"):
            Reviewer._valider_review({
                "review": {"score": 8, "corrections": [], "alertes": []},
            })

    def test_valider_review_episode_invalide(self):
        """Une review avec un épisode mal structuré doit lever une erreur."""
        with pytest.raises(ValueError):
            Reviewer._valider_review({
                "review": {"score": 8, "corrections": [], "alertes": []},
                "episode": {"titre": "Test"},  # segments manquant
            })


class TestReviewerLogique:
    """Tests de la logique métier du reviewer."""

    def test_est_valide_score_suffisant(self, review_exemple):
        """Un score >= 7 doit être considéré valide."""
        reviewer = Reviewer()
        assert reviewer.est_valide(review_exemple) is True

    def test_est_valide_score_insuffisant(self, review_exemple):
        """Un score < 7 doit être considéré invalide."""
        reviewer = Reviewer()
        review_exemple["review"]["score"] = 5
        assert reviewer.est_valide(review_exemple) is False

    def test_est_valide_seuil_personnalise(self, review_exemple):
        """Le seuil personnalisé doit fonctionner."""
        reviewer = Reviewer()
        review_exemple["review"]["score"] = 8
        assert reviewer.est_valide(review_exemple, seuil=9) is False

    def test_extraire_corrections(self, review_exemple):
        """Les corrections doivent inclure corrections + alertes."""
        reviewer = Reviewer()
        review_exemple["review"]["alertes"] = ["Une alerte"]
        corrections = reviewer.extraire_corrections(review_exemple)
        assert len(corrections) == 2
        assert "Une alerte" in corrections

    def test_estimer_duree(self, script_exemple):
        """L'estimation de durée doit retourner une valeur positive."""
        duree = Reviewer.estimer_duree(script_exemple)
        assert duree > 0

    def test_estimer_duree_voix_differentes(self):
        """Les voix enfant doivent être plus lentes que les voix adulte."""
        script_adulte = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": " ".join(["mot"] * 120), "pause_apres_ms": 0},
                ]
            }
        }
        script_enfant = {
            "episode": {
                "segments": [
                    {"personnage": "antoine", "texte": " ".join(["mot"] * 120), "pause_apres_ms": 0},
                ]
            }
        }
        duree_adulte = Reviewer.estimer_duree(script_adulte)
        duree_enfant = Reviewer.estimer_duree(script_enfant)
        assert duree_enfant > duree_adulte


class TestReviewerEvaluation:
    """Tests de l'évaluation (avec mock API)."""

    @patch("agents.reviewer.anthropic.Anthropic")
    def test_evaluer_appelle_api(self, mock_anthropic, script_exemple, review_exemple):
        """L'évaluation doit appeler l'API Claude et retourner un résultat valide."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps(review_exemple))
        ]
        mock_client.messages.create.return_value = mock_response

        reviewer = Reviewer()
        reviewer.client = mock_client
        result = reviewer.evaluer(script_exemple)

        assert result["review"]["score"] == 8
        mock_client.messages.create.assert_called_once()
