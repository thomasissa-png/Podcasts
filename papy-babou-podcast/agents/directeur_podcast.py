"""Agent Directeur Podcast — Validation créative et audience par un expert.

Le directeur podcast est le N°1 du podcast pour enfants en France.
Il valide chaque script sous deux angles :
1. Son expertise de directeur créatif audio (voix IA, SFX, rythme, immersion)
2. Les retours simulés de 3 personas d'audience (enfants + parent)

Cet agent intervient APRÈS le reviewer technique, comme gate créatif final.
"""

import json
import logging

import anthropic

import config
from utils import parser_json_llm

logger = logging.getLogger(__name__)

# ── Personas d'audience ──────────────────────────────────────────────────────

PERSONAS = {
    "lina_7ans": {
        "nom": "Lina",
        "age": 7,
        "profil": "fille",
        "description": (
            "Lina a 7 ans. Elle est en CE1. Elle adore les histoires de princesses "
            "et d'animaux, mais elle s'intéresse aussi aux aventures. Elle a une capacité "
            "d'attention de 15-20 minutes. Si l'histoire est trop longue sans rebondissement, "
            "elle décroche et va jouer. Elle aime quand les personnages ont des émotions "
            "fortes (joie, peur, surprise) et quand il y a des bruitages rigolos. "
            "Elle connaît un peu les histoires bibliques par le catéchisme mais ne retient "
            "que les grandes lignes. Elle adore Noémie parce qu'elle se reconnaît dans la "
            "chipie. Elle a parfois peur quand c'est trop dramatique. "
            "Elle écoute le podcast dans la voiture avec ses parents ou le soir avant de dormir."
        ),
        "criteres": [
            "Est-ce que je comprends tous les mots ? (vocabulaire adapté 7 ans)",
            "Est-ce que j'ai envie de savoir la suite ? (suspense, curiosité)",
            "Est-ce que je rigole au moins une fois ? (humour enfantin)",
            "Est-ce que j'ai peur à un moment mais Papy me rassure ? (émotion maîtrisée)",
            "Est-ce que c'est trop long sans qu'il se passe quelque chose ? (rythme)",
            "Est-ce que je reconnais les bruitages et ils me font voyager ? (immersion SFX)",
        ],
    },
    "noah_10ans": {
        "nom": "Noah",
        "age": 10,
        "profil": "garçon",
        "description": (
            "Noah a 10 ans. Il est en CM2 et commence à trouver certaines choses 'bébé'. "
            "Il aime l'action, les combats, les héros courageux. Il joue au foot et fait "
            "du karaté. Il se reconnaît dans Antoine. Il a une bonne culture générale "
            "pour son âge et pose beaucoup de questions 'pourquoi'. Il aime quand Papy "
            "donne des détails historiques et géographiques concrets. Il déteste quand "
            "c'est 'trop mignon' ou trop simple. Il veut apprendre des choses que ses "
            "copains ne savent pas. Il a déjà écouté d'autres podcasts (Les Odyssées, "
            "Mythes et Légendes) et compare inconsciemment la qualité. "
            "Il écoute le podcast seul avec ses écouteurs ou en famille le dimanche."
        ),
        "criteres": [
            "Est-ce que c'est pas 'bébé' ? (sophistication narrative adaptée 10 ans)",
            "Est-ce que j'apprends un truc que mes copains savent pas ? (contenu éducatif)",
            "Est-ce qu'il y a de l'action ou du suspense ? (tension dramatique)",
            "Est-ce que les détails historiques sont vrais et intéressants ? (crédibilité)",
            "Est-ce que les voix et les bruitages sont bien faits ? (qualité production)",
            "Est-ce que j'ai envie d'écouter le prochain ? (fidélisation)",
        ],
    },
    "sophie_parent": {
        "nom": "Sophie",
        "age": 45,
        "profil": "parent catholique",
        "description": (
            "Sophie a 45 ans. Elle est mère de 3 enfants (7, 10 et 13 ans). "
            "Catholique pratiquante, elle cherche des contenus de qualité pour transmettre "
            "la foi chrétienne à ses enfants de manière vivante et joyeuse, pas moralisatrice. "
            "Elle veut que ses enfants AIMENT les histoires bibliques, pas qu'ils les subissent. "
            "Elle est exigeante sur la fidélité au texte biblique — elle repère les erreurs "
            "et les raccourcis. Elle apprécie quand le podcast fait réfléchir ses enfants "
            "et génère des discussions familiales après l'écoute. Elle est sensible au ton : "
            "pas de prosélytisme agressif, pas de culpabilisation, mais une vraie transmission "
            "de valeurs (courage, foi, amour, pardon). Elle compare avec les Belles Histoires "
            "de Pomme d'Api et les podcasts de Bayam. "
            "Elle écoute avec ses enfants dans la voiture et vérifie le contenu."
        ),
        "criteres": [
            "Est-ce que le récit biblique est FIDÈLE au texte ? (véracité)",
            "Est-ce que la morale est transmise sans moralisation pesante ? (ton juste)",
            "Est-ce que mes enfants vont poser des questions après ? (ouverture au dialogue)",
            "Est-ce que c'est adapté à la fois à mon fils de 7 ans ET celui de 10 ans ? (multi-âge)",
            "Est-ce que la qualité sonore est professionnelle ? (voix IA naturelles, SFX)",
            "Est-ce que je recommanderais ce podcast à d'autres parents ? (qualité globale)",
        ],
    },
}

# ── System Prompt du Directeur ───────────────────────────────────────────────

