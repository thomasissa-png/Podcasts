"""Tests pour le module theme.py — Design system Papy Babou.

Vérifie que tous les composants du design system fonctionnent
sans crash et produisent des sorties cohérentes.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from theme import (
    Palette,
    Icons,
    Typo,
    NOMS_PERSONNAGES_STYLED,
    BANNER_ART,
    BANNER_MINI,
    COVER_ART_STYLE,
    creer_console,
    get_rich_theme,
    banner,
    panel_episode,
    panel_episode_saison,
    panel_validation,
    panel_erreur,
    panel_succes,
    panel_info,
    panel_rapport_final,
    panel_roadmap,
    panel_separateur_episode,
    table_review,
    table_episodes_dashboard,
    ajouter_episode_dashboard,
    table_saison_plan,
    table_couts,
    table_db_status,
    stats_block,
    personnages_block,
    progression_saison,
    afficher_script,
)


class TestPalette:
    """Tests de la palette de couleurs."""

    def test_couleurs_principales_definies(self):
        """Les 10 couleurs de la marque doivent être des codes hex."""
        couleurs = [
            Palette.OCRE, Palette.BLEU_CIEL, Palette.ROSE_POUDRE,
            Palette.VERT_OLIVE, Palette.BEIGE_CHAUD, Palette.LAVANDE,
            Palette.TERRE_CUITE, Palette.MIEL, Palette.ARDOISE, Palette.IVOIRE,
        ]
        for couleur in couleurs:
            assert couleur.startswith("#"), f"{couleur} n'est pas un code hex"
            assert len(couleur) == 7, f"{couleur} devrait avoir 7 caractères (#RRGGBB)"

    def test_couleurs_fonctionnelles_definies(self):
        """Les couleurs fonctionnelles (succès, erreur, etc.) doivent exister."""
        assert Palette.SUCCES
        assert Palette.ATTENTION
        assert Palette.ERREUR
        assert Palette.INFO
        assert Palette.EN_COURS

    def test_rich_theme_est_un_dict(self):
        """RICH_THEME doit être un dictionnaire de styles."""
        assert isinstance(Palette.RICH_THEME, dict)
        assert len(Palette.RICH_THEME) > 0

    def test_palette_personnages_json_alignee(self):
        """Les couleurs hex de la palette doivent correspondre au format attendu."""
        assert Palette.OCRE == "#D4A054"
        assert Palette.BLEU_CIEL == "#7BAFD4"
        assert Palette.ROSE_POUDRE == "#D4869A"


class TestIcons:
    """Tests des icônes Unicode."""

    def test_icones_personnages(self):
        """Chaque personnage principal doit avoir une icône."""
        assert Icons.PAPY
        assert Icons.ANTOINE
        assert Icons.NOEMIE
        assert Icons.NARRATEUR
        assert Icons.SFX

    def test_icones_etapes_pipeline(self):
        """Chaque étape du pipeline doit avoir une icône."""
        etapes = [
            Icons.SCRIPT, Icons.REVIEW, Icons.AUDIO,
            Icons.SFX_STEP, Icons.MONTAGE, Icons.METADONNEES,
            Icons.PUBLICATION, Icons.RAPPORT,
        ]
        for etape in etapes:
            assert etape, "Icône d'étape manquante"

    def test_icones_statuts(self):
        """Les statuts doivent avoir des icônes distinctes."""
        assert Icons.OK != Icons.FAIL
        assert Icons.EN_COURS != Icons.A_FAIRE
        assert Icons.ETOILE != Icons.ETOILE_VIDE

    def test_score_etoiles_format(self):
        """score_etoiles doit produire une chaîne lisible."""
        result = Icons.score_etoiles(7, 10)
        assert "★" in result
        assert "☆" in result
        assert "7/10" in result

    def test_score_etoiles_zero(self):
        """score_etoiles(0) doit produire que des étoiles vides."""
        result = Icons.score_etoiles(0, 10)
        assert "★" not in result
        assert "0/10" in result

    def test_score_etoiles_max(self):
        """score_etoiles(10) doit produire que des étoiles pleines."""
        result = Icons.score_etoiles(10, 10)
        assert "☆" not in result
        assert "10/10" in result

    def test_barre_progression_format(self):
        """barre_progression doit produire une barre lisible."""
        result = Icons.barre_progression(5, 10, largeur=20)
        assert "█" in result
        assert "░" in result
        assert "5/10" in result
        assert "50%" in result

    def test_barre_progression_vide(self):
        """barre_progression(0, 10) doit être vide."""
        result = Icons.barre_progression(0, 10, largeur=10)
        assert "█" not in result
        assert "0/10" in result

    def test_barre_progression_total_zero(self):
        """barre_progression(0, 0) ne doit pas lever de ZeroDivisionError."""
        result = Icons.barre_progression(0, 0)
        assert "0/0" in result

    def test_barre_progression_complete(self):
        """barre_progression(10, 10) doit être pleine."""
        result = Icons.barre_progression(10, 10, largeur=10)
        assert "░" not in result
        assert "100%" in result

    def test_personnage_icon(self):
        """personnage_icon doit retourner l'icône du personnage."""
        assert Icons.personnage_icon("papy_babou") == Icons.PAPY
        assert Icons.personnage_icon("antoine") == Icons.ANTOINE
        assert Icons.personnage_icon("noemie") == Icons.NOEMIE
        assert Icons.personnage_icon("narrateur") == Icons.NARRATEUR
        assert Icons.personnage_icon("sfx") == Icons.SFX

    def test_personnage_icon_inconnu(self):
        """personnage_icon avec un nom inconnu doit retourner PERSONNAGE."""
        assert Icons.personnage_icon("inconnu") == Icons.PERSONNAGE


