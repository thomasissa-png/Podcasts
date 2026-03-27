# Audit Backend — web.py vs Specs fonctionnelles
> @infrastructure — 2026-03-25
> Scope : Routes API critiques, resilience, securite, performance
> Fichiers audites : web.py (~5700 lignes), database.py, persistent_storage.py, templates/public.html

---

## 1. Conformite aux specs fonctionnelles (F1-F4)

### F2 — Production audio E01

| Spec | Route/Mecanisme | Statut | Details |
|------|----------------|--------|---------|
| kill-productions avant launch-fresh | `POST /api/episode/<id>/kill-productions` (L2536) | OK | Marque toutes les productions non-terminales comme `failed` en DB |
| launch-fresh avec script en body | `POST /api/episode/<id>/launch-fresh` (L2565) | OK | Ecrit `_script.json` + `_valide.json`, purge 7 prefixes Object Storage, cree checkpoint, lance auto-chain |
| seg_003 verification en DB sous 90s | Pas de route dediee | PARTIEL | La verification est manuelle via `/api/claude/query` SQL. Pas de route automatisee `/api/episode/<id>/verify-seg003`. Conforme aux specs (verification cote producteur), mais automatisable. |
| Auto-chain audio → SFX → montage | `on_success_fn` callbacks dans `_start_job()` | OK | `_chain_sfx_then_montage` → `_chain_montage` — enchainement automatique |
| Duree 1680-1920s | Pas de validation cote web | PARTIEL | La duree est verifiee dans le pipeline CLI (`main.py`), pas dans les routes web. Le dashboard affiche la duree mais ne bloque pas. |
| Validation humaine montage | `POST /api/episode/<id>/validate` | OK | Met `validation_humaine: true` en DB et checkpoint |
| SIGTERM → checkpoint → auto-resume | `_sigterm_handler` (main.py) + `_auto_resume_interrupted()` (web.py L3606) | OK | Handler forward SIGTERM au subprocess, daemon thread relance apres redeploy |

### F1 / F3 — Audit et scripts

| Spec | Route/Mecanisme | Statut | Details |
|------|----------------|--------|---------|
| Workflow dans Claude Code | N/A | OK | Pas de routes web pour l'audit — conforme (workflow CLI/agents) |
| Sync `_script.json` → `_valide.json` | `launch-fresh` + `continue-production` | OK | Les deux routes copient/restaurent le fichier valide |
| Checkpoint `waiting_script` | Pipeline + `_etape_mapping` | OK | `waiting_script` mappe vers `audio` dans `_pipeline_inner()` |

### F4 — GA4 sur site public

| Spec | Route/Mecanisme | Statut | Details |
|------|----------------|--------|---------|
| `gtag.js` dans `<head>` | `templates/public.html` | **ABSENT** | Zero reference a gtag, GA4, google analytics dans le HTML |
| `play_episode` event | JS dans `public.html` | **ABSENT** | Aucun event tracking implemente |
| `episode_complete` a 80% | JS dans `public.html` | **ABSENT** | Aucun seuil de completion |
| `anonymize_ip: true` | Config GA4 | **ABSENT** | Pas de configuration GA4 |

**Verdict F4 : 0% implemente. C'est le seul gap majeur entre backend et specs.**

---

## 2. Bugs P0 (backlog.md) — Verification

| Bug | Description | Statut | Preuve |
|-----|------------|--------|--------|
| E1-S1 | Chemins audio double-nestes `audio/episodes/audio/episodes/` | CORRIGE | Toutes les routes V1+V2 utilisent `config.OUTPUT_DIR` directement |
| E1-S2 | Arguments `upload_file(local_path, key)` inverses | CORRIGE | 3 sites verifies (L4502, L5028, L5031) — ordre correct `(storage_key, local_path)` |
| E1-S3 | `OUTPUT_DIR / "segments"` au lieu de `config.SEGMENTS_DIR` | CORRIGE | Toutes les routes V2 utilisent `config.SEGMENTS_DIR` |

---

