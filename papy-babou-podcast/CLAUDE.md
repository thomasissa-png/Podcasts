# CLAUDE.md — Papy Babou Podcast Production System

## Project Overview

Production pipeline for "Les Histoires de Papy Babou", a French children's podcast (ages 6-10) based on Biblical stories. Supports both episodic and **serial production** (10 episodes/season with arcs, character evolution, rituals, previously-on/teasing).

## Architecture

```
papy-babou-podcast/
├── main.py                  # Orchestrator: pipeline(), CLI commands, historique
├── config.py                # Central config, API keys, rate limiters, season mgmt
├── utils.py                 # Shared utilities: JSON parsing, file locking, secret masking
├── agents/
│   ├── __init__.py          # Exports all 9 agents
│   ├── scripteur.py         # Script generation (Claude API) — serial-aware
│   ├── reviewer.py          # Script review (Claude API) — type-aware criteria
│   ├── producteur_audio.py  # TTS via ElevenLabs (parallel, per-character voices)
│   ├── sfx_provider.py      # SFX: ElevenLabs → Freesound → silence fallback
│   ├── monteur.py           # Audio assembly: jingles, mixing, LUFS, chapters
│   ├── metadonnees.py       # Metadata generation (Claude API) + transcript
│   ├── publisher.py         # RSS 2.0 feed + iTunes/Podcast Index namespaces
│   ├── cover_art.py         # DALL-E 3 cover art generation (PNG format)
│   └── planificateur.py     # Season planning (Claude API)
├── tests/                   # 255 tests (pytest)
│   ├── conftest.py          # Fixtures: script_exemple, script_avec_sfx_overlay, review_exemple
│   ├── test_scripteur.py    # Validation, comptage, bible, serial context, structure narrative
│   ├── test_reviewer.py     # Review validation, scoring, corrections vs alertes
│   ├── test_monteur.py      # Slug, assets, assembly, jingles, pan, silence fallback
│   ├── test_main.py         # Historique, checkpoints, costs
│   ├── test_config.py       # API keys, rate limiter, formats, seasons, characters
│   ├── test_sfx_provider.py # Local/cache/API fallback chain
│   ├── test_planificateur.py# Validation, export CSV/MD, generation
│   └── test_corrections.py  # Bug regression tests (19 tests)
├── assets/                  # Audio assets (jingles, music)
├── data/
│   ├── personnages.json     # Character bible
│   └── saisons/             # Season plans (saison_01.json, etc.)
└── output/                  # Generated episodes, scripts, segments
```

## Key Concepts

### Serial Production System
- **Season Plans**: Generated via `planifier-saison`, stored as `saisons/saison_XX.json`
- **Episode Types**: `ouverture` (15min/1600 words), `standard` (13min/1400), `mi-saison` (15/1600), `final` (18/1900), `bonus` (10/1000)
- **STRUCTURES_NARRATIVES**: Template dict in scripteur.py with previously-on, teasing, rituals per type
- **Character Evolution**: arcs_personnages in season bible, tracked across episodes
- **Dynamic Characters**: `config.ajouter_personnage()` + `config.personnages_valides()` (set-based)
- **Variable season length**: `nb_episodes` parameter in `planifier_saison()` (default 10)

### Human Approval Workflow (3 steps)
The pipeline has **3 human validation points** (skipped in `--auto` mode):
1. **Plan de saison** (`_validation_plan_saison`): After season plan generation in `planifier-saison`, review the complete plan (episodes, arcs, characters, rituals). Options: validate, modify JSON, regenerate, abandon. Also a go/no-go confirmation before `produire-saison` starts.
2. **Script** (`_validation_script`): After script generation + review loop. Options: validate, modify JSON, give corrections (re-runs scripteur), abandon.
3. **Montage** (`_validation_montage`): After audio assembly. Options: validate (publish), abandon (audio kept).

### API Integration
- **Claude (Anthropic)**: Script generation, review, metadata, season planning — all use `config.appel_claude_avec_retry()` with exponential backoff on 429/500/502/503/529
- **ElevenLabs**: TTS voices (per-character voice_id) + SFX generation — with `RateLimiter(3/s)` and retry
- **OpenAI DALL-E 3**: Cover art — uses `rate_limiter_openai`
- **Freesound**: SFX fallback

