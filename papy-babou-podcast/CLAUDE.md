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
├── tests/                   # 386 tests (pytest)
│   ├── conftest.py          # Fixtures: script_exemple, script_avec_sfx_overlay, review_exemple
│   ├── test_scripteur.py    # Validation, comptage, bible, serial context, structure narrative
│   ├── test_reviewer.py     # Review validation, scoring, corrections vs alertes
│   ├── test_monteur.py      # Slug, assets, assembly, jingles, pan, silence fallback
│   ├── test_main.py         # Historique, checkpoints, costs
│   ├── test_config.py       # API keys, rate limiter, formats, seasons, characters
│   ├── test_sfx_provider.py # Local/cache/API fallback chain
│   ├── test_planificateur.py# Validation, export CSV/MD, generation
│   └── test_corrections.py  # Bug regression + creative quality tests (77 tests)
├── assets/                  # Audio assets (jingles, music)
├── data/
│   ├── personnages.json     # Character bible
│   ├── preferences_producteur.json  # Persistent producer preferences/rules
│   └── saisons/             # Season plans (saison_01.json, etc.)
└── output/                  # Generated episodes, scripts, segments
```

## Key Concepts

### Serial Production System
- **Season Plans**: Generated via `planifier-saison`, stored as `saisons/saison_XX.json`
- **Episode Types**: `ouverture` (30min/3200 words), `standard` (25min/3000), `mi-saison` (30/3200), `final` (35/3800), `bonus` (20/2000)
- **STRUCTURES_NARRATIVES**: Template dict in scripteur.py with previously-on, teasing, rituals per type
- **Character Evolution**: arcs_personnages in season bible, tracked across episodes
- **Dynamic Characters**: `config.ajouter_personnage()` + `config.personnages_valides()` (set-based)
- **Variable season length**: `nb_episodes` parameter in `planifier_saison()` (default 10)

### Human Approval Workflow (5 steps)
The pipeline has **5 human validation points** (skipped in `--auto` mode):
1. **Plan de saison** (`_validation_plan_saison`): Options: validate, modify JSON, regenerate, guided regeneration with instructions (i), abandon. Shows full episode details, cost estimates. Instructions stored in plan JSON (`instructions_producteur`). Decisions logged in `plan["saison"]["decisions_humaines"]`.
2. **Script** (`_validation_script`): Returns `tuple[dict, float]`. Options: validate, modify JSON (triggers Reviewer re-evaluation), corrections (re-runs scripteur + reviewer), abandon. After validation with corrections, proposes memorizing corrections as permanent preferences (A6). Score recap with duration/word targets.
3. **Montage** (`_validation_montage`): Returns `bool`. Options: validate, edit script then remontage (e), relaunch montage (r), abandon. Edit option reloads and validates modified script before re-assembling.
4. **Métadonnées** (`_validation_metadonnees`): Options: validate, regenerate with instructions (c), modify JSON manually, abandon. Regeneration calls `Metadonnees.generer()` with user instructions.
5. **Publication** (`_validation_publication`): **Prerequisite check**: blocks publication unless both `rapport["etapes"]["script"]["validation_humaine"]` AND `rapport["etapes"]["montage"]["validation_humaine"]` are True. Options (if prerequisites met): publish, skip (audio conserved), abandon. Double safety: `_validation_publication()` checks prerequisites, AND a hard guard-rail before `publisher.publier()` re-checks them.

**Publication safety invariant**: No episode can be published without script review (relecture) AND montage listening (écoute). This is enforced at 3 levels:
- `_validation_publication()` checks prerequisite flags and returns False if missing
- Hard guard-rail in pipeline before `publisher.publier()` blocks even if validation was bypassed
- When no preview file exists, montage validation is impossible → `validation_humaine` stays False → publication blocked
- Checkpoint resume (`reprendre`) restores `validation_humaine` flags from saved rapport data

All pipeline validation functions log decisions to `rapport["decisions_humaines"]`. Plan validation logs to `plan["saison"]["decisions_humaines"]`. Uses `if rapport is not None:` (not `if rapport:`) since empty dicts are falsy.

### Producer Memory System
- **Preferences** (`data/preferences_producteur.json`): Persistent rules/preferences accumulated from human corrections. Functions: `charger_preferences()`, `sauvegarder_preferences()`, `ajouter_preference()`, `_construire_bloc_preferences()`.
- **Injection**: Preferences injected into scripteur system prompt (`{preferences_producteur}` placeholder in `SYSTEM_PROMPT_BASE`) and planificateur prompt. All `scripteur.generer()` and `planificateur.planifier_saison()` calls pass `preferences_producteur=_construire_bloc_preferences()`.
- **Historique enrichi**: `ajouter_historique()` includes `retours_humains` field (corrections text from `rapport["decisions_humaines"]`). Scripteur sees these in the "ÉPISODES PRÉCÉDENTS" section of its prompt.
- **A6 flow**: After script validation with corrections, user is asked "memoriser comme regles permanentes?". If yes, corrections are added to `preferences_producteur.json` via `ajouter_preference()`.

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

**Expected**: 537 passed, 3 skipped (integration tests requiring ffmpeg), 3 pre-existing flaky (TestHistorique)

## Critical Patterns to Remember

### When modifying scripteur.py
- `type_episode` default is `"standard"` — comparison must be `== "standard"` not `not type_episode`
- `_construire_system_prompt()` accepts: `type_episode`, `contexte_saison`, `episode_plan`, `historique`, `preferences_producteur`
- `Scripteur.generer()` accepts `preferences_producteur` param — passed through to `_construire_system_prompt()`
- `SYSTEM_PROMPT_BASE` has `{preferences_producteur}` placeholder for producer rules injection
- `_valider_structure()` uses `config.personnages_valides()` (dynamic set), not a hardcoded set
- `STRUCTURES_NARRATIVES` dict has templates for all 5 episode types
- Adaptive `max_tokens` by episode type: final=16384, ouverture/mi-saison=12288, standard=10240, bonus=8192
- Post-generation word count validation with warnings against `FORMATS_EPISODES`
- Full season history for final/mi-saison episodes (not just last 5)
- Ambiance fallback from 'fond_doux' to 'calme' (mutates script in place)

### When modifying reviewer.py
- System prompt uses `.format()` — JSON braces must be double-escaped (`{{` / `}}`)
- Format criteria dynamically synced from `config.FORMATS_EPISODES` via `_construire_system_prompt_reviewer()`
- `_verifier_coherence()` checks segment count ratio and principal character presence
- `extraire_corrections()` returns corrections only; alertes used as fallback when no corrections (avoids infinite review loops)

### When modifying main.py
- **5 validation functions**: `_validation_plan_saison()`, `_validation_script()`, `_validation_montage()`, `_validation_metadonnees()`, `_validation_publication()`
- `_validation_script()` returns `tuple[dict, float]` (script, score) — NOT just `dict`
- `_validation_montage()` returns `bool` (True if remontage requested) — call site has remontage loop
- Decision logging: all validation functions use `rapport.setdefault("decisions_humaines", []).append({...})`
- Use `if rapport is not None:` (NOT `if rapport:`) — empty dicts are falsy
- `_validation_script()` must receive and pass serial context: `contexte_saison`, `episode_plan`, `type_episode`
- All `sauvegarder_checkpoint()` calls must include `type_episode` in data
- `ajouter_historique()` builds `resume_court` from first 3 segments, not from title; includes `retours_humains` from `rapport["decisions_humaines"]`
- All `scripteur.generer()` calls must pass `preferences_producteur=_construire_bloc_preferences()`
- All `planificateur.planifier_saison()` calls must pass `preferences_producteur=_construire_bloc_preferences()`
- `_validation_metadonnees()` accepts `script` and `duree_secondes` for regeneration option
- Pipeline variables (`chemin_hq`, `resultat_montage`, `duree_secondes`, `taille_bytes`, `score`) must be initialized before the step loop for checkpoint resume safety
- `_validation_publication()` checks `rapport["etapes"]["script"]["validation_humaine"]` and `rapport["etapes"]["montage"]["validation_humaine"]` — returns False if either missing
- Checkpoint resume restores `validation_humaine` flags from `checkpoint_data["etapes"]` so publication prerequisites are preserved across resumes
- Hard guard-rail before `publisher.publier()` re-checks prerequisites even if `_validation_publication` was somehow bypassed
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
- `get_conn()` has pre-ping: checks connection liveness before returning it from pool
- Stale connections are automatically replaced; if all connections are dead, pool is reset via `_reset_pool()`
- Pool uses TCP keepalives (`keepalives_idle=30`) to detect dead connections early
- `_ping_connection()` runs `SELECT 1` + rollback to test without side effects

### When modifying planificateur.py
- Variable season length via `nb_episodes` parameter (default 10)
- Plan coherence validation: episode type checks, ambiance variety warnings
- `planifier_saison()` accepts `preferences_producteur` param — injected into user prompt
- Plan JSON may contain `instructions_producteur` list (A5) and `decisions_humaines` list

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

## Human Validation Audit Improvements (Session 2)
Complete audit of 3→5 validation points (overall score: 5/10 → improved):
- P1/T1 CRITICAL: Fixed `--auto` flag in `produire-saison` and `batch` (was `default=True`, making validation dead code)
- S1/S2: Reviewer re-evaluation after human corrections; rapport updated with new score
- S3: Structure validation (`_valider_structure()`) on manual JSON reload
- S4/S5/S6: Script recap panel with score, word count vs target, duration vs target, correction counter with cost warnings
- P2: Guided regeneration option (i) with user instructions passed to LLM
- P4/P5: Enriched plan display with full episode details and cost estimates
- M1/M2/M5: Enriched montage validation with duration comparison, chapters, file size, remontage loop
- M3: Warning when montage validation is skipped (no preview file)
- T2/M4: New metadata validation step (`_validation_metadonnees`) before publication
- T3: Decision logging in `rapport["decisions_humaines"]` across all validation points
- T4: New publication confirmation step (`_validation_publication`) before RSS feed update
- FIX: `if rapport:` → `if rapport is not None:` (empty dicts are falsy in Python)
- `_validation_script` return type changed from `dict` to `tuple[dict, float]`

## Feedback Memory System (Session 3)
Complete audit of feedback→memory→future-use chain (overall: 4/10 → fixed). 7 improvements:
- A1: Producer preferences system (`preferences_producteur.json`) — persistent rules injected into scripteur + planificateur prompts
- A2: Historique enriched with `retours_humains` field — human corrections visible in future episodes' context
- A3: Remontage with script editing (option 'e') — edit pauses/SFX/tons before re-assembly (no longer a no-op)
- A4: Re-review after manual JSON edit — Reviewer auto-re-evaluates after manual script modification
- A5: Producer instructions stored in plan JSON (`instructions_producteur` list) for future reference
- A6: Auto-memorization of corrections — after script validation, user can promote corrections to permanent preferences
- A7: Metadata regeneration with free-text feedback (option 'c') — re-calls Metadonnees.generer() with instructions
- Decision logging added to `_validation_plan_saison` (stored in `plan["saison"]["decisions_humaines"]`)

## Dashboard & Validation UX Audit (Session 4)
Comprehensive UX/flat design audit of all 5 validation workflows and the dashboard. Key fixes:

### Dashboard Improvements
- Added `morale` column to episode table (`ajouter_episode_dashboard` accepts `morale` kwarg)
- Added "Retours humains recents" panel — shows last 5 episodes' `retours_humains`
- Added "Preferences producteur" panel — shows rules from `preferences_producteur.json` with source episode
- Wrapped "Saisons planifiees" and "Checkpoints en attente" sections in themed panels
- Title truncation with ellipsis (32 chars + "…") instead of hard cut at 35

### Validation UX Consistency Fixes
- **C1 BUG**: `_validation_metadonnees` error hint listed "v, m, a" but should be "v, c, m, a"
- **C2**: Added `panel_info` summary at top of `_validation_plan_saison` loop (was the only validation without one)
- **M1**: Full `panel_info` re-display after modifications in `_validation_metadonnees` (was partial — only title/description)
- **M2/M3**: Normalized manual edit prompt in `_validation_metadonnees` to match standard pattern
- **M4/M5**: Standardized error messages: "Erreur au rechargement" + "Les donnees precedentes sont conservees." across all 5 functions
- **M6**: Added structure validation (`titre`, `description_courte` required) on metadonnees JSON reload
- **M7**: Standardized confirmation messages with `Palette.SUCCES` colors and trailing periods
- **m5**: Added Icons to `panel_info` titles: `Icons.SCRIPT` for script recap, `Icons.SAISON` for plan previsionnel
- Extracted `_afficher_recap_metadonnees()` helper for DRY re-display after modifications
- Replaced all raw `[green]` tags with `Palette.SUCCES` in validation flows and `initialiser_db()`

### UX Pattern Standards (for future validation functions)
- Error on reload: `"[red]  Erreur au rechargement : {e}[/red]"`
- Preservation: `"[yellow]  Les donnees precedentes sont conservees.[/yellow]"`
- Confirmation: `f"[{Palette.SUCCES}]  [Thing] valide(es) par le producteur.[/]"`
- Manual edit prompt: `[yellow]  Modifiez le fichier...` → `[bold]{path}[/bold]` → `[cyan]  Appuyez sur Entree...[/cyan]`
- All `panel_info` titles include relevant Icon
- All validation menus use `panel_validation()` with consistent key patterns

## Workflow UX Separation (Session 5)
Clear visual separation between single-episode and season production workflows:

### Two distinct visual identities
- **Épisode unique**: `panel_episode()` — Ocre border, "studio de production" subtitle
- **Production sérielle**: `panel_episode_saison()` — Bleu Ciel border, "production sérielle" subtitle, shows season theme + progress bar

### New theme components
- `panel_episode_saison()`: Season-aware episode header with progress bar and theme display
- `panel_roadmap(etape_courante, dry_run)`: Visual roadmap of 8 pipeline steps with current position
- `panel_separateur_episode(episode_courant, total_episodes, ...)`: Styled separator between episodes in serial production

### Pipeline changes
- `pipeline()` accepts `episode_courant`, `total_episodes`, `saison_theme` for season display context
- `_pipeline_inner()` shows `panel_episode_saison` when `total_episodes > 0`, else `panel_episode`
- Roadmap displayed after header in all modes (shows dry-run skips)
- `produire-saison` and `batch` use `panel_separateur_episode` instead of raw `====` separators

### Interactif mode redesign
- Detects existing season plans via `config.liste_saisons()`
- If seasons exist: offers choice between "Saison" (s) and "Épisode unique" (e) workflows
- Season mode: shows episode list with produced/remaining status, offers "all remaining" or "pick one"
- Episode unique mode: classic parameter input with styled prompts
- Split into `_interactif_saison()` and `_interactif_episode_unique()` helpers

### Publication safety invariant (Session 5 fix)
- `_validation_publication()` checks `validation_humaine` flags on script AND montage before allowing publish
- Hard guard-rail in pipeline re-checks prerequisites before calling `publisher.publier()`
- Checkpoint resume restores `validation_humaine` flags from saved rapport

### Validation UX improvements (Session 5 continued)
- **Audio preview auto-open**: `ouvrir_fichier()` opens preview in system player at montage validation
- **Cover art auto-open**: Opens PNG in system viewer at metadata validation
- **Re-listen/re-view options**: (l) to re-listen audio, (o) to reopen cover art without leaving validation
- **Checklists**: Each validation step shows explicit checklist of what to verify before validating
- **Publication recap**: Shows green checkmarks for completed prerequisites (script ✓, montage ✓, metadata ✓)
- `ouvrir_fichier()` in `utils.py`: cross-platform (macOS `open`, Linux `xdg-open`, Windows `start`)

### When modifying validation functions (Session 5 patterns)
- `_validation_montage()` options: v, l, e, r, a (l=réécouter is new)
- `_validation_metadonnees()` options: v, o, c, m, a (o=ouvrir cover art is new)
- `_validation_montage()` uses `preview_path` variable (Path) initialized before the while loop
- `ouvrir_fichier()` returns bool — always check return value and show fallback message with file path
- Checklists are displayed once before the validation loop (not inside the loop)

## Season Audit Fixes (Session 6)

### Critical fixes
- **pubdate_offset**: Uses `ep["numero"] * 3600` (not loop counter `i`) for stable RSS ordering regardless of production order
- **itunes:type=serial**: RSS channel declares `<itunes:type>serial</itunes:type>` so apps display episodes in chronological order
- **Empty theme validation**: `planifier-saison` rejects empty/whitespace themes with SystemExit(1)

### High-priority fixes
- **Buzzsprout retry**: Upload retries up to 4 times with exponential backoff (2s, 4s, 8s, 16s) on network failures
- **RSS file locking**: `_mettre_a_jour_rss()` uses `fichier_lock(feed_path)` to prevent concurrent RSS corruption
- **Episode skip on error**: Both production loops (interactif + CLI) offer (c)ontinue/(a)rrêter when an episode fails mid-season
- **Episode type validation**: LLM-generated types validated against `{"ouverture", "standard", "mi-saison", "final", "bonus"}`, invalid types auto-corrected to "standard"
- **Episode numbering validation**: Auto-renumbers episodes if LLM returns non-sequential numbers

### UX improvements
- **Season completion table**: Rich Table with per-episode status (OK/Ignoré/Échec), details, and summary counts

### Publisher patterns
- `publisher.py` now imports `time` (for retry sleep) and `fichier_lock` from utils
- `_mettre_a_jour_rss()` delegates to `_ecrire_rss()` under lock
- `_upload_buzzsprout()` has retry loop — mock `time.sleep` in tests

## Web Dashboard (Session 7)

### Episode Deletion
- `POST /api/episode/<episode_id>/delete` — soft-delete + file archival
- Files moved to `output/archive/<episode_id>/` (not deleted — recoverable)
- DB: soft-delete on `episodes` table, removes from `historique_episodes`, marks `productions` as deleted
- Audit trail logged in `audit_log` table with reason
- Frontend: two-step confirmation in validation page (click delete → confirm zone with reason input)

### Mobile Responsive Design
- Breakpoints: 768px (tablet), 600px (phone), 480px (small phone)
- `.hide-mobile` class hides elements at ≤768px
- Navigation tabs: compact padding, scrollable, no scrollbar, min-height 44px (touch target)
- Dashboard episode table: audio, durée, date columns hidden on mobile; type + checkmark hidden on small phones
- Validation episode list: type, audio, script, montage columns hidden on mobile — only ID, titre, action button shown
- All `.btn` elements have `min-height: 44px` on mobile for touch targets
- Form inputs use `font-size: 1rem` on mobile to prevent iOS zoom on focus
- Validation action buttons stack vertically on mobile (`.val-actions-grid` → `flex-direction: column`)

## Persistent Storage (Replit Object Storage)

### Architecture
- `persistent_storage.py`: Abstraction over Replit Object Storage SDK
- Lazy client initialization — no-op when Object Storage is unavailable (dev local, tests)
- Three storage prefixes: `audio/`, `scripts/`, `rapports/`

### Upload (automatic after production)
- **Audio**: `upload_episode_audio()` after montage (both HQ and preview MP3)
- **Script**: `upload_script()` after script validation
- **Rapport**: `upload_rapport()` after rapport final save
- Storage keys stored in `rapport["etapes"]["montage"]["object_storage"]` and `rapport["etapes"]["script"]["object_storage"]`

### Restore (automatic on access)
- **`web.py` `/audio/episodes/<file>`**: If local file missing, downloads from Object Storage transparently
- **`web.py` `/api/episode/<id>`**: Restores script from Object Storage before DB fallback
- **`dashboard_data.py` `trouver_fichier_audio()`**: Step 4 restores audio from Object Storage
- **`dashboard_data.py` `charger_rapport()`**: Restores rapport JSON from Object Storage

### Patterns
- All `persistent_storage` imports are inside try/except blocks — never breaks the pipeline
- `is_available()` caches availability check (lazy singleton)
- `restore_*()` functions check local file first, download only if missing
- `upload_file()` returns bool — caller logs warning on failure but continues

## Season Production Pipeline Audit Fixes (Session 8)

### Production Blockers (PostgreSQL + Gunicorn)
- **PostgreSQL pre-ping**: `_ping_connection()` tests connection liveness before returning from pool; stale connections auto-replaced
- **Pool reset**: `_reset_pool()` recreates entire pool when all connections are dead
- **TCP keepalives**: `keepalives_idle=30` on pool creation to detect dead connections early
- **Gunicorn gthread**: 2 workers × 4 threads = 8 concurrent requests; 1800s timeout for long production runs
- **post_fork hook**: Resets psycopg2 pool after fork (not fork-safe)

### Web Dashboard Fixes
- **W1**: Job result TTL caching — jobs kept 60s after read (was deleted on first poll, causing race conditions)
- **W4**: Delete route uses `_archiver()` helper that logs failures instead of silent `except: pass`
- **W7**: Deleted episode guard returns 410 Gone before validation (`_is_episode_deleted()` check)
- **W16**: Montage validation button disabled in frontend when no audio exists (prevents impossible validation)

### Pipeline Fixes
- **M5**: Forced montage validation option when no preview file exists (was permanently blocking publication)
- **M9**: Checkpoint saved after remontage loop (was losing remontage work on crash)
- **Reviewer type field**: Scripteur now injects `type` into generated script JSON so reviewer uses correct adaptive thresholds (was always falling back to "standard" seuil=7)
- **Planificateur episode count**: Validates generated episode count matches `nb_episodes` parameter; truncates excess, errors on deficit
- **Scripteur arc injection**: First episode of season gets character arc starting states injected into prompt (was missing emotional context for opening episode)

## Creative Quality Audit (Session 9)
10 improvements to audio quality and scriptwriting, plus season jingle preview system.

### Audio Production Improvements
- **Tone → voice_settings mapping**: `TONE_VOICE_ADJUSTMENTS` in `producteur_audio.py` — 17 tones dynamically adjust ElevenLabs stability/similarity/style per segment. Applied additively to base character settings, clamped to [0.0, 1.0].
- **Crossfade 100ms**: `CROSSFADE_VOIX_MS = 100` (was 50) in `monteur.py` for smoother voice transitions.
- **Act transitions**: `_charger_transition()` generates/loads a 2s chime sound inserted every 8+ segments when narrateur starts a new section. Asset cached at `assets/music/transition_acte.mp3`.
- **Micro-respirations**: 35% probability of 80ms silence between different speakers (`RESPIRATION_PROBABILITE`, `RESPIRATION_DUREE_MS`). Tests must patch `agents.monteur.random.random` to disable.
- **Narrateur effect**: `_appliquer_effet_narrateur()` applies -3dB gain + fade in/out to distinguish narrator voice from characters.
- **Rhythm variation**: Segments can have `"rythme": "rapide|normal|lent"` — monteur multiplies pause by 0.6/1.0/1.5.
- **Signature jingle**: `_charger_signature()` loads/generates a 5s recurring jingle that bookends every episode. Asset cached at `assets/music/signature_jingle.mp3`.
- **Dynamic ambiance per act**: `ambiance_par_acte` field in episode JSON (list of ambiance names). `_mixer_ambiance_dynamique()` splits audio into equal sections with 2s crossfade between ambiances.

### Script Quality Improvements
- **SFX in English**: Scripteur prompt now requires SFX descriptions in English for better ElevenLabs generation. Minimum 5 SFX per episode.
- **Tics de langage verification**: `Scripteur._verifier_tics_de_langage()` post-validates that each character uses ≥2 of their signature phrases. Emits warning if insufficient.
- **Prompt enhancements**: JSON format now includes `rythme` field and `ambiance_par_acte` field.

### Season Jingle Preview System
- **`_previsualiser_ambiances_saison()`** in `main.py`: Called after plan validation in `planifier-saison` (skipped in `--auto` mode).
- **Flow**: For each jingle (intro_saison, outro_saison): listen (e), validate (v), regenerate via ElevenLabs (g), or replace with custom file (f).
- **Custom files**: Copied to `assets/music/saison_XX_intro_saison.mp3`, path stored in `plan["saison"]["jingles_custom"]`.
- **`config.jingles_saison(numero)`**: Reads custom jingle paths from season plan JSON.
- **Monteur priority**: `_charger_jingle()` now accepts `numero_saison` parameter. Priority order: (0) season custom jingle → (1) JINGLES_PAR_TYPE → (2) AUDIO_ASSETS → (3) auto-gen → (4) silence.
- **Decision logging**: Jingle choices logged in `plan["saison"]["decisions_humaines"]` with action `ambiances_saison_validees`.

### When modifying monteur.py (Session 9 additions)
- `_assembler_segments()` now takes optional `transition: AudioSegment` parameter — pass `None` to disable act transitions
- `_assembler_segments()` uses `random.random()` for micro-respirations — mock `agents.monteur.random.random` in tests for determinism
- `_charger_jingle()` now takes optional `numero_saison: int` — when provided, checks `config.jingles_saison()` first
- `_assembler_final()` wraps episode with signature jingle on both ends
- `_mixer_ambiance_dynamique()` splits voix into equal sections per ambiance with 2s crossfade
- Segment `rythme` field ("rapide"/"normal"/"lent") modulates pause duration in `_assembler_segments()`

### When modifying monteur.py (Session 10 — Audio Immersion)
- `_appliquer_effet_narrateur()` has been REMOVED — no more narrateur-specific audio effect
- `_generer_micro_respiration()` now generates noise (numpy) instead of silence for natural feel
- `_appliquer_ducking()` new static method — side-chain ducking attenuates voice during SFX overlay
- `_charger_room_tone()` new method — loads/generates continuous room ambiance (fireplace, clock)
- `_appliquer_master_bus()` new static method — soft compression + limiter before LUFS normalization
- `CROSSFADE_VOIX_MS = 200` (was 100) — smoother voice transitions
- `DUCKING_GAIN_DB = -6`, `DUCKING_FADE_MS = 150` — ducking parameters
- `SFX_VOLUME_PAR_TON` dict — contextual SFX volume based on previous segment's `ton` field
- `ROOM_TONE_DB = -28` — very quiet room tone volume
- `ROOM_TONE_PROMPTS` dict — 4 variants: defaut, soir, jour, orage
- `AMBIANCE_ROOM_TONE` dict — maps ambiance name to room tone variant
- `_charger_room_tone(ambiance)` accepts ambiance param for adaptive room tone
- `EQ_VOICE_BOOST_*` constants — 2-5 kHz boost at +2.5 dB via scipy bandpass filter
- `TRUE_PEAK_OVERSAMPLE = 4` — 4x oversampling for inter-sample peak detection via scipy
- Master bus now has 3 stages: EQ boost → compression → true peak limiter (with scipy fallback)
- Act transitions now trigger on `papy_babou` after 8+ segments (was `narrateur`)
- Chapter generation also triggers on `papy_babou` (was `narrateur`)
- Room tone is overlaid on the full voice+fond track before assembler_final
- Master bus runs after assembler_final, before LUFS normalization

### When modifying config.py (Session 9-10 additions)
- `jingles_saison(numero)` reads `plan["saison"]["jingles_custom"]` from season JSON — returns dict of `{key: Path}` for existing files only
- `musique_fond_db: -15` (was -20) — background music more present
- `STEREO_PAN`: antoine=-0.4, noemie=0.4, mamie_sonia=0.5 (was -0.3/0.3/0.2) — wider stereo image

## Deployment (Gunicorn)
- `gunicorn.conf.py`: gthread workers (2 workers × 4 threads = 8 concurrent requests)
- Timeout: 1800s (30min) because production subprocesses block the thread during `proc.communicate()`
- `post_fork` hook: resets PostgreSQL pool after fork (psycopg2 pool is not fork-safe)
- `.replit` uses `gunicorn -c gunicorn.conf.py web:app` (not `python web.py`)
- Env vars: `GUNICORN_WORKERS`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`, `GUNICORN_LOG_LEVEL`

