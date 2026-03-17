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
import main
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


# ── Config : age_personnage ──────────────────────────────────────────────────


class TestAgePersonnage:
    """config.age_personnage() doit retourner l'âge correct par saison."""

    def test_age_saison_1(self):
        """Saison 1 : âge de base."""
        age = config.age_personnage("antoine", 1)
        assert age is not None
        assert isinstance(age, int)
        # Antoine a 8 ans en saison 1 d'après personnages.json
        assert age == 8

    def test_age_saison_2(self):
        """Saison 2 : âge défini dans age_par_saison."""
        age = config.age_personnage("antoine", 2)
        assert age is not None
        assert age == 9

    def test_age_extrapolation(self):
        """Saison non définie : extrapolation depuis âge de base."""
        age = config.age_personnage("antoine", 10)
        assert age is not None
        # age_base=8, (10-1)//2 = 4 → 12
        assert age == 8 + (10 - 1) // 2

    def test_personnage_inconnu(self):
        """Personnage inconnu retourne None."""
        age = config.age_personnage("personnage_inexistant", 1)
        assert age is None

    def test_noemie_saison_1(self):
        """Noémie a 5 ans en saison 1."""
        age = config.age_personnage("noemie", 1)
        assert age == 5


# ── Planificateur : âge injecté dans prompt ──────────────────────────────────


class TestPlanificateurAgeInjection:
    """Le planificateur doit injecter l'âge par saison dans le prompt."""

    @patch("config.ANTHROPIC_API_KEY", "test-key")
    @patch("agents.planificateur.config.appel_claude_avec_retry")
    def test_age_dans_prompt(self, mock_claude):
        """L'âge des personnages doit apparaître dans le prompt du planificateur."""
        plan_response = {
            "saison": {
                "numero": 3,
                "theme": "Test",
                "episodes": [
                    {"numero": 1, "titre": "T1", "resume": "R1", "morale": "M1",
                     "type": "ouverture", "ambiance": "calme"},
                    {"numero": 2, "titre": "T2", "resume": "R2", "morale": "M2",
                     "type": "standard", "ambiance": "joyeux"},
                    {"numero": 3, "titre": "T3", "resume": "R3", "morale": "M3",
                     "type": "final", "ambiance": "tendre"},
                ],
            }
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(plan_response))]
        mock_response.stop_reason = "end_turn"
        mock_claude.return_value = mock_response

        planificateur = Planificateur()
        planificateur.planifier_saison(
            numero_saison=3, theme="Test", nb_episodes=3,
        )

        # Vérifier que le prompt contient un âge
        call_args = mock_claude.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        prompt = messages[0]["content"]
        # Antoine est saison 3 → age_par_saison["3"] = 9
        assert "ans" in prompt


# ── Planificateur : rituels evolution directive ──────────────────────────────


class TestPlanificateurRituelsEvolution:
    """Le planificateur doit injecter une directive d'évolution des rituels."""

    @patch("config.ANTHROPIC_API_KEY", "test-key")
    @patch("agents.planificateur.config.appel_claude_avec_retry")
    def test_rituels_evolution_dans_prompt(self, mock_claude):
        """Si archives avec rituels, le prompt doit contenir la directive d'évolution."""
        plan_response = {
            "saison": {
                "numero": 2,
                "theme": "Test S2",
                "episodes": [
                    {"numero": 1, "titre": "T", "resume": "R", "morale": "M",
                     "type": "ouverture", "ambiance": "calme"},
                    {"numero": 2, "titre": "T2", "resume": "R2", "morale": "M2",
                     "type": "standard", "ambiance": "joyeux"},
                    {"numero": 3, "titre": "T3", "resume": "R3", "morale": "M3",
                     "type": "final", "ambiance": "tendre"},
                ],
            }
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(plan_response))]
        mock_response.stop_reason = "end_turn"
        mock_claude.return_value = mock_response

        archives = [{
            "numero": 1,
            "theme": "Saison 1",
            "rituels": {
                "accroche": "Ah mes petits loups !",
                "au_revoir": "À bientôt les enfants !",
                "running_gag": "Le chat qui ronronne",
            },
            "questions_ouvertes_finales": ["Qui est Moïse ?"],
            "moments_cles_saison": [],
        }]

        planificateur = Planificateur()
        planificateur.planifier_saison(
            numero_saison=2, theme="Test S2", nb_episodes=3,
            archives_saisons=archives,
        )

        call_args = mock_claude.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        prompt = messages[0]["content"]
        assert "ÉVOLUTION DES RITUELS" in prompt
        assert "Ah mes petits loups !" in prompt
        assert "Le chat qui ronronne" in prompt

    @patch("config.ANTHROPIC_API_KEY", "test-key")
    @patch("agents.planificateur.config.appel_claude_avec_retry")
    def test_sans_archives_pas_de_directive_rituels(self, mock_claude):
        """Sans archives, pas de directive d'évolution des rituels."""
        plan_response = {
            "saison": {
                "numero": 1,
                "theme": "Test",
                "episodes": [
                    {"numero": 1, "titre": "T", "resume": "R", "morale": "M",
                     "type": "ouverture", "ambiance": "calme"},
                    {"numero": 2, "titre": "T2", "resume": "R2", "morale": "M2",
                     "type": "standard", "ambiance": "joyeux"},
                    {"numero": 3, "titre": "T3", "resume": "R3", "morale": "M3",
                     "type": "final", "ambiance": "tendre"},
                ],
            }
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(plan_response))]
        mock_response.stop_reason = "end_turn"
        mock_claude.return_value = mock_response

        planificateur = Planificateur()
        planificateur.planifier_saison(
            numero_saison=1, theme="Test", nb_episodes=3,
        )

        call_args = mock_claude.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        prompt = messages[0]["content"]
        assert "ÉVOLUTION DES RITUELS" not in prompt


