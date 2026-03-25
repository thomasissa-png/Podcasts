# Backlog produit — Les Histoires de Papy Babou

> Produit par @product-manager — 2026-03-25
> Personas : Producteur (fondateur), Sophie (parent pratiquante), Camille (parent non-pratiquant), Client SaaS (Phase 2)
> KPI North Star : 3 000 écoutes complètes/mois (≥ 80% de durée)
> Méthode de priorisation : MoSCoW (Must/Should/Could/Won't) + score RICE simplifié

---

## Légende

- [FAIT] Feature existante et fonctionnelle — incluse pour visibilité, score RICE non requis
- [BUG] Bug identifié par @reviewer — Must Have impératif
- [À FAIRE] À développer ou compléter
- RICE = (Reach × Impact × Confidence) / Effort — Reach=0-3, Impact=0-3, Confidence=%, Effort=1-5

---

## EPIC 1 — Workflow de production bout-en-bout (Phase 1 critique)

### E1-S1 — Corriger les chemins audio à la publication

**En tant que** Producteur, **je veux** que le bouton "Publier" copie le fichier audio au bon chemin (`output/episodes/`) afin que l'épisode soit accessible sur le site public.

**Statut** : [BUG] BLOQUANT — Must Have
**Source** : `docs/reviews/cross-review-montage-workflow.md` (2 BLOQUANTS publish V1+V2)
**Critères d'acceptation** :
- Le fichier audio HQ est accessible via `/audio/episodes/{episode_id}_*.mp3` après publication
- Le test d'intégration E2E (publish → homepage) passe sans 404
- Les routes V1 et V2 de publication utilisent toutes deux `output/episodes/` (pas `output/episodes/audio/episodes/`)

**Edge cases** : si le fichier source est manquant (redeploy), la route doit retourner 400 avec message explicite avant de tenter la copie.

**RICE** : Reach=3 (bloque tous les épisodes), Impact=3 (bloquant total), Confidence=95%, Effort=1 → Score=**855**

---

### E1-S2 — Corriger les arguments inversés upload_file dans les routes V2 admin

**En tant que** Producteur, **je veux** que les segments audio soient uploadés dans le bon ordre (clé Object Storage en premier, chemin local en second) afin que la reprise après redeploy fonctionne.

**Statut** : [BUG] BLOQUANT — Must Have
**Source** : `docs/reviews/cross-review-segment-namespacing.md` (3 endroits : web.py:4502/5028/5031)
**Critères d'acceptation** :
- Les 3 appels `ps.upload_file()` dans les routes V2 ont les arguments dans l'ordre `(storage_key, local_path)`
- Un segment uploadé est téléchargeable depuis Object Storage avec la clé `segments/{episode_id}/{production_run_id}/seg_XXX.mp3`
- Tests unitaires sur les 3 routes V2 vérifient l'ordre des arguments

**Edge cases** : si le fichier local est absent au moment de l'upload (redeploy entre TTS et upload), logger un warning et continuer sans crash.

**RICE** : Reach=3, Impact=3, Confidence=95%, Effort=1 → Score=**855**

---

### E1-S3 — Corriger les chemins SEGMENTS_DIR dans les 8 routes V2 admin

**En tant que** Producteur, **je veux** que les routes V2 (generate-audio, montage/run, regenerate-segment) utilisent `config.SEGMENTS_DIR` afin que les segments soient écrits au bon endroit et retrouvés par le pipeline.

**Statut** : [BUG] BLOQUANT — Must Have
**Source** : `docs/reviews/cross-review-segment-namespacing.md`
**Critères d'acceptation** :
- Tous les chemins de segments dans les routes V2 utilisent `config.SEGMENTS_DIR`, jamais `config.OUTPUT_DIR / "segments"`
- Un grep sur `web.py` ne retourne aucun `OUTPUT_DIR.*segments` dans les routes V2

**RICE** : Reach=3, Impact=3, Confidence=95%, Effort=1 → Score=**855**

---

### E1-S4 — Auditer et valider les scripts E03 et E04

**En tant que** Producteur, **je veux** passer E03 (Abraham) et E04 (Joseph) par `@audit-episode` et corriger les P0+P1 afin que ces scripts atteignent 9/10 avant lancement audio.

**Statut** : [À FAIRE] — Must Have (chemin critique vers la production audio)
**Critères d'acceptation** :
- `@audit-episode scripts/episodes/S01E03_script.json` retourne un verdict ≥ 9.0/10 sur les 4 auditeurs
- Idem pour S01E04
- Les fichiers `_valide.json` sont synchronisés après chaque correction
- Les checkpoints E03 et E04 existent avec `validation_humaine: true` et `dry_run: false`

**Edge cases** : si le score ne dépasse pas 9/10 après 3 itérations, signaler au Producteur les axes bloquants pour décision humaine.

**RICE** : Reach=3 (bloque 8 épisodes), Impact=3, Confidence=80%, Effort=2 → Score=**360**

---

### E1-S5 — Produire l'audio de E01 (La Création)

**En tant que** Producteur, **je veux** lancer `launch-fresh` pour S01E01 et obtenir un fichier audio validé afin d'avoir le premier épisode prêt pour la publication.

**Statut** : [À FAIRE] — Must Have
**Pré-requis** : E1-S1, E1-S2, E1-S3 corrigés. Checkpoint E01 : `waiting_script`, `validation_humaine: true`, `dry_run: false`
**Critères d'acceptation** :
- La chaîne TTS → SFX → montage se termine sans erreur (statut DB `montage_done`)
- Le fichier audio HQ (`_192k.mp3`) est accessible via l'URL publique
- `seg_003` vérifié en DB correspond au contenu du script local
- Durée audio entre 28 et 32 minutes (type `ouverture`, cible 30 min)
- Le Producteur a écouté l'intégralité du montage preview et validé

**Edge cases** : si Replit redéploie pendant le montage (30-45 min), l'auto-resume reprend depuis le dernier checkpoint. Si montage corrompu (WAV < 1 KB), régénérer depuis les segments.

**RICE** : Reach=1 (1 épisode), Impact=3 (déblocage de toute la chaîne), Confidence=75%, Effort=3 → Score=**75**

---

### E1-S6 — Générer les scripts E05 à E10

**En tant que** Producteur, **je veux** générer les scripts des épisodes 5 à 10 de la saison 1 (Moïse, David, Salomon, Daniel, Jonas, Esther) en respectant les 24 règles de qualité afin de compléter le catalogue de la saison.

**Statut** : [À FAIRE] — Must Have (volume minimum pour lancement)
**Critères d'acceptation** :
- 6 scripts générés et passés à l'audit @audit-episode (score ≥ 9/10 chacun)
- E05 Moïse : type `mi-saison`, 30 min, ~185 segments voix + ~41 SFX
- E10 Esther : type `final`, 35 min, ~200 segments voix + ~45 SFX, include l'événement Lucas
- Chaque script a un goûter thématique distinct des épisodes précédents
- Previously-on cohérent avec l'épisode N-1 pour chaque script

**RICE** : Reach=3 (saison complète), Impact=3, Confidence=80%, Effort=4 → Score=**180**

---

## EPIC 2 — Site public et distribution (Phase 1 — lancement)

### E2-S1 — Instrumenter GA4 sur le site public

**En tant que** Producteur, **je veux** que Google Analytics 4 soit actif sur `public.html` avant la soumission sur Apple Podcasts afin de mesurer l'acquisition dès le premier auditeur.

**Statut** : [À FAIRE] — Must Have (pré-requis lancement)
**Critères d'acceptation** :
- Balise GA4 (gtag.js) présente dans `<head>` de `public.html`
- Event `play_episode` envoyé quand un épisode démarre
- Event `episode_complete` envoyé quand l'épisode atteint ≥ 80% de sa durée (proxy écoute complète)
- Aucune collecte de données personnelles sans consentement (pas de cookie banner requis si mesure anonymisée)

**Edge cases** : si l'épisode est mis en pause et repris, ne pas déclencher `play_episode` à nouveau.

**RICE** : Reach=3 (affecte toutes les futures acquisitions), Impact=2, Confidence=90%, Effort=1 → Score=**540**

---

### E2-S2 — Soumettre le flux RSS à Apple Podcasts Connect

**En tant que** Sophie, **je veux** trouver "Les Histoires de Papy Babou" sur Apple Podcasts afin de m'abonner facilement depuis mon iPhone.

**Statut** : [À FAIRE] — Must Have (canal de distribution principal)
**Pré-requis** : 10 épisodes audio validés + RSS généré + couvertures présentes
**Critères d'acceptation** :
- Soumission effectuée via podcasters.apple.com (processus manuel ~1h)
- Validation Apple reçue (délai 24-72h)
- Le flux RSS inclut `<itunes:type>serial</itunes:type>` (déjà en place)
- Chaque épisode a une cover art (PNG 3000x3000 requis par Apple)
- Catégorie : "Kids & Family" + "Religion & Spirituality > Christianity"

**Edge cases** : si Apple rejette pour mauvaise résolution de cover art, régénérer avec DALL-E ou crop custom.

**RICE** : Reach=3, Impact=3 (canal #1 des podcasts familiaux FR), Confidence=90%, Effort=1 → Score=**810**

---

### E2-S3 — Soumettre le flux RSS à Spotify for Podcasters

**En tant que** Camille, **je veux** trouver "Les Histoires de Papy Babou" sur Spotify afin de l'écouter sans avoir à installer une nouvelle application.

**Statut** : [À FAIRE] — Must Have
**Pré-requis** : RSS Apple validé (même flux)
**Critères d'acceptation** :
- Soumission via podcasters.spotify.com
- Disponible en écoute sur Spotify dans les 48h
- La courbe de rétention par épisode est accessible dans Spotify for Podcasters (KPI Noah : drop-off < 3 min)

**RICE** : Reach=2 (Spotify = audience plus large mais moins intentionnelle sur podcasts enfants), Impact=2, Confidence=90%, Effort=1 → Score=**360**

---

### E2-S4 — Préparer les covers art E03 à E10

**En tant que** Producteur, **je veux** que chaque épisode ait une cover art personnalisée avant la soumission aux plateformes afin que la page publique affiche les épisodes avec badge "À venir".

**Statut** : [À FAIRE] — Should Have
**Critères d'acceptation** :
- 8 fichiers `S01E03_cover.png` à `S01E10_cover.png` présents dans `assets/covers/`
- Format PNG, résolution suffisante pour Apple Podcasts (3000x3000 recommandé)
- Cohérence visuelle avec E01 et E02 (style illustration, palette couleurs)
- Les épisodes apparaissent sur la homepage avec badge "À venir" dès que la cover est présente

**RICE** : Reach=3 (visibilité site public), Impact=2, Confidence=80%, Effort=2 → Score=**240**

---

## EPIC 3 — Expérience auditeur (Sophie, Lina, Noah, Camille)

### E3-S1 — Optimiser le lecteur audio pour mobile

**En tant que** Sophie, **je veux** écouter un épisode directement sur mon iPhone depuis le site sans avoir à l'ouvrir dans Apple Podcasts afin de partager facilement avec mes enfants.

**Statut** : [FAIT] — lecteur audio embarqué présent. **Should Have** : amélioration vitesse de chargement
**Critères d'acceptation existants** :
- Lecteur HTML5 fonctionnel sur mobile (touch targets ≥ 44px, ajusté en Session 7)
- La progression est sauvegardée localement si l'utilisateur quitte la page

**Amélioration à faire** : mesurer le temps de chargement initial sur mobile 3G — si > 3s, implémenter le preload progressif.

**RICE** : Reach=2, Impact=2, Confidence=60%, Effort=2 → Score=**120**

---

### E3-S2 — Page épisode avec transcript accessible

**En tant que** Sophie, **je veux** accéder à un résumé de l'épisode et aux thèmes abordés avant de le proposer à mes enfants afin de préparer des questions pour la discussion en famille.

**Statut** : [À FAIRE] — Should Have
**Critères d'acceptation** :
- La modal épisode (déjà présente) affiche : titre, durée, résumé, morale (le "trésor de cette mission")
- Le transcript complet est accessible depuis un lien "Lire le texte" (fichier JSON métadonnées existe déjà)
- La morale n'est jamais formulée comme une leçon frontale (respect du ton de marque)

**RICE** : Reach=2 (Sophie principalement), Impact=2 (réduit l'objection d'adoption), Confidence=70%, Effort=2 → Score=**140**

---

## EPIC 4 — Historique et traçabilité (Producteur)

### E4-S1 — Dashboard de suivi de production par épisode

**En tant que** Producteur, **je veux** voir en un coup d'œil l'état de chaque épisode (script/audio/montage/publié) dans le dashboard admin afin de savoir exactement où j'en suis dans la production de la saison.

**Statut** : [FAIT] — dashboard V1 fonctionnel avec tableau épisodes, colonnes validation script/montage, score review.
**Amélioration souhaitée** : ajouter colonne "Audit score" (note @audit-episode) et "Couverture" (custom/DALL-E/absente).

**RICE amélioration** : Reach=1 (Producteur solo), Impact=2, Confidence=90%, Effort=1 → Score=**180**

---

### E4-S2 — Rapport de production complet par épisode (scripts, audits, décisions)

**En tant que** Producteur, **je veux** accéder au rapport complet d'un épisode (scores d'audit, corrections appliquées, décisions humaines, coûts API) afin de comprendre l'historique de chaque épisode et de mémoriser les patterns qui fonctionnent.

**Statut** : [FAIT] — rapport JSON accessible via `/api/episode/{id}`. **Could Have** : interface lisible dans le dashboard (actuellement JSON brut).

**RICE** : Reach=1, Impact=1, Confidence=80%, Effort=2 → Score=**40**

---

## EPIC 5 — Phase 2 SaaS (après S1 complète)

> Les stories ci-dessous sont en attente des réponses fondateur (voir product-vision.md).
> Elles sont listées pour cadrage — aucune estimation d'effort avant validation du modèle.

### E5-S1 — [QUESTION FONDATEUR] Abstraction multi-tenant du pipeline

**En tant que** Client SaaS, **je veux** créer mon propre podcast thématique (science, histoire, contes) sans coder, en partant du même pipeline que Papy Babou, afin de produire un contenu audio professionnel en quelques heures.

**Statut** : [À FAIRE — Phase 2] — priorité conditionnelle aux réponses fondateur
**Hypothèses à valider** :
- [HYPOTHÈSE] Le pipeline actuel est suffisamment paramétrable pour supporter un thème différent (Bible → Science, etc.) sans réécriture majeure
- [HYPOTHÈSE] La personnalisation des voix ElevenLabs par "univers" est faisable via l'API existante

**Critères d'acceptation (draft)** :
- Un créateur peut créer un "projet" avec : nom, thème, personnages, voix
- Les 24 règles de qualité sont adaptables par projet (ou surchargées)
- La production d'un épisode reste automatisée de A à Z

**RICE** : non chiffré — dépend du modèle économique retenu

---

### E5-S2 — [QUESTION FONDATEUR] Interface créateur no-code

**En tant que** Client SaaS non-technique, **je veux** configurer mon univers podcast via une interface web sans toucher au code, afin d'utiliser le pipeline sans compétences Python.

**Statut** : [À FAIRE — Phase 2]
**Critères d'acceptation (draft)** :
- Formulaire de création d'univers : nom du podcast, personnages (nom, ton, voix), thème éditorial
- Bibliothèque de "prétextes narratifs" (équivalent de la maison de Papy Babou pour d'autres univers)
- Preview du premier épisode généré avant engagement

---

### E5-S3 — [QUESTION FONDATEUR] Système de billing (Stripe)

**En tant que** Client SaaS, **je veux** payer mensuellement selon mon usage (nombre d'épisodes produits) afin de maîtriser mes coûts.

**Statut** : [À FAIRE — Phase 2]
**Note** : le modèle pay-per-use est cohérent avec les coûts variables du pipeline (API Claude ~$2-5/script, ElevenLabs ~$5-10/épisode). Un abonnement fixe nécessiterait un quota.

---

## Priorisation globale Phase 1

| Priorité | Story | Type | Bloque quoi |
|----------|-------|------|-------------|
| P0 | E1-S1 : Chemins audio publication | BUG BLOQUANT | Toute publication |
| P0 | E1-S2 : Arguments upload_file inversés | BUG BLOQUANT | Toute reprise post-redeploy |
| P0 | E1-S3 : SEGMENTS_DIR routes V2 | BUG BLOQUANT | Routes admin V2 |
| P1 | E2-S1 : GA4 | Pré-requis lancement | Mesure acquisition |
| P1 | E1-S4 : Audit E03+E04 | Script | Production E03/E04 |
| P1 | E1-S5 : Production audio E01 | Audio | Premier épisode en ligne |
| P1 | E1-S6 : Scripts E05-E10 | Script | Saison complète |
| P2 | E2-S2 : Apple Podcasts | Distribution | KPI North Star |
| P2 | E2-S3 : Spotify | Distribution | KPI North Star |
| P2 | E2-S4 : Covers E03-E10 | Asset | Homepage visible |
| P3 | E3-S2 : Page épisode + transcript | UX | Sophie adoption |
| P4 | E5-S1 à E5-S3 | Phase 2 | Attente réponses fondateur |

---

## Connexion au KPI North Star

Chaque story Phase 1 est rattachée à l'objectif 3 000 écoutes complètes/mois :

| Story | Contribution au North Star |
|-------|---------------------------|
| E1-S1/S2/S3 (bugs) | Déblocage total — 0 écoute possible sans ces corrections |
| E1-S4 à E1-S6 (scripts) | Volume minimum : 10 épisodes requis pour abonnement Apple/Spotify |
| E2-S1 (GA4) | Mesure du North Star — sans GA4, les 3 000 écoutes ne sont pas comptables |
| E2-S2 (Apple) | Canal #1 de découverte pour Sophie et Noah (40%+30% du poids decisions) |
| E2-S3 (Spotify) | Canal d'accès pour Camille (non-pratiquant, pas d'Apple Podcasts) |
| E3-S2 (transcript) | Rétention Sophie : réduit l'objection "je ne sais pas ce que mon enfant va entendre" |

---

**Handoff → @fullstack**
- Fichiers produits : `docs/product/backlog.md`, `docs/product/product-vision.md` (mis à jour), `docs/product/roadmap.md` (mis à jour)
- Décisions prises : P0 absolus = les 3 bugs BLOQUANTS (chemins audio publish, arguments upload_file inversés, SEGMENTS_DIR V2). Production audio E01 ne peut démarrer qu'après correction P0. Phase 2 SaaS suspendue aux réponses fondateur sur 5 questions.
- Points d'attention : (1) Les bugs P0 sont dans `web.py` routes V2 — ne pas toucher `main.py` qui est à 9/10 selon @reviewer. (2) E03/E04 ont des `_valide.json` mais aucun checkpoint — créer les checkpoints après audit. (3) GA4 doit être actif AVANT la soumission Apple Podcasts, pas après.
