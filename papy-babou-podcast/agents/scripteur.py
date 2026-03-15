"""Agent Scripteur — Génère le script complet d'un épisode de podcast.

Supporte la production sérielle : contexte de saison, previously-on,
teasing, rituels, personnages dynamiques, et types d'épisodes variables.
"""

import json
import logging
from pathlib import Path

import anthropic

import config
from utils import parser_json_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_BASE = """\
Tu es un scénariste spécialisé dans les podcasts SÉRIELS pour enfants de 6 à 10 ans.
Tu écris les scripts du podcast "Les Histoires de Papy Babou".
Ce podcast fonctionne par séries de 10 épisodes avec un arc narratif continu.

IMMERSION ET NATUREL :
Le podcast est une SCÈNE DE VIE entre un grand-père et ses petits-enfants. Tout doit
être naturel, comme si on écoutait une vraie conversation familiale.
- PAS DE NARRATEUR : il n'y a pas de voix off. C'est Papy Babou qui raconte, explique,
  décrit les lieux et fait les transitions. Les descriptions de contexte historique ou
  géographique passent par SA voix, dans son style chaleureux.
- JAMAIS de langage méta : ne JAMAIS utiliser les mots "saison", "épisode", "podcast",
  "série" dans les dialogues. Ces concepts n'existent pas dans l'univers des personnages.
- Chaque épisode commence par un PRÉTEXTE NATUREL qui amène l'histoire. Exemples :
  * Les enfants viennent dormir chez Papy → histoire du soir
  * Il pleut, on est coincés à la maison → "Tiens, je vais vous raconter..."
  * Promenade dans la nature → un élément du paysage rappelle une histoire à Papy
  * Les enfants trouvent un vieux livre ou objet → Papy raconte l'histoire liée
  * Repas de famille, goûter → la conversation dérive vers une histoire
  * Un événement du quotidien (dispute, peur, courage) → Papy fait le parallèle avec une histoire biblique
  Le prétexte doit varier d'un épisode à l'autre pour garder la fraîcheur.

{bible_personnages}

{contexte_serie}

STRUCTURE NARRATIVE :
{structure_narrative}

RÈGLE FONDAMENTALE — CONTENU ÉDUCATIF :
Ce podcast est AVANT TOUT éducatif. L'objectif principal est que les enfants APPRENNENT
l'histoire biblique en détail. Le script doit consacrer AU MINIMUM 60% de son contenu
au récit biblique lui-même : les événements, les personnages bibliques, les lieux, les dialogues,
les péripéties, les anecdotes, le contexte historique et géographique.
- Papy Babou RACONTE l'histoire en détail, avec des descriptions vivantes et des dialogues reconstitués.
- Il inclut des ANECDOTES concrètes et des détails marquants (nombres, lieux, noms, objets, coutumes).
- Les interventions des enfants doivent FAIRE AVANCER le récit (poser des questions sur la suite,
  réagir à un événement, demander une précision) et NON le ralentir avec du bavardage hors-sujet.
- Chaque épisode doit couvrir l'INTÉGRALITÉ de l'histoire annoncée, pas juste une introduction.
- À la fin de l'épisode, l'auditeur doit pouvoir résumer les événements clés de l'histoire biblique.

RÈGLES STRICTES :
1. Le script doit faire environ {mots_cible} mots pour {duree_cible} minutes (rythme adapté aux enfants).
   C'est un MINIMUM — ne pas faire plus court. Développe le récit biblique en profondeur.
2. Les enfants doivent intervenir au moins toutes les 90 secondes de narration (~150-180 mots).
   Leurs interventions doivent être PERTINENTES à l'histoire (questions, réactions, demandes de précision).
3. Alterner entre Antoine (le grand frère, questions logiques/action, veut faire comme les grands,
   langage de garçon de 8 ans) et Noémie (la petite sœur, chipie, blagues, parfois peureuse,
   langage plus simple adapté à une enfant de 5 ans). Noémie parle avec un vocabulaire plus
   limité, des phrases plus courtes, et fait parfois des erreurs de prononciation mignonnes.
4. Utiliser les tics de langage de chaque personnage régulièrement.
5. Expliquer les mots ou concepts difficiles avec des analogies simples.
6. L'histoire biblique doit être fidèle au texte original, adaptée aux enfants.
   Inclure un MAXIMUM de détails narratifs : dialogues des personnages bibliques, descriptions
   des lieux, contexte historique, péripéties secondaires, conséquences des événements.
7. PAUSES NATURELLES : les transitions entre personnages doivent être fluides.
    - Réplique conversationnelle rapide (enchaînement naturel) : pause_apres_ms = 150-300
    - Pause normale (changement de sujet, respiration) : pause_apres_ms = 400-600
    - Pause dramatique (révélation, suspense) : pause_apres_ms = 800-1500
    - Long silence dramatique (rare, 1-2 par épisode max) : pause_apres_ms = 1500-2500
    La MAJORITÉ des segments doivent avoir 150-400ms de pause pour un rythme naturel.
8. Commencer par une scène de vie naturelle avec un PRÉTEXTE qui amène l'histoire
   (voir la section IMMERSION ET NATUREL ci-dessus). Ne JAMAIS commencer par "Bienvenue dans..."
   ou tout autre format de podcast. C'est une conversation, pas une émission.
9. Terminer par la leçon de vie spécifiée et un au revoir chaleureux et naturel.
   Ne JAMAIS dire "à la prochaine saison" ou "dans le prochain épisode". Préférer :
   "La prochaine fois que vous viendrez...", "Un jour je vous raconterai...", "On en reparlera..."
10. BRUITAGES : insère des segments avec personnage "sfx" pour enrichir l'ambiance.
    - Le champ "texte" contient une description courte du son EN ANGLAIS (pour l'API de génération).
      Exemples : "door creaking open slowly", "birds singing in morning sun", "thunder rumbling".
    - Le champ "duree_sfx_secondes" indique la durée souhaitée (2 à 10 secondes).
    - Le champ "mode" indique "overlay" (superposé aux voix suivantes) ou "insert" (séquentiel).
      Utilise "overlay" pour les ambiances de fond (vent, pluie, nature) et "insert" pour les
      effets ponctuels (tonnerre, porte qui claque, cri d'animal).
    - Place les bruitages aux moments clés : entrée des enfants, moments dramatiques,
      transitions de scène, et pour illustrer les éléments de l'histoire.
    - OBLIGATOIRE : au minimum 8 bruitages par épisode, maximum 12. Chaque acte doit avoir
      au moins 2 bruitages. Privilégie les bruitages "insert" pour les moments d'action, et
      "overlay" pour les ambiances de fond.
    - Exemples de bruitages contextuels :
      * Entrée des enfants : "children's footsteps running, door opening"
      * Scène en extérieur : "gentle wind blowing through trees, birds chirping"
      * Moment dramatique : "deep thunder in the distance"
      * Transition de scène : "soft magical chime, page turning"
      * Scène de repas : "gentle clinking of dishes, pouring water"
11. AMBIANCE MUSICALE : choisis l'ambiance générale de l'épisode parmi :
    "joyeux", "dramatique", "calme", "mystere", "epique", "tendre", "humoristique", "solennel".
    Indique-la dans le champ "ambiance" de l'épisode.
    Guide : "epique" pour les batailles et exodes, "tendre" pour les moments familiaux,
    "humoristique" pour les épisodes légers, "solennel" pour les scènes sacrées.
    AMBIANCE DYNAMIQUE : fournis le champ "ambiance_par_acte" (liste de 3 ambiances) pour
    varier la musique de fond selon l'acte. Ex : ["calme", "dramatique", "tendre"].
    C'est FORTEMENT RECOMMANDÉ pour enrichir l'expérience sonore.
    Si absent, l'ambiance principale s'applique uniformément à tout l'épisode.
12. ARC ÉMOTIONNEL : chaque épisode doit suivre une courbe émotionnelle claire :
    curiosité → montée en tension → climax → résolution → morale apaisante.
    Varie l'intensité des émotions. Place au moins un moment de SURPRISE ou RÉVÉLATION.
13. DIALOGUES NATURELS : les répliques des enfants doivent être courtes (1-2 phrases max),
    spontanées, avec parfois des hésitations ("Euh...", "Attends..."). Antoine et Noémie
    interagissent aussi ENTRE EUX, pas seulement avec Papy. Utilise au moins 3 tics de
    langage différents par personnage par épisode.
14. BACKSTORY DE PAPY : Papy Babou (vrai prénom Jean-Pierre) est né à Dakar au Sénégal,
    a grandi au Liban (où il a rencontré Sonia dans les abris pendant la guerre), puis a vécu
    en Afrique du Sud et en Suisse avant de s'installer en Normandie. Très courageux, très fort,
    gourmand (adore la viande et le café). Il peut faire référence à son vécu personnel pour
    enrichir le récit ("Quand j'étais petit à Dakar...", "Au Liban, pendant la guerre...",
    "Mamie Sonia me disait justement...", "Quand on vivait en Afrique du Sud...").
    BACKSTORY DE SONIA : Mamie Sonia est née au Caire en Égypte, partie au Liban bébé où
    elle a rencontré Jean-Pierre. Architecte d'intérieur de métier, cuisinière exceptionnelle.
    Elle peut enrichir l'histoire de commentaires tendres ou d'anecdotes de cuisine/voyage.
{regles_personnages_dynamiques}
INSTRUCTIONS CRÉATIVES :
- VÉRACITÉ BIBLIQUE : ne JAMAIS inventer de détails non-bibliques dans le récit lui-même.
  Adapter le langage et simplifier, oui. Inventer des événements ou personnages bibliques, non.
  Seuls les dialogues de la scène de vie (Papy, enfants) sont libres.
- TRAITS OBLIGATOIRES par épisode : au moins 1 moment chipie/blague de Noémie (elle embête
  Antoine ou fait rire), au moins 1 moment de bravoure/enthousiasme d'Antoine (il veut faire
  comme les héros), au moins 1 anecdote personnelle de Papy liée à son vécu.
- ANTI-RÉPÉTITION SFX : ne pas réutiliser les mêmes descriptions de bruitages d'un épisode
  à l'autre. Varier les ambiances sonores. Chaque bruitage doit être unique et contextuel.
- PÉDAGOGIE : quand un nom ou concept biblique important apparaît, le répéter au moins 3 fois
  dans l'épisode (par Papy puis par les enfants qui le reformulent). Les enfants doivent
  reformuler ce qu'ils comprennent dans leurs mots ("Ah, donc c'est comme si...").
- SPATIALISATION : exploiter le décor de la maison normande dans les scènes de vie. Noémie
  sur les genoux de Papy dans le grand fauteuil, Antoine assis par terre, le chat qui ronronne,
  l'horloge qui sonne, les bruits de cuisine de mamie Sonia. Ces détails rendent la scène vivante.
- MIROIRS D'ÂGE : Antoine et Noémie ne comprennent PAS les choses de la même façon. Antoine
  pose des questions de logique ("Mais comment il a fait ?"), Noémie pose des questions
  d'émotion ("Il avait pas peur ?"). Papy adapte ses explications à chacun.
{evenement_special}

MOTS INTERDITS (ne jamais utiliser ces mots, préférer des alternatives douces) :
{mots_interdits}
{preferences_producteur}
FORMAT DE SORTIE — JSON STRICT :
{{
  "episode": {{
    "titre": "...",
    "numero": N,
    "saison": N,
    "duree_cible_minutes": {duree_cible},
    "ambiance": "joyeux|dramatique|calme|mystere|epique|tendre|humoristique|solennel",
    "ambiance_par_acte": ["calme", "dramatique", "tendre"],
    "morale": "La leçon de vie de cet épisode",
    "personnages_presents": ["papy_babou", "antoine", "noemie"],
    "moments_cles": ["Moment important 1", "Moment important 2"],
    "evolutions_personnages": "Résumé en 1-2 phrases de comment les personnages ont évolué dans cet épisode (émotions, apprentissages, relations).",
    "segments": [
      {{
        "id": "seg_001",
        "personnage": "{personnages_format}",
        "texte": "...",
        "ton": "chaleureux|curieux|inquiet|neutre|enthousiaste|dramatique|joyeux|rassurant|triste|chuchotant|excite|mystérieux|solennel|espiègle|émerveillé|effrayé",
        "rythme": "normal|rapide|lent",
        "pause_apres_ms": 250
      }},
      {{
        "id": "sfx_001",
        "personnage": "sfx",
        "texte": "gentle wind blowing through olive trees",
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
1. ACCROCHE NATURELLE (4-5 min) :
   - Scène de vie : un prétexte naturel amène les enfants chez Papy (ou Papy chez eux).
   - Quelque chose éveille la curiosité des enfants et Papy commence à raconter.
   - Les enfants réagissent avec enthousiasme et curiosité.
   - {ritual_accroche}

2. DÉVELOPPEMENT — RÉCIT BIBLIQUE DÉTAILLÉ (20-22 min) :
   - Première grande histoire biblique, racontée EN PROFONDEUR par Papy Babou.
   - Papy raconte avec des détails vivants : lieux, personnages, dialogues reconstitués.
   - Il inclut des anecdotes historiques et géographiques (ex: "À cette époque, en Mésopotamie...").
   - Les péripéties sont développées une par une, pas résumées.
   - Les enfants réagissent aux moments clés et posent des questions qui approfondissent le récit.
   - L'histoire ouvre naturellement sur d'autres histoires à venir.
{running_gag}

3. CONCLUSION (4-5 min) :
   - Résolution de l'histoire.
   - Leçon de vie que Papy tire naturellement du récit.
   - Papy laisse entendre qu'il a d'autres histoires à raconter ("La prochaine fois...").
   - {ritual_au_revoir}""",

    "standard": """\
1. ACCROCHE (3-4 min) :
   - {previously_on}
   - Scène de vie : un prétexte naturel amène l'histoire (goûter, pluie, promenade, coucher...).
   - {ritual_accroche}
   - Papy plante le décor de l'histoire avec un élément d'intrigue.

2. DÉVELOPPEMENT — RÉCIT BIBLIQUE DÉTAILLÉ (17-19 min) :
   - Récit principal de l'histoire biblique raconté EN PROFONDEUR et en détail par Papy Babou.
   - Papy raconte les événements un par un, avec des descriptions vivantes des lieux et personnages.
   - Il reconstitue les DIALOGUES des personnages bibliques (ex: "Et Dieu dit à Abraham...").
   - Il ajoute des détails historiques et géographiques qui enrichissent le récit.
   - Les péripéties sont développées, pas résumées en une phrase.
   - Moments de tension dramatique (bruitages d'ambiance, silences).
   - Les enfants réagissent aux moments clés : Antoine sur l'action, Noémie sur l'émotion.
   - Leurs questions font AVANCER l'histoire ("Et après, qu'est-ce qui s'est passé ?").
   - Papy explique les mots difficiles avec des analogies adaptées.
   - {segment_recurrent}
{running_gag}

3. CONCLUSION (3-4 min) :
   - Résolution de l'histoire.
   - Leçon de vie claire et mémorable pour les enfants.
   - {teasing}
   - {ritual_au_revoir}""",

    "mi-saison": """\
1. ACCROCHE (4-5 min) :
   - {previously_on}
   - Scène de vie naturelle. Les enfants font naturellement le lien avec les histoires précédentes.
   - {ritual_accroche}
   - Les enfants se souviennent de ce qu'ils ont appris et veulent en savoir plus.

2. DÉVELOPPEMENT — TOURNANT BIBLIQUE DÉTAILLÉ (20-22 min) :
   - Histoire biblique qui représente un tournant important dans le thème abordé.
   - Le récit est raconté EN PROFONDEUR avec tous les détails narratifs par Papy Babou.
   - Dialogues reconstitués, descriptions des lieux, contexte historique.
   - Moment de surprise ou de révélation pour les enfants.
   - Approfondissement du thème central à travers les détails de l'histoire.
   - {segment_recurrent}
{running_gag}

3. CONCLUSION (4-5 min) :
   - La résolution ouvre de nouvelles questions.
   - Leçon de vie que Papy tire naturellement du récit.
   - {teasing}
   - {ritual_au_revoir}""",

    "final": """\
1. ACCROCHE ÉMOTIONNELLE (4-5 min) :
   - {previously_on}
   - Scène de vie avec un prétexte spécial (moment intime, occasion particulière).
   - Les enfants montrent naturellement combien ils ont grandi grâce aux histoires.
   - {ritual_accroche}

2. DÉVELOPPEMENT — CLIMAX BIBLIQUE DÉTAILLÉ (24-26 min) :
   - Dernière grande histoire biblique du thème, racontée EN PROFONDEUR par Papy Babou.
   - Le récit est le plus développé : détails, dialogues, péripéties secondaires.
   - Moment émotionnel fort : les personnages montrent leur évolution.
   - Résolution de toutes les questions ouvertes des histoires précédentes.
   - {segment_recurrent}
{running_gag}

3. CONCLUSION CHALEUREUSE (4-5 min) :
   - Grande leçon de vie que Papy tire de toutes les histoires racontées.
   - Moment d'émotion entre Papy et les enfants.
   - Au revoir tendre, avec l'idée que d'autres histoires viendront un jour.""",

    "bonus": """\
1. ACCROCHE SPÉCIALE (3 min) :
   - Prétexte naturel pour un moment un peu différent (jeu, devinettes, retour sur les histoires).
   - {ritual_accroche}

2. CONTENU SPÉCIAL (14-15 min) :
   - Questions-réponses des enfants, coulisses, ou récapitulatif.
   - Si récapitulatif : revenir sur les histoires avec des détails supplémentaires.
   - Ton plus léger et interactif.
{running_gag}

3. CONCLUSION (3 min) :
   - Au revoir décontracté.
   - {ritual_au_revoir}""",
}


