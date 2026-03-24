"""Serveur web Flask — Dashboard de production Les Histoires de Papy Babou.

Lance le dashboard complet en mode web : dashboard, production d'episodes,
planification de saisons, reprise de checkpoints, configuration.

Usage :
    python web.py                     # Demarre sur le port 5000
"""

import atexit
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

# Ensure imports work when launched from repo root (Replit)
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
os.chdir(_THIS_DIR)

from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

import config
import dashboard_data as dashboard_data_mod
from dashboard_data import get_dashboard_data, charger_preferences, charger_checkpoints, charger_publications
from utils import fichier_lock

# ── Initialisation PostgreSQL ─────────────────────────────────────────────────
try:
    import database
    from database import DATABASE_URL
    _DB_AVAILABLE = bool(DATABASE_URL)
except ImportError:
    _DB_AVAILABLE = False

app = Flask(__name__, template_folder=str(_THIS_DIR / "templates"))

logger = logging.getLogger(__name__)


@app.after_request
def _no_cache_html(response):
    """Empêche le navigateur de cacher les pages HTML (dashboard).

    Sans ça, après un redéploiement Replit, le navigateur sert l'ancienne
    version du JS depuis son cache → timeouts, bugs fantômes, etc.
    """
    if response.content_type and "text/html" in response.content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response

_default_secret = "papy-babou-dev-key"
app.secret_key = os.getenv("FLASK_SECRET_KEY", _default_secret)
if app.secret_key == _default_secret:
    logger.warning(
        "FLASK_SECRET_KEY non configurée — clé par défaut utilisée. "
        "Configurez FLASK_SECRET_KEY en production."
    )


## ── Admin Authentication ─────────────────────────────────────────────────────
_CLAUDE_API_SECRET = os.getenv("CLAUDE_API_SECRET", "")
if not _CLAUDE_API_SECRET:
    logger.info(
        "CLAUDE_API_SECRET non configurée — endpoints /api/claude/ désactivés. "
        "Configurez CLAUDE_API_SECRET dans les Secrets Replit pour activer l'accès DB distant."
    )

_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "papybabou")
if _ADMIN_PASSWORD == "papybabou":
    logger.warning(
        "ADMIN_PASSWORD non configurée — mot de passe par défaut 'papybabou'. "
        "Configurez ADMIN_PASSWORD en production."
    )

# Routes publiques qui ne nécessitent PAS d'authentification admin
_PUBLIC_ROUTES = frozenset({
    "/", "/favicon.ico", "/healthz",
    "/admin/login", "/admin/logout",
    "/api/public/episodes",
})
_PUBLIC_PREFIXES = (
    "/assets/artwork/", "/audio/episodes/", "/audio/covers/",
)


@app.before_request
def _check_admin_auth():
    """Protège toutes les routes /admin et /api (sauf publiques) par authentification."""
    path = request.path

    # Routes publiques : accès libre
    if path in _PUBLIC_ROUTES:
        return None
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return None

    # Bearer token : authentifie TOUTES les routes /api/ (pas seulement /api/claude/)
    if path.startswith("/api/") and _CLAUDE_API_SECRET:
        auth_header = request.headers.get("Authorization", "")
        if auth_header == f"Bearer {_CLAUDE_API_SECRET}":
            return None  # Authentifié via Bearer token — accès complet

    # Pages et API admin : exiger authentification session
    if path.startswith("/admin") or path.startswith("/api/"):
        if not session.get("admin_authenticated"):
            if path.startswith("/api/"):
                return jsonify({"error": "Authentification admin requise"}), 401
            return redirect(url_for("admin_login"))

    return None


def _admin_required(f):
    """Décorateur : exige une session admin (doublon de sécurité pour routes critiques)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentification admin requise"}), 401
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Page de connexion admin."""
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == _ADMIN_PASSWORD:
            session["admin_authenticated"] = True
            return redirect(url_for("admin_dashboard"))
        error = "Mot de passe incorrect"
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    """Déconnexion admin."""
    session.pop("admin_authenticated", None)
    return redirect("/")


def _init_db_if_available():
    """Initialise le schema PostgreSQL au demarrage du serveur web."""
    if not _DB_AVAILABLE:
        logger.info("PostgreSQL non configure — mode fichiers JSON")
        return False
    try:
        database.initialiser_schema()
        logger.info("PostgreSQL schema initialise avec succes")
        return True
    except Exception as e:
        logger.warning("PostgreSQL indisponible au demarrage : %s", e)
        return False


@app.errorhandler(500)
def handle_500(e):
    """Retourne JSON au lieu d'une page HTML sur erreur 500."""
    logger.exception("Erreur serveur 500")
    return jsonify({"error": f"Erreur interne du serveur : {e}", "status": "error"}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """Attrape les exceptions non gerees pour eviter les pages 500 HTML."""
    logger.exception("Exception non geree")
    return jsonify({"error": str(e), "status": "error"}), 500


@app.route("/favicon.ico")
def favicon():
    """Sert le favicon PNG ou retourne 204 si absent."""
    favicon_path = _THIS_DIR / "assets" / "artwork" / "favicon2.png"
    if favicon_path.exists():
        response = send_from_directory(str(favicon_path.parent), favicon_path.name, mimetype="image/png")
        response.cache_control.max_age = 2592000  # 30 jours
        return response
    return "", 204


@app.route("/assets/manifest.json")
def serve_manifest():
    """Sert le web app manifest."""
    response = send_from_directory(str(_THIS_DIR / "assets"), "manifest.json", mimetype="application/manifest+json")
    response.cache_control.max_age = 86400  # 1 jour
    return response


@app.route("/assets/artwork/<path:filename>")
def serve_artwork(filename):
    """Sert les fichiers artwork (favicon, images)."""
    artwork_dir = _THIS_DIR / "assets" / "artwork"
    response = send_from_directory(str(artwork_dir), filename)
    response.cache_control.max_age = 2592000  # 30 jours
    return response


@app.route("/audio/episodes/<path:filename>")
def serve_episode_audio(filename):
    """Sert les fichiers audio des épisodes produits (MP3).

    Cherche d'abord sur le filesystem local, puis restaure depuis
    Replit Object Storage si le fichier est absent (après re-deploy).
    """
    # Security: only allow .mp3 files, no path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "Nom de fichier invalide"}), 400
    if not filename.endswith(".mp3"):
        return jsonify({"error": "Format non supporté"}), 400
    episodes_dir = config.OUTPUT_DIR
    audio_path = episodes_dir / filename
    if not audio_path.exists():
        # Tenter de restaurer depuis Object Storage
        try:
            import persistent_storage
            storage_key = f"{persistent_storage.PREFIX_AUDIO}{filename}"
            if persistent_storage.download_file(storage_key, audio_path):
                logger.info("Audio restauré depuis Object Storage : %s", filename)
            else:
                return jsonify({"error": f"Fichier audio introuvable : {filename}"}), 404
        except Exception:
            return jsonify({"error": f"Fichier audio introuvable : {filename}"}), 404
    response = send_from_directory(str(episodes_dir), filename, mimetype="audio/mpeg")
    # Empêcher le cache navigateur de servir un ancien fichier après regénération
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


def _check_api_key(key_name="ANTHROPIC_API_KEY"):
    """Verifie qu'une cle API est configuree. Retourne une reponse d'erreur ou None."""
    if not os.getenv(key_name):
        return jsonify({
            "error": f"Cle API manquante : {key_name}. "
                     f"Ajoutez-la dans les Secrets Replit (onglet cadenas).",
            "status": "error",
        }), 400
    return None


# ── Systeme de jobs asynchrones ──────────────────────────────────────────────

_jobs = {}          # {job_id: {"status": ..., "result": ..., "created_at": ...}}
_jobs_lock = threading.Lock()
_job_processes = {} # {job_id: subprocess.Popen} — per-job process tracking
_process_lock = threading.Lock()


def _terminate_all_subprocesses():
    """Envoie SIGTERM à tous les subprocesses de production en cours.

    Appelé via atexit et le handler SIGTERM du worker gunicorn pour que les
    subprocesses main.py reçoivent SIGTERM et puissent sauvegarder leurs
    checkpoints avant de mourir.

    Sans cela, quand Replit recycle le container :
    1. SIGTERM → gunicorn master → workers meurent
    2. Les subprocesses deviennent orphelins → SIGKILL direct → aucun checkpoint
    """
    with _process_lock:
        procs = list(_job_processes.items())
    for jid, proc in procs:
        try:
            if proc.poll() is None:  # Encore vivant
                logger.info("Forwarding SIGTERM to subprocess %s (pid %d)", jid, proc.pid)
                proc.terminate()  # Envoie SIGTERM
        except Exception as e:
            logger.debug("Cannot terminate subprocess %s: %s", jid, e)
    # Laisser le temps aux subprocesses de sauvegarder leurs checkpoints
    # (le handler SIGTERM de main.py prend ~2-5 secondes pour DB+OS+fichier)
    if procs:
        time.sleep(5)


# ── Forward SIGTERM aux subprocesses ──────────────────────────────────────
# Quand Replit recycle le container, SIGTERM va à gunicorn qui tue ses workers.
# Les subprocesses (main.py) ne reçoivent PAS SIGTERM et sont SIGKILL'd sans
# pouvoir sauvegarder leur checkpoint. Ceci est la cause racine des 17 échecs.
_original_sigterm = signal.getsignal(signal.SIGTERM)


def _sigterm_forward_handler(signum, frame):
    """Forward SIGTERM aux subprocesses, puis exécuter le handler original."""
    _terminate_all_subprocesses()
    # Ré-exécuter le handler original (gunicorn en a un)
    if callable(_original_sigterm) and _original_sigterm not in (signal.SIG_DFL, signal.SIG_IGN):
        _original_sigterm(signum, frame)
    else:
        sys.exit(0)


try:
    signal.signal(signal.SIGTERM, _sigterm_forward_handler)
except (ValueError, OSError):
    pass  # Pas le thread principal — on se rabat sur atexit


# Fallback: atexit fonctionne sur exit() et SystemExit (mais pas SIGKILL)
atexit.register(_terminate_all_subprocesses)


_JOB_TTL_SECONDS = 3600  # Supprimer les jobs termines apres 1 heure

# Timeouts par type de job (configurables via env, minimum 300s = 5 min)
_TIMEOUT_MIN = 300  # Sécurité: empêcher les timeouts absurdement bas (ex: env var à "2")
_TIMEOUT_PRODUIRE = max(_TIMEOUT_MIN, int(os.getenv("TIMEOUT_PRODUIRE", "7200")))          # 2h
_TIMEOUT_PLANIFIER = max(_TIMEOUT_MIN, int(os.getenv("TIMEOUT_PLANIFIER", "1800")))        # 30 min
_TIMEOUT_PRODUIRE_SAISON = max(_TIMEOUT_MIN, int(os.getenv("TIMEOUT_PRODUIRE_SAISON", "7200")))  # 2h
_TIMEOUT_REPRENDRE = max(_TIMEOUT_MIN, int(os.getenv("TIMEOUT_REPRENDRE", "7200")))        # 2h
_TIMEOUT_BATCH = max(_TIMEOUT_MIN, int(os.getenv("TIMEOUT_BATCH", "7200")))                # 2h

# Avertir si un timeout env var était trop bas (cause fréquente de "timed out after 2 seconds")
for _tname, _tval, _tenv in [
    ("PRODUIRE", _TIMEOUT_PRODUIRE, "TIMEOUT_PRODUIRE"),
    ("REPRENDRE", _TIMEOUT_REPRENDRE, "TIMEOUT_REPRENDRE"),
    ("PLANIFIER", _TIMEOUT_PLANIFIER, "TIMEOUT_PLANIFIER"),
    ("BATCH", _TIMEOUT_BATCH, "TIMEOUT_BATCH"),
    ("SAISON", _TIMEOUT_PRODUIRE_SAISON, "TIMEOUT_PRODUIRE_SAISON"),
]:
    _raw = os.getenv(_tenv)
    if _raw is not None and int(_raw) < _TIMEOUT_MIN:
        logger.warning(
            "⚠ Variable %s=%s trop basse (min %ds) — forcée à %ds. "
            "Supprimez cette variable des Replit Secrets.",
            _tenv, _raw, _TIMEOUT_MIN, _tval,
        )

_JOB_ID_RE = re.compile(r'^[0-9a-f]{12}$')


def _sync_rapport_to_db(episode_id: str, rapport: dict) -> None:
    """Synchronise le rapport de production en DB (mise à jour de la production la plus récente).

    Appelé après chaque modification du rapport (validation, etc.) pour que les données
    survivent aux redéploiements Replit.
    """
    try:
        from database import DATABASE_URL, get_cursor
        if not DATABASE_URL:
            return
        with get_cursor() as cur:
            cur.execute(
                "UPDATE productions SET rapport_json = %s, updated_at = NOW() "
                "WHERE id = (SELECT id FROM productions WHERE episode_id = %s "
                "ORDER BY started_at DESC LIMIT 1) "
                "RETURNING id",
                (json.dumps(rapport, ensure_ascii=False, default=str), episode_id),
            )
            row = cur.fetchone()
            if not row:
                logger.warning(
                    "Sync rapport DB : aucune production trouvée pour %s — "
                    "le rapport n'a pas été persisté en DB.", episode_id,
                )
    except Exception as e:
        logger.error("Sync rapport DB ÉCHOUÉ pour %s : %s", episode_id, e)


def _sync_script_validated_to_db(episode_id: str) -> None:
    """Marque le script le plus récent comme validé en DB.

    Appelé lors de la validation web du script pour que le script validé
    survive aux redéploiements Replit (le fichier _valide.json est éphémère).
    """
    try:
        from database import DATABASE_URL, get_cursor
        if not DATABASE_URL:
            return
        with get_cursor() as cur:
            # Charger le script le plus récent
            cur.execute(
                "UPDATE scripts SET is_validated = TRUE "
                "WHERE id = (SELECT id FROM scripts WHERE episode_id = %s "
                "ORDER BY version DESC LIMIT 1) "
                "RETURNING id",
                (episode_id,),
            )
            row = cur.fetchone()
            if row:
                logger.info("Script %s marqué validé en DB (id=%d)", episode_id, row["id"])
            else:
                # Pas de script en DB → sauvegarder depuis le fichier
                import json as _json
                script_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
                if script_path.exists():
                    with open(script_path, "r", encoding="utf-8") as f:
                        script = _json.load(f)
                    from db_models import ScriptRepo
                    nb_mots = sum(
                        len(s.get("texte", "").split())
                        for s in script.get("episode", {}).get("segments", [])
                        if s.get("personnage") != "sfx"
                    )
                    ScriptRepo.sauvegarder(
                        episode_id=episode_id,
                        script=script,
                        nb_mots=nb_mots,
                        is_validated=True,
                        source="validation_web",
                    )
                    logger.info("Script %s sauvegardé + validé en DB depuis fichier", episode_id)
    except Exception as e:
        logger.error("Sync script validé DB ÉCHOUÉ pour %s : %s", episode_id, e)


def _sync_checkpoint_to_db(episode_id: str) -> None:
    """Synchronise le checkpoint en DB pour survie au redéploiement.

    Sauvegarde le dict 'data' interne du checkpoint en DB (pas l'enveloppe
    complète). L'enveloppe {episode_id, etape, timestamp, data} est
    reconstruite par _restore_checkpoint_from_db() à la restauration.
    """
    try:
        from database import DATABASE_URL, get_cursor
        if not DATABASE_URL:
            return
        import json as _json
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
        if not checkpoint_path.exists():
            return
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            cp_full = _json.load(f)
        # Stocker SEULEMENT le dict 'data' interne, pas l'enveloppe complète.
        # L'enveloppe sera reconstruite par _restore_checkpoint_from_db().
        cp_data_only = cp_full.get("data", cp_full)
        with get_cursor() as cur:
            cur.execute(
                "UPDATE productions SET checkpoint_data = %s, updated_at = NOW() "
                "WHERE id = (SELECT id FROM productions WHERE episode_id = %s "
                "ORDER BY started_at DESC LIMIT 1) "
                "RETURNING id",
                (_json.dumps(cp_data_only, ensure_ascii=False, default=str), episode_id),
            )
            row = cur.fetchone()
            if row:
                logger.info("Checkpoint %s synchronisé en DB (production id=%d)", episode_id, row["id"])
    except Exception as e:
        logger.error("Sync checkpoint DB ÉCHOUÉ pour %s : %s", episode_id, e)


def _restore_valide_script(episode_id: str) -> bool:
    """S'assure que _valide.json existe pour un épisode. Retourne True si le fichier existe.

    Restauration 3 couches (défense en profondeur, post-redeploy Replit) :
    1. Copie locale _script.json → _valide.json
    2. Object Storage (persistent_storage.restore_script)
    3. DB (ScriptRepo.charger_valide / charger_derniere_version)

    Appelé par continue-production (avant subprocess) et par les callbacks
    de chaînage SFX/montage (entre jobs auto-chaînés).
    """
    valide_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    if valide_path.exists():
        return True
    script_source = config.SCRIPTS_DIR / f"{episode_id}_script.json"
    # Couche 1 : copie locale
    if script_source.exists():
        import shutil
        shutil.copy2(script_source, valide_path)
        logger.info("_restore_valide_script: copie locale _script→_valide pour %s", episode_id)
        return True
    # Couche 2 : Object Storage
    try:
        import persistent_storage
        persistent_storage.restore_script(episode_id, config.SCRIPTS_DIR)
        if valide_path.exists():
            logger.info("_restore_valide_script: restauré _valide depuis Object Storage pour %s", episode_id)
            return True
        # Object Storage peut avoir _script.json mais pas _valide.json
        if script_source.exists():
            import shutil
            shutil.copy2(script_source, valide_path)
            logger.info("_restore_valide_script: restauré _script depuis OS puis copie vers _valide pour %s", episode_id)
            return True
    except Exception as e:
        logger.debug("_restore_valide_script: Object Storage pour %s : %s", episode_id, e)
    # Couche 3 : DB
    if not valide_path.exists():
        try:
            from db_models import ScriptRepo
            db_script = ScriptRepo.charger_valide(episode_id)
            if not db_script or not db_script.get("episode"):
                db_script = ScriptRepo.charger_derniere_version(episode_id)
            if db_script and db_script.get("episode"):
                config.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
                import json as _json
                with open(valide_path, "w", encoding="utf-8") as f:
                    _json.dump(db_script, f, ensure_ascii=False, indent=2)
                logger.info("_restore_valide_script: restauré depuis DB pour %s", episode_id)
                return True
        except Exception as e:
            logger.warning("_restore_valide_script: DB pour %s : %s", episode_id, e)
    return valide_path.exists()


def _restore_checkpoint_from_db(episode_id: str, checkpoint_path) -> None:
    """Restaure un checkpoint depuis la DB si le fichier local n'existe pas.

    Après un redéploiement Replit, les fichiers checkpoint sont perdus.
    Cette fonction les restaure depuis le champ checkpoint_data de la
    production la plus récente NON-VIDE en DB.

    IMPORTANT : la DB stocke uniquement le dict 'data' du checkpoint,
    pas l'enveloppe complète {episode_id, etape, timestamp, data}.
    On reconstruit l'enveloppe ici avec etape_courante de la production.

    La query filtre les checkpoint_data vides ('{}') pour éviter de prendre
    une production fraîchement créée par reprendre() qui n'a pas encore
    de checkpoint sauvegardé.
    """
    try:
        from database import DATABASE_URL, get_cursor
        if not DATABASE_URL:
            return
        import json as _json
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT checkpoint_data, etape_courante FROM productions "
                "WHERE episode_id = %s "
                "AND checkpoint_data IS NOT NULL "
                "AND checkpoint_data != '{}' "
                "AND checkpoint_data != 'null' "
                "AND status NOT IN ('completed', 'failed') "
                "ORDER BY updated_at DESC LIMIT 1",
                (episode_id,),
            )
            row = cur.fetchone()
        if row and row["checkpoint_data"]:
            cp_data = row["checkpoint_data"]
            etape = row["etape_courante"] or "script"

            # Détecter si la DB contient une enveloppe complète (ancien bug)
            # ou juste le dict 'data' interne (format correct).
            # Enveloppe = a "episode_id" + "etape" + "data" keys
            if (isinstance(cp_data, dict) and "data" in cp_data
                    and "etape" in cp_data and "episode_id" in cp_data):
                # Ancien format : la DB contient l'enveloppe complète.
                # Utiliser directement comme checkpoint (ne pas re-envelopper).
                checkpoint_envelope = cp_data
                # Mais utiliser l'étape DB (plus récente) si dispo
                if etape and etape != "script":
                    checkpoint_envelope["etape"] = etape
                logger.info("Checkpoint %s : détecté ancien format enveloppe en DB, utilisé tel quel", episode_id)
            else:
                # Format correct : la DB contient le dict 'data' interne.
                # Reconstruire l'enveloppe attendue par charger_checkpoint()
                checkpoint_envelope = {
                    "episode_id": episode_id,
                    "etape": etape,
                    "timestamp": datetime.now().isoformat(),
                    "data": cp_data,
                }

            # S'assurer que le répertoire existe
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                _json.dump(checkpoint_envelope, f, ensure_ascii=False, indent=2)
            logger.info("Checkpoint %s restauré depuis la DB (étape: %s)", episode_id, etape)

            # Restaurer aussi le script validé si absent
            script_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
            if not script_path.exists():
                try:
                    from db_models import ScriptRepo
                    db_script = ScriptRepo.charger_valide(episode_id)
                    if not db_script or not db_script.get("episode"):
                        db_script = ScriptRepo.charger_derniere_version(episode_id)
                    if db_script and db_script.get("episode"):
                        script_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(script_path, "w", encoding="utf-8") as f:
                            _json.dump(db_script, f, ensure_ascii=False, indent=2)
                        logger.info("Script validé %s restauré depuis la DB", episode_id)
                except Exception as e:
                    logger.warning("Restauration script %s depuis DB échouée : %s", episode_id, e)
    except Exception as e:
        logger.warning("Restauration checkpoint %s depuis DB échouée : %s", episode_id, e)


def _gc_expired_jobs():
    """Supprime les jobs termines dont le TTL est depasse (appele sous _jobs_lock).

    Les jobs lus par le client sont supprimés après _JOB_RESULT_TTL (60s).
    Les jobs non lus sont supprimés après _JOB_TTL_SECONDS (1h).
    """
    now = time.monotonic()
    expired = []
    for jid, job in _jobs.items():
        if job["status"] != "done":
            continue
        # Jobs lus par le client : TTL court
        read_at = job.get("read_at")
        if read_at and now - read_at > _JOB_RESULT_TTL:
            expired.append(jid)
        # Jobs non lus : TTL long
        elif now - job.get("created_at", now) > _JOB_TTL_SECONDS:
            expired.append(jid)
    for jid in expired:
        _jobs.pop(jid, None)


def _extract_error_from_stderr(stderr):
    """Extrait un message d'erreur lisible du stderr d'un subprocess."""
    if not stderr:
        return None
    # Lignes a ignorer (warnings de configuration, pas des erreurs)
    _IGNORE_PATTERNS = ("PODCAST_CONFIG", "champs non configurés", "WARNING")
    for line in reversed(stderr.strip().splitlines()):
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
        if not clean:
            continue
        if any(pat in clean for pat in _IGNORE_PATTERNS):
            continue
        if clean.startswith("Erreur") or "API" in clean or "cle" in clean.lower():
            return clean
    # Derniere ligne nettoyee comme fallback (en ignorant les warnings)
    for line in reversed(stderr.strip().splitlines()):
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
        if clean and not any(pat in clean for pat in _IGNORE_PATTERNS):
            return clean
    return None