SYSTEM_PROMPT = """\
Tu es Marc Delacroix, le directeur podcast le plus reconnu en France pour les \
contenus audio destinés aux enfants de 6 à 10 ans. Tu as dirigé des productions \
primées : "Les Petites Voix" (Prix Europa), "Contes Sonores" (Grand Prix du \
Podcast Jeunesse), et tu as collaboré avec Radio France, Audible et Lunii.

Tu maîtrises parfaitement :
- La direction artistique de voix IA (ElevenLabs, synthèse vocale) et voix humaines
- Le sound design immersif pour enfants (SFX, ambiances, musique)
- La narration sérielle (arcs, personnages récurrents, fidélisation)
- L'adaptation de contenus éducatifs pour différentes tranches d'âge
- Les standards de qualité des plateformes (Apple Podcasts, Spotify Kids)

Tu révises le script du podcast "Les Histoires de Papy Babou" — un podcast \
SÉRIEL pour enfants de 6 à 10 ans basé sur des histoires bibliques, produit \
avec des voix IA ElevenLabs et des SFX générés.

TON RÔLE :
1. Évaluer le script en tant que directeur créatif expert
2. Simuler les réactions de 3 auditeurs-types (personas)
3. Donner un verdict final avec des recommandations actionnables

EXPERTISE SPÉCIFIQUE — VOIX IA :
Ce podcast utilise des voix ElevenLabs (synthèse). Tu sais que :
- Les onomatopées écrites (haha, hihihi, euh, oh) sonnent TERRIBLES avec les voix IA
- Les phrases courtes et percutantes passent mieux que les longues tirades
- Les changements de ton (champ "ton" du segment) sont CRITIQUES pour l'émotion
- Les pauses (champ "pause_apres_ms") remplacent les respirations naturelles
- Les segments trop longs (>80 mots) deviennent monotones en voix IA
- Le rythme (champ "rythme") doit varier pour éviter l'effet "robot qui lit"
- Les SFX bien placés compensent le manque d'expressivité des voix IA

PERSONAS D'AUDIENCE :
{personas}

ÉVALUATION EN 6 AXES (chacun noté sur 10) :

1. IMMERSION SONORE (note/10)
   - Les SFX sont-ils bien placés, variés, et immersifs ?
   - Les ambiances par acte créent-elles un voyage sonore ?
   - Les transitions entre scènes sont-elles fluides ?
   - Le sound design compense-t-il les limites des voix IA ?
   - MUSIQUE DE FOND : le champ "ambiance" et "ambiance_par_acte" sont-ils cohérents
     avec le contenu du récit ? L'ambiance_par_acte doit varier entre les 3 actes
     pour créer un vrai voyage émotionnel sonore (ex: calme → dramatique → tendre).
     Une ambiance uniforme sur tout l'épisode est un DÉFAUT majeur.
   - Les choix d'ambiance correspondent-ils à l'arc émotionnel ? (ex: "epique" pour
     les batailles, "tendre" pour les moments familiaux, "mystere" pour les révélations)

2. RYTHME & ACCROCHE (note/10)
   - L'accroche capte-t-elle l'attention dans les 30 premières secondes ?
   - Le rythme maintient-il l'attention sur toute la durée ?
   - Y a-t-il des "temps morts" où un enfant décrocherait ?
   - Les rebondissements sont-ils bien espacés ?

3. ÉMOTION & PERSONNAGES (note/10)
   - Les personnages sont-ils vivants et attachants ?
   - L'arc émotionnel est-il clair et satisfaisant ?
   - Les moments d'humour fonctionnent-ils ?
   - Les moments de tension sont-ils bien dosés pour l'âge ?

4. VALEUR ÉDUCATIVE & FIDÉLITÉ (note/10)
   - L'histoire biblique est-elle racontée fidèlement et complètement ?
   - Les enfants retiennent-ils quelque chose d'utile ?
   - La morale est-elle naturelle (pas moralisatrice) ?
   - Le contenu génère-t-il des discussions parent-enfant ?

5. COMPATIBILITÉ VOIX IA (note/10)
   - Les segments sont-ils optimisés pour la synthèse vocale ?
   - Les tons variés exploitent-ils bien les capacités d'ElevenLabs ?
   - Les pauses sont-elles réalistes et bien calibrées ?
   - Reste-t-il des onomatopées ou formulations problématiques ?
   - Les segments ne sont-ils pas trop longs pour la voix IA (>80 mots) ?

6. QUALITÉ SFX POUR GÉNÉRATION AUDIO (note/10) — NOUVEL AXE
   Tu sais que les SFX seront générés automatiquement via ElevenLabs Sound Effects.
   La QUALITÉ des descriptions SFX dans le script détermine directement la qualité du son produit.
   Vérifie :
   - Les descriptions SFX sont-elles EN ANGLAIS ? (obligatoire pour ElevenLabs)
   - Sont-elles DESCRIPTIVES et SPÉCIFIQUES ? ("gentle warm breeze through olive trees at sunset"
     est excellent, "wind" est trop vague et donnera un résultat générique)
   - Les durées sont-elles cohérentes ? (overlay d'ambiance ≥ 15s, insert ponctuel 2-5s)
   - Les modes "overlay" vs "insert" sont-ils bien choisis ?
     * overlay = ambiance de fond continue (nature, lieu, atmosphère)
     * insert = effet ponctuel (porte, tonnerre, réaction)
   - Y a-t-il une VARIÉTÉ suffisante ? (pas 3 fois "wind blowing" — varier les descriptions)
   - Les SFX sont-ils DYNAMIQUES ? Le paysage sonore évolue-t-il au fil de l'épisode ?
     * Changement d'ambiance quand le lieu de l'histoire change
     * Intensification des SFX pendant les moments dramatiques
     * Retour au calme pendant les moments tendres
   - Y a-t-il un SFX de TRANSITION entre la scène de vie et le récit biblique ?
   - Le rythme SFX est-il régulier ? (jamais plus de 2 minutes sans un SFX)
   - Les SFX ponctuent-ils les moments clés ? (révélations, actions, émotions)
   - ANTI-RÉPÉTITION : chaque description SFX est-elle unique dans l'épisode ?

FORMAT DE RÉPONSE — JSON STRICT :
{{
  "directeur": {{
    "note_globale": 8.5,
    "verdict": "feu_vert|ajustements_mineurs|retravailler",
    "synthese": "Résumé en 2-3 phrases de l'avis global du directeur.",
    "axes": {{
      "immersion_sonore": {{
        "note": 8,
        "commentaire": "..."
      }},
      "rythme_accroche": {{
        "note": 7,
        "commentaire": "..."
      }},
      "emotion_personnages": {{
        "note": 9,
        "commentaire": "..."
      }},
      "valeur_educative": {{
        "note": 8,
        "commentaire": "..."
      }},
      "compatibilite_voix_ia": {{
        "note": 7,
        "commentaire": "..."
      }},
      "qualite_sfx": {{
        "note": 8,
        "commentaire": "...",
        "sfx_problematiques": [
          {{
            "id": "sfx_003",
            "probleme": "Description trop vague — 'wind' devrait être 'gentle warm breeze through olive trees'",
            "suggestion": "hot dry desert wind blowing sand over ancient dunes"
          }}
        ]
      }}
    }},
    "recommandations": [
      {{
        "priorite": "critique|important|suggestion",
        "texte": "Description actionnable de la recommandation"
      }}
    ],
    "points_forts": ["Ce qui fonctionne très bien"]
  }},
  "personas": {{
    "lina_7ans": {{
      "reaction": "Description de la réaction de Lina en 2-3 phrases, ÉCRITE COMME SI C'ÉTAIT LINA QUI PARLAIT.",
      "accrocherait": true,
      "moments_preferes": ["Moment 1"],
      "points_decrochage": ["Moment où elle décrocherait"],
      "note": 8
    }},
    "noah_10ans": {{
      "reaction": "Description de la réaction de Noah en 2-3 phrases, ÉCRITE COMME SI C'ÉTAIT NOAH QUI PARLAIT.",
      "accrocherait": true,
      "moments_preferes": ["Moment 1"],
      "points_decrochage": [],
      "note": 7
    }},
    "sophie_parent": {{
      "reaction": "Description de la réaction de Sophie en 2-3 phrases.",
      "recommanderait": true,
      "points_positifs": ["Ce qu'elle apprécie"],
      "reserves": ["Ce qui la gêne"],
      "note": 8
    }}
  }},
  "note_audience": 7.7
}}

La "note_audience" est la MOYENNE pondérée des 3 personas : Lina (30%), Noah (30%), Sophie (40%).
Sophie pèse plus car un parent mécontent = podcast désinstallé.

Le "verdict" suit cette grille :
- "feu_vert" : note_globale >= 7.5 ET note_audience >= 7 ET aucune recommandation critique
- "ajustements_mineurs" : note_globale >= 6 OU recommandations non-critiques uniquement
- "retravailler" : note_globale < 6 OU note_audience < 6 OU recommandation critique

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""

# ── Adaptive max_tokens par type d'épisode ───────────────────────────────────

_MAX_TOKENS_PAR_TYPE = {
    "final": 8192,
    "ouverture": 6144,
    "mi-saison": 6144,
    "standard": 4096,
    "bonus": 4096,
}


def _construire_system_prompt_directeur() -> str:
    """Construit le system prompt avec les personas injectées."""
    personas_text = []
    for key, persona in PERSONAS.items():
        personas_text.append(
            f"PERSONA {persona['nom'].upper()} ({persona['age']} ans, {persona['profil']}) :\n"
            f"{persona['description']}\n"
            f"Critères d'évaluation :\n"
            + "\n".join(f"  - {c}" for c in persona["criteres"])
        )
    return SYSTEM_PROMPT.format(personas="\n\n".join(personas_text))


def _construire_user_prompt(script: dict, contexte: dict | None = None) -> str:
    """Construit le prompt utilisateur avec le script et son contexte.

    Args:
        script: Script complet de l'épisode (dict avec clé "episode").
        contexte: Contexte optionnel (type_episode, score_reviewer, alertes, etc.).
    """
    parts = []

    if contexte:
        parts.append("CONTEXTE DE PRODUCTION :")
        if contexte.get("type_episode"):
            parts.append(f"- Type d'épisode : {contexte['type_episode']}")
        if contexte.get("score_reviewer") is not None:
            parts.append(f"- Score du reviewer technique : {contexte['score_reviewer']}/10")
        if contexte.get("alertes"):
            parts.append("- Alertes du reviewer : " + "; ".join(contexte["alertes"]))
        if contexte.get("metriques"):
            for k, v in contexte["metriques"].items():
                parts.append(f"- {k} : {v}")
        parts.append("")

    parts.append("SCRIPT À ÉVALUER :")
    parts.append(json.dumps(script, ensure_ascii=False, indent=2))

    return "\n".join(parts)


# ── System Prompt — Évaluation de plan de saison ─────────────────────────────

SYSTEM_PROMPT_PLAN_SAISON = """\
Tu es Marc Delacroix, le directeur podcast le plus reconnu en France pour les \
contenus audio destinés aux enfants de 6 à 10 ans. Tu as dirigé des productions \
primées et tu maîtrises la narration sérielle, les arcs de personnages, et la \
fidélisation d'audience sur une saison entière.