## Full Pipeline Audit Improvements (Session 11)
Comprehensive audit of the entire production pipeline: season preparation, episode production, next episode continuity, full season production, and S2 preparation.

### Arc State Final Tracking (CRITICAL)
- After each episode production, `arc_state_final` is extracted and saved to `{episode_id}_arc_state.json`
- Contains: `moments_cles`, `questions_ouvertes`, `evolutions_personnages`, `fil_rouge`, `ambiance`
- Automatically loaded and injected into scripteur prompt for episode N+1
- Scripteur `generer()` accepts `arc_state_precedent` parameter
- `_construire_user_prompt()` injects arc state with "continuité obligatoire" directive
- Pipeline loads arc state from `config.SCRIPTS_DIR / f"{ep_prec_id}_arc_state.json"`

### Season Archive System (CRITICAL)
- `Planificateur.generer_archive_saison(plan, historique)` generates comprehensive archive after final episode
- Archive includes: arcs finaux, questions ouvertes non résolues, moments clés, évolutions personnages, fil rouge
- Saved to `config.ARCHIVES_DIR / f"archive_saison_{saison:02d}.json"`
- Auto-triggered in `_pipeline_inner()` when `numero == dernier_ep` of season
- `planifier_saison()` accepts `archives_saisons` parameter for inter-season continuity
- Archives loaded in `planifier_saison` CLI command and passed to planificateur

