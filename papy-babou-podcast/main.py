"""Orchestrateur principal — Pipeline de production sérielle du podcast Papy Babou.

Usage:
    python main.py produire -e "Le buisson ardent" -s 1 -n 2 -r "..." -m "..."
    python main.py produire -e "..." -s 1 -n 1 -r "..." --dry-run
    python main.py interactif
    python main.py batch -f planning.json
    python main.py planifier-saison -s 1 -t "Les grands voyages de la Bible"
    python main.py produire-saison -s 1 --auto
    python main.py produire-saison -s 1 -e "1,2,3" --dry-run
    python main.py dashboard
    python main.py dashboard -s 1
    python main.py reprendre -c checkpoints/S01E01_checkpoint.json
"""

import json
import logging
import os
import signal
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.prompt import Prompt
from rich.style import Style

import config
from utils import fichier_lock, ouvrir_fichier, slug as _slug
from agents import (
    Scripteur, Reviewer, ProducteurAudio, SfxProvider, Monteur,
    Metadonnees, Publisher, CoverArt, Planificateur, DirecteurPodcast,
)
from theme import (
    Palette, Icons, Typo, NOMS_PERSONNAGES_STYLED,
    creer_console, banner, get_rich_theme,
    panel_episode, panel_episode_saison, panel_validation, panel_erreur,
    panel_succes, panel_info, panel_rapport_final,
    panel_roadmap, panel_separateur_episode,
    table_review, table_episodes_dashboard, ajouter_episode_dashboard,
    table_saison_plan, table_couts, table_db_status,
    progression_saison, stats_block, personnages_block,
    afficher_script,
)

# Import optionnel PostgreSQL (fallback gracieux vers JSON)
try:
    import database
    from db_models import (
        SaisonRepo, EpisodeRepo, ScriptRepo, ReviewRepo,
        ProductionRepo, MetadonneesRepo, FichierAudioRepo,
        HistoriqueRepo, PersonnageRepo, CoutRepo, PublicationRepo,
        AuditRepo, PreferencesRepo,
    )
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

console = creer_console()

# ── Configuration du logging ──────────────────────────────────────────────────

LOG_FILE = config.LOGS_DIR / "production.log"


def configurer_logging() -> None:
    """Configure le logging avec sortie console (Rich) et fichier.

    Utilise force=True pour écraser toute configuration antérieure
    (imports de bibliothèques qui appellent logging avant nous).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True),
            logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        ],
        force=True,
    )
    # Ajouter un handler stderr explicite pour les subprocesses
    # Rich Console peut ne pas flusher correctement quand stdout est un PIPE.
    # Ce handler garantit que les messages INFO+ arrivent dans stderr,
    # capturé par _stream_reader dans web.py.
    # Vérifier qu'on n'ajoute pas un doublon (appels multiples de configurer_logging).
    _root = logging.getLogger()
    _has_stderr = any(
        isinstance(h, logging.StreamHandler)
        and getattr(h, "_is_papy_stderr", False)
        for h in _root.handlers
    )
    if not _has_stderr:
        _stderr_handler = logging.StreamHandler(sys.stderr)
        _stderr_handler.setLevel(logging.INFO)
        _stderr_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
        _stderr_handler._is_papy_stderr = True  # tag pour détection doublon
        _root.addHandler(_stderr_handler)


def initialiser_db() -> bool:
    """Initialise la base de données PostgreSQL si disponible.

    Returns:
        True si la DB est prête.
    """
    if not _DB_AVAILABLE:
        return False
    try:
        if not database.DATABASE_URL:
            return False
        database.initialiser_schema()
        console.print(f"[{Palette.SUCCES}]  PostgreSQL connecté et schéma initialisé.[/]")
        return True
    except Exception as e:
        console.print(f"[yellow]  PostgreSQL indisponible : {e}[/yellow]")
        console.print("[yellow]  Mode fichiers JSON activé (rétrocompatibilité)[/yellow]")
        return False


logger = logging.getLogger("papy-babou")


# ── Historique des épisodes ──────────────────────────────────────────────────

HISTORIQUE_PATH = config.HISTORIQUE_DIR / "historique_episodes.json"


def _use_db() -> bool:
    """Vérifie si PostgreSQL est disponible et initialisé."""
    if not _DB_AVAILABLE:
        return False
    try:
        return database.verifier_connexion()
    except Exception:
        return False


def charger_historique() -> list[dict]:
    """Charge l'historique des épisodes produits (DB prioritaire, JSON fallback)."""
    if _use_db():
        try:
            return HistoriqueRepo.charger_tout()
        except Exception as e:
            logger.warning("DB indisponible pour historique : %s", e)

    # Fallback JSON
    if HISTORIQUE_PATH.exists():
        with open(HISTORIQUE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _episodes_deja_produits(
    saison_num: int,
    episodes_plan: list[dict],
) -> set[str]:
    """Retourne les episode_id déjà produits ET dont l'histoire n'a pas changé.

    Compare l'histoire_biblique du plan actuel avec celle de l'historique.
    Si le plan a changé (nouvelle histoire pour le même numéro), l'épisode
    est considéré comme NON produit — il faut le re-produire.
    """
    historique = charger_historique()

    # Index historique : episode_id → titre de l'historique
    hist_par_id: dict[str, str] = {}
    for h in historique:
        eid = h.get("episode_id", "")
        if eid.startswith(f"S{saison_num:02d}"):
            hist_par_id[eid] = h.get("titre", "")

    deja: set[str] = set()
    for ep in episodes_plan:
        ep_id = f"S{saison_num:02d}E{ep['numero']:02d}"
        if ep_id not in hist_par_id:
            continue
        # Comparer le titre du plan avec celui de l'historique
        titre_plan = ep.get("titre", "")
        titre_hist = hist_par_id[ep_id]
        # Si le titre a changé, l'épisode a changé → pas "déjà produit"
        if titre_plan and titre_hist and titre_plan != titre_hist:
            logger.info(
                "Épisode %s : plan changé ('%s' → '%s') — sera re-produit",
                ep_id, titre_hist, titre_plan,
            )
            continue
        deja.add(ep_id)

    return deja


def sauvegarder_historique(historique: list[dict]) -> None:
    """Sauvegarde l'historique des épisodes (JSON — rétrocompatibilité).

    Utilise une écriture atomique pour éviter la corruption si crash mid-write.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", dir=HISTORIQUE_PATH.parent, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp:
        json.dump(historique, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, HISTORIQUE_PATH)


# ── Préférences producteur (mémoire persistante) ────────────────────────────


def charger_preferences() -> list[dict]:
    """Charge les preferences du producteur depuis le fichier JSON.

    Returns:
        Liste de regles/preferences persistantes.
    """
    if config.PREFERENCES_PATH.exists():
        try:
            with open(config.PREFERENCES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Fichier préférences corrompu (%s) : %s — ignoré",
                           config.PREFERENCES_PATH, e)
    return []


def sauvegarder_preferences(preferences: list[dict]) -> None:
    """Sauvegarde les preferences du producteur."""
    with fichier_lock(config.PREFERENCES_PATH):
        with open(config.PREFERENCES_PATH, "w", encoding="utf-8") as f:
            json.dump(preferences, f, ensure_ascii=False, indent=2)


def ajouter_preference(regle: str, source_episode: str = "", categorie: str = "general") -> None:
    """Ajoute une preference/regle du producteur a la memoire persistante.

    Args:
        regle: La regle ou preference en texte libre.
        source_episode: Episode d'ou vient cette preference.
        categorie: Categorie (style, ton, structure, personnages, technique, general).
    """
    # Stocker en DB si disponible
    if _use_db():
        try:
            PreferencesRepo.ajouter(regle, categorie=categorie, source_episode=source_episode)
        except Exception as e:
            logger.warning("DB indisponible pour préférence : %s", e)

    # Toujours sauvegarder en JSON (rétrocompatibilité)
    with fichier_lock(config.PREFERENCES_PATH):
        preferences = []
        if config.PREFERENCES_PATH.exists():
            with open(config.PREFERENCES_PATH, "r", encoding="utf-8") as f:
                preferences = json.load(f)
        preferences.append({
            "regle": regle,
            "categorie": categorie,
            "source_episode": source_episode,
            "date_ajout": datetime.now().isoformat(),
        })
        with open(config.PREFERENCES_PATH, "w", encoding="utf-8") as f:
            json.dump(preferences, f, ensure_ascii=False, indent=2)
    logger.info("Preference producteur ajoutee : %s", regle[:80])


def _construire_bloc_preferences() -> str:
    """Construit le bloc de preferences producteur pour injection dans les prompts.

    Returns:
        Texte formate pour inclusion dans un system prompt LLM.
    """
    preferences = charger_preferences()
    if not preferences:
        return ""

    lignes = ["\nPRÉFÉRENCES DU PRODUCTEUR (à respecter impérativement) :"]
    for i, pref in enumerate(preferences, 1):
        lignes.append(f"  {i}. {pref.get('regle', '(règle manquante)')}")
    return "\n".join(lignes)


def _appliquer_instructions_montage(
    script: dict, instructions: str, episode_id: str
) -> dict:
    """Modifie le script selon les instructions du producteur pour le montage.

    Utilise Claude pour interpréter les instructions en langage naturel et
    adapter les paramètres du script qui affectent le montage : pause_apres_ms,
    ton, rythme, mode SFX, ambiance_par_acte.

    Le script modifié est sauvegardé comme nouvelle version validée.

    Args:
        script: Script JSON validé actuel.
        instructions: Instructions en texte libre du producteur.
        episode_id: Identifiant de l'épisode (pour la sauvegarde).

    Returns:
        Script modifié avec les ajustements demandés.
    """
    import anthropic
    from utils import parser_json_llm

    client = anthropic.Anthropic()

    # Extraire les segments actuels pour contexte
    segments = script.get("episode", {}).get("segments", [])
    segments_resume = []
    for i, seg in enumerate(segments):
        segments_resume.append(
            f"  [{i}] id={seg['id']} personnage={seg['personnage']} "
            f"ton={seg.get('ton', 'normal')} rythme={seg.get('rythme', 'normal')} "
            f"pause_apres_ms={seg.get('pause_apres_ms', 0)} "
            f"texte=\"{seg.get('texte', '')[:60]}...\""
        )

    system_prompt = (
        "Tu es un ingénieur son spécialisé dans le montage de podcasts pour enfants. "
        "On te donne un script JSON d'épisode et des instructions du producteur. "
        "Tu dois modifier UNIQUEMENT les paramètres de montage du script, sans changer "
        "le texte des dialogues ni ajouter/supprimer de segments.\n\n"
        "Paramètres modifiables par segment :\n"
        "- pause_apres_ms (0-2500) : durée de la pause après le segment en ms\n"
        "- ton : émotion du segment (joyeux, triste, dramatique, solennel, tendre, "
        "epique, malicieux, mystérieux, calme, surpris, effrayé, enthousiaste, "
        "nostalgique, complice, rieur)\n"
        "- rythme : cadence (rapide, normal, lent)\n"
        "- mode (SFX uniquement) : overlay (superposé à la voix) ou insert (séquentiel)\n\n"
        "Paramètres modifiables au niveau épisode :\n"
        "- ambiance : thème musical de fond\n"
        "- ambiance_par_acte : liste de 3 ambiances pour varier par acte\n\n"
        "Réponds UNIQUEMENT avec un JSON contenant les modifications :\n"
        "{\n"
        '  "modifications_segments": {\n'
        '    "<index_segment>": {"pause_apres_ms": 1500, "ton": "dramatique", ...},\n'
        "    ...\n"
        "  },\n"
        '  "modifications_episode": {"ambiance": "...", "ambiance_par_acte": [...]},\n'
        '  "resume_modifications": "Description courte des changements appliqués"\n'
        "}\n\n"
        "Ne modifie QUE ce qui est demandé par le producteur. "
        "Laisse les autres paramètres inchangés."
    )

    user_prompt = (
        f"INSTRUCTIONS DU PRODUCTEUR :\n{instructions}\n\n"
        f"SEGMENTS ACTUELS ({len(segments)} segments) :\n"
        + "\n".join(segments_resume)
        + f"\n\nAmbiance actuelle : {script.get('episode', {}).get('ambiance', 'non définie')}"
        + f"\nAmbiance par acte : {script.get('episode', {}).get('ambiance_par_acte', 'non défini')}"
    )

    logger.info("Appel Claude pour instructions montage %s", episode_id)
    response = config.appel_claude_avec_retry(
        client,
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = response.content[0].text
    try:
        modifications = parser_json_llm(response_text)
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Réponse Claude non parsable pour instructions montage %s", episode_id
        )
        return script

    if not modifications:
        logger.warning("Aucune modification retournée par Claude pour %s", episode_id)
        return script

    # Appliquer les modifications aux segments
    mods_segments = modifications.get("modifications_segments", {})
    for idx_str, changements in mods_segments.items():
        try:
            idx = int(idx_str)
            if 0 <= idx < len(segments):
                _RYTHMES_VALIDES = {"rapide", "normal", "lent"}
                _MODES_VALIDES = {"insert", "overlay"}
                _TONS_VALIDES = {
                    "joyeux", "triste", "dramatique", "solennel", "tendre",
                    "epique", "malicieux", "mystérieux", "calme", "surpris",
                    "effrayé", "enthousiaste", "nostalgique", "complice",
                    "rieur", "normal",
                }
                for cle, valeur in changements.items():
                    if cle == "pause_apres_ms":
                        if isinstance(valeur, (int, float)):
                            valeur = max(0, min(int(valeur), config.PRODUCTION.get("max_pause_ms", 2500)))
                            segments[idx][cle] = valeur
                    elif cle == "rythme":
                        if isinstance(valeur, str) and valeur in _RYTHMES_VALIDES:
                            segments[idx][cle] = valeur
                    elif cle == "mode":
                        if isinstance(valeur, str) and valeur in _MODES_VALIDES:
                            segments[idx][cle] = valeur
                    elif cle == "ton":
                        if isinstance(valeur, str) and valeur in _TONS_VALIDES:
                            segments[idx][cle] = valeur
        except (ValueError, IndexError):
            logger.warning("Index segment invalide : %s", idx_str)

    # Appliquer les modifications au niveau épisode
    mods_episode = modifications.get("modifications_episode", {})
    if "ambiance" in mods_episode:
        script["episode"]["ambiance"] = mods_episode["ambiance"]
    if "ambiance_par_acte" in mods_episode:
        script["episode"]["ambiance_par_acte"] = mods_episode["ambiance_par_acte"]

    resume = modifications.get("resume_modifications", "Modifications appliquées")
    logger.info("Instructions montage appliquées pour %s : %s", episode_id, resume)

    # Sauvegarder le script modifié comme version validée
    chemin_valide = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    try:
        with fichier_lock(chemin_valide):
            with open(chemin_valide, "w", encoding="utf-8") as f:
                json.dump(script, f, ensure_ascii=False, indent=2)
        logger.info("Script modifié sauvegardé : %s", chemin_valide)
    except Exception as e:
        logger.warning("Erreur sauvegarde script modifié : %s", e)

    return script


def _charger_scripts_precedents_saison(saison: int, numero: int) -> list[dict]:
    """Charge les scripts validés des épisodes précédents de la même saison.

    Pour l'épisode S01E03, charge les scripts de S01E01 et S01E02.
    Cela permet au scripteur de lire les vrais dialogues et événements,
    pas seulement les résumés courts de l'historique.

    Returns:
        Liste de dicts {episode_id, titre, segments_resume} triés par numéro.
    """
    scripts_precedents = []
    for n in range(1, numero):
        ep_id = f"S{saison:02d}E{n:02d}"
        chemin = config.SCRIPTS_DIR / f"{ep_id}_valide.json"
        if not chemin.exists():
            # Tenter la restauration depuis Object Storage
            try:
                import persistent_storage
                persistent_storage.restore_script(ep_id, config.SCRIPTS_DIR)
            except Exception:
                pass
        if not chemin.exists():
            # B8: Signaler le script manquant (trou dans la continuité narrative)
            logger.warning(
                "Script précédent %s introuvable — trou dans la continuité "
                "narrative pour S%02dE%02d", ep_id, saison, numero,
            )
            continue
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                script_data = json.load(f)
            episode = script_data.get("episode", {})
            segments = episode.get("segments", [])

            # Extraire les dialogues clés (pas les SFX) — résumé condensé
            dialogues = []
            for seg in segments:
                if seg.get("personnage", "") == "sfx":
                    continue
                texte = seg.get("texte", "").strip()
                perso = seg.get("personnage", "inconnu")
                if texte:
                    # Tronquer les longs textes pour ne pas exploser le contexte
                    if len(texte) > 300:
                        texte = texte[:300] + "..."
                    dialogues.append(f"[{perso}] {texte}")

            scripts_precedents.append({
                "episode_id": ep_id,
                "titre": episode.get("titre", ep_id),
                "ambiance": episode.get("ambiance", ""),
                "nb_segments": len(segments),
                "dialogues": dialogues,
            })
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.debug("Script précédent %s illisible : %s", ep_id, e)
            continue

    return scripts_precedents


def ajouter_historique(rapport: dict, script: dict) -> None:
    """Ajoute un épisode à l'historique (DB + JSON pour rétrocompatibilité)."""
    episode = script.get("episode", {})

    # Extraire les personnages présents dans le script
    personnages_presents = sorted({
        seg["personnage"] for seg in episode.get("segments", [])
        if seg["personnage"] != "sfx"
    })

    # Construire un résumé court : priorité au résumé narratif, puis morale, puis titre
    resume_court = (
        episode.get("resume")
        or rapport.get("resume")
        or episode.get("morale")
        or rapport.get("titre", "")
    )
    if resume_court:
        resume_court = resume_court[:200]

    # Construire un resume des retours humains pour la memoire (A2)
    retours_humains = ""
    decisions = rapport.get("decisions_humaines", [])
    corrections_texte = []
    for d in decisions:
        if d.get("action") == "correction_humaine" and d.get("corrections"):
            corrections_texte.extend(d["corrections"])
    if corrections_texte:
        retours_humains = "; ".join(corrections_texte[:5])  # Max 5 corrections resumees

    entree = {
        "episode_id": rapport.get("episode_id", ""),
        "saison": episode.get("saison", rapport.get("saison", 1)),
        "numero": episode.get("numero", rapport.get("numero", 1)),
        "titre": rapport.get("titre", ""),
        "morale": episode.get("morale", ""),
        "resume_court": resume_court,
        "date_production": rapport.get("debut", ""),
        "score_review": rapport.get("etapes", {}).get("script", {}).get("score_review", 0),
        # Contexte sériel
        "personnages_presents": personnages_presents,
        "moments_cles": episode.get("moments_cles", []),
        "questions_ouvertes": episode.get("questions_ouvertes", []),
        "evolutions_personnages": episode.get("evolutions_personnages", ""),
        "ambiance": episode.get("ambiance", ""),
        "type_episode": episode.get("type", "standard"),
        # Retours humains pour la memoire inter-episodes (A2)
        "retours_humains": retours_humains,
        # Métriques de validation post-génération
        "ratio_biblique": rapport.get("metriques", {}).get("ratio_biblique", 0),
        "ratio_enfants": rapport.get("metriques", {}).get("ratio_enfants", 0),
        # Fil rouge
        "elements_fil_rouge": episode.get("elements_fil_rouge", ""),
    }

    # Sauvegarder en DB si disponible
    if _use_db():
        try:
            HistoriqueRepo.ajouter(
                episode_id=entree["episode_id"],
                titre=entree["titre"],
                morale=entree["morale"],
                resume_court=entree["resume_court"],
                score_review=entree["score_review"],
                personnages_presents=entree["personnages_presents"],
                moments_cles=entree["moments_cles"],
                questions_ouvertes=entree["questions_ouvertes"],
                evolutions_personnages=entree["evolutions_personnages"],
                ambiance=entree["ambiance"],
                retours_humains=entree.get("retours_humains", ""),
                type_episode=entree["type_episode"],
                date_production=entree["date_production"],
            )
        except Exception as e:
            logger.warning("DB indisponible pour ajout historique : %s", e)

    # Toujours sauvegarder en JSON (rétrocompatibilité) avec verrou
    with fichier_lock(HISTORIQUE_PATH):
        historique = []
        if HISTORIQUE_PATH.exists():
            with open(HISTORIQUE_PATH, "r", encoding="utf-8") as f:
                historique = json.load(f)
        # UPSERT : remplace l'entrée si episode_id existe déjà
        historique = [h for h in historique if h.get("episode_id") != entree["episode_id"]]
        historique.append(entree)
        sauvegarder_historique(historique)


# ── Système de checkpoints ───────────────────────────────────────────────────

# Thread-local pour l'ID de production courante (DB)
_production_local = threading.local()


# ── Gestionnaire SIGTERM (redéploiement Replit) ────────────────────────────────

def _sigterm_handler(signum, frame):
    """Sauvegarde l'état du pipeline avant arrêt forcé (SIGTERM de Replit autoscale).

    Quand Replit redéploie, il envoie SIGTERM au process gunicorn, qui le propage
    aux subprocesses (main.py). Ce handler :
    1. Sauvegarde le checkpoint avec l'état courant
    2. Marque la production comme 'interrupted' en DB (distinct de 'failed')
    3. Sort proprement pour que le serveur puisse reprendre au redémarrage
    """
    pipeline_ctx = getattr(_production_local, 'pipeline_context', None)
    pid = getattr(_production_local, 'production_id', None)

    if pipeline_ctx:
        episode_id = pipeline_ctx.get('episode_id', 'unknown')
        rapport = pipeline_ctx.get('rapport', {})
        logger.warning(
            "SIGTERM reçu — sauvegarde checkpoint d'interruption pour %s (étape: %s)",
            episode_id, pipeline_ctx.get('etape_courante', '?'),
        )
        try:
            sauvegarder_checkpoint(episode_id, pipeline_ctx.get('etape_courante', 'interrupted'), {
                "episode_id": episode_id,
                "titre": pipeline_ctx.get("titre", ""),
                "resume": pipeline_ctx.get("resume", ""),
                "saison": pipeline_ctx.get("saison", 1),
                "numero": pipeline_ctx.get("numero", 1),
                "morale": pipeline_ctx.get("morale", ""),
                "type_episode": pipeline_ctx.get("type_episode", "standard"),
                "dry_run": pipeline_ctx.get("dry_run", False),
                "rapport": rapport,
                "pubdate_offset_seconds": pipeline_ctx.get("pubdate_offset_seconds", 0),
                "stop_after": pipeline_ctx.get("stop_after", ""),
            })
        except Exception as e:
            logger.error("Impossible de sauvegarder le checkpoint SIGTERM : %s", e)

    # Marquer la production comme 'interrupted' en DB — retry car DB peut être lente
    if _use_db() and pid:
        for _attempt in range(3):
            try:
                from db_models import get_cursor
                with get_cursor() as cur:
                    cur.execute(
                        """UPDATE productions SET status = 'interrupted', updated_at = NOW()
                           WHERE id = %s AND status NOT IN ('completed', 'failed')""",
                        (pid,),
                    )
                logger.info("Production #%d marquée 'interrupted' en DB", pid)
                break  # Succès
            except Exception as e:
                logger.error(
                    "Marquage interrupted tentative %d/3 échouée : %s", _attempt + 1, e,
                )
                if _attempt < 2:
                    time.sleep(0.5)

    # Sortie propre — SystemExit n'est pas capturé par except Exception
    sys.exit(0)


def sauvegarder_checkpoint(episode_id: str, etape: str, data: dict) -> Path:
    """Sauvegarde un checkpoint pour permettre la reprise sur échec.

    En mode PostgreSQL, le checkpoint est sauvegardé dans la table productions
    (jamais supprimé). Le fichier JSON est aussi conservé pour rétrocompatibilité.

    Args:
        episode_id: Identifiant de l'épisode (ex: S01E01).
        etape: Nom de l'étape en cours.
        data: Données à sauvegarder.

    Returns:
        Chemin du fichier checkpoint.
    """
    _pid = getattr(_production_local, 'production_id', None)

    # Mettre à jour le contexte SIGTERM avec l'étape courante et le rapport
    ctx = getattr(_production_local, 'pipeline_context', None)
    if ctx:
        ctx['etape_courante'] = etape
        if 'rapport' in data:
            ctx['rapport'] = data['rapport']

    # Sauvegarder en DB si disponible
    if _use_db() and _pid:
        try:
            ProductionRepo.maj_etape(
                _pid,
                etape=etape,
                rapport=data.get("rapport"),
                checkpoint_data=data,
            )
        except Exception as e:
            logger.warning("DB indisponible pour checkpoint : %s", e)

    # Toujours sauvegarder en JSON (rétrocompatibilité + backup)
    chemin = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
    checkpoint = {
        "episode_id": episode_id,
        "etape": etape,
        "timestamp": datetime.now().isoformat(),
        "data": data,
    }
    # Écriture atomique pour éviter la corruption si crash mid-write
    with tempfile.NamedTemporaryFile(
        mode="w", dir=chemin.parent, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp:
        json.dump(checkpoint, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, chemin)
    logger.info("Checkpoint sauvegardé : %s (étape: %s)", chemin, etape)

    # Persister en Object Storage (survit aux redéploiements Replit)
    try:
        import persistent_storage
        persistent_storage.upload_checkpoint(episode_id, chemin)
    except Exception as e:
        logger.debug("Object Storage indisponible pour checkpoint : %s", e)

    return chemin


def charger_checkpoint(chemin: Path) -> dict:
    """Charge un checkpoint pour reprendre la production.

    Tente d'abord la DB, puis le fichier JSON.

    Raises:
        FileNotFoundError: Si le fichier n'existe pas.
        ValueError: Si le fichier est corrompu ou invalide.
    """
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Checkpoint corrompu ({chemin}) : {e}") from e

    for champ in ("episode_id", "etape", "data"):
        if champ not in data:
            raise ValueError(f"Checkpoint invalide — champ manquant : '{champ}'")

    return data


def archiver_checkpoint(episode_id: str) -> None:
    """Archive le checkpoint après une production réussie.

    CHANGEMENT CRITIQUE : le checkpoint n'est PLUS supprimé.
    En DB, il est marqué 'completed'. Le fichier JSON est renommé avec un
    suffixe _done pour conservation.
    """
    _pid = getattr(_production_local, 'production_id', None)

    # En DB : marquer terminé (jamais supprimé)
    if _use_db() and _pid:
        try:
            # Le statut sera mis à jour par ProductionRepo.terminer()
            pass
        except Exception as e:
            logger.warning("DB indisponible pour archivage checkpoint : %s", e)

    # Fichier JSON : renommer au lieu de supprimer
    chemin = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
    try:
        if chemin.exists():
            archive = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint_done_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            chemin.rename(archive)
            logger.info("Checkpoint archivé (non supprimé) : %s → %s", chemin, archive)
    except FileNotFoundError:
        # Déjà archivé par un autre processus concurrent
        logger.debug("Checkpoint déjà archivé par un autre processus : %s", chemin)


# ── Métriques de coût ────────────────────────────────────────────────────────


def _calculer_couts(rapport: dict) -> dict:
    """Calcule les coûts estimés de production d'un épisode.

    Args:
        rapport: Rapport de production avec les étapes complétées.

    Returns:
        Dictionnaire avec le détail des coûts par service.
    """
    couts = config.COUTS
    detail = {}
    total = 0.0

    # Coût ElevenLabs (TTS voix)
    audio_data = rapport.get("etapes", {}).get("audio", {})
    chars_tts = audio_data.get("caracteres", {})
    if isinstance(chars_tts, dict):
        total_chars = sum(chars_tts.values())
        cout_tts = total_chars * couts["elevenlabs_par_caractere"]
        detail["elevenlabs_tts"] = {
            "caracteres": total_chars,
            "cout": round(cout_tts, 4),
        }
        total += cout_tts

    # Coût ElevenLabs (SFX)
    sfx_data = rapport.get("etapes", {}).get("sfx", {})
    nb_sfx_elevenlabs = sum(
        1 for src in sfx_data.get("sources", {}).values()
        if src == "elevenlabs"
    )
    if nb_sfx_elevenlabs > 0:
        cout_sfx = nb_sfx_elevenlabs * couts["elevenlabs_sfx_par_generation"]
        detail["elevenlabs_sfx"] = {
            "nb_sfx": nb_sfx_elevenlabs,
            "cout": round(cout_sfx, 4),
        }
        total += cout_sfx

    # Coût Claude — compter les vrais appels (scripteur × itérations + reviewer × itérations + meta)
    etapes = rapport.get("etapes", {})
    script_data = etapes.get("script", {})
    nb_appels_claude = 0
    if script_data:
        nb_iterations = script_data.get("iterations", 1)
        # Chaque itération = 1 appel scripteur + 1 appel reviewer
        nb_appels_claude = nb_iterations * 2
    if "metadonnees" in etapes:
        nb_appels_claude += 1
    # Tokens réalistes : system prompt ~3500 + user ~1500 = ~5000 input, ~5000 output
    if nb_appels_claude > 0:
        cout_input = nb_appels_claude * 5000 * couts["claude_input_par_token"]
        cout_output = nb_appels_claude * 5000 * couts["claude_output_par_token"]
        cout_claude = cout_input + cout_output
        detail["anthropic_claude"] = {
            "nb_appels": nb_appels_claude,
            "cout": round(cout_claude, 4),
        }
        total += cout_claude

    # Coût cover art
    cover_art_cout = rapport.get("etapes", {}).get("metadonnees", {}).get("cover_art_cout", 0)
    if cover_art_cout > 0:
        detail["openai_dalle3"] = {
            "nb_images": 1,
            "cout": round(cover_art_cout, 4),
        }
        total += cover_art_cout

    detail["total_estime"] = round(total, 4)
    return detail


# ── Pipeline de production ────────────────────────────────────────────────────


NOMS_PERSONNAGES = {
    "papy_babou": "Papy Babou",
    "antoine": "Antoine",
    "noemie": "Noémie",
    "narrateur": "Narrateur",
    "sfx": "SFX",
}

# Alias pour le thème (utilisé dans les anciens appels)
NOMS_STYLED = NOMS_PERSONNAGES_STYLED


class ProductionAbandonnee(Exception):
    """Levée quand l'utilisateur abandonne la production."""


def _afficher_script(script: dict) -> None:
    """Affiche le script complet avec l'identité visuelle Papy Babou."""
    afficher_script(console, script)


def _afficher_recap_script(script: dict, score: float, type_episode: str, rapport: dict | None = None) -> None:
    """Affiche un recap du script avec score, duree et comparaison cible."""
    episode = script["episode"]
    scripteur = Scripteur()
    reviewer = Reviewer()
    nb_mots = scripteur.compter_mots(script)
    duree_estimee = reviewer.estimer_duree(script)
    nb_segments = len(episode.get("segments", []))
    nb_sfx = sum(1 for s in episode.get("segments", []) if s["personnage"] == "sfx")

    # Duree cible depuis le format
    format_ep = config.FORMATS_EPISODES.get(type_episode, config.FORMATS_EPISODES["standard"])
    duree_cible = format_ep["duree_cible_minutes"]
    mots_cible = format_ep["mots_cible"]

    # Ecart
    ecart_duree = duree_estimee - duree_cible
    ecart_mots = nb_mots - mots_cible
    couleur_duree = "green" if abs(ecart_duree) < 2 else "yellow" if abs(ecart_duree) < 4 else "red"
    couleur_mots = "green" if abs(ecart_mots) < 200 else "yellow" if abs(ecart_mots) < 400 else "red"

    console.print(panel_info(
        f"{Typo.label_valeur('Score review', f'{score}/10')}\n"
        f"{Typo.label_valeur('Mots', f'{nb_mots} (cible: {mots_cible},')} [{couleur_mots}]écart : {ecart_mots:+d}[/]\n"
        f"{Typo.label_valeur('Durée estimée', f'{duree_estimee:.1f} min (cible: {duree_cible} min,')} [{couleur_duree}]écart : {ecart_duree:+.1f} min[/]\n"
        f"{Typo.label_valeur('Segments', f'{nb_segments} (dont {nb_sfx} SFX)')}\n"
        f"{Typo.label_valeur('Type', type_episode)}",
        titre=f"{Icons.SCRIPT} Récap du script",
    ))


def _validation_script(
    script: dict,
    chemin_script: Path,
    morale: str = "",
    resume: str = "",
    contexte_saison: dict | None = None,
    episode_plan: dict | None = None,
    type_episode: str = "standard",
    score: float = 0,
    rapport: dict | None = None,
) -> tuple[dict, float]:
    """Point de validation humaine apres la review du script.

    Returns:
        Tuple (script, score) — le script (potentiellement modifie) et le score actuel.

    Raises:
        ProductionAbandonnee: Si l'utilisateur choisit d'abandonner.
    """
    nb_corrections_humaines = 0

    _afficher_script(script)
    _afficher_recap_script(script, score, type_episode, rapport)

    console.print(panel_info(
        f"[bold {Palette.MIEL}]Checklist avant validation :[/]\n"
        + Typo.dim("  1. Lire le script en entier (dialogues, narration, SFX)\n")
        + Typo.dim("  2. Vérifier la cohérence des personnages (ton, tics)\n")
        + Typo.dim("  3. Vérifier la morale et la fidélité biblique\n")
        + Typo.dim("  4. Vérifier la durée estimée (dans la cible ?)\n")
        + Typo.dim("  5. Vérifier le score du Reviewer (≥ 7/10 ?)\n")
        + Typo.dim(f"\n  Fichier : {chemin_script}"),
        titre=f"{Icons.REVIEW} Relecture du script",
    ))

    while True:
        console.print(panel_validation([
            ("v", "Valider et continuer"),
            ("m", "Modifier le fichier JSON manuellement"),
            ("c", "Donner des corrections (relance scripteur + reviewer)"),
            ("a", "Abandonner la production"),
        ], titre="Validation du script"))

        choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

        if choix in ("v", "valider"):
            console.print(f"[{Palette.SUCCES}]  Script validé par le producteur.[/]")
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "script",
                    "action": "valide",
                    "nb_corrections": nb_corrections_humaines,
                    "score_final": score,
                    "timestamp": datetime.now().isoformat(),
                })

            # Proposer de memoriser les corrections comme preferences (A6)
            if nb_corrections_humaines > 0:
                all_corrections = []
                for d in rapport.get("decisions_humaines", []) if rapport is not None else []:
                    if d.get("action") == "correction_humaine" and d.get("corrections"):
                        all_corrections.extend(d["corrections"])
                if all_corrections:
                    console.print(
                        f"\n[yellow]  Vous avez donne {len(all_corrections)} correction(s) "
                        f"sur cet episode.[/yellow]"
                    )
                    console.print(
                        "[dim]  Voulez-vous les mémoriser comme règles permanentes "
                        "pour les prochains épisodes ? (o/n)[/dim]"
                    )
                    choix_mem = console.input(f"  [{Palette.MIEL}]>[/] ").strip().lower()
                    if choix_mem in ("o", "oui", "y", "yes"):
                        episode = script.get("episode", {})
                        ep_id = f"S{episode.get('saison', 0):02d}E{episode.get('numero', 0):02d}"
                        for corr in all_corrections:
                            ajouter_preference(corr, source_episode=ep_id, categorie="style")
                        console.print(
                            f"[{Palette.SUCCES}]  {len(all_corrections)} préférence(s) mémorisée(s) "
                            f"pour les prochains épisodes.[/]"
                        )

            return script, score

        elif choix in ("m", "modifier"):
            console.print(
                f"\n[yellow]  Modifiez le fichier puis revenez ici :[/yellow]"
                f"\n  [bold]{chemin_script}[/bold]\n"
            )
            console.input("[cyan]  Appuyez sur Entrée quand c'est fait...[/cyan]")

            try:
                with open(chemin_script, "r", encoding="utf-8") as f:
                    script = json.load(f)
                # Valider la structure du script recharge (S3)
                Scripteur._valider_structure(script)
                console.print(f"[{Palette.SUCCES}]  Script rechargé et structure validée.[/]")
                if rapport is not None:
                    rapport.setdefault("decisions_humaines", []).append({
                        "etape": "script",
                        "action": "modification_json",
                        "timestamp": datetime.now().isoformat(),
                    })
                # Re-evaluation par le Reviewer apres edition manuelle (A4)
                console.print("[cyan]  Réévaluation par le Reviewer...[/cyan]")
                reviewer = Reviewer()
                resultat_review = reviewer.evaluer(script)
                score = resultat_review["review"]["score"]
                console.print(table_review(score, resultat_review["review"].get("details_score", {})))
                script = {"episode": resultat_review["episode"]}
                if not reviewer.est_valide(resultat_review):
                    console.print(f"[{Palette.ATTENTION}]  Score sous le seuil ({score}/10) — vous pourrez re-corriger.[/]")
                if rapport is not None:
                    rapport["etapes"]["script"]["score_review"] = score
                _afficher_script(script)
                _afficher_recap_script(script, score, type_episode, rapport)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                console.print(f"[red]  Erreur au rechargement : {e}[/red]")
                console.print("[yellow]  Les données précédentes sont conservées.[/yellow]")
            except ValueError as e:
                console.print(f"[red]  Structure invalide : {e}[/red]")
                console.print("[yellow]  Les données précédentes sont conservées.[/yellow]")

        elif choix in ("c", "corrections"):
            nb_corrections_humaines += 1
            if nb_corrections_humaines >= 3:
                console.print(
                    f"[yellow]  Attention : {nb_corrections_humaines}ᵉ correction humaine. "
                    f"Chaque correction coûte ~1 appel Claude (scripteur + reviewer).[/yellow]"
                )

            console.print(
                "\n[yellow]  Décrivez vos corrections "
                "(terminez par une ligne vide) :[/yellow]"
            )
            lignes = []
            while True:
                ligne = console.input("  > ")
                if not ligne.strip():
                    break
                lignes.append(ligne)

            if lignes:
                console.print(
                    "\n[cyan]  Corrections enregistrées "
                    "— relance du scripteur...[/cyan]"
                )
                scripteur = Scripteur()
                historique = charger_historique()
                script = scripteur.generer(
                    titre=script["episode"]["titre"],
                    resume=resume,
                    saison=script["episode"]["saison"],
                    numero=script["episode"]["numero"],
                    morale=morale,
                    corrections=lignes,
                    historique=historique,
                    contexte_saison=contexte_saison,
                    episode_plan=episode_plan,
                    type_episode=type_episode,
                    preferences_producteur=_construire_bloc_preferences(),
                )
                scripteur.sauvegarder(script, chemin_script)
                nb = scripteur.compter_mots(script)
                console.print(
                    f"[{Palette.SUCCES}]  Nouveau script généré ({nb} mots).[/]"
                )

                # Re-evaluer avec le Reviewer (S1)
                console.print("[cyan]  Réévaluation par le Reviewer...[/cyan]")
                reviewer = Reviewer()
                resultat_review = reviewer.evaluer(script)
                score = resultat_review["review"]["score"]

                console.print(table_review(
                    score, resultat_review["review"].get("details_score", {})
                ))

                if resultat_review["review"]["corrections"]:
                    console.print("[yellow]  Corrections du reviewer :[/yellow]")
                    for c in resultat_review["review"]["corrections"]:
                        console.print(f"    - {c}")

                if resultat_review["review"]["alertes"]:
                    console.print("[red]  Alertes :[/red]")
                    for a in resultat_review["review"]["alertes"]:
                        console.print(f"    ! {a}")

                # Appliquer les corrections du reviewer au script
                if reviewer.est_valide(resultat_review):
                    script = {"episode": resultat_review["episode"]}
                    console.print(f"[{Palette.SUCCES}]  Script corrigé validé ({score}/10).[/]")
                else:
                    script = {"episode": resultat_review["episode"]}
                    console.print(
                        f"[yellow]  Score {score}/10 (sous le seuil). "
                        f"Vous pouvez re-corriger ou valider manuellement.[/yellow]"
                    )

                scripteur.sauvegarder(script, chemin_script)

                # Mettre a jour le rapport (S2)
                if rapport is not None:
                    rapport["etapes"]["script"]["score_review"] = score
                    rapport["etapes"]["script"]["nb_mots"] = scripteur.compter_mots(script)
                    rapport["etapes"]["script"]["duree_estimee_min"] = round(
                        reviewer.estimer_duree(script), 1
                    )
                    rapport.setdefault("decisions_humaines", []).append({
                        "etape": "script",
                        "action": "correction_humaine",
                        "corrections": lignes,
                        "score_apres": score,
                        "timestamp": datetime.now().isoformat(),
                    })

                _afficher_script(script)
                _afficher_recap_script(script, score, type_episode, rapport)

        elif choix in ("a", "abandonner"):
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "script",
                    "action": "abandonne",
                    "timestamp": datetime.now().isoformat(),
                })
            raise ProductionAbandonnee(
                "Production abandonnée par l'utilisateur."
            )

        else:
            console.print("[red]  Choix non reconnu. Tapez v, m, c ou a.[/red]")


