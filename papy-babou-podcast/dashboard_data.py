"""Module de données pour le dashboard — partagé entre CLI et Web.

Extrait et structure les données du dashboard pour éviter la duplication
entre la commande CLI (main.py) et le frontend web (web.py).
"""

import json
import logging
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def charger_historique_complet() -> list[dict]:
    """Charge tout l'historique des épisodes (DB prioritaire, JSON fallback)."""
    try:
        from database import DATABASE_URL
        if DATABASE_URL:
            from db_models import HistoriqueRepo
            rows = HistoriqueRepo.charger_tout()
            if rows:
                return rows
    except Exception:
        pass

    historique_path = config.HISTORIQUE_DIR / "historique.json"
    if historique_path.exists():
        with open(historique_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def charger_preferences() -> list[dict]:
    """Charge les préférences producteur."""
    if config.PREFERENCES_PATH.exists():
        with open(config.PREFERENCES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def charger_checkpoints() -> list[dict]:
    """Charge les checkpoints en attente."""
    checkpoints = []
    for cp_path in config.CHECKPOINTS_DIR.glob("*_checkpoint.json"):
        try:
            with open(cp_path, "r", encoding="utf-8") as f:
                cp = json.load(f)
            checkpoints.append({
                "episode_id": cp.get("episode_id", cp_path.stem),
                "etape": cp.get("etape", "?"),
                "timestamp": cp.get("timestamp", ""),
                "fichier": cp_path.name,
            })
        except (json.JSONDecodeError, FileNotFoundError):
            checkpoints.append({
                "episode_id": cp_path.stem,
                "etape": "?",
                "timestamp": "",
                "fichier": cp_path.name,
            })
    return checkpoints


def charger_publications() -> dict:
    """Charge les informations de publication (flux RSS, Buzzsprout)."""
    import os
    from xml.etree import ElementTree as ET

    result = {
        "rss_existe": False,
        "nb_episodes_rss": 0,
        "episodes_publies": [],
        "buzzsprout_configure": bool(os.getenv("BUZZSPROUT_API_KEY")) and bool(os.getenv("BUZZSPROUT_PODCAST_ID")),
        "podcast_config": {},
    }

    # Charger PODCAST_CONFIG
    if hasattr(config, "PODCAST_CONFIG"):
        pc = config.PODCAST_CONFIG
        result["podcast_config"] = {
            "titre": pc.get("titre", ""),
            "auteur": pc.get("auteur", ""),
            "site_web": pc.get("site_web", ""),
        }

    # Lire le flux RSS
    feed_path = config.RSS_DIR / "feed.xml"
    if feed_path.exists():
        result["rss_existe"] = True
        try:
            tree = ET.parse(str(feed_path))
            root = tree.getroot()
            channel = root.find("channel")
            if channel is not None:
                items = channel.findall("item")
                result["nb_episodes_rss"] = len(items)
                for item in items[-10:]:
                    title = item.find("title")
                    pub_date = item.find("pubDate")
                    enclosure = item.find("enclosure")
                    result["episodes_publies"].append({
                        "titre": title.text if title is not None else "?",
                        "date": pub_date.text if pub_date is not None else "",
                        "url_audio": enclosure.get("url", "") if enclosure is not None else "",
                    })
                result["episodes_publies"].reverse()
        except Exception as e:
            logger.warning("Erreur lecture flux RSS : %s", e)

    # Vérifier les rapports de production pour les publications
    for rapport_path in config.LOGS_DIR.glob("S*_rapport.json"):
        try:
            with open(rapport_path, "r", encoding="utf-8") as f:
                rapport = json.load(f)
            pub = rapport.get("etapes", {}).get("publication", {})
            if isinstance(pub, dict) and pub.get("url_audio"):
                # Déjà couvert par le RSS, mais on note les infos supplémentaires
                pass
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    return result


def calculer_couts(saison: int = 0) -> dict:
    """Calcule les coûts à partir des rapports JSON."""
    cout_total = 0.0
    total_chars = 0
    cout_par_service: dict[str, float] = {}

    pattern = f"S{saison:02d}*_rapport.json" if saison > 0 else "S*_rapport.json"
    for rapport_path in config.LOGS_DIR.glob(pattern):
        try:
            with open(rapport_path, "r", encoding="utf-8") as f:
                rapport = json.load(f)
            chars = rapport.get("etapes", {}).get("audio", {}).get("caracteres", {})
            if isinstance(chars, dict):
                total_chars += sum(chars.values())
            couts_ep = rapport.get("couts", {})
            for service, detail in couts_ep.items():
                if service == "total_estime" and isinstance(detail, (int, float)):
                    cout_total += detail
                elif isinstance(detail, dict):
                    cout_val = detail.get("cout", 0)
                    if isinstance(cout_val, (int, float)):
                        cout_par_service[service] = cout_par_service.get(service, 0) + cout_val
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    return {
        "total": cout_total,
        "total_chars": total_chars,
        "par_service": cout_par_service,
    }


def get_dashboard_data(saison: int = 0) -> dict:
    """Retourne toutes les données du dashboard sous forme structurée.

    Args:
        saison: Numéro de saison (0 = toutes).

    Returns:
        Dictionnaire contenant toutes les sections du dashboard.
    """
    historique = charger_historique_complet()

    # Filtrer par saison
    if saison > 0:
        prefix = f"S{saison:02d}"
        historique = [ep for ep in historique if ep.get("episode_id", "").startswith(prefix)]

    # Épisodes
    episodes = []
    for ep in historique:
        score_val = ep.get("score_review", 0)
        if not isinstance(score_val, (int, float)):
            score_val = 0
        episodes.append({
            "episode_id": ep.get("episode_id", "?"),
            "titre": ep.get("titre", "?"),
            "type_episode": ep.get("type_episode", "standard"),
            "score": round(score_val, 1),
            "ambiance": ep.get("ambiance", ""),
            "date": ep.get("date_production", ""),
            "morale": ep.get("morale", ""),
            "personnages": ep.get("personnages_presents", []),
            "retours_humains": ep.get("retours_humains", ""),
        })

    # Statistiques
    scores = [ep["score"] for ep in episodes if ep["score"] > 0]
    stats = {
        "nb_episodes": len(episodes),
        "score_moyen": round(sum(scores) / len(scores), 1) if scores else 0,
        "score_max": max(scores) if scores else 0,
        "score_min": min(scores) if scores else 0,
    }

    # Personnages
    personnages: dict[str, int] = {}
    for ep in episodes:
        for p in ep.get("personnages", []):
            personnages[p] = personnages.get(p, 0) + 1

    # Progression de saison
    progression = None
    if saison > 0:
        plan = config.charger_saison(saison)
        if plan:
            saison_data = plan.get("saison", {})
            episodes_plan = saison_data.get("episodes", [])
            episodes_produits = {ep["episode_id"] for ep in episodes}
            total_plan = len(episodes_plan)
            nb_produits = sum(
                1 for ep in episodes_plan
                if f"S{saison:02d}E{ep.get('numero', 0):02d}" in episodes_produits
            )
            progression = {
                "theme": saison_data.get("theme", ""),
                "fil_rouge": saison_data.get("fil_rouge", ""),
                "total": total_plan,
                "produits": nb_produits,
                "pourcentage": round((nb_produits / total_plan) * 100) if total_plan else 0,
                "episodes_plan": [
                    {
                        "numero": ep.get("numero", 0),
                        "titre": ep.get("titre", "?"),
                        "type": ep.get("type", "standard"),
                        "produit": f"S{saison:02d}E{ep.get('numero', 0):02d}" in episodes_produits,
                    }
                    for ep in episodes_plan
                ],
                "arcs_personnages": saison_data.get("arcs_personnages", {}),
                "plan_vs_prod": [
                    {
                        "episode_id": f"S{saison:02d}E{ep.get('numero', 0):02d}",
                        "titre": ep.get("titre", "?"),
                        "type": ep.get("type", "standard"),
                        "produit": f"S{saison:02d}E{ep.get('numero', 0):02d}" in episodes_produits,
                        "score": next(
                            (
                                e.get("score", 0)
                                for e in episodes
                                if e["episode_id"] == f"S{saison:02d}E{ep.get('numero', 0):02d}"
                            ),
                            None,
                        ),
                    }
                    for ep in episodes_plan
                ],
            }

    # Retours humains récents
    retours = [
        {"episode_id": ep["episode_id"], "retours": ep["retours_humains"]}
        for ep in episodes if ep.get("retours_humains")
    ][-5:]

    # Préférences
    preferences = charger_preferences()

    # Saisons disponibles
    saisons_dispo = config.liste_saisons()

    # Coûts
    couts = calculer_couts(saison)

    # Checkpoints
    checkpoints = charger_checkpoints()

    # Publications
    publications = charger_publications()

    return {
        "saison_filtre": saison,
        "episodes": episodes,
        "stats": stats,
        "personnages": personnages,
        "progression": progression,
        "retours_humains": retours,
        "preferences": preferences,
        "saisons_dispo": saisons_dispo,
        "couts": couts,
        "checkpoints": checkpoints,
        "publications": publications,
    }