### Post-Generation Validation (CRITICAL)
- **Biblical ratio**: `Reviewer.verifier_ratio_biblique()` — counts Papy mots / total mots, alerts if < 60%
- **Papy/enfants ratio**: `Reviewer.verifier_ratio_papy_enfants()` — enfants should be 25-45% of segments
- **Teasing validation**: `Reviewer.verifier_teasing()` — detects meta-language ("prochain épisode", "abonnez-vous")
- **Pause validation**: `Reviewer.verifier_pauses()` — detects >3s pauses (max 3/episode) and 0ms pauses
- All validations run in pipeline after script review, results stored in `rapport["metriques"]` and `rapport["alertes_post_generation"]`

### Publisher Safety
- `Publisher.publier()` verifies audio file exists before upload — raises `FileNotFoundError` if missing
- Check happens before any upload/RSS operation

### Planificateur Enhancements
- `Planificateur.integrer_evenements_speciaux(plan)` — reads `config.EVENEMENTS_SPECIAUX` and enriches episodes with `evenement_special` field
- Called automatically after plan generation in `planifier_saison` CLI command
- Season archive injection into planning prompt with questions ouvertes and moments clés

### Metadonnees Enrichment
- `source_biblique` field added from `episode.get("histoire_biblique")`
- `ambiance` field added from `episode.get("ambiance")`