def _sauvegarder_plan_complet(
    plan: dict,
    chemin_json: Path,
    saison: int,
    planificateur_instance=None,
) -> None:
    """Sauvegarde un plan de saison sur les 3 backends : JSON + DB + Object Storage.

    Doit être appelé après chaque modification du plan pour éviter la perte
    de données en cas de redéploiement Replit (le filesystem est éphémère).
    """
    # 1. JSON (filesystem local)
    if planificateur_instance:
        planificateur_instance.sauvegarder(plan, chemin_json)
    else:
        from agents import Planificateur
        Planificateur().sauvegarder(plan, chemin_json)

    # 2. PostgreSQL (versionnée)
    if _use_db():
        try:
            db_id = SaisonRepo.sauvegarder(plan)
            logger.info("Plan saison %d sauvegardé en DB (id=%d)", saison, db_id)
        except Exception as e:
            logger.warning("DB indisponible pour plan saison %d : %s", saison, e)

    # 3. Object Storage (survit aux redéploiements)
    try:
        import persistent_storage
        key = persistent_storage.upload_saison(saison, chemin_json)
        if not key:
            logger.warning(
                "Object Storage : échec upload plan saison %d "
                "(bucket non configuré ? Allez dans Tools > Object Storage sur Replit)",
                saison,
            )
    except Exception as e:
        logger.warning("Object Storage indisponible pour plan saison %d : %s", saison, e)


def _previsualiser_ambiances_saison(
    plan: dict,
    chemin_json: Path,
    saison: int,
) -> dict:
    """Prévisualisation et remplacement des jingles intro/outro de la saison.

    Permet au producteur d'écouter les jingles de saison (intro_saison,
    outro_saison), et de les remplacer soit par auto-génération ElevenLabs,
    soit par un fichier audio custom.

    Les chemins custom sont sauvegardés dans ``plan["saison"]["jingles_custom"]``
    pour que le monteur les utilise durant toute la production de la saison.

    Args:
        plan: Plan de saison (sera muté avec les chemins jingles_custom).
        chemin_json: Chemin du fichier JSON du plan (pour sauvegarde).
        saison: Numéro de saison.

    Returns:
        Le plan mis à jour.
    """
    from agents.monteur import (
        Monteur, JINGLE_PROMPTS,
    )

    console.print(Panel(
        f"[bold]Prévisualisation des ambiances sonores — Saison {saison}[/bold]\n"
        "Écoutez les jingles d'intro et d'outro de la saison.\n"
        "Vous pouvez les remplacer si vous n'êtes pas satisfait.",
        title=f"{Icons.SAISON} Ambiances sonores de saison",
        border_style="blue",
    ))

    monteur = Monteur()
    jingles_custom = plan.get("saison", {}).get("jingles_custom", {})

    for position, label in [("intro", "Intro de saison"), ("outro", "Outro de saison")]:
        jingle_key = f"{position}_saison"
        chemin_defaut = config.JINGLES_PAR_TYPE.get(
            "ouverture" if position == "intro" else "final", {},
        ).get(position, config.ASSETS_DIR / "music" / f"{jingle_key}.mp3")

        # Chercher le jingle actuel (custom ou par défaut)
        chemin_custom = jingles_custom.get(jingle_key)
        chemin_actuel = Path(chemin_custom) if chemin_custom and Path(chemin_custom).exists() else None
        if not chemin_actuel and chemin_defaut.exists():
            chemin_actuel = chemin_defaut
        source = "custom" if chemin_custom else "par défaut"

        # Générer si aucun fichier n'existe encore
        if not chemin_actuel:
            console.print(f"\n  [yellow]{label} : aucun fichier trouvé — génération automatique...[/yellow]")
            prompt = JINGLE_PROMPTS.get(jingle_key, "")
            if prompt and monteur._generer_asset_elevenlabs(prompt, 10.0, chemin_defaut):
                chemin_actuel = chemin_defaut
                source = "auto-généré"
                console.print(f"  [{Palette.SUCCES}]Jingle généré : {chemin_defaut}[/]")
            else:
                console.print(f"  [red]Impossible de générer le jingle {position}.[/red]")
                continue

        console.print(f"\n  [bold]{label}[/bold] ({source}) : {chemin_actuel}")

        # Boucle d'écoute / remplacement pour ce jingle
        while True:
            console.print(panel_validation([
                ("e", f"Écouter le jingle {position}"),
                ("v", "Valider — garder ce jingle"),
                ("g", "Régénérer automatiquement (ElevenLabs)"),
                ("f", "Remplacer par un fichier audio custom"),
            ], titre=f"Jingle {label}"))

            choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

            if choix in ("e", "ecouter"):
                if chemin_actuel and chemin_actuel.exists():
                    if ouvrir_fichier(chemin_actuel):
                        console.print(f"  [{Palette.SUCCES}]Lecture lancée.[/]")
                    else:
                        console.print(f"  [yellow]Ouvrez manuellement : {chemin_actuel}[/yellow]")
                else:
                    console.print("  [red]Fichier introuvable.[/red]")

            elif choix in ("v", "valider"):
                console.print(f"  [{Palette.SUCCES}]Jingle {position} validé.[/]")
                break

            elif choix in ("g", "generer"):
                console.print(f"  [cyan]Régénération du jingle {position}...[/cyan]")
                prompt = JINGLE_PROMPTS.get(jingle_key, "")
                if not prompt:
                    console.print("  [red]Aucun prompt configuré pour ce jingle.[/red]")
                    continue

                # Supprimer l'ancien fichier pour forcer la régénération
                chemin_gen = chemin_defaut
                if chemin_gen.exists():
                    chemin_gen.unlink()

                if monteur._generer_asset_elevenlabs(prompt, 10.0, chemin_gen):
                    chemin_actuel = chemin_gen
                    source = "auto-généré"
                    # Supprimer l'éventuel custom puisqu'on revient au généré
                    jingles_custom.pop(jingle_key, None)
                    console.print(f"  [{Palette.SUCCES}]Nouveau jingle généré : {chemin_gen}[/]")
                else:
                    console.print("  [red]Échec de la génération ElevenLabs.[/red]")

            elif choix in ("f", "fichier"):
                console.print(
                    "\n  [yellow]Entrez le chemin absolu du fichier audio de remplacement "
                    "(MP3) :[/yellow]"
                )
                chemin_input = console.input("  > ").strip()
                if not chemin_input:
                    console.print("  [yellow]Annulé.[/yellow]")
                    continue

                chemin_remplacement = Path(chemin_input)
                if not chemin_remplacement.exists():
                    console.print(f"  [red]Fichier introuvable : {chemin_remplacement}[/red]")
                    continue
                if not chemin_remplacement.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a"):
                    console.print("  [red]Format non supporté. Utilisez MP3, WAV, OGG ou M4A.[/red]")
                    continue

                # Copier dans le dossier assets de la saison
                import shutil
                dest = config.ASSETS_DIR / "music" / f"saison_{saison:02d}_{jingle_key}{chemin_remplacement.suffix}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(chemin_remplacement), str(dest))
                chemin_actuel = dest
                jingles_custom[jingle_key] = str(dest)
                console.print(f"  [{Palette.SUCCES}]Fichier copié : {dest}[/]")

            else:
                console.print("  [red]Choix non reconnu. Tapez e, v, g ou f.[/red]")

    # Sauvegarder les jingles custom dans le plan
    plan.setdefault("saison", {})["jingles_custom"] = jingles_custom
    plan["saison"].setdefault("decisions_humaines", []).append({
        "action": "ambiances_saison_validees",
        "jingles_custom": jingles_custom,
        "timestamp": datetime.now().isoformat(),
    })

    # Sauvegarder le plan mis à jour (JSON + DB + Object Storage)
    _sauvegarder_plan_complet(plan, chemin_json, saison)
    console.print(f"\n[{Palette.SUCCES}]Ambiances sonores de saison validées et sauvegardées.[/]")

    return plan


def _afficher_retour_directeur_saison(resultat: dict) -> None:
    """Affiche le retour du directeur podcast sur un plan de saison."""
    dir_data = resultat.get("directeur_saison", {})
    note_dir = dir_data.get("note_globale", 0)
    verdict = dir_data.get("verdict", "?")
    note_aud = DirecteurPodcast.note_audience_plan(resultat)

    # Verdict avec couleur
    couleur_verdict = {
        "feu_vert": Palette.SUCCES,
        "ajustements_mineurs": "yellow",
        "retravailler": "red",
    }.get(verdict, "white")

    # Construire le contenu du panel (M4: cohérence thème)
    lignes = []
    lignes.append(
        f"[{couleur_verdict}]{verdict.replace('_', ' ').upper()}[/] "
        f"— note {note_dir}/10, audience {note_aud}/10"
    )

    # Synthèse
    synthese = dir_data.get("synthese", "")
    if synthese:
        lignes.append(f"\n{Typo.dim(synthese)}")

    # Axes détaillés
    for axe_nom, axe_data in dir_data.get("axes", {}).items():
        axe_label = axe_nom.replace("_", " ").title()
        axe_note = axe_data.get("note", 0)
        lignes.append(f"  {axe_label} : {axe_note}/10")

    console.print(panel_info("\n".join(lignes), titre=f"{Icons.REVIEW} Avis du Directeur Podcast"))

    # Recommandations
    recommandations = dir_data.get("recommandations", [])
    if recommandations:
        console.print("[yellow]  Recommandations :[/yellow]")
        priorite_ordre = {"critique": 0, "important": 1, "suggestion": 2}
        triees = sorted(
            recommandations,
            key=lambda r: priorite_ordre.get(r.get("priorite", "suggestion"), 3),
        )
        for r in triees:
            ep = r.get("episode")
            # M1: guard against non-int episode values from LLM
            ep_str = f" (E{int(ep):02d})" if isinstance(ep, (int, float)) and ep else ""
            console.print(f"    - [{r.get('priorite', '?')}]{ep_str} {r.get('texte', '')}")

    # Points forts
    points_forts = dir_data.get("points_forts", [])
    if points_forts:
        console.print(f"[{Palette.SUCCES}]  Points forts :[/]")
        for p in points_forts:
            console.print(f"    + {p}")

    # Réactions des personas
    personas = resultat.get("personas", {})
    for persona_key, persona_data in personas.items():
        nom = persona_key.replace("_", " ").title()
        reaction = persona_data.get("reaction", "")
        p_note = persona_data.get("note", 0)
        console.print(f"  {Typo.dim(f'{nom} ({p_note}/10) : {reaction}')}")


