"""Serveur web Flask — Dashboard de production Les Histoires de Papy Babou.

Lance le dashboard complet en mode web : dashboard, production d'episodes,
planification de saisons, reprise de checkpoints, configuration.

Usage :
    python web.py                     # Demarre sur le port 5000
"""

import logging
import os
import re
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

from flask import Flask, jsonify, render_template, request, send_from_directory

import config
import dashboard_data as dashboard_data_mod
from dashboard_data import get_dashboard_data, charger_preferences, charger_checkpoints, charger_publications

# ── Initialisation PostgreSQL ─────────────────────────────────────────────────
try:
    import database
    from database import DATABASE_URL
    _DB_AVAILABLE = bool(DATABASE_URL)
except ImportError:
    _DB_AVAILABLE = False

app = Flask(__name__, template_folder=str(_THIS_DIR / "templates"))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "papy-babou-dev-key")


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

logger = logging.getLogger(__name__)


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
    """Sert le favicon SVG ou retourne 204 si absent."""
    favicon_path = _THIS_DIR / "assets" / "artwork" / "favicon.svg"
    if favicon_path.exists():
        return send_from_directory(str(favicon_path.parent), favicon_path.name, mimetype="image/svg+xml")
    return "", 204


@app.route("/assets/artwork/<path:filename>")
def serve_artwork(filename):
    """Sert les fichiers artwork (favicon, images)."""
    artwork_dir = _THIS_DIR / "assets" / "artwork"
    return send_from_directory(str(artwork_dir), filename)


@app.route("/audio/episodes/<path:filename>")
def serve_episode_audio(filename):
    """Sert les fichiers audio des épisodes produits (MP3)."""
    # Security: only allow .mp3 files, no path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "Nom de fichier invalide"}), 400
    if not filename.endswith(".mp3"):
        return jsonify({"error": "Format non supporté"}), 400
    episodes_dir = _THIS_DIR / "output" / "episodes"
    audio_path = episodes_dir / filename
    if not audio_path.exists():
        return jsonify({"error": f"Fichier audio introuvable : {filename}"}), 404
    return send_from_directory(str(episodes_dir), filename, mimetype="audio/mpeg")


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

_JOB_TTL_SECONDS = 3600  # Supprimer les jobs termines apres 1 heure

# Timeouts par type de job (configurables via env)
_TIMEOUT_PRODUIRE = int(os.getenv("TIMEOUT_PRODUIRE", "1800"))          # 30 min
_TIMEOUT_PLANIFIER = int(os.getenv("TIMEOUT_PLANIFIER", "1800"))        # 30 min
_TIMEOUT_PRODUIRE_SAISON = int(os.getenv("TIMEOUT_PRODUIRE_SAISON", "7200"))  # 2h
_TIMEOUT_REPRENDRE = int(os.getenv("TIMEOUT_REPRENDRE", "1800"))        # 30 min
_TIMEOUT_BATCH = int(os.getenv("TIMEOUT_BATCH", "7200"))                # 2h
_JOB_ID_RE = re.compile(r'^[0-9a-f]{12}$')


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


def _run_cli(cmd_args, timeout=300, job_id=None):
    """Lance une commande main.py et retourne le resultat.

    Utilise Popen pour permettre l'annulation via /api/cancel.
    """
    cmd = [sys.executable, "main.py"] + cmd_args
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_THIS_DIR),
        )
        if job_id:
            with _process_lock:
                _job_processes[job_id] = proc
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return {"error": f"Timeout ({timeout}s)", "status": "error"}

        if proc.returncode == -9 or proc.returncode == -15:
            return {"error": "Production annulee par l'utilisateur.", "status": "cancelled"}

        result = {
            "status": "ok" if proc.returncode == 0 else "error",
            "stdout": stdout[-4000:] if stdout else "",
            "stderr": stderr[-1000:] if stderr else "",
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


def _start_job(cmd_args, timeout=300, cleanup_fn=None):
    """Lance un job en arriere-plan et retourne son ID immediatement.

    Args:
        cmd_args: Arguments pour main.py.
        timeout: Timeout en secondes.
        cleanup_fn: Fonction optionnelle appelee apres le job (ex: supprimer fichier temp).

    Returns:
        job_id (str): Identifiant unique du job.
    """
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _gc_expired_jobs()
        _jobs[job_id] = {"status": "running", "result": None, "created_at": time.monotonic()}

    def _worker():
        try:
            result = _run_cli(cmd_args, timeout=timeout, job_id=job_id)
            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "done",
                    "result": result,
                    "created_at": time.monotonic(),
                }
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


_JOB_RESULT_TTL = 60  # Garder les résultats de jobs terminés 60 secondes


@app.route("/api/job-status/<job_id>")
def api_job_status(job_id):
    """Retourne le statut d'un job asynchrone.

    Les jobs terminés sont gardés en cache pendant 60 secondes pour éviter
    la perte de résultat si le client ne poll pas assez vite (race condition).
    """
    if not _JOB_ID_RE.match(job_id):
        return jsonify({"error": "Format de job_id invalide"}), 400
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": f"Job introuvable : {job_id}"}), 404
        if job["status"] == "running":
            return jsonify({"status": "running"})
        # Job terminé — marquer comme lu mais garder en cache pour le TTL
        result = job["result"]
        job["read_at"] = time.monotonic()
    return jsonify(result)