## 3. Resilience

### SIGTERM et auto-resume

| Composant | Implementation | Verdict |
|-----------|---------------|---------|
| SIGTERM handler | `_sigterm_handler` dans main.py, forward au subprocess | OK |
| Auto-resume thread | `_auto_resume_interrupted()` daemon thread au demarrage | OK |
| Exclusions auto-resume | `NOT IN ('completed', 'failed', 'waiting_script', 'waiting_montage')` | OK |
| Recency guard | `updated_at < NOW() - 2 minutes` | OK |
| DB retry au demarrage | 4 tentatives avec backoff (5s, 8s, 12s, 20s) | OK |
| Checkpoint DB restore | `_restore_checkpoint_from_db()` avec detection double-envelope | OK |
| Segment restore avant montage | Guard `etape_idx > 2` + `restore_segments()` + fallback `etape_idx = 2` | OK |

### Object Storage coverage

| Type fichier | Upload | Restore | Prefixe |
|-------------|--------|---------|---------|
| Audio HQ/Preview | OK | OK | `audio/` |
| Script valide | OK | OK | `scripts/` |
| Rapport | OK | OK | `rapports/` |
| Checkpoint | OK | OK | `checkpoints/` |
| Segments voix/SFX | OK | OK | `segments/` |
| Metadonnees | OK | OK | `metadonnees/` |
| Chapitres | OK | OK | `chapters/` |
| Cover art | OK | OK | `covers/` |
| WAV intermediaire | OK | OK | `montage_wav/` |

**Verdict resilience : 10/10 — couverture complete, tous les cas de redeploy couverts.**

---

## 4. Securite

| Aspect | Implementation | Verdict | Notes |
|--------|---------------|---------|-------|
| Auth Bearer token | `_CLAUDE_API_SECRET` via env, verifie dans `@_require_auth` | OK | |
| Auth session admin | Login form + `session["logged_in"]` | OK | |
| Secret key Flask | `FLASK_SECRET_KEY` env var avec warning si defaut | ACCEPTABLE | Le warning est la, mais en prod le defaut est trop previsible. Recommandation : bloquer le demarrage si `FLASK_SECRET_KEY` est le defaut. |
| XSS protection | `escapeHtml()` dans dashboard.html, `encodeURIComponent()` pour les URLs | OK | Tous les `.innerHTML` passent par `escapeHtml()` |
| Routes publiques whitelist | `_PUBLIC_ROUTES` set + `@app.before_request` | OK | |
| SQL injection | `psycopg2.sql.Identifier` pour noms de tables, parametres lies | OK | |
| Purge routes | Double confirmation UI, audit trail DB | OK | |

**Points d'amelioration securite :**
1. Pas de CSRF token sur les formulaires (Flask-WTF absent) — risque faible car API Bearer, mais dashboard admin vulnerable
2. `_CLAUDE_API_SECRET` en clair dans env — acceptable pour Replit Secrets
3. Rate limiting absent sur routes d'authentification — risque de brute-force

---

## 5. Performance

| Aspect | Implementation | Verdict | Notes |
|--------|---------------|---------|-------|
| Timeout production | `_TIMEOUT_PRODUIRE = 7200s` (2h) | OK | Suffisant pour episodes 35 min + marge |
| Timeout Gunicorn | `3900s` dans `gunicorn.conf.py` | OK | > `_TIMEOUT_PRODUIRE` n'est pas requis car les jobs sont en subprocess |
| Thread safety jobs | `_jobs_lock = threading.Lock()` sur toutes les mutations de `_jobs` | OK | |
| Thread safety logs | `_lines_lock` dans `_run_cli()` | OK | |
| DB pool | `ThreadedConnectionPool(minconn=1, maxconn=10)` + keepalives | OK | |
| DB keepalive | `_pool_keepalive_loop()` daemon, ping toutes les 120s | OK | Empeche Neon de fermer les connexions idle |
| Job TTL | `_JOB_RESULT_TTL = 60s` apres lecture | OK | Evite les race conditions poll |
| Workers | 1 worker × 8 threads | OK | 1 worker = `_jobs` dict en memoire coherent |