def _validation_plan_saison(
    plan: dict,
    chemin_json: Path,
    planificateur: Planificateur,
    saison: int,
    theme: str,
    description: str = "",
    personnages_list: list[str] | None = None,
    saisons_prec: list[dict] | None = None,
    nb_episodes: int = 10,
    archives_saisons: list[dict] | None = None,
) -> dict:
    """Point de validation humaine du plan de saison (go/no-go).

    Le directeur podcast évalue le plan à chaque tour (max 3 retours).
    Au 4e tour, le directeur modifie le plan directement.

    Affiche le plan complet et permet au producteur de valider, modifier,
    regenerer ou abandonner avant de lancer la production des episodes.

    Args:
        plan: Plan de saison genere.
        chemin_json: Chemin du fichier JSON du plan.
        planificateur: Instance du Planificateur (pour regeneration).
        saison: Numero de saison.
        theme: Theme de la saison.
        description: Description du producteur.
        personnages_list: Personnages secondaires.
        saisons_prec: Saisons precedentes pour contexte.
        nb_episodes: Nombre d'episodes.
        archives_saisons: Archives des saisons precedentes pour continuite.

    Returns:
        Le plan (potentiellement modifie ou regenere).

    Raises:
        ProductionAbandonnee: Si l'utilisateur choisit d'abandonner.
    """
    retours_directeur: list[dict] = []
    MAX_RETOURS_DIRECTEUR = 3
    MAX_ECHECS_DIRECTEUR = 3
    echecs_directeur = 0

    # Instancier le directeur une seule fois (H2)
    try:
        directeur = DirecteurPodcast()
    except Exception as e:
        logger.warning("Directeur Podcast non disponible : %s", e)
        directeur = None

    while True:
        # Afficher un resume compact du plan avant les choix
        saison_data = plan.get("saison", {})
        nb_eps = len(saison_data.get("episodes", []))
        theme_plan = saison_data.get("theme", "?")
        console.print(panel_info(
            f"{Typo.label_valeur('Thème', theme_plan)}\n"
            f"{Typo.label_valeur('Épisodes', str(nb_eps))}\n"
            f"{Typo.label_valeur('Fil rouge', saison_data.get('fil_rouge', 'N/A')[:80])}",
            titre=f"{Icons.SAISON} Résumé du plan de saison",
        ))

        # ── Évaluation du Directeur Podcast ─────────────────────────────
        nb_retours = len(retours_directeur)

        if directeur is None or echecs_directeur >= MAX_ECHECS_DIRECTEUR:
            # Directeur indisponible ou trop d'échecs consécutifs — on skip
            if echecs_directeur >= MAX_ECHECS_DIRECTEUR:
                console.print(
                    f"[yellow]  Directeur indisponible après {echecs_directeur} échecs "
                    f"consécutifs — évaluation désactivée.[/yellow]"
                )
        elif nb_retours >= MAX_RETOURS_DIRECTEUR:
            # 4e tour : le directeur prend la main et corrige directement
            console.print(
                f"\n[bold red]  {Icons.ATTENTION_IC} Le directeur podcast a donné "
                f"{MAX_RETOURS_DIRECTEUR} retours. Il prend la main et corrige "
                f"le plan directement.[/bold red]"
            )
            try:
                plan_corrige = directeur.corriger_plan_saison(
                    plan, retours_directeur,
                )
                plan = plan_corrige
                _sauvegarder_plan_complet(plan, chemin_json, saison, planificateur)
                console.print(
                    f"[{Palette.SUCCES}]  Plan corrigé par le directeur podcast "
                    f"et sauvegardé (DB + Object Storage).[/]"
                )
                _afficher_plan_saison(plan)
                plan["saison"].setdefault("decisions_humaines", []).append({
                    "action": "correction_directeur_podcast",
                    "timestamp": datetime.now().isoformat(),
                    "nb_retours_avant_correction": MAX_RETOURS_DIRECTEUR,
                })
                # Réinitialiser les retours — le directeur a corrigé
                retours_directeur = []
                echecs_directeur = 0
            except Exception as e:
                echecs_directeur += 1
                logger.warning("Directeur Podcast (correction plan) indisponible : %s", e)
                console.print(
                    f"[yellow]  Correction directeur non disponible : {e}[/yellow]"
                )
        else:
            # Tours 1-3 : le directeur évalue et donne ses retours
            tour_label = f"Tour {nb_retours + 1}/{MAX_RETOURS_DIRECTEUR}"
            console.print(
                f"\n  {Icons.REVIEW} Évaluation Directeur Podcast ({tour_label})..."
            )
            try:
                resultat_directeur = directeur.evaluer_plan_saison(
                    plan, retours_precedents=retours_directeur or None,
                )
                retours_directeur.append(resultat_directeur)
                _afficher_retour_directeur_saison(resultat_directeur)
                echecs_directeur = 0

                # Stocker dans le plan
                plan["saison"].setdefault("retours_directeur", []).append({
                    "tour": nb_retours + 1,
                    "note_globale": resultat_directeur.get("directeur_saison", {}).get("note_globale"),
                    "verdict": resultat_directeur.get("directeur_saison", {}).get("verdict"),
                    "note_audience": directeur.note_audience_plan(resultat_directeur),
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as e:
                echecs_directeur += 1
                logger.warning("Directeur Podcast (évaluation plan) indisponible : %s", e)
                console.print(
                    f"[yellow]  Évaluation directeur non disponible ({echecs_directeur}/{MAX_ECHECS_DIRECTEUR}) : {e}[/yellow]"
                )

        # ── Menu de validation humaine ──────────────────────────────────
        console.print(panel_validation([
            ("v", "Valider le plan — lancer la production"),
            ("m", "Modifier le fichier JSON manuellement"),
            ("r", "Régénérer le plan (nouvel appel au Planificateur)"),
            ("i", "Régénérer avec instructions (guidée)"),
            ("a", "Abandonner"),
        ], titre="Validation du plan de saison"))

        choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

        if choix in ("v", "valider"):
            console.print(f"[{Palette.SUCCES}]  Plan de saison validé par le producteur.[/]")
            plan["saison"].setdefault("decisions_humaines", []).append({
                "action": "valide",
                "timestamp": datetime.now().isoformat(),
            })
            _sauvegarder_plan_complet(plan, chemin_json, saison, planificateur)
            return plan

        elif choix in ("m", "modifier"):
            console.print(
                f"\n[yellow]  Modifiez le fichier puis revenez ici :[/yellow]"
                f"\n  [bold]{chemin_json}[/bold]\n"
            )
            console.input("[cyan]  Appuyez sur Entrée quand c'est fait...[/cyan]")

            try:
                with open(chemin_json, "r", encoding="utf-8") as f:
                    plan = json.load(f)
                planificateur._valider_plan(plan)
                plan["saison"].setdefault("decisions_humaines", []).append({
                    "action": "modification_json",
                    "timestamp": datetime.now().isoformat(),
                })
                _sauvegarder_plan_complet(plan, chemin_json, saison, planificateur)
                console.print(f"[{Palette.SUCCES}]  Plan rechargé, validé et sauvegardé (DB + Object Storage).[/]")
                _afficher_plan_saison(plan)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                console.print(f"[red]  Erreur au rechargement : {e}[/red]")
                console.print("[yellow]  Les données précédentes sont conservées.[/yellow]")
            except ValueError as e:
                console.print(f"[red]  Structure invalide : {e}[/red]")
                console.print("[yellow]  Les données précédentes sont conservées.[/yellow]")

        elif choix in ("r", "regenerer"):
            console.print(
                "\n[cyan]  Régénération du plan de saison...[/cyan]"
            )
            plan = planificateur.planifier_saison(
                numero_saison=saison,
                theme=theme,
                description=description,
                personnages_secondaires=personnages_list,
                saisons_precedentes=saisons_prec or None,
                nb_episodes=nb_episodes,
                preferences_producteur=_construire_bloc_preferences(),
                archives_saisons=archives_saisons or None,
            )
            _sauvegarder_plan_complet(plan, chemin_json, saison, planificateur)
            console.print(f"[{Palette.SUCCES}]  Nouveau plan généré et sauvegardé (DB + Object Storage).[/]")
            _afficher_plan_saison(plan)
            # H1: réinitialiser les retours directeur — le plan est entièrement nouveau
            retours_directeur = []
            echecs_directeur = 0

        elif choix in ("i", "instructions"):
            console.print(
                "\n[yellow]  Décrivez ce que vous souhaitez changer dans le plan "
                "(terminez par une ligne vide) :[/yellow]"
            )
            lignes_instructions = []
            while True:
                ligne = console.input("  > ")
                if not ligne.strip():
                    break
                lignes_instructions.append(ligne)

            if lignes_instructions:
                # Concatener les instructions a la description pour guider le LLM
                instructions_texte = "\n".join(lignes_instructions)
                description_enrichie = (
                    f"{description}\n\n"
                    f"INSTRUCTIONS DU PRODUCTEUR (prioritaires) :\n{instructions_texte}"
                ) if description else (
                    f"INSTRUCTIONS DU PRODUCTEUR (prioritaires) :\n{instructions_texte}"
                )
                console.print(
                    "\n[cyan]  Régénération guidée du plan...[/cyan]"
                )
                plan = planificateur.planifier_saison(
                    numero_saison=saison,
                    theme=theme,
                    description=description_enrichie,
                    personnages_secondaires=personnages_list,
                    saisons_precedentes=saisons_prec or None,
                    nb_episodes=nb_episodes,
                    preferences_producteur=_construire_bloc_preferences(),
                    archives_saisons=archives_saisons or None,
                )
                # Stocker les instructions dans le plan pour reference future (A5)
                plan["saison"].setdefault("instructions_producteur", []).append({
                    "instructions": instructions_texte,
                    "date": datetime.now().isoformat(),
                })
                _sauvegarder_plan_complet(plan, chemin_json, saison, planificateur)
                console.print(f"[{Palette.SUCCES}]  Nouveau plan généré avec vos instructions (DB + Object Storage).[/]")
                _afficher_plan_saison(plan)
                # H1: réinitialiser les retours directeur — le plan est entièrement nouveau
                retours_directeur = []
                echecs_directeur = 0

        elif choix in ("a", "abandonner"):
            plan["saison"].setdefault("decisions_humaines", []).append({
                "action": "abandonne",
                "timestamp": datetime.now().isoformat(),
            })
            raise ProductionAbandonnee(
                "Planification abandonnée par l'utilisateur."
            )

        else:
            console.print("[red]  Choix non reconnu. Tapez v, m, r, i ou a.[/red]")


def _afficher_plan_saison(plan: dict) -> None:
    """Affiche le resume complet d'un plan de saison."""
    saison_data = plan["saison"]
    saison_num = saison_data.get("numero", "?")

    # Description de la saison
    desc = saison_data.get("description", "")
    if desc:
        console.print(f"\n  [bold]Description :[/bold] {desc}")

    # Table des episodes avec resume complet (P4)
    table = table_saison_plan(saison_num, saison_data.get("theme", "Sans thème"))
    for ep in saison_data.get("episodes", []):
        table.add_row(
            str(ep.get("numero", "?")),
            ep.get("titre", "(sans titre)"),
            ep.get("type", "standard"),
            ep.get("ambiance", "?"),
            ep.get("morale", "")[:40],
        )
    console.print(table)

    # Detail de chaque episode (P4 — resume + histoire biblique)
    console.print(f"\n  [bold]Détail des épisodes :[/bold]")
    for ep in saison_data["episodes"]:
        type_ep = ep.get("type", "standard")
        format_ep = config.FORMATS_EPISODES.get(type_ep, config.FORMATS_EPISODES["standard"])
        console.print(
            f"    [bold]E{ep['numero']:02d}[/bold] {ep['titre']} "
            f"[dim]({type_ep}, ~{format_ep['duree_cible_minutes']} min)[/dim]"
        )
        histoire = ep.get("histoire_biblique", "")
        if histoire:
            console.print(f"      Histoire : {histoire[:120]}")
        resume_ep = ep.get("resume", "")
        if resume_ep:
            console.print(f"      Résumé : {resume_ep[:120]}")
        console.print(f"      Morale : {ep.get('morale', 'N/A')}")

    # Fil rouge
    fil_rouge = saison_data.get("fil_rouge", "")
    if fil_rouge:
        console.print(f"\n  [bold]Fil rouge :[/bold] {fil_rouge}")

    # Arcs de personnages
    arcs = saison_data.get("arcs_personnages", {})
    if arcs:
        console.print("\n[bold]  Arcs de personnages :[/bold]")
        for perso, arc in arcs.items():
            nom = perso.replace("_", " ").title()
            console.print(
                f"    {nom} : {arc.get('depart', '')} -> {arc.get('arrivee', '')}"
            )

    # Personnages secondaires
    secondaires = saison_data.get("personnages_secondaires", [])
    if secondaires:
        console.print("\n[bold]  Personnages secondaires :[/bold]")
        for p in secondaires:
            console.print(
                f"    {p.get('nom_complet', '?')} "
                f"(episode {p.get('apparait_episode', '?')}) : "
                f"{p.get('description', '')[:80]}"
            )

    # Rituels
    rituels = saison_data.get("rituels", {})
    if rituels:
        console.print("\n[bold]  Rituels :[/bold]")
        for cle, val in rituels.items():
            console.print(f"    {cle.replace('_', ' ').title()} : {val}")

    # Estimation des couts previsionnels (P5)
    nb_episodes = len(saison_data["episodes"])
    duree_totale = sum(
        config.FORMATS_EPISODES.get(
            ep.get("type", "standard"), config.FORMATS_EPISODES["standard"]
        )["duree_cible_minutes"]
        for ep in saison_data["episodes"]
    )
    mots_totaux = sum(
        config.FORMATS_EPISODES.get(
            ep.get("type", "standard"), config.FORMATS_EPISODES["standard"]
        )["mots_cible"]
        for ep in saison_data["episodes"]
    )
    # Estimation : ~3 appels Claude/episode (script, review, meta) + TTS
    cout_claude_estime = nb_episodes * 3 * (
        2000 * config.COUTS["claude_input_par_token"]
        + 4000 * config.COUTS["claude_output_par_token"]
    )
    cout_tts_estime = mots_totaux * 5 * config.COUTS["elevenlabs_par_caractere"]  # ~5 chars/mot
    cout_total_estime = cout_claude_estime + cout_tts_estime

    console.print(panel_info(
        f"{Typo.label_valeur('Épisodes', str(nb_episodes))}\n"
        f"{Typo.label_valeur('Durée totale estimée', f'~{duree_totale} min ({duree_totale / 60:.1f}h)')}\n"
        f"{Typo.label_valeur('Mots totaux estimés', f'~{mots_totaux:,}')}\n"
        f"{Typo.label_valeur('Coût estimé', f'~${cout_total_estime:.2f}')} "
        f"[dim](Claude: ${cout_claude_estime:.2f} + TTS: ${cout_tts_estime:.2f})[/dim]",
        titre=f"{Icons.SAISON} Prévisionnel de la saison",
    ))


def _validation_montage(
    chemin_hq: Path,
    chemin_preview: Path,
    duree_secondes: float,
    script: dict | None = None,
    type_episode: str = "standard",
    resultat_montage: dict | None = None,
    rapport: dict | None = None,
) -> bool:
    """Point de validation humaine apres le montage audio.

    Returns:
        True si le montage a ete relance (le pipeline doit refaire l'assemblage).

    Raises:
        ProductionAbandonnee: Si l'utilisateur choisit d'abandonner.
    """
    # Duree cible depuis le format (M2)
    format_ep = config.FORMATS_EPISODES.get(type_episode, config.FORMATS_EPISODES["standard"])
    duree_cible = format_ep["duree_cible_minutes"]
    ecart = (duree_secondes / 60) - duree_cible
    couleur_ecart = "green" if abs(ecart) < 2 else "yellow" if abs(ecart) < 4 else "red"

    # Infos enrichies (M2)
    info_lines = [
        f"{Typo.label_valeur('Durée', f'{duree_secondes:.0f}s ({duree_secondes / 60:.1f} min)')} "
        f"[{couleur_ecart}](cible: {duree_cible} min, écart : {ecart:+.1f} min)[/]",
        f"{Typo.label_valeur('Fichier HQ', str(chemin_hq))}",
        f"{Typo.label_valeur('Preview', str(chemin_preview))}",
    ]

    if resultat_montage:
        chapitres = resultat_montage.get("chapitres", [])
        if chapitres:
            info_lines.append(f"{Typo.label_valeur('Chapitres', str(len(chapitres)))}")
        taille_mb = resultat_montage.get("taille_mb") or round(
            resultat_montage.get("taille_bytes", 0) / 1024 / 1024, 1
        )
        if taille_mb:
            info_lines.append(f"{Typo.label_valeur('Taille', f'{taille_mb:.1f} MB')}")

    if script:
        nb_sfx = sum(1 for s in script["episode"].get("segments", []) if s["personnage"] == "sfx")
        nb_voix = sum(1 for s in script["episode"].get("segments", []) if s["personnage"] != "sfx")
        info_lines.append(f"{Typo.label_valeur('Segments', f'{nb_voix} voix + {nb_sfx} SFX')}")

    info_lines.append("")
    info_lines.append(f"[bold {Palette.MIEL}]Checklist avant validation :[/]")
    info_lines.append(Typo.dim("  1. Écouter le fichier preview en entier"))
    info_lines.append(Typo.dim("  2. Vérifier les voix (prononciation, rythme, volume)"))
    info_lines.append(Typo.dim("  3. Vérifier les bruitages (timing, volume)"))
    info_lines.append(Typo.dim("  4. Vérifier la durée (dans la cible ?)"))
    info_lines.append("")
    info_lines.append(Typo.dim(f"  Preview : {chemin_preview}"))

    console.print(panel_info(
        "\n".join(info_lines),
        titre=f"{Icons.MONTAGE} Écoute du montage",
    ))

    # Tenter d'ouvrir le fichier preview automatiquement
    preview_path = Path(chemin_preview) if chemin_preview else None
    if preview_path and preview_path.exists():
        if ouvrir_fichier(preview_path):
            console.print(
                f"  [{Palette.SUCCES}]{Icons.OK} Fichier preview ouvert dans le lecteur par défaut.[/]"
            )
        else:
            console.print(
                f"  [{Palette.ATTENTION}]{Icons.ATTENTION_IC} Impossible d'ouvrir le fichier automatiquement.[/]\n"
                f"  [{Palette.ARDOISE}]Ouvrez manuellement : {chemin_preview}[/]"
            )

    # Trouver le chemin du script pour l'edition (A3)
    script_path = None
    if script:
        episode = script.get("episode", {})
        ep_id = f"S{episode.get('saison', 0):02d}E{episode.get('numero', 0):02d}"
        chemin_candidat = config.SCRIPTS_DIR / f"{ep_id}_valide.json"
        if chemin_candidat.exists():
            script_path = chemin_candidat

    while True:
        options = [
            ("v", "Valider et continuer vers les métadonnées"),
            ("l", "Réécouter le preview (ouvrir le fichier)"),
            ("e", "Éditer le script (pauses, SFX) puis relancer le montage"),
            ("r", "Relancer le montage tel quel"),
            ("a", "Abandonner (l'audio est conservé, pas de publication)"),
        ]
        console.print(panel_validation(options, titre="Validation du montage"))

        choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

        if choix in ("l", "listen", "ecouter"):
            if preview_path and preview_path.exists():
                if ouvrir_fichier(preview_path):
                    console.print(f"  [{Palette.SUCCES}]{Icons.OK} Fichier preview rouvert.[/]")
                else:
                    console.print(
                        f"  [{Palette.ATTENTION}]{Icons.ATTENTION_IC} Ouverture impossible.[/]\n"
                        f"  [{Palette.ARDOISE}]Chemin : {chemin_preview}[/]"
                    )
            else:
                console.print(f"  [{Palette.ATTENTION}]Fichier preview introuvable.[/]")
            continue

        elif choix in ("v", "valider"):
            console.print(
                f"[{Palette.SUCCES}]  Montage validé par le producteur.[/]"
            )
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "montage",
                    "action": "valide",
                    "timestamp": datetime.now().isoformat(),
                })
            return False  # Pas de remontage

        elif choix in ("e", "editer"):
            reload_ok = False
            if script_path:
                console.print(
                    f"\n[yellow]  Éditez les segments du script (pauses, SFX, tons) :[/yellow]"
                    f"\n  [bold]{script_path}[/bold]"
                    f"\n[dim]  Modifiez pause_apres_ms, duree_sfx_secondes, mode, etc.[/dim]\n"
                )
                console.input("[cyan]  Appuyez sur Entrée quand c'est fait...[/cyan]")
                try:
                    with open(script_path, "r", encoding="utf-8") as f:
                        script_recharge = json.load(f)
                    Scripteur._valider_structure(script_recharge)
                    # Mettre a jour le script en place pour le remontage
                    script.clear()
                    script.update(script_recharge)
                    console.print(f"[{Palette.SUCCES}]  Script rechargé et validé — relance du montage.[/]")
                    reload_ok = True
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    console.print(f"[red]  Erreur au rechargement : {e}[/red]")
                    console.print("[yellow]  Les données précédentes sont conservées. Retour au menu.[/yellow]")
                except ValueError as e:
                    console.print(f"[red]  Structure invalide : {e}[/red]")
                    console.print("[yellow]  Les données précédentes sont conservées. Retour au menu.[/yellow]")
            else:
                console.print("[red]  Fichier script introuvable — édition impossible.[/red]")
                console.print("[yellow]  Retour au menu de validation.[/yellow]")
                reload_ok = False

            if reload_ok:
                if rapport is not None:
                    rapport.setdefault("decisions_humaines", []).append({
                        "etape": "montage",
                        "action": "remontage_apres_edition",
                        "timestamp": datetime.now().isoformat(),
                    })
                return True  # Remontage avec script potentiellement modifie

        elif choix in ("r", "relancer"):
            console.print(
                "[cyan]  Relance du montage...[/cyan]"
            )
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "montage",
                    "action": "remontage",
                    "timestamp": datetime.now().isoformat(),
                })
            return True  # Demande de remontage

        elif choix in ("a", "abandonner"):
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "montage",
                    "action": "abandonne",
                    "timestamp": datetime.now().isoformat(),
                })
            raise ProductionAbandonnee(
                "Production arrêtée après montage. "
                f"L'audio est conserve dans : {chemin_hq}"
            )

        else:
            console.print("[red]  Choix non reconnu. Tapez v, l, e, r ou a.[/red]")


def _afficher_recap_metadonnees(meta: dict) -> None:
    """Affiche le recap complet des metadonnees dans un panel info."""
    info_lines = [
        f"{Typo.label_valeur('Titre', meta.get('titre', 'N/A'))}",
        f"{Typo.label_valeur('Description', meta.get('description_courte', 'N/A'))}",
    ]

    tags = meta.get("tags", [])
    if tags:
        info_lines.append(f"{Typo.label_valeur('Tags', ', '.join(tags))}")

    keywords = meta.get("keywords", [])
    if keywords:
        info_lines.append(f"{Typo.label_valeur('Mots-clés', ', '.join(keywords))}")

    cover_path = meta.get("cover_art_path", "")
    if cover_path:
        info_lines.append(f"{Typo.label_valeur('Cover art', cover_path)}")
    else:
        info_lines.append(Typo.dim("  Pas de cover art généré."))

    transcript = meta.get("transcript", "")
    if transcript:
        nb_lignes = len(transcript.strip().split("\n"))
        info_lines.append(f"{Typo.label_valeur('Transcript', f'{nb_lignes} lignes')}")

    info_lines.append("")
    info_lines.append(f"[bold {Palette.MIEL}]Checklist avant validation :[/]")
    info_lines.append(Typo.dim("  1. Vérifier le titre (accrocheur, fidèle à l'épisode)"))
    info_lines.append(Typo.dim("  2. Vérifier la description (claire, sans spoiler)"))
    info_lines.append(Typo.dim("  3. Vérifier les mots-clés (pertinents pour le référencement)"))
    info_lines.append(Typo.dim("  4. Vérifier le cover art (adapté, pas de contenu interdit)"))

    console.print(panel_info(
        "\n".join(info_lines),
        titre=f"{Icons.METADONNEES} Métadonnées générées",
    ))


def _validation_metadonnees(
    meta: dict,
    chemin_meta: Path,
    script: dict | None = None,
    duree_secondes: float = 0,
    rapport: dict | None = None,
) -> dict:
    """Point de validation humaine pour les metadonnees avant publication.

    Returns:
        Le dict meta (potentiellement modifie par l'utilisateur).
    """
    _afficher_recap_metadonnees(meta)

    # Ouvrir le cover art automatiquement s'il existe
    cover_path = meta.get("cover_art_path", "")
    if cover_path and Path(cover_path).exists():
        if ouvrir_fichier(Path(cover_path)):
            console.print(
                f"  [{Palette.SUCCES}]{Icons.OK} Cover art ouvert pour visualisation.[/]"
            )
        else:
            console.print(
                f"  [{Palette.ARDOISE}]Cover art : {cover_path}[/]"
            )

    while True:
        options = [
            ("v", "Valider les métadonnées"),
            ("o", "Ouvrir le cover art"),
            ("c", "Régénérer avec instructions"),
            ("m", "Modifier le JSON manuellement"),
            ("a", "Abandonner"),
        ]
        console.print(panel_validation(options, titre="Validation des métadonnées"))

        choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

        if choix in ("o", "ouvrir"):
            cp = meta.get("cover_art_path", "")
            if cp and Path(cp).exists():
                if ouvrir_fichier(Path(cp)):
                    console.print(f"  [{Palette.SUCCES}]{Icons.OK} Cover art ouvert.[/]")
                else:
                    console.print(f"  [{Palette.ATTENTION}]Ouverture impossible. Chemin : {cp}[/]")
            else:
                console.print(f"  [{Palette.ARDOISE}]Pas de cover art disponible.[/]")
            continue

        elif choix in ("v", "valider"):
            console.print(f"[{Palette.SUCCES}]  Métadonnées validées par le producteur.[/]")
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "metadonnees",
                    "action": "valide",
                    "timestamp": datetime.now().isoformat(),
                })
            return meta

        elif choix in ("c", "corrections"):
            if not script:
                console.print("[yellow]  Script non disponible — régénération impossible.[/yellow]")
                continue
            console.print(
                "\n[yellow]  Décrivez ce que vous souhaitez changer dans les métadonnées "
                "(terminez par une ligne vide) :[/yellow]"
            )
            lignes = []
            while True:
                ligne = console.input("  > ")
                if not ligne.strip():
                    break
                lignes.append(ligne)
            if lignes:
                console.print("[cyan]  Régénération des métadonnées...[/cyan]")
                metadonnees_agent = Metadonnees()
                instructions = "\n".join(lignes)
                # Passer les instructions via le script enrichi
                script_enrichi = dict(script)
                script_enrichi["_instructions_metadonnees"] = instructions
                if duree_secondes > 0:
                    meta = metadonnees_agent.generer(script_enrichi, duree_secondes)
                else:
                    meta = metadonnees_agent.generer_dry_run(script_enrichi)
                metadonnees_agent.sauvegarder(meta, chemin_meta)
                console.print(f"[{Palette.SUCCES}]  Métadonnées régénérées.[/]")
                _afficher_recap_metadonnees(meta)
                if rapport is not None:
                    rapport.setdefault("decisions_humaines", []).append({
                        "etape": "metadonnees",
                        "action": "regenere_avec_instructions",
                        "instructions": lignes,
                        "timestamp": datetime.now().isoformat(),
                    })

        elif choix in ("m", "modifier"):
            console.print(
                f"\n[yellow]  Modifiez le fichier puis revenez ici :[/yellow]"
                f"\n  [bold]{chemin_meta}[/bold]\n"
            )
            console.input("[cyan]  Appuyez sur Entrée quand c'est fait...[/cyan]")
            try:
                with open(chemin_meta, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                # Valider la structure minimale
                if "titre" not in meta or "description_courte" not in meta:
                    raise ValueError("Champs requis manquants : titre, description_courte")
                console.print(f"[{Palette.SUCCES}]  Métadonnées rechargées depuis le fichier.[/]")
                if rapport is not None:
                    rapport.setdefault("decisions_humaines", []).append({
                        "etape": "metadonnees",
                        "action": "modifie_json",
                        "timestamp": datetime.now().isoformat(),
                    })
                _afficher_recap_metadonnees(meta)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                console.print(f"[red]  Erreur au rechargement : {e}[/red]")
                console.print("[yellow]  Les données précédentes sont conservées.[/yellow]")
            except ValueError as e:
                console.print(f"[red]  Structure invalide : {e}[/red]")
                console.print("[yellow]  Les données précédentes sont conservées.[/yellow]")

        elif choix in ("a", "abandonner"):
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "metadonnees",
                    "action": "abandonne",
                    "timestamp": datetime.now().isoformat(),
                })
            raise ProductionAbandonnee(
                "Production arrêtée après génération des métadonnées."
            )

        else:
            console.print("[red]  Choix non reconnu. Tapez v, o, c, m ou a.[/red]")


def _validation_publication(
    meta: dict,
    episode_id: str,
    rapport: dict | None = None,
) -> bool:
    """Point de confirmation avant publication RSS.

    Vérifie que le script a été relu et le montage écouté avant
    d'autoriser la publication. Bloque si ces prérequis ne sont pas remplis.

    Returns:
        True si l'utilisateur confirme la publication, False pour annuler.
    """
    # ── Vérification des prérequis : relecture + écoute ──────────────
    etapes = rapport.get("etapes", {}) if rapport else {}
    script_valide = etapes.get("script", {}).get("validation_humaine", False)
    montage_valide = etapes.get("montage", {}).get("validation_humaine", False)

    prerequis_manquants = []
    if not script_valide:
        prerequis_manquants.append("Relecture du script")
    if not montage_valide:
        prerequis_manquants.append("Écoute du montage audio")

    if prerequis_manquants:
        console.print(
            f"\n[bold red]  PUBLICATION BLOQUÉE — prérequis manquants :[/bold red]"
        )
        for p in prerequis_manquants:
            console.print(f"[red]    • {p}[/red]")
        console.print(
            "[yellow]  Pas de publication sans relecture et sans écoute. "
            "Relancez la production sans --auto pour valider ces étapes.[/yellow]"
        )
        if rapport is not None:
            rapport.setdefault("decisions_humaines", []).append({
                "etape": "publication",
                "action": "bloque_prerequis_manquants",
                "prerequis_manquants": prerequis_manquants,
                "timestamp": datetime.now().isoformat(),
            })
        return False

    info_lines = [
        f"{Typo.label_valeur('Épisode', episode_id)}",
        f"{Typo.label_valeur('Titre', meta.get('titre', 'N/A'))}",
        "",
        f"[{Palette.SUCCES}]{Icons.OK} Script relu et validé par le producteur.[/]",
        f"[{Palette.SUCCES}]{Icons.OK} Montage écouté et validé par le producteur.[/]",
        f"[{Palette.SUCCES}]{Icons.OK} Métadonnées vérifiées.[/]",
        "",
        f"[bold {Palette.ATTENTION}]{Icons.ATTENTION_IC} La publication ajoutera l'épisode au flux RSS public.[/]",
        Typo.dim("Cette action est irréversible sans intervention manuelle."),
    ]

    console.print(panel_info(
        "\n".join(info_lines),
        titre=f"{Icons.PUBLICATION} Confirmation de publication",
    ))

    while True:
        console.print(panel_validation([
            ("p", "Publier l'épisode"),
            ("s", "Sauter la publication (audio conservé)"),
            ("a", "Abandonner la production"),
        ], titre="Publication"))

        choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

        if choix in ("p", "publier"):
            console.print(f"[{Palette.SUCCES}]  Publication confirmée par le producteur.[/]")
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "publication",
                    "action": "publie",
                    "timestamp": datetime.now().isoformat(),
                })
            return True

        elif choix in ("s", "sauter"):
            console.print(
                "[yellow]  Publication sautée — l'audio et les métadonnées "
                "sont conservés pour publication ultérieure.[/yellow]"
            )
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "publication",
                    "action": "saute",
                    "timestamp": datetime.now().isoformat(),
                })
            return False

        elif choix in ("a", "abandonner"):
            console.print(
                f"[{Palette.ATTENTION}]  Publication annulée. "
                f"L'audio et les métadonnées sont conservés. "
                f"Le rapport final sera tout de même généré.[/]"
            )
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "publication",
                    "action": "abandonne",
                    "timestamp": datetime.now().isoformat(),
                })
            return False  # Ne pas publier mais continuer vers le rapport final

        else:
            console.print("[red]  Choix non reconnu. Tapez p, s ou a.[/red]")


# ── Pipeline de production ────────────────────────────────────────────────────


