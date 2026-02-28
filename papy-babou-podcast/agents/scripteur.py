"""Agent Scripteur — Génère le script complet d'un épisode de podcast.

Supporte la production sérielle : contexte de saison, previously-on,
teasing, rituels, personnages dynamiques, et types d'épisodes variables.
"""

import json
import logging
from pathlib import Path

import anthropic

import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_BASE = """\
Tu es un scénariste spécialisé dans les podcasts SÉRIELS pour enfants de 6 à 10 ans.
Tu écris les scripts du podcast "Les Histoires de Papy Babou".
Ce podcast fonctionne par SAISONS de 10 épisodes avec un arc narratif continu.

{bible_personnages}

{contexte_serie}

STRUCTURE NARRATIVE :
{structure_narrative}

RÈGLES STRICTES :
1. Le script doit faire environ {mots_cible} mots pour {duree_cible} minutes (rythme adapté aux enfants).
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
{regles_personnages_dynamiques}

MOTS INTERDITS (ne jamais utiliser ces mots, préférer des alternatives douces) :
{mots_interdits}

FORMAT DE SORTIE — JSON STRICT :
{{
  "episode": {{
    "titre": "...",
    "numero": N,
    "saison": N,
    "duree_cible_minutes": {duree_cible},
    "ambiance": "joyeux|dramatique|calme|mystere",
    "morale": "La leçon de vie de cet épisode",
    "personnages_presents": ["papy_babou", "antoine", "noemie"],
    "moments_cles": ["Moment important 1", "Moment important 2"],
    "segments": [
      {{
        "id": "seg_001",
        "personnage": "{personnages_format}",
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

# ── Structure narrative par type d'épisode ───────────────────────────────────

STRUCTURES_NARRATIVES = {
    "ouverture": """\
1. ACCROCHE DE SAISON (3-4 min) :
   - Scène d'ouverture : Papy Babou présente le THÈME de la nouvelle saison.
   - Il crée l'excitation : "Cette saison, on va découvrir ensemble..."
   - Les enfants réagissent au thème avec enthousiasme et curiosité.
   - {ritual_accroche}

2. DÉVELOPPEMENT (8-9 min) :
   - Première histoire biblique de la saison, qui pose les bases du thème.
   - Présentation des enjeux de la saison.
   - Les enfants posent des questions qui ouvrent sur les épisodes suivants.

3. CONCLUSION + TEASING (3-4 min) :
   - Résolution de la première histoire.
   - Leçon de vie inaugurale.
   - Papy tease la prochaine histoire avec mystère.
   - {ritual_au_revoir}""",

    "standard": """\
1. ACCROCHE (2-3 min) :
   - {previously_on}
   - Scène d'ouverture : Papy Babou accueille les enfants chaleureusement.
   - {ritual_accroche}
   - Il plante le décor de l'histoire avec un élément d'intrigue.