### Scripteur Enhancements
- `ambiance_par_acte` changed from "optionnel" to "FORTEMENT RECOMMANDÉ" in prompt
- Arc state precedent injection in user prompt for N→N+1 continuity

### Historique Enrichment
- `ratio_biblique` and `ratio_enfants` metrics added to historique entries
- `elements_fil_rouge` field added for season tracking

### Config Additions
- `RATIO_BIBLIQUE_MINIMUM = 0.60` — minimum Papy content ratio
- `RATIO_ENFANTS_MIN = 0.25` — minimum children intervention ratio
- `RATIO_ENFANTS_MAX = 0.45` — maximum children intervention ratio
- `MAX_PAUSES_EXCESSIVES = 3` — max pauses >3s per episode
- `ARCHIVES_DIR = HISTORIQUE_DIR / "archives"` — season archives storage

### When modifying reviewer.py (Session 11 additions)
- `verifier_teasing(script)` checks last 5 non-SFX segments for meta-language
- `verifier_ratio_biblique(script)` returns `tuple[float, list[str]]` — (ratio, alertes)
- `verifier_ratio_papy_enfants(script)` returns `tuple[float, list[str]]` — (ratio_enfants, alertes)
- `verifier_pauses(script)` returns `list[str]` — alerts for excessive/missing pauses