### Shared Utilities (`utils.py`)
- `extraire_json_llm()` / `parser_json_llm()`: Extract and parse JSON from LLM responses (handles markdown backticks, text before JSON, etc.)
- `fichier_lock()`: Context manager for advisory file locking (`fcntl.LOCK_EX`)
- `masquer_secret()`: Mask API keys in log output (shows first/last 4 chars)

### Checkpoint System
- Saves after each major step: script → audio → sfx → montage → metadonnees
- Data includes: episode_id, titre, resume, saison, numero, morale, **type_episode**, dry_run, rapport, **script_path**
- Resume with `reprendre -c checkpoints/S01E01_checkpoint.json`
- Checkpoints archived (renamed `_done_TIMESTAMP`) on success, never deleted

### Historique
- JSON file: `historique_episodes.json` (with advisory file locking)
- DB + JSON dual storage (PostgreSQL primary, JSON fallback)
- Each entry: episode_id, titre, morale, resume_court (from segment text, not title), date_production, score_review, personnages_presents, moments_cles, questions_ouvertes, evolutions_personnages, ambiance, type_episode

### Error Handling
- Pipeline wrapped in try/except: DB status updated to "failed", partial rapport saved to `{episode_id}_rapport_echec.json`
- `_production_id_courante` reset at each pipeline start to avoid cross-contamination

## CLI Commands

```bash
python main.py produire -e "Le buisson ardent" -s 1 -n 1 -r "..." -m "..."
python main.py produire -e "..." -s 1 -n 1 -r "..." --dry-run --auto
python main.py interactif
python main.py batch -f planning.json
python main.py planifier-saison -s 1 -t "Les grands voyages" -d "..." -p "mamie_rose,cousin_paul"
python main.py produire-saison -s 1 --auto [--dry-run] [-e "1,3,5"]
python main.py dashboard [-s 1]
python main.py reprendre -c checkpoints/S01E01_checkpoint.json
```

## Running Tests

```bash
python -m pytest tests/ -q              # All tests
python -m pytest tests/ -x              # Stop on first failure
python -m pytest tests/test_corrections.py -v  # Bug regression tests only
```

**Expected**: 255 passed, 3 skipped (integration tests requiring ffmpeg)

## Critical Patterns to Remember

### When modifying scripteur.py
- `type_episode` default is `"standard"` — comparison must be `== "standard"` not `not type_episode`
- `_construire_system_prompt()` accepts: `type_episode`, `contexte_saison`, `episode_plan`, `historique`
- `_valider_structure()` uses `config.personnages_valides()` (dynamic set), not a hardcoded set
- `STRUCTURES_NARRATIVES` dict has templates for all 5 episode types
- Adaptive `max_tokens` by episode type: final=8192, ouverture/mi-saison=7168, standard=6144, bonus=4096
- Post-generation word count validation with warnings against `FORMATS_EPISODES`
- Full season history for final/mi-saison episodes (not just last 5)
- Ambiance fallback from 'fond_doux' to 'calme' (mutates script in place)

### When modifying reviewer.py
- System prompt uses `.format()` — JSON braces must be double-escaped (`{{` / `}}`)
- Format criteria dynamically synced from `config.FORMATS_EPISODES` via `_construire_system_prompt_reviewer()`
- `_verifier_coherence()` checks segment count ratio and principal character presence
- `extraire_corrections()` returns corrections only; alertes used as fallback when no corrections (avoids infinite review loops)

### When modifying main.py
- **3 validation functions**: `_validation_plan_saison()`, `_validation_script()`, `_validation_montage()`
- `_validation_script()` must receive and pass serial context: `contexte_saison`, `episode_plan`, `type_episode`
- All `sauvegarder_checkpoint()` calls must include `type_episode` in data
- `ajouter_historique()` builds `resume_court` from first 3 segments, not from title
- Pipeline variables (`chemin_hq`, `resultat_montage`, `duree_secondes`, `taille_bytes`, `score`) must be initialized before the step loop for checkpoint resume safety
- `_production_id_courante` reset to None at pipeline start

### When modifying producteur_audio.py
- Thread-safe character counting with `threading.Lock` (`self._compteur_lock`)
- Secondary characters without voice_id → fallback to narrateur's voice_id
- `max_workers` must be `max(1, min(config, total))` to avoid 0

