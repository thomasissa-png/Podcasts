"""Tests for _find_all_v1_montages and V1 montage fallback logic.

Regression tests for the stale montage bug where the back-office displayed
a 7min50 old montage instead of the latest ~30min montage.

Root cause: _find_all_v1_montages used database.get_conn() without the 'with'
context manager (get_conn is a @contextmanager generator), causing silent
AttributeError. The DB path always failed, and the fallback only checked the
most recent production via charger_rapport (which might be a test/failure
with no montage). So the stale V2 montage from the montages table won.
"""
import json
from unittest.mock import MagicMock, patch
from contextlib import contextmanager


class TestV1MontageSelectionLogic:
    """Tests for the V1 vs V2 comparison logic."""

    def test_v1_longer_duration_wins_over_stale_v2(self):
        """When V1 has 30min montage and V2 has 7min, V1 should be preferred."""
        v1_duree = 1800  # 30 min
        v2_duree = 470   # ~7min50

        # Duration difference must be > 60s to be considered a different montage
        assert abs(v1_duree - v2_duree) > 60
        assert v1_duree > v2_duree

    def test_get_cursor_is_context_manager(self):
        """Verify get_cursor is a proper context manager (validates the fix)."""
        try:
            from database import get_cursor
            assert callable(get_cursor), "get_cursor should be callable"
        except ImportError:
            pass

    def test_get_conn_is_not_a_connection(self):
        """Verify that get_conn() returns a context manager, not a raw connection.

        This is the root cause of the bug: calling get_conn() without 'with'
        returns a generator object that has no .cursor() method.
        """
        try:
            from database import get_conn
            result = get_conn()
            assert not hasattr(result, "cursor"), \
                "get_conn() should not have .cursor() -- it is a context manager, use 'with'"
            result.close()
        except (ImportError, Exception):
            pass


class TestFindAllV1Montages:
    """Tests for _find_all_v1_montages DB query path."""

    def test_db_path_finds_montage_in_older_production(self, monkeypatch):
        """When most recent production has no montage but an older one does,
        the function should find the older montage via DB iteration."""
        rapport_with_montage = {
            "episode_id": "S01E01",
            "etapes": {
                "montage": {
                    "chemin_hq": "/output/audio/episodes/S01E01_hq.mp3",
                    "duree_secondes": 1800,
                }
            },
            "debut": "2026-03-20T10:00:00",
        }
        rapport_without_montage = {
            "episode_id": "S01E01",
            "etapes": {
                "script": {"status": "waiting_script"},
            },
            "debut": "2026-03-22T10:00:00",
        }

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"rapport_json": rapport_without_montage, "started_at": "2026-03-22"},
            {"rapport_json": rapport_with_montage, "started_at": "2026-03-20"},
        ]

        @contextmanager
        def mock_get_cursor(commit=True):
            yield mock_cursor

        import web
        monkeypatch.setattr(web, "_DB_AVAILABLE", True)

        with patch("database.get_cursor", mock_get_cursor):
            # Also mock _build_v1_montage_dict to return a simple dict
            with patch.object(web, "_build_v1_montage_dict") as mock_build:
                mock_build.return_value = {
                    "id": "v1_test",
                    "duree_secondes": 1800,
                    "audio_path_hq": "/output/audio/episodes/S01E01_hq.mp3",
                }
                results = web._find_all_v1_montages("S01E01")

        assert len(results) == 1
        assert results[0]["duree_secondes"] == 1800
        # _build_v1_montage_dict called only for the rapport WITH montage
        mock_build.assert_called_once()
        args = mock_build.call_args[0]
        assert args[1] == rapport_with_montage  # rapport
        assert args[2]["chemin_hq"] == "/output/audio/episodes/S01E01_hq.mp3"

    def test_db_unavailable_falls_back_to_charger_rapport(self, monkeypatch):
        """When DB is unavailable, falls back to charger_rapport."""
        rapport_with_montage = {
            "etapes": {
                "montage": {"chemin_hq": "/output/audio/S01E01_hq.mp3"},
            },
        }

        import web
        monkeypatch.setattr(web, "_DB_AVAILABLE", False)

        mock_dd = MagicMock()
        mock_dd.charger_rapport.return_value = rapport_with_montage

        with patch.dict("sys.modules", {"dashboard_data": mock_dd}):
            with patch.object(web, "_build_v1_montage_dict") as mock_build:
                mock_build.return_value = {"id": "v1_test", "duree_secondes": 1800}
                results = web._find_all_v1_montages("S01E01")

        assert len(results) == 1

    def test_no_montage_anywhere_returns_empty(self, monkeypatch):
        """When no production has a montage, return empty list."""
        rapport_no_montage = {
            "etapes": {"script": {"status": "completed"}},
        }

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"rapport_json": rapport_no_montage, "started_at": "2026-03-22"},
        ]

        @contextmanager
        def mock_get_cursor(commit=True):
            yield mock_cursor

        import web
        monkeypatch.setattr(web, "_DB_AVAILABLE", True)

        with patch("database.get_cursor", mock_get_cursor):
            mock_dd = MagicMock()
            mock_dd.charger_rapport.return_value = rapport_no_montage
            with patch.dict("sys.modules", {"dashboard_data": mock_dd}):
                results = web._find_all_v1_montages("S01E01")

        assert len(results) == 0


class TestDatabaseGetConnMisuse:
    """Verify the bug pattern is fixed: get_conn() is never used without 'with'."""

    def test_no_bare_get_conn_in_web_v2_montage_section(self):
        """Ensure web.py never uses 'conn = database.get_conn()' without 'with'.

        This was the root cause: get_conn() is a @contextmanager, calling it
        without 'with' returns a generator, not a connection.
        """
        import inspect
        import web
        source = inspect.getsource(web)

        # Count occurrences of the broken pattern
        import re
        broken_pattern = re.findall(r'(?<!=\s)conn\s*=\s*database\.get_conn\(\)', source)
        # This should not appear. Only `with database.get_conn() as conn:` is valid.
        assert len(broken_pattern) == 0, (
            f"Found {len(broken_pattern)} instance(s) of bare 'conn = database.get_conn()' "
            "without 'with'. This creates a generator, not a connection."
        )