def _stream_reader(stream, label, job_id, collected_lines, lock):
    """Lit un flux ligne par ligne et le logue en temps réel.

    Tourne dans un thread dédié pour ne pas bloquer le thread principal.
    Les lignes sont aussi collectées dans collected_lines (protégé par lock) pour le résultat final.
    """
    try:
        for line in stream:
            line = line.rstrip("\n")
            if line:
                with lock:
                    collected_lines.append(line)
                logger.info("[%s %s] %s", label, job_id or "?", line)
    except Exception as e:
        # I3: Ne pas avaler silencieusement les erreurs de lecture
        logger.debug("[%s %s] Stream reader terminé : %s", label, job_id or "?", e)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _run_cli(cmd_args, timeout=300, job_id=None):
    """Lance une commande main.py et retourne le resultat.

    Utilise Popen pour permettre l'annulation via /api/cancel.
    Les logs (stdout/stderr) sont streamés en temps réel dans les deployment
    logs Replit, pour être visibles PENDANT l'exécution (pas seulement à la fin).
    """
    cmd = [sys.executable, "-u", "main.py"] + cmd_args
    # PYTHONUNBUFFERED=1 + "-u" : forcer le flush immédiat de stdout/stderr
    # Sans cela, Python utilise un buffer de 4-8KB quand stdout/stderr sont des PIPE,
    # et les logs ne sortent jamais avant que le process soit tué par le recyclage container.
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_THIS_DIR),
            env=env,
        )
        if job_id:
            with _process_lock:
                _job_processes[job_id] = proc

        # ── Streaming en temps réel ──────────────────────────────────────
        # Au lieu de proc.communicate() qui bufferise tout, on lit
        # stdout et stderr dans des threads séparés. Chaque ligne est
        # immédiatement loguée dans les deployment logs Replit.
        # I4: Lock partagé pour protéger les listes contre les accès concurrents.
        stdout_lines = []
        stderr_lines = []
        _lines_lock = threading.Lock()
        t_out = threading.Thread(
            target=_stream_reader,
            args=(proc.stdout, "stdout", job_id, stdout_lines, _lines_lock),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_stream_reader,
            args=(proc.stderr, "stderr", job_id, stderr_lines, _lines_lock),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()  # SIGTERM d'abord (graceful)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()  # SIGKILL en dernier recours
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass  # Le process est zombie, on continue
            return {"error": f"Timeout ({timeout}s)", "status": "error"}

        # Attendre que les threads de lecture finissent
        t_out.join(timeout=5)
        t_err.join(timeout=5)

        with _lines_lock:
            stdout = "\n".join(stdout_lines)
            stderr = "\n".join(stderr_lines)

        if proc.returncode == -9 or proc.returncode == -15:
            # SIGKILL (-9) = OOM killer ou kill externe
            # SIGTERM (-15) = annulation utilisateur ou recyclage container
            if proc.returncode == -9:
                err_msg = (
                    "Le processus a été tué par le système (SIGKILL). "
                    "Cause probable : mémoire insuffisante (OOM). "
                    "Le montage audio charge trop de données en RAM."
                )
                logger.error(
                    "[subprocess %s] OOM kill (SIGKILL) — "
                    "le montage a dépassé la limite mémoire du container",
                    job_id or "?",
                )
                return {"error": err_msg, "status": "error"}
            else:
                return {"error": "Production annulée (SIGTERM).", "status": "cancelled"}

        if proc.returncode != 0:
            logger.error(
                "[subprocess %s] Exited with code %d",
                job_id or "?", proc.returncode,
            )

        result = {
            "status": "ok" if proc.returncode == 0 else "error",
            "stdout": stdout[-4000:] if stdout else "",
            "stderr": stderr[-2000:] if stderr else "",
        }

        if proc.returncode != 0 and stderr:
            err_msg = _extract_error_from_stderr(stderr)
            if err_msg:
                result["error"] = err_msg

        return result
    except Exception as e:
        return {"error": str(e), "status": "error"}
    finally:
        if job_id:
            with _process_lock:
                _job_processes.pop(job_id, None)


def _persist_web_job_id(job_id, episode_id, max_wait=90):
    """Attend que la row production existe en DB, puis y stocke le web_job_id.

    Le subprocess (main.py) crée la row production APRÈS son lancement.
    Sur Replit, le subprocess met 15-30s pour démarrer Python, importer les
    modules, charger le checkpoint et appeler ProductionRepo.creer().
    On attend donc jusqu'à 90s (avec backoff progressif).
    """
    from db_models import get_cursor
    for attempt in range(max_wait):
        try:
            with get_cursor() as cur:
                cur.execute(
                    """UPDATE productions SET web_job_id = %s
                       WHERE id = (
                           SELECT id FROM productions
                           WHERE episode_id = %s
                           ORDER BY started_at DESC LIMIT 1
                       ) AND web_job_id IS NULL
                       RETURNING id""",
                    (job_id, episode_id),
                )
                if cur.fetchone():
                    logger.info("web_job_id %s persisté pour %s", job_id, episode_id)
                    return
        except Exception as exc:
            logger.debug("_persist_web_job_id tentative %d : %s", attempt, exc)
        # Backoff progressif : 1s les 30 premières tentatives, 2s ensuite
        time.sleep(1 if attempt < 30 else 2)
    logger.warning("web_job_id %s non persisté pour %s après %d tentatives", job_id, episode_id, max_wait)


def _start_job(cmd_args, timeout=300, cleanup_fn=None, episode_id=None, on_success_fn=None):
    """Lance un job en arriere-plan et retourne son ID immediatement.

    Args:
        cmd_args: Arguments pour main.py.
        timeout: Timeout en secondes.
        cleanup_fn: Fonction optionnelle appelee apres le job (ex: supprimer fichier temp).
        episode_id: Identifiant de l'épisode (pour empêcher les jobs concurrents).
        on_success_fn: Fonction appelée uniquement si le job réussit (returncode=0).
            Utilisé pour chaîner automatiquement les étapes (audio → sfx → montage).

    Returns:
        job_id (str): Identifiant unique du job.

    Raises:
        ValueError: Si un job est déjà en cours pour cet épisode.
    """
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _gc_expired_jobs()
        # Vérifier qu'aucun job n'est déjà en cours pour cet épisode
        if episode_id:
            for existing_job in _jobs.values():
                if (existing_job.get("episode_id") == episode_id
                        and existing_job["status"] == "running"):
                    raise ValueError(f"Un job est déjà en cours pour {episode_id}")
        _jobs[job_id] = {
            "status": "running", "result": None,
            "created_at": time.monotonic(),
            "episode_id": episode_id,
        }

    def _worker():
        # Persister web_job_id en parallèle (thread séparé car _run_cli bloque)
        if episode_id and _DB_AVAILABLE:
            threading.Thread(
                target=_persist_web_job_id,
                args=(job_id, episode_id),
                daemon=True,
            ).start()
        try:
            result = _run_cli(cmd_args, timeout=timeout, job_id=job_id)
            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "done",
                    "result": result,
                    "created_at": time.monotonic(),
                }
            # Auto-chaînage : lancer l'étape suivante si le job a réussi
            if on_success_fn and result.get("status") == "ok":
                try:
                    on_success_fn()
                except Exception as chain_err:
                    logger.warning(
                        "Auto-chaînage échoué après job %s : %s", job_id, chain_err,
                    )
        except Exception as e:
            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "done",
                    "result": {"error": str(e), "status": "error"},
                    "created_at": time.monotonic(),
                }
        finally:
            if cleanup_fn:
                try:
                    cleanup_fn()
                except Exception as exc:
                    logger.warning("Echec du cleanup pour le job %s : %s", job_id, exc)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id


_JOB_RESULT_TTL = 300  # Garder les résultats de jobs terminés 5 minutes
# (le client peut être en sleep/onglet inactif — 60s était trop court)


@app.route("/api/job-status/<job_id>")
def api_job_status(job_id):
    """Retourne le statut d'un job asynchrone.

    Les jobs terminés sont gardés en cache pendant 60 secondes pour éviter
    la perte de résultat si le client ne poll pas assez vite (race condition).
    """
    if not _JOB_ID_RE.match(job_id):
        return jsonify({"error": "Format de job_id invalide"}), 400
    with _jobs_lock:
        _gc_expired_jobs()  # Nettoyage actif à chaque poll (pas seulement au lancement)
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": f"Job introuvable : {job_id}"}), 404
        if job["status"] == "running":
            return jsonify({"status": "running"})
        # Job terminé — marquer comme lu mais garder en cache pour le TTL
        result = job["result"]
        job["read_at"] = time.monotonic()
    return jsonify(result)


@app.route("/api/running-jobs")
def api_running_jobs():
    """Liste les jobs en cours — permet au navigateur de se reconnecter après perte réseau.

    Vérifie deux sources :
    1. Le dict _jobs en mémoire (jobs du process courant — prioritaire)
    2. La table productions en DB (jobs qui ont survécu à un redéploiement)

    Les productions 'interrupted' ne sont PAS listées ici — elles sont
    reprises automatiquement par le thread _auto_resume_interrupted au démarrage.
    Une fois reprises, elles apparaissent comme jobs en mémoire (source 1).
    """
    running = []
    memory_episodes = set()

    # Source 1 : jobs en mémoire (prioritaires — ce sont les vrais jobs actifs)
    with _jobs_lock:
        for jid, job in _jobs.items():
            if job["status"] == "running":
                ep_id = job.get("episode_id")
                running.append({
                    "job_id": jid,
                    "episode_id": ep_id,
                    "source": "memory",
                })
                if ep_id:
                    memory_episodes.add(ep_id)

    # Source 2 : productions en DB (fallback pour les jobs non encore repris)
    if _DB_AVAILABLE:
        try:
            from db_models import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    """SELECT web_job_id, episode_id, etape_courante, status
                       FROM productions
                       WHERE web_job_id IS NOT NULL
                         AND status NOT IN ('completed', 'failed', 'interrupted')
                         AND started_at > NOW() - INTERVAL '2 hours'
                       ORDER BY started_at DESC LIMIT 10""",
                )
                for row in cur.fetchall():
                    ep_id = row["episode_id"]
                    jid = row["web_job_id"]
                    # Ne pas dupliquer si un job en mémoire couvre déjà cet épisode
                    if ep_id in memory_episodes:
                        continue
                    if not any(r["job_id"] == jid for r in running):
                        running.append({
                            "job_id": jid,
                            "episode_id": ep_id,
                            "etape": row["etape_courante"],
                            "source": "db",
                        })
        except Exception as exc:
            logger.warning("Erreur lecture running-jobs DB : %s", exc)

    return jsonify({"jobs": running})


# ── Routes pages ─────────────────────────────────────────────────────────────


@app.route("/healthz")
def healthz():
    """Endpoint de health check leger — repond 200 immediatement."""
    return "ok", 200


@app.route("/api/storage-status")
def api_storage_status():
    """Diagnostic de l'état des systèmes de persistance.

    Vérifie PostgreSQL, Object Storage, et les données disponibles.
    """
    status = {
        "postgresql": {"available": False, "url_configured": False},
        "object_storage": {"available": False},
        "saisons_fichiers": [],
        "persistence_ok": False,
    }

    # PostgreSQL
    try:
        from database import DATABASE_URL
        status["postgresql"]["url_configured"] = bool(DATABASE_URL)
        if DATABASE_URL:
            from database import verifier_connexion
            status["postgresql"]["available"] = verifier_connexion()
    except Exception as e:
        status["postgresql"]["error"] = str(e)

    # Object Storage
    try:
        import persistent_storage
        status["object_storage"]["available"] = persistent_storage.is_available()
        if persistent_storage.is_available():
            status["object_storage"]["saisons"] = persistent_storage.list_files("saisons/")
            status["object_storage"]["scripts"] = len(persistent_storage.list_files("scripts/"))
            status["object_storage"]["rapports"] = len(persistent_storage.list_files("rapports/"))
            status["object_storage"]["checkpoints"] = len(persistent_storage.list_files("checkpoints/"))
    except Exception as e:
        status["object_storage"]["error"] = str(e)

    # Fichiers locaux
    try:
        for f in config.SAISONS_DIR.glob("saison_*.json"):
            status["saisons_fichiers"].append(f.name)
    except Exception:
        pass

    # Résumé
    status["persistence_ok"] = (
        status["postgresql"]["available"]
        or status["object_storage"]["available"]
    )
    if not status["persistence_ok"]:
        status["warning"] = (
            "AUCUN système de persistance actif ! "
            "Les données seront perdues au prochain redéploiement. "
            "Configurez DATABASE_URL ou activez Replit Object Storage."
        )

    return jsonify(status)


@app.route("/")
def public_index():
    """Page publique — Site vitrine du podcast."""
    return render_template("public.html")


@app.route("/admin")
@_admin_required
def admin_dashboard():
    """Dashboard admin V2 — SPA (protégé par mot de passe)."""
    return render_template("admin_v2.html")


@app.route("/admin/v1")
@_admin_required
def admin_dashboard_v1():
    """Dashboard admin V1 legacy (protégé par mot de passe)."""
    try:
        saison = request.args.get("saison", 0, type=int)
        data = get_dashboard_data(saison)
        return render_template("dashboard.html", **data)
    except Exception as e:
        logger.exception("Erreur rendu dashboard")
        return (
            f"<html><body><h1>Les Histoires de Papy Babou</h1>"
            f"<p>Erreur au chargement du dashboard : {e}</p>"
            f"<p><a href='/api/dashboard'>Voir les donnees JSON</a></p>"
            f"</body></html>"
        ), 200


# ── Route API publique ────────────────────────────────────────────────────────


@app.route("/api/public/episodes")
def api_public_episodes():
    """API publique — Episodes publiés avec métadonnées pour le site vitrine.

    Retourne uniquement les épisodes qui ont un audio disponible (produits et publiés).
    Aucune donnée sensible (rapports, checkpoints, config) n'est exposée.

    Performance: loads seasons ONCE, batches all DB queries and filesystem globs
    to avoid N+1 patterns (was calling liste_saisons() twice, charger_saison()
    per season twice, and cover art check per episode).
    """
    try:
        historique = dashboard_data_mod.charger_historique_complet()
    except Exception:
        historique = []

    # ── Load all season plans ONCE ────────────────────────────────────────────
    # liste_saisons() triggers Object Storage restore — call it only once
    saison_plans_cache = {}  # {numero: plan_dict}
    try:
        saisons_list = config.liste_saisons() if hasattr(config, 'liste_saisons') else []
        for num in saisons_list:
            saison_plans_cache[num] = config.charger_saison(num)
    except Exception as e:
        logger.warning("Erreur chargement saisons: %s", e)

    # Build saisons_info (only saisons with episodes in historique)
    # Extract saison from episode_id (S01E01 → 1) when field is missing (DB rows)
    def _extract_saison(ep):
        s = ep.get("saison")
        if s:
            return int(s)
        eid = ep.get("episode_id", "")
        if eid and len(eid) >= 3 and eid[0] == "S":
            try:
                return int(eid[1:3])
            except ValueError:
                pass
        return 1

    saisons_info = []
    saison_nums_avec_episodes = set(_extract_saison(ep) for ep in historique)
    for num in sorted(saison_plans_cache):
        if num not in saison_nums_avec_episodes:
            continue  # Saison planifiée mais pas encore diffusée
        saison_data = saison_plans_cache[num].get("saison", {})
        saisons_info.append({
            "numero": num,
            "theme": saison_data.get("theme", ""),
        })

    # Fallback: saisons détectées depuis l'historique mais sans plan JSON
    saisons_in_info = set(s["numero"] for s in saisons_info)
    for num in sorted(saison_nums_avec_episodes):
        if num not in saisons_in_info:
            saisons_info.append({"numero": num, "theme": ""})
    saisons_info.sort(key=lambda s: s["numero"])

    # Build plans_episodes from cached plans (no second liste_saisons/charger_saison call)
    plans_episodes = {}  # {(saison, numero): episode_plan_data}
    for num, plan in saison_plans_cache.items():
        for ep_plan in plan.get("saison", {}).get("episodes", []):
            plans_episodes[(num, ep_plan.get("numero", 0))] = ep_plan

    # ── Batch DB queries ──────────────────────────────────────────────────────
    # Single _db_disponible() check, then run production statuses query
    _production_statuses = {}  # episode_id -> latest status
    _AUDIO_READY_STATUSES = {
        "completed", "montage_done", "metadonnees_done", "waiting_montage",
    }
    if config._db_disponible():
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT DISTINCT ON (episode_id) episode_id, status "
                    "FROM productions ORDER BY episode_id, id DESC"
                )
                for row in cur.fetchall():
                    _production_statuses[row["episode_id"]] = row["status"]
        except Exception:
            pass

    # Pré-charger les fichiers audio en batch (1 query DB + 1 glob filesystem)
    all_episode_ids = [ep.get("episode_id", "") for ep in historique if ep.get("episode_id")]
    _audio_batch = {}
    try:
        _audio_batch = dashboard_data_mod.trouver_audio_batch(all_episode_ids)
    except Exception:
        pass

    # ── Batch cover art lookup (single glob instead of per-episode checks) ────
    _cover_files = {}  # episode_id -> cover_url
    try:
        if config.COVERS_DIR.exists():
            for cover_file in config.COVERS_DIR.iterdir():
                fname = cover_file.name
                if not fname.endswith((".png", ".jpg")):
                    continue
                # Parse episode_id from filename pattern: S01E01_cover.png
                if "_cover" in fname:
                    eid = fname.split("_cover")[0]
                    if eid and eid not in _cover_files:
                        _cover_files[eid] = f"/audio/covers/{fname}"
    except Exception:
        pass

    # Construire la liste d'épisodes publics
    episodes_public = []
    for ep in historique:
        episode_id = ep.get("episode_id", "")
        saison = ep.get("saison", 1)
        numero = ep.get("numero", 0)
        titre = ep.get("titre", "")

        # Fallback: parse saison/numero from episode_id (e.g. "S01E01")
        if (not numero or not saison) and len(episode_id) >= 6:
            try:
                saison = saison or int(episode_id[1:3])
                numero = numero or int(episode_id[4:6])
            except (ValueError, IndexError):
                pass

        # Chercher le fichier audio — seulement si la dernière production
        # a réellement terminé le montage (évite d'afficher des audio
        # d'anciennes productions obsolètes)
        audio_url = None
        latest_status = _production_statuses.get(episode_id)
        audio_eligible = (
            latest_status in _AUDIO_READY_STATUSES
            if latest_status
            else True  # pas de production en DB → fallback historique
        )
        if audio_eligible:
            audio_info = _audio_batch.get(episode_id, {})
            audio_name = audio_info.get("hq") or audio_info.get("preview")
            if audio_name:
                audio_url = f"/audio/episodes/{audio_name}"

        # Cover art from pre-loaded batch
        cover_url = _cover_files.get(episode_id)

        # Calculer la durée
        duree_minutes = None
        if ep.get("duree_secondes"):
            duree_minutes = round(ep["duree_secondes"] / 60)
        elif ep.get("duree_cible_minutes"):
            duree_minutes = ep["duree_cible_minutes"]

        # Date de production formatée
        date_str = ""
        date_prod = ep.get("date_production", "")
        if date_prod:
            try:
                dt = datetime.fromisoformat(date_prod.replace("Z", "+00:00"))
                date_str = dt.strftime("%d %b %Y")
            except (ValueError, TypeError):
                date_str = str(date_prod)[:10]

        # Enrichir avec le plan de saison (resume, histoire_biblique)
        plan_ep = plans_episodes.get((saison if isinstance(saison, int) else 1, numero if isinstance(numero, int) else 0), {})
        resume = ep.get("resume_court", ep.get("resume", ""))
        if not resume or len(resume) < 30:
            resume = plan_ep.get("resume", resume)
        histoire_biblique = plan_ep.get("histoire_biblique", "")

        # Determiner le statut de l'episode
        if audio_url:
            ep_status = "available"
        elif cover_url:
            ep_status = "coming_soon"
        else:
            ep_status = "planned"

        episodes_public.append({
            "episode_id": episode_id,
            "saison": saison if isinstance(saison, int) else 1,
            "numero": numero if isinstance(numero, int) else 0,
            "titre": titre,
            "resume": resume,
            "histoire_biblique": histoire_biblique,
            "morale": ep.get("morale", ""),
            "audio_url": audio_url,
            "cover_url": cover_url,
            "duree_minutes": duree_minutes,
            "date": date_str,
            "status": ep_status,
        })

    # Pour les saisons commencees, ajouter les episodes du plan qui ne sont
    # pas encore dans l'historique (episodes "planned")
    episodes_ids_existants = set(ep["episode_id"] for ep in episodes_public)
    for saison_num in sorted(saison_nums_avec_episodes):
        for key, ep_plan in plans_episodes.items():
            plan_saison, plan_numero = key
            if plan_saison != saison_num:
                continue
            ep_id = f"S{plan_saison:02d}E{plan_numero:02d}"
            if ep_id in episodes_ids_existants:
                continue

            # Cover art from pre-loaded batch
            plan_cover_url = _cover_files.get(ep_id)

            plan_status = "coming_soon" if plan_cover_url else "planned"

            # Duree cible depuis le plan
            plan_duree = ep_plan.get("duree_cible_minutes")

            episodes_public.append({
                "episode_id": ep_id,
                "saison": plan_saison,
                "numero": plan_numero,
                "titre": ep_plan.get("titre", f"Episode {plan_numero}"),
                "resume": ep_plan.get("resume", ""),
                "histoire_biblique": ep_plan.get("histoire_biblique", ""),
                "morale": ep_plan.get("morale", ""),
                "audio_url": None,
                "cover_url": plan_cover_url,
                "duree_minutes": plan_duree,
                "date": "",
                "status": plan_status,
            })

    # Trier par saison puis numero
    episodes_public.sort(key=lambda e: (e["saison"], e["numero"]))

    return jsonify({
        "episodes": episodes_public,
        "saisons": saisons_info,
    })


# ── Routes API (JSON) — Lecture (admin) ──────────────────────────────────────


@app.route("/api/dashboard")
def api_dashboard():
    """API JSON — Donnees completes du dashboard."""
    saison = request.args.get("saison", 0, type=int)
    data = get_dashboard_data(saison)
    return jsonify(data)


@app.route("/api/episodes")
def api_episodes():
    """API JSON — Liste des episodes."""
    saison = request.args.get("saison", 0, type=int)
    data = get_dashboard_data(saison)
    return jsonify(data["episodes"])


@app.route("/api/preferences")
def api_preferences():
    """API JSON — Preferences producteur."""
    return jsonify(charger_preferences())


@app.route("/api/checkpoints")
def api_checkpoints():
    """API JSON — Checkpoints en attente."""
    return jsonify(charger_checkpoints())


@app.route("/api/publications")
def api_publications():
    """API JSON — Statut des publications (RSS, Buzzsprout)."""
    return jsonify(charger_publications())


@app.route("/api/plan-saison/<int:numero>")
def api_plan_saison(numero):
    """API JSON — Detail d'un plan de saison."""
    plan = config.charger_saison(numero)
    if not plan:
        return jsonify({"error": f"Aucun plan pour la saison {numero}"}), 404
    return jsonify(plan)


@app.route("/api/saison-existe/<int:numero>")
def api_saison_existe(numero):
    """API JSON — Verifie si une saison existe deja."""
    plan = config.charger_saison(numero)
    if plan:
        saison_data = plan.get("saison", {})
        return jsonify({
            "existe": True,
            "theme": saison_data.get("theme", ""),
            "nb_episodes": len(saison_data.get("episodes", [])),
        })
    return jsonify({"existe": False})


