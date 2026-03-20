"""Design System — Identité visuelle du podcast Les Histoires de Papy Babou.

Système de design flat + chaleureux pour CLI Rich, cover art, et assets web.
Cible : enfants 6-10 ans + parents. Univers : contes bibliques, Provence, chaleur familiale.

Usage:
    from theme import Theme, Icons, styled_panel, styled_table, banner, ...
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.style import Style
from rich.theme import Theme as RichTheme


# ══════════════════════════════════════════════════════════════════════════════
# PALETTE DE COULEURS — Flat Design Papy Babou
# Inspirée : Provence, aquarelle, livres pour enfants, cheminée
# ══════════════════════════════════════════════════════════════════════════════

class Palette:
    """Tokens couleur de la charte graphique — style cartoon aventure."""

    # ── Couleurs primaires ───────────────────────────────────────────────
    OCRE          = "#E8A020"   # Doré vif — couleur signature Papy Babou
    BLEU_CIEL     = "#4A9FE5"   # Bleu ciel vif — Antoine
    ROSE_POUDRE   = "#E895A8"   # Rose tendre — Noémie
    VERT_OLIVE    = "#5DBD72"   # Vert prairie — succès, validation
    BEIGE_CHAUD   = "#FFF0D6"   # Fond sable chaud

    # ── Couleurs secondaires ─────────────────────────────────────────────
    LAVANDE       = "#9B8EC4"   # Mystère, nuit, spirituel
    TERRE_CUITE   = "#F26B5E"   # Corail — accents, alertes
    MIEL          = "#FFD234"   # Jaune soleil — titres, étoiles
    ARDOISE       = "#5A6B78"   # Texte secondaire, neutre
    IVOIRE        = "#FFF8ED"   # Fond le plus clair

    # ── Couleurs fonctionnelles ──────────────────────────────────────────
    SUCCES        = "#6BA368"   # Vert doux — validé, publié
    ATTENTION     = "#D4A054"   # Ocre — avertissement doux
    ERREUR        = "#C45A5A"   # Rouge brique — erreur
    INFO          = "#7BAFD4"   # Bleu ciel — information
    EN_COURS      = "#E8B84B"   # Miel — en cours, spinner

    # ── Mapping Rich (noms courts pour le markup) ────────────────────────
    RICH_THEME = {
        "papy":       Style(color=OCRE, bold=True),
        "antoine":    Style(color=BLEU_CIEL, bold=True),
        "noemie":     Style(color=ROSE_POUDRE, bold=True),
        "narrateur":  Style(color=ARDOISE, italic=True),
        "sfx":        Style(color=LAVANDE, dim=True, italic=True),
        "titre":      Style(color=OCRE, bold=True),
        "succes":     Style(color=SUCCES, bold=True),
        "attention":  Style(color=ATTENTION),
        "erreur":     Style(color=ERREUR, bold=True),
        "info":       Style(color=INFO),
        "miel":       Style(color=MIEL),
        "dim":        Style(color=ARDOISE, dim=True),
        "accent":     Style(color=TERRE_CUITE),
        "score.bon":  Style(color=SUCCES, bold=True),
        "score.moyen": Style(color=ATTENTION, bold=True),
        "score.bas":  Style(color=ERREUR, bold=True),
        "etape":      Style(color=BLEU_CIEL, bold=True),
        "label":      Style(color=ARDOISE),
        "valeur":     Style(color=IVOIRE, bold=True),
    }


# ══════════════════════════════════════════════════════════════════════════════
# ICÔNES — Flat design enfant (Unicode)
# Cohérentes avec l'univers : pas de tech, que du chaleureux
# ══════════════════════════════════════════════════════════════════════════════

class Icons:
    """Icônes Unicode flat design pour le CLI."""

    # ── Personnages ──────────────────────────────────────────────────────
    PAPY          = "📖"    # Livre ouvert — le conteur
    ANTOINE       = "⚡"    # Éclair — l'aventurier
    NOEMIE        = "🌸"    # Fleur — la sensible
    NARRATEUR     = "🎙️"    # Micro — voix off
    SFX           = "🔔"    # Clochette — bruitage

    # ── Étapes du pipeline ───────────────────────────────────────────────
    SCRIPT        = "✏️"     # Écriture
    REVIEW        = "📋"    # Relecture
    AUDIO         = "🎵"    # Musique / voix
    SFX_STEP      = "🔔"    # Bruitages
    MONTAGE       = "🎬"    # Assemblage
    METADONNEES   = "🏷️"    # Étiquette
    PUBLICATION   = "📡"    # Diffusion
    RAPPORT       = "📊"    # Statistiques

    # ── Statuts ──────────────────────────────────────────────────────────
    OK            = "✓"     # Flat check (pas d'emoji lourd)
    FAIL          = "✗"     # Flat cross
    EN_COURS      = "◉"     # Dot filled
    A_FAIRE       = "○"     # Dot empty
    FLECHE        = "→"     # Transition
    ETOILE        = "★"     # Score / favori
    ETOILE_VIDE   = "☆"     # Score manquant
    ATTENTION_IC  = "▲"     # Triangle warning
    PAUSE         = "‖"     # Pause

    # ── Dashboard ────────────────────────────────────────────────────────
    SAISON        = "📚"    # Collection
    EPISODE       = "📄"    # Page
    COUT          = "💰"    # Budget (seul emoji doré toléré)
    PERSONNAGE    = "👤"    # Personnage
    HORLOGE       = "◷"     # Durée (flat, pas emoji)
    DB            = "⬡"     # Hexagone — base de données
    CHECKPOINT    = "⚑"     # Drapeau — reprise

    # ── Séparateurs ──────────────────────────────────────────────────────
    SEPARATEUR    = "─"
    DOUBLE_SEP    = "═"
    COIN_HG       = "╭"
    COIN_HD       = "╮"
    COIN_BG       = "╰"
    COIN_BD       = "╯"
    BARRE_V       = "│"

    @classmethod
    def score_etoiles(cls, score: float, max_score: float = 10) -> str:
        """Génère une barre d'étoiles flat pour un score.

        Args:
            score: Score obtenu.
            max_score: Score maximum.

        Returns:
            Chaîne d'étoiles (ex: ★★★★★★★☆☆☆ 7/10).
        """
        nb_pleines = round(score / max_score * 10)
        nb_vides = 10 - nb_pleines
        return f"{cls.ETOILE * nb_pleines}{cls.ETOILE_VIDE * nb_vides} {score:.0f}/{max_score:.0f}"

    @classmethod
    def barre_progression(cls, fait: int, total: int, largeur: int = 20) -> str:
        """Barre de progression flat avec caractères Unicode.

        Args:
            fait: Nombre d'éléments complétés.
            total: Nombre total d'éléments.
            largeur: Largeur de la barre en caractères.

        Returns:
            Barre de progression (ex: ████████░░░░ 8/12).
        """
        if total == 0:
            return f"{'░' * largeur} 0/0"
        ratio = min(fait / total, 1.0)
        rempli = round(ratio * largeur)
        vide = largeur - rempli
        pct = round(ratio * 100)
        return f"{'█' * rempli}{'░' * vide} {fait}/{total} ({pct}%)"

    @classmethod
    def personnage_icon(cls, personnage_id: str) -> str:
        """Retourne l'icône d'un personnage."""
        mapping = {
            "papy_babou": cls.PAPY,
            "antoine": cls.ANTOINE,
            "noemie": cls.NOEMIE,
            "narrateur": cls.NARRATEUR,
            "sfx": cls.SFX,
        }
        return mapping.get(personnage_id, cls.PERSONNAGE)

    @classmethod
    def etape_icon(cls, etape: str) -> str:
        """Retourne l'icône d'une étape du pipeline."""
        mapping = {
            "script": cls.SCRIPT,
            "review": cls.REVIEW,
            "audio": cls.AUDIO,
            "sfx": cls.SFX_STEP,
            "montage": cls.MONTAGE,
            "metadonnees": cls.METADONNEES,
            "publication": cls.PUBLICATION,
            "rapport": cls.RAPPORT,
        }
        return mapping.get(etape, cls.FLECHE)


# ══════════════════════════════════════════════════════════════════════════════
# TYPOGRAPHIE CLI — Hiérarchie visuelle
# ══════════════════════════════════════════════════════════════════════════════

class Typo:
    """Styles typographiques pour la hiérarchie visuelle."""

    @staticmethod
    def h1(texte: str) -> str:
        """Titre principal — Ocre gras."""
        return f"[bold {Palette.OCRE}]{texte}[/]"

    @staticmethod
    def h2(texte: str) -> str:
        """Sous-titre — Bleu ciel gras."""
        return f"[bold {Palette.BLEU_CIEL}]{texte}[/]"

    @staticmethod
    def h3(texte: str) -> str:
        """Titre de section — Terre cuite."""
        return f"[bold {Palette.TERRE_CUITE}]{texte}[/]"

    @staticmethod
    def body(texte: str) -> str:
        """Texte courant — Ivoire."""
        return f"[{Palette.IVOIRE}]{texte}[/]"

    @staticmethod
    def dim(texte: str) -> str:
        """Texte secondaire — Ardoise dim."""
        return f"[dim {Palette.ARDOISE}]{texte}[/]"

    @staticmethod
    def succes(texte: str) -> str:
        """Message de succès — Vert olive."""
        return f"[bold {Palette.SUCCES}]{Icons.OK} {texte}[/]"

    @staticmethod
    def erreur(texte: str) -> str:
        """Message d'erreur — Rouge brique."""
        return f"[bold {Palette.ERREUR}]{Icons.FAIL} {texte}[/]"

    @staticmethod
    def attention(texte: str) -> str:
        """Avertissement — Ocre."""
        return f"[{Palette.ATTENTION}]{Icons.ATTENTION_IC} {texte}[/]"

    @staticmethod
    def info(texte: str) -> str:
        """Information — Bleu ciel."""
        return f"[{Palette.INFO}]{texte}[/]"

    @staticmethod
    def label_valeur(label: str, valeur: str) -> str:
        """Paire label: valeur avec styles différenciés."""
        return f"[{Palette.ARDOISE}]{label} :[/] [bold {Palette.IVOIRE}]{valeur}[/]"

    @staticmethod
    def etape(numero: int, total: int, nom: str) -> str:
        """En-tête d'étape du pipeline."""
        icon = Icons.etape_icon(nom.lower().split()[0] if nom else "")
        return f"[bold {Palette.BLEU_CIEL}]{icon} Étape {numero}/{total} — {nom}[/]"

    @staticmethod
    def score_styled(score: float) -> str:
        """Score coloré selon la valeur."""
        if score >= 8:
            color = Palette.SUCCES
        elif score >= 6:
            color = Palette.ATTENTION
        else:
            color = Palette.ERREUR
        return f"[bold {color}]{score:.0f}/10[/]"


