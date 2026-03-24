# Project Context — Gradient Agents Framework

## Identite
- **Nom du projet** : Gradient Agents
- **Secteur** : Framework multi-agents IA pour pilotage de projets digitaux (dev tools / productivity)
- **Stade** : Production
- **Type** : Open-source framework (pas un SaaS direct)

## Cible
- **Persona principal** : Thomas, 32 ans, developpeur indie / entrepreneur technique, lance des side projects seul, utilise Claude Code quotidiennement, frustre par le manque de structure quand il delegue a l'IA
- **Probleme principal** : Coordonner 19 agents IA specialises sans perdre la coherence entre les livrables, et fournir des prompts prets a l'emploi de qualite professionnelle
- **Alternative actuelle** : Prompts ad hoc, pas de framework, chaque projet repart de zero

## Positionnement
- **Promesse unique** : Une equipe complete de 19 agents IA coordonnes qui pilotent un projet digital de la strategie au deploiement
- **Ton de marque** : Expert et direct, sans jargon inutile, oriente action
- **3 mots** : Coordination, Expertise, Autonomie
- **Concurrent principal** : Cursor rules / custom instructions generiques — notre difference : orchestration multi-agents avec dependances et phases

## Objectifs
- **Objectif principal a 6 mois** : Framework de reference pour la coordination multi-agents sur Claude Code, 500+ utilisateurs GitHub
- **KPI North Star** : Nombre de projets lances avec le framework par semaine

## Stack technique
- **Frontend** : HTML/CSS/JS vanilla (index.html dashboard)
- **Backend** : N/A (framework de prompts, pas d'API)
- **Base de donnees** : N/A
- **Hebergement** : GitHub Pages
- **IA utilisee** : Claude Opus 4 + Claude Sonnet 4 (agents)

## Modele economique
- **Type** : Open-source
- **Pays** : International (francophone en priorite)
- **Donnees sensibles** : Non

## Budget & Contraintes
- **Budget infra mensuel** : 0 (GitHub Pages)
- **Budget acquisition mensuel** : 0
- **Timeline** : En production
- **Contraintes specifiques** : Les 59 prompts doivent etre auto-suffisants (fonctionner sans editer de fichiers manuellement)

## Notes libres
Mission actuelle : audit exhaustif des 59 prompts de la bibliotheque par les 18 agents du framework. Chaque agent evalue selon sa perspective propre.

## Historique des interventions agents
| Agent | Date | Fichiers | Decisions cles | Pourquoi |
|---|---|---|---|---|
| orchestrator | 2026-03-22 | docs/reviews/audit-59-prompts.md, docs/orchestration-plan.md | Audit complet des 59 prompts par 18 perspectives d'agents. Note globale 6.2/10. Top 5 : #1 Definir mon projet, #19 Landing page, #10 Valider la demande, #39 Plan de lancement, #14 Scope MVP. Bottom 5 : #49 Monitoring, #28 Modeles IA, #54 Creer agent, #55 Migration stack, #57 Post-mortem. 8 recommandations transversales, 18 prompts manquants identifies. | Audit demande par l'utilisateur pour evaluer la qualite de la bibliotheque avant amelioration. Methode : evaluation croisee multi-perspectives plutot qu'audit sequentiel pour capturer les lacunes transversales. |