def _construire_bible_personnages(numero_saison: int = 1) -> str:
    """Construit la section personnages du prompt à partir de personnages.json.

    Args:
        numero_saison: Numéro de saison en cours (pour la progression d'âge).
    """
    data = config.charger_personnages()
    if not data:
        return _BIBLE_FALLBACK

    personnages = data.get("personnages", {})
    regles = data.get("regles_interaction", {})

    sections = ["PERSONNAGES (bible de référence) :"]
    for key, perso in personnages.items():
        # Pas de narrateur — tout passe par Papy Babou
        if key == "narrateur":
            continue
        nom = perso.get("nom_complet", key)
        # Progression d'âge via config.age_personnage (extrapolation si absent)
        age = config.age_personnage(key, numero_saison) or perso.get("age", "")
        desc = perso.get("description", "")
        ton = perso.get("ton", "")
        role = perso.get("role", "principal")
        age_str = f", {age} ans" if age else ""

        section = f"- {nom}{age_str} ({role}) : {desc}\n  Ton : {ton}"

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

        # Backstory et famille — enrichissement narratif
        backstory = perso.get("backstory", "")
        if backstory:
            section += f"\n  Backstory : {backstory}"

        famille = perso.get("famille", {})
        if famille:
            liens = []
            for lien, membres in famille.items():
                if isinstance(membres, list):
                    liens.append(f"{lien}: {', '.join(membres)}")
                else:
                    liens.append(f"{lien}: {membres}")
            section += f"\n  Famille : {'; '.join(liens)}"

        anecdotes = perso.get("anecdotes_possibles", [])
        if anecdotes:
            section += f"\n  Anecdotes possibles : {'; '.join(anecdotes)}"

        # Relations entre personnages
        for rel_key in ("relation_avec_papy", "relation_avec_noemie",
                        "relation_avec_antoine"):
            rel = perso.get(rel_key, "")
            if rel:
                qui = rel_key.replace("relation_avec_", "").replace("_", " ").title()
                section += f"\n  Relation avec {qui} : {rel}"

        # Personnages secondaires — infos spécifiques
        premiere = perso.get("premiere_apparition", "")
        if premiere:
            section += f"\n  Première apparition : {premiere}"

        frequence = perso.get("frequence", "")
        if frequence:
            section += f"\n  Fréquence : {frequence}"

        interventions = perso.get("interventions_typiques", [])
        if interventions:
            section += f"\n  Interventions typiques : {'; '.join(interventions)}"

        # Règles spéciales (ex: Lucas fil rouge)
        regles_perso = perso.get("regles", [])
        if regles_perso:
            section += f"\n  RÈGLES STRICTES : {'; '.join(regles_perso)}"

        sections.append(section)

    if regles:
        sections.append("\nRÈGLES D'INTERACTION :")
        for cle, valeur in regles.items():
            sections.append(f"- {cle.replace('_', ' ').title()} : {valeur}")

    return "\n".join(sections)