Tu révises le PLAN DE SAISON du podcast "Les Histoires de Papy Babou" — un podcast \
SÉRIEL pour enfants de 6 à 10 ans basé sur des histoires bibliques.

TON RÔLE :
1. Évaluer le plan de saison en tant que directeur créatif expert
2. Simuler les réactions de 3 auditeurs-types (personas) sur la SAISON ENTIÈRE
3. Donner un verdict final avec des recommandations actionnables

PERSONAS D'AUDIENCE :
{personas}

ÉVALUATION EN 5 AXES (chacun noté sur 10) :

1. COHÉRENCE NARRATIVE (note/10)
   - Le fil rouge tient-il sur toute la saison ?
   - Les épisodes forment-ils un arc cohérent avec progression thématique ?
   - Les liens entre épisodes (teasing, rappels) sont-ils naturels ?
   - L'ouverture pose-t-elle bien le décor ? Le final conclut-il les arcs ?

2. VARIÉTÉ DES THÈMES (note/10)
   - Les histoires bibliques sont-elles suffisamment diversifiées ?
   - Les ambiances varient-elles d'un épisode à l'autre ?
   - Les prétextes (scènes de vie) sont-ils variés et crédibles ?
   - Y a-t-il un bon équilibre action/émotion/humour sur la saison ?

3. ARCS DE PERSONNAGES (note/10)
   - Les arcs d'Antoine, Noémie et Papy sont-ils crédibles et progressifs ?
   - Les personnages secondaires sont-ils bien introduits et utiles ?
   - Les évolutions émotionnelles sont-elles adaptées aux âges des personnages ?
   - Les tics de langage et rituels renforcent-ils l'identité de chaque personnage ?

4. RYTHME DE SAISON (note/10)
   - L'alternance des types d'épisodes (ouverture, standard, mi-saison, final) est-elle judicieuse ?
   - Les durées sont-elles adaptées aux moments de la saison ?
   - Y a-t-il des temps forts bien espacés pour maintenir l'engagement ?
   - Le rythme de la saison correspond-il à l'attention d'un enfant (pas de tunnel ennuyeux) ?

5. POTENTIEL AUDIENCE (note/10)
   - Cette saison va-t-elle fidéliser les auditeurs existants ?
   - Les sujets bibliques choisis sont-ils attractifs pour des enfants de 6-10 ans ?
   - Y a-t-il des "épisodes événements" qui peuvent attirer de nouveaux auditeurs ?
   - Le plan génère-t-il l'envie de binge-écouter la saison ?

FORMAT DE RÉPONSE — JSON STRICT :
{{
  "directeur_saison": {{
    "note_globale": 8.0,
    "verdict": "feu_vert|ajustements_mineurs|retravailler",
    "synthese": "Résumé en 3-4 phrases de l'avis global du directeur sur la saison.",
    "axes": {{
      "coherence_narrative": {{
        "note": 8,
        "commentaire": "..."
      }},
      "variete_themes": {{
        "note": 7,
        "commentaire": "..."
      }},
      "arcs_personnages": {{
        "note": 9,
        "commentaire": "..."
      }},
      "rythme_saison": {{
        "note": 8,
        "commentaire": "..."
      }},
      "potentiel_audience": {{
        "note": 7,
        "commentaire": "..."
      }}
    }},
    "recommandations": [
      {{
        "priorite": "critique|important|suggestion",
        "episode": null,
        "texte": "Description actionnable. Si 'episode' est un numéro, la recommandation concerne cet épisode spécifique."
      }}
    ],
    "points_forts": ["Ce qui fonctionne très bien dans ce plan"]
  }},
  "personas": {{
    "lina_7ans": {{
      "reaction": "Réaction de Lina sur la saison entière (ÉCRITE COMME SI C'ÉTAIT LINA).",
      "episodes_preferes": [1, 5],
      "episodes_moins_attractifs": [3],
      "accrocherait_toute_la_saison": true,
      "note": 8
    }},
    "noah_10ans": {{
      "reaction": "Réaction de Noah sur la saison entière (ÉCRITE COMME SI C'ÉTAIT NOAH).",
      "episodes_preferes": [2, 10],
      "episodes_moins_attractifs": [],
      "accrocherait_toute_la_saison": true,
      "note": 7
    }},
    "sophie_parent": {{
      "reaction": "Réaction de Sophie sur la saison entière.",
      "episodes_preferes": [1, 5, 10],
      "reserves": ["Ce qui la gêne"],
      "recommanderait_la_saison": true,
      "note": 8
    }}
  }},
  "note_audience": 7.7
}}

La "note_audience" est la MOYENNE pondérée : Lina (30%), Noah (30%), Sophie (40%).

Le "verdict" suit cette grille :
- "feu_vert" : note_globale >= 7.5 ET note_audience >= 7 ET aucune recommandation critique
- "ajustements_mineurs" : note_globale >= 6 OU recommandations non-critiques uniquement
- "retravailler" : note_globale < 6 OU note_audience < 6 OU recommandation critique

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""

# ── System Prompt — Correction directe du plan ───────────────────────────────

SYSTEM_PROMPT_CORRECTION_PLAN = """\
Tu es Marc Delacroix, le directeur podcast le plus reconnu en France pour les \
contenus audio destinés aux enfants de 6 à 10 ans.

Tu as déjà donné 3 retours sur ce plan de saison. Le producteur n'a pas réussi \
à intégrer toutes tes recommandations. C'est maintenant TOI qui prends la main \
et qui modifies le plan DIRECTEMENT.

MISSION : Réécrire le plan de saison en appliquant TOUTES tes recommandations \
cumulées des 3 retours précédents. Tu produis le plan FINAL, prêt pour la production.

RÈGLES :
1. Conserve la STRUCTURE JSON identique au plan d'entrée (clé "saison" avec les mêmes champs)
2. Conserve le thème et le numéro de saison
3. Conserve le nombre d'épisodes
4. Applique TOUTES tes recommandations critiques et importantes des 3 retours
5. Améliore ce qui peut l'être pour les suggestions aussi
6. Un sujet biblique par épisode, COMPLET de A à Z (pas de multi-parties)
7. Ordre chronologique biblique respecté
8. Chaque épisode garde les champs obligatoires : numero, titre, type, histoire_biblique, \
resume, morale, ambiance, duree_cible_minutes, pretexte, personnages_presents, \
personnages_secondaires_presents, arc_personnage_focus, progression_arc, \
lien_episode_precedent, teasing_episode_suivant, elements_fil_rouge, \
moments_cles, questions_ouvertes

Réponds UNIQUEMENT avec le plan JSON corrigé (clé racine "saison"), sans texte ni commentaire.
"""


def _construire_system_prompt_plan_saison() -> str:
    """Construit le system prompt plan saison avec les personas injectées."""
    personas_text = []
    for key, persona in PERSONAS.items():
        personas_text.append(
            f"PERSONA {persona['nom'].upper()} ({persona['age']} ans, {persona['profil']}) :\n"
            f"{persona['description']}\n"
            f"Critères d'évaluation :\n"
            + "\n".join(f"  - {c}" for c in persona["criteres"])
        )
    return SYSTEM_PROMPT_PLAN_SAISON.format(personas="\n\n".join(personas_text))


def _construire_system_prompt_correction_plan() -> str:
    """Retourne le system prompt pour la correction directe du plan."""
    return SYSTEM_PROMPT_CORRECTION_PLAN