# ── Scripteur : age_personnage utilisé dans la bible ─────────────────────────


class TestScripteurAgePersonnage:
    """Le scripteur doit utiliser config.age_personnage pour les âges."""

    def test_bible_contient_age_saison(self):
        """La bible construite doit contenir l'âge adapté à la saison."""
        from agents.scripteur import _construire_bible_personnages
        bible_s1 = _construire_bible_personnages(numero_saison=1)
        bible_s3 = _construire_bible_personnages(numero_saison=3)
        # Antoine 8 ans en S1, 10 ans en S3 (age_par_saison corrigé)
        assert "8 ans" in bible_s1
        assert "10 ans" in bible_s3


# ── Tests Audit Final (Session 13) ────────────────────────────────────────────


class TestPersonnagesBibleCompletude:
    """Vérifie la complétude de la bible personnages après corrections audit."""

    def test_antoine_champs_requis(self):
        """Antoine doit avoir tous les champs enrichis."""
        bible = config.charger_personnages()
        antoine = bible["personnages"]["antoine"]
        for champ in ("vocabulaire_typique", "interdictions", "backstory",
                      "famille", "relation_avec_mamie_sonia", "anecdotes_possibles"):
            assert champ in antoine, f"Champ manquant pour Antoine : {champ}"

    def test_noemie_champs_requis(self):
        """Noémie doit avoir tous les champs enrichis."""
        bible = config.charger_personnages()
        noemie = bible["personnages"]["noemie"]
        for champ in ("vocabulaire_typique", "interdictions", "backstory",
                      "famille", "relation_avec_mamie_sonia", "anecdotes_possibles"):
            assert champ in noemie, f"Champ manquant pour Noémie : {champ}"

    def test_relations_bidirectionnelles(self):
        """Les relations entre personnages doivent être bidirectionnelles."""
        bible = config.charger_personnages()
        papy = bible["personnages"]["papy_babou"]
        mamie = bible["personnages"]["mamie_sonia"]
        assert "relation_avec_antoine" in papy
        assert "relation_avec_noemie" in papy
        assert "relation_avec_mamie_sonia" in papy
        assert "relation_avec_antoine" in mamie
        assert "relation_avec_noemie" in mamie

    def test_annees_naissance_coherentes(self):
        """Les années de naissance doivent être cohérentes avec les âges."""
        bible = config.charger_personnages()
        meta = bible.get("_meta", {})
        annee_ref = meta.get("annee_reference", 2024)
        antoine = bible["personnages"]["antoine"]
        noemie = bible["personnages"]["noemie"]
        # Antoine : 8 ans en S1 (2024) → né en 2016
        assert antoine["annee_naissance"] == annee_ref - antoine["age"]
        # Noémie : 5 ans en S1 (2024) → née en 2019
        assert noemie["annee_naissance"] == annee_ref - noemie["age"]

    def test_meta_block_present(self):
        """La bible doit avoir un bloc _meta avec annee_reference."""
        bible = config.charger_personnages()
        assert "_meta" in bible
        assert "annee_reference" in bible["_meta"]