def pipeline(
    titre: str,
    resume: str,
    saison: int,
    numero: int,
    morale: str = "",
    dry_run: bool = False,
    auto: bool = False,
    max_iterations_review: int = 3,
    etape_depart: str = "script",
    checkpoint_data: dict | None = None,
    contexte_saison: dict | None = None,
    type_episode: str = "standard",
    pubdate_offset_seconds: int = 0,
    no_publish: bool = False,
    stop_after: str = "",
    # Contexte d'affichage pour production sérielle
    episode_courant: int = 0,
    total_episodes: int = 0,
    saison_theme: str = "",
) -> dict:
    """Execute le pipeline complet de production d'un episode.

    Args:
        titre: Titre de l'episode.
        resume: Resume de l'histoire biblique.
        saison: Numero de saison.
        numero: Numero d'episode.
        morale: Leçon de vie à transmettre.
        dry_run: Si True, pas de generation audio ni de publication.
        auto: Si True, pas de validation humaine.
        max_iterations_review: Nombre max de boucles scripteur-reviewer.
        etape_depart: Étape à laquelle reprendre (pour les checkpoints).
        checkpoint_data: Données du checkpoint (pour la reprise).
        contexte_saison: Plan de saison complet pour le contexte sériel.
        type_episode: Type d'épisode (ouverture, standard, mi-saison, final, bonus).
        no_publish: Si True, saute l'étape de publication (upload + RSS).

    Returns:
        Rapport de production complet.
    """
    _production_local.production_id = None  # Reset au début de chaque pipeline

    episode_id = f"S{saison:02d}E{numero:02d}"
    rapport = checkpoint_data if checkpoint_data is not None else {
        "episode_id": episode_id,
        "titre": titre,
        "dry_run": dry_run,
        "debut": datetime.now().isoformat(),
        "etapes": {},
    }

    # Enregistrer le contexte du pipeline pour le handler SIGTERM
    _production_local.pipeline_context = {
        "episode_id": episode_id, "titre": titre, "resume": resume,
        "saison": saison, "numero": numero, "morale": morale,
        "type_episode": type_episode, "dry_run": dry_run,
        "rapport": rapport, "etape_courante": etape_depart,
        "pubdate_offset_seconds": pubdate_offset_seconds,
        "stop_after": stop_after,
    }
    # Installer le handler SIGTERM (uniquement depuis le thread principal)
    try:
        signal.signal(signal.SIGTERM, _sigterm_handler)
    except ValueError:
        pass  # Pas le thread principal — handler déjà installé ou non supporté

    # Créer ou réutiliser une production en DB
    if _use_db():
        try:
            # Si on reprend un checkpoint, réutiliser la production existante
            # au lieu d'en créer une nouvelle (évite les lignes orphelines en DB)
            if etape_depart != "script":
                existing = ProductionRepo.charger_dernier_checkpoint(episode_id)
                if existing:
                    _production_local.production_id = existing["id"]
                    logger.info("Reprise de la production DB #%d pour %s", existing["id"], episode_id)
                else:
                    _production_local.production_id = ProductionRepo.creer(
                        episode_id=episode_id,
                        dry_run=dry_run,
                        auto_mode=auto,
                    )
                    logger.info("Production DB #%d créée pour %s (reprise sans production existante)", _production_local.production_id, episode_id)
            else:
                _production_local.production_id = ProductionRepo.creer(
                    episode_id=episode_id,
                    dry_run=dry_run,
                    auto_mode=auto,
                )
                logger.info("Production DB #%d créée pour %s", _production_local.production_id, episode_id)
            EpisodeRepo.creer_ou_maj(
                episode_id=episode_id,
                saison=saison,
                numero=numero,
                titre=titre,
                type_episode=type_episode,
                resume=resume,
                morale=morale,
                status="in_progress",
            )
        except Exception as e:
            logger.warning("DB indisponible pour création production : %s", e)
            _production_local.production_id = None

    try:
        return _pipeline_inner(
            titre=titre, resume=resume, saison=saison, numero=numero,
            morale=morale, dry_run=dry_run, auto=auto,
            max_iterations_review=max_iterations_review,
            etape_depart=etape_depart, checkpoint_data=checkpoint_data,
            contexte_saison=contexte_saison, type_episode=type_episode,
            episode_id=episode_id, rapport=rapport,
            pubdate_offset_seconds=pubdate_offset_seconds,
            no_publish=no_publish, stop_after=stop_after,
            episode_courant=episode_courant,
            total_episodes=total_episodes,
            saison_theme=saison_theme,
        )
    except ProductionAbandonnee:
        raise
    except Exception as e:
        # Marquer la production comme échouée en DB (BUG 29)
        import traceback as _tb_pipeline
        sys.stderr.write(
            f"[pipeline {episode_id}] ERREUR FATALE dans pipeline(): "
            f"{type(e).__name__}: {e}\n"
            f"{_tb_pipeline.format_exc()}\n"
        )
        sys.stderr.flush()
        logger.error("Pipeline échoué pour %s : %s", episode_id, e)
        _pid = getattr(_production_local, 'production_id', None)
        if _use_db() and _pid:
            try:
                ProductionRepo.echouer(_pid, str(e))
                EpisodeRepo.maj_status(episode_id, "failed")
            except Exception as db_err:
                logger.warning("DB indisponible pour marquage échec : %s", db_err)
        # W13: Nettoyer le fichier de corrections web en cas de crash
        # pour éviter qu'il ne soit réutilisé lors d'une prochaine production
        try:
            corrections_stale = config.SCRIPTS_DIR / f"{episode_id}_web_corrections.txt"
            if corrections_stale.exists():
                corrections_stale.unlink()
        except OSError:
            pass
        # Sauvegarder le rapport partiel dans le fichier NORMAL (pas _echec)
        # pour que charger_rapport() le trouve et que le web dashboard affiche
        # les résultats partiels (ex: script OK, audio OK, montage échoué).
        rapport["erreur"] = str(e)
        rapport["status"] = "failed"
        rapport["fin"] = datetime.now().isoformat()
        chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
        # MERGE avec le rapport existant pour préserver decisions_humaines,
        # etapes déjà complétées, etc. (ne pas écraser un rapport riche
        # par un rapport d'erreur squelettique)
        with fichier_lock(chemin_rapport):
            if chemin_rapport.exists():
                try:
                    with open(chemin_rapport, "r", encoding="utf-8") as f:
                        rapport_existant = json.load(f)
                    # Préserver les clés du rapport existant absentes du nouveau
                    for cle in ("decisions_humaines", "metriques", "alertes_post_generation"):
                        if cle in rapport_existant and cle not in rapport:
                            rapport[cle] = rapport_existant[cle]
                    # Merger les étapes : garder les étapes existantes, écraser
                    # uniquement celles que le nouveau rapport a aussi
                    if "etapes" in rapport_existant:
                        etapes_merged = rapport_existant["etapes"].copy()
                        etapes_merged.update(rapport.get("etapes", {}))
                        rapport["etapes"] = etapes_merged
                except (json.JSONDecodeError, OSError) as merge_err:
                    logger.debug("Impossible de merger avec rapport existant : %s", merge_err)
            with open(chemin_rapport, "w", encoding="utf-8") as f:
                json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)
        # Upload rapport vers Object Storage (survit aux redéploiements)
        try:
            import persistent_storage
            persistent_storage.upload_rapport(episode_id, chemin_rapport)
        except Exception as e_os:
            logger.warning("Object Storage indisponible pour rapport échec : %s", e_os)
        # Sauvegarder un checkpoint d'erreur pour permettre la reprise
        try:
            sauvegarder_checkpoint(episode_id, "erreur", {
                "episode_id": episode_id, "titre": titre, "resume": resume,
                "saison": saison, "numero": numero, "morale": morale,
                "type_episode": type_episode,
                "dry_run": dry_run, "rapport": rapport,
                "pubdate_offset_seconds": pubdate_offset_seconds,
                "stop_after": stop_after,
            })
        except Exception:
            logger.debug("Impossible de sauvegarder le checkpoint d'erreur")
        console.print(panel_erreur(
            f"Pipeline échoué pour {episode_id} : {e}\n"
            f"Rapport partiel sauvé : {chemin_rapport}"
        ))
        raise


