"""Repositories PostgreSQL — Couche d'accès aux données pour Papy Babou.

Chaque classe encapsule les opérations CRUD pour une entité.
Règles fondamentales :
  - JAMAIS de DELETE physique → soft-delete via deleted_at
  - Toutes les versions sont conservées (scripts, reviews, saisons)
  - Audit trail automatique via triggers PostgreSQL
"""

import json
import logging
from datetime import datetime, timezone

import psycopg2.extras

from database import get_cursor

logger = logging.getLogger(__name__)


# ── Saisons ──────────────────────────────────────────────────────────────────


class SaisonRepo:
    """Gestion des plans de saisons en PostgreSQL."""

    @staticmethod
    def sauvegarder(plan: dict) -> int:
        """Sauvegarde un plan de saison (crée une nouvelle version si existe déjà).

        Args:
            plan: Plan de saison complet (structure JSON).

        Returns:
            ID de l'enregistrement créé.
        """
        saison = plan.get("saison", {})
        numero = saison.get("numero", 0)

        # Déterminer la prochaine version
        with get_cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_v "
                "FROM saisons WHERE numero = %s",
                (numero,),
            )
            next_version = cur.fetchone()["next_v"]

            cur.execute(
                """INSERT INTO saisons
                   (numero, version, theme, description, fil_rouge,
                    plan_json, arcs_personnages, rituels, personnages_secondaires)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    numero,
                    next_version,
                    saison.get("theme", ""),
                    saison.get("description", ""),
                    saison.get("fil_rouge", ""),
                    json.dumps(plan, ensure_ascii=False),
                    json.dumps(saison.get("arcs_personnages", {}), ensure_ascii=False),
                    json.dumps(saison.get("rituels", {}), ensure_ascii=False),
                    json.dumps(saison.get("personnages_secondaires", []), ensure_ascii=False),
                ),
            )
            record_id = cur.fetchone()["id"]

        logger.info(
            "Saison %d v%d sauvegardée en DB (id=%d)",
            numero, next_version, record_id,
        )
        return record_id

    @staticmethod
    def charger(numero: int) -> dict:
        """Charge la dernière version du plan d'une saison.

        Args:
            numero: Numéro de la saison.

        Returns:
            Plan de saison ou dict vide.
        """
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT plan_json FROM saisons "
                "WHERE numero = %s AND deleted_at IS NULL "
                "ORDER BY version DESC LIMIT 1",
                (numero,),
            )
            row = cur.fetchone()
        if row:
            return row["plan_json"]
        return {}

    @staticmethod
    def charger_episode(saison: int, numero_episode: int) -> dict:
        """Charge les données d'un épisode depuis le plan de saison.

        Args:
            saison: Numéro de la saison.
            numero_episode: Numéro de l'épisode.

        Returns:
            Données de l'épisode ou dict vide.
        """
        plan = SaisonRepo.charger(saison)
        if not plan:
            return {}
        for ep in plan.get("saison", {}).get("episodes", []):
            if ep.get("numero") == numero_episode:
                return ep
        return {}

    @staticmethod
    def liste_saisons() -> list[int]:
        """Retourne la liste des numéros de saisons existantes."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT DISTINCT numero FROM saisons "
                "WHERE deleted_at IS NULL ORDER BY numero"
            )
            return [row["numero"] for row in cur.fetchall()]

    @staticmethod
    def historique_versions(numero: int) -> list[dict]:
        """Retourne l'historique des versions d'une saison.

        Args:
            numero: Numéro de la saison.

        Returns:
            Liste des versions avec métadonnées.
        """
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT id, version, theme, created_at FROM saisons "
                "WHERE numero = %s ORDER BY version DESC",
                (numero,),
            )
            return [dict(row) for row in cur.fetchall()]


# ── Épisodes ─────────────────────────────────────────────────────────────────


