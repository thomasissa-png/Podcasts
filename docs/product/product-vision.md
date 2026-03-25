# Product Vision — Les Histoires de Papy Babou

> Produit par @product-manager — 2026-03-25

---

## Vision

Dans un monde où les familles ont accès à Papy Babou, les parents n'ont plus à choisir
entre divertir leurs enfants et leur transmettre quelque chose de substantiel.
Les grandes histoires de la Bible deviennent un rituel familial attendu — pas une obligation,
pas un cours, mais le moment du soir où tout le monde s'arrête pour écouter.
La qualité audio est indiscernable d'une production France Inter.
N'importe quel créateur solo peut reproduire ce pipeline pour son propre univers.

---

## Mission produit

Produire et distribuer 10 épisodes audio de la Saison 1 avec une qualité irréprochable,
puis transformer le pipeline de production en plateforme SaaS accessible à d'autres créateurs.

---

## Principes produit

1. **Qualité avant volume** — Un épisode à 9/10 vaut mieux que trois à 7/10. Le seuil d'audit ne descend pas.
2. **Le pipeline est le produit** — Chaque amélioration du workflow bénéficie à la fois à Papy Babou et au futur SaaS.
3. **Zéro régression audio** — Aucun épisode publié sans validation humaine du montage final.
4. **Historique exhaustif** — Chaque décision de production (script, audit, montage, publication) est traçable.
5. **Un workflow, une persona** — Le back-office est conçu pour le Producteur solo, pas pour une équipe.

---

## Phase 1 — Produire la Saison 1 (maintenant → lancement)

**Objectif** : 10 épisodes produits, audités, montés et publiés sur Apple Podcasts + Spotify + site web.

**Ce qui existe déjà (ne pas reconstruire) :**
- Pipeline complet Python (scripteur → reviewer → directeur_podcast → TTS → SFX → montage → métadonnées → publication)
- 577 tests, checkpoint atomique, SIGTERM survival, Object Storage, auto-resume
- 4 scripts validés (E01 9.2/10, E02 9.0/10, E03 et E04 non encore audités)
- 5 agents d'audit (audit-sfx, audit-voix, audit-marc, audit-claire, audit-episode)
- Site public fonctionnel avec lecteur audio, FAQ, newsletter
- Admin dashboard V1 + V2 (V2 a des bugs bloquants identifiés par @reviewer)
- API `launch-fresh` + `kill-productions` pour déclencher la production depuis Claude Code

**Ce qui bloque (chemin critique Phase 1) :**
- 0 épisode audio produit à ce jour
- Bugs bloquants admin V2 (chemins audio erronés dans publish, arguments upload_file inversés)
- E03 et E04 non encore audités (scripts à auditer avant lancement production audio)
- Pas encore distribué sur Apple Podcasts ni Spotify

---

## Phase 2 — Transformer en SaaS (après S1 complète)

**Objectif** : rendre le pipeline de production accessible à d'autres créateurs de podcasts.

**Ce qui est clair :**
- Papy Babou devient le showcase/cas d'usage #1 de la plateforme
- Le pipeline existant est l'asset technologique central
- La Phase 2 démarre après la S1 complète (pas avant)

**Questions en attente de réponse du fondateur :**

[QUESTION FONDATEUR 1] Cible B2B ou B2C ?
- Option A : B2C — créateurs indépendants (YouTubers, podcasteurs, auteurs) qui veulent leur propre univers audio
- Option B : B2B — studios de production, maisons d'édition, éditeurs de contenu jeunesse
- Option C : les deux (freemium créateur + licences studio)

[QUESTION FONDATEUR 2] Niveau de customisation offert ?
- Option A : "Papy Babou as a Service" — même format, thème configurable (Bible, histoire, science...)
- Option B : Pipeline générique — l'utilisateur apporte ses propres personnages, voix, univers
- Option C : Clé en main thématique — bibliothèque de thèmes prêts à l'emploi

[QUESTION FONDATEUR 3] Modèle de pricing envisagé ?
- Par épisode produit (pay-per-use) ?
- Abonnement mensuel (quota d'épisodes) ?
- Licence annuelle (usage illimité) ?
- Freemium avec tier payant ?

[QUESTION FONDATEUR 4] La technologie est-elle revendable as-is ou faut-il une interface créateur complète (no-code/low-code) ?

[QUESTION FONDATEUR 5] Quel est le délai acceptable entre la fin de S1 et le lancement SaaS ?

---

**Handoff → @fullstack**
- Fichiers produits : `docs/product/product-vision.md`
- Décisions prises : Phase 1 = production 10 épisodes S1 (priorité absolue). Phase 2 = SaaS (questions ouvertes). 5 principes produit. Chemin critique Phase 1 identifié (bugs V2, 0 audio produit, E03/E04 non audités).
- Points d'attention : Les bugs bloquants admin V2 (chemins audio + arguments upload_file inversés) documentés dans `docs/reviews/cross-review-segment-namespacing.md` et `docs/reviews/cross-review-montage-workflow.md` doivent être corrigés AVANT la mise en production audio.
