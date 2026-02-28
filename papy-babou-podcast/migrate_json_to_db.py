"""Script de migration — Importe les données JSON existantes dans PostgreSQL.

Usage:
    python migrate_json_to_db.py
    python main.py migrer-json-vers-db

Ce script lit tous les fichiers JSON existants et les importe dans PostgreSQL
sans rien supprimer. Les données JSON restent intactes après la migration.
"""

import json
import logging
from pathlib import Path

import config
import database
from db_models import (
    SaisonRepo,
    EpisodeRepo,
    ScriptRepo,
    HistoriqueRepo,
    PersonnageRepo,
    ProductionRepo,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def migrer_personnages() -> int:
    """Migre la bible des personnages depuis personnages.json."""
    count = 0
    chemin = config.PERSONNAGES_JSON_PATH
    if not chemin.exists():
        logger.info("Aucun fichier personnages.json trouvé")
        return 0

    with open(chemin, "r", encoding="utf-8") as f:
        bible = json.load(f)

    for pid, data in bible.get("personnages", {}).items():
        try:
            PersonnageRepo.sauvegarder(
                personnage_id=pid,
                data=data,
                voice_id=config.VOICE_IDS.get(pid, ""),
                pan=config.STEREO_PAN.get(pid, 0.0),
            )
            count += 1
            logger.info("  Personnage migré : %s", pid)
        except Exception as e:
            logger.error("  Erreur migration personnage %s : %s", pid, e)

    return count


def migrer_saisons() -> int:
    """Migre les plans de saisons depuis data/saisons/*.json."""
    count = 0
    for chemin in sorted(config.SAISONS_DIR.glob("saison_*.json")):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                plan = json.load(f)
            SaisonRepo.sauvegarder(plan)
            count += 1
            numero = plan.get("saison", {}).get("numero", "?")
            logger.info("  Saison %s migrée depuis %s", numero, chemin.name)
        except Exception as e:
            logger.error("  Erreur migration saison %s : %s", chemin.name, e)

    return count


def migrer_historique() -> int:
    """Migre l'historique des épisodes depuis data/historique_episodes.json."""
    count = 0
    chemin = config.HISTORIQUE_DIR / "historique_episodes.json"
    if not chemin.exists():
        logger.info("Aucun fichier historique_episodes.json trouvé")
        return 0

    with open(chemin, "r", encoding="utf-8") as f:
        historique = json.load(f)

    for entree in historique:
        try:
            HistoriqueRepo.ajouter(
                episode_id=entree.get("episode_id", ""),
                titre=entree.get("titre", ""),
                morale=entree.get("morale", ""),
                resume_court=entree.get("resume_court", ""),
                score_review=entree.get("score_review", 0),
                personnages_presents=entree.get("personnages_presents", []),
                moments_cles=entree.get("moments_cles", []),
                questions_ouvertes=entree.get("questions_ouvertes", []),
                evolutions_personnages=entree.get("evolutions_personnages", ""),
                ambiance=entree.get("ambiance", ""),
                type_episode=entree.get("type_episode", "standard"),
                date_production=entree.get("date_production", ""),
            )
            count += 1
            logger.info("  Historique migré : %s", entree.get("episode_id", "?"))
        except Exception as e:
            logger.error(
                "  Erreur migration historique %s : %s",
                entree.get("episode_id", "?"), e,
            )

    return count


def migrer_scripts() -> int:
    """Migre tous les scripts depuis scripts/episodes/*.json."""
    count = 0
    for chemin in sorted(config.SCRIPTS_DIR.glob("S*_v*.json")):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                script = json.load(f)

            # Extraire episode_id depuis le nom de fichier
            nom = chemin.stem  # ex: S01E01_v1
            parts = nom.split("_v")
            episode_id = parts[0] if parts else nom

            episode = script.get("episode", {})
            nb_mots = sum(
                len(s.get("texte", "").split())
                for s in episode.get("segments", [])
                if s.get("personnage") != "sfx"
            )

            ScriptRepo.sauvegarder(
                episode_id=episode_id,
                script=script,
                nb_mots=nb_mots,
                source="migration",
            )
            count += 1
            logger.info("  Script migré : %s", chemin.name)
        except Exception as e:
            logger.error("  Erreur migration script %s : %s", chemin.name, e)

    # Scripts validés
    for chemin in sorted(config.SCRIPTS_DIR.glob("S*_valide.json")):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                script = json.load(f)

            episode_id = chemin.stem.replace("_valide", "")
            episode = script.get("episode", {})
            nb_mots = sum(
                len(s.get("texte", "").split())
                for s in episode.get("segments", [])
                if s.get("personnage") != "sfx"
            )

            ScriptRepo.sauvegarder(
                episode_id=episode_id,
                script=script,
                nb_mots=nb_mots,
                is_validated=True,
                source="migration_validated",
            )
            count += 1
            logger.info("  Script validé migré : %s", chemin.name)
        except Exception as e:
            logger.error("  Erreur migration script validé %s : %s", chemin.name, e)

    return count


def migrer_checkpoints() -> int:
    """Migre les checkpoints existants (conservation complète)."""
    count = 0
    for chemin in sorted(config.CHECKPOINTS_DIR.glob("*_checkpoint*.json")):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                cp = json.load(f)

            episode_id = cp.get("episode_id", "")
            if not episode_id:
                continue

            data = cp.get("data", {})
            prod_id = ProductionRepo.creer(
                episode_id=episode_id,
                dry_run=data.get("dry_run", False),
            )

            status = "migrated"
            if "_done_" in chemin.name:
                status = "completed"

            ProductionRepo.maj_etape(
                prod_id,
                etape=cp.get("etape", "unknown"),
                rapport=data.get("rapport"),
                checkpoint_data=data,
            )

            if status == "completed":
                ProductionRepo.terminer(
                    prod_id,
                    rapport=data.get("rapport", {}),
                    couts={},
                )

            count += 1
            logger.info("  Checkpoint migré : %s (status=%s)", chemin.name, status)
        except Exception as e:
            logger.error("  Erreur migration checkpoint %s : %s", chemin.name, e)

    return count


def migrer_rapports() -> int:
    """Migre les rapports de production depuis logs/*_rapport.json."""
    count = 0
    for chemin in sorted(config.LOGS_DIR.glob("S*_rapport.json")):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                rapport = json.load(f)

            episode_id = rapport.get("episode_id", "")
            if not episode_id:
                continue

            # Créer un épisode si nécessaire
            EpisodeRepo.creer_ou_maj(
                episode_id=episode_id,
                saison=int(episode_id[1:3]) if len(episode_id) >= 3 else 0,
                numero=int(episode_id[4:6]) if len(episode_id) >= 6 else 0,
                titre=rapport.get("titre", ""),
                status="produced",
            )

            # Créer une production
            prod_id = ProductionRepo.creer(
                episode_id=episode_id,
                dry_run=rapport.get("dry_run", False),
            )
            ProductionRepo.terminer(
                prod_id,
                rapport=rapport,
                couts=rapport.get("couts", {}),
            )

            count += 1
            logger.info("  Rapport migré : %s", chemin.name)
        except Exception as e:
            logger.error("  Erreur migration rapport %s : %s", chemin.name, e)

    return count


def migrer_tout() -> None:
    """Exécute la migration complète JSON → PostgreSQL."""
    logger.info("=" * 60)
    logger.info("MIGRATION JSON → PostgreSQL")
    logger.info("=" * 60)

    # Initialiser le schéma
    database.initialiser_schema()
    logger.info("Schéma PostgreSQL prêt\n")

    # 1. Personnages
    logger.info("── Personnages ──")
    n = migrer_personnages()
    logger.info("  → %d personnage(s) migré(s)\n", n)

    # 2. Saisons
    logger.info("── Saisons ──")
    n = migrer_saisons()
    logger.info("  → %d saison(s) migrée(s)\n", n)

    # 3. Historique
    logger.info("── Historique ──")
    n = migrer_historique()
    logger.info("  → %d entrée(s) migrée(s)\n", n)

    # 4. Scripts
    logger.info("── Scripts ──")
    n = migrer_scripts()
    logger.info("  → %d script(s) migré(s)\n", n)

    # 5. Checkpoints
    logger.info("── Checkpoints ──")
    n = migrer_checkpoints()
    logger.info("  → %d checkpoint(s) migré(s)\n", n)

    # 6. Rapports
    logger.info("── Rapports ──")
    n = migrer_rapports()
    logger.info("  → %d rapport(s) migré(s)\n", n)

    # Statistiques finales
    logger.info("=" * 60)
    stats = database.obtenir_stats_db()
    logger.info("STATISTIQUES FINALES :")
    for table, count in stats.items():
        logger.info("  %-25s : %d enregistrements", table, count)
    logger.info("=" * 60)
    logger.info("Migration terminée avec succès !")


if __name__ == "__main__":
    migrer_tout()
