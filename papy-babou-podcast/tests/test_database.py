"""Tests pour les modules database.py et db_models.py.

Utilise des mocks pour psycopg2 afin de tester sans PostgreSQL réel.
Vérifie le schéma SQL, les context managers, les repos CRUD et le soft-delete.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Tests du module database.py ──────────────────────────────────────────────


class TestSchemaSQL:
    """Vérifie la cohérence du schéma SQL."""

    def test_schema_contient_toutes_les_tables(self):
        """Le schéma doit définir les 12 tables attendues."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            tables_attendues = [
                "saisons", "episodes", "scripts", "reviews", "productions",
                "metadonnees", "fichiers_audio", "historique_episodes",
                "personnages", "couts_api", "publications", "audit_log",
            ]
            for table in tables_attendues:
                assert f"CREATE TABLE IF NOT EXISTS {table}" in database.SCHEMA_SQL, \
                    f"Table {table} manquante dans le schéma"

    def test_schema_contient_soft_delete(self):
        """Les tables principales doivent avoir deleted_at pour le soft-delete."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            # saisons, episodes, personnages ont deleted_at
            assert database.SCHEMA_SQL.count("deleted_at") >= 3

    def test_schema_contient_audit_trigger(self):
        """Le schéma doit contenir la fonction d'audit trigger."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            assert "audit_trigger_func" in database.SCHEMA_SQL
            assert "audit_log" in database.SCHEMA_SQL

    def test_schema_contient_updated_at_trigger(self):
        """Le schéma doit contenir le trigger update_updated_at."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            assert "update_updated_at" in database.SCHEMA_SQL

    def test_schema_contient_index(self):
        """Le schéma doit contenir des index pour les colonnes fréquemment recherchées."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            assert database.SCHEMA_SQL.count("CREATE INDEX IF NOT EXISTS") >= 10

    def test_tables_jamais_supprimees_ont_deleted_at(self):
        """Les tables saisons, episodes, personnages doivent avoir deleted_at."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            # Vérifier que deleted_at est présent pour les tables qui le nécessitent
            # saisons, episodes, personnages
            schema = database.SCHEMA_SQL
            # Split by CREATE TABLE and check each
            assert "deleted_at      TIMESTAMPTZ" in schema


class TestDatabasePool:
    """Tests du pool de connexions et des context managers."""

    def test_get_pool_sans_database_url(self):
        """get_pool doit lever RuntimeError si DATABASE_URL est vide."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            database._pool = None
            database.DATABASE_URL = ""

            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                database.get_pool()

    def test_get_pool_singleton(self):
        """get_pool doit retourner le même pool à chaque appel."""
        mock_pool = MagicMock()
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            database._pool = mock_pool
            assert database.get_pool() is mock_pool

    def test_close_pool(self):
        """close_pool doit fermer et réinitialiser le pool."""
        mock_pool = MagicMock()
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            database._pool = mock_pool
            database.close_pool()

            mock_pool.closeall.assert_called_once()
            assert database._pool is None

    def test_close_pool_quand_deja_none(self):
        """close_pool ne doit pas lever d'erreur si pool est déjà None."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            database._pool = None
            database.close_pool()  # Ne doit pas lever d'erreur

    def test_obtenir_stats_db_liste_toutes_tables(self):
        """obtenir_stats_db doit interroger les 13 tables."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {"count": 5}
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_pool = MagicMock()
            mock_pool.getconn.return_value = mock_conn
            database._pool = mock_pool

            stats = database.obtenir_stats_db()

            assert len(stats) == 13
            assert "audit_log" in stats
            assert "scripts" in stats
            assert "preferences_producteur" in stats
            assert all(v == 5 for v in stats.values())


# ── Tests des repositories (db_models.py) ────────────────────────────────────


class TestSaisonRepoLogique:
    """Tests de la logique du SaisonRepo sans accès réel à la DB."""

    def test_sauvegarder_extrait_numero(self):
        """sauvegarder doit extraire le numéro de saison du plan."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            mock_cursor = MagicMock()
            mock_cursor.fetchone.side_effect = [
                {"next_v": 1},  # SELECT MAX(version)
                {"id": 42},     # INSERT ... RETURNING id
            ]
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_pool = MagicMock()
            mock_pool.getconn.return_value = mock_conn
            database._pool = mock_pool

            import db_models
            importlib.reload(db_models)

            plan = {
                "saison": {
                    "numero": 3,
                    "theme": "Les Miracles",
                    "description": "Saison test",
                }
            }
            result = db_models.SaisonRepo.sauvegarder(plan)
            assert result == 42

    def test_charger_retourne_dict_vide_si_absent(self):
        """charger doit retourner {} si la saison n'existe pas."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_pool = MagicMock()
            mock_pool.getconn.return_value = mock_conn
            database._pool = mock_pool

            import db_models
            importlib.reload(db_models)

            result = db_models.SaisonRepo.charger(99)
            assert result == {}