2. DÉVELOPPEMENT (7-8 min) :
   - Récit principal de l'histoire biblique avec les péripéties.
   - Moments de tension dramatique (bruitages d'ambiance, silences).
   - Les enfants réagissent régulièrement : Antoine sur l'action, Noémie sur l'émotion.
   - Papy explique les mots difficiles avec des analogies adaptées.
   - {segment_recurrent}

3. CONCLUSION + TEASING (2-3 min) :
   - Résolution de l'histoire.
   - Leçon de vie claire et mémorable pour les enfants.
   - {teasing}
   - {ritual_au_revoir}""",

    "mi-saison": """\
1. RÉCAPITULATIF + ACCROCHE (3-4 min) :
   - {previously_on}
   - Papy rappelle le fil rouge de la saison : ce qu'on a appris jusqu'ici.
   - {ritual_accroche}
   - Les enfants font le point sur ce qu'ils ont retenu.

2. DÉVELOPPEMENT — TOURNANT (8-9 min) :
   - Histoire biblique qui représente un TOURNANT dans le thème de la saison.
   - Moment de surprise ou de révélation pour les enfants.
   - Approfondissement du thème central.
   - {segment_recurrent}

3. CONCLUSION + OUVERTURE (3-4 min) :
   - La résolution ouvre de nouvelles questions.
   - Leçon de vie qui fait évoluer la compréhension du thème.
   - {teasing}
   - {ritual_au_revoir}""",

    "final": """\
1. GRAND RÉCAPITULATIF (3-4 min) :
   - {previously_on}
   - Papy rappelle toutes les histoires de la saison et leurs leçons.
   - {ritual_accroche}
   - Les enfants montrent combien ils ont grandi au fil de la saison.

2. DÉVELOPPEMENT — CLIMAX (10-11 min) :
   - Dernière histoire biblique qui conclut le thème de la saison.
   - Moment émotionnel fort : les personnages montrent leur évolution.
   - Résolution de toutes les questions ouvertes de la saison.
   - {segment_recurrent}

3. CONCLUSION DE SAISON (3-4 min) :
   - Grande leçon de vie qui résume toute la saison.
   - Moment d'émotion entre Papy et les enfants.
   - Au revoir spécial de fin de saison.
   - Éventuel teasing de la prochaine saison (si applicable).""",

    "bonus": """\
1. ACCROCHE SPÉCIALE (2 min) :
   - Papy annonce un épisode spécial / bonus.
   - {ritual_accroche}

2. CONTENU SPÉCIAL (6-7 min) :
   - Questions-réponses des enfants, coulisses, ou récapitulatif.
   - Ton plus léger et interactif.

3. CONCLUSION (2 min) :
   - Au revoir décontracté.
   - {ritual_au_revoir}""",
}


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


def _construire_contexte_serie(contexte_saison: dict | None = None) -> str:
    """Construit la section contexte sériel du prompt.

    Args:
        contexte_saison: Données du plan de saison (optionnel).

    Returns:
        Texte de contexte sériel pour le system prompt.
    """
    if not contexte_saison:
        return "CONTEXTE : Épisode indépendant (pas de contexte de saison)."

    sections = ["CONTEXTE DE LA SAISON :"]

    saison = contexte_saison.get("saison", {})
    if saison:
        sections.append(f"- Thème de la saison : {saison.get('theme', '?')}")
        sections.append(f"- Description : {saison.get('description', '')}")
        sections.append(f"- Fil rouge : {saison.get('fil_rouge', '')}")

    # Arcs de personnages
    arcs = saison.get("arcs_personnages", {})
    if arcs:
        sections.append("\nARCS DE PERSONNAGES CETTE SAISON :")
        for perso, arc in arcs.items():
            nom = perso.replace("_", " ").title()
            sections.append(
                f"  - {nom} : de \"{arc.get('depart', '')}\" "
                f"vers \"{arc.get('arrivee', '')}\" "
                f"(évolution : {arc.get('evolution', '')})"
            )

    return "\n".join(sections)


def _construire_structure_narrative(
    type_episode: str,
    contexte_saison: dict | None = None,
    episode_plan: dict | None = None,
    historique: list[dict] | None = None,
) -> str:
    """Construit la structure narrative adaptée au type d'épisode.

    Args:
        type_episode: Type d'épisode (ouverture, standard, mi-saison, final, bonus).
        contexte_saison: Données du plan de saison.
        episode_plan: Données de l'épisode dans le plan de saison.
        historique: Historique des épisodes précédents.
    """
    template = STRUCTURES_NARRATIVES.get(type_episode, STRUCTURES_NARRATIVES["standard"])

    # Rituels
    rituels = {}
    if contexte_saison:
        rituels = contexte_saison.get("saison", {}).get("rituels", {})

    ritual_accroche = (
        f"Utilise la phrase d'accroche récurrente : \"{rituels['accroche']}\""
        if rituels.get("accroche")
        else "Papy Babou accueille les enfants chaleureusement."
    )
    ritual_au_revoir = (
        f"Utilise la formule de clôture récurrente : \"{rituels['au_revoir']}\""
        if rituels.get("au_revoir")
        else "Au revoir chaleureux de Papy Babou."
    )
    segment_recurrent = (
        f"Intègre le segment récurrent de la saison : \"{rituels['segment_recurrent']}\""
        if rituels.get("segment_recurrent")
        else ""
    )

    # Previously On
    previously_on = ""
    if historique and len(historique) > 0:
        dernier = historique[-1]
        previously_on = (
            f"PREVIOUSLY ON : Papy rappelle brièvement l'épisode précédent "
            f"\"{dernier.get('titre', '?')}\" et sa leçon "
            f"({dernier.get('morale', '?')})."
        )
        if dernier.get("questions_ouvertes"):
            questions = dernier["questions_ouvertes"]
            if isinstance(questions, list) and questions:
                previously_on += f" Reprends la question ouverte : \"{questions[0]}\""
            elif isinstance(questions, str):
                previously_on += f" Reprends la question ouverte : \"{questions}\""
    if not previously_on:
        previously_on = "Scène d'ouverture directe (premier épisode ou pas de contexte précédent)."

    # Teasing
    teasing = ""
    if episode_plan and episode_plan.get("teasing_episode_suivant"):
        teasing = (
            f"TEASING : Papy tease la prochaine histoire : "
            f"\"{episode_plan['teasing_episode_suivant']}\""
        )
    elif type_episode != "final":
        teasing = "Papy donne un avant-goût mystérieux de la prochaine histoire."

    return template.format(
        ritual_accroche=ritual_accroche,
        ritual_au_revoir=ritual_au_revoir,
        segment_recurrent=segment_recurrent,
        previously_on=previously_on,
        teasing=teasing,
    )


def _construire_system_prompt(
    contexte_saison: dict | None = None,
    episode_plan: dict | None = None,
    type_episode: str = "standard",
    historique: list[dict] | None = None,
) -> str:
    """Construit le system prompt complet avec bible, contexte sériel et mots interdits.

    Args:
        contexte_saison: Plan de saison complet (optionnel).
        episode_plan: Données de l'épisode dans le plan de saison.
        type_episode: Type d'épisode.
        historique: Historique des épisodes précédents.
    """
    bible = _construire_bible_personnages()
    mots = ", ".join(config.MOTS_INTERDITS)
    contexte_serie = _construire_contexte_serie(contexte_saison)
    structure = _construire_structure_narrative(
        type_episode, contexte_saison, episode_plan, historique,
    )

    # Format d'épisode
    format_ep = config.FORMATS_EPISODES.get(type_episode, config.FORMATS_EPISODES["standard"])
    duree_cible = format_ep["duree_cible_minutes"]
    mots_cible = format_ep["mots_cible"]

    # Personnages dynamiques
    personnages_connus = config.personnages_valides()
    personnages_voix = sorted(p for p in personnages_connus if p != "sfx")
    personnages_format = "|".join(personnages_voix)
    regles_dyn = ""
    extra_persos = personnages_connus - {"papy_babou", "antoine", "noemie", "narrateur", "sfx"}
    if extra_persos:
        regles_dyn = (
            "\n12. PERSONNAGES SECONDAIRES disponibles cette saison : "
            + ", ".join(sorted(extra_persos))
            + ".\n    N'utilise un personnage secondaire QUE s'il est mentionné dans les "
            "personnages présents de cet épisode."
        )

    return SYSTEM_PROMPT_BASE.format(
        bible_personnages=bible,
        mots_interdits=mots,
        contexte_serie=contexte_serie,
        structure_narrative=structure,
        duree_cible=duree_cible,
        mots_cible=mots_cible,
        personnages_format=personnages_format,
        regles_personnages_dynamiques=regles_dyn,
    )


class Scripteur:
    """Génère le script complet d'un épisode à partir d'un pitch.

    Supporte la production sérielle avec contexte de saison, previously-on,
    teasing, et personnages dynamiques.
    """

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
        contexte_saison: dict | None = None,
        episode_plan: dict | None = None,
        type_episode: str = "standard",
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
            contexte_saison: Plan de saison complet pour le contexte sériel (optionnel).
            episode_plan: Données de l'épisode depuis le plan de saison (optionnel).
            type_episode: Type d'épisode (ouverture, standard, mi-saison, final, bonus).

        Returns:
            Dictionnaire JSON du script structuré.
        """
        # Déterminer le type d'épisode depuis le plan si disponible
        if episode_plan and type_episode == "standard":
            type_episode = episode_plan.get("type", "standard")

        format_ep = config.FORMATS_EPISODES.get(type_episode, config.FORMATS_EPISODES["standard"])
        nb_episodes_saison = 10
        if contexte_saison:
            nb_episodes_saison = len(
                contexte_saison.get("saison", {}).get("episodes", [])
            ) or 10

        prompt = (
            f"Écris le script complet de l'épisode suivant :\n"
            f"- Titre : {titre}\n"
            f"- Saison : {saison}, Épisode : {numero}/{nb_episodes_saison}\n"
            f"- Type d'épisode : {type_episode} ({format_ep['description']})\n"
            f"- Durée cible : {format_ep['duree_cible_minutes']} minutes (~{format_ep['mots_cible']} mots)\n"
            f"- Résumé de l'histoire biblique : {resume}\n"
        )

        if morale:
            prompt += f"- Leçon de vie / morale à transmettre : {morale}\n"

        # Contexte sériel depuis le plan d'épisode
        if episode_plan:
            if episode_plan.get("arc_personnage_focus"):
                prompt += (
                    f"- Arc de personnage en focus : {episode_plan['arc_personnage_focus']}\n"
                    f"  Progression : {episode_plan.get('progression_arc', '')}\n"
                )
            if episode_plan.get("elements_fil_rouge"):
                prompt += f"- Éléments du fil rouge à intégrer : {episode_plan['elements_fil_rouge']}\n"
            if episode_plan.get("personnages_secondaires_presents"):
                prompt += (
                    f"- Personnages secondaires présents : "
                    f"{', '.join(episode_plan['personnages_secondaires_presents'])}\n"
                )
            if episode_plan.get("lien_episode_precedent"):
                prompt += f"- Lien avec l'épisode précédent : {episode_plan['lien_episode_precedent']}\n"
            if episode_plan.get("questions_ouvertes"):
                questions = episode_plan["questions_ouvertes"]
                if isinstance(questions, list):
                    prompt += f"- Questions ouvertes à laisser en suspens : {'; '.join(questions)}\n"

        if historique:
            prompt += "\nÉPISODES PRÉCÉDENTS (pour la continuité, fais-y référence) :\n"
            for ep in historique[-5:]:
                ep_info = (
                    f"  - {ep.get('episode_id', '?')} \"{ep.get('titre', '?')}\" : "
                    f"{ep.get('resume_court', ep.get('morale', ''))}"
                )
                if ep.get("moments_cles"):
                    cles = ep["moments_cles"]
                    if isinstance(cles, list):
                        ep_info += f" | Moments clés : {', '.join(cles[:2])}"
                if ep.get("evolutions_personnages"):
                    ep_info += f" | Évolutions : {ep['evolutions_personnages']}"
                prompt += ep_info + "\n"

        if corrections:
            prompt += (
                "\n⚠️ CORRECTIONS À INTÉGRER (le script précédent avait ces problèmes) :\n"
            )
            for i, c in enumerate(corrections, 1):
                prompt += f"  {i}. {c}\n"
            prompt += "\nCorrige tous ces points dans cette nouvelle version.\n"

        logger.info(
            "Génération du script : %s (S%02dE%02d, type=%s)",
            titre, saison, numero, type_episode,
        )

        system_prompt = _construire_system_prompt(
            contexte_saison=contexte_saison,
            episode_plan=episode_plan,
            type_episode=type_episode,
            historique=historique,
        )

        response = config.appel_claude_avec_retry(
            self.client,
            model=config.CLAUDE_MODEL,
            max_tokens=6144,
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

        personnages_ok = config.personnages_valides()
        sfx_count = 0
        for seg in ep["segments"]:
            for champ in ("id", "personnage", "texte", "ton", "pause_apres_ms"):
                if champ not in seg:
                    raise ValueError(
                        f"Champ manquant dans segment {seg.get('id', '?')}: '{champ}'"
                    )
            if seg["personnage"] not in personnages_ok:
                raise ValueError(
                    f"Personnage inconnu '{seg['personnage']}' dans segment {seg['id']}. "
                    f"Valides : {personnages_ok}"
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
