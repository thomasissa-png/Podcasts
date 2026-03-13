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
from pathlib import Path

# Ensure imports work when launched from repo root (Replit)
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
os.chdir(_THIS_DIR)

from flask import Flask, jsonify, render_template, request

import config
from dashboard_data import get_dashboard_data, charger_preferences, charger_checkpoints, charger_publications

app = Flask(__name__, template_folder=str(_THIS_DIR / "templates"))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "papy-babou-dev-key")

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


def _check_api_key(key_name="ANTHROPIC_API_KEY"):
    """Verifie qu'une cle API est configuree. Retourne une reponse d'erreur ou None."""
    if not os.getenv(key_name):
        return jsonify({
            "error": f"Cle API manquante : {key_name}. "
                     f"Ajoutez-la dans les Secrets Replit (onglet cadenas).",
            "status": "error",
        }), 400
    return None


# ── Helper : lancer une commande CLI (avec support annulation) ───────────────

_current_process = None
_process_lock = threading.Lock()


def _run_cli(cmd_args, timeout=300):
    """Lance une commande main.py et retourne le resultat.

    Utilise Popen pour permettre l'annulation via /api/cancel.
    """
    global _current_process
    cmd = [sys.executable, "main.py"] + cmd_args
    try:
        with _process_lock:
            _current_process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(_THIS_DIR),
            )
        proc = _current_process
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

        # Extraire un message d'erreur lisible du stderr quand le process echoue
        if proc.returncode != 0 and stderr:
            # Chercher les lignes "Erreur : ..." produites par main.py
            for line in reversed(stderr.strip().splitlines()):
                # Nettoyer les codes ANSI
                clean = line
                clean = re.sub(r'\x1b\[[0-9;]*m', '', clean).strip()
                if clean.startswith("Erreur") or "API" in clean or "cle" in clean.lower():
                    result["error"] = clean
                    break
            if "error" not in result:
                # Derniere ligne nettoyee comme fallback
                last = stderr.strip().splitlines()[-1]
                clean = re.sub(r'\x1b\[[0-9;]*m', '', last).strip()
                if clean:
                    result["error"] = clean

        return result
    except Exception as e:
        return {"error": str(e), "status": "error"}
    finally:
        with _process_lock:
            _current_process = None


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
    """Annule la production en cours."""
    with _process_lock:
        proc = _current_process
    if proc and proc.poll() is None:
        proc.terminate()
        return jsonify({"status": "ok", "message": "Production annulee."})
    return jsonify({"status": "ok", "message": "Aucune production en cours."})


# ── Routes API (JSON) — Actions ─────────────────────────────────────────────


@app.route("/api/produire", methods=["POST"])
def api_produire():
    """Lance la production d'un episode."""
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

    return jsonify(_run_cli(cmd, timeout=600))


@app.route("/api/planifier-saison", methods=["POST"])
def api_planifier_saison():
    """Planifie une saison complete."""
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

    return jsonify(_run_cli(cmd, timeout=300))


@app.route("/api/produire-saison", methods=["POST"])
def api_produire_saison():
    """Produit les episodes d'une saison planifiee."""
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

    return jsonify(_run_cli(cmd, timeout=600))


@app.route("/api/reprendre", methods=["POST"])
def api_reprendre():
    """Reprend une production depuis un checkpoint."""
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

    return jsonify(_run_cli(cmd, timeout=600))


@app.route("/api/batch", methods=["POST"])
def api_batch():
    """Lance une production batch depuis un JSON envoye par le client."""
    import json as _json
    import tempfile

    body = request.get_json(force=True)
    episodes_list = body.get("episodes", [])
    dry_run = body.get("dry_run", False)

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
        cmd = ["batch", "-f", tmp_path, "--auto"]
        if dry_run:
            cmd.append("--dry-run")
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