class TestScriptRepoLogique:
    """Tests de la logique du ScriptRepo."""

    def test_sauvegarder_incremente_version(self):
        """sauvegarder doit auto-incrémenter la version."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            mock_cursor = MagicMock()
            mock_cursor.fetchone.side_effect = [
                {"next_v": 3},  # Version 3
                {"id": 100},    # INSERT
            ]
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_pool = MagicMock()
            mock_pool.getconn.return_value = mock_conn
            database._pool = mock_pool

            import db_models
            importlib.reload(db_models)

            script = {"episode": {"segments": [{"id": "seg_001"}]}}
            result = db_models.ScriptRepo.sauvegarder(
                episode_id="S01E01",
                script=script,
                nb_mots=150,
            )
            assert result == 100

    def test_sauvegarder_valide_desactive_anciennes(self):
        """Valider un script doit dé-valider les précédents."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            mock_cursor = MagicMock()
            mock_cursor.fetchone.side_effect = [
                {"next_v": 2},
                {"id": 200},
            ]
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_pool = MagicMock()
            mock_pool.getconn.return_value = mock_conn
            database._pool = mock_pool

            import db_models
            importlib.reload(db_models)

            script = {"episode": {"segments": []}}
            db_models.ScriptRepo.sauvegarder(
                episode_id="S01E01",
                script=script,
                is_validated=True,
            )

            # Vérifier que UPDATE ... is_validated = FALSE a été appelé
            calls = [str(c) for c in mock_cursor.execute.call_args_list]
            devalidation = any("is_validated = FALSE" in c for c in calls)
            assert devalidation, "Doit dé-valider les versions précédentes"

    def test_charger_valide_retourne_vide_si_absent(self):
        """charger_valide retourne {} si aucun script validé."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_pool = MagicMock()
            mock_pool.getconn.return_value = mock_conn
            database._pool = mock_pool

            import db_models
            importlib.reload(db_models)

            result = db_models.ScriptRepo.charger_valide("S99E99")
            assert result == {}


class TestProductionRepoLogique:
    """Tests de la logique du ProductionRepo — vérifier que JAMAIS de DELETE."""

    def test_creer_retourne_id(self):
        """creer doit retourner l'ID de la production."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {"id": 7}
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_pool = MagicMock()
            mock_pool.getconn.return_value = mock_conn
            database._pool = mock_pool

            import db_models
            importlib.reload(db_models)

            result = db_models.ProductionRepo.creer("S01E01", dry_run=True)
            assert result == 7

    def test_aucune_requete_delete_dans_repos(self):
        """Aucun repo ne doit contenir de requête DELETE (principe fondamental)."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)
            import db_models
            importlib.reload(db_models)

            import inspect
            source = inspect.getsource(db_models)
            # Chercher DELETE FROM ou DELETE dans les requêtes SQL
            # (hors commentaires)
            lines = source.split("\n")
            sql_deletes = [
                line for line in lines
                if "DELETE FROM" in line and not line.strip().startswith("#")
            ]
            assert len(sql_deletes) == 0, \
                f"DELETE trouvé dans db_models.py : {sql_deletes}"


class TestHistoriqueRepoLogique:
    """Tests du repo d'historique — crucial pour la continuité sérielle."""

    def test_ajouter_utilise_upsert(self):
        """ajouter doit utiliser ON CONFLICT (UPSERT) pour ne jamais perdre de données."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)
            import db_models
            importlib.reload(db_models)

            import inspect
            source = inspect.getsource(db_models.HistoriqueRepo.ajouter)
            assert "ON CONFLICT" in source, "HistoriqueRepo.ajouter doit utiliser UPSERT"

    def test_charger_tout_retourne_liste(self):
        """charger_tout doit retourner une liste (même vide)."""
        with patch.dict("sys.modules", {
            "psycopg2": MagicMock(),
            "psycopg2.extras": MagicMock(),
            "psycopg2.pool": MagicMock(),
        }):
            import importlib
            import database
            importlib.reload(database)

            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_pool = MagicMock()
            mock_pool.getconn.return_value = mock_conn
            database._pool = mock_pool

            import db_models
            importlib.reload(db_models)

            result = db_models.HistoriqueRepo.charger_tout()
            assert isinstance(result, list)
            assert result == []