# ── Routes pages ─────────────────────────────────────────────────────────────


@app.route("/healthz")
def healthz():
    """Endpoint de health check leger — repond 200 immediatement."""
    return "ok", 200


@app.route("/")
def index():
    """Page principale — Dashboard complet avec navigation."""
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


# ── Routes API (JSON) — Lecture ──────────────────────────────────────────────


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

    # Episodes dans l'historique
    data = get_dashboard_data(numero)
    for ep in data.get("episodes", []):
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

                # Soft-delete de l'historique DB
                cur.execute(
                    "DELETE FROM historique_episodes WHERE episode_id = %s",
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

    # Load script content (filesystem first, DB fallback)
    script = None
    script_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    if script_path.exists():
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script = _json.load(f)
        except (ValueError, FileNotFoundError):
            pass
    if not script:
        # Fallback: load validated script from DB (survives re-deploys)
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

    # Load cover art path
    cover_art = None
    for ext in (".png", ".jpg"):
        cover_path = config.COVERS_DIR / f"{episode_id}_cover{ext}"
        if cover_path.exists():
            cover_art = f"{episode_id}_cover{ext}"
            break

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
    """Diagnostic endpoint — montre l'état complet des données d'un épisode."""
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
                "SELECT id, status, etape_courante, created_at, completed_at, "
                "rapport_json IS NOT NULL AS has_rapport "
                "FROM productions WHERE episode_id = %s ORDER BY created_at DESC LIMIT 5",
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

    # Load or create the rapport file
    rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
    rapport = {}
    if rapport_path.exists():
        try:
            with open(rapport_path, "r", encoding="utf-8") as f:
                rapport = _json.load(f)
        except (ValueError, FileNotFoundError):
            pass

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

    # Save rapport
    try:
        with open(rapport_path, "w", encoding="utf-8") as f:
            _json.dump(rapport, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({"error": f"Erreur sauvegarde rapport : {e}"}), 500

    action_label = "validé" if action == "validate" else "rejeté"
    step_labels = {"script": "Script", "montage": "Montage", "metadonnees": "Métadonnées"}
    return jsonify({
        "status": "ok",
        "message": f"{step_labels.get(step, step)} {action_label} pour {episode_id}.",
    })


def _handle_publication(episode_id, comment=""):
    """Gère la publication d'un épisode validé via le web."""
    import json as _json

    # Check prerequisites: script AND montage must be validated
    rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
    if not rapport_path.exists():
        return jsonify({"error": "Aucun rapport trouvé. L'épisode doit d'abord être produit."}), 400

    try:
        with open(rapport_path, "r", encoding="utf-8") as f:
            rapport = _json.load(f)
    except (ValueError, FileNotFoundError):
        return jsonify({"error": "Rapport illisible."}), 500

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

    # Launch publication via CLI (async)
    cmd = [
        "produire",
        "-e", episode_id,
        "--auto",
    ]

    # For now, just mark publication as validated in the rapport
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

    try:
        with open(rapport_path, "w", encoding="utf-8") as f:
            _json.dump(rapport, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({"error": f"Erreur sauvegarde : {e}"}), 500

    return jsonify({
        "status": "ok",
        "message": f"Publication validée pour {episode_id}. L'épisode peut maintenant être publié.",
    })


@app.route("/api/episodes-a-valider")
def api_episodes_a_valider():
    """API JSON — Liste des épisodes en attente de validation."""
    data = get_dashboard_data(0)
    episodes = []
    for ep in data["episodes"]:
        needs_validation = (
            not ep.get("validation_script", False)
            or not ep.get("validation_montage", False)
        )
        episodes.append({
            **ep,
            "needs_validation": needs_validation,
            "has_audio": bool(ep.get("audio_preview") or ep.get("audio_hq")),
        })
    return jsonify(episodes)


@app.route("/audio/covers/<path:filename>")
def serve_cover_art(filename):
    """Sert les fichiers cover art des épisodes."""
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "Nom de fichier invalide"}), 400
    covers_dir = config.COVERS_DIR
    cover_path = covers_dir / filename
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
    ]
    if morale:
        cmd.extend(["-m", morale])
    if dry_run:
        cmd.append("--dry-run")

    job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE)
    return jsonify({"status": "accepted", "job_id": job_id})


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


@app.route("/api/produire-saison", methods=["POST"])
def api_produire_saison():
    """Produit les episodes d'une saison planifiee (asynchrone)."""
    err = _check_api_key("ANTHROPIC_API_KEY")
    if err:
        return err
    body = request.get_json(force=True)
    saison = body.get("saison", 1)
    episodes = body.get("episodes", "").strip()
    dry_run = body.get("dry_run", False)

    cmd = [
        "produire-saison",
        "-s", str(saison),
        "--auto",
    ]
    if episodes:
        cmd.extend(["-e", episodes])
    if dry_run:
        cmd.append("--dry-run")

    job_id = _start_job(cmd, timeout=_TIMEOUT_PRODUIRE_SAISON)
    return jsonify({"status": "accepted", "job_id": job_id})


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

    job_id = _start_job(cmd, timeout=_TIMEOUT_REPRENDRE)
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

# ── Lancement ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    print(f"\n  Les Histoires de Papy Babou — Dashboard Web")
    print(f"  http://0.0.0.0:{port}\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
