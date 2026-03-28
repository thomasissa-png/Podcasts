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


# ── Fixtures Plan Saison ────────────────────────────────────────────────────

@pytest.fixture
def plan_saison_exemple():
    """Plan de saison minimal pour les tests."""
    return {
        "saison": {
            "numero": 1,
            "theme": "Les grands voyages de la Bible",
            "description": "De la Création au sacrifice d'Abraham",
            "fil_rouge": "La découverte de la foi à travers les voyages",
            "arcs_personnages": {
                "antoine": {"depart": "Curieux", "evolution": "Apprend le courage", "arrivee": "Courageux"},
                "noemie": {"depart": "Timide", "evolution": "Gagne en confiance", "arrivee": "Confiante"},
                "papy_babou": {"depart": "Conteur", "evolution": "Transmet sa sagesse", "arrivee": "Fier"},
            },
            "personnages_secondaires": [],
            "rituels": {
                "accroche": "Mes petits loups, installez-vous bien...",
                "au_revoir": "À la prochaine histoire !",
            },
            "episodes": [
                {
                    "numero": 1, "titre": "Au commencement", "type": "ouverture",
                    "histoire_biblique": "La Création du monde",
                    "resume": "Dieu crée le monde en 7 jours.",
                    "morale": "La beauté de la création",
                    "ambiance": "mystere", "duree_cible_minutes": 30,
                    "pretexte": "Jour de pluie chez Papy",
                    "personnages_presents": ["papy_babou", "antoine", "noemie"],
                    "personnages_secondaires_presents": [],
                    "arc_personnage_focus": "antoine",
                    "progression_arc": "Antoine découvre l'émerveillement",
                    "lien_episode_precedent": "",
                    "teasing_episode_suivant": "Papy promet de raconter l'histoire d'un grand bateau",
                    "elements_fil_rouge": "Premier voyage : la naissance du monde",
                    "moments_cles": ["Création de la lumière", "Création des animaux"],
                    "questions_ouvertes": ["Pourquoi Dieu s'est-il reposé le 7e jour ?"],
                },
                {
                    "numero": 2, "titre": "Le grand déluge", "type": "standard",
                    "histoire_biblique": "Noé et l'arche",
                    "resume": "Noé construit l'arche et sauve les animaux.",
                    "morale": "La fidélité et l'obéissance",
                    "ambiance": "dramatique", "duree_cible_minutes": 25,
                    "pretexte": "Orage dehors, Antoine a un peu peur",
                    "personnages_presents": ["papy_babou", "antoine", "noemie"],
                    "personnages_secondaires_presents": [],
                    "arc_personnage_focus": "noemie",
                    "progression_arc": "Noémie apprend qu'on peut avoir peur et être courageux",
                    "lien_episode_precedent": "Rappel de la Création",
                    "teasing_episode_suivant": "Papy promet de raconter un long voyage",
                    "elements_fil_rouge": "Voyage sur les eaux",
                    "moments_cles": ["Construction de l'arche", "L'arc-en-ciel"],
                    "questions_ouvertes": ["Comment les animaux tenaient-ils tous dans l'arche ?"],
                },
            ],
        }
    }


@pytest.fixture
def resultat_directeur_plan_valide():
    """Résultat de directeur valide pour un plan de saison."""
    return {
        "directeur_saison": {
            "note_globale": 8.0,
            "verdict": "feu_vert",
            "synthese": "Plan solide avec une bonne progression.",
            "axes": {
                "coherence_narrative": {"note": 8, "commentaire": "Bon fil rouge."},
                "variete_themes": {"note": 7, "commentaire": "Bonne diversité."},
                "arcs_personnages": {"note": 9, "commentaire": "Arcs crédibles."},
                "rythme_saison": {"note": 8, "commentaire": "Bon rythme."},
                "potentiel_audience": {"note": 7, "commentaire": "Attractif."},
            },
            "recommandations": [
                {"priorite": "suggestion", "episode": 2, "texte": "Renforcer le teasing."},
            ],
            "points_forts": ["Fil rouge cohérent", "Arcs de personnages progressifs"],
        },
        "personas": {
            "lina_7ans": {
                "reaction": "J'ai trop hâte d'écouter l'histoire de Noé !",
                "episodes_preferes": [1],
                "episodes_moins_attractifs": [],
                "accrocherait_toute_la_saison": True,
                "note": 8,
            },
            "noah_10ans": {
                "reaction": "Le déluge c'est cool, j'espère qu'il y a de l'action.",
                "episodes_preferes": [2],
                "episodes_moins_attractifs": [],
                "accrocherait_toute_la_saison": True,
                "note": 7,
            },
            "sophie_parent": {
                "reaction": "Une bonne progression dans l'histoire biblique.",
                "episodes_preferes": [1, 2],
                "reserves": [],
                "recommanderait_la_saison": True,
                "note": 9,
            },
        },
        "note_audience": 8.1,
    }


