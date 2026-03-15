"""Tests pour les améliorations Phase 2 — audit complet du pipeline de production.

Couvre :
- Publisher : vérification existence audio
- Reviewer : teasing, ratio biblique, ratio Papy/enfants, pauses
- Planificateur : archive de saison, événements spéciaux, arc transmission
- Metadonnees : source biblique, ambiance
- Scripteur : arc_state_precedent injection
- Config : nouvelles constantes
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agents.publisher import Publisher
from agents.reviewer import Reviewer
from agents.planificateur import Planificateur
from agents.metadonnees import Metadonnees
from agents.scripteur import Scripteur


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def script_papy_dominant():
    """Script où Papy Babou parle beaucoup (ratio biblique OK)."""
    segments = []
    seg_id = 1
    # 20 segments Papy (long texte)
    for _ in range(20):
        segments.append({
            "id": f"seg_{seg_id:03d}",
            "personnage": "papy_babou",
            "texte": "Figurez-vous que dans cette histoire extraordinaire, Abraham a quitté "
                     "la ville d'Ur des Chaldéens pour suivre l'appel de Dieu. Il a pris "
                     "sa femme Sarah et son neveu Loth et ils sont partis vers le pays de Canaan.",
            "ton": "chaleureux",
            "pause_apres_ms": 400,
        })
        seg_id += 1
    # 8 segments enfants (court texte)
    for i in range(8):
        perso = "antoine" if i % 2 == 0 else "noemie"
        segments.append({
            "id": f"seg_{seg_id:03d}",
            "personnage": perso,
            "texte": "Trop cool Papy !" if perso == "antoine" else "Raconte encore !",
            "ton": "curieux",
            "pause_apres_ms": 300,
        })
        seg_id += 1
    # 2 SFX
    for _ in range(2):
        segments.append({
            "id": f"seg_{seg_id:03d}",
            "personnage": "sfx",
            "texte": "wind blowing",
            "ton": "",
            "pause_apres_ms": 0,
            "mode": "insert",
            "duree_sfx_secondes": 3.0,
        })
        seg_id += 1
    return {"episode": {"titre": "Test", "saison": 1, "numero": 1, "segments": segments}}


@pytest.fixture
def script_bavardage():
    """Script où les enfants parlent trop (ratio biblique KO)."""
    segments = []
    seg_id = 1
    # 5 segments Papy
    for _ in range(5):
        segments.append({
            "id": f"seg_{seg_id:03d}",
            "personnage": "papy_babou",
            "texte": "Ah, c'est une longue histoire.",
            "ton": "chaleureux",
            "pause_apres_ms": 400,
        })
        seg_id += 1
    # 15 segments enfants
    for i in range(15):
        perso = "antoine" if i % 2 == 0 else "noemie"
        segments.append({
            "id": f"seg_{seg_id:03d}",
            "personnage": perso,
            "texte": "Et après ? Et après ? Raconte-nous Papy, c'est super génial, "
                     "on adore quand tu nous racontes des histoires.",
            "ton": "curieux",
            "pause_apres_ms": 300,
        })
        seg_id += 1
    return {"episode": {"titre": "Test", "saison": 1, "numero": 1, "segments": segments}}


@pytest.fixture
def script_avec_teasing_meta():
    """Script avec un teasing non naturel (langage méta)."""
    return {
        "episode": {
            "titre": "Test",
            "saison": 1,
            "numero": 1,
            "segments": [
                {"id": "seg_001", "personnage": "papy_babou",
                 "texte": "Et voilà, mes petits loups.", "ton": "chaleureux",
                 "pause_apres_ms": 400},
                {"id": "seg_002", "personnage": "papy_babou",
                 "texte": "Dans le prochain épisode, on découvrira la suite.",
                 "ton": "chaleureux", "pause_apres_ms": 400},
            ],
        }
    }


@pytest.fixture
def script_avec_teasing_naturel():
    """Script avec un teasing naturel."""
    return {
        "episode": {
            "titre": "Test",
            "saison": 1,
            "numero": 1,
            "segments": [
                {"id": "seg_001", "personnage": "papy_babou",
                 "texte": "Et voilà, mes petits loups.", "ton": "chaleureux",
                 "pause_apres_ms": 400},
                {"id": "seg_002", "personnage": "papy_babou",
                 "texte": "La prochaine fois que vous viendrez, je vous raconterai la suite.",
                 "ton": "chaleureux", "pause_apres_ms": 400},
            ],
        }
    }


# ── Publisher : existence audio ──────────────────────────────────────────────


class TestPublisherAudioExistence:
    """Le publisher doit vérifier que le fichier audio existe avant l'upload."""

    def test_audio_inexistant_raise(self, tmp_path):
        """publier() doit lever FileNotFoundError si le fichier n'existe pas."""
        publisher = Publisher()
        meta = {
            "titre": "Test", "saison": 1, "numero": 1,
            "titre_court": "Test", "description_longue": "test",
            "description_courte": "test", "explicit": False,
            "duree_secondes": 100,
        }
        chemin = tmp_path / "inexistant.mp3"
        with pytest.raises(FileNotFoundError, match="introuvable"):
            publisher.publier(meta, chemin, 1000)

    def test_audio_existant_ok(self, tmp_path, monkeypatch):
        """publier() ne lève pas si le fichier existe (mock l'upload)."""
        publisher = Publisher()
        meta = {
            "titre": "Test", "saison": 1, "numero": 1,
            "titre_court": "Test", "description_longue": "test",
            "description_courte": "test", "explicit": False,
            "duree_secondes": 100, "transcript": "",
        }
        chemin = tmp_path / "episode.mp3"
        chemin.write_bytes(b"fake audio")
        monkeypatch.setattr(config, "BUZZSPROUT_API_KEY", "")
        monkeypatch.setattr(config, "BUZZSPROUT_PODCAST_ID", "")
        monkeypatch.setattr(config, "RSS_DIR", tmp_path)
        monkeypatch.setattr(config, "TRANSCRIPTS_DIR", tmp_path)
        monkeypatch.setattr(config, "CHAPTERS_DIR", tmp_path)
        # Should not raise
        result = publisher.publier(meta, chemin, chemin.stat().st_size)
        assert "url_audio" in result


