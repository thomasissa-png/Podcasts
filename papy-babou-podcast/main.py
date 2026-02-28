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

import config
from agents import (
    Scripteur, Reviewer, ProducteurAudio, SfxProvider, Monteur,
    Metadonnees, Publisher, CoverArt, Planificateur,
)

console = Console()

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


logger = logging.getLogger("papy-babou")


# ── Historique des épisodes ──────────────────────────────────────────────────

HISTORIQUE_PATH = config.HISTORIQUE_DIR / "historique_episodes.json"


def charger_historique() -> list[dict]:
    """Charge l'historique des épisodes produits."""
    if HISTORIQUE_PATH.exists():
        with open(HISTORIQUE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def sauvegarder_historique(historique: list[dict]) -> None:
    """Sauvegarde l'historique des épisodes."""
    with open(HISTORIQUE_PATH, "w", encoding="utf-8") as f:
        json.dump(historique, f, ensure_ascii=False, indent=2)


def ajouter_historique(rapport: dict, script: dict) -> None:
    """Ajoute un épisode à l'historique avec contexte sériel complet."""
    historique = charger_historique()
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
    }

    historique.append(entree)
    sauvegarder_historique(historique)


# ── Système de checkpoints ───────────────────────────────────────────────────


def sauvegarder_checkpoint(episode_id: str, etape: str, data: dict) -> Path:
    """Sauvegarde un checkpoint pour permettre la reprise sur échec.

    Args:
        episode_id: Identifiant de l'épisode (ex: S01E01).
        etape: Nom de l'étape en cours.
        data: Données à sauvegarder.

    Returns:
        Chemin du fichier checkpoint.
    """
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


def supprimer_checkpoint(episode_id: str) -> None:
    """Supprime le checkpoint après une production réussie."""
    chemin = config.CHECKPOINTS_DIR / f"{episode_id}_checkpoint.json"
    if chemin.exists():
        chemin.unlink()
        logger.info("Checkpoint supprimé : %s", chemin)


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


class ProductionAbandonnee(Exception):
    """Levée quand l'utilisateur abandonne la production."""


def _afficher_script(script: dict) -> None:
    """Affiche le script complet de manière lisible dans le terminal."""
    episode = script["episode"]

    console.print(Panel(
        f"[bold]{episode['titre']}[/bold] — "
        f"S{episode['saison']:02d}E{episode['numero']:02d}\n"
        f"Ambiance : {episode.get('ambiance', 'non définie')} | "
        f"Morale : {episode.get('morale', 'non définie')}",
        title="Script complet",
        border_style="cyan",
    ))

    for seg in episode["segments"]:
        nom = NOMS_PERSONNAGES.get(seg["personnage"], seg["personnage"])
        if seg["personnage"] == "sfx":
            mode = seg.get("mode", "insert")
            console.print(
                f"  [dim italic]  SFX ({mode}) : {seg['texte']} "
                f"({seg.get('duree_sfx_secondes', '?')}s)[/dim italic]"
            )
        elif seg["personnage"] == "narrateur":
            console.print(f"  [dim][Narrateur][/dim] {seg['texte']}")
        else:
            style = {
                "papy_babou": "bold yellow",
                "antoine": "bold blue",
                "noemie": "bold magenta",
            }.get(seg["personnage"], "")
            console.print(f"  [{style}][{nom}][/{style}] {seg['texte']}")

        pause = seg.get("pause_apres_ms", 0)
        if pause >= 1500:
            console.print(f"  [dim]  ... (pause {pause / 1000:.1f}s)[/dim]")

    console.print()


