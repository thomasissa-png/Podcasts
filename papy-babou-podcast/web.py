"""Serveur web Flask — Dashboard de production Les Histoires de Papy Babou.

Lance le dashboard complet en mode web : dashboard, production d'episodes,
planification de saisons, reprise de checkpoints, configuration.

Usage :
    python web.py                     # Demarre sur le port 5000
"""

import json
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
_TIMEOUT_PRODUIRE = int(os.getenv("TIMEOUT_PRODUIRE", "3600"))          # 1h (audio TTS peut être long)
_TIMEOUT_PLANIFIER = int(os.getenv("TIMEOUT_PLANIFIER", "1800"))        # 30 min
_TIMEOUT_PRODUIRE_SAISON = int(os.getenv("TIMEOUT_PRODUIRE_SAISON", "7200"))  # 2h
_TIMEOUT_REPRENDRE = int(os.getenv("TIMEOUT_REPRENDRE", "3600"))        # 1h (audio TTS peut être long)
_TIMEOUT_BATCH = int(os.getenv("TIMEOUT_BATCH", "7200"))                # 2h
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
                "ORDER BY created_at DESC LIMIT 1) "
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

    Sauvegarde le contenu du checkpoint dans le champ checkpoint_data
    de la production la plus récente. Permet de reprendre la production
    audio après un redéploiement même si le fichier checkpoint est perdu.
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
            cp_data = _json.load(f)
        with get_cursor() as cur:
            cur.execute(
                "UPDATE productions SET checkpoint_data = %s, updated_at = NOW() "
                "WHERE id = (SELECT id FROM productions WHERE episode_id = %s "
                "ORDER BY created_at DESC LIMIT 1) "
                "RETURNING id",
                (_json.dumps(cp_data, ensure_ascii=False, default=str), episode_id),
            )
            row = cur.fetchone()
            if row:
                logger.info("Checkpoint %s synchronisé en DB (production id=%d)", episode_id, row["id"])
    except Exception as e:
        logger.error("Sync checkpoint DB ÉCHOUÉ pour %s : %s", episode_id, e)


def _restore_checkpoint_from_db(episode_id: str, checkpoint_path) -> None:
    """Restaure un checkpoint depuis la DB si le fichier local n'existe pas.

    Après un redéploiement Replit, les fichiers checkpoint sont perdus.
    Cette fonction les restaure depuis le champ checkpoint_data de la
    production la plus récente en DB.
    """
    try:
        from database import DATABASE_URL, get_cursor
        if not DATABASE_URL:
            return
        import json as _json
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT checkpoint_data FROM productions "
                "WHERE episode_id = %s AND checkpoint_data IS NOT NULL "
                "AND checkpoint_data != '{}' "
                "ORDER BY created_at DESC LIMIT 1",
                (episode_id,),
            )
            row = cur.fetchone()
        if row and row["checkpoint_data"]:
            cp_data = row["checkpoint_data"]
            # S'assurer que le répertoire existe
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                _json.dump(cp_data, f, ensure_ascii=False, indent=2)
            logger.info("Checkpoint %s restauré depuis la DB", episode_id)

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
            proc.terminate()  # SIGTERM d'abord (graceful)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()  # SIGKILL en dernier recours
                proc.wait(timeout=2)
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