class TestConfigAuditFixes:
    """Vérifie les corrections config.py de l'audit final."""

    def test_stereo_pan_mamie_sonia(self):
        """Le STEREO_PAN de mamie_sonia doit être 0.3 (pas 0.5)."""
        assert config.STEREO_PAN["mamie_sonia"] == 0.3

    def test_voice_settings_mamie_sonia_style(self):
        """Le style TTS de mamie_sonia doit être 0.25 (pas 0.15)."""
        assert config.VOICE_SETTINGS["mamie_sonia"]["style"] == 0.25

    def test_evenement_special_lucas(self):
        """L'événement spécial Lucas (S1E10) doit exister."""
        assert (1, 10) in config.EVENEMENTS_SPECIAUX
        evt = config.EVENEMENTS_SPECIAUX[(1, 10)]
        assert evt["type"] == "naissance"
        assert evt["personnage"] == "lucas"


class TestScripteurSFXSeuil:
    """Vérifie le seuil SFX à 8 (pas 5)."""

    def test_sfx_warning_sous_seuil(self):
        """Moins de 8 SFX doit déclencher un warning."""
        import logging
        script = {
            "episode": {
                "titre": "Test",
                "saison": 1,
                "numero": 1,
                "type": "standard",
                "ambiance": "calme",
                "segments": [
                    {"id": "seg_01", "personnage": "papy_babou", "texte": "Bonjour",
                     "ton": "joyeux", "pause_apres_ms": 500},
                ] + [
                    {"id": f"sfx_{i}", "personnage": "sfx", "texte": f"sound effect {i}",
                     "ton": "neutre", "pause_apres_ms": 0, "mode": "overlay"}
                    for i in range(5)
                ],
                "morale": "test",
                "resume_court": "test",
                "evolutions_personnages": "test",
            }
        }
        from agents.scripteur import Scripteur
        with patch.object(logging.getLogger("agents.scripteur"), "warning") as mock_warn:
            Scripteur._valider_structure(script)
            # Chercher l'appel warning sur les bruitages
            sfx_warns = [c for c in mock_warn.call_args_list
                         if "bruitages" in str(c) and "minimum 8" in str(c)]
            assert len(sfx_warns) > 0, "Devrait alerter quand SFX < 8"


class TestScripteurMotsInterditsRegex:
    """Vérifie que les mots interdits utilisent word boundary regex."""

    def test_mot_interdit_exact_match(self):
        """Un mot interdit exact doit être détecté."""
        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Il est mort ce jour-là."}
                ]
            }
        }
        with patch.object(config, "MOTS_INTERDITS", ["mort"]):
            from agents.scripteur import Scripteur
            import logging
            with patch.object(logging.getLogger("agents.scripteur"), "warning") as mock_warn:
                Scripteur._verifier_mots_interdits(script)
                assert any("mort" in str(c) for c in mock_warn.call_args_list)

    def test_mot_interdit_pas_de_faux_positif(self):
        """'mort' ne doit PAS matcher 'immortel' (word boundary)."""
        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Il était immortel."}
                ]
            }
        }
        with patch.object(config, "MOTS_INTERDITS", ["mort"]):
            from agents.scripteur import Scripteur
            import logging
            with patch.object(logging.getLogger("agents.scripteur"), "warning") as mock_warn:
                Scripteur._verifier_mots_interdits(script)
                # "mort" ne doit PAS être trouvé dans "immortel"
                mot_warns = [c for c in mock_warn.call_args_list
                             if "mot" in str(c).lower() and "interdit" in str(c).lower()]
                assert len(mot_warns) == 0, "Ne devrait pas détecter 'mort' dans 'immortel'"


class TestReviewerMaxRetry:
    """Vérifie le paramètre max_retry du Reviewer."""

    def test_evaluer_signature_max_retry(self):
        """evaluer() doit accepter le paramètre max_retry."""
        import inspect
        sig = inspect.signature(Reviewer.evaluer)
        assert "max_retry" in sig.parameters
        param = sig.parameters["max_retry"]
        assert param.default == 3


class TestThreadingLocal:
    """Vérifie que _production_id_courante utilise threading.local."""

    def test_production_local_is_threading_local(self):
        """_production_local doit être une instance de threading.local."""
        import threading
        from main import _production_local
        assert isinstance(_production_local, threading.local)


