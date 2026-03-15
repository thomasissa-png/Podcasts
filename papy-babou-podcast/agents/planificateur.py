"""Agent Planificateur — Génère le plan complet d'une saison sérielle."""

import json
import logging
from pathlib import Path

import anthropic

import config
from utils import parser_json_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Tu es un directeur éditorial de podcast sériel pour enfants (6-10 ans).
Tu planifies des séries complètes pour le podcast
"Les Histoires de Papy Babou" (histoires bibliques racontées par un grand-père
à ses petits-enfants Antoine et Noémie).

Tes références sont les podcasts sériels pour enfants comme "Les Aventures de Tina"
ou "Les Voyages d'Amélie" : chaque série a un THÈME, un ARC NARRATIF, et les
personnages ÉVOLUENT au fil des épisodes.

RÈGLES DE PLANIFICATION :
1. Les épisodes doivent former un arc cohérent avec une progression thématique.
2. Chaque personnage principal doit avoir un arc émotionnel sur la série.
3. Introduire des personnages secondaires progressivement (max 1-2 par série).
4. Varier les ambiances et les formats au fil de la série.
5. Le premier épisode est l'ouverture (présentation du thème), le dernier est le final.
6. Prévoir des liens entre épisodes (rappels, fil rouge, running gags).
7. Chaque épisode a un teasing NATUREL vers l'épisode suivant. Le teasing doit être
   formulé comme Papy le dirait naturellement, PAS avec du langage méta.
   BON : "Ce que Papy promet de raconter la prochaine fois que les enfants viendront"
   MAUVAIS : "Dans le prochain épisode..." / "La semaine prochaine..."
8. Adapter la difficulté et la profondeur au fil de la série (progression).
9. Chaque épisode doit avoir un PRÉTEXTE NATUREL qui amène l'histoire :
   goûter chez Papy, jour de pluie, histoire du soir, promenade, vieux livre trouvé,
   événement du quotidien qui fait penser à une histoire biblique, etc.
   Varier les prétextes d'un épisode à l'autre.
10. DURÉES par type : ouverture ~30 min, standard ~25 min, mi-saison ~30 min,
    final ~35 min, bonus ~20 min. Indiquer la durée correspondante au type.

