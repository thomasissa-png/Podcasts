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
from pathlib import Path

# Ensure imports work when launched from repo root (Replit)
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
os.chdir(_THIS_DIR)

from flask import Flask, jsonify, render_template, request, send_from_directory

import config
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
    """Supprime les jobs termines dont le TTL est depasse (appele sous _jobs_lock)."""
    now = time.monotonic()
    expired = [
        jid for jid, job in _jobs.items()
        if job["status"] == "done" and now - job.get("created_at", now) > _JOB_TTL_SECONDS
    ]
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


@app.route("/api/job-status/<job_id>")
def api_job_status(job_id):
    """Retourne le statut d'un job asynchrone."""
    if not _JOB_ID_RE.match(job_id):
        return jsonify({"error": "Format de job_id invalide"}), 400
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": f"Job introuvable : {job_id}"}), 404
        if job["status"] == "running":
            return jsonify({"status": "running"})
        # Job termine — copier le resultat et nettoyer atomiquement
        result = job["result"]
        _jobs.pop(job_id, None)
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