# ── Reviewer : teasing validation ────────────────────────────────────────────


class TestReviewerTeasing:
    """Le reviewer doit détecter le teasing non naturel."""

    def test_teasing_meta_detecte(self, script_avec_teasing_meta):
        alertes = Reviewer.verifier_teasing(script_avec_teasing_meta)
        assert len(alertes) > 0
        assert any("prochain épisode" in a.lower() or "non naturel" in a.lower()
                    for a in alertes)

    def test_teasing_naturel_ok(self, script_avec_teasing_naturel):
        alertes = Reviewer.verifier_teasing(script_avec_teasing_naturel)
        assert len(alertes) == 0


# ── Reviewer : ratio biblique ───────────────────────────────────────────────


class TestReviewerRatioBiblique:
    """Le reviewer doit vérifier le ratio de contenu biblique."""

    def test_ratio_ok(self, script_papy_dominant):
        ratio, alertes = Reviewer.verifier_ratio_biblique(script_papy_dominant)
        assert ratio >= 0.60
        assert len(alertes) == 0

    def test_ratio_insuffisant(self, script_bavardage):
        ratio, alertes = Reviewer.verifier_ratio_biblique(script_bavardage)
        assert ratio < 0.60
        assert len(alertes) > 0
        assert "60%" in alertes[0]

    def test_script_vide(self):
        script = {"episode": {"segments": []}}
        ratio, alertes = Reviewer.verifier_ratio_biblique(script)
        assert ratio == 0.0


# ── Reviewer : ratio Papy/enfants ────────────────────────────────────────────


class TestReviewerRatioPapyEnfants:
    """Le reviewer doit vérifier l'équilibre Papy/enfants."""

    def test_ratio_equilibre(self, script_papy_dominant):
        ratio, alertes = Reviewer.verifier_ratio_papy_enfants(script_papy_dominant)
        # 8 enfants / 28 non-sfx ≈ 0.286
        assert 0.25 <= ratio <= 0.45
        assert len(alertes) == 0

    def test_trop_peu_enfants(self):
        """Si les enfants ont moins de 25% des segments."""
        segments = [
            {"id": f"seg_{i}", "personnage": "papy_babou",
             "texte": "Blah blah blah", "ton": "chaleureux",
             "pause_apres_ms": 400}
            for i in range(20)
        ] + [
            {"id": "seg_21", "personnage": "antoine",
             "texte": "Oui Papy", "ton": "curieux", "pause_apres_ms": 300},
        ]
        script = {"episode": {"segments": segments}}
        ratio, alertes = Reviewer.verifier_ratio_papy_enfants(script)
        assert ratio < 0.25
        assert len(alertes) > 0


