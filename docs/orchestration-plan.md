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
- Statut : Termine
- Livrable : docs/infra/backend-audit.md
- Verdict : OK — F4 GA4 identifie comme seul gap majeur (0% implemente)

**Agent 2 : @qa** — Audit couverture tests vs specs
- Statut : Termine
- Livrable : docs/qa/qa-strategy.md (enrichi avec matrice critere-par-critere)
- Verdict : OK — 3 gaps P0 critiques (launch-fresh, kill-productions, seg_003), F4 bloquant

### Phase consolidation

**Orchestrateur** — Synthese croisee
- Statut : Termine
- Livrable : docs/orchestration-plan.md (ce fichier)

## Feedbacks remontants
| # | Severite | Agent source | Agent cible | Probleme | Statut |
|---|---|---|---|---|---|
| 1 | P0 | @qa | @fullstack | F4 GA4 completement absent — North Star KPI impossible | Ouvert — a implementer |
| 2 | P0 | @qa | @qa | Zero test pour launch-fresh, kill-productions, seg_003 | Ouvert — tests a ecrire |

## Decisions d'arbitrage
| # | Sujet | Decision | Justification | Agents impactes |
|---|---|---|---|---|
| 1 | Priorite F4 vs tests P0 | Implementer F4 EN PARALLELE des tests P0 | F4 bloque le North Star, les tests P0 bloquent la confiance prod | @fullstack (F4), @qa (tests) |
| 2 | Verification seg_003 | Garder manuelle (via SQL) | Route dediee nice-to-have (P3), verification actuelle suffisante | — |