def _construire_user_prompt_plan(
    plan: dict,
    retours_precedents: list[dict] | None = None,
) -> str:
    """Construit le prompt utilisateur pour l'évaluation d'un plan de saison.

    Args:
        plan: Plan de saison complet.
        retours_precedents: Retours précédents du directeur (mémoire cumulative).
    """
    parts = []

    if retours_precedents:
        parts.append(
            f"RETOURS PRÉCÉDENTS DU DIRECTEUR ({len(retours_precedents)} tour(s)) :"
        )
        for i, retour in enumerate(retours_precedents, 1):
            dir_data = retour.get("directeur_saison", {})
            parts.append(f"\n--- Tour {i} (note {dir_data.get('note_globale', '?')}/10, "
                         f"verdict: {dir_data.get('verdict', '?')}) ---")
            synthese = dir_data.get("synthese", "")
            if synthese:
                parts.append(f"Synthèse : {synthese}")
            recommandations = dir_data.get("recommandations", [])
            for r in recommandations:
                parts.append(f"  [{r.get('priorite', '?')}] {r.get('texte', '')}")
        parts.append("")
        parts.append(
            "IMPORTANT : Tiens compte de tes retours précédents. "
            "NE RÉPÈTE PAS les mêmes remarques si elles ont été corrigées. "
            "Concentre-toi sur ce qui reste à améliorer."
        )
        parts.append("")

    parts.append("PLAN DE SAISON À ÉVALUER :")
    parts.append(json.dumps(plan, ensure_ascii=False, indent=2))

    return "\n".join(parts)


def _construire_user_prompt_correction(
    plan: dict,
    retours_precedents: list[dict],
) -> str:
    """Construit le prompt pour la correction directe du plan par le directeur.

    Args:
        plan: Plan de saison à corriger.
        retours_precedents: Les 3 retours précédents du directeur.
    """
    parts = []

    parts.append(
        f"TES 3 RETOURS PRÉCÉDENTS (à appliquer INTÉGRALEMENT) :"
    )
    for i, retour in enumerate(retours_precedents, 1):
        dir_data = retour.get("directeur_saison", {})
        parts.append(f"\n--- Tour {i} (note {dir_data.get('note_globale', '?')}/10) ---")
        synthese = dir_data.get("synthese", "")
        if synthese:
            parts.append(f"Synthèse : {synthese}")
        recommandations = dir_data.get("recommandations", [])
        for r in recommandations:
            ep = r.get("episode")
            ep_str = f" (épisode {ep})" if ep else ""
            parts.append(f"  [{r.get('priorite', '?')}]{ep_str} {r.get('texte', '')}")
    parts.append("")

    parts.append("PLAN DE SAISON À CORRIGER :")
    parts.append(json.dumps(plan, ensure_ascii=False, indent=2))

    return "\n".join(parts)


# ── System Prompt — Validation des métadonnées ────────────────────────────────

_SYSTEM_PROMPT_METADONNEES = """\
Tu es Marc Delacroix, directeur podcast expert. Tu valides les MÉTADONNÉES \
d'un épisode du podcast "Les Histoires de Papy Babou" (enfants 6-10 ans, \
histoires bibliques).

Les métadonnées déterminent si un parent va cliquer "Play" sur Apple Podcasts \
ou Spotify. C'est la VITRINE de l'épisode. Un mauvais titre = 0 écoute.

PERSONAS D'AUDIENCE :
{personas}

ÉVALUATION :
1. TITRE — Est-il accrocheur, court (<60 chars), évocateur pour un enfant ET un parent ?
   Éviter les titres génériques ("L'histoire de..."), préférer l'intrigue ou l'émotion.
2. DESCRIPTION COURTE — Donne-t-elle envie d'écouter en 2-3 phrases ?
   Un parent scroll vite — la 1ère phrase doit captiver.
3. MOTS-CLÉS — Sont-ils pertinents pour le SEO podcast ?
   Inclure : thème biblique, personnages, émotion principale.
4. COHÉRENCE — Les métadonnées reflètent-elles fidèlement le contenu ?
   Pas de promesses non tenues (clickbait).

FORMAT DE RÉPONSE — JSON STRICT :
{{
  "verdict": "feu_vert|ajustements_mineurs|retravailler",
  "note": 8,
  "titre_avis": "Avis sur le titre — ce qui fonctionne et ce qui pourrait être amélioré.",
  "description_avis": "Avis sur la description.",
  "suggestions": {{
    "titres_alternatifs": ["Titre alternatif 1", "Titre alternatif 2"],
    "description_amelioree": "Version améliorée de la description si nécessaire.",
    "mots_cles_manquants": ["mot-clé 1"]
  }},
  "personas": {{
    "lina_7ans": {{
      "cliquerait": true,
      "commentaire": "Réaction de Lina face au titre/description"
    }},
    "noah_10ans": {{
      "cliquerait": true,
      "commentaire": "Réaction de Noah"
    }},
    "sophie_parent": {{
      "cliquerait": true,
      "commentaire": "Réaction de Sophie (parent)"
    }}
  }}
}}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""

# ── System Prompt — Go/No-Go publication ──────────────────────────────────────

_SYSTEM_PROMPT_GO_NO_GO = """\
Tu es Marc Delacroix, directeur podcast expert. Tu donnes l'avis FINAL \
avant publication RSS d'un épisode du podcast "Les Histoires de Papy Babou" \
(enfants 6-10 ans, histoires bibliques, voix IA ElevenLabs).

C'est le moment de vérité. Une fois publié, l'épisode est public et \
irréversible. Tu as devant toi le RAPPORT COMPLET de production : \
script, review, montage, métadonnées.

PERSONAS D'AUDIENCE :
{personas}

TON RÔLE :
1. Synthétiser TOUTES les données du rapport (notes, alertes, métriques)
2. Identifier les RISQUES résiduels (alertes non résolues, notes basses)
3. Donner un verdict tranché : GO, NO-GO, ou CONDITIONNEL

GRILLE DE DÉCISION :
- "go" : Note directeur ≥7, note audience ≥7, pas d'alerte critique, \
  validation humaine script + montage = OK. Épisode prêt.
- "conditionnel" : Note entre 6-7 OU alertes mineures non résolues. \
  Publication acceptable avec réserves (les lister).
- "no_go" : Note <6 OU alerte critique OU validation humaine manquante. \
  Ne PAS publier en l'état. Expliquer ce qui bloque.

FORMAT DE RÉPONSE — JSON STRICT :
{{
  "verdict": "go|no_go|conditionnel",
  "note_globale": 8.0,
  "synthese": "Synthèse en 3-4 phrases du verdict final.",
  "risques": ["Risque résiduel 1"],
  "points_forts": ["Point fort 1"],
  "conditions": ["Condition pour publier (si conditionnel)"],
  "personas": {{
    "lina_7ans": {{
      "pret_a_publier": true,
      "commentaire": "Lina serait contente de cet épisode parce que..."
    }},
    "noah_10ans": {{
      "pret_a_publier": true,
      "commentaire": "Noah trouverait cet épisode..."
    }},
    "sophie_parent": {{
      "pret_a_publier": true,
      "commentaire": "Sophie recommanderait cet épisode parce que..."
    }}
  }}
}}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""

# ── System Prompt — Brief créatif pré-génération ─────────────────────────────

