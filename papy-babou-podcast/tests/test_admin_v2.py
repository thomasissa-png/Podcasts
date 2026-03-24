"""Tests pour le back-office V2 : repos DB (SegmentAudioRepo, MontageRepo) et routes API V2.

Pourquoi ces tests existent :
- Les repos DB sont nouveaux et critiques pour le workflow de production segment par segment.
- Les routes API V2 exposent un nouveau pipeline (push script -> generate audio -> montage -> publish)
  qui doit fonctionner sans regression meme quand la DB est absente.
- Chaque test verifie un comportement precis : SQL correct, status codes, gestion d'erreurs.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ajouter le repertoire du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# A. Tests des repos DB (mock psycopg2)
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeCursor:
    """Curseur mock qui enregistre les requetes executees."""

    def __init__(self, rows=None, fetchone_val=None):
        self.executed = []
        self.params = []
        self._rows = rows or []
        self._fetchone_val = fetchone_val
        self.rowcount = len(self._rows) if rows else 0

    def execute(self, sql, params=None):
        self.executed.append(sql)
        self.params.append(params)

    def mogrify(self, sql, params=None):
        """Simule mogrify (utilise par execute_batch)."""
        return sql.encode() if isinstance(sql, str) else sql

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._fetchone_val

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeRow(dict):
    """Simule un RealDictRow psycopg2."""
    def __getitem__(self, key):
        return super().__getitem__(key)


@pytest.fixture
def mock_get_cursor():
    """Mock get_cursor pour isoler les tests DB du vrai PostgreSQL."""
    from contextlib import contextmanager

    cursors = []

    @contextmanager
    def _fake_get_cursor(commit=True):
        cur = _FakeCursor()
        cursors.append(cur)
        yield cur

    with patch("db_models.get_cursor", side_effect=_fake_get_cursor):
        yield cursors


@pytest.fixture
def mock_get_cursor_with_rows():
    """Factory pour mock get_cursor avec des lignes pre-configurees."""
    from contextlib import contextmanager

    def _factory(rows=None, fetchone_val=None):
        cursors = []

        @contextmanager
        def _fake_get_cursor(commit=True):
            cur = _FakeCursor(rows=rows, fetchone_val=fetchone_val)
            cursors.append(cur)
            yield cur

        return _fake_get_cursor, cursors

    return _factory


# ── A1. SegmentAudioRepo.creer_depuis_script ─────────────────────────────────


class TestSegmentAudioRepoCreerDepuisScript:
    """Verifie que creer_depuis_script genere les bons INSERT SQL."""

    def test_cree_segments_depuis_script_valide(self, mock_get_cursor):
        """Un script avec 3 segments (2 voix + 1 SFX) doit inserer 3 lignes."""
        from db_models import SegmentAudioRepo

        script = {
            "episode": {
                "segments": [
                    {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour", "ton": "chaleureux"},
                    {"id": "seg_002", "personnage": "antoine", "texte": "Salut", "ton": "curieux"},
                    {"id": "sfx_001", "personnage": "sfx", "texte": "wind sound", "ton": "ambiance"},
                ]
            }
        }

        result = SegmentAudioRepo.creer_depuis_script("S01E01", script)

        assert result == 3
        # Premier curseur : DELETE + execute_batch (via le meme contexte)
        assert len(mock_get_cursor) == 1
        cur = mock_get_cursor[0]
        # Le DELETE doit etre la premiere requete
        assert "DELETE FROM segments_audio" in cur.executed[0]

    def test_script_vide_retourne_zero(self, mock_get_cursor):
        """Un script sans segments doit retourner 0 sans toucher la DB."""
        from db_models import SegmentAudioRepo

        result = SegmentAudioRepo.creer_depuis_script("S01E01", {"episode": {"segments": []}})
        assert result == 0

    def test_segment_sfx_marque_correctement(self, mock_get_cursor):
        """Les segments SFX doivent avoir segment_type='sfx' et sfx_prompt rempli."""
        from db_models import SegmentAudioRepo

        script = {
            "episode": {
                "segments": [
                    {"id": "sfx_001", "personnage": "sfx", "texte": "thunder", "ton": "ambiance"},
                ]
            }
        }

        with patch("psycopg2.extras.execute_batch") as mock_batch:
            SegmentAudioRepo.creer_depuis_script("S01E01", script)
            # Verifier que execute_batch a ete appele
            assert mock_batch.called
            rows = mock_batch.call_args[0][2]  # 3eme argument = liste de dicts
            assert rows[0]["segment_type"] == "sfx"
            assert rows[0]["sfx_prompt"] == "thunder"


# ── A2. SegmentAudioRepo.lister ──────────────────────────────────────────────


class TestSegmentAudioRepoLister:
    """Verifie les SELECT avec filtres optionnels."""

    def test_lister_par_episode_sans_filtre(self, mock_get_cursor_with_rows):
        """Sans filtre, la requete ne doit contenir que episode_id."""
        from db_models import SegmentAudioRepo

        fake_rows = [
            _FakeRow({"segment_id": "seg_001", "personnage": "papy_babou", "status": "pending"}),
            _FakeRow({"segment_id": "seg_002", "personnage": "antoine", "status": "generated"}),
        ]
        factory, cursors = mock_get_cursor_with_rows(rows=fake_rows)

        with patch("db_models.get_cursor", side_effect=factory):
            result = SegmentAudioRepo.lister("S01E01")

        assert len(result) == 2
        assert result[0]["segment_id"] == "seg_001"
        cur = cursors[0]
        assert "episode_id = %s" in cur.executed[0]
        # Pas de filtre supplementaire
        assert "segment_type" not in cur.executed[0]

    def test_lister_avec_filtre_type(self, mock_get_cursor_with_rows):
        """Le filtre segment_type ajoute une clause WHERE."""
        from db_models import SegmentAudioRepo

        factory, cursors = mock_get_cursor_with_rows(rows=[])

        with patch("db_models.get_cursor", side_effect=factory):
            SegmentAudioRepo.lister("S01E01", segment_type="voix")

        cur = cursors[0]
        assert "segment_type = %s" in cur.executed[0]

    def test_lister_avec_filtre_status_multiple(self, mock_get_cursor_with_rows):
        """Le filtre status avec virgules doit generer IN (...)."""
        from db_models import SegmentAudioRepo

        factory, cursors = mock_get_cursor_with_rows(rows=[])

        with patch("db_models.get_cursor", side_effect=factory):
            SegmentAudioRepo.lister("S01E01", status="pending,error")

        cur = cursors[0]
        assert "status IN" in cur.executed[0]


# ── A3. SegmentAudioRepo.progression ─────────────────────────────────────────


class TestSegmentAudioRepoProgression:
    """Verifie le GROUP BY status et le calcul de pourcentage."""

    def test_progression_calcule_pourcentage(self, mock_get_cursor_with_rows):
        """60 generated + 40 validated sur 200 total = 50%."""
        from db_models import SegmentAudioRepo

        fake_rows = [
            _FakeRow({"status": "pending", "cnt": 80}),
            _FakeRow({"status": "generating", "cnt": 20}),
            _FakeRow({"status": "generated", "cnt": 60}),
            _FakeRow({"status": "validated", "cnt": 40}),
        ]
        factory, cursors = mock_get_cursor_with_rows(rows=fake_rows)

        with patch("db_models.get_cursor", side_effect=factory):
            result = SegmentAudioRepo.progression("S01E01")

        assert result["total"] == 200
        assert result["pending"] == 80
        assert result["generated"] == 60
        assert result["validated"] == 40
        assert result["percent"] == 50  # (60+40)/200*100

    def test_progression_episode_vide(self, mock_get_cursor_with_rows):
        """Un episode sans segments doit retourner percent=0."""
        from db_models import SegmentAudioRepo

        factory, cursors = mock_get_cursor_with_rows(rows=[])

        with patch("db_models.get_cursor", side_effect=factory):
            result = SegmentAudioRepo.progression("S01E99")

        assert result["total"] == 0
        assert result["percent"] == 0


# ── A4. MontageRepo.creer ────────────────────────────────────────────────────


class TestMontageRepoCreer:
    """Verifie l'INSERT montage avec statut processing."""

    def test_creer_retourne_id(self, mock_get_cursor_with_rows):
        """creer() doit retourner l'ID du montage cree."""
        from db_models import MontageRepo

        factory, cursors = mock_get_cursor_with_rows(
            fetchone_val=_FakeRow({"id": 42})
        )

        with patch("db_models.get_cursor", side_effect=factory):
            result = MontageRepo.creer("S01E01")

        assert result == 42
        cur = cursors[0]
        assert "INSERT INTO montages" in cur.executed[0]
        assert "'processing'" in cur.executed[0]


