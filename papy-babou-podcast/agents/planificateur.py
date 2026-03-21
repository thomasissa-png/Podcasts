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
11. UN PERSONNAGE BIBLIQUE PAR ÉPISODE — RÈGLE ABSOLUE :
    Chaque épisode doit couvrir UN personnage biblique DIFFÉRENT de manière COMPLÈTE.
    INTERDIT : plusieurs épisodes sur le même personnage (ex: Moïse épisode 1 + Moïse
    épisode 5, ou Joseph épisode 3 + Joseph épisode 4). INTERDIT : "partie 1 / partie 2".
    Le plan sera REJETÉ automatiquement si un personnage apparaît dans plus d'1 épisode.
    Pour chaque personnage, choisir le moment le PLUS emblématique et raconter l'histoire
    COMPLÈTE de A à Z en un seul épisode (15-20 min = largement suffisant).
    Exemples CORRECTS (10 épisodes, 10 personnages/histoires différents) :
    Ep1=Création du monde, Ep2=Noé, Ep3=Abraham, Ep4=Joseph,
    Ep5=Moïse, Ep6=David, Ep7=Salomon, Ep8=Daniel, Ep9=Jonas, Ep10=Esther.
    Exemples INTERDITS :
    Ep1=Moïse et le buisson, Ep2=Moïse et l'Exode, Ep3=Moïse et la mer Rouge (3x Moïse!)
    Ep1=Joseph vendu, Ep2=Joseph en Égypte, Ep3=Joseph viceroy (3x Joseph!)
    Le fil rouge passe par les PERSONNAGES RÉCURRENTS (Papy, Antoine, Noémie) et le
    THÈME de la saison, PAS par la répétition du même personnage biblique.
