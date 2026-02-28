"""Agent Reviewer — Relit et corrige le script avant production audio."""

import json
import logging

import anthropic

import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Tu es un relecteur-correcteur spécialisé dans les contenus pour enfants (6-10 ans).
Tu révises les scripts du podcast "Les Histoires de Papy Babou".

CRITÈRES D'ÉVALUATION (note sur 10) :

1. COHÉRENCE DU PERSONNAGE PAPY BABOU (2 pts)
   - Utilise-t-il ses tics de langage ? ("Ah mes petits loups...", "Figurez-vous que...",
     "Et devinez quoi ?", "Comme disait ma grand-mère...")
   - Ton chaleureux et pédagogue ?
   - Pas d'argot moderne ni de références technologiques ?

2. ADÉQUATION ÂGE 6-10 ANS (2 pts)
   - Les concepts sont-ils expliqués simplement ?
   - Les analogies sont-elles adaptées ?
   - Pas de violence ou de peur excessive ?

3. FIDÉLITÉ BIBLIQUE (2 pts)
   - L'histoire est-elle fidèle au récit biblique original ?
   - Pas de contresens théologiques majeurs ?
   - Les adaptations pour enfants restent-elles cohérentes ?

4. RYTHME ET STRUCTURE (2 pts)
   - Les enfants interviennent-ils régulièrement (toutes les 90 sec max) ?
   - Alternance correcte narration / dialogue / question ?
   - Les pauses sont-elles bien placées ?

5. DURÉE ET FORMAT (2 pts)
   - Environ 1400 mots (~13 min) ?
   - Comptage : 100 mots/min pour enfants, 120 mots/min pour adultes.
   - Format JSON correct et complet ?

FORMAT DE RÉPONSE — JSON STRICT :
{
  "review": {
    "score": 8,
    "corrections": [
      "Description de chaque correction effectuée"
    ],
    "alertes": [
      "Points d'attention qui n'ont pas été corrigés automatiquement"
    ],
    "details_score": {
      "coherence_personnage": 2,
      "adequation_age": 1.5,
      "fidelite_biblique": 2,
      "rythme_structure": 1.5,
      "duree_format": 1
    }
  },
  "episode": {
    "...le script corrigé complet..."
  }
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""


class Reviewer:
    """Relit, évalue et corrige un script avant la production audio."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def evaluer(self, script: dict) -> dict:
        """Évalue et corrige un script.

        Args:
            script: Script JSON structuré (sortie du Scripteur).

        Returns:
            Dictionnaire contenant la review et le script corrigé.
        """
        prompt = (
            "Voici le script à relire et corriger. "
            "Applique toutes les corrections nécessaires et renvoie le résultat "
            "au format JSON demandé.\n\n"
            f"```json\n{json.dumps(script, ensure_ascii=False, indent=2)}\n```"
        )

        logger.info(
            "Relecture du script : %s (S%02dE%02d)",
            script["episode"]["titre"],
            script["episode"]["saison"],
            script["episode"]["numero"],
        )

        response = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        texte_brut = response.content[0].text.strip()

        if texte_brut.startswith("```"):
            lignes = texte_brut.split("\n")
            lignes = [l for l in lignes if not l.startswith("```")]
            texte_brut = "\n".join(lignes)

        resultat = json.loads(texte_brut)
        self._valider_review(resultat)

        score = resultat["review"]["score"]
        nb_corrections = len(resultat["review"]["corrections"])
        nb_alertes = len(resultat["review"]["alertes"])

        logger.info(
            "Review terminée : score %s/10, %d corrections, %d alertes",
            score,
            nb_corrections,
            nb_alertes,
        )

        return resultat

    def est_valide(self, resultat_review: dict, seuil: int = 7) -> bool:
        """Vérifie si le script a obtenu un score suffisant.

        Args:
            resultat_review: Résultat de la review.
            seuil: Score minimum requis (défaut : 7/10).

        Returns:
            True si le score est >= seuil.
        """
        return resultat_review["review"]["score"] >= seuil

    def extraire_corrections(self, resultat_review: dict) -> list[str]:
        """Extrait la liste des corrections à transmettre au Scripteur.

        Args:
            resultat_review: Résultat de la review.

        Returns:
            Liste de corrections textuelles.
        """
        return (
            resultat_review["review"]["corrections"]
            + resultat_review["review"]["alertes"]
        )

    @staticmethod
    def estimer_duree(script: dict) -> float:
        """Estime la durée en minutes du script.

        Utilise 100 mots/min pour les voix enfant et 120 mots/min pour les voix adulte.

        Args:
            script: Script JSON structuré.

        Returns:
            Durée estimée en minutes.
        """
        duree_sec = 0.0
        for seg in script["episode"]["segments"]:
            nb_mots = len(seg["texte"].split())
            personnage = seg["personnage"]
            if personnage in ("antoine", "noemie"):
                mots_par_min = config.PRODUCTION["mots_par_minute_enfant"]
            else:
                mots_par_min = config.PRODUCTION["mots_par_minute_adulte"]
            duree_sec += (nb_mots / mots_par_min) * 60
            duree_sec += seg.get("pause_apres_ms", 0) / 1000.0
        return duree_sec / 60.0

    @staticmethod
    def _valider_review(resultat: dict) -> None:
        """Vérifie la structure du résultat de review."""
        if "review" not in resultat:
            raise ValueError("Le résultat doit contenir une clé 'review'.")
        review = resultat["review"]
        for champ in ("score", "corrections", "alertes"):
            if champ not in review:
                raise ValueError(f"Champ manquant dans review: '{champ}'")
        if not isinstance(review["score"], (int, float)):
            raise ValueError("Le score doit être un nombre.")
        if "episode" not in resultat:
            raise ValueError("Le résultat doit contenir le script corrigé sous 'episode'.")
