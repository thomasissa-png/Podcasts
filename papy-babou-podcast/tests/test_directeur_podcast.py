"""Tests pour l'agent Directeur Podcast."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.directeur_podcast import (
    DirecteurPodcast,
    PERSONAS,
    _construire_system_prompt_directeur,
    _construire_user_prompt,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def script_exemple():
    """Script minimal pour les tests."""
    return {
        "episode": {
            "titre": "Le buisson ardent",
            "numero": 1,
            "saison": 1,
            "duree_cible_minutes": 25,
            "ambiance": "mystere",
            "ambiance_par_acte": ["calme", "mystere", "solennel"],
            "morale": "Dieu peut appeler chacun de nous, même les plus humbles.",
            "personnages_presents": ["papy_babou", "antoine", "noemie"],
            "moments_cles": ["Moïse voit le buisson", "Dieu parle"],
            "segments": [
                {
                    "id": "seg_001", "personnage": "papy_babou",
                    "texte": "Mes petits loups, ce soir je vais vous raconter une histoire incroyable.",
                    "ton": "chaleureux", "pause_apres_ms": 400,
                },
                {
                    "id": "seg_002", "personnage": "antoine",
                    "texte": "C'est une histoire avec des batailles, Papy ?",
                    "ton": "curieux", "pause_apres_ms": 250,
                },
                {
                    "id": "seg_003", "personnage": "noemie",
                    "texte": "C'est trop drôle ! Raconte vite !",
                    "ton": "excite", "pause_apres_ms": 200,
                },
                {
                    "id": "sfx_001", "personnage": "sfx",
                    "texte": "crackling fire in cozy fireplace",
                    "ton": "ambiance", "pause_apres_ms": 300,
                    "duree_sfx_secondes": 5.0, "mode": "overlay",
                },
                {
                    "id": "seg_004", "personnage": "papy_babou",
                    "texte": "Figurez-vous que Moïse gardait les moutons dans le désert quand il a vu quelque chose d'extraordinaire.",
                    "ton": "mystérieux", "pause_apres_ms": 600,
                },
            ],
        }
    }


@pytest.fixture
def resultat_directeur_valide():
    """Résultat de directeur valide pour les tests."""
    return {
        "directeur": {
            "note_globale": 8.0,
            "verdict": "feu_vert",
            "synthese": "Très bon épisode avec un rythme bien maîtrisé.",
            "axes": {
                "immersion_sonore": {"note": 8, "commentaire": "SFX bien placés."},
                "rythme_accroche": {"note": 7, "commentaire": "Bon rythme."},
                "emotion_personnages": {"note": 9, "commentaire": "Personnages vivants."},
                "valeur_educative": {"note": 8, "commentaire": "Contenu riche."},
                "compatibilite_voix_ia": {"note": 8, "commentaire": "Bien adapté."},
                "qualite_sfx": {"note": 8, "commentaire": "SFX bien décrits.", "sfx_problematiques": []},
            },
            "recommandations": [
                {"priorite": "suggestion", "texte": "Ajouter un SFX de vent."},
            ],
            "points_forts": ["Narration immersive", "Personnages attachants"],
        },
        "personas": {
            "lina_7ans": {
                "reaction": "J'adore quand Papy raconte ! C'est rigolo !",
                "accrocherait": True,
                "moments_preferes": ["Le buisson en feu"],
                "points_decrochage": [],
                "note": 8,
            },
            "noah_10ans": {
                "reaction": "C'est cool les détails sur le désert. J'ai appris des trucs.",
                "accrocherait": True,
                "moments_preferes": ["Les détails historiques"],
                "points_decrochage": [],
                "note": 7,
            },
            "sophie_parent": {
                "reaction": "Le récit est fidèle et bien adapté. Je recommande.",
                "recommanderait": True,
                "points_positifs": ["Fidélité biblique"],
                "reserves": [],
                "note": 9,
            },
        },
        "note_audience": 8.1,
    }


# ── Tests Personas ───────────────────────────────────────────────────────────

class TestPersonas:
    """Tests de la configuration des personas."""

    def test_trois_personas_definies(self):
        """Les 3 personas doivent être définies."""
        assert "lina_7ans" in PERSONAS
        assert "noah_10ans" in PERSONAS
        assert "sophie_parent" in PERSONAS

    def test_lina_est_fille_7_ans(self):
        """Lina doit être une fille de 7 ans."""
        lina = PERSONAS["lina_7ans"]
        assert lina["age"] == 7
        assert lina["profil"] == "fille"
        assert lina["nom"] == "Lina"
        assert len(lina["criteres"]) >= 4

    def test_noah_est_garcon_10_ans(self):
        """Noah doit être un garçon de 10 ans."""
        noah = PERSONAS["noah_10ans"]
        assert noah["age"] == 10
        assert noah["profil"] == "garçon"
        assert noah["nom"] == "Noah"
        assert len(noah["criteres"]) >= 4

    def test_sophie_est_parent_catholique(self):
        """Sophie doit être une parente catholique de 45 ans."""
        sophie = PERSONAS["sophie_parent"]
        assert sophie["age"] == 45
        assert "catholique" in sophie["profil"].lower()
        assert sophie["nom"] == "Sophie"
        assert len(sophie["criteres"]) >= 4

    def test_sophie_poids_plus_eleve(self):
        """Sophie (parent) a le poids le plus élevé : 40% vs 30% pour les enfants."""
        # Vérification via note_audience
        resultat = {
            "personas": {
                "lina_7ans": {"note": 10},
                "noah_10ans": {"note": 10},
                "sophie_parent": {"note": 0},
            }
        }
        note = DirecteurPodcast.note_audience(resultat)
        # 10*0.3 + 10*0.3 + 0*0.4 = 6.0
        assert note == 6.0

    def test_personas_descriptions_non_vides(self):
        """Chaque persona doit avoir une description substantielle."""
        for key, persona in PERSONAS.items():
            assert len(persona["description"]) > 100, f"{key} description trop courte"

    def test_personas_criteres_specifiques(self):
        """Chaque persona a des critères d'évaluation spécifiques."""
        # Lina : vocabulaire, humour, rythme
        lina_criteres = " ".join(PERSONAS["lina_7ans"]["criteres"]).lower()
        assert "vocabulaire" in lina_criteres or "comprends" in lina_criteres

        # Noah : pas bébé, éducatif
        noah_criteres = " ".join(PERSONAS["noah_10ans"]["criteres"]).lower()
        assert "bébé" in noah_criteres or "apprend" in noah_criteres

        # Sophie : fidèle, morale, recommanderait
        sophie_criteres = " ".join(PERSONAS["sophie_parent"]["criteres"]).lower()
        assert "fidèle" in sophie_criteres or "biblique" in sophie_criteres