# ── Tests Plan Saison — Prompts ─────────────────────────────────────────────

from agents.directeur_podcast import (
    _construire_system_prompt_plan_saison,
    _construire_user_prompt_plan,
    _construire_user_prompt_correction,
    SYSTEM_PROMPT_PLAN_SAISON,
    SYSTEM_PROMPT_CORRECTION_PLAN,
)


class TestPromptsplanSaison:
    """Tests des prompts pour l'évaluation de plan de saison."""

    def test_system_prompt_contient_personas(self):
        """Le system prompt injecte les 3 personas."""
        prompt = _construire_system_prompt_plan_saison()
        assert "LINA" in prompt
        assert "NOAH" in prompt
        assert "SOPHIE" in prompt

    def test_system_prompt_contient_5_axes(self):
        """Le system prompt contient les 5 axes d'évaluation."""
        prompt = _construire_system_prompt_plan_saison()
        assert "COHÉRENCE NARRATIVE" in prompt
        assert "VARIÉTÉ DES THÈMES" in prompt
        assert "ARCS DE PERSONNAGES" in prompt
        assert "RYTHME DE SAISON" in prompt
        assert "POTENTIEL AUDIENCE" in prompt

    def test_user_prompt_plan_contient_json(self, plan_saison_exemple):
        """Le prompt utilisateur contient le plan en JSON."""
        prompt = _construire_user_prompt_plan(plan_saison_exemple)
        assert "PLAN DE SAISON À ÉVALUER" in prompt
        assert "Les grands voyages de la Bible" in prompt

    def test_user_prompt_plan_avec_retours(self, plan_saison_exemple, resultat_directeur_plan_valide):
        """Le prompt intègre les retours précédents."""
        prompt = _construire_user_prompt_plan(
            plan_saison_exemple,
            retours_precedents=[resultat_directeur_plan_valide],
        )
        assert "RETOURS PRÉCÉDENTS DU DIRECTEUR (1 tour(s))" in prompt
        assert "Tour 1" in prompt
        assert "NE RÉPÈTE PAS" in prompt

    def test_user_prompt_correction_contient_retours(
        self, plan_saison_exemple, resultat_directeur_plan_valide,
    ):
        """Le prompt de correction contient les 3 retours cumulés."""
        retours = [resultat_directeur_plan_valide] * 3
        prompt = _construire_user_prompt_correction(plan_saison_exemple, retours)
        assert "TES 3 RETOURS PRÉCÉDENTS" in prompt
        assert "Tour 1" in prompt
        assert "Tour 2" in prompt
        assert "Tour 3" in prompt
        assert "PLAN DE SAISON À CORRIGER" in prompt

    def test_system_prompt_correction_demande_reecriture(self):
        """Le prompt de correction demande une réécriture directe."""
        assert "TOI qui prends la main" in SYSTEM_PROMPT_CORRECTION_PLAN
        assert "TOUTES tes recommandations" in SYSTEM_PROMPT_CORRECTION_PLAN


# ── Tests Plan Saison — Validation ───────────────────────────────────────────