### When modifying planificateur.py (Session 11 additions)
- `generer_archive_saison(plan, historique)` is a `@staticmethod` — returns dict
- `integrer_evenements_speciaux(plan)` is a `@staticmethod` — mutates and returns plan
- `planifier_saison()` accepts optional `archives_saisons: list[dict]` for inter-season context
- Archive rituels injection: when archives have `rituels`, a "ÉVOLUTION DES RITUELS" directive is added to prompt
- Character ages injected via `config.age_personnage(key, numero_saison)` in bible section of prompt

### When modifying config.py (Session 12 additions)
- `age_personnage(personnage_id, saison)` returns age for a specific season
- Uses `age_par_saison` dict if defined, extrapolates (+1 every 2 seasons) otherwise
- Returns `None` for unknown characters

### When modifying main.py (Session 11 additions)
- Arc state saved after `ajouter_historique()` in `_pipeline_inner()`
- Season archive generated when `numero == dernier_ep` of season
- `planifier_saison` CLI loads archives from `config.ARCHIVES_DIR` and passes to planificateur
- Post-generation validations (ratio biblique, ratio enfants, teasing, pauses) run after script review
- Metrics stored in `rapport.setdefault("metriques", {})`

## Final Audit Fixes (Session 12)
Three residual issues from the re-audit (9.9/10 → 10/10):

