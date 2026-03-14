"""Tests pour l'agent Planificateur de saison."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.planificateur import Planificateur


@pytest.fixture
def plan_saison_exemple():
    """Plan de saison minimal valide pour les tests."""
    return {
        "saison": {
            "numero": 1,
            "theme": "Les grands voyages de la Bible",
            "description": "Découvrir les grands voyages bibliques",
            "fil_rouge": "Le courage de partir vers l'inconnu",
            "arcs_personnages": {
                "antoine": {
                    "depart": "Timide face à l'inconnu",
                    "evolution": "Découvre le courage progressivement",
                    "arrivee": "Prêt à affronter de nouvelles aventures",
                },
                "noemie": {
                    "depart": "Inquiète de quitter ce qu'elle connaît",
                    "evolution": "Apprend à faire confiance",
                    "arrivee": "Comprend que le changement peut être beau",
                },
                "papy_babou": {
                    "depart": "Guide bienveillant",
                    "evolution": "Partage sa propre sagesse du voyage",
                    "arrivee": "Fier de ses petits-enfants",
                },
            },
            "personnages_secondaires": [
                {
                    "id": "mamie_rose",
                    "nom_complet": "Mamie Rose",
                    "description": "Épouse de Papy Babou",
                    "apparait_episode": 3,
                    "ton": "doux, malicieux",
                    "relation": "Apporte un autre regard",
                    "tics_de_langage": ["Oh, ton Papy exagère toujours..."],
                }
            ],
            "rituels": {
                "accroche": "Alors mes petits explorateurs, prêts pour le voyage ?",
                "au_revoir": "Bon voyage jusqu'à la prochaine fois !",
                "running_gag": "Papy perd toujours sa carte",
                "segment_recurrent": "Le mot du voyageur",
            },
            "episodes": [
                {
                    "numero": 1,
                    "titre": "Abraham quitte sa terre",
                    "type": "ouverture",
                    "histoire_biblique": "Le départ d'Abraham",
                    "resume": "Abraham quitte Ur pour la Terre Promise",
                    "morale": "Le courage de partir vers l'inconnu",
                    "ambiance": "mystere",
                    "duree_cible_minutes": 15,
                    "personnages_presents": ["papy_babou", "antoine", "noemie"],
                    "personnages_secondaires_presents": [],
                    "arc_personnage_focus": "antoine",
                    "progression_arc": "Antoine découvre ce qu'est le courage",
                    "lien_episode_precedent": "",
                    "teasing_episode_suivant": "La prochaine fois, on suivra Moïse...",
                    "elements_fil_rouge": "Premier voyage, premier pas",
                    "moments_cles": ["Abraham dit au revoir", "Découverte du désert"],
                    "questions_ouvertes": ["Où Abraham va-t-il arriver ?"],
                },
                {
                    "numero": 2,
                    "titre": "Moïse traverse le désert",
                    "type": "standard",
                    "histoire_biblique": "L'exode",
                    "resume": "Moïse guide le peuple",
                    "morale": "La persévérance face aux obstacles",
                    "ambiance": "dramatique",
                    "duree_cible_minutes": 13,
                    "personnages_presents": ["papy_babou", "antoine", "noemie"],
                    "personnages_secondaires_presents": [],
                    "arc_personnage_focus": "noemie",
                    "progression_arc": "Noémie comprend la persévérance",
                    "lien_episode_precedent": "Comme Abraham, Moïse aussi a dû partir",
                    "teasing_episode_suivant": "La prochaine fois, une surprise...",
                    "elements_fil_rouge": "Un autre grand voyageur",
                    "moments_cles": ["La traversée de la mer"],
                    "questions_ouvertes": ["Comment Moïse a-t-il trouvé son chemin ?"],
                },
            ],
        }
    }


class TestPlanificateurValidation:
    """Tests de la validation du plan de saison."""

    def test_valider_plan_valide(self, plan_saison_exemple):
        """Un plan valide ne doit pas lever d'exception."""
        Planificateur._valider_plan(plan_saison_exemple)

    def test_valider_plan_sans_saison(self):
        """Un plan sans clé 'saison' doit lever une erreur."""
        with pytest.raises(ValueError, match="saison"):
            Planificateur._valider_plan({"autre": {}})

    def test_valider_plan_champ_manquant(self):
        """Un plan avec un champ manquant doit lever une erreur."""
        plan = {"saison": {"numero": 1, "theme": "Test"}}
        with pytest.raises(ValueError, match="episodes"):
            Planificateur._valider_plan(plan)

    def test_valider_plan_episodes_vides(self):
        """Un plan sans épisode doit lever une erreur."""
        plan = {"saison": {"numero": 1, "theme": "Test", "episodes": []}}
        with pytest.raises(ValueError, match="au moins un"):
            Planificateur._valider_plan(plan)

    def test_valider_plan_episode_champ_manquant(self):
        """Un épisode avec un champ manquant doit lever une erreur."""
        plan = {
            "saison": {
                "numero": 1,
                "theme": "Test",
                "episodes": [{"numero": 1, "titre": "Test"}],
            }
        }
        with pytest.raises(ValueError, match="resume"):
            Planificateur._valider_plan(plan)