class TestValidationPlanSaison:
    """Tests de la validation de résultat de plan de saison."""

    def test_resultat_plan_valide(self, resultat_directeur_plan_valide):
        """Un résultat plan valide passe la validation."""
        DirecteurPodcast._valider_resultat_plan(resultat_directeur_plan_valide)

    def test_cle_directeur_saison_manquante(self):
        """Rejet si clé directeur_saison manquante."""
        with pytest.raises(ValueError, match="directeur_saison"):
            DirecteurPodcast._valider_resultat_plan({"personas": {}})

    def test_cle_personas_manquante(self, resultat_directeur_plan_valide):
        """Rejet si clé personas manquante."""
        del resultat_directeur_plan_valide["personas"]
        with pytest.raises(ValueError, match="personas"):
            DirecteurPodcast._valider_resultat_plan(resultat_directeur_plan_valide)

    def test_axe_manquant(self, resultat_directeur_plan_valide):
        """Rejet si un axe est manquant."""
        del resultat_directeur_plan_valide["directeur_saison"]["axes"]["coherence_narrative"]
        with pytest.raises(ValueError, match="coherence_narrative"):
            DirecteurPodcast._valider_resultat_plan(resultat_directeur_plan_valide)

    def test_verdict_invalide(self, resultat_directeur_plan_valide):
        """Rejet si verdict invalide."""
        resultat_directeur_plan_valide["directeur_saison"]["verdict"] = "moyen"
        with pytest.raises(ValueError, match="Verdict invalide"):
            DirecteurPodcast._valider_resultat_plan(resultat_directeur_plan_valide)

    def test_persona_manquante(self, resultat_directeur_plan_valide):
        """Rejet si une persona est manquante."""
        del resultat_directeur_plan_valide["personas"]["lina_7ans"]
        with pytest.raises(ValueError, match="lina_7ans"):
            DirecteurPodcast._valider_resultat_plan(resultat_directeur_plan_valide)

    def test_champ_directeur_manquant(self, resultat_directeur_plan_valide):
        """Rejet si un champ requis du directeur est manquant."""
        del resultat_directeur_plan_valide["directeur_saison"]["recommandations"]
        with pytest.raises(ValueError, match="recommandations"):
            DirecteurPodcast._valider_resultat_plan(resultat_directeur_plan_valide)


# ── Tests Plan Saison — Utilitaires ──────────────────────────────────────────

class TestUtilitairesPlanSaison:
    """Tests des utilitaires pour plan de saison."""

    def test_note_audience_plan_ponderation(self):
        """La note audience plan respecte Lina 30%, Noah 30%, Sophie 40%."""
        resultat = {
            "personas": {
                "lina_7ans": {"note": 10},
                "noah_10ans": {"note": 10},
                "sophie_parent": {"note": 0},
            }
        }
        assert DirecteurPodcast.note_audience_plan(resultat) == 6.0

    def test_note_audience_plan_sophie_poids_fort(self):
        """Sophie à 10 seule donne 4.0 (40%)."""
        resultat = {
            "personas": {
                "lina_7ans": {"note": 0},
                "noah_10ans": {"note": 0},
                "sophie_parent": {"note": 10},
            }
        }
        assert DirecteurPodcast.note_audience_plan(resultat) == 4.0

    def test_note_audience_plan_parfaite(self):
        """Toutes les notes à 10 donnent 10.0."""
        resultat = {
            "personas": {
                "lina_7ans": {"note": 10},
                "noah_10ans": {"note": 10},
                "sophie_parent": {"note": 10},
            }
        }
        assert DirecteurPodcast.note_audience_plan(resultat) == 10.0


# ── Tests Plan Saison — Evaluer & Corriger ───────────────────────────────────

