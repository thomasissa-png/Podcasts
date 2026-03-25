# Plan d'orchestration — Audit Backend vs Specs

## Demande utilisateur
Auditer le backend (web.py + main.py) pour verifier qu'il matche les specifications fonctionnelles du @product-manager (functional-specs.md, backlog.md).

## Mode detecte
Projet existant (stade Beta, historique riche) — audit cible, pas de lancement complet

## Profil utilisateur
- Niveau technique : Expert
- Ton de communication : Technique
- Mode d'interaction : Standard

## Complexite estimee
Moyenne — 2 agents, 1 phase

## Plan par phase

### Phase unique — Audit backend parallele

**Agent 1 : @infrastructure** — Audit technique des routes web.py
- Statut : En cours
- Livrable attendu : docs/infra/backend-audit.md
- Verdict verification : En attente

**Agent 2 : @qa** — Audit couverture tests vs specs
- Statut : En cours
- Livrable attendu : docs/qa/qa-strategy.md (mis a jour avec matrice enrichie)
- Verdict verification : En attente

## Feedbacks remontants
| # | Severite | Agent source | Agent cible | Probleme | Statut |
|---|---|---|---|---|---|

## Decisions d'arbitrage
| # | Sujet | Decision | Justification | Agents impactes |
|---|---|---|---|---|
