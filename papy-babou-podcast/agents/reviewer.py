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

CRITÈRES D'ÉVALUATION (note sur 12, ramenée à 10) :

1. COHÉRENCE DU PERSONNAGE PAPY BABOU (2 pts)
   - Utilise-t-il ses tics de langage ? ("Ah mes petits loups...", "Figurez-vous que...",
     "Et devinez quoi ?", "Comme disait ma grand-mère...") — au moins 3 différents
   - Ton chaleureux et pédagogue ?
   - Pas d'argot moderne ni de références technologiques ?

2. ADÉQUATION ÂGE 6-10 ANS (2 pts)
   - Les concepts sont-ils expliqués simplement ?
   - Les analogies sont-elles adaptées au quotidien d'un enfant ?
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

6. CRÉATIVITÉ NARRATIVE (2 pts)
   - L'épisode suit-il un arc émotionnel clair (curiosité → tension → climax → résolution) ?
   - Y a-t-il au moins un moment de SURPRISE ou RÉVÉLATION inattendue ?
   - Les questions des enfants font-elles avancer l'histoire (pas juste décoratives) ?
   - Les dialogues sont-ils naturels et spontanés (répliques courtes, hésitations) ?
   - Si un fil rouge de saison est indiqué, progresse-t-il visiblement ?
   - Le SFX enrichit-il l'émotion (pas juste l'ambiance) ?

Le score final = somme des 6 critères, ramenée sur 10 (diviser par 1.2).

FORMAT DE RÉPONSE — JSON STRICT :
{{
  "review": {{
    "score": 8,
    "corrections": [
      {{
        "priorite": "critique|majeur|mineur",
        "texte": "Description de la correction effectuée"
      }}
    ],
    "alertes": [
      "Points d'attention qui n'ont pas été corrigés automatiquement"
    ],
    "details_score": {{
      "coherence_personnage": 2,
      "adequation_age": 1.5,
      "fidelite_biblique": 2,
      "rythme_structure": 1.5,
      "duree_format": 1,
      "creativite_narrative": 1.5
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
        if not config.ANTHROPIC_API_KEY:
            raise ValueError(
                "Cle API Anthropic (ANTHROPIC_API_KEY) non configuree. "
                "Ajoutez-la dans votre fichier .env ou dans les Secrets Replit."
            )
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

        if response.stop_reason == "max_tokens":
            raise ValueError(
                f"La review a été tronquée (max_tokens={max_tokens} atteint). "
                f"Le JSON est incomplet."
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

    # Seuils adaptatifs par type d'épisode — les épisodes pivots exigent plus
    SEUILS_PAR_TYPE = {
        "ouverture": 8,
        "standard": 7,
        "mi-saison": 8,
        "final": 8,
        "bonus": 6,
    }

    def est_valide(self, resultat_review: dict, seuil: int | None = None) -> bool:
        """Vérifie si le script a obtenu un score suffisant.

        Le seuil est adaptatif par type d'épisode : ouverture/mi-saison/final
        exigent un score ≥ 8, standard ≥ 7, bonus ≥ 6.

        Args:
            resultat_review: Résultat de la review.
            seuil: Score minimum requis (None = adaptatif par type d'épisode).

        Returns:
            True si le score est >= seuil.
        """
        if seuil is None:
            type_ep = resultat_review.get("episode", {}).get("type", "standard")
            seuil = self.SEUILS_PAR_TYPE.get(type_ep, 7)
        return resultat_review["review"]["score"] >= seuil

    def extraire_corrections(self, resultat_review: dict) -> list[str]:
        """Extrait la liste des corrections à transmettre au Scripteur.

        Retourne uniquement les corrections actionnables, pas les alertes
        informatives (qui risquent de créer des boucles infinies).
        Les corrections critiques et majeures sont placées en premier.

        Args:
            resultat_review: Résultat de la review.

        Returns:
            Liste de corrections textuelles.
        """
        corrections = resultat_review["review"]["corrections"]
        # Support ancien format (liste de strings) et nouveau (liste de dicts)
        if corrections and isinstance(corrections[0], dict):
            # Trier par priorité : critique > majeur > mineur
            ordre = {"critique": 0, "majeur": 1, "mineur": 2}
            corrections = sorted(corrections, key=lambda c: ordre.get(c.get("priorite", "mineur"), 2))
            return [c["texte"] for c in corrections]
        return list(corrections)

    @staticmethod
    def verifier_mots_interdits(script: dict) -> list[str]:
        """Vérifie que le script ne contient aucun mot interdit.

        Vérification post-génération indépendante du LLM.

        Args:
            script: Script JSON structuré.

        Returns:
            Liste des violations trouvées (vide si OK).
        """
        violations = []
        for seg in script["episode"]["segments"]:
            if seg["personnage"] == "sfx":
                continue
            texte_lower = seg["texte"].lower()
            for mot in config.MOTS_INTERDITS:
                # Chercher le mot comme mot complet (pas en sous-chaîne)
                import re
                if re.search(r"\b" + re.escape(mot) + r"\b", texte_lower):
                    violations.append(
                        f"Mot interdit '{mot}' dans segment {seg['id']} "
                        f"({seg['personnage']})"
                    )
        return violations

    @staticmethod
    def verifier_questions_ouvertes(
        script: dict, historique: list[dict] | None = None
    ) -> list[str]:
        """Vérifie si les questions ouvertes de l'épisode précédent sont reprises.

        Args:
            script: Script JSON structuré.
            historique: Historique des épisodes précédents.

        Returns:
            Liste d'alertes (vide si OK ou pas d'historique).
        """
        alertes = []
        if not historique:
            return alertes

        dernier = historique[-1]
        questions = dernier.get("questions_ouvertes", [])
        if not questions:
            return alertes

        # Vérifier qu'au moins une question est mentionnée dans les segments
        texte_complet = " ".join(
            seg["texte"].lower()
            for seg in script["episode"]["segments"]
            if seg["personnage"] != "sfx"
        )
        question_reprise = False
        for q in (questions if isinstance(questions, list) else [questions]):
            # Chercher des mots-clés de la question dans le texte
            mots_cles = [m for m in q.lower().split() if len(m) > 4]
            if mots_cles and sum(1 for m in mots_cles if m in texte_complet) >= len(mots_cles) // 2:
                question_reprise = True
                break

        if not question_reprise and questions:
            q_str = questions[0] if isinstance(questions, list) else questions
            alertes.append(
                f"La question ouverte de l'épisode précédent n'est pas reprise : "
                f"'{q_str[:80]}...'"
            )
        return alertes

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
        # Normaliser les corrections en format structuré si nécessaire
        if review["corrections"] and isinstance(review["corrections"][0], str):
            review["corrections"] = [
                {"priorite": "majeur", "texte": c} for c in review["corrections"]
            ]
        if "episode" not in resultat:
            raise ValueError("Le résultat doit contenir le script corrigé sous 'episode'.")

        # Valider la structure de l'épisode corrigé
        from agents.scripteur import Scripteur
        Scripteur._valider_structure({"episode": resultat["episode"]})