class EpisodeRepo:
    """Gestion des épisodes en PostgreSQL."""

    @staticmethod
    def creer_ou_maj(
        episode_id: str,
        saison: int,
        numero: int,
        titre: str,
        type_episode: str = "standard",
        resume: str = "",
        morale: str = "",
        ambiance: str = "",
        status: str = "planned",
        plan_data: dict | None = None,
    ) -> int:
        """Crée ou met à jour un épisode (upsert).

        Returns:
            ID de l'enregistrement.
        """
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO episodes
                   (episode_id, saison_numero, numero, titre, type_episode,
                    resume, morale, ambiance, status, plan_data)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (episode_id, saison_numero)
                   DO UPDATE SET
                     titre = EXCLUDED.titre,
                     type_episode = EXCLUDED.type_episode,
                     resume = EXCLUDED.resume,
                     morale = EXCLUDED.morale,
                     ambiance = EXCLUDED.ambiance,
                     status = EXCLUDED.status,
                     plan_data = EXCLUDED.plan_data
                   RETURNING id""",
                (
                    episode_id, saison, numero, titre, type_episode,
                    resume, morale, ambiance, status,
                    json.dumps(plan_data or {}, ensure_ascii=False),
                ),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def charger(episode_id: str) -> dict:
        """Charge un épisode par son identifiant."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT * FROM episodes WHERE episode_id = %s "
                "AND deleted_at IS NULL LIMIT 1",
                (episode_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else {}

    @staticmethod
    def maj_status(episode_id: str, status: str) -> None:
        """Met à jour le statut d'un épisode."""
        with get_cursor() as cur:
            cur.execute(
                "UPDATE episodes SET status = %s WHERE episode_id = %s",
                (status, episode_id),
            )


# ── Scripts ──────────────────────────────────────────────────────────────────


class ScriptRepo:
    """Gestion des scripts en PostgreSQL — toutes les versions conservées."""

    @staticmethod
    def sauvegarder(
        episode_id: str,
        script: dict,
        nb_mots: int = 0,
        is_validated: bool = False,
        source: str = "scripteur",
    ) -> int:
        """Sauvegarde une nouvelle version du script (jamais d'écrasement).

        Args:
            episode_id: Identifiant de l'épisode.
            script: Script JSON complet.
            nb_mots: Nombre de mots.
            is_validated: Si ce script est la version validée.
            source: Origine du script (scripteur, reviewer, humain).

        Returns:
            ID de l'enregistrement.
        """
        segments = script.get("episode", {}).get("segments", [])

        with get_cursor() as cur:
            # Prochaine version
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_v "
                "FROM scripts WHERE episode_id = %s",
                (episode_id,),
            )
            next_version = cur.fetchone()["next_v"]

            # Si on valide, dé-valider les versions précédentes
            if is_validated:
                cur.execute(
                    "UPDATE scripts SET is_validated = FALSE "
                    "WHERE episode_id = %s AND is_validated = TRUE",
                    (episode_id,),
                )

            cur.execute(
                """INSERT INTO scripts
                   (episode_id, version, script_json, nb_mots, nb_segments,
                    is_validated, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    episode_id,
                    next_version,
                    json.dumps(script, ensure_ascii=False),
                    nb_mots,
                    len(segments),
                    is_validated,
                    source,
                ),
            )
            record_id = cur.fetchone()["id"]

        logger.info(
            "Script %s v%d sauvegardé en DB (id=%d, validé=%s)",
            episode_id, next_version, record_id, is_validated,
        )
        return record_id

    @staticmethod
    def charger_valide(episode_id: str) -> dict:
        """Charge le script validé le plus récent."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT script_json FROM scripts "
                "WHERE episode_id = %s AND is_validated = TRUE "
                "ORDER BY version DESC LIMIT 1",
                (episode_id,),
            )
            row = cur.fetchone()
        return row["script_json"] if row else {}

    @staticmethod
    def charger_derniere_version(episode_id: str) -> dict:
        """Charge la dernière version du script (validée ou non)."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT script_json FROM scripts "
                "WHERE episode_id = %s ORDER BY version DESC LIMIT 1",
                (episode_id,),
            )
            row = cur.fetchone()
        return row["script_json"] if row else {}

    @staticmethod
    def historique(episode_id: str) -> list[dict]:
        """Retourne l'historique des versions d'un script."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT id, version, nb_mots, nb_segments, is_validated, "
                "source, created_at FROM scripts "
                "WHERE episode_id = %s ORDER BY version DESC",
                (episode_id,),
            )
            return [dict(row) for row in cur.fetchall()]


# ── Reviews ──────────────────────────────────────────────────────────────────


class ReviewRepo:
    """Gestion des reviews en PostgreSQL — toutes conservées."""

    @staticmethod
    def sauvegarder(
        episode_id: str,
        script_id: int,
        resultat_review: dict,
    ) -> int:
        """Sauvegarde une review complète.

        Args:
            episode_id: Identifiant de l'épisode.
            script_id: ID du script reviewé.
            resultat_review: Résultat complet de la review.

        Returns:
            ID de l'enregistrement.
        """
        review = resultat_review.get("review", {})
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO reviews
                   (script_id, episode_id, score, details_score,
                    corrections, alertes, script_corrige_json)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    script_id,
                    episode_id,
                    review.get("score", 0),
                    json.dumps(review.get("details_score", {}), ensure_ascii=False),
                    json.dumps(review.get("corrections", []), ensure_ascii=False),
                    json.dumps(review.get("alertes", []), ensure_ascii=False),
                    json.dumps(
                        resultat_review.get("episode"),
                        ensure_ascii=False,
                    ) if resultat_review.get("episode") else None,
                ),
            )
            return cur.fetchone()["id"]


# ── Productions (remplace les checkpoints) ───────────────────────────────────