def _validation_script(
    script: dict,
    chemin_script: Path,
    morale: str = "",
    contexte_saison: dict | None = None,
    episode_plan: dict | None = None,
    type_episode: str = "standard",
) -> dict:
    """Point de validation humaine apres la review du script.

    Returns:
        Le script (potentiellement modifie).

    Raises:
        ProductionAbandonnee: Si l'utilisateur choisit d'abandonner.
    """
    _afficher_script(script)

    while True:
        console.print(Panel(
            "[bold](v)[/bold] Valider et continuer\n"
            "[bold](m)[/bold] Modifier le fichier JSON manuellement\n"
            "[bold](c)[/bold] Donner des corrections (relance le scripteur)\n"
            "[bold](a)[/bold] Abandonner la production",
            title="Validation du script",
            border_style="green",
        ))

        choix = console.input("[cyan]Votre choix :[/cyan] ").strip().lower()

        if choix in ("v", "valider"):
            console.print("[green]  Script valide par le producteur[/green]")
            return script

        elif choix in ("m", "modifier"):
            console.print(
                f"\n[yellow]  Modifiez le fichier puis revenez ici :[/yellow]"
                f"\n  [bold]{chemin_script}[/bold]\n"
            )
            console.input("[cyan]  Appuyez sur Entree quand c'est fait...[/cyan]")

            try:
                with open(chemin_script, "r", encoding="utf-8") as f:
                    script = json.load(f)
                console.print("[green]  Script recharge depuis le fichier[/green]")
                _afficher_script(script)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                console.print(f"[red]  Erreur au rechargement : {e}[/red]")
                console.print("[yellow]  Le script precedent est conserve.[/yellow]")

        elif choix in ("c", "corrections"):
            console.print(
                "\n[yellow]  Decrivez vos corrections "
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
                    "\n[cyan]  Corrections enregistrees "
                    "— relance du scripteur...[/cyan]"
                )
                scripteur = Scripteur()
                historique = charger_historique()
                script = scripteur.generer(
                    titre=script["episode"]["titre"],
                    resume="",
                    saison=script["episode"]["saison"],
                    numero=script["episode"]["numero"],
                    morale=morale,
                    corrections=lignes,
                    historique=historique,
                    contexte_saison=contexte_saison,
                    episode_plan=episode_plan,
                    type_episode=type_episode,
                )
                scripteur.sauvegarder(script, chemin_script)
                nb = scripteur.compter_mots(script)
                console.print(
                    f"[green]  Nouveau script genere ({nb} mots)[/green]"
                )
                _afficher_script(script)

        elif choix in ("a", "abandonner"):
            raise ProductionAbandonnee(
                "Production abandonnee par l'utilisateur."
            )

        else:
            console.print("[red]  Choix non reconnu. Tapez v, m, c ou a.[/red]")


