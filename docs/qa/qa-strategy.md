# QA Strategy — Features P0/P1
> @qa — 2026-03-25
> Scope : F1 (audit E03/E04), F2 (audio E01), F3 (scripts E05-E10), F4 (GA4)
> Stack : pytest (577+ tests existants), Python/Flask, pas de Vitest/Playwright

---

## 1. Audit des criteres d'acceptation

### F1 — Audit et validation scripts E03/E04

| # | Given/When/Then | Testable auto ? | Type | Notes |
|---|----------------|-----------------|------|-------|
| 1 | Script existe → audit 4 auditeurs → corrections si < 9/10 | Non | Manuel (Claude Code) | Les auditeurs sont des agents LLM — pas de test deterministe possible. Tester uniquement la mecanique : fichier existe, score parsing, boucle de relance. |
| 2 | Audit >= 9/10 → sync valide + checkpoint cree | Oui | Integration | Verifier : `_valide.json` identique a `_script.json`, checkpoint contient `waiting_script`, `validation_humaine: true` |
| 3 | 3 iterations < 9/10 → alerte producteur | Non | Manuel | Decision humaine. Tester que le compteur d'iterations est incremente correctement (unit). |

**Edge cases**
- Script absent → `FileNotFoundError` : **Oui, unit**
- `_valide.json` desynchronise → regeneration : **Oui, integration** — comparer hash des deux fichiers
- Checkpoint `dry_run: true` → ecrasement : **Oui, unit** — verifier que le nouveau checkpoint a `dry_run: false`

### F2 — Production audio E01

| # | Given/When/Then | Testable auto ? | Type | Notes |
|---|----------------|-----------------|------|-------|
| 1 | Checkpoint ready → kill + launch-fresh → DB started | Oui | Integration | Mocker ElevenLabs + Claude API. Verifier `status='started'` et `production_run_id` en DB. |
| 2 | seg_003 verification en DB apres 90s | Oui | Integration | Mocker TTS, inserer seg_003 en DB, verifier `nb_caracteres` vs script local. |
| 3 | Auto-chain complete → fichier MP3 + duree 1680-1920s | Partiellement | Integration | Duree verifiable en DB (`fichiers_audio.duree_secondes`). Fichier MP3 = mocker ffmpeg. |
| 4 | Producteur ecoute preview → valide montage | Non | Manuel | Validation humaine. Tester que `validation_humaine` passe a `true` en DB apres appel API. |
| 5 | SIGTERM → checkpoint → auto-resume | Oui | Integration | Test existant (`TestSIGTERMHandler`). Verifier que `_auto_resume_interrupted` relance. |

**Edge cases**
- Timeout ffmpeg > 1800s : **Oui, unit** — mocker `subprocess.run` avec `TimeoutExpired`
- WAV corrompu < 1KB : **Oui, unit** — test existant dans `test_montage_resilience.py`
- Segments manquants apres redeploy → fallback `etape_idx=2` : **Oui, integration** — test existant

### F3 — Generation scripts E05-E10

| # | Given/When/Then | Testable auto ? | Type | Notes |
|---|----------------|-----------------|------|-------|
| 1 | Saison plan → generer E05 mi-saison → ~185 voix, ~41 SFX | Partiellement | Unit | Compter segments par type dans le JSON genere. Score LLM = non deterministe. |
| 2 | Script genere → audit → sync + checkpoint | Oui | Integration | Identique a F1#2. |
| 3 | E10 Esther → Lucas + morale + teasing S2 | Oui | Unit | Grep dans le JSON : `lucas` present, champ `morale` non vide, dernier segment contient teasing. |
| 4 | 6 checkpoints waiting_script crees | Oui | Integration | Glob `checkpoints/S01E0[5-9]_checkpoint.json` + `S01E10`. Verifier contenu. |