# ══════════════════════════════════════════════════════════════════════════════
# COMPOSANTS UI — Panels, Tables, Bannières
# ══════════════════════════════════════════════════════════════════════════════

# ── Noms de personnages avec icônes ──────────────────────────────────────────

NOMS_PERSONNAGES_STYLED = {
    "papy_babou": f"[bold {Palette.OCRE}]{Icons.PAPY} Papy Babou[/]",
    "antoine":    f"[bold {Palette.BLEU_CIEL}]{Icons.ANTOINE} Antoine[/]",
    "noemie":     f"[bold {Palette.ROSE_POUDRE}]{Icons.NOEMIE} Noémie[/]",
    "narrateur":  f"[italic {Palette.ARDOISE}]{Icons.NARRATEUR} Narrateur[/]",
    "sfx":        f"[dim italic {Palette.LAVANDE}]{Icons.SFX} SFX[/]",
}


def get_rich_theme() -> RichTheme:
    """Retourne le thème Rich configuré pour le podcast."""
    return RichTheme(Palette.RICH_THEME)


def creer_console() -> Console:
    """Crée une console Rich avec le thème Papy Babou."""
    return Console(theme=get_rich_theme())


# ── Bannière d'accueil ───────────────────────────────────────────────────────

BANNER_ART = r"""
[#D4A054]  ╭──────────────────────────────────────────────╮[/]
[#D4A054]  │[/]  [bold #D4A054]📖  Les Histoires de Papy Babou[/]         [#D4A054]│[/]
[#D4A054]  │[/]  [dim #5A6978]Système de production automatisée[/]        [#D4A054]│[/]
[#D4A054]  ╰──────────────────────────────────────────────╯[/]
"""