# ── Tests Prompts ────────────────────────────────────────────────────────────

class TestPrompts:
    """Tests de construction des prompts."""

    def test_system_prompt_contient_personas(self):
        """Le system prompt doit contenir les 3 personas."""
        prompt = _construire_system_prompt_directeur()
        assert "LINA" in prompt
        assert "NOAH" in prompt
        assert "SOPHIE" in prompt

    def test_system_prompt_contient_axes(self):
        """Le system prompt doit contenir les 5 axes d'évaluation."""
        prompt = _construire_system_prompt_directeur()
        assert "IMMERSION SONORE" in prompt
        assert "RYTHME" in prompt
        assert "ÉMOTION" in prompt
        assert "VALEUR ÉDUCATIVE" in prompt
        assert "COMPATIBILITÉ VOIX IA" in prompt

    def test_system_prompt_mentionne_elevenlabs(self):
        """Le system prompt doit mentionner ElevenLabs."""
        prompt = _construire_system_prompt_directeur()
        assert "ElevenLabs" in prompt

    def test_system_prompt_contient_verdicts(self):
        """Le system prompt doit expliquer les 3 verdicts possibles."""
        prompt = _construire_system_prompt_directeur()
        assert "feu_vert" in prompt
        assert "ajustements_mineurs" in prompt
        assert "retravailler" in prompt

    def test_user_prompt_contient_script(self, script_exemple):
        """Le user prompt doit contenir le script JSON."""
        prompt = _construire_user_prompt(script_exemple)
        assert "Le buisson ardent" in prompt
        assert "seg_001" in prompt

    def test_user_prompt_avec_contexte(self, script_exemple):
        """Le user prompt avec contexte doit inclure le score reviewer."""
        contexte = {
            "type_episode": "ouverture",
            "score_reviewer": 8.5,
            "alertes": ["Ratio biblique faible"],
            "metriques": {"ratio_biblique": 0.55},
        }
        prompt = _construire_user_prompt(script_exemple, contexte)
        assert "ouverture" in prompt
        assert "8.5" in prompt
        assert "Ratio biblique faible" in prompt
        assert "0.55" in prompt

    def test_user_prompt_sans_contexte(self, script_exemple):
        """Le user prompt sans contexte ne doit pas avoir de section contexte."""
        prompt = _construire_user_prompt(script_exemple)
        assert "CONTEXTE DE PRODUCTION" not in prompt