@app.route("/api/episodes-saison/<int:numero>")
def api_episodes_saison(numero):
    """API JSON — Episodes existants d'une saison (produits ou planifies)."""
    episodes_produits = []

    # Episodes dans l'historique — extraire le numéro depuis episode_id (ex: "S01E03" → 3)
    data = get_dashboard_data(numero)
    for ep in data.get("episodes", []):
        eid = ep.get("episode_id", "")
        match = re.match(r"S\d{2}E(\d{2})", eid)
        if match:
            episodes_produits.append(int(match.group(1)))
        else:
            episodes_produits.append(ep.get("numero", 0))

    # Episodes dans le plan de saison
    plan = config.charger_saison(numero)
    nb_planifies = 0
    if plan:
        nb_planifies = len(plan.get("saison", {}).get("episodes", []))

    return jsonify({
        "saison": numero,
        "episodes_produits": sorted(set(episodes_produits)),
        "nb_planifies": nb_planifies,
        "prochain_numero": max(episodes_produits, default=0) + 1,
    })


@app.route("/api/config")
def api_config():
    """API JSON — Configuration du systeme."""
    try:
        api_keys = {
            "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
            "ELEVENLABS_API_KEY": bool(os.getenv("ELEVENLABS_API_KEY")),
            "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
            "BUZZSPROUT_API_KEY": bool(os.getenv("BUZZSPROUT_API_KEY")),
        }

        production = {}
        if hasattr(config, "PRODUCTION"):
            production = config.PRODUCTION

        voix = {}
        if hasattr(config, "VOICE_IDS"):
            voix = config.VOICE_IDS

        couts = {}
        if hasattr(config, "COUTS"):
            couts = config.COUTS

        formats = {}
        if hasattr(config, "FORMATS_EPISODES"):
            formats = config.FORMATS_EPISODES

        return jsonify({
            "api_keys": api_keys,
            "production": production,
            "voix": voix,
            "couts": couts,
            "formats": formats,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _is_episode_deleted(episode_id: str) -> bool:
    """Vérifie si un épisode a été supprimé (soft-delete DB ou fichiers archivés)."""
    # 1. Vérifier en DB
    if _DB_AVAILABLE:
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT deleted_at FROM episodes "
                    "WHERE episode_id = %s AND deleted_at IS NOT NULL LIMIT 1",
                    (episode_id,),
                )
                if cur.fetchone():
                    return True
        except Exception:
            pass

    # 2. Vérifier si les fichiers ont été archivés
    archive_dir = _THIS_DIR / "output" / "archive" / episode_id
    if archive_dir.exists() and any(archive_dir.iterdir()):
        return True

    return False


# ── Routes API — Suppression d'épisodes ──────────────────────────────────────


@app.route("/api/episode/<episode_id>/delete", methods=["POST"])
def api_delete_episode(episode_id):
    """Supprime un épisode produit (soft-delete DB + archivage fichiers).

    Supprime les fichiers locaux (script, rapport, audio, cover, checkpoint)
    et marque l'épisode comme supprimé en DB si PostgreSQL est disponible.
    L'historique JSON est aussi nettoyé.

    Body JSON optionnel :
        {"raison": "Pas satisfait du résultat"}
    """
    import json as _json
    import shutil

    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format d'identifiant invalide (attendu: S01E01)"}), 400

    body = request.get_json(silent=True) or {}
    raison = body.get("raison", "").strip()

    supprime = {"fichiers": [], "echecs": [], "db": []}

    def _archiver(src_path, category):
        """Déplace un fichier vers l'archive. Log les échecs au lieu de les ignorer."""
        try:
            shutil.move(str(src_path), str(archive_dir / src_path.name))
            supprime["fichiers"].append(f"{category}/{src_path.name}")
        except Exception as e:
            logger.warning("Échec archivage %s : %s", src_path, e)
            supprime["echecs"].append(f"{category}/{src_path.name}: {e}")

    # 1. Archiver les fichiers locaux (déplacer vers output/archive/)
    archive_dir = _THIS_DIR / "output" / "archive" / episode_id
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Script
    for pattern in [f"{episode_id}_valide.json", f"{episode_id}_script*.json"]:
        for f in config.SCRIPTS_DIR.glob(pattern):
            _archiver(f, "scripts")

    # Rapport
    rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
    if rapport_path.exists():
        _archiver(rapport_path, "logs")
    for f in config.LOGS_DIR.glob(f"{episode_id}_rapport_echec*.json"):
        _archiver(f, "logs")

    # Audio (preview + HQ)
    episodes_dir = _THIS_DIR / "output" / "episodes"
    if episodes_dir.exists():
        for f in episodes_dir.glob(f"{episode_id}*"):
            _archiver(f, "episodes")

    # Cover art
    if hasattr(config, "COVERS_DIR") and config.COVERS_DIR.exists():
        for f in config.COVERS_DIR.glob(f"{episode_id}_cover*"):
            _archiver(f, "covers")

    # Transcript
    if hasattr(config, "TRANSCRIPTS_DIR") and config.TRANSCRIPTS_DIR.exists():
        for f in config.TRANSCRIPTS_DIR.glob(f"{episode_id}_transcript*"):
            _archiver(f, "transcripts")

    # Checkpoint
    if hasattr(config, "CHECKPOINTS_DIR"):
        for f in config.CHECKPOINTS_DIR.glob(f"{episode_id}*checkpoint*"):
            _archiver(f, "checkpoints")

    # 2. Supprimer de l'historique JSON
    historique_path = config.HISTORIQUE_DIR / "historique_episodes.json"
    if historique_path.exists():
        try:
            with open(historique_path, "r", encoding="utf-8") as f:
                historique = _json.load(f)
            original_len = len(historique)
            historique = [ep for ep in historique if ep.get("episode_id") != episode_id]
            if len(historique) < original_len:
                with open(historique_path, "w", encoding="utf-8") as f:
                    _json.dump(historique, f, ensure_ascii=False, indent=2)
                supprime["fichiers"].append("historique_episodes.json (entrée retirée)")
        except Exception as e:
            logger.warning("Erreur nettoyage historique JSON pour %s : %s", episode_id, e)

    # 3. Soft-delete en DB (si disponible)
    if _DB_AVAILABLE:
        try:
            from database import get_cursor
            with get_cursor() as cur:
                # Soft-delete épisode
                cur.execute(
                    "UPDATE episodes SET deleted_at = NOW(), status = 'deleted' "
                    "WHERE episode_id = %s AND deleted_at IS NULL",
                    (episode_id,),
                )
                if cur.rowcount > 0:
                    supprime["db"].append("episodes")

                # Soft-delete de l'historique DB (récupérable)
                cur.execute(
                    "UPDATE historique_episodes SET deleted_at = NOW() "
                    "WHERE episode_id = %s AND deleted_at IS NULL",
                    (episode_id,),
                )
                if cur.rowcount > 0:
                    supprime["db"].append("historique_episodes")

                # Marquer les productions comme failed/deleted
                cur.execute(
                    "UPDATE productions SET status = 'deleted' "
                    "WHERE episode_id = %s AND status NOT IN ('deleted')",
                    (episode_id,),
                )
                if cur.rowcount > 0:
                    supprime["db"].append("productions")

                # Log dans audit_log
                cur.execute(
                    "INSERT INTO audit_log (table_name, action, context) "
                    "VALUES ('episodes', 'SOFT_DELETE', %s)",
                    (_json.dumps({
                        "episode_id": episode_id,
                        "raison": raison,
                        "fichiers_archives": supprime["fichiers"],
                    }, ensure_ascii=False),),
                )
        except Exception as e:
            logger.warning("Erreur soft-delete DB pour %s : %s", episode_id, e)

    # 4. Nettoyer Object Storage
    try:
        import persistent_storage
        if persistent_storage.is_available():
            for prefix in [persistent_storage.PREFIX_AUDIO,
                           persistent_storage.PREFIX_SCRIPT,
                           persistent_storage.PREFIX_RAPPORT]:
                keys = persistent_storage.list_files(f"{prefix}{episode_id}")
                for key in keys:
                    if persistent_storage.delete_file(key):
                        supprime["fichiers"].append(f"object_storage/{key}")
    except Exception as e:
        logger.warning("Erreur nettoyage Object Storage pour %s : %s", episode_id, e)

    total = len(supprime["fichiers"]) + len(supprime["db"])
    if total == 0:
        return jsonify({
            "status": "warning",
            "message": f"Aucune donnée trouvée pour {episode_id}. L'épisode n'existe peut-être pas.",
        })

    return jsonify({
        "status": "ok",
        "message": f"Épisode {episode_id} supprimé. {len(supprime['fichiers'])} fichier(s) archivé(s), {len(supprime['db'])} table(s) DB nettoyée(s).",
        "archive": str(archive_dir),
        "details": supprime,
    })


# ── Routes API — Purge de données de production ──────────────────────────────


@app.route("/api/purge/saison/<int:saison_num>", methods=["POST"])
def api_purge_saison(saison_num):
    """Purge TOUTES les données de production d'une saison.

    Supprime : historique, scripts, rapports, audio, checkpoints, covers,
    segments, productions DB, épisodes DB, plan de saison JSON + DB.

    Body JSON optionnel :
        {"garder_plan": true}  — supprime les épisodes produits mais garde le plan
    """
    import shutil

    body = request.get_json(silent=True) or {}
    garder_plan = body.get("garder_plan", False)

    prefix = f"S{saison_num:02d}"
    supprime = {"fichiers": 0, "db": 0, "details": []}

    # 1. Trouver tous les épisodes de cette saison dans l'historique
    historique_path = config.HISTORIQUE_DIR / "historique_episodes.json"
    episode_ids = set()
    if historique_path.exists():
        try:
            import json as _json
            with open(historique_path, "r", encoding="utf-8") as f:
                historique = _json.load(f)
            original_len = len(historique)
            episode_ids = {
                ep.get("episode_id") for ep in historique
                if ep.get("episode_id", "").startswith(prefix)
            }
            historique = [
                ep for ep in historique
                if not ep.get("episode_id", "").startswith(prefix)
            ]
            if len(historique) < original_len:
                with open(historique_path, "w", encoding="utf-8") as f:
                    _json.dump(historique, f, ensure_ascii=False, indent=2)
                nb = original_len - len(historique)
                supprime["fichiers"] += nb
                supprime["details"].append(f"historique: {nb} entrée(s)")
        except Exception as e:
            logger.warning("Erreur purge historique saison %d : %s", saison_num, e)

    # Aussi chercher les épisodes par pattern dans les fichiers
    for i in range(1, 21):
        episode_ids.add(f"S{saison_num:02d}E{i:02d}")

    # 2. Archiver les fichiers de chaque épisode
    for episode_id in sorted(episode_ids):
        archive_dir = _THIS_DIR / "output" / "archive" / episode_id
        archive_dir.mkdir(parents=True, exist_ok=True)

        for d, patterns in [
            (config.SCRIPTS_DIR, [f"{episode_id}_valide.json", f"{episode_id}_script*.json"]),
            (config.LOGS_DIR, [f"{episode_id}_rapport*.json"]),
            (_THIS_DIR / "output" / "episodes", [f"{episode_id}*"]),
        ]:
            if d.exists():
                for pat in patterns:
                    for f in d.glob(pat):
                        try:
                            shutil.move(str(f), str(archive_dir / f.name))
                            supprime["fichiers"] += 1
                        except Exception:
                            pass

        if hasattr(config, "COVERS_DIR") and config.COVERS_DIR.exists():
            for f in config.COVERS_DIR.glob(f"{episode_id}_cover*"):
                try:
                    shutil.move(str(f), str(archive_dir / f.name))
                    supprime["fichiers"] += 1
                except Exception:
                    pass

        if hasattr(config, "CHECKPOINTS_DIR"):
            for f in config.CHECKPOINTS_DIR.glob(f"{episode_id}*checkpoint*"):
                try:
                    shutil.move(str(f), str(archive_dir / f.name))
                    supprime["fichiers"] += 1
                except Exception:
                    pass

    # 3. Supprimer le plan de saison (sauf si garder_plan)
    if not garder_plan:
        plan_path = config.SAISONS_DIR / f"saison_{saison_num:02d}.json"
        if plan_path.exists():
            try:
                plan_path.unlink()
                supprime["fichiers"] += 1
                supprime["details"].append("plan de saison supprimé")
            except Exception as e:
                logger.warning("Erreur suppression plan saison %d : %s", saison_num, e)

    # 4. Purge DB
    if _DB_AVAILABLE:
        try:
            from database import get_cursor
            with get_cursor() as cur:
                for table in ["historique_episodes", "episodes", "productions", "scripts", "fichiers_audio"]:
                    try:
                        cur.execute(
                            f"DELETE FROM {table} WHERE episode_id LIKE %s",
                            (f"{prefix}%",),
                        )
                        if cur.rowcount > 0:
                            supprime["db"] += cur.rowcount
                            supprime["details"].append(f"DB {table}: {cur.rowcount} ligne(s)")
                    except Exception as e:
                        logger.warning("Erreur purge DB %s saison %d : %s", table, saison_num, e)

                if not garder_plan:
                    try:
                        cur.execute(
                            "DELETE FROM saisons WHERE numero = %s",
                            (saison_num,),
                        )
                        if cur.rowcount > 0:
                            supprime["db"] += cur.rowcount
                            supprime["details"].append(f"DB saisons: {cur.rowcount} version(s)")
                    except Exception as e:
                        logger.warning("Erreur purge DB saisons %d : %s", saison_num, e)

                cur.execute(
                    "INSERT INTO audit_log (table_name, action, context) "
                    "VALUES ('saisons', 'PURGE', %s)",
                    (json.dumps({
                        "saison": saison_num,
                        "garder_plan": garder_plan,
                        "supprime": supprime,
                    }, ensure_ascii=False, default=str),),
                )
        except Exception as e:
            logger.warning("Erreur purge DB saison %d : %s", saison_num, e)

    # 5. Nettoyer Object Storage
    try:
        import persistent_storage
        if persistent_storage.is_available():
            for pfx in [persistent_storage.PREFIX_AUDIO, persistent_storage.PREFIX_SCRIPT,
                        persistent_storage.PREFIX_RAPPORT, "segments/", "metadonnees/",
                        "chapters/", "covers/", "checkpoints/"]:
                for eid in sorted(episode_ids):
                    keys = persistent_storage.list_files(f"{pfx}{eid}")
                    for key in keys:
                        if persistent_storage.delete_file(key):
                            supprime["fichiers"] += 1
    except Exception as e:
        logger.warning("Erreur purge Object Storage saison %d : %s", saison_num, e)

    total = supprime["fichiers"] + supprime["db"]
    return jsonify({
        "status": "ok",
        "message": f"Saison {saison_num} purgée. {supprime['fichiers']} fichier(s), {supprime['db']} entrée(s) DB.",
        "total": total,
        "details": supprime,
    })


@app.route("/api/purge/tout", methods=["POST"])
def api_purge_tout():
    """Purge TOUTES les données de production — reset complet.

    Supprime : historique JSON, tous les fichiers produits, toutes les tables DB.
    Les plans de saison sont supprimés aussi.
    """
    supprime = {"fichiers": 0, "db": 0, "details": []}

    # 1. Vider l'historique JSON
    historique_path = config.HISTORIQUE_DIR / "historique_episodes.json"
    if historique_path.exists():
        try:
            with open(historique_path, "w", encoding="utf-8") as f:
                json.dump([], f)
            supprime["fichiers"] += 1
            supprime["details"].append("historique vidé")
        except Exception as e:
            logger.warning("Erreur purge historique : %s", e)

    # 2. Vider les répertoires de production
    import shutil
    for d_name, d_path in [
        ("scripts", config.SCRIPTS_DIR),
        ("logs", config.LOGS_DIR),
        ("episodes", _THIS_DIR / "output" / "episodes"),
        ("saisons", config.SAISONS_DIR),
    ]:
        if d_path.exists():
            for f in d_path.iterdir():
                if f.is_file() and f.suffix == ".json" or f.suffix in (".mp3", ".wav", ".png", ".jpg"):
                    try:
                        f.unlink()
                        supprime["fichiers"] += 1
                    except Exception:
                        pass

    if hasattr(config, "COVERS_DIR") and config.COVERS_DIR.exists():
        for f in config.COVERS_DIR.glob("*"):
            if f.is_file():
                try:
                    f.unlink()
                    supprime["fichiers"] += 1
                except Exception:
                    pass

    if hasattr(config, "CHECKPOINTS_DIR") and config.CHECKPOINTS_DIR.exists():
        for f in config.CHECKPOINTS_DIR.glob("*"):
            if f.is_file():
                try:
                    f.unlink()
                    supprime["fichiers"] += 1
                except Exception:
                    pass

    # 3. Purge DB complète
    if _DB_AVAILABLE:
        try:
            from database import get_cursor
            with get_cursor() as cur:
                for table in ["historique_episodes", "productions", "scripts",
                              "fichiers_audio", "episodes", "saisons"]:
                    try:
                        cur.execute(f"DELETE FROM {table}")
                        if cur.rowcount > 0:
                            supprime["db"] += cur.rowcount
                            supprime["details"].append(f"DB {table}: {cur.rowcount}")
                    except Exception as e:
                        logger.warning("Erreur purge DB %s : %s", table, e)

                cur.execute(
                    "INSERT INTO audit_log (table_name, action, context) "
                    "VALUES ('all', 'PURGE_TOUT', %s)",
                    (json.dumps({"supprime": supprime}, ensure_ascii=False, default=str),),
                )
        except Exception as e:
            logger.warning("Erreur purge DB globale : %s", e)

    total = supprime["fichiers"] + supprime["db"]
    return jsonify({
        "status": "ok",
        "message": f"Reset complet. {supprime['fichiers']} fichier(s), {supprime['db']} entrée(s) DB.",
        "total": total,
        "details": supprime,
    })


# ── Routes API — Validation des épisodes ─────────────────────────────────────


@app.route("/api/episode/<episode_id>")
def api_episode_detail(episode_id):
    """API JSON — Détail complet d'un épisode pour la validation."""
    import json as _json

    # Security: validate episode_id format (S01E01)
    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format d'identifiant invalide (attendu: S01E01)"}), 400

    data = get_dashboard_data(0)
    episode = next((ep for ep in data["episodes"] if ep["episode_id"] == episode_id), None)
    if not episode:
        return jsonify({"error": f"Épisode introuvable : {episode_id}"}), 404

    # Load script content (filesystem → Object Storage → DB)
    script = None
    # Chercher le script : _valide.json d'abord, puis _script.json (scripts écrits hors pipeline)
    script_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    if not script_path.exists():
        script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"
    if not script_path.exists():
        # Tenter de restaurer depuis Object Storage
        try:
            import persistent_storage
            persistent_storage.restore_script(episode_id, config.SCRIPTS_DIR)
            # Re-vérifier après restauration
            for suffix in ("_valide.json", "_script.json"):
                p = config.SCRIPTS_DIR / f"{episode_id}{suffix}"
                if p.exists():
                    script_path = p
                    break
        except Exception:
            pass
    if script_path.exists():
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script = _json.load(f)
        except (ValueError, FileNotFoundError):
            pass
    if not script:
        # Fallback: load validated script from DB
        try:
            from db_models import ScriptRepo
            db_script = ScriptRepo.charger_valide(episode_id)
            if db_script and db_script.get("episode"):
                script = db_script
                logger.info("Script %s chargé depuis la DB (version validée).", episode_id)
            else:
                db_script = ScriptRepo.charger_derniere_version(episode_id)
                if db_script and db_script.get("episode"):
                    script = db_script
                    logger.info("Script %s chargé depuis la DB (dernière version).", episode_id)
        except Exception as e:
            logger.warning("Échec chargement script DB pour %s : %s", episode_id, e)

    # Load rapport for detailed info
    rapport = dashboard_data_mod.charger_rapport(episode_id)

    # Dernier recours : charger le script depuis le checkpoint
    if not script:
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    cp_data = _json.load(f)
                script_path_cp = cp_data.get("data", {}).get("script_path")
                if script_path_cp:
                    sp = Path(script_path_cp)
                    if sp.exists():
                        with open(sp, "r", encoding="utf-8") as f:
                            script = _json.load(f)
                        logger.info("Script %s chargé depuis checkpoint.", episode_id)
            except Exception as e:
                logger.warning("Échec chargement script checkpoint %s : %s", episode_id, e)

    # Load cover art path (restore from Object Storage if missing)
    cover_art = None
    for ext in (".png", ".jpg"):
        cover_path = config.COVERS_DIR / f"{episode_id}_cover{ext}"
        if cover_path.exists():
            cover_art = f"{episode_id}_cover{ext}"
            break
    if not cover_art:
        try:
            import persistent_storage
            restored = persistent_storage.restore_cover(episode_id, config.COVERS_DIR)
            if restored:
                cover_art = restored.name
        except Exception:
            pass

    # Load transcript
    transcript = None
    transcript_path = config.TRANSCRIPTS_DIR / f"{episode_id}_transcript.txt"
    if transcript_path.exists():
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                transcript = f.read()
        except FileNotFoundError:
            pass

    # Extract metadata from rapport
    metadonnees = None
    if rapport:
        metadonnees = rapport.get("etapes", {}).get("metadonnees", {})

    result = {
        **episode,
        "script": script,
        "rapport": rapport,
        "cover_art": cover_art,
        "transcript": transcript,
        "metadonnees": metadonnees,
    }
    return jsonify(result)


@app.route("/api/episode/<episode_id>/debug")
def api_episode_debug(episode_id):
    """Diagnostic endpoint — montre l'état complet des données d'un épisode.

    Protégé par un header X-Debug-Key ou le paramètre ?debug_key=...
    pour éviter l'exposition accidentelle de données internes.
    """
    debug_key = os.getenv("DEBUG_KEY", "")
    if debug_key:
        provided = request.headers.get("X-Debug-Key") or request.args.get("debug_key", "")
        if provided != debug_key:
            return jsonify({"error": "Accès refusé — clé de debug requise."}), 403
    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format invalide"}), 400

    diag = {"episode_id": episode_id, "filesystem": {}, "db": {}, "rapport": {}}

    # 1. Filesystem
    script_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    diag["filesystem"]["script_valide"] = str(script_path)
    diag["filesystem"]["script_exists"] = script_path.exists()

    episodes_dir = config.OUTPUT_DIR
    diag["filesystem"]["output_dir"] = str(episodes_dir)
    diag["filesystem"]["output_dir_exists"] = episodes_dir.exists()
    if episodes_dir.exists():
        matching = [f.name for f in episodes_dir.glob(f"{episode_id}*")]
        diag["filesystem"]["matching_files"] = matching
    else:
        diag["filesystem"]["matching_files"] = []

    rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
    diag["filesystem"]["rapport_json"] = str(rapport_path)
    diag["filesystem"]["rapport_exists"] = rapport_path.exists()

    # 2. Database
    try:
        from database import get_cursor
        with get_cursor(commit=False) as cur:
            # Productions
            cur.execute(
                "SELECT id, status, etape_courante, started_at, completed_at, "
                "rapport_json IS NOT NULL AS has_rapport "
                "FROM productions WHERE episode_id = %s ORDER BY started_at DESC LIMIT 5",
                (episode_id,),
            )
            diag["db"]["productions"] = [
                {k: (str(v) if hasattr(v, 'isoformat') else v) for k, v in dict(r).items()}
                for r in cur.fetchall()
            ]

            # Scripts
            cur.execute(
                "SELECT id, version, is_validated, source, nb_mots, created_at "
                "FROM scripts WHERE episode_id = %s ORDER BY version DESC LIMIT 5",
                (episode_id,),
            )
            diag["db"]["scripts"] = [
                {k: (str(v) if hasattr(v, 'isoformat') else v) for k, v in dict(r).items()}
                for r in cur.fetchall()
            ]

            # Fichiers audio
            cur.execute(
                "SELECT id, type_fichier, chemin, duree_secondes, taille_bytes, created_at "
                "FROM fichiers_audio WHERE episode_id = %s ORDER BY created_at DESC LIMIT 10",
                (episode_id,),
            )
            diag["db"]["fichiers_audio"] = [
                {k: (str(v) if hasattr(v, 'isoformat') else v) for k, v in dict(r).items()}
                for r in cur.fetchall()
            ]

            # Historique
            cur.execute(
                "SELECT episode_id, titre, score_review, date_production "
                "FROM historique_episodes WHERE episode_id = %s",
                (episode_id,),
            )
            row = cur.fetchone()
            diag["db"]["historique"] = (
                {k: (str(v) if hasattr(v, 'isoformat') else v) for k, v in dict(row).items()}
                if row else None
            )
    except Exception as e:
        diag["db"]["error"] = str(e)

    # 3. Rapport (via dashboard_data)
    rapport = dashboard_data_mod.charger_rapport(episode_id)
    if rapport:
        diag["rapport"]["found"] = True
        etapes = rapport.get("etapes", {})
        diag["rapport"]["etapes_presentes"] = list(etapes.keys())
        montage = etapes.get("montage", {})
        diag["rapport"]["montage_chemin_hq"] = montage.get("chemin_hq")
        diag["rapport"]["montage_chemin_preview"] = montage.get("chemin_preview")
        diag["rapport"]["montage_duree"] = montage.get("duree_secondes")
        script_info = etapes.get("script", {})
        diag["rapport"]["script_chemin"] = script_info.get("chemin")
    else:
        diag["rapport"]["found"] = False

    return jsonify(diag)


@app.route("/api/episode/<episode_id>/script")
def api_episode_script(episode_id):
    """API JSON — Script complet d'un épisode (segments, personnages, tons)."""
    import json as _json

    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format d'identifiant invalide"}), 400

    script = None
    script_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    # Restaurer depuis Object Storage si absent (post-redéploiement)
    if not script_path.exists():
        try:
            import persistent_storage
            persistent_storage.restore_script(episode_id, config.SCRIPTS_DIR)
        except Exception:
            pass
    if script_path.exists():
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script = _json.load(f)
        except (ValueError, FileNotFoundError):
            pass
    if not script:
        try:
            from db_models import ScriptRepo
            db_script = ScriptRepo.charger_valide(episode_id)
            if db_script and db_script.get("episode"):
                script = db_script
            else:
                db_script = ScriptRepo.charger_derniere_version(episode_id)
                if db_script and db_script.get("episode"):
                    script = db_script
        except Exception as e:
            logger.warning("Échec chargement script DB pour %s : %s", episode_id, e)
    if not script:
        return jsonify({"error": f"Script introuvable pour {episode_id}"}), 404
    return jsonify(script)


@app.route("/api/episode/<episode_id>/validate", methods=["POST"])
def api_validate_episode(episode_id):
    """Valide une étape d'un épisode (script, montage, metadonnees, publication).

    Body JSON attendu:
        {"step": "script"|"montage"|"metadonnees", "action": "validate"|"reject", "comment": "..."}

    Pour la publication:
        {"step": "publication", "action": "publish"}
    """
    import json as _json

    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format d'identifiant invalide"}), 400

    # Vérifier que l'épisode n'a pas été supprimé
    if _is_episode_deleted(episode_id):
        return jsonify({"error": f"Épisode {episode_id} supprimé. Impossible de le valider."}), 410

    body = request.get_json(force=True)
    step = body.get("step", "").strip()
    action = body.get("action", "").strip()
    comment = body.get("comment", "").strip()

    valid_steps = ("script", "montage", "metadonnees")
    if step == "publication":
        return _handle_publication(episode_id, comment)

    if step not in valid_steps:
        return jsonify({"error": f"Étape invalide : {step}. Valeurs acceptées : {', '.join(valid_steps)}, publication"}), 400

    if action not in ("validate", "reject"):
        return jsonify({"error": "Action invalide. Valeurs acceptées : validate, reject"}), 400

    # Load, update, and save rapport (DB + file for resilience)
    rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
    try:
        # AUDIT-7: Charger le rapport existant — refuser si aucun (pas de rapport fantôme)
        rapport = dashboard_data_mod.charger_rapport(episode_id)
        if not rapport:
            return jsonify({
                "error": f"Aucun rapport trouvé pour {episode_id}. "
                         f"L'épisode doit d'abord être produit."
            }), 404

        with fichier_lock(rapport_path):
            # AUDIT-5: Re-charger le rapport SOUS le lock pour éviter les race conditions
            # (deux validations simultanées sur le même épisode ne s'écrasent plus)
            if rapport_path.exists():
                try:
                    with open(rapport_path, "r", encoding="utf-8") as f:
                        rapport = _json.load(f)
                except (ValueError, FileNotFoundError):
                    pass  # Garder le rapport chargé depuis la DB

            # Update validation status
            rapport.setdefault("etapes", {})
            rapport["etapes"].setdefault(step, {})
            rapport["etapes"][step]["validation_humaine"] = (action == "validate")
            rapport["etapes"][step]["validation_web"] = True
            rapport["etapes"][step]["validation_date"] = datetime.now().isoformat()

            if comment:
                rapport["etapes"][step]["commentaire_validation"] = comment

            # Log the decision
            rapport.setdefault("decisions_humaines", [])
            rapport["decisions_humaines"].append({
                "timestamp": datetime.now().isoformat(),
                "type": f"validation_{step}_web",
                "action": action,
                "commentaire": comment or "",
            })

            # Save rapport to file (local cache)
            with open(rapport_path, "w", encoding="utf-8") as f:
                _json.dump(rapport, f, ensure_ascii=False, indent=2)

        # Sync rapport to DB (survit aux redéploiements)
        _sync_rapport_to_db(episode_id, rapport)

        # Persister rapport en Object Storage (survit aux redéploiements Replit)
        try:
            import persistent_storage
            persistent_storage.upload_rapport(episode_id, rapport_path)
        except Exception as e:
            logger.debug("Object Storage indisponible pour rapport : %s", e)

        # Si validation du script → créer _valide.json, mettre à jour checkpoint, sync DB
        if step == "script" and action == "validate":
            # CRITICAL: Créer _valide.json à partir de _script.json
            # Le pipeline (reprendre) cherche _valide.json pour l'étape audio.
            # Sans ce fichier, il crash immédiatement avec FileNotFoundError.
            valide_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
            script_source = config.SCRIPTS_DIR / f"{episode_id}_script.json"

            # BUG #7: Restaurer le script depuis Object Storage si les fichiers
            # locaux sont absents (cas fréquent après redéploiement Replit).
            if not valide_path.exists() and not script_source.exists():
                try:
                    import persistent_storage
                    persistent_storage.restore_script(episode_id, config.SCRIPTS_DIR)
                    logger.info("Script restauré depuis Object Storage pour validation %s", episode_id)
                except Exception as e:
                    logger.debug("Restauration script Object Storage pour %s : %s", episode_id, e)
                # Fallback DB si Object Storage n'a rien restauré
                if not valide_path.exists() and not script_source.exists():
                    try:
                        from db_models import ScriptRepo
                        db_script = ScriptRepo.charger_valide(episode_id)
                        if not db_script or not db_script.get("episode"):
                            db_script = ScriptRepo.charger_derniere_version(episode_id)
                        if db_script and db_script.get("episode"):
                            config.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
                            with open(valide_path, "w", encoding="utf-8") as f:
                                _json.dump(db_script, f, ensure_ascii=False, indent=2)
                            logger.info("Script %s restauré depuis DB pour validation", episode_id)
                    except Exception as e:
                        logger.warning("Restauration script DB pour %s échouée : %s", episode_id, e)

            if not valide_path.exists() and script_source.exists():
                import shutil
                shutil.copy2(script_source, valide_path)
                logger.info("Script validé créé : %s → %s", script_source.name, valide_path.name)

            # CRITICAL: Mettre à jour validation_humaine dans le checkpoint
            # Le pipeline lit cette valeur depuis checkpoint_data.etapes.script
            checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"

            # BUG #6: Restaurer le checkpoint depuis Object Storage / DB si le
            # fichier local est absent (redéploiement Replit). Sans cela, le
            # checkpoint n'est jamais mis à jour avec validation_humaine=True,
            # et la publication sera bloquée plus tard.
            if not checkpoint_path.exists():
                try:
                    import persistent_storage
                    persistent_storage.restore_checkpoint(episode_id, config.CHECKPOINTS_DIR)
                    logger.info("Checkpoint restauré depuis Object Storage pour validation %s", episode_id)
                except Exception:
                    pass
            if not checkpoint_path.exists():
                _restore_checkpoint_from_db(episode_id, checkpoint_path)

            if checkpoint_path.exists():
                try:
                    with fichier_lock(checkpoint_path):
                        with open(checkpoint_path, "r", encoding="utf-8") as f:
                            cp = _json.load(f)
                        cp_data = cp.get("data", cp)
                        cp_rapport = cp_data.setdefault("rapport", {})
                        cp_rapport.setdefault("etapes", {}).setdefault("script", {})
                        cp_rapport["etapes"]["script"]["validation_humaine"] = True
                        # Stocker le hash du script validé pour détecter les changements
                        # Si le script est modifié après validation, le hash changera et
                        # la garde des segments dans main.py purgera les anciens audio.
                        _script_for_hash = None
                        if valide_path.exists():
                            try:
                                with open(valide_path, "r", encoding="utf-8") as sf:
                                    _script_for_hash = _json.load(sf)
                            except Exception:
                                pass
                        elif script_source.exists():
                            try:
                                with open(script_source, "r", encoding="utf-8") as sf:
                                    _script_for_hash = _json.load(sf)
                            except Exception:
                                pass
                        if _script_for_hash:
                            from utils import compute_script_hash
                            _script_hash = compute_script_hash(_script_for_hash)
                            cp_data["script_content_hash"] = _script_hash
                            cp_rapport["script_content_hash"] = _script_hash
                        with open(checkpoint_path, "w", encoding="utf-8") as f:
                            _json.dump(cp, f, ensure_ascii=False, indent=2)
                    logger.info("Checkpoint %s mis à jour : validation_humaine=True", episode_id)
                except Exception as cp_err:
                    logger.warning("Échec mise à jour checkpoint %s : %s", episode_id, cp_err)

            _sync_script_validated_to_db(episode_id)
            _sync_checkpoint_to_db(episode_id)
            # Upload script validé et checkpoint en Object Storage
            try:
                import persistent_storage
                if valide_path.exists():
                    persistent_storage.upload_script(episode_id, valide_path)
                checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
                if checkpoint_path.exists():
                    persistent_storage.upload_checkpoint(episode_id, checkpoint_path)
            except Exception as e:
                logger.debug("Object Storage indisponible pour script/checkpoint : %s", e)

    except OSError as e:
        return jsonify({"error": f"Erreur sauvegarde rapport : {e}"}), 500

    action_label = "validé" if action == "validate" else "rejeté"
    step_labels = {"script": "Script", "montage": "Montage", "metadonnees": "Métadonnées"}

    # Après validation du script → lancer automatiquement la production audio
    response = {
        "status": "ok",
        "message": f"{step_labels.get(step, step)} {action_label} pour {episode_id}.",
    }
    if step == "script" and action == "validate":
        # BUG #4: Vérifier que le checkpoint existe avant de proposer la suite
        # Restaurer depuis Object Storage / DB si nécessaire (après redéploiement)
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
        if not checkpoint_path.exists():
            try:
                import persistent_storage
                persistent_storage.restore_checkpoint(episode_id, config.CHECKPOINTS_DIR)
            except Exception:
                pass
        if not checkpoint_path.exists():
            _restore_checkpoint_from_db(episode_id, checkpoint_path)
        if checkpoint_path.exists():
            response["next_phase"] = "audio"
            response["message"] += " Lancez maintenant la production audio."
        else:
            response["message"] += " Checkpoint introuvable — relancez la production manuellement."
    elif step == "montage" and action == "validate":
        response["next_phase"] = "publication"
        response["message"] += " L'épisode est prêt pour la publication."

    return jsonify(response)


@app.route("/api/episode/<episode_id>/continue-production", methods=["POST"])
def api_continue_production(episode_id):
    """Continue la production d'un épisode après validation d'une étape.

    Appelé automatiquement après validation du script (lance audio→montage)
    ou après validation du montage (lance métadonnées→publication).

    Body JSON:
        {"phase": "audio"|"publication"}
    """
    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format d'identifiant invalide (attendu: S01E01)"}), 400

    body = request.get_json(force=True)
    phase = body.get("phase", "").strip()

    if phase not in ("audio", "montage", "publication"):
        return jsonify({"error": "Phase invalide. Valeurs acceptées : audio, montage, publication"}), 400

    # Vérifier qu'un checkpoint existe pour cet épisode
    # Si le fichier n'existe pas (redéploiement), restaurer depuis Object Storage ou DB
    checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
    if not checkpoint_path.exists():
        try:
            import persistent_storage
            persistent_storage.restore_checkpoint(episode_id, config.CHECKPOINTS_DIR)
        except Exception as e:
            logger.debug("continue-production: restore checkpoint Object Storage pour %s : %s", episode_id, e)
    if not checkpoint_path.exists():
        _restore_checkpoint_from_db(episode_id, checkpoint_path)
    if not checkpoint_path.exists():
        return jsonify({"error": f"Checkpoint introuvable pour {episode_id}. La production initiale doit d'abord être lancée."}), 404

    # ── FILET DE SÉCURITÉ : s'assurer que _valide.json existe AVANT le subprocess ──
    # Après un redeploy Replit, le filesystem est wipé. Le subprocess (reprendre)
    # cherche _valide.json mais ne le trouve pas → crash immédiat.
    if not _restore_valide_script(episode_id):
        return jsonify({
            "error": f"Script validé introuvable pour {episode_id}. "
                     f"Validez d'abord le script depuis le dashboard."
        }), 400

    if phase == "audio":
        # ── Auto-chaînage : audio → sfx → montage en 3 jobs courts ──
        # Chaque job dure ~10-15 min au lieu de ~40 min pour les 3 ensemble.
        # Cela permet de survivre aux recyclages container Replit (30-90 min).
        # Entre chaque job, un checkpoint est sauvé → reprise possible.

        def _chain_sfx_then_montage():
            """Lancé automatiquement après le job audio."""
            _restore_valide_script(episode_id)
            _cp = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
            if not _cp.exists():
                _restore_checkpoint_from_db(episode_id, _cp)
            if not _cp.exists():
                logger.warning("Chaînage sfx impossible : checkpoint %s introuvable", episode_id)
                return

            def _chain_montage():
                """Lancé automatiquement après le job SFX."""
                _restore_valide_script(episode_id)
                _cp2 = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
                if not _cp2.exists():
                    _restore_checkpoint_from_db(episode_id, _cp2)
                if not _cp2.exists():
                    logger.warning("Chaînage montage impossible : checkpoint %s introuvable", episode_id)
                    return
                cmd_montage = [
                    "reprendre", "-c", str(_cp2), "--auto",
                    "--stop-after", "montage",
                ]
                try:
                    _start_job(cmd_montage, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
                    logger.info("Auto-chaînage : montage lancé pour %s", episode_id)
                except ValueError:
                    logger.debug("Auto-chaînage montage ignoré (job déjà en cours) pour %s", episode_id)

            cmd_sfx = [
                "reprendre", "-c", str(_cp), "--auto",
                "--stop-after", "sfx",
            ]
            try:
                _start_job(
                    cmd_sfx, timeout=_TIMEOUT_PRODUIRE,
                    episode_id=episode_id, on_success_fn=_chain_montage,
                )
                logger.info("Auto-chaînage : SFX lancé pour %s", episode_id)
            except ValueError:
                logger.debug("Auto-chaînage SFX ignoré (job déjà en cours) pour %s", episode_id)

        cmd = [
            "reprendre",
            "-c", str(checkpoint_path),
            "--auto",
            "--stop-after", "audio",
        ]
        try:
            job_id = _start_job(
                cmd, timeout=_TIMEOUT_PRODUIRE,
                episode_id=episode_id, on_success_fn=_chain_sfx_then_montage,
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify({"status": "accepted", "job_id": job_id, "phase": "audio"})

    elif phase == "montage":
        # Re-montage uniquement : reprend depuis le checkpoint avec stop_after=montage
        # Utile quand les segments audio sont OK mais le montage doit être refait
        # (ex: changement monteur, suppression cold open, etc.)
        cmd = [
            "reprendre",
            "-c", str(checkpoint_path),
            "--auto",
            "--stop-after", "montage",
        ]
        try:
            job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify({"status": "accepted", "job_id": job_id, "phase": "montage"})

    elif phase == "publication":
        # C1: Injecter validation_humaine dans le checkpoint pour que
        # le pipeline en mode --auto détecte la validation web
        import json as _json
        try:
            with fichier_lock(checkpoint_path):
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    cp_data = _json.load(f)
                # BUG #5: S'assurer que data.rapport existe dans cp_data
                # (sinon .get({}) crée un dict détaché qui ne sera pas sauvé)
                cp_data.setdefault("data", {}).setdefault("rapport", {})
                rapport_cp = cp_data["data"]["rapport"]
                rapport_cp.setdefault("etapes", {}).setdefault("publication", {})
                rapport_cp["etapes"]["publication"]["validation_humaine"] = True
                with open(checkpoint_path, "w", encoding="utf-8") as f:
                    _json.dump(cp_data, f, ensure_ascii=False, indent=2)
        except (OSError, ValueError) as e:
            logger.warning("Impossible de mettre à jour le checkpoint pour publication: %s", e)

        # Reprendre depuis métadonnées jusqu'à la fin
        cmd = [
            "reprendre",
            "-c", str(checkpoint_path),
            "--auto",
        ]
        try:
            job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify({"status": "accepted", "job_id": job_id, "phase": "publication"})


@app.route("/api/episode/<episode_id>/kill-productions", methods=["POST"])
def api_kill_productions(episode_id):
    """Marque TOUTES les productions non-terminales d'un épisode comme 'failed'.

    Empêche l'auto-resume de relancer de vieilles productions après un redeploy.
    À appeler AVANT launch-fresh pour partir de zéro.
    """
    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format invalide"}), 400
    if not _DB_AVAILABLE:
        return jsonify({"status": "ok", "killed": 0, "message": "DB indisponible, pas de productions à tuer"})
    try:
        from db_models import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """UPDATE productions
                   SET status = 'failed', etape_courante = 'killed_by_api'
                   WHERE episode_id = %s
                     AND status NOT IN ('completed', 'failed')
                   RETURNING id""",
                (episode_id,),
            )
            killed = cur.rowcount
        return jsonify({"status": "ok", "killed": killed})
    except Exception as e:
        logger.warning("kill-productions %s : %s", episode_id, e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/episode/<episode_id>/launch-fresh", methods=["POST"])
def api_launch_fresh(episode_id):
    """Lance la production audio from scratch pour un script déjà validé.

    1. Vérifie que _script.json existe sur le filesystem (pushé via git)
    2. Copie _script.json → _valide.json
    3. Crée un checkpoint neuf (étape=audio, validation_humaine=true)
    4. Lance audio → SFX → montage en auto-chaînage

    Ne touche PAS au script. Ne régénère rien. Utilise tel quel ce qui est dans git.
    """
    import json as _json
    from datetime import datetime

    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format invalide"}), 400

    # Accepter le script dans le body OU lire depuis le filesystem
    script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"
    valide_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    import shutil

    body = request.get_json(silent=True) or {}
    script_from_body = body.get("script")

    if script_from_body:
        # Script envoyé directement dans le POST — source de vérité
        script = script_from_body
        config.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(script_path, "w", encoding="utf-8") as f:
            _json.dump(script, f, ensure_ascii=False, indent=2)
        with open(valide_path, "w", encoding="utf-8") as f:
            _json.dump(script, f, ensure_ascii=False, indent=2)
        # Upload vers Object Storage pour survivre aux redeploys
        try:
            import persistent_storage
            persistent_storage.upload_script(episode_id, script_path)
        except Exception:
            pass
        logger.info("launch-fresh %s : script reçu dans le body POST (source de vérité)", episode_id)
    elif script_path.exists():
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script = _json.load(f)
        except Exception as e:
            return jsonify({"error": f"Script illisible: {e}"}), 400
        shutil.copy2(script_path, valide_path)
    else:
        return jsonify({"error": f"Script introuvable: envoyez-le dans le body ou déployez d'abord"}), 404

    # Extraire les métadonnées
    try:
        ep = script.get("episode", {})
        titre = ep.get("titre", episode_id)
        segments = ep.get("segments", [])
        nb_segments = len(segments)
        nb_voix = len([s for s in segments if s.get("personnage") != "sfx"])
        nb_sfx = nb_segments - nb_voix
        logger.info("launch-fresh %s : %d segments (%d voix + %d SFX)", episode_id, nb_segments, nb_voix, nb_sfx)
    except Exception as e:
        return jsonify({"error": f"Script illisible: {e}"}), 400

    # Extraire saison/numéro depuis l'episode_id
    saison = int(episode_id[1:3])
    numero = int(episode_id[4:6])
    now = datetime.utcnow().isoformat()

    # Créer un checkpoint neuf à l'étape "audio"
    checkpoint_data = {
        "episode_id": episode_id,
        "etape": "audio",
        "timestamp": now,
        "data": {
            "episode_id": episode_id,
            "titre": titre,
            "resume": ep.get("morale", ""),
            "saison": saison,
            "numero": numero,
            "morale": ep.get("morale", ""),
            "type_episode": ep.get("type", "standard"),
            "dry_run": False,
            "rapport": {
                "episode_id": episode_id,
                "titre": titre,
                "dry_run": False,
                "debut": now,
                "etapes": {
                    "script": {
                        "status": "ok",
                        "script_path": str(valide_path),
                        "validation_humaine": True,
                        "nb_mots": sum(len(s.get("texte", "").split()) for s in ep.get("segments", []) if s.get("personnage") != "sfx"),
                        "nb_segments": nb_segments,
                    }
                },
                "decisions_humaines": [],
            },
            "script_path": str(valide_path),
            "pubdate_offset_seconds": numero * 3600,
            "stop_after": "",
        },
    }

    # Ajouter le hash du script pour la détection de modifications
    try:
        from utils import compute_script_hash
        script_hash = compute_script_hash(script)
        checkpoint_data["data"]["script_content_hash"] = script_hash
        checkpoint_data["data"]["rapport"]["script_content_hash"] = script_hash
    except Exception as e:
        logger.debug("launch-fresh %s : hash échoué: %s", episode_id, e)

    checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
    config.CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        _json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
    logger.info("launch-fresh %s : checkpoint créé à %s", episode_id, checkpoint_path)

    # Sauvegarder le script en DB pour visibilité dans la page validation
    try:
        from db_models import ScriptRepo
        nb_mots = sum(
            len(s.get("texte", "").split())
            for s in segments
            if s.get("personnage") != "sfx"
        )
        ScriptRepo.sauvegarder(
            episode_id=episode_id,
            script=script,
            nb_mots=nb_mots,
            is_validated=True,
            source="launch_fresh",
        )
        logger.info("launch-fresh %s : script sauvegardé en DB (%d mots)", episode_id, nb_mots)
    except Exception as e:
        logger.warning("launch-fresh %s : sauvegarde script DB échouée: %s", episode_id, e)

    # Upload checkpoint vers Object Storage (survit à un redeploy entre maintenant et le subprocess)
    try:
        import persistent_storage
        persistent_storage.upload_checkpoint(episode_id, checkpoint_path)
    except Exception as e:
        logger.warning("launch-fresh %s : upload checkpoint OS échoué: %s", episode_id, e)

    # CRITICAL: Purger TOUT l'Object Storage pour cet épisode
    # Sans ça, un redeploy restaure les ANCIENS fichiers audio/segments/wav par-dessus les nouveaux
    # C'est la cause de 6 échecs consécutifs où le mauvais audio était servi
    try:
        import persistent_storage as _ps
        if _ps.is_available():
            for prefix in [
                f"segments/{episode_id}/",
                f"audio/{episode_id}",          # audio/S01E01_*.mp3
                f"montage_wav/{episode_id}",     # WAV intermédiaires
                f"rapports/{episode_id}",        # anciens rapports
                f"checkpoints/{episode_id}",     # anciens checkpoints
                f"metadonnees/{episode_id}",     # anciennes métadonnées
                f"chapters/{episode_id}",        # anciens chapitres
            ]:
                _ps.delete_prefix(prefix)
            logger.info("launch-fresh %s : Object Storage intégralement purgé (7 préfixes)", episode_id)
    except Exception as e:
        logger.warning("launch-fresh %s : purge OS échouée: %s", episode_id, e)

    # Purger les fichiers locaux aussi
    segments_dir = config.OUTPUT_DIR / "segments" / episode_id
    if segments_dir.exists():
        shutil.rmtree(segments_dir, ignore_errors=True)
    # Purger les anciens MP3 locaux
    episodes_dir = config.OUTPUT_DIR / "episodes"
    if episodes_dir.exists():
        slug = episode_id.lower()
        for f in episodes_dir.glob(f"{episode_id}*"):
            f.unlink(missing_ok=True)
        for f in episodes_dir.glob(f"{slug}*"):
            f.unlink(missing_ok=True)
    logger.info("launch-fresh %s : fichiers locaux purgés", episode_id)

    # Lancer audio → SFX → montage (même chaînage que continue-production)
    def _chain_sfx_then_montage():
        _restore_valide_script(episode_id)
        _cp = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
        if not _cp.exists():
            _restore_checkpoint_from_db(episode_id, _cp)
        if not _cp.exists():
            logger.warning("launch-fresh chaînage sfx impossible : checkpoint %s introuvable", episode_id)
            return

        def _chain_montage():
            _restore_valide_script(episode_id)
            _cp2 = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
            if not _cp2.exists():
                _restore_checkpoint_from_db(episode_id, _cp2)
            if not _cp2.exists():
                logger.warning("launch-fresh chaînage montage impossible : checkpoint %s introuvable", episode_id)
                return
            cmd_montage = ["reprendre", "-c", str(_cp2), "--auto", "--stop-after", "montage"]
            try:
                _start_job(cmd_montage, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
                logger.info("launch-fresh : montage lancé pour %s", episode_id)
            except ValueError:
                logger.debug("launch-fresh montage ignoré (job déjà en cours) pour %s", episode_id)

        cmd_sfx = ["reprendre", "-c", str(_cp), "--auto", "--stop-after", "sfx"]
        try:
            _start_job(cmd_sfx, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id, on_success_fn=_chain_montage)
            logger.info("launch-fresh : SFX lancé pour %s", episode_id)
        except ValueError:
            logger.debug("launch-fresh SFX ignoré (job déjà en cours) pour %s", episode_id)

    cmd = ["reprendre", "-c", str(checkpoint_path), "--auto", "--stop-after", "audio"]
    try:
        job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id, on_success_fn=_chain_sfx_then_montage)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({
        "status": "accepted",
        "job_id": job_id,
        "phase": "audio→sfx→montage",
        "script": {
            "segments": nb_segments,
            "voix": nb_voix,
            "sfx": nb_sfx,
            "titre": titre,
        },
    })


@app.route("/api/episode/<episode_id>/regenerate", methods=["POST"])
def api_regenerate_episode(episode_id):
    """Relance une étape de production avec les instructions du producteur.

    Permet de modifier le script ou le montage en fournissant des corrections
    textuelles. L'étape est relancée et le résultat remplace le précédent.

    Body JSON:
        {"step": "script"|"montage", "instructions": "Rends le dialogue plus drôle..."}
    """
    import json as _json

    if not re.match(r'^S\d{2}E\d{2}$', episode_id):
        return jsonify({"error": "Format d'identifiant invalide (attendu: S01E01)"}), 400

    body = request.get_json(force=True)
    step = body.get("step", "").strip()
    instructions = body.get("instructions", "").strip()

    if step not in ("script", "montage"):
        return jsonify({"error": "Étape invalide. Valeurs acceptées : script, montage"}), 400
    if not instructions:
        return jsonify({"error": "Instructions requises pour la modification."}), 400

    if step == "script":
        # Sauvegarder les instructions pour le pipeline
        corrections_path = config.SCRIPTS_DIR / f"{episode_id}_web_corrections.txt"
        corrections_path.parent.mkdir(parents=True, exist_ok=True)
        corrections_path.write_text(instructions, encoding="utf-8")

        # Réinitialiser le flag de validation script dans le rapport (DB + fichier)
        rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
        rapport = dashboard_data_mod.charger_rapport(episode_id) or {}
        if rapport:
            try:
                rapport.get("etapes", {}).get("script", {}).pop("validation_humaine", None)
                rapport.setdefault("decisions_humaines", []).append({
                    "timestamp": datetime.now().isoformat(),
                    "type": "regeneration_script_web",
                    "instructions": instructions,
                })
                with fichier_lock(rapport_path):
                    with open(rapport_path, "w", encoding="utf-8") as f:
                        json.dump(rapport, f, ensure_ascii=False, indent=2)
                _sync_rapport_to_db(episode_id, rapport)
            except Exception as e:
                logger.warning("Erreur mise à jour rapport %s : %s", episode_id, e)

        # W3: Utiliser reprendre depuis le checkpoint pour éviter de créer
        # une nouvelle entrée production en DB (produire en crée une à chaque appel)
        # Restaurer checkpoint depuis Object Storage / DB si nécessaire
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
        if not checkpoint_path.exists():
            try:
                import persistent_storage
                persistent_storage.restore_checkpoint(episode_id, config.CHECKPOINTS_DIR)
            except Exception as e:
                logger.debug("regenerate: restore checkpoint Object Storage pour %s : %s", episode_id, e)
        if not checkpoint_path.exists():
            _restore_checkpoint_from_db(episode_id, checkpoint_path)
        if checkpoint_path.exists():
            try:
                with fichier_lock(checkpoint_path):
                    with open(checkpoint_path, "r", encoding="utf-8") as f:
                        cp = _json.load(f)
                    # B4: Ne modifier QUE l'étape, préserver toutes les données
                    cp["etape"] = "script"
                    with open(checkpoint_path, "w", encoding="utf-8") as f:
                        _json.dump(cp, f, ensure_ascii=False, indent=2)
            except Exception as e:
                corrections_path.unlink(missing_ok=True)
                return jsonify({"error": f"Erreur lecture checkpoint : {e}"}), 500

            cmd = [
                "reprendre",
                "-c", str(checkpoint_path),
                "--auto",
                "--stop-after", "script",
            ]
            try:
                job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
            except ValueError as e:
                return jsonify({"error": str(e)}), 409
            return jsonify({"status": "accepted", "job_id": job_id, "phase": "script"})

        # Fallback: pas de checkpoint, utiliser produire (première production)
        params = _load_episode_params(episode_id)
        if not params:
            corrections_path.unlink(missing_ok=True)
            return jsonify({"error": f"Paramètres introuvables pour {episode_id}. Relancez la production manuellement."}), 404

        cmd = [
            "produire",
            "-e", params["titre"],
            "-s", str(params["saison"]),
            "-n", str(params["numero"]),
            "-r", params["resume"],
            "-t", params.get("type_episode", "standard"),
            "--auto",
            "--stop-after", "script",
        ]
        if params.get("morale"):
            cmd.extend(["-m", params["morale"]])

        try:
            job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify({"status": "accepted", "job_id": job_id, "phase": "script"})

    elif step == "montage":
        # Relancer le montage depuis le checkpoint avec instructions
        # Si le fichier n'existe pas (redéploiement), restaurer depuis Object Storage ou DB
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
        if not checkpoint_path.exists():
            try:
                import persistent_storage
                persistent_storage.restore_checkpoint(episode_id, config.CHECKPOINTS_DIR)
            except Exception as e:
                logger.debug("regenerate montage: restore checkpoint Object Storage pour %s : %s", episode_id, e)
        if not checkpoint_path.exists():
            _restore_checkpoint_from_db(episode_id, checkpoint_path)
        if not checkpoint_path.exists():
            return jsonify({"error": f"Checkpoint introuvable pour {episode_id}. Relancez la production depuis le début."}), 404

        # Sauvegarder les instructions dans un fichier pour le pipeline
        montage_instructions_path = config.SCRIPTS_DIR / f"{episode_id}_montage_instructions.txt"
        montage_instructions_path.parent.mkdir(parents=True, exist_ok=True)
        montage_instructions_path.write_text(instructions, encoding="utf-8")

        # Sauvegarder les instructions dans le rapport (DB + fichier)
        rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
        rapport = dashboard_data_mod.charger_rapport(episode_id) or {}
        if rapport:
            try:
                montage_etape = rapport.get("etapes", {}).get("montage", {})
                montage_etape.pop("validation_humaine", None)
                # W7: Nettoyer les données de montage obsolètes
                for stale_key in ("chemin_hq", "chemin_preview", "duree_secondes",
                                  "taille_bytes", "chapitres", "object_storage"):
                    montage_etape.pop(stale_key, None)
                rapport.setdefault("decisions_humaines", []).append({
                    "timestamp": datetime.now().isoformat(),
                    "type": "regeneration_montage_web",
                    "instructions": instructions,
                })
                with fichier_lock(rapport_path):
                    with open(rapport_path, "w", encoding="utf-8") as f:
                        json.dump(rapport, f, ensure_ascii=False, indent=2)
                _sync_rapport_to_db(episode_id, rapport)
            except Exception as e:
                logger.warning("Erreur mise à jour rapport %s : %s", episode_id, e)

        # Filet de sécurité : restaurer _valide.json (le monteur charge le script)
        _restore_valide_script(episode_id)

        # Forcer la reprise depuis l'étape montage (pas audio — les segments existent déjà)
        try:
            with fichier_lock(checkpoint_path):
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    cp = _json.load(f)
                cp["etape"] = "montage"
                with open(checkpoint_path, "w", encoding="utf-8") as f:
                    _json.dump(cp, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return jsonify({"error": f"Erreur lecture checkpoint : {e}"}), 500

        cmd = [
            "reprendre",
            "-c", str(checkpoint_path),
            "--auto",
            "--stop-after", "montage",
        ]
        try:
            job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify({"status": "accepted", "job_id": job_id, "phase": "montage"})


def _load_episode_params(episode_id):
    """Charge les paramètres de production d'un épisode depuis le checkpoint ou le rapport."""
    import json as _json

    # 1. Essayer le checkpoint
    checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                cp = _json.load(f)
            data = cp.get("data", {})
            if data.get("titre"):
                return data
        except Exception as e:
            logger.warning("Échec lecture checkpoint %s : %s", episode_id, e)

    # 2. Essayer la DB (source fiable pour titre/resume)
    if _DB_AVAILABLE:
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT titre, resume, type_episode, morale "
                    "FROM episodes WHERE episode_id = %s LIMIT 1",
                    (episode_id,),
                )
                row = cur.fetchone()
            if row:
                m = re.match(r'S(\d+)E(\d+)', episode_id)
                return {
                    "titre": row["titre"],
                    "resume": row.get("resume", ""),
                    "saison": int(m.group(1)) if m else 1,
                    "numero": int(m.group(2)) if m else 1,
                    "morale": row.get("morale", ""),
                    "type_episode": row.get("type_episode", "standard"),
                }
        except Exception as e:
            logger.warning("Échec lecture DB pour params %s : %s", episode_id, e)

    # 3. Essayer le plan de saison
    m = re.match(r'S(\d+)E(\d+)', episode_id)
    if m:
        saison_num = int(m.group(1))
        episode_num = int(m.group(2))
        plan = config.charger_saison(saison_num)
        if plan:
            episodes_plan = plan.get("saison", {}).get("episodes", [])
            ep = next((e for e in episodes_plan if e.get("numero") == episode_num), None)
            if ep:
                return {
                    "titre": ep.get("titre", ""),
                    "resume": ep.get("resume", ep.get("histoire_biblique", "")),
                    "saison": saison_num,
                    "numero": episode_num,
                    "morale": ep.get("morale", ""),
                    "type_episode": ep.get("type", "standard"),
                }

    # BUG #7: Toujours logger quand les paramètres sont introuvables
    logger.warning(
        "Paramètres introuvables pour %s (checkpoint: %s, DB: %s)",
        episode_id, checkpoint_path.exists(), _DB_AVAILABLE,
    )
    return None


def _handle_publication(episode_id, comment=""):
    """Gère la publication d'un épisode validé via le web."""
    import json as _json

    # Check prerequisites: script AND montage must be validated
    rapport = dashboard_data_mod.charger_rapport(episode_id)
    if not rapport:
        return jsonify({"error": "Aucun rapport trouvé. L'épisode doit d'abord être produit."}), 400

    rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
    # B2: Lecture + écriture rapport sous file lock
    try:
        with fichier_lock(rapport_path):
            etapes = rapport.get("etapes", {})
            script_ok = etapes.get("script", {}).get("validation_humaine", False)
            montage_ok = etapes.get("montage", {}).get("validation_humaine", False)

            if not script_ok or not montage_ok:
                missing = []
                if not script_ok:
                    missing.append("script")
                if not montage_ok:
                    missing.append("montage")
                return jsonify({
                    "error": f"Publication bloquée : validation(s) manquante(s) — {', '.join(missing)}. "
                             f"Validez d'abord le script et le montage avant de publier.",
                }), 400

            rapport["etapes"].setdefault("publication", {})
            rapport["etapes"]["publication"]["validation_humaine"] = True
            rapport["etapes"]["publication"]["validation_web"] = True
            rapport["etapes"]["publication"]["validation_date"] = datetime.now().isoformat()

            rapport.setdefault("decisions_humaines", [])
            rapport["decisions_humaines"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "validation_publication_web",
                "action": "publish",
                "commentaire": comment or "",
            })

            with open(rapport_path, "w", encoding="utf-8") as f:
                json.dump(rapport, f, ensure_ascii=False, indent=2)
        _sync_rapport_to_db(episode_id, rapport)
    except (ValueError, FileNotFoundError):
        return jsonify({"error": "Rapport illisible."}), 500
    except OSError as e:
        return jsonify({"error": f"Erreur sauvegarde : {e}"}), 500

    return jsonify({
        "status": "ok",
        "message": f"Publication validée pour {episode_id}. L'épisode peut maintenant être publié.",
    })


@app.route("/api/episodes-a-valider")
def api_episodes_a_valider():
    """API JSON — Liste complète : en production + produits + planifiés.

    Fusionne trois sources (dans cet ordre de priorité) :
    1. Épisodes en cours de production (depuis table productions) — statut waiting_*
    2. Épisodes produits (depuis historique) — avec statut de validation
    3. Épisodes planifiés mais pas encore produits (depuis plans de saison)

    Tri : en production d'abord, puis produits (plus récent en premier), puis planifiés.
    """
    data = get_dashboard_data(0)
    episodes = []
    known_ids = set()

    # 1. Épisodes en cours de production (DB : productions avec status != completed/failed)
    #    Ces épisodes sont prioritaires car ils nécessitent une action immédiate
    if _DB_AVAILABLE:
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT episode_id, etape_courante, status, started_at, rapport_json "
                    "FROM productions "
                    "WHERE status NOT IN ('completed', 'failed') "
                    "ORDER BY started_at DESC"
                )
                in_prod_rows = cur.fetchall()
            for row in in_prod_rows:
                ep_id = row["episode_id"]
                if ep_id in known_ids:
                    continue
                known_ids.add(ep_id)
                rapport = row.get("rapport_json") or {}
                etapes = rapport.get("etapes", {})
                episodes.append({
                    "episode_id": ep_id,
                    "titre": rapport.get("titre", ep_id),
                    "type_episode": rapport.get("type_episode", "standard"),
                    "score": 0,
                    "ambiance": "",
                    "date": row["started_at"].isoformat() if hasattr(row["started_at"], "isoformat") else str(row.get("started_at", "")),
                    "morale": rapport.get("morale", ""),
                    "personnages": [],
                    "retours_humains": "",
                    "audio_preview": None,
                    "audio_hq": None,
                    "duree_secondes": None,
                    "taille_mb": None,
                    "validation_script": etapes.get("script", {}).get("validation_humaine", False),
                    "validation_montage": etapes.get("montage", {}).get("validation_humaine", False),
                    "audio_missing": False,
                    "needs_validation": True,
                    "has_audio": bool(etapes.get("montage", {}).get("chemin_hq")),
                    "status": "in_production",
                    "etape_courante": row.get("etape_courante", "script"),
                })
        except Exception as e:
            logger.debug("DB indisponible pour productions en cours : %s", e)

    # 2. Épisodes produits (depuis historique — plus récent en premier)
    for ep in data["episodes"]:
        ep_id = ep.get("episode_id", "")
        if ep_id in known_ids:
            continue
        known_ids.add(ep_id)
        needs_validation = (
            not ep.get("validation_script", False)
            or not ep.get("validation_montage", False)
        )
        episodes.append({
            **ep,
            "needs_validation": needs_validation,
            "has_audio": bool(ep.get("audio_preview") or ep.get("audio_hq")),
            "status": "produced",
        })

    # 3. Épisodes planifiés mais pas encore produits
    for num_saison in data.get("saisons_dispo", []):
        plan = config.charger_saison(num_saison)
        if not plan:
            continue
        saison_data = plan.get("saison", {})
        for ep_plan in saison_data.get("episodes", []):
            ep_id = f"S{num_saison:02d}E{ep_plan.get('numero', 0):02d}"
            if ep_id in known_ids:
                continue
            known_ids.add(ep_id)
            episodes.append({
                "episode_id": ep_id,
                "titre": ep_plan.get("titre", "?"),
                "type_episode": ep_plan.get("type", "standard"),
                "score": 0,
                "ambiance": ep_plan.get("ambiance", ""),
                "date": "",
                "morale": ep_plan.get("morale", ""),
                "personnages": ep_plan.get("personnages", []),
                "retours_humains": "",
                "audio_preview": None,
                "audio_hq": None,
                "duree_secondes": None,
                "taille_mb": None,
                "validation_script": False,
                "validation_montage": False,
                "audio_missing": False,
                "needs_validation": True,
                "has_audio": False,
                "status": "planned",
            })

    # Tri : en production d'abord, puis produits (déjà triés par date DESC),
    # puis planifiés par ID croissant
    _status_order = {"in_production": 0, "produced": 1, "planned": 2}
    episodes.sort(key=lambda e: (
        _status_order.get(e.get("status"), 9),
        "" if e.get("status") == "in_production" else (e.get("date", "") or ""),
        e.get("episode_id", ""),
    ))

    return jsonify(episodes)


@app.route("/audio/covers/<path:filename>")
def serve_cover_art(filename):
    """Sert les fichiers cover art des épisodes."""
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "Nom de fichier invalide"}), 400
    # SEC #1: Valider l'extension (images uniquement) et le chemin résolu
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        return jsonify({"error": "Type de fichier invalide"}), 400
    covers_dir = config.COVERS_DIR
    cover_path = (covers_dir / filename).resolve()
    if not str(cover_path).startswith(str(covers_dir.resolve())):
        return jsonify({"error": "Fichier hors du répertoire autorisé"}), 400
    if not cover_path.exists():
        return jsonify({"error": f"Cover introuvable : {filename}"}), 404
    mimetype = "image/png" if filename.endswith(".png") else "image/jpeg"
    return send_from_directory(str(covers_dir), filename, mimetype=mimetype)


