# Roadmap — Les Histoires de Papy Babou

> Produit par @product-manager — 2026-03-25
> Horizon : Phase 1 = S1 complète. Phase 2 = SaaS (questions fondateur en attente).

---

## Légende

- [FAIT] Existe et fonctionne — ne pas retoucher sauf bug
- [BUG] Existe mais cassé — corriger en priorité
- [MANQUE] N'existe pas — à construire
- [CHEMIN CRITIQUE] Bloque les étapes suivantes

---

## Phase 1 — Produire et publier la Saison 1

### Sprint 0 — Correction des bugs bloquants [CHEMIN CRITIQUE]

**Durée estimée : 1-2 sessions de dev**
Objectif : débloquer la chaîne publish→site avant de mettre en production les 10 épisodes.

| Tâche | Statut | Source |
|-------|--------|--------|
| Corriger chemins audio dans publish V1 + V2 (output/episodes/audio/episodes/ → output/episodes/) | [BUG] BLOQUANT | cross-review-montage-workflow.md |
| Corriger arguments inversés upload_file (3 endroits web.py:4502/5028/5031) | [BUG] BLOQUANT | cross-review-segment-namespacing.md |
| Corriger chemins OUTPUT_DIR → SEGMENTS_DIR dans 8 endroits web.py routes V2 | [BUG] BLOQUANT | cross-review-segment-namespacing.md |
| Ajouter suppression fichier audio sur dépublication | [BUG] MAJEUR | cross-review-montage-workflow.md |
| Stabiliser IDs publish V1 (UUID instables) | [BUG] MAJEUR | cross-review-montage-workflow.md |

**Dépendance** : Sprint 1 et 2 ne peuvent pas livrer d'épisodes publiables sans ces corrections.

---

### Sprint 1 — Workflow script → audit → validation [2-3 sessions]

**Objectif** : valider que la chaîne scripteur → audit → correction → checkpoint fonctionne end-to-end pour E03 et E04.

| Tâche | Statut |
|-------|--------|
| Script E01 La Création — script validé 9.2/10, checkpoint waiting_script | [FAIT] |
| Script E02 Noé — script validé 9.0/10, checkpoint waiting_script | [FAIT] |
| Script E03 Abraham — `_script_valide.json` présent, audit @audit-episode requis | [MANQUE] Audit + vérification checkpoint |
| Script E04 Joseph — `_script_valide.json` présent, audit @audit-episode requis | [MANQUE] Audit + vérification checkpoint |
| Scripts E05 à E10 — à générer, auditer, valider | [MANQUE] |
| Workflow audit itératif (seuil 9/10 par auditeur) | [FAIT] — 5 agents d'audit opérationnels |
| Préférences producteur (24 règles) injectées dans scripteur | [FAIT] |
| Validation humaine du script (dashboard ou CLI) | [FAIT] |
| Historique script sauvegardé (DB + Object Storage + JSON) | [FAIT] |

**Jalon** : 10 scripts validés ≥ 9/10, checkpoints `waiting_script` prêts.

---

### Sprint 2 — Workflow audio → SFX → montage → validation [4-6 sessions, 30-45 min/épisode]

**Objectif** : produire l'audio complet des 10 épisodes avec le pipeline existant.

| Tâche | Statut |
|-------|--------|
| API `launch-fresh` (kill + purge + prod audio auto-chainée) | [FAIT] |
| TTS ElevenLabs par personnage (17 tons dynamiques) | [FAIT] |
| SFX ElevenLabs → Freesound → silence fallback | [FAIT] |
| Montage ffmpeg (LUFS, room tone, ducking, crossfade 200ms) | [FAIT] |
| SIGTERM survival + auto-resume après redeploy Replit | [FAIT] |
| Object Storage (9 préfixes, segments namespaced par production_run_id) | [FAIT] |
| Validation audio humaine dans dashboard (écoute + checklist) | [FAIT] |
| Cover art DALL-E 3 ou custom (assets/covers/S01EXX_cover.png) | [FAIT] |
| Segment coherence check (>50% segments présents avant montage) | [FAIT] |
| Métadonnées + transcript générés | [FAIT] |
| Production monitoring via /api/claude/query (SQL) + /api/job-status | [FAIT] |
| Cover art E01 — fichier custom en place | [FAIT] |
| Cover art E02 — fichier custom en place | [FAIT] |
| Cover art E03 à E10 — à préparer | [MANQUE] |

