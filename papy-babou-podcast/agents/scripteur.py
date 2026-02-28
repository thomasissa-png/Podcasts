"""Agent Scripteur — Génère le script complet d'un épisode de podcast."""

import json
import logging
from pathlib import Path

import anthropic

import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_BASE = """\
Tu es un scénariste spécialisé dans les podcasts pour enfants de 6 à 10 ans.
Tu écris les scripts du podcast "Les Histoires de Papy Babou".

{bible_personnages}

STRUCTURE NARRATIVE EN 3 ACTES :
1. ACCROCHE (2-3 min) :
   - Scène d'ouverture : Papy Babou accueille les enfants chaleureusement.
   - Il plante le décor de l'histoire avec un élément d'intrigue.
   - Les enfants posent des questions pour lancer le récit.

2. DÉVELOPPEMENT (7-8 min) :
   - Récit principal de l'histoire biblique avec les péripéties.
   - Moments de tension dramatique (bruitages d'ambiance, silences).
   - Les enfants réagissent régulièrement : Antoine sur l'action, Noémie sur l'émotion.
   - Papy explique les mots difficiles avec des analogies adaptées.

3. CONCLUSION (2-3 min) :
   - Résolution de l'histoire.
   - Leçon de vie claire et mémorable pour les enfants.
   - Au revoir chaleureux de Papy Babou.

RÈGLES STRICTES :
1. Le script doit faire environ 1400 mots pour 13 minutes (rythme adapté aux enfants).
2. Les enfants doivent intervenir au moins toutes les 90 secondes de narration (~150-180 mots).
3. Alterner entre Antoine (questions logiques/action) et Noémie (questions émotionnelles).
4. Utiliser les tics de langage de chaque personnage régulièrement.
5. Expliquer les mots ou concepts difficiles avec des analogies simples.
6. L'histoire biblique doit être fidèle au texte original, adaptée aux enfants.
7. Marquer les silences dramatiques avec pause_apres_ms élevé (1500-3000ms).
8. Commencer par une scène où Papy Babou accueille les enfants.
9. Terminer par la leçon de vie spécifiée et un au revoir chaleureux.
10. BRUITAGES : insère des segments avec personnage "sfx" pour enrichir l'ambiance.
    - Le champ "texte" contient une description courte du son en français.
    - Le champ "duree_sfx_secondes" indique la durée souhaitée (2 à 10 secondes).
    - Le champ "mode" indique "overlay" (superposé aux voix suivantes) ou "insert" (séquentiel).
      Utilise "overlay" pour les ambiances de fond (vent, pluie, nature) et "insert" pour les
      effets ponctuels (tonnerre, porte qui claque, cri d'animal).
    - Place les bruitages aux moments clés : entrée des enfants, moments dramatiques,
      transitions de scène, et pour illustrer les éléments de l'histoire.
    - Utilise 3 à 8 bruitages par épisode, pas plus (ne pas surcharger).
11. AMBIANCE MUSICALE : choisis l'ambiance générale de l'épisode parmi :
    "joyeux", "dramatique", "calme", "mystere". Indique-la dans le champ "ambiance" de l'épisode.

MOTS INTERDITS (ne jamais utiliser ces mots, préférer des alternatives douces) :
{mots_interdits}

FORMAT DE SORTIE — JSON STRICT :
{{
  "episode": {{
    "titre": "...",
    "numero": N,
    "saison": N,
    "duree_cible_minutes": 13,
    "ambiance": "joyeux|dramatique|calme|mystere",
    "morale": "La leçon de vie de cet épisode",
    "segments": [
      {{
        "id": "seg_001",
        "personnage": "papy_babou|antoine|noemie|narrateur",
        "texte": "...",
        "ton": "chaleureux|curieux|inquiet|neutre|enthousiaste|dramatique|joyeux|rassurant",
        "pause_apres_ms": 800
      }},
      {{
        "id": "sfx_001",
        "personnage": "sfx",
        "texte": "description courte du bruitage",
        "ton": "ambiance",
        "pause_apres_ms": 300,
        "duree_sfx_secondes": 5.0,
        "mode": "overlay|insert"
      }}
    ]
  }}
}}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""


def _construire_bible_personnages() -> str:
    """Construit la section personnages du prompt à partir de personnages.json."""
    data = config.charger_personnages()
    if not data:
        return _BIBLE_FALLBACK

    personnages = data.get("personnages", {})
    regles = data.get("regles_interaction", {})

    sections = ["PERSONNAGES (bible de référence) :"]
    for key, perso in personnages.items():
        nom = perso.get("nom_complet", key)
        age = perso.get("age", "")
        desc = perso.get("description", "")
        ton = perso.get("ton", "")
        age_str = f", {age} ans" if age else ""

        section = f"- {nom}{age_str} : {desc}\n  Ton : {ton}"

        tics = perso.get("tics_de_langage", [])
        if tics:
            section += f"\n  Tics de langage : {', '.join(repr(t) for t in tics)}"

        vocab = perso.get("vocabulaire_typique", [])
        if vocab:
            section += f"\n  Vocabulaire typique : {', '.join(vocab)}"

        interdictions = perso.get("interdictions", [])
        if interdictions:
            section += f"\n  Interdictions : {'; '.join(interdictions)}"

        reactions = perso.get("reactions_typiques", [])
        if reactions:
            section += f"\n  Réactions typiques : {'; '.join(reactions)}"

        usage = perso.get("usage", [])
        if usage:
            section += f"\n  Usage : {'; '.join(usage)}"

        sections.append(section)

    if regles:
        sections.append("\nRÈGLES D'INTERACTION :")
        for cle, valeur in regles.items():
            sections.append(f"- {cle.replace('_', ' ').title()} : {valeur}")

    return "\n".join(sections)


_BIBLE_FALLBACK = """\
PERSONNAGES :
- Papy Babou : grand-père de 72 ans, ancien instituteur, ton chaleureux et grave.
  Tics de langage : "Ah mes petits loups...", "Figurez-vous que...", "Et devinez quoi ?",
  "Comme disait ma grand-mère...", "C'est pas merveilleux, ça ?", "Attendez, attendez, j'y viens !"