class ProductionRepo:
    """Gestion des runs de production — JAMAIS supprimés (remplace checkpoint.unlink())."""

    @staticmethod
    def creer(
        episode_id: str,
        dry_run: bool = False,
        auto_mode: bool = False,
    ) -> int:
        """Crée une nouvelle production.

        Returns:
            ID de la production.
        """
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO productions
                   (episode_id, status, dry_run, auto_mode, etape_courante)
                   VALUES (%s, 'started', %s, %s, 'script')
                   RETURNING id""",
                (episode_id, dry_run, auto_mode),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def maj_etape(
        production_id: int,
        etape: str,
        rapport: dict | None = None,
        checkpoint_data: dict | None = None,
    ) -> None:
        """Met à jour l'étape courante et sauvegarde le checkpoint.

        Contrairement à l'ancien système, le checkpoint n'est JAMAIS supprimé.
        """
        with get_cursor() as cur:
            updates = ["etape_courante = %s", "status = %s"]
            # Les statuts "waiting_*" sont des statuts terminaux de workflow
            # (attente de validation humaine) — NE PAS suffixer "_done".
            if etape.startswith("waiting_"):
                params = [etape, etape]
            else:
                params = [etape, f"{etape}_done"]

            if rapport:
                updates.append("rapport_json = %s")
                params.append(json.dumps(rapport, ensure_ascii=False, default=str))

            if checkpoint_data:
                updates.append("checkpoint_data = %s")
                params.append(json.dumps(checkpoint_data, ensure_ascii=False, default=str))

            params.append(production_id)
            cur.execute(
                f"UPDATE productions SET {', '.join(updates)} WHERE id = %s",
                params,
            )

    @staticmethod
    def terminer(production_id: int, rapport: dict, couts: dict) -> None:
        """Marque une production comme terminée (JAMAIS supprimée)."""
        with get_cursor() as cur:
            cur.execute(
                """UPDATE productions SET
                   status = 'completed',
                   rapport_json = %s,
                   couts_json = %s,
                   completed_at = NOW()
                   WHERE id = %s""",
                (
                    json.dumps(rapport, ensure_ascii=False, default=str),
                    json.dumps(couts, ensure_ascii=False, default=str),
                    production_id,
                ),
            )

    @staticmethod
    def echouer(production_id: int, erreur: str) -> None:
        """Marque une production comme échouée (JAMAIS supprimée)."""
        with get_cursor() as cur:
            cur.execute(
                """UPDATE productions SET
                   status = 'failed',
                   checkpoint_data = COALESCE(checkpoint_data, '{}') || %s,
                   completed_at = NOW()
                   WHERE id = %s""",
                (
                    json.dumps({"erreur": erreur}, ensure_ascii=False),
                    production_id,
                ),
            )

    @staticmethod
    def charger_dernier_checkpoint(episode_id: str) -> dict | None:
        """Charge le dernier checkpoint non-terminé pour un épisode.

        Returns:
            Données du checkpoint ou None.
        """
        with get_cursor(commit=False) as cur:
            cur.execute(
                """SELECT id, etape_courante, rapport_json, checkpoint_data
                   FROM productions
                   WHERE episode_id = %s AND status NOT IN ('completed', 'failed')
                   ORDER BY started_at DESC LIMIT 1""",
                (episode_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def charger_par_id(production_id: int) -> dict | None:
        """Charge une production par son ID."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT * FROM productions WHERE id = %s",
                (production_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def lister_par_episode(episode_id: str) -> list[dict]:
        """Liste toutes les productions d'un épisode (historique complet)."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT id, status, dry_run, etape_courante, "
                "started_at, completed_at FROM productions "
                "WHERE episode_id = %s ORDER BY started_at DESC",
                (episode_id,),
            )
            return [dict(row) for row in cur.fetchall()]


# ── Métadonnées ──────────────────────────────────────────────────────────────


class MetadonneesRepo:
    """Gestion des métadonnées en PostgreSQL."""

    @staticmethod
    def sauvegarder(
        episode_id: str,
        meta: dict,
        production_id: int | None = None,
    ) -> int:
        """Sauvegarde les métadonnées (crée une nouvelle entrée, jamais d'écrasement).

        Returns:
            ID de l'enregistrement.
        """
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO metadonnees
                   (episode_id, production_id, meta_json, titre_complet,
                    description_courte, description_longue, tags,
                    cover_art_prompt, cover_art_path, transcript, duree_secondes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    episode_id,
                    production_id,
                    json.dumps(meta, ensure_ascii=False),
                    meta.get("titre", ""),
                    meta.get("description_courte", ""),
                    meta.get("description_longue", ""),
                    json.dumps(meta.get("tags", []), ensure_ascii=False),
                    meta.get("cover_art_prompt", ""),
                    meta.get("cover_art_path", ""),
                    meta.get("transcript", ""),
                    meta.get("duree_secondes", 0),
                ),
            )
            return cur.fetchone()["id"]


# ── Fichiers audio ───────────────────────────────────────────────────────────


class FichierAudioRepo:
    """Registre des fichiers audio générés — traçabilité complète."""

    @staticmethod
    def enregistrer(
        episode_id: str,
        type_fichier: str,
        chemin: str,
        production_id: int | None = None,
        segment_id: str = "",
        personnage: str = "",
        taille_bytes: int = 0,
        duree_secondes: float = 0,
        source: str = "",
        nb_caracteres: int = 0,
    ) -> int:
        """Enregistre un fichier audio dans le registre.

        Args:
            type_fichier: segment_voix, segment_sfx, episode_hq,
                         episode_preview, cover_art.
        """
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO fichiers_audio
                   (episode_id, production_id, type_fichier, segment_id,
                    personnage, chemin, taille_bytes, duree_secondes,
                    source, nb_caracteres)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    episode_id, production_id, type_fichier, segment_id,
                    personnage, chemin, taille_bytes, duree_secondes,
                    source, nb_caracteres,
                ),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def enregistrer_batch(fichiers: list[dict]) -> None:
        """Enregistre plusieurs fichiers audio en une seule transaction."""
        if not fichiers:
            return
        with get_cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """INSERT INTO fichiers_audio
                   (episode_id, production_id, type_fichier, segment_id,
                    personnage, chemin, taille_bytes, duree_secondes,
                    source, nb_caracteres)
                   VALUES (%(episode_id)s, %(production_id)s, %(type_fichier)s,
                           %(segment_id)s, %(personnage)s, %(chemin)s,
                           %(taille_bytes)s, %(duree_secondes)s,
                           %(source)s, %(nb_caracteres)s)""",
                fichiers,
            )


# ── Historique des épisodes ──────────────────────────────────────────────────


class HistoriqueRepo:
    """Historique des épisodes pour la continuité sérielle."""

    @staticmethod
    def ajouter(
        episode_id: str,
        titre: str,
        morale: str = "",
        resume_court: str = "",
        score_review: float = 0,
        personnages_presents: list | None = None,
        moments_cles: list | None = None,
        questions_ouvertes: list | None = None,
        evolutions_personnages: str = "",
        ambiance: str = "",
        type_episode: str = "standard",
        date_production: str = "",
        retours_humains: str = "",
    ) -> int:
        """Ajoute ou met à jour une entrée dans l'historique.

        Utilise UPSERT pour ne jamais perdre de données.

        Returns:
            ID de l'enregistrement.
        """
        dt_production = None
        if date_production:
            try:
                dt_production = datetime.fromisoformat(date_production)
            except (ValueError, TypeError):
                dt_production = datetime.now(timezone.utc)
        else:
            dt_production = datetime.now(timezone.utc)

        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO historique_episodes
                   (episode_id, titre, morale, resume_court, score_review,
                    personnages_presents, moments_cles, questions_ouvertes,
                    evolutions_personnages, ambiance, type_episode, date_production,
                    retours_humains)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (episode_id)
                   DO UPDATE SET
                     titre = EXCLUDED.titre,
                     morale = EXCLUDED.morale,
                     resume_court = EXCLUDED.resume_court,
                     score_review = EXCLUDED.score_review,
                     personnages_presents = EXCLUDED.personnages_presents,
                     moments_cles = EXCLUDED.moments_cles,
                     questions_ouvertes = EXCLUDED.questions_ouvertes,
                     evolutions_personnages = EXCLUDED.evolutions_personnages,
                     ambiance = EXCLUDED.ambiance,
                     type_episode = EXCLUDED.type_episode,
                     date_production = EXCLUDED.date_production,
                     retours_humains = EXCLUDED.retours_humains
                   RETURNING id""",
                (
                    episode_id,
                    titre,
                    morale,
                    resume_court,
                    score_review,
                    json.dumps(personnages_presents or [], ensure_ascii=False),
                    json.dumps(moments_cles or [], ensure_ascii=False),
                    json.dumps(questions_ouvertes or [], ensure_ascii=False),
                    evolutions_personnages,
                    ambiance,
                    type_episode,
                    dt_production,
                    retours_humains,
                ),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def charger_tout(saison: int | None = None) -> list[dict]:
        """Charge tout l'historique, optionnellement filtré par saison.

        Args:
            saison: Numéro de saison pour filtrer (None = tout).

        Returns:
            Liste des entrées d'historique (plus récent en premier).
        """
        with get_cursor(commit=False) as cur:
            if saison:
                prefix = f"S{saison:02d}"
                cur.execute(
                    "SELECT * FROM historique_episodes "
                    "WHERE episode_id LIKE %s AND deleted_at IS NULL "
                    "ORDER BY date_production DESC",
                    (f"{prefix}%",),
                )
            else:
                cur.execute(
                    "SELECT * FROM historique_episodes "
                    "WHERE deleted_at IS NULL "
                    "ORDER BY date_production DESC"
                )
            rows = cur.fetchall()

        # Convertir en format compatible avec l'ancien système
        result = []
        for row in rows:
            entry = dict(row)
            # Les champs JSONB sont déjà des objets Python via psycopg2
            result.append(entry)
        return result


# ── Personnages ──────────────────────────────────────────────────────────────


class PersonnageRepo:
    """Gestion de la bible des personnages — versionnée, jamais supprimée."""

    @staticmethod
    def sauvegarder(
        personnage_id: str,
        data: dict,
        voice_id: str = "",
        pan: float = 0.0,
    ) -> int:
        """Sauvegarde un personnage (nouvelle version si existe).

        Returns:
            ID de l'enregistrement.
        """
        with get_cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_v "
                "FROM personnages WHERE personnage_id = %s",
                (personnage_id,),
            )
            next_version = cur.fetchone()["next_v"]

            # Désactiver les anciennes versions
            if next_version > 1:
                cur.execute(
                    "UPDATE personnages SET is_active = FALSE "
                    "WHERE personnage_id = %s AND is_active = TRUE",
                    (personnage_id,),
                )

            cur.execute(
                """INSERT INTO personnages
                   (personnage_id, version, data_json, voice_id, pan, is_active)
                   VALUES (%s, %s, %s, %s, %s, TRUE)
                   RETURNING id""",
                (
                    personnage_id,
                    next_version,
                    json.dumps(data, ensure_ascii=False),
                    voice_id,
                    pan,
                ),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def charger_tous_actifs() -> dict:
        """Charge tous les personnages actifs.

        Returns:
            Dictionnaire {personnage_id: data_json}.
        """
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT personnage_id, data_json, voice_id, pan "
                "FROM personnages WHERE is_active = TRUE AND deleted_at IS NULL"
            )
            rows = cur.fetchall()

        result = {}
        for row in rows:
            result[row["personnage_id"]] = {
                "data": row["data_json"],
                "voice_id": row["voice_id"],
                "pan": row["pan"],
            }
        return result

    @staticmethod
    def charger_bible_complete() -> dict:
        """Charge la bible complète au format original (compatible personnages.json).

        Returns:
            Dict au format {"personnages": {...}, ...}.
        """
        personnages_actifs = PersonnageRepo.charger_tous_actifs()
        bible = {"personnages": {}}
        for pid, info in personnages_actifs.items():
            bible["personnages"][pid] = info["data"]
        return bible


# ── Coûts API ────────────────────────────────────────────────────────────────


class CoutRepo:
    """Suivi granulaire des coûts API — jamais supprimé."""

    @staticmethod
    def enregistrer(
        episode_id: str,
        service: str,
        cout_estime: float,
        detail: dict | None = None,
        production_id: int | None = None,
    ) -> int:
        """Enregistre un coût API.

        Args:
            service: elevenlabs_tts, elevenlabs_sfx, anthropic_claude, openai_dalle3.
        """
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO couts_api
                   (production_id, episode_id, service, detail, cout_estime)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    production_id,
                    episode_id,
                    service,
                    json.dumps(detail or {}, ensure_ascii=False),
                    cout_estime,
                ),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def total_par_episode(episode_id: str) -> float:
        """Retourne le coût total pour un épisode."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT COALESCE(SUM(cout_estime), 0) AS total "
                "FROM couts_api WHERE episode_id = %s",
                (episode_id,),
            )
            return float(cur.fetchone()["total"])

    @staticmethod
    def total_par_saison(saison: int) -> float:
        """Retourne le coût total pour une saison."""
        prefix = f"S{saison:02d}"
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT COALESCE(SUM(cout_estime), 0) AS total "
                "FROM couts_api WHERE episode_id LIKE %s",
                (f"{prefix}%",),
            )
            return float(cur.fetchone()["total"])

    @staticmethod
    def rapport_detaille(episode_id: str) -> list[dict]:
        """Rapport détaillé des coûts pour un épisode."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT service, cout_estime, detail, created_at "
                "FROM couts_api WHERE episode_id = %s "
                "ORDER BY created_at",
                (episode_id,),
            )
            return [dict(row) for row in cur.fetchall()]