### Character Age Auto-Resolution
- `config.age_personnage(personnage_id, saison)` centralizes age resolution
- Uses `age_par_saison` from personnages.json when available
- Extrapolates missing seasons: `age_base + (saison - 1) // 2` (1 year per 2 seasons)
- Injected into both planificateur and scripteur prompts

### Rituels Evolution Directive
- When `archives_saisons` contain `rituels`, the planificateur prompt now includes an explicit directive:
  "ÉVOLUTION DES RITUELS : la nouvelle saison DOIT faire évoluer les rituels existants"
- Previous season's rituels are listed for reference
- Prevents ritual stagnation across seasons

### Scripteur Age Integration
- `_construire_bible_personnages()` now uses `config.age_personnage()` instead of manual dict lookup
- Ensures consistent age resolution with extrapolation support

### Tests (Session 12)
- 9 new tests: TestAgePersonnage (5), TestPlanificateurAgeInjection (1), TestPlanificateurRituelsEvolution (2), TestScripteurAgePersonnage (1)
- Total: 33 tests in test_phase2_improvements.py
- Full suite: 519 passed, 3 pre-existing flaky (TestHistorique), 3 skipped (ffmpeg)

## Pre-Launch Audit Fixes (Session 13)
Comprehensive 8-agent audit followed by full implementation of all fixes before production launch.