class TestTypo:
    """Tests de la hiérarchie typographique."""

    def test_h1_contient_texte(self):
        """h1 doit contenir le texte passé."""
        result = Typo.h1("Titre Test")
        assert "Titre Test" in result

    def test_h2_contient_texte(self):
        result = Typo.h2("Sous-titre")
        assert "Sous-titre" in result

    def test_h3_contient_texte(self):
        result = Typo.h3("Section")
        assert "Section" in result

    def test_body_contient_texte(self):
        result = Typo.body("Contenu")
        assert "Contenu" in result

    def test_dim_contient_texte(self):
        result = Typo.dim("Secondaire")
        assert "Secondaire" in result

    def test_succes_contient_ok(self):
        """succes doit inclure l'icône OK."""
        result = Typo.succes("Réussi")
        assert Icons.OK in result
        assert "Réussi" in result

    def test_erreur_contient_fail(self):
        """erreur doit inclure l'icône FAIL."""
        result = Typo.erreur("Échoué")
        assert Icons.FAIL in result

    def test_attention_contient_warning(self):
        result = Typo.attention("Attention")
        assert Icons.ATTENTION_IC in result

    def test_label_valeur_format(self):
        result = Typo.label_valeur("Score", "8/10")
        assert "Score" in result
        assert "8/10" in result

    def test_etape_format(self):
        result = Typo.etape(1, 8, "Script")
        assert "1/8" in result
        assert "Script" in result

    def test_score_styled_bon(self):
        result = Typo.score_styled(9)
        assert "9/10" in result
        assert Palette.SUCCES in result

    def test_score_styled_moyen(self):
        result = Typo.score_styled(6.5)
        assert Palette.ATTENTION in result

    def test_score_styled_bas(self):
        result = Typo.score_styled(3)
        assert Palette.ERREUR in result


