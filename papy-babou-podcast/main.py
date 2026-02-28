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
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.style import Style

import config
from utils import fichier_lock
from agents import (
    Scripteur, Reviewer, ProducteurAudio, SfxProvider, Monteur,
    Metadonnees, Publisher, CoverArt, Planificateur,
)
from theme import (
    Palette, Icons, Typo, NOMS_PERSONNAGES_STYLED,
    creer_console, banner, get_rich_theme,
    panel_episode, panel_validation, panel_erreur, panel_succes,
    panel_info, panel_rapport_final,
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
        AuditRepo,
    )
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

console = creer_console()

# ── Configuration du logging ──────────────────────────────────────────────────

LOG_FILE = config.LOGS_DIR / "production.log"


def configurer_logging() -> None:
    """Configure le logging avec sortie console (Rich) et fichier."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True),
            logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        ],
    )


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


def sauvegarder_historique(historique: list[dict]) -> None:
    """Sauvegarde l'historique des épisodes (JSON — rétrocompatibilité)."""
    with open(HISTORIQUE_PATH, "w", encoding="utf-8") as f:
        json.dump(historique, f, ensure_ascii=False, indent=2)


# ── Préférences producteur (mémoire persistante) ────────────────────────────


def charger_preferences() -> list[dict]:
    """Charge les preferences du producteur depuis le fichier JSON.

    Returns:
        Liste de regles/preferences persistantes.
    """
    if config.PREFERENCES_PATH.exists():
        with open(config.PREFERENCES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
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
    preferences = charger_preferences()
    preferences.append({
        "regle": regle,
        "categorie": categorie,
        "source_episode": source_episode,
        "date_ajout": datetime.now().isoformat(),
    })
    sauvegarder_preferences(preferences)
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
        lignes.append(f"  {i}. {pref['regle']}")
    return "\n".join(lignes)


def ajouter_historique(rapport: dict, script: dict) -> None:
    """Ajoute un épisode à l'historique (DB + JSON pour rétrocompatibilité)."""
    episode = script.get("episode", {})

    # Extraire les personnages présents dans le script
    personnages_presents = sorted({
        seg["personnage"] for seg in episode.get("segments", [])
        if seg["personnage"] != "sfx"
    })

    # Construire un résumé court à partir des premiers segments (pas juste le titre)
    premiers_textes = [
        seg["texte"] for seg in episode.get("segments", [])[:3]
        if seg.get("personnage") != "sfx"
    ]
    resume_court = " ".join(premiers_textes)[:200] if premiers_textes else episode.get("titre", "")

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
        historique.append(entree)
        sauvegarder_historique(historique)


# ── Système de checkpoints ───────────────────────────────────────────────────

# Variable globale pour l'ID de production courante (DB)
_production_id_courante: int | None = None


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
    global _production_id_courante

    # Sauvegarder en DB si disponible
    if _use_db() and _production_id_courante:
        try:
            ProductionRepo.maj_etape(
                _production_id_courante,
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
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    logger.info("Checkpoint sauvegardé : %s (étape: %s)", chemin, etape)
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
    global _production_id_courante

    # En DB : marquer terminé (jamais supprimé)
    if _use_db() and _production_id_courante:
        try:
            # Le statut sera mis à jour par ProductionRepo.terminer()
            pass
        except Exception as e:
            logger.warning("DB indisponible pour archivage checkpoint : %s", e)

    # Fichier JSON : renommer au lieu de supprimer
    chemin = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
    if chemin.exists():
        archive = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint_done_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        chemin.rename(archive)
        logger.info("Checkpoint archivé (non supprimé) : %s → %s", chemin, archive)


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
        cout_sfx = nb_sfx_elevenlabs * 0.01  # ~$0.01 par SFX généré
        detail["elevenlabs_sfx"] = {
            "nb_sfx": nb_sfx_elevenlabs,
            "cout": round(cout_sfx, 4),
        }
        total += cout_sfx

    # Coût Claude (estimation basée sur les tokens)
    # ~2000 tokens input + ~4000 tokens output par appel (script, review, meta)
    nb_appels_claude = sum(1 for etape in ("script", "metadonnees") if etape in rapport.get("etapes", {}))
    score_review = rapport.get("etapes", {}).get("script", {}).get("score_review", 0)
    if score_review > 0:
        nb_appels_claude += 1  # review
    if nb_appels_claude > 0:
        cout_input = nb_appels_claude * 2000 * couts["claude_input_par_token"]
        cout_output = nb_appels_claude * 4000 * couts["claude_output_par_token"]
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
                for d in rapport.get("decisions_humaines", []) if rapport else []:
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
                console.print(table_review(resultat_review["review"]))
                if reviewer.est_valide(resultat_review):
                    script = {"episode": resultat_review["episode"]}
                else:
                    script = {"episode": resultat_review["episode"]}
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


def _validation_plan_saison(
    plan: dict,
    chemin_json: Path,
    planificateur: Planificateur,
    saison: int,
    theme: str,
    description: str = "",
    personnages_list: list[str] | None = None,
    saisons_prec: list[dict] | None = None,
) -> dict:
    """Point de validation humaine du plan de saison (go/no-go).

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

    Returns:
        Le plan (potentiellement modifie ou regenere).

    Raises:
        ProductionAbandonnee: Si l'utilisateur choisit d'abandonner.
    """
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
                console.print(f"[{Palette.SUCCES}]  Plan rechargé et validé depuis le fichier.[/]")
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
                preferences_producteur=_construire_bloc_preferences(),
            )
            planificateur.sauvegarder(plan, chemin_json)
            console.print(f"[{Palette.SUCCES}]  Nouveau plan généré et sauvegardé.[/]")
            _afficher_plan_saison(plan)

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
                    preferences_producteur=_construire_bloc_preferences(),
                )
                # Stocker les instructions dans le plan pour reference future (A5)
                plan["saison"].setdefault("instructions_producteur", []).append({
                    "instructions": instructions_texte,
                    "date": datetime.now().isoformat(),
                })
                planificateur.sauvegarder(plan, chemin_json)
                console.print(f"[{Palette.SUCCES}]  Nouveau plan généré avec vos instructions.[/]")
                _afficher_plan_saison(plan)

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
    table = table_saison_plan(saison_num, saison_data["theme"])
    for ep in saison_data["episodes"]:
        table.add_row(
            str(ep["numero"]),
            ep["titre"],
            ep.get("type", "standard"),
            ep.get("ambiance", "?"),
            ep["morale"][:40],
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
        console.print(f"      Morale : {ep['morale']}")

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
        taille_mb = resultat_montage.get("taille_mb", 0)
        if taille_mb:
            info_lines.append(f"{Typo.label_valeur('Taille', f'{taille_mb:.1f} MB')}")

    if script:
        nb_sfx = sum(1 for s in script["episode"].get("segments", []) if s["personnage"] == "sfx")
        nb_voix = sum(1 for s in script["episode"].get("segments", []) if s["personnage"] != "sfx")
        info_lines.append(f"{Typo.label_valeur('Segments', f'{nb_voix} voix + {nb_sfx} SFX')}")

    info_lines.append("")
    info_lines.append(Typo.dim("Écoutez le fichier preview avant de valider la publication."))
    info_lines.append(Typo.dim(f"  Fichier : {chemin_preview}"))

    console.print(panel_info(
        "\n".join(info_lines),
        titre=f"{Icons.MONTAGE} Écoute du montage",
    ))

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
            ("v", "Valider et publier"),
            ("e", "Éditer le script (pauses, SFX) puis relancer le montage"),
            ("r", "Relancer le montage tel quel"),
            ("a", "Abandonner (l'audio est conservé, pas de publication)"),
        ]
        console.print(panel_validation(options, titre="Validation du montage"))

        choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

        if choix in ("v", "valider"):
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
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    console.print(f"[red]  Erreur au rechargement : {e}[/red]")
                    console.print("[yellow]  Les données précédentes sont conservées.[/yellow]")
                except ValueError as e:
                    console.print(f"[red]  Structure invalide : {e}[/red]")
                    console.print("[yellow]  Les données précédentes sont conservées.[/yellow]")
            else:
                console.print("[yellow]  Fichier script introuvable — relance sans modification.[/yellow]")

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
            console.print("[red]  Choix non reconnu. Tapez v, e, r ou a.[/red]")


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

    while True:
        options = [
            ("v", "Valider les métadonnées"),
            ("c", "Régénérer avec instructions"),
            ("m", "Modifier le JSON manuellement"),
            ("a", "Abandonner"),
        ]
        console.print(panel_validation(options, titre="Validation des métadonnées"))

        choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()

        if choix in ("v", "valider"):
            console.print(f"[{Palette.SUCCES}]  Métadonnées validées par le producteur.[/]")
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "metadonnees",
                    "action": "valide",
                    "timestamp": datetime.now().isoformat(),
                })
            return meta

        elif choix in ("c", "corrections"):
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
            if lignes and script:
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
            elif not script:
                console.print("[yellow]  Script non disponible — régénération impossible.[/yellow]")

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
            console.print("[red]  Choix non reconnu. Tapez v, c, m ou a.[/red]")


