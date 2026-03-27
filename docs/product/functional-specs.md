# Specs fonctionnelles — Features P0/P1
> @product-manager — 2026-03-25
> North Star : 3 000 écoutes complètes/mois
> Périmètre : F1 (E1-S4), F2 (E1-S5), F3 (E1-S6), F4 (E2-S1)
> P0 (E1-S1/S2/S3) : déjà corrigés — non spécifiés ici

---

## F1 — Audit et validation scripts E03/E04

**User story** : En tant que Producteur, je veux passer E03 (Abraham) et E04 (Joseph) par `@audit-episode` et atteindre ≥ 9/10 afin de créer leurs checkpoints de production audio.

**Règles métier**
- Workflow entièrement dans Claude Code (pas le web dashboard)
- Seuil bloquant : 4/4 auditeurs ≥ 9.0/10 — en dessous, itérer
- Après audit : créer `checkpoints/S01E0X_checkpoint.json` + entrée dans `historique_episodes.json`
- Synchroniser `_script.json` → `_valide.json` après chaque correction
- `validation_humaine: true` et `dry_run: false` obligatoires dans le checkpoint

**Given/When/Then**

| # | Given | When | Then |
|---|-------|------|------|
| 1 | `S01E03_script.json` existe dans `scripts/episodes/` | `@audit-episode scripts/episodes/S01E03_script.json` est lancé | Les 4 auditeurs retournent chacun un score — si < 9/10 sur l'un d'eux, les corrections P0+P1 sont appliquées automatiquement et l'audit relancé |
| 2 | Audit E03 retourne ≥ 9/10 sur les 4 auditeurs | Le producteur valide les corrections | `S01E03_script_valide.json` est synchronisé, `S01E03_checkpoint.json` est créé avec `etape: "waiting_script"`, `validation_humaine: true` |
| 3 | Après 3 itérations le score reste < 9/10 sur un axe | Le producteur est alerté | Les axes bloquants sont listés avec leur score, le producteur décide si correction manuelle ou acceptation avec réserves |

**Edge cases**
- Si `_script.json` est absent : arrêter, afficher le chemin attendu
- Si `_valide.json` désynchronisé après correction : regénérer avant de créer le checkpoint
- Si checkpoint existant avec `dry_run: true` : écraser sans confirmation (était un test)

**Dépendances** : E1-S1/S2/S3 déjà corrigés (checkpoints seront utilisés en E1-S5)

