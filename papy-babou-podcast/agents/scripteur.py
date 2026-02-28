"""Agent Scripteur — Génère le script complet d'un épisode de podcast."""

import json
import logging
from pathlib import Path

import anthropic

import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Tu es un scénariste spécialisé dans les podcasts pour enfants de 6 à 10 ans.
Tu écris les scripts du podcast "Les Histoires de Papy Babou".

PERSONNAGES :
- Papy Babou : grand-père de 72 ans, ancien instituteur, ton chaleureux et grave.
  Tics de langage : "Ah mes petits loups...", "Figurez-vous que...", "Et devinez quoi ?",
  "Comme disait ma grand-mère...", "C'est pas merveilleux, ça ?", "Attendez, attendez, j'y viens !"
- Antoine : petit-fils de 8 ans, curieux et aventurier, pose des questions d'action.
  Tics : "Mais Papy, pourquoi... ?", "Trop cool !", "Et après ?", "Comme un super-héros ?"
- Noémie : petite-fille de 6 ans, sensible et empathique, s'inquiète pour les personnages.
  Tics : "Oh non, le pauvre...", "Il avait pas peur, Papy ?", "C'est triste, Papy..."
- Narrateur : voix neutre pour les transitions.

RÈGLES STRICTES :
1. Le script doit faire environ 1400 mots pour 13 minutes (rythme adapté aux enfants).
2. Les enfants doivent intervenir au moins toutes les 90 secondes de narration (~150-180 mots).
3. Alterner entre Antoine (questions logiques/action) et Noémie (questions émotionnelles).
4. Utiliser les tics de langage de chaque personnage régulièrement.
5. Expliquer les mots ou concepts difficiles avec des analogies simples.
6. L'histoire biblique doit être fidèle au texte original, adaptée aux enfants.
7. Marquer les silences dramatiques avec pause_apres_ms élevé (1500-3000ms).
8. Commencer par une scène où Papy Babou accueille les enfants.
9. Terminer par une leçon de vie simple et un au revoir chaleureux.

FORMAT DE SORTIE — JSON STRICT :
{
  "episode": {
    "titre": "...",
    "numero": N,
    "saison": N,
    "duree_cible_minutes": 13,
    "segments": [
      {
        "id": "seg_001",
        "personnage": "papy_babou|antoine|noemie|narrateur",
        "texte": "...",
        "ton": "chaleureux|curieux|inquiet|neutre|enthousiaste|dramatique|joyeux|rassurant",
        "pause_apres_ms": 800
      }
    ]
  }
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""


class Scripteur:
    """Génère le script complet d'un épisode à partir d'un pitch."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def generer(
        self,
        titre: str,
        resume: str,
        saison: int,
        numero: int,
        corrections: list[str] | None = None,
    ) -> dict:
        """Génère un script JSON structuré pour un épisode.

        Args:
            titre: Titre de l'épisode (ex: "Le buisson ardent").
            resume: Résumé de l'histoire biblique à raconter.
            saison: Numéro de saison.
            numero: Numéro d'épisode dans la saison.
            corrections: Liste de corrections du reviewer à intégrer (optionnel).

        Returns:
            Dictionnaire JSON du script structuré.
        """
        prompt = (
            f"Écris le script complet de l'épisode suivant :\n"
            f"- Titre : {titre}\n"
            f"- Saison : {saison}, Épisode : {numero}\n"
            f"- Résumé de l'histoire biblique : {resume}\n"
        )

        if corrections:
            prompt += (
                "\n⚠️ CORRECTIONS À INTÉGRER (le script précédent avait ces problèmes) :\n"
            )
            for i, c in enumerate(corrections, 1):
                prompt += f"  {i}. {c}\n"
            prompt += "\nCorrige tous ces points dans cette nouvelle version.\n"

        logger.info("Génération du script : %s (S%02dE%02d)", titre, saison, numero)

        response = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        texte_brut = response.content[0].text.strip()

        # Extraire le JSON même si Claude ajoute des backticks
        if texte_brut.startswith("```"):
            lignes = texte_brut.split("\n")
            lignes = [l for l in lignes if not l.startswith("```")]
            texte_brut = "\n".join(lignes)

        script = json.loads(texte_brut)
        self._valider_structure(script)

        logger.info(
            "Script généré : %d segments, ~%d mots",
            len(script["episode"]["segments"]),
            self.compter_mots(script),
        )

        return script

    def sauvegarder(self, script: dict, chemin: Path) -> Path:
        """Sauvegarde le script JSON sur disque.

        Args:
            script: Script structuré.
            chemin: Chemin du fichier de sortie.

        Returns:
            Chemin du fichier sauvegardé.
        """
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
        logger.info("Script sauvegardé dans %s", chemin)
        return chemin

    @staticmethod
    def compter_mots(script: dict) -> int:
        """Compte le nombre total de mots dans le script."""
        total = 0
        for seg in script["episode"]["segments"]:
            total += len(seg["texte"].split())
        return total

    @staticmethod
    def _valider_structure(script: dict) -> None:
        """Vérifie que le script a la structure attendue."""
        if "episode" not in script:
            raise ValueError("Le script JSON doit contenir une clé 'episode'.")
        ep = script["episode"]
        for champ in ("titre", "numero", "saison", "segments"):
            if champ not in ep:
                raise ValueError(f"Champ manquant dans episode: '{champ}'")
        if not ep["segments"]:
            raise ValueError("Le script ne contient aucun segment.")
        personnages_valides = {"papy_babou", "antoine", "noemie", "narrateur"}
        for seg in ep["segments"]:
            for champ in ("id", "personnage", "texte", "ton", "pause_apres_ms"):
                if champ not in seg:
                    raise ValueError(
                        f"Champ manquant dans segment {seg.get('id', '?')}: '{champ}'"
                    )
            if seg["personnage"] not in personnages_valides:
                raise ValueError(
                    f"Personnage inconnu '{seg['personnage']}' dans segment {seg['id']}. "
                    f"Valides : {personnages_valides}"
                )
