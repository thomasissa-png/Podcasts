"""Module PostgreSQL — Connexion, schéma et pool de connexions pour Papy Babou.

Utilise DATABASE_URL (fournie par Replit PostgreSQL / autoscale) pour la connexion.
Toutes les données sont persistées avec audit trail et soft-delete.
"""

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

# ── Pool de connexions ─────────────────────────────────────────────────────────

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Retourne le pool de connexions (singleton thread-safe)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if not DATABASE_URL:
                    raise RuntimeError(
                        "DATABASE_URL non configurée. "
                        "Ajoutez-la dans .env ou dans les secrets Replit."
                    )
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,   # Réduit de 2 à 1 — moins de connexions idle
                    maxconn=10,
                    dsn=DATABASE_URL,
                    connect_timeout=10,  # Timeout de connexion (Neon cold start ~3s)
                    # TCP keepalives pour détecter les connexions mortes
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5,
                )
                logger.info("Pool PostgreSQL initialisé (2-10 connexions)")
    return _pool


def _ping_connection(conn) -> bool:
    """Vérifie qu'une connexion est encore vivante (pre-ping).

    Retourne True si la connexion est utilisable, False sinon.
    psycopg2 utilise conn.closed == 0 pour une connexion ouverte.
    """
    try:
        # psycopg2: closed est un int (0=ouvert, >0=fermé)
        closed_attr = getattr(conn, "closed", 0)
        if isinstance(closed_attr, int) and closed_attr != 0:
            return False
        # Exécuter un SELECT 1 léger pour détecter les connexions périmées
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        # Annuler toute transaction ouverte par le ping
        conn.rollback()
        return True
    except Exception:
        return False


@contextmanager
def get_conn():
    """Context manager pour obtenir une connexion du pool.

    Vérifie que la connexion est vivante (pre-ping). Si elle est périmée,
    la ferme, en obtient une nouvelle du pool, et réessaie une fois.

    Usage:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()
    """
    pool = get_pool()
    conn = pool.getconn()

    # Pre-ping : vérifier que la connexion n'est pas périmée
    if not _ping_connection(conn):
        logger.warning("Connexion PostgreSQL périmée détectée, renouvellement...")
        try:
            pool.putconn(conn, close=True)
        except Exception:
            # Si putconn échoue aussi, on ignore — on va en chercher une neuve
            pass
        conn = pool.getconn()
        if not _ping_connection(conn):
            # Deuxième échec : recréer tout le pool
            logger.error("Pool PostgreSQL corrompu, recréation...")
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            _reset_pool()
            pool = get_pool()
            conn = pool.getconn()

    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            pool.putconn(conn)
        except Exception:
            # Connexion irrécupérable — la fermer silencieusement
            logger.warning("Impossible de remettre la connexion dans le pool")
            try:
                conn.close()
            except Exception:
                pass


@contextmanager
def get_cursor(commit: bool = True):
    """Context manager pour obtenir un curseur dict directement.

    Usage:
        with get_cursor() as cur:
            cur.execute("SELECT ...", ...)
            rows = cur.fetchall()
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
            if commit:
                conn.commit()


def close_pool() -> None:
    """Ferme proprement le pool de connexions."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Pool PostgreSQL fermé")


def _reset_pool() -> None:
    """Ferme le pool existant et force sa recréation au prochain appel.

    Utilisé quand le pool est corrompu (toutes les connexions périmées).
    """
    global _pool
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.closeall()
            except Exception:
                pass
            _pool = None
            logger.info("Pool PostgreSQL réinitialisé (sera recréé au prochain appel)")


# ── Keepalive du pool (Neon scale-to-zero) ───────────────────────────────────

def _pool_keepalive_loop():
    """Ping périodique pour empêcher Neon de fermer les connexions idle.

    Neon (PostgreSQL managé de Replit) ferme les connexions après ~5 min
    d'inactivité. Les TCP keepalives ne traversent pas toujours le proxy.
    Ce thread envoie un SELECT 1 toutes les 2 minutes pour maintenir le pool.
    """
    while True:
        time.sleep(120)  # 2 minutes
        try:
            pool = _pool  # Lecture sans lock (atomique pour les refs Python)
            if pool is None:
                continue
            # Obtenir une connexion, la pinguer, la remettre
            conn = pool.getconn()
            try:
                if _ping_connection(conn):
                    pool.putconn(conn)
                else:
                    pool.putconn(conn, close=True)
                    logger.debug("Keepalive : connexion périmée remplacée")
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception:
            pass  # Pool fermé ou indisponible — on réessaie au prochain cycle


