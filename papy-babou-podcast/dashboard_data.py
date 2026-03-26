"""Module de données pour le dashboard — partagé entre CLI et Web.

Extrait et structure les données du dashboard pour éviter la duplication
entre la commande CLI (main.py) et le frontend web (web.py).

Stratégie de persistance :
  - PostgreSQL est la source primaire (survit aux redéploiements Replit)
  - Fichiers JSON en fallback uniquement si la DB est indisponible
"""

import json
import logging
import time
from pathlib import Path

import config

logger = logging.getLogger(__name__)

# ── Helper : vérifier si la DB est disponible ─────────────────────────────────

def _db_disponible() -> bool:
    """Vérifie si PostgreSQL est accessible."""
    try:
        from database import DATABASE_URL
        if not DATABASE_URL:
            return False
        from database import verifier_connexion
        return verifier_connexion()
    except Exception:
        return False


# ── Historique ─────────────────────────────────────────────────────────────────

def charger_historique_complet() -> list[dict]:
    """Charge tout l'historique des épisodes (fusion DB + JSON).

    Fusionne les deux sources pour ne jamais perdre d'épisodes :
    - DB peut avoir des entrées absentes du JSON (épisodes produits via web)
    - JSON peut avoir des entrées absentes de la DB (sync DB échouée)

    En cas de doublon (même episode_id), l'entrée la plus récente gagne.
    Retente une fois la connexion DB en cas d'échec (Neon scale-to-zero).
    """
    historique_db: list[dict] = []
    for attempt in range(2):
        try:
            from database import DATABASE_URL
            if DATABASE_URL:
                from db_models import HistoriqueRepo
                rows = HistoriqueRepo.charger_tout()
                if rows is not None:
                    historique_db = rows
                    break
        except Exception as e:
            logger.warning(
                "Échec chargement historique DB (tentative %d/2) : %s",
                attempt + 1, e,
            )
            if attempt == 0:
                time.sleep(1)  # Laisser Neon se réveiller

    # Charger aussi le JSON (toujours, pas seulement en fallback)
    historique_json: list[dict] = []
    historique_path = config.HISTORIQUE_DIR / "historique_episodes.json"
    if historique_path.exists():
        try:
            with open(historique_path, "r", encoding="utf-8") as f:
                historique_json = json.load(f)
        except Exception as e:
            logger.warning("Échec chargement historique JSON : %s", e)

    # Si une seule source, retourner directement
    if not historique_db:
        return historique_json
    if not historique_json:
        return historique_db

    # Fusionner : indexer par episode_id, préférer l'entrée la plus récente
    merged: dict[str, dict] = {}
    for ep in historique_db:
        eid = ep.get("episode_id", "")
        if eid:
            merged[eid] = ep

    for ep in historique_json:
        eid = ep.get("episode_id", "")
        if not eid:
            continue
        if eid not in merged:
            # Épisode absent de la DB → l'ajouter
            merged[eid] = ep
        else:
            # Doublon : comparer les dates de production
            db_date = merged[eid].get("date_production", "")
            json_date = ep.get("date_production", "")
            # Convertir en string pour comparaison
            if hasattr(db_date, "isoformat"):
                db_date = db_date.isoformat()
            if hasattr(json_date, "isoformat"):
                json_date = json_date.isoformat()
            # L'entrée JSON plus récente remplace la DB
            if json_date and json_date > str(db_date):
                merged[eid] = ep

    # Trier par date de production DESCENDANT (plus récent en premier)
    result = list(merged.values())
    result.sort(key=lambda x: str(x.get("date_production", "")), reverse=True)
    return result


# ── Rapports de production ─────────────────────────────────────────────────────