class TestComposantsUI:
    """Tests des composants UI (panels, tables, bannières)."""

    def test_creer_console(self):
        """creer_console doit retourner une console Rich valide."""
        from rich.console import Console
        console = creer_console()
        assert isinstance(console, Console)

    def test_get_rich_theme(self):
        """get_rich_theme doit retourner un objet Theme."""
        from rich.theme import Theme
        theme = get_rich_theme()
        assert isinstance(theme, Theme)

    def test_banner_ne_crashe_pas(self):
        """banner() ne doit pas lever d'exception."""
        console = creer_console()
        banner(console, "Test")

    def test_banner_avec_sous_titre(self):
        console = creer_console()
        banner(console, "Mon sous-titre")

    def test_banner_sans_sous_titre(self):
        console = creer_console()
        banner(console)

    def test_banner_art_contient_nom_podcast(self):
        assert "Papy Babou" in BANNER_ART

    def test_banner_mini_contient_nom(self):
        assert "Papy Babou" in BANNER_MINI

    def test_panel_episode_retourne_panel(self):
        from rich.panel import Panel
        result = panel_episode("S01E01", "Le buisson ardent")
        assert isinstance(result, Panel)

    def test_panel_episode_avec_options(self):
        from rich.panel import Panel
        result = panel_episode(
            "S01E01", "Test", mode="DRY-RUN",
            type_episode="ouverture", morale="La foi", ambiance="mystere",
        )
        assert isinstance(result, Panel)

    def test_panel_validation_retourne_panel(self):
        from rich.panel import Panel
        result = panel_validation([("v", "Valider"), ("r", "Rejeter")])
        assert isinstance(result, Panel)

    def test_panel_erreur_retourne_panel(self):
        from rich.panel import Panel
        result = panel_erreur("Erreur critique")
        assert isinstance(result, Panel)

    def test_panel_succes_retourne_panel(self):
        from rich.panel import Panel
        result = panel_succes("Tout est OK")
        assert isinstance(result, Panel)

    def test_panel_info_retourne_panel(self):
        from rich.panel import Panel
        result = panel_info("Info test")
        assert isinstance(result, Panel)

    def test_panel_rapport_final_retourne_panel(self):
        from rich.panel import Panel
        result = panel_rapport_final(
            "S01E01", "Le buisson ardent", 8.5,
            "La foi déplace les montagnes", "$0.50",
            "/logs/rapport.json",
        )
        assert isinstance(result, Panel)

    def test_panel_rapport_final_dry_run(self):
        from rich.panel import Panel
        result = panel_rapport_final(
            "S01E01", "Test", 7.0, "Morale", "$0",
            "/logs/rapport.json", dry_run=True,
        )
        assert isinstance(result, Panel)

    def test_panel_episode_saison_retourne_panel(self):
        """panel_episode_saison affiche le contexte sériel."""
        from rich.panel import Panel
        result = panel_episode_saison(
            "S01E03", "L'arche de Noé",
            saison_theme="Les grands voyages",
            episode_courant=3,
            total_episodes=10,
        )
        assert isinstance(result, Panel)

    def test_panel_episode_saison_avec_toutes_options(self):
        from rich.panel import Panel
        result = panel_episode_saison(
            "S01E01", "Le départ",
            mode="DRY RUN",
            type_episode="ouverture",
            morale="Le courage",
            ambiance="aventure",
            saison_theme="Les grands voyages",
            episode_courant=1,
            total_episodes=10,
        )
        assert isinstance(result, Panel)

    def test_panel_roadmap_retourne_panel(self):
        """panel_roadmap affiche les 8 étapes avec la position courante."""
        from rich.panel import Panel
        result = panel_roadmap(0)
        assert isinstance(result, Panel)

    def test_panel_roadmap_dry_run(self):
        from rich.panel import Panel
        result = panel_roadmap(2, dry_run=True)
        assert isinstance(result, Panel)

    def test_panel_roadmap_derniere_etape(self):
        from rich.panel import Panel
        result = panel_roadmap(7)
        assert isinstance(result, Panel)

    def test_panel_separateur_episode(self):
        """panel_separateur_episode affiche le séparateur de production sérielle."""
        from rich.panel import Panel
        result = panel_separateur_episode(
            episode_courant=3,
            total_episodes=10,
            episode_id="S01E03",
            titre="L'arche de Noé",
            type_episode="standard",
        )
        assert isinstance(result, Panel)

    def test_panel_separateur_episode_avec_type(self):
        from rich.panel import Panel
        result = panel_separateur_episode(
            episode_courant=1,
            total_episodes=10,
            episode_id="S01E01",
            titre="Le départ",
            type_episode="ouverture",
        )
        assert isinstance(result, Panel)