# ── Publications ─────────────────────────────────────────────────────────────


class PublicationRepo:
    """Gestion des publications — jamais supprimées."""

    @staticmethod
    def enregistrer(
        episode_id: str,
        rapport_pub: dict,
        production_id: int | None = None,
    ) -> int:
        """Enregistre une publication.

        Returns:
            ID de l'enregistrement.
        """
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO publications
                   (episode_id, production_id, url_audio, transcript_url,
                    flux_rss_path, plateformes_notifiees, buzzsprout_response)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    episode_id,
                    production_id,
                    rapport_pub.get("url_audio", ""),
                    rapport_pub.get("transcript_url", ""),
                    rapport_pub.get("flux_rss", ""),
                    json.dumps(
                        rapport_pub.get("plateformes_notifiees", []),
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        rapport_pub.get("buzzsprout_response", {}),
                        ensure_ascii=False,
                    ),
                ),
            )
            return cur.fetchone()["id"]


# ── Audit ────────────────────────────────────────────────────────────────────


class AuditRepo:
    """Consultation du journal d'audit (lecture seule — les écritures sont via triggers)."""

    @staticmethod
    def consulter(
        table_name: str | None = None,
        record_id: int | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Consulte le journal d'audit.

        Args:
            table_name: Filtrer par table.
            record_id: Filtrer par enregistrement.
            limit: Nombre max de résultats.

        Returns:
            Entrées d'audit (les plus récentes d'abord).
        """
        conditions = []
        params: list = []

        if table_name:
            conditions.append("table_name = %s")
            params.append(table_name)
        if record_id:
            conditions.append("record_id = %s")
            params.append(record_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with get_cursor(commit=False) as cur:
            cur.execute(
                f"SELECT * FROM audit_log {where} "
                "ORDER BY created_at DESC LIMIT %s",
                params,
            )
            return [dict(row) for row in cur.fetchall()]


# ── Préférences producteur ──────────────────────────────────────────────────


class PreferencesRepo:
    """Mémoire persistante des préférences producteur en DB."""

    @staticmethod
    def ajouter(regle: str, categorie: str = "general", source_episode: str = "") -> int:
        """Ajoute une préférence.

        Returns:
            ID de l'enregistrement.
        """
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO preferences_producteur
                   (regle, categorie, source_episode)
                   VALUES (%s, %s, %s)
                   RETURNING id""",
                (regle, categorie, source_episode),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def charger_actives() -> list[dict]:
        """Charge toutes les préférences actives.

        Returns:
            Liste de dicts avec regle, categorie, source_episode, date_ajout.
        """
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT regle, categorie, source_episode, date_ajout "
                "FROM preferences_producteur "
                "WHERE is_active = TRUE "
                "ORDER BY date_ajout"
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def desactiver(regle_id: int) -> None:
        """Désactive une préférence (soft-delete)."""
        with get_cursor() as cur:
            cur.execute(
                "UPDATE preferences_producteur SET is_active = FALSE WHERE id = %s",
                (regle_id,),
            )