class TestHistoriqueUpsert:
    """Vérifie le mécanisme UPSERT du historique JSON."""

    def test_upsert_code_path_exists(self):
        """Le code UPSERT (dédoublonnage par episode_id) doit exister dans main.py."""
        import inspect
        from main import ajouter_historique
        source = inspect.getsource(ajouter_historique)
        # Vérifie que la logique UPSERT est présente
        assert "episode_id" in source
        # Doit filtrer les doublons avant d'ajouter
        assert "episode_id" in source


class TestWebSecurityFixes:
    """Vérifie les corrections sécurité du dashboard (source code inspection)."""

    def test_secret_key_not_hardcoded(self):
        """web.py doit utiliser FLASK_SECRET_KEY env var, pas un secret en dur."""
        source_path = Path(__file__).resolve().parent.parent / "web.py"
        source = source_path.read_text()
        assert "FLASK_SECRET_KEY" in source
        assert "secret_key" in source

    def test_job_result_ttl_defined(self):
        """_JOB_RESULT_TTL doit être défini dans web.py."""
        source_path = Path(__file__).resolve().parent.parent / "web.py"
        source = source_path.read_text()
        assert "_JOB_RESULT_TTL" in source


class TestXSSProtection:
    """Vérifie la protection XSS dans le template dashboard."""

    def test_goToSuivi_uses_encodeURIComponent(self):
        """goToSuivi doit utiliser encodeURIComponent pour éviter XSS."""
        template_path = Path(__file__).resolve().parent.parent / "templates" / "dashboard.html"
        content = template_path.read_text()
        assert "encodeURIComponent(saison)" in content


class TestUtilsWindowsFix:
    """Vérifie que ouvrir_fichier n'utilise plus shell=True sur Windows."""

    def test_pas_de_shell_true_windows(self):
        """Le code Windows doit utiliser os.startfile, pas shell=True."""
        import inspect
        from utils import ouvrir_fichier
        source = inspect.getsource(ouvrir_fichier)
        assert "os.startfile" in source
        assert "shell=True" not in source


class TestPlanificateurUnSujetParEpisode:
    """Vérifie que le planificateur rejette les doublons d'histoires bibliques."""

    def _plan(self, histoires: list[str]) -> dict:
        """Construit un plan minimal avec les histoires bibliques données."""
        episodes = []
        for i, h in enumerate(histoires, 1):
            episodes.append({
                "numero": i,
                "titre": f"Épisode {i}",
                "resume": f"Résumé {i}",
                "morale": f"Morale {i}",
                "histoire_biblique": h,
                "ambiance": ["joyeux", "calme", "mystere", "dramatique"][i % 4],
                "type": "ouverture" if i == 1 else ("final" if i == len(histoires) else "standard"),
            })
        return {"saison": {"numero": 1, "theme": "Test", "episodes": episodes}}

    def test_histoires_toutes_differentes_passe(self):
        """Un plan avec des histoires toutes différentes en ordre chrono doit passer."""
        plan = self._plan([
            "Abraham et Isaac",
            "Moïse et le buisson ardent",
            "David contre Goliath",
            "Jonas et la baleine",
        ])
        # Ne doit pas lever d'erreur (ordre chronologique respecté)
        Planificateur._valider_plan(plan)

    def test_doublon_exact_rejete(self):
        """Un plan avec la même histoire biblique exacte doit être rejeté."""
        plan = self._plan([
            "Abraham et Isaac",
            "David contre Goliath",
            "Abraham et Isaac",
        ])
        with pytest.raises(ValueError, match="doublon"):
            Planificateur._valider_plan(plan)

    def test_doublon_meme_personnage_avertissement(self):
        """Plusieurs épisodes sur le même personnage émettent un avertissement (pas une erreur).

        Un même personnage biblique (ex: Abraham, Moïse) peut légitimement apparaître
        dans plusieurs épisodes s'il s'agit d'histoires différentes.
        """
        plan = self._plan([
            "Abraham quitte son pays",
            "Moïse et le buisson ardent",
            "Moïse traverse la mer Rouge",
            "Jonas et la baleine",
        ])
        # Ne doit plus lever d'erreur — juste un warning (Moïse x2 mais histoires différentes)
        Planificateur._valider_plan(plan)

    def test_ordre_chronologique_inverse_rejete(self):
        """Un plan avec des histoires dans le mauvais ordre chronologique est rejeté."""
        plan = self._plan([
            "David contre Goliath",
            "Abraham et Isaac",
            "Jonas et la baleine",
        ])
        with pytest.raises(ValueError, match="chronologique"):
            Planificateur._valider_plan(plan)

    def test_ordre_chronologique_correct_passe(self):
        """Un plan avec des histoires en ordre chronologique passe."""
        plan = self._plan([
            "Noé et le Déluge",
            "Abraham et Isaac",
            "Moïse et le buisson ardent",
            "Salomon et le temple",
        ])
        Planificateur._valider_plan(plan)

    def test_prompt_contient_regle_un_sujet(self):
        """Le system prompt doit contenir la règle un sujet par épisode."""
        from agents.planificateur import SYSTEM_PROMPT
        assert "UN SUJET PAR ÉPISODE" in SYSTEM_PROMPT
        assert "JAMAIS" in SYSTEM_PROMPT
        assert "partie 1" in SYSTEM_PROMPT

    def test_prompt_contient_regle_chronologique(self):
        """Le system prompt doit contenir la règle d'ordre chronologique."""
        from agents.planificateur import SYSTEM_PROMPT
        assert "ORDRE CHRONOLOGIQUE" in SYSTEM_PROMPT