def _pipeline_inner(
    titre, resume, saison, numero, morale, dry_run, auto,
    max_iterations_review, etape_depart, checkpoint_data,
    contexte_saison, type_episode, episode_id, rapport,
    pubdate_offset_seconds=0, no_publish=False, stop_after="",
    episode_courant=0, total_episodes=0, saison_theme="",
):
    """Corps interne du pipeline, encapsulé pour la gestion d'erreurs."""
    # Log direct stderr pour visibilité subprocess (ne dépend pas de Rich Console)
    def _log_direct(msg: str) -> None:
        sys.stderr.write(f"[pipeline {episode_id}] {msg}\n")
        sys.stderr.flush()

    _log_direct(f"Démarrage pipeline — etape_depart={etape_depart}, stop_after={stop_after}")

    # Timer pour mesurer la durée de chaque étape
    _t_pipeline_start = time.perf_counter()
    _t_last_step = _t_pipeline_start

    def _log_step_duration(step_name: str) -> None:
        nonlocal _t_last_step
        now = time.perf_counter()
        step_s = now - _t_last_step
        total_s = now - _t_pipeline_start
        logger.info(
            "⏱ %s : %.1fs (total %.1fs)", step_name, step_s, total_s
        )
        _t_last_step = now

    # Charger le contexte de saison automatiquement si pas fourni
    if not contexte_saison:
        contexte_saison = config.charger_saison(saison) or None

    # Charger les données de l'épisode depuis le plan de saison
    episode_plan = None
    if contexte_saison:
        episode_plan = config.charger_episode_saison(saison, numero)
        if episode_plan:
            type_episode = episode_plan.get("type", type_episode)
            if not morale and episode_plan.get("morale"):
                morale = episode_plan["morale"]
            # Enregistrer les personnages secondaires de CETTE saison uniquement
            persos_saison = contexte_saison.get("saison", {}).get("personnages_secondaires", [])
            for perso_sec in persos_saison:
                perso_id = perso_sec.get("id", "")
                if perso_id and perso_id not in config.personnages_valides():
                    config.ajouter_personnage(
                        perso_id,
                        {
                            "nom_complet": perso_sec.get("nom_complet", perso_id),
                            "description": perso_sec.get("description", ""),
                            "ton": perso_sec.get("ton", "neutre"),
                            "tics_de_langage": perso_sec.get("tics_de_langage", []),
                        },
                        voice_id=perso_sec.get("voice_id", ""),
                        pan=perso_sec.get("pan", 0.0),
                    )

    # Validation des clés API au démarrage
    erreurs_api = config.valider_cles_api(dry_run=dry_run)
    if erreurs_api:
        console.print(Panel(
            "\n".join(f"[red]  {e}[/red]" for e in erreurs_api),
            title="Erreurs de configuration",
            border_style="red",
        ))
        raise RuntimeError("Configuration API invalide : " + "; ".join(erreurs_api))

    mode_str = "DRY RUN" if dry_run else "PRODUCTION"
    est_mode_saison = total_episodes > 0

    if est_mode_saison:
        console.print(panel_episode_saison(
            episode_id=episode_id,
            titre=titre,
            mode=mode_str,
            type_episode=type_episode,
            morale=morale or "non définie",
            saison_theme=saison_theme,
            episode_courant=episode_courant,
            total_episodes=total_episodes,
        ))
    else:
        console.print(panel_episode(
            episode_id=episode_id,
            titre=titre,
            mode=mode_str,
            type_episode=type_episode,
            morale=morale or "non définie",
        ))

    etapes = ["script", "review", "audio", "sfx", "montage", "metadonnees", "publication", "rapport"]
    # Mapper les statuts DB vers l'étape pipeline correspondante.
    # Chaque statut non-standard DOIT être ici, sinon etape_idx = 0 → restart total.
    _etape_mapping = {
        "waiting_script": "audio",        # script validé → reprendre à l'audio
        "waiting_montage": "metadonnees",  # montage validé → reprendre aux métadonnées
        "script_done": "audio",
        "review_done": "audio",
        "audio_done": "sfx",
        "sfx_done": "montage",
        "montage_done": "metadonnees",
        "metadonnees_done": "publication",
        "publication_done": "rapport",
        "interrupted": "script",           # fallback sûr — le checkpoint data a la bonne étape
        "erreur": "script",                # erreur handler checkpoint — restart propre
        "started": "script",               # production créée mais jamais avancée
    }
    etape_effective = _etape_mapping.get(etape_depart, etape_depart)
    if etape_effective != etape_depart:
        logger.info("Étape de reprise mappée : %s → %s", etape_depart, etape_effective)
    if etape_effective not in etapes:
        logger.error(
            "Étape de reprise inconnue : %r (ni dans etapes ni dans _etape_mapping) — "
            "redémarrage depuis le script par sécurité", etape_depart,
        )
        etape_effective = "script"
    etape_idx = etapes.index(etape_effective)
    _log_direct(f"etape_idx={etape_idx} ({etape_effective}), etapes à jouer: {etapes[etape_idx:]}")

    # ── Nettoyer les anciennes erreurs du rapport pour les étapes qui seront rejouées ──
    # Quand on reprend un checkpoint "empoisonné" (ex: montage échoué), le rapport
    # contient status="error" pour l'étape. Si le pipeline crashe AVANT d'atteindre
    # cette étape (ex: erreur de chargement script), l'error handler re-sauvegarde
    # le rapport tel quel — perpétuant la vieille erreur indéfiniment.
    # On nettoie ici les statuts error/failed des étapes qui vont être rejouées.
    if rapport.get("etapes"):
        for i in range(etape_idx, len(etapes)):
            step_name = etapes[i]
            step_data = rapport["etapes"].get(step_name, {})
            if step_data.get("status") in ("error", "failed"):
                logger.info(
                    "Nettoyage erreur précédente pour l'étape '%s' avant retry "
                    "(ancien status=%s, erreur=%s)",
                    step_name, step_data.get("status"), step_data.get("erreur", "?"),
                )
                # Supprimer l'étape erronée — elle sera recréée proprement
                del rapport["etapes"][step_name]
        # Nettoyer les flags d'erreur globaux du rapport
        rapport.pop("erreur", None)
        rapport.pop("erreur_montage", None)
        if rapport.get("status") == "failed":
            del rapport["status"]

    # Roadmap visuel des étapes
    console.print(panel_roadmap(etape_idx, dry_run=dry_run))

    # Initialiser les variables qui pourraient ne pas être définies lors d'une reprise
    chemin_hq = None
    resultat_montage = None
    duree_secondes = 0.0
    taille_bytes = 0
    score = 0
    meta = None
    chemin_meta = config.SCRIPTS_DIR / f"{episode_id}_meta.json"

    # Restaurer les variables depuis le checkpoint si on reprend après le montage
    if checkpoint_data and etape_idx > 4:
        montage_data = checkpoint_data.get("etapes", {}).get("montage", {})
        if montage_data.get("chemin_hq"):
            chemin_hq = Path(montage_data["chemin_hq"])
        duree_secondes = montage_data.get("duree_secondes", 0.0)
        taille_bytes = int(montage_data.get("taille_mb", 0) * 1024 * 1024) if montage_data.get("taille_mb") else 0
        resultat_montage = montage_data

    # Restaurer les flags validation_humaine depuis le checkpoint
    # pour que les prérequis de publication soient correctement vérifiés
    if checkpoint_data:
        cp_etapes = checkpoint_data.get("etapes", {})
        if cp_etapes.get("script", {}).get("validation_humaine"):
            rapport["etapes"].setdefault("script", {})["validation_humaine"] = True
        if cp_etapes.get("montage", {}).get("validation_humaine"):
            rapport["etapes"].setdefault("montage", {})["validation_humaine"] = True

    # Restaurer les métadonnées depuis le fichier si on reprend après l'étape metadonnees
    if etape_idx > 5:
        if not chemin_meta.exists():
            # Restaurer depuis Object Storage
            try:
                import persistent_storage
                persistent_storage.restore_metadonnees(episode_id, config.SCRIPTS_DIR)
                logger.info("Métadonnées restaurées depuis Object Storage : %s", chemin_meta)
            except Exception as e:
                logger.warning("Restauration métadonnées Object Storage échouée : %s", e)
        if chemin_meta.exists():
            with open(chemin_meta, "r", encoding="utf-8") as f:
                meta = json.load(f)
            logger.info("Métadonnées chargées depuis : %s", chemin_meta)
        else:
            raise FileNotFoundError(
                f"Reprise à l'étape {etape_depart} impossible : "
                f"le fichier de métadonnées {chemin_meta} est introuvable "
                f"(ni local, ni Object Storage)."
            )

    # Charger l'historique pour la continuité
    historique = charger_historique()

    script = None
    score = 0
    chemin_valide = config.SCRIPTS_DIR / f"{episode_id}_valide.json"

    # Si on reprend, charger le script existant et restaurer le score
    if etape_idx > 0:
        # Restaurer depuis Object Storage / DB si le fichier local est absent
        # (cas fréquent après un redéploiement Replit qui remet le FS à zéro)
        if not chemin_valide.exists():
            _restored = False
            # Tentative 1 : Object Storage
            try:
                import persistent_storage
                if persistent_storage.restore_script(episode_id, config.SCRIPTS_DIR):
                    logger.info("Script validé restauré depuis Object Storage : %s", chemin_valide)
                    _restored = True
            except Exception as e:
                logger.warning("Restauration Object Storage échouée : %s", e)
            # Tentative 2 : DB (ScriptRepo)
            if not _restored:
                try:
                    from db_models import ScriptRepo
                    db_script = ScriptRepo.charger_valide(episode_id)
                    if not db_script or not db_script.get("episode"):
                        db_script = ScriptRepo.charger_derniere_version(episode_id)
                    if db_script and db_script.get("episode"):
                        chemin_valide.parent.mkdir(parents=True, exist_ok=True)
                        with open(chemin_valide, "w", encoding="utf-8") as f:
                            json.dump(db_script, f, ensure_ascii=False, indent=2)
                        logger.info("Script validé restauré depuis la DB : %s", chemin_valide)
                        _restored = True
                except Exception as e:
                    logger.warning("Restauration DB échouée : %s", e)
            if not _restored:
                raise FileNotFoundError(
                    f"Reprise à l'étape {etape_depart} impossible : "
                    f"le script validé {chemin_valide} est introuvable "
                    f"(ni local, ni Object Storage, ni DB)."
                )
        # Charger le script
        try:
            with open(chemin_valide, "r", encoding="utf-8") as f:
                script = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(
                f"Script validé corrompu ({chemin_valide}) : {e}. "
                f"Supprimez-le et relancez la production."
            ) from e
        if checkpoint_data:
            score = checkpoint_data.get("etapes", {}).get("script", {}).get("score_review", 0)
        logger.info("Script chargé pour reprise : %s", chemin_valide)

    # ── Étape 1-2 : Scripteur + Reviewer ─────────────────────────────────────

    if etape_idx <= 1:
        console.print(f"\n{Typo.etape(1, 8, 'Génération du script')}")
        scripteur = Scripteur()
        corrections = None

        # Charger les corrections soumises depuis le web (modification demandée)
        web_corrections_path = config.SCRIPTS_DIR / f"{episode_id}_web_corrections.txt"
        if web_corrections_path.exists():
            try:
                web_text = web_corrections_path.read_text(encoding="utf-8").strip()
                if web_text:
                    corrections = web_text
                    console.print(
                        f"  [bold cyan]Corrections du producteur :[/bold cyan] {web_text[:200]}"
                    )
                web_corrections_path.unlink()  # Usage unique
            except Exception as e:
                logger.warning("Erreur lecture corrections web : %s", e)

        if max_iterations_review < 1:
            raise ValueError(f"max_iterations_review doit être >= 1, reçu {max_iterations_review}")

        # Charger les scripts validés des épisodes précédents de la saison
        # pour que le scripteur puisse lire les vrais dialogues
        scripts_precedents = _charger_scripts_precedents_saison(saison, numero)
        if scripts_precedents:
            console.print(
                f"  [bold cyan]Contexte sériel :[/bold cyan] "
                f"{len(scripts_precedents)} script(s) précédent(s) chargé(s) "
                f"({', '.join(s['episode_id'] for s in scripts_precedents)})"
            )

        # Charger l'arc state de l'épisode précédent pour injection N→N+1
        arc_state_precedent = None
        if numero == 1 and saison > 1:
            # Continuité inter-saisons : charger l'arc state du dernier épisode de la saison précédente
            plan_prec = config.charger_saison(saison - 1)
            if plan_prec:
                nb_eps_prec = len(plan_prec.get("saison", {}).get("episodes", []))
                if nb_eps_prec > 0:
                    ep_prec_id = f"S{saison - 1:02d}E{nb_eps_prec:02d}"
                    chemin_arc_prec = config.SCRIPTS_DIR / f"{ep_prec_id}_arc_state.json"
                    if chemin_arc_prec.exists():
                        try:
                            with open(chemin_arc_prec, "r", encoding="utf-8") as f:
                                arc_state_precedent = json.load(f)
                            console.print(
                                f"  [bold cyan]Arc state inter-saison :[/bold cyan] "
                                f"{ep_prec_id} (fin S{saison - 1:02d})"
                            )
                        except (json.JSONDecodeError, OSError) as e:
                            logger.warning("Arc state inter-saison %s illisible : %s", ep_prec_id, e)
        if numero > 1:
            ep_prec_id = f"S{saison:02d}E{numero - 1:02d}"
            chemin_arc_prec = config.SCRIPTS_DIR / f"{ep_prec_id}_arc_state.json"
            if chemin_arc_prec.exists():
                try:
                    with open(chemin_arc_prec, "r", encoding="utf-8") as f:
                        arc_state_precedent = json.load(f)
                    console.print(
                        f"  [bold cyan]Arc state précédent :[/bold cyan] "
                        f"{ep_prec_id} — {len(arc_state_precedent.get('moments_cles', []))} "
                        f"moments clés, {len(arc_state_precedent.get('questions_ouvertes', []))} "
                        f"questions ouvertes"
                    )
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Arc state %s illisible : %s", ep_prec_id, e)

        # ── Directeur Podcast — brief créatif pré-génération ──────────────
        brief_directeur = ""
        if not dry_run:
            try:
                directeur_brief = DirecteurPodcast()
                resultat_brief = directeur_brief.brief_creatif(
                    titre=titre, resume=resume, morale=morale,
                    type_episode=type_episode,
                    episode_plan=episode_plan,
                    contexte_saison=contexte_saison,
                )
                # Afficher le brief
                console.print(f"\n  {Icons.REVIEW} Brief créatif du directeur :")
                if resultat_brief.get("directives_ton"):
                    console.print(f"  Ton : {Typo.dim(resultat_brief['directives_ton'])}")
                if resultat_brief.get("accroche_suggestion"):
                    console.print(f"  Accroche : {Typo.dim(resultat_brief['accroche_suggestion'])}")
                moments = resultat_brief.get("moments_cles", [])
                if moments:
                    console.print("  Moments clés :")
                    for m in moments[:5]:
                        console.print(f"    - {m}")
                pieges = resultat_brief.get("pieges_a_eviter", [])
                if pieges:
                    console.print("[yellow]  Pièges à éviter :[/yellow]")
                    for p in pieges[:3]:
                        console.print(f"    ! {p}")

                # Construire le bloc texte à injecter dans le prompt du scripteur
                brief_lines = ["\n\nBRIEF CRÉATIF DU DIRECTEUR PODCAST :"]
                brief_lines.append(f"Ton : {resultat_brief.get('directives_ton', '')}")
                brief_lines.append(f"Accroche : {resultat_brief.get('accroche_suggestion', '')}")
                if moments:
                    brief_lines.append("Moments clés à ne pas manquer :")
                    for m in moments:
                        brief_lines.append(f"  - {m}")
                sfx_attendus = resultat_brief.get("sfx_attendus", [])
                if sfx_attendus:
                    brief_lines.append("SFX attendus :")
                    for s in sfx_attendus:
                        brief_lines.append(f"  - {s}")
                ambiances = resultat_brief.get("ambiances_suggerees", {})
                if ambiances:
                    brief_lines.append("Ambiances suggérées :")
                    for acte, amb in ambiances.items():
                        brief_lines.append(f"  - {acte} : {amb}")
                if pieges:
                    brief_lines.append("Pièges à éviter :")
                    for p in pieges:
                        brief_lines.append(f"  - {p}")
                perso_focus = resultat_brief.get("personnages_focus", "")
                if perso_focus:
                    brief_lines.append(f"Focus personnages : {perso_focus}")
                brief_directeur = "\n".join(brief_lines)

                rapport["etapes"]["brief_directeur"] = {
                    "directives_ton": resultat_brief.get("directives_ton", ""),
                    "nb_moments_cles": len(moments),
                    "nb_sfx_attendus": len(sfx_attendus),
                    "nb_pieges": len(pieges),
                }
            except Exception as e:
                logger.warning("Directeur Podcast (brief créatif) indisponible : %s", e)
                console.print(f"[yellow]  Brief créatif non disponible : {e}[/yellow]")

        # Combiner préférences producteur + brief directeur
        preferences_completes = _construire_bloc_preferences() + brief_directeur

        for iteration in range(1, max_iterations_review + 1):
            console.print(f"  Iteration {iteration}/{max_iterations_review}...")

            script = scripteur.generer(
                titre=titre, resume=resume, saison=saison, numero=numero,
                morale=morale, corrections=corrections, historique=historique,
                contexte_saison=contexte_saison, episode_plan=episode_plan,
                type_episode=type_episode,
                preferences_producteur=preferences_completes,
                scripts_precedents=scripts_precedents,
                arc_state_precedent=arc_state_precedent,
            )

            chemin_script = config.SCRIPTS_DIR / f"{episode_id}_v{iteration}.json"
            scripteur.sauvegarder(script, chemin_script)
            nb_mots = scripteur.compter_mots(script)
            console.print(f"  Script v{iteration} : {nb_mots} mots, {len(script['episode']['segments'])} segments")

            # Sauvegarder en DB
            script_db_id = None
            if _use_db():
                try:
                    script_db_id = ScriptRepo.sauvegarder(
                        episode_id=episode_id,
                        script=script,
                        nb_mots=nb_mots,
                        source="scripteur",
                    )
                except Exception as e:
                    logger.warning("DB indisponible pour sauvegarde script : %s", e)

            # ── Reviewer ─────────────────────────────────────────────────────

            console.print(f"\n{Typo.etape(2, 8, f'Relecture (itération {iteration})')}")
            reviewer = Reviewer()
            resultat_review = reviewer.evaluer(script)
            score = resultat_review["review"]["score"]

            console.print(table_review(
                score, resultat_review["review"].get("details_score", {})
            ))

            if resultat_review["review"]["corrections"]:
                console.print("[yellow]  Corrections :[/yellow]")
                for c in resultat_review["review"]["corrections"]:
                    console.print(f"    - {c}")

            if resultat_review["review"]["alertes"]:
                console.print("[red]  Alertes :[/red]")
                for a in resultat_review["review"]["alertes"]:
                    console.print(f"    ! {a}")

            # Sauvegarder review en DB
            if _use_db():
                try:
                    ReviewRepo.sauvegarder(
                        episode_id=episode_id,
                        script_id=script_db_id or 0,
                        resultat_review=resultat_review,
                    )
                except Exception as e:
                    logger.warning("DB indisponible pour sauvegarde review : %s", e)

            seuil_effectif = Reviewer.SEUILS_PAR_TYPE.get(type_episode, 7)
            if reviewer.est_valide(resultat_review, seuil=seuil_effectif):
                script = {"episode": resultat_review["episode"]}
                console.print(f"[{Palette.SUCCES}]  Script validé (score {score}/10, seuil {seuil_effectif}).[/]")
                break

            console.print(f"[yellow]  Score insuffisant ({score}/10 < {seuil_effectif}) — relance du scripteur[/yellow]")
            corrections = reviewer.extraire_corrections(resultat_review)

        else:
            console.print(
                f"[red]  Score final : {score}/10 apres {max_iterations_review} iterations. "
                "Poursuite avec le meilleur script disponible.[/red]"
            )
            script = {"episode": resultat_review["episode"]}

        scripteur.sauvegarder(script, chemin_valide)

        # ── Vérifications post-génération (indépendantes du LLM) ─────────
        violations_mots = Reviewer.verifier_mots_interdits(script)
        if violations_mots:
            console.print(f"[red]  Mots interdits détectés ({len(violations_mots)}) :[/red]")
            for v in violations_mots:
                console.print(f"    ! {v}")
            rapport.setdefault("alertes_post_generation", []).extend(violations_mots)

        alertes_questions = Reviewer.verifier_questions_ouvertes(script, historique)
        if alertes_questions:
            console.print("[yellow]  Alertes continuité :[/yellow]")
            for a in alertes_questions:
                console.print(f"    ! {a}")
            rapport.setdefault("alertes_post_generation", []).extend(alertes_questions)

        # Validation ratio biblique (≥60%) — CRITIQUE
        ratio_bib, alertes_bib = Reviewer.verifier_ratio_biblique(script)
        if alertes_bib:
            console.print(f"[red]  Ratio biblique : {ratio_bib:.0%} (minimum 60%) :[/red]")
            for a in alertes_bib:
                console.print(f"    ! {a}")
            rapport.setdefault("alertes_post_generation", []).extend(alertes_bib)
        else:
            console.print(f"  Ratio biblique : {ratio_bib:.0%} {Icons.OK}")
        rapport.setdefault("metriques", {})["ratio_biblique"] = round(ratio_bib, 2)

        # Validation ratio Papy/enfants
        ratio_enf, alertes_enf = Reviewer.verifier_ratio_papy_enfants(script)
        if alertes_enf:
            console.print("[yellow]  Ratio Papy/enfants :[/yellow]")
            for a in alertes_enf:
                console.print(f"    ! {a}")
            rapport.setdefault("alertes_post_generation", []).extend(alertes_enf)
        rapport.setdefault("metriques", {})["ratio_enfants"] = round(ratio_enf, 2)

        # Validation teasing naturel
        alertes_teasing = Reviewer.verifier_teasing(script)
        if alertes_teasing:
            console.print("[yellow]  Alertes teasing :[/yellow]")
            for a in alertes_teasing:
                console.print(f"    ! {a}")
            rapport.setdefault("alertes_post_generation", []).extend(alertes_teasing)

        # Validation pauses
        alertes_pauses = Reviewer.verifier_pauses(script)
        if alertes_pauses:
            console.print("[yellow]  Alertes pauses :[/yellow]")
            for a in alertes_pauses:
                console.print(f"    ! {a}")
            rapport.setdefault("alertes_post_generation", []).extend(alertes_pauses)

        alertes_sfx_overlay = Reviewer.verifier_sfx_overlay_duree(script)
        if alertes_sfx_overlay:
            console.print("[yellow]  Alertes SFX overlay trop courts :[/yellow]")
            for a in alertes_sfx_overlay:
                console.print(f"    ! {a}")
            rapport.setdefault("alertes_post_generation", []).extend(alertes_sfx_overlay)

        # Marquer comme validé en DB
        if _use_db():
            try:
                ScriptRepo.sauvegarder(
                    episode_id=episode_id,
                    script=script,
                    nb_mots=scripteur.compter_mots(script),
                    is_validated=True,
                    source="reviewer",
                )
            except Exception as e:
                logger.warning("DB indisponible pour script validé : %s", e)

        duree_estimee = reviewer.estimer_duree(script)
        console.print(f"  Duree estimee : {duree_estimee:.1f} minutes")

        rapport["etapes"]["script"] = {
            "score_review": score,
            "iterations": iteration,
            "nb_mots": scripteur.compter_mots(script),
            "duree_estimee_min": round(duree_estimee, 1),
            "chemin": str(chemin_valide),
        }

        # Upload script vers Object Storage (persistance inter-deploy)
        try:
            import persistent_storage
            script_key = persistent_storage.upload_script(episode_id, chemin_valide)
            if script_key:
                rapport["etapes"]["script"]["object_storage"] = script_key
        except Exception as e:
            logger.warning("Object Storage indisponible pour script : %s", e)

        # ── Validation ambiances musicales ──────────────────────────────
        ambiance_validation = DirecteurPodcast.valider_ambiances(script)
        if ambiance_validation["alertes"]:
            console.print(f"[yellow]  Ambiances musicales — {len(ambiance_validation['alertes'])} alerte(s) :[/yellow]")
            for a in ambiance_validation["alertes"]:
                console.print(f"    ! {a}")
            rapport.setdefault("alertes_post_generation", []).extend(ambiance_validation["alertes"])
        else:
            stats_amb = ambiance_validation["stats"]
            dyn = "dynamique" if stats_amb["dynamique"] else "uniforme"
            console.print(
                f"  Ambiances : {stats_amb['ambiance_principale']} ({dyn}, "
                f"{stats_amb['nb_ambiances_distinctes']} variantes)"
            )

        # ── Directeur Podcast — validation créative + audience (BLOQUANT) ──
        # Le directeur peut demander jusqu'à MAX_RETOURS_DIRECTEUR_SCRIPT corrections.
        # Si "retravailler" ou "ajustements_mineurs" avec critiques, le script est
        # renvoyé au scripteur avec les recommandations du directeur comme corrections.
        MAX_RETOURS_DIRECTEUR_SCRIPT = 2
        directeur_ok = False

        if not dry_run:
            for tour_dir in range(1, MAX_RETOURS_DIRECTEUR_SCRIPT + 2):  # +1 pour la dernière éval
                console.print(f"\n{Typo.etape(2, 8, f'Validation Directeur Podcast (tour {tour_dir})')}")
                try:
                    directeur = DirecteurPodcast()
                    contexte_directeur = {
                        "type_episode": type_episode,
                        "score_reviewer": score,
                        "alertes": rapport.get("alertes_post_generation", []),
                        "metriques": rapport.get("metriques", {}),
                    }
                    resultat_directeur = directeur.evaluer(script, contexte=contexte_directeur)
                    dir_data = resultat_directeur.get("directeur", {})
                    note_dir = dir_data.get("note_globale", 0)
                    verdict = dir_data.get("verdict", "?")
                    note_aud = directeur.note_audience(resultat_directeur)

                    # Affichage verdict
                    couleur_verdict = {
                        "feu_vert": Palette.SUCCES,
                        "ajustements_mineurs": "yellow",
                        "retravailler": "red",
                    }.get(verdict, "white")
                    console.print(
                        f"  Directeur : [{couleur_verdict}]{verdict.replace('_', ' ').upper()}[/] "
                        f"(note {note_dir}/10, audience {note_aud}/10)"
                    )

                    # Synthèse
                    if dir_data.get("synthese"):
                        console.print(f"  {Typo.dim(dir_data['synthese'])}")

                    # Axes détaillés
                    for axe_nom, axe_data in dir_data.get("axes", {}).items():
                        axe_label = axe_nom.replace("_", " ").title()
                        axe_note = axe_data.get("note", 0)
                        console.print(f"    {axe_label} : {axe_note}/10")

                    # Recommandations
                    recommandations = directeur.extraire_recommandations(resultat_directeur)
                    if recommandations:
                        console.print("[yellow]  Recommandations :[/yellow]")
                        for r in recommandations:
                            console.print(f"    - {r}")

                    # Points forts
                    points_forts = dir_data.get("points_forts", [])
                    if points_forts:
                        console.print(f"[{Palette.SUCCES}]  Points forts :[/]")
                        for p in points_forts:
                            console.print(f"    + {p}")

                    # Réactions des personas
                    personas = resultat_directeur.get("personas", {})
                    for persona_key, persona_data in personas.items():
                        nom = persona_key.replace("_", " ").title()
                        reaction = persona_data.get("reaction", "")
                        p_note = persona_data.get("note", 0)
                        console.print(f"  {Typo.dim(f'{nom} ({p_note}/10) : {reaction}')}")

                    # Sauvegarder dans le rapport
                    rapport["etapes"]["directeur_podcast"] = {
                        "note_globale": note_dir,
                        "verdict": verdict,
                        "note_audience": note_aud,
                        "tour": tour_dir,
                        "axes": {
                            k: v.get("note", 0) for k, v in dir_data.get("axes", {}).items()
                        },
                        "nb_recommandations_critiques": sum(
                            1 for r in dir_data.get("recommandations", [])
                            if r.get("priorite") == "critique"
                        ),
                        "personas": {
                            k: {"note": v.get("note", 0)}
                            for k, v in personas.items()
                        },
                    }

                    # ── Verdict : feu vert → on continue ────────────────────
                    if verdict == "feu_vert":
                        console.print(f"[{Palette.SUCCES}]  {Icons.OK} Feu vert du directeur — script approuvé.[/]")
                        directeur_ok = True
                        break

                    # ── Verdict : retravailler ou ajustements avec critiques ──
                    has_critiques = directeur.a_critiques(resultat_directeur)

                    if verdict == "ajustements_mineurs" and not has_critiques:
                        # Ajustements mineurs sans critiques → on accepte
                        console.print(
                            f"[yellow]  {Icons.ATTENTION_IC} Ajustements mineurs suggérés "
                            f"(pas de critique bloquante) — script accepté.[/yellow]"
                        )
                        directeur_ok = True
                        break

                    # ── Verdict bloquant : renvoi au scripteur ──────────────
                    if tour_dir > MAX_RETOURS_DIRECTEUR_SCRIPT:
                        # On a atteint le max de tours → on accepte tel quel
                        console.print(
                            f"[yellow]  {Icons.ATTENTION_IC} Max retours directeur atteint "
                            f"({MAX_RETOURS_DIRECTEUR_SCRIPT}) — script accepté avec réserves.[/yellow]"
                        )
                        directeur_ok = True
                        break

                    # Extraire les corrections du directeur pour le scripteur
                    corrections_directeur = recommandations
                    nb_critiques = sum(
                        1 for r in dir_data.get("recommandations", [])
                        if r.get("priorite") == "critique"
                    )
                    console.print(
                        f"\n[bold red]  {Icons.ATTENTION_IC} Le directeur demande une réécriture "
                        f"({nb_critiques} critique(s)). Relance du scripteur...[/bold red]"
                    )

                    # Relancer le scripteur avec les corrections du directeur
                    corrections = corrections_directeur
                    script = scripteur.generer(
                        titre=titre, resume=resume, saison=saison, numero=numero,
                        morale=morale, corrections=corrections, historique=historique,
                        contexte_saison=contexte_saison, episode_plan=episode_plan,
                        type_episode=type_episode,
                        preferences_producteur=preferences_completes,
                        scripts_precedents=scripts_precedents,
                        arc_state_precedent=arc_state_precedent,
                    )

                    # Re-review le script corrigé
                    resultat_review = reviewer.evaluer(script, type_episode=type_episode)
                    score = resultat_review["review"]["note"]
                    seuil_effectif = Reviewer.SEUILS_PAR_TYPE.get(type_episode, 7)
                    console.print(
                        f"  Re-review après corrections directeur : {score}/10 "
                        f"(seuil {seuil_effectif})"
                    )
                    if resultat_review.get("episode"):
                        script = {"episode": resultat_review["episode"]}

                    # Sauvegarder la version corrigée
                    chemin_corrige = config.SCRIPTS_DIR / f"{episode_id}_dir_v{tour_dir}.json"
                    scripteur.sauvegarder(script, chemin_corrige)
                    chemin_valide = chemin_corrige
                    console.print(
                        f"  Script corrigé v{tour_dir} : {scripteur.compter_mots(script)} mots"
                    )

                except Exception as e:
                    logger.warning("Directeur Podcast indisponible : %s", e)
                    console.print(f"[yellow]  Directeur Podcast non disponible : {e}[/yellow]")
                    directeur_ok = True  # En cas d'erreur, on ne bloque pas
                    break
        else:
            directeur_ok = True  # dry-run → pas de validation directeur

        # Enregistrer le statut directeur dans le rapport
        if "directeur_podcast" in rapport.get("etapes", {}):
            rapport["etapes"]["directeur_podcast"]["approuve"] = directeur_ok

        _log_step_duration("Script + Review")

        # Checkpoint après script (inclut le chemin du script validé)
        sauvegarder_checkpoint(episode_id, "audio", {
            "episode_id": episode_id, "titre": titre, "resume": resume,
            "saison": saison, "numero": numero, "morale": morale,
            "type_episode": type_episode,
            "dry_run": dry_run, "rapport": rapport,
            "chemin_script_valide": str(chemin_valide),
            "pubdate_offset_seconds": pubdate_offset_seconds,
            "stop_after": stop_after,
        })

        # ── Validation humaine : script ──────────────────────────────────────

        if not auto:
            console.print(
                "\n[bold magenta]VALIDATION — Relisez le script avant "
                "la production audio[/bold magenta]"
            )
            script, score = _validation_script(
                script, chemin_valide, morale,
                resume=resume,
                contexte_saison=contexte_saison,
                episode_plan=episode_plan,
                type_episode=type_episode,
                score=score,
                rapport=rapport,
            )
            scripteur.sauvegarder(script, chemin_valide)
            duree_estimee = reviewer.estimer_duree(script)
            rapport["etapes"]["script"]["validation_humaine"] = True

    # ── Stop après script (mode web : attendre validation avant audio) ────────
    if stop_after == "script":
        rapport["stop_after"] = "script"
        rapport["status"] = "waiting_validation"
        console.print(
            f"\n[bold cyan]  Pipeline arrêté après le script — "
            f"en attente de validation.[/bold cyan]"
        )
        # Sauvegarder le rapport partiel
        chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
        with fichier_lock(chemin_rapport):
            with open(chemin_rapport, "w", encoding="utf-8") as f_out:
                json.dump(rapport, f_out, ensure_ascii=False, indent=2, default=str)
        # Upload rapport vers Object Storage (survit aux redéploiements)
        try:
            import persistent_storage
            persistent_storage.upload_rapport(episode_id, chemin_rapport)
        except Exception as e:
            logger.warning("Object Storage indisponible pour rapport (stop_after=script) : %s", e)
        # Ajouter à l'historique dès maintenant pour que la page de validation
        # web affiche l'épisode avec les données à jour (titre, résumé, score, etc.)
        ajouter_historique(rapport, script)
        # Marquer la production DB comme en attente (pas "in_progress" indéfiniment)
        _pid = getattr(_production_local, 'production_id', None)
        if _use_db() and _pid:
            try:
                ProductionRepo.maj_etape(
                    _pid, etape="waiting_script",
                    rapport=rapport,
                )
            except Exception as e:
                logger.warning("DB indisponible pour maj_etape waiting_script : %s", e)
        return rapport

    # ── Garde : si le checkpoint demande montage mais que les segments audio
    #    sont introuvables (ni local, ni Object Storage), reculer à l'étape audio
    #    pour régénérer. Cela arrive quand les segments ont été générés avant
    #    l'introduction de l'upload Object Storage, puis perdus au redéploiement.
    if not dry_run and etape_idx > 2:
        segments_episode_dir = config.SEGMENTS_DIR / episode_id
        _segments_present = (
            segments_episode_dir.exists()
            and any(segments_episode_dir.glob("*.mp3"))
        )
        if not _segments_present:
            # Tenter la restauration depuis Object Storage
            try:
                import persistent_storage
                nb_restored = persistent_storage.restore_segments(episode_id, config.SEGMENTS_DIR)
                if nb_restored > 0:
                    logger.info(
                        "Segments restaurés depuis Object Storage : %d fichiers", nb_restored
                    )
                    console.print(
                        f"  [cyan]Segments restaurés depuis Object Storage : "
                        f"{nb_restored} fichiers[/cyan]"
                    )
                    _segments_present = True
            except Exception as e:
                logger.warning("Restauration segments Object Storage échouée : %s", e)

        if not _segments_present:
            logger.warning(
                "Segments introuvables pour %s (ni local, ni Object Storage). "
                "Fallback : régénération audio depuis le script validé.",
                episode_id,
            )
            console.print(
                f"\n  [bold yellow]Segments audio introuvables — "
                f"régénération automatique depuis le script validé[/bold yellow]"
            )
            etape_idx = 2  # Reculer à l'étape audio

        # ── Nettoyage des segments périmés ──
        # Après restauration depuis Object Storage, il peut y avoir des segments
        # d'anciennes productions (IDs différents du script actuel).
        # Les supprimer pour éviter toute confusion lors du montage.
        if _segments_present and script:
            _ids_attendus = {s["id"] for s in script["episode"]["segments"]}
            _voix_ids = {
                s["id"] for s in script["episode"]["segments"]
                if s["personnage"] != "sfx"
            }
            _nb_nettoyes = 0
            for _old_mp3 in segments_episode_dir.glob("*.mp3"):
                _seg_id = _old_mp3.stem  # ex: "seg_001" from "seg_001.mp3"
                if _seg_id not in _ids_attendus:
                    try:
                        _old_mp3.unlink()
                        _nb_nettoyes += 1
                    except OSError:
                        pass
            if _nb_nettoyes > 0:
                _log_direct(
                    f"Nettoyage : {_nb_nettoyes} segments périmés supprimés "
                    f"(ne correspondent pas au script actuel avec {len(_ids_attendus)} segments)"
                )
                logger.info(
                    "Segments périmés nettoyés : %d fichiers supprimés "
                    "(script actuel : %d segments)",
                    _nb_nettoyes, len(_ids_attendus),
                )

            # Vérifier que les segments voix du script actuel sont présents
            _fichiers_restants = {f.stem for f in segments_episode_dir.glob("*.mp3")}
            _voix_manquants = _voix_ids - _fichiers_restants
            _sfx_ids = {
                s["id"] for s in script["episode"]["segments"]
                if s["personnage"] == "sfx"
            }
            _sfx_manquants = _sfx_ids - _fichiers_restants

            _total_attendus = len(_ids_attendus)
            _total_presents = len(_fichiers_restants)
            _total_manquants = len(_voix_manquants) + len(_sfx_manquants)

            if _total_manquants > 0:
                _log_direct(
                    f"Segments : {_total_presents}/{_total_attendus} présents, "
                    f"{len(_voix_manquants)} voix manquants, "
                    f"{len(_sfx_manquants)} SFX manquants"
                )

            if len(_voix_manquants) > len(_voix_ids) * 0.5:
                # >50% voix manquants → régénérer tout l'audio
                _log_direct(
                    f"Après nettoyage : {len(_voix_manquants)}/{len(_voix_ids)} "
                    f"segments voix manquants — régénération audio nécessaire"
                )
                etape_idx = 2  # Reculer à audio
            elif _voix_manquants or _sfx_manquants:
                # Quelques segments manquants (voix ≤50% + SFX) → régénérer audio+SFX
                if _voix_manquants:
                    _log_direct(
                        f"{len(_voix_manquants)}/{len(_voix_ids)} segments voix manquants "
                        f"+ {len(_sfx_manquants)} SFX — régénération audio nécessaire"
                    )
                    etape_idx = 2  # Régénérer voix (l'étape audio ne regénère que les manquants)
                elif _sfx_manquants:
                    _log_direct(
                        f"Voix OK, {len(_sfx_manquants)}/{len(_sfx_ids)} SFX manquants "
                        f"— régénération SFX nécessaire"
                    )
                    etape_idx = min(etape_idx, 3)  # SFX seulement

    # ── Étape 3 : Production audio (voix) ─────────────────────────────────────

    if etape_idx <= 2:
        if dry_run:
            console.print(f"\n{Typo.etape(3, 8, 'Audio')}  {Typo.attention('SAUTÉ — dry-run')}")
            rapport["etapes"]["audio"] = {"status": "skipped (dry-run)"}
        else:
            console.print(f"\n{Typo.etape(3, 8, 'Audio — Production voix')}")
            producteur = ProducteurAudio()

            segments_voix = [
                s for s in script["episode"]["segments"] if s["personnage"] != "sfx"
            ]
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Generation des segments audio...",
                    total=len(segments_voix),
                )
                fichiers_audio = producteur.produire_episode(script)
                progress.update(task, completed=len(segments_voix))

            nb_attendus = len(segments_voix)
            nb_recus = len(fichiers_audio)
            console.print(f"  {nb_recus} segments voix générés")
            if nb_recus < nb_attendus:
                console.print(
                    f"  [{Palette.ATTENTION}]{Icons.ATTENTION_IC} {nb_attendus - nb_recus} "
                    f"segment(s) manquant(s) — sera(ont) remplacé(s) par du silence au montage.[/]"
                )
            rapport["etapes"]["audio"] = {
                "nb_segments": nb_recus,
                "nb_segments_attendus": nb_attendus,
                "caracteres": dict(producteur.caracteres_utilises),
            }

            # Enregistrer les segments audio et coûts en DB
            if _use_db():
                try:
                    for seg_audio in script["episode"]["segments"]:
                        if seg_audio["personnage"] == "sfx":
                            continue
                        chemin_seg = config.SEGMENTS_DIR / episode_id / f"{seg_audio['id']}.mp3"
                        nb_chars = len(seg_audio.get("texte", ""))
                        FichierAudioRepo.enregistrer(
                            episode_id=episode_id,
                            type_fichier="segment_voix",
                            chemin=str(chemin_seg),
                            production_id=getattr(_production_local, 'production_id', None),
                            segment_id=seg_audio["id"],
                            personnage=seg_audio["personnage"],
                            source="elevenlabs",
                            nb_caracteres=nb_chars,
                        )
                    # Coût ElevenLabs TTS
                    total_chars = sum(producteur.caracteres_utilises.values())
                    cout_tts = total_chars * config.COUTS["elevenlabs_par_caractere"]
                    CoutRepo.enregistrer(
                        episode_id=episode_id,
                        service="elevenlabs_tts",
                        cout_estime=cout_tts,
                        detail={"caracteres": dict(producteur.caracteres_utilises)},
                        production_id=getattr(_production_local, 'production_id', None),
                    )
                except Exception as e:
                    logger.warning("DB indisponible pour enregistrement audio : %s", e)

            # Upload segments voix vers Object Storage (survie au redéploiement)
            try:
                import persistent_storage
                nb_uploaded = persistent_storage.upload_segments(episode_id, config.SEGMENTS_DIR)
                if nb_uploaded > 0:
                    logger.info("Segments voix uploadés : %d fichiers", nb_uploaded)
            except Exception as e:
                logger.warning("Object Storage indisponible pour segments voix : %s", e)

            _log_step_duration("Audio TTS")

            sauvegarder_checkpoint(episode_id, "sfx", {
                "episode_id": episode_id, "titre": titre, "resume": resume,
                "saison": saison, "numero": numero, "morale": morale,
                "type_episode": type_episode,
                "dry_run": dry_run, "rapport": rapport,
                "pubdate_offset_seconds": pubdate_offset_seconds,
                "stop_after": stop_after,
            })

    # ── Stop après audio (survie au recyclage container) ──────────────────────
    if stop_after == "audio":
        # Le checkpoint sauvé ci-dessus (etape="sfx") garde stop_after="audio".
        # On le met à jour vers "montage" pour que l'auto-resume ne boucle pas
        # sur le stop_after="audio" si le chaînage web échoue.
        sauvegarder_checkpoint(episode_id, "sfx", {
            "episode_id": episode_id, "titre": titre, "resume": resume,
            "saison": saison, "numero": numero, "morale": morale,
            "type_episode": type_episode,
            "dry_run": dry_run, "rapport": rapport,
            "pubdate_offset_seconds": pubdate_offset_seconds,
            "stop_after": "montage",  # Destination finale, pas l'étape intermédiaire
        })
        rapport["stop_after"] = "audio"
        rapport["status"] = "audio_done"
        console.print(
            f"\n[bold cyan]  Pipeline arrêté après l'audio — "
            f"SFX et montage dans le prochain job.[/bold cyan]"
        )
        chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
        with fichier_lock(chemin_rapport):
            with open(chemin_rapport, "w", encoding="utf-8") as f_out:
                json.dump(rapport, f_out, ensure_ascii=False, indent=2, default=str)
        try:
            import persistent_storage
            persistent_storage.upload_rapport(episode_id, chemin_rapport)
        except Exception as e:
            logger.warning("Object Storage indisponible pour rapport (stop_after=audio) : %s", e)
        ajouter_historique(rapport, script)
        _pid = getattr(_production_local, 'production_id', None)
        if _use_db() and _pid:
            try:
                ProductionRepo.maj_etape(
                    _pid, etape="audio_done",
                    rapport=rapport,
                )
            except Exception as e:
                logger.warning("DB indisponible pour maj_etape audio_done : %s", e)
        return rapport

    # ── Étape 4 : Bruitages (SFX) ─────────────────────────────────────────────

    if etape_idx <= 3:
        nb_sfx = len([s for s in script["episode"]["segments"] if s["personnage"] == "sfx"])

        if dry_run:
            console.print(f"\n{Typo.etape(4, 8, 'SFX Bruitages')}  {Typo.attention(f'SAUTÉ — dry-run ({nb_sfx} SFX)')}")
            rapport["etapes"]["sfx"] = {"status": "skipped (dry-run)", "nb_sfx": nb_sfx}
        elif nb_sfx == 0:
            console.print(f"\n{Typo.etape(4, 8, 'SFX Bruitages')}  {Typo.dim('aucun dans le script')}")
            rapport["etapes"]["sfx"] = {"status": "no sfx segments", "nb_sfx": 0}
        else:
            console.print(f"\n{Typo.etape(4, 8, f'SFX Bruitages ({nb_sfx})')}")

            # Pré-validation SFX par le directeur podcast
            sfx_validation = DirecteurPodcast.valider_sfx_pour_generation(script)
            stats_sfx_pre = sfx_validation["stats"]
            console.print(
                f"  Pré-validation SFX : {stats_sfx_pre['nb_sfx']} SFX "
                f"({stats_sfx_pre['nb_overlay']} overlay, {stats_sfx_pre['nb_insert']} insert)"
            )
            if sfx_validation["alertes"]:
                console.print(f"[yellow]  {len(sfx_validation['alertes'])} alerte(s) SFX :[/yellow]")
                for a in sfx_validation["alertes"][:10]:
                    console.print(f"    ! {a}")
                if len(sfx_validation["alertes"]) > 10:
                    console.print(f"    ... et {len(sfx_validation['alertes']) - 10} autres")
            rapport.setdefault("alertes_post_generation", []).extend(sfx_validation["alertes"])

            sfx_provider = SfxProvider()
            fichiers_sfx = sfx_provider.produire_sfx(script)

            console.print(f"  {len(fichiers_sfx)} bruitages générés/téléchargés")
            for seg_id, source in sfx_provider.stats.items():
                console.print(f"    {seg_id} : {source}")

            rapport["etapes"]["sfx"] = {
                "nb_sfx": len(fichiers_sfx),
                "sources": dict(sfx_provider.stats),
                "pre_validation": sfx_validation["stats"],
            }

            # Audit niveaux audio des SFX générés
            if fichiers_sfx:
                try:
                    audit_sfx = sfx_provider.auditer_niveaux_audio(script, fichiers_sfx)
                    stats_audit = audit_sfx["stats"]
                    console.print(
                        f"  Audit audio : {stats_audit['nb_ok']}/{stats_audit['nb_sfx_audites']} "
                        f"SFX OK (niveau moyen {stats_audit.get('dbfs_moyen', '?')} dBFS)"
                    )
                    if audit_sfx["alertes"]:
                        console.print(f"[yellow]  {len(audit_sfx['alertes'])} alerte(s) audio :[/yellow]")
                        for a in audit_sfx["alertes"][:5]:
                            console.print(f"    ! {a}")
                    rapport["etapes"]["sfx"]["audit_audio"] = {
                        "ok": audit_sfx["ok"],
                        "nb_ok": stats_audit["nb_ok"],
                        "nb_problemes": stats_audit["nb_problemes"],
                        "dbfs_moyen": stats_audit.get("dbfs_moyen"),
                    }
                    rapport.setdefault("alertes_post_generation", []).extend(audit_sfx["alertes"])
                except Exception as e:
                    logger.warning("Audit audio SFX échoué : %s", e)

            # Enregistrer les SFX en DB
            if _use_db():
                try:
                    for seg_id, source in sfx_provider.stats.items():
                        chemin_sfx = config.SEGMENTS_DIR / episode_id / f"{seg_id}.mp3"
                        FichierAudioRepo.enregistrer(
                            episode_id=episode_id,
                            type_fichier="segment_sfx",
                            chemin=str(chemin_sfx),
                            production_id=getattr(_production_local, 'production_id', None),
                            segment_id=seg_id,
                            personnage="sfx",
                            source=source,
                        )
                    # Coût SFX ElevenLabs
                    nb_sfx_el = sum(1 for s in sfx_provider.stats.values() if s == "elevenlabs")
                    if nb_sfx_el > 0:
                        CoutRepo.enregistrer(
                            episode_id=episode_id,
                            service="elevenlabs_sfx",
                            cout_estime=nb_sfx_el * config.COUTS["elevenlabs_sfx_par_generation"],
                            detail={"nb_sfx_elevenlabs": nb_sfx_el},
                            production_id=getattr(_production_local, 'production_id', None),
                        )
                except Exception as e:
                    logger.warning("DB indisponible pour enregistrement SFX : %s", e)

        # Upload segments SFX vers Object Storage (les SFX sont dans le même dossier)
        if not dry_run and nb_sfx > 0:
            try:
                import persistent_storage
                nb_uploaded = persistent_storage.upload_segments(episode_id, config.SEGMENTS_DIR)
                if nb_uploaded > 0:
                    logger.info("Segments (voix+SFX) uploadés : %d fichiers", nb_uploaded)
            except Exception as e:
                logger.warning("Object Storage indisponible pour segments SFX : %s", e)

        _log_step_duration("SFX Bruitages")

        # Checkpoint après SFX (manquant auparavant — perte de données SFX sur crash)
        sauvegarder_checkpoint(episode_id, "montage", {
            "episode_id": episode_id, "titre": titre, "resume": resume,
            "saison": saison, "numero": numero, "morale": morale,
            "type_episode": type_episode,
            "dry_run": dry_run, "rapport": rapport,
            "pubdate_offset_seconds": pubdate_offset_seconds,
            "stop_after": stop_after,
        })

    # ── Stop après SFX (survie au recyclage container) ────────────────────────
    if stop_after == "sfx":
        # Mettre à jour le checkpoint avec stop_after="montage" pour l'auto-resume
        sauvegarder_checkpoint(episode_id, "montage", {
            "episode_id": episode_id, "titre": titre, "resume": resume,
            "saison": saison, "numero": numero, "morale": morale,
            "type_episode": type_episode,
            "dry_run": dry_run, "rapport": rapport,
            "pubdate_offset_seconds": pubdate_offset_seconds,
            "stop_after": "montage",  # Destination finale, pas l'étape intermédiaire
        })
        rapport["stop_after"] = "sfx"
        rapport["status"] = "sfx_done"
        console.print(
            f"\n[bold cyan]  Pipeline arrêté après les SFX — "
            f"montage dans le prochain job.[/bold cyan]"
        )
        chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
        with fichier_lock(chemin_rapport):
            with open(chemin_rapport, "w", encoding="utf-8") as f_out:
                json.dump(rapport, f_out, ensure_ascii=False, indent=2, default=str)
        try:
            import persistent_storage
            persistent_storage.upload_rapport(episode_id, chemin_rapport)
        except Exception as e:
            logger.warning("Object Storage indisponible pour rapport (stop_after=sfx) : %s", e)
        ajouter_historique(rapport, script)
        _pid = getattr(_production_local, 'production_id', None)
        if _use_db() and _pid:
            try:
                ProductionRepo.maj_etape(
                    _pid, etape="sfx_done",
                    rapport=rapport,
                )
            except Exception as e:
                logger.warning("DB indisponible pour maj_etape sfx_done : %s", e)
        return rapport

    # ── Étape 5 : Montage ─────────────────────────────────────────────────────

    if etape_idx <= 4:
        _log_direct("Entrée étape 5 — Montage")
        if dry_run:
            console.print(f"\n{Typo.etape(5, 8, 'Montage')}  {Typo.attention('SAUTÉ — dry-run')}")
            rapport["etapes"]["montage"] = {"status": "skipped (dry-run)"}
            reviewer = Reviewer()
            duree_estimee = reviewer.estimer_duree(script)
            duree_secondes = duree_estimee * 60
            taille_bytes = 0
            chemin_hq = None
        else:
            _log_direct(f"Montage — {len(script['episode']['segments'])} segments dans le script")
            console.print(f"\n{Typo.etape(5, 8, 'Montage')}")

            # ── Restaurer le WAV intermédiaire depuis Object Storage si nécessaire ──
            # Si le container a été recyclé pendant l'export MP3, le WAV intermédiaire
            # (étapes 1-8 déjà complétées) peut être en Object Storage.
            _wav_checkpoint_name = f"{episode_id}_{_slug(titre)}_pre_export.wav"
            _wav_checkpoint_path = config.OUTPUT_DIR / _wav_checkpoint_name
            if not _wav_checkpoint_path.exists():
                try:
                    import persistent_storage
                    _wav_key = persistent_storage.PREFIX_MONTAGE_WAV + f"{episode_id}_pre_export.wav"
                    if persistent_storage.download_file(_wav_key, _wav_checkpoint_path):
                        logger.info(
                            "WAV intermédiaire restauré depuis Object Storage — "
                            "montage reprendra à l'export MP3"
                        )
                        console.print(
                            "  [cyan]WAV intermédiaire restauré — "
                            "reprise à l'export MP3 (skip étapes 1-8)[/cyan]"
                        )
                except Exception as e_wav_restore:
                    logger.debug("Pas de WAV intermédiaire en Object Storage : %s", e_wav_restore)

            # ── Vérification de cohérence segments vs script ──
            # CRITIQUE : si les segments locaux ne correspondent pas au script actuel
            # (ex: anciennes productions restaurées depuis Object Storage), le montage
            # produira un épisode incohérent ou échouera silencieusement.
            _seg_dir_check = config.SEGMENTS_DIR / episode_id
            if _seg_dir_check.exists() and script:
                _voix_ids_script = {
                    s["id"] for s in script["episode"]["segments"]
                    if s["personnage"] != "sfx"
                }
                _fichiers_locaux = {f.stem for f in _seg_dir_check.glob("*.mp3")}
                _voix_manquants = _voix_ids_script - _fichiers_locaux
                if _voix_manquants:
                    _log_direct(
                        f"ALERTE : {len(_voix_manquants)} segments voix manquants "
                        f"sur {len(_voix_ids_script)} attendus. "
                        f"Manquants: {sorted(_voix_manquants)[:10]}"
                    )
                    logger.warning(
                        "Segments voix manquants avant montage : %d/%d — %s",
                        len(_voix_manquants), len(_voix_ids_script),
                        sorted(_voix_manquants)[:10],
                    )
                    # Si plus de 50% des segments voix manquent, le montage est impossible
                    if len(_voix_manquants) > len(_voix_ids_script) * 0.5:
                        raise RuntimeError(
                            f"Montage impossible : {len(_voix_manquants)}/{len(_voix_ids_script)} "
                            f"segments voix manquants. Relancez la production audio."
                        )

            # ── Appliquer les instructions de montage (modification depuis le web) ──
            # Si le producteur a soumis des instructions via "Modifier le montage",
            # on utilise Claude pour adapter le script (pauses, tons, rythmes, SFX)
            # avant de relancer le montage avec les segments audio existants.
            _montage_instructions_path = config.SCRIPTS_DIR / f"{episode_id}_montage_instructions.txt"
            if _montage_instructions_path.exists():
                try:
                    _montage_instructions = _montage_instructions_path.read_text(
                        encoding="utf-8"
                    ).strip()
                    if _montage_instructions:
                        _log_direct(
                            f"Instructions de montage détectées : "
                            f"{_montage_instructions[:200]}"
                        )
                        console.print(
                            f"  [bold cyan]Instructions du producteur :[/bold cyan] "
                            f"{_montage_instructions[:200]}"
                        )
                        script = _appliquer_instructions_montage(
                            script, _montage_instructions, episode_id
                        )
                    _montage_instructions_path.unlink()  # Usage unique
                except Exception as e:
                    logger.warning(
                        "Erreur application instructions montage : %s", e
                    )

            monteur = Monteur()

            # Audit des musiques de fond avant montage
            try:
                audit_musique = Monteur.auditer_musiques_fond(script)
                stats_mus = audit_musique["stats"]
                console.print(
                    f"  Musiques de fond : {stats_mus['nb_ok']} prêtes, "
                    f"{stats_mus['nb_a_generer']} à générer "
                    f"({'dynamique' if stats_mus['dynamique'] else 'uniforme'})"
                )
                if audit_musique["alertes"]:
                    console.print(f"[yellow]  {len(audit_musique['alertes'])} alerte(s) musique :[/yellow]")
                    for a in audit_musique["alertes"][:5]:
                        console.print(f"    ! {a}")
                rapport.setdefault("etapes", {}).setdefault("montage", {})["audit_musique"] = {
                    "ok": audit_musique["ok"],
                    "nb_ambiances": stats_mus["nb_ambiances"],
                    "dynamique": stats_mus["dynamique"],
                }
                rapport.setdefault("alertes_post_generation", []).extend(audit_musique["alertes"])
            except Exception as e:
                logger.warning("Audit musiques de fond échoué : %s", e)

            # Vérifier que les segments audio existent avant de lancer le montage
            _seg_dir = config.SEGMENTS_DIR / episode_id
            _seg_count = len(list(_seg_dir.glob("*.mp3"))) if _seg_dir.exists() else 0
            _script_seg_count = len(script["episode"]["segments"])
            _log_direct(
                f"Lancement monteur.assembler() — "
                f"{_seg_count} fichiers MP3 en local, "
                f"{_script_seg_count} segments dans le script"
            )
            try:
                resultat_montage = monteur.assembler(script)
                _log_direct(
                    f"Montage terminé — "
                    f"durée={resultat_montage.get('duree_secondes', '?')}s, "
                    f"fichier={resultat_montage.get('chemin_hq', '?')}"
                )
            except Exception as e:
                # ── Montage échoué : sauvegarder l'erreur dans le rapport ──
                _log_direct(f"ERREUR MONTAGE : {type(e).__name__}: {e}")
                logger.error("Montage échoué pour %s : %s", episode_id, e, exc_info=True)
                rapport["etapes"]["montage"] = {
                    "status": "error",
                    "erreur": str(e),
                    "erreur_type": type(e).__name__,
                }
                # Sauvegarder le rapport partiel (même en cas d'erreur)
                chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
                rapport["erreur_montage"] = str(e)
                with fichier_lock(chemin_rapport):
                    with open(chemin_rapport, "w", encoding="utf-8") as f_out:
                        json.dump(rapport, f_out, ensure_ascii=False, indent=2, default=str)
                try:
                    import persistent_storage
                    persistent_storage.upload_rapport(episode_id, chemin_rapport)
                except Exception as e_os:
                    logger.warning("Object Storage indisponible pour rapport montage échec : %s", e_os)
                # Sauvegarder checkpoint pour reprise
                sauvegarder_checkpoint(episode_id, "montage", {
                    "episode_id": episode_id, "titre": titre, "resume": resume,
                    "saison": saison, "numero": numero, "morale": morale,
                    "type_episode": type_episode,
                    "dry_run": dry_run, "rapport": rapport,
                    "pubdate_offset_seconds": pubdate_offset_seconds,
                    "stop_after": stop_after,
                })
                raise  # Re-raise pour que le outer handler marque failed en DB

            duree_secondes = resultat_montage["duree_secondes"]
            taille_bytes = resultat_montage["taille_bytes"]
            chemin_hq = resultat_montage["chemin_hq"]

            console.print(f"  Episode assemble : {duree_secondes:.0f}s, {taille_bytes / 1024 / 1024:.1f} MB")
            rapport["etapes"]["montage"] = {
                "duree_secondes": duree_secondes,
                "taille_mb": round(taille_bytes / 1024 / 1024, 1),
                "chemin_hq": str(chemin_hq),
                "chemin_preview": str(resultat_montage["chemin_preview"]),
                "chapitres": resultat_montage.get("chapitres", []),
            }

            # Enregistrer les fichiers finaux en DB
            if _use_db():
                try:
                    FichierAudioRepo.enregistrer(
                        episode_id=episode_id,
                        type_fichier="episode_hq",
                        chemin=str(chemin_hq),
                        production_id=getattr(_production_local, 'production_id', None),
                        taille_bytes=taille_bytes,
                        duree_secondes=duree_secondes,
                    )
                    FichierAudioRepo.enregistrer(
                        episode_id=episode_id,
                        type_fichier="episode_preview",
                        chemin=str(resultat_montage["chemin_preview"]),
                        production_id=getattr(_production_local, 'production_id', None),
                        duree_secondes=duree_secondes,
                    )
                except Exception as e:
                    logger.warning("DB indisponible pour enregistrement montage : %s", e)

            # Upload audio + chapitres vers Object Storage (persistance inter-deploy)
            try:
                import persistent_storage
                _preview_raw = resultat_montage.get("chemin_preview")
                preview_path = Path(_preview_raw) if _preview_raw else None
                storage_keys = persistent_storage.upload_episode_audio(
                    episode_id, Path(chemin_hq), preview_path,
                )
                if storage_keys:
                    rapport["etapes"]["montage"]["object_storage"] = storage_keys
                # Upload chapitres
                chemin_chapitres = resultat_montage.get("chemin_chapitres")
                if chemin_chapitres:
                    chap_key = persistent_storage.upload_chapters(episode_id, Path(chemin_chapitres))
                    if chap_key:
                        rapport["etapes"]["montage"]["object_storage_chapters"] = chap_key
            except Exception as e:
                logger.warning("Object Storage indisponible pour audio/chapitres : %s", e)

            sauvegarder_checkpoint(episode_id, "metadonnees", {
                "episode_id": episode_id, "titre": titre, "resume": resume,
                "saison": saison, "numero": numero, "morale": morale,
                "type_episode": type_episode,
                "dry_run": dry_run, "rapport": rapport,
                "pubdate_offset_seconds": pubdate_offset_seconds,
                "stop_after": stop_after,
            })

    # ── Validation humaine : montage ─────────────────────────────────────────

    montage_deja_valide = rapport.get("etapes", {}).get("montage", {}).get("validation_humaine", False)
    if not auto and not dry_run and chemin_hq and resultat_montage and not montage_deja_valide:
        preview_chemin = (
            resultat_montage.get("chemin_preview")
            if isinstance(resultat_montage, dict)
            else None
        )
        if preview_chemin:
            demande_remontage = _validation_montage(
                chemin_hq,
                preview_chemin,
                duree_secondes,
                script=script,
                type_episode=type_episode,
                resultat_montage=resultat_montage if isinstance(resultat_montage, dict) else None,
                rapport=rapport,
            )
            rapport["etapes"]["montage"]["validation_humaine"] = True

            # Boucle de remontage (M5)
            while demande_remontage:
                console.print(f"\n{Typo.etape(5, 8, 'Remontage')}")
                monteur = Monteur()
                resultat_montage = monteur.assembler(script)

                duree_secondes = resultat_montage["duree_secondes"]
                taille_bytes = resultat_montage["taille_bytes"]
                chemin_hq = resultat_montage["chemin_hq"]

                console.print(
                    f"  Episode re-assemble : {duree_secondes:.0f}s, "
                    f"{taille_bytes / 1024 / 1024:.1f} MB"
                )
                rapport["etapes"]["montage"].update({
                    "duree_secondes": duree_secondes,
                    "taille_mb": round(taille_bytes / 1024 / 1024, 1),
                    "chemin_hq": str(chemin_hq),
                    "chemin_preview": str(resultat_montage["chemin_preview"]),
                    "chapitres": resultat_montage.get("chapitres", []),
                })

                preview_chemin = resultat_montage.get("chemin_preview")
                demande_remontage = _validation_montage(
                    chemin_hq,
                    preview_chemin,
                    duree_secondes,
                    script=script,
                    type_episode=type_episode,
                    resultat_montage=resultat_montage,
                    rapport=rapport,
                )

            # Upload audio remontée vers Object Storage
            try:
                import persistent_storage
                preview_remonté = resultat_montage.get("chemin_preview")
                preview_path_r = Path(preview_remonté) if preview_remonté else None
                storage_keys = persistent_storage.upload_episode_audio(
                    episode_id, Path(chemin_hq), preview_path_r,
                )
                if storage_keys:
                    rapport["etapes"]["montage"]["object_storage"] = storage_keys
            except Exception as e:
                logger.warning("Object Storage indisponible pour audio remontée : %s", e)

            # M9: Save checkpoint after remontage loop to preserve remontage work
            sauvegarder_checkpoint(episode_id, "metadonnees", {
                "episode_id": episode_id, "titre": titre, "resume": resume,
                "saison": saison, "numero": numero, "morale": morale,
                "type_episode": type_episode,
                "dry_run": dry_run, "rapport": rapport,
                "pubdate_offset_seconds": pubdate_offset_seconds,
                "stop_after": stop_after,
            })
        else:
            logger.warning(
                "Pas de fichier preview disponible — validation du montage impossible."
            )
            console.print(
                "[bold red]  Aucun fichier preview disponible — "
                "impossible de valider le montage sans écoute.[/bold red]\n"
                "[yellow]  La publication sera bloquée tant que le montage "
                "n'aura pas été écouté et validé.[/yellow]"
            )
            # M5: Allow forced validation when no preview exists
            console.print(
                "\n[bold yellow]  Vous pouvez forcer la validation du montage "
                "sans écoute (non recommandé).[/bold yellow]\n"
                "[dim]  Le fichier HQ existe mais aucun preview n'a été généré.[/dim]"
            )
            choix_force = Prompt.ask(
                "  Forcer la validation sans écoute ?",
                choices=["o", "n"],
                default="n",
            )
            if choix_force == "o":
                console.print(
                    f"  [{Palette.ATTENTION}]{Icons.ATTENTION_IC} Montage validé SANS écoute "
                    f"— vérifiez le fichier HQ manuellement : {chemin_hq}[/]"
                )
                rapport["etapes"]["montage"]["validation_humaine"] = True
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "montage",
                    "action": "validation_forcee_sans_preview",
                    "raison": "Aucun fichier preview disponible",
                })
                logger.info("Montage validé sans écoute (forcé par le producteur).")

    # ── Stop après montage (mode web : attendre validation avant publication) ─
    if stop_after == "montage":
        _log_direct(f"Stop après montage — chemin_hq={chemin_hq}")
        rapport["stop_after"] = "montage"
        rapport["status"] = "waiting_validation"
        console.print(
            f"\n[bold cyan]  Pipeline arrêté après le montage — "
            f"en attente de validation.[/bold cyan]"
        )
        chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
        with fichier_lock(chemin_rapport):
            with open(chemin_rapport, "w", encoding="utf-8") as f_out:
                json.dump(rapport, f_out, ensure_ascii=False, indent=2, default=str)
        # Upload rapport vers Object Storage (survit aux redéploiements)
        try:
            import persistent_storage
            persistent_storage.upload_rapport(episode_id, chemin_rapport)
        except Exception as e:
            logger.warning("Object Storage indisponible pour rapport (stop_after=montage) : %s", e)
        # Mettre à jour l'historique pour que la page de validation web soit à jour
        ajouter_historique(rapport, script)
        _pid = getattr(_production_local, 'production_id', None)
        if _use_db() and _pid:
            try:
                ProductionRepo.maj_etape(
                    _pid, etape="waiting_montage",
                    rapport=rapport,
                )
            except Exception as e:
                logger.warning("DB indisponible pour maj_etape waiting_montage : %s", e)
        return rapport

    _log_step_duration("Montage")

    # ── Étape 6 : Métadonnées ─────────────────────────────────────────────────

    if etape_idx <= 5:
        console.print(f"\n{Typo.etape(6, 8, 'Métadonnées')}")
        metadonnees = Metadonnees()

        if dry_run:
            meta = metadonnees.generer_dry_run(script)
        else:
            meta = metadonnees.generer(script, duree_secondes)

        chemin_meta = config.SCRIPTS_DIR / f"{episode_id}_meta.json"
        metadonnees.sauvegarder(meta, chemin_meta)
        console.print(f"  Titre : {meta['titre']}")
        console.print(f"  Description : {meta['description_courte']}")
        if meta.get("cover_art_prompt"):
            console.print(f"  Cover art prompt : {meta['cover_art_prompt']}")

        rapport["etapes"]["metadonnees"] = {
            "titre": meta["titre"],
            "chemin": str(chemin_meta),
            "cover_art_path": meta.get("cover_art_path", ""),
        }

        # Sauvegarder métadonnées en DB
        if _use_db():
            try:
                MetadonneesRepo.sauvegarder(
                    episode_id=episode_id,
                    meta=meta,
                    production_id=getattr(_production_local, 'production_id', None),
                )
                # Coût Claude pour métadonnées
                if not dry_run:
                    cout_claude_meta = (
                        2000 * config.COUTS["claude_input_par_token"]
                        + 4000 * config.COUTS["claude_output_par_token"]
                    )
                    CoutRepo.enregistrer(
                        episode_id=episode_id,
                        service="anthropic_claude",
                        cout_estime=cout_claude_meta,
                        detail={"operation": "metadonnees"},
                        production_id=getattr(_production_local, 'production_id', None),
                    )
            except Exception as e:
                logger.warning("DB indisponible pour métadonnées : %s", e)

        # Vérifier si un cover art custom existe déjà (fourni manuellement)
        cover_custom = None
        for ext in (".png", ".jpg", ".jpeg"):
            p = config.COVERS_DIR / f"{episode_id}_cover{ext}"
            if p.exists():
                cover_custom = p
                break

        if cover_custom:
            # Cover art custom fourni — pas de génération DALL-E
            meta["cover_art_path"] = str(cover_custom)
            metadonnees.sauvegarder(meta, chemin_meta)
            rapport["etapes"]["metadonnees"]["cover_art_path"] = str(cover_custom)
            rapport["etapes"]["metadonnees"]["cover_art_source"] = "custom"
            console.print(f"  Cover art custom détecté : {cover_custom}")

            # Upload cover art vers Object Storage
            try:
                import persistent_storage
                cover_key = persistent_storage.upload_cover(episode_id, cover_custom)
                if cover_key:
                    rapport["etapes"]["metadonnees"]["object_storage_cover"] = cover_key
            except Exception as e:
                logger.warning("Object Storage indisponible pour cover art : %s", e)

        elif meta.get("cover_art_prompt") and config.COVER_ART_CONFIG.get("enabled"):
            # Générer le cover art via DALL-E
            console.print("  Génération du cover art...")
            cover_agent = CoverArt()
            cover_path = cover_agent.generer(meta["cover_art_prompt"], episode_id)
            if cover_path:
                meta["cover_art_path"] = str(cover_path)
                metadonnees.sauvegarder(meta, chemin_meta)
                rapport["etapes"]["metadonnees"]["cover_art_path"] = str(cover_path)
                rapport["etapes"]["metadonnees"]["cover_art_source"] = "dalle3"
                console.print(f"  Cover art : {cover_path}")
                rapport["etapes"]["metadonnees"]["cover_art_cout"] = config.COUTS["openai_dalle3_par_image"]

                # Upload cover art vers Object Storage
                try:
                    import persistent_storage
                    cover_key = persistent_storage.upload_cover(episode_id, cover_path)
                    if cover_key:
                        rapport["etapes"]["metadonnees"]["object_storage_cover"] = cover_key
                except Exception as e:
                    logger.warning("Object Storage indisponible pour cover art : %s", e)

    # ── Directeur Podcast — validation métadonnées ────────────────────────────

    if not dry_run and etape_idx <= 5:
        try:
            directeur_meta = DirecteurPodcast()
            resultat_meta_dir = directeur_meta.valider_metadonnees(meta, script)
            note_meta = resultat_meta_dir.get("note", 0)
            verdict_meta = resultat_meta_dir.get("verdict", "?")

            couleur = {
                "feu_vert": Palette.SUCCES,
                "ajustements_mineurs": "yellow",
                "retravailler": "red",
            }.get(verdict_meta, "white")
            console.print(
                f"  Directeur (métadonnées) : [{couleur}]{verdict_meta.replace('_', ' ').upper()}[/] "
                f"(note {note_meta}/10)"
            )

            # Titre
            titre_avis = resultat_meta_dir.get("titre_avis", "")
            if titre_avis:
                console.print(f"  Titre : {Typo.dim(titre_avis)}")

            # Suggestions de titres alternatifs
            suggestions = resultat_meta_dir.get("suggestions", {})
            titres_alt = suggestions.get("titres_alternatifs", [])
            if titres_alt:
                console.print("[yellow]  Titres alternatifs proposés :[/yellow]")
                for t in titres_alt[:3]:
                    console.print(f"    - {t}")

            # Description
            desc_avis = resultat_meta_dir.get("description_avis", "")
            if desc_avis:
                console.print(f"  Description : {Typo.dim(desc_avis)}")

            # Personas
            personas_meta = resultat_meta_dir.get("personas", {})
            for pk, pv in personas_meta.items():
                nom = pk.replace("_", " ").title()
                clic = "cliquerait" if pv.get("cliquerait", True) else "NE cliquerait PAS"
                comm = pv.get("commentaire", "")
                console.print(f"  {Typo.dim(f'{nom} : {clic} — {comm}')}")

            rapport["etapes"]["directeur_metadonnees"] = {
                "note": note_meta,
                "verdict": verdict_meta,
                "titres_alternatifs": titres_alt,
            }

            # Si "retravailler" → régénérer les métadonnées avec les suggestions du directeur
            if verdict_meta == "retravailler":
                console.print(
                    f"\n[bold red]  {Icons.ATTENTION_IC} Le directeur demande de retravailler "
                    f"les métadonnées. Régénération avec ses suggestions...[/bold red]"
                )
                desc_amelioree = suggestions.get("description_amelioree", "")
                instructions_dir = []
                if titres_alt:
                    instructions_dir.append(f"Utiliser un titre parmi : {', '.join(titres_alt[:3])}")
                if desc_amelioree:
                    instructions_dir.append(f"Description améliorée : {desc_amelioree}")
                mots_manquants = suggestions.get("mots_cles_manquants", [])
                if mots_manquants:
                    instructions_dir.append(f"Ajouter les mots-clés : {', '.join(mots_manquants)}")
                if titre_avis:
                    instructions_dir.append(f"Avis titre : {titre_avis}")
                if desc_avis:
                    instructions_dir.append(f"Avis description : {desc_avis}")

                try:
                    # Injecter les instructions du directeur dans le script pour le LLM
                    script_enrichi = dict(script)
                    if instructions_dir:
                        script_enrichi["_instructions_metadonnees"] = "\n".join(instructions_dir)
                    meta = metadonnees.generer(script_enrichi, duree_secondes)
                    # Appliquer le titre alternatif suggéré par le directeur si disponible
                    if titres_alt:
                        meta["titre"] = titres_alt[0]
                        console.print(f"  Titre remplacé par suggestion directeur : {titres_alt[0]}")
                    if desc_amelioree:
                        meta["description_courte"] = desc_amelioree
                        console.print(f"  Description remplacée par suggestion directeur")
                    metadonnees.sauvegarder(meta, chemin_meta)
                    console.print(f"  Nouveau titre : {meta['titre']}")
                    console.print(f"  Nouvelle description : {meta['description_courte']}")
                    rapport["etapes"]["metadonnees"]["titre"] = meta["titre"]
                    rapport["etapes"]["metadonnees"]["regenere_par_directeur"] = True
                except Exception as regen_e:
                    logger.warning("Régénération métadonnées échouée : %s", regen_e)
                    console.print(f"[yellow]  Régénération échouée : {regen_e}[/yellow]")

        except Exception as e:
            logger.warning("Directeur Podcast (métadonnées) indisponible : %s", e)
            console.print(f"[yellow]  Validation directeur métadonnées non disponible : {e}[/yellow]")

    # ── Validation humaine : metadonnees ──────────────────────────────────────

    if not auto and not dry_run and etape_idx <= 5:
        meta = _validation_metadonnees(
            meta, chemin_meta,
            script=script, duree_secondes=duree_secondes,
            rapport=rapport,
        )
        # Resauvegarder si modifie
        metadonnees_agent = Metadonnees()
        metadonnees_agent.sauvegarder(meta, chemin_meta)
        rapport["etapes"]["metadonnees"]["validation_humaine"] = True

    # Upload métadonnées vers Object Storage (après validation éventuelle)
    if not dry_run and etape_idx <= 5:
        try:
            import persistent_storage
            meta_key = persistent_storage.upload_metadonnees(episode_id, chemin_meta)
            if meta_key:
                rapport["etapes"]["metadonnees"]["object_storage_meta"] = meta_key
        except Exception as e:
            logger.warning("Object Storage indisponible pour métadonnées : %s", e)

    _log_step_duration("Métadonnées")

    # ── Étape 7 : Publication ─────────────────────────────────────────────────

    if etape_idx <= 6:
        if dry_run or no_publish:
            raison = "dry-run" if dry_run else "no-publish"
            console.print(f"\n{Typo.etape(7, 8, 'Publication')}  {Typo.attention(f'SAUTÉ — {raison}')}")
            rapport["etapes"]["publication"] = {"status": f"skipped ({raison})"}
        else:
            # ── Directeur Podcast — Go/No-Go final ────────────────────────
            publication_bloquee_directeur = False
            try:
                directeur_pub = DirecteurPodcast()
                resultat_go = directeur_pub.go_no_go_publication(rapport, meta)
                verdict_go = resultat_go.get("verdict", "?")
                note_go = resultat_go.get("note_globale", 0)

                couleur_go = {
                    "go": Palette.SUCCES,
                    "conditionnel": "yellow",
                    "no_go": "red",
                }.get(verdict_go, "white")
                console.print(
                    f"  Directeur — verdict final : [{couleur_go}]{verdict_go.upper()}[/] "
                    f"(note {note_go}/10)"
                )

                synthese_go = resultat_go.get("synthese", "")
                if synthese_go:
                    console.print(f"  {Typo.dim(synthese_go)}")

                # Points forts
                for pf in resultat_go.get("points_forts", []):
                    console.print(f"  [{Palette.SUCCES}]+ {pf}[/]")

                # Risques
                for r in resultat_go.get("risques", []):
                    console.print(f"  [yellow]! {r}[/yellow]")

                # Conditions (si conditionnel)
                for c in resultat_go.get("conditions", []):
                    console.print(f"  [bold yellow]? {c}[/bold yellow]")

                # Personas
                personas_go = resultat_go.get("personas", {})
                for pk, pv in personas_go.items():
                    nom = pk.replace("_", " ").title()
                    pret = "OK" if pv.get("pret_a_publier", True) else "NON"
                    comm_go = pv.get("commentaire", "")
                    console.print(f"  {Typo.dim(f'{nom} ({pret}) : {comm_go}')}")

                rapport["etapes"]["directeur_go_no_go"] = {
                    "verdict": verdict_go,
                    "note_globale": note_go,
                    "risques": resultat_go.get("risques", []),
                }

                # Bloquer si no_go — la publication est interdite
                if verdict_go == "no_go":
                    console.print(
                        f"\n[bold red]  {Icons.ATTENTION_IC} Le directeur podcast BLOQUE "
                        f"la publication. Raisons :[/bold red]"
                    )
                    for r in resultat_go.get("risques", []):
                        console.print(f"  [red]  • {r}[/red]")
                    console.print(
                        "[yellow]  L'audio et les métadonnées sont conservés. "
                        "Corrigez les problèmes et relancez.[/yellow]"
                    )
                    rapport["etapes"]["publication"] = {
                        "status": "blocked (directeur no_go)",
                        "risques": resultat_go.get("risques", []),
                    }
                    publication_bloquee_directeur = True

            except Exception as e:
                logger.warning("Directeur Podcast (go/no-go) indisponible : %s", e)
                console.print(f"[yellow]  Go/No-Go directeur non disponible : {e}[/yellow]")

            # Confirmation avant publication (T4)
            # Si le directeur a bloqué, pas de publication possible
            publier = False
            if publication_bloquee_directeur:
                console.print(f"\n{Typo.etape(7, 8, 'Publication')}  [bold red]BLOQUÉ — directeur no_go[/bold red]")
            elif not auto:
                publier = _validation_publication(meta, episode_id, rapport=rapport)
            elif rapport.get("etapes", {}).get("publication", {}).get("validation_humaine"):
                # Web validation already confirmed — proceed with publication
                publier = True
                logger.info("Publication auto-validée (validation_humaine=True dans rapport)")

            if publier:
                # Garde-fou ultime : jamais de publication sans relecture ET écoute
                script_valide = rapport.get("etapes", {}).get("script", {}).get("validation_humaine", False)
                montage_valide = rapport.get("etapes", {}).get("montage", {}).get("validation_humaine", False)
                if not script_valide or not montage_valide:
                    manquants = []
                    if not script_valide:
                        manquants.append("relecture du script")
                    if not montage_valide:
                        manquants.append("écoute du montage")
                    console.print(
                        f"\n{Typo.etape(7, 8, 'Publication')}  "
                        f"[bold red]BLOQUÉ — prérequis : {', '.join(manquants)}[/bold red]"
                    )
                    rapport["etapes"]["publication"] = {
                        "status": "blocked (prerequis manquants)",
                        "prerequis_manquants": manquants,
                    }
                elif not chemin_hq or not Path(str(chemin_hq)).exists():
                    console.print(
                        "[bold red]  BLOQUÉ — fichier audio HQ introuvable. "
                        "Relancez le montage ou reprenez depuis un checkpoint.[/bold red]"
                    )
                    rapport["etapes"]["publication"] = {
                        "status": "blocked (audio HQ manquant)",
                    }
                else:
                    console.print(f"\n{Typo.etape(7, 8, 'Publication')}")
                    publisher = Publisher()
                    rapport_pub = publisher.publier(
                        meta, chemin_hq, taille_bytes,
                        pubdate_offset_seconds=pubdate_offset_seconds,
                    )
                    console.print(f"  URL audio : {rapport_pub['url_audio']}")
                    if rapport_pub.get("transcript_url"):
                        console.print(f"  Transcript : {rapport_pub['transcript_url']}")
                    rapport_pub["validation_humaine"] = True
                    rapport["etapes"]["publication"] = rapport_pub

                    # Enregistrer publication en DB
                    if _use_db():
                        try:
                            PublicationRepo.enregistrer(
                                episode_id=episode_id,
                                rapport_pub=rapport_pub,
                                production_id=getattr(_production_local, 'production_id', None),
                            )
                            EpisodeRepo.maj_status(episode_id, "published")
                        except Exception as e:
                            logger.warning("DB indisponible pour publication : %s", e)
            else:
                raison_skip = "mode auto" if auto else "choix utilisateur"
                console.print(f"\n{Typo.etape(7, 8, 'Publication')}  {Typo.attention(f'SAUTÉ — {raison_skip}')}")
                rapport["etapes"]["publication"] = {"status": f"skipped ({raison_skip})"}

    _log_step_duration("Publication")

    # ── Étape 8 : Rapport final ───────────────────────────────────────────────

    console.print(f"\n{Typo.etape(8, 8, 'Rapport final')}")
    rapport["fin"] = datetime.now().isoformat()
    rapport["status"] = "completed"

    # Calculer les métriques de coût
    rapport["couts"] = _calculer_couts(rapport)

    # Sauvegarder le rapport
    chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
    with fichier_lock(chemin_rapport):
        with open(chemin_rapport, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)

    # Upload rapport vers Object Storage (persistance inter-deploy)
    try:
        import persistent_storage
        persistent_storage.upload_rapport(episode_id, chemin_rapport)
    except Exception as e:
        logger.warning("Object Storage indisponible pour rapport : %s", e)

    # Ajouter à l'historique
    ajouter_historique(rapport, script)

    # ── Arc state final : sauvegarder l'état narratif pour l'épisode suivant ──
    # Extraire arc_state_final du script et le sauvegarder pour injection N→N+1
    arc_state = {
        "episode_id": episode_id,
        "moments_cles": script["episode"].get("moments_cles", []),
        "questions_ouvertes": script["episode"].get("questions_ouvertes", []),
        "evolutions_personnages": script["episode"].get("evolutions_personnages", ""),
        "ambiance": script["episode"].get("ambiance", ""),
        "fil_rouge": script["episode"].get("elements_fil_rouge", ""),
    }
    chemin_arc = config.SCRIPTS_DIR / f"{episode_id}_arc_state.json"
    with open(chemin_arc, "w", encoding="utf-8") as f:
        json.dump(arc_state, f, ensure_ascii=False, indent=2)
    logger.info("Arc state sauvegardé : %s", chemin_arc)

    # ── Season Archive : générer après le dernier épisode de la saison ──
    if contexte_saison and episode_plan:
        episodes_saison = contexte_saison.get("saison", {}).get("episodes", [])
        dernier_ep = max((ep.get("numero", 0) for ep in episodes_saison), default=0)
        if numero == dernier_ep:
            try:
                historique_saison = [
                    h for h in charger_historique()
                    if h.get("episode_id", "").startswith(f"S{saison:02d}")
                ]
                archive = Planificateur.generer_archive_saison(
                    contexte_saison, historique_saison
                )
                chemin_archive = config.ARCHIVES_DIR / f"archive_saison_{saison:02d}.json"
                with open(chemin_archive, "w", encoding="utf-8") as f:
                    json.dump(archive, f, ensure_ascii=False, indent=2)
                console.print(
                    f"  [{Palette.SUCCES}]Archive de saison {saison} générée : {chemin_archive}[/]"
                )
                logger.info("Archive de saison %d sauvegardée : %s", saison, chemin_archive)
            except Exception as e:
                logger.warning("Erreur lors de la génération de l'archive de saison : %s", e)

    # Archiver le checkpoint (JAMAIS supprimer — conservation des données)
    archiver_checkpoint(episode_id)

    # Finaliser la production en DB
    _pid = getattr(_production_local, 'production_id', None)
    if _use_db() and _pid:
        try:
            ProductionRepo.terminer(
                _pid,
                rapport=rapport,
                couts=rapport.get("couts", {}),
            )
            pub_status = rapport.get("etapes", {}).get("publication", {}).get("status", "")
            est_publie = "url_audio" in rapport.get("etapes", {}).get("publication", {})
            db_status = "published" if est_publie else ("dry_run" if dry_run else "produced")
            EpisodeRepo.maj_status(episode_id, db_status)
        except Exception as e:
            logger.warning("DB indisponible pour finalisation production : %s", e)

    # Afficher le résumé et les coûts
    couts = rapport["couts"]
    cout_total_str = f"${couts['total_estime']:.3f}" if not dry_run else "N/A (dry-run)"
    console.print(panel_rapport_final(
        episode_id=episode_id,
        titre=titre,
        score=score,
        morale=script['episode'].get('morale', 'N/A'),
        cout=cout_total_str,
        chemin_rapport=str(chemin_rapport),
        dry_run=dry_run,
    ))

    total_s = time.perf_counter() - _t_pipeline_start
    logger.info("⏱ Pipeline complet : %.1fs (%.1f min)", total_s, total_s / 60)
    console.print(f"  Durée totale : {total_s:.0f}s ({total_s/60:.1f} min)")

    return rapport