def charger_rapport(episode_id: str) -> dict | None:
    """Charge le rapport de production d'un épisode (DB prioritaire, JSON fallback).

    Retourne le rapport de la production LA PLUS RÉCENTE, quel que soit son statut.
    C'est crucial quand un épisode est re-produit après un nouveau plan de saison :
    la nouvelle production (waiting_script) doit primer sur l'ancienne (completed).
    """
    # 1. Essayer la DB — production la plus récente avec rapport
    if _db_disponible():
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                # Prendre la production la plus récente, tous statuts confondus
                cur.execute(
                    "SELECT rapport_json FROM productions "
                    "WHERE episode_id = %s AND rapport_json IS NOT NULL "
                    "ORDER BY started_at DESC LIMIT 1",
                    (episode_id,),
                )
                row = cur.fetchone()
                if row and row["rapport_json"]:
                    return row["rapport_json"]
        except Exception as e:
            logger.debug("DB indisponible pour rapport %s : %s", episode_id, e)

    # 2. Fallback fichier JSON (local puis Object Storage)
    rapport_path = config.LOGS_DIR / f"{episode_id}_rapport.json"
    if not rapport_path.exists():
        # Tenter de restaurer depuis Object Storage
        try:
            import persistent_storage
            persistent_storage.restore_rapport(episode_id, config.LOGS_DIR)
        except Exception:
            pass
    if rapport_path.exists():
        try:
            with open(rapport_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return None


def trouver_audio_batch(episode_ids: list) -> dict:
    """Lookup audio files for multiple episodes in a single pass.

    Lightweight alternative to trouver_fichier_audio() for the public API.
    Does ONE DB query + ONE filesystem glob instead of N individual lookups.
    Restores from Object Storage when files are missing locally (after redeploy).

    Returns: {episode_id: {"hq": filename_or_None, "preview": filename_or_None}}
    """
    if not episode_ids:
        return {}

    result = {eid: {"hq": None, "preview": None} for eid in episode_ids}

    # Track DB paths for Object Storage restoration
    _db_paths = {}  # episode_id -> {type_fichier: chemin}

    # 1. Single DB query for all episodes at once
    if _db_disponible():
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT episode_id, type_fichier, chemin "
                    "FROM fichiers_audio "
                    "WHERE episode_id = ANY(%s) "
                    "AND type_fichier IN ('episode_hq', 'episode_preview') "
                    "ORDER BY created_at DESC",
                    (list(episode_ids),),
                )
                for row in cur.fetchall():
                    eid = row["episode_id"]
                    if eid not in result:
                        continue
                    p = Path(row["chemin"])
                    # Track DB path for later restoration
                    if eid not in _db_paths:
                        _db_paths[eid] = {}
                    if row["type_fichier"] not in _db_paths[eid]:
                        _db_paths[eid][row["type_fichier"]] = row["chemin"]
                    if p.exists():
                        if row["type_fichier"] == "episode_preview" and not result[eid]["preview"]:
                            result[eid]["preview"] = p.name
                        elif row["type_fichier"] == "episode_hq" and not result[eid]["hq"]:
                            result[eid]["hq"] = p.name
        except Exception as e:
            logger.debug("DB batch audio lookup failed: %s", e)

    # 2. Object Storage restoration for episodes with DB paths but missing files
    _needs_restore = [
        eid for eid in episode_ids
        if not result[eid]["preview"] and not result[eid]["hq"] and eid in _db_paths
    ]
    if _needs_restore:
        try:
            from persistent_storage import restore_episode_audio
            for eid in _needs_restore:
                restored = restore_episode_audio(eid, config.OUTPUT_DIR)
                if restored:
                    # Re-check the DB paths after restoration
                    for type_fichier, chemin in _db_paths[eid].items():
                        p = Path(chemin)
                        if p.exists():
                            if type_fichier == "episode_preview" and not result[eid]["preview"]:
                                result[eid]["preview"] = p.name
                            elif type_fichier == "episode_hq" and not result[eid]["hq"]:
                                result[eid]["hq"] = p.name
        except Exception as e:
            logger.debug("Object Storage batch restore failed: %s", e)

    # 3. Filesystem fallback for episodes still missing audio
    missing = [eid for eid in episode_ids if not result[eid]["preview"] and not result[eid]["hq"]]
    if missing and config.OUTPUT_DIR.exists():
        # Single glob for all mp3 files, then match to episodes
        all_mp3 = {f.name: f for f in config.OUTPUT_DIR.glob("*.mp3")}
        for eid in missing:
            for suffix, key in [("_128k.mp3", "preview"), ("_192k.mp3", "hq")]:
                for fname, fpath in all_mp3.items():
                    if fname.startswith(eid) and fname.endswith(suffix):
                        result[eid][key] = fname
                        break

    return result