**Edge cases**
- 3 iterations < 9/10 → escalade : identique a F1#3, **Manuel**
- Gouter thematique repete : **Oui, unit** — extraire le gouter de chaque script, verifier unicite sur 10 episodes
- E10 sans Lucas : **Oui, unit** — grep `lucas` (insensible casse) dans segments E10

### F4 — GA4 sur site public

| # | Given/When/Then | Testable auto ? | Type | Notes |
|---|----------------|-----------------|------|-------|
| 1 | Page charge → `page_view` envoye | Partiellement | Unit (JS) | Verifier que `gtag.js` est dans le HTML (`<script.*gtag`). L'envoi reel = GA4 Realtime (manuel). |
| 2 | Clic Play → `play_episode` avec params | Oui | Unit (JS) | Mocker `gtag()`, simuler click, verifier appel avec `episode_id`, `episode_title`, `saison`. |
| 3 | Position >= 80% → `episode_complete` une seule fois | Oui | Unit (JS) | Mocker `gtag()`, simuler `timeupdate` a 80%+, verifier 1 seul appel. |
| 4 | Resume apres pause → pas de `play_episode` en double | Oui | Unit (JS) | Mocker `gtag()`, simuler play→pause→play, verifier 1 seul `play_episode`. |

**Edge cases**
- Adblocker bloque gtag.js : **Oui, unit** — verifier que `gtag` est appele dans un try/catch
- Duree audio = 0 : **Oui, unit** — verifier que `episode_complete` n'est pas emis
- Reformulation necessaire : F4#1 "visible en GA4 Realtime dans les 30s" est non testable automatiquement. Reformuler : "le tag `gtag('config', GA_ID)` est present dans le HTML rendu par Flask"

---

## 2. Scenarios E2E (pytest)

### E2E-1 : Workflow audit → checkpoint (F1/F3)
```
1. Creer un script factice S99E99_script.json (structure valide, segments, SFX)
2. Appeler la logique de sync _script → _valide (cp + hash compare)
3. Appeler sauvegarder_checkpoint() avec les bons champs
4. Verifier : _valide.json existe et == _script.json
5. Verifier : checkpoint contient waiting_script, validation_humaine=true, dry_run=false
6. Cleanup
```

### E2E-2 : launch-fresh → seg_003 → montage (F2)
```
1. Mocker ElevenLabs TTS (retourne bytes), Claude API, ffmpeg
2. POST /api/episode/S99E99/kill-productions (DB mock)
3. POST /api/episode/S99E99/launch-fresh avec script en body
4. Verifier : script ecrit sur filesystem + Object Storage
5. Verifier : checkpoint cree avec script_content_hash
6. Simuler completion audio → verifier seg_003 en DB
7. Simuler auto-chain SFX → montage → verifier etape_courante='montage_done'
```

### E2E-3 : Gouter thematique unique (F3)
```
1. Charger les 10 scripts (ou fixtures representatifs)
2. Pour chaque script : extraire le gouter de Mamie (grep "gouter|gateau|chocolat" dans segments Mamie)
3. Verifier : set(gouters).length == nombre_episodes (pas de doublons)
```

### E2E-4 : GA4 events (F4)
```
1. GET /  → verifier gtag.js dans le HTML
2. Verifier : script contient 'play_episode', 'episode_complete'
3. Verifier : try/catch autour des appels gtag
4. Verifier : anonymize_ip: true present
```

---

## 3. Matrice de couverture

| Feature | Unit | Integration | E2E (pytest) | Manuel |
|---------|------|-------------|--------------|--------|
| F1 Audit E03/E04 | Fichier existe, hash sync, checkpoint fields | Sync + checkpoint creation | E2E-1 | Score LLM, decision humaine |
| F2 Audio E01 | ffmpeg timeout, WAV corrupt, seg_003 match | kill+launch-fresh, auto-chain, SIGTERM | E2E-2 | Ecoute preview, validation montage |
| F3 Scripts E05-E10 | Segment count, gouter unique, E10 Lucas | 6 checkpoints crees | E2E-1, E2E-3 | Score LLM, corrections manuelles |
| F4 GA4 | gtag present, try/catch, anonymize_ip | Flask route rend le HTML | E2E-4 | GA4 Realtime verification |