BANNER_MINI = f"[bold {Palette.OCRE}]{Icons.PAPY} Les Histoires de Papy Babou[/]"


def banner(console: Console, sous_titre: str = "") -> None:
    """Affiche la bannière principale du podcast."""
    console.print(BANNER_ART)
    if sous_titre:
        console.print(f"  {Typo.dim(sous_titre)}\n")


# ── Panels stylisés ─────────────────────────────────────────────────────────

def panel_episode(
    episode_id: str,
    titre: str,
    mode: str = "PRODUCTION",
    type_episode: str = "standard",
    morale: str = "",
    ambiance: str = "",
) -> Panel:
    """Panel d'en-tête d'épisode avec identité visuelle."""
    type_str = f" [{type_episode}]" if type_episode != "standard" else ""
    lignes = [
        f"[bold {Palette.OCRE}]{episode_id} — {titre}{type_str}[/]",
        "",
        f"[{Palette.ARDOISE}]Mode[/]     [bold]{mode}[/]",
    ]
    if morale:
        lignes.append(f"[{Palette.ARDOISE}]Morale[/]   [{Palette.IVOIRE}]{morale}[/]")
    if ambiance:
        lignes.append(f"[{Palette.ARDOISE}]Ambiance[/] [{Palette.LAVANDE}]{ambiance}[/]")

    return Panel(
        "\n".join(lignes),
        title=f"{Icons.PAPY} [bold {Palette.OCRE}]Papy Babou[/]",
        subtitle=Typo.dim("studio de production"),
        border_style=Style(color=Palette.OCRE),
        padding=(1, 2),
    )


