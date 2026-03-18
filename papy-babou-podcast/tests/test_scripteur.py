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
        assert "massacre" in prompt
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
        assert "ACCROCHE" in result
        assert "CONCLUSION" in result

    def test_structure_standard(self):
        """La structure standard doit contenir un rappel naturel et teasing."""
        historique = [{"titre": "Épisode précédent", "morale": "La foi"}]
        result = _construire_structure_narrative("standard", historique=historique)
        assert "RAPPEL NATUREL" in result
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
        assert "30" in prompt  # durée ouverture = 30 min
        assert "3200" in prompt  # mots cible ouverture = 3200

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


class TestVerifierTicsDeLangage:
    """Tests directs de _verifier_tics_de_langage."""

    def test_tics_presents(self, monkeypatch, caplog):
        """Les tics utilisés ne doivent pas générer de warning."""
        import config
        import logging

        monkeypatch.setattr(config, "charger_personnages", lambda: {
            "personnages": {
                "papy_babou": {
                    "nom_complet": "Papy Babou",
                    "tics_de_langage": ["Ah mes petits loups", "Figurez-vous que"],
                },
            }
        })
        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Ah mes petits loups, venez !"},
                    {"personnage": "papy_babou", "texte": "Figurez-vous que c'est vrai."},
                ],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._verifier_tics_de_langage(script)
        assert not any("n'utilise que" in r.message for r in caplog.records)

    def test_tics_absents(self, monkeypatch, caplog):
        """Aucun tic utilisé doit générer un warning."""
        import config
        import logging

        monkeypatch.setattr(config, "charger_personnages", lambda: {
            "personnages": {
                "papy_babou": {
                    "nom_complet": "Papy Babou",
                    "tics_de_langage": ["Ah mes petits loups", "Figurez-vous que"],
                },
            }
        })
        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Bonjour les enfants."},
                ],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._verifier_tics_de_langage(script)
        assert any("n'utilise que" in r.message for r in caplog.records)

    def test_personnage_sans_tics_definis(self, monkeypatch, caplog):
        """Un personnage sans tics définis ne doit pas générer de warning."""
        import config
        import logging

        monkeypatch.setattr(config, "charger_personnages", lambda: {
            "personnages": {
                "mamie_sonia": {
                    "nom_complet": "Mamie Sonia",
                },
            }
        })
        script = {
            "episode": {
                "segments": [
                    {"personnage": "mamie_sonia", "texte": "Le gâteau est prêt !"},
                ],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._verifier_tics_de_langage(script)
        assert not any("n'utilise que" in r.message for r in caplog.records)


class TestVerifierMotsInterdits:
    """Tests de la vérification post-génération des mots interdits."""

    def test_mots_interdits_detectes(self, caplog):
        """Les mots interdits dans le texte doivent déclencher un warning."""
        import logging

        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Il allait torturer le prisonnier."},
                ],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._verifier_mots_interdits(script)
        assert any("Mots interdits" in r.message for r in caplog.records)

    def test_mots_interdits_absents(self, caplog):
        """Un script sans mots interdits ne doit pas générer de warning."""
        import logging

        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Il voyagea dans le désert."},
                ],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._verifier_mots_interdits(script)
        assert not any("Mots interdits" in r.message for r in caplog.records)

    def test_mots_interdits_ignore_sfx(self, caplog):
        """Les segments SFX ne doivent pas être vérifiés pour les mots interdits."""
        import logging

        script = {
            "episode": {
                "segments": [
                    {"personnage": "sfx", "texte": "death scream"},
                    {"personnage": "papy_babou", "texte": "Il traversa la mer."},
                ],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._verifier_mots_interdits(script)
        assert not any("Mots interdits" in r.message for r in caplog.records)


class TestValidationPauseEtTexte:
    """Tests de la validation pause_apres_ms et texte dans _valider_structure."""

    def test_pause_negative_corrigee(self, monkeypatch, caplog):
        """Une pause négative doit être corrigée à 0 avec warning."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "narrateur", "sfx"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {"papy_babou": "v", "narrateur": "v"})

        script = {
            "episode": {
                "titre": "Test", "numero": 1, "saison": 1,
                "ambiance": "calme", "morale": "Test",
                "segments": [{
                    "id": "seg_001", "personnage": "papy_babou",
                    "texte": "Bonjour", "ton": "chaleureux",
                    "pause_apres_ms": -500,
                }],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)
        assert script["episode"]["segments"][0]["pause_apres_ms"] == 0
        assert any("pause_apres_ms invalide" in r.message for r in caplog.records)

    def test_texte_vide_warning(self, monkeypatch, caplog):
        """Un texte vide doit générer un warning."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "narrateur", "sfx"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {"papy_babou": "v", "narrateur": "v"})

        script = {
            "episode": {
                "titre": "Test", "numero": 1, "saison": 1,
                "ambiance": "calme", "morale": "Test",
                "segments": [{
                    "id": "seg_001", "personnage": "papy_babou",
                    "texte": "", "ton": "chaleureux",
                    "pause_apres_ms": 500,
                }],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)
        assert any("Texte vide" in r.message for r in caplog.records)

    def test_texte_vide_sfx_pas_de_warning(self, monkeypatch, caplog):
        """Un segment SFX avec texte vide ne doit PAS lever de warning texte."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "narrateur", "sfx"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {"papy_babou": "v"})

        script = {
            "episode": {
                "titre": "Test", "numero": 1, "saison": 1,
                "ambiance": "calme", "morale": "Test",
                "segments": [
                    {"id": "seg_001", "personnage": "papy_babou",
                     "texte": "Bonjour", "ton": "chaleureux", "pause_apres_ms": 500},
                    {"id": "sfx_001", "personnage": "sfx",
                     "texte": "", "ton": "ambiance", "pause_apres_ms": 0,
                     "duree_sfx_secondes": 5.0, "mode": "insert"},
                ],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)
        assert not any("Texte vide" in r.message for r in caplog.records)


class TestValidationSFXAlignee:
    """Tests de la validation SFX alignée sur le prompt (8-12)."""

    def test_sfx_insuffisants_warning(self, monkeypatch, caplog):
        """Moins de 5 SFX doit générer un warning."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "narrateur", "sfx"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {"papy_babou": "v"})

        segments = [
            {"id": "seg_001", "personnage": "papy_babou",
             "texte": "Bonjour", "ton": "chaleureux", "pause_apres_ms": 500},
        ]
        # Seulement 2 SFX
        for i in range(2):
            segments.append({
                "id": f"sfx_{i:03d}", "personnage": "sfx",
                "texte": "wind", "ton": "ambiance", "pause_apres_ms": 0,
                "duree_sfx_secondes": 5.0, "mode": "insert",
            })
        script = {
            "episode": {
                "titre": "Test", "numero": 1, "saison": 1,
                "ambiance": "calme", "morale": "Test",
                "segments": segments,
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)
        assert any("Pas assez de bruitages" in r.message for r in caplog.records)

    def test_sfx_excessifs_warning(self, monkeypatch, caplog):
        """Plus de 15 SFX doit générer un warning."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "narrateur", "sfx"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {"papy_babou": "v"})

        segments = [
            {"id": "seg_001", "personnage": "papy_babou",
             "texte": "Bonjour", "ton": "chaleureux", "pause_apres_ms": 500},
        ]
        for i in range(16):
            segments.append({
                "id": f"sfx_{i:03d}", "personnage": "sfx",
                "texte": f"sound_{i}", "ton": "ambiance", "pause_apres_ms": 0,
                "duree_sfx_secondes": 3.0, "mode": "insert",
            })
        script = {
            "episode": {
                "titre": "Test", "numero": 1, "saison": 1,
                "ambiance": "calme", "morale": "Test",
                "segments": segments,
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)
        assert any("Trop de bruitages" in r.message for r in caplog.records)

    def test_sfx_dans_plage_pas_de_warning(self, monkeypatch, caplog):
        """8-15 SFX ne doit pas générer de warning SFX."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "narrateur", "sfx"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {"papy_babou": "v"})

        segments = [
            {"id": "seg_001", "personnage": "papy_babou",
             "texte": "Bonjour", "ton": "chaleureux", "pause_apres_ms": 500},
        ]
        for i in range(10):
            segments.append({
                "id": f"sfx_{i:03d}", "personnage": "sfx",
                "texte": f"sound_{i}", "ton": "ambiance", "pause_apres_ms": 0,
                "duree_sfx_secondes": 3.0, "mode": "insert",
            })
        script = {
            "episode": {
                "titre": "Test", "numero": 1, "saison": 1,
                "ambiance": "calme", "morale": "Test",
                "segments": segments,
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)
        assert not any("bruitages" in r.message for r in caplog.records)


class TestValidationSegmentDuplique:
    """Tests de la validation d'unicité des IDs de segments."""

    def test_ids_dupliques_raise(self):
        """Des IDs de segments dupliqués doivent lever une ValueError."""
        script = {
            "episode": {
                "titre": "Test", "numero": 1, "saison": 1,
                "segments": [
                    {"id": "seg_001", "personnage": "narrateur",
                     "texte": "A", "ton": "neutre", "pause_apres_ms": 0},
                    {"id": "seg_001", "personnage": "narrateur",
                     "texte": "B", "ton": "neutre", "pause_apres_ms": 0},
                ],
            }
        }
        with pytest.raises(ValueError, match="dupliqué"):
            Scripteur._valider_structure(script)


class TestAmbianceInvalideFallback:
    """Tests du fallback d'ambiance invalide vers 'calme'."""

    def test_ambiance_invalide_corrigee(self, monkeypatch, caplog):
        """Une ambiance invalide doit être corrigée vers 'calme'."""
        import config
        import logging

        monkeypatch.setattr(
            config, "personnages_valides",
            lambda: {"papy_babou", "narrateur", "sfx"},
        )
        monkeypatch.setattr(config, "VOICE_IDS", {"papy_babou": "v"})

        script = {
            "episode": {
                "titre": "Test", "numero": 1, "saison": 1,
                "ambiance": "romantique",
                "morale": "Test",
                "segments": [{
                    "id": "seg_001", "personnage": "papy_babou",
                    "texte": "Bonjour", "ton": "chaleureux", "pause_apres_ms": 500,
                }],
            }
        }
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_structure(script)
        assert script["episode"]["ambiance"] == "calme"
        assert any("non reconnue" in r.message for r in caplog.records)


class TestRetryResponseTronquee:
    """Tests du retry sur réponse tronquée (stop_reason=max_tokens)."""

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_retry_augmente_max_tokens(self, mock_anthropic, script_exemple):
        """Le retry doit augmenter max_tokens de 50%."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        # Premier appel : tronqué
        truncated_response = MagicMock()
        truncated_response.stop_reason = "max_tokens"
        truncated_response.content = [MagicMock(text="truncated")]

        # Deuxième appel : OK
        ok_response = MagicMock()
        ok_response.stop_reason = "end_turn"
        ok_response.content = [MagicMock(text=json.dumps(script_exemple))]

        mock_client.messages.create.side_effect = [truncated_response, ok_response]

        scripteur = Scripteur()
        scripteur.client = mock_client
        result = scripteur.generer(
            titre="Test", resume="Test", saison=1, numero=1,
        )
        assert result["episode"]["titre"] == "Le buisson ardent"
        # Vérifier que le 2ème appel a des tokens plus élevés
        calls = mock_client.messages.create.call_args_list
        assert calls[1][1]["max_tokens"] > calls[0][1]["max_tokens"]


class TestRetryJsonMalforme:
    """Tests du retry sur JSON malformé."""

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_retry_json_invalide_puis_valide(self, mock_anthropic, script_exemple):
        """Un JSON invalide suivi d'un valide doit réussir."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        # Premier appel : JSON invalide
        bad_response = MagicMock()
        bad_response.stop_reason = "end_turn"
        bad_response.content = [MagicMock(text="not json at all {{{")]

        # Deuxième appel (retry) : OK
        ok_response = MagicMock()
        ok_response.stop_reason = "end_turn"
        ok_response.content = [MagicMock(text=json.dumps(script_exemple))]

        mock_client.messages.create.side_effect = [bad_response, ok_response]

        scripteur = Scripteur()
        scripteur.client = mock_client
        result = scripteur.generer(
            titre="Test", resume="Test", saison=1, numero=1,
        )
        assert result["episode"]["titre"] == "Le buisson ardent"
        assert mock_client.messages.create.call_count == 2


class TestResponseContentVide:
    """Tests de la protection contre response.content vide."""

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_response_content_vide_raise(self, mock_anthropic):
        """Une réponse sans contenu doit lever une ValueError explicite."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        empty_response = MagicMock()
        empty_response.stop_reason = "end_turn"
        empty_response.content = []

        mock_client.messages.create.return_value = empty_response

        scripteur = Scripteur()
        scripteur.client = mock_client
        with pytest.raises(ValueError, match="vide"):
            scripteur.generer(titre="Test", resume="Test", saison=1, numero=1)


class TestTypeCheckApresParsingJson:
    """Tests du type-check après parser_json_llm."""

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_json_liste_raise(self, mock_anthropic):
        """Un JSON qui est une liste (pas un dict) doit lever une ValueError."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        response = MagicMock()
        response.stop_reason = "end_turn"
        response.content = [MagicMock(text='[1, 2, 3]')]

        mock_client.messages.create.return_value = response

        scripteur = Scripteur()
        scripteur.client = mock_client
        with pytest.raises(ValueError, match="n'est pas un objet"):
            scripteur.generer(titre="Test", resume="Test", saison=1, numero=1)


class TestConstruireUserPrompt:
    """Tests de la méthode _construire_user_prompt extraite."""

    def test_prompt_contient_titre_et_resume(self):
        """Le prompt doit contenir le titre et le résumé."""
        prompt = Scripteur._construire_user_prompt(
            titre="Le buisson ardent",
            resume="Moïse et le buisson",
            saison=1, numero=1,
        )
        assert "Le buisson ardent" in prompt
        assert "Moïse et le buisson" in prompt

    def test_prompt_contient_morale(self):
        """Le prompt doit contenir la morale si fournie."""
        prompt = Scripteur._construire_user_prompt(
            titre="Test", resume="Test", saison=1, numero=1,
            morale="La confiance en Dieu",
        )
        assert "La confiance en Dieu" in prompt

    def test_prompt_contient_corrections(self):
        """Le prompt doit contenir les corrections."""
        prompt = Scripteur._construire_user_prompt(
            titre="Test", resume="Test", saison=1, numero=1,
            corrections=["Ajouter plus de bruitages", "Corriger le ton"],
        )
        assert "Ajouter plus de bruitages" in prompt
        assert "Corriger le ton" in prompt

    def test_prompt_contient_scripts_precedents(self):
        """Le prompt doit inclure les dialogues des scripts précédents."""
        scripts = [{
            "episode_id": "S01E01",
            "titre": "Noé",
            "ambiance": "epique",
            "nb_segments": 30,
            "dialogues": ["Papy: Ah mes petits loups", "Antoine: Raconte !"],
        }]
        prompt = Scripteur._construire_user_prompt(
            titre="Test", resume="Test", saison=1, numero=2,
            scripts_precedents=scripts,
        )
        assert "Noé" in prompt
        assert "Ah mes petits loups" in prompt

    def test_prompt_contient_evenement_anniversaire(self):
        """Le prompt doit inclure l'événement anniversaire pour S01E06."""
        prompt = Scripteur._construire_user_prompt(
            titre="Test", resume="Test", saison=1, numero=6,
        )
        assert "anniversaire" in prompt.lower()
        assert "Noémie" in prompt

    def test_prompt_pas_evenement_hors_anniversaire(self):
        """Le prompt ne doit PAS inclure d'événement pour un épisode normal."""
        prompt = Scripteur._construire_user_prompt(
            titre="Test", resume="Test", saison=1, numero=3,
        )
        assert "ÉVÉNEMENT SPÉCIAL" not in prompt


class TestSystemPromptCreatif:
    """Tests des nouvelles instructions créatives dans le system prompt."""

    def test_prompt_contient_veracite_biblique(self):
        """Le system prompt doit contenir l'instruction de véracité biblique."""
        prompt = _construire_system_prompt()
        assert "VÉRACITÉ BIBLIQUE" in prompt

    def test_prompt_contient_traits_obligatoires(self):
        """Le system prompt doit contenir les traits obligatoires."""
        prompt = _construire_system_prompt()
        assert "TRAITS OBLIGATOIRES" in prompt
        assert "chipie" in prompt or "blague" in prompt

    def test_prompt_contient_spatialisation(self):
        """Le system prompt doit contenir les instructions de spatialisation."""
        prompt = _construire_system_prompt()
        assert "SPATIALISATION" in prompt
        assert "fauteuil" in prompt

    def test_prompt_contient_miroirs_age(self):
        """Le system prompt doit contenir les miroirs d'âge."""
        prompt = _construire_system_prompt()
        assert "MIROIRS D'ÂGE" in prompt

    def test_prompt_contient_anti_repetition_sfx(self):
        """Le system prompt doit contenir l'anti-répétition SFX."""
        prompt = _construire_system_prompt()
        assert "ANTI-RÉPÉTITION SFX" in prompt

    def test_prompt_contient_pedagogie(self):
        """Le system prompt doit contenir les instructions de pédagogie."""
        prompt = _construire_system_prompt()
        assert "PÉDAGOGIE" in prompt

    def test_prompt_backstory_pas_instituteur(self):
        """Le prompt ne doit PAS mentionner 'ancien instituteur' (erreur corrigée)."""
        prompt = _construire_system_prompt()
        assert "instituteur" not in prompt

    def test_prompt_backstory_dakar(self):
        """Le prompt doit mentionner Dakar dans le backstory de Papy."""
        prompt = _construire_system_prompt()
        assert "Dakar" in prompt

    def test_prompt_backstory_sonia(self):
        """Le prompt doit mentionner le backstory de Mamie Sonia."""
        prompt = _construire_system_prompt()
        assert "BACKSTORY DE SONIA" in prompt
        assert "Caire" in prompt or "Égypte" in prompt

    def test_prompt_age_noemie_langage(self):
        """La règle 3 doit mentionner le langage adapté à l'âge de Noémie."""
        prompt = _construire_system_prompt()
        assert "5 ans" in prompt
        assert "langage plus simple" in prompt

    def test_prompt_evenement_special_s01e06(self):
        """Le system prompt pour S01E06 doit contenir l'anniversaire."""
        prompt = _construire_system_prompt(numero_saison=1, numero_episode=6)
        assert "ANNIVERSAIRE" in prompt
        assert "Noémie" in prompt

    def test_prompt_pas_evenement_episode_normal(self):
        """Le system prompt pour un épisode normal ne doit pas avoir d'événement."""
        prompt = _construire_system_prompt(numero_saison=1, numero_episode=3)
        assert "ÉVÉNEMENT SPÉCIAL" not in prompt

    def test_personnages_dynamiques_non_numerotes(self):
        """Les personnages dynamiques ne doivent PAS avoir un numéro de règle."""
        import config

        prompt = _construire_system_prompt()
        # Vérifier que la règle 12 existante (arc émotionnel) est présente
        assert "ARC ÉMOTIONNEL" in prompt


class TestEvenementsSpeciaux:
    """Tests du système d'événements spéciaux (anniversaires)."""

    def test_config_anniversaire_noemie(self):
        """L'anniversaire de Noémie doit être configuré en S01E06."""
        import config
        evt = config.EVENEMENTS_SPECIAUX.get((1, 6))
        assert evt is not None
        assert evt["type"] == "anniversaire"
        assert evt["personnage"] == "noemie"

    def test_config_anniversaire_antoine(self):
        """L'anniversaire d'Antoine doit être configuré en S02E04."""
        import config
        evt = config.EVENEMENTS_SPECIAUX.get((2, 4))
        assert evt is not None
        assert evt["type"] == "anniversaire"
        assert evt["personnage"] == "antoine"

    def test_pas_evenement_episode_normal(self):
        """Un épisode sans événement ne doit rien retourner."""
        import config
        assert config.EVENEMENTS_SPECIAUX.get((1, 3)) is None


class TestAgesPersonnages:
    """Tests de la cohérence des âges dans la bible."""

    def test_papy_babou_age(self):
        """Papy Babou doit avoir 66 ans."""
        import config
        bible = config.charger_personnages()
        assert bible["personnages"]["papy_babou"]["age"] == 66

    def test_mamie_sonia_age(self):
        """Mamie Sonia doit avoir 65 ans."""
        import config
        bible = config.charger_personnages()
        assert bible["personnages"]["mamie_sonia"]["age"] == 65

    def test_antoine_age(self):
        """Antoine doit avoir 8 ans."""
        import config
        bible = config.charger_personnages()
        assert bible["personnages"]["antoine"]["age"] == 8

    def test_noemie_age(self):
        """Noémie doit avoir 5 ans."""
        import config
        bible = config.charger_personnages()
        assert bible["personnages"]["noemie"]["age"] == 5

    def test_vieillissement_saison_2(self):
        """En saison 2, Antoine doit avoir 9 ans et Noémie 6 ans."""
        import config
        bible = config.charger_personnages()
        antoine = bible["personnages"]["antoine"]["age_par_saison"]
        noemie = bible["personnages"]["noemie"]["age_par_saison"]
        assert antoine["2"] == 9
        assert noemie["2"] == 6

    def test_bible_fallback_ages(self):
        """Le fallback de la bible doit avoir les bons âges."""
        from agents.scripteur import _BIBLE_FALLBACK
        assert "66 ans" in _BIBLE_FALLBACK
        assert "8 ans" in _BIBLE_FALLBACK
        assert "5 ans" in _BIBLE_FALLBACK
        assert "65 ans" in _BIBLE_FALLBACK


class TestNettoyerOnomatopees:
    """Tests du nettoyage post-génération des onomatopées pour voix IA."""

    @staticmethod
    def _make_script(segments):
        """Construit un script minimal avec les segments donnés."""
        return {"episode": {"segments": segments}}

    def test_segment_pure_onomatopee_supprime(self):
        """Un segment ne contenant que des onomatopées est supprimé."""
        script = self._make_script([
            {"id": "seg_001", "personnage": "noemie", "texte": "Hihihi !", "ton": "joyeux"},
            {"id": "seg_002", "personnage": "antoine", "texte": "C'est cool !", "ton": "enthousiaste"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        assert len(script["episode"]["segments"]) == 1
        assert script["episode"]["segments"][0]["id"] == "seg_002"

    def test_onomatopee_debut_replique_retiree(self):
        """Les onomatopées en début de réplique sont retirées."""
        script = self._make_script([
            {"id": "seg_001", "personnage": "noemie", "texte": "Hihihi ! C'est trop drôle !", "ton": "joyeux"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        assert script["episode"]["segments"][0]["texte"] == "C'est trop drôle !"

    def test_onomatopee_inline_retiree(self):
        """Les rires inline sont retirés."""
        script = self._make_script([
            {"id": "seg_001", "personnage": "antoine", "texte": "C'est génial Hahaha on continue", "ton": "joyeux"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        texte = script["episode"]["segments"][0]["texte"]
        assert "Hahaha" not in texte
        assert "génial" in texte
        assert "continue" in texte

    def test_sfx_pas_touche(self):
        """Les segments SFX ne doivent pas être modifiés."""
        script = self._make_script([
            {"id": "sfx_001", "personnage": "sfx", "texte": "children laughing happily", "ton": "ambiance"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        assert len(script["episode"]["segments"]) == 1
        assert script["episode"]["segments"][0]["texte"] == "children laughing happily"

    def test_oh_lala_retire(self):
        """'Oh là là' en début de réplique est retiré."""
        script = self._make_script([
            {"id": "seg_001", "personnage": "noemie", "texte": "Oh là là ! C'est incroyable !", "ton": "excite"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        assert script["episode"]["segments"][0]["texte"] == "C'est incroyable !"

    def test_euh_hesitation_retiree(self):
        """'Euh...' en début de réplique est retiré."""
        script = self._make_script([
            {"id": "seg_001", "personnage": "antoine", "texte": "Euh... je sais pas trop.", "ton": "neutre"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        assert script["episode"]["segments"][0]["texte"] == "Je sais pas trop."

    def test_recapitalisation(self):
        """Le texte est recapitalisé après nettoyage du préfixe."""
        script = self._make_script([
            {"id": "seg_001", "personnage": "noemie", "texte": "Ah c'est rigolo !", "ton": "joyeux"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        assert script["episode"]["segments"][0]["texte"][0].isupper()

    def test_texte_normal_pas_modifie(self):
        """Un texte sans onomatopées n'est pas modifié."""
        script = self._make_script([
            {"id": "seg_001", "personnage": "papy_babou", "texte": "Mes petits loups, laissez-moi vous raconter.", "ton": "chaleureux"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        assert script["episode"]["segments"][0]["texte"] == "Mes petits loups, laissez-moi vous raconter."

    def test_hahaha_pur_supprime(self):
        """Un segment 'Hahaha !' pur est supprimé."""
        script = self._make_script([
            {"id": "seg_001", "personnage": "antoine", "texte": "Hahaha !", "ton": "joyeux"},
            {"id": "seg_002", "personnage": "papy_babou", "texte": "Oui, c'est drôle.", "ton": "chaleureux"},
        ])
        Scripteur._nettoyer_onomatopees(script)
        assert len(script["episode"]["segments"]) == 1
        assert script["episode"]["segments"][0]["id"] == "seg_002"

    def test_multiple_nettoyages(self, caplog):
        """Plusieurs segments nettoyés doivent être loggés."""
        import logging
        script = self._make_script([
            {"id": "seg_001", "personnage": "noemie", "texte": "Hihihi !", "ton": "joyeux"},
            {"id": "seg_002", "personnage": "antoine", "texte": "Oh ! C'est super !", "ton": "excite"},
            {"id": "seg_003", "personnage": "papy_babou", "texte": "Exactement.", "ton": "chaleureux"},
        ])
        with caplog.at_level(logging.INFO, logger="agents.scripteur"):
            Scripteur._nettoyer_onomatopees(script)
        assert any("Onomatopées nettoyées" in m for m in caplog.messages)

    def test_prompt_contient_regle_voix_ia(self):
        """Le system prompt doit contenir la règle d'adaptation voix IA."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert "ADAPTATION VOIX IA" in SYSTEM_PROMPT_BASE
        assert "onomatopée" in SYSTEM_PROMPT_BASE.lower()
        assert "ElevenLabs" in SYSTEM_PROMPT_BASE

    def test_tics_bible_sans_onomatopees(self):
        """Les tics dans la bible personnages ne doivent plus contenir d'onomatopées."""
        from agents.scripteur import _BIBLE_FALLBACK
        assert "Hihihi" not in _BIBLE_FALLBACK
        assert "Ah mes petits loups" not in _BIBLE_FALLBACK
        assert "Oh non, le pauvre" not in _BIBLE_FALLBACK