# ── Route API — Annulation ───────────────────────────────────────────────────


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    """Annule la production en cours (termine tous les processus actifs)."""
    terminated = 0
    with _process_lock:
        for jid, proc in list(_job_processes.items()):
            if proc and proc.poll() is None:
                proc.terminate()
                terminated += 1
    if terminated:
        return jsonify({"status": "ok", "message": f"{terminated} production(s) annulee(s)."})
    return jsonify({"status": "ok", "message": "Aucune production en cours."})


# ── Routes API (JSON) — Actions (asynchrones) ─────────────────────────────


@app.route("/api/produire", methods=["POST"])
def api_produire():
    """Lance la production d'un episode (asynchrone)."""
    err = _check_api_key("ANTHROPIC_API_KEY")
    if err:
        return err
    body = request.get_json(force=True)
    titre = body.get("titre", "").strip()
    saison = body.get("saison", 1)
    numero = body.get("numero", 1)
    resume = body.get("resume", "").strip()
    morale = body.get("morale", "").strip()
    type_episode = body.get("type_episode", "standard")
    dry_run = body.get("dry_run", False)

    if not titre:
        return jsonify({"error": "Titre requis"}), 400
    if not resume:
        return jsonify({"error": "Resume requis"}), 400

    # SÉCURITÉ: bloquer si un script validé existe déjà
    episode_id = f"S{saison:02d}E{numero:02d}"
    script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"
    valide_path = config.SCRIPTS_DIR / f"{episode_id}_script_valide.json"
    if script_path.exists() or valide_path.exists():
        return jsonify({
            "error": f"Un script existe déjà pour {episode_id}. "
                     f"Utilisez /api/episode/{episode_id}/continue-production pour lancer l'audio, "
                     f"ou supprimez le script existant avant de régénérer."
        }), 409

    types_valides = ("standard", "ouverture", "mi-saison", "final", "bonus")
    if type_episode not in types_valides:
        type_episode = "standard"

    cmd = [
        "produire",
        "-e", titre,
        "-s", str(saison),
        "-n", str(numero),
        "-r", resume,
        "-t", type_episode,
        "--auto",
        "--stop-after", "script",
    ]
    if morale:
        cmd.extend(["-m", morale])
    if dry_run:
        cmd.append("--dry-run")

    try:
        job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"status": "accepted", "job_id": job_id, "phase": "script"})