def panel_episode_saison(
    episode_id: str,
    titre: str,
    mode: str = "PRODUCTION",
    type_episode: str = "standard",
    morale: str = "",
    ambiance: str = "",
    saison_theme: str = "",
    episode_courant: int = 1,
    total_episodes: int = 1,
) -> Panel:
    """Panel d'en-tête d'épisode dans le contexte d'une saison.

    Se distingue visuellement de panel_episode() pour signaler
    clairement que l'on est dans un workflow de production sérielle.
    """
    type_str = f" [{type_episode}]" if type_episode != "standard" else ""
    progression = Icons.barre_progression(episode_courant - 1, total_episodes, largeur=15)

    lignes = [
        f"[bold {Palette.BLEU_CIEL}]{Icons.SAISON} Saison — {saison_theme}[/]",
        f"[{Palette.ARDOISE}]Progression[/] {progression}",
        "",
        f"[bold {Palette.OCRE}]{episode_id} — {titre}{type_str}[/]",
        f"[{Palette.ARDOISE}]Episode[/]    [{Palette.MIEL}]{episode_courant}/{total_episodes}[/]",
        f"[{Palette.ARDOISE}]Mode[/]       [bold]{mode}[/]",
    ]
    if morale:
        lignes.append(f"[{Palette.ARDOISE}]Morale[/]     [{Palette.IVOIRE}]{morale}[/]")
    if ambiance:
        lignes.append(f"[{Palette.ARDOISE}]Ambiance[/]   [{Palette.LAVANDE}]{ambiance}[/]")

    return Panel(
        "\n".join(lignes),
        title=f"{Icons.PAPY} [bold {Palette.OCRE}]Papy Babou[/] {Typo.dim('— production sérielle')}",
        subtitle=Typo.dim("studio de production"),
        border_style=Style(color=Palette.BLEU_CIEL),
        padding=(1, 2),
    )


def panel_roadmap(etape_courante: int, dry_run: bool = False) -> Panel:
    """Affiche le roadmap des 8 étapes du pipeline avec la position courante.

    Args:
        etape_courante: Index 0-based de l'étape en cours.
        dry_run: Si True, marque les étapes sautées en dry-run.
    """
    etapes_info = [
        ("script",      "Script",       Icons.SCRIPT),
        ("review",      "Relecture",    Icons.REVIEW),
        ("audio",       "Audio",        Icons.AUDIO),
        ("sfx",         "Bruitages",    Icons.SFX_STEP),
        ("montage",     "Montage",      Icons.MONTAGE),
        ("metadonnees", "Métadonnées",  Icons.METADONNEES),
        ("publication", "Publication",  Icons.PUBLICATION),
        ("rapport",     "Rapport",      Icons.RAPPORT),
    ]

    # Étapes sautées en dry-run
    skip_dry = {2, 3, 4, 6}  # audio, sfx, montage, publication

    parties = []
    for i, (_, nom, icon) in enumerate(etapes_info):
        if i < etape_courante:
            parties.append(f"[{Palette.SUCCES}]{Icons.OK} {icon} {nom}[/]")
        elif i == etape_courante:
            parties.append(f"[bold {Palette.MIEL}]{Icons.EN_COURS} {icon} {nom}[/]")
        elif dry_run and i in skip_dry:
            parties.append(f"[{Palette.ARDOISE}]{Icons.PAUSE} {icon} {nom} (skip)[/]")
        else:
            parties.append(f"[{Palette.ARDOISE}]{Icons.A_FAIRE} {icon} {nom}[/]")

    return Panel(
        "  ".join(parties),
        border_style=Style(color=Palette.ARDOISE),
        padding=(0, 1),
    )


def panel_separateur_episode(
    episode_courant: int,
    total_episodes: int,
    episode_id: str,
    titre: str,
    type_episode: str = "standard",
) -> Panel:
    """Séparateur visuel entre épisodes dans une production sérielle."""
    type_str = f" [{type_episode}]" if type_episode != "standard" else ""
    progression = Icons.barre_progression(episode_courant - 1, total_episodes, largeur=20)

    return Panel(
        f"[bold {Palette.BLEU_CIEL}]Épisode {episode_courant}/{total_episodes}[/]"
        f" — {episode_id} {titre}{type_str}\n"
        f"{progression}",
        border_style=Style(color=Palette.BLEU_CIEL),
        padding=(0, 2),
    )


def panel_validation(options: list[tuple[str, str]], titre: str = "Validation") -> Panel:
    """Panel de choix interactif avec style flat.

    Args:
        options: Liste de tuples (touche, description).
        titre: Titre du panel.
    """
    lignes = []
    for touche, desc in options:
        lignes.append(
            f"  [{Palette.MIEL}]({touche})[/]  [{Palette.IVOIRE}]{desc}[/]"
        )

    return Panel(
        "\n".join(lignes),
        title=f"[{Palette.VERT_OLIVE}]{titre}[/]",
        border_style=Style(color=Palette.VERT_OLIVE),
        padding=(1, 2),
    )


def panel_erreur(message: str, titre: str = "Erreur") -> Panel:
    """Panel d'erreur avec style rouge brique."""
    return Panel(
        f"[{Palette.ERREUR}]{message}[/]",
        title=f"[bold {Palette.ERREUR}]{Icons.FAIL} {titre}[/]",
        border_style=Style(color=Palette.ERREUR),
        padding=(1, 2),
    )


