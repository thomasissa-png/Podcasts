"""Tests pour l'agent Scripteur."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.scripteur import (
    Scripteur, _construire_bible_personnages, _construire_system_prompt,
    _construire_contexte_serie, _construire_structure_narrative,
)


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
                        "personnage": "personnage_xyz_inconnu",
                        "texte": "Texte",
                        "ton": "neutre",
                        "pause_apres_ms": 0,
                    }
                ],
            }
        }
        with pytest.raises(ValueError, match="personnage_xyz_inconnu"):
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
                    {"personnage": "narrateur", "texte": "Bonjour"},
                ]
            }
        }
        assert Scripteur.compter_mots(script) == 1

    def test_compter_mots_ignore_sfx(self):
        """Le comptage doit ignorer les segments SFX."""
        script = {
            "episode": {
                "segments": [
                    {"personnage": "narrateur", "texte": "Un deux trois"},
                    {"personnage": "sfx", "texte": "vent du desert"},
                    {"personnage": "papy_babou", "texte": "Quatre cinq"},
                ]
            }
        }
        assert Scripteur.compter_mots(script) == 5


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


class TestScripteurBiblePersonnages:
    """Tests de l'injection de la bible des personnages."""

    def test_construire_bible_avec_fichier(self, tmp_path, monkeypatch):
        """La bible doit être construite à partir du fichier JSON."""
        import config
        personnages = {
            "personnages": {
                "papy_babou": {
                    "nom_complet": "Papy Babou",
                    "age": 72,
                    "description": "Grand-père aimant",
                    "ton": "chaleureux",
                    "tics_de_langage": ["Ah mes petits loups..."],
                    "vocabulaire_typique": ["formidable"],
                    "interdictions": ["Pas d'argot moderne"],
                },
            },
            "regles_interaction": {
                "frequence_interruptions": "Toutes les 90 secondes",
            },
        }
        chemin = tmp_path / "personnages.json"
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(personnages, f)

        monkeypatch.setattr(config, "PERSONNAGES_JSON_PATH", chemin)

        bible = _construire_bible_personnages()
        assert "Papy Babou" in bible
        assert "72 ans" in bible
        assert "Ah mes petits loups..." in bible
        assert "formidable" in bible
        assert "Toutes les 90 secondes" in bible

    def test_construire_bible_sans_fichier(self, monkeypatch):
        """Sans fichier, le fallback doit être utilisé."""
        import config
        monkeypatch.setattr(config, "PERSONNAGES_JSON_PATH", Path("/nonexistent/path.json"))

        bible = _construire_bible_personnages()
        assert "Papy Babou" in bible
        assert "Antoine" in bible

    def test_system_prompt_contient_mots_interdits(self):
        """Le system prompt doit inclure les mots interdits."""
        prompt = _construire_system_prompt()
        assert "tuer" in prompt
        assert "MOTS INTERDITS" in prompt

    def test_system_prompt_contient_3_actes(self):
        """Le system prompt doit inclure la structure en 3 actes."""
        prompt = _construire_system_prompt()
        assert "ACCROCHE" in prompt
        assert "DÉVELOPPEMENT" in prompt
        assert "CONCLUSION" in prompt

    def test_system_prompt_contient_ambiance(self):
        """Le system prompt doit inclure le choix d'ambiance."""
        prompt = _construire_system_prompt()
        assert "joyeux" in prompt
        assert "dramatique" in prompt
        assert "mystere" in prompt

    def test_system_prompt_contient_mode_sfx(self):
        """Le system prompt doit inclure les modes SFX overlay/insert."""
        prompt = _construire_system_prompt()
        assert "overlay" in prompt
        assert "insert" in prompt


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
            morale="La confiance en Dieu",
        )

        assert result["episode"]["titre"] == "Le buisson ardent"
        mock_client.messages.create.assert_called_once()

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_generer_avec_historique(self, mock_anthropic, script_exemple):
        """La génération avec historique doit mentionner les épisodes précédents."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps(script_exemple))
        ]
        mock_client.messages.create.return_value = mock_response

        scripteur = Scripteur()
        scripteur.client = mock_client
        historique = [
            {"episode_id": "S01E01", "titre": "Noé", "morale": "Obéissance"},
        ]
        result = scripteur.generer(
            titre="Le buisson ardent",
            resume="Moïse",
            saison=1,
            numero=2,
            historique=historique,
        )

        assert result["episode"]["titre"] == "Le buisson ardent"
        # Vérifier que le prompt contient l'historique
        call_args = mock_client.messages.create.call_args
        user_msg = call_args[1]["messages"][0]["content"]
        assert "Noé" in user_msg

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_generer_avec_contexte_saison(self, mock_anthropic, script_exemple):
        """La génération avec contexte de saison doit inclure le type d'épisode."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps(script_exemple))
        ]
        mock_client.messages.create.return_value = mock_response

        contexte = {
            "saison": {
                "numero": 1,
                "theme": "Les voyages",
                "description": "Grands voyages bibliques",
                "fil_rouge": "Le courage",
                "arcs_personnages": {},
                "rituels": {
                    "accroche": "Prêts pour le voyage ?",
                    "au_revoir": "Bon voyage !",
                },
                "episodes": [],
            }
        }
        episode_plan = {
            "numero": 1,
            "type": "ouverture",
            "arc_personnage_focus": "antoine",
            "progression_arc": "Découvre le courage",
            "teasing_episode_suivant": "La prochaine fois, Moïse...",
            "elements_fil_rouge": "Premier voyage",
        }

        scripteur = Scripteur()
        scripteur.client = mock_client
        result = scripteur.generer(
            titre="Abraham",
            resume="Le départ d'Abraham",
            saison=1,
            numero=1,
            type_episode="ouverture",
            contexte_saison=contexte,
            episode_plan=episode_plan,
        )

        call_args = mock_client.messages.create.call_args
        user_msg = call_args[1]["messages"][0]["content"]
        system_msg = call_args[1]["system"]
        assert "ouverture" in user_msg
        assert "Les voyages" in system_msg
        assert "Le courage" in system_msg


