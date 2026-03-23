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
│   └── test_corrections.py  # Bug regression tests (30 tests)
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
- **Episode Types**: `ouverture` (15min/1600 words), `standard` (13min/1400), `mi-saison` (15/1600), `final` (18/1900), `bonus` (10/1000)
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

**Expected**: 378 passed, 3 skipped (integration tests requiring ffmpeg)

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

## Audit Episode System (Session 7)

### Agents d'audit qualité pré-production
5 agents spécialisés dans `.claude/agents/` pour l'audit qualité des scripts d'épisode. Source originale : branche `claude/episode-2-script-QbSiY`.

Si les agents ne sont pas sur la branche courante, les récupérer avec :
```bash
git fetch origin claude/episode-2-script-QbSiY && git checkout origin/claude/episode-2-script-QbSiY -- papy-babou-podcast/.claude/agents/audit-episode.md papy-babou-podcast/.claude/agents/audit-sfx.md papy-babou-podcast/.claude/agents/audit-voix.md papy-babou-podcast/.claude/agents/audit-marc.md papy-babou-podcast/.claude/agents/audit-claire.md
```

**IMPORTANT** : Ces agents sont dans `papy-babou-podcast/.claude/agents/`, pas à la racine du repo. Pour que Claude Code les détecte comme `subagent_type`, il faut lancer Claude depuis `papy-babou-podcast/` (i.e. `cd papy-babou-podcast && claude`).

### Orchestrateur : `audit-episode`
Coordonne 4 audits spécialisés en 4 phases :

| Phase | Agents | Mode |
|-------|--------|------|
| 1. Techniques | `@audit-sfx` (Thomas Lavigne) + `@audit-voix` (Isabelle Fontaine) | PARALLÈLE |
| 2. Créatifs | `@audit-marc` (Marc Delacroix) + `@audit-claire` (Claire Moreau) | PARALLÈLE |
| 3. Consolidation | Orchestrateur | Tableau croisé, convergences, plan d'action P0-P3 |
| 4. Corrections | Orchestrateur | Application P0+P1 automatiques, P2/P3 pour décision humaine |

### Les 4 auditeurs

| Agent | Fichier | Rôle | Axes | Personas | Cible |
|-------|---------|------|------|----------|-------|
| **Thomas Lavigne** | `audit-sfx.md` | Sound designer | 10 règles conformité + B1-B5 créatif (couverture, densité, transitions, émotion, prompts) | — | 9/10 |
| **Isabelle Fontaine** | `audit-voix.md` | Directrice vocale | 6 règles TTS + B1-B5 créatif (tons, rythme, naturalité enfants, arc émotionnel, dynamique) | — | 9/10 |
| **Marc Delacroix** | `audit-marc.md` | Directeur créatif #1 France | 5 axes (immersion, rythme, émotion, éducatif, production IA) | Lina 7ans (30%), Noah 10ans (30%), Sophie parent catho (40%) | 9/10 |
| **Claire Moreau** | `audit-claire.md` | Concurrente directe (podcast Tina) | 6 axes (accroche, pacing, authenticité, immersion, éducatif, viralité) | Timéo 9ans accro YouTube (50%), Camille parent non-pratiquante (50%) | 9/10 |

### Seuil qualité
- **9/10 minimum** sur TOUTES les dimensions clés
- Un épisode à 9/10 = "l'enfant dit 'remets l'épisode', le parent recommande à ses amis"
- Les 7 critères du 9/10 : réécoute, raconte l'histoire, parent recommande, son transporte, voix vivantes, 3 émotions minimum, on apprend quelque chose

### Fichiers de sortie
- Rapports individuels : `output/scripts/[EPISODE_ID]_audit_sfx.md`, `_audit_voix.md`, `_audit_marc.md`, `_audit_claire.md`
- Rapport consolidé : `output/scripts/[EPISODE_ID]_audit_complet.md`