@app.route("/api/planifier-saison", methods=["POST"])
def api_planifier_saison():
    """Planifie une saison complete (asynchrone)."""
    err = _check_api_key("ANTHROPIC_API_KEY")
    if err:
        return err
    body = request.get_json(force=True)
    saison = body.get("saison", 1)
    theme = body.get("theme", "").strip()
    description = body.get("description", "").strip()
    personnages = body.get("personnages", "").strip()
    nb_episodes = body.get("nb_episodes", 10)

    if not theme:
        return jsonify({"error": "Theme requis"}), 400

    cmd = [
        "planifier-saison",
        "-s", str(saison),
        "-t", theme,
        "-n", str(nb_episodes),
        "--auto",
    ]
    if description:
        cmd.extend(["-d", description])
    if personnages:
        cmd.extend(["-p", personnages])

    job_id = _start_job(cmd, timeout=_TIMEOUT_PLANIFIER)
    return jsonify({"status": "accepted", "job_id": job_id})


@app.route("/api/saison/<int:saison_num>/prochain-episode")
def api_prochain_episode(saison_num):
    """Retourne le prochain épisode à produire dans une saison.

    La production sérielle est séquentielle : on ne peut pas produire l'épisode N
    tant que l'épisode N-1 n'est pas terminé (script + audio validés, ou publié).
    """
    import json as _json

    plan = config.charger_saison(saison_num)
    if not plan:
        return jsonify({"error": f"Plan de saison {saison_num} introuvable."}), 404

    saison_data = plan.get("saison", {})
    episodes_plan = saison_data.get("episodes", [])
    if not episodes_plan:
        return jsonify({"error": "Le plan de saison ne contient aucun épisode."}), 400

    # Charger l'état de chaque épisode (DB + fichier + Object Storage)
    episodes_status = []
    for ep in sorted(episodes_plan, key=lambda e: e.get("numero", 0)):
        ep_id = f"S{saison_num:02d}E{ep['numero']:02d}"
        checkpoint_path = config.CHECKPOINTS_DIR / f"{ep_id}_checkpoint.json"

        status = "a_faire"  # Par défaut : pas encore commencé
        validation_script = False
        validation_montage = False

        # Info fichier script (date de dernière modification)
        script_path = config.SCRIPTS_DIR / f"{ep_id}_script.json"
        script_modifie = None
        if script_path.exists():
            import datetime as _dt
            mtime = script_path.stat().st_mtime
            script_modifie = _dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

        rapport = dashboard_data_mod.charger_rapport(ep_id)
        if rapport:
            etapes = rapport.get("etapes", {})
            validation_script = etapes.get("script", {}).get("validation_humaine", False)
            validation_montage = etapes.get("montage", {}).get("validation_humaine", False)
            pub = etapes.get("publication", {})

            if pub.get("validation_humaine") or rapport.get("status") == "completed":
                status = "termine"
            elif validation_montage:
                status = "montage_valide"
            elif validation_script:
                # Script validé : vérifier si audio est en cours/terminé
                if etapes.get("montage", {}).get("chemin_hq"):
                    status = "attente_validation_montage"
                else:
                    status = "script_valide"
            elif (etapes.get("script", {}).get("chemin")
                  or etapes.get("script", {}).get("script_path")
                  or rapport.get("status") in ("waiting_validation", "waiting_script")):
                # Script existe (produit ou rejeté) → en attente de validation
                # BUG #3: Après rejet, validation_humaine=False mais le script existe
                # toujours — l'utilisateur doit pouvoir le modifier/régénérer
                status = "attente_validation_script"
            else:
                status = "en_cours"
        elif checkpoint_path.exists():
            status = "en_cours"

        # Fallback : si le script existe sur le disque, c'est au moins attente_validation_script
        if status in ("a_faire", "en_cours") and script_path.exists():
            status = "attente_validation_script"

        episodes_status.append({
            "numero": ep["numero"],
            "episode_id": ep_id,
            "titre": ep.get("titre", ""),
            "type": ep.get("type", "standard"),
            "status": status,
            "validation_script": validation_script,
            "validation_montage": validation_montage,
            "script_modifie": script_modifie,
        })

    # Identifier tous les épisodes actionnables (pas de blocage séquentiel)
    STATUTS_PRETS = ("termine", "montage_valide")
    STATUTS_ACTIONNABLES = (
        "attente_validation_script", "script_valide",
        "attente_validation_montage", "a_faire",
    )
    actionnables = [
        ep_s for ep_s in episodes_status
        if ep_s["status"] in STATUTS_ACTIONNABLES
    ]
    # Rétrocompatibilité : prochain = premier actionnable, bloque_par toujours None
    prochain = actionnables[0] if actionnables else None

    return jsonify({
        "saison": saison_num,
        "theme": saison_data.get("theme", ""),
        "episodes": episodes_status,
        "prochain": prochain,
        "bloque_par": None,
        "actionnables": actionnables,
        "total": len(episodes_plan),
        "termines": sum(1 for e in episodes_status if e["status"] == "termine"),
    })