if DATABASE_URL:
    _keepalive_thread = threading.Thread(
        target=_pool_keepalive_loop, daemon=True, name="pg-keepalive"
    )
    _keepalive_thread.start()


# ── Schéma de la base de données ────────────────────────────────────────────────

SCHEMA_SQL = """
-- Extension pour les UUID et timestamps
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: saisons — Plans de saisons (jamais supprimés)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS saisons (
    id              SERIAL PRIMARY KEY,
    numero          INT NOT NULL,
    version         INT NOT NULL DEFAULT 1,
    theme           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    fil_rouge       TEXT DEFAULT '',
    plan_json       JSONB NOT NULL,
    arcs_personnages JSONB DEFAULT '{}',
    rituels         JSONB DEFAULT '{}',
    personnages_secondaires JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(numero, version)
);
CREATE INDEX IF NOT EXISTS idx_saisons_numero ON saisons(numero);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: episodes — Épisodes (jamais supprimés)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS episodes (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    saison_numero   INT NOT NULL,
    numero          INT NOT NULL,
    titre           TEXT NOT NULL,
    type_episode    VARCHAR(30) DEFAULT 'standard',
    resume          TEXT DEFAULT '',
    morale          TEXT DEFAULT '',
    ambiance        VARCHAR(30) DEFAULT '',
    status          VARCHAR(30) DEFAULT 'planned',
    plan_data       JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(episode_id, saison_numero)
);
CREATE INDEX IF NOT EXISTS idx_episodes_episode_id ON episodes(episode_id);
CREATE INDEX IF NOT EXISTS idx_episodes_saison ON episodes(saison_numero);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: scripts — Toutes les versions de scripts (JAMAIS supprimées)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS scripts (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    version         INT NOT NULL,
    script_json     JSONB NOT NULL,
    nb_mots         INT DEFAULT 0,
    nb_segments     INT DEFAULT 0,
    is_validated    BOOLEAN DEFAULT FALSE,
    source          VARCHAR(30) DEFAULT 'scripteur',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_scripts_episode_id ON scripts(episode_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: reviews — Toutes les reviews (JAMAIS supprimées)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS reviews (
    id              SERIAL PRIMARY KEY,
    script_id       INT REFERENCES scripts(id),
    episode_id      VARCHAR(10) NOT NULL,
    score           FLOAT NOT NULL,
    details_score   JSONB DEFAULT '{}',
    corrections     JSONB DEFAULT '[]',
    alertes         JSONB DEFAULT '[]',
    script_corrige_json JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reviews_episode_id ON reviews(episode_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: productions — Runs de production (remplace les checkpoints)
-- Les checkpoints ne sont JAMAIS supprimés, seulement marqués terminés
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS productions (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    status          VARCHAR(30) DEFAULT 'started',
    dry_run         BOOLEAN DEFAULT FALSE,
    auto_mode       BOOLEAN DEFAULT FALSE,
    etape_courante  VARCHAR(30) DEFAULT 'script',
    rapport_json    JSONB DEFAULT '{}',
    couts_json      JSONB DEFAULT '{}',
    checkpoint_data JSONB DEFAULT '{}',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_productions_episode_id ON productions(episode_id);
CREATE INDEX IF NOT EXISTS idx_productions_status ON productions(status);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: metadonnees — Métadonnées d'épisodes (jamais supprimées)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS metadonnees (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    production_id   INT REFERENCES productions(id),
    meta_json       JSONB NOT NULL,
    titre_complet   TEXT DEFAULT '',
    description_courte TEXT DEFAULT '',
    description_longue TEXT DEFAULT '',
    tags            JSONB DEFAULT '[]',
    cover_art_prompt TEXT DEFAULT '',
    cover_art_path  TEXT DEFAULT '',
    transcript      TEXT DEFAULT '',
    duree_secondes  INT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_metadonnees_episode_id ON metadonnees(episode_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: fichiers_audio — Registre de tous les fichiers audio générés
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS fichiers_audio (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    production_id   INT REFERENCES productions(id),
    type_fichier    VARCHAR(30) NOT NULL,
    segment_id      VARCHAR(50) DEFAULT '',
    personnage      VARCHAR(50) DEFAULT '',
    chemin          TEXT NOT NULL,
    taille_bytes    BIGINT DEFAULT 0,
    duree_secondes  FLOAT DEFAULT 0,
    source          VARCHAR(30) DEFAULT '',
    nb_caracteres   INT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fichiers_audio_episode_id ON fichiers_audio(episode_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: historique_episodes — Historique pour la continuité sérielle
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS historique_episodes (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL UNIQUE,
    titre           TEXT DEFAULT '',
    morale          TEXT DEFAULT '',
    resume_court    TEXT DEFAULT '',
    score_review    FLOAT DEFAULT 0,
    personnages_presents JSONB DEFAULT '[]',
    moments_cles    JSONB DEFAULT '[]',
    questions_ouvertes JSONB DEFAULT '[]',
    evolutions_personnages TEXT DEFAULT '',
    ambiance        VARCHAR(30) DEFAULT '',
    type_episode    VARCHAR(30) DEFAULT 'standard',
    date_production TIMESTAMPTZ,
    retours_humains TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_historique_episode_id ON historique_episodes(episode_id);

-- Migration : ajouter retours_humains si la colonne n'existe pas encore
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'historique_episodes'
                   AND column_name = 'retours_humains') THEN
        ALTER TABLE historique_episodes ADD COLUMN retours_humains TEXT DEFAULT '';
    END IF;
END $$;

-- Migration : ajouter deleted_at pour soft-delete (remplace le hard DELETE)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'historique_episodes'
                   AND column_name = 'deleted_at') THEN
        ALTER TABLE historique_episodes ADD COLUMN deleted_at TIMESTAMPTZ DEFAULT NULL;
    END IF;
END $$;

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: preferences_producteur — Mémoire persistante des préférences
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS preferences_producteur (
    id              SERIAL PRIMARY KEY,
    regle           TEXT NOT NULL,
    categorie       VARCHAR(50) DEFAULT 'general',
    source_episode  VARCHAR(20) DEFAULT '',
    date_ajout      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE
);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: personnages — Bible des personnages (versionnée, jamais supprimée)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS personnages (
    id              SERIAL PRIMARY KEY,
    personnage_id   VARCHAR(50) NOT NULL,
    version         INT NOT NULL DEFAULT 1,
    data_json       JSONB NOT NULL,
    voice_id        VARCHAR(100) DEFAULT '',
    pan             FLOAT DEFAULT 0.0,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(personnage_id, version)
);
CREATE INDEX IF NOT EXISTS idx_personnages_pid ON personnages(personnage_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: couts_api — Suivi granulaire des coûts API
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS couts_api (
    id              SERIAL PRIMARY KEY,
    production_id   INT REFERENCES productions(id),
    episode_id      VARCHAR(10) NOT NULL,
    service         VARCHAR(50) NOT NULL,
    detail          JSONB DEFAULT '{}',
    cout_estime     FLOAT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_couts_episode_id ON couts_api(episode_id);
CREATE INDEX IF NOT EXISTS idx_couts_service ON couts_api(service);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: publications — Publications d'épisodes
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS publications (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    production_id   INT REFERENCES productions(id),
    url_audio       TEXT DEFAULT '',
    transcript_url  TEXT DEFAULT '',
    flux_rss_path   TEXT DEFAULT '',
    plateformes_notifiees JSONB DEFAULT '[]',
    buzzsprout_response JSONB DEFAULT '{}',
    published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_publications_episode_id ON publications(episode_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: segments_audio — Segments audio individuels pour le back-office V2
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS segments_audio (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    segment_id      VARCHAR(20) NOT NULL,
    segment_type    VARCHAR(10) DEFAULT 'voix',
    personnage      VARCHAR(50),
    texte           TEXT,
    texte_original  TEXT,
    ton             VARCHAR(30),
    rythme          VARCHAR(10),
    sfx_prompt      TEXT,
    audio_path      TEXT,
    audio_os_key    TEXT,
    duree_ms        INTEGER,
    nb_caracteres   INTEGER,
    status          VARCHAR(20) DEFAULT 'pending',
    version         INTEGER DEFAULT 1,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_seg_audio_uniq ON segments_audio(episode_id, segment_id, version);
CREATE INDEX IF NOT EXISTS idx_seg_audio_episode ON segments_audio(episode_id, status);

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: montages — Montages audio assemblés pour le back-office V2
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS montages (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    audio_path_hq   TEXT,
    audio_path_preview TEXT,
    audio_os_key_hq TEXT,
    audio_os_key_preview TEXT,
    duree_secondes  FLOAT,
    taille_bytes    BIGINT,
    nb_segments     INTEGER,
    status          VARCHAR(20) DEFAULT 'pending',
    is_published    BOOLEAN DEFAULT FALSE,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_montage_episode ON montages(episode_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_montage_published ON montages(episode_id) WHERE is_published = TRUE;

-- ══════════════════════════════════════════════════════════════════════════════
-- Table: audit_log — Journal d'audit (JAMAIS supprimé, append-only)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    table_name      VARCHAR(50) NOT NULL,
    record_id       INT,
    action          VARCHAR(20) NOT NULL,
    old_data        JSONB,
    new_data        JSONB,
    context         TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_table ON audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

-- ══════════════════════════════════════════════════════════════════════════════
-- Fonction trigger pour audit_log automatique
-- ══════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION audit_trigger_func()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log (table_name, record_id, action, new_data)
        VALUES (TG_TABLE_NAME, NEW.id, 'INSERT', to_jsonb(NEW));
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log (table_name, record_id, action, old_data, new_data)
        VALUES (TG_TABLE_NAME, NEW.id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW));
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_log (table_name, record_id, action, old_data)
        VALUES (TG_TABLE_NAME, OLD.id, 'DELETE', to_jsonb(OLD));
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Migration : ajouter web_job_id pour reconnecter le polling après perte réseau
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'productions'
                   AND column_name = 'web_job_id') THEN
        ALTER TABLE productions ADD COLUMN web_job_id VARCHAR(12) DEFAULT NULL;
    END IF;
END $$;

-- Appliquer le trigger d'audit sur toutes les tables principales
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'saisons', 'episodes', 'scripts', 'reviews', 'productions',
            'metadonnees', 'fichiers_audio', 'historique_episodes',
            'personnages', 'couts_api', 'publications',
            'segments_audio', 'montages'
        ])
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS audit_%I ON %I; '
            'CREATE TRIGGER audit_%I '
            'AFTER INSERT OR UPDATE OR DELETE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();',
            tbl, tbl, tbl, tbl
        );
    END LOOP;
END;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- Fonction pour updated_at automatique
-- ══════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'saisons', 'episodes', 'productions', 'personnages',
            'segments_audio'
        ])
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS set_updated_at_%I ON %I; '
            'CREATE TRIGGER set_updated_at_%I '
            'BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION update_updated_at();',
            tbl, tbl, tbl, tbl
        );
    END LOOP;
END;
$$;
"""


def initialiser_schema() -> None:
    """Crée toutes les tables et triggers si elles n'existent pas."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
    logger.info("Schéma PostgreSQL initialisé avec succès")


def verifier_connexion() -> bool:
    """Vérifie que la connexion PostgreSQL fonctionne.

    Returns:
        True si la connexion est OK.
    """
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error("Connexion PostgreSQL échouée : %s", e)
        return False


_TABLES_CONNUES = (
    "saisons", "episodes", "scripts", "reviews", "productions",
    "metadonnees", "fichiers_audio", "historique_episodes",
    "personnages", "couts_api", "publications", "audit_log",
    "preferences_producteur", "segments_audio", "montages",
)


def obtenir_stats_db() -> dict:
    """Retourne des statistiques sur la base de données."""
    stats = {}
    with get_cursor() as cur:
        for table in _TABLES_CONNUES:
            # Utilisation de psycopg2.sql pour éviter l'injection SQL
            from psycopg2 import sql
            cur.execute(
                sql.SQL("SELECT COUNT(*) as count FROM {}").format(
                    sql.Identifier(table)
                )
            )
            row = cur.fetchone()
            stats[table] = row["count"] if row else 0
    return stats