# ── CLI Click ─────────────────────────────────────────────────────────────────


def _healthcheck() -> None:
    """Affiche l'état des dépendances au démarrage."""
    problemes = []

    # Vérifier les clés API
    if not config.ANTHROPIC_API_KEY:
        problemes.append("ANTHROPIC_API_KEY manquante")
    if not config.ELEVENLABS_API_KEY:
        problemes.append("ELEVENLABS_API_KEY manquante (production audio impossible)")

    # Vérifier ffmpeg (nécessaire pour le montage)
    if not config.verifier_ffmpeg():
        problemes.append("ffmpeg non installé (montage audio impossible)")

    # Vérifier la bible des personnages
    if not config.PERSONNAGES_JSON_PATH.exists():
        problemes.append("personnages.json introuvable")

    if problemes:
        console.print(f"[{Palette.ATTENTION}]  {Icons.ATTENTION_IC} Healthcheck :[/]")
        for p in problemes:
            console.print(f"[{Palette.ATTENTION}]    {Icons.FLECHE} {p}[/]")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Les Histoires de Papy Babou — Systeme de production automatisee."""
    configurer_logging()
    initialiser_db()
    _healthcheck()
    if ctx.invoked_subcommand is None:
        ctx.invoke(interactif)


@cli.command()
@click.option("--episode", "-e", required=True, help="Titre de l'episode")
@click.option("--saison", "-s", type=click.IntRange(min=1), required=True, help="Numero de saison (>= 1)")
@click.option("--numero", "-n", type=click.IntRange(min=1), required=True, help="Numero d'episode (>= 1)")
@click.option("--resume", "-r", required=True, help="Resume de l'histoire biblique")
@click.option("--morale", "-m", default="", help="Lecon de vie a transmettre")
@click.option("--type-episode", "-t", type=click.Choice(["standard", "ouverture", "mi-saison", "final", "bonus"]), default="standard", help="Type d'episode (structure narrative)")
@click.option("--dry-run", is_flag=True, help="Tester sans audio ni publication")
@click.option("--auto", is_flag=True, help="Mode automatique sans validation humaine")
@click.option("--no-publish", is_flag=True, help="Sauter l'etape de publication (upload + RSS)")
@click.option("--stop-after", type=click.Choice(["script", "audio", "sfx", "montage", ""]), default="", help="Arreter le pipeline apres l'etape donnee (pour validation web)")
def produire(episode: str, saison: int, numero: int, resume: str, morale: str, type_episode: str, dry_run: bool, auto: bool, no_publish: bool, stop_after: str):
    """Produit un episode complet du podcast."""
    try:
        pipeline(
            titre=episode,
            resume=resume,
            saison=saison,
            numero=numero,
            morale=morale,
            dry_run=dry_run,
            auto=auto,
            type_episode=type_episode,
            no_publish=no_publish,
            stop_after=stop_after,
        )
    except ProductionAbandonnee as e:
        console.print(f"\n[bold yellow]Production arrêtée : {e}[/bold yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur dans le pipeline de production")
        sys.exit(1)


@cli.command()
def interactif():
    """Mode interactif — saisie guidee des parametres avec validation humaine."""
    banner(console, "Vous serez invité à valider chaque étape avant publication.")

    # ── Détecter les saisons existantes et proposer le choix ─────────
    saisons_existantes = config.liste_saisons()

    if saisons_existantes:
        console.print(panel_info(
            f"[{Palette.ARDOISE}]Saisons planifiées :[/] "
            + ", ".join(f"[bold]S{s:02d}[/bold]" for s in saisons_existantes)
            + "\n\n"
            f"[bold {Palette.BLEU_CIEL}]s[/] — Produire un épisode d'une saison existante\n"
            f"[bold {Palette.OCRE}]e[/] — Produire un épisode unique (hors saison)",
            titre=f"{Icons.PAPY} Que souhaitez-vous produire ?",
        ))
        choix_mode = console.input(
            f"  [{Palette.MIEL}]Votre choix (s/e) :[/] "
        ).strip().lower()
    else:
        choix_mode = "e"

    if choix_mode in ("s", "saison"):
        _interactif_saison(saisons_existantes)
    else:
        _interactif_episode_unique()


def _interactif_saison(saisons_existantes: list[int]):
    """Mode interactif — production d'un épisode depuis un plan de saison."""
    # Choisir la saison
    if len(saisons_existantes) == 1:
        saison_num = saisons_existantes[0]
        console.print(f"  [{Palette.SUCCES}]Saison {saison_num} sélectionnée automatiquement.[/]")
    else:
        while True:
            try:
                saison_num = int(console.input(
                    f"  [{Palette.MIEL}]Numéro de saison ({', '.join(str(s) for s in saisons_existantes)}) :[/] "
                ).strip())
                if saison_num in saisons_existantes:
                    break
                console.print(f"[red]  Saison {saison_num} non trouvée. Réessayez.[/red]")
            except ValueError:
                console.print("[red]  Numéro invalide. Réessayez.[/red]")

    plan = config.charger_saison(saison_num)
    if not plan:
        console.print(f"[red]Plan de saison {saison_num} introuvable.[/red]")
        return

    if "saison" not in plan or "episodes" not in plan.get("saison", {}):
        console.print("[red]Plan de saison invalide : clés 'saison' ou 'episodes' manquantes.[/red]")
        sys.exit(1)

    saison_data = plan["saison"]
    episodes_plan = saison_data["episodes"]

    # Détecter les épisodes déjà produits (en vérifiant que le plan n'a pas changé)
    deja_produits = _episodes_deja_produits(saison_num, episodes_plan)

    # Afficher les épisodes disponibles
    console.print(f"\n  [{Palette.BLEU_CIEL}]Saison {saison_num} — {saison_data.get('theme', '')}[/]")
    episodes_restants = []
    for ep in episodes_plan:
        ep_id = f"S{saison_num:02d}E{ep['numero']:02d}"
        deja = ep_id in deja_produits
        status_icon = f"[{Palette.SUCCES}]{Icons.OK}[/]" if deja else f"[{Palette.ARDOISE}]{Icons.A_FAIRE}[/]"
        type_str = f" [{ep.get('type', 'standard')}]" if ep.get('type', 'standard') != 'standard' else ''
        deja_str = f" [{Palette.ARDOISE}](déjà produit)[/]" if deja else ""
        console.print(
            f"  {status_icon} [bold]{ep_id}[/bold] — {ep['titre']}{type_str}{deja_str}"
        )
        if not deja:
            episodes_restants.append(ep)

    if not episodes_restants:
        console.print(f"\n[{Palette.SUCCES}]Tous les épisodes de cette saison sont déjà produits.[/]")
        return

    console.print(
        f"\n  [{Palette.ARDOISE}]{len(episodes_restants)} épisode(s) restant(s) à produire.[/]"
    )
    console.print(panel_validation([
        ("t", "Produire tous les épisodes restants"),
        ("n", "Choisir un épisode spécifique"),
    ], titre="Production de saison"))

    choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

    dry_run_str = console.input(f"  [{Palette.MIEL}]Mode dry-run ? (o/n) :[/] ").strip().lower()
    dry_run = dry_run_str in ("o", "oui", "y", "yes")

    if choix in ("n", "numero"):
        # Produire un seul épisode de la saison
        try:
            num_ep = int(console.input(
                f"  [{Palette.MIEL}]Numéro d'épisode :[/] "
            ).strip())
        except ValueError:
            console.print("[red]Numéro invalide.[/red]")
            sys.exit(1)

        ep = next((e for e in episodes_restants if e["numero"] == num_ep), None)
        if not ep:
            console.print(f"[red]Épisode {num_ep} introuvable ou déjà produit.[/red]")
            sys.exit(1)

        console.print()
        try:
            pipeline(
                titre=ep["titre"],
                resume=ep.get("resume", ep.get("histoire_biblique", "")),
                saison=saison_num,
                numero=ep["numero"],
                morale=ep.get("morale", ""),
                dry_run=dry_run,
                auto=False,
                contexte_saison=plan,
                type_episode=ep.get("type", "standard"),
                pubdate_offset_seconds=ep["numero"] * 3600,
                episode_courant=ep["numero"],
                total_episodes=len(episodes_plan),
                saison_theme=saison_data.get("theme", ""),
            )
        except ProductionAbandonnee as e:
            console.print(f"\n[bold yellow]Production arrêtée : {e}[/bold yellow]")
        except Exception as e:
            console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
            logger.exception("Erreur dans le pipeline de production")
            sys.exit(1)
    else:
        # Produire tous les épisodes restants
        nb_restants = len(episodes_restants)

        # Confirmation avant de lancer la production en série
        console.print(
            f"\n  [{Palette.BLEU_CIEL}]Vous allez produire {nb_restants} épisode(s) "
            f"en mode {'DRY RUN' if dry_run else 'PRODUCTION'}.[/]"
        )
        console.print(panel_validation([
            ("v", "Valider — lancer la production"),
            ("a", "Abandonner"),
        ], titre="Confirmation — Production en série"))
        while True:
            choix_conf = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()
            if choix_conf in ("v", "valider"):
                break
            elif choix_conf in ("a", "abandonner"):
                console.print(f"[{Palette.ATTENTION}]Production annulée.[/]")
                return
            else:
                console.print("[red]  Choix non reconnu. Tapez v ou a.[/red]")

        console.print(
            f"\n  [{Palette.BLEU_CIEL}]Lancement de la production de "
            f"{nb_restants} épisode(s)...[/]"
        )

        resultats = []
        for i, ep in enumerate(episodes_restants, 1):
            ep_id = f"S{saison_num:02d}E{ep['numero']:02d}"
            console.print()
            console.print(panel_separateur_episode(
                episode_courant=i,
                total_episodes=nb_restants,
                episode_id=ep_id,
                titre=ep["titre"],
                type_episode=ep.get("type", "standard"),
            ))

            try:
                rapport = pipeline(
                    titre=ep["titre"],
                    resume=ep.get("resume", ep.get("histoire_biblique", "")),
                    saison=saison_num,
                    numero=ep["numero"],
                    morale=ep.get("morale", ""),
                    dry_run=dry_run,
                    auto=False,
                    contexte_saison=plan,
                    type_episode=ep.get("type", "standard"),
                    pubdate_offset_seconds=ep["numero"] * 3600,
                    episode_courant=ep["numero"],
                    total_episodes=len(episodes_plan),
                    saison_theme=saison_data.get("theme", ""),
                )
                resultats.append({"status": "ok", "episode": ep["titre"]})
            except ProductionAbandonnee as e:
                console.print(f"\n[bold yellow]Production abandonnée : {e}[/bold yellow]")
                resultats.append({"status": "skipped", "episode": ep["titre"], "raison": str(e)})
            except Exception as e:
                logger.exception("Erreur sur l'episode %s", ep.get("titre", "?"))
                resultats.append({"status": "error", "episode": ep["titre"], "erreur": str(e)})
                # Proposer de continuer ou d'arrêter la production
                if nb_restants - i > 0:
                    choix = console.input(
                        f"[bold yellow]Épisode échoué. (c) Continuer avec les suivants / (a) Arrêter la saison ? [/] "
                    ).strip().lower()
                    if choix == "a":
                        console.print("[bold red]Production de saison interrompue.[/bold red]")
                        break

        # Rapport de série
        ok = sum(1 for r in resultats if r["status"] == "ok")
        console.print(f"\n[{Palette.SUCCES}]Production terminée : {ok}/{nb_restants} réussis.[/]")