def _validation_montage(
    chemin_hq: Path, chemin_preview: Path, duree_secondes: float
) -> None:
    """Point de validation humaine apres le montage audio.

    Raises:
        ProductionAbandonnee: Si l'utilisateur choisit d'abandonner.
    """
    console.print(Panel(
        f"Duree : [bold]{duree_secondes:.0f}s[/bold] "
        f"({duree_secondes / 60:.1f} min)\n"
        f"Fichier HQ  : [bold]{chemin_hq}[/bold]\n"
        f"Preview     : [bold]{chemin_preview}[/bold]\n\n"
        "[dim]Ecoutez le fichier preview avant de valider la publication.[/dim]",
        title="Ecoute du montage",
        border_style="cyan",
    ))

    while True:
        console.print(Panel(
            "[bold](v)[/bold] Valider et publier\n"
            "[bold](a)[/bold] Abandonner (l'audio est conserve, pas de publication)",
            title="Validation du montage",
            border_style="green",
        ))

        choix = console.input("[cyan]Votre choix :[/cyan] ").strip().lower()

        if choix in ("v", "valider"):
            console.print(
                "[green]  Montage valide — lancement de la publication[/green]"
            )
            return

        elif choix in ("a", "abandonner"):
            raise ProductionAbandonnee(
                "Production arretee apres montage. "
                f"L'audio est conserve dans : {chemin_hq}"
            )

        else:
            console.print("[red]  Choix non reconnu. Tapez v ou a.[/red]")


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
    episode_id = f"S{saison:02d}E{numero:02d}"
    rapport = checkpoint_data or {
        "episode_id": episode_id,
        "titre": titre,
        "dry_run": dry_run,
        "debut": datetime.now().isoformat(),
        "etapes": {},
    }

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
            # Enregistrer les personnages secondaires de la saison
            for perso_sec in contexte_saison.get("saison", {}).get("personnages_secondaires", []):
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

    mode_str = "DRY RUN (pas d'audio ni de publication)" if dry_run else "PRODUCTION"
    morale_str = morale or "non définie"
    type_str = f" [{type_episode}]" if type_episode != "standard" else ""
    console.print(
        Panel(
            f"[bold]Épisode {episode_id} — {titre}{type_str}[/bold]\n"
            f"Mode : {mode_str}\n"
            f"Morale : {morale_str}",
            title="Les Histoires de Papy Babou",
            border_style="blue",
        )
    )

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
        console.print("\n[bold cyan]Etape 1/8 — Generation du script[/bold cyan]")
        scripteur = Scripteur()
        corrections = None

        for iteration in range(1, max_iterations_review + 1):
            console.print(f"  Iteration {iteration}/{max_iterations_review}...")

            script = scripteur.generer(
                titre=titre, resume=resume, saison=saison, numero=numero,
                morale=morale, corrections=corrections, historique=historique,
                contexte_saison=contexte_saison, episode_plan=episode_plan,
                type_episode=type_episode,
            )

            chemin_script = config.SCRIPTS_DIR / f"{episode_id}_v{iteration}.json"
            scripteur.sauvegarder(script, chemin_script)
            nb_mots = scripteur.compter_mots(script)
            console.print(f"  Script v{iteration} : {nb_mots} mots, {len(script['episode']['segments'])} segments")

            # ── Reviewer ─────────────────────────────────────────────────────

            console.print(f"\n[bold cyan]Etape 2/8 — Relecture (iteration {iteration})[/bold cyan]")
            reviewer = Reviewer()
            resultat_review = reviewer.evaluer(script)
            score = resultat_review["review"]["score"]

            table = Table(title=f"Score de review : {score}/10")
            table.add_column("Critere", style="cyan")
            table.add_column("Score", justify="right")
            for critere, val in resultat_review["review"].get("details_score", {}).items():
                table.add_row(critere.replace("_", " ").title(), f"{val}/2")
            console.print(table)

            if resultat_review["review"]["corrections"]:
                console.print("[yellow]  Corrections :[/yellow]")
                for c in resultat_review["review"]["corrections"]:
                    console.print(f"    - {c}")

            if resultat_review["review"]["alertes"]:
                console.print("[red]  Alertes :[/red]")
                for a in resultat_review["review"]["alertes"]:
                    console.print(f"    ! {a}")

            if reviewer.est_valide(resultat_review):
                script = {"episode": resultat_review["episode"]}
                console.print(f"[green]  Script valide (score {score}/10)[/green]")
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

        duree_estimee = reviewer.estimer_duree(script)
        console.print(f"  Duree estimee : {duree_estimee:.1f} minutes")

        rapport["etapes"]["script"] = {
            "score_review": score,
            "nb_mots": scripteur.compter_mots(script),
            "duree_estimee_min": round(duree_estimee, 1),
            "chemin": str(chemin_valide),
        }

        # Checkpoint après script
        sauvegarder_checkpoint(episode_id, "audio", {
            "episode_id": episode_id, "titre": titre, "resume": resume,
            "saison": saison, "numero": numero, "morale": morale,
            "type_episode": type_episode,
            "dry_run": dry_run, "rapport": rapport,
        })

        # ── Validation humaine : script ──────────────────────────────────────

        if not auto:
            console.print(
                "\n[bold magenta]VALIDATION — Relisez le script avant "
                "la production audio[/bold magenta]"
            )
            script = _validation_script(
                script, chemin_valide, morale,
                contexte_saison=contexte_saison,
                episode_plan=episode_plan,
                type_episode=type_episode,
            )
            scripteur.sauvegarder(script, chemin_valide)
            duree_estimee = reviewer.estimer_duree(script)
            rapport["etapes"]["script"]["validation_humaine"] = True

    # ── Étape 3 : Production audio (voix) ─────────────────────────────────────

    if etape_idx <= 2:
        if dry_run:
            console.print("\n[bold yellow]Etape 3/8 — Production audio (SAUTEE — dry-run)[/bold yellow]")
            rapport["etapes"]["audio"] = {"status": "skipped (dry-run)"}
        else:
            console.print("\n[bold cyan]Etape 3/8 — Production audio (voix)[/bold cyan]")
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

            console.print(f"  {len(fichiers_audio)} segments voix generes")
            rapport["etapes"]["audio"] = {
                "nb_segments": len(fichiers_audio),
                "caracteres": dict(producteur.caracteres_utilises),
            }

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
            console.print(f"\n[bold yellow]Etape 4/8 — Bruitages SFX (SAUTEE — dry-run) [{nb_sfx} SFX][/bold yellow]")
            rapport["etapes"]["sfx"] = {"status": "skipped (dry-run)", "nb_sfx": nb_sfx}
        elif nb_sfx == 0:
            console.print("\n[bold cyan]Etape 4/8 — Bruitages SFX (aucun dans le script)[/bold cyan]")
            rapport["etapes"]["sfx"] = {"status": "no sfx segments", "nb_sfx": 0}
        else:
            console.print(f"\n[bold cyan]Etape 4/8 — Bruitages SFX ({nb_sfx} bruitages)[/bold cyan]")
            sfx_provider = SfxProvider()
            fichiers_sfx = sfx_provider.produire_sfx(script)

            console.print(f"  {len(fichiers_sfx)} bruitages generes/telecharges")
            for seg_id, source in sfx_provider.stats.items():
                console.print(f"    {seg_id} : {source}")

            rapport["etapes"]["sfx"] = {
                "nb_sfx": len(fichiers_sfx),
                "sources": dict(sfx_provider.stats),
            }

    # ── Étape 5 : Montage ─────────────────────────────────────────────────────

    if etape_idx <= 4:
        if dry_run:
            console.print("\n[bold yellow]Etape 5/8 — Montage (SAUTE — dry-run)[/bold yellow]")
            rapport["etapes"]["montage"] = {"status": "skipped (dry-run)"}
            reviewer = Reviewer()
            duree_estimee = reviewer.estimer_duree(script)
            duree_secondes = duree_estimee * 60
            taille_bytes = 0
            chemin_hq = None
        else:
            console.print("\n[bold cyan]Etape 5/8 — Montage[/bold cyan]")
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
            console.print(
                "\n[bold magenta]VALIDATION — Ecoutez l'episode avant "
                "publication[/bold magenta]"
            )
            _validation_montage(
                chemin_hq,
                preview_chemin,
                duree_secondes,
            )
            rapport["etapes"]["montage"]["validation_humaine"] = True

    # ── Étape 6 : Métadonnées ─────────────────────────────────────────────────

    if etape_idx <= 5:
        console.print("\n[bold cyan]Etape 6/8 — Generation des metadonnees[/bold cyan]")
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

    # ── Étape 7 : Publication ─────────────────────────────────────────────────

    if etape_idx <= 6:
        if dry_run:
            console.print("\n[bold yellow]Etape 7/8 — Publication (SAUTEE — dry-run)[/bold yellow]")
            rapport["etapes"]["publication"] = {"status": "skipped (dry-run)"}
        else:
            console.print("\n[bold cyan]Etape 7/8 — Publication[/bold cyan]")
            publisher = Publisher()
            rapport_pub = publisher.publier(meta, chemin_hq, taille_bytes)
            console.print(f"  URL audio : {rapport_pub['url_audio']}")
            if rapport_pub.get("transcript_url"):
                console.print(f"  Transcript : {rapport_pub['transcript_url']}")
            rapport["etapes"]["publication"] = rapport_pub

    # ── Étape 8 : Rapport final ───────────────────────────────────────────────

    console.print("\n[bold cyan]Etape 8/8 — Rapport final[/bold cyan]")
    rapport["fin"] = datetime.now().isoformat()

    # Calculer les métriques de coût
    rapport["couts"] = _calculer_couts(rapport)

    # Sauvegarder le rapport
    chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
    with open(chemin_rapport, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)

    # Ajouter à l'historique
    ajouter_historique(rapport, script)

    # Supprimer le checkpoint (production réussie)
    supprimer_checkpoint(episode_id)

    # Afficher le résumé et les coûts
    couts = rapport["couts"]
    cout_total_str = f"${couts['total_estime']:.3f}" if not dry_run else "N/A (dry-run)"
    console.print(
        Panel(
            f"[bold green]Production terminee ![/bold green]\n\n"
            f"Episode : {episode_id} — {titre}\n"
            f"Score review : {score}/10\n"
            f"Morale : {script['episode'].get('morale', 'N/A')}\n"
            f"Cout estime : {cout_total_str}\n"
            f"Rapport : {chemin_rapport}",
            title="Resume",
            border_style="green",
        )
    )

    return rapport