def _validation_publication(
    meta: dict,
    episode_id: str,
    rapport: dict | None = None,
) -> bool:
    """Point de confirmation avant publication RSS.

    Returns:
        True si l'utilisateur confirme la publication, False pour annuler.
    """
    info_lines = [
        f"{Typo.label_valeur('Épisode', episode_id)}",
        f"{Typo.label_valeur('Titre', meta.get('titre', 'N/A'))}",
        Typo.dim("La publication ajoutera l'épisode au flux RSS public."),
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
            if rapport is not None:
                rapport.setdefault("decisions_humaines", []).append({
                    "etape": "publication",
                    "action": "abandonne",
                    "timestamp": datetime.now().isoformat(),
                })
            raise ProductionAbandonnee(
                "Production arrêtée avant publication. "
                "L'audio et les métadonnées sont conservés."
            )

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

    Returns:
        Rapport de production complet.
    """
    global _production_id_courante
    _production_id_courante = None  # Reset au début de chaque pipeline

    episode_id = f"S{saison:02d}E{numero:02d}"
    rapport = checkpoint_data or {
        "episode_id": episode_id,
        "titre": titre,
        "dry_run": dry_run,
        "debut": datetime.now().isoformat(),
        "etapes": {},
    }

    # Créer une production en DB si disponible
    if _use_db():
        try:
            _production_id_courante = ProductionRepo.creer(
                episode_id=episode_id,
                dry_run=dry_run,
                auto_mode=auto,
            )
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
            logger.info("Production DB #%d créée pour %s", _production_id_courante, episode_id)
        except Exception as e:
            logger.warning("DB indisponible pour création production : %s", e)
            _production_id_courante = None

    try:
        return _pipeline_inner(
            titre=titre, resume=resume, saison=saison, numero=numero,
            morale=morale, dry_run=dry_run, auto=auto,
            max_iterations_review=max_iterations_review,
            etape_depart=etape_depart, checkpoint_data=checkpoint_data,
            contexte_saison=contexte_saison, type_episode=type_episode,
            episode_id=episode_id, rapport=rapport,
        )
    except ProductionAbandonnee:
        raise
    except Exception as e:
        # Marquer la production comme échouée en DB (BUG 29)
        logger.error("Pipeline échoué pour %s : %s", episode_id, e)
        if _use_db() and _production_id_courante:
            try:
                ProductionRepo.echouer(_production_id_courante, str(e))
                EpisodeRepo.maj_status(episode_id, "failed")
            except Exception as db_err:
                logger.warning("DB indisponible pour marquage échec : %s", db_err)
        # Sauvegarder le rapport partiel
        rapport["erreur"] = str(e)
        rapport["fin"] = datetime.now().isoformat()
        chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport_echec.json"
        with open(chemin_rapport, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)
        console.print(panel_erreur(
            f"Pipeline échoué pour {episode_id} : {e}\n"
            f"Rapport partiel sauvé : {chemin_rapport}"
        ))
        raise


def _pipeline_inner(
    titre, resume, saison, numero, morale, dry_run, auto,
    max_iterations_review, etape_depart, checkpoint_data,
    contexte_saison, type_episode, episode_id, rapport,
):
    """Corps interne du pipeline, encapsulé pour la gestion d'erreurs."""
    global _production_id_courante

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
                    )

    # Validation des clés API au démarrage
    erreurs_api = config.valider_cles_api(dry_run=dry_run)
    if erreurs_api:
        console.print(Panel(
            "\n".join(f"[red]  {e}[/red]" for e in erreurs_api),
            title="Erreurs de configuration",
            border_style="red",
        ))
        sys.exit(1)

    mode_str = "DRY RUN" if dry_run else "PRODUCTION"
    console.print(panel_episode(
        episode_id=episode_id,
        titre=titre,
        mode=mode_str,
        type_episode=type_episode,
        morale=morale or "non définie",
    ))

    etapes = ["script", "review", "audio", "sfx", "montage", "metadonnees", "publication", "rapport"]
    etape_idx = etapes.index(etape_depart) if etape_depart in etapes else 0

    # Initialiser les variables qui pourraient ne pas être définies lors d'une reprise
    chemin_hq = None
    resultat_montage = None
    duree_secondes = 0.0
    taille_bytes = 0
    score = 0

    # Restaurer les variables depuis le checkpoint si on reprend après le montage
    if checkpoint_data and etape_idx > 4:
        montage_data = checkpoint_data.get("etapes", {}).get("montage", {})
        if montage_data.get("chemin_hq"):
            chemin_hq = Path(montage_data["chemin_hq"])
        duree_secondes = montage_data.get("duree_secondes", 0.0)
        taille_bytes = int(montage_data.get("taille_mb", 0) * 1024 * 1024) if montage_data.get("taille_mb") else 0
        resultat_montage = montage_data

    # Charger l'historique pour la continuité
    historique = charger_historique()

    script = None
    score = 0
    chemin_valide = config.SCRIPTS_DIR / f"{episode_id}_valide.json"

    # Si on reprend, charger le script existant
    if etape_idx > 0 and chemin_valide.exists():
        with open(chemin_valide, "r", encoding="utf-8") as f:
            script = json.load(f)
        logger.info("Script chargé depuis le checkpoint : %s", chemin_valide)

    # ── Étape 1-2 : Scripteur + Reviewer ─────────────────────────────────────

    if etape_idx <= 1:
        console.print(f"\n{Typo.etape(1, 8, 'Génération du script')}")
        scripteur = Scripteur()
        corrections = None

        for iteration in range(1, max_iterations_review + 1):
            console.print(f"  Iteration {iteration}/{max_iterations_review}...")

            script = scripteur.generer(
                titre=titre, resume=resume, saison=saison, numero=numero,
                morale=morale, corrections=corrections, historique=historique,
                contexte_saison=contexte_saison, episode_plan=episode_plan,
                type_episode=type_episode,
                preferences_producteur=_construire_bloc_preferences(),
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

            if reviewer.est_valide(resultat_review):
                script = {"episode": resultat_review["episode"]}
                console.print(f"[{Palette.SUCCES}]  Script validé (score {score}/10).[/]")
                break

            console.print(f"[yellow]  Score insuffisant ({score}/10 < 7) — relance du scripteur[/yellow]")
            corrections = reviewer.extraire_corrections(resultat_review)

        else:
            console.print(
                f"[red]  Score final : {score}/10 apres {max_iterations_review} iterations. "
                "Poursuite avec le meilleur script disponible.[/red]"
            )
            script = {"episode": resultat_review["episode"]}

        scripteur.sauvegarder(script, chemin_valide)

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
            "nb_mots": scripteur.compter_mots(script),
            "duree_estimee_min": round(duree_estimee, 1),
            "chemin": str(chemin_valide),
        }

        # Checkpoint après script (inclut le chemin du script validé)
        sauvegarder_checkpoint(episode_id, "audio", {
            "episode_id": episode_id, "titre": titre, "resume": resume,
            "saison": saison, "numero": numero, "morale": morale,
            "type_episode": type_episode,
            "dry_run": dry_run, "rapport": rapport,
            "chemin_script_valide": str(chemin_valide),
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

            console.print(f"  {len(fichiers_audio)} segments voix générés")
            rapport["etapes"]["audio"] = {
                "nb_segments": len(fichiers_audio),
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
                            production_id=_production_id_courante,
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
                        production_id=_production_id_courante,
                    )
                except Exception as e:
                    logger.warning("DB indisponible pour enregistrement audio : %s", e)

            sauvegarder_checkpoint(episode_id, "sfx", {
                "episode_id": episode_id, "titre": titre, "resume": resume,
                "saison": saison, "numero": numero, "morale": morale,
                "type_episode": type_episode,
                "dry_run": dry_run, "rapport": rapport,
            })

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
            sfx_provider = SfxProvider()
            fichiers_sfx = sfx_provider.produire_sfx(script)

            console.print(f"  {len(fichiers_sfx)} bruitages générés/téléchargés")
            for seg_id, source in sfx_provider.stats.items():
                console.print(f"    {seg_id} : {source}")

            rapport["etapes"]["sfx"] = {
                "nb_sfx": len(fichiers_sfx),
                "sources": dict(sfx_provider.stats),
            }

            # Enregistrer les SFX en DB
            if _use_db():
                try:
                    for seg_id, source in sfx_provider.stats.items():
                        chemin_sfx = config.SEGMENTS_DIR / episode_id / f"{seg_id}.mp3"
                        FichierAudioRepo.enregistrer(
                            episode_id=episode_id,
                            type_fichier="segment_sfx",
                            chemin=str(chemin_sfx),
                            production_id=_production_id_courante,
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
                            cout_estime=nb_sfx_el * 0.01,
                            detail={"nb_sfx_elevenlabs": nb_sfx_el},
                            production_id=_production_id_courante,
                        )
                except Exception as e:
                    logger.warning("DB indisponible pour enregistrement SFX : %s", e)

    # ── Étape 5 : Montage ─────────────────────────────────────────────────────

    if etape_idx <= 4:
        if dry_run:
            console.print(f"\n{Typo.etape(5, 8, 'Montage')}  {Typo.attention('SAUTÉ — dry-run')}")
            rapport["etapes"]["montage"] = {"status": "skipped (dry-run)"}
            reviewer = Reviewer()
            duree_estimee = reviewer.estimer_duree(script)
            duree_secondes = duree_estimee * 60
            taille_bytes = 0
            chemin_hq = None
        else:
            console.print(f"\n{Typo.etape(5, 8, 'Montage')}")
            monteur = Monteur()
            resultat_montage = monteur.assembler(script)

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
                        production_id=_production_id_courante,
                        taille_bytes=taille_bytes,
                        duree_secondes=duree_secondes,
                    )
                    FichierAudioRepo.enregistrer(
                        episode_id=episode_id,
                        type_fichier="episode_preview",
                        chemin=str(resultat_montage["chemin_preview"]),
                        production_id=_production_id_courante,
                        duree_secondes=duree_secondes,
                    )
                except Exception as e:
                    logger.warning("DB indisponible pour enregistrement montage : %s", e)

            sauvegarder_checkpoint(episode_id, "metadonnees", {
                "episode_id": episode_id, "titre": titre, "resume": resume,
                "saison": saison, "numero": numero, "morale": morale,
                "type_episode": type_episode,
                "dry_run": dry_run, "rapport": rapport,
            })

    # ── Validation humaine : montage ─────────────────────────────────────────

    if not auto and not dry_run and chemin_hq and resultat_montage:
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
        else:
            logger.warning(
                "Pas de fichier preview disponible — validation du montage impossible. "
                "Le montage sera publié sans écoute préalable."
            )

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
                    production_id=_production_id_courante,
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
                        production_id=_production_id_courante,
                    )
            except Exception as e:
                logger.warning("DB indisponible pour métadonnées : %s", e)

        # Générer le cover art si configuré
        if meta.get("cover_art_prompt") and config.COVER_ART_CONFIG.get("enabled"):
            console.print("  Génération du cover art...")
            cover_agent = CoverArt()
            cover_path = cover_agent.generer(meta["cover_art_prompt"], episode_id)
            if cover_path:
                meta["cover_art_path"] = str(cover_path)
                metadonnees.sauvegarder(meta, chemin_meta)
                rapport["etapes"]["metadonnees"]["cover_art_path"] = str(cover_path)
                console.print(f"  Cover art : {cover_path}")
                rapport["etapes"]["metadonnees"]["cover_art_cout"] = config.COUTS["openai_dalle3_par_image"]

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

    # ── Étape 7 : Publication ─────────────────────────────────────────────────

    if etape_idx <= 6:
        if dry_run:
            console.print(f"\n{Typo.etape(7, 8, 'Publication')}  {Typo.attention('SAUTÉ — dry-run')}")
            rapport["etapes"]["publication"] = {"status": "skipped (dry-run)"}
        else:
            # Confirmation avant publication (T4)
            publier = True
            if not auto:
                publier = _validation_publication(meta, episode_id, rapport=rapport)

            if publier:
                console.print(f"\n{Typo.etape(7, 8, 'Publication')}")
                publisher = Publisher()
                rapport_pub = publisher.publier(meta, chemin_hq, taille_bytes)
                console.print(f"  URL audio : {rapport_pub['url_audio']}")
                if rapport_pub.get("transcript_url"):
                    console.print(f"  Transcript : {rapport_pub['transcript_url']}")
                rapport["etapes"]["publication"] = rapport_pub

                # Enregistrer publication en DB
                if _use_db():
                    try:
                        PublicationRepo.enregistrer(
                            episode_id=episode_id,
                            rapport_pub=rapport_pub,
                            production_id=_production_id_courante,
                        )
                        EpisodeRepo.maj_status(episode_id, "published")
                    except Exception as e:
                        logger.warning("DB indisponible pour publication : %s", e)
            else:
                console.print(f"\n{Typo.etape(7, 8, 'Publication')}  {Typo.attention('SAUTÉ — choix utilisateur')}")
                rapport["etapes"]["publication"] = {"status": "skipped (user choice)"}

    # ── Étape 8 : Rapport final ───────────────────────────────────────────────

    console.print(f"\n{Typo.etape(8, 8, 'Rapport final')}")
    rapport["fin"] = datetime.now().isoformat()

    # Calculer les métriques de coût
    rapport["couts"] = _calculer_couts(rapport)

    # Sauvegarder le rapport
    chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
    with open(chemin_rapport, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)

    # Ajouter à l'historique
    ajouter_historique(rapport, script)

    # Archiver le checkpoint (JAMAIS supprimer — conservation des données)
    archiver_checkpoint(episode_id)

    # Finaliser la production en DB
    if _use_db() and _production_id_courante:
        try:
            ProductionRepo.terminer(
                _production_id_courante,
                rapport=rapport,
                couts=rapport.get("couts", {}),
            )
            EpisodeRepo.maj_status(episode_id, "produced" if dry_run else "published")
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
@click.option("--dry-run", is_flag=True, help="Tester sans audio ni publication")
@click.option("--auto", is_flag=True, help="Mode automatique sans validation humaine")
def produire(episode: str, saison: int, numero: int, resume: str, morale: str, dry_run: bool, auto: bool):
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
    banner(console, "Vous serez invité à valider le script et le montage avant publication.")

    titre = console.input("[cyan]Titre de l'épisode :[/cyan] ")
    try:
        saison = int(console.input("[cyan]Numéro de saison :[/cyan] "))
        numero = int(console.input("[cyan]Numéro d'épisode :[/cyan] "))
    except ValueError:
        console.print("[red]Les numéros de saison et d'épisode doivent être des entiers.[/red]")
        sys.exit(1)
    resume = console.input("[cyan]Résumé de l'histoire biblique :[/cyan] ")
    morale = console.input("[cyan]Leçon de vie / morale (optionnel) :[/cyan] ")

    dry_run_str = console.input("[cyan]Mode dry-run ? (o/n) :[/cyan] ").strip().lower()
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
def batch(fichier: str, dry_run: bool, auto: bool):
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
    for i, ep in enumerate(planning, 1):
        console.print(f"\n[bold]{'='*60}[/bold]")
        console.print(f"[bold cyan]Épisode {i}/{len(planning)} — {ep.get('titre', '?')}[/bold cyan]")
        console.print(f"[bold]{'='*60}[/bold]")

        try:
            rapport = pipeline(
                titre=ep["titre"],
                resume=ep.get("resume", ""),
                saison=ep.get("saison", 1),
                numero=ep.get("numero", i),
                morale=ep.get("morale", ""),
                dry_run=dry_run,
                auto=auto,
            )
            resultats.append({"status": "ok", "episode": ep["titre"], "rapport": rapport})
        except Exception as e:
            logger.exception("Erreur sur l'episode %s", ep.get("titre", "?"))
            resultats.append({"status": "error", "episode": ep["titre"], "erreur": str(e)})

    # Rapport batch
    console.print(f"\n[bold]{'='*60}[/bold]")
    console.print("[bold green]Rapport batch[/bold green]")
    ok = sum(1 for r in resultats if r["status"] == "ok")
    erreurs = sum(1 for r in resultats if r["status"] == "error")
    console.print(f"  Reussis : {ok}/{len(planning)}")
    console.print(f"  Echecs  : {erreurs}/{len(planning)}")

    for r in resultats:
        status = "[green]OK[/green]" if r["status"] == "ok" else "[red]ERREUR[/red]"
        console.print(f"  {status} — {r['episode']}")
        if r["status"] == "error":
            console.print(f"    [red]{r['erreur']}[/red]")

    # Sauvegarder le rapport batch
    chemin_batch = config.LOGS_DIR / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(chemin_batch, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2, default=str)
    console.print(f"\n  Rapport batch : {chemin_batch}")