class TestContexteSerie:
    """Tests de la construction du contexte sériel."""

    def test_contexte_sans_saison(self):
        """Sans contexte de saison, le texte doit indiquer un épisode indépendant."""
        result = _construire_contexte_serie(None)
        assert "indépendant" in result.lower() or "independant" in result.lower()

    def test_contexte_avec_saison(self):
        """Avec un contexte de saison, le thème doit apparaître."""
        contexte = {
            "saison": {
                "theme": "Les grands voyages",
                "description": "Découvrir les voyages",
                "fil_rouge": "Le courage de partir",
                "arcs_personnages": {
                    "antoine": {
                        "depart": "Timide",
                        "evolution": "Grandit",
                        "arrivee": "Courageux",
                    },
                },
            }
        }
        result = _construire_contexte_serie(contexte)
        assert "Les grands voyages" in result
        assert "Le courage de partir" in result
        assert "Antoine" in result
        assert "Timide" in result


class TestStructureNarrative:
    """Tests de la construction de la structure narrative par type d'épisode."""

    def test_structure_ouverture(self):
        """L'ouverture doit contenir les éléments spécifiques."""
        result = _construire_structure_narrative("ouverture")
        assert "SAISON" in result
        assert "TEASING" in result

    def test_structure_standard(self):
        """La structure standard doit contenir previously-on et teasing."""
        historique = [{"titre": "Épisode précédent", "morale": "La foi"}]
        result = _construire_structure_narrative("standard", historique=historique)
        assert "PREVIOUSLY ON" in result
        assert "Épisode précédent" in result

    def test_structure_final(self):
        """Le final doit contenir un grand récapitulatif."""
        result = _construire_structure_narrative("final")
        assert "RÉCAPITULATIF" in result or "CLIMAX" in result

    def test_structure_avec_rituels(self):
        """Les rituels doivent apparaître dans la structure."""
        contexte = {
            "saison": {
                "rituels": {
                    "accroche": "Prêts pour l'aventure ?",
                    "au_revoir": "À la prochaine !",
                    "segment_recurrent": "Le mot du jour",
                },
            }
        }
        result = _construire_structure_narrative("standard", contexte_saison=contexte)
        assert "Prêts pour l'aventure" in result
        assert "À la prochaine" in result
        assert "Le mot du jour" in result

    def test_structure_avec_teasing(self):
        """Le teasing de l'épisode suivant doit apparaître."""
        episode_plan = {
            "teasing_episode_suivant": "Moïse va traverser la mer...",
        }
        result = _construire_structure_narrative("standard", episode_plan=episode_plan)
        assert "Moïse va traverser la mer" in result