# ── Segments Audio (Back-office V2) ──────────────────────────────────────────


class SegmentAudioRepo:
    """Gestion des segments audio individuels pour le back-office V2.

    Chaque segment du script (voix ou SFX) a une ligne correspondante dans
    `segments_audio`. Permet le suivi granulaire de la génération TTS/SFX,
    l'édition de texte, la regénération individuelle et la validation.
    """

    @staticmethod
    def creer_depuis_script(episode_id: str, script: dict) -> int:
        """Crée les lignes segments_audio à partir d'un script JSON.

        Supprime d'abord les anciennes lignes pour cet épisode (reset complet),
        puis insère une ligne par segment du script.

        Args:
            episode_id: Identifiant de l'épisode (ex: "S01E01").
            script: Script JSON validé.

        Returns:
            Nombre de segments créés.
        """
        segments = script.get("episode", {}).get("segments", [])
        if not segments:
            return 0

        with get_cursor() as cur:
            # Reset complet : supprimer les anciennes lignes
            cur.execute(
                "DELETE FROM segments_audio WHERE episode_id = %s",
                (episode_id,),
            )

            rows = []
            for seg in segments:
                personnage = seg.get("personnage", "")
                is_sfx = personnage == "sfx"
                rows.append({
                    "episode_id": episode_id,
                    "segment_id": seg.get("id", ""),
                    "segment_type": "sfx" if is_sfx else "voix",
                    "personnage": personnage,
                    "texte": seg.get("texte", ""),
                    "texte_original": seg.get("texte", ""),
                    "ton": seg.get("ton", ""),
                    "rythme": seg.get("rythme", "normal"),
                    "sfx_prompt": seg.get("texte", "") if is_sfx else None,
                    "nb_caracteres": len(seg.get("texte", "")),
                    "status": "pending",
                    "version": 1,
                })

            if rows:
                psycopg2.extras.execute_batch(
                    cur,
                    """INSERT INTO segments_audio
                       (episode_id, segment_id, segment_type, personnage,
                        texte, texte_original, ton, rythme, sfx_prompt,
                        nb_caracteres, status, version)
                       VALUES (%(episode_id)s, %(segment_id)s, %(segment_type)s,
                               %(personnage)s, %(texte)s, %(texte_original)s,
                               %(ton)s, %(rythme)s, %(sfx_prompt)s,
                               %(nb_caracteres)s, %(status)s, %(version)s)""",
                    rows,
                )

        logger.info(
            "Segments audio créés pour %s : %d segments (%d voix, %d SFX)",
            episode_id,
            len(rows),
            sum(1 for r in rows if r["segment_type"] == "voix"),
            sum(1 for r in rows if r["segment_type"] == "sfx"),
        )
        return len(rows)

    @staticmethod
    def lister(
        episode_id: str,
        segment_type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Liste les segments audio d'un épisode avec filtres optionnels.

        Args:
            episode_id: Identifiant de l'épisode.
            segment_type: Filtrer par type ("voix", "sfx", ou None pour tous).
            status: Filtrer par statut (ex: "pending,error") ou None pour tous.

        Returns:
            Liste de segments triés par segment_id.
        """
        conditions = ["episode_id = %s"]
        params: list = [episode_id]

        if segment_type and segment_type != "all":
            conditions.append("segment_type = %s")
            params.append(segment_type)

        if status:
            statuses = [s.strip() for s in status.split(",")]
            placeholders = ", ".join(["%s"] * len(statuses))
            conditions.append(f"status IN ({placeholders})")
            params.extend(statuses)

        where = " AND ".join(conditions)

        with get_cursor(commit=False) as cur:
            cur.execute(
                f"SELECT * FROM segments_audio WHERE {where} "
                "ORDER BY segment_id",
                params,
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def charger(episode_id: str, segment_id: str) -> dict | None:
        """Charge un segment audio spécifique (version la plus récente).

        Returns:
            Dictionnaire du segment ou None si non trouvé.
        """
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT * FROM segments_audio "
                "WHERE episode_id = %s AND segment_id = %s "
                "ORDER BY version DESC LIMIT 1",
                (episode_id, segment_id),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def maj_status(
        episode_id: str,
        segment_id: str,
        status: str,
        audio_path: str | None = None,
        audio_os_key: str | None = None,
        duree_ms: int | None = None,
        nb_caracteres: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Met à jour le statut et les métadonnées audio d'un segment.

        Args:
            episode_id: Identifiant de l'épisode.
            segment_id: Identifiant du segment.
            status: Nouveau statut (pending, generating, generated, validated, error).
            audio_path: Chemin du fichier audio MP3 généré.
            audio_os_key: Clé Object Storage.
            duree_ms: Durée en millisecondes.
            nb_caracteres: Nombre de caractères du texte.
            error_message: Message d'erreur (si status=error).
        """
        updates = ["status = %s"]
        params: list = [status]

        if audio_path is not None:
            updates.append("audio_path = %s")
            params.append(audio_path)
        if audio_os_key is not None:
            updates.append("audio_os_key = %s")
            params.append(audio_os_key)
        if duree_ms is not None:
            updates.append("duree_ms = %s")
            params.append(duree_ms)
        if nb_caracteres is not None:
            updates.append("nb_caracteres = %s")
            params.append(nb_caracteres)
        if error_message is not None:
            updates.append("error_message = %s")
            params.append(error_message)

        params.extend([episode_id, segment_id])

        with get_cursor() as cur:
            cur.execute(
                f"UPDATE segments_audio SET {', '.join(updates)} "
                "WHERE episode_id = %s AND segment_id = %s "
                "AND version = (SELECT MAX(version) FROM segments_audio "
                "WHERE episode_id = %s AND segment_id = %s)",
                params + [episode_id, segment_id],
            )

    @staticmethod
    def maj_texte(episode_id: str, segment_id: str, texte: str) -> None:
        """Met à jour le texte d'un segment et le passe en pending.

        Incrémente la version pour traçabilité.
        """
        with get_cursor() as cur:
            cur.execute(
                "UPDATE segments_audio SET texte = %s, status = 'pending', "
                "version = version + 1, nb_caracteres = %s "
                "WHERE episode_id = %s AND segment_id = %s "
                "AND version = (SELECT MAX(version) FROM segments_audio "
                "WHERE episode_id = %s AND segment_id = %s)",
                (texte, len(texte), episode_id, segment_id,
                 episode_id, segment_id),
            )

    @staticmethod
    def progression(episode_id: str) -> dict:
        """Retourne la progression de génération audio pour un épisode.

        Returns:
            Dict avec total, pending, generating, generated, validated, errors, percent.
        """
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT status, COUNT(*) as cnt FROM segments_audio "
                "WHERE episode_id = %s GROUP BY status",
                (episode_id,),
            )
            rows = cur.fetchall()

        counts = {row["status"]: row["cnt"] for row in rows}
        total = sum(counts.values())
        done = counts.get("generated", 0) + counts.get("validated", 0)
        percent = round(done / total * 100) if total > 0 else 0

        return {
            "total": total,
            "pending": counts.get("pending", 0),
            "generating": counts.get("generating", 0),
            "generated": counts.get("generated", 0),
            "validated": counts.get("validated", 0),
            "errors": counts.get("error", 0),
            "percent": percent,
        }

    @staticmethod
    def valider_tous(episode_id: str) -> int:
        """Valide tous les segments générés d'un épisode.

        Returns:
            Nombre de segments validés.
        """
        with get_cursor() as cur:
            cur.execute(
                "UPDATE segments_audio SET status = 'validated' "
                "WHERE episode_id = %s AND status = 'generated' ",
                (episode_id,),
            )
            return cur.rowcount