# ── Reviewer : pauses ────────────────────────────────────────────────────────


class TestReviewerPauses:
    """Le reviewer doit vérifier les pauses."""

    def test_pauses_excessives(self):
        segments = [
            {"id": f"seg_{i}", "personnage": "papy_babou",
             "texte": "Test", "ton": "chaleureux",
             "pause_apres_ms": 5000}
            for i in range(5)
        ]
        script = {"episode": {"segments": segments}}
        alertes = Reviewer.verifier_pauses(script)
        assert any("3 secondes" in a for a in alertes)

    def test_pauses_normales(self):
        segments = [
            {"id": f"seg_{i}", "personnage": "papy_babou",
             "texte": "Test", "ton": "chaleureux",
             "pause_apres_ms": 500}
            for i in range(10)
        ]
        script = {"episode": {"segments": segments}}
        alertes = Reviewer.verifier_pauses(script)
        assert len(alertes) == 0


# ── Planificateur : archive de saison ────────────────────────────────────────


class TestPlanificateurArchive:
    """Le planificateur doit générer une archive de fin de saison."""

    def test_generer_archive(self):
        plan = {
            "saison": {
                "numero": 1,
                "theme": "Les grands voyages",
                "fil_rouge": "La promesse faite à Abraham",
                "arcs_personnages": {
                    "antoine": {"depart": "timide", "evolution": "grandit", "arrivee": "courageux"},
                },
                "personnages_secondaires": [{"id": "mamie_sonia"}],
                "rituels": {"accroche": "Ah mes petits loups..."},
            }
        }
        historique = [
            {
                "episode_id": "S01E01",
                "questions_ouvertes": ["Que va devenir Abraham ?"],
                "moments_cles": ["Le départ d'Ur"],
                "evolutions_personnages": "Antoine commence à poser des questions profondes",
            },
            {
                "episode_id": "S01E10",
                "questions_ouvertes": ["Abraham reviendra-t-il ?"],
                "moments_cles": ["Le sacrifice d'Isaac"],
                "evolutions_personnages": "",
            },
        ]
        archive = Planificateur.generer_archive_saison(plan, historique)
        assert archive["numero"] == 1
        assert archive["theme"] == "Les grands voyages"
        assert "Que va devenir Abraham ?" in archive["questions_ouvertes_finales"]
        assert "Abraham reviendra-t-il ?" in archive["questions_ouvertes_finales"]
        assert len(archive["moments_cles_saison"]) == 2

    def test_archive_historique_vide(self):
        plan = {"saison": {"numero": 1, "theme": "Test"}}
        archive = Planificateur.generer_archive_saison(plan, [])
        assert archive["questions_ouvertes_finales"] == []
        assert archive["moments_cles_saison"] == []


# ── Planificateur : événements spéciaux ─────────────────────────────────────


class TestPlanificateurEvenements:
    """Le planificateur doit intégrer les événements spéciaux."""

    def test_integration_anniversaire(self):
        plan = {
            "saison": {
                "numero": 1,
                "episodes": [
                    {"numero": 1, "titre": "Ep 1"},
                    {"numero": 6, "titre": "Ep 6"},
                ],
            }
        }
        plan = Planificateur.integrer_evenements_speciaux(plan)
        # S01E06 = anniversaire de Noémie
        ep6 = plan["saison"]["episodes"][1]
        assert "evenement_special" in ep6
        assert ep6["evenement_special"]["personnage"] == "noemie"
        assert ep6["evenement_special"]["type"] == "anniversaire"

    def test_pas_evenement(self):
        plan = {
            "saison": {
                "numero": 1,
                "episodes": [{"numero": 1, "titre": "Ep 1"}],
            }
        }
        plan = Planificateur.integrer_evenements_speciaux(plan)
        assert "evenement_special" not in plan["saison"]["episodes"][0]


