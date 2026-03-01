"""Serveur web Flask — Dashboard de production Les Histoires de Papy Babou.

Lance le dashboard de production en mode web accessible depuis un navigateur.
Usage :
    python web.py                     # Démarre sur le port 5000
    python web.py --port 8080         # Port personnalisé
"""

import json
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


# ── Routes pages ─────────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Page principale — Dashboard."""
    saison = request.args.get("saison", 0, type=int)
    data = get_dashboard_data(saison)
    return render_template("dashboard.html", **data)


# ── Routes API (JSON) ────────────────────────────────────────────────────────


@app.route("/api/dashboard")
def api_dashboard():
    """API JSON — Données complètes du dashboard."""
    saison = request.args.get("saison", 0, type=int)
    data = get_dashboard_data(saison)
    return jsonify(data)


@app.route("/api/episodes")
def api_episodes():
    """API JSON — Liste des épisodes."""
    saison = request.args.get("saison", 0, type=int)
    data = get_dashboard_data(saison)
    return jsonify(data["episodes"])


@app.route("/api/preferences")
def api_preferences():
    """API JSON — Préférences producteur."""
    return jsonify(charger_preferences())


@app.route("/api/checkpoints")
def api_checkpoints():
    """API JSON — Checkpoints en attente."""
    return jsonify(charger_checkpoints())


@app.route("/api/produire", methods=["POST"])
def api_produire():
    """Lance une production en dry-run via le CLI."""
    body = request.get_json(force=True)
    titre = body.get("titre", "")
    saison = body.get("saison", 1)
    numero = body.get("numero", 1)
    resume = body.get("resume", "")
    morale = body.get("morale", "")

    if not titre:
        return jsonify({"error": "Titre requis"}), 400

    cmd = [
        sys.executable, "main.py", "produire",
        "-e", titre,
        "-s", str(saison),
        "-n", str(numero),
        "-r", resume,
        "-m", morale,
        "--dry-run",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=config.BASE_DIR,
        )
        return jsonify({
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout (120s)"}), 504


# ── Lancement ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    print(f"\n  Les Histoires de Papy Babou — Dashboard Web")
    print(f"  http://0.0.0.0:{port}\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
