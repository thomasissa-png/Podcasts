# QA Strategy — Features P0/P1 (enrichi post-audit backend)
> @qa — 2026-03-25 (mis a jour)
> Scope : F1 (audit E03/E04), F2 (audio E01), F3 (scripts E05-E10), F4 (GA4)
> Stack : pytest (577+ tests existants), Python/Flask, pas de Vitest/Playwright
> Audit croise avec : docs/infra/backend-audit.md

---

## 1. Audit des criteres d'acceptation

### F1 — Audit et validation scripts E03/E04

| # | Given/When/Then | Testable auto ? | Type | Test existant ? | Gap |
|---|----------------|-----------------|------|----------------|-----|
| 1 | Script existe → audit 4 auditeurs → corrections si < 9/10 | Non | Manuel (Claude Code) | N/A (workflow agent) | Aucun — workflow CLI |
| 2 | Audit >= 9/10 → sync valide + checkpoint cree | Oui | Integration | `test_web_production_flow.py::test_valide_json_created_from_script_json` (sync), `test_corrections.py::test_checkpoint_contient_type` (checkpoint fields) | PARTIEL — le test de sync existe mais ne verifie pas `waiting_script` + `validation_humaine: true` ensemble |
| 3 | 3 iterations < 9/10 → alerte producteur | Non | Manuel | Aucun test du compteur d'iterations | GAP — pas de test unitaire du compteur |

**Edge cases — mapping**
| Edge case | Test existant ? | Gap |
|-----------|----------------|-----|
| Script absent → FileNotFoundError | `test_web_production_flow.py::test_checkpoint_not_updated_when_missing_no_restore` | OK (couvert) |
| `_valide.json` desynchronise → regeneration | `test_web_production_flow.py::test_valide_json_created_from_script_json` | OK (couvert) |
| Checkpoint `dry_run: true` → ecrasement | Aucun | GAP |

### F2 — Production audio E01

| # | Given/When/Then | Testable auto ? | Type | Test existant ? | Gap |
|---|----------------|-----------------|------|----------------|-----|
| 1 | Checkpoint ready → kill + launch-fresh → DB started | Oui | Integration | **AUCUN** | **GAP CRITIQUE** — zero test pour `launch-fresh` et `kill-productions` |
| 2 | seg_003 verification en DB apres 90s | Oui | Integration | **AUCUN** | **GAP CRITIQUE** — zero test pour verification seg_003 |
| 3 | Auto-chain complete → fichier MP3 + duree 1680-1920s | Partiellement | Integration | `test_web_production_flow.py::test_chain_continues_on_audio_success`, `test_chain_stops_on_audio_error` | PARTIEL — auto-chain testee mais pas la duree finale ni le fichier MP3 |
| 4 | Producteur ecoute preview → valide montage | Non | Manuel | `test_web_production_flow.py::test_validation_humaine_restored_from_checkpoint` | OK (flag `validation_humaine` teste) |
| 5 | SIGTERM → checkpoint → auto-resume | Oui | Integration | `test_phase2_improvements.py::TestSIGTERMHandler` (3 tests), `test_corrections.py::test_auto_resume_excludes_waiting_statuses`, `test_auto_resume_has_recency_guard` | OK (bien couvert) |

**Edge cases — mapping**
| Edge case | Test existant ? | Gap |
|-----------|----------------|-----|
| Timeout ffmpeg > 1800s | `test_monteur.py` (mock subprocess) | OK |
| WAV corrompu < 1KB | `test_montage_resilience.py` | OK |
| Segments manquants → fallback etape_idx=2 | `test_montage_resilience.py` | OK |

### F3 — Generation scripts E05-E10

| # | Given/When/Then | Testable auto ? | Type | Test existant ? | Gap |
|---|----------------|-----------------|------|----------------|-----|
| 1 | Saison plan → generer E05 mi-saison → ~185 voix, ~41 SFX | Partiellement | Unit | `test_scripteur.py` (validation structure, comptage) | PARTIEL — comptage generic, pas specifique mi-saison |
| 2 | Script genere → audit → sync + checkpoint | Oui | Integration | Identique a F1#2 | Meme gap que F1#2 |
| 3 | E10 Esther → Lucas + morale + teasing S2 | Oui | Unit | **AUCUN** | GAP — pas de test specifique E10 |
| 4 | 6 checkpoints waiting_script crees | Oui | Integration | **AUCUN** | GAP — pas de test batch checkpoint creation |

**Edge cases — mapping**
| Edge case | Test existant ? | Gap |
|-----------|----------------|-----|
| 3 iterations < 9/10 → escalade | Identique F1#3 | GAP |
| Gouter thematique repete | **AUCUN** | GAP |
| E10 sans Lucas | **AUCUN** | GAP |

### F4 — GA4 sur site public