def panel_succes(message: str, titre: str = "Terminé") -> Panel:
    """Panel de succès avec style vert olive."""
    return Panel(
        f"[{Palette.IVOIRE}]{message}[/]",
        title=f"[bold {Palette.SUCCES}]{Icons.OK} {titre}[/]",
        border_style=Style(color=Palette.SUCCES),
        padding=(1, 2),
    )


def panel_info(message: str, titre: str = "Information") -> Panel:
    """Panel informatif avec style bleu ciel."""
    return Panel(
        f"[{Palette.IVOIRE}]{message}[/]",
        title=f"[{Palette.INFO}]{titre}[/]",
        border_style=Style(color=Palette.BLEU_CIEL),
        padding=(1, 2),
    )


def panel_rapport_final(
    episode_id: str,
    titre: str,
    score: float,
    morale: str,
    cout: str,
    chemin_rapport: str,
    dry_run: bool = False,
) -> Panel:
    """Panel du rapport final de production avec identité visuelle complète."""
    etoiles = Icons.score_etoiles(score)
    lignes = [
        f"[bold {Palette.SUCCES}]{Icons.OK} Production terminée ![/]",
        "",
        f"  [{Palette.ARDOISE}]Épisode[/]  [bold {Palette.OCRE}]{episode_id} — {titre}[/]",
        f"  [{Palette.ARDOISE}]Score[/]    {etoiles}",
        f"  [{Palette.ARDOISE}]Morale[/]   [{Palette.IVOIRE}]{morale}[/]",
        f"  [{Palette.ARDOISE}]Coût[/]     [{Palette.MIEL}]{cout}[/]",
        f"  [{Palette.ARDOISE}]Rapport[/]  [{Palette.ARDOISE}]{chemin_rapport}[/]",
    ]

    return Panel(
        "\n".join(lignes),
        title=f"{Icons.RAPPORT} [{Palette.OCRE}]Résumé[/]",
        border_style=Style(color=Palette.SUCCES if not dry_run else Palette.ATTENTION),
        padding=(1, 2),
    )


# ── Tables stylisées ────────────────────────────────────────────────────────

def table_review(score: float, details: dict) -> Table:
    """Table de score de review avec étoiles et couleurs."""
    etoiles = Icons.score_etoiles(score)
    table = Table(
        title=f"{Icons.REVIEW} Review — {etoiles}",
        title_style=Style(color=Palette.OCRE, bold=True),
        border_style=Style(color=Palette.ARDOISE),
        show_lines=False,
        pad_edge=True,
        padding=(0, 2),
    )
    table.add_column("Critère", style=Style(color=Palette.BLEU_CIEL))
    table.add_column("Score", justify="right", style=Style(color=Palette.IVOIRE))
    table.add_column("", width=12)

    for critere, val in details.items():
        nom = critere.replace("_", " ").title()
        barre = Icons.barre_progression(round(val * 5), 10, largeur=10)
        if val >= 1.5:
            style_score = Palette.SUCCES
        elif val >= 1.0:
            style_score = Palette.ATTENTION
        else:
            style_score = Palette.ERREUR
        table.add_row(
            nom,
            f"[{style_score}]{val}/2[/]",
            f"[{Palette.ARDOISE}]{barre}[/]",
        )

    return table


def table_episodes_dashboard(titre_table: str) -> Table:
    """Table du dashboard des épisodes avec identité visuelle."""
    table = Table(
        title=f"{Icons.SAISON} {titre_table}",
        title_style=Style(color=Palette.OCRE, bold=True),
        border_style=Style(color=Palette.ARDOISE),
        show_lines=False,
        pad_edge=True,
        padding=(0, 1),
        row_styles=[
            Style(),
            Style(bgcolor="#1a1a2e"),  # Alternance douce
        ],
    )
    table.add_column("", width=2)  # Status icon
    table.add_column("Épisode", style=Style(color=Palette.BLEU_CIEL, bold=True), width=8)
    table.add_column("Titre", style=Style(color=Palette.IVOIRE), min_width=20)
    table.add_column("Type", style=Style(color=Palette.ARDOISE), width=10)
    table.add_column("Score", justify="center", width=14)
    table.add_column("Morale", style=Style(color=Palette.VERT_OLIVE), max_width=30)
    table.add_column("Ambiance", style=Style(color=Palette.LAVANDE), width=12)
    table.add_column("Date", style=Style(color=Palette.ARDOISE), width=10)

    return table


