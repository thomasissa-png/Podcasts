"""Agent Métadonnées — Génère toutes les métadonnées pour la distribution."""

import json
import logging
from pathlib import Path

import anthropic

import config

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
  "sous_categories_itunes": ["Stories for Kids"]
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
            f"- Nombre de segments : {len(episode['segments'])}\n\n"
            f"Résumé du contenu (premiers segments) :\n"
        )

        # Ajouter les 5 premiers segments comme contexte
        for seg in episode["segments"][:5]:
            prompt += f"  [{seg['personnage']}] {seg['texte'][:100]}...\n"

        logger.info(
            "Génération des métadonnées : %s (S%02dE%02d)",
            episode["titre"],
            episode["saison"],
            episode["numero"],
        )

        response = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        texte_brut = response.content[0].text.strip()
        if texte_brut.startswith("```"):
            lignes = texte_brut.split("\n")
            lignes = [l for l in lignes if not l.startswith("```")]
            texte_brut = "\n".join(lignes)

        meta = json.loads(texte_brut)

        # Enrichir avec les données techniques
        meta["saison"] = episode["saison"]
        meta["numero"] = episode["numero"]
        meta["duree_secondes"] = int(duree_secondes)
        meta["langue"] = config.PODCAST_CONFIG["langue"]
        meta["explicit"] = config.PODCAST_CONFIG["explicit"]

        # Générer le transcript
        meta["transcript"] = self._generer_transcript(episode)

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

        # Estimer la durée
        nb_mots = sum(len(s["texte"].split()) for s in episode["segments"])
        duree_estimee = (nb_mots / 110) * 60  # Moyenne entre adulte et enfant

        meta = {
            "titre": f"{episode_id} — {episode['titre']} | Les Histoires de Papy Babou",
            "titre_court": episode["titre"],
            "description_courte": f"Papy Babou raconte : {episode['titre']}. Une histoire biblique pour les enfants.",
            "description_longue": (
                f"Dans cet épisode, Papy Babou raconte à Antoine et Noémie "
                f"l'histoire de {episode['titre']}. "
                f"Rejoignez-les pour découvrir cette belle histoire biblique !"
            ),
            "tags": ["Histoires bibliques", "Enfants", "Famille"],
            "categories_itunes": ["Kids & Family", "Religion & Spirituality"],
            "sous_categories_itunes": ["Stories for Kids"],
            "saison": episode["saison"],
            "numero": episode["numero"],
            "duree_secondes": int(duree_estimee),
            "langue": config.PODCAST_CONFIG["langue"],
            "explicit": config.PODCAST_CONFIG["explicit"],
            "transcript": self._generer_transcript(episode),
        }
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
        noms = {
            "papy_babou": "Papy Babou",
            "antoine": "Antoine",
            "noemie": "Noémie",
            "narrateur": "Narrateur",
        }
        lignes = [f"TRANSCRIPT — {episode['titre']}\n"]
        for seg in episode["segments"]:
            nom = noms.get(seg["personnage"], seg["personnage"])
            lignes.append(f"[{nom}] {seg['texte']}")
        return "\n\n".join(lignes)