def _start_job(cmd_args, timeout=300, cleanup_fn=None, episode_id=None):
    """Lance un job en arriere-plan et retourne son ID immediatement.

    Args:
        cmd_args: Arguments pour main.py.
        timeout: Timeout en secondes.
        cleanup_fn: Fonction optionnelle appelee apres le job (ex: supprimer fichier temp).
        episode_id: Identifiant de l'épisode (pour empêcher les jobs concurrents).

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
    script_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    if not script_path.exists():
        # Tenter de restaurer depuis Object Storage
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

        # Si validation du script → marquer le script comme validé en DB
        # et sauvegarder le checkpoint/script en Object Storage
        if step == "script" and action == "validate":
            _sync_script_validated_to_db(episode_id)
            _sync_checkpoint_to_db(episode_id)
            # Upload script validé et checkpoint en Object Storage
            try:
                import persistent_storage
                script_path = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
                if script_path.exists():
                    persistent_storage.upload_script(episode_id, script_path)
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
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
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

    if phase not in ("audio", "publication"):
        return jsonify({"error": "Phase invalide. Valeurs acceptées : audio, publication"}), 400

    # Vérifier qu'un checkpoint existe pour cet épisode
    # Si le fichier n'existe pas (redéploiement), restaurer depuis Object Storage ou DB
    checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
    if not checkpoint_path.exists():
        try:
            import persistent_storage
            persistent_storage.restore_checkpoint(episode_id, config.CHECKPOINTS_DIR)
        except Exception:
            pass
    if not checkpoint_path.exists():
        _restore_checkpoint_from_db(episode_id, checkpoint_path)
    if not checkpoint_path.exists():
        return jsonify({"error": f"Checkpoint introuvable pour {episode_id}. La production initiale doit d'abord être lancée."}), 404

    if phase == "audio":
        # Reprendre depuis l'étape audio, s'arrêter après le montage
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
        return jsonify({"status": "accepted", "job_id": job_id, "phase": "audio"})

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
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
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
        # Relancer audio+montage depuis le checkpoint
        checkpoint_path = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
        if not checkpoint_path.exists():
            return jsonify({"error": f"Checkpoint introuvable pour {episode_id}."}), 404

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

        # Forcer la reprise depuis l'étape audio en réécrivant le checkpoint
        try:
            with fichier_lock(checkpoint_path):
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    cp = _json.load(f)
                cp["etape"] = "audio"
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

    episode_id = f"S{saison:02d}E{numero:02d}"
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
            elif etapes.get("script", {}).get("chemin") or rapport.get("status") == "waiting_validation":
                # Script existe (produit ou rejeté) → en attente de validation
                # BUG #3: Après rejet, validation_humaine=False mais le script existe
                # toujours — l'utilisateur doit pouvoir le modifier/régénérer
                status = "attente_validation_script"
            else:
                status = "en_cours"
        elif checkpoint_path.exists():
            status = "en_cours"

        episodes_status.append({
            "numero": ep["numero"],
            "episode_id": ep_id,
            "titre": ep.get("titre", ""),
            "type": ep.get("type", "standard"),
            "status": status,
            "validation_script": validation_script,
            "validation_montage": validation_montage,
        })

    # Trouver le prochain épisode à produire (premier non terminé)
    # B3: Un épisode est "prêt" quand script ET montage sont validés
    # (pas besoin d'attendre la publication pour passer au suivant)
    STATUTS_PRETS = ("termine", "montage_valide")
    prochain = None
    bloque_par = None
    for i, ep_s in enumerate(episodes_status):
        if ep_s["status"] in STATUTS_PRETS:
            continue
        # Vérifier que l'épisode précédent est prêt (sauf pour le premier)
        if i > 0 and episodes_status[i - 1]["status"] not in STATUTS_PRETS:
            bloque_par = episodes_status[i - 1]
        prochain = ep_s
        break

    return jsonify({
        "saison": saison_num,
        "theme": saison_data.get("theme", ""),
        "episodes": episodes_status,
        "prochain": prochain,
        "bloque_par": bloque_par,
        "total": len(episodes_plan),
        "termines": sum(1 for e in episodes_status if e["status"] == "termine"),
    })


@app.route("/api/produire-saison", methods=["POST"])
def api_produire_saison():
    """Produit le prochain épisode d'une saison (un seul à la fois).

    La production sérielle est séquentielle : chaque épisode doit être validé
    avant de passer au suivant, pour que le scripteur puisse lire les scripts
    précédents et assurer la continuité narrative.
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

    # Vérifier que les épisodes précédents sont terminés (DB + fichier)
    for n in range(1, numero):
        prev_id = f"S{saison:02d}E{n:02d}"
        rp = dashboard_data_mod.charger_rapport(prev_id)
        if not rp:
            return jsonify({
                "error": f"L'épisode {prev_id} doit être terminé avant de produire {episode_id}. "
                         f"La production sérielle est séquentielle."
            }), 409
        etapes = rp.get("etapes", {})
        script_ok = etapes.get("script", {}).get("validation_humaine", False)
        montage_ok = etapes.get("montage", {}).get("validation_humaine", False)
        if not (script_ok and montage_ok):
            return jsonify({
                "error": f"L'épisode {prev_id} n'est pas entièrement validé "
                         f"(script: {'OK' if script_ok else 'en attente'}, "
                         f"montage: {'OK' if montage_ok else 'en attente'}). "
                         f"Terminez-le avant de passer à {episode_id}."
            }), 409

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

# ── Lancement ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    print(f"\n  Les Histoires de Papy Babou — Dashboard Web")
    print(f"  http://0.0.0.0:{port}\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
