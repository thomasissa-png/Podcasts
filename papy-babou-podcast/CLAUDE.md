# CLAUDE.md — Papy Babou Podcast Production System

## Project Overview

Production pipeline for "Les Histoires de Papy Babou", a French children's podcast (ages 6-10) based on Biblical stories. Supports both episodic and **serial production** (10 episodes/season with arcs, character evolution, rituals, previously-on/teasing).

## Architecture

```
papy-babou-podcast/
├── main.py                  # Orchestrator: pipeline(), CLI commands, historique
├── config.py                # Central config, API keys, rate limiters, season mgmt
├── agents/
│   ├── __init__.py          # Exports all 9 agents
│   ├── scripteur.py         # Script generation (Claude API) — serial-aware
│   ├── reviewer.py          # Script review (Claude API) — type-aware criteria
│   ├── producteur_audio.py  # TTS via ElevenLabs (parallel, per-character voices)
│   ├── sfx_provider.py      # SFX: ElevenLabs → Freesound → silence fallback
│   ├── monteur.py           # Audio assembly: jingles, mixing, LUFS, chapters
│   ├── metadonnees.py       # Metadata generation (Claude API) + transcript
│   ├── publisher.py         # RSS 2.0 feed + iTunes/Podcast Index namespaces
│   ├── cover_art.py         # DALL-E 3 cover art generation
│   └── planificateur.py     # Season planning (Claude API)
├── tests/                   # 172+ tests (pytest)
│   ├── conftest.py          # Fixtures: script_exemple, script_avec_sfx_overlay, review_exemple
│   ├── test_scripteur.py    # Validation, comptage, bible, serial context, structure narrative
│   ├── test_reviewer.py     # Review validation, scoring
│   ├── test_monteur.py      # Slug, assets, assembly, jingles, pan
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

### API Integration
- **Claude (Anthropic)**: Script generation, review, metadata, season planning — all use `config.appel_claude_avec_retry()` with exponential backoff on 429/500/503
- **ElevenLabs**: TTS voices (per-character voice_id) + SFX generation — with `RateLimiter(3/s)` and retry
- **OpenAI DALL-E 3**: Cover art — uses `rate_limiter_openai`
- **Freesound**: SFX fallback

### Checkpoint System
- Saves after each major step: script → audio → sfx → montage → metadonnees
- Data includes: episode_id, titre, resume, saison, numero, morale, **type_episode**, dry_run, rapport
- Resume with `reprendre -c checkpoints/S01E01_checkpoint.json`

### Historique
- JSON file: `historique_episodes.json`
- Each entry: episode_id, titre, morale, resume_court (from segment text, not title), date_production, score_review, personnages_presents, moments_cles, questions_ouvertes, evolutions_personnages, ambiance, type_episode

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

**Expected**: 172+ passed, 3 skipped (integration tests requiring ffmpeg)

## Critical Patterns to Remember

### When modifying scripteur.py
- `type_episode` default is `"standard"` — comparison must be `== "standard"` not `not type_episode`
- `_construire_system_prompt()` accepts: `type_episode`, `contexte_saison`, `episode_plan`, `historique`
- `_valider_structure()` uses `config.personnages_valides()` (dynamic set), not a hardcoded set
- `STRUCTURES_NARRATIVES` dict has templates for all 5 episode types

### When modifying main.py
- `_validation_script()` must receive and pass serial context: `contexte_saison`, `episode_plan`, `type_episode`
- All `sauvegarder_checkpoint()` calls must include `type_episode` in data
- `ajouter_historique()` builds `resume_court` from first 3 segments, not from title
- Pipeline variables (`chemin_hq`, `resultat_montage`, `duree_secondes`, `taille_bytes`, `score`) must be initialized before the step loop for checkpoint resume safety

### When modifying producteur_audio.py
- Secondary characters without voice_id → fallback to narrateur's voice_id
- `max_workers` must be `max(1, min(config, total))` to avoid 0

### When modifying agents calling Claude API
- Always use `config.appel_claude_avec_retry(client, ...)` instead of raw `client.messages.create()`
- This handles rate limiting + retry with backoff on 429/500/502/503/529

### When modifying monteur.py
- Chapter timestamps start at `intro_jingle_ms + 500ms` (not 0)
- `_preparer_fond()` must handle empty AudioSegment (0ms) without division by zero
- `_charger_jingle()` selects jingle by episode type from `config.JINGLES_PAR_TYPE`

### When modifying sfx_provider.py
- Local SFX file paths must be validated: `resolve()` must stay within `SFX_DIR.resolve()`

### When modifying cover_art.py
- Uses `config.rate_limiter_openai` (NOT `rate_limiter_anthropic`)

### When modifying metadonnees.py
- `_generer_transcript()` enriches character names from bible + `.replace("_", " ").title()` fallback

### When modifying publisher.py
- `pubDate` uses `now.timestamp()` (NOT `mktime(now.timetuple())` which has timezone issues)

## Common Pitfalls
- ffmpeg is not available in test environment — mock `AudioSegment.from_mp3` and `silence.export`
- Tests that create audio files must use `write_bytes(b"fake")` + mock
- `config.charger_saison(N)` returns `{}` (not None) when season doesn't exist
- `config.personnages_valides()` returns a set, not a list
- Rate limiters are global singletons — tests should mock them or use monkeypatch
- The `score` variable in pipeline must be initialized before the review loop (checkpoint resume)

## Git Workflow
- Branch: `claude/podcast-production-system-YkngW`
- Push: `git push -u origin claude/podcast-production-system-YkngW`
- Retry on network failure: 4 times with exponential backoff (2s, 4s, 8s, 16s)