**Jalon** : 10 fichiers audio HQ validés, montage approuvé par le Producteur pour chaque épisode.

---

### Sprint 3 — Publication + historique complet [1-2 sessions]

**Objectif** : publier les 10 épisodes sur le site web + soumettre le flux RSS aux plateformes.

| Tâche | Statut |
|-------|--------|
| RSS 2.0 iTunes/Podcast Index généré | [FAIT] |
| Page publique épisodes avec lecteur audio | [FAIT] |
| Badge "À venir" pour épisodes avec cover mais sans audio | [FAIT] |
| Filtre cover_url sur api_public_episodes() | [FAIT] |
| Soumission Apple Podcasts Connect | [MANQUE] — manuel, 1h, post-production |
| Soumission Spotify for Podcasters | [MANQUE] — manuel, 1h, post-production |
| GA4 instrumenté sur le site public | [MANQUE] — requis avant distribution |
| Historique exhaustif (script + audit + audio + décisions) | [FAIT] — DB + Object Storage + JSON |
| Rapport de production par épisode accessible en dashboard | [FAIT] |

**Jalon** : 10 épisodes en ligne, RSS soumis Apple + Spotify, GA4 actif.

---

### Sprint 4 — Production sérielle des 10 épisodes [running]

**Objectif** : exécuter le pipeline pour chaque épisode dans l'ordre, en parallélisant autant que possible.

Ordre de priorité recommandé :
1. E01 (script prêt, cover prête) → lancer audio dès Sprint 0 résolu
2. E02 (script prêt, cover prête) → lancer audio immédiatement après E01
3. E03 (après audit script)
4. E04 (après audit script)
5. E05 à E10 (scripts à générer + auditer)

**Chemin critique** : un épisode bloqué en production audio (bug, timeout) ne doit pas bloquer les autres. Le pipeline supporte la production parallèle de scripts pendant la production audio d'un autre épisode.

---

## Phase 2 — Transformation SaaS [après S1 complète]

**Statut** : questions fondateur en attente (voir product-vision.md). Grandes étapes identifiées.

| Étape | Prérequis | Estimé |
|-------|-----------|--------|
| Réponses fondateur sur cible, pricing, customisation | — | Avant tout dev Phase 2 |
| Abstraction du pipeline (multi-tenant, isolation par projet) | S1 complète | [HYPOTHÈSE : 4-6 semaines] |
| Interface créateur (configuration univers, personnages, voix) | Abstraction | [HYPOTHÈSE : 4-6 semaines] |
| Système de billing (Stripe ou équivalent) | Interface créateur | [HYPOTHÈSE : 2 semaines] |
| Onboarding premier client externe | Pipeline multi-tenant | — |
| Papy Babou comme showcase public de la plateforme | Lancement SaaS | — |

---

## Chemin critique global

```
Sprint 0 (bugs bloquants)
    → Sprint 1 (scripts E03-E10 audités)
        → Sprint 2 (10 audios produits)
            → Sprint 0 résolu (publish fonctionne)
                → Sprint 3 (publication + GA4 + Apple/Spotify)
                    → 3 000 écoutes/mois (North Star)
                        → Phase 2 SaaS
```

Tout est séquentiel jusqu'à la publication. Sprint 1 (écriture scripts) peut tourner en parallèle avec Sprint 2 (production audio des premiers épisodes).

---

**Handoff → @fullstack**
- Fichiers produits : `docs/product/roadmap.md`
- Décisions prises : Sprint 0 non négociable avant tout (bugs publish bloquants). Sprint 4 peut démarrer dès E01 en parallèle de l'écriture E03-E10. Phase 2 suspendue aux réponses fondateur.
- Points d'attention : le pipeline audio dure 30-45 min/épisode sur Replit. Prévoir 5-7 jours pour les 10 épisodes (Replit redeploys, retries). Ne pas sous-estimer le Sprint 3 : la soumission Apple Podcasts est manuelle et peut prendre 48-72h de validation.