def _interactif_episode_unique():
    """Mode interactif — production d'un épisode unique hors saison."""
    console.print(panel_info(
        Typo.dim("Saisissez les paramètres de votre épisode unique."),
        titre=f"{Icons.EPISODE} Épisode unique",
    ))

    titre = console.input(f"  [{Palette.MIEL}]Titre de l'épisode :[/] ")
    try:
        saison = int(console.input(f"  [{Palette.MIEL}]Numéro de saison :[/] "))
        numero = int(console.input(f"  [{Palette.MIEL}]Numéro d'épisode :[/] "))
    except ValueError:
        console.print("[red]Les numéros de saison et d'épisode doivent être des entiers.[/red]")
        sys.exit(1)
    resume = console.input(f"  [{Palette.MIEL}]Résumé de l'histoire biblique :[/] ")
    morale = console.input(f"  [{Palette.MIEL}]Leçon de vie / morale (optionnel) :[/] ")

    type_episode_str = console.input(
        f"  [{Palette.MIEL}]Type d'épisode (standard/ouverture/mi-saison/final/bonus) :[/] "
    ).strip().lower() or "standard"
    types_valides = {"ouverture", "standard", "mi-saison", "final", "bonus"}
    if type_episode_str not in types_valides:
        console.print(f"[yellow]  Type '{type_episode_str}' non reconnu — 'standard' utilisé.[/yellow]")
        type_episode_str = "standard"

    dry_run_str = console.input(f"  [{Palette.MIEL}]Mode dry-run ? (o/n) :[/] ").strip().lower()
    dry_run = dry_run_str in ("o", "oui", "y", "yes")

    console.print()
    try:
        pipeline(
            titre=titre,
            resume=resume,
            saison=saison,
            numero=numero,
            morale=morale,
            dry_run=dry_run,
            auto=False,
            type_episode=type_episode_str,
        )
    except ProductionAbandonnee as e:
        console.print(f"\n[bold yellow]Production arrêtée : {e}[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur dans le pipeline de production")
        sys.exit(1)


@cli.command()
@click.option("--fichier", "-f", required=True, type=click.Path(exists=True),
              help="Fichier JSON de planning (liste d'episodes)")
@click.option("--dry-run", is_flag=True, help="Tester sans audio ni publication")
@click.option("--auto", is_flag=True, help="Mode automatique sans validation humaine")
@click.option("--no-publish", is_flag=True, help="Sauter l'etape de publication (upload + RSS)")
def batch(fichier: str, dry_run: bool, auto: bool, no_publish: bool):
    """Mode batch — produit plusieurs episodes depuis un fichier de planning.

    Le fichier JSON doit contenir une liste d'episodes :
    [
      {"titre": "...", "resume": "...", "saison": 1, "numero": 1, "morale": "..."},
      ...
    ]
    """
    with open(fichier, "r", encoding="utf-8") as f:
        planning = json.load(f)

    if not isinstance(planning, list):
        console.print("[red]Le fichier doit contenir une liste d'épisodes.[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[bold]Production en serie — {len(planning)} episodes[/bold]\n"
        f"Mode : {'DRY RUN' if dry_run else 'PRODUCTION'}\n"
        f"Validation humaine : {'Non (auto)' if auto else 'Oui'}",
        title="Batch Mode",
        border_style="blue",
    ))

    resultats = []
    nb_planning = len(planning)
    for i, ep in enumerate(planning, 1):
        if "titre" not in ep:
            console.print(f"[red]Episode {i} : clé 'titre' manquante dans le JSON. Ignoré.[/red]")
            resultats.append({"status": "error", "episode": f"(episode {i})", "erreur": "titre manquant"})
            continue
        ep_saison = ep.get("saison", 1)
        ep_numero = ep.get("numero", i)
        ep_id = f"S{ep_saison:02d}E{ep_numero:02d}"
        console.print()
        console.print(panel_separateur_episode(
            episode_courant=i,
            total_episodes=nb_planning,
            episode_id=ep_id,
            titre=ep.get("titre", "?"),
        ))

        try:
            rapport = pipeline(
                titre=ep["titre"],
                resume=ep.get("resume", ""),
                saison=ep_saison,
                numero=ep_numero,
                morale=ep.get("morale", ""),
                dry_run=dry_run,
                auto=auto,
                no_publish=no_publish,
                type_episode=ep.get("type", ep.get("type_episode", "standard")),
                pubdate_offset_seconds=ep_numero * 3600,
                episode_courant=i,
                total_episodes=nb_planning,
            )
            resultats.append({"status": "ok", "episode": ep["titre"], "rapport": rapport})
        except ProductionAbandonnee as e:
            console.print(f"\n[bold yellow]Production abandonnée : {e}[/bold yellow]")
            resultats.append({"status": "skipped", "episode": ep["titre"], "raison": str(e)})
        except Exception as e:
            logger.exception("Erreur sur l'episode %s", ep.get("titre", "?"))
            resultats.append({"status": "error", "episode": ep["titre"], "erreur": str(e)})
            if not auto:
                choix_cont = console.input(
                    f"  [{Palette.ATTENTION}]Épisode en erreur. "
                    f"(c)ontinuer / (a)rrêter ? [/] "
                ).strip().lower()
                if choix_cont == "a":
                    console.print(f"  [{Palette.ATTENTION}]Production batch arrêtée par le producteur.[/]")
                    break

    # Rapport batch
    console.print(f"\n[bold]{'='*60}[/bold]")
    console.print(f"[bold {Palette.SUCCES}]Rapport batch[/]")
    ok = sum(1 for r in resultats if r["status"] == "ok")
    skipped = sum(1 for r in resultats if r["status"] == "skipped")
    erreurs = sum(1 for r in resultats if r["status"] == "error")
    console.print(f"  Réussis    : {ok}/{len(planning)}")
    if skipped:
        console.print(f"  Abandonnés : {skipped}/{len(planning)}")
    console.print(f"  Échecs     : {erreurs}/{len(planning)}")

    for r in resultats:
        if r["status"] == "ok":
            status = f"[{Palette.SUCCES}]OK[/]"
        elif r["status"] == "skipped":
            status = "[yellow]ABANDONNÉ[/yellow]"
        else:
            status = "[red]ERREUR[/red]"
        console.print(f"  {status} — {r['episode']}")
        if r["status"] == "error":
            console.print(f"    [red]{r['erreur']}[/red]")

    # Sauvegarder le rapport batch
    chemin_batch = config.LOGS_DIR / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(chemin_batch, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2, default=str)
    console.print(f"\n  Rapport batch : {chemin_batch}")

    if erreurs > 0:
        sys.exit(1)


def _mark_failed_in_db(episode_id: str | None) -> None:
    """Marque la production la plus récente comme 'failed' en DB.

    Utilisé par reprendre() pour empêcher _auto_resume_interrupted de relancer
    en boucle une production qui crash systématiquement.
    """
    if not episode_id or not _use_db():
        return
    try:
        from db_models import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """UPDATE productions SET status = 'failed', updated_at = NOW()
                   WHERE id = (
                       SELECT id FROM productions
                       WHERE episode_id = %s
                         AND status NOT IN ('completed', 'failed')
                       ORDER BY started_at DESC LIMIT 1
                   )""",
                (episode_id,),
            )
        logger.info("Production %s marquée 'failed' après crash dans reprendre()", episode_id)
    except Exception as db_err:
        logger.warning("Impossible de marquer la production failed : %s", db_err)


@cli.command()
@click.option("--checkpoint", "-c", required=True, type=click.Path(exists=True),
              help="Chemin du fichier checkpoint")
@click.option("--auto", is_flag=True, help="Mode automatique sans validation humaine")
@click.option("--no-publish", is_flag=True, help="Sauter l'etape de publication (upload + RSS)")
@click.option("--stop-after", type=click.Choice(["script", "audio", "sfx", "montage", ""]), default="", help="Arreter apres l'etape donnee")
def reprendre(checkpoint: str, auto: bool, no_publish: bool, stop_after: str):
    """Reprend une production depuis un checkpoint."""
    # Log explicite sur stderr pour garantir la visibilité dans les deployment logs
    # (Rich Console peut ne pas flusher quand stdout est un PIPE subprocess)
    def _log_direct(msg: str) -> None:
        sys.stderr.write(f"[reprendre] {msg}\n")
        sys.stderr.flush()

    _log_direct(f"Démarrage reprendre — checkpoint={checkpoint}, stop_after={stop_after}")
    episode_id = None  # Initialisé tôt pour le marquage failed dans le except
    try:
        cp = charger_checkpoint(Path(checkpoint))
        data = cp["data"]
        etape = cp["etape"]
        episode_id = data.get("episode_id")
        _log_direct(f"Checkpoint chargé — episode={episode_id}, etape={etape}")

        # Utiliser le stop_after du checkpoint si pas spécifié en CLI
        # (reprise automatique après interruption SIGTERM)
        effective_stop_after = stop_after or data.get("stop_after", "")

        console.print(Panel(
            f"[bold]Reprise depuis le checkpoint[/bold]\n"
            f"Episode : {data.get('episode_id', '?')} — {data.get('titre', '?')}\n"
            f"Etape de reprise : {etape}"
            + (f"\nArrêt après : {effective_stop_after}" if effective_stop_after else ""),
            title="Reprise de production",
            border_style="yellow",
        ))

        # Valider les champs obligatoires du checkpoint
        for _required in ("titre", "saison", "numero"):
            if _required not in data:
                raise ValueError(
                    f"Checkpoint corrompu : champ '{_required}' manquant dans data. "
                    f"Clés présentes : {list(data.keys())}"
                )

        _log_direct(f"Lancement pipeline — etape_depart={etape}, stop_after={effective_stop_after}")
        pipeline(
            titre=data["titre"],
            resume=data.get("resume", ""),
            saison=data["saison"],
            numero=data["numero"],
            morale=data.get("morale", ""),
            dry_run=data.get("dry_run", False),
            auto=auto,
            etape_depart=etape,
            checkpoint_data=data.get("rapport"),
            type_episode=data.get("type_episode", "standard"),
            no_publish=no_publish,
            stop_after=effective_stop_after,
            pubdate_offset_seconds=data.get("pubdate_offset_seconds", 0),
        )
        _log_direct(f"Pipeline terminé avec succès pour {episode_id}")
    except ProductionAbandonnee as e:
        _log_direct(f"Production abandonnée : {e}")
        console.print(f"\n[bold yellow]Production arrêtée : {e}[/bold yellow]")
    except SystemExit:
        raise  # Ne pas intercepter sys.exit() du SIGTERM handler
    except Exception as e:
        import traceback as _tb
        _full_tb = _tb.format_exc()
        _log_direct(f"ERREUR FATALE : {type(e).__name__}: {e}")
        _log_direct(f"TRACEBACK COMPLET:\n{_full_tb}")
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur lors de la reprise")
        # CRITICAL: Marquer la production 'failed' en DB pour éviter que
        # _auto_resume_interrupted ne la relance en boucle à chaque redéploiement.
        # Sans ce marquage, le status reste 'interrupted'/'started'/etc. →
        # chaque redeploy re-auto-resume → même crash → boucle infinie.
        _mark_failed_in_db(episode_id)
        sys.exit(1)


