"""Serveur web Flask — Dashboard de production Les Histoires de Papy Babou.

Lance le dashboard complet en mode web : dashboard, production d'episodes,
planification de saisons, reprise de checkpoints, configuration.

Usage :
    python web.py                     # Demarre sur le port 5000
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

# Ensure imports work when launched from repo root (Replit)
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
os.chdir(_THIS_DIR)

from flask import Flask, jsonify, render_template, request

import config
from dashboard_data import get_dashboard_data, charger_preferences, charger_checkpoints

app = Flask(__name__, template_folder=str(_THIS_DIR / "templates"))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "papy-babou-dev-key")

logger = logging.getLogger(__name__)


# ── Helper : lancer une commande CLI ─────────────────────────────────────────


def _run_cli(cmd_args, timeout=300):
    """Lance une commande main.py et retourne le resultat."""
    cmd = [sys.executable, "main.py"] + cmd_args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_THIS_DIR),
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout[-4000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout ({timeout}s)", "status": "error"}
    except Exception as e:
        return {"error": str(e), "status": "error"}


# ── Routes pages ─────────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Page principale — Dashboard complet avec navigation."""
    saison = request.args.get("saison", 0, type=int)
    data = get_dashboard_data(saison)
    return render_template("dashboard.html", **data)


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


# ── Routes API (JSON) — Actions ─────────────────────────────────────────────


@app.route("/api/produire", methods=["POST"])
def api_produire():
    """Lance la production d'un episode."""
    body = request.get_json(force=True)
    titre = body.get("titre", "").strip()
    saison = body.get("saison", 1)
    numero = body.get("numero", 1)
    resume = body.get("resume", "").strip()
    morale = body.get("morale", "").strip()
    dry_run = body.get("dry_run", False)
    auto = body.get("auto", False)

    if not titre:
        return jsonify({"error": "Titre requis"}), 400
    if not resume:
        return jsonify({"error": "Resume requis"}), 400

    cmd = [
        "produire",
        "-e", titre,
        "-s", str(saison),
        "-n", str(numero),
        "-r", resume,
        "-m", morale,
    ]
    if dry_run:
        cmd.append("--dry-run")
    if auto:
        cmd.append("--auto")

    return jsonify(_run_cli(cmd, timeout=300))


@app.route("/api/planifier-saison", methods=["POST"])
def api_planifier_saison():
    """Planifie une saison complete."""
    body = request.get_json(force=True)
    saison = body.get("saison", 1)
    theme = body.get("theme", "").strip()
    description = body.get("description", "").strip()
    personnages = body.get("personnages", "").strip()

    if not theme:
        return jsonify({"error": "Theme requis"}), 400

    cmd = [
        "planifier-saison",
        "-s", str(saison),
        "-t", theme,
    ]
    if description:
        cmd.extend(["-d", description])
    if personnages:
        cmd.extend(["-p", personnages])

    return jsonify(_run_cli(cmd, timeout=180))


@app.route("/api/produire-saison", methods=["POST"])
def api_produire_saison():
    """Produit les episodes d'une saison planifiee."""
    body = request.get_json(force=True)
    saison = body.get("saison", 1)
    episodes = body.get("episodes", "").strip()
    dry_run = body.get("dry_run", False)
    auto = body.get("auto", False)

    cmd = [
        "produire-saison",
        "-s", str(saison),
    ]
    if episodes:
        cmd.extend(["-e", episodes])
    if dry_run:
        cmd.append("--dry-run")
    if auto:
        cmd.append("--auto")

    return jsonify(_run_cli(cmd, timeout=600))


@app.route("/api/reprendre", methods=["POST"])
def api_reprendre():
    """Reprend une production depuis un checkpoint."""
    body = request.get_json(force=True)
    fichier = body.get("fichier", "").strip()
    auto = body.get("auto", True)

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
    ]
    if auto:
        cmd.append("--auto")

    return jsonify(_run_cli(cmd, timeout=300))


@app.route("/api/batch", methods=["POST"])
def api_batch():
    """Lance une production batch depuis un JSON envoye par le client."""
    import json as _json
    import tempfile

    body = request.get_json(force=True)
    episodes_list = body.get("episodes", [])
    dry_run = body.get("dry_run", False)
    auto = body.get("auto", False)

    if not episodes_list or not isinstance(episodes_list, list):
        return jsonify({"error": "Liste d'episodes requise (tableau JSON)"}), 400

    # Validate each episode has required fields
    for i, ep in enumerate(episodes_list):
        if not isinstance(ep, dict):
            return jsonify({"error": f"Episode {i+1} : doit etre un objet JSON"}), 400
        if not ep.get("titre"):
            return jsonify({"error": f"Episode {i+1} : titre requis"}), 400
        if not ep.get("resume"):
            return jsonify({"error": f"Episode {i+1} : resume requis"}), 400

    # Write to temp file, pass to CLI
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(_THIS_DIR), delete=False
    ) as tmp:
        _json.dump(episodes_list, tmp, ensure_ascii=False)
        tmp_path = tmp.name

    try:
        cmd = ["batch", "-f", tmp_path]
        if dry_run:
            cmd.append("--dry-run")
        if auto:
            cmd.append("--auto")
        return jsonify(_run_cli(cmd, timeout=600))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Lancement ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    print(f"\n  Les Histoires de Papy Babou — Dashboard Web")
    print(f"  http://0.0.0.0:{port}\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