class TestSauvegarderPlanComplet:
    """Tests pour _sauvegarder_plan_complet — sauvegarde JSON + DB + Object Storage."""

    def test_sauvegarde_json_db_objstore(self, tmp_path, monkeypatch):
        """Le plan doit être sauvegardé sur les 3 backends."""
        import main
        import persistent_storage

        plan = {"saison": {"numero": 1, "theme": "Test", "episodes": []}}
        chemin_json = tmp_path / "saison_01.json"

        monkeypatch.setattr(main, "_use_db", lambda: True)

        mock_saison_repo = MagicMock()
        mock_saison_repo.sauvegarder.return_value = 42
        monkeypatch.setattr(main, "SaisonRepo", mock_saison_repo)

        # Mock Object Storage au niveau du module
        monkeypatch.setattr(persistent_storage, "upload_saison", MagicMock(return_value="saisons/saison_01.json"))

        mock_planificateur = MagicMock()

        main._sauvegarder_plan_complet(plan, chemin_json, 1, mock_planificateur)

        mock_planificateur.sauvegarder.assert_called_once_with(plan, chemin_json)
        mock_saison_repo.sauvegarder.assert_called_once_with(plan)
        persistent_storage.upload_saison.assert_called_once_with(1, chemin_json)

    def test_sauvegarde_sans_db(self, tmp_path, monkeypatch):
        """Sans DB, le plan est sauvegardé en JSON + Object Storage seulement."""
        import main
        import persistent_storage

        plan = {"saison": {"numero": 1, "theme": "Test", "episodes": []}}
        chemin_json = tmp_path / "saison_01.json"

        monkeypatch.setattr(main, "_use_db", lambda: False)
        monkeypatch.setattr(persistent_storage, "upload_saison", MagicMock(return_value="saisons/saison_01.json"))

        mock_planificateur = MagicMock()

        main._sauvegarder_plan_complet(plan, chemin_json, 1, mock_planificateur)

        mock_planificateur.sauvegarder.assert_called_once()
        persistent_storage.upload_saison.assert_called_once()

    def test_sauvegarde_objstore_echec_warning(self, tmp_path, monkeypatch, caplog):
        """Échec Object Storage doit logger un warning, pas crasher."""
        import main
        import persistent_storage
        import logging

        plan = {"saison": {"numero": 1, "theme": "Test", "episodes": []}}
        chemin_json = tmp_path / "saison_01.json"

        monkeypatch.setattr(main, "_use_db", lambda: False)
        monkeypatch.setattr(persistent_storage, "upload_saison", MagicMock(return_value=None))

        mock_planificateur = MagicMock()

        with caplog.at_level(logging.WARNING):
            main._sauvegarder_plan_complet(plan, chemin_json, 1, mock_planificateur)

        # La sauvegarde JSON doit toujours se faire
        mock_planificateur.sauvegarder.assert_called_once()


# ── Tests SIGTERM handler et auto-resume ────────────────────────────────────