def trouver_fichier_audio(episode_id: str) -> dict:
    """Trouve les fichiers audio d'un épisode (preview et HQ).

    Cherche d'abord dans la DB (survit aux redéploiements), puis dans le
    rapport JSON, puis par convention de nommage sur le système de fichiers.
    """
    result = {"preview": None, "hq": None, "duree_secondes": None, "taille_mb": None}

    # 1. Chercher dans la DB (fichiers_audio + productions)
    rapport = charger_rapport(episode_id)

    if rapport:
        montage = rapport.get("etapes", {}).get("montage", {})
        if montage:
            result["duree_secondes"] = montage.get("duree_secondes")
            result["taille_mb"] = montage.get("taille_mb")

            # Vérifier que les fichiers existent encore sur le filesystem
            for key, rapport_key in [("preview", "chemin_preview"), ("hq", "chemin_hq")]:
                chemin = montage.get(rapport_key)
                if chemin:
                    p = Path(chemin)
                    if p.exists():
                        result[key] = p.name
                    else:
                        # Fichier absent (re-deploy Replit) — stocker le nom pour info
                        # mais marquer comme manquant pour affichage dans le dashboard
                        result[f"{key}_missing"] = p.name

        # Validation info
        etapes = rapport.get("etapes", {})
        result["validation_script"] = etapes.get("script", {}).get("validation_humaine", False)
        result["validation_montage"] = etapes.get("montage", {}).get("validation_humaine", False)
        result["publication"] = etapes.get("publication", {})

    # 2. Si pas d'audio trouvé, chercher dans la table fichiers_audio (DB)
    if not result["preview"] and not result["hq"] and _db_disponible():
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT type_fichier, chemin, duree_secondes, taille_bytes "
                    "FROM fichiers_audio "
                    "WHERE episode_id = %s AND type_fichier IN ('episode_hq', 'episode_preview') "
                    "ORDER BY created_at DESC",
                    (episode_id,),
                )
                rows = cur.fetchall()
            for row in rows:
                p = Path(row["chemin"])
                if not result["duree_secondes"] and row["duree_secondes"]:
                    result["duree_secondes"] = row["duree_secondes"]
                if row["type_fichier"] == "episode_hq":
                    if not result["taille_mb"] and row["taille_bytes"]:
                        result["taille_mb"] = round(row["taille_bytes"] / (1024 * 1024), 2)
                # N'assigner que si le fichier existe réellement sur le filesystem
                # sinon stocker comme missing et laisser step 4 (Object Storage) restaurer
                if p.exists():
                    if row["type_fichier"] == "episode_preview":
                        result["preview"] = p.name
                    elif row["type_fichier"] == "episode_hq":
                        result["hq"] = p.name
                else:
                    key = "preview" if row["type_fichier"] == "episode_preview" else "hq"
                    result[f"{key}_missing"] = p.name
        except Exception as e:
            logger.debug("DB indisponible pour fichiers audio %s : %s", episode_id, e)

    # 3. Fallback: chercher par convention de nommage dans output/episodes/
    if not result["preview"] and not result["hq"]:
        episodes_dir = config.OUTPUT_DIR
        if episodes_dir.exists():
            for suffix, key in [("_128k.mp3", "preview"), ("_192k.mp3", "hq")]:
                candidates = list(episodes_dir.glob(f"{episode_id}*{suffix}"))
                if candidates:
                    result[key] = candidates[0].name

    # 4. Object Storage: restaurer les fichiers audio manquants
    if not result["preview"] and not result["hq"]:
        try:
            import persistent_storage
            if persistent_storage.is_available():
                restored = persistent_storage.restore_episode_audio(
                    episode_id, config.OUTPUT_DIR,
                )
                if restored.get("hq"):
                    result["hq"] = restored["hq"].name
                    # Effacer le flag missing puisque le fichier est restauré
                    result.pop("hq_missing", None)
                if restored.get("preview"):
                    result["preview"] = restored["preview"].name
                    result.pop("preview_missing", None)
                if restored.get("hq") or restored.get("preview"):
                    logger.info(
                        "Audio %s restauré depuis Object Storage.", episode_id,
                    )
        except Exception as e:
            logger.debug("Object Storage indisponible pour audio %s : %s", episode_id, e)

    return result


