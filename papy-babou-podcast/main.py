"""Orchestrateur principal — Pipeline de production du podcast Papy Babou.

Usage:
    python main.py produire -e "Le buisson ardent" -s 1 -n 2 -r "..." -m "La confiance en Dieu"
    python main.py produire -e "..." -s 1 -n 1 -r "..." --dry-run
    python main.py produire -e "..." -s 1 -n 1 -r "..." --auto  (sans validation humaine)
    python main.py interactif
    python main.py batch -f planning.json
    python main.py dashboard
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
    """Ajoute un épisode à l'historique pour la continuité inter-épisodes."""
    historique = charger_historique()
    episode = script.get("episode", {})
    historique.append({
        "episode_id": rapport.get("episode_id", ""),
        "titre": rapport.get("titre", ""),
        "morale": episode.get("morale", ""),
        "resume_court": episode.get("titre", ""),
        "date_production": rapport.get("debut", ""),
        "score_review": rapport.get("etapes", {}).get("script", {}).get("score_review", 0),
    })
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


def _validation_script(script: dict, chemin_script: Path, morale: str = "") -> dict:
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
    console.print(
        Panel(
            f"[bold]Épisode {episode_id} — {titre}[/bold]\n"
            f"Mode : {mode_str}\n"
            f"Morale : {morale_str}",
            title="Les Histoires de Papy Babou",
            border_style="blue",
        )
    )

    etapes = ["script", "review", "audio", "sfx", "montage", "metadonnees", "publication", "rapport"]
    etape_idx = etapes.index(etape_depart) if etape_depart in etapes else 0

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
            "dry_run": dry_run, "rapport": rapport,
        })

        # ── Validation humaine : script ──────────────────────────────────────

        if not auto:
            console.print(
                "\n[bold magenta]VALIDATION — Relisez le script avant "
                "la production audio[/bold magenta]"
            )
            script = _validation_script(script, chemin_valide, morale)
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
                "dry_run": dry_run, "rapport": rapport,
            })

    # ── Validation humaine : montage ─────────────────────────────────────────

    if not auto and not dry_run and chemin_hq:
        console.print(
            "\n[bold magenta]VALIDATION — Ecoutez l'episode avant "
            "publication[/bold magenta]"
        )
        _validation_montage(
            chemin_hq,
            resultat_montage["chemin_preview"],
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

    # Sauvegarder le rapport
    chemin_rapport = config.LOGS_DIR / f"{episode_id}_rapport.json"
    with open(chemin_rapport, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)

    # Ajouter à l'historique
    ajouter_historique(rapport, script)

    # Supprimer le checkpoint (production réussie)
    supprimer_checkpoint(episode_id)

    # Afficher le résumé
    console.print(
        Panel(
            f"[bold green]Production terminee ![/bold green]\n\n"
            f"Episode : {episode_id} — {titre}\n"
            f"Score review : {score}/10\n"
            f"Morale : {script['episode'].get('morale', 'N/A')}\n"
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
    saison = int(console.input("[cyan]Numero de saison :[/cyan] "))
    numero = int(console.input("[cyan]Numero d'episode :[/cyan] "))
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
        )
    except ProductionAbandonnee as e:
        console.print(f"\n[bold yellow]Production arretee : {e}[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Erreur fatale : {e}[/bold red]")
        logger.exception("Erreur lors de la reprise")
        sys.exit(1)


@cli.command()
def dashboard():
    """Affiche le dashboard de suivi des episodes produits."""
    historique = charger_historique()

    if not historique:
        console.print("[yellow]Aucun episode produit pour le moment.[/yellow]")
        return

    # Tableau des épisodes
    table = Table(title="Dashboard — Episodes produits")
    table.add_column("Episode", style="cyan")
    table.add_column("Titre", style="white")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Morale", style="dim")
    table.add_column("Date", style="dim")

    for ep in historique:
        score = ep.get("score_review", "?")
        score_style = "green" if isinstance(score, (int, float)) and score >= 7 else "yellow"
        table.add_row(
            ep.get("episode_id", "?"),
            ep.get("titre", "?"),
            f"[{score_style}]{score}/10[/{score_style}]",
            ep.get("morale", "")[:50],
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

    # Coûts ElevenLabs (depuis les rapports)
    total_chars = 0
    rapports_dir = config.LOGS_DIR
    for rapport_path in rapports_dir.glob("S*_rapport.json"):
        try:
            with open(rapport_path, "r", encoding="utf-8") as f:
                rapport = json.load(f)
            chars = rapport.get("etapes", {}).get("audio", {}).get("caracteres", {})
            if isinstance(chars, dict):
                total_chars += sum(chars.values())
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    if total_chars > 0:
        console.print(f"\n  Total caracteres ElevenLabs : {total_chars:,}")
        cout_estime = total_chars * 0.000018  # ~$0.018 par 1000 caractères
        console.print(f"  Cout estime ElevenLabs : ~${cout_estime:.2f}")

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