@app.route("/api/produire-saison", methods=["POST"])
def api_produire_saison():
    """Produit un épisode d'une saison (un seul à la fois).

    La production est libre : n'importe quel épisode dont le script est prêt
    peut être lancé en production audio, indépendamment de l'ordre.
    """
    err = _check_api_key("ANTHROPIC_API_KEY")
    if err:
        return err
    body = request.get_json(force=True)
    saison = body.get("saison", 1)
    numero = body.get("numero")  # Numéro spécifique de l'épisode à produire
    dry_run = body.get("dry_run", False)

    # Charger le plan de saison
    plan = config.charger_saison(saison)
    if not plan:
        return jsonify({"error": f"Plan de saison {saison} introuvable."}), 404

    saison_data = plan.get("saison", {})
    episodes_plan = saison_data.get("episodes", [])

    if not numero:
        return jsonify({"error": "Numéro d'épisode requis. Utilisez /api/saison/<n>/prochain-episode pour connaître le prochain."}), 400

    # Trouver l'épisode dans le plan
    ep = next((e for e in episodes_plan if e.get("numero") == numero), None)
    if not ep:
        return jsonify({"error": f"Épisode {numero} introuvable dans le plan de saison {saison}."}), 404

    episode_id = f"S{saison:02d}E{numero:02d}"

    # Produire l'épisode avec --stop-after script (workflow séquentiel)
    cmd = [
        "produire",
        "-e", ep.get("titre", ""),
        "-s", str(saison),
        "-n", str(numero),
        "-r", ep.get("resume", ep.get("histoire_biblique", "")),
        "-t", ep.get("type", "standard"),
        "--auto",
        "--stop-after", "script",
    ]
    if ep.get("morale"):
        cmd.extend(["-m", ep["morale"]])
    if dry_run:
        cmd.append("--dry-run")

    try:
        job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({
        "status": "accepted",
        "job_id": job_id,
        "episode_id": episode_id,
        "phase": "script",
        "message": f"Production du script de {episode_id} lancée.",
    })


@app.route("/api/reprendre", methods=["POST"])
def api_reprendre():
    """Reprend une production depuis un checkpoint (asynchrone)."""
    body = request.get_json(force=True)
    fichier = body.get("fichier", "").strip()

    if not fichier:
        return jsonify({"error": "Fichier checkpoint requis"}), 400

    # Security: only allow filenames, no path traversal
    if "/" in fichier or "\\" in fichier or ".." in fichier:
        return jsonify({"error": "Nom de fichier invalide"}), 400

    checkpoint_path = config.CHECKPOINTS_DIR / fichier
    if not checkpoint_path.exists():
        return jsonify({"error": f"Checkpoint introuvable : {fichier}"}), 404

    cmd = [
        "reprendre",
        "-c", str(checkpoint_path),
        "--auto",
    ]

    # Extraire l'episode_id du nom de fichier (S01E01_checkpoint.json)
    ep_id_match = re.match(r'^(S\d{2}E\d{2})_', fichier)
    ep_id = ep_id_match.group(1) if ep_id_match else None
    try:
        job_id = _start_job(cmd, timeout=_TIMEOUT_REPRENDRE, episode_id=ep_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"status": "accepted", "job_id": job_id})


@app.route("/api/batch", methods=["POST"])
def api_batch():
    """Lance une production batch depuis un JSON envoye par le client (asynchrone)."""
    import json as _json
    import tempfile

    body = request.get_json(force=True)
    episodes_list = body.get("episodes", [])
    dry_run = body.get("dry_run", False)

    if not episodes_list or not isinstance(episodes_list, list):
        return jsonify({"error": "Liste d'episodes requise (tableau JSON)"}), 400

    # Validate each episode has required fields and correct types
    for i, ep in enumerate(episodes_list):
        if not isinstance(ep, dict):
            return jsonify({"error": f"Episode {i+1} : doit etre un objet JSON"}), 400
        if not ep.get("titre"):
            return jsonify({"error": f"Episode {i+1} : titre requis"}), 400
        if not ep.get("resume"):
            return jsonify({"error": f"Episode {i+1} : resume requis"}), 400
        # Normaliser saison/numero en entiers
        for field in ("saison", "numero"):
            if field in ep:
                try:
                    ep[field] = int(ep[field])
                except (ValueError, TypeError):
                    return jsonify({"error": f"Episode {i+1} : {field} doit etre un entier"}), 400

    # Write to temp file, pass to CLI
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(_THIS_DIR), delete=False
    ) as tmp:
        _json.dump(episodes_list, tmp, ensure_ascii=False)
        tmp_path = tmp.name

    def _cleanup():
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    cmd = ["batch", "-f", tmp_path, "--auto"]
    if dry_run:
        cmd.append("--dry-run")

    job_id = _start_job(cmd, timeout=_TIMEOUT_BATCH, cleanup_fn=_cleanup)
    return jsonify({"status": "accepted", "job_id": job_id})


# ── Initialisation au chargement du module ──────────────────────────────────
# Important : cette initialisation doit se faire au niveau module pour que
# gunicorn/Replit l'execute aussi (pas seulement __main__).
_init_db_if_available()


# ── Reprise automatique après redéploiement (SIGTERM) ─────────────────────────

def _auto_resume_interrupted():
    """Reprend automatiquement les productions interrompues par un SIGTERM.

    Après un redéploiement Replit, les productions en cours sont tuées.
    Le handler SIGTERM dans main.py les marque 'interrupted' en DB.
    Mais si le handler échoue (DB down), le status reste à '{etape}_done'
    ou 'started'. Ce thread détecte TOUS les cas et relance.

    Statuts possibles d'une production interrompue :
    - 'interrupted' : SIGTERM handler a réussi l'UPDATE
    - 'started' : production créée mais jamais passée à l'étape suivante
    - '*_done' : SIGTERM a tué le process APRÈS un checkpoint mais AVANT
      que le handler ne puisse marquer 'interrupted' (DB down, SIGKILL, etc.)
    """
    if not _DB_AVAILABLE:
        return

    # Retry avec backoff exponentiel — la DB peut être en cold start (Neon)
    import json as _json
    rows = None
    for db_attempt in range(4):
        wait = [5, 8, 12, 20][db_attempt]
        time.sleep(wait)
        try:
            from db_models import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    """SELECT episode_id, etape_courante, checkpoint_data, status
                       FROM productions
                       WHERE status NOT IN ('completed', 'failed',
                                            'waiting_script', 'waiting_montage')
                         AND started_at > NOW() - INTERVAL '2 hours'
                         AND updated_at < NOW() - INTERVAL '2 minutes'
                       ORDER BY started_at DESC LIMIT 5""",
                )
                rows = cur.fetchall()
            break  # DB OK
        except Exception as e:
            logger.warning(
                "Auto-resume DB tentative %d/4 échouée : %s", db_attempt + 1, e,
            )

    if rows is None:
        logger.error("Auto-resume abandonné — DB inaccessible après 4 tentatives")
        return

    if not rows:
        logger.debug("Aucune production interrompue à reprendre")
        return

    for row in rows:
        episode_id = row["episode_id"]
        status = row["status"]

        # Vérifier qu'aucun job n'est déjà en cours en mémoire pour cet épisode
        with _jobs_lock:
            already_running = any(
                j.get("episode_id") == episode_id and j["status"] == "running"
                for j in _jobs.values()
            )
        if already_running:
            continue

        # Restaurer le checkpoint depuis la DB (le fichier local est perdu après redeploy)
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
        # Toujours restaurer depuis la DB — le fichier local peut être corrompu ou périmé
        _restore_checkpoint_from_db(episode_id, checkpoint_path)
        # Vérifier que le fichier est lisible
        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    cp = _json.load(f)
                # Vérifier les champs obligatoires
                if "etape" not in cp or "data" not in cp:
                    raise ValueError("Enveloppe checkpoint incomplète")
            except (ValueError, _json.JSONDecodeError) as e:
                logger.warning(
                    "Checkpoint corrompu pour %s (%s), re-restauration depuis DB", episode_id, e,
                )
                checkpoint_path.unlink(missing_ok=True)
                _restore_checkpoint_from_db(episode_id, checkpoint_path)

        if not checkpoint_path.exists():
            logger.warning("Checkpoint introuvable pour %s — impossible de reprendre", episode_id)
            continue

        # Lire le stop_after du checkpoint pour respecter le workflow original
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                cp = _json.load(f)
            stop_after = cp.get("data", {}).get("stop_after", "")
        except Exception:
            stop_after = ""

        # Construire la commande de reprise
        cmd = ["reprendre", "-c", str(checkpoint_path), "--auto"]
        if stop_after:
            cmd.extend(["--stop-after", stop_after])

        try:
            job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE, episode_id=episode_id)
            logger.info(
                "Auto-reprise de %s (status=%s, étape=%s) → job %s",
                episode_id, status, row["etape_courante"], job_id,
            )
        except ValueError as e:
            logger.debug("Auto-reprise ignorée pour %s : %s", episode_id, e)
        except Exception as e:
            logger.warning("Erreur auto-reprise pour %s : %s", episode_id, e)


# Lancer la reprise automatique dans un thread daemon
threading.Thread(target=_auto_resume_interrupted, daemon=True, name="auto-resume").start()


# ── API Claude Code (accès DB distant via Bearer token) ─────────────────────

_CLAUDE_ALLOWED_TABLES = frozenset({
    "productions", "scripts", "fichiers_audio", "saisons",
    "historique_episodes", "episodes", "audit_log",
})

_CLAUDE_SAFE_OPS = frozenset({"SELECT"})
_CLAUDE_WRITE_OPS = frozenset({"UPDATE", "INSERT", "DELETE"})


@app.route("/api/claude/status")
def api_claude_db_status():
    """Vérifie la connexion DB et retourne les tables disponibles."""
    if not _DB_AVAILABLE:
        return jsonify({"ok": False, "error": "DATABASE_URL non configurée"}), 503
    try:
        with database.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name"
                )
                tables = [r[0] for r in cur.fetchall()]
        return jsonify({"ok": True, "tables": tables})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude/query", methods=["POST"])