# ── CLI Click ─────────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Les Histoires de Papy Babou — Systeme de production automatisee."""
    configurer_logging()
    if ctx.invoked_subcommand is None:
        ctx.invoke(interactif)


@cli.command()
@click.option("--episode", "-e", required=True, help="Titre de l'episode")
@click.option("--saison", "-s", type=int, required=True, help="Numero de saison")
@click.option("--numero", "-n", type=int, required=True, help="Numero d'episode")
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
        console.print(f"\n[bold yellow]Production arretee : {e}[/bold yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur dans le pipeline de production")
        sys.exit(1)


@cli.command()
def interactif():
    """Mode interactif — saisie guidee des parametres avec validation humaine."""
    console.print(
        Panel(
            "[bold]Bienvenue dans le studio de production[/bold]\n"
            "Les Histoires de Papy Babou\n\n"
            "[dim]Vous serez invite a valider le script et le montage "
            "avant publication.[/dim]",
            border_style="blue",
        )
    )

    titre = console.input("[cyan]Titre de l'episode :[/cyan] ")
    try:
        saison = int(console.input("[cyan]Numero de saison :[/cyan] "))
        numero = int(console.input("[cyan]Numero d'episode :[/cyan] "))
    except ValueError:
        console.print("[red]Les numeros de saison et d'episode doivent etre des entiers.[/red]")
        sys.exit(1)
    resume = console.input("[cyan]Resume de l'histoire biblique :[/cyan] ")
    morale = console.input("[cyan]Lecon de vie / morale (optionnel) :[/cyan] ")

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
        console.print(f"\n[bold yellow]Production arretee : {e}[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur dans le pipeline de production")
        sys.exit(1)