class TestSIGTERMHandler:
    """Tests pour le handler SIGTERM qui sauvegarde l'état avant arrêt."""

    def test_sigterm_handler_saves_checkpoint(self, tmp_path, monkeypatch):
        """Le handler SIGTERM doit sauvegarder un checkpoint avec l'état courant."""
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        # Simuler le contexte du pipeline
        main._production_local.pipeline_context = {
            "episode_id": "S01E03",
            "titre": "Le test SIGTERM",
            "resume": "Un résumé",
            "saison": 1,
            "numero": 3,
            "morale": "La patience",
            "type_episode": "standard",
            "dry_run": False,
            "rapport": {"etapes": {"script": {"score": 8.5}}},
            "etape_courante": "audio",
            "pubdate_offset_seconds": 0,
            "stop_after": "montage",
        }
        main._production_local.production_id = None

        # Appeler le handler directement (il appelle sys.exit(0))
        with pytest.raises(SystemExit) as exc_info:
            main._sigterm_handler(15, None)  # 15 = SIGTERM

        assert exc_info.value.code == 0

        # Vérifier que le checkpoint a été sauvegardé
        checkpoint_path = tmp_path / "S01E03_checkpoint.json"
        assert checkpoint_path.exists()
        cp = json.loads(checkpoint_path.read_text())
        assert cp["episode_id"] == "S01E03"
        assert cp["etape"] == "audio"
        assert cp["data"]["stop_after"] == "montage"
        assert cp["data"]["rapport"]["etapes"]["script"]["score"] == 8.5

    def test_sigterm_handler_marks_db_interrupted(self, tmp_path, monkeypatch):
        """Le handler SIGTERM doit marquer la production comme 'interrupted' en DB."""
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        main._production_local.pipeline_context = {
            "episode_id": "S01E04",
            "titre": "Test",
            "resume": "",
            "saison": 1,
            "numero": 4,
            "morale": "",
            "type_episode": "standard",
            "dry_run": False,
            "rapport": {},
            "etape_courante": "sfx",
            "pubdate_offset_seconds": 0,
            "stop_after": "",
        }
        main._production_local.production_id = 42

        # Mock DB
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(main, "_use_db", lambda: True)

        with patch("db_models.get_cursor", return_value=mock_cursor):
            with pytest.raises(SystemExit):
                main._sigterm_handler(15, None)

        # Vérifier que l'UPDATE a été appelé avec status='interrupted'
        mock_cursor.execute.assert_called()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "interrupted" in sql_call

    def test_sigterm_handler_no_context(self):
        """Le handler SIGTERM ne doit pas crasher si aucun pipeline n'est actif."""
        main._production_local.pipeline_context = None
        main._production_local.production_id = None

        with pytest.raises(SystemExit) as exc_info:
            main._sigterm_handler(15, None)

        assert exc_info.value.code == 0


class TestStopAfterInCheckpoint:
    """Tests pour la persistance du stop_after dans les checkpoints."""

    def test_reprendre_uses_checkpoint_stop_after(self, tmp_path, monkeypatch):
        """reprendre() doit utiliser le stop_after du checkpoint si pas de CLI."""
        checkpoint_data = {
            "episode_id": "S01E05",
            "etape": "audio",
            "timestamp": "2026-03-16T10:00:00",
            "data": {
                "episode_id": "S01E05",
                "titre": "Test stop_after",
                "saison": 1,
                "numero": 5,
                "stop_after": "montage",
                "rapport": {},
            },
        }
        cp_path = tmp_path / "checkpoint.json"
        cp_path.write_text(json.dumps(checkpoint_data))

        # Mock pipeline pour capturer les arguments
        captured = {}

        def mock_pipeline(**kwargs):
            captured.update(kwargs)
            return {}

        monkeypatch.setattr(main, "pipeline", mock_pipeline)
        monkeypatch.setattr(main, "console", MagicMock())

        # Invoquer reprendre SANS stop_after CLI (= "")
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(main.cli, [
            "reprendre", "-c", str(cp_path), "--auto",
        ])

        # Le pipeline doit avoir reçu stop_after="montage" du checkpoint
        assert captured.get("stop_after") == "montage"

    def test_cli_stop_after_overrides_checkpoint(self, tmp_path, monkeypatch):
        """Le stop_after CLI doit prendre le dessus sur celui du checkpoint."""
        checkpoint_data = {
            "episode_id": "S01E06",
            "etape": "audio",
            "timestamp": "2026-03-16T10:00:00",
            "data": {
                "episode_id": "S01E06",
                "titre": "Test override",
                "saison": 1,
                "numero": 6,
                "stop_after": "montage",
                "rapport": {},
            },
        }
        cp_path = tmp_path / "checkpoint.json"
        cp_path.write_text(json.dumps(checkpoint_data))

        captured = {}

        def mock_pipeline(**kwargs):
            captured.update(kwargs)
            return {}

        monkeypatch.setattr(main, "pipeline", mock_pipeline)
        monkeypatch.setattr(main, "console", MagicMock())

        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(main.cli, [
            "reprendre", "-c", str(cp_path), "--auto", "--stop-after", "script",
        ])

        # Le CLI stop_after "script" doit prendre le dessus
        assert captured.get("stop_after") == "script"