_BIBLE_FALLBACK = """\
PERSONNAGES :
- Papy Babou : grand-père de 66 ans, né à Dakar, grand voyageur (Liban, Afrique du Sud, Suisse), ton chaleureux et grave.
  Tics de langage : "Ah mes petits loups...", "Figurez-vous que...", "Et devinez quoi ?",
  "Comme disait ma grand-mère...", "C'est pas merveilleux, ça ?", "Attendez, attendez, j'y viens !"
  Backstory : Gourmand, très courageux et fort, père de Thomas et Nathalie, marié à mamie Sonia.
- Antoine : petit-fils de 8 ans, curieux et aventurier, fait du judo et du football.
  Tics : "Mais Papy, pourquoi... ?", "Trop cool !", "Et après ?", "Comme un super-héros ?"
- Noémie : petite-fille de 5 ans, chipie avec un très gros caractère, espiègle et rigolote.
  Tics : "Oh non, le pauvre...", "Hihihi ! C'est trop drôle !", "Babouuuu ! Encore une histoire !"
- Mamie Sonia : épouse de Papy, 65 ans, née en Égypte, architecte d'intérieur, cuisine divinement.
  Apparitions légères : goûter, coucher, commentaire tendre depuis la cuisine."""


def _construire_contexte_serie(contexte_saison: dict | None = None) -> str:
    """Construit la section contexte sériel du prompt.

    Args:
        contexte_saison: Données du plan de saison (optionnel).

    Returns:
        Texte de contexte sériel pour le system prompt.
    """
    if not contexte_saison:
        return "CONTEXTE : Épisode indépendant (pas de contexte de saison)."

    sections = ["CONTEXTE DE LA SÉRIE D'HISTOIRES :"]

    saison = contexte_saison.get("saison", {})
    if saison:
        sections.append(f"- Thème principal : {saison.get('theme', '?')}")
        sections.append(f"- Description : {saison.get('description', '')}")
        sections.append(f"- Fil rouge : {saison.get('fil_rouge', '')}")

    # Arcs de personnages
    arcs = saison.get("arcs_personnages", {})
    if arcs:
        sections.append("\nARCS DE PERSONNAGES :")
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
        f"Intègre le segment récurrent : \"{rituels['segment_recurrent']}\""
        if rituels.get("segment_recurrent")
        else ""
    )
    # Running gag de la saison
    running_gag = ""
    if rituels.get("running_gag"):
        running_gag = (
            f"   - RUNNING GAG : intègre naturellement le gag récurrent : "
            f"\"{rituels['running_gag']}\""
        )

    # Previously On — rappel naturel de l'histoire précédente
    previously_on = ""
    if historique and len(historique) > 0:
        dernier = historique[-1]
        previously_on = (
            f"RAPPEL NATUREL : Papy ou les enfants font naturellement référence à "
            f"l'histoire précédente \"{dernier.get('titre', '?')}\" et sa leçon "
            f"({dernier.get('morale', '?')}). Le rappel doit être conversationnel, "
            f"pas un résumé formel (ex: \"Vous vous souvenez de...\" ou un enfant qui dit "
            f"\"Papy, c'est comme dans l'histoire de...\")."
        )
        if dernier.get("questions_ouvertes"):
            questions = dernier["questions_ouvertes"]
            if isinstance(questions, list) and questions:
                previously_on += f" Reprends la question ouverte : \"{questions[0]}\""
            elif isinstance(questions, str):
                previously_on += f" Reprends la question ouverte : \"{questions}\""
    if not previously_on:
        previously_on = "Scène d'ouverture directe (premier épisode ou pas de contexte précédent)."

    # Inject character arc starting states for first episode of season
    if (not historique or len(historique) == 0) and contexte_saison:
        arcs = contexte_saison.get("saison", {}).get("arcs_personnages", {})
        if arcs:
            arc_lines = ["\nÉTATS INITIAUX DES PERSONNAGES :"]
            for perso, arc in arcs.items():
                nom = perso.replace("_", " ").title()
                depart = arc.get("depart", "")
                if depart:
                    arc_lines.append(
                        f"  - {nom} commence dans l'état : \"{depart}\". "
                        f"Montre cet état dans ses réactions et dialogues."
                    )
            if len(arc_lines) > 1:
                previously_on += "\n" + "\n".join(arc_lines)

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
        running_gag=running_gag,
        previously_on=previously_on,
        teasing=teasing,
    )