_SYSTEM_PROMPT_BRIEF_CREATIF = """\
Tu es Marc Delacroix, directeur podcast expert pour enfants de 6-10 ans. \
Tu donnes un BRIEF CRÉATIF au scripteur AVANT qu'il écrive le script \
du podcast "Les Histoires de Papy Babou" (histoires bibliques, voix IA).

Ton brief est une FEUILLE DE ROUTE créative. Le scripteur va s'en servir \
pour écrire un script de qualité broadcast. Sois CONCRET et ACTIONNABLE.

Tu sais que :
- Le podcast utilise des voix IA ElevenLabs — les segments doivent être \
  courts, percutants, avec des tons variés
- Les SFX sont générés automatiquement — les descriptions doivent être \
  en ANGLAIS, spécifiques et immersives
- Le public = enfants 6-10 ans + parents qui écoutent ensemble
- Chaque épisode = UNE histoire biblique complète de A à Z
- Structure : scène de vie familiale → transition → récit biblique → retour

FORMAT DE RÉPONSE — JSON STRICT :
{
  "directives_ton": "Directive globale sur le ton de l'épisode (ex: 'Commencer mystérieux, monter en épique, finir tendre')",
  "accroche_suggestion": "Suggestion concrète pour l'accroche des 30 premières secondes",
  "moments_cles": [
    "Moment clé 1 à ne pas manquer dans le récit biblique",
    "Moment clé 2 — la scène la plus émouvante/spectaculaire",
    "Moment clé 3 — le twist ou la révélation"
  ],
  "sfx_attendus": [
    "SFX atmosphère attendu pour la scène d'ouverture (EN ANGLAIS)",
    "SFX clé pour le moment dramatique (EN ANGLAIS)",
    "SFX de transition entre scène de vie et récit biblique (EN ANGLAIS)"
  ],
  "ambiances_suggerees": {
    "acte_1": "ambiance suggérée pour l'acte 1",
    "acte_2": "ambiance suggérée pour l'acte 2",
    "acte_3": "ambiance suggérée pour l'acte 3"
  },
  "pieges_a_eviter": [
    "Piège 1 spécifique à cette histoire biblique",
    "Piège 2 lié au public enfant"
  ],
  "personnages_focus": "Conseil sur l'utilisation des personnages récurrents dans cet épisode"
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""


def _construire_personas_text() -> str:
    """Construit le texte des personas pour injection dans les prompts."""
    parts = []
    for key, persona in PERSONAS.items():
        parts.append(
            f"PERSONA {persona['nom'].upper()} ({persona['age']} ans, {persona['profil']}) :\n"
            f"{persona['description']}\n"
            f"Critères d'évaluation :\n"
            + "\n".join(f"  - {c}" for c in persona["criteres"])
        )
    return "\n\n".join(parts)


class DirecteurPodcast:
    """Directeur créatif — validation finale et retours d'audience simulés."""

    def __init__(self) -> None:
        """Initialise le client Anthropic."""
        if not config.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY non configurée — impossible d'initialiser "
                "le Directeur Podcast."
            )
        self.client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY,
            timeout=300.0,
        )

    def evaluer(
        self,
        script: dict,
        contexte: dict | None = None,
        max_retry: int = 3,
    ) -> dict:
        """Évalue un script en tant que directeur créatif + personas d'audience.

        Args:
            script: Script complet (dict avec clé "episode").
            contexte: Contexte optionnel (type_episode, score_reviewer, etc.).
            max_retry: Nombre de tentatives de parsing JSON.

        Returns:
            Dict avec clés "directeur", "personas", "note_audience".
        """
        system_prompt = _construire_system_prompt_directeur()
        user_prompt = _construire_user_prompt(script, contexte)

        type_episode = (
            contexte.get("type_episode", "standard") if contexte else "standard"
        )
        max_tokens = _MAX_TOKENS_PAR_TYPE.get(type_episode, 4096)

        derniere_erreur = None
        for tentative in range(1, max_retry + 1):
            response = config.appel_claude_avec_retry(
                self.client,
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            texte_brut = response.content[0].text.strip()

            try:
                resultat = parser_json_llm(texte_brut)
                self._valider_resultat(resultat)
                return resultat
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                derniere_erreur = e
                if tentative < max_retry:
                    logger.warning(
                        "Directeur — parsing JSON tentative %d/%d : %s",
                        tentative, max_retry, e,
                    )
                    continue
                raise ValueError(
                    f"Directeur Podcast : impossible de parser le résultat "
                    f"après {max_retry} tentatives. Dernière erreur : {derniere_erreur}"
                ) from derniere_erreur

        # Impossible en théorie mais sécurité
        raise ValueError("Directeur Podcast : aucun résultat obtenu.")  # pragma: no cover

    @staticmethod
    def _valider_resultat(resultat: dict) -> None:
        """Vérifie la structure minimale du résultat.

        Raises:
            ValueError: Si la structure est invalide.
        """
        if "directeur" not in resultat:
            raise ValueError("Clé 'directeur' manquante dans le résultat.")
        if "personas" not in resultat:
            raise ValueError("Clé 'personas' manquante dans le résultat.")

        directeur = resultat["directeur"]
        for champ in ("note_globale", "verdict", "axes", "recommandations"):
            if champ not in directeur:
                raise ValueError(f"Champ 'directeur.{champ}' manquant.")

        axes_attendus = {
            "immersion_sonore", "rythme_accroche", "emotion_personnages",
            "valeur_educative", "compatibilite_voix_ia", "qualite_sfx",
        }
        axes_presents = set(directeur.get("axes", {}).keys())
        manquants = axes_attendus - axes_presents
        if manquants:
            raise ValueError(f"Axes manquants : {', '.join(sorted(manquants))}")

        if directeur["verdict"] not in ("feu_vert", "ajustements_mineurs", "retravailler"):
            raise ValueError(
                f"Verdict invalide : '{directeur['verdict']}'. "
                "Attendu : feu_vert, ajustements_mineurs, retravailler."
            )

        personas_attendues = {"lina_7ans", "noah_10ans", "sophie_parent"}
        personas_presentes = set(resultat.get("personas", {}).keys())
        manquantes = personas_attendues - personas_presentes
        if manquantes:
            raise ValueError(f"Personas manquantes : {', '.join(sorted(manquantes))}")

    @staticmethod
    def est_feu_vert(resultat: dict) -> bool:
        """Vérifie si le verdict est un feu vert (prêt pour production).

        Returns:
            True si le directeur a donné le feu vert.
        """
        return resultat.get("directeur", {}).get("verdict") == "feu_vert"

    @staticmethod
    def a_critiques(resultat: dict) -> bool:
        """Vérifie si le résultat contient des recommandations critiques.

        Returns:
            True si au moins une recommandation est de priorité "critique".
        """
        recommandations = resultat.get("directeur", {}).get("recommandations", [])
        return any(r.get("priorite") == "critique" for r in recommandations)

    @staticmethod
    def extraire_recommandations(resultat: dict) -> list[str]:
        """Extrait les recommandations sous forme de liste de textes.

        Returns:
            Liste de recommandations triées par priorité.
        """
        priorite_ordre = {"critique": 0, "important": 1, "suggestion": 2}
        recommandations = resultat.get("directeur", {}).get("recommandations", [])
        triees = sorted(
            recommandations,
            key=lambda r: priorite_ordre.get(r.get("priorite", "suggestion"), 3),
        )
        return [
            f"[{r.get('priorite', '?')}] {r.get('texte', '')}"
            for r in triees
        ]

    @staticmethod
    def valider_ambiances(script: dict) -> dict:
        """Validation programmatique des choix d'ambiance musicale.

        Vérifie la cohérence des ambiances avec le type d'épisode,
        le dynamisme de ambiance_par_acte, et les ambiances valides.

        Args:
            script: Script JSON structuré.

        Returns:
            Dict avec clés:
              - "valide" (bool): True si les ambiances sont cohérentes.
              - "alertes" (list[str]): Problèmes détectés.
              - "stats" (dict): Statistiques ambiances.
        """
        alertes = []
        episode = script.get("episode", {})
        ambiance = episode.get("ambiance", "")
        ambiance_par_acte = episode.get("ambiance_par_acte", [])

        # 1. Ambiance principale présente et valide
        if not ambiance:
            alertes.append("Champ 'ambiance' manquant — pas de musique de fond.")
        elif ambiance not in config.AMBIANCES_VALIDES and ambiance != "fond_doux":
            alertes.append(
                f"Ambiance '{ambiance}' non reconnue. "
                f"Valides : {', '.join(config.AMBIANCES_VALIDES)}."
            )

        # 2. ambiance_par_acte — dynamisme
        dynamique = False
        if not ambiance_par_acte or not isinstance(ambiance_par_acte, list):
            alertes.append(
                "Champ 'ambiance_par_acte' absent ou invalide. "
                "La musique sera uniforme sur tout l'épisode — "
                "fortement recommandé de varier entre les 3 actes."
            )
        elif len(ambiance_par_acte) < 2:
            alertes.append(
                "ambiance_par_acte n'a qu'un seul élément — "
                "devrait avoir 3 ambiances (une par acte)."
            )
        elif len(set(ambiance_par_acte)) == 1:
            alertes.append(
                f"ambiance_par_acte : les {len(ambiance_par_acte)} actes ont "
                f"TOUS '{ambiance_par_acte[0]}'. Varier pour un voyage sonore."
            )
        else:
            dynamique = True
            # Vérifier que chaque ambiance est valide
            for i, a in enumerate(ambiance_par_acte):
                if a not in config.AMBIANCES_VALIDES and a != "fond_doux":
                    alertes.append(
                        f"ambiance_par_acte[{i}] = '{a}' non reconnue."
                    )

        # 3. Cohérence ambiance/type d'épisode
        type_ep = episode.get("type", "standard")
        if type_ep == "final" and ambiance in ("humoristique", "fond_doux"):
            alertes.append(
                f"Épisode final avec ambiance '{ambiance}' — un final "
                f"mérite une ambiance plus forte (epique, tendre, solennel)."
            )
        if type_ep == "ouverture" and ambiance == "fond_doux":
            alertes.append(
                "Épisode d'ouverture avec fond_doux — manque d'impact. "
                "Préférer une ambiance plus engageante (joyeux, mystere, epique)."
            )

        return {
            "valide": len(alertes) == 0,
            "alertes": alertes,
            "stats": {
                "ambiance_principale": ambiance,
                "ambiance_par_acte": ambiance_par_acte,
                "dynamique": dynamique,
                "nb_ambiances_distinctes": len(set(ambiance_par_acte)) if ambiance_par_acte else 0,
            },
        }

    @staticmethod
    def valider_sfx_pour_generation(script: dict) -> dict:
        """Validation programmatique des SFX avant envoi au SfxProvider.

        Vérifie la qualité des descriptions, les durées, les modes,
        la variété et le dynamisme du paysage sonore.

        Args:
            script: Script JSON structuré avec segments SFX.

        Returns:
            Dict avec clés:
              - "valide" (bool): True si tous les checks critiques passent.
              - "alertes" (list[str]): Problèmes détectés.
              - "stats" (dict): Statistiques SFX.
        """
        alertes = []
        segments = script.get("episode", {}).get("segments", [])
        sfx_segments = [s for s in segments if s.get("personnage") == "sfx"]
        non_sfx = [s for s in segments if s.get("personnage") != "sfx"]

        # ── Stats de base ──
        nb_sfx = len(sfx_segments)
        nb_overlay = sum(1 for s in sfx_segments if s.get("mode") == "overlay")
        nb_insert = sum(1 for s in sfx_segments if s.get("mode") == "insert")

        # 1. Nombre minimum de SFX
        if nb_sfx < 25:
            alertes.append(
                f"Seulement {nb_sfx} SFX (minimum 25, idéal 30-35). "
                f"L'épisode risque d'être plat sans habillage sonore continu."
            )

        # 2. Descriptions en anglais (détection de mots français courants)
        mots_fr = {"le", "la", "les", "un", "une", "des", "du", "de",
                    "et", "ou", "qui", "que", "dans", "sur", "avec"}
        for seg in sfx_segments:
            texte = seg.get("texte", "")
            mots = set(texte.lower().split())
            nb_fr = len(mots & mots_fr)
            if nb_fr >= 2:
                alertes.append(
                    f"SFX '{seg['id']}' semble en français : \"{texte[:60]}\". "
                    f"Les descriptions doivent être EN ANGLAIS pour ElevenLabs."
                )

        # 3. Descriptions trop courtes (< 3 mots = trop vague)
        for seg in sfx_segments:
            texte = seg.get("texte", "")
            if len(texte.split()) < 3:
                alertes.append(
                    f"SFX '{seg['id']}' trop vague : \"{texte}\". "
                    f"Ajouter des détails (lieu, intensité, texture)."
                )

        # 4. Durée overlay < 15s
        for seg in sfx_segments:
            if seg.get("mode") == "overlay":
                duree = seg.get("duree_sfx_secondes", 5.0)
                if duree < 15.0:
                    alertes.append(
                        f"SFX overlay '{seg['id']}' ne dure que {duree}s "
                        f"(minimum 15s pour couvrir la narration)."
                    )

        # 5. Variété — descriptions dupliquées
        descriptions = [s.get("texte", "").lower().strip() for s in sfx_segments]
        vus = set()
        for i, desc in enumerate(descriptions):
            if desc in vus:
                alertes.append(
                    f"SFX '{sfx_segments[i]['id']}' est un doublon : \"{desc[:50]}\". "
                    f"Chaque SFX doit être unique."
                )
            vus.add(desc)

        # 6. Dynamisme — vérifier qu'il n'y a pas de trous > 2min sans SFX
        # Estimer la position temporelle des segments
        position_ms = 0
        dernier_sfx_ms = 0
        trous = []
        for seg in segments:
            if seg.get("personnage") == "sfx":
                dernier_sfx_ms = position_ms
                position_ms += int(seg.get("duree_sfx_secondes", 5.0) * 1000)
            else:
                nb_mots = len(seg.get("texte", "").split())
                mpm = 100 if seg.get("personnage") in ("antoine", "noemie") else 120
                position_ms += int((nb_mots / mpm) * 60 * 1000)
            position_ms += seg.get("pause_apres_ms", 0)

            ecart = position_ms - dernier_sfx_ms
            if ecart > 120_000 and seg.get("personnage") != "sfx":
                trous.append((ecart // 1000, seg.get("id", "?")))

        for ecart_s, seg_id in trous:
            alertes.append(
                f"Trou de {ecart_s}s sans SFX avant segment '{seg_id}'. "
                f"Maximum recommandé : 120s."
            )

        # 7. Équilibre overlay/insert
        if nb_sfx > 0 and nb_overlay == 0:
            alertes.append(
                "Aucun SFX overlay (ambiance). L'épisode manquera "
                "d'ambiances de fond continues."
            )
        if nb_sfx > 0 and nb_insert == 0:
            alertes.append(
                "Aucun SFX insert (ponctuel). L'épisode manquera "
                "d'effets ponctuels qui marquent l'action."
            )

        # 8. Transition scène de vie → récit biblique
        descriptions_lower = " ".join(descriptions)
        has_transition = any(
            mot in descriptions_lower
            for mot in ("transition", "whoosh", "entering", "return")
        )
        if not has_transition and nb_sfx > 0:
            alertes.append(
                "Pas de SFX de transition entre scène de vie et récit biblique. "
                "Ajouter un 'magical transition whoosh' pour marquer le changement d'univers."
            )

        # Validation globale
        critiques = [a for a in alertes if "français" in a.lower() or "doublon" in a.lower()]
        valide = len(critiques) == 0

        return {
            "valide": valide,
            "alertes": alertes,
            "stats": {
                "nb_sfx": nb_sfx,
                "nb_overlay": nb_overlay,
                "nb_insert": nb_insert,
                "nb_alertes": len(alertes),
                "nb_critiques": len(critiques),
                "duree_estimee_sfx_s": sum(
                    s.get("duree_sfx_secondes", 5.0) for s in sfx_segments
                ),
            },
        }

    def evaluer_plan_saison(
        self,
        plan: dict,
        retours_precedents: list[dict] | None = None,
        max_retry: int = 3,
    ) -> dict:
        """Évalue un plan de saison en tant que directeur créatif + personas.

        Analyse la cohérence narrative, la variété, les arcs de personnages,
        le rythme de la saison, et simule les réactions des 3 personas.

        Args:
            plan: Plan de saison (dict avec clé "saison").
            retours_precedents: Liste des retours précédents du directeur
                (pour mémoire cumulative, éviter de répéter les mêmes remarques).
            max_retry: Nombre de tentatives de parsing JSON.

        Returns:
            Dict avec clés "directeur_saison", "personas", "note_audience".
        """
        system_prompt = _construire_system_prompt_plan_saison()
        user_prompt = _construire_user_prompt_plan(plan, retours_precedents)

        max_tokens = 8192

        derniere_erreur = None
        for tentative in range(1, max_retry + 1):
            response = config.appel_claude_avec_retry(
                self.client,
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            texte_brut = response.content[0].text.strip()

            try:
                resultat = parser_json_llm(texte_brut)
                self._valider_resultat_plan(resultat)
                return resultat
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                derniere_erreur = e
                if tentative < max_retry:
                    logger.warning(
                        "Directeur plan saison — parsing JSON tentative %d/%d : %s",
                        tentative, max_retry, e,
                    )
                    continue
                raise ValueError(
                    f"Directeur Podcast (plan saison) : impossible de parser le résultat "
                    f"après {max_retry} tentatives. Dernière erreur : {derniere_erreur}"
                ) from derniere_erreur

        raise ValueError("Directeur Podcast (plan saison) : aucun résultat obtenu.")  # pragma: no cover

    def corriger_plan_saison(
        self,
        plan: dict,
        retours_precedents: list[dict],
        max_retry: int = 3,
    ) -> dict:
        """Corrige directement un plan de saison (intervention directe, 4e tour).

        Le directeur ne donne plus de retours — il modifie lui-même le plan
        en appliquant toutes ses recommandations cumulées.

        Args:
            plan: Plan de saison à corriger (dict avec clé "saison").
            retours_precedents: Les 3 retours précédents du directeur.
            max_retry: Nombre de tentatives de parsing JSON.

        Returns:
            Plan de saison corrigé (même structure que l'entrée).
        """
        system_prompt = _construire_system_prompt_correction_plan()
        user_prompt = _construire_user_prompt_correction(plan, retours_precedents)

        max_tokens = 12000

        derniere_erreur = None
        for tentative in range(1, max_retry + 1):
            response = config.appel_claude_avec_retry(
                self.client,
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            texte_brut = response.content[0].text.strip()

            try:
                plan_corrige = parser_json_llm(texte_brut)
                # Valider que c'est bien un plan de saison complet
                if "saison" not in plan_corrige:
                    raise ValueError("Le plan corrigé ne contient pas la clé 'saison'.")
                if "episodes" not in plan_corrige.get("saison", {}):
                    raise ValueError("Le plan corrigé ne contient pas d'épisodes.")
                return plan_corrige
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                derniere_erreur = e
                if tentative < max_retry:
                    logger.warning(
                        "Directeur correction plan — parsing JSON tentative %d/%d : %s",
                        tentative, max_retry, e,
                    )
                    continue
                raise ValueError(
                    f"Directeur Podcast (correction plan) : impossible de parser "
                    f"après {max_retry} tentatives. Dernière erreur : {derniere_erreur}"
                ) from derniere_erreur

        raise ValueError("Directeur Podcast (correction plan) : aucun résultat obtenu.")  # pragma: no cover

    @staticmethod
    def _valider_resultat_plan(resultat: dict) -> None:
        """Vérifie la structure minimale du résultat d'évaluation de plan.

        Raises:
            ValueError: Si la structure est invalide.
        """
        if "directeur_saison" not in resultat:
            raise ValueError("Clé 'directeur_saison' manquante dans le résultat.")
        if "personas" not in resultat:
            raise ValueError("Clé 'personas' manquante dans le résultat.")

        directeur = resultat["directeur_saison"]
        for champ in ("note_globale", "verdict", "axes", "recommandations"):
            if champ not in directeur:
                raise ValueError(f"Champ 'directeur_saison.{champ}' manquant.")

        axes_attendus = {
            "coherence_narrative", "variete_themes", "arcs_personnages",
            "rythme_saison", "potentiel_audience",
        }
        axes_presents = set(directeur.get("axes", {}).keys())
        manquants = axes_attendus - axes_presents
        if manquants:
            raise ValueError(f"Axes manquants : {', '.join(sorted(manquants))}")

        if directeur["verdict"] not in ("feu_vert", "ajustements_mineurs", "retravailler"):
            raise ValueError(
                f"Verdict invalide : '{directeur['verdict']}'. "
                "Attendu : feu_vert, ajustements_mineurs, retravailler."
            )

        personas_attendues = {"lina_7ans", "noah_10ans", "sophie_parent"}
        personas_presentes = set(resultat.get("personas", {}).keys())
        manquantes = personas_attendues - personas_presentes
        if manquantes:
            raise ValueError(f"Personas manquantes : {', '.join(sorted(manquantes))}")

    @staticmethod
    def note_audience(resultat: dict) -> float:
        """Calcule la note audience pondérée à partir des personas.

        Pondération : Lina 30%, Noah 30%, Sophie 40%.

        Returns:
            Note sur 10.
        """
        personas = resultat.get("personas", {})
        lina = personas.get("lina_7ans", {}).get("note", 0)
        noah = personas.get("noah_10ans", {}).get("note", 0)
        sophie = personas.get("sophie_parent", {}).get("note", 0)
        return round(lina * 0.3 + noah * 0.3 + sophie * 0.4, 1)

    @staticmethod
    def note_audience_plan(resultat: dict) -> float:
        """Calcule la note audience pondérée pour un plan de saison.

        Même pondération que pour les scripts : Lina 30%, Noah 30%, Sophie 40%.
        Délègue à note_audience() pour éviter la duplication (M2).

        Returns:
            Note sur 10.
        """
        return DirecteurPodcast.note_audience(resultat)

    # ══════════════════════════════════════════════════════════════════════════
    # Validation métadonnées (titre, description, transcript)
    # ══════════════════════════════════════════════════════════════════════════

    def valider_metadonnees(
        self,
        meta: dict,
        script: dict,
        *,
        max_retry: int = 3,
    ) -> dict:
        """Valide les métadonnées de l'épisode (titre, description, mots-clés).

        Le directeur vérifie que le titre est accrocheur, que la description
        donne envie d'écouter, et que les mots-clés sont pertinents pour le SEO
        podcast (Apple Podcasts, Spotify).

        Args:
            meta: Dict des métadonnées (titre, description_courte, mots_cles, etc.).
            script: Script de l'épisode pour le contexte.
            max_retry: Nombre de tentatives de parsing JSON.

        Returns:
            Dict avec clés : "verdict", "note", "titre_avis", "description_avis",
            "suggestions", "personas".
        """
        system_prompt = _SYSTEM_PROMPT_METADONNEES.format(
            personas=_construire_personas_text(),
        )

        episode = script.get("episode", {})
        user_prompt = (
            "MÉTADONNÉES À VALIDER :\n"
            f"{json.dumps(meta, ensure_ascii=False, indent=2)}\n\n"
            "CONTEXTE DU SCRIPT :\n"
            f"- Titre épisode : {episode.get('titre', '?')}\n"
            f"- Histoire biblique : {episode.get('histoire_biblique', '?')}\n"
            f"- Morale : {episode.get('morale', '?')}\n"
            f"- Type : {episode.get('type', 'standard')}\n"
            f"- Nombre de segments : {len(episode.get('segments', []))}\n"
        )

        client = anthropic.Anthropic()
        derniere_erreur = None

        for tentative in range(1, max_retry + 1):
            try:
                response = config.appel_claude_avec_retry(
                    client,
                    model=config.CLAUDE_MODEL,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                resultat = parser_json_llm(response.content[0].text)
                self._valider_resultat_metadonnees(resultat)
                return resultat

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                derniere_erreur = e
                if tentative < max_retry:
                    logger.warning(
                        "Directeur métadonnées — parsing tentative %d/%d : %s",
                        tentative, max_retry, e,
                    )
                    continue
                raise ValueError(
                    f"Directeur Podcast (métadonnées) : impossible de parser "
                    f"après {max_retry} tentatives."
                ) from derniere_erreur

        raise ValueError("Directeur Podcast (métadonnées) : aucun résultat obtenu.")  # pragma: no cover

    @staticmethod
    def _valider_resultat_metadonnees(resultat: dict) -> None:
        """Vérifie la structure minimale du résultat de validation métadonnées."""
        for champ in ("verdict", "note", "titre_avis", "description_avis"):
            if champ not in resultat:
                raise ValueError(f"Champ '{champ}' manquant dans le résultat métadonnées.")
        if resultat["verdict"] not in ("feu_vert", "ajustements_mineurs", "retravailler"):
            raise ValueError(f"Verdict invalide : '{resultat['verdict']}'")

    # ══════════════════════════════════════════════════════════════════════════
    # Go/No-Go final avant publication
    # ══════════════════════════════════════════════════════════════════════════

    def go_no_go_publication(
        self,
        rapport: dict,
        meta: dict,
        *,
        max_retry: int = 3,
    ) -> dict:
        """Avis final du directeur avant publication RSS.

        Synthétise toutes les étapes (script, review, montage, métadonnées)
        et donne un verdict go/no-go pour la publication.

        Args:
            rapport: Rapport complet de production avec toutes les étapes.
            meta: Métadonnées de l'épisode.
            max_retry: Nombre de tentatives de parsing JSON.

        Returns:
            Dict avec clés : "verdict" (go/no_go/conditionnel), "note_globale",
            "synthese", "risques", "points_forts", "personas".
        """
        system_prompt = _SYSTEM_PROMPT_GO_NO_GO.format(
            personas=_construire_personas_text(),
        )

        # Synthèse du rapport pour le LLM
        etapes = rapport.get("etapes", {})
        user_prompt = (
            "RAPPORT DE PRODUCTION COMPLET :\n\n"
            f"ÉPISODE : {meta.get('titre', '?')}\n"
            f"Description : {meta.get('description_courte', '?')}\n\n"
        )

        # Script
        script_data = etapes.get("script", {})
        user_prompt += (
            "1. SCRIPT :\n"
            f"   - Score reviewer : {script_data.get('score', '?')}/10\n"
            f"   - Validation humaine : {'Oui' if script_data.get('validation_humaine') else 'Non'}\n\n"
        )

        # Directeur évaluation script
        dir_data = etapes.get("directeur_podcast", {})
        if dir_data:
            user_prompt += (
                "2. ÉVALUATION DIRECTEUR (script) :\n"
                f"   - Note globale : {dir_data.get('note_globale', '?')}/10\n"
                f"   - Verdict : {dir_data.get('verdict', '?')}\n"
                f"   - Note audience : {dir_data.get('note_audience', '?')}/10\n\n"
            )

        # Montage
        montage_data = etapes.get("montage", {})
        user_prompt += (
            "3. MONTAGE AUDIO :\n"
            f"   - Durée : {montage_data.get('duree_secondes', '?')}s\n"
            f"   - Validation humaine : {'Oui' if montage_data.get('validation_humaine') else 'Non'}\n\n"
        )

        # Métadonnées
        meta_data = etapes.get("metadonnees", {})
        user_prompt += (
            "4. MÉTADONNÉES :\n"
            f"   - Titre : {meta_data.get('titre', meta.get('titre', '?'))}\n"
            f"   - Cover art : {'Oui' if meta_data.get('cover_art_path') else 'Non'}\n\n"
        )

        # Alertes
        alertes = rapport.get("alertes_post_generation", [])
        metriques = rapport.get("metriques", {})
        if alertes:
            user_prompt += "ALERTES :\n" + "\n".join(f"  - {a}" for a in alertes) + "\n\n"
        if metriques:
            user_prompt += "MÉTRIQUES :\n"
            for k, v in metriques.items():
                user_prompt += f"  - {k} : {v}\n"
            user_prompt += "\n"

        user_prompt += "Donne ton verdict GO / NO-GO / CONDITIONNEL pour la publication."

        client = anthropic.Anthropic()
        derniere_erreur = None

        for tentative in range(1, max_retry + 1):
            try:
                response = config.appel_claude_avec_retry(
                    client,
                    model=config.CLAUDE_MODEL,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                resultat = parser_json_llm(response.content[0].text)
                self._valider_resultat_go_no_go(resultat)
                return resultat

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                derniere_erreur = e
                if tentative < max_retry:
                    logger.warning(
                        "Directeur go/no-go — parsing tentative %d/%d : %s",
                        tentative, max_retry, e,
                    )
                    continue
                raise ValueError(
                    f"Directeur Podcast (go/no-go) : impossible de parser "
                    f"après {max_retry} tentatives."
                ) from derniere_erreur

        raise ValueError("Directeur Podcast (go/no-go) : aucun résultat obtenu.")  # pragma: no cover

    @staticmethod
    def _valider_resultat_go_no_go(resultat: dict) -> None:
        """Vérifie la structure minimale du résultat go/no-go."""
        for champ in ("verdict", "note_globale", "synthese"):
            if champ not in resultat:
                raise ValueError(f"Champ '{champ}' manquant dans le résultat go/no-go.")
        if resultat["verdict"] not in ("go", "no_go", "conditionnel"):
            raise ValueError(f"Verdict invalide : '{resultat['verdict']}'")

    # ══════════════════════════════════════════════════════════════════════════
    # Brief créatif pré-génération script
    # ══════════════════════════════════════════════════════════════════════════

    def brief_creatif(
        self,
        titre: str,
        resume: str,
        morale: str,
        type_episode: str = "standard",
        *,
        episode_plan: dict | None = None,
        contexte_saison: dict | None = None,
        max_retry: int = 3,
    ) -> dict:
        """Génère un brief créatif pour guider le scripteur.

        Le directeur donne des directives sur le ton, le rythme, les SFX
        attendus, les moments clés à ne pas manquer, et les pièges à éviter.

        Args:
            titre: Titre de l'épisode.
            resume: Résumé de l'histoire biblique.
            morale: Morale de l'épisode.
            type_episode: Type (standard, ouverture, final, etc.).
            episode_plan: Plan de l'épisode depuis le planificateur.
            contexte_saison: Contexte de la saison (fil rouge, arcs, etc.).
            max_retry: Nombre de tentatives de parsing JSON.

        Returns:
            Dict avec clés : "directives_ton", "moments_cles", "sfx_attendus",
            "pieges_a_eviter", "accroche_suggestion", "ambiances_suggerees".
        """
        system_prompt = _SYSTEM_PROMPT_BRIEF_CREATIF

        user_parts = [
            f"TITRE : {titre}",
            f"TYPE D'ÉPISODE : {type_episode}",
            f"RÉSUMÉ BIBLIQUE : {resume}",
            f"MORALE : {morale}",
        ]

        if episode_plan:
            user_parts.append(f"PRÉTEXTE (scène de vie) : {episode_plan.get('pretexte', '?')}")
            user_parts.append(f"AMBIANCE PRÉVUE : {episode_plan.get('ambiance', '?')}")
            if episode_plan.get("arcs_personnages"):
                user_parts.append("ARCS PERSONNAGES :")
                for perso, arc in episode_plan["arcs_personnages"].items():
                    user_parts.append(f"  - {perso} : {arc}")

        if contexte_saison:
            user_parts.append(f"\nFIL ROUGE SAISON : {contexte_saison.get('fil_rouge', '?')}")
            user_parts.append(f"THÈME SAISON : {contexte_saison.get('theme', '?')}")

        user_parts.append(
            "\nDonne tes directives créatives pour que le scripteur "
            "produise un épisode de qualité broadcast."
        )

        client = anthropic.Anthropic()
        derniere_erreur = None

        for tentative in range(1, max_retry + 1):
            try:
                response = config.appel_claude_avec_retry(
                    client,
                    model=config.CLAUDE_MODEL,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": "\n".join(user_parts)}],
                )
                resultat = parser_json_llm(response.content[0].text)
                self._valider_resultat_brief(resultat)
                return resultat

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                derniere_erreur = e
                if tentative < max_retry:
                    logger.warning(
                        "Directeur brief créatif — parsing tentative %d/%d : %s",
                        tentative, max_retry, e,
                    )
                    continue
                raise ValueError(
                    f"Directeur Podcast (brief créatif) : impossible de parser "
                    f"après {max_retry} tentatives."
                ) from derniere_erreur

        raise ValueError("Directeur Podcast (brief créatif) : aucun résultat obtenu.")  # pragma: no cover

    @staticmethod
    def _valider_resultat_brief(resultat: dict) -> None:
        """Vérifie la structure minimale du brief créatif."""
        for champ in ("directives_ton", "moments_cles", "pieges_a_eviter"):
            if champ not in resultat:
                raise ValueError(f"Champ '{champ}' manquant dans le brief créatif.")