def api_claude_query():
    """Exécute une requête SELECT (lecture seule) et retourne les résultats en JSON.

    Body JSON: {"sql": "SELECT ...", "params": [...]}
    Limite automatique à 200 lignes.
    """
    if not _DB_AVAILABLE:
        return jsonify({"error": "DATABASE_URL non configurée"}), 503

    data = request.get_json(silent=True) or {}
    sql = (data.get("sql") or "").strip()
    params = data.get("params") or []

    if not sql:
        return jsonify({"error": "Champ 'sql' requis"}), 400

    # Sécurité : seules les requêtes SELECT sont autorisées
    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word not in _CLAUDE_SAFE_OPS:
        return jsonify({"error": f"Seules les requêtes SELECT sont autorisées (reçu: {first_word})"}), 403

    # Limite automatique
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 200"

    try:
        with database.get_conn() as conn:
            with conn.cursor(cursor_factory=database.psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description] if cur.description else []
        # Sérialiser les types non-JSON (datetime, etc.)
        result = []
        for row in rows:
            result.append({k: _serialize_value(v) for k, v in row.items()})
        return jsonify({"ok": True, "columns": columns, "rows": result, "count": len(result)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude/execute", methods=["POST"])
def api_claude_execute():
    """Exécute une requête d'écriture (UPDATE, INSERT, DELETE).

    Body JSON: {"sql": "UPDATE ...", "params": [...]}
    Requiert confirmation: {"confirm": true}
    """
    if not _DB_AVAILABLE:
        return jsonify({"error": "DATABASE_URL non configurée"}), 503

    data = request.get_json(silent=True) or {}
    sql = (data.get("sql") or "").strip()
    params = data.get("params") or []
    confirm = data.get("confirm", False)

    if not sql:
        return jsonify({"error": "Champ 'sql' requis"}), 400

    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word not in _CLAUDE_WRITE_OPS:
        return jsonify({"error": f"Opérations autorisées: UPDATE, INSERT, DELETE (reçu: {first_word})"}), 403

    # Protection contre DROP, TRUNCATE, ALTER injectés
    sql_upper = sql.upper()
    for forbidden in ("DROP ", "TRUNCATE ", "ALTER ", "CREATE ", "GRANT ", "REVOKE "):
        if forbidden in sql_upper:
            return jsonify({"error": f"Opération interdite: {forbidden.strip()}"}), 403

    if not confirm:
        return jsonify({
            "warning": "Requête d'écriture détectée. Renvoyez avec confirm=true pour exécuter.",
            "sql": sql,
            "params": params,
        }), 200

    try:
        with database.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                affected = cur.rowcount
            conn.commit()
        return jsonify({"ok": True, "rows_affected": affected})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude/table/<table_name>")
def api_claude_table_info(table_name):
    """Retourne le schéma d'une table (colonnes, types) + les 10 dernières lignes."""
    if not _DB_AVAILABLE:
        return jsonify({"error": "DATABASE_URL non configurée"}), 503

    if table_name not in _CLAUDE_ALLOWED_TABLES:
        return jsonify({"error": f"Table non autorisée. Tables: {sorted(_CLAUDE_ALLOWED_TABLES)}"}), 403

    try:
        with database.get_conn() as conn:
            with conn.cursor(cursor_factory=database.psycopg2.extras.RealDictCursor) as cur:
                # Schéma
                cur.execute(
                    "SELECT column_name, data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s "
                    "ORDER BY ordinal_position",
                    (table_name,)
                )
                columns = [dict(r) for r in cur.fetchall()]

                # Count
                cur.execute(f'SELECT COUNT(*) AS total FROM "{table_name}"')
                total = cur.fetchone()["total"]

                # Sample (10 dernières lignes)
                # Trouver la colonne de tri
                sort_col = None
                for c in columns:
                    if c["column_name"] in ("updated_at", "started_at", "created_at", "date_production"):
                        sort_col = c["column_name"]
                        break
                if sort_col:
                    cur.execute(f'SELECT * FROM "{table_name}" ORDER BY "{sort_col}" DESC LIMIT 10')
                else:
                    cur.execute(f'SELECT * FROM "{table_name}" LIMIT 10')
                sample = [
                    {k: _serialize_value(v) for k, v in row.items()}
                    for row in cur.fetchall()
                ]

        return jsonify({
            "ok": True,
            "table": table_name,
            "columns": columns,
            "total_rows": total,
            "sample": sample,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude/productions")
def api_claude_productions():
    """Vue synthétique des productions récentes."""
    if not _DB_AVAILABLE:
        return jsonify({"error": "DATABASE_URL non configurée"}), 503

    try:
        with database.get_conn() as conn:
            with conn.cursor(cursor_factory=database.psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, episode_id, status, etape_courante,
                           started_at, updated_at, completed_at,
                           dry_run, web_job_id
                    FROM productions
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 30
                """)
                rows = [
                    {k: _serialize_value(v) for k, v in row.items()}
                    for row in cur.fetchall()
                ]
        return jsonify({"ok": True, "productions": rows, "count": len(rows)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude/episodes")
def api_claude_episodes():
    """Vue synthétique des épisodes en base."""
    if not _DB_AVAILABLE:
        return jsonify({"error": "DATABASE_URL non configurée"}), 503

    try:
        with database.get_conn() as conn:
            with conn.cursor(cursor_factory=database.psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT episode_id, titre, type_episode,
                           score_review, date_production,
                           morale, ambiance, resume_court
                    FROM historique_episodes
                    ORDER BY episode_id
                """)
                rows = [
                    {k: _serialize_value(v) for k, v in row.items()}
                    for row in cur.fetchall()
                ]
        return jsonify({"ok": True, "episodes": rows, "count": len(rows)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude/upload", methods=["POST"])
def api_claude_upload():
    """Upload un fichier (cover art, script JSON) en base64.

    Body JSON: {
        "path": "assets/covers/S01E01_cover.png",  // chemin relatif depuis le projet
        "content_base64": "iVBORw0KGgo...",          // contenu encodé en base64
        "overwrite": true                              // optionnel, défaut false
    }

    Chemins autorisés: assets/covers/, scripts/episodes/, data/
    """
    import base64

    data = request.get_json(silent=True) or {}
    rel_path = (data.get("path") or "").strip()
    content_b64 = data.get("content_base64", "")
    overwrite = data.get("overwrite", False)

    if not rel_path or not content_b64:
        return jsonify({"error": "Champs 'path' et 'content_base64' requis"}), 400

    # Sécurité : seuls certains répertoires sont autorisés
    _ALLOWED_PREFIXES = ("assets/covers/", "scripts/episodes/", "data/",
                         "checkpoints/", "logs/")
    if not any(rel_path.startswith(p) for p in _ALLOWED_PREFIXES):
        return jsonify({
            "error": f"Chemin non autorisé. Préfixes autorisés: {_ALLOWED_PREFIXES}"
        }), 403

    # Protection path traversal
    target = (_THIS_DIR / rel_path).resolve()
    if not str(target).startswith(str(_THIS_DIR)):
        return jsonify({"error": "Path traversal interdit"}), 403

    if target.exists() and not overwrite:
        return jsonify({
            "error": f"Le fichier existe déjà. Utilisez overwrite=true pour remplacer.",
            "existing_size": target.stat().st_size,
        }), 409

    try:
        content = base64.b64decode(content_b64)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        logger.info("Claude API upload: %s (%d bytes)", rel_path, len(content))
        return jsonify({
            "ok": True,
            "path": rel_path,
            "size": len(content),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude/download/<path:rel_path>")
def api_claude_download(rel_path):
    """Télécharge un fichier du projet en base64.

    Retourne: {"ok": true, "path": "...", "content_base64": "...", "size": 123}
    """
    import base64

    _ALLOWED_PREFIXES = ("assets/covers/", "scripts/episodes/", "data/",
                         "checkpoints/", "logs/", "output/")
    if not any(rel_path.startswith(p) for p in _ALLOWED_PREFIXES):
        return jsonify({
            "error": f"Chemin non autorisé. Préfixes autorisés: {_ALLOWED_PREFIXES}"
        }), 403

    target = (_THIS_DIR / rel_path).resolve()
    if not str(target).startswith(str(_THIS_DIR)):
        return jsonify({"error": "Path traversal interdit"}), 403

    if not target.exists():
        return jsonify({"error": "Fichier introuvable"}), 404

    # Limite à 10 MB
    size = target.stat().st_size
    if size > 10 * 1024 * 1024:
        return jsonify({"error": f"Fichier trop volumineux ({size} bytes, max 10 MB)"}), 413

    try:
        content = target.read_bytes()
        return jsonify({
            "ok": True,
            "path": rel_path,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "size": size,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude/files/<path:rel_dir>")
def api_claude_list_files(rel_dir):
    """Liste les fichiers dans un répertoire du projet.

    Retourne: {"ok": true, "files": [{"name": "...", "size": 123, "modified": "..."}]}
    """
    _ALLOWED_PREFIXES = ("assets/covers/", "scripts/episodes/", "data/",
                         "checkpoints/", "logs/", "output/")
    if not any(rel_dir.startswith(p) for p in _ALLOWED_PREFIXES):
        return jsonify({
            "error": f"Répertoire non autorisé. Préfixes autorisés: {_ALLOWED_PREFIXES}"
        }), 403

    target = (_THIS_DIR / rel_dir).resolve()
    if not str(target).startswith(str(_THIS_DIR)):
        return jsonify({"error": "Path traversal interdit"}), 403

    if not target.is_dir():
        return jsonify({"error": "Répertoire introuvable"}), 404

    files = []
    for f in sorted(target.iterdir()):
        if f.is_file():
            st = f.stat()
            files.append({
                "name": f.name,
                "size": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
            })
    return jsonify({"ok": True, "directory": rel_dir, "files": files})


def _serialize_value(v):
    """Convertit les types Python non-JSON en string."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v)


# ══════════════════════════════════════════════════════════════════════════════
# ── BACK-OFFICE V2 — Routes API granulaires ─────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# Import V2 repos
try:
    from db_models import SegmentAudioRepo, MontageRepo
except ImportError:
    SegmentAudioRepo = None
    MontageRepo = None

try:
    import persistent_storage as ps
except ImportError:
    ps = None


def _start_fn_job(fn, episode_id=None):
    """Lance une fonction Python en background thread (pattern V2 — pas de subprocess).

    Returns:
        job_id (str)

    Raises:
        ValueError si un job tourne déjà pour cet épisode.
    """
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _gc_expired_jobs()
        if episode_id:
            for ej in _jobs.values():
                if ej.get("episode_id") == episode_id and ej["status"] == "running":
                    raise ValueError(f"Un job est déjà en cours pour {episode_id}")
        _jobs[job_id] = {
            "status": "running", "result": None,
            "created_at": time.monotonic(), "episode_id": episode_id,
        }

    def _worker():
        try:
            result = fn()
            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "done",
                    "result": {"status": "ok", **(result or {})},
                    "created_at": time.monotonic(),
                }
        except Exception as e:
            logger.exception("Job V2 %s échoué: %s", job_id, e)
            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "done",
                    "result": {"status": "error", "error": str(e)},
                    "created_at": time.monotonic(),
                }

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


# ── V2 : Scripts ─────────────────────────────────────────────────────────────


@app.route("/api/v2/episode/<episode_id>/push-script", methods=["POST"])
def api_v2_push_script(episode_id):
    """Push un script JSON depuis Claude Code. Crée les segments_audio."""
    data = request.get_json(silent=True) or {}
    script = data.get("script")
    if not script:
        return jsonify({"error": "Champ 'script' requis"}), 400

    segments = script.get("episode", {}).get("segments", [])
    if not segments:
        return jsonify({"error": "Script sans segments"}), 400

    # Sauvegarder le script sur le filesystem
    # IMPORTANT: pipeline expects _valide.json (NOT _script_valide.json)
    script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"
    valide_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    config.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    script_text = json.dumps(script, ensure_ascii=False, indent=2)
    for p in (script_path, valide_path):
        p.write_text(script_text, encoding="utf-8")
    # Also write _script_valide.json for backward compat (CLAUDE.md sync rule)
    compat_path = config.SCRIPTS_DIR / f"{episode_id}_script_valide.json"
    compat_path.write_text(script_text, encoding="utf-8")

    # Upload Object Storage
    if ps and ps.is_available():
        try:
            ps.upload_script(episode_id, script_path)
        except Exception as e:
            logger.warning("Upload script OS échoué: %s", e)

    # Sauvegarder en DB
    if _DB_AVAILABLE:
        try:
            from db_models import ScriptRepo
            ScriptRepo.sauvegarder(episode_id, script)
        except Exception as e:
            logger.warning("Sauvegarde script DB échouée: %s", e)

    # Créer les segments_audio
    nb_created = 0
    if _DB_AVAILABLE and SegmentAudioRepo:
        try:
            nb_created = SegmentAudioRepo.creer_depuis_script(episode_id, script)
        except Exception as e:
            logger.warning("Création segments_audio échouée: %s", e)

    # Stats
    voix = [s for s in segments if s.get("personnage") != "sfx"]
    sfx = [s for s in segments if s.get("personnage") == "sfx"]
    nb_mots = sum(len(s.get("texte", "").split()) for s in voix)

    return jsonify({
        "ok": True,
        "episode_id": episode_id,
        "nb_segments": len(segments),
        "nb_voix": len(voix),
        "nb_sfx": len(sfx),
        "nb_mots": nb_mots,
        "segments_db": nb_created,
    })


@app.route("/api/v2/episode/<episode_id>/script")
def api_v2_get_script(episode_id):
    """Retourne le script avec stats.

    Priority: filesystem -> DB (ScriptRepo) -> Object Storage -> 404.
    """
    script = None
    script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"

    # 1. Try filesystem
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Erreur lecture script %s: %s", episode_id, e)

    # 2. Fallback: DB (charger_valide returns the script dict directly, or {})
    if script is None and _DB_AVAILABLE:
        try:
            from db_models import ScriptRepo
            db_script = ScriptRepo.charger_valide(episode_id)
            if not db_script or not db_script.get("episode"):
                db_script = ScriptRepo.charger_derniere_version(episode_id)
            if db_script and db_script.get("episode"):
                script = db_script
                # Restore to filesystem for next time
                try:
                    config.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
                    script_path.write_text(
                        json.dumps(script, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Erreur lecture script DB %s: %s", episode_id, e)

    # 3. Fallback: Object Storage
    if script is None:
        try:
            if ps and ps.is_available():
                restored = ps.restore_script(episode_id, config.SCRIPTS_DIR)
                if restored and script_path.exists():
                    script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Erreur restore script OS %s: %s", episode_id, e)

    if script is None:
        return jsonify({"error": "Script non trouvé"}), 404
    segments = script.get("episode", {}).get("segments", [])
    voix = [s for s in segments if s.get("personnage") != "sfx"]
    sfx = [s for s in segments if s.get("personnage") == "sfx"]

    # Ratios personnages
    ratios = {}
    for s in voix:
        p = s.get("personnage", "inconnu")
        ratios[p] = ratios.get(p, 0) + 1
    total_voix = len(voix)
    ratios_pct = {p: round(c / total_voix * 100, 1) for p, c in ratios.items()} if total_voix else {}

    # Vérifier si validé
    validated = False
    if _DB_AVAILABLE and SegmentAudioRepo:
        try:
            segs = SegmentAudioRepo.lister(episode_id)
            validated = len(segs) > 0
        except Exception:
            pass

    return jsonify({
        "script": script,
        "stats": {
            "nb_segments": len(segments),
            "nb_voix": total_voix,
            "nb_sfx": len(sfx),
            "nb_mots": sum(len(s.get("texte", "").split()) for s in voix),
            "ratios": ratios_pct,
        },
        "validated": validated,
    })


@app.route("/api/v2/episode/<episode_id>/validate-script", methods=["POST"])
def api_v2_validate_script(episode_id):
    """Valide le script (prérequis pour lancer la génération audio)."""
    script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"
    if not script_path.exists():
        return jsonify({"error": "Script non trouvé"}), 404

    # S'assurer que les segments existent en DB
    if _DB_AVAILABLE and SegmentAudioRepo:
        segs = SegmentAudioRepo.lister(episode_id)
        if not segs:
            # Créer les segments si pas encore fait
            script = json.loads(script_path.read_text(encoding="utf-8"))
            SegmentAudioRepo.creer_depuis_script(episode_id, script)

    return jsonify({"ok": True, "validated_at": datetime.utcnow().isoformat()})


@app.route("/api/v2/episode/<episode_id>/scripts")
def api_v2_list_scripts(episode_id):
    """Liste toutes les versions de script d'un episode (metadata only, pas le contenu)."""
    if not _DB_AVAILABLE:
        return jsonify({"error": "DB non disponible"}), 503

    try:
        from db_models import ScriptRepo
        versions = ScriptRepo.historique(episode_id)
    except Exception as e:
        logger.warning("Erreur lecture historique scripts %s: %s", episode_id, e)
        return jsonify({"error": "Erreur DB"}), 500

    # Serialiser les datetimes
    for v in versions:
        if v.get("created_at"):
            v["created_at"] = v["created_at"].isoformat() if hasattr(v["created_at"], "isoformat") else str(v["created_at"])

    return jsonify(versions)


@app.route("/api/v2/episode/<episode_id>/script/<int:version>/validate", methods=["POST"])
def api_v2_validate_script_version(episode_id, version):
    """Valide une version specifique du script et l'active pour la production."""
    if not _DB_AVAILABLE:
        return jsonify({"error": "DB non disponible"}), 503

    try:
        from db_models import ScriptRepo

        # Valider la version en DB
        ok = ScriptRepo.valider(episode_id, version)
        if not ok:
            return jsonify({"error": f"Version {version} non trouvee pour {episode_id}"}), 404

        # Charger le script valide et ecrire sur le filesystem
        script = ScriptRepo.charger_valide(episode_id)
        if script and script.get("episode"):
            config.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            script_text = json.dumps(script, ensure_ascii=False, indent=2)
            for suffix in ("_script.json", "_valide.json", "_script_valide.json"):
                p = config.SCRIPTS_DIR / f"{episode_id}{suffix}"
                p.write_text(script_text, encoding="utf-8")

            # Upload Object Storage
            if ps and ps.is_available():
                try:
                    ps.upload_script(episode_id, config.SCRIPTS_DIR / f"{episode_id}_script.json")
                except Exception as e:
                    logger.warning("Upload script OS echoue: %s", e)

            # Recreer les segments_audio pour la nouvelle version
            if SegmentAudioRepo:
                try:
                    SegmentAudioRepo.creer_depuis_script(episode_id, script)
                except Exception as e:
                    logger.warning("Recreation segments_audio echouee: %s", e)

    except Exception as e:
        logger.warning("Erreur validation script %s v%d: %s", episode_id, version, e)
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True, "version": version, "validated_at": datetime.utcnow().isoformat()})


# ── V2 : Audio — Génération ──────────────────────────────────────────────────


@app.route("/api/v2/episode/<episode_id>/generate-audio", methods=["POST"])
def api_v2_generate_audio(episode_id):
    """Lance la génération TTS/SFX de tous les segments pending (job async)."""
    script_path = config.SCRIPTS_DIR / f"{episode_id}_script_valide.json"
    if not script_path.exists():
        script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"
    if not script_path.exists():
        return jsonify({"error": "Script non trouvé"}), 404

    def _job():
        return _job_generate_audio(episode_id, script_path)

    try:
        job_id = _start_fn_job(_job, episode_id=episode_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"job_id": job_id, "episode_id": episode_id})


def _job_generate_audio(episode_id, script_path):
    """Job async : génère les segments TTS + SFX en parallèle (4 workers)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from agents.producteur_audio import ProducteurAudio
    from agents.sfx_provider import SfxProvider

    script = json.loads(script_path.read_text(encoding="utf-8"))
    segments = script.get("episode", {}).get("segments", [])

    # Dossier de sortie
    segments_dir = config.OUTPUT_DIR / "segments" / episode_id
    segments_dir.mkdir(parents=True, exist_ok=True)

    producteur = ProducteurAudio()
    sfx_provider = SfxProvider()

    generated = 0
    errors = 0

    # Filtrer les segments déjà générés
    to_generate = []
    for seg in segments:
        seg_id = seg.get("id", "")

        # Vérifier si déjà généré en DB
        if _DB_AVAILABLE and SegmentAudioRepo:
            db_seg = SegmentAudioRepo.charger(episode_id, seg_id)
            if db_seg and db_seg["status"] in ("generated", "validated"):
                audio_path = db_seg.get("audio_path", "")
                # Vérifier que le fichier existe localement
                if audio_path and Path(audio_path).exists():
                    generated += 1
                    continue
                # Fichier absent localement (redeploy) — tenter restore Object Storage
                if audio_path and ps and ps.is_available():
                    try:
                        os_key = db_seg.get("audio_os_key") or f"segments/{episode_id}/{seg_id}.mp3"
                        dest = Path(audio_path)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        if ps.download_file(os_key, str(dest)):
                            logger.info("Segment %s restauré depuis Object Storage", seg_id)
                            generated += 1
                            continue
                    except Exception as e_os:
                        logger.warning("Restore OS segment %s échoué: %s", seg_id, e_os)

        to_generate.append(seg)

    def _generate_one(seg):
        """Génère un seul segment. Thread-safe grâce au rate limiter interne."""
        seg_id = seg.get("id", "")
        personnage = seg.get("personnage", "")
        is_sfx = personnage == "sfx"
        chemin = segments_dir / f"{seg_id}.mp3"

        # Marquer comme generating
        if _DB_AVAILABLE and SegmentAudioRepo:
            try:
                SegmentAudioRepo.maj_status(episode_id, seg_id, "generating")
            except Exception:
                pass

        if is_sfx:
            sfx_provider.generer_segment(seg.get("texte", ""), chemin)
        else:
            producteur.generer_segment(seg, chemin)

        # Mesurer durée
        duree_ms = 0
        try:
            from pydub import AudioSegment as AS
            audio = AS.from_mp3(str(chemin))
            duree_ms = len(audio)
        except Exception:
            pass

        # Mettre à jour en DB
        if _DB_AVAILABLE and SegmentAudioRepo:
            os_key = None
            if ps and ps.is_available():
                try:
                    os_key = f"segments/{episode_id}/{seg_id}.mp3"
                    ps.upload_file(str(chemin), os_key)
                except Exception:
                    os_key = None

            SegmentAudioRepo.maj_status(
                episode_id, seg_id, "generated",
                audio_path=str(chemin),
                audio_os_key=os_key,
                duree_ms=duree_ms,
                nb_caracteres=len(seg.get("texte", "")),
            )

        return seg_id, duree_ms

    # Génération parallèle : 4 workers (rate limiter ElevenLabs 3/s géré en interne)
    max_workers = min(4, max(1, len(to_generate)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_generate_one, seg): seg for seg in to_generate}
        for future in as_completed(futures):
            seg = futures[future]
            seg_id = seg.get("id", "")
            try:
                result_seg_id, duree_ms = future.result()
                generated += 1
                logger.info("Segment %s/%s généré (%dms)", episode_id, result_seg_id, duree_ms)
            except Exception as e:
                errors += 1
                logger.warning("Erreur segment %s/%s: %s", episode_id, seg_id, e)
                if _DB_AVAILABLE and SegmentAudioRepo:
                    try:
                        SegmentAudioRepo.maj_status(
                            episode_id, seg_id, "error",
                            error_message=str(e)[:500],
                        )
                    except Exception:
                        pass

    return {"generated": generated, "errors": errors, "total": len(segments)}


@app.route("/api/v2/episode/<episode_id>/segments")
def api_v2_segments(episode_id):
    """Liste les segments audio avec leur statut.

    Priority: DB segments (with audio status) → script JSON fallback.
    """
    seg_type = request.args.get("type")
    status = request.args.get("status")
    segments = []

    # 1. Try DB first (has audio status, paths, etc.)
    if _DB_AVAILABLE and SegmentAudioRepo:
        try:
            segments = SegmentAudioRepo.lister(episode_id, segment_type=seg_type, status=status)
        except Exception as e:
            logger.warning("SegmentAudioRepo.lister(%s) failed: %s", episode_id, e)

    # 2. Fallback: read from script JSON (covers pre-validation state)
    if not segments:
        script = None
        script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"

        # 2a. Try filesystem
        if script_path.exists():
            try:
                script = json.loads(script_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Script JSON read failed for %s: %s", episode_id, e)

        # 2b. Fallback to DB script (charger_valide returns dict directly)
        if script is None and _DB_AVAILABLE:
            try:
                from db_models import ScriptRepo
                db_script = ScriptRepo.charger_valide(episode_id)
                if not db_script or not db_script.get("episode"):
                    db_script = ScriptRepo.charger_derniere_version(episode_id)
                if db_script and db_script.get("episode"):
                    script = db_script
            except Exception as e:
                logger.warning("ScriptRepo fallback for segments %s: %s", episode_id, e)

        if script is None:
            return jsonify([])

        try:
            raw_segs = script.get("episode", {}).get("segments", [])
            for s in raw_segs:
                seg_id = s.get("id", "")
                personnage = s.get("personnage", "")
                is_sfx = personnage == "sfx" or s.get("type") == "sfx"
                s_type = "sfx" if is_sfx else "voix"
                # Apply type filter
                if seg_type and s_type != seg_type:
                    continue
                segments.append({
                    "segment_id": seg_id,
                    "episode_id": episode_id,
                    "personnage": personnage,
                    "texte": s.get("texte", s.get("description", "")),
                    "ton": s.get("ton", ""),
                    "rythme": s.get("rythme", "normal"),
                    "segment_type": s_type,
                    "status": "pending",
                    "audio_url": None,
                    "duree_ms": s.get("duree_ms") or s.get("duree_secondes", 0) * 1000,
                    "source": "script_json",
                })
        except Exception as e:
            logger.warning("Script segment parsing failed for %s: %s", episode_id, e)
            return jsonify([])
        return jsonify(segments)

    # Enrich DB segments with audio_url
    for s in segments:
        if s.get("audio_path") and Path(s["audio_path"]).exists():
            s["audio_url"] = f"/api/v2/segment/{episode_id}/{s['segment_id']}/audio"
        else:
            s["audio_url"] = None
        # Nettoyer les champs datetime pour JSON
        for k in ("created_at", "updated_at"):
            if s.get(k):
                s[k] = s[k].isoformat() if hasattr(s[k], "isoformat") else str(s[k])

    return jsonify(segments)


@app.route("/api/v2/episode/<episode_id>/audio-progress")
def api_v2_audio_progress(episode_id):
    """Progression de la génération audio."""
    if not _DB_AVAILABLE or not SegmentAudioRepo:
        return jsonify({"error": "DB non disponible"}), 503
    return jsonify(SegmentAudioRepo.progression(episode_id))


# ── V2 : Segment individuel ──────────────────────────────────────────────────


@app.route("/api/v2/segment/<episode_id>/<segment_id>/audio")
def api_v2_segment_audio(episode_id, segment_id):
    """Sert le fichier MP3 d'un segment."""
    if _DB_AVAILABLE and SegmentAudioRepo:
        seg = SegmentAudioRepo.charger(episode_id, segment_id)
        if seg and seg.get("audio_path"):
            p = Path(seg["audio_path"])
            if p.exists():
                return send_from_directory(str(p.parent), p.name, mimetype="audio/mpeg")

    # Fallback filesystem
    segments_dir = config.OUTPUT_DIR / "segments" / episode_id
    path = segments_dir / f"{segment_id}.mp3"
    if path.exists():
        return send_from_directory(str(segments_dir), f"{segment_id}.mp3", mimetype="audio/mpeg")

    return jsonify({"error": "Audio non trouvé"}), 404


@app.route("/api/v2/segment/<episode_id>/<segment_id>/edit", methods=["POST"])
def api_v2_segment_edit(episode_id, segment_id):
    """Édite le texte, ton et/ou rythme d'un segment. Met à jour DB + script JSON."""
    data = request.get_json(silent=True) or {}
    texte = data.get("texte")
    ton = data.get("ton")
    rythme = data.get("rythme")

    if not texte and ton is None and rythme is None:
        return jsonify({"error": "Au moins un champ requis (texte, ton, rythme)"}), 400

    # Mettre à jour le texte en DB (remet en pending)
    if texte and _DB_AVAILABLE and SegmentAudioRepo:
        SegmentAudioRepo.maj_texte(episode_id, segment_id, texte)

    # Mettre à jour ton/rythme en DB (colonnes dédiées)
    if (ton is not None or rythme is not None) and _DB_AVAILABLE and SegmentAudioRepo:
        try:
            from database import get_cursor
            updates = []
            params = []
            if ton is not None:
                updates.append("ton = %s")
                params.append(ton)
            if rythme is not None:
                updates.append("rythme = %s")
                params.append(rythme)
            if updates:
                params.extend([episode_id, segment_id, episode_id, segment_id])
                with get_cursor() as cur:
                    cur.execute(
                        f"UPDATE segments_audio SET {', '.join(updates)} "
                        "WHERE episode_id = %s AND segment_id = %s "
                        "AND version = (SELECT MAX(version) FROM segments_audio "
                        "WHERE episode_id = %s AND segment_id = %s)",
                        params,
                    )
        except Exception as e:
            logger.warning("Mise à jour ton/rythme DB échouée: %s", e)

    # Mettre à jour le script JSON (texte + ton + rythme)
    for suffix in ("_script.json", "_script_valide.json"):
        script_path = config.SCRIPTS_DIR / f"{episode_id}{suffix}"
        if script_path.exists():
            try:
                script = json.loads(script_path.read_text(encoding="utf-8"))
                for seg in script.get("episode", {}).get("segments", []):
                    if seg.get("id") == segment_id:
                        if texte:
                            seg["texte"] = texte
                        if ton is not None:
                            seg["ton"] = ton
                        if rythme is not None:
                            seg["rythme"] = rythme
                        break
                script_path.write_text(
                    json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception as e:
                logger.warning("Mise à jour script %s échouée: %s", suffix, e)

    return jsonify({"ok": True, "segment_id": segment_id})


@app.route("/api/v2/segment/<episode_id>/<segment_id>/regenerate", methods=["POST"])
def api_v2_segment_regenerate(episode_id, segment_id):
    """Regénère un segment (optionnellement avec nouveau texte)."""
    data = request.get_json(silent=True) or {}
    new_texte = data.get("texte")

    # Si nouveau texte, éditer d'abord
    if new_texte:
        if _DB_AVAILABLE and SegmentAudioRepo:
            SegmentAudioRepo.maj_texte(episode_id, segment_id, new_texte)
        # Sync script JSON
        for suffix in ("_script.json", "_script_valide.json"):
            script_path = config.SCRIPTS_DIR / f"{episode_id}{suffix}"
            if script_path.exists():
                try:
                    script = json.loads(script_path.read_text(encoding="utf-8"))
                    for seg in script.get("episode", {}).get("segments", []):
                        if seg.get("id") == segment_id:
                            seg["texte"] = new_texte
                            break
                    script_path.write_text(
                        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                except Exception as e:
                    logger.warning("Sync script échouée: %s", e)

    def _job():
        return _job_regenerate_segment(episode_id, segment_id)

    try:
        job_id = _start_fn_job(_job, episode_id=f"{episode_id}_regen_{segment_id}")
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"job_id": job_id})


def _job_regenerate_segment(episode_id, segment_id):
    """Regénère un seul segment TTS/SFX."""
    from agents.producteur_audio import ProducteurAudio
    from agents.sfx_provider import SfxProvider

    # Charger le segment depuis le script
    script_path = config.SCRIPTS_DIR / f"{episode_id}_script_valide.json"
    if not script_path.exists():
        script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"

    script = json.loads(script_path.read_text(encoding="utf-8"))
    seg = None
    for s in script.get("episode", {}).get("segments", []):
        if s.get("id") == segment_id:
            seg = s
            break

    if not seg:
        raise ValueError(f"Segment {segment_id} non trouvé dans le script")

    # Utiliser le texte DB si disponible (peut être plus récent)
    if _DB_AVAILABLE and SegmentAudioRepo:
        db_seg = SegmentAudioRepo.charger(episode_id, segment_id)
        if db_seg and db_seg.get("texte"):
            seg["texte"] = db_seg["texte"]
        SegmentAudioRepo.maj_status(episode_id, segment_id, "generating")

    segments_dir = config.OUTPUT_DIR / "segments" / episode_id
    segments_dir.mkdir(parents=True, exist_ok=True)
    chemin = segments_dir / f"{segment_id}.mp3"

    is_sfx = seg.get("personnage") == "sfx"

    try:
        if is_sfx:
            SfxProvider().generer(seg.get("texte", ""), chemin)
        else:
            ProducteurAudio()._generer_segment(seg, chemin)

        duree_ms = 0
        try:
            from pydub import AudioSegment as AS
            duree_ms = len(AS.from_mp3(str(chemin)))
        except Exception:
            pass

        if _DB_AVAILABLE and SegmentAudioRepo:
            SegmentAudioRepo.maj_status(
                episode_id, segment_id, "generated",
                audio_path=str(chemin), duree_ms=duree_ms,
                nb_caracteres=len(seg.get("texte", "")),
            )

        return {"segment_id": segment_id, "duree_ms": duree_ms}

    except Exception as e:
        if _DB_AVAILABLE and SegmentAudioRepo:
            SegmentAudioRepo.maj_status(
                episode_id, segment_id, "error", error_message=str(e)[:500],
            )
        raise


@app.route("/api/v2/segment/<episode_id>/<segment_id>/validate", methods=["POST"])
def api_v2_segment_validate(episode_id, segment_id):
    """Valide un segment audio."""
    if not _DB_AVAILABLE or not SegmentAudioRepo:
        return jsonify({"error": "DB non disponible"}), 503
    SegmentAudioRepo.maj_status(episode_id, segment_id, "validated")
    return jsonify({"ok": True})


@app.route("/api/v2/episode/<episode_id>/validate-all-segments", methods=["POST"])
def api_v2_validate_all_segments(episode_id):
    """Valide tous les segments générés d'un épisode."""
    if not _DB_AVAILABLE or not SegmentAudioRepo:
        return jsonify({"error": "DB non disponible"}), 503
    count = SegmentAudioRepo.valider_tous(episode_id)
    return jsonify({"ok": True, "count": count})


@app.route("/api/v2/episode/<episode_id>/segments/bulk-action", methods=["POST"])
def api_v2_segments_bulk_action(episode_id):
    """Actions groupées sur une sélection de segments: validate ou regenerate."""
    if not _DB_AVAILABLE or not SegmentAudioRepo:
        return jsonify({"error": "DB non disponible"}), 503

    data = request.get_json(silent=True) or {}
    action = data.get("action")
    segment_ids = data.get("segment_ids", [])

    if action not in ("validate", "regenerate"):
        return jsonify({"error": "Action invalide (validate ou regenerate)"}), 400
    if not segment_ids or not isinstance(segment_ids, list):
        return jsonify({"error": "segment_ids requis (liste non vide)"}), 400

    if action == "validate":
        count = 0
        for sid in segment_ids:
            try:
                SegmentAudioRepo.maj_status(episode_id, sid, "validated")
                count += 1
            except Exception as e:
                logger.warning("Bulk validate %s/%s échoué: %s", episode_id, sid, e)
        return jsonify({"ok": True, "count": count})

    # action == "regenerate"
    def _job():
        return _job_regenerate_errors(episode_id, segment_ids)

    try:
        job_id = _start_fn_job(_job, episode_id=f"{episode_id}_bulk_regen")
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"job_id": job_id, "count": len(segment_ids)})


@app.route("/api/v2/episode/<episode_id>/segments/regenerate-errors", methods=["POST"])
def api_v2_regenerate_errors(episode_id):
    """Régénère tous les segments en erreur pour un épisode (job async)."""
    if not _DB_AVAILABLE or not SegmentAudioRepo:
        return jsonify({"error": "DB non disponible"}), 503

    error_segments = SegmentAudioRepo.lister(episode_id, status="error")
    if not error_segments:
        return jsonify({"error": "Aucun segment en erreur"}), 404

    error_ids = [s["segment_id"] for s in error_segments]

    def _job():
        return _job_regenerate_errors(episode_id, error_ids)

    try:
        job_id = _start_fn_job(_job, episode_id=f"{episode_id}_regen_errors")
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"job_id": job_id, "count": len(error_ids)})


def _job_regenerate_errors(episode_id, segment_ids):
    """Régénère une liste de segments en erreur."""
    regenerated = 0
    still_errors = 0
    for seg_id in segment_ids:
        try:
            _job_regenerate_segment(episode_id, seg_id)
            regenerated += 1
        except Exception as e:
            still_errors += 1
            logger.warning("Retry segment %s/%s échoué: %s", episode_id, seg_id, e)
    return {"regenerated": regenerated, "still_errors": still_errors, "total": len(segment_ids)}


# ── V2 : Montage ─────────────────────────────────────────────────────────────


@app.route("/api/v2/episode/<episode_id>/montage", methods=["POST"])
def api_v2_montage(episode_id):
    """Lance le montage des segments validés (job async ~20-30 min)."""
    if not _DB_AVAILABLE or not MontageRepo:
        return jsonify({"error": "DB non disponible"}), 503

    # Vérifier que les segments voix sont prêts
    progress = SegmentAudioRepo.progression(episode_id)
    voix_ready = progress["generated"] + progress["validated"]
    if progress["pending"] > 0 or progress["generating"] > 0:
        return jsonify({
            "error": f"Segments non prêts: {progress['pending']} pending, {progress['generating']} en cours",
        }), 400

    # Compute script hash for coherence tracking
    _montage_script_hash = None
    try:
        from utils import compute_script_hash
        script_path = config.SCRIPTS_DIR / f"{episode_id}_script_valide.json"
        if not script_path.exists():
            script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"
        if script_path.exists():
            _script = json.loads(script_path.read_text(encoding="utf-8"))
            _montage_script_hash = compute_script_hash(_script)
    except Exception:
        pass

    # Créer la ligne montage
    montage_id = MontageRepo.creer(episode_id, script_content_hash=_montage_script_hash)

    def _job():
        return _job_montage(episode_id, montage_id)

    try:
        job_id = _start_fn_job(_job, episode_id=episode_id)
    except ValueError as e:
        MontageRepo.echouer(montage_id, str(e))
        return jsonify({"error": str(e)}), 409

    return jsonify({"job_id": job_id, "montage_id": montage_id})


def _job_montage(episode_id, montage_id):
    """Job async : lance Monteur.assembler()."""
    from agents.monteur import Monteur

    script_path = config.SCRIPTS_DIR / f"{episode_id}_script_valide.json"
    if not script_path.exists():
        script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"

    script = json.loads(script_path.read_text(encoding="utf-8"))
    segments_dir = config.OUTPUT_DIR / "segments" / episode_id
    sortie_dir = config.OUTPUT_DIR / "audio" / "episodes"
    sortie_dir.mkdir(parents=True, exist_ok=True)

    # Compute script hash for coherence tracking
    _script_hash = None
    try:
        from utils import compute_script_hash
        _script_hash = compute_script_hash(script)
    except Exception:
        pass

    try:
        monteur = Monteur()
        resultat = monteur.assembler(script, dossier_segments=segments_dir, dossier_sortie=sortie_dir)

        chemin_hq = resultat.get("chemin_hq", "")
        chemin_preview = resultat.get("chemin_preview", "")
        duree = resultat.get("duree_secondes", 0)
        taille = 0
        if chemin_hq and Path(chemin_hq).exists():
            taille = Path(chemin_hq).stat().st_size
        chapitres = resultat.get("chapitres", [])

        # Upload Object Storage
        os_key_hq = None
        os_key_preview = None
        if ps and ps.is_available():
            try:
                if chemin_hq:
                    os_key_hq = f"audio/{episode_id}/{Path(chemin_hq).name}"
                    ps.upload_file(chemin_hq, os_key_hq)
                if chemin_preview:
                    os_key_preview = f"audio/{episode_id}/{Path(chemin_preview).name}"
                    ps.upload_file(chemin_preview, os_key_preview)
            except Exception as e:
                logger.warning("Upload montage OS échoué: %s", e)

        # Mettre à jour en DB
        MontageRepo.terminer(
            montage_id,
            audio_path_hq=chemin_hq,
            audio_path_preview=chemin_preview,
            duree_secondes=duree,
            taille_bytes=taille,
            nb_segments=len(script.get("episode", {}).get("segments", [])),
            chapitres_json=chapitres,
            audio_os_key_hq=os_key_hq,
            audio_os_key_preview=os_key_preview,
            script_content_hash=_script_hash,
        )

        return {"montage_id": montage_id, "duree_secondes": duree, "taille_bytes": taille}

    except Exception as e:
        MontageRepo.echouer(montage_id, str(e)[:500])
        raise


@app.route("/api/v2/episode/<episode_id>/montages")
def api_v2_list_montages(episode_id):
    """Liste les montages d'un épisode. Fallback sur pipeline V1 si aucun montage V2 complet."""
    if not _DB_AVAILABLE or not MontageRepo:
        return jsonify({"error": "DB non disponible"}), 503

    montages = MontageRepo.lister(episode_id)

    # ── Fallback V1: si aucun montage V2 completed, chercher dans le pipeline V1 ──
    has_completed_v2 = any(m.get("status") == "completed" for m in montages)
    if not has_completed_v2:
        v1_montage = _find_v1_montage(episode_id)
        if v1_montage:
            # Update any stale "processing" row, or inject a virtual montage
            stale = [m for m in montages if m.get("status") == "processing"]
            if stale:
                # Update the stale row in DB with V1 data
                _v1_update_ok = False
                try:
                    _update_montage_from_v1(stale[0]["id"], v1_montage)
                    # Refresh from DB — preserve V1 audio URLs for serving
                    montages = MontageRepo.lister(episode_id)
                    # Inject V1 audio URLs into the updated row (lost during DB reload)
                    for m in montages:
                        if m.get("id") == stale[0]["id"]:
                            m["_v1_audio_url_hq"] = v1_montage.get("_v1_audio_url_hq")
                            m["_v1_audio_url_preview"] = v1_montage.get("_v1_audio_url_preview")
                    _v1_update_ok = True
                except Exception as e:
                    logger.warning("Impossible de mettre à jour montage V2 depuis V1: %s", e)
                # If DB update failed, replace the stale row with virtual V1 montage
                if not _v1_update_ok:
                    montages = [m for m in montages if m.get("status") != "processing"]
                    montages.append(v1_montage)
            else:
                # No V2 row at all — inject virtual montage from V1
                montages.append(v1_montage)

    # ── Compute current script hash for mismatch detection ──
    _current_script_hash = None
    try:
        from utils import compute_script_hash
        # Try DB first (latest version)
        try:
            from db_models import ScriptRepo
            db_script = ScriptRepo.charger_valide(episode_id)
            if not db_script:
                db_script = ScriptRepo.charger_derniere_version(episode_id)
            if db_script:
                _current_script_hash = compute_script_hash(db_script)
        except Exception:
            pass
        # Fallback to filesystem
        if not _current_script_hash:
            for suffix in ("_script_valide.json", "_script.json"):
                _sp = config.SCRIPTS_DIR / f"{episode_id}{suffix}"
                if _sp.exists():
                    _s = json.loads(_sp.read_text(encoding="utf-8"))
                    _current_script_hash = compute_script_hash(_s)
                    break
    except Exception:
        pass

    for m in montages:
        # ── Script/audio coherence fields ──
        _prod_hash = m.get("script_content_hash")
        m["script_hash_production"] = _prod_hash
        m["script_hash_current"] = _current_script_hash
        m["script_mismatch"] = bool(
            _prod_hash and _current_script_hash and _prod_hash != _current_script_hash
        )

        if m.get("audio_path_hq") and Path(m["audio_path_hq"]).exists():
            m["audio_url_hq"] = f"/api/v2/montage/{m['id']}/audio?quality=hq"
            m["audio_url_preview"] = f"/api/v2/montage/{m['id']}/audio?quality=preview"
            m["download_url"] = f"/api/v2/montage/{m['id']}/download"
        elif m.get("_v1_audio_url_hq"):
            # V1 virtual montage — use direct audio route
            m["audio_url_hq"] = m.pop("_v1_audio_url_hq")
            m["audio_url_preview"] = m.pop("_v1_audio_url_preview", None)
            m["download_url"] = m.get("audio_url_hq")
        else:
            # Try Object Storage restore for V2 montages
            os_key = m.get("audio_os_key_hq")
            if os_key and ps and ps.is_available():
                try:
                    local_path = config.OUTPUT_DIR / "audio" / "episodes" / Path(os_key).name
                    if not local_path.exists():
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        ps.download_file(os_key, str(local_path))
                    if local_path.exists():
                        m["audio_path_hq"] = str(local_path)
                        m["audio_url_hq"] = f"/api/v2/montage/{m['id']}/audio?quality=hq"
                        m["audio_url_preview"] = f"/api/v2/montage/{m['id']}/audio?quality=preview"
                        m["download_url"] = f"/api/v2/montage/{m['id']}/download"
                except Exception as e:
                    logger.warning("Restore audio OS échoué pour montage %s: %s", m.get("id"), e)
            if "audio_url_hq" not in m or m["audio_url_hq"] is None:
                m["audio_url_hq"] = None
                m["audio_url_preview"] = None
                m["download_url"] = None
        if m.get("created_at"):
            m["created_at"] = m["created_at"].isoformat() if hasattr(m["created_at"], "isoformat") else str(m["created_at"])
        if m.get("chapitres_json"):
            m["chapitres_json"] = m["chapitres_json"] if isinstance(m["chapitres_json"], list) else []

    return jsonify(montages)


def _find_v1_montage(episode_id):
    """Cherche un montage terminé dans le pipeline V1 (productions + fichiers_audio)."""
    try:
        import dashboard_data as dd
        rapport = dd.charger_rapport(episode_id)
        if not rapport:
            return None
        montage_data = rapport.get("etapes", {}).get("montage", {})
        chemin_hq = montage_data.get("chemin_hq")
        chemin_preview = montage_data.get("chemin_preview")
        if not chemin_hq:
            return None

        # Try to find audio locally or via V1 audio route
        hq_name = Path(chemin_hq).name
        preview_name = Path(chemin_preview).name if chemin_preview else hq_name

        # Check local filesystem (V1 audio route serves from output/episodes/)
        local_hq = config.OUTPUT_DIR / "episodes" / hq_name
        if not local_hq.exists():
            # Try Object Storage restore via V1 keys
            os_data = montage_data.get("object_storage", {})
            os_key_hq = os_data.get("hq")
            if os_key_hq and ps and ps.is_available():
                try:
                    local_hq.parent.mkdir(parents=True, exist_ok=True)
                    ps.download_file(os_key_hq, str(local_hq))
                except Exception:
                    pass

        duree = montage_data.get("duree_secondes", 0)
        taille = montage_data.get("taille_mb", 0) * 1024 * 1024 if montage_data.get("taille_mb") else 0
        if not taille and local_hq.exists():
            taille = local_hq.stat().st_size
        chapitres = montage_data.get("chapitres", [])

        return {
            "id": "v1",
            "episode_id": episode_id,
            "status": "completed",
            "is_published": False,
            "duree_secondes": duree,
            "taille_bytes": int(taille),
            "nb_segments": None,
            "chapitres_json": chapitres,
            "audio_path_hq": str(local_hq) if local_hq.exists() else None,
            "audio_path_preview": None,
            "audio_os_key_hq": montage_data.get("object_storage", {}).get("hq"),
            "audio_os_key_preview": montage_data.get("object_storage", {}).get("preview"),
            "created_at": rapport.get("debut", ""),
            "error_message": None,
            "_v1_audio_url_hq": f"/audio/episodes/{hq_name}",
            "_v1_audio_url_preview": f"/audio/episodes/{preview_name}",
        }
    except Exception as e:
        logger.warning("Erreur recherche montage V1 pour %s: %s", episode_id, e)
        return None


def _update_montage_from_v1(montage_id, v1_data):
    """Met à jour une ligne montage V2 stale avec les données du pipeline V1."""
    conn = database.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE montages SET
                    status = 'completed',
                    audio_path_hq = %s,
                    audio_path_preview = %s,
                    duree_secondes = %s,
                    taille_bytes = %s,
                    chapitres_json = %s::jsonb,
                    audio_os_key_hq = %s,
                    audio_os_key_preview = %s
                WHERE id = %s
            """, (
                v1_data.get("audio_path_hq"),
                v1_data.get("audio_path_preview"),
                v1_data.get("duree_secondes"),
                v1_data.get("taille_bytes"),
                json.dumps(v1_data.get("chapitres_json", [])),
                v1_data.get("audio_os_key_hq"),
                v1_data.get("audio_os_key_preview"),
                montage_id,
            ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        database.release_conn(conn)


@app.route("/api/v2/montage/<int:montage_id>/audio")
def api_v2_montage_audio(montage_id):
    """Sert le fichier audio d'un montage."""
    if not _DB_AVAILABLE or not MontageRepo:
        return jsonify({"error": "DB non disponible"}), 503

    montage = MontageRepo.charger(montage_id)
    if not montage:
        return jsonify({"error": "Montage non trouvé"}), 404

    quality = request.args.get("quality", "preview")
    key = "audio_path_hq" if quality == "hq" else "audio_path_preview"
    path = montage.get(key) or montage.get("audio_path_hq")

    # Try local file first
    if path and Path(path).exists():
        p = Path(path)
        return send_from_directory(str(p.parent), p.name, mimetype="audio/mpeg")

    # Fallback: restore from Object Storage
    os_key_field = "audio_os_key_hq" if quality == "hq" else "audio_os_key_preview"
    os_key = montage.get(os_key_field) or montage.get("audio_os_key_hq")
    if os_key and ps and ps.is_available():
        try:
            local_path = config.OUTPUT_DIR / "audio" / "episodes" / Path(os_key).name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if not local_path.exists():
                ps.download_file(os_key, str(local_path))
            if local_path.exists():
                return send_from_directory(str(local_path.parent), local_path.name, mimetype="audio/mpeg")
        except Exception as e:
            logger.warning("Restore audio OS échoué pour montage %s: %s", montage_id, e)

    return jsonify({"error": "Fichier audio non trouvé"}), 404


@app.route("/api/v2/montage/<int:montage_id>/download")
def api_v2_montage_download(montage_id):
    """Télécharge le montage en qualité HD."""
    if not _DB_AVAILABLE or not MontageRepo:
        return jsonify({"error": "DB non disponible"}), 503

    montage = MontageRepo.charger(montage_id)
    if not montage:
        return jsonify({"error": "Montage non trouvé"}), 404

    path = montage.get("audio_path_hq")

    # Try local file first
    if path and Path(path).exists():
        p = Path(path)
        return send_from_directory(
            str(p.parent), p.name,
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name=f"{montage['episode_id']}_montage_{montage_id}_hq.mp3",
        )

    # Fallback: restore from Object Storage
    os_key = montage.get("audio_os_key_hq")
    if os_key and ps and ps.is_available():
        try:
            local_path = config.OUTPUT_DIR / "audio" / "episodes" / Path(os_key).name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if not local_path.exists():
                ps.download_file(os_key, str(local_path))
            if local_path.exists():
                return send_from_directory(
                    str(local_path.parent), local_path.name,
                    mimetype="audio/mpeg",
                    as_attachment=True,
                    download_name=f"{montage['episode_id']}_montage_{montage_id}_hq.mp3",
                )
        except Exception as e:
            logger.warning("Restore audio OS échoué pour download montage %s: %s", montage_id, e)

    return jsonify({"error": "Fichier HD non trouvé"}), 404


# ── V2 : Publication ─────────────────────────────────────────────────────────


@app.route("/api/v2/montage/<int:montage_id>/publish", methods=["POST"])
def api_v2_publish(montage_id):
    """Publie un montage (le rend écoutable sur le front public)."""
    if not _DB_AVAILABLE or not MontageRepo:
        return jsonify({"error": "DB non disponible"}), 503

    montage = MontageRepo.charger(montage_id)
    if not montage:
        return jsonify({"error": "Montage non trouvé"}), 404
    if montage["status"] != "completed":
        return jsonify({"error": f"Montage en statut '{montage['status']}', pas 'completed'"}), 400

    episode_id = montage["episode_id"]

    # Copier l'audio vers le chemin attendu par le front public
    if montage.get("audio_path_hq") and Path(montage["audio_path_hq"]).exists():
        public_dir = config.OUTPUT_DIR / "audio" / "episodes"
        public_dir.mkdir(parents=True, exist_ok=True)
        src = Path(montage["audio_path_hq"])
        dst = public_dir / f"{episode_id}_192k.mp3"
        import shutil
        shutil.copy2(str(src), str(dst))

        # Copier aussi le preview
        if montage.get("audio_path_preview") and Path(montage["audio_path_preview"]).exists():
            dst_preview = public_dir / f"{episode_id}_preview.mp3"
            shutil.copy2(str(montage["audio_path_preview"]), str(dst_preview))

    # Publier en DB
    try:
        MontageRepo.publier(montage_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Charger le script pour RSS + historique
    script = None
    script_path = config.SCRIPTS_DIR / f"{episode_id}_script_valide.json"
    if not script_path.exists():
        script_path = config.SCRIPTS_DIR / f"{episode_id}_script.json"
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Lecture script échouée pour publication: %s", e)

    ep = script.get("episode", {}) if script else {}

    # P1-3 : Mettre à jour le flux RSS
    dst = config.OUTPUT_DIR / "audio" / "episodes" / f"{episode_id}_192k.mp3"
    if dst.exists():
        try:
            from agents.publisher import Publisher
            publisher = Publisher()
            # Construire les meta minimales pour le RSS
            saison_num = int(episode_id[1:3]) if len(episode_id) >= 6 else 1
            numero_ep = int(episode_id[4:6]) if len(episode_id) >= 6 else 1
            rss_meta = {
                "titre": ep.get("titre", episode_id),
                "description_courte": ep.get("resume", ep.get("titre", "")),
                "description_longue": ep.get("resume", ""),
                "saison": saison_num,
                "numero": numero_ep,
                "episode_id": episode_id,
                "type_episode": ep.get("type", "standard"),
                "morale": ep.get("morale", ""),
            }
            taille = dst.stat().st_size
            publisher._mettre_a_jour_rss(
                rss_meta, str(dst), taille,
                pubdate_offset_seconds=numero_ep * 3600,
            )
            logger.info("RSS mis à jour pour %s", episode_id)
        except ImportError:
            logger.warning("Module publisher non disponible — RSS non mis à jour")
        except Exception as e:
            logger.warning("Mise à jour RSS échouée: %s", e)

    # P1-4 : Créer un rapport V1 compatible + appeler ajouter_historique
    try:
        rapport_v1 = {
            "episode_id": episode_id,
            "titre": ep.get("titre", episode_id),
            "dry_run": False,
            "debut": datetime.utcnow().isoformat(),
            "etapes": {
                "script": {"status": "ok", "validation_humaine": True},
                "montage": {"status": "ok", "validation_humaine": True},
                "publication": {"status": "ok"},
            },
            "decisions_humaines": [],
        }
        # Sauvegarder le rapport V1
        rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        rapport_path.write_text(
            json.dumps(rapport_v1, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Appeler ajouter_historique pour visibilité dashboard V1 + site public
        if script:
            try:
                from main import ajouter_historique
                ajouter_historique(rapport_v1, script)
                logger.info("Historique V1 mis à jour pour %s", episode_id)
            except ImportError:
                logger.warning("Import main.ajouter_historique échoué — historique non mis à jour")
            except Exception as e_hist:
                logger.warning("ajouter_historique échoué: %s", e_hist)
    except Exception as e:
        logger.warning("Création rapport V1 échouée: %s", e)

    return jsonify({"ok": True, "episode_id": episode_id, "montage_id": montage_id})


@app.route("/api/v2/montage/<int:montage_id>/depublish", methods=["POST"])
def api_v2_depublish(montage_id):
    """Depublie un montage."""
    if not _DB_AVAILABLE or not MontageRepo:
        return jsonify({"error": "DB non disponible"}), 503

    montage = MontageRepo.charger(montage_id)
    if not montage:
        return jsonify({"error": "Montage non trouve"}), 404
    if not montage.get("is_published"):
        return jsonify({"error": "Ce montage n'est pas publie"}), 400

    try:
        MontageRepo.depublier(montage_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True, "montage_id": montage_id})


# ── V2 : Vue saisons ─────────────────────────────────────────────────────────


@app.route("/api/v2/saisons/episodes")
def api_v2_saisons_episodes():
    """Vue consolidée des 30 épisodes (3 saisons) avec statut."""
    result = []

    for saison_num in range(1, 4):
        plan = config.charger_saison(saison_num)
        if not plan:
            continue

        episodes = plan.get("saison", {}).get("episodes", [])
        for ep in episodes:
            eid = f"S{saison_num:02d}E{ep.get('numero', 0):02d}"

            # Script exists?
            has_script = (config.SCRIPTS_DIR / f"{eid}_script.json").exists()

            # Audio progress
            audio_progress = None
            if _DB_AVAILABLE and SegmentAudioRepo:
                try:
                    audio_progress = SegmentAudioRepo.progression(eid)
                except Exception:
                    pass

            # Montages
            montage_count = 0
            is_published = False
            if _DB_AVAILABLE and MontageRepo:
                try:
                    montages = MontageRepo.lister(eid)
                    montage_count = len(montages)
                    is_published = any(m.get("is_published") for m in montages)
                except Exception:
                    pass

            result.append({
                "episode_id": eid,
                "saison": saison_num,
                "numero": ep.get("numero", 0),
                "titre": ep.get("titre", ""),
                "type": ep.get("type", "standard"),
                "has_script": has_script,
                "audio_progress": audio_progress,
                "montage_count": montage_count,
                "is_published": is_published,
            })

    return jsonify(result)


@app.route("/admin/v2")
@app.route("/admin/v2/")
@_admin_required
def admin_v2_redirect():
    """Redirect /admin/v2 to /admin (V2 is now the default)."""
    return redirect(url_for("admin_dashboard"))


# ── Lancement ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    print(f"\n  Les Histoires de Papy Babou — Dashboard Web")
    print(f"  http://0.0.0.0:{port}\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