@cli.command()
@click.option("--checkpoint", "-c", required=True, type=click.Path(exists=True),
              help="Chemin du fichier checkpoint")
@click.option("--auto", is_flag=True, help="Mode automatique sans validation humaine")
def reprendre(checkpoint: str, auto: bool):
    """Reprend une production depuis un checkpoint."""
    cp = charger_checkpoint(Path(checkpoint))
    data = cp["data"]
    etape = cp["etape"]

    console.print(Panel(
        f"[bold]Reprise depuis le checkpoint[/bold]\n"
        f"Episode : {data['episode_id']} — {data['titre']}\n"
        f"Etape de reprise : {etape}",
        title="Reprise de production",
        border_style="yellow",
    ))

    try:
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
        )
    except ProductionAbandonnee as e:
        console.print(f"\n[bold yellow]Production arrêtée : {e}[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur lors de la reprise")
        sys.exit(1)


@cli.command("planifier-saison")
@click.option("--saison", "-s", type=click.IntRange(min=1), required=True, help="Numero de la saison (>= 1)")
@click.option("--theme", "-t", required=True, help="Theme central de la saison")
@click.option("--description", "-d", default="", help="Description / vision du producteur")
@click.option("--personnages", "-p", default="", help="Personnages secondaires a introduire (separes par des virgules)")
def planifier_saison(saison: int, theme: str, description: str, personnages: str):
    """Planifie une saison complete de 10 episodes avec arcs narratifs."""
    console.print(Panel(
        f"[bold]Planification — Saison {saison}[/bold]\n"
        f"Theme : {theme}\n"
        f"Description : {description or 'non fournie'}",
        title="Planificateur de saison",
        border_style="blue",
    ))

    # Charger les saisons précédentes pour continuité
    saisons_prec = []
    for num in config.liste_saisons():
        plan = config.charger_saison(num)
        if plan:
            saison_data = plan.get("saison", {})
            saisons_prec.append({
                "numero": saison_data.get("numero", num),
                "theme": saison_data.get("theme", "?"),
                "description": saison_data.get("description", ""),
            })

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
        )

        # Sauvegarder le plan (brouillon)
        chemin_json = config.SAISONS_DIR / f"saison_{saison:02d}.json"
        planificateur.sauvegarder(plan, chemin_json)
        console.print(f"  Plan sauvegarde : {chemin_json}")

        # Afficher le plan complet
        _afficher_plan_saison(plan)

        # ── Validation humaine du plan de saison (go/no-go) ──────────
        plan = _validation_plan_saison(
            plan=plan,
            chemin_json=chemin_json,
            planificateur=planificateur,
            saison=saison,
            theme=theme,
            description=description,
            personnages_list=personnages_list,
            saisons_prec=saisons_prec,
        )

        # Re-sauvegarder le plan valide (peut avoir ete modifie ou regenere)
        planificateur.sauvegarder(plan, chemin_json)

        # Sauvegarder en DB (versionnée — anciennes versions conservées)
        if _use_db():
            try:
                db_id = SaisonRepo.sauvegarder(plan)
                console.print(f"  Plan sauvegardé en PostgreSQL (id={db_id})")
            except Exception as e:
                console.print(f"  [yellow]DB indisponible pour plan : {e}[/yellow]")

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
def produire_saison(saison: int, episodes: str, dry_run: bool, auto: bool):
    """Produit les episodes d'une saison a partir du plan de saison."""
    plan = config.charger_saison(saison)
    if not plan:
        console.print(f"[red]Plan de saison {saison} introuvable. Lancez planifier-saison d'abord.[/red]")
        sys.exit(1)

    saison_data = plan["saison"]
    episodes_plan = saison_data["episodes"]

    # Filtrer les épisodes si spécifié
    if episodes:
        nums = [int(n.strip()) for n in episodes.split(",")]
        episodes_plan = [ep for ep in episodes_plan if ep["numero"] in nums]

    console.print(Panel(
        f"[bold]Production sérielle — Saison {saison}[/bold]\n"
        f"Theme : {saison_data['theme']}\n"
        f"Episodes : {len(episodes_plan)}\n"
        f"Mode : {'DRY RUN' if dry_run else 'PRODUCTION'}",
        title="Production de saison",
        border_style="blue",
    ))

    # ── Validation humaine du plan avant production (go/no-go) ───────
    if not auto:
        _afficher_plan_saison(plan)
        console.print(panel_validation([
            ("g", "Go — lancer la production"),
            ("a", "Abandonner"),
        ], titre="Go / No-Go — Plan de saison"))

        choix = console.input(f"  [{Palette.MIEL}]Votre choix :[/] ").strip().lower()
        if choix in ("a", "abandonner"):
            console.print(
                "[bold yellow]Production annulee. "
                "Modifiez le plan avec planifier-saison si nécessaire.[/bold yellow]"
            )
            return
        elif choix not in ("g", "go"):
            console.print("[yellow]  Choix non reconnu — lancement par défaut.[/yellow]")

    resultats = []
    for i, ep in enumerate(episodes_plan, 1):
        console.print(f"\n[bold]{'='*60}[/bold]")
        console.print(
            f"[bold cyan]Épisode {i}/{len(episodes_plan)} — "
            f"S{saison:02d}E{ep['numero']:02d} {ep['titre']} "
            f"[{ep.get('type', 'standard')}][/bold cyan]"
        )
        console.print(f"[bold]{'='*60}[/bold]")

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
            )
            resultats.append({"status": "ok", "episode": ep["titre"], "rapport": rapport})
        except Exception as e:
            logger.exception("Erreur sur l'episode %s", ep.get("titre", "?"))
            resultats.append({"status": "error", "episode": ep["titre"], "erreur": str(e)})

    # Rapport de saison
    console.print(f"\n[bold]{'='*60}[/bold]")
    console.print("[bold green]Rapport de saison[/bold green]")
    ok = sum(1 for r in resultats if r["status"] == "ok")
    erreurs = sum(1 for r in resultats if r["status"] == "error")
    console.print(f"  Reussis : {ok}/{len(episodes_plan)}")
    console.print(f"  Echecs  : {erreurs}/{len(episodes_plan)}")

    for r in resultats:
        status = "[green]OK[/green]" if r["status"] == "ok" else "[red]ERREUR[/red]"
        console.print(f"  {status} — {r['episode']}")
        if r["status"] == "error":
            console.print(f"    [red]{r['erreur']}[/red]")

    chemin_batch = config.LOGS_DIR / f"saison_{saison:02d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(chemin_batch, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2, default=str)
    console.print(f"\n  Rapport saison : {chemin_batch}")


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
    console.print("[green]Migration terminée ![/green]")


if __name__ == "__main__":
    cli()
