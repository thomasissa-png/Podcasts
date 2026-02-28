"""Agent Métadonnées — Génère toutes les métadonnées pour la distribution."""

import json
import logging
from pathlib import Path

import anthropic

import config
from utils import parser_json_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Tu es un spécialiste des métadonnées de podcasts. Tu génères les métadonnées
de distribution pour le podcast "Les Histoires de Papy Babou" (histoires bibliques pour enfants 6-10 ans).

FORMAT DE RÉPONSE — JSON STRICT :
{
  "titre": "S01E02 — Le buisson ardent | Les Histoires de Papy Babou",
  "titre_court": "Le buisson ardent",
  "description_courte": "Max 160 caractères. Accroche pour l'aperçu dans les apps.",
  "description_longue": "Max 4000 caractères. Description complète pour la fiche épisode. Inclure un résumé de l'histoire, les personnages, et une invitation à écouter.",
  "tags": ["Histoires bibliques", "Enfants", "Famille", "Moïse"],
  "categories_itunes": ["Kids & Family", "Religion & Spirituality"],
  "sous_categories_itunes": ["Stories for Kids"],
  "cover_art_prompt": "Description courte pour générer une illustration d'épisode (ex: 'Moïse devant le buisson ardent dans le désert, style illustration enfant')"
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""


class Metadonnees:
    """Génère les métadonnées d'un épisode pour la distribution podcast."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def generer(self, script: dict, duree_secondes: float) -> dict:
        """Génère les métadonnées complètes d'un épisode.

        Args:
            script: Script JSON validé.
            duree_secondes: Durée exacte de l'épisode en secondes.

        Returns:
            Dictionnaire de métadonnées.
        """
        episode = script["episode"]

        prompt = (
            f"Génère les métadonnées pour cet épisode :\n"
            f"- Titre : {episode['titre']}\n"
            f"- Saison : {episode['saison']}, Épisode : {episode['numero']}\n"
            f"- Durée : {duree_secondes:.0f} secondes\n"
            f"- Nombre de segments : {len(episode['segments'])}\n"
        )

        morale = episode.get("morale", "")
        if morale:
            prompt += f"- Morale / leçon de vie : {morale}\n"

        prompt += "\nRésumé du contenu (premiers segments) :\n"

        # Ajouter les 5 premiers segments comme contexte
        for seg in episode["segments"][:5]:
            prompt += f"  [{seg['personnage']}] {seg['texte'][:100]}...\n"

        logger.info(
            "Génération des métadonnées : %s (S%02dE%02d)",
            episode["titre"],
            episode["saison"],
            episode["numero"],
        )

        response = config.appel_claude_avec_retry(
            self.client,
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        texte_brut = response.content[0].text.strip()
        meta = parser_json_llm(texte_brut)

        # Enrichir avec les données techniques
        meta["saison"] = episode["saison"]
        meta["numero"] = episode["numero"]
        meta["duree_secondes"] = int(duree_secondes)
        meta["langue"] = config.PODCAST_CONFIG["langue"]
        meta["explicit"] = config.PODCAST_CONFIG["explicit"]

        # Générer le transcript
        meta["transcript"] = self._generer_transcript(episode)

        # Chemin du cover art (si existe — PNG ou JPG)
        episode_id = f"S{episode['saison']:02d}E{episode['numero']:02d}"
        cover_path_png = config.COVERS_DIR / f"{episode_id}_cover.png"
        cover_path_jpg = config.COVERS_DIR / f"{episode_id}_cover.jpg"
        if cover_path_png.exists():
            meta["cover_art_path"] = str(cover_path_png)
        elif cover_path_jpg.exists():
            meta["cover_art_path"] = str(cover_path_jpg)
        else:
            meta["cover_art_path"] = ""

        logger.info("Métadonnées générées : %s", meta["titre"])
        return meta

    def generer_dry_run(self, script: dict) -> dict:
        """Génère des métadonnées sans appel API (mode dry-run).

        Args:
            script: Script JSON validé.

        Returns:
            Métadonnées basiques générées localement.
        """
        episode = script["episode"]
        episode_id = f"S{episode['saison']:02d}E{episode['numero']:02d}"

        # Estimer la durée (exclure les SFX du comptage de mots)
        nb_mots = sum(
            len(s["texte"].split()) for s in episode["segments"]
            if s["personnage"] != "sfx"
        )
        sfx_duree = sum(
            s.get("duree_sfx_secondes", 5.0) for s in episode["segments"]
            if s["personnage"] == "sfx"
        )
        duree_estimee = (nb_mots / 110) * 60 + sfx_duree  # Moyenne + durée SFX

        morale = episode.get("morale", "")

        meta = {
            "titre": f"{episode_id} — {episode['titre']} | Les Histoires de Papy Babou",
            "titre_court": episode["titre"],
            "description_courte": f"Papy Babou raconte : {episode['titre']}. Une histoire biblique pour les enfants.",
            "description_longue": (
                f"Dans cet épisode, Papy Babou raconte à Antoine et Noémie "
                f"l'histoire de {episode['titre']}. "
                f"Rejoignez-les pour découvrir cette belle histoire biblique !"
                + (f"\n\nMorale : {morale}" if morale else "")
            ),
            "tags": ["Histoires bibliques", "Enfants", "Famille"],
            "categories_itunes": ["Kids & Family", "Religion & Spirituality"],
            "sous_categories_itunes": ["Stories for Kids"],
            "cover_art_prompt": f"Illustration pour enfants de l'histoire biblique : {episode['titre']}",
            "cover_art_path": "",
            "saison": episode["saison"],
            "numero": episode["numero"],
            "duree_secondes": int(duree_estimee),
            "langue": config.PODCAST_CONFIG["langue"],
            "explicit": config.PODCAST_CONFIG["explicit"],
            "transcript": self._generer_transcript(episode),
        }

        # Vérifier si un cover art existe (PNG ou JPG)
        cover_path_png = config.COVERS_DIR / f"{episode_id}_cover.png"
        cover_path_jpg = config.COVERS_DIR / f"{episode_id}_cover.jpg"
        if cover_path_png.exists():
            meta["cover_art_path"] = str(cover_path_png)
        elif cover_path_jpg.exists():
            meta["cover_art_path"] = str(cover_path_jpg)

        logger.info("Métadonnées dry-run générées : %s", meta["titre"])
        return meta

    def sauvegarder(self, meta: dict, chemin: Path) -> Path:
        """Sauvegarde les métadonnées en JSON.

        Args:
            meta: Dictionnaire de métadonnées.
            chemin: Chemin du fichier de sortie.

        Returns:
            Chemin du fichier sauvegardé.
        """
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        logger.info("Métadonnées sauvegardées dans %s", chemin)
        return chemin

    @staticmethod
    def _generer_transcript(episode: dict) -> str:
        """Génère un transcript texte à partir du script JSON.

        Args:
            episode: Données de l'épisode.

        Returns:
            Transcript formaté.
        """
        noms_base = {
            "papy_babou": "Papy Babou",
            "antoine": "Antoine",
            "noemie": "Noémie",
            "narrateur": "Narrateur",
        }
        # Enrichir avec les noms depuis la bible des personnages
        bible = config.charger_personnages()
        for key, perso in bible.get("personnages", {}).items():
            if key not in noms_base:
                noms_base[key] = perso.get(
                    "nom_complet", key.replace("_", " ").title()
                )

        lignes = [f"TRANSCRIPT — {episode['titre']}\n"]
        for seg in episode["segments"]:
            if seg["personnage"] == "sfx":
                continue
            nom = noms_base.get(
                seg["personnage"],
                seg["personnage"].replace("_", " ").title(),
            )
            lignes.append(f"[{nom}] {seg['texte']}")
        return "\n\n".join(lignes)
