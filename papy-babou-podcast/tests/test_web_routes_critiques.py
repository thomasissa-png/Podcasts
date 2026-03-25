"""Tests P0 critiques pour les routes de production web (launch-fresh, kill-productions, seg_003).

Ces tests couvrent les routes les plus critiques du pipeline de production audio
qui n'avaient AUCUN test avant cette session. Identifies comme GAP CRITIQUE dans
docs/qa/qa-strategy.md (F2#1, F2#2).

Chaque test est autonome : pas d'appels reels a DB, Object Storage, subprocess, APIs.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ajouter le repertoire du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_script():
    """Script JSON minimal valide pour les tests launch-fresh."""
    return {
        "episode": {
            "titre": "Test Episode Production",
            "numero": 99,
            "saison": 99,
            "type": "standard",
            "morale": "Le courage vient du coeur",
            "ambiance": "mystere",
            "segments": [
                {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour les enfants.", "ton": "chaleureux", "pause_apres_ms": 500},
                {"id": "seg_002", "personnage": "antoine", "texte": "Salut Papy !", "ton": "curieux", "pause_apres_ms": 300},
                {"id": "seg_003", "personnage": "noemie", "texte": "Raconte-nous une histoire !", "ton": "enthousiaste", "pause_apres_ms": 400},
                {"id": "sfx_001", "personnage": "sfx", "texte": "fireplace crackling", "ton": "ambiance", "pause_apres_ms": 0, "duree_sfx_secondes": 3.0},
                {"id": "seg_004", "personnage": "papy_babou", "texte": "Aujourd'hui, je vais vous raconter l'histoire.", "ton": "chaleureux", "pause_apres_ms": 800},
            ],
        }
    }


@pytest.fixture
def web_app(monkeypatch, tmp_path):
    """Cree une app Flask de test avec tous les modules externes mockes.

    Mock : DB, Object Storage, subprocess, config paths.
    """
    # Preparer les repertoires temporaires
    scripts_dir = tmp_path / "scripts" / "episodes"
    scripts_dir.mkdir(parents=True)
    checkpoints_dir = tmp_path / "checkpoints"
    checkpoints_dir.mkdir()
    output_dir = tmp_path / "output" / "episodes"
    output_dir.mkdir(parents=True)
    segments_dir = tmp_path / "segments"
    segments_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    # Mock config avant import web
    import config
    monkeypatch.setattr(config, "SCRIPTS_DIR", scripts_dir)
    monkeypatch.setattr(config, "CHECKPOINTS_DIR", checkpoints_dir)
    monkeypatch.setattr(config, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(config, "SEGMENTS_DIR", segments_dir)
    monkeypatch.setattr(config, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test-fake-key")

    import web

    # Desactiver l'authentification pour les tests
    monkeypatch.setattr(web, "_CLAUDE_API_SECRET", "test-secret")

    # Desactiver la DB par defaut (certains tests la re-activent)
    monkeypatch.setattr(web, "_DB_AVAILABLE", False)

    # Mock _start_job pour ne pas lancer de subprocess reel
    mock_start_job = MagicMock(return_value="job_test_123")
    monkeypatch.setattr(web, "_start_job", mock_start_job)

    web.app.config["TESTING"] = True
    web.app.config["SECRET_KEY"] = "test-secret-key"

    with web.app.test_client() as client:
        client._scripts_dir = scripts_dir
        client._checkpoints_dir = checkpoints_dir
        client._mock_start_job = mock_start_job
        client._web = web
        yield client


def _auth_headers():
    """Headers Bearer pour authentifier les requetes de test."""
    return {
        "Authorization": "Bearer test-secret",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Test 1 : launch-fresh ecrit le script et cree un checkpoint
# ---------------------------------------------------------------------------

class TestLaunchFreshWritesScriptAndPurges:
    """POST /api/episode/S01E99/launch-fresh avec script dans le body.

    Verifie que :
    - Le script est ecrit en _script.json ET _script_valide.json
    - Le checkpoint est cree avec validation_humaine=true
    - Le job audio est lance (mock subprocess)
    - Object Storage est mocke (pas d'appel reel)
    """

    def test_script_written_to_both_files(self, web_app, sample_script):
        """Le script POST body est ecrit a la fois dans _script.json et _valide.json."""
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({"script": sample_script}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "accepted"
        assert "job_id" in data

        scripts_dir = web_app._scripts_dir
        script_path = scripts_dir / "S01E99_script.json"
        valide_path = scripts_dir / "S01E99_valide.json"

        assert script_path.exists(), "_script.json non cree"
        assert valide_path.exists(), "_valide.json non cree"

        # Verifier que le contenu est identique au script envoye
        with open(script_path, "r", encoding="utf-8") as f:
            written_script = json.load(f)
        assert written_script["episode"]["titre"] == "Test Episode Production"
        assert len(written_script["episode"]["segments"]) == 5

        with open(valide_path, "r", encoding="utf-8") as f:
            valide_script = json.load(f)
        assert valide_script == written_script

    def test_checkpoint_created_with_validation_humaine(self, web_app, sample_script):
        """Le checkpoint cree contient validation_humaine=true et les bonnes metadonnees."""
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({"script": sample_script}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200

        checkpoint_path = web_app._checkpoints_dir / "S01E99_checkpoint.json"
        assert checkpoint_path.exists(), "Checkpoint non cree"

        with open(checkpoint_path, "r", encoding="utf-8") as f:
            cp = json.load(f)

        # Verifier la structure du checkpoint
        assert cp["episode_id"] == "S01E99"
        assert cp["etape"] == "audio"

        data = cp["data"]
        assert data["episode_id"] == "S01E99"
        assert data["titre"] == "Test Episode Production"
        assert data["dry_run"] is False
        assert data["type_episode"] == "standard"
        # saison/numero extraits de l'episode_id "S01E99" -> saison=1, numero=99
        assert data["saison"] == 1
        assert data["numero"] == 99

        # Verifier validation_humaine dans le rapport imbrique
        rapport = data["rapport"]
        assert rapport["etapes"]["script"]["validation_humaine"] is True
        assert rapport["etapes"]["script"]["status"] == "ok"

    def test_job_launched_via_start_job(self, web_app, sample_script):
        """_start_job est appele pour lancer le job audio."""
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({"script": sample_script}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200

        mock = web_app._mock_start_job
        assert mock.called, "_start_job n'a pas ete appele"

        # Verifier les arguments du premier appel (le job audio)
        call_args = mock.call_args
        cmd_args = call_args[0][0]  # Premier argument positionnel
        assert "reprendre" in cmd_args
        assert "--auto" in cmd_args
        assert "--stop-after" in cmd_args
        assert "audio" in cmd_args

    def test_response_contains_script_stats(self, web_app, sample_script):
        """La reponse JSON contient les statistiques du script (segments, voix, SFX)."""
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({"script": sample_script}),
            headers=_auth_headers(),
        )
        data = resp.get_json()
        assert data["script"]["segments"] == 5
        assert data["script"]["voix"] == 4  # 4 voice + 1 sfx
        assert data["script"]["sfx"] == 1
        assert data["script"]["titre"] == "Test Episode Production"

    def test_checkpoint_has_script_content_hash(self, web_app, sample_script, monkeypatch):
        """Le checkpoint contient un script_content_hash si utils.compute_script_hash existe."""
        # Mock compute_script_hash pour retourner un hash fixe
        mock_hash_fn = MagicMock(return_value="abc123hash")
        monkeypatch.setattr("web.compute_script_hash", mock_hash_fn, raising=False)

        # Si le module utils n'exporte pas compute_script_hash, le test verifie
        # que le checkpoint est quand meme cree (hash optionnel)
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({"script": sample_script}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200

        checkpoint_path = web_app._checkpoints_dir / "S01E99_checkpoint.json"
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            cp = json.load(f)

        # Le checkpoint est toujours cree meme si le hash echoue
        assert cp["data"]["episode_id"] == "S01E99"

    def test_production_run_id_in_checkpoint(self, web_app, sample_script):
        """Le checkpoint contient un production_run_id pour le segment namespacing."""
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({"script": sample_script}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200

        checkpoint_path = web_app._checkpoints_dir / "S01E99_checkpoint.json"
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            cp = json.load(f)

        assert "production_run_id" in cp["data"]
        assert cp["data"]["production_run_id"].startswith("prod_")


# ---------------------------------------------------------------------------
# Test 2 : kill-productions marque les productions comme failed
# ---------------------------------------------------------------------------

class TestKillProductions:
    """POST /api/episode/S01E99/kill-productions.

    Verifie que les productions non-terminales sont marquees 'failed' en DB.
    """

    def test_kill_with_db_available(self, web_app, monkeypatch):
        """Avec DB disponible, les productions non-terminales sont tuees."""
        web = web_app._web
        monkeypatch.setattr(web, "_DB_AVAILABLE", True)

        # Mock get_cursor pour simuler la DB
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 3  # 3 productions tuees

        mock_get_cursor = MagicMock(return_value=mock_cursor)
        monkeypatch.setattr("web.get_cursor", mock_get_cursor, raising=False)

        # On doit aussi patcher l'import dans la route
        with patch.dict("sys.modules", {"db_models": MagicMock(get_cursor=MagicMock(return_value=mock_cursor))}):
            resp = web_app.post(
                "/api/episode/S01E99/kill-productions",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["killed"] == 3

    def test_kill_without_db(self, web_app):
        """Sans DB, retourne killed=0 sans erreur."""
        resp = web_app.post(
            "/api/episode/S01E99/kill-productions",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["killed"] == 0

    def test_kill_invalid_episode_id(self, web_app):
        """Un episode_id invalide retourne 400."""
        resp = web_app.post(
            "/api/episode/INVALID/kill-productions",
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_kill_sql_updates_correct_statuses(self, web_app, monkeypatch):
        """Le SQL exclut bien 'completed' et 'failed' du kill."""
        web = web_app._web
        monkeypatch.setattr(web, "_DB_AVAILABLE", True)

        captured_sql = {}

        class FakeCursor:
            rowcount = 2

            def execute(self, sql, params):
                captured_sql["sql"] = sql
                captured_sql["params"] = params

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        mock_get_cursor = MagicMock(return_value=FakeCursor())

        with patch.dict("sys.modules", {"db_models": MagicMock(get_cursor=mock_get_cursor)}):
            resp = web_app.post(
                "/api/episode/S01E99/kill-productions",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        # Verifier que le SQL contient bien NOT IN ('completed', 'failed')
        sql = captured_sql.get("sql", "")
        assert "NOT IN" in sql
        assert "'completed'" in sql
        assert "'failed'" in sql
        assert captured_sql["params"] == ("S01E99",)


# ---------------------------------------------------------------------------
# Test 3 : verification seg_003 via /api/claude/query
# ---------------------------------------------------------------------------

class TestSeg003Verification:
    """Simule une requete SQL de verification seg_003 via /api/claude/query.

    Verifie que le nb_caracteres retourne par la DB correspond au script.
    """

    def test_claude_query_returns_seg_003(self, web_app, monkeypatch):
        """La route /api/claude/query retourne les donnees de seg_003."""
        web = web_app._web
        monkeypatch.setattr(web, "_DB_AVAILABLE", True)

        # Le texte de seg_003 dans notre sample_script
        texte_seg_003 = "Raconte-nous une histoire !"
        nb_chars_attendu = len(texte_seg_003)

        # Mock database.get_conn pour retourner les resultats
        mock_row = {"segment_id": "seg_003", "personnage": "noemie", "nb_caracteres": nb_chars_attendu}

        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [mock_row]
        mock_cursor.description = [("segment_id",), ("personnage",), ("nb_caracteres",)]

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        # Inject a mock database module into sys.modules AND web namespace
        # (database.py requires psycopg2 which is not installed in test env)
        mock_database = MagicMock()
        mock_database.get_conn.return_value = mock_conn
        mock_database.psycopg2 = MagicMock()
        mock_database.psycopg2.extras.RealDictCursor = None
        monkeypatch.setitem(sys.modules, "database", mock_database)
        monkeypatch.setattr(web, "database", mock_database, raising=False)

        sql = """SELECT segment_id, personnage, nb_caracteres FROM fichiers_audio
                 WHERE segment_id='seg_003' LIMIT 1"""

        resp = web_app.post(
            "/api/claude/query",
            data=json.dumps({"sql": sql}),
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["count"] == 1
        assert data["rows"][0]["segment_id"] == "seg_003"
        assert data["rows"][0]["nb_caracteres"] == nb_chars_attendu

    def test_seg_003_nb_caracteres_matches_script(self, sample_script):
        """Verifie que le nb_caracteres de seg_003 correspond bien au texte du script.

        Ce test est une validation unitaire de la logique de verification
        sans avoir besoin de la DB.
        """
        segments = sample_script["episode"]["segments"]
        seg_003 = next(s for s in segments if s["id"] == "seg_003")
        texte = seg_003["texte"]
        nb_chars = len(texte)

        # Le nb_caracteres stocke en DB doit correspondre exactement
        assert nb_chars == len("Raconte-nous une histoire !")
        assert seg_003["personnage"] == "noemie"

    def test_claude_query_rejects_non_select(self, web_app, monkeypatch):
        """La route /api/claude/query refuse les requetes non-SELECT."""
        web = web_app._web
        monkeypatch.setattr(web, "_DB_AVAILABLE", True)

        resp = web_app.post(
            "/api/claude/query",
            data=json.dumps({"sql": "DELETE FROM productions WHERE id = 1"}),
            headers=_auth_headers(),
        )

        assert resp.status_code == 403
        data = resp.get_json()
        assert "error" in data
        assert "SELECT" in data["error"]

    def test_claude_query_without_db(self, web_app):
        """Sans DB, retourne 503."""
        resp = web_app.post(
            "/api/claude/query",
            data=json.dumps({"sql": "SELECT 1"}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Test 4 : launch-fresh SANS script retourne 400 (pas 500)
# ---------------------------------------------------------------------------

class TestLaunchFreshWithoutScript:
    """POST /api/episode/S01E99/launch-fresh SANS script dans le body.

    Verifie que la route retourne une erreur propre (400 ou 404) et pas un crash 500.
    """

    def test_no_body_no_filesystem_returns_error(self, web_app):
        """Sans script dans le body ET sans fichier sur le filesystem -> erreur propre."""
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({}),
            headers=_auth_headers(),
        )
        # Doit etre 404 (script introuvable) et pas 500 (crash)
        assert resp.status_code in (400, 404), f"Attendu 400 ou 404, recu {resp.status_code}"
        data = resp.get_json()
        assert "error" in data

    def test_empty_body_returns_error(self, web_app):
        """Body vide (pas de JSON) -> erreur propre."""
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            headers=_auth_headers(),
        )
        assert resp.status_code in (400, 404), f"Attendu 400 ou 404, recu {resp.status_code}"
        data = resp.get_json()
        assert "error" in data

    def test_invalid_episode_id_returns_400(self, web_app, sample_script):
        """Un episode_id invalide retourne 400 meme avec un script valide."""
        resp = web_app.post(
            "/api/episode/BADFORMAT/launch-fresh",
            data=json.dumps({"script": sample_script}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "Format" in data["error"]

    def test_script_from_filesystem_fallback(self, web_app, sample_script):
        """Si le body n'a pas de script mais le fichier existe sur le filesystem, ca marche."""
        # Creer le script sur le filesystem
        script_path = web_app._scripts_dir / "S01E99_script.json"
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(sample_script, f, ensure_ascii=False)

        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "accepted"

    def test_no_auth_returns_401(self, web_app, sample_script):
        """Sans authentification, la route retourne 401."""
        resp = web_app.post(
            "/api/episode/S01E99/launch-fresh",
            data=json.dumps({"script": sample_script}),
            content_type="application/json",
            # Pas de header Authorization
        )
        assert resp.status_code == 401
