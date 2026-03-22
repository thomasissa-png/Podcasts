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
│   ├── __init__.py          # Exports all 10 agents
│   ├── scripteur.py         # Script generation (Claude API) — serial-aware
│   ├── reviewer.py          # Script review (Claude API) — type-aware criteria
│   ├── directeur_podcast.py # Creative director + audience personas validation (Claude API)
│   ├── producteur_audio.py  # TTS via ElevenLabs (parallel, per-character voices)
│   ├── sfx_provider.py      # SFX: ElevenLabs → Freesound → silence fallback
│   ├── monteur.py           # Audio assembly: jingles, mixing, LUFS, chapters
│   ├── metadonnees.py       # Metadata generation (Claude API) + transcript
│   ├── publisher.py         # RSS 2.0 feed + iTunes/Podcast Index namespaces
│   ├── cover_art.py         # DALL-E 3 cover art generation (PNG format)
│   └── planificateur.py     # Season planning (Claude API)
├── tests/                   # 577 tests (pytest)
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
├── scripts/episodes/        # Episode scripts (config.SCRIPTS_DIR) — THE canonical location
└── output/                  # Generated audio, segments
```

### Script File Location — ABSOLUTE RULE
- **ALL scripts MUST be in `scripts/episodes/`** (= `config.SCRIPTS_DIR`)
- NEVER create or reference scripts in `output/scripts/` — that directory is NOT used by the pipeline or web routes
- When creating scripts manually (outside pipeline), ALWAYS use `config.SCRIPTS_DIR`
- Checkpoint `script_path` MUST point to `scripts/episodes/S01EXX_script.json`
- This rule has caused 2 production failures — treat any `output/scripts/` script reference as a bug

## Key Concepts

### Serial Production System
- **Season Plans**: Generated via `planifier-saison`, stored as `saisons/saison_XX.json`
- **Episode Types**: `ouverture` (20min/2400 words), `standard` (18min/2100), `mi-saison` (20/2400), `final` (20/2400), `bonus` (15/1800)
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
- Pipeline wrapped in try/except: DB status updated to "failed", partial rapport saved to `{episode_id}_rapport.json` (normal file, NOT `_echec`) + uploaded to Object Storage
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

**Expected**: 577 passed, 3 skipped (integration tests requiring ffmpeg)

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
- **MANDATORY**: When a script is modified (audit corrections, manual edits, regeneration), `validation_humaine` MUST be reset to `false` in BOTH the checkpoint and rapport files. Otherwise the dashboard shows "déjà validé" for the old version and skips re-validation. This applies to ALL script modifications — audit P0/P1 corrections, manual JSON edits, regeneration via pipeline.
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

## Identite Visuelle & Design System

### Illustration de reference
L'identite visuelle est basee sur `assets/artwork/cover_base.png` — illustration style "Quelle Histoire" (ChatGPT). C'est la **reference absolue** pour tout le design.

**Personnages dans l'illustration** :
- **Papy Babou** : chauve, lunettes noires, chemise bleu marine (#3A4E7A), conteur avec livre ouvert, index leve
- **Antoine** : cheveux bruns ebouriffes, t-shirt rouge (#E04040), emerveillement
- **Noemie** : cheveux chatains, queue de cheval, pull jaune moutarde (#E8B040), reveuse
- **Ambiance** : fond bleu cornflower (#5B9BD5), sol beige, doodles blancs style craie (micro, etoiles, livre, dinosaure)

### Cover podcast (`assets/artwork/cover.svg`)
SVG superposant le titre sur le PNG : "Les Histoires de" (blanc) + "Papy Babou" (or #FFD234) + sous-titre, banniere degradee semi-transparente en bas.

### Palette CSS du site (alignee sur illustration)
| Variable | Hex | Role |
|----------|-----|------|
| `--bleu-nuit` | `#5B9BD5` | Theme principal, hero |
| `--bleu-doux` | `#8ECFF5` | Gradients legers |
| `--dore` | `#E8A020` | CTA, boutons, badges |
| `--dore-light` | `#FFD234` | Accents, titres |
| `--antoine-rouge` | `#E04040` | Avatar Antoine |
| `--noemie-rose` | `#E8B040` | Avatar Noemie (jaune moutarde) |
| `--corail` | `#F26B5E` | Alertes, accents |
| `--vert-prairie` | `#5DBD72` | Badges ecoute |
| `--sable` | `#FFF8ED` | Fond de page |

### Favicon — ABSOLUTE RULE (DO NOT CHANGE)
- **The ONLY favicon is `assets/artwork/favicon2.png`** — PNG format, no SVG
- ALL pages (public.html, dashboard.html, admin_login.html) MUST use `favicon2.png`
- NEVER add `favicon.svg`, `favicon_16.svg`, `favicon_32.svg`, or any SVG favicon
- NEVER add a second `<link rel="icon">` tag — only ONE favicon link per page
- Route `/favicon.ico` in `web.py` serves `favicon2.png` — do NOT change this
- This rule has been violated 3+ times — treat any SVG favicon reference as a regression bug

### Typographie web
- Corps : Nunito (sans-serif) — `--font-body`
- Titres : Baloo 2 (display) — `--font-display`

### Agents design
- `.claude/agents/designer.md` — Agent Design (audit, palette, CSS)
- `.claude/agents/ux.md` — Agent UX (parcours, interactions, trust signals)
- `.claude/agents/copywriter.md` — Agent Copywriter (tons, textes)

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
- Nine storage prefixes: `audio/`, `scripts/`, `rapports/`, `saisons/`, `checkpoints/`, `segments/`, `metadonnees/`, `chapters/`, `covers/`

### Upload (automatic after production)
- **Audio HQ/Preview**: `upload_episode_audio()` after montage
- **Script validé**: `upload_script()` after script validation
- **Rapport**: `upload_rapport()` after rapport save (+ error handler + stop_after blocks)
- **Segments voix**: `upload_segments()` after audio TTS production
- **Segments SFX**: `upload_segments()` after SFX generation
- **Checkpoint**: `upload_checkpoint()` after each major step
- **Saison plan**: `upload_saison()` after plan generation/validation
- **Métadonnées**: `upload_metadonnees()` after metadata validation
- **Chapitres**: `upload_chapters()` after montage alongside audio
- **Cover art**: `upload_cover()` after DALL-E generation
- Storage keys stored in `rapport["etapes"][step]["object_storage*"]`

### Restore (automatic on access/resume)
- **Audio**: `dashboard_data.trouver_fichier_audio()` → `restore_episode_audio()`
- **Script**: `main.py` pipeline resume → `restore_script()` + DB fallback (`ScriptRepo`)
- **Rapport**: `dashboard_data.charger_rapport()` → `restore_rapport()`
- **Segments**: `main.py` guard before audio step → `restore_segments()` (+ fallback to audio regeneration)
- **Checkpoint**: `web.py` resume route → `restore_checkpoint()`
- **Saison**: `config.charger_saison()` + `config.liste_saisons()` → `restore_saison()` / `restore_all_saisons()`
- **Métadonnées**: `main.py` pipeline resume at etape > 5 → `restore_metadonnees()`
- **Cover art**: `web.py` `/api/episode/<id>` → `restore_cover()`

### Patterns
- All `persistent_storage` imports are inside try/except blocks — never breaks the pipeline
- `is_available()` caches availability check (lazy singleton)
- `restore_*()` functions check local file first, download only if missing
- `upload_file()` returns bool — caller logs warning on failure but continues
- Pipeline works fully without Object Storage (dev local, tests) — JSON files as fallback

### Segment Fallback (CRITICAL for resume after redeploy)
- Before audio step: if `etape_idx > 2` (checkpoint says SFX/montage/etc.), check if segments exist locally
- If not: try `restore_segments()` from Object Storage
- If still missing (segments were never uploaded — pre-upload-code productions): **fallback to `etape_idx = 2`** to regenerate audio from validated script
- This prevents the "stuck at montage with no segments" infinite loop

### DATABASE_URL Configuration
- Pipeline works WITHOUT PostgreSQL — all DB writes guarded by `_use_db()` which returns False if `DATABASE_URL` env var is empty
- All data persisted to JSON files + Object Storage as fallback
- To enable DB: set `DATABASE_URL` in Replit Secrets (Neon PostgreSQL connection string)
- `initialiser_db()` creates schema only when `DATABASE_URL` is set

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
- `gunicorn.conf.py`: gthread workers (1 worker × 8 threads = 8 concurrent requests)
- IMPORTANT: 1 worker only — `_jobs` dict is in-memory, multiple workers would lose job state
- Timeout: 3900s (65min) — must be > `_TIMEOUT_PRODUIRE` (3600s) + margin
- `graceful_timeout = 60` — gives SIGTERM handler time to save checkpoint
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

## Audio IA Quality Rules (Session 15 — MANDATORY for all episodes)

### SFX Prompts — Rules for AI Sound Generation (ElevenLabs SFX / Stable Audio)

Every SFX prompt MUST describe ONLY reproducible sounds. Apply these filters systematically:

1. **NO visual descriptions**: Remove `light`, `darkness`, `brilliant`, `radiant`, `bioluminescent`, `sunlight`, `warm sunlight`. Replace with sonic equivalents (e.g., `"brilliant explosion of light"` → `"massive orchestral swell rising from silence"`).
2. **NO abstract/emotional concepts**: Remove `divine`, `primordial`, `sacred`, `majestic`, `primal`, `infinite`. Replace with concrete sound descriptors (e.g., `"majestic and primal"` → `"low sub-bass throb with reverb"`).
3. **NO silent events**: Remove `plants growing`, `flowers blooming`, `fish swimming`, `warm embrace`, `baking smell`, `soil rich and damp`, `sky forming`, `dry land emerging`. Replace with audible equivalents (e.g., `"flowers blooming"` → `"wind rustling through dense leaves"`).
4. **NO montage metadata in prompts**: Remove `day transition marker`, `second day transition`, `returning to cozy room`, `gentle return transition`. These are edit instructions, not sounds.
5. **NO human speech risk**: Replace `voices` with `laughing` or `cheering` to prevent AI generating speech that conflicts with TTS.
6. **NO "silence" descriptions**: `"absolute silence"` generates nothing. Replace with `"low sub-bass drone"`, `"dark atmospheric pad"`, etc.
7. **NO conflicting spatial layers**: Don't mix `underwater` + `seagulls` in same prompt.
8. **Use concrete audio vocabulary**: frequencies (sub-bass, high-pitched), instruments (tubular bell, harp, organ), textures (drone, pad, shimmer, swell, reverb), actions (crackling, rustling, clinking, creaking).