**KPI de succès** : 4/4 auditeurs ≥ 9.0/10 pour E03 ET E04 (mesurable dans le rapport d'audit)

---

## F2 — Production audio E01 (La Création)

**User story** : En tant que Producteur, je veux lancer la production audio de S01E01 via `launch-fresh` et obtenir un fichier audio validé entre 28 et 32 minutes.

**Règles métier**
- Toujours envoyer le script dans le body POST (le filesystem Replit est non fiable)
- `kill-productions` OBLIGATOIRE avant `launch-fresh` (évite les conflits auto-resume)
- Vérification `seg_003` en DB sous 90s : si `nb_caracteres` ne correspond pas → kill + relancer
- Auto-chain automatique : audio → SFX → montage (3 jobs de ~10-15 min chacun)
- Durée cible : 1680-1920 secondes (28-32 min, type `ouverture`)
- Validation humaine obligatoire : le Producteur écoute le montage preview avant de valider

**Given/When/Then**

| # | Given | When | Then |
|---|-------|------|------|
| 1 | Checkpoint E01 : `waiting_script`, `validation_humaine: true`, `dry_run: false` | `kill-productions` puis `launch-fresh` avec script en body | DB : `status='started'`, job audio lancé, `production_run_id` créé |
| 2 | Job audio démarré | 90s après le lancement, SQL sur `fichiers_audio` pour `seg_003` | `nb_caracteres` correspond au script local → continuer. Sinon → kill + relancer |
| 3 | Auto-chain audio → SFX → montage terminé | DB : `etape_courante='montage_done'` | Fichier `_192k.mp3` accessible via URL publique, durée entre 1680 et 1920s |
| 4 | Montage disponible | Producteur ouvre le dashboard, écoute le preview | `validation_humaine: true` sur montage → déblocage de la publication |
| 5 | Replit redéploie pendant le montage | SIGTERM reçu, checkpoint sauvé | Auto-resume thread relance depuis le dernier checkpoint, job visible dans dashboard |

**Edge cases**
- Timeout ffmpeg (> 1800s) : montage échoue → rapport d'erreur dans `etapes.montage.erreur`, retry depuis les segments existants
- WAV intermédiaire corrompu (< 1 KB) : suppression + régénération complète depuis les segments
- Segments Object Storage manquants après redeploy : `restore_segments()` → si échec → `etape_idx = 2` (régénération TTS)

**Contrainte perf** : durée totale chaîne ≤ 45 min (Replit Gunicorn timeout 3900s)

**KPI de succès** : `fichiers_audio.duree_secondes` entre 1680 et 1920, `seg_003` vérifié, montage humainement validé

---

## F3 — Génération scripts E05 à E10

**User story** : En tant que Producteur, je veux générer les 6 scripts restants (Moïse, David, Salomon, Daniel, Jonas, Esther) avec les 24 règles de qualité, chacun audité ≥ 9/10, afin de compléter le catalogue de la saison 1.

**Règles métier**
- Lire `data/saisons/saison_01.json` pour le résumé, prétexte, previously-on, teasing de chaque épisode avant génération
- Lire les scripts précédents comme référence (E01 9.2/10, E02 9.0/10)
- Cibles par type : E05 mi-saison (~185 voix + ~41 SFX, 30 min), E06-E09 standard (~165 voix + ~40 SFX, 25 min), E10 final (~200 voix + ~45 SFX, 35 min + événement Lucas)
- Goûter thématique différent à chaque épisode (E01=sablés étoiles, E02=chocolat chaud cannelle — ne pas répéter)
- Previously-on cohérent avec l'épisode N-1 à chaque script
- Après chaque script approuvé : sync `_valide.json` + créer checkpoint `waiting_script`

**Given/When/Then**

| # | Given | When | Then |
|---|-------|------|------|
| 1 | `saison_01.json` contient les 10 épisodes imposés | Génération de `S01E05_script.json` (Moïse, type `mi-saison`) | Script généré avec ~185 voix, ~41 SFX, type `mi-saison`, previously-on depuis E04 |
| 2 | Script E05 généré | `@audit-episode scripts/episodes/S01E05_script.json` lancé | Si ≥ 9/10 → sync `_valide.json` + checkpoint. Sinon → corrections P0+P1 + relancer |
| 3 | Script E10 (Esther) généré | Vérification : événement Lucas présent, morale "courage pour les autres", teasing S2 | Ces 3 éléments sont dans le script. Type = `final`. |
| 4 | 6 scripts passent l'audit ≥ 9/10 | Checkpoints créés pour E05-E10 | 6 checkpoints `waiting_script` avec `validation_humaine: true` et `dry_run: false` |

**Edge cases**
- Si un script ne dépasse pas 9/10 après 3 itérations : escalade au Producteur avec les axes bloquants
- Si le goûter thématique se répète entre épisodes : l'auditeur @audit-marc le signale en correction P1 — corriger avant validation
- E10 sans événement Lucas → bloquant (condition définie dans le plan de saison)

**Dépendances** : E1-S4 (workflow audit validé sur E03/E04 avant de générer E05-E10)

**KPI de succès** : 6/6 scripts avec score ≥ 9/10 et checkpoints `waiting_script` (mesurable dans dashboard)

---

## F4 — GA4 sur site public

**User story** : En tant que Producteur, je veux que Google Analytics 4 mesure les écoutes dès le premier épisode en ligne, sans cookies ni consentement requis.

**Règles métier**
- `gtag.js` dans `<head>` de `public.html` (avant `</head>`) — chargement synchrone
- Mesure anonymisée : `anonymize_ip: true`, pas de cookies de collecte — RGPD compliant sans bandeau consentement
- `play_episode` : déclenché à la première lecture (pas sur resume après pause)
- `episode_complete` : déclenché quand position ≥ 80% de la durée totale (seuil North Star)
- `page_view` : déclenché automatiquement par gtag.js

**Given/When/Then**

| # | Given | When | Then |
|---|-------|------|------|
| 1 | `public.html` servi par Flask | La page se charge | GA4 envoie un `page_view` — visible en GA4 Realtime dans les 30s |
| 2 | Lecteur audio HTML5 présent | Utilisateur clique Play sur un épisode | GA4 envoie `play_episode` avec paramètres `episode_id`, `episode_title`, `saison` |
| 3 | Épisode en lecture | Position audio atteint 80% de `duration` | GA4 envoie `episode_complete` avec les mêmes paramètres — **une seule fois par session** |
| 4 | Épisode mis en pause puis repris | Play déclenché à nouveau | `play_episode` n'est PAS renvoyé (flag `_hasStarted` par épisode) |

**Implémentation (extrait logique)**
```
// Dans l'event listener 'timeupdate' du lecteur audio
if (!_completeFired[episodeId] && audio.currentTime / audio.duration >= 0.80) {
  gtag('event', 'episode_complete', { episode_id, episode_title, saison });
  _completeFired[episodeId] = true;
}
```

**Wireframe** : aucun — GA4 est invisible pour l'utilisateur final.

**Edge cases**
- Si gtag.js bloqué par un adblocker : aucun crash JS (appels GA4 dans try/catch silencieux)
- Si la durée audio est 0 (épisode sans audio chargé) : ne pas déclencher `episode_complete`
- En mode dev local (localhost) : events envoyés en debug — utiliser `debug_mode: true` ou filtrer dans GA4

**Events tracking résumé**

| Event | Paramètres | Déclencheur |
|-------|-----------|-------------|
| `page_view` | `page_location`, `page_title` | Chargement page (auto gtag) |
| `play_episode` | `episode_id`, `episode_title`, `saison` | 1er clic Play par épisode |
| `episode_complete` | `episode_id`, `episode_title`, `saison` | Position ≥ 80% durée, 1 fois |

**Dépendances** : aucune — peut être implémenté avant E01 en production.
**Contrainte perf** : gtag.js chargé en `async` — n'impacte pas le Time to Interactive.

**KPI de succès** : event `episode_complete` reçu dans GA4 Realtime dans les 24h post-lancement (prouve que la chaîne mesure le North Star)

---

## Auto-évaluation

- [x] Chaque user story a des critères d'acceptance testables et des edge cases
- [x] Pas de priorisation intuitive — basée sur RICE du backlog.md (F2 < F1 sur RICE mais sur chemin critique)
- [x] Scope MVP défendable — F3 est bloqué par F1 (workflow audit validé), F2 bloqué par P0 déjà corrigés
- [x] KPI de succès mesurables définis pour chaque feature
- [x] RGPD : GA4 anonymisé, pas de cookie banner requis

---

**Handoff → @qa**
- Fichiers produits : `docs/product/functional-specs.md`
- Décisions prises :
  - F1 : seuil 9/10 bloquant sur les 4 auditeurs — pas d'exception sur aucun axe
  - F2 : vérification seg_003 en DB est obligatoire et non contournable (4 échecs de production passés)
  - F3 : ordre de génération E05→E10 séquentiel (previously-on N-1 requis)
  - F4 : GA4 anonymisé sans cookie banner (RGPD) — `anonymize_ip: true`
- Points d'attention pour les tests :
  - F2 : mocker `launch-fresh` en test (éviter les appels ElevenLabs réels). Tester le fallback `etape_idx = 2` quand les segments sont manquants après redeploy
  - F4 : tester que `play_episode` ne se déclenche pas deux fois (flag `_hasStarted`), que `episode_complete` ne se déclenche qu'une fois à ≥ 80%
  - F3 : vérifier que le goûter thématique est distinct entre épisodes (test de non-répétition sur les 10 checkpoints)
  - GA4 : tester en mode `debug_mode: true` sur staging avant de mettre `gtag.js` en production
