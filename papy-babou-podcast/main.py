"""Orchestrateur principal — Pipeline de production du podcast Papy Babou.

Usage:
    python main.py --episode "Le buisson ardent" --saison 1 --numero 2 --resume "..."
    python main.py --episode "..." --saison 1 --numero 1 --resume "..." --dry-run
    python main.py --interactive
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
from agents import Scripteur, Reviewer, ProducteurAudio, Monteur, Metadonnees, Publisher

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


# ── Pipeline de production ────────────────────────────────────────────────────


def pipeline(
    titre: str,
    resume: str,
    saison: int,
    numero: int,
    dry_run: bool = False,
    max_iterations_review: int = 3,
) -> dict:
    """Exécute le pipeline complet de production d'un épisode.

    Args:
        titre: Titre de l'épisode.
        resume: Résumé de l'histoire biblique.
        saison: Numéro de saison.
        numero: Numéro d'épisode.
        dry_run: Si True, pas de génération audio ni de publication.
        max_iterations_review: Nombre max de boucles scripteur-reviewer.

    Returns:
        Rapport de production complet.
    """
    episode_id = f"S{saison:02d}E{numero:02d}"
    rapport = {
        "episode_id": episode_id,
        "titre": titre,
        "dry_run": dry_run,
        "debut": datetime.now().isoformat(),
        "etapes": {},
    }

    console.print(
        Panel(
            f"[bold]Épisode {episode_id} — {titre}[/bold]\n"
            f"Mode : {'DRY RUN (pas d\\'audio ni de publication)' if dry_run else 'PRODUCTION'}",
            title="🎙️ Les Histoires de Papy Babou",
            border_style="blue",
        )
    )

    # ── Étape 1 : Scripteur ───────────────────────────────────────────────────

    console.print("\n[bold cyan]▶ Étape 1/7 — Génération du script[/bold cyan]")
    scripteur = Scripteur()
    corrections = None
    script = None
    score = 0

    for iteration in range(1, max_iterations_review + 1):
        console.print(f"  Itération {iteration}/{max_iterations_review}...")

        if dry_run and iteration == 1:
            # En dry-run, charger un script existant ou générer via API
            script = scripteur.generer(
                titre=titre, resume=resume, saison=saison, numero=numero,
                corrections=corrections,
            )
        else:
            script = scripteur.generer(
                titre=titre, resume=resume, saison=saison, numero=numero,
                corrections=corrections,
            )

        # Sauvegarder le script brut
        chemin_script = config.SCRIPTS_DIR / f"{episode_id}_v{iteration}.json"
        scripteur.sauvegarder(script, chemin_script)
        nb_mots = scripteur.compter_mots(script)
        console.print(f"  Script v{iteration} : {nb_mots} mots, {len(script['episode']['segments'])} segments")

        # ── Étape 2 : Reviewer ────────────────────────────────────────────────

        console.print(f"\n[bold cyan]▶ Étape 2/7 — Relecture (itération {iteration})[/bold cyan]")
        reviewer = Reviewer()
        resultat_review = reviewer.evaluer(script)
        score = resultat_review["review"]["score"]

        # Afficher le rapport de review
        table = Table(title=f"Score de review : {score}/10")
        table.add_column("Critère", style="cyan")
        table.add_column("Score", justify="right")
        for critere, val in resultat_review["review"].get("details_score", {}).items():
            table.add_row(critere.replace("_", " ").title(), f"{val}/2")
        console.print(table)

        if resultat_review["review"]["corrections"]:
            console.print("[yellow]  Corrections :[/yellow]")
            for c in resultat_review["review"]["corrections"]:
                console.print(f"    • {c}")

        if resultat_review["review"]["alertes"]:
            console.print("[red]  Alertes :[/red]")
            for a in resultat_review["review"]["alertes"]:
                console.print(f"    ⚠ {a}")

        if reviewer.est_valide(resultat_review):
            script = {"episode": resultat_review["episode"]}
            console.print(f"[green]  ✓ Script validé (score {score}/10)[/green]")
            break

        console.print(f"[yellow]  Score insuffisant ({score}/10 < 7) — relance du scripteur[/yellow]")
        corrections = reviewer.extraire_corrections(resultat_review)

    else:
        console.print(
            f"[red]  ⚠ Score final : {score}/10 après {max_iterations_review} itérations. "
            "Poursuite avec le meilleur script disponible.[/red]"
        )
        script = {"episode": resultat_review["episode"]}

    # Sauvegarder le script validé
    chemin_valide = config.SCRIPTS_DIR / f"{episode_id}_valide.json"
    scripteur.sauvegarder(script, chemin_valide)

    # Estimer la durée
    duree_estimee = reviewer.estimer_duree(script)
    console.print(f"  Durée estimée : {duree_estimee:.1f} minutes")

    rapport["etapes"]["script"] = {
        "score_review": score,
        "nb_mots": scripteur.compter_mots(script),
        "duree_estimee_min": round(duree_estimee, 1),
        "chemin": str(chemin_valide),
    }

    # ── Étape 3 : Production audio ────────────────────────────────────────────

    if dry_run:
        console.print("\n[bold yellow]▶ Étape 3/7 — Production audio (SAUTÉE — dry-run)[/bold yellow]")
        rapport["etapes"]["audio"] = {"status": "skipped (dry-run)"}
    else:
        console.print("\n[bold cyan]▶ Étape 3/7 — Production audio[/bold cyan]")
        producteur = ProducteurAudio()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Génération des segments audio...",
                total=len(script["episode"]["segments"]),
            )
            fichiers_audio = producteur.produire_episode(script)
            progress.update(task, completed=len(script["episode"]["segments"]))

        console.print(f"  {len(fichiers_audio)} segments audio générés")
        rapport["etapes"]["audio"] = {
            "nb_segments": len(fichiers_audio),
            "caracteres": dict(producteur.caracteres_utilises),
        }

    # ── Étape 4 : Montage ─────────────────────────────────────────────────────

    if dry_run:
        console.print("\n[bold yellow]▶ Étape 4/7 — Montage (SAUTÉ — dry-run)[/bold yellow]")
        rapport["etapes"]["montage"] = {"status": "skipped (dry-run)"}
        duree_secondes = duree_estimee * 60
        taille_bytes = 0
        chemin_hq = None
    else:
        console.print("\n[bold cyan]▶ Étape 4/7 — Montage[/bold cyan]")
        monteur = Monteur()
        resultat_montage = monteur.assembler(script)

        duree_secondes = resultat_montage["duree_secondes"]
        taille_bytes = resultat_montage["taille_bytes"]
        chemin_hq = resultat_montage["chemin_hq"]

        console.print(f"  Épisode assemblé : {duree_secondes:.0f}s, {taille_bytes / 1024 / 1024:.1f} MB")
        rapport["etapes"]["montage"] = {
            "duree_secondes": duree_secondes,
            "taille_mb": round(taille_bytes / 1024 / 1024, 1),
            "chemin_hq": str(chemin_hq),
            "chemin_preview": str(resultat_montage["chemin_preview"]),
        }

    # ── Étape 5 : Métadonnées ─────────────────────────────────────────────────

    console.print("\n[bold cyan]▶ Étape 5/7 — Génération des métadonnées[/bold cyan]")
    metadonnees = Metadonnees()

    if dry_run:
        meta = metadonnees.generer_dry_run(script)
    else:
        meta = metadonnees.generer(script, duree_secondes)

    chemin_meta = config.SCRIPTS_DIR / f"{episode_id}_meta.json"
    metadonnees.sauvegarder(meta, chemin_meta)
    console.print(f"  Titre : {meta['titre']}")
    console.print(f"  Description : {meta['description_courte']}")

    rapport["etapes"]["metadonnees"] = {
        "titre": meta["titre"],
        "chemin": str(chemin_meta),
    }

    # ── Étape 6 : Publication ─────────────────────────────────────────────────

    if dry_run:
        console.print("\n[bold yellow]▶ Étape 6/7 — Publication (SAUTÉE — dry-run)[/bold yellow]")
        rapport["etapes"]["publication"] = {"status": "skipped (dry-run)"}
    else:
        console.print("\n[bold cyan]▶ Étape 6/7 — Publication[/bold cyan]")
        publisher = Publisher()
        rapport_pub = publisher.publier(meta, chemin_hq, taille_bytes)
        console.print(f"  URL audio : {rapport_pub['url_audio']}")
        rapport["etapes"]["publication"] = rapport_pub

    # ── Étape 7 : Rapport final ───────────────────────────────────────────────

    console.print("\n[bold cyan]▶ Étape 7/7 — Rapport final[/bold cyan]")
    rapport["fin"] = datetime.now().isoformat()

    # Sauvegarder le rapport
    chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
    with open(chemin_rapport, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)

    # Afficher le résumé
    console.print(
        Panel(
            f"[bold green]Production terminée ![/bold green]\n\n"
            f"Épisode : {episode_id} — {titre}\n"
            f"Score review : {score}/10\n"
            f"Durée estimée : {duree_estimee:.1f} min\n"
            f"Rapport : {chemin_rapport}",
            title="✅ Résumé",
            border_style="green",
        )
    )

    return rapport


# ── CLI Click ─────────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Les Histoires de Papy Babou — Système de production automatisée."""
    configurer_logging()
    if ctx.invoked_subcommand is None:
        ctx.invoke(interactif)