### Character Bible Completeness
- Antoine: added `vocabulaire_typique`, `interdictions`, `backstory`, `famille`, `relation_avec_mamie_sonia`, `anecdotes_possibles`; fixed `annee_naissance` 2015→2016, `age_par_saison` S3 9→10
- Noémie: added same enrichment fields; fixed `annee_naissance` 2018→2019
- Papy Babou: added `relation_avec_antoine`, `relation_avec_noemie`, `relation_avec_mamie_sonia`
- Mamie Sonia: added `relation_avec_antoine`, `relation_avec_noemie`
- Added `_meta` block with `annee_reference: 2024`

### Audio Config Fixes
- `STEREO_PAN["mamie_sonia"]`: 0.5 → 0.3 (less extreme panning)
- `VOICE_SETTINGS["mamie_sonia"]["style"]`: 0.15 → 0.25 (more expressive)
- Added `EVENEMENTS_SPECIAUX[(1, 10)]` for Lucas birth event

### Scripteur Fixes
- SFX minimum threshold: 5 → 8 (recommended range 8-12)
- Mots interdits: substring match → word boundary regex (`\b` pattern) to avoid false positives (e.g. "mort" no longer matches "immortel")

### Reviewer Fixes
- `evaluer()` accepts `max_retry: int = 3` parameter for configurable JSON retry

### Security Fixes
- `web.py`: Secret key from `FLASK_SECRET_KEY` env var with warning on default
- `web.py`: `_JOB_RESULT_TTL = 60` — keep job results 60s after read (prevents race conditions)
- `dashboard.html`: `encodeURIComponent(saison)` in `goToSuivi()` to prevent XSS

### Infrastructure Fixes
- `utils.py`: Windows `ouvrir_fichier()` uses `os.startfile()` instead of `shell=True` Popen
- `main.py`: `_production_id_courante` replaced with `threading.local()` for Gunicorn thread safety
- `main.py`: Historique JSON UPSERT — deduplicates by `episode_id` before appending

### Tests (Session 13)
- 18 new tests: TestPersonnagesBibleCompletude (5), TestConfigAuditFixes (3), TestScripteurSFXSeuil (1), TestScripteurMotsInterditsRegex (2), TestReviewerMaxRetry (1), TestThreadingLocal (1), TestHistoriqueUpsert (1), TestWebSecurityFixes (2), TestXSSProtection (1), TestUtilsWindowsFix (1)
- Total: 51 tests in test_phase2_improvements.py
- Full suite: 537 passed, 3 pre-existing flaky (TestHistorique), 3 skipped (ffmpeg)

## Git Workflow
- Branch: `claude/fix-postgres-gunicorn-SV32c`
- Push: `git push -u origin claude/fix-postgres-gunicorn-SV32c`
- Retry on network failure: 4 times with exponential backoff (2s, 4s, 8s, 16s)

## One Topic Per Episode Rule (Session 14)
**ABSOLUTE RULE**: Each episode must cover ONE biblical story completely, from A to Z.

### Problem solved
The planificateur was generating multi-part episodes (e.g., 3 episodes on Abraham, 3 on Jacob), reducing topic variety in a season.