def ajouter_episode_dashboard(
    table: Table,
    episode_id: str,
    titre: str,
    type_episode: str,
    score: float,
    ambiance: str,
    date: str,
    morale: str = "",
) -> None:
    """Ajoute une ligne épisode au tableau dashboard."""
    # Icône de statut
    if score >= 8:
        status_icon = f"[{Palette.SUCCES}]{Icons.OK}[/]"
    elif score >= 6:
        status_icon = f"[{Palette.ATTENTION}]{Icons.EN_COURS}[/]"
    elif score > 0:
        status_icon = f"[{Palette.ERREUR}]{Icons.ATTENTION_IC}[/]"
    else:
        status_icon = f"[{Palette.ARDOISE}]{Icons.A_FAIRE}[/]"

    # Score avec mini étoiles
    if isinstance(score, (int, float)) and score > 0:
        nb_stars = round(score / 2)
        stars = f"[{Palette.MIEL}]{Icons.ETOILE * nb_stars}[/]"
        score_str = f"{stars} {Typo.score_styled(score)}"
    else:
        score_str = Typo.dim("—")

    titre_affiche = titre[:32] + "…" if len(titre) > 35 else titre
    morale_affiche = morale[:27] + "…" if len(morale) > 30 else morale if morale else "—"
    table.add_row(
        status_icon,
        episode_id,
        titre_affiche,
        type_episode,
        score_str,
        morale_affiche,
        ambiance or "—",
        date[:10] if date else "—",
    )