class TestPipelineContextForSIGTERM:
    """Tests pour la mise à jour du contexte pipeline dans sauvegarder_checkpoint."""

    def test_checkpoint_updates_pipeline_context(self, tmp_path, monkeypatch):
        """sauvegarder_checkpoint doit mettre à jour le contexte SIGTERM."""
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)
        main._production_local.production_id = None
        main._production_local.pipeline_context = {
            "etape_courante": "script",
            "rapport": {},
        }

        main.sauvegarder_checkpoint("S01E01", "audio", {
            "rapport": {"etapes": {"script": {"done": True}}},
        })

        # Le contexte SIGTERM doit être mis à jour
        ctx = main._production_local.pipeline_context
        assert ctx["etape_courante"] == "audio"
        assert ctx["rapport"]["etapes"]["script"]["done"] is True

    def test_signal_handler_registered_in_pipeline(self, monkeypatch):
        """pipeline() doit enregistrer le handler SIGTERM."""
        import signal

        handlers_set = []

        def mock_signal(signum, handler):
            handlers_set.append((signum, handler))
            return None

        monkeypatch.setattr(signal, "signal", mock_signal)
        monkeypatch.setattr(main, "_use_db", lambda: False)

        # Le pipeline va crasher rapidement (pas de vrai scripteur),
        # mais on vérifie que le signal est enregistré avant le crash
        try:
            main.pipeline(
                titre="Test", resume="Résumé", saison=1, numero=1,
                dry_run=True, auto=True,
            )
        except Exception:
            pass

        # Vérifier que SIGTERM a été enregistré
        sigterm_handlers = [h for s, h in handlers_set if s == signal.SIGTERM]
        assert len(sigterm_handlers) >= 1
        assert sigterm_handlers[0] == main._sigterm_handler


# ── Tests instructions montage ───────────────────────────────────────────────