### Voice Text — Rules for TTS (ElevenLabs)

1. **NO onomatopoeia**: Remove `Boum`, `Splash`, `Crac`, `Bang`, `Pfff`, `Brrr`, `Grr`. If the sound matters, the SFX handles it.
2. **NO hyphenated syllabification**: `Fir-ma-ment` → `Firmament` with `"rythme": "lent"`. TTS reads hyphens as pauses or literal characters.
3. **NO uncontrolled ellipsis**: `Boum... boum...` → rewrite without `...` or accept unpredictable TTS pausing.
4. **Rare proper nouns**: Write phonetically for French TTS (e.g., `Pishon` → `Pichone`, `Gihon` → `Guihone`).
5. **Word count limits**: Max 60 words per segment for adult voices, max 40 words for children's voices (Antoine, Noémie). Split longer segments.
6. **Numbers > 9**: Spell out in letters (e.g., `30` → `trente`).

## Season 1 Episode Plan — IMPOSED (Session 21)

### Episode List (FINAL — do not regenerate)
| # | Titre | Type | Durée |
|---|-------|------|-------|
| 01 | La création du monde — quand Dieu a tout inventé | ouverture | 30 min |
| 02 | Noé et le déluge | standard | 25 min |
| 03 | Abraham — quitter tout par confiance | standard | 25 min |
| 04 | Joseph et la tunique de couleurs | standard | 25 min |
| 05 | Moïse — l'enfant du Nil et la mer qui s'ouvre | mi-saison | 30 min |
| 06 | David et Goliath | standard | 25 min |
| 07 | Salomon — le roi sage | standard | 25 min |
| 08 | Daniel dans la fosse aux lions | standard | 25 min |
| 09 | Jonas — avalé par une baleine | standard | 25 min |
| 10 | Esther — la reine qui sauve son peuple | final | 35 min |

### Why Adam & Eve was removed
Episode 1 (La Création) already covers Adam and Eve extensively: their creation from dust, the breath of life, naming the animals, Eve from Adam's rib, the Garden of Eden, and the teasing about the forbidden fruit. Having a separate Adam & Eve episode was redundant.

### Episode 10 — Esther (NEW)
Esther replaces the old Jonas finale. Jonas moves to E09 (standard). Esther becomes the season finale with:
- **Lucas birth event** (same as old E10): the family celebrates Lucas's arrival
- **Moral**: "Le vrai courage, c'est agir pour les autres même quand on a peur pour soi"
- **Arc focus**: Papy Babou — emotional conclusion, Noémie says Esther is her favorite hero
- **Teasing S2**: "Il y a un homme dont je n'ai pas encore parlé — le plus grand de tous"

### S01E01 Script — VALIDATED (do not regenerate)
- Script at `scripts/episodes/S01E01_script.json` — 190 segments, 3314 words, 39 SFX
- Score: 9.2/10 (directeur validation)
- Audio IA audit: 0 remaining issues (26 SFX prompts + 4 voice segments corrected)
- Status: `waiting_script` in pipeline (ready for audio production)
- Production data files: `data/historique_episodes.json`, `logs/S01E01_rapport.json`, `checkpoints/S01E01_checkpoint.json`

### Audio IA Audit Process (MANDATORY for every script)
Before any script goes to audio production, run this audit:

**SFX audit** — check every SFX prompt for:
1. Non-auditory descriptions (visual, olfactory, tactile) → replace with sonic equivalents
2. Abstract concepts (divine, primordial, sacred) → replace with concrete sound descriptors
3. Silent events (plants growing, flowers blooming) → replace with audible equivalents
4. Montage metadata in prompts (day transition marker) → remove
5. Human speech risk (voices) → replace with laughing/cheering
6. Silence described poetically → replace with drones/pads
7. Conflicting spatial layers (underwater + seagulls) → fix

**Voice text audit** — check every spoken segment for:
1. Onomatopoeia (Boum, Splash, Crac) → remove, let SFX handle it
2. Hyphenated syllabification (Fir-ma-ment) → write normally + use rythme lent
3. Uncontrolled ellipsis (...) → rewrite
4. Rare proper nouns → French phonetic spelling (Pishon → Pichone)
5. Word count: max 60 words adult, max 40 words children → split
6. Numbers > 9 → spell out

### Files updated in this session
- `data/saisons/saison_01.json` — season plan with 10 episodes (Esther replaces Adam & Eve)
- `config.py` — `PERIMETRES_SAISONS[1]["episodes_imposes"]` updated
- `agents/planificateur.py` — prompt examples updated
- `data/preferences_producteur.json` — 2 new rules (audio_sfx + audio_voix)
- `scripts/episodes/S01E01_script.json` — audited script with all SFX/voice fixes
- `data/historique_episodes.json` — S01E01 entry for frontend visibility
- `logs/S01E01_rapport.json` — rapport with waiting_script status
- `checkpoints/S01E01_checkpoint.json` — checkpoint for pipeline resume

### When producing future episodes
1. Generate script via pipeline (scripteur + reviewer + directeur)
2. Run Audio IA audit (SFX prompts + voice text) — rules in `preferences_producteur.json` are injected into scripteur prompt automatically, but POST-GENERATION audit is still recommended
3. Validate script via frontend or CLI
4. Continue to audio production (TTS + SFX + montage)

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

## Triple Audit UX + Infrastructure + Auditeur (Session 15b)
3-agent audit of the full season production workflow. 25 fixes (2 CRITICAL, 8 HIGH, 15 MEDIUM).

### CRITICAL fixes
- **Go/No-Go fallback**: Unrecognized input in `produire-saison` Go/No-Go used to launch production by default — now loops until valid choice ("v" or "a")
- **Atomic checkpoints**: `sauvegarder_checkpoint()` and `sauvegarder_historique()` now use `tempfile + os.replace()` for crash-safe writes

### HIGH fixes
- **Publication abandon**: "a" in `_validation_publication()` now returns `False` (continues to rapport) instead of raising `ProductionAbandonnee` (which lost rapport/historique/arc state)
- **Go/No-Go option**: Changed from "g" (Go) to "v" (Valider) for consistency with all other validation menus
- **Montage edit guard**: No longer relaunches remontage when script file is missing — shows error and returns to menu
- **Interactif confirmation**: Added Go/No-Go before "produire tous les épisodes restants" in interactive season mode
- **Reviewer seuil**: Pipeline now passes `seuil=SEUILS_PAR_TYPE[type_episode]` explicitly instead of relying on LLM response field
- **chemin_hq None guard**: Publication blocked with explicit message when audio HQ file is missing (prevents TypeError crash on checkpoint resume)
- **Voice config thread safety**: `_voice_config_lock` protects `VOICE_IDS`, `VOICE_SETTINGS`, `STEREO_PAN` mutations in `ajouter_personnage()` and `configurer_voix()`
- **Atomic writes**: Both `sauvegarder_checkpoint()` and `sauvegarder_historique()` now use atomic write pattern

### MEDIUM fixes
- **Auto mode error display**: Explicit error message when episode fails in `--auto` mode (was silent)
- **total_episodes accuracy**: Interactive season mode now shows episode's position in full season (not just remaining count)
- **Metadonnees "c" guard**: Script availability checked before asking for instructions (was checked after, losing input)
- **type_episode in interactif**: Episode unique mode now prompts for type (standard/ouverture/mi-saison/final/bonus)
- **Saison input loop**: Invalid season number in interactive mode now loops instead of `sys.exit(1)`
- **Prétexte injection**: `episode_plan["pretexte"]` now injected into scripteur prompt
- **Archive warning**: Warning displayed when planning season N if archive of season N-1 is missing
- **Audio segments check**: Warning displayed if audio segments are missing before montage
- **Inter-season arc state**: S(N+1)E01 now loads arc state from last episode of season N

### When modifying main.py (Session 15b patterns)
- `sauvegarder_checkpoint()` uses atomic write: `tempfile.NamedTemporaryFile` + `os.replace()`
- `sauvegarder_historique()` uses atomic write
- `_validation_publication()` "a" option returns `False` (not `ProductionAbandonnee`)
- Go/No-Go uses "v" (not "g") and loops on invalid input (never falls through)
- `reviewer.est_valide()` called with explicit `seuil=` parameter from pipeline
- Arc state for S(N+1)E01 loaded from last episode of previous season

### When modifying config.py (Session 15b)
- `_voice_config_lock` must be acquired before modifying `VOICE_IDS`, `VOICE_SETTINGS`, or `STEREO_PAN`

## Job Resilience & SIGTERM Survival (Session 16)
Complete resilience system for surviving Replit autoscale SIGTERM + redeploy during long-running productions (18-30 min).

### Architecture: 3-layer resilience

**Layer 1 — SIGTERM Handler (main.py)**
- `signal.signal(signal.SIGTERM, _sigterm_handler)` registered at `pipeline()` start
- Pipeline context stored in `_production_local.pipeline_context` (thread-local), updated by `sauvegarder_checkpoint()` at every step
- On SIGTERM: saves checkpoint (file + DB + Object Storage), marks production `status='interrupted'` in DB with 3 retries (0.5s intervals)
- Uses `sys.exit(0)` — `SystemExit` is `BaseException`, not caught by `except Exception` in pipeline error handler