# ── Tests Validation Résultat ────────────────────────────────────────────────

class TestValidation:
    """Tests de validation de la structure du résultat."""

    def test_resultat_valide_passe(self, resultat_directeur_valide):
        """Un résultat bien formé passe la validation."""
        DirecteurPodcast._valider_resultat(resultat_directeur_valide)

    def test_directeur_manquant(self):
        """Résultat sans clé 'directeur' doit échouer."""
        with pytest.raises(ValueError, match="directeur"):
            DirecteurPodcast._valider_resultat({"personas": {}})

    def test_personas_manquantes(self):
        """Résultat sans clé 'personas' doit échouer."""
        with pytest.raises(ValueError, match="personas"):
            DirecteurPodcast._valider_resultat({
                "directeur": {
                    "note_globale": 8, "verdict": "feu_vert",
                    "axes": {
                        "immersion_sonore": {}, "rythme_accroche": {},
                        "emotion_personnages": {}, "valeur_educative": {},
                        "compatibilite_voix_ia": {}, "qualite_sfx": {},
                    },
                    "recommandations": [],
                },
            })

    def test_axe_manquant(self, resultat_directeur_valide):
        """Un axe manquant doit être détecté."""
        del resultat_directeur_valide["directeur"]["axes"]["immersion_sonore"]
        with pytest.raises(ValueError, match="immersion_sonore"):
            DirecteurPodcast._valider_resultat(resultat_directeur_valide)

    def test_verdict_invalide(self, resultat_directeur_valide):
        """Un verdict non reconnu doit échouer."""
        resultat_directeur_valide["directeur"]["verdict"] = "peut-etre"
        with pytest.raises(ValueError, match="Verdict invalide"):
            DirecteurPodcast._valider_resultat(resultat_directeur_valide)

    def test_persona_manquante(self, resultat_directeur_valide):
        """Une persona manquante doit échouer."""
        del resultat_directeur_valide["personas"]["lina_7ans"]
        with pytest.raises(ValueError, match="lina_7ans"):
            DirecteurPodcast._valider_resultat(resultat_directeur_valide)

    def test_champ_directeur_manquant(self, resultat_directeur_valide):
        """Un champ obligatoire manquant dans directeur doit échouer."""
        del resultat_directeur_valide["directeur"]["note_globale"]
        with pytest.raises(ValueError, match="note_globale"):
            DirecteurPodcast._valider_resultat(resultat_directeur_valide)


# ── Tests Méthodes Utilitaires ───────────────────────────────────────────────