12. ORDRE CHRONOLOGIQUE — RÈGLE ABSOLUE : Les histoires bibliques DOIVENT être
    présentées dans l'ordre chronologique de la Bible / de l'Histoire. C'est un
    podcast éducatif pour enfants : on suit le fil de l'Histoire de manière
    progressive. Exemples pour l'Ancien Testament : Création →
    Noé → Abraham → Joseph → Moïse → David → Salomon → Daniel → Jonas → Esther.
    Exemples pour la vie de Jésus : Annonciation → Nativité → Fuite en Égypte →
    Baptême → Premiers miracles → Paraboles → Entrée à Jérusalem → Cène → Passion.
    JAMAIS un épisode tardif de la saison sur un événement antérieur à l'épisode 1.

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
        "histoire_biblique": "UNE histoire biblique UNIQUE et DISTINCTE des autres épisodes (ex: 'David contre Goliath', 'Jonas et la baleine')",
        "resume": "Résumé COMPLET de l'histoire de A à Z — début, milieu et fin. L'histoire doit être TERMINÉE dans cet épisode, jamais reportée au suivant.",
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
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=300.0)

    def planifier_saison(
        self,
        numero_saison: int,
        theme: str,
        description: str = "",
        personnages_secondaires: list[str] | None = None,
        saisons_precedentes: list[dict] | None = None,
        nb_episodes: int = 10,
        preferences_producteur: str = "",
        archives_saisons: list[dict] | None = None,
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

        # Injecter le périmètre biblique de la saison (si défini)
        perimetre = config.PERIMETRES_SAISONS.get(numero_saison)
        episodes_imposes = None
        if perimetre:
            prompt += (
                f"\n⚠️ PÉRIMÈTRE BIBLIQUE OBLIGATOIRE pour la saison {numero_saison} :\n"
                f"  {perimetre['perimetre']}\n"
                f"  {perimetre['description']}\n"
                f"  Toute histoire hors de ce périmètre sera REJETÉE.\n\n"
            )
            episodes_imposes = perimetre.get("episodes_imposes")

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
                # Utiliser l'âge spécifique à la saison
                age = config.age_personnage(key, numero_saison)
                age_str = f", {age} ans" if age is not None else ""
                line = f"  - {nom} ({role}{age_str}) : {desc}"
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

        # Injecter les archives de saisons précédentes (continuité renforcée)
        if archives_saisons:
            prompt += "\nARCHIVES DE SAISONS PRÉCÉDENTES (continuité narrative) :\n"
            for archive in archives_saisons:
                prompt += f"\n  Saison {archive.get('numero', '?')} — {archive.get('theme', '?')} :\n"
                # Questions ouvertes non résolues
                questions = archive.get("questions_ouvertes_finales", [])
                if questions:
                    prompt += "    Questions ouvertes à reprendre :\n"
                    for q in questions[:5]:
                        prompt += f"      - {q}\n"
                # Moments clés
                moments = archive.get("moments_cles_saison", [])
                if moments:
                    prompt += "    Moments clés :\n"
                    for m in moments[-3:]:
                        prompt += f"      - {m.get('episode', '')}: {', '.join(m.get('moments', [])[:3])}\n"
                # Rituels de la saison précédente — directive d'évolution
                rituels = archive.get("rituels", {})
                if rituels:
                    prompt += "    Rituels de la saison précédente :\n"
                    for cle, val in rituels.items():
                        prompt += f"      - {cle} : {val}\n"
                    prompt += (
                        "    → ÉVOLUTION DES RITUELS : la nouvelle saison DOIT faire évoluer "
                        "les rituels existants (nouvelle accroche, nouveau running gag, "
                        "ou variation de l'ancien). Ne PAS réutiliser les mêmes rituels "
                        "à l'identique — les personnages grandissent et changent.\n"
                    )
                prompt += (
                    "    → La nouvelle saison DOIT faire référence aux questions "
                    "ouvertes et aux moments clés quand c'est naturel.\n"
                )

        if preferences_producteur:
            prompt += f"\n{preferences_producteur}\n"

        logger.info("Planification de la saison %d : %s", numero_saison, theme)

        max_tokens = 12000
        max_retry_truncated = 2

        # Boucle de validation avec retry automatique :
        # Si le plan généré ne passe pas la validation (doublons, ordre chrono,
        # nombre d'épisodes insuffisant...), on re-génère en injectant l'erreur
        # dans le prompt pour que Claude corrige.
        max_validation_retries = 3
        derniere_erreur = ""
        for validation_attempt in range(1, max_validation_retries + 1):
            # Si retry après erreur de validation, enrichir le prompt
            prompt_effectif = prompt
            if derniere_erreur:
                prompt_effectif = (
                    f"{prompt}\n\n"
                    f"⚠️ ERREUR DE VALIDATION (tentative {validation_attempt}/{max_validation_retries}) :\n"
                    f"Le plan précédent a été REJETÉ pour la raison suivante :\n"
                    f"  {derniere_erreur}\n\n"
                    f"Corrige ce problème et génère un nouveau plan valide."
                )
                logger.warning(
                    "Retry validation %d/%d — erreur précédente : %s",
                    validation_attempt, max_validation_retries, derniere_erreur,
                )

            # Génération avec retry sur max_tokens
            for attempt in range(1, max_retry_truncated + 1):
                response = config.appel_claude_avec_retry(
                    self.client,
                    model=config.CLAUDE_MODEL,
                    max_tokens=max_tokens,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt_effectif}],
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
                derniere_erreur = f"JSON malformé : {e}"
                if validation_attempt < max_validation_retries:
                    continue
                raise ValueError(
                    f"Le plan de saison n'est pas du JSON valide "
                    f"après {max_validation_retries} tentatives : {e}"
                )

            # Validation structurelle et chronologique
            try:
                self._valider_plan(plan)
            except ValueError as e:
                derniere_erreur = str(e)
                if validation_attempt < max_validation_retries:
                    continue
                raise

            # Validate episode count matches requested nb_episodes
            nb_generes = len(plan["saison"]["episodes"])
            if nb_generes != nb_episodes:
                logger.warning(
                    "Le LLM a généré %d épisodes au lieu de %d demandés. "
                    "Auto-correction du plan.",
                    nb_generes, nb_episodes,
                )
                if nb_generes > nb_episodes:
                    plan["saison"]["episodes"] = plan["saison"]["episodes"][:nb_episodes]
                else:
                    derniere_erreur = (
                        f"Le plan ne contient que {nb_generes} épisodes "
                        f"au lieu de {nb_episodes} demandés."
                    )
                    if validation_attempt < max_validation_retries:
                        continue
                    raise ValueError(derniere_erreur)

            # Plan valide — sortir de la boucle
            if derniere_erreur:
                logger.info(
                    "Plan corrigé après %d tentative(s) de validation.",
                    validation_attempt,
                )
            break

        # Forcer les histoire_biblique imposées (si définies dans le périmètre)
        if episodes_imposes:
            plan_eps = plan["saison"]["episodes"]
            for idx, histoire in enumerate(episodes_imposes):
                if idx < len(plan_eps):
                    ancien = plan_eps[idx].get("histoire_biblique", "")
                    if ancien != histoire:
                        logger.info(
                            "Épisode %d : histoire_biblique forcée '%s' → '%s'",
                            idx + 1, ancien, histoire,
                        )
                    plan_eps[idx]["histoire_biblique"] = histoire

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

        # Vérifier la variété des histoires bibliques — STRICT
        histoires = [ep.get("histoire_biblique", "") for ep in episodes if ep.get("histoire_biblique")]
        if histoires:
            # Doublons exacts
            if len(set(histoires)) < len(histoires):
                doublons = [h for h in set(histoires) if histoires.count(h) > 1]
                raise ValueError(
                    f"Histoires bibliques en doublon : {doublons}. "
                    f"Chaque épisode DOIT traiter une histoire biblique DIFFÉRENTE."
                )
            # Doublons par sujet principal (même personnage biblique dominant)
            # On extrait le premier NOM PROPRE (mot capitalisé) comme sujet principal.
            # NOTE : un même personnage (ex: Abraham, Moïse) peut apparaître dans
            # plusieurs épisodes SI les histoires bibliques sont différentes.
            # On avertit mais on ne rejette pas.
            import re as _re
            _MOTS_NON_SUJETS = {
                # Articles et prépositions
                "le", "la", "les", "l", "de", "du", "des", "un", "une",
                "et", "ou", "au", "aux", "à", "en", "par", "pour", "sur",
                "dans", "avec", "vers", "son", "sa", "ses",
                # Mots descriptifs courants dans les titres bibliques
                "histoire", "récit", "partie", "suite", "grand", "grande",
                "grands", "grandes", "petit", "petite", "premier", "première",
                "dernier", "dernière", "nouveau", "nouvelle",
                # Mots d'action/description (NE SONT PAS des sujets bibliques)
                "voyage", "combat", "sacrifice", "création", "construction",
                "destruction", "traversée", "conquête", "fuite", "chute",
                "naissance", "mort", "appel", "épreuve", "miracle",
                "prophétie", "promesse", "alliance", "exil", "retour",
                "jugement", "bénédiction", "malédiction", "trahison",
                "résurrection", "ascension", "vision", "songe", "rêve",
                "prière", "offrande", "guerre", "paix", "règne",
            }
            _sujets_principaux: list[str] = []
            for h in histoires:
                # Chercher le premier nom propre (capitalisé, > 2 lettres)
                noms_propres = [m for m in _re.findall(r"\b[A-ZÀ-Ü][a-zà-ü]{2,}", h)
                                if m.lower() not in _MOTS_NON_SUJETS]
                if noms_propres:
                    _sujets_principaux.append(noms_propres[0].lower())
                else:
                    # Fallback: premier mot significatif
                    mots = [m for m in h.lower().replace("\u2019", " ").replace("'", " ").split()
                            if m not in _MOTS_NON_SUJETS]
                    _sujets_principaux.append(mots[0] if mots else h.lower())
            from collections import Counter
            compteur = Counter(_sujets_principaux)
            repetitions = {s: c for s, c in compteur.items() if c > 1}
            if repetitions:
                details = []
                for sujet, count in repetitions.items():
                    eps = [histoires[i] for i, s in enumerate(_sujets_principaux) if s == sujet]
                    details.append(f"'{sujet}' dans {count} épisodes : {eps}")
                raise ValueError(
                    f"DOUBLONS DE PERSONNAGES BIBLIQUES — chaque épisode doit couvrir "
                    f"un personnage biblique DIFFÉRENT. "
                    f"{'; '.join(details)}. "
                    f"Choisir le moment le plus emblématique de chaque personnage."
                )

        # Vérifier l'ordre chronologique des histoires bibliques
        # Dictionnaire de personnages/événements bibliques → ordre approximatif
        _ORDRE_CHRONOLOGIQUE: dict[str, int] = {
            # Ancien Testament (0-99)
            "création": 1, "adam": 2, "ève": 2, "eve": 2, "caïn": 3, "cain": 3,
            "abel": 3, "noé": 5, "noe": 5, "déluge": 5, "babel": 6,
            "abraham": 10, "sara": 10, "sarah": 10, "isaac": 12,
            "jacob": 14, "ésaü": 14, "esau": 14, "rachel": 14,
            "joseph": 16, "égypte": 16,
            "moïse": 20, "moise": 20, "pharaon": 20, "exode": 21,
            "mer rouge": 21, "sinaï": 22, "sinai": 22, "commandements": 22,
            "josué": 25, "josue": 25, "jéricho": 25, "jericho": 25,
            "gédéon": 28, "gedeon": 28, "samson": 30, "dalila": 30,
            "ruth": 32, "samuel": 34,
            "saül": 36, "saul": 36, "david": 38, "goliath": 38,
            "salomon": 40, "temple": 40,
            "élie": 45, "elie": 45, "élisée": 46, "elisee": 46,
            "daniel": 48, "jonas": 50, "esther": 52,
            # Nouveau Testament — Jésus (100-199)
            "annonciation": 100, "nativité": 101, "nativite": 101,
            "mages": 102, "bethléem": 101, "bethleem": 101,
            "hérode": 103, "herode": 103, "nazareth": 105,
            "jean-baptiste": 110, "baptême": 110, "bapteme": 110,
            "cana": 112, "béatitudes": 114, "beatitudes": 114,
            "samaritain": 116, "lazare": 120,
            "multiplication": 118, "transfiguration": 122,
            "jérusalem": 125, "jerusalem": 125, "cène": 128, "cene": 128,
            "passion": 130, "crucifixion": 132, "golgotha": 132,
            # Nouveau Testament — après Jésus (200-299)
            "résurrection": 200, "resurrection": 200,
            "ascension": 202, "pentecôte": 204, "pentecote": 204,
            "pierre": 206, "étienne": 208, "etienne": 208,
            "paul": 210, "marie-madeleine": 201, "madeleine": 201,
            "philippe": 212, "jean": 215, "apocalypse": 220,
            # Saints chrétiens (300+)
            "françois": 330, "francois": 330, "assise": 330,
            "jeanne": 340, "arc": 340,
            "nicolas": 325, "myre": 325,
            "thérèse": 350, "therese": 350, "lisieux": 350,
            "teresa": 360, "calcutta": 360,
            "martin": 310, "patrick": 320,
        }
        if histoires:
            ordres_detectes: list[tuple[int, int, str]] = []  # (ep_num, ordre, histoire)
            for ep in episodes:
                h = ep.get("histoire_biblique", "")
                if not h:
                    continue
                # Chercher le meilleur match dans le dictionnaire
                h_lower = h.lower()
                meilleur_ordre = -1
                for cle, ordre in _ORDRE_CHRONOLOGIQUE.items():
                    if cle in h_lower:
                        if ordre > meilleur_ordre:
                            meilleur_ordre = ordre
                if meilleur_ordre >= 0:
                    ordres_detectes.append((ep.get("numero", 0), meilleur_ordre, h))

            # Vérifier que l'ordre est croissant
            if len(ordres_detectes) >= 2:
                inversions = []
                for i in range(len(ordres_detectes) - 1):
                    ep_num_a, ordre_a, hist_a = ordres_detectes[i]
                    ep_num_b, ordre_b, hist_b = ordres_detectes[i + 1]
                    if ordre_b < ordre_a:
                        inversions.append(
                            f"Ep{ep_num_a} ({hist_a[:40]}) → Ep{ep_num_b} ({hist_b[:40]})"
                        )
                if inversions:
                    logger.warning(
                        "Ordre chronologique biblique non respecté. "
                        "Inversions détectées : %s. "
                        "Le directeur podcast ou l'utilisateur pourra réordonner.",
                        "; ".join(inversions),
                    )

    @staticmethod
    def generer_archive_saison(plan: dict, historique: list[dict]) -> dict:
        """Génère une archive de fin de saison pour la continuité inter-saisons.

        L'archive contient :
        - Les arcs finaux des personnages (état d'arrivée)
        - Les questions ouvertes non résolues
        - Les moments clés de la saison
        - Le fil rouge et son état final
        - Les personnages secondaires introduits

        Args:
            plan: Plan de la saison terminée.
            historique: Historique des épisodes de cette saison.

        Returns:
            Archive structurée pour injection dans la saison suivante.
        """
        saison = plan.get("saison", {})
        archive = {
            "numero": saison.get("numero", 0),
            "theme": saison.get("theme", ""),
            "fil_rouge": saison.get("fil_rouge", ""),
            "arcs_personnages": saison.get("arcs_personnages", {}),
            "personnages_secondaires": saison.get("personnages_secondaires", []),
            "rituels": saison.get("rituels", {}),
            # Collecter les questions ouvertes non résolues de toute la saison
            "questions_ouvertes_finales": [],
            # Collecter les moments clés de chaque épisode
            "moments_cles_saison": [],
            # Collecter les évolutions de personnages
            "evolutions_personnages": [],
        }

        for ep in historique:
            questions = ep.get("questions_ouvertes", [])
            if questions:
                archive["questions_ouvertes_finales"].extend(questions)
            moments = ep.get("moments_cles", [])
            if moments:
                archive["moments_cles_saison"].append({
                    "episode": ep.get("episode_id", ""),
                    "moments": moments,
                })
            evolution = ep.get("evolutions_personnages", "")
            if evolution:
                archive["evolutions_personnages"].append({
                    "episode": ep.get("episode_id", ""),
                    "evolution": evolution,
                })

        # Dédupliquer les questions ouvertes
        archive["questions_ouvertes_finales"] = list(
            dict.fromkeys(archive["questions_ouvertes_finales"])
        )

        return archive

    @staticmethod
    def integrer_evenements_speciaux(plan: dict) -> dict:
        """Intègre les événements spéciaux (anniversaires, etc.) dans le plan.

        Lit config.EVENEMENTS_SPECIAUX et enrichit les épisodes concernés
        avec les détails de l'événement.

        Args:
            plan: Plan de saison à enrichir.

        Returns:
            Plan enrichi.
        """
        saison_num = plan.get("saison", {}).get("numero", 0)
        for ep in plan.get("saison", {}).get("episodes", []):
            cle = (saison_num, ep.get("numero", 0))
            evenement = config.EVENEMENTS_SPECIAUX.get(cle)
            if evenement:
                ep["evenement_special"] = evenement
                logger.info(
                    "Événement spécial intégré : S%02dE%02d — %s (%s)",
                    saison_num, ep["numero"],
                    evenement.get("type", ""),
                    evenement.get("personnage", ""),
                )
        return plan

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