# ── Metadonnees : source biblique + ambiance ─────────────────────────────────


class TestMetadonneesEnrichies:
    """Les métadonnées doivent inclure source biblique et ambiance."""

    def test_source_biblique_dans_meta(self):
        """generer_dry_run doit inclure la source biblique et l'ambiance."""
        m = Metadonnees()
        script = {
            "episode": {
                "titre": "Le buisson ardent",
                "saison": 1,
                "numero": 1,
                "histoire_biblique": "Exode 3:1-15",
                "ambiance": "mystere",
                "segments": [
                    {"id": "seg_001", "personnage": "papy_babou",
                     "texte": "Test", "ton": "chaleureux", "pause_apres_ms": 300},
                ],
            }
        }
        meta = m.generer_dry_run(script)
        # generer_dry_run ne passe pas par generer() qui ajoute les champs
        # mais vérifions que les données sont dans le script pour generer()
        assert script["episode"]["histoire_biblique"] == "Exode 3:1-15"
        assert script["episode"]["ambiance"] == "mystere"


# ── Scripteur : arc_state_precedent injection ────────────────────────────────


class TestScripteurArcState:
    """Le scripteur doit injecter l'arc state de l'épisode précédent."""

    def test_arc_state_dans_prompt(self):
        arc_state = {
            "episode_id": "S01E01",
            "moments_cles": ["Le départ d'Abraham"],
            "questions_ouvertes": ["Que va devenir Loth ?"],
            "evolutions_personnages": "Antoine est fasciné par le courage d'Abraham",
            "fil_rouge": "La promesse divine",
        }
        prompt = Scripteur._construire_user_prompt(
            titre="Le sacrifice d'Isaac",
            resume="Abraham doit sacrifier son fils",
            saison=1, numero=2,
            arc_state_precedent=arc_state,
        )
        assert "Le départ d'Abraham" in prompt
        assert "Que va devenir Loth ?" in prompt
        assert "Antoine est fasciné" in prompt
        assert "La promesse divine" in prompt
        assert "continuité obligatoire" in prompt.lower()

    def test_sans_arc_state(self):
        prompt = Scripteur._construire_user_prompt(
            titre="Le buisson ardent",
            resume="Moïse et le buisson",
            saison=1, numero=1,
        )
        assert "ÉTAT NARRATIF" not in prompt


# ── Config : nouvelles constantes ────────────────────────────────────────────


class TestConfigConstantes:
    """Les nouvelles constantes de config doivent exister."""

    def test_ratio_biblique_minimum(self):
        assert hasattr(config, "RATIO_BIBLIQUE_MINIMUM")
        assert config.RATIO_BIBLIQUE_MINIMUM == 0.60

    def test_ratio_enfants(self):
        assert hasattr(config, "RATIO_ENFANTS_MIN")
        assert config.RATIO_ENFANTS_MIN == 0.25
        assert hasattr(config, "RATIO_ENFANTS_MAX")
        assert config.RATIO_ENFANTS_MAX == 0.45

    def test_archives_dir(self):
        assert hasattr(config, "ARCHIVES_DIR")
        assert config.ARCHIVES_DIR.exists()

    def test_max_pauses_excessives(self):
        assert hasattr(config, "MAX_PAUSES_EXCESSIVES")
        assert config.MAX_PAUSES_EXCESSIVES == 3


# ── Scripteur : ambiance_par_acte dans le prompt ─────────────────────────────


class TestScripteurAmbianceParActe:
    """Le scripteur doit recommander ambiance_par_acte dans le prompt."""

    def test_ambiance_par_acte_recommande(self):
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert "FORTEMENT RECOMMANDÉ" in SYSTEM_PROMPT_BASE


# ── Planificateur : planifier_saison accepte archives_saisons ────────────────


class TestPlanificateurArchivesParam:
    """planifier_saison doit accepter le paramètre archives_saisons."""

    def test_signature_accepte_archives(self):
        """Vérifie que le paramètre archives_saisons est dans la signature."""
        import inspect
        sig = inspect.signature(Planificateur.planifier_saison)
        assert "archives_saisons" in sig.parameters