class TestUtilitaires:
    """Tests des méthodes utilitaires statiques."""

    def test_est_feu_vert_true(self, resultat_directeur_valide):
        """Feu vert détecté correctement."""
        assert DirecteurPodcast.est_feu_vert(resultat_directeur_valide) is True

    def test_est_feu_vert_false(self, resultat_directeur_valide):
        """Non feu vert détecté correctement."""
        resultat_directeur_valide["directeur"]["verdict"] = "retravailler"
        assert DirecteurPodcast.est_feu_vert(resultat_directeur_valide) is False

    def test_a_critiques_false(self, resultat_directeur_valide):
        """Pas de recommandation critique."""
        assert DirecteurPodcast.a_critiques(resultat_directeur_valide) is False

    def test_a_critiques_true(self, resultat_directeur_valide):
        """Recommandation critique détectée."""
        resultat_directeur_valide["directeur"]["recommandations"].append(
            {"priorite": "critique", "texte": "Script trop court"}
        )
        assert DirecteurPodcast.a_critiques(resultat_directeur_valide) is True

    def test_extraire_recommandations_triees(self):
        """Les recommandations doivent être triées par priorité."""
        resultat = {
            "directeur": {
                "recommandations": [
                    {"priorite": "suggestion", "texte": "Ajouter un SFX"},
                    {"priorite": "critique", "texte": "Script trop court"},
                    {"priorite": "important", "texte": "Rythme inégal"},
                ],
            },
        }
        recommandations = DirecteurPodcast.extraire_recommandations(resultat)
        assert len(recommandations) == 3
        assert "[critique]" in recommandations[0]
        assert "[important]" in recommandations[1]
        assert "[suggestion]" in recommandations[2]

    def test_note_audience_ponderation(self):
        """La note audience doit respecter la pondération 30/30/40."""
        resultat = {
            "personas": {
                "lina_7ans": {"note": 10},
                "noah_10ans": {"note": 10},
                "sophie_parent": {"note": 10},
            }
        }
        assert DirecteurPodcast.note_audience(resultat) == 10.0

    def test_note_audience_ponderation_desequilibree(self):
        """Sophie pèse 40% — sa note basse tire la moyenne."""
        resultat = {
            "personas": {
                "lina_7ans": {"note": 10},
                "noah_10ans": {"note": 10},
                "sophie_parent": {"note": 5},
            }
        }
        # 10*0.3 + 10*0.3 + 5*0.4 = 3 + 3 + 2 = 8.0
        assert DirecteurPodcast.note_audience(resultat) == 8.0

    def test_note_audience_personas_vides(self):
        """Note audience avec personas manquantes = 0."""
        assert DirecteurPodcast.note_audience({"personas": {}}) == 0.0


# ── Tests Evaluer (mocké) ────────────────────────────────────────────────────

class TestEvaluer:
    """Tests de la méthode evaluer avec API mockée."""

    def test_evaluer_succes(self, script_exemple, resultat_directeur_valide):
        """Évaluation réussie avec résultat valide."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps(resultat_directeur_valide, ensure_ascii=False))
        ]

        directeur = DirecteurPodcast()
        with patch.object(
            directeur.client.messages, "create", return_value=mock_response
        ), patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.evaluer(script_exemple)

        assert resultat["directeur"]["verdict"] == "feu_vert"
        assert "lina_7ans" in resultat["personas"]

    def test_evaluer_avec_contexte(self, script_exemple, resultat_directeur_valide):
        """L'évaluation passe le contexte au prompt."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps(resultat_directeur_valide, ensure_ascii=False))
        ]

        directeur = DirecteurPodcast()
        contexte = {"type_episode": "ouverture", "score_reviewer": 8.5}

        with patch("config.appel_claude_avec_retry", return_value=mock_response) as mock_api:
            resultat = directeur.evaluer(script_exemple, contexte=contexte)
            # Vérifier que max_tokens est adapté au type ouverture
            call_kwargs = mock_api.call_args
            assert call_kwargs.kwargs.get("max_tokens") == 6144

    def test_evaluer_retry_json_invalide(self, script_exemple, resultat_directeur_valide):
        """L'évaluation doit retenter si le JSON est invalide."""
        mock_bad = MagicMock()
        mock_bad.content = [MagicMock(text="ceci n'est pas du JSON")]
        mock_good = MagicMock()
        mock_good.content = [
            MagicMock(text=json.dumps(resultat_directeur_valide, ensure_ascii=False))
        ]

        directeur = DirecteurPodcast()
        with patch(
            "config.appel_claude_avec_retry",
            side_effect=[mock_bad, mock_good],
        ):
            resultat = directeur.evaluer(script_exemple)
            assert resultat["directeur"]["verdict"] == "feu_vert"

    def test_evaluer_echec_apres_retries(self, script_exemple):
        """L'évaluation échoue après toutes les tentatives."""
        mock_bad = MagicMock()
        mock_bad.content = [MagicMock(text="pas du JSON")]

        directeur = DirecteurPodcast()
        with patch(
            "config.appel_claude_avec_retry",
            return_value=mock_bad,
        ), pytest.raises(ValueError, match="impossible de parser"):
            directeur.evaluer(script_exemple, max_retry=2)

    def test_init_sans_api_key(self, monkeypatch):
        """L'initialisation échoue sans clé API."""
        import config
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            DirecteurPodcast()