FORMAT DE SORTIE — JSON STRICT :
{
  "saison": {
    "numero": 1,
    "theme": "Le thème central de la série",
    "description": "Description de la série en 2-3 phrases",
    "fil_rouge": "Le fil narratif qui relie tous les épisodes",
    "arcs_personnages": {
      "antoine": {
        "depart": "État émotionnel d'Antoine au début",
        "evolution": "Comment il évolue au fil des épisodes",
        "arrivee": "Où il en est à la fin"
      },
      "noemie": {
        "depart": "...",
        "evolution": "...",
        "arrivee": "..."
      },
      "papy_babou": {
        "depart": "...",
        "evolution": "...",
        "arrivee": "..."
      }
    },
    "personnages_secondaires": [
      {
        "id": "mamie_sonia",
        "nom_complet": "Mamie Sonia",
        "description": "Description du personnage",
        "apparait_episode": 2,
        "ton": "doux, chaleureux",
        "relation": "Épouse de Papy Babou, apporte un autre regard sur les histoires",
        "tics_de_langage": ["Mes petits chéris...", "Votre Papy exagère toujours un peu..."]
      }
    ],
    "rituels": {
      "accroche": "La phrase d'accroche récurrente de Papy Babou (naturelle, pas de format émission)",
      "au_revoir": "La formule de clôture récurrente (chaleureuse, familiale)",
      "running_gag": "Un gag récurrent (optionnel)",
      "segment_recurrent": "Un segment spécial récurrent (ex: 'Le mot du jour', 'La question des enfants')"
    },
    "episodes": [
      {
        "numero": 1,
        "titre": "Titre de l'épisode",
        "type": "ouverture",
        "histoire_biblique": "Le récit biblique de base",
        "resume": "Résumé de ce qui sera raconté — doit couvrir l'INTÉGRALITÉ de l'histoire, pas juste une introduction",
        "morale": "La leçon de vie",
        "ambiance": "joyeux|dramatique|calme|mystere",
        "duree_cible_minutes": 30,
        "pretexte": "Le prétexte naturel qui amène l'histoire (ex: 'Jour de pluie, coincés à la maison')",
        "personnages_presents": ["papy_babou", "antoine", "noemie"],
        "personnages_secondaires_presents": [],
        "arc_personnage_focus": "Le personnage dont l'arc progresse le plus dans cet épisode",
        "progression_arc": "Comment l'arc du personnage avance dans cet épisode",
        "lien_episode_precedent": "",
        "teasing_episode_suivant": "Ce que Papy promet de raconter la prochaine fois (langage naturel)",
        "elements_fil_rouge": "Comment le fil rouge apparaît dans cet épisode",
        "moments_cles": ["Moment important 1", "Moment important 2"],
        "questions_ouvertes": ["Une question laissée en suspens pour les épisodes suivants"]
      }
    ]
  }
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""


class Planificateur:
    """Planifie une saison complète avec arcs narratifs."""

    def __init__(self):
        if not config.ANTHROPIC_API_KEY:
            raise ValueError(
                "Cle API Anthropic (ANTHROPIC_API_KEY) non configuree. "
                "Ajoutez-la dans votre fichier .env ou dans les Secrets Replit."
            )
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def planifier_saison(
        self,
        numero_saison: int,
        theme: str,
        description: str = "",
        personnages_secondaires: list[str] | None = None,
        saisons_precedentes: list[dict] | None = None,
        nb_episodes: int = 10,
        preferences_producteur: str = "",
    ) -> dict:
        """Génère le plan complet d'une saison.

        Args:
            numero_saison: Numéro de la saison.
            theme: Thème central de la saison.
            description: Description libre du producteur.
            personnages_secondaires: Personnages à introduire cette saison.
            saisons_precedentes: Résumés des saisons précédentes.
            nb_episodes: Nombre d'épisodes dans la saison (défaut : 10).
            preferences_producteur: Bloc de preferences du producteur.

        Returns:
            Plan de saison structuré.
        """
        prompt = (
            f"Planifie la saison {numero_saison} complète ({nb_episodes} épisodes) :\n"
            f"- Thème : {theme}\n"
        )

        if description:
            prompt += f"- Description / vision du producteur : {description}\n"

        if personnages_secondaires:
            prompt += (
                f"- Personnages secondaires à introduire : "
                f"{', '.join(personnages_secondaires)}\n"
            )

        if saisons_precedentes:
            prompt += "\nSAISONS PRÉCÉDENTES :\n"
            for s in saisons_precedentes:
                prompt += (
                    f"  - Saison {s.get('numero', '?')} : {s.get('theme', '?')} "
                    f"({s.get('description', '')})\n"
                )
                # Continuité inter-saisons : passer les arcs finaux des personnages
                arcs = s.get("saison", {}).get("arcs_personnages", {})
                if arcs:
                    prompt += "    Arcs de personnages (fin de saison) :\n"
                    for perso, arc in arcs.items():
                        nom = perso.replace("_", " ").title()
                        prompt += (
                            f"      - {nom} : terminé à \"{arc.get('arrivee', '?')}\"\n"
                        )
                    prompt += (
                        "    → La nouvelle saison DOIT continuer ces arcs "
                        "(l'état d'arrivée devient le nouveau départ).\n"
                    )

        # Charger la bible des personnages pour contexte
        personnages = config.charger_personnages()
        if personnages:
            prompt += "\nBIBLE DES PERSONNAGES (référence) :\n"
            for key, perso in personnages.get("personnages", {}).items():
                nom = perso.get("nom_complet", key)
                desc = perso.get("description", "")
                role = perso.get("role", "principal")
                line = f"  - {nom} ({role}) : {desc}"
                backstory = perso.get("backstory", "")
                if backstory:
                    line += f"\n    Backstory : {backstory}"
                anecdotes = perso.get("anecdotes_possibles", [])
                if anecdotes:
                    line += f"\n    Anecdotes possibles : {'; '.join(anecdotes)}"
                regles_perso = perso.get("regles", [])
                if regles_perso:
                    line += f"\n    Règles : {'; '.join(regles_perso)}"
                prompt += line + "\n"

        if preferences_producteur:
            prompt += f"\n{preferences_producteur}\n"

        logger.info("Planification de la saison %d : %s", numero_saison, theme)

        max_tokens = 12000
        max_retry_truncated = 2
        for attempt in range(1, max_retry_truncated + 1):
            response = config.appel_claude_avec_retry(
                self.client,
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            if response.stop_reason == "max_tokens":
                if attempt < max_retry_truncated:
                    max_tokens = min(int(max_tokens * 1.5), 16384)
                    logger.warning(
                        "Plan tronqué (max_tokens atteint). "
                        "Retry %d/%d avec max_tokens=%d",
                        attempt, max_retry_truncated, max_tokens,
                    )
                    continue
                else:
                    raise ValueError(
                        f"Le plan de saison dépasse la limite de tokens "
                        f"({max_tokens}) même après {max_retry_truncated} "
                        f"tentatives. Essayez avec moins d'épisodes."
                    )
            break

        texte_brut = response.content[0].text.strip()
        try:
            plan = parser_json_llm(texte_brut)
        except json.JSONDecodeError as e:
            logger.warning(
                "JSON malformé dans le plan LLM (%s). "
                "Retry avec une nouvelle génération...", e,
            )
            response = config.appel_claude_avec_retry(
                self.client,
                model=config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            if response.stop_reason == "max_tokens":
                raise ValueError(
                    f"Le plan de saison dépasse la limite de tokens "
                    f"({max_tokens}). Le JSON est tronqué et inutilisable."
                )
            texte_brut = response.content[0].text.strip()
            plan = parser_json_llm(texte_brut)
        self._valider_plan(plan)

        # Validate episode count matches requested nb_episodes
        nb_generes = len(plan["saison"]["episodes"])
        if nb_generes != nb_episodes:
            logger.warning(
                "Le LLM a généré %d épisodes au lieu de %d demandés. "
                "Auto-correction du plan.",
                nb_generes, nb_episodes,
            )
            if nb_generes > nb_episodes:
                # Truncate excess episodes
                plan["saison"]["episodes"] = plan["saison"]["episodes"][:nb_episodes]
            else:
                raise ValueError(
                    f"Le plan ne contient que {nb_generes} épisodes "
                    f"au lieu de {nb_episodes} demandés. "
                    f"Relancez la planification."
                )

        logger.info(
            "Saison %d planifiée : %d épisodes, thème '%s'",
            numero_saison,
            len(plan["saison"]["episodes"]),
            plan["saison"]["theme"],
        )

        return plan

    def sauvegarder(self, plan: dict, chemin: Path) -> Path:
        """Sauvegarde le plan de saison en JSON.

        La sauvegarde en DB est gérée par la commande CLI planifier-saison
        pour éviter les doublons.
        """
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        logger.info("Plan de saison sauvegardé (JSON) : %s", chemin)
        return chemin

    @staticmethod
    def _valider_plan(plan: dict) -> None:
        """Valide la structure et la cohérence du plan de saison."""
        if "saison" not in plan:
            raise ValueError("Le plan doit contenir une clé 'saison'.")
        saison = plan["saison"]
        for champ in ("numero", "theme", "episodes"):
            if champ not in saison:
                raise ValueError(f"Champ manquant dans saison : '{champ}'")
        if not saison["episodes"]:
            raise ValueError("La saison doit contenir au moins un épisode.")

        episodes = saison["episodes"]
        for i, ep in enumerate(episodes):
            for champ in ("numero", "titre", "resume", "morale"):
                if champ not in ep:
                    raise ValueError(
                        f"Champ '{champ}' manquant dans l'épisode {i + 1}."
                    )

        # Validation de cohérence (warnings, pas d'erreurs)
        # Vérifier les types d'épisodes
        types = [ep.get("type", "standard") for ep in episodes]
        if len(episodes) >= 3:
            if types[0] != "ouverture":
                logger.warning(
                    "L'épisode 1 devrait être de type 'ouverture' (trouvé : '%s').",
                    types[0],
                )
            if types[-1] != "final":
                logger.warning(
                    "Le dernier épisode devrait être de type 'final' (trouvé : '%s').",
                    types[-1],
                )

        # Vérifier la variété des ambiances (strict si ≥ 5 épisodes)
        ambiances = [ep.get("ambiance", "") for ep in episodes if ep.get("ambiance")]
        if ambiances:
            nb_uniques = len(set(ambiances))
            if len(episodes) >= 5 and nb_uniques < 3:
                raise ValueError(
                    f"Variété d'ambiances insuffisante : seulement {nb_uniques} "
                    f"ambiance(s) distincte(s) ({set(ambiances)}) pour "
                    f"{len(episodes)} épisodes. Minimum requis : 3."
                )
            elif nb_uniques < min(3, len(ambiances)):
                logger.warning(
                    "Faible variété d'ambiances dans la saison : %s. "
                    "Pensez à varier pour maintenir l'intérêt.",
                    set(ambiances),
                )

        # Vérifier la variété des histoires bibliques
        histoires = [ep.get("histoire_biblique", "") for ep in episodes if ep.get("histoire_biblique")]
        if histoires and len(set(histoires)) < len(histoires):
            doublons = [h for h in set(histoires) if histoires.count(h) > 1]
            logger.warning(
                "Histoires bibliques en doublon dans la saison : %s",
                doublons,
            )

    def exporter_csv(self, plan: dict, chemin: Path) -> Path:
        """Exporte le planning en CSV pour partage éditorial."""
        import csv

        chemin.parent.mkdir(parents=True, exist_ok=True)
        saison = plan["saison"]

        with open(chemin, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Saison", "Episode", "Titre", "Type", "Histoire biblique",
                "Morale", "Ambiance", "Durée (min)", "Personnages secondaires",
                "Teasing", "Arc focus",
            ])
            for ep in saison["episodes"]:
                writer.writerow([
                    saison["numero"],
                    ep["numero"],
                    ep["titre"],
                    ep.get("type", "standard"),
                    ep.get("histoire_biblique", ""),
                    ep["morale"],
                    ep.get("ambiance", ""),
                    ep.get("duree_cible_minutes", 13),
                    ", ".join(ep.get("personnages_secondaires_presents", [])),
                    ep.get("teasing_episode_suivant", ""),
                    ep.get("arc_personnage_focus", ""),
                ])

        logger.info("Planning CSV exporté : %s", chemin)
        return chemin

    def exporter_markdown(self, plan: dict, chemin: Path) -> Path:
        """Exporte le planning en Markdown pour documentation."""
        chemin.parent.mkdir(parents=True, exist_ok=True)
        saison = plan["saison"]

        lignes = [
            f"# Saison {saison['numero']} — {saison['theme']}",
            "",
            f"> {saison.get('description', '')}",
            "",
            f"**Fil rouge :** {saison.get('fil_rouge', '')}",
            "",
        ]

        # Arcs
        arcs = saison.get("arcs_personnages", {})
        if arcs:
            lignes.append("## Arcs de personnages")
            lignes.append("")
            for perso, arc in arcs.items():
                lignes.append(f"### {perso.replace('_', ' ').title()}")
                lignes.append(f"- **Départ :** {arc.get('depart', '')}")
                lignes.append(f"- **Évolution :** {arc.get('evolution', '')}")
                lignes.append(f"- **Arrivée :** {arc.get('arrivee', '')}")
                lignes.append("")

        # Personnages secondaires
        secondaires = saison.get("personnages_secondaires", [])
        if secondaires:
            lignes.append("## Personnages secondaires")
            lignes.append("")
            for p in secondaires:
                lignes.append(
                    f"- **{p.get('nom_complet', p.get('id', '?'))}** "
                    f"(apparaît épisode {p.get('apparait_episode', '?')}) : "
                    f"{p.get('description', '')}"
                )
            lignes.append("")

        # Rituels
        rituels = saison.get("rituels", {})
        if rituels:
            lignes.append("## Rituels de la saison")
            lignes.append("")
            for cle, val in rituels.items():
                lignes.append(f"- **{cle.replace('_', ' ').title()} :** {val}")
            lignes.append("")

        # Épisodes
        lignes.append("## Épisodes")
        lignes.append("")
        for ep in saison["episodes"]:
            type_ep = ep.get("type", "standard")
            lignes.append(
                f"### E{ep['numero']:02d} — {ep['titre']} [{type_ep}]"
            )
            lignes.append(f"- **Histoire :** {ep.get('histoire_biblique', ep.get('resume', ''))}")
            lignes.append(f"- **Morale :** {ep['morale']}")
            lignes.append(f"- **Ambiance :** {ep.get('ambiance', '?')}")
            if ep.get("personnages_secondaires_presents"):
                lignes.append(
                    f"- **Personnages secondaires :** "
                    f"{', '.join(ep['personnages_secondaires_presents'])}"
                )
            if ep.get("arc_personnage_focus"):
                lignes.append(f"- **Arc focus :** {ep['arc_personnage_focus']}")
            if ep.get("teasing_episode_suivant"):
                lignes.append(f"- **Teasing :** _{ep['teasing_episode_suivant']}_")
            lignes.append("")

        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(lignes))

        logger.info("Planning Markdown exporté : %s", chemin)
        return chemin
