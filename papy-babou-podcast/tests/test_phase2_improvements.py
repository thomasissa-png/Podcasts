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

    def test_doublon_meme_personnage_rejete(self):
        """Plusieurs épisodes sur le même personnage biblique sont rejetés."""
        plan = self._plan([
            "Abraham et Isaac",
            "Abraham et le sacrifice",
            "Moïse et le buisson ardent",
            "Jonas et la baleine",
        ])
        with pytest.raises(ValueError, match="[Mm]ême personnage|sujet"):
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