class TestSystemPromptSeriel:
    """Tests du system prompt sériel."""

    def test_system_prompt_contient_type_episode(self):
        """Le system prompt doit adapter la durée au type d'épisode."""
        prompt = _construire_system_prompt(type_episode="ouverture")
        assert "15" in prompt  # durée ouverture = 15 min
        assert "1600" in prompt  # mots cible ouverture = 1600

    def test_system_prompt_contient_contexte_saison(self):
        """Le system prompt doit inclure le contexte sériel."""
        contexte = {
            "saison": {
                "theme": "La création",
                "description": "Les 7 jours",
                "fil_rouge": "L'émerveillement",
                "arcs_personnages": {},
            }
        }
        prompt = _construire_system_prompt(contexte_saison=contexte)
        assert "La création" in prompt
        assert "L'émerveillement" in prompt

    def test_system_prompt_personnages_dynamiques(self, monkeypatch):
        """Le system prompt doit inclure les personnages dynamiques."""
        import config
        # Simuler un personnage secondaire
        original = config.personnages_valides
        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "antoine", "noemie", "narrateur", "sfx", "mamie_rose"},
        )
        prompt = _construire_system_prompt()
        assert "mamie_rose" in prompt
        assert "PERSONNAGES SECONDAIRES" in prompt


class TestValidationPreTTS:
    """Tests de la validation pre-TTS des voice_id dans le scripteur."""

    def test_warning_voice_id_manquant(self, monkeypatch, caplog):
        """Un personnage sans voice_id doit générer un warning lors de la validation."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "antoine", "noemie", "narrateur", "sfx", "mamie_rose"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {
            "papy_babou": "voice_papy",
            "antoine": "voice_antoine",
            "noemie": "voice_noemie",
            "narrateur": "voice_narrateur",
        })

        script = {
            "episode": {
                "titre": "Test",
                "numero": 1,
                "saison": 1,
                "ambiance": "calme",
                "morale": "Courage",
                "segments": [
                    {
                        "id": "seg_001",
                        "personnage": "mamie_rose",
                        "texte": "Bonjour",
                        "ton": "doux",
                        "pause_apres_ms": 500,
                    },
                ],
            }
        }

        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)

        assert any("Voice ID manquant" in r.message and "mamie_rose" in r.message for r in caplog.records)

    def test_pas_de_warning_voice_id_present(self, monkeypatch, caplog):
        """Un personnage avec voice_id ne doit PAS générer de warning."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "narrateur", "sfx"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {
            "papy_babou": "voice_papy",
            "narrateur": "voice_narrateur",
        })

        script = {
            "episode": {
                "titre": "Test",
                "numero": 1,
                "saison": 1,
                "ambiance": "calme",
                "morale": "Courage",
                "segments": [
                    {
                        "id": "seg_001",
                        "personnage": "papy_babou",
                        "texte": "Bonjour",
                        "ton": "chaleureux",
                        "pause_apres_ms": 500,
                    },
                ],
            }
        }

        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)

        assert not any("Voice ID manquant" in r.message for r in caplog.records)
