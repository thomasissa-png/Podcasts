# Plan d'orchestration — Les Histoires de Papy Babou

## Session du 2026-03-25/26 — Cloturee

### Demande utilisateur initiale
Orchestration complete du projet : strategie, specs, audit backend, preparation production audio.

### Mode detecte
Projet existant (stade Beta, 28 sessions dev anterieures) — orchestration multi-phase sur fondations existantes

### Profil utilisateur
- Niveau technique : Expert
- Ton de communication : Technique
- Mode d'interaction : Standard (validation entre phases)

### Complexite realisee
Lourde — 8 agents invoques, 20 interventions, 16 livrables

---

## Phase 0 — Strategie (TERMINEE)

**@creative-strategy** — Brand platform + personas + benchmark + creative brief
- Statut : Termine
- Livrables : docs/strategy/brand-platform.md, docs/strategy/personas.md, docs/strategy/competitive-benchmark.md, docs/strategy/creative-brief.md
- Verdict : OK
- Decisions cles : Espace libre confirme (Bible + seriel + immersif = 0 concurrent direct). Archetype Sage Conteur. Camille (parent non-pratiquant) = persona croissance. "catechisme" banni.

**@data-analyst** — KPI framework
- Statut : Termine
- Livrables : docs/analytics/kpi-framework.md
- Verdict : OK
- Decisions cles : North Star = 3 000 ecoutes completes/mois (>= 80% duree). Umami comme outil (choix fondateur).

**@product-manager** — Vision, roadmap, backlog
- Statut : Termine
- Livrables : docs/product/product-vision.md, docs/product/roadmap.md, docs/product/backlog.md
- Verdict : OK
- Decisions cles : 2 phases (S1 production → SaaS). 3 bugs P0 confirmes deja corriges. 5 questions Phase 2 en attente.

**@creative-strategy** — Value proposition
- Statut : Termine
- Livrable : docs/strategy/value-proposition.md
- Verdict : OK

**@copywriter** — Brand voice
- Statut : Termine
- Livrable : docs/copy/brand-voice.md
- Verdict : OK
- Decisions cles : Double registre Sophie/Camille. 8 mots interdits. 3 variantes UVP.

## Phase 1 — Specs & QA (TERMINEE)

**@product-manager** — Functional specs
- Statut : Termine
- Livrable : docs/product/functional-specs.md
- Verdict : OK
- Decisions cles : 4 features specifiees Given/When/Then. Seuil 9/10 bloquant.

**@data-analyst** — KPI enrichi (mapping features)
- Statut : Termine
- Livrable : docs/analytics/kpi-framework.md (section 3)
- Verdict : OK

**@qa** — QA strategy + tests
- Statut : Termine
- Livrables : docs/qa/qa-strategy.md, papy-babou-podcast/tests/test_web_routes_critiques.py (19 tests, 19 passes)
- Verdict : OK

## Phase 2 — Audit Backend (TERMINEE)

**@infrastructure** — Backend audit
- Statut : Termine
- Livrable : docs/infra/backend-audit.md
- Verdict : OK — F1-F3 couvertes, F4 resolue par Umami existant

**@fullstack** — Confirmation Umami
- Statut : Termine (confirmation sans code)
- Verdict : OK — Umami deja implemente

**@qa** — Tests routes critiques
- Statut : Termine
- Livrable : papy-babou-podcast/tests/test_web_routes_critiques.py
- Verdict : OK — 19/19 passes

## Fix direct — Montage count mismatch
- Statut : Termine
- Fix : 6 lignes dans web.py (filter par episode_id dans requete SQL montage count)

---

## Feedbacks remontants
| # | Severite | Agent source | Agent cible | Probleme | Statut |
|---|---|---|---|---|---|
| 1 | P0 | @qa | — | F4 GA4 → resolue : Umami deja implemente (choix fondateur) | Ferme |
| 2 | P0 | @qa | @qa | Tests launch-fresh, kill-productions, seg_003 | Ferme — 19 tests ecrits et passes |

## Decisions d'arbitrage
| # | Sujet | Decision | Justification |
|---|---|---|---|
| 1 | Tracking analytics | Umami (pas GA4) | Choix fondateur — deja implemente, pas de cookie banner necessaire |
| 2 | Verification seg_003 | Manuelle via SQL | Route dediee = nice-to-have P3 |
| 3 | Phase 2 SaaS | En attente | 5 questions fondateur sans reponse — pas de dev avant arbitrage |
| 4 | Priorite prochaine session | Production audio S01E01 | Script valide 9.2/10, checkpoint pret, pipeline fonctionnel |

## Cloture de session

**Fichiers de cloture produits** :
- docs/lessons-learned.md — apprentissages de la session
- docs/founder-preferences.md — preferences fondateur detectees
- project-context.md — memo de reprise et historique mis a jour
- docs/orchestration-plan.md — etat final du plan

**Metriques d'orchestration** :
- Agents invoques : 8/19 (@orchestrator, @creative-strategy, @data-analyst, @product-manager, @copywriter, @qa, @infrastructure, @fullstack)
- Interventions totales : 20 (dont 3 Explore agent, 1 fix direct)
- Echecs Task : 1 (product-manager timeout — resolu a la relance avec prompt raccourci)
- Relances correctives : 1 (product-manager)
- Feedbacks remontants : 2 (P0 GA4 resolue par Umami, P0 tests routes critiques)
- Phases completees : Phase 0 (Strategie) + Phase 1 (Specs/QA) + Phase 2 (Audit Backend)
- Drift detecte : NON
- Livrables produits : 19 fichiers (17 dans docs/ + 1 test + 1 fix web.py)
- Score moyen des livrables : non score formellement par @reviewer (pas de fin de run complete)

## Prochaines etapes (par priorite)
1. **PRIORITE 1** : Lancer production audio S01E01 (web dashboard, ~30-45 min). Script valide 9.2/10, checkpoint pret.
2. **PRIORITE 2** : Auditer scripts E03/E04 avec @audit-episode (scripts presents, audit manquant)
3. **PRIORITE 3** : Ecrire + auditer scripts E05-E10 (Moise, David, Salomon, Daniel, Jonas, Esther)
4. **PRIORITE 4** : Repondre aux 5 questions fondateur Phase 2 SaaS (docs/product/product-vision.md)
5. **P2** : CSRF + rate limiting login, newsletter backend, V2 admin JS incomplet
6. **Quand 10 episodes produits** : Soumettre RSS a Apple Podcasts + Spotify. Lancer Phase 3 (Contenu/SEO) + Phase 4 (Acquisition).