@cli.command("planifier-saison")
@click.option("--saison", "-s", type=click.IntRange(min=1), required=True, help="Numero de la saison (>= 1)")
@click.option("--theme", "-t", required=True, help="Theme central de la saison")
@click.option("--description", "-d", default="", help="Description / vision du producteur")
@click.option("--personnages", "-p", default="", help="Personnages secondaires a introduire (separes par des virgules)")
@click.option("--nb-episodes", "-n", type=click.IntRange(min=3, max=20), default=10, help="Nombre d'episodes (defaut 10)")
@click.option("--auto", is_flag=True, help="Mode automatique sans validation humaine")
def planifier_saison(saison: int, theme: str, description: str, personnages: str, nb_episodes: int, auto: bool):
    """Planifie une saison complete de 10 episodes avec arcs narratifs."""
    # Valider que le thème n'est pas vide
    if not theme or not theme.strip():
        console.print(panel_erreur("Le thème de la saison ne peut pas être vide.", titre="Thème manquant"))
        raise SystemExit(1)
    theme = theme.strip()

    console.print(Panel(
        f"[bold]Planification — Saison {saison}[/bold]\n"
        f"Theme : {theme}\n"
        f"Episodes : {nb_episodes}\n"
        f"Description : {description or 'non fournie'}",
        title="Planificateur de saison",
        border_style="blue",
    ))

    # Charger les saisons précédentes pour continuité
    # IMPORTANT : exclure la saison courante pour éviter que le LLM
    # ne l'interprète comme "déjà existante" et incrémente le numéro
    saisons_prec = []
    for num in config.liste_saisons():
        if num >= saison:
            continue
        plan_prec = config.charger_saison(num)
        if plan_prec:
            saison_data_prec = plan_prec.get("saison", {})
            saisons_prec.append({
                "numero": saison_data_prec.get("numero", num),
                "theme": saison_data_prec.get("theme", "?"),
                "description": saison_data_prec.get("description", ""),
                "saison": saison_data_prec,
            })

    # Charger les archives de saisons précédentes pour continuité renforcée
    archives_saisons = []
    for num in config.liste_saisons():
        if num >= saison:
            continue
        chemin_archive = config.ARCHIVES_DIR / f"archive_saison_{num:02d}.json"
        if chemin_archive.exists():
            try:
                with open(chemin_archive, "r", encoding="utf-8") as f:
                    archives_saisons.append(json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Archive saison %d illisible : %s", num, e)

    # Avertir si l'archive de la saison précédente est absente
    if saison > 1:
        archive_prec = config.ARCHIVES_DIR / f"archive_saison_{saison - 1:02d}.json"
        if not archive_prec.exists():
            console.print(
                f"[bold yellow]{Icons.ATTENTION_IC} Archive de la saison {saison - 1} "
                f"non trouvée. La continuité inter-saisons sera limitée.\n"
                f"  Terminez la saison {saison - 1} pour générer l'archive automatiquement.[/bold yellow]"
            )

    personnages_list = [p.strip() for p in personnages.split(",") if p.strip()] if personnages else None

    try:
        planificateur = Planificateur()
        plan = planificateur.planifier_saison(
            numero_saison=saison,
            theme=theme,
            description=description,
            personnages_secondaires=personnages_list,
            saisons_precedentes=saisons_prec or None,
            preferences_producteur=_construire_bloc_preferences(),
            nb_episodes=nb_episodes,
            archives_saisons=archives_saisons or None,
        )

        # Forcer le numéro de saison dans le plan (le LLM peut l'avoir changé)
        plan.setdefault("saison", {})["numero"] = saison

        # Intégrer les événements spéciaux dans le plan
        plan = Planificateur.integrer_evenements_speciaux(plan)

        # Valider les types d'épisodes retournés par le LLM
        types_valides = {"ouverture", "standard", "mi-saison", "final", "bonus"}
        plan_episodes = plan.get("saison", {}).get("episodes", [])
        for ep in plan_episodes:
            t = ep.get("type", "standard")
            if t not in types_valides:
                logger.warning(
                    "Type d'épisode invalide '%s' pour '%s' — corrigé en 'standard'",
                    t, ep.get("titre", "?"),
                )
                ep["type"] = "standard"

        # Valider la séquence des numéros d'épisodes
        numeros = [ep.get("numero") for ep in plan_episodes]
        attendus = list(range(1, len(numeros) + 1))
        if numeros != attendus:
            logger.warning(
                "Numéros d'épisodes non séquentiels (%s) — renumérotation automatique",
                numeros,
            )
            for idx, ep in enumerate(plan_episodes, 1):
                ep["numero"] = idx

        # Sauvegarder le plan (brouillon)
        chemin_json = config.SAISONS_DIR / f"saison_{saison:02d}.json"
        planificateur.sauvegarder(plan, chemin_json)
        console.print(f"  Plan sauvegarde : {chemin_json}")

        # Purger l'historique des épisodes de cette saison dont le titre a changé
        # (sinon, produire-saison les skip comme "déjà produits")
        try:
            historique = charger_historique()
            prefix = f"S{saison:02d}"
            titres_plan = {}
            for ep in plan.get("saison", {}).get("episodes", []):
                ep_id = f"S{saison:02d}E{ep['numero']:02d}"
                titres_plan[ep_id] = ep.get("titre", "")
            historique_filtre = [
                h for h in historique
                if not h.get("episode_id", "").startswith(prefix)
                or h.get("titre", "") == titres_plan.get(h.get("episode_id", ""), "")
            ]
            if len(historique_filtre) < len(historique):
                nb_purge = len(historique) - len(historique_filtre)
                sauvegarder_historique(historique_filtre)
                console.print(
                    f"  [yellow]{nb_purge} épisode(s) obsolète(s) supprimé(s) de l'historique "
                    f"(plan changé)[/yellow]"
                )
        except Exception as e:
            logger.warning("Purge historique échouée : %s", e)

        # Afficher le plan complet
        _afficher_plan_saison(plan)

        # ── Validation humaine du plan de saison (go/no-go) ──────────
        if not auto:
            plan = _validation_plan_saison(
                plan=plan,
                chemin_json=chemin_json,
                planificateur=planificateur,
                saison=saison,
                theme=theme,
                description=description,
                personnages_list=personnages_list,
                saisons_prec=saisons_prec,
                nb_episodes=nb_episodes,
                archives_saisons=archives_saisons,
            )
        else:
            plan["saison"].setdefault("decisions_humaines", []).append({
                "action": "auto_valide",
                "timestamp": datetime.now().isoformat(),
            })

        # ── Prévisualisation des ambiances sonores de saison ──────────
        if not auto:
            plan = _previsualiser_ambiances_saison(
                plan=plan,
                chemin_json=chemin_json,
                saison=saison,
            )

        # Re-sauvegarder le plan valide (JSON + DB + Object Storage)
        _sauvegarder_plan_complet(plan, chemin_json, saison, planificateur)
        console.print(f"  Plan sauvegardé (JSON + DB + Object Storage).")

        # Exporter en CSV et Markdown
        chemin_csv = config.SAISONS_DIR / f"saison_{saison:02d}.csv"
        chemin_md = config.SAISONS_DIR / f"saison_{saison:02d}.md"
        planificateur.exporter_csv(plan, chemin_csv)
        planificateur.exporter_markdown(plan, chemin_md)
        console.print(f"  Export CSV : {chemin_csv}")
        console.print(f"  Export Markdown : {chemin_md}")

        console.print(panel_succes(
            f"Plan de saison {saison} valide et exporte.\n"
            f"  JSON : {chemin_json}\n"
            f"  CSV  : {chemin_csv}\n"
            f"  MD   : {chemin_md}",
            titre="Plan de saison valide",
        ))

    except ProductionAbandonnee as e:
        console.print(f"\n[bold yellow]Planification arretee : {e}[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Erreur : {e}[/bold red]")
        logger.exception("Erreur lors de la planification")
        sys.exit(1)


@cli.command("produire-saison")
@click.option("--saison", "-s", type=click.IntRange(min=1), required=True, help="Numero de la saison (>= 1)")
@click.option("--episodes", "-e", default="", help="Episodes specifiques (ex: '1,3,5' — vide = tous)")
@click.option("--dry-run", is_flag=True, help="Tester sans audio ni publication")
@click.option("--auto", is_flag=True, help="Mode automatique sans validation humaine")
@click.option("--no-publish", is_flag=True, help="Sauter l'etape de publication (upload + RSS)")
def produire_saison(saison: int, episodes: str, dry_run: bool, auto: bool, no_publish: bool):
    """Produit les episodes d'une saison a partir du plan de saison."""
    plan = config.charger_saison(saison)
    if not plan:
        console.print(f"[red]Plan de saison {saison} introuvable. Lancez planifier-saison d'abord.[/red]")
        sys.exit(1)

    if "saison" not in plan or "episodes" not in plan.get("saison", {}):
        console.print("[red]Plan de saison invalide : clés 'saison' ou 'episodes' manquantes.[/red]")
        sys.exit(1)

    saison_data = plan["saison"]
    episodes_plan = saison_data["episodes"]

    # Filtrer les épisodes si spécifié
    if episodes:
        try:
            nums = [int(n.strip()) for n in episodes.split(",") if n.strip()]
        except ValueError:
            console.print(
                "[red]Format invalide pour --episodes. "
                "Utilisez des numeros separes par des virgules : --episodes '1,3,5'[/red]"
            )
            sys.exit(1)
        episodes_plan = [ep for ep in episodes_plan if ep["numero"] in nums]
        if not episodes_plan:
            console.print(f"[red]Aucun episode trouve pour les numeros {nums} dans le plan.[/red]")
            sys.exit(1)

    # Detecter les episodes deja produits pour les skipper
    # (en vérifiant que le plan n'a pas changé — si l'histoire a changé,
    #  l'épisode est considéré comme non produit et sera re-produit)
    deja_produits = _episodes_deja_produits(saison, episodes_plan)
    episodes_a_produire = []
    episodes_skipped = []
    for ep in episodes_plan:
        ep_id = f"S{saison:02d}E{ep['numero']:02d}"
        if ep_id in deja_produits:
            episodes_skipped.append(ep)
        else:
            episodes_a_produire.append(ep)

    if episodes_skipped:
        noms_skipped = ", ".join(
            f"E{ep['numero']:02d}" for ep in episodes_skipped
        )
        console.print(
            f"[yellow]  Episodes deja produits (skipped) : {noms_skipped}[/yellow]"
        )

    if not episodes_a_produire:
        console.print("[green]Tous les episodes de cette saison sont deja produits.[/green]")
        return

    console.print(Panel(
        f"[bold]Production sérielle — Saison {saison}[/bold]\n"
        f"Theme : {saison_data.get('theme', 'N/A')}\n"
        f"A produire : {len(episodes_a_produire)}/{len(episodes_plan)} episodes\n"
        f"Mode : {'DRY RUN' if dry_run else 'PRODUCTION'}",
        title="Production de saison",
        border_style="blue",
    ))

    # ── Validation humaine du plan avant production (go/no-go) ───────
    if not auto:
        _afficher_plan_saison(plan)
        console.print(panel_validation([
            ("v", "Valider — lancer la production"),
            ("a", "Abandonner"),
        ], titre="Go / No-Go — Plan de saison"))

        while True:
            choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()
            if choix in ("v", "g", "go", "valider"):
                break
            elif choix in ("a", "abandonner"):
                console.print(
                    "[bold yellow]Production annulée. "
                    "Modifiez le plan avec planifier-saison si nécessaire.[/bold yellow]"
                )
                return
            else:
                console.print("[red]  Choix non reconnu. Tapez v pour valider ou a pour abandonner.[/red]")

    resultats = []
    # Ajouter les episodes skippés au rapport
    for ep in episodes_skipped:
        resultats.append({"status": "skipped", "episode": ep["titre"], "raison": "deja produit"})

    nb_a_produire = len(episodes_a_produire)
    for i, ep in enumerate(episodes_a_produire, 1):
        ep_id = f"S{saison:02d}E{ep['numero']:02d}"
        console.print()
        console.print(panel_separateur_episode(
            episode_courant=i,
            total_episodes=nb_a_produire,
            episode_id=ep_id,
            titre=ep["titre"],
            type_episode=ep.get("type", "standard"),
        ))

        try:
            rapport = pipeline(
                titre=ep["titre"],
                resume=ep.get("resume", ep.get("histoire_biblique", "")),
                saison=saison,
                numero=ep["numero"],
                morale=ep.get("morale", ""),
                dry_run=dry_run,
                auto=auto,
                contexte_saison=plan,
                type_episode=ep.get("type", "standard"),
                # Espacer les pubDate RSS d'1h entre chaque épisode
                # pour garantir un tri correct dans les apps podcast
                # Utilise ep["numero"] (pas le compteur de boucle) pour un offset stable
                pubdate_offset_seconds=ep["numero"] * 3600,
                no_publish=no_publish,
                # Contexte d'affichage sériel
                episode_courant=i,
                total_episodes=nb_a_produire,
                saison_theme=saison_data.get("theme", ""),
            )
            resultats.append({"status": "ok", "episode": ep["titre"], "rapport": rapport})
        except ProductionAbandonnee as e:
            console.print(f"\n[bold yellow]Production abandonnée : {e}[/bold yellow]")
            resultats.append({"status": "skipped", "episode": ep["titre"], "raison": str(e)})
        except Exception as e:
            logger.exception("Erreur sur l'episode %s", ep.get("titre", "?"))
            resultats.append({"status": "error", "episode": ep["titre"], "erreur": str(e)})
            console.print(
                f"  [bold red]{Icons.ERREUR} Épisode '{ep['titre']}' échoué : {e}[/bold red]"
            )
            # Proposer de continuer ou d'arrêter la production
            if not auto and nb_a_produire - i > 0:
                choix = console.input(
                    f"[bold yellow]Épisode échoué. (c) Continuer avec les suivants / (a) Arrêter la saison ? [/] "
                ).strip().lower()
                if choix == "a":
                    console.print("[bold red]Production de saison interrompue.[/bold red]")
                    break

    # Rapport de saison — tableau récapitulatif
    nb_total = len(episodes_plan)
    ok = sum(1 for r in resultats if r["status"] == "ok")
    skipped = sum(1 for r in resultats if r["status"] == "skipped")
    erreurs = sum(1 for r in resultats if r["status"] == "error")

    table = Table(
        title=f"Rapport de saison {saison:02d}",
        border_style=Palette.SUCCES if erreurs == 0 else "red",
        show_lines=True,
    )
    table.add_column("#", style="bold", width=4)
    table.add_column("Épisode", min_width=30)
    table.add_column("Statut", justify="center", width=12)
    table.add_column("Détails", min_width=20)

    for idx, r in enumerate(resultats, 1):
        if r["status"] == "ok":
            statut = f"[{Palette.SUCCES}]{Icons.OK} OK[/]"
            details = ""
        elif r["status"] == "skipped":
            statut = f"[yellow]{Icons.PAUSE} Ignoré[/yellow]"
            details = r.get("raison", "")
        else:
            statut = f"[red]{Icons.FAIL} Échec[/red]"
            details = f"[red]{r.get('erreur', '')}[/red]"
        table.add_row(str(idx), r["episode"], statut, details)

    console.print()
    console.print(table)
    console.print(
        f"\n  {Icons.OK} Réussis : {ok}/{nb_total}  |  "
        f"{Icons.PAUSE} Ignorés : {skipped}/{nb_total}  |  "
        f"{Icons.FAIL} Échecs : {erreurs}/{nb_total}"
    )

    chemin_batch = config.LOGS_DIR / f"saison_{saison:02d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(chemin_batch, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2, default=str)
    console.print(f"\n  Rapport saison : {chemin_batch}")

    if erreurs > 0:
        sys.exit(1)


@cli.command()
@click.option("--saison", "-s", type=int, default=0, help="Filtrer par saison (0 = toutes)")
def dashboard(saison: int):
    """Affiche le dashboard de suivi des épisodes produits."""
    banner(console, "Dashboard de production")

    historique = charger_historique()

    if not historique:
        console.print(Typo.attention("Aucun épisode produit pour le moment."))
        return

    # Filtrer par saison si demandé
    if saison > 0:
        prefix = f"S{saison:02d}"
        historique = [ep for ep in historique if ep.get("episode_id", "").startswith(prefix)]
        if not historique:
            console.print(Typo.attention(f"Aucun épisode produit pour la saison {saison}."))
            return

    # ── Tableau des épisodes ─────────────────────────────────────────────
    titre_table = f"Saison {saison}" if saison > 0 else "Tous les épisodes"
    table = table_episodes_dashboard(titre_table)

    for ep in historique:
        score_val = ep.get("score_review", 0)
        if not isinstance(score_val, (int, float)):
            score_val = 0
        ajouter_episode_dashboard(
            table,
            episode_id=ep.get("episode_id", "?"),
            titre=ep.get("titre", "?"),
            type_episode=ep.get("type_episode", "standard"),
            score=score_val,
            ambiance=ep.get("ambiance", ""),
            date=ep.get("date_production", ""),
            morale=ep.get("morale", ""),
        )

    console.print(table)

    # ── Statistiques globales ────────────────────────────────────────────
    scores = [ep.get("score_review", 0) for ep in historique if isinstance(ep.get("score_review"), (int, float))]
    if scores:
        stats_block(
            console,
            nb_episodes=len(historique),
            score_moyen=sum(scores) / len(scores),
            score_max=max(scores),
            score_min=min(scores),
        )

    # ── Personnages utilisés ─────────────────────────────────────────────
    all_personnages: dict[str, int] = {}
    for ep in historique:
        for p in ep.get("personnages_presents", []):
            all_personnages[p] = all_personnages.get(p, 0) + 1
    personnages_block(console, all_personnages)

    # ── Progression de saison ────────────────────────────────────────────
    if saison > 0:
        plan = config.charger_saison(saison)
        if plan:
            saison_data = plan.get("saison", {})
            episodes_plan = saison_data.get("episodes", [])
            episodes_produits = {ep.get("episode_id") for ep in historique}
            progression_saison(console, saison, episodes_plan, episodes_produits)

            # ── Arcs de personnages (A13) ─────────────────────────────────
            arcs = saison_data.get("arcs_personnages", {})
            if arcs:
                arc_lines = []
                for perso, arc in arcs.items():
                    nom = perso.replace("_", " ").title()
                    arc_lines.append(
                        f"  [{Palette.MIEL}]{nom}[/] : "
                        f"[{Palette.ARDOISE}]{arc.get('depart', '?')}[/] "
                        f"[bold]→[/bold] "
                        f"[{Palette.SUCCES}]{arc.get('arrivee', '?')}[/]"
                    )
                console.print(panel_info(
                    "\n".join(arc_lines),
                    titre=f"{Icons.PAPY} Arcs de personnages — Saison {saison}",
                ))

            # ── Plan vs Production (A14) ──────────────────────────────────
            plan_vs_prod = []
            for ep_plan in episodes_plan:
                ep_id = f"S{saison:02d}E{ep_plan['numero']:02d}"
                ep_hist = next(
                    (e for e in historique if e.get("episode_id") == ep_id),
                    None,
                )
                if ep_hist:
                    score_val = ep_hist.get("score_review", 0)
                    if not isinstance(score_val, (int, float)):
                        score_val = 0
                    plan_vs_prod.append(
                        f"  [{Palette.SUCCES}]{ep_id}[/] "
                        f"[{Palette.IVOIRE}]{ep_plan.get('titre', '?')[:30]}[/] "
                        f"— Score: [{Palette.MIEL}]{score_val}/10[/] "
                        f"— Type: {ep_plan.get('type', 'standard')}"
                    )
                else:
                    plan_vs_prod.append(
                        f"  [{Palette.ARDOISE}]{ep_id}[/] "
                        f"[{Palette.ARDOISE}]{ep_plan.get('titre', '?')[:30]}[/] "
                        f"— [dim]Non produit[/dim]"
                    )
            if plan_vs_prod:
                console.print(panel_info(
                    "\n".join(plan_vs_prod),
                    titre=f"{Icons.EPISODE} Plan vs Production — Saison {saison}",
                ))

    # ── Retours humains récents ───────────────────────────────────────────
    episodes_avec_retours = [
        ep for ep in historique if ep.get("retours_humains")
    ]
    if episodes_avec_retours:
        retours_lines = []
        for ep in episodes_avec_retours[-5:]:  # 5 derniers
            ep_id = ep.get("episode_id", "?")
            retours_lines.append(
                f"{Typo.label_valeur(ep_id, ep['retours_humains'][:80])}"
            )
        console.print(panel_info(
            "\n".join(retours_lines),
            titre=f"{Icons.REVIEW} Retours humains récents",
        ))

    # ── Préférences producteur ─────────────────────────────────────────
    preferences = charger_preferences()
    if preferences:
        pref_lines = []
        for pref in preferences[-8:]:  # 8 dernières
            source = pref.get("source_episode", "")
            source_str = f" [{Palette.ARDOISE}]({source})[/]" if source else ""
            pref_lines.append(
                f"  [{Palette.MIEL}]{Icons.ETOILE}[/] [{Palette.IVOIRE}]{pref['regle'][:70]}[/]{source_str}"
            )
        if len(preferences) > 8:
            pref_lines.append(
                Typo.dim(f"  … et {len(preferences) - 8} autre(s)")
            )
        console.print(panel_info(
            "\n".join(pref_lines),
            titre=f"{Icons.PAPY} Préférences producteur ({len(preferences)} règles)",
        ))

    # ── Saisons disponibles ──────────────────────────────────────────────
    saisons_dispo = config.liste_saisons()
    if saisons_dispo:
        nums_str = "  ".join(
            f"[bold {Palette.OCRE}]{s}[/]" for s in saisons_dispo
        )
        console.print(panel_info(
            f"  {Icons.SAISON} {nums_str}",
            titre=f"{Icons.SAISON} Saisons planifiées",
        ))

    # ── Coûts détaillés ──────────────────────────────────────────────────
    cout_total_global = 0.0
    total_chars = 0
    rapports_dir = config.LOGS_DIR
    cout_par_service: dict[str, float] = {}
    pattern = f"S{saison:02d}*_rapport.json" if saison > 0 else "S*_rapport.json"
    for rapport_path in rapports_dir.glob(pattern):
        try:
            with open(rapport_path, "r", encoding="utf-8") as f:
                rapport = json.load(f)
            chars = rapport.get("etapes", {}).get("audio", {}).get("caracteres", {})
            if isinstance(chars, dict):
                total_chars += sum(chars.values())
            couts_ep = rapport.get("couts", {})
            for service, detail in couts_ep.items():
                if service == "total_estime":
                    cout_total_global += detail
                elif isinstance(detail, dict):
                    cout_par_service[service] = cout_par_service.get(service, 0) + detail.get("cout", 0)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    if total_chars > 0 or cout_total_global > 0:
        t_couts = table_couts()
        if total_chars > 0:
            t_couts.add_row("ElevenLabs", f"{total_chars:,} caractères", "—")
        for service, cout in sorted(cout_par_service.items()):
            t_couts.add_row(service, "", f"${cout:.4f}")
        if cout_total_global > 0:
            t_couts.add_row(
                f"[bold {Palette.IVOIRE}]TOTAL[/]",
                "",
                f"[bold {Palette.MIEL}]${cout_total_global:.4f}[/]",
            )
        console.print()
        console.print(t_couts)

    # ── Checkpoints en cours ─────────────────────────────────────────────
    checkpoints = list(config.CHECKPOINTS_DIR.glob("*_checkpoint.json"))
    if checkpoints:
        cp_lines = []
        for cp_path in checkpoints:
            try:
                with open(cp_path, "r", encoding="utf-8") as f:
                    cp = json.load(f)
                cp_lines.append(
                    f"  [{Palette.BLEU_CIEL}]{cp['episode_id']}[/] "
                    f"[{Palette.ARDOISE}]étape : {cp['etape']} — {cp['timestamp']}[/]"
                )
            except (json.JSONDecodeError, FileNotFoundError):
                cp_lines.append(f"  [{Palette.ARDOISE}]{cp_path.name} (illisible)[/]")
        console.print(Panel(
            "\n".join(cp_lines),
            title=f"[{Palette.ATTENTION}]{Icons.CHECKPOINT} Checkpoints en attente ({len(checkpoints)})[/]",
            border_style=Style(color=Palette.ATTENTION),
            padding=(1, 2),
        ))

    console.print()


@cli.command("db-status")
def db_status():
    """Affiche l'état de la base de données PostgreSQL."""
    if not _DB_AVAILABLE:
        console.print("[red]Module database non disponible. Installez psycopg2-binary.[/red]")
        return

    if not database.DATABASE_URL:
        console.print("[yellow]DATABASE_URL non configurée.[/yellow]")
        console.print("[dim]Le système fonctionne en mode fichiers JSON.[/dim]")
        return

    if not database.verifier_connexion():
        console.print("[red]Connexion PostgreSQL échouée.[/red]")
        return

    console.print(Typo.succes("PostgreSQL connecté"))
    console.print()

    try:
        stats = database.obtenir_stats_db()
        table = table_db_status()

        total = 0
        max_count = max(stats.values()) if stats else 1
        for table_name, count in stats.items():
            barre_len = round((count / max_count) * 20) if max_count > 0 else 0
            barre = f"[{Palette.BLEU_CIEL}]{'█' * barre_len}{'░' * (20 - barre_len)}[/]"
            table.add_row(table_name, str(count), barre)
            total += count

        table.add_row(
            f"[bold {Palette.IVOIRE}]TOTAL[/]",
            f"[bold {Palette.MIEL}]{total}[/]",
            "",
        )
        console.print(table)

        # Coûts totaux
        with database.get_cursor(commit=False) as cur:
            cur.execute("SELECT COALESCE(SUM(cout_estime), 0) AS total FROM couts_api")
            row = cur.fetchone()
            cout_total = float(row["total"]) if row else 0
        console.print(f"\n  Coût total estimé : ${cout_total:.4f}")

        # Dernières productions
        with database.get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT episode_id, status, started_at, completed_at "
                "FROM productions ORDER BY started_at DESC LIMIT 5"
            )
            rows = cur.fetchall()
        if rows:
            console.print("\n[bold]  Dernières productions :[/bold]")
            for row in rows:
                status_style = "green" if row["status"] == "completed" else "yellow"
                console.print(
                    f"    {row['episode_id']} — "
                    f"[{status_style}]{row['status']}[/{status_style}] "
                    f"({str(row['started_at'])[:16]})"
                )

    except Exception as e:
        console.print(f"[red]Erreur : {e}[/red]")


@cli.command("migrer-json-vers-db")
def migrer_json_vers_db():
    """Migre toutes les données JSON existantes vers PostgreSQL."""
    if not _use_db():
        console.print("[red]PostgreSQL non disponible. Configurez DATABASE_URL.[/red]")
        return

    console.print(Panel(
        "[bold]Migration JSON → PostgreSQL[/bold]\n"
        "Toutes les données JSON existantes seront importées en DB.\n"
        "[dim]Les données JSON ne sont pas supprimées.[/dim]",
        title="Migration",
        border_style="blue",
    ))

    from migrate_json_to_db import migrer_tout
    migrer_tout()
    console.print(f"[{Palette.SUCCES}]Migration terminée ![/]")


@cli.command("configurer-voix")
@click.option("--personnage", "-c", required=True, help="Identifiant du personnage (ex: mamie_rose)")
@click.option("--voice-id", "-v", default="", help="ElevenLabs voice ID a assigner")
@click.option("--pan", "-p", type=float, default=None, help="Panoramique stereo (-1.0 gauche a 1.0 droite)")
@click.option("--stability", type=float, default=None, help="TTS stability (0.0-1.0)")
@click.option("--similarity-boost", type=float, default=None, help="TTS similarity boost (0.0-1.0)")
@click.option("--style", type=float, default=None, help="TTS style (0.0-1.0)")
def configurer_voix(personnage: str, voice_id: str, pan: float | None,
                    stability: float | None, similarity_boost: float | None,
                    style: float | None):
    """Configure la voix ElevenLabs et le panoramique stereo d'un personnage."""
    if not voice_id and pan is None and stability is None and similarity_boost is None and style is None:
        console.print("[red]Erreur : specifiez au moins --voice-id, --pan, ou un parametre TTS.[/red]")
        sys.exit(1)

    persos = config.personnages_valides()
    if personnage not in persos:
        console.print(
            f"[yellow]Personnage '{personnage}' inconnu — il sera cree dans la bible.[/yellow]"
        )

    config.configurer_voix(
        personnage_id=personnage,
        voice_id=voice_id,
        pan=pan,
        stability=stability,
        similarity_boost=similarity_boost,
        style=style,
    )

    # Afficher le résultat
    table = Table(title=f"Configuration voix — {personnage}", border_style="blue")
    table.add_column("Parametre", style="bold")
    table.add_column("Valeur")

    vid = config.VOICE_IDS.get(personnage, "")
    table.add_row("voice_id", vid if vid else "[dim]non configure[/dim]")
    table.add_row("pan", str(config.STEREO_PAN.get(personnage, 0.0)))
    settings = config.VOICE_SETTINGS.get(personnage, {})
    table.add_row("stability", str(settings.get("stability", "-")))
    table.add_row("similarity_boost", str(settings.get("similarity_boost", "-")))
    table.add_row("style", str(settings.get("style", "-")))

    console.print(table)
    console.print(f"[{Palette.SUCCES}]Configuration sauvegardee dans {config.PERSONNAGES_JSON_PATH}[/]")


if __name__ == "__main__":
    cli()