---

## 6. Routes API — Inventaire complet audite

| Route | Methode | Auth | Specs | Statut |
|-------|---------|------|-------|--------|
| `/api/episode/<id>/kill-productions` | POST | Bearer | F2 | OK |
| `/api/episode/<id>/launch-fresh` | POST | Bearer | F2 | OK |
| `/api/episode/<id>/continue-production` | POST | Bearer | F2 | OK |
| `/api/job-status/<job_id>` | GET | Bearer | Monitoring | OK |
| `/api/running-jobs` | GET | Bearer | Monitoring | OK |
| `/api/public/episodes` | GET | Public | Site public | OK |
| `/api/episode/<id>/validate` | POST | Bearer | F2 | OK |
| `/api/episode/<id>/delete` | POST | Bearer | Admin | OK |
| `/api/purge/saison/<num>` | POST | Bearer | Admin | OK |
| `/api/purge/tout` | POST | Bearer | Admin | OK |
| `/api/claude/query` | POST | Bearer | Monitoring | OK |
| `/api/v2/montage/<id>/publish` | POST | Bearer | Publication | OK |
| `/api/v2/episode/<id>/publish-v1` | POST | Bearer | Publication | OK |

---

## 7. Synthese

### Ce qui matche les specs
- **F1 (Audit scripts)** : 100% — workflow Claude Code, pas de routes web requises
- **F2 (Production audio)** : 95% — toutes les routes presentes, auto-chain, resilience complete. Seule la verification automatique seg_003 n'est pas une route dediee (verification manuelle via SQL).
- **F3 (Scripts E05-E10)** : 100% — memes mecaniques que F1
- **P0 bugs** : 100% — les 3 bugs (E1-S1, E1-S2, E1-S3) sont corriges

### Ce qui ne matche PAS les specs
- **F4 (GA4)** : 0% — completement absent. Aucun code gtag.js, aucun event tracking, aucune configuration GA4 dans `public.html`.

### Actions correctives recommandees

| # | Priorite | Action | Impact |
|---|----------|--------|--------|
| 1 | **P0 CRITIQUE** | Implementer F4 (GA4) dans `public.html` : gtag.js, `play_episode`, `episode_complete`, `anonymize_ip` | North Star KPI impossible a mesurer sans GA4 |
| 2 | P1 | Ajouter CSRF protection sur le dashboard admin (Flask-WTF ou token custom) | Securite formulaires |
| 3 | P2 | Bloquer demarrage si `FLASK_SECRET_KEY` est la valeur par defaut | Securite session |
| 4 | P2 | Ajouter rate limiting sur `/admin/login` | Anti brute-force |
| 5 | P3 | Route dediee `/api/episode/<id>/verify-seg003` pour automatiser la verification | Qualite de vie producteur |

---

## Auto-evaluation

- [x] Toutes les routes critiques auditees (launch-fresh, kill-productions, continue-production, auto-resume)
- [x] 3 bugs P0 verifies comme corriges
- [x] Resilience complete (SIGTERM, Object Storage, checkpoints, DB pool)
- [x] Securite auditee (auth, XSS, SQL injection)
- [x] Performance verifiee (timeouts, thread safety, pool)
- [x] Gap F4 (GA4) clairement identifie et documente
- [x] Actions correctives priorisees

---

**Handoff → @qa**
- Fichiers produits : `docs/infra/backend-audit.md`
- Decisions prises :
  - F4 GA4 est le seul gap majeur — 0% implemente vs specs
  - Les 3 bugs P0 sont confirmes corriges
  - La resilience (SIGTERM + Object Storage + auto-resume) est complete
  - La securite est acceptable avec 3 ameliorations recommandees (CSRF, secret key, rate limiting)
- Points d'attention :
  - Zero test pour `launch-fresh` et `kill-productions` — couverture critique manquante
  - F4 doit etre implemente avant tout lancement public (North Star KPI en depend)