# ── Montages (Back-office V2) ────────────────────────────────────────────────


class MontageRepo:
    """Gestion des montages audio assemblés pour le back-office V2.

    N montages par épisode, un seul publié à la fois (contrainte unique partielle).
    """

    @staticmethod
    def creer(episode_id: str) -> int:
        """Crée une nouvelle ligne montage en statut 'processing'.

        Returns:
            ID du montage créé.
        """
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO montages (episode_id, status)
                   VALUES (%s, 'processing')
                   RETURNING id""",
                (episode_id,),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def terminer(
        montage_id: int,
        audio_path_hq: str,
        audio_path_preview: str,
        duree_secondes: float,
        taille_bytes: int,
        nb_segments: int,
        chapitres_json: list | None = None,
        audio_os_key_hq: str | None = None,
        audio_os_key_preview: str | None = None,
    ) -> None:
        """Met à jour un montage après assemblage réussi."""
        with get_cursor() as cur:
            cur.execute(
                """UPDATE montages SET
                   status = 'completed',
                   audio_path_hq = %s,
                   audio_path_preview = %s,
                   duree_secondes = %s,
                   taille_bytes = %s,
                   nb_segments = %s,
                   chapitres_json = %s,
                   audio_os_key_hq = %s,
                   audio_os_key_preview = %s
                   WHERE id = %s""",
                (
                    audio_path_hq,
                    audio_path_preview,
                    duree_secondes,
                    taille_bytes,
                    nb_segments,
                    json.dumps(chapitres_json or [], ensure_ascii=False),
                    audio_os_key_hq,
                    audio_os_key_preview,
                    montage_id,
                ),
            )

    @staticmethod
    def echouer(montage_id: int, error_message: str) -> None:
        """Marque un montage comme échoué."""
        with get_cursor() as cur:
            cur.execute(
                "UPDATE montages SET status = 'error', error_message = %s WHERE id = %s",
                (error_message, montage_id),
            )

    @staticmethod
    def lister(episode_id: str) -> list[dict]:
        """Liste tous les montages d'un épisode (plus récent en premier)."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT * FROM montages WHERE episode_id = %s ORDER BY created_at DESC",
                (episode_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def charger(montage_id: int) -> dict | None:
        """Charge un montage par son ID."""
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT * FROM montages WHERE id = %s",
                (montage_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def publier(montage_id: int) -> None:
        """Publie un montage (un seul publié par épisode).

        Dépublie d'abord tous les montages de cet épisode, puis publie celui-ci.
        Met également à jour `episodes.published_montage_id`.
        """
        with get_cursor() as cur:
            # Récupérer l'episode_id
            cur.execute(
                "SELECT episode_id FROM montages WHERE id = %s",
                (montage_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Montage {montage_id} non trouvé")
            episode_id = row["episode_id"]

            # Dépublier tous les montages de cet épisode
            cur.execute(
                "UPDATE montages SET is_published = FALSE WHERE episode_id = %s",
                (episode_id,),
            )

            # Publier le montage sélectionné
            cur.execute(
                "UPDATE montages SET is_published = TRUE WHERE id = %s",
                (montage_id,),
            )

            # Mettre à jour episodes.published_montage_id
            cur.execute(
                "UPDATE episodes SET published_montage_id = %s WHERE episode_id = %s",
                (montage_id, episode_id),
            )

        logger.info("Montage %d publié pour %s", montage_id, episode_id)

    @staticmethod
    def depublier(montage_id: int) -> None:
        """Dépublie un montage."""
        with get_cursor() as cur:
            cur.execute(
                "SELECT episode_id FROM montages WHERE id = %s",
                (montage_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Montage {montage_id} non trouvé")
            episode_id = row["episode_id"]

            cur.execute(
                "UPDATE montages SET is_published = FALSE WHERE id = %s",
                (montage_id,),
            )
            cur.execute(
                "UPDATE episodes SET published_montage_id = NULL WHERE episode_id = %s",
                (episode_id,),
            )

        logger.info("Montage %d dépublié pour %s", montage_id, episode_id)