**Layer 2 — Auto-Resume Thread (web.py)**
- `_auto_resume_interrupted()` runs as daemon thread on server startup
- Retries DB connection 4 times with exponential backoff (5s, 8s, 12s, 20s) — handles Neon cold start
- Queries `WHERE status NOT IN ('completed', 'failed')` — catches ALL non-terminal statuses including `interrupted`, `started`, `*_done` (in case SIGTERM handler's DB update failed)
- Restores checkpoint from DB → validates envelope structure → launches `reprendre --auto` with original `stop_after`
- Corrupted checkpoint files detected and re-restored from DB

**Layer 3 — Frontend Reconnection (dashboard.html)**
- `_reconnectActiveJob()` retries `/api/running-jobs` 3 times with 3s intervals on page load
- Discovers auto-resumed job (new job_id), updates sessionStorage, resumes polling
- `/api/running-jobs` prioritizes in-memory jobs (source=memory) over DB jobs (source=db)
- DB source excludes `'interrupted'` status (handled by auto-resume thread)

### Network resilience (from earlier in this session)
- `pollJob()` retries 404s up to 30 times (3s intervals) during network loss
- `apiCallAsync()` saves job to sessionStorage BEFORE polling — survives page reload
- `_clearActiveJob()` NOT called on network errors (keeps sessionStorage for reconnection)
- Running job banner shown immediately on reconnect, before polling result

### DB Pool Keepalive (database.py)
- `_pool_keepalive_loop()` daemon thread pings DB every 2 minutes via `SELECT 1`
- Prevents Neon from closing idle connections during long productions (~18 min)
- `minconn=1` (was 2) — fewer idle connections to go stale
- `connect_timeout=10` — faster failure detection on Neon cold start

### Checkpoint System Fixes
- `stop_after` now persisted in ALL checkpoint data dicts — auto-resume respects original workflow
- `_restore_checkpoint_from_db()` reconstructs the full envelope `{episode_id, etape, timestamp, data}` from DB (DB stores only the inner `data` dict)
- Uses `etape_courante` from production row + `checkpoint_data` for the data
- Query uses `ORDER BY updated_at DESC` and filters out empty `checkpoint_data` to avoid reading a fresh empty row from `reprendre()` instead of the real checkpoint

### SQL Column Fixes
- Table `productions` has columns: `started_at`, `completed_at`, `updated_at` — NO `created_at`
- Fixed 4 queries in web.py that referenced non-existent `created_at`: `_restore_checkpoint_from_db`, `_sync_rapport_to_db`, `_sync_checkpoint_to_db`, episode diagnostic
- Tables `scripts`, `fichiers_audio`, `saisons`, etc. DO have `created_at` — those queries are correct

### Status State Machine
Production lifecycle statuses:
- `'started'` — row created by `ProductionRepo.creer()` at pipeline start
- `'{etape}_done'` — set by `ProductionRepo.maj_etape()` after each step (script_done, audio_done, sfx_done, montage_done, metadonnees_done)
- `'interrupted'` — set by SIGTERM handler (may fail if DB is down → stays in `*_done`)
- `'completed'` — set by `ProductionRepo.terminer()` at pipeline end
- `'failed'` — set by `ProductionRepo.echouer()` on pipeline exception
- `'waiting_script'` / `'waiting_montage'` — set when `--stop-after` is used

### When modifying main.py (Session 16 patterns)
- `_production_local.pipeline_context` must be set BEFORE registering SIGTERM handler
- `sauvegarder_checkpoint()` automatically updates `pipeline_context['etape_courante']` and `pipeline_context['rapport']`
- ALL `sauvegarder_checkpoint()` calls must include `stop_after` in the data dict
- `signal.signal(signal.SIGTERM, ...)` wrapped in try/except ValueError (fails if not main thread)
- `reprendre()` reads `stop_after` from checkpoint data if not specified on CLI: `effective_stop_after = stop_after or data.get("stop_after", "")`

### When modifying web.py (Session 16 patterns)
- `_auto_resume_interrupted()` catches ALL non-terminal statuses — never use `status IN ('interrupted', 'started')`, always use `status NOT IN ('completed', 'failed')`
- `_restore_checkpoint_from_db()` must reconstruct checkpoint envelope with `episode_id`, `etape`, `timestamp`, `data` — `charger_checkpoint()` validates all 3 fields
- DB queries on `productions` table: use `started_at` or `updated_at`, NEVER `created_at` (column doesn't exist)
- `_persist_web_job_id()` runs in a parallel thread with retry loop (max 15 attempts, 1s intervals)
- `/api/running-jobs` uses `memory_episodes` set to skip DB rows when an in-memory job already covers that episode

### When modifying database.py (Session 16 additions)
- `_pool_keepalive_loop()` daemon thread pings every 120s — do NOT remove or it will break long productions
- `minconn=1` (not 2) — reduces idle connections that Neon might close
- `connect_timeout=10` added for faster cold-start failure detection

### When modifying dashboard.html (Session 16 patterns)
- `_reconnectActiveJob()` must retry `/api/running-jobs` with delays — auto-resume thread needs time to start
- `pollJob()` must NOT clear sessionStorage on network errors — only clear on definitive job completion/failure
- `apiCallAsync()` must save to sessionStorage BEFORE calling `pollJob()` — survives page reload mid-poll

### Tests (Session 16)
- 7 new tests: TestSIGTERMHandler (3), TestStopAfterInCheckpoint (2), TestPipelineContextForSIGTERM (2)
- Full suite: 557 passed, 3 skipped (ffmpeg), 0 failures

### Git Workflow (Session 16)
- Branch: `claude/audit-episode-workflow-pWYpg`
- Push: `git push -u origin claude/audit-episode-workflow-pWYpg`

## Production Result Visibility Fix (Session 16b)
Root cause diagnosis for 9 consecutive production failures where 35-minute jobs produced no visible results.

### CRITICAL fix
- **`charger_rapport()` SQL column** (`dashboard_data.py:131`): Used `ORDER BY created_at DESC` on the `productions` table, but `productions` has `started_at` (not `created_at`). This caused EVERY DB rapport lookup to silently fail, falling back to local JSON files. After Replit redeploy (which wipes local files), rapport data became permanently invisible despite being correctly stored in DB by the pipeline.

### HIGH fix
- **`_persist_web_job_id` timeout** (`web.py`): `max_wait=15` was insufficient — `reprendre` subprocess needs 15-30s on Replit to start Python, import modules, load checkpoint, and call `ProductionRepo.creer()`. Increased to `max_wait=90` with progressive backoff (1s for first 30 attempts, 2s after).

### MEDIUM fixes
- **`stop_after` Object Storage upload**: Both `stop_after == "script"` and `stop_after == "montage"` blocks now upload rapport to Object Storage via `persistent_storage.upload_rapport()` — ensures rapport survives Replit redeploys even if DB is temporarily down.
- **`stop_after` error logging**: Replaced bare `except Exception: pass` with `except Exception as e: logger.warning(...)` in DB update calls — errors no longer silently swallowed.

### Why 9 failures occurred (post-mortem)
1. Pipeline ran correctly for 35 minutes (TTS + montage)
2. Audio saved to: local filesystem ✓, Object Storage ✓, DB (FichierAudioRepo) ✓
3. Rapport saved to: local JSON ✓, DB (ProductionRepo.maj_etape) ✓
4. Replit redeployed (common during 35-minute productions) → local files lost
5. `/api/episode/S01E01` called `charger_rapport()` → DB query crashed on `created_at` → fell back to JSON → JSON gone → returned None
6. Episode appeared as if production never happened
7. `_persist_web_job_id` also failed (15s timeout too short) → browser couldn't reconnect to job after redeploy

### When modifying dashboard_data.py (Session 16b)
- `charger_rapport()` SQL MUST use `ORDER BY started_at DESC` (not `created_at`) — `productions` table has no `created_at` column
- `trouver_fichier_audio()` SQL on `fichiers_audio` table CAN use `created_at` — that table has it

### When modifying main.py stop_after blocks (Session 16b)
- Both `stop_after == "script"` and `stop_after == "montage"` blocks must:
  1. Save rapport to local JSON file
  2. Upload rapport to Object Storage
  3. Call `ajouter_historique()`
  4. Update DB via `ProductionRepo.maj_etape()` with error logging (not bare `except: pass`)

### Montage Error Visibility (Session 16b — commit 2)
3 additional fixes for subprocess observability and error resilience.

**Subprocess logs in deployment logs** (`web.py`):
- `_run_cli()` now logs last 50 stderr lines to parent logger after subprocess completes
- On non-zero exit code: full error logged with `logger.error()` including stderr tail (2000 chars)
- Stderr capture increased from 1000 → 2000 chars in job result

**Montage error handling** (`main.py`):
- `monteur.assembler(script)` now wrapped in try/except
- On failure: `rapport["etapes"]["montage"]` populated with `{"status": "error", "erreur": str(e), "erreur_type": type(e).__name__}`
- Rapport saved to normal file (`_rapport.json`) + Object Storage even on montage error
- Checkpoint saved at etape="montage" for retry — then exception re-raised for outer handler to mark DB as failed

**Partial rapport always visible** (`main.py`):
- Pipeline outer error handler now saves to `{episode_id}_rapport.json` (was `_rapport_echec.json` which `charger_rapport()` never read)
- Uploads to Object Storage in error handler
- All bare `except Exception: pass` in `_pipeline_inner` replaced with proper `logger.warning()` calls

### When modifying main.py montage step (Session 16b)
- `monteur.assembler()` MUST be in try/except
- On error: save to `rapport["etapes"]["montage"]["erreur"]`, save rapport to normal file, save checkpoint, then re-raise
- NEVER save error rapport to `_rapport_echec.json` — always use the normal `_rapport.json` so `charger_rapport()` finds it
- All `except Exception:` blocks MUST have logging (no bare `pass`)

### When modifying web.py _run_cli (Session 16b)
- After `proc.communicate()`: log stderr lines to parent logger for deployment log visibility
- On error (non-zero returncode): log full error with stderr tail via `logger.error()`
- stderr capture: 2000 chars (not 1000) for better error diagnostics

### Tests (Session 16b)
- 7 new tests: TestChargerRapportSQL — charger_rapport uses started_at, persist_web_job_id timeout, stop_after Object Storage upload, stop_after error logging, stderr only on error, monteur error handling, error rapport normal filename
- Full suite: 564 passed, 3 skipped (ffmpeg), 0 failures

### Audit corrections (Session 16b — post-audit)
- **stderr spam fix**: `_run_cli()` now only logs stderr lines when `returncode != 0` (was logging for ALL jobs including success)
- **CLAUDE.md coherence**: Error Handling section updated from `_rapport_echec.json` to `_rapport.json`
- **3 missing tests added**: stderr conditional logging, monteur error handling, error rapport filename

## Crash Recovery Fixes (Session 16c)
Two CRITICAL bugs causing NameError crashes and data loss on resume/redeploy.

### CRITICAL fix 1: `_log_step_duration` NameError
- `_log_step_duration()` was defined inside `pipeline()` but called from `_pipeline_inner()` (a separate function)
- Every job that reached montage (or any step calling `_log_step_duration`) crashed with `NameError: name '_log_step_duration' is not defined`
- **Fix**: Moved `_log_step_duration()` definition (and its timer variables) from `pipeline()` into `_pipeline_inner()`

### CRITICAL fix 2: Error rapport overwrites `decisions_humaines`
- When a crash occurred, the error handler saved a minimal rapport that overwrote the existing rich rapport (with `decisions_humaines`, validated steps, etc.)
- **Fix**: Error handler now loads existing rapport and merges: preserves `decisions_humaines`, `metriques`, `alertes_post_generation`, and merges `etapes` (existing + new)
- Uses `rapport_existant["etapes"].copy()` + `.update()` so existing step data is preserved while new error data is added

### When modifying main.py (Session 16c patterns)
- `_log_step_duration()` MUST be defined inside `_pipeline_inner()`, NOT inside `pipeline()` — `_pipeline_inner` is a separate function, not a nested one
- Error handler in `pipeline()` MUST merge with existing rapport before saving — never overwrite blindly
- Keys to preserve on merge: `decisions_humaines`, `metriques`, `alertes_post_generation`
- Etapes merge: existing etapes as base, new etapes overwrite only their own keys

## Resume & SQL Fixes (Session 16d)
Three bugs causing auto-resume to restart from scratch and SQL errors on script validation.

### CRITICAL fix 1: `FOR UPDATE` with aggregate functions
- `db_models.py` used `SELECT MAX(version) ... FOR UPDATE` in 3 places (ScriptRepo, SaisonRepo, PersonnageRepo)
- PostgreSQL forbids `FOR UPDATE` with aggregate functions (`MAX`)
- Caused "Sync script validé DB ÉCHOUÉ" error on script validation
- **Fix**: Removed `FOR UPDATE` from all 3 aggregate queries — row-level locking not needed for version counter in single-user context

### CRITICAL fix 2: Auto-resume re-launches from scratch
- `_auto_resume_interrupted()` query used `status NOT IN ('completed', 'failed')` — this included `waiting_script` and `waiting_montage` statuses
- Productions waiting for human validation were auto-resumed, launching a fresh script generation instead of waiting for the user
- **Fix**: Excluded `waiting_script` and `waiting_montage` from auto-resume query

### CRITICAL fix 3: `etape_depart` mapping for DB statuses
- `_pipeline_inner()` had `etapes.index(etape_depart)` with fixed list `["script", "review", "audio", ...]`
- DB statuses like `"waiting_script"`, `"waiting_montage"`, `"script_done"` are NOT in this list
- When `etape_depart` was not in the list, `etape_idx` defaulted to 0 → full restart from scratch
- **Fix**: Added `_etape_mapping` dict in `_pipeline_inner()` that maps DB statuses to pipeline steps:
  - `waiting_script` → `audio`, `waiting_montage` → `metadonnees`
  - `script_done` → `audio`, `audio_done` → `sfx`, `sfx_done` → `montage`
  - `montage_done` → `metadonnees`, `metadonnees_done` → `publication`

### When modifying db_models.py (Session 16d)
- NEVER use `FOR UPDATE` with aggregate functions (`MAX`, `MIN`, `COUNT`, `SUM`, `AVG`)
- PostgreSQL will reject the query with "FOR UPDATE is not allowed with aggregate functions"

### When modifying web.py (Session 16d)
- `_auto_resume_interrupted()` must exclude ALL terminal AND waiting statuses: `'completed', 'failed', 'waiting_script', 'waiting_montage'`
- `waiting_*` statuses mean "waiting for human validation" — auto-resuming them defeats the purpose

### When modifying main.py (Session 16d)
- `_pipeline_inner()` has `_etape_mapping` dict that maps DB statuses to pipeline steps
- Any new `waiting_*` or `*_done` status MUST be added to this mapping
- The mapping ensures checkpoint resume works even when `etape_courante` in DB uses DB-specific status names instead of pipeline step names

## Checkpoint DB Format Fix (Session 16d-bis)
CRITICAL bug causing `KeyError: 'titre'` on every auto-resume after redeployment.

### Root cause: double-envelope bug
- `_sync_checkpoint_to_db()` stored the FULL checkpoint envelope `{episode_id, etape, timestamp, data: {titre, ...}}` in DB
- `_restore_checkpoint_from_db()` then wrapped it in ANOTHER envelope: `{episode_id, etape, data: {episode_id, etape, data: {titre, ...}}}`
- `reprendre()` did `cp["data"]["titre"]` → got the outer envelope → `KeyError: 'titre'`

### Fix
- **`_sync_checkpoint_to_db()`**: Now extracts `cp_full.get("data", cp_full)` before storing — only the inner `data` dict goes to DB
- **`_restore_checkpoint_from_db()`**: Detects if DB contains old envelope format (has both `"data"` + `"etape"` + `"episode_id"` keys) and uses it directly instead of re-wrapping

### When modifying web.py (Session 16d-bis)
- `_sync_checkpoint_to_db()` MUST store only the `data` dict, NEVER the full envelope — `sauvegarder_checkpoint()` in main.py already stores the `data` dict directly via `ProductionRepo.maj_etape(checkpoint_data=data)`
- `_restore_checkpoint_from_db()` MUST handle both formats in DB: old envelope (detect via `"data" in cp_data and "etape" in cp_data`) and new data-only format
- The two storage paths (`sauvegarder_checkpoint` → `maj_etape` and `_sync_checkpoint_to_db`) MUST store the same format

## Infinite Auto-Resume Loop Fix (Session 16e)
ROOT CAUSE of 12 consecutive failures: `maj_etape()` + `reprendre()` error handling.

### ROOT CAUSE: `maj_etape()` generates wrong status for waiting states
- `ProductionRepo.maj_etape()` unconditionally did `status = f"{etape}_done"`
- Called with `etape="waiting_script"` → `status = "waiting_script_done"`
- Auto-resume exclusion list had `waiting_script` but NOT `waiting_script_done`
- Every redeploy: auto-resume picked up `"waiting_script_done"` → re-ran script → stopped at same point → next redeploy → repeat FOREVER
- **Fix**: `maj_etape()` detects `etape.startswith("waiting_")` and sets `status = etape` (no `_done` suffix)

### CRITICAL: `reprendre()` error handling
- `reprendre()` had `data['titre']` OUTSIDE the try/except → KeyError crashed before the error handler
- No marking of the production as `failed` in DB → auto-resume kept relaunching
- **Fix**: Entire body wrapped in try/except, `data.get('titre', '?')` for display, `_mark_failed_in_db()` in except block

### Anti-loop safeguards
- `_auto_resume_interrupted()` now filters `updated_at < NOW() - 2 minutes` — won't re-resume a production that just crashed
- `_etape_mapping` now covers ALL possible DB statuses including `interrupted`, `erreur`, `started`
- Unknown `etape_depart` values now log an explicit error and fall back to `"script"` (was silently defaulting)
- `_restore_checkpoint_from_db` now filters `status NOT IN ('completed', 'failed')` — won't restore completed productions
- `echouer()` uses `COALESCE(checkpoint_data, '{}')` for safe JSONB concat

### When modifying db_models.py (Session 16e)
- `maj_etape()` MUST check `etape.startswith("waiting_")` — waiting states are workflow terminal, NOT step completion
- `echouer()` must use `COALESCE(checkpoint_data, '{}')` for NULL safety

### When modifying main.py (Session 16e)
- `reprendre()` entire body MUST be in try/except — any crash before pipeline() reaches the error handler
- `_mark_failed_in_db()` MUST be called in the except block to prevent auto-resume loops
- `SystemExit` must be re-raised (SIGTERM handler uses `sys.exit(0)`)
- `_etape_mapping` must cover ALL possible DB statuses: `interrupted`, `erreur`, `started`, all `*_done`, all `waiting_*`

## Redeploy Resilience & Object Storage Audit (Session 17)
Root cause of 14 consecutive production failures after Replit redeploys. Full Object Storage coverage audit.

### ROOT CAUSE: Missing segments on resume → stuck at montage forever
After Replit redeploy, filesystem is wiped. The pipeline checkpoint said "montage" but audio segments (88 voix + 14 SFX) existed only on local filesystem — never uploaded to Object Storage (the upload code didn't exist yet). Pipeline skipped to montage, found 0 segments, crashed. Next resume → same thing. Infinite loop.

### Fix 1: Script restoration from Object Storage on resume
- **Before**: `main.py:2208` checked `if chemin_valide.exists()` — if file missing (redeploy), raised `FileNotFoundError` without trying Object Storage
- **After**: Tries Object Storage first (`persistent_storage.restore_script()`), then DB (`ScriptRepo.charger_valide()`), then raises error only if both fail
- Same pattern applied to metadata restoration (`restore_metadonnees()`)

### Fix 2: Audio segments upload to Object Storage
- New functions: `persistent_storage.upload_segments()` / `restore_segments()`
- Prefix: `segments/{episode_id}/{filename}.mp3`
- Upload after audio TTS (all voice segments) and after SFX generation
- Restore before montage on resume

### Fix 3: Segment fallback — regenerate audio if segments irrecoverable
- Guard BEFORE the audio step (`if etape_idx > 2`): checks if segments exist locally
- If not: tries `restore_segments()` from Object Storage
- If still missing: **resets `etape_idx = 2`** to regenerate audio+SFX from validated script
- This breaks the "stuck at montage" infinite loop for productions where segments were never uploaded

### Fix 4: Resume reuses existing production row (no orphaned DB rows)
- `pipeline()` was unconditionally calling `ProductionRepo.creer()` even on resume
- Each resume created a new empty production row, polluting the DB
- **Fix**: When `etape_depart != "script"`, looks up existing production via `charger_dernier_checkpoint()` and reuses its ID

### Fix 5: Full Object Storage coverage (audit 7/10 → 10/10)
Three file types were created locally but never uploaded:
- **Cover art PNG**: `upload_cover()` / `restore_cover()` — uploaded after DALL-E generation, restored in dashboard
- **Métadonnées JSON** (includes transcript): `upload_metadonnees()` / `restore_metadonnees()` — uploaded after validation, restored on resume
- **Chapitres JSON**: `upload_chapters()` / `restore_chapters()` — uploaded after montage

### Fix 6: DATABASE_URL not configured (DB empty)
- `DATABASE_URL` env var was empty → `_use_db()` always returned False → 0 DB writes
- Not a code bug — config issue. Pipeline designed to work without DB (JSON + Object Storage fallback)
- To enable: set `DATABASE_URL` in Replit Secrets

### When modifying persistent_storage.py (Session 17)
- 9 prefixes: `audio/`, `scripts/`, `rapports/`, `saisons/`, `checkpoints/`, `segments/`, `metadonnees/`, `chapters/`, `covers/`
- `upload_segments()` / `restore_segments()` handle entire `{segments_dir}/{episode_id}/` directory
- `restore_cover()` tries both PNG and JPG extensions
- All new functions follow existing patterns: try/except, log warnings, return None/0 on failure

### When modifying main.py (Session 17)
- Segment guard BEFORE audio step: `if not dry_run and etape_idx > 2` → check segments → restore → fallback to `etape_idx = 2`
- Script restore on resume: tries Object Storage → DB → error (not just local file check)
- Metadata restore on resume: same pattern as script
- Cover art upload: after DALL-E generation in metadata step
- Chapters upload: after montage alongside audio upload
- Metadata upload: after metadata validation
- `pipeline()` reuses existing production on resume (`etape_depart != "script"`)

### When modifying web.py (Session 17)
- `/api/episode/<id>`: restores cover art from Object Storage if missing locally
- All `persistent_storage` imports remain inside try/except blocks
- `continue-production` route MUST ensure `_valide.json` exists BEFORE launching subprocess (3-layer restore: local copy → Object Storage → DB → 400 error)
- Auto-chaining callbacks (`_chain_sfx_then_montage`, `_chain_montage`) call `_ensure_valide_exists()` to handle redeploys between jobs

### Complete Object Storage Upload/Restore Map
| File Type | Upload Location | Restore Location | Prefix |
|-----------|----------------|------------------|--------|
| Audio HQ/Preview | main.py (montage) | dashboard_data.py | `audio/` |
| Script validé | main.py (review) | main.py (resume) + web.py | `scripts/` |
| Rapport | main.py (multiple) | dashboard_data.py | `rapports/` |
| Checkpoint | main.py (each step) | web.py (resume route) | `checkpoints/` |
| Saison plan | main.py (planifier) | config.py | `saisons/` |
| Segments voix/SFX | main.py (audio+SFX) | main.py (guard before audio) | `segments/` |
| Métadonnées JSON | main.py (after validation) | main.py (resume) | `metadonnees/` |
| Chapitres JSON | main.py (montage) | — | `chapters/` |
| Cover art PNG | main.py (DALL-E) | web.py (episode endpoint) | `covers/` |
| WAV intermédiaire | monteur.py (after LUFS) | main.py (before montage) | `montage_wav/` |

### Tests (Session 17)
- Full suite: 577 passed, 3 skipped (ffmpeg), 0 failures
- Branch: `claude/audit-episode-workflow-pWYpg`

## Infrastructure Audit Fixes (Session 17b)
6 fixes from infrastructure audit (3 CRITICAL, 3 HIGH) — score 6.5/10 → fixed.

### I1 CRITICAL: WAV export atomique
- `monteur.py` WAV checkpoint was written directly → container kill = truncated file → montage stuck forever
- **Fix**: tempfile + os.replace() pattern — atomic rename prevents corrupt WAV files
- Temp file cleaned up on exception

### I2 CRITICAL: WAV integrity validation on load
- No validation when loading intermediate WAV — truncated/corrupt file caused crash or silent audio loss
- **Fix**: Size check (>1KB), duration check (>10s), try/except around AudioSegment.from_wav()
- On corrupt WAV: delete + regenerate from scratch (full montage)

### I3 CRITICAL: _stream_reader exception logging
- `except Exception: pass` silently swallowed all read errors — invisible failures
- **Fix**: Log exceptions at debug level with stream label and job_id
- Also protect stream.close() in finally block

### I4 HIGH: Thread-safe log collection
- stdout_lines/stderr_lines lists shared between threads without lock
- **Fix**: threading.Lock() shared between both reader threads, acquired on append and join

### I5 HIGH: PREFIX_MONTAGE_WAV constant
- `montage_wav/` prefix hardcoded in main.py and monteur.py, not defined in persistent_storage.py
- **Fix**: `PREFIX_MONTAGE_WAV = "montage_wav/"` constant in persistent_storage.py, used by both callers

### I6 HIGH: WAV cleanup in try/except
- `.unlink()` on WAV cleanup not protected — OSError could crash pipeline after successful export
- **Fix**: Wrapped in try/except OSError with warning log

### When modifying monteur.py (Session 17b)
- WAV export MUST use tempfile + os.replace() (atomic write)
- WAV load MUST validate: size >1KB, duration >10s, wrapped in try/except
- On corrupt WAV: set `episode_complet = None` → triggers full regeneration
- `if episode_complet is None:` replaces `else:` for the regeneration block
- WAV cleanup in try/except OSError

### When modifying web.py (Session 17b)
- `_stream_reader()` takes a `lock` parameter — all list.append() under lock
- `_run_cli()` creates `_lines_lock = threading.Lock()` passed to both reader threads
- Final join reads lists under lock: `with _lines_lock: stdout = "\n".join(...)`
- `_stream_reader` logs exceptions at debug level (not silent pass)

## Montage Job Logging & Segment Coherence Fix (Session 18)
Root cause diagnosis of 18 consecutive montage failures: invisible subprocess logs + stale segments from Object Storage.

### ROOT CAUSE 1: Subprocess logs invisible
- `logging.basicConfig()` is a NO-OP if root logger already has handlers (can happen from imports)
- Rich Console may not flush properly when stdout is a PIPE (subprocess mode)
- **Fix**: `configurer_logging()` now uses `force=True` to override any prior config
- **Fix**: Added explicit `sys.stderr.write()` + `flush()` at ALL critical points in `reprendre()`, `_pipeline_inner()`, and `monteur.assembler()`
- **Fix**: Added `logging.StreamHandler(sys.stderr)` as backup handler that bypasses Rich Console
- This guarantees log visibility in deployment logs regardless of Rich Console behavior

### ROOT CAUSE 2: Stale segments from Object Storage
- `restore_segments()` downloads ALL files matching `segments/{episode_id}/` — including segments from OLD script versions
- After script regeneration or modification, Object Storage accumulates segments from multiple production attempts
- The monteur iterates over the CURRENT script's segment IDs, but stale segments pollute the directory and cause confusion
- **Fix**: After restoring segments, cleanup phase removes any MP3 files whose stem (ID) is NOT in the current script's segment list
- **Fix**: After cleanup, verify that >50% of voice segments are present — if not, force audio regeneration (`etape_idx = 2`)
- **Fix**: Before montage, coherence check raises `RuntimeError` if >50% of voice segments are still missing

### ROOT CAUSE 3: No heartbeat during montage
- `monteur.assembler()` runs for 20-30 minutes with logs only every 20 segments via `logger.info()`
- If logging is broken, the subprocess appears to run silently for the entire duration
- **Fix**: Direct `sys.stderr.write()` at monteur startup, every 20 segments, and at export completion
- These bypass all logging frameworks and go directly to stderr, captured by `_stream_reader` in web.py

### When modifying main.py (Session 18)
- `configurer_logging()` MUST use `force=True` — without it, `basicConfig()` may be silently ignored
- `_pipeline_inner()` has `_log_direct()` helper for stderr logging — use it at all critical checkpoints
- `reprendre()` has its own `_log_direct()` — use it for all startup/completion/error messages
- Segment cleanup guard runs BEFORE audio step and removes files not in `script["episode"]["segments"]`
- Segment coherence check in montage step raises `RuntimeError` if >50% voice segments are missing

### When modifying monteur.py (Session 18)
- `assembler()` writes directly to `sys.stderr` at startup, during segment progress, and at export completion
- These writes bypass `logger` and Rich Console — guaranteed to be captured by subprocess PIPE readers

### When modifying persistent_storage.py (Session 18)
- `restore_segments()` restores ALL segments for an episode — caller is responsible for cleaning stale ones
- Stale segments MUST be cleaned by the pipeline AFTER `restore_segments()` and BEFORE `monteur.assembler()`

### Tests (Session 18)
- Full suite: 579 passed, 3 skipped (ffmpeg), 0 failures

## Onomatopoeia Removal & Directeur Podcast Agent (Session 19)

### Onomatopoeia Removal for AI Voice Compatibility
ElevenLabs voices pronounce onomatopoeia literally ("hache-i-hache-i"), sounding unnatural.

- **Rule 15 in scripteur prompt**: "ADAPTATION VOIX IA" — explicitly prohibits all written onomatopoeia (hahaha, hihihi, euh, oh là là, etc.) with verbal alternatives
- **`Scripteur._nettoyer_onomatopees()`**: Post-generation filter that:
  - Removes pure-onomatopoeia segments (e.g., "Hihihi !")
  - Strips onomatopoeia prefixes (e.g., "Ah c'est rigolo" → "C'est rigolo")
  - Cleans inline laughs (e.g., "C'est super Hahaha on continue" → "C'est super on continue")
  - Recapitalizes after prefix removal
- **Bible updates**: Tics de langage cleaned in `personnages.json` and `_BIBLE_FALLBACK`:
  - "Hihihi ! C'est trop drôle !" → "C'est trop drôle !"
  - "Ah mes petits loups" → "Mes petits loups"
  - "Oh non, le pauvre" → "Le pauvre, quand même"
  - "Wahou !" → "C'est incroyable !"

### Directeur Podcast Agent — Creative Director + Audience Personas
New agent `DirecteurPodcast` (`agents/directeur_podcast.py`) for final creative validation.

**Role**: "Marc Delacroix", the #1 French children's podcast director. Validates scripts after the Reviewer, as a creative quality gate.

**5 Evaluation Axes** (each scored /10):
1. **Immersion sonore**: SFX placement, ambiance transitions, sound design
2. **Rythme & accroche**: Hook quality, pacing, attention retention
3. **Émotion & personnages**: Character depth, emotional arc, humor
4. **Valeur éducative**: Biblical fidelity, educational richness, moral delivery
5. **Compatibilité voix IA**: Segment optimization for ElevenLabs, tone variety, pauses

**3 Verdicts**: `feu_vert` (≥7.5 + no critiques), `ajustements_mineurs`, `retravailler` (<6)

**3 Audience Personas**:
- **Lina (7 ans, fille)**: CE1, attention 15-20min, loves Noémie, sensitive to fear. Criteria: vocabulary, curiosity, humor, rhythm, SFX immersion. Weight: 30%.
- **Noah (10 ans, garçon)**: CM2, finds "baby stuff" boring, action-oriented, compares with Les Odyssées. Criteria: sophistication, learning, action, credibility, production quality. Weight: 30%.
- **Sophie (45 ans, parent catholique)**: 3 children, exigent on biblical fidelity, wants joyful faith transmission not moralization. Criteria: fidelity, tone, discussion triggers, multi-age, quality. Weight: 40%.

Note audience = Lina×0.3 + Noah×0.3 + Sophie×0.4 (parent weighs more).

**Pipeline Integration**: Runs after reviewer post-generation checks, before human validation. Results in `rapport["etapes"]["directeur_podcast"]`. Wrapped in try/except — failure doesn't block pipeline.

### When modifying directeur_podcast.py
- System prompt uses `{{` / `}}` for `.format()` compatibility (like reviewer)
- Always use `config.appel_claude_avec_retry()` for API calls
- Always use `parser_json_llm()` from utils.py
- `_MAX_TOKENS_PAR_TYPE` mirrors scripteur pattern (final=8192, standard=4096)
- `_valider_resultat()` checks all 5 axes + all 3 personas + valid verdict
- Pipeline catches all exceptions — agent failure is non-blocking

### When modifying main.py (Session 19)
- `DirecteurPodcast` imported alongside other agents
- Directeur evaluation runs AFTER reviewer post-generation checks and BEFORE `_log_step_duration("Script + Review")`
- Contexte dict passed: `type_episode`, `score_reviewer`, `alertes`, `metriques`
- Results stored in `rapport["etapes"]["directeur_podcast"]` with: `note_globale`, `verdict`, `note_audience`, `axes`, `nb_recommandations_critiques`, `personas`

### Tests (Session 19)
- 12 new tests in test_scripteur.py (TestNettoyerOnomatopees)
- 34 new tests in test_directeur_podcast.py: TestPersonas (7), TestPrompts (7), TestValidation (7), TestUtilitaires (9), TestEvaluer (5)
- Full scripteur + directeur suite: 123 passed, 0 failures

## Infrastructure Audit + Fixed Episodes + Purge System (Session 20)
Comprehensive 6-commit session: infrastructure audit, fixed episodes, season increment bug, SEO titles, historique pollution fix, and production data purge system.

### Infrastructure Audit Fixes (H1 + M1 + M2 + L1)

**H1 (HIGH)**: `valider_metadonnees()`, `go_no_go_publication()`, `brief_creatif()` created `anthropic.Anthropic()` without arguments instead of using `self.client` (which has explicit API key + 300s timeout). Fixed: replaced with `self.client` at lines 1346, 1470, 1569 of `directeur_podcast.py`.

**M1 (MEDIUM)**: `instructions_dir` built by directeur for metadata regeneration were NEVER injected into `metadonnees.generer()`. Fixed: script enriched with `script_enrichi["_instructions_metadonnees"] = "\n".join(instructions_dir)` before the call, matching the pattern in `_validation_metadonnees()`.

**M2 (MEDIUM)**: `_construire_system_prompt_directeur()` duplicated persona-building logic from `_construire_personas_text()`. Fixed: refactored to call `_construire_personas_text()` — DRY.

**L1 (LOW)**: Variable `directeur_ok` was assigned but never read. Fixed: now used in `rapport["etapes"]["directeur_podcast"]["approuve"]`.

### Fixed Episodes — Saison 1 IMPOSED (10 biblical stories)

**CRITICAL CHANGE**: Season 1 episodes are no longer generated freely by the LLM. They are IMPOSED in this exact order:
1. La création du monde
2. Adam et Ève — le fruit défendu
3. Noé et le déluge
4. Abraham — quitter tout par confiance
5. Joseph et la tunique de couleurs
6. Moïse — l'enfant du Nil et la mer qui s'ouvre
7. David et Goliath
8. Salomon — le roi sage
9. Daniel dans la fosse aux lions
10. Jonas — avalé par une baleine

**Implementation**:
- `config.PERIMETRES_SAISONS[1]` now has `episodes_imposes` list with the exact 10 stories
- `planificateur.planifier_saison()` captures `episodes_imposes` from perimetre and forces `histoire_biblique` post-generation
- System prompt examples updated to match the new stories
- `_ORDRE_CHRONOLOGIQUE` in planificateur: Daniel=48, Jonas=50 (was reversed)

### Fixed Episodes — Saisons 2 and 3 IMPOSED

**Saison 2 — La vie de Jésus** (10 episodes):
1. L'annonce à Marie — l'ange Gabriel
2. La naissance à Bethléem
3. Les rois mages et l'étoile
4. Jésus enfant au Temple
5. Le baptême dans le Jourdain
6. Les noces de Cana — l'eau changée en vin
7. Le sermon sur la montagne
8. La multiplication des pains
9. Lazare — le miracle de la résurrection
10. La Passion, la mort et la résurrection de Jésus

**Saison 3 — Apôtres et grands saints** (10 episodes):
1. Pierre — le pêcheur devenu chef des apôtres
2. Paul — le persécuteur foudroyé sur le chemin de Damas
3. Étienne — le premier martyr chrétien
4. Marie-Madeleine — la première témoin de la résurrection
5. Jean — l'apôtre qui écrit l'Apocalypse à Patmos
6. François d'Assise — le riche qui choisit la pauvreté
7. Jeanne d'Arc — la bergère qui entend des voix
8. Nicolas de Myre — le saint qui donne en secret
9. Thérèse de Lisieux — la petite voie vers Dieu
10. Mère Teresa — servir Dieu dans les rues de Calcutta

### Season Increment Bug Fix

**Bug**: When re-planning saison 1, the LLM saw "Saison 1 already exists" in `saisons_precedentes` and generated a "saison 2" instead of replacing.

**Fix** (3 layers):
1. `saisons_precedentes` in `planifier_saison()` now excludes saisons `>= current` (was including all)
2. Same filter applied to `archives_saisons`
3. Season number forced in plan JSON after generation: `plan["saison"]["numero"] = saison`

### Directeur Podcast — SEO Title Verification

**New requirement**: Titles must be both ACCROCHEURS (catchy) and CHERCHABLES (searchable on podcast platforms).

**Changes to `_SYSTEM_PROMPT_METADONNEES`**:
- Title criterion split into 2 mandatory sub-criteria: a) Accrocheur, b) Cherchable/SEO
- Title MUST contain biblical character/story name — missing = verdict "retravailler" (blocking)
- Good/bad examples added (e.g., "David contre Goliath — le berger qui terrasse un géant" = good, "Le courage d'un petit berger" = bad — searchable but unfindable)
- Description must also contain SEO keywords
- New JSON response fields: `titre_cherchable`, `titre_contient_nom_biblique`

### Historique Pollution Fix

**Bug**: When re-planning a season, old historique entries (from previous production) remained. Episodes were skipped as "déjà produits" even though the plan had completely changed.

**Fix** (3 layers):
1. **`_episodes_deja_produits()` helper** (main.py): Compares title from current plan vs historique. If title changed → episode is NOT "déjà produit" → will be re-produced.
2. **Purge at plan save**: When a new plan is saved in `planifier-saison`, historique entries whose title doesn't match the new plan are automatically purged.
3. Both `_interactif_saison()` and `produire_saison()` now use `_episodes_deja_produits()` instead of raw episode_id matching.

### Production Data Purge System (Web Dashboard)

**New section in Config tab**: "Nettoyage des données de production"

**3 levels of purge**:

| Action | Endpoint | What it does |
|--------|----------|-------------|
| Purger une saison | `POST /api/purge/saison/<num>` | Deletes all produced episodes of a season (historique, scripts, audio, rapports, DB). Option `garder_plan` to keep the season plan. |
| Reset complet | `POST /api/purge/tout` | Deletes EVERYTHING: historique, plans, saisons, DB tables, files. |
| (existing) Supprimer épisode | `POST /api/episode/<id>/delete` | Soft-delete single episode (was already present) |

**Security**:
- 2-step confirmation (click → confirmation zone → confirm button)
- Files archived to `output/archive/` (recoverable)
- Audit trail in `audit_log` DB table
- Object Storage cleanup included

**Frontend**: Card with red border in Config page, saison number input, "garder plan" checkbox, "Purger la saison" button (coral), "Tout supprimer" button (dark red), confirmation zone with contextual message, result display with details.

### When modifying config.py (Session 20)
- `PERIMETRES_SAISONS` now has `episodes_imposes` key (list of strings) for seasons with fixed episodes
- All 3 seasons have `episodes_imposes` — the LLM receives them in the description AND the planificateur forces them post-generation
- To add/change episodes for a season: update both `description` (for prompt) and `episodes_imposes` (for enforcement)

### When modifying planificateur.py (Session 20)
- `planifier_saison()` reads `perimetre.get("episodes_imposes")` and stores it in `episodes_imposes` variable
- After validation loop, if `episodes_imposes` is set, forces each episode's `histoire_biblique` to match
- `_ORDRE_CHRONOLOGIQUE`: Daniel=48, Jonas=50 (Daniel is before Jonas biblically)
- Marie-Madeleine=201, Jean=215, François d'Assise=330, Jeanne d'Arc=340, Nicolas de Myre=325, Teresa=360 added

### When modifying main.py (Session 20)
- `_episodes_deja_produits(saison_num, episodes_plan)` → `set[str]` — compares title between plan and historique
- `planifier_saison()`: excludes saisons `>= current` from `saisons_precedentes` and `archives_saisons`
- `planifier_saison()`: forces `plan["saison"]["numero"] = saison` after generation
- `planifier_saison()`: purges stale historique entries after saving new plan
- Both `_interactif_saison()` and `produire_saison()` use `_episodes_deja_produits()` not raw set comprehension

### When modifying directeur_podcast.py (Session 20)
- `valider_metadonnees()`, `go_no_go_publication()`, `brief_creatif()` use `self.client` (not `anthropic.Anthropic()`)
- `_construire_system_prompt_directeur()` calls `_construire_personas_text()` (no more duplication)
- `_SYSTEM_PROMPT_METADONNEES` has SEO/searchability criteria for titles — `titre_cherchable` and `titre_contient_nom_biblique` fields in response JSON

### When modifying web.py (Session 20)
- `POST /api/purge/saison/<num>` — purges all episode data for a season, optional `garder_plan` body param
- `POST /api/purge/tout` — full reset of all production data
- Both endpoints: archive files, purge historique JSON, DELETE from DB tables (hard delete, not soft), clean Object Storage, log to audit_log
- DB tables purged: `historique_episodes`, `episodes`, `productions`, `scripts`, `fichiers_audio`, `saisons`

### Tests (Session 20)
- Full suite: 749 passed, 7 pre-existing failures, 3 skipped (ffmpeg)
- No regressions from any of the 6 commits

## Copywriting Audit & Rewrites (Session 21)

### Audit Results (Score: 6.9/10 → ~8.5/10 after fixes)

Full audit of `templates/public.html` covering 10 axes:
| Axe | Score |
|-----|-------|
| Accroche & première impression | 7.0 |
| Proposition de valeur unique (UVP) | 5.0 → fixed |
| Hiérarchie des messages | 6.5 |
| Ton & voix de marque | 8.0 |
| CTA (Call to Action) | 6.0 → fixed |
| Preuve sociale & trust | 6.5 → fixed |
| FAQ / Objections | 7.0 → fixed |
| Micro-copy & labels UI | 8.0 → fixed |
| SEO & lisibilité web | 7.5 → fixed |
| Emotional design & storytelling | 7.0 → fixed |

### 20 Rewrites Applied (P0+P1+P2)

**P0 CRITIQUE (4):**
1. **UVP ajoutée** dans la section About : "Le seul podcast où vos enfants ne sont pas spectateurs — ils participent à la mission"
2. **"bientôt disponible" supprimé** de la FAQ → "Écoutez directement sur ce site ou retrouvez-nous sur Apple Podcasts, Spotify..."
3. **Répétition "mission/mission"** corrigée → "Chaque semaine, une nouvelle épopée extraordinaire"
4. **Triple "mission" FAQ** corrigée → "Chaque épisode est écrit avec soin..."

**P1 IMPORTANT (8):**
5. Hero subtitle → "Le podcast qui transforme le coucher en expédition biblique"
6. Hero description → Suppression duplication, ajout mystère
7. Hero meta → "Pour les 6-10 ans" (au lieu de "Héros dès 6 ans")
8. Badge trust → "Créé par des parents chrétiens"
9. Meta description SEO optimisée avec CTA final
10. Titre témoignages → "Ce que les familles en pensent"
11. CTA intermédiaire après témoignages : "Lancez la première mission — c'est gratuit"
12. 2 nouvelles FAQ : "Est-ce du catéchisme ?" + "À quelle fréquence sortent les épisodes ?"

**P2 POLISH (8):**
13. Badge hero → "10 missions disponibles — Saison 1 complète"
14. H2 épisodes → "Choisissez votre mission"
15. H2 About → "Le podcast biblique pour enfants" (SEO keywords)
16. H2 FAQ → "Questions fréquentes des parents" (SEO keywords)
17. Modal buttons → "Lancer la mission" / "Envoyer à un ami"
18. Subscribe → placeholder "email@famille-dupont.fr" + "Me prévenir à chaque nouvelle mission"
19. Success message → "Bienvenue dans l'équipage !"
20. Footer → Citation italique de Papy Babou
21. Blockquote Papy Babou ajouté entre About et Plateformes
22. Témoignage 4★ → 5★
23. Bouton erreur → "Relancer la connexion"

### Key Copy Decisions
- **UVP différenciante** : format interactif (questions, enquête, solutions farfelues) — unique vs Les Odyssées, Quelle Histoire, etc.
- **Mot "mission"** : était utilisé 28+ fois → variantes introduites (épopée, épisode, aventure) pour éviter la saturation
- **Ton** : maintenu l'univers mission/équipage/expédition tout en réduisant les répétitions
- **SEO** : h2 optimisés avec mots-clés ("podcast biblique pour enfants", "questions fréquentes des parents")
- **Anti-patterns supprimés** : "bientôt disponible" (signale produit inachevé), badge "Nouveau" (deviendra obsolète)

### Remaining Opportunities (not implemented)
- Ajouter un compteur quantitatif ("Rejoint par 500+ familles")
- Bullet points / mise en gras stratégique dans la section About pour la scannabilité
- Ajouter un 4e témoignage ciblant un enfant de 10 ans
- Dark mode toggle manuel (bouton jour/nuit dans la nav)
- Dark mode contraste cards/fond insuffisant (augmenter l'écart --sable/--blanc)

## Gradient Agents Team (Session 22)

### Installation
Gradient Agents team installed from github.com/thomasissa-png/Agent-Team.
15 agents added to `.claude/agents/`: orchestrator, creative-strategy, product-manager, data-analyst, design, fullstack, qa, infrastructure, ia, seo, geo, growth, social, reviewer, legal.
3 custom agents preserved (not overwritten): copywriter.md, designer.md, ux.md.
`project-context.md` template and `update.sh` added at project root.

### 3-Agent Site Audit (Session 22)
Orchestrator launched parallel audit of `templates/public.html` with @design (7.75/10), @ux (7.70/10), @copywriter (7.15/10). Consolidated score: 7.5/10.

### 22 Fixes Implemented (Session 22)

**P0 CRITICAL (3):**
- #1: OG image: generated `og_image.png` 1200x630 from `cover_base.png` (SVG was invisible on social platforms)
- #2: Favicons: `favicon.svg` now primary `<link>` (SVG files existed but were not referenced)
- #3: Newsletter error: no longer shows success message on HTTP failure — shows distinct error

**P1 IMPORTANT (11):**
- #5: UVP added in hero above the fold: "Le seul podcast où vos enfants participent à l'aventure"
- #6: Episodes moved UP — now directly after trust bar (was section 8 after About + Citation). New order: Hero → Trust → Episodes → About → Citation → Testimonials → CTA → FAQ → Newsletter
- #7: CTA intermédiaire moved BEFORE newsletter (was after — counter-intuitive)
- #8: Origin story paragraph added in About: "Chaque soir, dans le salon, Papy Babou ouvre son grand livre..."
- #9: FAQ "Qui est Papy Babou" enriched: "parents chrétiens", "documenté à partir des textes originaux", "relu et validé"
- #10: Trust badge "Écoutable partout" → "Créé par des parents chrétiens" (with heart icon)
- #11: Palette divergences documented in CSS comments (--accent red vs spec gold = deliberate choice)
- #12: Hero CTA hover now uses visible color change (#B81E2A) instead of filter-only brightness
- #14: Subscribe button "Me prévenir" → "Rejoindre l'équipage"
- #15: Vocabulary unified: "Bientôt disponible" → "Disponible prochainement"; search empty state thematic
- Copy: "c'est LE podcast" → "c'est le podcast" (removed infomercial caps)

**P2 POLISH (8):**
- #16: Touch target at 320px: play button 44px minimum (was 32px, below WCAG)
- #17: Manifest `theme_color` aligned to `#5B9BD5` (was `#4A9FE5`)
- #18: Removed unused Baloo 2 font weight 600
- #19: Modal "La leçon de l'épisode" → "Le trésor de cette mission"
- #21: Collective words unified to "équipage" (was bord/équipe/groupe/bande)
- #22: SEO title tag: "Podcast biblique pour enfants 6-10 ans | Les Histoires de Papy Babou" (keywords first)
- #23: Episode cards: `role="article"` added for screen readers
- #24: Nav label "L'équipage" → "À propos" (more intuitive for new visitors)
- #25: Mobile menu closes on outside click (backdrop event listener)
- H2 "Rencontrez les aventuriers" → "L'équipage de Papy Babou" (SEO keywords)
- Error button "Relancer la connexion" → "Réessayer"
- FAQ "étoiles dans les yeux" → "émerveillés et pleins de questions"

**Excluded by user choice:**
- #4: Testimonials (kept 3 existing, no changes)
- #13: Dark mode toggle + contrast (deferred)
- #20: Noémie "tornade" kept (user preference, not "rêveuse")

### Current page structure (after Session 22)
1. Nav sticky (À propos, Épisodes, Parents, S'abonner)
2. Hero (title + UVP + meta + CTA)
3. Wave SVG
4. Trust bar (Adapté 6-10 ans, 15-20 min, Créé par des parents chrétiens)
5. Saison tabs + Search
6. **Episodes** (main content — moved up from position 8)
7. About (L'équipage + Le podcast biblique + origin story)
8. Citation Papy Babou
9. Testimonials
10. Plateformes (Apple, Spotify, RSS)
11. Séparateur doré
12. FAQ Parents
13. **CTA intermédiaire** (moved before newsletter)
14. Newsletter (Rejoindre l'équipage)
15. Wave closing
16. Footer

### When modifying public.html (Session 22 patterns)
- Trust bar 3rd badge is "Créé par des parents chrétiens" (not "Écoutable partout")
- UVP line exists between hero-subtitle and hero-meta (class="hero-uvp")
- Episodes section is BEFORE About section (not after)
- CTA intermédiaire is BEFORE newsletter section (not after)
- Subscribe button text is "Rejoindre l'équipage" (not "Me prévenir")
- Hero CTA hover uses explicit `background: #B81E2A` (not filter:brightness)
- Episode cards have `role="article"` set via JS
- Mobile nav has document click listener to close on outside click
- `og_image.png` exists in assets/artwork/ (generated from cover_base.png, 1200x630)
- favicon2.png is the ONLY favicon (no SVG — see "Favicon — ABSOLUTE RULE" section)
- Baloo 2 loads only weight 800 (600 removed)
- Modal morale label: "Le trésor de cette mission"
- All character descriptions use "l'équipage" for collective reference
- Nav uses "À propos" label (not "L'équipage")
- Title tag has keywords before brand name for SEO

### Git Workflow (Session 22)
- Branch: `claude/restructure-frontend-admin-J8dKf`
- Push: `git push -u origin claude/restructure-frontend-admin-J8dKf`

## Audit System Overhaul (Session 23)
Complete rewrite of 5 audit agents with 9/10 minimum quality threshold.

### 5 Audit Agents (rewritten)

| Agent | Persona | Focus | Axes |
|-------|---------|-------|------|
| **audit-sfx** | Thomas Lavigne (sound designer) | Experience sonore technique + creative | A: 10 regles SFX, B1: couverture sonore, B2: densite/variete, B3: transitions/immersion, B4: impact emotionnel, B5: qualite prompts |
| **audit-voix** | Isabelle Fontaine (directrice vocale) | Direction vocale technique + creative | A: 6 regles TTS, B1: variete tons, B2: rythme/pauses, B3: naturalite enfants, B4: arc emotionnel, B5: dynamique echanges |
| **audit-marc** | Marc Delacroix (directeur creatif #1) | 5 axes creatifs + 3 personas | Immersion, Rythme, Emotion, Educatif, Production + Lina(7), Noah(10), Sophie(parent) |
| **audit-claire** | Claire Moreau (concurrente) | 6 axes + 2 personas | Accroche, Pacing, Authenticite, Immersion, Educatif, Viralite + Timeo(9), Camille(parent non-pratiquante) |
| **audit-episode** | Orchestrateur | Consolide 4 audits, plan d'action, corrections auto | P0 technique, P1 convergences, P2 un seul, P3 optionnel |

### How to run audits
- Full audit: `@audit-episode scripts/episodes/S01EXX_script.json`
- Individual: `@audit-sfx`, `@audit-voix`, `@audit-marc`, `@audit-claire`
- Phase 1 (technique) runs in parallel, Phase 2 (creatif) runs in parallel
- P0+P1 corrections applied automatically, P2+P3 listed for human decision

### Verdict thresholds (raised from 8.5 to 9.0)
- `feu_vert`: moyenne >= 9.0 ET audience >= 8.5 ET 0 axe < 8.0
- `ajustements_mineurs`: moyenne >= 8.0 ET audience >= 7.5 ET 0 axe < 7.0
- `retravailler`: moyenne < 8.0 OU un axe < 7.0

### S01E01 Audit Results (Session 23)

**Scores des 4 auditeurs:**
| Auditeur | Score | Verdict |
|----------|-------|---------|
| Thomas Lavigne (Son) | 9.1/10 | Corrections mineures |
| Isabelle Fontaine (Voix) | 9.4/10 | Pret pour production |
| Marc Delacroix (Creatif) | 9.0/10 | feu_vert |
| Claire Moreau (Creatif) | 8.2/10 | ajustements_mineurs |
| **Moyenne** | **8.9/10** | |

**Axes sous 9/10 identifies:**
- Potentiel viral/partage: 7.5 (Claire)
- Rythme & pacing: 8.7 (Claire 8.0, Marc 9.0, Isabelle 9.0)
- Immersion sonore: 8.7 (Thomas 9.1, Marc 8.5, Claire 8.5)

**15 corrections appliquees (P0+P1):**
- P0: sfx_032b birds singing→chirping, sfx_039 children's footsteps→small footsteps, sfx_036 remove contented sigh
- P1: chime Jour3→4 (sfx_017b), overlay gouter Mamie (sfx_024b), fusion seg_085-086, dedupliquation SFX salon, Noemie seg_100 recalibree 5 ans, seg_100b ajout Papy fait lien Lucas, seg_094 recalibree, seg_115 recalibree, echange fratrie seg_120b-120c, Mamie seg_083 ton emerveille, seg_092 rythme lent, seg_111 rythme lent

**Corrections P2 NON appliquees (decision humaine):**
- Claire R1: Jeu interactif "Devine le jour" pour casser linearite 7 jours
- Claire R3: Resserrer installation Acte 1 (14 segments → 8)
- Marc R3: Fun fact precoce pour accrocher Noah des premieres minutes
- Claire R5: Etendre jeu des noms d'animaux (moment viral)

**Points forts unanimes:**
- Systeme de chimes tubulaires entre les jours (leitmotiv structurant)
- Cold open in medias res cinematographique
- Fun facts scientifiques de premier ordre (5+ memorables)
- Dialogue Bible/science dinosaures ("le pourquoi vs le comment")
- Running gag du gouter de Mamie

### S01E01 Script Status After Audit
- 190+ segments (post-corrections), ~3400 mots, 41+ SFX
- Status: pret pour production audio
- Corrections P0+P1 appliquees automatiquement
- Score projete apres corrections: ~9.2/10

### Git Workflow (Session 23)
- Branch: `claude/episode-2-script-QbSiY`
- Push: `git push -u origin claude/episode-2-script-QbSiY`

## Checkpoint Corruption & Recovery (Session 24)

### ROOT CAUSE: Test runs overwrite production checkpoints
A test production of S01E01 (titre "Test", dry_run=true, type "standard") overwrote the real checkpoint (titre "La création du monde", type "ouverture", validation_humaine=true). When `continue-production` was called via web dashboard, it loaded the corrupted checkpoint → subprocess crashed → `web_job_id` never persisted → "90 tentatives" error.

**Symptom**: `web_job_id non persisté pour S01E01 après 90 tentatives` — this is ALWAYS a symptom, never the root cause. It means the subprocess crashed before creating a production row in DB. Look at the checkpoint and rapport files to find the real cause.

### How to restore a corrupted checkpoint
When a checkpoint is corrupted (wrong title, wrong type, failed status from test run), manually recreate it:

```json
{
  "episode_id": "S01EXX",
  "etape": "waiting_script",
  "timestamp": "2026-XX-XXTXX:XX:XX.000000",
  "data": {
    "episode_id": "S01EXX",
    "titre": "[EXACT title from saison_01.json]",
    "resume": "[from historique or script]",
    "saison": 1,
    "numero": X,
    "morale": "[from script]",
    "type_episode": "[ouverture|standard|mi-saison|final]",
    "dry_run": false,
    "rapport": {
      "episode_id": "S01EXX",
      "titre": "[same title]",
      "dry_run": false,
      "debut": "[original date]",
      "etapes": {
        "script": {
          "status": "waiting_script",
          "script_path": "/home/user/Podcasts/papy-babou-podcast/scripts/episodes/S01EXX_script.json",
          "score_review": X.X,
          "validation_humaine": true
        }
      },
      "decisions_humaines": []
    },
    "script_path": "/home/user/Podcasts/papy-babou-podcast/scripts/episodes/S01EXX_script.json",
    "pubdate_offset_seconds": [numero * 3600],
    "stop_after": "script"
  }
}
```

**Critical fields**:
- `etape`: must be `"waiting_script"` (not `"erreur"` or `"failed"`)
- `validation_humaine`: must be `true` for audio production to proceed
- `type_episode`: must match the season plan (ouverture for E01, standard for E02-E04/E06-E09, etc.)
- `dry_run`: must be `false` for real production
- `stop_after`: `"script"` if the script was produced with `--stop-after script`
- Also restore `logs/S01EXX_rapport.json` with matching data

### Prevention
- NEVER run test/dry-run productions with the same episode_id as a real production
- If you must test, use a different episode_id (e.g., S99E99)
- Checkpoints are in `.gitignore` — they don't survive git operations. After any git pull/merge, verify checkpoint integrity before launching production

## Custom Cover Art (Session 24)

### How it works
The pipeline now checks for custom cover art BEFORE calling DALL-E:
1. Checks `assets/covers/{episode_id}_cover.png` (also .jpg, .jpeg)
2. If found → uses it directly, no DALL-E call, no OpenAI cost
3. If not found → generates via DALL-E as before
4. Source tracked in `rapport["etapes"]["metadonnees"]["cover_art_source"]`: `"custom"` or `"dalle3"`

### To add a custom cover for an episode
```bash
cp my_cover.png assets/covers/S01EXX_cover.png
```
That's it. The pipeline will detect and use it automatically.

### Files
- `coverepisode2.png` at repo root → copied to `assets/covers/S01E02_cover.png`
- `assets/covers/S01E01_cover.png` — E01 cover (from Session 21)

## Production Workflow — Step by Step (for future sessions)

### Episode Production via Web Dashboard (the CORRECT flow)

**Phase 1 — Script generation** (done in Claude Code session):
1. Generate script via pipeline: `python main.py produire -e "Titre" -s 1 -n X -r "..." -m "..." --auto --stop-after script`
2. Run Audio IA audit: `@audit-episode scripts/episodes/S01EXX_script.json`
3. Apply P0+P1 corrections from audit
4. Verify checkpoint file has correct data (especially `validation_humaine`, `type_episode`, `dry_run: false`)
5. Verify rapport file has matching data

**Phase 2 — Audio production** (via web dashboard):
1. Open web dashboard → navigate to episode → click "Valider le script"
2. This sets `validation_humaine: true` in checkpoint
3. Click "Lancer la production audio" → calls `POST /api/episode/S01EXX/continue-production` with `{"phase": "audio"}`
4. Auto-chaining: audio → SFX → montage (3 separate jobs, each ~10-15 min)
5. Each job saves checkpoint → survives Replit redeploy

**Phase 3 — Publication** (via web dashboard):
1. Listen to montage preview
2. Validate montage → click "Publier"
3. Calls `continue-production` with `{"phase": "publication"}`

### Debugging production failures
1. **Check checkpoint**: `cat checkpoints/S01EXX_checkpoint.json` — is `etape` correct? Is `dry_run: false`? Is `validation_humaine: true`?
2. **Check rapport**: `cat logs/S01EXX_rapport.json` — what's the `status`? Any `erreur`?
3. **Check deployment logs**: The web server logs show subprocess stderr. Look for `[reprendre]` prefix lines.
4. **"web_job_id non persisté"**: This is ALWAYS a symptom. The real error is in the checkpoint/rapport or subprocess stderr.
5. **Restore from Object Storage**: If files are missing after redeploy, they should be auto-restored. If not, check `persistent_storage.py` functions.

### S01E02 Status (Session 24)
- Script: `scripts/episodes/S01E02_script.json` (65 KB, score 9.0/10)
- Audits: SFX + voix + reviewer + copywriter completed
- Cover art: `assets/covers/S01E02_cover.png` (custom, 1.9 MB)
- Checkpoint: `waiting_script`, `validation_humaine: false` (needs web dashboard validation)
- Next step: Validate script via web dashboard → launch audio production

### S01E01 Status (Session 24 — restored)
- Script: `scripts/episodes/S01E01_script.json` (190 segments, 3314 words, 41 SFX, score 9.2/10)
- Cover art: `assets/covers/S01E01_cover.png`
- Checkpoint: RESTORED — `waiting_script`, `validation_humaine: true`, type `ouverture`
- Next step: Launch audio production via web dashboard (`continue-production` phase=audio)

### Git Workflow (Session 24)
- Branch: `claude/episode-2-script-QbSiY`
- Push: `git push -u origin claude/episode-2-script-QbSiY`
