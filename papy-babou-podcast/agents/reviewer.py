"""Agent Reviewer — Relit et corrige le script avant production audio."""

import json
import logging

import anthropic

import config
from utils import parser_json_llm

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
   - Durée et mots cibles : vérifie selon le type d'épisode indiqué dans le script.
     Référence des formats : {formats_episodes}
   - Comptage : {mots_min_enfant} mots/min pour enfants, {mots_min_adulte} mots/min pour adultes.
   - Format JSON correct et complet ?
   - Les segments SFX (personnage "sfx") sont-ils bien placés et pertinents ?
   - Les bruitages enrichissent-ils l'histoire sans surcharger ? (3-8 SFX max)
   - Chaque segment SFX doit avoir un champ "mode" : "overlay" (superposé aux voix)
     ou "insert" (inséré séquentiellement entre les segments voix).
   - Chaque segment SFX doit avoir un champ "duree_sfx_secondes" (durée en secondes).

FORMAT DE RÉPONSE — JSON STRICT :
{{
  "review": {{
    "score": 8,
    "corrections": [
      "Description de chaque correction effectuée"
    ],
    "alertes": [
      "Points d'attention qui n'ont pas été corrigés automatiquement"
    ],
    "details_score": {{
      "coherence_personnage": 2,
      "adequation_age": 1.5,
      "fidelite_biblique": 2,
      "rythme_structure": 1.5,
      "duree_format": 1
    }}
  }},
  "episode": {{
    "...le script corrigé complet..."
  }}
}}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""


def _construire_system_prompt_reviewer() -> str:
    """Construit le system prompt du reviewer avec les formats synchronisés depuis config."""
    formats_str = ", ".join(
        f"{t} ~{f['mots_cible']} mots/{f['duree_cible_minutes']} min"
        for t, f in config.FORMATS_EPISODES.items()
    )
    return SYSTEM_PROMPT.format(
        formats_episodes=formats_str,
        mots_min_enfant=config.PRODUCTION["mots_par_minute_enfant"],
        mots_min_adulte=config.PRODUCTION["mots_par_minute_adulte"],
    )


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

        system_prompt = _construire_system_prompt_reviewer()

        # max_tokens adaptatif selon le type d'épisode du script
        type_episode = script.get("episode", {}).get("type", "standard")
        max_tokens_map = {
            "ouverture": 7168,
            "standard": 6144,
            "mi-saison": 7168,
            "final": 8192,
            "bonus": 4096,
        }
        max_tokens = max_tokens_map.get(type_episode, 6144)

        response = config.appel_claude_avec_retry(
            self.client,
            model=config.CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        texte_brut = response.content[0].text.strip()
        resultat = parser_json_llm(texte_brut)
        self._valider_review(resultat)

        # Vérifier la cohérence structurelle du script corrigé vs original (BUG 6)
        self._verifier_coherence(script, resultat)

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

        Retourne uniquement les corrections actionnables, pas les alertes
        informatives (qui risquent de créer des boucles infinies).

        Args:
            resultat_review: Résultat de la review.

        Returns:
            Liste de corrections textuelles.
        """
        return list(resultat_review["review"]["corrections"])

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
            personnage = seg["personnage"]
            if personnage == "sfx":
                duree_sec += seg.get("duree_sfx_secondes", 5.0)
                duree_sec += seg.get("pause_apres_ms", 0) / 1000.0
                continue
            nb_mots = len(seg["texte"].split())
            if personnage in ("antoine", "noemie"):
                mots_par_min = config.PRODUCTION["mots_par_minute_enfant"]
            else:
                mots_par_min = config.PRODUCTION["mots_par_minute_adulte"]
            duree_sec += (nb_mots / mots_par_min) * 60
            duree_sec += seg.get("pause_apres_ms", 0) / 1000.0
        return duree_sec / 60.0

    @staticmethod
    def _verifier_coherence(script_original: dict, resultat: dict) -> None:
        """Vérifie que le reviewer n'a pas altéré la structure du script de manière excessive.

        Alerte si le nombre de segments change de plus de 30% ou si des personnages
        principaux ont été supprimés.
        """
        orig_segs = script_original["episode"]["segments"]
        corr_segs = resultat["episode"]["segments"]
        nb_orig = len(orig_segs)
        nb_corr = len(corr_segs)

        if nb_orig > 0:
            ratio = nb_corr / nb_orig
            if ratio < 0.7:
                logger.warning(
                    "Le reviewer a supprimé %.0f%% des segments (%d → %d). "
                    "Vérifiez la cohérence du script corrigé.",
                    (1 - ratio) * 100, nb_orig, nb_corr,
                )
            elif ratio > 1.5:
                logger.warning(
                    "Le reviewer a ajouté %.0f%% de segments (%d → %d). "
                    "La durée de l'épisode pourrait dépasser la cible.",
                    (ratio - 1) * 100, nb_orig, nb_corr,
                )

        # Vérifier que les personnages principaux sont toujours présents
        persos_orig = {s["personnage"] for s in orig_segs if s["personnage"] != "sfx"}
        persos_corr = {s["personnage"] for s in corr_segs if s["personnage"] != "sfx"}
        principaux = {"papy_babou", "antoine", "noemie"}
        disparus = (persos_orig & principaux) - persos_corr
        if disparus:
            logger.warning(
                "Le reviewer a supprimé les personnages principaux : %s. "
                "Ceci est probablement une erreur.",
                ", ".join(disparus),
            )

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

        # Valider la structure de l'épisode corrigé
        from agents.scripteur import Scripteur
        Scripteur._valider_structure({"episode": resultat["episode"]})