class TestTables:
    """Tests des tables Rich."""

    def test_table_review(self):
        """table_review doit retourner une Table sans crash."""
        from rich.table import Table
        result = table_review(8.0, {
            "coherence_personnage": 2,
            "adequation_age": 1.5,
            "fidelite_biblique": 2,
            "richesse_educative": 1.5,
            "rythme_structure": 1.5,
            "duree_format": 1,
            "creativite_narrative": 1.5,
        })
        assert isinstance(result, Table)

    def test_table_episodes_dashboard(self):
        from rich.table import Table
        result = table_episodes_dashboard("Saison 1")
        assert isinstance(result, Table)

    def test_ajouter_episode_dashboard_ne_crashe_pas(self):
        table = table_episodes_dashboard("Test")
        ajouter_episode_dashboard(
            table, "S01E01", "Le buisson ardent",
            "standard", 8.5, "mystere", "2025-01-01",
        )

    def test_table_saison_plan(self):
        from rich.table import Table
        result = table_saison_plan(1, "Les Miracles")
        assert isinstance(result, Table)

    def test_table_couts(self):
        from rich.table import Table
        result = table_couts()
        assert isinstance(result, Table)

    def test_table_db_status(self):
        from rich.table import Table
        result = table_db_status()
        assert isinstance(result, Table)


class TestWidgets:
    """Tests des widgets du dashboard."""

    def test_stats_block_ne_crashe_pas(self):
        console = creer_console()
        stats_block(console, nb_episodes=5, score_moyen=8.2, score_max=9.5, score_min=6.0)

    def test_personnages_block_ne_crashe_pas(self):
        console = creer_console()
        personnages_block(console, {"papy_babou": 5, "antoine": 3, "noemie": 4})

    def test_personnages_block_vide(self):
        console = creer_console()
        personnages_block(console, {})

    def test_progression_saison_ne_crashe_pas(self):
        console = creer_console()
        episodes_plan = [{"numero": 1, "titre": "Test", "episode_id": "S01E01"}]
        episodes_produits = {"S01E01"}
        progression_saison(console, 1, episodes_plan, episodes_produits)

    def test_progression_saison_vide(self):
        console = creer_console()
        progression_saison(console, 1, [], set())


class TestAfficherScript:
    """Tests de l'affichage du script avec couleurs personnages."""

    def test_afficher_script_ne_crashe_pas(self):
        console = creer_console()
        script = {
            "episode": {
                "titre": "Test",
                "saison": 1,
                "numero": 1,
                "ambiance": "mystere",
                "morale": "La foi",
                "segments": [
                    {"personnage": "papy_babou", "texte": "Bonjour", "ton": "chaleureux"},
                    {"personnage": "antoine", "texte": "Salut", "ton": "curieux"},
                    {"personnage": "sfx", "texte": "vent", "ton": "ambiance"},
                ],
            }
        }
        afficher_script(console, script)

    def test_afficher_script_vide(self):
        console = creer_console()
        script = {"episode": {"titre": "Vide", "saison": 1, "numero": 1, "segments": []}}
        afficher_script(console, script)


class TestNomsPersStyled:
    """Tests des noms de personnages stylisés."""

    def test_noms_principaux_presents(self):
        assert "papy_babou" in NOMS_PERSONNAGES_STYLED
        assert "antoine" in NOMS_PERSONNAGES_STYLED
        assert "noemie" in NOMS_PERSONNAGES_STYLED
        assert "narrateur" in NOMS_PERSONNAGES_STYLED
        assert "sfx" in NOMS_PERSONNAGES_STYLED

    def test_noms_contiennent_icones(self):
        assert Icons.PAPY in NOMS_PERSONNAGES_STYLED["papy_babou"]
        assert Icons.ANTOINE in NOMS_PERSONNAGES_STYLED["antoine"]


class TestCoverArtStyle:
    """Tests du style DALL-E pour le cover art."""

    def test_cover_art_style_non_vide(self):
        assert len(COVER_ART_STYLE) > 50

    def test_cover_art_style_contient_flat_design(self):
        assert "flat" in COVER_ART_STYLE.lower()

    def test_cover_art_style_contient_couleurs(self):
        """Le style doit référencer les couleurs de la marque."""
        assert "#D4A054" in COVER_ART_STYLE or "ocre" in COVER_ART_STYLE.lower()