class TestEvaluerPlanSaison:
    """Tests d'évaluation de plan de saison via API mockée."""

    @pytest.fixture(autouse=True)
    def _mock_api_key(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")

    def test_evaluer_plan_saison_succes(self, plan_saison_exemple, resultat_directeur_plan_valide):
        """L'évaluation retourne un résultat valide."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(resultat_directeur_plan_valide, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.evaluer_plan_saison(plan_saison_exemple)
            assert resultat["directeur_saison"]["verdict"] == "feu_vert"
            assert resultat["directeur_saison"]["note_globale"] == 8.0

    def test_evaluer_plan_saison_avec_retours(
        self, plan_saison_exemple, resultat_directeur_plan_valide,
    ):
        """L'évaluation avec retours précédents fonctionne."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(resultat_directeur_plan_valide, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.evaluer_plan_saison(
                plan_saison_exemple,
                retours_precedents=[resultat_directeur_plan_valide],
            )
            assert "directeur_saison" in resultat

    def test_evaluer_plan_saison_echec_parsing(self, plan_saison_exemple):
        """L'évaluation échoue après toutes les tentatives."""
        mock_bad = MagicMock()
        mock_bad.content = [MagicMock(text="pas du JSON")]

        directeur = DirecteurPodcast()
        with patch(
            "config.appel_claude_avec_retry",
            return_value=mock_bad,
        ), pytest.raises(ValueError, match="impossible de parser"):
            directeur.evaluer_plan_saison(plan_saison_exemple, max_retry=2)

    def test_corriger_plan_saison_succes(
        self, plan_saison_exemple, resultat_directeur_plan_valide,
    ):
        """La correction retourne un plan valide."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(plan_saison_exemple, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        retours = [resultat_directeur_plan_valide] * 3
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            plan_corrige = directeur.corriger_plan_saison(
                plan_saison_exemple, retours,
            )
            assert "saison" in plan_corrige
            assert "episodes" in plan_corrige["saison"]

    def test_corriger_plan_saison_structure_invalide(
        self, plan_saison_exemple, resultat_directeur_plan_valide,
    ):
        """La correction échoue si le résultat n'est pas un plan."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({"invalid": "data"}, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        retours = [resultat_directeur_plan_valide] * 3
        with patch(
            "config.appel_claude_avec_retry",
            return_value=mock_response,
        ), pytest.raises(ValueError, match="impossible de parser"):
            directeur.corriger_plan_saison(plan_saison_exemple, retours, max_retry=1)

    def test_corriger_plan_saison_echec_parsing(
        self, plan_saison_exemple, resultat_directeur_plan_valide,
    ):
        """La correction échoue sur JSON invalide."""
        mock_bad = MagicMock()
        mock_bad.content = [MagicMock(text="pas du json")]

        directeur = DirecteurPodcast()
        retours = [resultat_directeur_plan_valide] * 3
        with patch(
            "config.appel_claude_avec_retry",
            return_value=mock_bad,
        ), pytest.raises(ValueError, match="impossible de parser"):
            directeur.corriger_plan_saison(
                plan_saison_exemple, retours, max_retry=1,
            )


# ── Tests Validation Métadonnées ────────────────────────────────────────────

from agents.directeur_podcast import (
    _SYSTEM_PROMPT_METADONNEES,
    _SYSTEM_PROMPT_GO_NO_GO,
    _SYSTEM_PROMPT_BRIEF_CREATIF,
    _construire_personas_text,
)