### When modifying agents calling Claude API
- Always use `config.appel_claude_avec_retry(client, ...)` instead of raw `client.messages.create()`
- This handles rate limiting + retry with backoff on 429/500/502/503/529
- Use `parser_json_llm()` from `utils.py` (not custom backtick stripping)

### When modifying monteur.py
- Chapter timestamps start at `intro_jingle_ms + 500ms` (not 0)
- `_preparer_fond()` must handle empty AudioSegment (0ms) without division by zero
- `_charger_jingle()` selects jingle by episode type from `config.JINGLES_PAR_TYPE`
- Missing audio segments replaced with silence (not crash) with warning logged
- SFX overlay truncation logged as warning when overlay > remaining segment duration

### When modifying sfx_provider.py
- Local SFX file paths must be validated: `resolve()` must stay within `SFX_DIR.resolve()`

### When modifying cover_art.py
- Uses `config.rate_limiter_openai` (NOT `rate_limiter_anthropic`)
- DALL-E 3 returns PNG — extension is `.png` (not `.jpg`)

### When modifying metadonnees.py
- `_generer_transcript()` enriches character names from bible + `.replace("_", " ").title()` fallback
- Dry-run: SFX excluded from word count, SFX duration added separately
- Cover art path checks both `.png` and `.jpg` extensions

### When modifying publisher.py
- `pubDate` uses `now.timestamp()` (NOT `mktime(now.timetuple())` which has timezone issues)
- GUID based on `episode_id + titre` (not titre alone) — uses `uuid5(NAMESPACE_URL, seed)`
- RSS deduplication: replaces existing items with same GUID before inserting

### When modifying config.py
- `CLAUDE_MODEL` configurable via `CLAUDE_MODEL` env var
- `PODCAST_CONFIG` fields from env vars with placeholder warnings at import time
- API keys masked in error logs via `masquer_secret()`

### When modifying database.py
- Table names in `obtenir_stats_db` use `psycopg2.sql.Identifier` (not f-strings)

### When modifying planificateur.py
- Variable season length via `nb_episodes` parameter (default 10)
- Plan coherence validation: episode type checks, ambiance variety warnings

## Common Pitfalls
- ffmpeg is not available in test environment — mock `AudioSegment.from_mp3` and `silence.export`
- Tests that create audio files must use `write_bytes(b"fake")` + mock
- `config.charger_saison(N)` returns `{}` (not None) when season doesn't exist
- `config.personnages_valides()` returns a set, not a list
- Rate limiters are global singletons — tests should mock them or use monkeypatch
- The `score` variable in pipeline must be initialized before the review loop (checkpoint resume)
- JSON file writes use advisory file locking (`fichier_lock()` from utils.py)
- Reviewer system prompt JSON braces must be `{{` `}}` for `.format()` compatibility

## Completed Bug Fixes (Session 1)
All 32 bugs from comprehensive audit implemented and tested (255 tests, 0 failures):
- BUG 2: Resume parameter passthrough in corrections
- BUG 3: Ambiance fallback mutation
- BUG 4: Adaptive max_tokens by episode type
- BUG 5: Post-generation word count validation
- BUG 6: Reviewer structure coherence verification
- BUG 8: Corrections vs alertes separation
- BUG 9: Thread-safe TTS counter
- BUG 10: SFX overlay truncation warning
- BUG 11: Missing segments → silence fallback
- BUG 12: Smart chapter generation
- BUG 14: RSS GUID deduplication
- BUG 15: GUID based on episode_id + titre
- BUG 16: Dry-run SFX duration counting
- BUG 17: Cover art PNG extension + dual format check
- BUG 18: Full history for final/mi-saison episodes
- BUG 19: Secondary characters scoped to current season
- BUG 20: Variable season length
- BUG 21: Plan coherence validation
- BUG 22: File locking on historique writes
- BUG 23: Production ID reset
- BUG 24: Script path in checkpoint
- BUG 25: Parameterized SQL table names
- BUG 26: API key masking in logs
- BUG 27: Config from env vars
- BUG 28: Configurable Claude model
- BUG 29: Pipeline error handling with DB rollback
- BUG 31: Dynamic reviewer format criteria
- BUG 32: Shared JSON parser (utils.py)

## Git Workflow
- Branch: `claude/podcast-production-system-YkngW`
- Push: `git push -u origin claude/podcast-production-system-YkngW`
- Retry on network failure: 4 times with exponential backoff (2s, 4s, 8s, 16s)