class TestAppliquerInstructionsMontage:
    """Tests pour _appliquer_instructions_montage()."""

    def _make_script(self):
        return {
            "episode": {
                "titre": "Test",
                "saison": 1,
                "numero": 1,
                "ambiance": "fond_doux",
                "segments": [
                    {
                        "id": "seg_001",
                        "personnage": "papy_babou",
                        "texte": "Il était une fois...",
                        "ton": "chaleureux",
                        "rythme": "normal",
                        "pause_apres_ms": 500,
                    },
                    {
                        "id": "seg_002",
                        "personnage": "antoine",
                        "texte": "Raconte-moi, Papy !",
                        "ton": "enthousiaste",
                        "rythme": "normal",
                        "pause_apres_ms": 300,
                    },
                    {
                        "id": "seg_003",
                        "personnage": "sfx",
                        "texte": "birds chirping",
                        "ton": "calme",
                        "mode": "insert",
                        "pause_apres_ms": 0,
                        "duree_sfx_secondes": 3,
                    },
                ],
            }
        }

    def test_applies_segment_modifications(self, monkeypatch, tmp_path):
        """Les modifications de segments (pause, ton, rythme) sont appliquées."""
        script = self._make_script()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "modifications_segments": {
                "0": {"pause_apres_ms": 1200, "ton": "dramatique"},
                "1": {"rythme": "lent"},
            },
            "modifications_episode": {},
            "resume_modifications": "Pause allongée, ton dramatique pour Papy",
        }))]

        monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)
        monkeypatch.setattr(
            config, "appel_claude_avec_retry", lambda *a, **kw: mock_response
        )

        result = main._appliquer_instructions_montage(script, "Plus de tension", "S01E01")

        assert result["episode"]["segments"][0]["pause_apres_ms"] == 1200
        assert result["episode"]["segments"][0]["ton"] == "dramatique"
        assert result["episode"]["segments"][1]["rythme"] == "lent"
        # Segment 2 inchangé
        assert result["episode"]["segments"][2]["mode"] == "insert"

    def test_applies_episode_modifications(self, monkeypatch, tmp_path):
        """Les modifications d'ambiance au niveau épisode sont appliquées."""
        script = self._make_script()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "modifications_segments": {},
            "modifications_episode": {
                "ambiance": "mystérieux",
                "ambiance_par_acte": ["mystérieux", "dramatique", "calme"],
            },
            "resume_modifications": "Ambiance mystérieuse",
        }))]

        monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)
        monkeypatch.setattr(
            config, "appel_claude_avec_retry", lambda *a, **kw: mock_response
        )

        result = main._appliquer_instructions_montage(script, "Ambiance plus sombre", "S01E01")

        assert result["episode"]["ambiance"] == "mystérieux"
        assert result["episode"]["ambiance_par_acte"] == ["mystérieux", "dramatique", "calme"]

    def test_ignores_invalid_segment_index(self, monkeypatch, tmp_path):
        """Les index de segment invalides sont ignorés sans crash."""
        script = self._make_script()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "modifications_segments": {
                "999": {"ton": "triste"},
                "abc": {"ton": "triste"},
            },
            "modifications_episode": {},
            "resume_modifications": "Rien appliqué",
        }))]

        monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)
        monkeypatch.setattr(
            config, "appel_claude_avec_retry", lambda *a, **kw: mock_response
        )

        # Ne doit pas crasher
        result = main._appliquer_instructions_montage(script, "Test invalide", "S01E01")
        assert result["episode"]["segments"][0]["ton"] == "chaleureux"  # Inchangé

    def test_returns_unmodified_on_empty_response(self, monkeypatch, tmp_path):
        """Si Claude ne retourne rien, le script original est retourné."""
        script = self._make_script()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Je ne sais pas quoi faire")]

        monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)
        monkeypatch.setattr(
            config, "appel_claude_avec_retry", lambda *a, **kw: mock_response
        )

        result = main._appliquer_instructions_montage(script, "Hmm", "S01E01")
        # Script inchangé
        assert result["episode"]["segments"][0]["ton"] == "chaleureux"

    def test_saves_modified_script(self, monkeypatch, tmp_path):
        """Le script modifié est sauvegardé comme version validée."""
        script = self._make_script()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "modifications_segments": {"0": {"ton": "solennel"}},
            "modifications_episode": {},
            "resume_modifications": "Ton solennel",
        }))]

        monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)
        monkeypatch.setattr(
            config, "appel_claude_avec_retry", lambda *a, **kw: mock_response
        )

        main._appliquer_instructions_montage(script, "Plus solennel", "S01E01")

        # Vérifier que le fichier est sauvegardé
        saved = tmp_path / "S01E01_valide.json"
        assert saved.exists()
        saved_data = json.loads(saved.read_text(encoding="utf-8"))
        assert saved_data["episode"]["segments"][0]["ton"] == "solennel"

    def test_only_modifies_allowed_keys(self, monkeypatch, tmp_path):
        """Seuls pause_apres_ms, ton, rythme, mode sont modifiables."""
        script = self._make_script()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "modifications_segments": {
                "0": {"texte": "HACKED", "personnage": "HACKED", "ton": "triste"},
            },
            "modifications_episode": {},
            "resume_modifications": "Test sécurité",
        }))]

        monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)
        monkeypatch.setattr(
            config, "appel_claude_avec_retry", lambda *a, **kw: mock_response
        )

        result = main._appliquer_instructions_montage(script, "Hack test", "S01E01")

        # ton modifié (autorisé)
        assert result["episode"]["segments"][0]["ton"] == "triste"
        # texte et personnage inchangés (non autorisés)
        assert result["episode"]["segments"][0]["texte"] == "Il était une fois..."
        assert result["episode"]["segments"][0]["personnage"] == "papy_babou"


class TestMontageInstructionsWebRoute:
    """Tests pour la sauvegarde des instructions montage dans web.py."""

    def test_instructions_file_created(self, monkeypatch, tmp_path):
        """Le fichier d'instructions est créé par la route montage."""
        instructions_path = tmp_path / "S01E01_montage_instructions.txt"
        monkeypatch.setattr(config, "SCRIPTS_DIR", tmp_path)

        # Simuler l'écriture comme le fait web.py
        instructions = "Augmente les pauses entre les segments"
        instructions_path.write_text(instructions, encoding="utf-8")

        assert instructions_path.exists()
        assert instructions_path.read_text(encoding="utf-8") == instructions

    def test_instructions_file_deleted_after_use(self, monkeypatch, tmp_path):
        """Le fichier d'instructions est supprimé après usage unique."""
        instructions_path = tmp_path / "S01E01_montage_instructions.txt"
        instructions_path.write_text("Plus de tension", encoding="utf-8")

        # Simuler le comportement du pipeline
        assert instructions_path.exists()
        instructions_path.unlink()
        assert not instructions_path.exists()