---

## 4. Tests prioritaires (top 5)

| # | Test | Justification |
|---|------|---------------|
| 1 | **test_launch_fresh_writes_script_and_purges** | F2 bloquant. 4 echecs de production passes causes par script stale. Verifier que le script du body POST est ecrit + Object Storage purge. |
| 2 | **test_seg_003_verification** | F2 bloquant. Verifier que `nb_caracteres` en DB correspond au script local. Empeche de produire 45 min d'audio sur le mauvais script. |
| 3 | **test_checkpoint_fields_after_audit** | F1/F3 bloquant. Verifier `waiting_script`, `validation_humaine: true`, `dry_run: false`, `type_episode` correct. Un champ manquant = production bloquee. |
| 4 | **test_valide_sync_after_correction** | F1/F3 bloquant. Hash de `_script.json` == hash de `_valide.json`. Desync = production sur ancien script (1 redo complet en production). |
| 5 | **test_ga4_gtag_present_and_anonymized** | F4 critique pour North Star. `gtag.js` dans le HTML, `anonymize_ip: true`, `play_episode` et `episode_complete` references dans le JS. |

---

## 5. Outils et mocks

- **Framework** : pytest (existant, 577+ tests — ne pas migrer)
- **Mocks necessaires** :
  - `ElevenLabs` : `unittest.mock.patch` sur `producteur_audio` et `sfx_provider` (retourne bytes factices)
  - `Claude API` : `monkeypatch` sur `config.appel_claude_avec_retry` (retourne JSON fixture)
  - `Object Storage` : `monkeypatch` sur `persistent_storage.upload_file` / `restore_*` (retourne True/None)
  - `ffmpeg` : `monkeypatch` sur `subprocess.run` (retourne `CompletedProcess` factice)
  - `DB` : Tests existants utilisent `monkeypatch` sur les repos (`ProductionRepo`, `ScriptRepo`, etc.)
  - `gtag()` : Test du HTML rendu par Flask (`client.get("/")` puis parse le HTML)
- **Fixtures existantes** : `conftest.py` contient `script_exemple`, `script_avec_sfx_overlay`, `review_exemple` — reutiliser
- **Pas de tests E2E navigateur** : GA4 events sont testes par inspection du HTML (pas de Playwright — le frontend est du HTML/JS statique servi par Flask)

---

## Auto-evaluation

- [x] Chaque critere d'acceptation audite (testable auto oui/non + type)
- [x] Criteres vagues reformules (F4#1 "visible en 30s" → "gtag config present dans le HTML")
- [x] 4 scenarios E2E couvrent les parcours critiques
- [x] Matrice feature x type de test complete
- [x] 5 tests prioritaires justifies par l'impact production
- [x] Outils = pytest existant, pas de migration

---

**Handoff → @infrastructure**
- Fichiers produits : `docs/qa/qa-strategy.md`
- Decisions prises :
  - Pas de Playwright/Vitest — tout en pytest (coherent avec les 577+ tests existants)
  - Les scores LLM des auditeurs sont non testables automatiquement — seules les mecaniques (sync, checkpoint, compteur) sont testees
  - GA4 teste par inspection HTML (pas de navigateur headless) — validation reelle en GA4 Realtime = manuelle
  - F4#1 reformule : "visible en 30s" n'est pas testable, remplace par "gtag config present dans le HTML"
- Points d'attention :
  - Les 5 tests prioritaires couvrent les 4 bugs de production passes (script stale, seg_003, checkpoint incomplet, valide desync)
  - Aucun test existant ne couvre `launch-fresh` endpoint ni la verification seg_003 — ce sont les trous les plus critiques
  - Les mocks ElevenLabs et ffmpeg sont deja utilises dans `test_monteur.py` et `test_producteur_audio.py` — reutiliser les patterns