def _construire_system_prompt(
    contexte_saison: dict | None = None,
    episode_plan: dict | None = None,
    type_episode: str = "standard",
    historique: list[dict] | None = None,
    preferences_producteur: str = "",
    numero_saison: int = 1,
    numero_episode: int = 0,
) -> str:
    """Construit le system prompt complet avec bible, contexte sériel et mots interdits.

    Args:
        contexte_saison: Plan de saison complet (optionnel).
        episode_plan: Données de l'épisode dans le plan de saison.
        type_episode: Type d'épisode.
        historique: Historique des épisodes précédents.
        preferences_producteur: Bloc de préférences du producteur à injecter.
        numero_saison: Numéro de saison (pour progression d'âge).
        numero_episode: Numéro d'épisode dans la saison (pour événements spéciaux).
    """
    bible = _construire_bible_personnages(numero_saison=numero_saison)
    mots = ", ".join(config.MOTS_INTERDITS)
    contexte_serie = _construire_contexte_serie(contexte_saison)
    structure = _construire_structure_narrative(
        type_episode, contexte_saison, episode_plan, historique,
    )

    # Format d'épisode
    format_ep = config.FORMATS_EPISODES.get(type_episode, config.FORMATS_EPISODES["standard"])
    duree_cible = format_ep["duree_cible_minutes"]
    mots_cible = format_ep["mots_cible"]

    # Personnages dynamiques (pas de narrateur — tout passe par Papy Babou)
    personnages_connus = config.personnages_valides()
    personnages_voix = sorted(p for p in personnages_connus if p not in ("sfx", "narrateur"))
    personnages_format = "|".join(personnages_voix)
    regles_dyn = ""
    extra_persos = personnages_connus - {"papy_babou", "antoine", "noemie", "narrateur", "sfx"}
    if extra_persos:
        regles_dyn = (
            "\nPERSONNAGES SECONDAIRES disponibles : "
            + ", ".join(sorted(extra_persos))
            + ".\n    N'utilise un personnage secondaire QUE s'il est mentionné dans les "
            "personnages présents de cet épisode."
        )

    # Événement spécial (anniversaire, etc.)
    evenement = config.EVENEMENTS_SPECIAUX.get((numero_saison, numero_episode), {})
    evenement_special = ""
    if evenement:
        evenement_special = (
            f"\nÉVÉNEMENT SPÉCIAL — {evenement['type'].upper()} :\n"
            f"{evenement['details']}"
        )

    # Échapper les accolades dans les valeurs textuelles libres
    # pour éviter un crash de str.format() (KeyError/ValueError)
    safe_preferences = preferences_producteur.replace("{", "{{").replace("}", "}}")
    safe_bible = bible.replace("{", "{{").replace("}", "}}")
    safe_mots = mots.replace("{", "{{").replace("}", "}}")

    return SYSTEM_PROMPT_BASE.format(
        bible_personnages=safe_bible,
        mots_interdits=safe_mots,
        contexte_serie=contexte_serie,
        structure_narrative=structure,
        duree_cible=duree_cible,
        mots_cible=mots_cible,
        personnages_format=personnages_format,
        regles_personnages_dynamiques=regles_dyn,
        preferences_producteur=safe_preferences,
        evenement_special=evenement_special,
    )


