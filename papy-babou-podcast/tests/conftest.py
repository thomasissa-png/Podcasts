"""Fixtures partagées pour les tests du projet Papy Babou."""

import sys
from pathlib import Path

import pytest

# Ajouter le répertoire du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    """Injecte une fausse cle API pour eviter les erreurs dans les constructeurs d'agents."""
    import config
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test-fake-key")


@pytest.fixture
def script_exemple():
    """Script JSON minimal valide pour les tests."""
    return {
        "episode": {
            "titre": "Le buisson ardent",
            "numero": 1,
            "saison": 1,
            "duree_cible_minutes": 13,
            "ambiance": "mystere",
            "morale": "Dieu peut accomplir de grandes choses a travers nous",
            "segments": [
                {
                    "id": "seg_001",
                    "personnage": "narrateur",
                    "texte": "Bienvenue dans Les Histoires de Papy Babou.",
                    "ton": "neutre",
                    "pause_apres_ms": 1000,
                },
                {
                    "id": "seg_002",
                    "personnage": "papy_babou",
                    "texte": "Ah mes petits loups ! Venez vous asseoir, j'ai une histoire formidable à vous raconter aujourd'hui.",
                    "ton": "chaleureux",
                    "pause_apres_ms": 800,
                },
                {
                    "id": "seg_003",
                    "personnage": "antoine",
                    "texte": "C'est quoi l'histoire, Papy ?",
                    "ton": "curieux",
                    "pause_apres_ms": 500,
                },
                {
                    "id": "seg_004",
                    "personnage": "noemie",
                    "texte": "Oh oui, raconte-nous Papy !",
                    "ton": "enthousiaste",
                    "pause_apres_ms": 500,
                },
                {
                    "id": "seg_005",
                    "personnage": "papy_babou",
                    "texte": "Figurez-vous que c'est l'histoire de Moïse et du buisson ardent. Un jour, Moïse gardait les moutons dans le désert.",
                    "ton": "chaleureux",
                    "pause_apres_ms": 1200,
                },
            ],
        }
    }


@pytest.fixture
def script_avec_sfx_overlay():
    """Script avec des SFX en mode overlay et insert."""
    return {
        "episode": {
            "titre": "Le buisson ardent",
            "numero": 1,
            "saison": 1,
            "ambiance": "mystere",
            "morale": "La confiance en Dieu",
            "segments": [
                {
                    "id": "seg_001",
                    "personnage": "narrateur",
                    "texte": "Bienvenue.",
                    "ton": "neutre",
                    "pause_apres_ms": 500,
                },
                {
                    "id": "sfx_001",
                    "personnage": "sfx",
                    "texte": "vent dans le desert",
                    "ton": "ambiance",
                    "pause_apres_ms": 0,
                    "duree_sfx_secondes": 5.0,
                    "mode": "overlay",
                },
                {
                    "id": "seg_002",
                    "personnage": "papy_babou",
                    "texte": "Ah mes petits loups !",
                    "ton": "chaleureux",
                    "pause_apres_ms": 800,
                },
                {
                    "id": "sfx_002",
                    "personnage": "sfx",
                    "texte": "tonnerre",
                    "ton": "ambiance",
                    "pause_apres_ms": 500,
                    "duree_sfx_secondes": 3.0,
                    "mode": "insert",
                },
            ],
        }
    }


@pytest.fixture
def review_exemple():
    """Résultat de review minimal valide pour les tests."""
    return {
        "review": {
            "score": 8,
            "corrections": ["Ajout d'un tic de langage manquant pour Papy Babou"],
            "alertes": [],
            "details_score": {
                "coherence_personnage": 2,
                "adequation_age": 1.5,
                "fidelite_biblique": 2,
                "rythme_structure": 1.5,
                "duree_format": 1,
            },
        },
        "episode": {
            "titre": "Le buisson ardent",
            "numero": 1,
            "saison": 1,
            "duree_cible_minutes": 13,
            "ambiance": "mystere",
            "morale": "La confiance en Dieu",
            "segments": [
                {
                    "id": "seg_001",
                    "personnage": "narrateur",
                    "texte": "Bienvenue dans Les Histoires de Papy Babou.",
                    "ton": "neutre",
                    "pause_apres_ms": 1000,
                },
            ],
        },
    }