### Implementation
- **Rule 11** added to `SYSTEM_PROMPT` in `planificateur.py`: explicit prohibition of multi-part episodes with good/bad examples
- **JSON template** reinforced: `histoire_biblique` and `resume` fields emphasize uniqueness and completeness
- **Hard validation** in `_valider_plan()`: rejects plans with duplicate biblical stories (exact match AND same-subject detection by dominant biblical character)
- **Producer preferences** stored in `data/preferences_producteur.json`: two rules about one topic per episode and maximum topic variety
- The season's narrative arc comes from the RECURRING CHARACTERS (Papy, Antoine, Noémie) and the season THEME, not from repeating the same biblical subject

### Validation Page Stale Data Fix (Session 14)
- **Bug 1**: When producing via web dashboard with `--stop-after script`, `ajouter_historique()` was never called because it runs at the end of the full pipeline. The validation page reads from historique, so it showed old episode data.
- **Fix**: `ajouter_historique(rapport, script)` now called in both `stop_after == "script"` and `stop_after == "montage"` blocks in `_pipeline_inner()`. The UPSERT logic handles duplicates.
- **Pattern**: Any new `stop_after` block must also call `ajouter_historique()` before returning.

- **Bug 2**: `charger_rapport()` in `dashboard_data.py` prioritized `completed` productions over recent ones. When re-producing an episode (e.g., after regenerating a season plan), the OLD completed production was returned instead of the NEW waiting_script one.
- **Fix**: Single query `ORDER BY created_at DESC LIMIT 1` regardless of status — always returns the most recent production.

- **Bug 3**: `api_prochain_episode()` and `api_produire_saison()` in `web.py` read rapports from filesystem only (`config.LOGS_DIR`), missing data after Replit redeploys when files are lost but DB has the data.
- **Fix**: Both routes now use `dashboard_data_mod.charger_rapport()` which checks DB → filesystem → Object Storage.

### When modifying dashboard_data.py (Session 14)
- `charger_rapport()` returns the MOST RECENT production's rapport, not the most recent completed one
- Never prioritize `completed` status over recency — a new `waiting_script` production must supersede an old `completed` one

### When modifying web.py (Session 14)
- Always use `dashboard_data_mod.charger_rapport()` instead of reading rapport files directly from `config.LOGS_DIR`
- This ensures DB + filesystem + Object Storage fallback chain is used consistently

### Web Dashboard DB Resilience (Session 14)
After Replit redeploy, local files are lost but PostgreSQL data survives. All rapport reads/writes in web.py now go through DB first:
- **`_sync_rapport_to_db()`**: New helper in web.py that updates the most recent production's rapport_json in DB. Called after every validation action.
- **Validate/Regenerate/Publication routes**: Load rapport via `dashboard_data_mod.charger_rapport()` (DB → file → Object Storage), save to both file AND DB.
- **`config._db_disponible()`**: Neon scale-to-zero retry (1 retry after 1s) for cold starts.
- **Pattern**: Never read rapports from `config.LOGS_DIR` directly in web.py — always use `dashboard_data_mod.charger_rapport()`.

### When modifying planificateur.py (Session 14 additions)
- `_valider_plan()` now raises `ValueError` (not just warning) on duplicate `histoire_biblique`
- Subject-similarity detection extracts dominant biblical character name from each `histoire_biblique` and rejects if same character appears in multiple episodes
- Uses `collections.Counter` for subject frequency analysis

## Episode Workflow Audit (Session 15)
Comprehensive 6-agent audit of the entire episode creation workflow. 14 fixes (2 CRITICAL, 1 HIGH, 11 MEDIUM).

### CRITICAL fixes
- **Prompt import**: `from rich.prompt import Prompt` was missing — `Prompt.ask()` in M5 forced montage validation would crash with `NameError`
- **Plan validation dead code**: `plan.get("episodes", [])` always returned `[]` — must be `plan.get("saison", {}).get("episodes", [])`. Episode type validation and auto-renumbering in `planifier-saison` were completely non-functional

### HIGH fix
- **Montage re-validation on resume**: Montage validation block had no `etape_idx` guard — on checkpoint resume at step 5+, montage was re-prompted even though already validated. Fixed by checking `rapport["etapes"]["montage"]["validation_humaine"]`

### MEDIUM fixes
- **max_tokens adaptatif**: Was flat 16384/12000 — now graduated: final=16384, ouverture/mi-saison=12288, standard=10240, bonus=8192
- **relation_avec_mamie_sonia**: Missing from scripteur's relations loop — Papy's key relationship never reached the LLM prompt
- **import re in loop**: reviewer.py had `import re` inside a for loop — moved to module level
- **generer_dry_run() incomplete**: Missing `source_biblique` and `ambiance` fields (present in `generer()`)
- **Chapter timestamp offset**: Missing signature jingle duration (~5s) — all chapter markers were shifted
- **Room tone fallback order**: Generic file was checked before variant, preventing variant auto-generation
- **Character counter timing**: Incremented before TTS success — inflated cost tracking on failure
- **reset_compteur thread safety**: `.clear()` not protected by `_compteur_lock`
- **Batch error handling**: No continue/stop prompt on error (inconsistent with `produire-saison`)

### When modifying main.py (Session 15 patterns)
- Plan episode access: always use `plan.get("saison", {}).get("episodes", [])`, never `plan.get("episodes", [])`
- Montage validation guard: check `not montage_deja_valide` before prompting (prevents re-validation on resume)
- `Prompt` import from `rich.prompt` is required for `Prompt.ask()` calls

### When modifying scripteur.py (Session 15)
- `max_tokens` uses a graduated dict by episode type (not flat value)
- Relations loop includes `relation_avec_mamie_sonia`

### Tests (Session 15)
- Full suite: 541 passed, 3 skipped (ffmpeg), 3 pre-existing flaky (TestHistorique)