# ── Préférences producteur ─────────────────────────────────────────────────────

def charger_preferences() -> list[dict]:
    """Charge les préférences producteur (DB prioritaire, JSON fallback)."""
    if _db_disponible():
        try:
            from db_models import PreferencesRepo
            prefs = PreferencesRepo.charger_actives()
            if prefs is not None:
                # Convertir les datetime en strings pour JSON serialization
                for p in prefs:
                    if "date_ajout" in p and hasattr(p["date_ajout"], "isoformat"):
                        p["date_ajout"] = p["date_ajout"].isoformat()
                return prefs
        except Exception as e:
            logger.debug("DB indisponible pour preferences : %s", e)

    if config.PREFERENCES_PATH.exists():
        with open(config.PREFERENCES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ── Checkpoints ────────────────────────────────────────────────────────────────

def charger_checkpoints() -> list[dict]:
    """Charge les checkpoints en attente (DB prioritaire, JSON fallback)."""
    if _db_disponible():
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT id, episode_id, etape_courante, started_at, status "
                    "FROM productions "
                    "WHERE status NOT IN ('completed', 'failed') "
                    "ORDER BY started_at DESC"
                )
                rows = cur.fetchall()
            if rows is not None:
                return [
                    {
                        "episode_id": row["episode_id"],
                        "etape": row["etape_courante"],
                        "timestamp": row["started_at"].isoformat() if hasattr(row["started_at"], "isoformat") else str(row["started_at"]),
                        "fichier": f"production_db_{row['id']}",
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.debug("DB indisponible pour checkpoints : %s", e)

    # Fallback fichiers JSON
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


# ── Publications ───────────────────────────────────────────────────────────────

def charger_publications() -> dict:
    """Charge les informations de publication (DB prioritaire, RSS/JSON fallback)."""
    import os

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

    # 1. Essayer la DB
    if _db_disponible():
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT episode_id, url_audio, published_at "
                    "FROM publications "
                    "ORDER BY published_at DESC LIMIT 10"
                )
                rows = cur.fetchall()
            if rows:
                result["rss_existe"] = True
                result["nb_episodes_rss"] = len(rows)
                for row in rows:
                    result["episodes_publies"].append({
                        "titre": row["episode_id"],
                        "date": row["published_at"].isoformat() if hasattr(row["published_at"], "isoformat") else str(row["published_at"]),
                        "url_audio": row.get("url_audio", ""),
                    })
                return result
        except Exception as e:
            logger.debug("DB indisponible pour publications : %s", e)

    # 2. Fallback: lire le flux RSS
    from xml.etree import ElementTree as ET
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

    return result


# ── Coûts ──────────────────────────────────────────────────────────────────────

def calculer_couts(saison: int = 0) -> dict:
    """Calcule les coûts (DB prioritaire, rapports JSON fallback)."""
    # 1. Essayer la DB
    if _db_disponible():
        try:
            from database import get_cursor
            with get_cursor(commit=False) as cur:
                if saison > 0:
                    prefix = f"S{saison:02d}%"
                    cur.execute(
                        "SELECT COALESCE(SUM(cout_estime), 0) AS total "
                        "FROM couts_api WHERE episode_id LIKE %s",
                        (prefix,),
                    )
                else:
                    cur.execute("SELECT COALESCE(SUM(cout_estime), 0) AS total FROM couts_api")
                total = float(cur.fetchone()["total"])

                # Coûts par service
                if saison > 0:
                    cur.execute(
                        "SELECT service, SUM(cout_estime) AS total "
                        "FROM couts_api WHERE episode_id LIKE %s "
                        "GROUP BY service",
                        (prefix,),
                    )
                else:
                    cur.execute(
                        "SELECT service, SUM(cout_estime) AS total "
                        "FROM couts_api GROUP BY service"
                    )
                par_service = {row["service"]: float(row["total"]) for row in cur.fetchall()}

                # Total caractères depuis les rapports en DB
                total_chars = 0
                if saison > 0:
                    cur.execute(
                        "SELECT rapport_json FROM productions "
                        "WHERE episode_id LIKE %s AND status = 'completed'",
                        (prefix,),
                    )
                else:
                    cur.execute(
                        "SELECT rapport_json FROM productions WHERE status = 'completed'"
                    )
                for row in cur.fetchall():
                    rapport = row.get("rapport_json") or {}
                    chars = rapport.get("etapes", {}).get("audio", {}).get("caracteres", {})
                    if isinstance(chars, dict):
                        total_chars += sum(v for v in chars.values() if isinstance(v, (int, float)))

            if total > 0 or par_service:
                return {
                    "total": total,
                    "total_chars": total_chars,
                    "par_service": par_service,
                }
        except Exception as e:
            logger.debug("DB indisponible pour couts : %s", e)

    # 2. Fallback: rapports JSON
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


# ── Données complètes du dashboard ────────────────────────────────────────────

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
        episode_id = ep.get("episode_id", "?")
        audio_info = trouver_fichier_audio(episode_id)
        # date_production peut être un datetime (depuis la DB) ou une string (depuis JSON)
        date_val = ep.get("date_production", "")
        if hasattr(date_val, "isoformat"):
            date_val = date_val.isoformat()
        episodes.append({
            "episode_id": episode_id,
            "titre": ep.get("titre", "?"),
            "type_episode": ep.get("type_episode", "standard"),
            "score": round(score_val, 1),
            "ambiance": ep.get("ambiance", ""),
            "date": date_val,
            "morale": ep.get("morale", ""),
            "personnages": ep.get("personnages_presents", []),
            "retours_humains": ep.get("retours_humains", ""),
            "audio_preview": audio_info.get("preview"),
            "audio_hq": audio_info.get("hq"),
            "duree_secondes": audio_info.get("duree_secondes"),
            "taille_mb": audio_info.get("taille_mb"),
            "validation_script": audio_info.get("validation_script", False),
            "validation_montage": audio_info.get("validation_montage", False),
            "audio_missing": bool(audio_info.get("hq_missing") or audio_info.get("preview_missing")),
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

    # Saisons disponibles (avec info theme/nb_episodes pour le formulaire)
    saisons_dispo = config.liste_saisons()
    saisons_info = {}
    for num in saisons_dispo:
        plan = config.charger_saison(num)
        if plan:
            sd = plan.get("saison", {})
            saisons_info[num] = {
                "theme": sd.get("theme", ""),
                "nb_episodes": len(sd.get("episodes", [])),
                "description": sd.get("description", ""),
            }

    # Coûts
    couts = calculer_couts(saison)

    # Checkpoints
    checkpoints = charger_checkpoints()

    # Publications
    publications = charger_publications()

    # Vérifier la persistance
    persistence_warning = None
    has_db = _db_disponible()
    has_os = False
    try:
        import persistent_storage
        has_os = persistent_storage.is_available()
    except Exception:
        pass
    if not has_db and not has_os:
        persistence_warning = (
            "Aucun système de persistance actif (ni PostgreSQL ni Object Storage). "
            "Les données seront perdues au prochain redéploiement !"
        )

    return {
        "saison_filtre": saison,
        "episodes": episodes,
        "stats": stats,
        "personnages": personnages,
        "progression": progression,
        "retours_humains": retours,
        "preferences": preferences,
        "saisons_dispo": saisons_dispo,
        "saisons_info": saisons_info,
        "couts": couts,
        "checkpoints": checkpoints,
        "publications": publications,
        "persistence_warning": persistence_warning,
    }