@cli.command()
@click.option("--fichier", "-f", required=True, type=click.Path(exists=True),
              help="Fichier JSON de planning (liste d'episodes)")
@click.option("--dry-run", is_flag=True, help="Tester sans audio ni publication")
@click.option("--auto", is_flag=True, default=True, help="Mode automatique (defaut: oui)")
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
        console.print("[red]Le fichier doit contenir une liste d'episodes.[/red]")
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
        console.print(f"[bold cyan]Episode {i}/{len(planning)} — {ep.get('titre', '?')}[/bold cyan]")
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
        console.print(f"\n[bold yellow]Production arretee : {e}[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur lors de la reprise")
        sys.exit(1)


@cli.command("planifier-saison")
@click.option("--saison", "-s", type=int, required=True, help="Numero de la saison")
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
        )

        # Sauvegarder le plan
        chemin_json = config.SAISONS_DIR / f"saison_{saison:02d}.json"
        planificateur.sauvegarder(plan, chemin_json)
        console.print(f"  Plan sauvegarde : {chemin_json}")

        # Exporter en CSV et Markdown
        chemin_csv = config.SAISONS_DIR / f"saison_{saison:02d}.csv"
        chemin_md = config.SAISONS_DIR / f"saison_{saison:02d}.md"
        planificateur.exporter_csv(plan, chemin_csv)
        planificateur.exporter_markdown(plan, chemin_md)
        console.print(f"  Export CSV : {chemin_csv}")
        console.print(f"  Export Markdown : {chemin_md}")

        # Afficher le résumé
        saison_data = plan["saison"]
        table = Table(title=f"Saison {saison} — {saison_data['theme']}")
        table.add_column("Ep", style="cyan", justify="right")
        table.add_column("Titre", style="white")
        table.add_column("Type", style="dim")
        table.add_column("Ambiance", style="dim")
        table.add_column("Morale", style="dim")

        for ep in saison_data["episodes"]:
            table.add_row(
                str(ep["numero"]),
                ep["titre"],
                ep.get("type", "standard"),
                ep.get("ambiance", "?"),
                ep["morale"][:40],
            )
        console.print(table)

        # Afficher les arcs
        arcs = saison_data.get("arcs_personnages", {})
        if arcs:
            console.print("\n[bold]  Arcs de personnages :[/bold]")
            for perso, arc in arcs.items():
                nom = perso.replace("_", " ").title()
                console.print(f"    {nom} : {arc.get('depart', '')} -> {arc.get('arrivee', '')}")

        # Afficher les personnages secondaires
        secondaires = saison_data.get("personnages_secondaires", [])
        if secondaires:
            console.print("\n[bold]  Personnages secondaires :[/bold]")
            for p in secondaires:
                console.print(
                    f"    {p.get('nom_complet', '?')} "
                    f"(episode {p.get('apparait_episode', '?')}) : "
                    f"{p.get('description', '')[:60]}"
                )

    except Exception as e:
        console.print(f"[bold red]Erreur : {e}[/bold red]")
        logger.exception("Erreur lors de la planification")
        sys.exit(1)