class TestValiderMetadonnees:
    """Tests de la validation de métadonnées par le directeur."""

    @pytest.fixture(autouse=True)
    def _mock_api_key(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")

    @pytest.fixture
    def meta_exemple(self):
        return {
            "titre": "Le buisson ardent",
            "description_courte": "Papy Babou raconte l'histoire de Moïse.",
            "mots_cles": ["bible", "moïse", "buisson"],
        }

    @pytest.fixture
    def resultat_meta_valide(self):
        return {
            "verdict": "feu_vert",
            "note": 8,
            "titre_avis": "Titre accrocheur et évocateur.",
            "description_avis": "Bonne description.",
            "suggestions": {
                "titres_alternatifs": ["Moïse et le feu sacré"],
                "description_amelioree": "",
                "mots_cles_manquants": ["enfants"],
            },
            "personas": {
                "lina_7ans": {"cliquerait": True, "commentaire": "Cool !"},
                "noah_10ans": {"cliquerait": True, "commentaire": "Intéressant."},
                "sophie_parent": {"cliquerait": True, "commentaire": "Bon contenu."},
            },
        }

    def test_valider_metadonnees_succes(
        self, script_exemple, meta_exemple, resultat_meta_valide,
    ):
        """La validation métadonnées retourne un résultat valide."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(resultat_meta_valide, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.valider_metadonnees(meta_exemple, script_exemple)
            assert resultat["verdict"] == "feu_vert"
            assert resultat["note"] == 8

    def test_valider_metadonnees_echec_parsing(self, script_exemple, meta_exemple):
        """Échec après tentatives de parsing."""
        mock_bad = MagicMock()
        mock_bad.content = [MagicMock(text="pas du JSON")]

        directeur = DirecteurPodcast()
        with patch(
            "config.appel_claude_avec_retry", return_value=mock_bad,
        ), pytest.raises(ValueError, match="impossible de parser"):
            directeur.valider_metadonnees(meta_exemple, script_exemple, max_retry=1)

    def test_valider_resultat_metadonnees_champ_manquant(self):
        """Rejet si champ obligatoire manquant."""
        with pytest.raises(ValueError, match="verdict"):
            DirecteurPodcast._valider_resultat_metadonnees({"note": 8})

    def test_valider_resultat_metadonnees_verdict_invalide(self):
        """Rejet si verdict invalide."""
        with pytest.raises(ValueError, match="Verdict invalide"):
            DirecteurPodcast._valider_resultat_metadonnees({
                "verdict": "bof", "note": 5,
                "titre_avis": "ok", "description_avis": "ok",
            })

    def test_valider_resultat_metadonnees_ok(self, resultat_meta_valide):
        """Un résultat valide passe la validation."""
        DirecteurPodcast._valider_resultat_metadonnees(resultat_meta_valide)


# ── Tests Go/No-Go Publication ──────────────────────────────────────────────

class TestGoNoGo:
    """Tests du go/no-go final avant publication."""

    @pytest.fixture(autouse=True)
    def _mock_api_key(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")

    @pytest.fixture
    def rapport_exemple(self):
        return {
            "etapes": {
                "script": {"score": 8.0, "validation_humaine": True},
                "directeur_podcast": {"note_globale": 8.0, "verdict": "feu_vert", "note_audience": 7.5},
                "montage": {"duree_secondes": 1500, "validation_humaine": True},
                "metadonnees": {"titre": "Le buisson ardent"},
            },
            "alertes_post_generation": [],
            "metriques": {"ratio_biblique": 0.65},
        }

    @pytest.fixture
    def resultat_go_valide(self):
        return {
            "verdict": "go",
            "note_globale": 8.5,
            "synthese": "Épisode prêt pour publication.",
            "risques": [],
            "points_forts": ["Narration immersive"],
            "conditions": [],
            "personas": {
                "lina_7ans": {"pret_a_publier": True, "commentaire": "Trop bien !"},
                "noah_10ans": {"pret_a_publier": True, "commentaire": "Cool."},
                "sophie_parent": {"pret_a_publier": True, "commentaire": "Recommandé."},
            },
        }

    def test_go_no_go_succes(self, rapport_exemple, resultat_go_valide):
        """Le go/no-go retourne un verdict valide."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(resultat_go_valide, ensure_ascii=False)
        )]
        meta = {"titre": "Le buisson ardent", "description_courte": "..."}

        directeur = DirecteurPodcast()
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.go_no_go_publication(rapport_exemple, meta)
            assert resultat["verdict"] == "go"
            assert resultat["note_globale"] == 8.5

    def test_go_no_go_echec_parsing(self, rapport_exemple):
        """Échec après tentatives de parsing."""
        mock_bad = MagicMock()
        mock_bad.content = [MagicMock(text="nope")]
        meta = {"titre": "Test"}

        directeur = DirecteurPodcast()
        with patch(
            "config.appel_claude_avec_retry", return_value=mock_bad,
        ), pytest.raises(ValueError, match="impossible de parser"):
            directeur.go_no_go_publication(rapport_exemple, meta, max_retry=1)

    def test_valider_resultat_go_no_go_champ_manquant(self):
        """Rejet si champ obligatoire manquant."""
        with pytest.raises(ValueError, match="verdict"):
            DirecteurPodcast._valider_resultat_go_no_go({"note_globale": 8})

    def test_valider_resultat_go_no_go_verdict_invalide(self):
        """Rejet si verdict invalide."""
        with pytest.raises(ValueError, match="Verdict invalide"):
            DirecteurPodcast._valider_resultat_go_no_go({
                "verdict": "maybe", "note_globale": 7, "synthese": "test",
            })

    def test_valider_resultat_go_no_go_ok(self, resultat_go_valide):
        """Un résultat valide passe la validation."""
        DirecteurPodcast._valider_resultat_go_no_go(resultat_go_valide)

    def test_go_no_go_verdict_no_go(self, rapport_exemple):
        """Un verdict no_go est correctement retourné."""
        resultat_nogo = {
            "verdict": "no_go",
            "note_globale": 4.0,
            "synthese": "Épisode pas prêt.",
            "risques": ["Script trop faible"],
            "points_forts": [],
            "conditions": [],
            "personas": {
                "lina_7ans": {"pret_a_publier": False, "commentaire": "Ennuyeux."},
                "noah_10ans": {"pret_a_publier": False, "commentaire": "Nul."},
                "sophie_parent": {"pret_a_publier": False, "commentaire": "Pas recommandé."},
            },
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(resultat_nogo, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.go_no_go_publication(rapport_exemple, {"titre": "Test"})
            assert resultat["verdict"] == "no_go"

    def test_go_no_go_conditionnel(self, rapport_exemple):
        """Un verdict conditionnel est correctement retourné."""
        resultat_cond = {
            "verdict": "conditionnel",
            "note_globale": 6.5,
            "synthese": "Peut passer avec réserves.",
            "risques": ["Note directeur limite"],
            "points_forts": ["Bon sujet"],
            "conditions": ["Améliorer le titre"],
            "personas": {
                "lina_7ans": {"pret_a_publier": True, "commentaire": "Ok."},
                "noah_10ans": {"pret_a_publier": True, "commentaire": "Bof."},
                "sophie_parent": {"pret_a_publier": True, "commentaire": "Moyen."},
            },
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(resultat_cond, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.go_no_go_publication(rapport_exemple, {"titre": "Test"})
            assert resultat["verdict"] == "conditionnel"
            assert len(resultat["conditions"]) > 0


# ── Tests Brief Créatif ─────────────────────────────────────────────────────

class TestBriefCreatif:
    """Tests du brief créatif pré-génération."""

    @pytest.fixture(autouse=True)
    def _mock_api_key(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")

    @pytest.fixture
    def resultat_brief_valide(self):
        return {
            "directives_ton": "Commencer mystérieux, monter en épique, finir tendre.",
            "accroche_suggestion": "Un feu dans le désert...",
            "moments_cles": [
                "Moïse voit le buisson en feu",
                "Dieu parle depuis les flammes",
                "Moïse accepte sa mission",
            ],
            "sfx_attendus": [
                "crackling fire in dry desert",
                "deep reverberant voice from above",
                "gentle wind through desert sand",
            ],
            "ambiances_suggerees": {
                "acte_1": "calme",
                "acte_2": "mystere",
                "acte_3": "solennel",
            },
            "pieges_a_eviter": [
                "Ne pas rendre Dieu effrayant — majestueux mais bienveillant",
                "Éviter un monologue trop long de Papy",
            ],
            "personnages_focus": "Antoine pose des questions pratiques, Noémie s'émerveille.",
        }

    def test_brief_creatif_succes(self, resultat_brief_valide):
        """Le brief créatif retourne un résultat valide."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(resultat_brief_valide, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.brief_creatif(
                titre="Le buisson ardent",
                resume="Moïse voit un buisson en feu...",
                morale="Dieu appelle les humbles.",
            )
            assert "directives_ton" in resultat
            assert len(resultat["moments_cles"]) == 3
            assert len(resultat["sfx_attendus"]) == 3

    def test_brief_creatif_avec_plan(self, resultat_brief_valide):
        """Le brief fonctionne avec episode_plan et contexte_saison."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps(resultat_brief_valide, ensure_ascii=False)
        )]

        directeur = DirecteurPodcast()
        with patch("config.appel_claude_avec_retry", return_value=mock_response):
            resultat = directeur.brief_creatif(
                titre="Le buisson ardent",
                resume="Moïse voit un buisson...",
                morale="Les humbles sont appelés.",
                type_episode="ouverture",
                episode_plan={
                    "pretexte": "Antoine fait un feu de camp",
                    "ambiance": "mystere",
                    "arcs_personnages": {"antoine": "Apprend le courage"},
                },
                contexte_saison={
                    "fil_rouge": "Le courage face à l'inconnu",
                    "theme": "Les grands voyages",
                },
            )
            assert resultat["directives_ton"]

    def test_brief_creatif_echec_parsing(self):
        """Échec après tentatives de parsing."""
        mock_bad = MagicMock()
        mock_bad.content = [MagicMock(text="invalide")]

        directeur = DirecteurPodcast()
        with patch(
            "config.appel_claude_avec_retry", return_value=mock_bad,
        ), pytest.raises(ValueError, match="impossible de parser"):
            directeur.brief_creatif(
                titre="Test", resume="Test", morale="Test", max_retry=1,
            )

    def test_valider_resultat_brief_champ_manquant(self):
        """Rejet si champ obligatoire manquant."""
        with pytest.raises(ValueError, match="directives_ton"):
            DirecteurPodcast._valider_resultat_brief({"moments_cles": [], "pieges_a_eviter": []})

    def test_valider_resultat_brief_ok(self, resultat_brief_valide):
        """Un résultat valide passe la validation."""
        DirecteurPodcast._valider_resultat_brief(resultat_brief_valide)


# ── Tests Prompts des nouvelles méthodes ────────────────────────────────────

class TestNouveauxPrompts:
    """Tests des prompts système des nouvelles méthodes."""

    def test_prompt_metadonnees_contient_personas(self):
        """Le prompt métadonnées mentionne les personas."""
        assert "{personas}" in _SYSTEM_PROMPT_METADONNEES
        prompt = _SYSTEM_PROMPT_METADONNEES.format(personas=_construire_personas_text())
        assert "LINA" in prompt
        assert "NOAH" in prompt
        assert "SOPHIE" in prompt

    def test_prompt_metadonnees_contient_evaluation(self):
        """Le prompt métadonnées contient les axes d'évaluation."""
        assert "TITRE" in _SYSTEM_PROMPT_METADONNEES
        assert "DESCRIPTION" in _SYSTEM_PROMPT_METADONNEES
        assert "MOTS-CLÉS" in _SYSTEM_PROMPT_METADONNEES
        assert "COHÉRENCE" in _SYSTEM_PROMPT_METADONNEES

    def test_prompt_go_no_go_contient_verdicts(self):
        """Le prompt go/no-go contient les 3 verdicts possibles."""
        assert "go" in _SYSTEM_PROMPT_GO_NO_GO
        assert "no_go" in _SYSTEM_PROMPT_GO_NO_GO
        assert "conditionnel" in _SYSTEM_PROMPT_GO_NO_GO

    def test_prompt_go_no_go_mentionne_irréversible(self):
        """Le prompt go/no-go rappelle que c'est irréversible."""
        assert "irréversible" in _SYSTEM_PROMPT_GO_NO_GO

    def test_prompt_brief_creatif_contient_directives(self):
        """Le prompt brief contient les sections attendues."""
        assert "directives_ton" in _SYSTEM_PROMPT_BRIEF_CREATIF
        assert "moments_cles" in _SYSTEM_PROMPT_BRIEF_CREATIF
        assert "sfx_attendus" in _SYSTEM_PROMPT_BRIEF_CREATIF
        assert "pieges_a_eviter" in _SYSTEM_PROMPT_BRIEF_CREATIF
        assert "ambiances_suggerees" in _SYSTEM_PROMPT_BRIEF_CREATIF

    def test_prompt_brief_creatif_mentionne_anglais(self):
        """Le prompt brief rappelle que les SFX doivent être en anglais."""
        assert "ANGLAIS" in _SYSTEM_PROMPT_BRIEF_CREATIF

    def test_construire_personas_text_contient_3_personas(self):
        """Le helper construit le texte des 3 personas."""
        text = _construire_personas_text()
        assert "LINA" in text
        assert "NOAH" in text
        assert "SOPHIE" in text
        assert "7 ans" in text
        assert "10 ans" in text
        assert "45 ans" in text