### Verdicts
- **`feu_vert`** : moyenne >= 9.0 ET audience >= 8.5 ET 0 axe < 8.0
- **`ajustements_mineurs`** : moyenne >= 8.0 ET audience >= 7.5 ET 0 axe < 7.0
- **`retravailler`** : moyenne < 8.0 OU un axe < 7.0 OU audience < 7.5

## Rédaction de Script — Bonnes Pratiques (Session 8)

### Gestion des timeouts lors de la rédaction
Les scripts d'épisode sont longs (20+ segments). La génération/édition d'un script complet en une seule passe provoque systématiquement des timeouts.

**Stratégie anti-timeout pour la rédaction :**
1. **Ne JAMAIS réécrire tout le script d'un coup** — toujours travailler segment par segment ou par petits groupes (3-5 segments max)
2. **Préparer le texte avant l'outil Edit** — rédiger le contenu dans la réponse, puis faire un seul `Edit` ciblé
3. **Découper les modifications en passes successives** :
   - Passe 1 : corrections structurelles (personnages_presents, métadonnées)
   - Passe 2 : réécriture des segments un par un
4. **Pour les gros segments** (>15 lignes de dialogue) : les traiter individuellement
5. **Valider après chaque modification** — ne pas attendre d'avoir tout fait pour vérifier

### Gestion des timeouts lors des audits (`audit-episode`)
Les agents d'audit (audit-sfx, audit-voix, audit-marc, audit-claire) sont lancés en parallèle et lisent chacun le script complet + la bible des personnages. Cela peut provoquer des timeouts sur les phases de consolidation.

**Stratégie anti-timeout pour les audits :**
1. **Phase 1 + 2 en parallèle** : Lancer les 4 agents en parallèle est OK (c'est le design voulu)
2. **Si un agent timeout** : le relancer seul (pas besoin de relancer les 4)
3. **Phase 3 (consolidation)** : Si elle timeout, découper :
   - D'abord synthétiser les rapports techniques (SFX + voix)
   - Puis synthétiser les rapports créatifs (Marc + Claire)
   - Enfin fusionner les deux synthèses
4. **Phase 4 (corrections)** : Appliquer les corrections P0/P1 segment par segment, pas en bloc
5. **Sauvegarder les rapports individuels au fur et à mesure** — ne pas attendre la consolidation

### Suppression du narrateur — Pattern récurrent
Le narrateur (`narrateur`) n'est PAS un personnage et ne doit JAMAIS apparaître dans `personnages_presents`. C'est un artefact du LLM qui le confond avec papy_babou.

**Règle** : Après chaque génération de script, vérifier `personnages_presents` et retirer `"narrateur"` s'il y est. Les segments attribués au narrateur doivent être réattribués à `papy_babou` (le vrai narrateur de l'histoire).

### Réécriture de segments — Qualité 9/10
Pour atteindre le niveau 9/10 exigé par les auditeurs :
- **Naturalité** : Utiliser des interjections naturelles ("Oh", "Hé", "Dis"), des hésitations ("euh"), des questions rhétoriques
- **Interaction** : Les enfants (Marc, Claire) doivent poser des questions, réagir, pas juste écouter
- **Immersion sonore** : Les SFX doivent être intégrés dans le dialogue ("Tu entends ce bruit ?"), pas juste décoratifs
- **Arc émotionnel** : Chaque segment a une émotion dominante — varier sur l'ensemble de l'épisode
- **Rituels** : Respecter les rituels de début (chanson d'intro, "Installez-vous bien") et de fin ("À la semaine prochaine")
- **Tons vocaux** : Varier les `ton` dans les répliques (curieux, émerveillé, mystérieux, tendre, solennel) — jamais le même ton 3 fois de suite

## Git Workflow
- Branch: `claude/podcast-production-system-YkngW`
- Push: `git push -u origin claude/podcast-production-system-YkngW`
- Retry on network failure: 4 times with exponential backoff (2s, 4s, 8s, 16s)