# ── A5. MontageRepo.lister ───────────────────────────────────────────────────


class TestMontageRepoLister:
    """Verifie le SELECT avec ORDER BY created_at DESC."""

    def test_lister_par_episode(self, mock_get_cursor_with_rows):
        """Doit retourner les montages tries par date decroissante."""
        from db_models import MontageRepo

        fake_rows = [
            _FakeRow({"id": 2, "episode_id": "S01E01", "status": "completed"}),
            _FakeRow({"id": 1, "episode_id": "S01E01", "status": "error"}),
        ]
        factory, cursors = mock_get_cursor_with_rows(rows=fake_rows)

        with patch("db_models.get_cursor", side_effect=factory):
            result = MontageRepo.lister("S01E01")

        assert len(result) == 2
        assert result[0]["id"] == 2
        cur = cursors[0]
        assert "ORDER BY created_at DESC" in cur.executed[0]


# ── A6. MontageRepo.charger ──────────────────────────────────────────────────


class TestMontageRepoCharger:
    """Verifie le chargement par ID."""

    def test_charger_existant(self, mock_get_cursor_with_rows):
        """charger() avec un ID existant retourne le dict."""
        from db_models import MontageRepo

        factory, cursors = mock_get_cursor_with_rows(
            fetchone_val=_FakeRow({"id": 1, "episode_id": "S01E01", "status": "completed"})
        )

        with patch("db_models.get_cursor", side_effect=factory):
            result = MontageRepo.charger(1)

        assert result is not None
        assert result["id"] == 1

    def test_charger_inexistant(self, mock_get_cursor_with_rows):
        """charger() avec un ID inexistant retourne None."""
        from db_models import MontageRepo

        factory, cursors = mock_get_cursor_with_rows(fetchone_val=None)

        with patch("db_models.get_cursor", side_effect=factory):
            result = MontageRepo.charger(999)

        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# B. Tests des routes API V2 (Flask test client)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cree un Flask test client avec les mocks necessaires."""
    import config

    # Configurer les repertoires temporaires
    scripts_dir = tmp_path / "scripts" / "episodes"
    scripts_dir.mkdir(parents=True)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    historique_dir = tmp_path / "data"
    historique_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    monkeypatch.setattr(config, "SCRIPTS_DIR", scripts_dir)
    monkeypatch.setattr(config, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(config, "HISTORIQUE_DIR", historique_dir)
    monkeypatch.setattr(config, "LOGS_DIR", logs_dir)

    # Mock la secret pour Bearer token
    monkeypatch.setenv("CLAUDE_API_SECRET", "test-secret")

    # Recharger web apres config
    import web
    monkeypatch.setattr(web, "_CLAUDE_API_SECRET", "test-secret")
    monkeypatch.setattr(web, "_DB_AVAILABLE", True)

    # Mock les repos
    mock_seg_repo = MagicMock()
    mock_montage_repo = MagicMock()
    monkeypatch.setattr(web, "SegmentAudioRepo", mock_seg_repo)
    monkeypatch.setattr(web, "MontageRepo", mock_montage_repo)

    web.app.config["TESTING"] = True
    web.app.config["SECRET_KEY"] = "test-secret-key"

    with web.app.test_client() as c:
        # Stocker les mocks dans le client pour acces dans les tests
        c._mock_seg_repo = mock_seg_repo
        c._mock_montage_repo = mock_montage_repo
        c._scripts_dir = scripts_dir
        c._output_dir = output_dir
        c._historique_dir = historique_dir
        yield c


def _auth_headers():
    """Headers d'authentification Bearer pour les tests."""
    return {"Authorization": "Bearer test-secret"}


def _create_test_script(scripts_dir, episode_id="S01E01"):
    """Cree un script de test minimal sur le filesystem."""
    script = {
        "episode": {
            "titre": "Test Episode",
            "numero": 1,
            "saison": 1,
            "segments": [
                {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour les enfants.", "ton": "chaleureux"},
                {"id": "seg_002", "personnage": "antoine", "texte": "Salut Papy !", "ton": "curieux"},
                {"id": "sfx_001", "personnage": "sfx", "texte": "fireplace crackling", "ton": "ambiance"},
            ],
        }
    }
    path = scripts_dir / f"{episode_id}_script.json"
    path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    valide_path = scripts_dir / f"{episode_id}_script_valide.json"
    valide_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    return script


# ── B1. GET /api/v2/episode/<eid>/script ─────────────────────────────────────


class TestApiV2GetScript:
    """Verifie la route script avec stats."""

    def test_script_existant_retourne_200(self, client):
        """Un script existant retourne 200 avec stats."""
        _create_test_script(client._scripts_dir)
        client._mock_seg_repo.lister.return_value = [{"segment_id": "seg_001"}]

        resp = client.get("/api/v2/episode/S01E01/script", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert "script" in data
        assert "stats" in data
        assert data["stats"]["nb_segments"] == 3
        assert data["stats"]["nb_voix"] == 2
        assert data["stats"]["nb_sfx"] == 1

    def test_script_inexistant_retourne_404(self, client):
        """Un episode sans script retourne 404."""
        resp = client.get("/api/v2/episode/S99E99/script", headers=_auth_headers())
        assert resp.status_code == 404


# ── B2. POST /api/v2/episode/<eid>/push-script ───────────────────────────────


class TestApiV2PushScript:
    """Verifie le push d'un script avec creation des segments."""

    def test_push_script_valide(self, client):
        """Un push valide cree le fichier et les segments DB."""
        script = {
            "episode": {
                "titre": "Test",
                "segments": [
                    {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour", "ton": "chaleureux"},
                ],
            }
        }
        client._mock_seg_repo.creer_depuis_script.return_value = 1

        resp = client.post(
            "/api/v2/episode/S01E01/push-script",
            json={"script": script},
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["nb_segments"] == 1
        # Verifier que le fichier a ete cree
        assert (client._scripts_dir / "S01E01_script.json").exists()
        assert (client._scripts_dir / "S01E01_script_valide.json").exists()

    def test_push_sans_script_retourne_400(self, client):
        """Un push sans champ 'script' retourne 400."""
        resp = client.post(
            "/api/v2/episode/S01E01/push-script",
            json={},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400


# ── B3. POST /api/v2/episode/<eid>/validate-script ───────────────────────────


class TestApiV2ValidateScript:
    """Verifie la validation de script."""

    def test_validate_script_existant(self, client):
        """Valider un script existant retourne 200."""
        _create_test_script(client._scripts_dir)
        client._mock_seg_repo.lister.return_value = [{"segment_id": "seg_001"}]

        resp = client.post(
            "/api/v2/episode/S01E01/validate-script",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "validated_at" in data

    def test_validate_script_inexistant(self, client):
        """Valider un script inexistant retourne 404."""
        resp = client.post(
            "/api/v2/episode/S99E99/validate-script",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404


# ── B4. GET /api/v2/episode/<eid>/segments ───────────────────────────────────


class TestApiV2Segments:
    """Verifie la liste des segments."""

    def test_segments_retourne_liste(self, client):
        """La route segments retourne la liste avec audio_url."""
        client._mock_seg_repo.lister.return_value = [
            {"segment_id": "seg_001", "personnage": "papy_babou", "status": "generated",
             "audio_path": None, "created_at": None, "updated_at": None},
        ]

        resp = client.get("/api/v2/episode/S01E01/segments", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["segment_id"] == "seg_001"

    def test_segments_avec_filtre_type(self, client):
        """Le filtre ?type=voix est passe au repo."""
        client._mock_seg_repo.lister.return_value = []

        resp = client.get(
            "/api/v2/episode/S01E01/segments?type=voix",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        client._mock_seg_repo.lister.assert_called_once_with(
            "S01E01", segment_type="voix", status=None
        )


# ── B5. POST /api/v2/episode/<eid>/generate-audio ────────────────────────────


class TestApiV2GenerateAudio:
    """Verifie le lancement de la generation audio (job async)."""

    def test_generate_audio_retourne_job_id(self, client):
        """Lancer la generation retourne 200 avec job_id."""
        _create_test_script(client._scripts_dir)

        with patch("web._start_fn_job", return_value="abc123") as mock_start:
            resp = client.post(
                "/api/v2/episode/S01E01/generate-audio",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["job_id"] == "abc123"
        assert data["episode_id"] == "S01E01"

    def test_generate_audio_script_manquant(self, client):
        """Sans script, retourne 404."""
        resp = client.post(
            "/api/v2/episode/S99E99/generate-audio",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_generate_audio_job_deja_en_cours(self, client):
        """Si un job tourne deja pour cet episode, retourne 409."""
        _create_test_script(client._scripts_dir)

        with patch("web._start_fn_job", side_effect=ValueError("Job en cours")):
            resp = client.post(
                "/api/v2/episode/S01E01/generate-audio",
                headers=_auth_headers(),
            )

        assert resp.status_code == 409


# ── B6. PUT segment edit ─────────────────────────────────────────────────────


class TestApiV2SegmentEdit:
    """Verifie l'edition de texte d'un segment."""

    def test_edit_segment_texte(self, client):
        """Editer le texte met a jour DB + script JSON."""
        _create_test_script(client._scripts_dir)

        resp = client.post(
            "/api/v2/segment/S01E01/seg_001/edit",
            json={"texte": "Nouveau texte"},
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

        # Verifier que le repo a ete appele
        client._mock_seg_repo.maj_texte.assert_called_once_with("S01E01", "seg_001", "Nouveau texte")

        # Verifier que le script JSON a ete mis a jour
        script = json.loads((client._scripts_dir / "S01E01_script.json").read_text(encoding="utf-8"))
        seg_001 = next(s for s in script["episode"]["segments"] if s["id"] == "seg_001")
        assert seg_001["texte"] == "Nouveau texte"

    def test_edit_sans_texte_retourne_400(self, client):
        """Sans champ texte, retourne 400."""
        resp = client.post(
            "/api/v2/segment/S01E01/seg_001/edit",
            json={},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400


# ── B7. POST segment regenerate ──────────────────────────────────────────────


class TestApiV2SegmentRegenerate:
    """Verifie la regeneration d'un segment (job async)."""

    def test_regenerate_retourne_job_id(self, client):
        """Regenerer un segment lance un job et retourne job_id."""
        with patch("web._start_fn_job", return_value="regen123"):
            resp = client.post(
                "/api/v2/segment/S01E01/seg_001/regenerate",
                json={},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["job_id"] == "regen123"

    def test_regenerate_avec_nouveau_texte(self, client):
        """Regenerer avec texte met a jour le texte avant de lancer le job."""
        _create_test_script(client._scripts_dir)

        with patch("web._start_fn_job", return_value="regen456"):
            resp = client.post(
                "/api/v2/segment/S01E01/seg_001/regenerate",
                json={"texte": "Texte modifie"},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        # Verifier que maj_texte a ete appele
        client._mock_seg_repo.maj_texte.assert_called_once_with("S01E01", "seg_001", "Texte modifie")


# ── B8. POST validate-all-segments ───────────────────────────────────────────


class TestApiV2ValidateAllSegments:
    """Verifie la validation en masse des segments."""

    def test_validate_all_retourne_count(self, client):
        """Valider tous les segments retourne le nombre de valides."""
        client._mock_seg_repo.valider_tous.return_value = 42

        resp = client.post(
            "/api/v2/episode/S01E01/validate-all-segments",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["count"] == 42


# ── B9. POST montage ─────────────────────────────────────────────────────────


class TestApiV2Montage:
    """Verifie le lancement du montage."""

    def test_montage_retourne_job_id(self, client):
        """Lancer le montage retourne job_id + montage_id."""
        client._mock_seg_repo.progression.return_value = {
            "total": 100, "pending": 0, "generating": 0,
            "generated": 60, "validated": 40, "errors": 0, "percent": 100,
        }
        client._mock_montage_repo.creer.return_value = 7

        with patch("web._start_fn_job", return_value="montage789"):
            resp = client.post(
                "/api/v2/episode/S01E01/montage",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["job_id"] == "montage789"
        assert data["montage_id"] == 7

    def test_montage_segments_pas_prets(self, client):
        """Si des segments sont encore pending, retourne 400."""
        client._mock_seg_repo.progression.return_value = {
            "total": 100, "pending": 30, "generating": 5,
            "generated": 60, "validated": 5, "errors": 0, "percent": 65,
        }

        resp = client.post(
            "/api/v2/episode/S01E01/montage",
            headers=_auth_headers(),
        )

        assert resp.status_code == 400


# ── B10. GET montages list ───────────────────────────────────────────────────


class TestApiV2ListMontages:
    """Verifie la liste des montages."""

    def test_list_montages(self, client):
        """La liste des montages retourne les montages avec URLs."""
        client._mock_montage_repo.lister.return_value = [
            {
                "id": 1, "episode_id": "S01E01", "status": "completed",
                "audio_path_hq": None, "created_at": None, "chapitres_json": None,
            },
        ]

        resp = client.get("/api/v2/episode/S01E01/montages", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["id"] == 1


# ── B11. GET montage audio ───────────────────────────────────────────────────


class TestApiV2MontageAudio:
    """Verifie le streaming audio d'un montage."""

    def test_montage_audio_inexistant(self, client):
        """Un montage inexistant retourne 404."""
        client._mock_montage_repo.charger.return_value = None

        resp = client.get("/api/v2/montage/999/audio", headers=_auth_headers())

        assert resp.status_code == 404

    def test_montage_audio_fichier_manquant(self, client):
        """Un montage sans fichier audio retourne 404."""
        client._mock_montage_repo.charger.return_value = {
            "id": 1, "episode_id": "S01E01",
            "audio_path_hq": "/nonexistent/file.mp3",
            "audio_path_preview": None,
        }

        resp = client.get("/api/v2/montage/1/audio", headers=_auth_headers())

        assert resp.status_code == 404


# ── B12. POST publish montage ────────────────────────────────────────────────


class TestApiV2Publish:
    """Verifie la publication d'un montage."""

    def test_publish_montage_completed(self, client):
        """Publier un montage completed retourne 200."""
        client._mock_montage_repo.charger.return_value = {
            "id": 1, "episode_id": "S01E01", "status": "completed",
            "audio_path_hq": None, "audio_path_preview": None,
        }

        resp = client.post("/api/v2/montage/1/publish", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        client._mock_montage_repo.publier.assert_called_once_with(1)

    def test_publish_montage_inexistant(self, client):
        """Publier un montage inexistant retourne 404."""
        client._mock_montage_repo.charger.return_value = None

        resp = client.post("/api/v2/montage/999/publish", headers=_auth_headers())

        assert resp.status_code == 404

    def test_publish_montage_non_completed(self, client):
        """Publier un montage non-completed retourne 400."""
        client._mock_montage_repo.charger.return_value = {
            "id": 1, "episode_id": "S01E01", "status": "processing",
        }

        resp = client.post("/api/v2/montage/1/publish", headers=_auth_headers())

        assert resp.status_code == 400


# ── B13. GET /admin (V2 is now the default) ──────────────────────────────────


class TestAdminV2Page:
    """Verifie que la page admin V2 est servie sur /admin."""

    def test_admin_sans_auth_redirige(self, client):
        """Sans authentification, redirige vers login."""
        resp = client.get("/admin")
        assert resp.status_code in (200, 302, 401)

    def test_admin_avec_session_auth(self, client):
        """Avec session admin, /admin retourne V2 (200)."""
        with client.session_transaction() as sess:
            sess["admin_authenticated"] = True

        resp = client.get("/admin")
        assert resp.status_code == 200

    def test_admin_v2_redirige_vers_admin(self, client):
        """/admin/v2 redirige vers /admin."""
        with client.session_transaction() as sess:
            sess["admin_authenticated"] = True

        resp = client.get("/admin/v2")
        assert resp.status_code == 302


# ── B14. GET /api/v2/episode/<eid>/audio-progress ────────────────────────────


class TestApiV2AudioProgress:
    """Verifie la route de progression audio."""

    def test_audio_progress(self, client):
        """La route retourne la progression depuis le repo."""
        client._mock_seg_repo.progression.return_value = {
            "total": 100, "pending": 10, "generating": 5,
            "generated": 50, "validated": 30, "errors": 5, "percent": 80,
        }

        resp = client.get("/api/v2/episode/S01E01/audio-progress", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["percent"] == 80
        assert data["total"] == 100


# ── B15. GET /api/v2/saisons/episodes ────────────────────────────────────────


class TestApiV2SaisonsEpisodes:
    """Verifie la vue consolidee des saisons."""

    def test_saisons_episodes(self, client, monkeypatch):
        """La route retourne les episodes de toutes les saisons."""
        import config

        def mock_charger_saison(num):
            if num == 1:
                return {
                    "saison": {
                        "episodes": [
                            {"numero": 1, "titre": "La creation", "type": "ouverture"},
                            {"numero": 2, "titre": "Noe", "type": "standard"},
                        ]
                    }
                }
            return {}

        monkeypatch.setattr(config, "charger_saison", mock_charger_saison)
        client._mock_seg_repo.progression.return_value = {
            "total": 0, "pending": 0, "generating": 0,
            "generated": 0, "validated": 0, "errors": 0, "percent": 0,
        }
        client._mock_montage_repo.lister.return_value = []

        resp = client.get("/api/v2/saisons/episodes", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["episode_id"] == "S01E01"
        assert data[0]["titre"] == "La creation"
        assert data[1]["episode_id"] == "S01E02"


# ═══════════════════════════════════════════════════════════════════════════════
# C. Tests d'integration du workflow
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkflowIntegration:
    """Verifie les enchainements cles du workflow V2."""

    def test_push_then_validate_then_segments(self, client):
        """Workflow : push script -> validate -> lister segments."""
        # 1. Push script
        script = {
            "episode": {
                "titre": "Test workflow",
                "segments": [
                    {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour", "ton": "chaleureux"},
                    {"id": "seg_002", "personnage": "antoine", "texte": "Salut", "ton": "curieux"},
                ],
            }
        }
        client._mock_seg_repo.creer_depuis_script.return_value = 2

        resp = client.post(
            "/api/v2/episode/S01E03/push-script",
            json={"script": script},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.get_json()["nb_segments"] == 2

        # 2. Validate script
        client._mock_seg_repo.lister.return_value = [{"segment_id": "seg_001"}, {"segment_id": "seg_002"}]
        resp = client.post("/api/v2/episode/S01E03/validate-script", headers=_auth_headers())
        assert resp.status_code == 200

        # 3. List segments
        client._mock_seg_repo.lister.return_value = [
            {"segment_id": "seg_001", "personnage": "papy_babou", "status": "pending",
             "audio_path": None, "created_at": None, "updated_at": None},
            {"segment_id": "seg_002", "personnage": "antoine", "status": "pending",
             "audio_path": None, "created_at": None, "updated_at": None},
        ]
        resp = client.get("/api/v2/episode/S01E03/segments", headers=_auth_headers())
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_auth_requise_sans_bearer(self, client):
        """Les routes V2 sans auth retournent 401."""
        resp = client.get("/api/v2/episode/S01E01/segments")
        assert resp.status_code == 401

    def test_segments_sans_db_fallback_json(self, client, monkeypatch):
        """Quand la DB est indisponible, segments endpoint falls back to script JSON."""
        import web
        monkeypatch.setattr(web, "_DB_AVAILABLE", False)

        # Without a script file, returns empty array (200)
        resp = client.get("/api/v2/episode/S01E01/segments", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_segments_fallback_json_with_script(self, client, monkeypatch, tmp_path):
        """Segments endpoint returns data from script JSON when DB is empty."""
        import web
        # Make DB return empty
        client._mock_seg_repo.lister.return_value = []

        # Create a test script file
        script = {"episode": {"segments": [
            {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour", "ton": "joyeux"},
            {"id": "sfx_001", "personnage": "sfx", "description": "Birds chirping"},
        ]}}
        script_dir = tmp_path / "scripts" / "episodes"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "S01E99_script.json"
        script_path.write_text(json.dumps(script), encoding="utf-8")
        monkeypatch.setattr(web.config, "SCRIPTS_DIR", script_dir)

        resp = client.get("/api/v2/episode/S01E99/segments", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["segment_id"] == "seg_001"
        assert data[0]["personnage"] == "papy_babou"
        assert data[0]["texte"] == "Bonjour"
        assert data[0]["segment_type"] == "voix"
        assert data[0]["source"] == "script_json"
        assert data[1]["segment_id"] == "sfx_001"
        assert data[1]["segment_type"] == "sfx"
        assert data[1]["texte"] == "Birds chirping"

    def test_audio_progress_sans_db_retourne_503(self, client, monkeypatch):
        """Quand la DB est indisponible, audio-progress retourne 503."""
        import web
        monkeypatch.setattr(web, "_DB_AVAILABLE", False)

        resp = client.get("/api/v2/episode/S01E01/audio-progress", headers=_auth_headers())
        assert resp.status_code == 503

    def test_segment_audio_inexistant(self, client):
        """Demander l'audio d'un segment inexistant retourne 404."""
        client._mock_seg_repo.charger.return_value = None

        resp = client.get("/api/v2/segment/S01E01/seg_999/audio", headers=_auth_headers())
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# F. Tests script version selector + montage selection
# ═══════════════════════════════════════════════════════════════════════════════


class TestScriptRepoValider:
    """Tests pour ScriptRepo.valider()."""

    def test_valider_devalide_autres_versions(self):
        """valider() de-valide les autres et valide la demandee."""
        from contextlib import contextmanager
        from db_models import ScriptRepo

        executed_sqls = []
        executed_params = []

        @contextmanager
        def _fake_get_cursor(commit=True):
            cur = _FakeCursor(fetchone_val=_FakeRow({"id": 42}))
            orig_execute = cur.execute
            def _track(sql, params=None):
                executed_sqls.append(sql)
                executed_params.append(params)
                orig_execute(sql, params)
            cur.execute = _track
            yield cur

        with patch("db_models.get_cursor", side_effect=_fake_get_cursor):
            result = ScriptRepo.valider("S01E01", 3)

        assert result is True
        assert len(executed_sqls) == 3
        assert "is_validated = FALSE" in executed_sqls[1]
        assert "is_validated = TRUE" in executed_sqls[2]

    def test_valider_version_inexistante(self):
        """valider() retourne False si la version n'existe pas."""
        from contextlib import contextmanager
        from db_models import ScriptRepo

        @contextmanager
        def _fake_get_cursor(commit=True):
            cur = _FakeCursor(fetchone_val=None)
            yield cur

        with patch("db_models.get_cursor", side_effect=_fake_get_cursor):
            result = ScriptRepo.valider("S01E01", 99)

        assert result is False


class TestScriptRepoHistoriqueAvecScore:
    """Tests pour ScriptRepo.historique() avec score_review."""

    def test_historique_inclut_score_review(self, mock_get_cursor_with_rows):
        """historique() retourne score_review depuis la table reviews."""
        from db_models import ScriptRepo

        rows = [
            _FakeRow({"id": 1, "version": 2, "nb_mots": 500, "nb_segments": 30,
                       "is_validated": True, "source": "scripteur",
                       "created_at": "2026-01-01", "score_review": 8.5}),
            _FakeRow({"id": 2, "version": 1, "nb_mots": 450, "nb_segments": 28,
                       "is_validated": False, "source": "scripteur",
                       "created_at": "2025-12-31", "score_review": None}),
        ]
        fake_get_cursor, cursors = mock_get_cursor_with_rows(rows=rows)
        with patch("db_models.get_cursor", side_effect=fake_get_cursor):
            result = ScriptRepo.historique("S01E01")

        assert len(result) == 2
        assert result[0]["score_review"] == 8.5
        assert result[1]["score_review"] is None


class TestApiV2ListScripts:
    """Tests pour GET /api/v2/episode/<eid>/scripts."""

    def test_list_scripts_retourne_versions(self, client, monkeypatch):
        """La route retourne la liste des versions."""
        import web

        mock_script_repo = MagicMock()
        mock_script_repo.historique.return_value = [
            {"id": 2, "version": 2, "nb_mots": 500, "nb_segments": 30,
             "is_validated": True, "source": "scripteur", "created_at": "2026-01-01T12:00:00", "score_review": 8.5},
            {"id": 1, "version": 1, "nb_mots": 450, "nb_segments": 28,
             "is_validated": False, "source": "scripteur", "created_at": "2025-12-31T10:00:00", "score_review": None},
        ]

        with patch("web.ScriptRepo", mock_script_repo, create=True):
            # Need to patch the import inside the function
            with patch.dict("sys.modules", {"db_models": MagicMock(ScriptRepo=mock_script_repo)}):
                resp = client.get("/api/v2/episode/S01E01/scripts", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["version"] == 2
        assert data[0]["is_validated"] is True
        assert data[0]["score_review"] == 8.5

    def test_list_scripts_sans_db(self, client, monkeypatch):
        """Sans DB, la route retourne 503."""
        import web
        monkeypatch.setattr(web, "_DB_AVAILABLE", False)

        resp = client.get("/api/v2/episode/S01E01/scripts", headers=_auth_headers())
        assert resp.status_code == 503


class TestApiV2ValidateScriptVersion:
    """Tests pour POST /api/v2/episode/<eid>/script/<version>/validate."""

    def test_validate_version_specifique(self, client, monkeypatch):
        """Valider une version specifique retourne ok."""
        import web

        mock_script_repo = MagicMock()
        mock_script_repo.valider.return_value = True
        mock_script_repo.charger_valide.return_value = {
            "episode": {"titre": "Test", "segments": [{"id": "seg_001", "personnage": "papy_babou", "texte": "Hello"}]}
        }

        with patch.dict("sys.modules", {"db_models": MagicMock(ScriptRepo=mock_script_repo)}):
            resp = client.post("/api/v2/episode/S01E01/script/2/validate", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["version"] == 2

    def test_validate_version_inexistante_retourne_404(self, client, monkeypatch):
        """Valider une version inexistante retourne 404."""
        import web

        mock_script_repo = MagicMock()
        mock_script_repo.valider.return_value = False

        with patch.dict("sys.modules", {"db_models": MagicMock(ScriptRepo=mock_script_repo)}):
            resp = client.post("/api/v2/episode/S01E01/script/99/validate", headers=_auth_headers())

        assert resp.status_code == 404


class TestApiV2Depublish:
    """Tests pour POST /api/v2/montage/<id>/depublish."""

    def test_depublish_montage_publie(self, client):
        """Depublier un montage publie retourne ok."""
        client._mock_montage_repo.charger.return_value = {
            "id": 1, "episode_id": "S01E01", "is_published": True, "status": "completed"
        }

        resp = client.post("/api/v2/montage/1/depublish", headers=_auth_headers())

        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        client._mock_montage_repo.depublier.assert_called_once_with(1)

    def test_depublish_montage_non_publie_retourne_400(self, client):
        """Depublier un montage non publie retourne 400."""
        client._mock_montage_repo.charger.return_value = {
            "id": 1, "episode_id": "S01E01", "is_published": False, "status": "completed"
        }

        resp = client.post("/api/v2/montage/1/depublish", headers=_auth_headers())
        assert resp.status_code == 400

    def test_depublish_montage_inexistant_retourne_404(self, client):
        """Depublier un montage inexistant retourne 404."""
        client._mock_montage_repo.charger.return_value = None

        resp = client.post("/api/v2/montage/999/depublish", headers=_auth_headers())
        assert resp.status_code == 404


class TestV1MontageFallback:
    """Tests pour le fallback V1 quand _update_montage_from_v1 echoue."""

    @pytest.fixture
    def client(self):
        """Cree un client Flask avec les mocks necessaires."""
        import web
        web.app.config["TESTING"] = True
        mock_montage_repo = MagicMock()
        with patch.object(web, "_DB_AVAILABLE", True), \
             patch.object(web, "MontageRepo", mock_montage_repo), \
             patch.object(web, "_CLAUDE_API_SECRET", "test-secret"):
            c = web.app.test_client()
            c._mock_montage_repo = mock_montage_repo
            yield c

    def test_v1_fallback_injects_virtual_montage_when_db_update_fails(self, client):
        """Quand un montage V2 est stale (processing) et que le V1 update echoue,
        le montage V1 virtuel doit quand meme etre retourne."""
        # Setup: V2 row stale
        client._mock_montage_repo.lister.return_value = [
            {"id": 1, "episode_id": "S01E01", "status": "processing",
             "duree_secondes": None, "taille_bytes": None, "is_published": False,
             "audio_path_hq": None, "audio_path_preview": None,
             "audio_os_key_hq": None, "audio_os_key_preview": None,
             "chapitres_json": [], "created_at": datetime.now(timezone.utc),
             "error_message": None, "nb_segments": None, "script_content_hash": None}
        ]
        # V1 rapport has complete montage data
        v1_montage = {
            "id": "v1", "episode_id": "S01E01", "status": "completed",
            "is_published": False, "duree_secondes": 1317.0, "taille_bytes": 30000000,
            "nb_segments": None, "chapitres_json": [{"title": "Ch1", "startTime": 10}],
            "audio_path_hq": None, "audio_path_preview": None,
            "audio_os_key_hq": "audio/S01E01_192k.mp3", "audio_os_key_preview": None,
            "created_at": "2026-01-01", "error_message": None,
            "_v1_audio_url_hq": "/audio/episodes/S01E01_192k.mp3",
            "_v1_audio_url_preview": "/audio/episodes/S01E01_128k.mp3",
        }
        with patch("web._find_v1_montage", return_value=v1_montage), \
             patch("web._update_montage_from_v1", side_effect=Exception("DB connection lost")):
            resp = client.get("/api/v2/episode/S01E01/montages", headers=_auth_headers())
            data = resp.get_json()
            # Should have the V1 virtual montage, not the stale processing one
            assert len(data) == 1
            assert data[0]["id"] == "v1"
            assert data[0]["status"] == "completed"
            assert data[0]["duree_secondes"] == 1317.0
            assert data[0]["audio_url_hq"] == "/audio/episodes/S01E01_192k.mp3"

    def test_v1_fallback_updates_db_when_successful(self, client):
        """Quand le V1 update reussit, le montage DB est mis a jour."""
        stale_row = {
            "id": 1, "episode_id": "S01E01", "status": "processing",
            "duree_secondes": None, "taille_bytes": None, "is_published": False,
            "audio_path_hq": None, "audio_path_preview": None,
            "audio_os_key_hq": None, "audio_os_key_preview": None,
            "chapitres_json": [], "created_at": datetime.now(timezone.utc),
            "error_message": None, "nb_segments": None, "script_content_hash": None}
        updated_row = dict(stale_row, status="completed", duree_secondes=1317.0,
                          taille_bytes=30000000, audio_os_key_hq="audio/S01E01_192k.mp3")
        # First call returns stale, second call (after update) returns updated
        client._mock_montage_repo.lister.side_effect = [[stale_row], [updated_row]]

        v1_montage = {
            "id": "v1", "episode_id": "S01E01", "status": "completed",
            "is_published": False, "duree_secondes": 1317.0, "taille_bytes": 30000000,
            "audio_os_key_hq": "audio/S01E01_192k.mp3",
            "_v1_audio_url_hq": "/audio/episodes/S01E01_192k.mp3",
            "_v1_audio_url_preview": "/audio/episodes/S01E01_128k.mp3",
        }
        with patch("web._find_v1_montage", return_value=v1_montage), \
             patch("web._update_montage_from_v1") as mock_update:
            resp = client.get("/api/v2/episode/S01E01/montages", headers=_auth_headers())
            data = resp.get_json()
            # DB was updated
            mock_update.assert_called_once_with(1, v1_montage)
            # Should show the updated DB row (not virtual)
            assert len(data) == 1
            assert data[0]["id"] == 1
            assert data[0]["status"] == "completed"
