"""Agent Planificateur — Génère le plan complet d'une saison sérielle."""

import json
import logging
from pathlib import Path

import anthropic

import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Tu es un directeur éditorial de podcast sériel pour enfants (6-10 ans).
Tu planifies des saisons complètes de 10 épisodes pour le podcast
"Les Histoires de Papy Babou" (histoires bibliques racontées par un grand-père
à ses petits-enfants Antoine et Noémie).

Tes références sont les podcasts sériels pour enfants comme "Les Aventures de Tina"
ou "Les Voyages d'Amélie" : chaque saison a un THÈME, un ARC NARRATIF, et les
personnages ÉVOLUENT au fil des épisodes.

RÈGLES DE PLANIFICATION :
1. Les 10 épisodes doivent former un arc cohérent avec une progression thématique.
2. Chaque personnage principal doit avoir un arc émotionnel sur la saison.
3. Introduire des personnages secondaires progressivement (max 1-2 par saison).
4. Varier les ambiances et les formats au fil de la saison.
5. L'épisode 1 est l'ouverture (présentation du thème), l'épisode 10 est le final.
6. Prévoir des liens entre épisodes (rappels, fil rouge, running gags).
7. Chaque épisode a un teasing vers l'épisode suivant.
8. Adapter la difficulté et la profondeur au fil de la saison (progression).

FORMAT DE SORTIE — JSON STRICT :
{
  "saison": {
    "numero": 1,
    "theme": "Le thème central de la saison",
    "description": "Description de la saison en 2-3 phrases",
    "fil_rouge": "Le fil narratif qui relie tous les épisodes",
    "arcs_personnages": {
      "antoine": {
        "depart": "État émotionnel d'Antoine au début de la saison",
        "evolution": "Comment il évolue au fil des épisodes",
        "arrivee": "Où il en est à la fin de la saison"
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
        "id": "mamie_rose",
        "nom_complet": "Mamie Rose",
        "description": "Description du personnage",
        "apparait_episode": 3,
        "ton": "doux, malicieux",
        "relation": "Épouse de Papy Babou, apporte un autre regard sur les histoires",
        "tics_de_langage": ["Oh, ton Papy exagère toujours...", "Moi je me souviens que..."]
      }
    ],
    "rituels": {
      "accroche": "La phrase d'ouverture récurrente de Papy Babou",
      "au_revoir": "La formule de clôture récurrente",
      "running_gag": "Un gag récurrent dans la saison (optionnel)",
      "segment_recurrent": "Un segment spécial récurrent (ex: 'Le mot du jour', 'La question des enfants')"
    },
    "episodes": [
      {
        "numero": 1,
        "titre": "Titre de l'épisode",
        "type": "ouverture",
        "histoire_biblique": "Le récit biblique de base",
        "resume": "Résumé de ce qui sera raconté",
        "morale": "La leçon de vie",
        "ambiance": "joyeux|dramatique|calme|mystere",
        "duree_cible_minutes": 13,
        "personnages_presents": ["papy_babou", "antoine", "noemie"],
        "personnages_secondaires_presents": [],
        "arc_personnage_focus": "Le personnage dont l'arc progresse le plus dans cet épisode",
        "progression_arc": "Comment l'arc du personnage avance dans cet épisode",
        "lien_episode_precedent": "",
        "teasing_episode_suivant": "Ce que Papy promet pour la prochaine fois",
        "elements_fil_rouge": "Comment le fil rouge de la saison apparaît dans cet épisode",
        "moments_cles": ["Moment important 1", "Moment important 2"],
        "questions_ouvertes": ["Une question laissée en suspens pour les épisodes suivants"]
      }
    ]
  }
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après.
"""


class Planificateur:
    """Planifie une saison complète de 10 épisodes avec arcs narratifs."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def planifier_saison(
        self,
        numero_saison: int,
        theme: str,
        description: str = "",
        personnages_secondaires: list[str] | None = None,
        saisons_precedentes: list[dict] | None = None,
    ) -> dict:
        """Génère le plan complet d'une saison de 10 épisodes.

        Args:
            numero_saison: Numéro de la saison.
            theme: Thème central de la saison.
            description: Description libre du producteur.
            personnages_secondaires: Personnages à introduire cette saison.
            saisons_precedentes: Résumés des saisons précédentes.

        Returns:
            Plan de saison structuré.
        """
        prompt = (
            f"Planifie la saison {numero_saison} complète (10 épisodes) :\n"
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

        # Charger la bible des personnages pour contexte
        personnages = config.charger_personnages()
        if personnages:
            prompt += "\nBIBLE DES PERSONNAGES (référence) :\n"
            for key, perso in personnages.get("personnages", {}).items():
                prompt += f"  - {perso.get('nom_complet', key)} : {perso.get('description', '')}\n"

        logger.info("Planification de la saison %d : %s", numero_saison, theme)

        config.rate_limiter_anthropic.attendre()
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

        plan = json.loads(texte_brut)
        self._valider_plan(plan)

        logger.info(
            "Saison %d planifiée : %d épisodes, thème '%s'",
            numero_saison,
            len(plan["saison"]["episodes"]),
            plan["saison"]["theme"],
        )

        return plan

    def sauvegarder(self, plan: dict, chemin: Path) -> Path:
        """Sauvegarde le plan de saison en JSON."""
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        logger.info("Plan de saison sauvegardé : %s", chemin)
        return chemin

    @staticmethod
    def _valider_plan(plan: dict) -> None:
        """Valide la structure du plan de saison."""
        if "saison" not in plan:
            raise ValueError("Le plan doit contenir une clé 'saison'.")
        saison = plan["saison"]
        for champ in ("numero", "theme", "episodes"):
            if champ not in saison:
                raise ValueError(f"Champ manquant dans saison : '{champ}'")
        if not saison["episodes"]:
            raise ValueError("La saison doit contenir au moins un épisode.")
        for i, ep in enumerate(saison["episodes"]):
            for champ in ("numero", "titre", "resume", "morale"):
                if champ not in ep:
                    raise ValueError(
                        f"Champ '{champ}' manquant dans l'épisode {i + 1}."
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