@cli.command("produire-saison")
@click.option("--saison", "-s", type=int, required=True, help="Numero de la saison")
@click.option("--episodes", "-e", default="", help="Episodes specifiques (ex: '1,3,5' — vide = tous)")
@click.option("--dry-run", is_flag=True, help="Tester sans audio ni publication")
@click.option("--auto", is_flag=True, default=True, help="Mode automatique (defaut: oui)")
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

    resultats = []
    for i, ep in enumerate(episodes_plan, 1):
        console.print(f"\n[bold]{'='*60}[/bold]")
        console.print(
            f"[bold cyan]Episode {i}/{len(episodes_plan)} — "
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
    """Affiche le dashboard de suivi des episodes produits."""
    historique = charger_historique()

    if not historique:
        console.print("[yellow]Aucun episode produit pour le moment.[/yellow]")
        return

    # Filtrer par saison si demandé
    if saison > 0:
        prefix = f"S{saison:02d}"
        historique = [ep for ep in historique if ep.get("episode_id", "").startswith(prefix)]
        if not historique:
            console.print(f"[yellow]Aucun episode produit pour la saison {saison}.[/yellow]")
            return

    # Tableau des épisodes
    titre_table = f"Dashboard — Saison {saison}" if saison > 0 else "Dashboard — Tous les episodes"
    table = Table(title=titre_table)
    table.add_column("Episode", style="cyan")
    table.add_column("Titre", style="white")
    table.add_column("Type", style="dim")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Morale", style="dim")
    table.add_column("Date", style="dim")

    for ep in historique:
        score = ep.get("score_review", "?")
        score_style = "green" if isinstance(score, (int, float)) and score >= 7 else "yellow"
        table.add_row(
            ep.get("episode_id", "?"),
            ep.get("titre", "?"),
            ep.get("type_episode", "standard"),
            f"[{score_style}]{score}/10[/{score_style}]",
            ep.get("morale", "")[:40],
            ep.get("date_production", "")[:10],
        )

    console.print(table)

    # Statistiques globales
    scores = [ep.get("score_review", 0) for ep in historique if isinstance(ep.get("score_review"), (int, float))]
    if scores:
        console.print(f"\n  Episodes produits : {len(historique)}")
        console.print(f"  Score moyen : {sum(scores)/len(scores):.1f}/10")
        console.print(f"  Meilleur score : {max(scores)}/10")
        console.print(f"  Plus bas score : {min(scores)}/10")

    # Personnages utilisés
    all_personnages: dict[str, int] = {}
    for ep in historique:
        for p in ep.get("personnages_presents", []):
            all_personnages[p] = all_personnages.get(p, 0) + 1
    if all_personnages:
        console.print("\n[bold]  Personnages :[/bold]")
        for p, count in sorted(all_personnages.items(), key=lambda x: -x[1]):
            console.print(f"    {p} : {count} episode(s)")

    # Vue saison si un plan existe
    if saison > 0:
        plan = config.charger_saison(saison)
        if plan:
            saison_data = plan.get("saison", {})
            episodes_plan = saison_data.get("episodes", [])
            episodes_produits = {ep.get("episode_id") for ep in historique}
            console.print(f"\n[bold]  Progression de la saison {saison} :[/bold]")
            for ep in episodes_plan:
                ep_id = f"S{saison:02d}E{ep['numero']:02d}"
                status = "[green]PRODUIT[/green]" if ep_id in episodes_produits else "[yellow]A FAIRE[/yellow]"
                console.print(f"    E{ep['numero']:02d} {ep['titre'][:40]} — {status}")

    # Saisons disponibles
    saisons_dispo = config.liste_saisons()
    if saisons_dispo:
        console.print(f"\n[bold]  Saisons planifiees :[/bold] {', '.join(str(s) for s in saisons_dispo)}")

    # Coûts détaillés (depuis les rapports)
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
        console.print("\n[bold]  Couts cumules :[/bold]")
        if total_chars > 0:
            console.print(f"  Total caracteres ElevenLabs : {total_chars:,}")
        for service, cout in sorted(cout_par_service.items()):
            console.print(f"  {service} : ${cout:.4f}")
        if cout_total_global > 0:
            console.print(f"  [bold]TOTAL estime : ${cout_total_global:.4f}[/bold]")

    # Checkpoints en cours
    checkpoints = list(config.CHECKPOINTS_DIR.glob("*_checkpoint.json"))
    if checkpoints:
        console.print(f"\n[yellow]  Checkpoints en attente : {len(checkpoints)}[/yellow]")
        for cp_path in checkpoints:
            try:
                with open(cp_path, "r", encoding="utf-8") as f:
                    cp = json.load(f)
                console.print(f"    - {cp['episode_id']} (etape: {cp['etape']}, {cp['timestamp']})")
            except (json.JSONDecodeError, FileNotFoundError):
                console.print(f"    - {cp_path.name} (illisible)")


if __name__ == "__main__":
    cli()