def table_saison_plan(saison: int, theme: str) -> Table:
    """Table de planification de saison."""
    table = Table(
        title=f"{Icons.SAISON} Saison {saison} — {theme}",
        title_style=Style(color=Palette.OCRE, bold=True),
        border_style=Style(color=Palette.ARDOISE),
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Ep", style=Style(color=Palette.BLEU_CIEL, bold=True), justify="right", width=4)
    table.add_column("Titre", style=Style(color=Palette.IVOIRE), min_width=25)
    table.add_column("Type", style=Style(color=Palette.ARDOISE), width=12)
    table.add_column("Ambiance", style=Style(color=Palette.LAVANDE), width=12)
    table.add_column("Morale", style=Style(color=Palette.ARDOISE), max_width=40)

    return table


def table_couts(titre: str = "Coûts de production") -> Table:
    """Table des coûts avec style financier flat."""
    table = Table(
        title=f"{Icons.COUT} {titre}",
        title_style=Style(color=Palette.MIEL, bold=True),
        border_style=Style(color=Palette.ARDOISE),
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("Service", style=Style(color=Palette.BLEU_CIEL))
    table.add_column("Détail", style=Style(color=Palette.ARDOISE))
    table.add_column("Coût", justify="right", style=Style(color=Palette.MIEL, bold=True))

    return table


def table_db_status() -> Table:
    """Table de statut de la base de données."""
    table = Table(
        title=f"{Icons.DB} Base de données PostgreSQL",
        title_style=Style(color=Palette.BLEU_CIEL, bold=True),
        border_style=Style(color=Palette.ARDOISE),
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("Table", style=Style(color=Palette.BLEU_CIEL))
    table.add_column("Enregistrements", justify="right", style=Style(color=Palette.MIEL))
    table.add_column("", width=25)  # Barre visuelle

    return table


# ── Widgets de progression saison ────────────────────────────────────────────

def progression_saison(
    console: Console,
    saison: int,
    episodes_plan: list[dict],
    episodes_produits: set[str],
) -> None:
    """Affiche la progression d'une saison avec barres et icônes."""
    fait = len(episodes_produits)
    total = len(episodes_plan)
    barre = Icons.barre_progression(fait, total, largeur=20)

    console.print(
        f"\n  {Icons.SAISON} [{Palette.OCRE}]Progression saison {saison}[/]  "
        f"[{Palette.ARDOISE}]{barre}[/]"
    )
    console.print()

    for ep in episodes_plan:
        ep_id = f"S{saison:02d}E{ep['numero']:02d}"
        if ep_id in episodes_produits:
            icon = f"[{Palette.SUCCES}]{Icons.OK}[/]"
            status = f"[{Palette.SUCCES}]produit[/]"
        else:
            icon = f"[{Palette.ARDOISE}]{Icons.A_FAIRE}[/]"
            status = f"[{Palette.ARDOISE}]à faire[/]"
        type_tag = f"[{Palette.LAVANDE}][{ep.get('type', 'standard')}][/]"
        titre_ep = ep['titre'][:32] + "…" if len(ep['titre']) > 35 else ep['titre']
        console.print(
            f"    {icon}  [{Palette.BLEU_CIEL}]E{ep['numero']:02d}[/]  "
            f"{titre_ep:<35}  {type_tag:<25}  {status}"
        )


# ── Widget statistiques ──────────────────────────────────────────────────────

def stats_block(
    console: Console,
    nb_episodes: int,
    score_moyen: float,
    score_max: float,
    score_min: float,
) -> None:
    """Bloc de statistiques compact et flat."""
    console.print(
        f"\n  [{Palette.ARDOISE}]{'─' * 50}[/]"
    )
    console.print(
        f"  {Icons.EPISODE} [{Palette.ARDOISE}]Épisodes produits[/]  "
        f"[bold {Palette.MIEL}]{nb_episodes}[/]"
    )
    console.print(
        f"  {Icons.ETOILE} [{Palette.ARDOISE}]Score moyen[/]       "
        f"{Typo.score_styled(score_moyen)}  "
        f"[{Palette.ARDOISE}](min {score_min:.0f} / max {score_max:.0f})[/]"
    )


def personnages_block(console: Console, personnages: dict[str, int]) -> None:
    """Bloc des personnages avec icônes et compteurs."""
    if not personnages:
        return
    console.print(f"\n  [{Palette.ARDOISE}]{'─' * 50}[/]")
    console.print(f"  [{Palette.TERRE_CUITE}]Personnages[/]")
    for p, count in sorted(personnages.items(), key=lambda x: -x[1]):
        icon = Icons.personnage_icon(p)
        nom_styled = NOMS_PERSONNAGES_STYLED.get(
            p, f"[{Palette.IVOIRE}]{p}[/]"
        )
        barre = "█" * min(count, 20)
        console.print(
            f"    {icon} {nom_styled:<30}  "
            f"[{Palette.ARDOISE}]{barre}[/] [{Palette.MIEL}]{count}[/]"
        )


# ══════════════════════════════════════════════════════════════════════════════
# AFFICHAGE SCRIPT — Vue de lecture avec personnages colorés
# ══════════════════════════════════════════════════════════════════════════════

def afficher_script(console: Console, script: dict) -> None:
    """Affiche un script complet avec l'identité visuelle Papy Babou."""
    episode = script["episode"]

    # En-tête
    console.print(Panel(
        f"[bold {Palette.OCRE}]{episode['titre']}[/]\n"
        f"[{Palette.BLEU_CIEL}]S{episode['saison']:02d}E{episode['numero']:02d}[/]  "
        f"[{Palette.ARDOISE}]│[/]  "
        f"[{Palette.LAVANDE}]{episode.get('ambiance', '?')}[/]  "
        f"[{Palette.ARDOISE}]│[/]  "
        f"[{Palette.VERT_OLIVE}]{episode.get('morale', '?')}[/]",
        title=f"{Icons.SCRIPT} [{Palette.OCRE}]Script[/]",
        border_style=Style(color=Palette.OCRE),
        padding=(1, 2),
    ))

    # Segments
    for seg in episode["segments"]:
        personnage = seg["personnage"]
        texte = seg["texte"]
        nom_styled = NOMS_PERSONNAGES_STYLED.get(
            personnage,
            f"[{Palette.IVOIRE}]{personnage}[/]"
        )

        if personnage == "sfx":
            mode = seg.get("mode", "insert")
            duree = seg.get("duree_sfx_secondes", "?")
            console.print(
                f"  [{Palette.LAVANDE}]  {Icons.SFX} SFX ({mode}) : "
                f"{texte} ({duree}s)[/]"
            )
        elif personnage == "narrateur":
            console.print(
                f"  [{Palette.ARDOISE}]  {Icons.NARRATEUR} [Narrateur][/] "
                f"[italic {Palette.ARDOISE}]{texte}[/]"
            )
        else:
            console.print(f"  {nom_styled}  {texte}")

        pause = seg.get("pause_apres_ms", 0)
        if pause >= 1500:
            console.print(
                f"  [{Palette.ARDOISE}]  {Icons.PAUSE} pause {pause / 1000:.1f}s[/]"
            )

    console.print()


# ══════════════════════════════════════════════════════════════════════════════
# COVER ART — Directives de style pour DALL-E
# ══════════════════════════════════════════════════════════════════════════════

COVER_ART_STYLE = (
    "Flat design illustration for children ages 6-10. "
    "Clean geometric shapes with soft rounded corners. "
    "Warm pastel color palette: golden ochre (#D4A054), sky blue (#7BAFD4), "
    "powder pink (#D4869A), olive green (#8BAF6E), warm beige (#F5E6D0), "
    "lavender (#9B8EC4), terracotta (#C47A5A). "
    "Provence countryside atmosphere with golden light. "
    "Minimalist style with bold outlines and flat color fills, no gradients. "
    "Inspired by modern children's book illustrations (Oliver Jeffers, Jon Klassen). "
    "Include a subtle golden frame border evoking an old storybook. "
)

COVER_ART_INTERDICTIONS = [
    "no realistic style",
    "no 3D rendering",
    "no dark or scary elements",
    "no violence",
    "no direct representation of God",
    "no nudity",
    "no gradients or shadows",
    "no photographic style",
]


# ══════════════════════════════════════════════════════════════════════════════
# FAVICON SVG — Logo flat design
# ══════════════════════════════════════════════════════════════════════════════

FAVICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <!-- Fond circulaire ocre doré -->
  <circle cx="256" cy="256" r="256" fill="#D4A054"/>

  <!-- Livre ouvert (flat) — symbole central -->
  <g transform="translate(256, 280)">
    <!-- Page gauche -->
    <path d="M-20,-80 L-20,40 Q-20,50 -30,50 L-130,50 Q-140,50 -140,40 L-140,-60 Q-140,-70 -130,-70 L-30,-80 Q-20,-80 -20,-80 Z"
          fill="#FDF8F0" stroke="#5A6978" stroke-width="4"/>
    <!-- Page droite -->
    <path d="M20,-80 L20,40 Q20,50 30,50 L130,50 Q140,50 140,40 L140,-60 Q140,-70 130,-70 L30,-80 Q20,-80 20,-80 Z"
          fill="#FDF8F0" stroke="#5A6978" stroke-width="4"/>
    <!-- Reliure -->
    <path d="M-20,-80 L0,-90 L20,-80 L20,40 L0,50 L-20,40 Z"
          fill="#C47A5A" stroke="#5A6978" stroke-width="3"/>

    <!-- Lignes de texte page gauche -->
    <line x1="-120" y1="-40" x2="-40" y2="-40" stroke="#D4A054" stroke-width="3" stroke-linecap="round"/>
    <line x1="-120" y1="-20" x2="-50" y2="-20" stroke="#D4A054" stroke-width="3" stroke-linecap="round" opacity="0.6"/>
    <line x1="-120" y1="0" x2="-45" y2="0" stroke="#D4A054" stroke-width="3" stroke-linecap="round" opacity="0.4"/>
    <line x1="-120" y1="20" x2="-55" y2="20" stroke="#D4A054" stroke-width="3" stroke-linecap="round" opacity="0.3"/>

    <!-- Lignes de texte page droite -->
    <line x1="40" y1="-40" x2="120" y2="-40" stroke="#7BAFD4" stroke-width="3" stroke-linecap="round"/>
    <line x1="40" y1="-20" x2="110" y2="-20" stroke="#7BAFD4" stroke-width="3" stroke-linecap="round" opacity="0.6"/>
    <line x1="40" y1="0" x2="115" y2="0" stroke="#7BAFD4" stroke-width="3" stroke-linecap="round" opacity="0.4"/>
    <line x1="40" y1="20" x2="105" y2="20" stroke="#7BAFD4" stroke-width="3" stroke-linecap="round" opacity="0.3"/>
  </g>

  <!-- Étoiles décoratives (flat) -->
  <polygon points="130,90 135,105 150,105 138,114 142,130 130,120 118,130 122,114 110,105 125,105"
           fill="#E8B84B"/>
  <polygon points="380,100 384,111 395,111 386,118 389,129 380,122 371,129 374,118 365,111 376,111"
           fill="#E8B84B" opacity="0.7"/>
  <polygon points="160,150 163,158 172,158 165,163 167,172 160,167 153,172 155,163 148,158 157,158"
           fill="#E8B84B" opacity="0.5"/>

  <!-- Lunettes de Papy (flat, signature) -->
  <g transform="translate(256, 160)">
    <circle cx="-25" cy="0" r="22" fill="none" stroke="#5A6978" stroke-width="5"/>
    <circle cx="25" cy="0" r="22" fill="none" stroke="#5A6978" stroke-width="5"/>
    <line x1="3" y1="0" x2="-3" y2="0" stroke="#5A6978" stroke-width="5"/>
    <line x1="-47" y1="-5" x2="-55" y2="-10" stroke="#5A6978" stroke-width="4" stroke-linecap="round"/>
    <line x1="47" y1="-5" x2="55" y2="-10" stroke="#5A6978" stroke-width="4" stroke-linecap="round"/>
  </g>
</svg>"""

FAVICON_ICO_16 = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
  <circle cx="8" cy="8" r="8" fill="#D4A054"/>
  <g transform="translate(8, 9.5)">
    <path d="M-1,-4 L-1,2.5 L-5.5,2.5 L-5.5,-3 L-1.5,-4 Z" fill="#FDF8F0" stroke="#5A6978" stroke-width="0.5"/>
    <path d="M1,-4 L1,2.5 L5.5,2.5 L5.5,-3 L1.5,-4 Z" fill="#FDF8F0" stroke="#5A6978" stroke-width="0.5"/>
    <rect x="-1" y="-4" width="2" height="6.5" fill="#C47A5A"/>
  </g>
  <circle cx="6" cy="5.5" r="1.5" fill="none" stroke="#5A6978" stroke-width="0.8"/>
  <circle cx="10" cy="5.5" r="1.5" fill="none" stroke="#5A6978" stroke-width="0.8"/>
  <line x1="7.5" y1="5.5" x2="8.5" y2="5.5" stroke="#5A6978" stroke-width="0.8"/>
</svg>"""


def generer_favicon(chemin_sortie: str) -> str:
    """Écrit le favicon SVG sur disque.

    Args:
        chemin_sortie: Chemin du fichier SVG de sortie.

    Returns:
        Chemin du fichier créé.
    """
    from pathlib import Path
    path = Path(chemin_sortie)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(FAVICON_SVG)
    return str(path)


def generer_favicon_16(chemin_sortie: str) -> str:
    """Écrit le favicon 16x16 SVG sur disque."""
    from pathlib import Path
    path = Path(chemin_sortie)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(FAVICON_ICO_16)
    return str(path)