- Antoine : petit-fils de 8 ans, curieux et aventurier, pose des questions d'action.
  Tics : "Mais Papy, pourquoi... ?", "Trop cool !", "Et après ?", "Comme un super-héros ?"
- Noémie : petite-fille de 6 ans, sensible et empathique, s'inquiète pour les personnages.
  Tics : "Oh non, le pauvre...", "Il avait pas peur, Papy ?", "C'est triste, Papy..."
- Narrateur : voix neutre pour les transitions."""


def _construire_system_prompt() -> str:
    """Construit le system prompt complet avec bible et mots interdits."""
    bible = _construire_bible_personnages()
    mots = ", ".join(config.MOTS_INTERDITS)
    return SYSTEM_PROMPT_BASE.format(
        bible_personnages=bible,
        mots_interdits=mots,
    )


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
        morale: str = "",
        corrections: list[str] | None = None,
        historique: list[dict] | None = None,
    ) -> dict:
        """Génère un script JSON structuré pour un épisode.

        Args:
            titre: Titre de l'épisode (ex: "Le buisson ardent").
            resume: Résumé de l'histoire biblique à raconter.
            saison: Numéro de saison.
            numero: Numéro d'épisode dans la saison.
            morale: Leçon de vie à transmettre (optionnel).
            corrections: Liste de corrections du reviewer à intégrer (optionnel).
            historique: Résumés des épisodes précédents pour la continuité (optionnel).

        Returns:
            Dictionnaire JSON du script structuré.
        """
        prompt = (
            f"Écris le script complet de l'épisode suivant :\n"
            f"- Titre : {titre}\n"
            f"- Saison : {saison}, Épisode : {numero}\n"
            f"- Résumé de l'histoire biblique : {resume}\n"
        )

        if morale:
            prompt += f"- Leçon de vie / morale à transmettre : {morale}\n"

        if historique:
            prompt += "\nÉPISODES PRÉCÉDENTS (pour la continuité, tu peux y faire référence) :\n"
            for ep in historique[-5:]:
                prompt += (
                    f"  - {ep.get('episode_id', '?')} \"{ep.get('titre', '?')}\" : "
                    f"{ep.get('resume_court', ep.get('morale', ''))}\n"
                )

        if corrections:
            prompt += (
                "\n⚠️ CORRECTIONS À INTÉGRER (le script précédent avait ces problèmes) :\n"
            )
            for i, c in enumerate(corrections, 1):
                prompt += f"  {i}. {c}\n"
            prompt += "\nCorrige tous ces points dans cette nouvelle version.\n"

        logger.info("Génération du script : %s (S%02dE%02d)", titre, saison, numero)

        system_prompt = _construire_system_prompt()

        response = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
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
        """Compte le nombre total de mots dans le script (hors SFX)."""
        total = 0
        for seg in script["episode"]["segments"]:
            if seg["personnage"] != "sfx":
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

        # Valider les champs optionnels avec avertissement
        if "ambiance" not in ep:
            logger.warning("Champ 'ambiance' manquant — fallback vers 'fond_doux'.")
        elif ep["ambiance"] not in ("joyeux", "dramatique", "calme", "mystere"):
            logger.warning("Ambiance '%s' non reconnue — fallback vers 'fond_doux'.", ep["ambiance"])

        if "morale" not in ep:
            logger.warning("Champ 'morale' manquant dans le script.")

        personnages_valides = {"papy_babou", "antoine", "noemie", "narrateur", "sfx"}
        sfx_count = 0
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
            # Validation spécifique aux segments SFX
            if seg["personnage"] == "sfx":
                sfx_count += 1
                if "duree_sfx_secondes" not in seg:
                    logger.warning(
                        "Champ 'duree_sfx_secondes' manquant dans SFX %s — défaut 5.0s.",
                        seg["id"],
                    )
                if "mode" not in seg:
                    logger.warning(
                        "Champ 'mode' manquant dans SFX %s — défaut 'insert'.",
                        seg["id"],
                    )
                elif seg["mode"] not in ("overlay", "insert"):
                    logger.warning(
                        "Mode SFX '%s' non reconnu dans %s — défaut 'insert'.",
                        seg["mode"], seg["id"],
                    )

        if sfx_count > 8:
            logger.warning("Trop de bruitages : %d (recommandé 3-8).", sfx_count)
        elif sfx_count < 1:
            logger.warning("Aucun bruitage dans le script (recommandé 3-8).")
