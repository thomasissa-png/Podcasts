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

ÉVALUATION EN 5 AXES (chacun noté sur 10) :

1. IMMERSION SONORE (note/10)
   - Les SFX sont-ils bien placés, variés, et immersifs ?
   - Les ambiances par acte créent-elles un voyage sonore ?
   - Les transitions entre scènes sont-elles fluides ?
   - Le sound design compense-t-il les limites des voix IA ?

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
            "valeur_educative", "compatibilite_voix_ia",
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