class TestPlanificateurSauvegarde:
    """Tests de la sauvegarde du plan."""

    def test_sauvegarder(self, plan_saison_exemple, tmp_path):
        """Le plan doit être sauvegardé correctement."""
        planificateur = Planificateur()
        chemin = tmp_path / "saison_01.json"
        planificateur.sauvegarder(plan_saison_exemple, chemin)

        assert chemin.exists()
        with open(chemin, encoding="utf-8") as f:
            data = json.load(f)
        assert data["saison"]["theme"] == "Les grands voyages de la Bible"


class TestPlanificateurExport:
    """Tests des exports CSV et Markdown."""

    def test_exporter_csv(self, plan_saison_exemple, tmp_path):
        """L'export CSV doit créer un fichier avec les bonnes colonnes."""
        planificateur = Planificateur()
        chemin = tmp_path / "saison_01.csv"
        planificateur.exporter_csv(plan_saison_exemple, chemin)

        assert chemin.exists()
        contenu = chemin.read_text(encoding="utf-8")
        assert "Abraham quitte sa terre" in contenu
        assert "ouverture" in contenu

    def test_exporter_markdown(self, plan_saison_exemple, tmp_path):
        """L'export Markdown doit contenir les sections attendues."""
        planificateur = Planificateur()
        chemin = tmp_path / "saison_01.md"
        planificateur.exporter_markdown(plan_saison_exemple, chemin)

        assert chemin.exists()
        contenu = chemin.read_text(encoding="utf-8")
        assert "Saison 1" in contenu
        assert "Les grands voyages de la Bible" in contenu
        assert "Arcs de personnages" in contenu
        assert "Mamie Rose" in contenu
        assert "Rituels" in contenu
        assert "Abraham quitte sa terre" in contenu


class TestPlanificateurGeneration:
    """Tests de la génération (avec mock API)."""

    @patch("agents.planificateur.anthropic.Anthropic")
    def test_planifier_saison(self, mock_anthropic, plan_saison_exemple):
        """La planification doit appeler l'API et retourner un plan valide."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps(plan_saison_exemple))
        ]
        mock_client.messages.create.return_value = mock_response

        planificateur = Planificateur()
        planificateur.client = mock_client
        plan = planificateur.planifier_saison(
            numero_saison=1,
            theme="Les grands voyages de la Bible",
            nb_episodes=2,
        )

        assert plan["saison"]["theme"] == "Les grands voyages de la Bible"
        assert len(plan["saison"]["episodes"]) == 2
        mock_client.messages.create.assert_called_once()