| # | Given/When/Then | Testable auto ? | Type | Test existant ? | Gap |
|---|----------------|-----------------|------|----------------|-----|
| 1 | Page charge → gtag config present | Oui | Unit | **AUCUN** | **GAP BLOQUANT** — F4 pas implemente du tout |
| 2 | Clic Play → `play_episode` avec params | Oui | Unit (JS) | **AUCUN** | **GAP BLOQUANT** — idem |
| 3 | Position >= 80% → `episode_complete` une seule fois | Oui | Unit (JS) | **AUCUN** | **GAP BLOQUANT** — idem |
| 4 | Resume apres pause → pas de `play_episode` en double | Oui | Unit (JS) | **AUCUN** | **GAP BLOQUANT** — idem |

**Note importante : F4 est a 0% d'implementation (confirme par l'audit infra). Les tests ne peuvent pas etre ecrits tant que le code n'existe pas. F4 est bloquant pour le North Star KPI (3000 ecoutes completes/mois).**

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
**Tests existants couvrant partiellement** : `test_valide_json_created_from_script_json`, `test_checkpoint_contient_type`
**Manque** : test integre combinant sync + checkpoint en un seul scenario

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
**Tests existants couvrant partiellement** : `test_chain_continues_on_audio_success` (auto-chain seulement)
**Manque** : TOUT le reste — launch-fresh, kill-productions, script writing, Object Storage purge, seg_003

### E2E-3 : Gouter thematique unique (F3)
```
1. Charger les 10 scripts (ou fixtures representatifs)
2. Pour chaque script : extraire le gouter de Mamie (grep "gouter|gateau|chocolat" dans segments Mamie)
3. Verifier : set(gouters).length == nombre_episodes (pas de doublons)
```
**Tests existants** : AUCUN

### E2E-4 : GA4 events (F4)
```
1. GET /  → verifier gtag.js dans le HTML
2. Verifier : script contient 'play_episode', 'episode_complete'
3. Verifier : try/catch autour des appels gtag
4. Verifier : anonymize_ip: true present
```
**Tests existants** : AUCUN (F4 pas implemente)

---

## 3. Matrice de couverture enrichie

### Par critere d'acceptation

| Feature | Critere | Tests existants | Couverture |
|---------|---------|----------------|------------|
| F1#1 | Audit 4 auditeurs | N/A (workflow agent) | N/A |
| F1#2 | Sync valide + checkpoint | 2 tests (partiels) | 60% |
| F1#3 | 3 iterations → alerte | 0 test | **0%** |
| F2#1 | kill + launch-fresh | 0 test | **0% CRITIQUE** |
| F2#2 | seg_003 verification | 0 test | **0% CRITIQUE** |
| F2#3 | Auto-chain → MP3 | 2 tests (auto-chain) | 40% |
| F2#4 | Validation humaine | 3 tests | 90% |
| F2#5 | SIGTERM → resume | 5 tests | 95% |
| F3#1 | Generation mi-saison | Tests scripteur generiques | 30% |
| F3#2 | Sync + checkpoint | Identique F1#2 | 60% |
| F3#3 | E10 Esther specifique | 0 test | **0%** |
| F3#4 | 6 checkpoints batch | 0 test | **0%** |
| F4#1 | gtag present | 0 test (code absent) | **0% BLOQUANT** |
| F4#2 | play_episode event | 0 test (code absent) | **0% BLOQUANT** |
| F4#3 | episode_complete 80% | 0 test (code absent) | **0% BLOQUANT** |
| F4#4 | Resume sans doublon | 0 test (code absent) | **0% BLOQUANT** |

### Par type de test

| Feature | Unit | Integration | E2E (pytest) | Manuel |
|---------|------|-------------|--------------|--------|
| F1 Audit E03/E04 | 1 test (partiel) | 1 test (partiel) | 0 | N/A (agent) |
| F2 Audio E01 | 2 tests (ffmpeg, WAV) | 5 tests (SIGTERM, chain, checkpoint) | 0 | Ecoute preview |
| F3 Scripts E05-E10 | Tests scripteur generiques | 0 specifique | 0 | Score LLM |
| F4 GA4 | **0 (code absent)** | **0 (code absent)** | **0 (code absent)** | GA4 Realtime |

---

## 4. Tests prioritaires (top 8 — enrichi)