@cli.command()
@click.option("--episode", "-e", required=True, help="Titre de l'épisode")
@click.option("--saison", "-s", type=int, required=True, help="Numéro de saison")
@click.option("--numero", "-n", type=int, required=True, help="Numéro d'épisode")
@click.option("--resume", "-r", required=True, help="Résumé de l'histoire biblique")
@click.option("--dry-run", is_flag=True, help="Tester sans audio ni publication")
def produire(episode: str, saison: int, numero: int, resume: str, dry_run: bool):
    """Produit un épisode complet du podcast."""
    try:
        pipeline(
            titre=episode,
            resume=resume,
            saison=saison,
            numero=numero,
            dry_run=dry_run,
        )
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur dans le pipeline de production")
        sys.exit(1)


@cli.command()
def interactif():
    """Mode interactif — saisie guidée des paramètres."""
    console.print(
        Panel(
            "[bold]Bienvenue dans le studio de production[/bold]\n"
            "Les Histoires de Papy Babou",
            border_style="blue",
        )
    )

    titre = console.input("[cyan]Titre de l'épisode :[/cyan] ")
    saison = int(console.input("[cyan]Numéro de saison :[/cyan] "))
    numero = int(console.input("[cyan]Numéro d'épisode :[/cyan] "))
    resume = console.input("[cyan]Résumé de l'histoire biblique :[/cyan] ")

    dry_run_str = console.input("[cyan]Mode dry-run ? (o/n) :[/cyan] ").strip().lower()
    dry_run = dry_run_str in ("o", "oui", "y", "yes")

    console.print()
    try:
        pipeline(
            titre=titre,
            resume=resume,
            saison=saison,
            numero=numero,
            dry_run=dry_run,
        )
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur dans le pipeline de production")
        sys.exit(1)


if __name__ == "__main__":
    cli()
