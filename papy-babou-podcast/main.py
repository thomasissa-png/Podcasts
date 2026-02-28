"""Orchestrateur principal — Pipeline de production du podcast Papy Babou.

Usage:
    python main.py produire -e "Le buisson ardent" -s 1 -n 2 -r "..."
    python main.py produire -e "..." -s 1 -n 1 -r "..." --dry-run
    python main.py produire -e "..." -s 1 -n 1 -r "..." --auto  (sans validation humaine)
    python main.py interactif
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
from agents import Scripteur, Reviewer, ProducteurAudio, SfxProvider, Monteur, Metadonnees, Publisher

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
        f"S{episode['saison']:02d}E{episode['numero']:02d}",
        title="Script complet",
        border_style="cyan",
    ))

    for seg in episode["segments"]:
        nom = NOMS_PERSONNAGES.get(seg["personnage"], seg["personnage"])
        if seg["personnage"] == "sfx":
            console.print(
                f"  [dim italic]  SFX : {seg['texte']} "
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


def _validation_script(script: dict, chemin_script: Path) -> dict:
    """Point de validation humaine apres la review du script.

    Affiche le script, puis propose :
      (v) Valider - continuer le pipeline
      (m) Modifier - ouvrir le fichier JSON, recharger apres modification
      (c) Corrections - saisir des instructions, relancer le scripteur
      (a) Abandonner - arreter la production

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
                script = scripteur.generer(
                    titre=script["episode"]["titre"],
                    resume="",
                    saison=script["episode"]["saison"],
                    numero=script["episode"]["numero"],
                    corrections=lignes,
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
    dry_run: bool = False,
    auto: bool = False,
    max_iterations_review: int = 3,
) -> dict:
    """Execute le pipeline complet de production d'un episode.

    Args:
        titre: Titre de l'episode.
        resume: Resume de l'histoire biblique.
        saison: Numero de saison.
        numero: Numero d'episode.
        dry_run: Si True, pas de generation audio ni de publication.
        auto: Si True, pas de validation humaine (pipeline 100% automatique).
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

    console.print("\n[bold cyan]▶ Étape 1/8 — Génération du script[/bold cyan]")
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

        console.print(f"\n[bold cyan]▶ Étape 2/8 — Relecture (itération {iteration})[/bold cyan]")
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

    # ── Validation humaine : script ──────────────────────────────────────────

    if not auto:
        console.print(
            "\n[bold magenta]■ VALIDATION — Relisez le script avant "
            "la production audio[/bold magenta]"
        )
        script = _validation_script(script, chemin_valide)
        # Re-sauvegarder au cas ou le script a ete modifie
        scripteur.sauvegarder(script, chemin_valide)
        duree_estimee = reviewer.estimer_duree(script)
        rapport["etapes"]["script"]["validation_humaine"] = True

    # ── Étape 3 : Production audio (voix) ─────────────────────────────────────

    if dry_run:
        console.print("\n[bold yellow]▶ Étape 3/8 — Production audio (SAUTÉE — dry-run)[/bold yellow]")
        rapport["etapes"]["audio"] = {"status": "skipped (dry-run)"}
    else:
        console.print("\n[bold cyan]▶ Étape 3/8 — Production audio (voix)[/bold cyan]")
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
                "Génération des segments audio...",
                total=len(segments_voix),
            )
            fichiers_audio = producteur.produire_episode(script)
            progress.update(task, completed=len(segments_voix))

        console.print(f"  {len(fichiers_audio)} segments voix générés")
        rapport["etapes"]["audio"] = {
            "nb_segments": len(fichiers_audio),
            "caracteres": dict(producteur.caracteres_utilises),
        }

    # ── Étape 4 : Bruitages (SFX) ─────────────────────────────────────────────

    nb_sfx = len([s for s in script["episode"]["segments"] if s["personnage"] == "sfx"])

    if dry_run:
        console.print(f"\n[bold yellow]▶ Étape 4/8 — Bruitages SFX (SAUTÉE — dry-run) [{nb_sfx} SFX dans le script][/bold yellow]")
        rapport["etapes"]["sfx"] = {"status": "skipped (dry-run)", "nb_sfx": nb_sfx}
    elif nb_sfx == 0:
        console.print("\n[bold cyan]▶ Étape 4/8 — Bruitages SFX (aucun dans le script)[/bold cyan]")
        rapport["etapes"]["sfx"] = {"status": "no sfx segments", "nb_sfx": 0}
    else:
        console.print(f"\n[bold cyan]▶ Étape 4/8 — Bruitages SFX ({nb_sfx} bruitages)[/bold cyan]")
        sfx_provider = SfxProvider()
        fichiers_sfx = sfx_provider.produire_sfx(script)

        console.print(f"  {len(fichiers_sfx)} bruitages générés/téléchargés")
        for seg_id, source in sfx_provider.stats.items():
            console.print(f"    {seg_id} : {source}")

        rapport["etapes"]["sfx"] = {
            "nb_sfx": len(fichiers_sfx),
            "sources": dict(sfx_provider.stats),
        }

    # ── Étape 5 : Montage ─────────────────────────────────────────────────────

    if dry_run:
        console.print("\n[bold yellow]▶ Étape 5/8 — Montage (SAUTÉ — dry-run)[/bold yellow]")
        rapport["etapes"]["montage"] = {"status": "skipped (dry-run)"}
        duree_secondes = duree_estimee * 60
        taille_bytes = 0
        chemin_hq = None
    else:
        console.print("\n[bold cyan]▶ Étape 5/8 — Montage[/bold cyan]")
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

    # ── Validation humaine : montage ─────────────────────────────────────────

    if not auto and not dry_run and chemin_hq:
        console.print(
            "\n[bold magenta]■ VALIDATION — Ecoutez l'episode avant "
            "publication[/bold magenta]"
        )
        _validation_montage(
            chemin_hq,
            resultat_montage["chemin_preview"],
            duree_secondes,
        )
        rapport["etapes"]["montage"]["validation_humaine"] = True

    # ── Étape 6 : Métadonnées ─────────────────────────────────────────────────

    console.print("\n[bold cyan]▶ Étape 6/8 — Génération des métadonnées[/bold cyan]")
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

    # ── Étape 7 : Publication ─────────────────────────────────────────────────

    if dry_run:
        console.print("\n[bold yellow]▶ Étape 7/8 — Publication (SAUTÉE — dry-run)[/bold yellow]")
        rapport["etapes"]["publication"] = {"status": "skipped (dry-run)"}
    else:
        console.print("\n[bold cyan]▶ Étape 7/8 — Publication[/bold cyan]")
        publisher = Publisher()
        rapport_pub = publisher.publier(meta, chemin_hq, taille_bytes)
        console.print(f"  URL audio : {rapport_pub['url_audio']}")
        rapport["etapes"]["publication"] = rapport_pub

    # ── Étape 8 : Rapport final ───────────────────────────────────────────────

    console.print("\n[bold cyan]▶ Étape 8/8 — Rapport final[/bold cyan]")
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
@click.option("--auto", is_flag=True, help="Mode automatique sans validation humaine")
def produire(episode: str, saison: int, numero: int, resume: str, dry_run: bool, auto: bool):
    """Produit un episode complet du podcast."""
    try:
        pipeline(
            titre=episode,
            resume=resume,
            saison=saison,
            numero=numero,
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
    saison = int(console.input("[cyan]Numero de saison :[/cyan] "))
    numero = int(console.input("[cyan]Numero d'episode :[/cyan] "))
    resume = console.input("[cyan]Resume de l'histoire biblique :[/cyan] ")

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
            auto=False,
        )
    except ProductionAbandonnee as e:
        console.print(f"\n[bold yellow]Production arretee : {e}[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur dans le pipeline de production")
        sys.exit(1)


if __name__ == "__main__":
    cli()