| # | Test | Feature | Priorite | Justification | Existe ? |
|---|------|---------|----------|---------------|----------|
| 1 | **test_launch_fresh_writes_script_and_purges** | F2 | P0 | 4 echecs de production passes. Verifier script ecrit + 7 prefixes Object Storage purges. | NON |
| 2 | **test_kill_productions_marks_failed** | F2 | P0 | Pre-requis de launch-fresh. Verifier que les productions non-terminales passent a `failed`. | NON |
| 3 | **test_seg_003_verification** | F2 | P0 | Empeche 45 min d'audio sur le mauvais script. Verifier `nb_caracteres` match. | NON |
| 4 | **test_launch_fresh_creates_checkpoint_with_hash** | F2 | P0 | Le checkpoint doit contenir `script_content_hash` + `validation_humaine: true`. | NON |
| 5 | **test_checkpoint_fields_after_audit** | F1/F3 | P1 | Verifier `waiting_script`, `validation_humaine: true`, `dry_run: false`, `type_episode`. | NON |
| 6 | **test_valide_sync_after_correction** | F1/F3 | P1 | Hash `_script.json` == `_valide.json`. 1 redo complet cause par desync. | PARTIEL |
| 7 | **test_ga4_gtag_present_and_anonymized** | F4 | P1 | North Star KPI. A ecrire APRES implementation F4. | BLOQUE (code absent) |
| 8 | **test_auto_chain_audio_sfx_montage** | F2 | P1 | Verifier la chaine complete callback → callback → completion. | PARTIEL |

---

## 5. Outils et mocks

- **Framework** : pytest (existant, 577+ tests — ne pas migrer)
- **Mocks necessaires** :
  - `ElevenLabs` : `unittest.mock.patch` sur `producteur_audio` et `sfx_provider` (retourne bytes factices)
  - `Claude API` : `monkeypatch` sur `config.appel_claude_avec_retry` (retourne JSON fixture)
  - `Object Storage` : `monkeypatch` sur `persistent_storage.upload_file` / `restore_*` (retourne True/None)
  - `ffmpeg` : `monkeypatch` sur `subprocess.run` (retourne `CompletedProcess` factice)
  - `DB` : Tests existants utilisent `monkeypatch` sur les repos (`ProductionRepo`, `ScriptRepo`, etc.)
  - `gtag()` : Test du HTML rendu par Flask (`client.get("/")` puis parse le HTML) — APRES implementation F4
- **Fixtures existantes** : `conftest.py` contient `script_exemple`, `script_avec_sfx_overlay`, `review_exemple` — reutiliser
- **Fixtures a creer** :
  - `flask_test_client` avec app.test_client() + mock DB
  - `sample_launch_fresh_body` avec script JSON + hash attendu
- **Pas de tests E2E navigateur** : GA4 events sont testes par inspection du HTML (pas de Playwright)

---

## 6. Resume des gaps critiques

| # | Gap | Severite | Feature | Action |
|---|-----|----------|---------|--------|
| 1 | Zero test pour `launch-fresh` | **P0 CRITIQUE** | F2 | Ecrire test_launch_fresh_writes_script_and_purges |
| 2 | Zero test pour `kill-productions` | **P0 CRITIQUE** | F2 | Ecrire test_kill_productions_marks_failed |
| 3 | Zero test pour verification seg_003 | **P0 CRITIQUE** | F2 | Ecrire test_seg_003_verification |
| 4 | F4 GA4 non implemente | **P0 BLOQUANT** | F4 | Implementer F4 AVANT d'ecrire les tests |
| 5 | Checkpoint hash non teste | P1 | F2 | Ecrire test_launch_fresh_creates_checkpoint_with_hash |
| 6 | Sync valide partiellement testee | P1 | F1/F3 | Enrichir test existant avec verification combinee |
| 7 | E10 Esther non teste | P2 | F3 | Ecrire test specifique Lucas + morale + teasing |
| 8 | Gouter thematique non teste | P2 | F3 | Ecrire test unicite gouters sur 10 episodes |

---

## Auto-evaluation

- [x] Chaque critere d'acceptation mappe a un test existant ou identifie comme gap
- [x] Criteres vagues reformules (F4#1 "visible en 30s" → "gtag config present dans le HTML")
- [x] 4 scenarios E2E couvrent les parcours critiques
- [x] Matrice enrichie feature x critere x test existant x gap
- [x] 8 tests prioritaires justifies par impact + existence
- [x] Outils = pytest existant, pas de migration
- [x] Gaps classes par severite (P0/P1/P2)
- [x] F4 clairement identifie comme bloquant (code absent)

---

**Handoff → @orchestrator**
- Fichiers produits : `docs/qa/qa-strategy.md` (enrichi)
- Decisions prises :
  - 3 gaps P0 CRITIQUES identifies : launch-fresh, kill-productions, seg_003 — zero couverture test
  - F4 GA4 est bloquant : 0% implemente, 0% teste — North Star KPI inaccessible
  - Les tests SIGTERM/auto-resume sont bien couverts (5 tests, 95%)
  - Les tests de validation humaine sont bien couverts (3 tests, 90%)
- Points d'attention :
  - Les 4 premiers tests prioritaires (P0) sont TOUS inexistants — a ecrire en urgence
  - F4 necessite d'abord l'implementation du code, puis les tests
  - Les fixtures Flask test_client n'existent pas encore — a creer pour tester les routes web