class Scripteur:
    """Génère le script complet d'un épisode à partir d'un pitch.

    Supporte la production sérielle avec contexte de saison, previously-on,
    teasing, et personnages dynamiques.
    """

    def __init__(self):
        if not config.ANTHROPIC_API_KEY:
            raise ValueError(
                "Cle API Anthropic (ANTHROPIC_API_KEY) non configuree. "
                "Ajoutez-la dans votre fichier .env ou dans les Secrets Replit."
            )
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    @staticmethod
    def _construire_user_prompt(
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
        format_ep: dict | None = None,
        scripts_precedents: list[dict] | None = None,
        arc_state_precedent: dict | None = None,
    ) -> str:
        """Construit le user prompt pour la génération de script.

        Args:
            titre: Titre de l'épisode.
            resume: Résumé de l'histoire biblique.
            saison: Numéro de saison.
            numero: Numéro d'épisode.
            morale: Leçon de vie (optionnel).
            corrections: Corrections du reviewer (optionnel).
            historique: Épisodes précédents (optionnel).
            contexte_saison: Plan de saison (optionnel).
            episode_plan: Données de l'épisode (optionnel).
            type_episode: Type d'épisode.
            format_ep: Format de l'épisode (durée, mots cible).
            scripts_precedents: Dialogues des scripts précédents (optionnel).
            arc_state_precedent: État narratif de l'épisode N-1 (optionnel).

        Returns:
            Texte du user prompt.
        """
        if format_ep is None:
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

        # Événement spécial (anniversaire, etc.)
        evenement = config.EVENEMENTS_SPECIAUX.get((saison, numero), {})
        if evenement:
            prompt += (
                f"\n🎉 ÉVÉNEMENT SPÉCIAL — {evenement['type'].upper()} :\n"
                f"{evenement['details']}\n"
            )

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

        # Arc state de l'épisode précédent (continuité N→N+1) — CRITIQUE
        if arc_state_precedent:
            prompt += "\n🔗 ÉTAT NARRATIF DE L'ÉPISODE PRÉCÉDENT (continuité obligatoire) :\n"
            moments = arc_state_precedent.get("moments_cles", [])
            if moments:
                prompt += f"  Moments clés : {', '.join(moments[:5])}\n"
            questions = arc_state_precedent.get("questions_ouvertes", [])
            if questions:
                prompt += "  Questions ouvertes à reprendre naturellement :\n"
                for q in questions[:3]:
                    prompt += f"    - {q}\n"
            evolution = arc_state_precedent.get("evolutions_personnages", "")
            if evolution:
                prompt += f"  Évolutions des personnages : {evolution}\n"
            fil_rouge = arc_state_precedent.get("fil_rouge", "")
            if fil_rouge:
                prompt += f"  Fil rouge : {fil_rouge}\n"
            prompt += (
                "  → Tu DOIS faire référence à au moins un de ces éléments dans les "
                "premières minutes de l'épisode pour assurer la continuité narrative.\n"
            )

        if historique:
            # Pour les épisodes finaux/mi-saison, inclure tout l'historique de la saison
            if type_episode in ("final", "mi-saison"):
                eps_a_inclure = [
                    ep for ep in historique
                    if ep.get("episode_id", "").startswith(f"S{saison:02d}")
                ]
                if not eps_a_inclure:
                    eps_a_inclure = historique[-5:]
            else:
                eps_a_inclure = historique[-5:]
            prompt += "\nÉPISODES PRÉCÉDENTS (pour la continuité, fais-y référence) :\n"
            for ep in eps_a_inclure:
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
                if ep.get("retours_humains"):
                    ep_info += f" | Retours producteur : {ep['retours_humains']}"
                prompt += ep_info + "\n"

        # Injecter les dialogues réels des épisodes précédents de la saison
        if scripts_precedents:
            prompt += (
                "\n📖 SCRIPTS DES ÉPISODES PRÉCÉDENTS DE CETTE SAISON "
                "(lis attentivement pour assurer la continuité des dialogues, "
                "du ton, des personnages et des arcs narratifs) :\n"
            )
            for sp in scripts_precedents:
                prompt += f"\n--- {sp['episode_id']} \"{sp['titre']}\" "
                if sp.get("ambiance"):
                    prompt += f"(ambiance: {sp['ambiance']}) "
                prompt += f"({sp['nb_segments']} segments) ---\n"
                dialogues = sp.get("dialogues", [])
                is_dernier = (sp == scripts_precedents[-1])
                max_lignes = 20 if is_dernier else 10
                for ligne in dialogues[:max_lignes]:
                    prompt += f"  {ligne}\n"
                if len(dialogues) > max_lignes:
                    prompt += f"  [...{len(dialogues) - max_lignes} lignes supplémentaires...]\n"
            prompt += "\n"

        if corrections:
            prompt += (
                "\n⚠️ CORRECTIONS À INTÉGRER (le script précédent avait ces problèmes) :\n"
            )
            for i, c in enumerate(corrections, 1):
                prompt += f"  {i}. {c}\n"
            prompt += "\nCorrige tous ces points dans cette nouvelle version.\n"

        return prompt

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
        preferences_producteur: str = "",
        scripts_precedents: list[dict] | None = None,
        arc_state_precedent: dict | None = None,
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
            preferences_producteur: Bloc de preferences du producteur a injecter.
            scripts_precedents: Dialogues des scripts précédents de la saison pour
                assurer la continuité (optionnel). Chaque élément contient episode_id,
                titre, ambiance, nb_segments et dialogues (liste de lignes).
            arc_state_precedent: État narratif de l'épisode précédent (moments clés,
                questions ouvertes, évolutions) pour assurer la continuité N→N+1.

        Returns:
            Dictionnaire JSON du script structuré.
        """
        # Déterminer le type d'épisode depuis le plan si disponible
        if episode_plan and type_episode == "standard":
            type_episode = episode_plan.get("type", "standard")

        format_ep = config.FORMATS_EPISODES.get(type_episode, config.FORMATS_EPISODES["standard"])

        prompt = self._construire_user_prompt(
            titre=titre,
            resume=resume,
            saison=saison,
            numero=numero,
            morale=morale,
            corrections=corrections,
            historique=historique,
            contexte_saison=contexte_saison,
            episode_plan=episode_plan,
            type_episode=type_episode,
            format_ep=format_ep,
            scripts_precedents=scripts_precedents,
            arc_state_precedent=arc_state_precedent,
        )

        logger.info(
            "Génération du script : %s (S%02dE%02d, type=%s)",
            titre, saison, numero, type_episode,
        )

        system_prompt = _construire_system_prompt(
            contexte_saison=contexte_saison,
            episode_plan=episode_plan,
            type_episode=type_episode,
            historique=historique,
            preferences_producteur=preferences_producteur,
            numero_saison=saison,
            numero_episode=numero,
        )

        # max_tokens adaptatif selon le type d'épisode
        max_tokens = 12000 if type_episode == "bonus" else 16384

        # Tentative avec retry automatique si la réponse est tronquée
        max_retry_truncated = 2
        for attempt in range(1, max_retry_truncated + 1):
            response = config.appel_claude_avec_retry(
                self.client,
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

            if response.stop_reason == "max_tokens":
                if attempt < max_retry_truncated:
                    max_tokens = min(int(max_tokens * 1.5), 32768)
                    logger.warning(
                        "Réponse tronquée (max_tokens atteint). "
                        "Retry %d/%d avec max_tokens=%d",
                        attempt, max_retry_truncated, max_tokens,
                    )
                    continue
                else:
                    raise ValueError(
                        f"Le script généré dépasse la limite de tokens "
                        f"({max_tokens} tokens) même après {max_retry_truncated} "
                        f"tentatives. Le JSON est tronqué et inutilisable."
                    )
            break

        # Protection contre une réponse vide
        if not response.content:
            raise ValueError(
                "La réponse de l'API Claude est vide (aucun bloc de contenu). "
                "Vérifiez la configuration de l'appel API."
            )

        texte_brut = response.content[0].text.strip()
        try:
            script = parser_json_llm(texte_brut)
        except json.JSONDecodeError as e:
            logger.warning(
                "JSON malformé dans la réponse LLM (%s). "
                "Retry avec instruction JSON explicite...", e,
            )
            # Retry avec un message supplémentaire pour guider le LLM
            response = config.appel_claude_avec_retry(
                self.client,
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "Je vais générer le script en JSON valide."},
                    {"role": "user", "content": "Réponds UNIQUEMENT en JSON valide, sans texte avant ni après. Commence directement par {"},
                ],
            )
            if response.stop_reason == "max_tokens":
                raise ValueError(
                    f"Le script généré dépasse la limite de tokens "
                    f"({max_tokens} tokens). Le JSON est tronqué et inutilisable."
                )
            if not response.content:
                raise ValueError("La réponse de l'API Claude est vide après retry JSON.")
            texte_brut = response.content[0].text.strip()
            script = parser_json_llm(texte_brut)

        # Type-check : le LLM doit retourner un dict, pas une liste ou un scalaire
        if not isinstance(script, dict):
            raise ValueError(
                f"Le JSON retourné par le LLM n'est pas un objet (type: {type(script).__name__}). "
                f"Attendu : un dictionnaire avec une clé 'episode'."
            )

        self._valider_structure(script)

        # Inject type_episode into script so reviewer can read it
        # Valider et auto-corriger le type si le LLM a généré un type invalide
        valid_types = {"ouverture", "standard", "mi-saison", "final", "bonus"}
        ep_type = script.get("episode", {}).get("type", "")
        if ep_type not in valid_types:
            if ep_type:
                logger.warning("Type épisode invalide '%s' généré par le LLM — corrigé à '%s'",
                               ep_type, type_episode)
            script.setdefault("episode", {})["type"] = type_episode

        # Vérifier l'utilisation des tics de langage par personnage
        self._verifier_tics_de_langage(script)

        # Vérifier les mots interdits dans le texte généré
        self._verifier_mots_interdits(script)

        nb_mots = self.compter_mots(script)
        mots_cible = format_ep["mots_cible"]
        logger.info(
            "Script généré : %d segments, ~%d mots (cible : %d)",
            len(script["episode"]["segments"]),
            nb_mots, mots_cible,
        )

        # Validation post-génération du nombre de mots
        ratio = nb_mots / mots_cible if mots_cible > 0 else 1.0
        if ratio < 0.5:
            logger.warning(
                "Script trop court : %d mots (cible %d, ratio %.0f%%). "
                "Le reviewer devrait demander une réécriture.",
                nb_mots, mots_cible, ratio * 100,
            )
        elif ratio > 1.5:
            logger.warning(
                "Script trop long : %d mots (cible %d, ratio %.0f%%). "
                "La durée réelle dépassera la cible.",
                nb_mots, mots_cible, ratio * 100,
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
    def _verifier_tics_de_langage(script: dict) -> None:
        """Vérifie que chaque personnage principal utilise ses tics de langage.

        Émet un warning si un personnage a moins de 2 tics utilisés dans l'épisode.
        Cela aide le reviewer à demander une réécriture si le script manque
        de caractérisation.
        """
        data = config.charger_personnages()
        if not data:
            return

        personnages = data.get("personnages", {})
        textes_par_perso: dict[str, str] = {}

        for seg in script.get("episode", {}).get("segments", []):
            perso = seg.get("personnage", "")
            if perso in personnages:
                textes_par_perso.setdefault(perso, "")
                textes_par_perso[perso] += " " + seg.get("texte", "")

        for perso_id, texte_complet in textes_par_perso.items():
            tics = personnages.get(perso_id, {}).get("tics_de_langage", [])
            if not tics:
                continue
            texte_lower = texte_complet.lower()
            tics_trouves = sum(
                1 for tic in tics if tic.lower().rstrip("...!?. ") in texte_lower
            )
            nom = personnages[perso_id].get("nom_complet", perso_id)
            if tics_trouves < 2:
                logger.warning(
                    "Tics de langage : %s n'utilise que %d/%d tics dans cet épisode "
                    "(minimum recommandé : 2-3).",
                    nom, tics_trouves, len(tics),
                )
            else:
                logger.info(
                    "Tics de langage : %s utilise %d/%d tics.",
                    nom, tics_trouves, len(tics),
                )

    @staticmethod
    def _verifier_mots_interdits(script: dict) -> None:
        """Vérifie qu'aucun mot interdit n'apparaît dans le texte généré.

        Le LLM reçoit l'instruction de ne pas utiliser ces mots, mais il n'est
        pas infaillible. Ce filtre post-génération émet un warning pour chaque
        mot interdit trouvé.
        """
        mots_interdits = config.MOTS_INTERDITS
        if not mots_interdits:
            return

        texte_complet = ""
        for seg in script.get("episode", {}).get("segments", []):
            if seg.get("personnage") != "sfx":
                texte_complet += " " + seg.get("texte", "")

        texte_lower = texte_complet.lower()
        trouves = []
        for mot in mots_interdits:
            if mot.lower() in texte_lower:
                trouves.append(mot)

        if trouves:
            logger.warning(
                "Mots interdits détectés dans le script généré : %s. "
                "Le LLM n'a pas respecté l'instruction. "
                "Le reviewer devrait signaler ces occurrences.",
                ", ".join(trouves),
            )

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
            ep["ambiance"] = "calme"
            logger.warning("Champ 'ambiance' manquant — défaut 'calme'.")
        elif ep["ambiance"] not in config.AMBIANCES_VALIDES:
            logger.warning(
                "Ambiance '%s' non reconnue (valides : %s) — défaut 'calme'.",
                ep["ambiance"], ", ".join(config.AMBIANCES_VALIDES),
            )
            ep["ambiance"] = "calme"

        if "morale" not in ep:
            logger.warning("Champ 'morale' manquant dans le script.")

        # Vérifier l'unicité des IDs de segments
        ids_vus = set()
        for seg in ep["segments"]:
            seg_id = seg.get("id", "")
            if seg_id in ids_vus:
                raise ValueError(f"ID de segment dupliqué : '{seg_id}'")
            ids_vus.add(seg_id)

        personnages_ok = config.personnages_valides()
        placeholder = "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"
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
            # Valider pause_apres_ms est un nombre >= 0
            pause = seg.get("pause_apres_ms", 0)
            if not isinstance(pause, (int, float)) or pause < 0:
                logger.warning(
                    "pause_apres_ms invalide (%s) dans segment %s — corrigé à 0.",
                    pause, seg["id"],
                )
                seg["pause_apres_ms"] = 0

            # Valider que le texte est non-vide (sauf SFX qui ont des descriptions)
            texte = seg.get("texte", "")
            if seg["personnage"] != "sfx" and not texte.strip():
                logger.warning(
                    "Texte vide dans segment %s (personnage: %s) — "
                    "causera une génération TTS inutile.",
                    seg["id"], seg["personnage"],
                )

            # Avertir si le personnage n'a pas de voice_id configuré
            if seg["personnage"] != "sfx":
                vid = config.VOICE_IDS.get(seg["personnage"])
                if not vid or vid == placeholder:
                    logger.warning(
                        "Voice ID manquant pour '%s' (segment %s) "
                        "— fallback voix appliqué au moment du TTS.",
                        seg["personnage"], seg["id"],
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

        if sfx_count > 15:
            logger.warning("Trop de bruitages : %d (recommandé 8-12).", sfx_count)
        elif sfx_count < 5:
            logger.warning("Pas assez de bruitages : %d (recommandé 8-12).", sfx_count)

        # Vérifier que evolutions_personnages est présent et non vide
        evolutions = ep.get("evolutions_personnages", "")
        if not evolutions or (isinstance(evolutions, str) and not evolutions.strip()):
            logger.warning(
                "Champ 'evolutions_personnages' manquant ou vide — "
                "l'historique inter-épisodes perdra la trace de l'évolution "
                "des personnages pour cet épisode."
            )
