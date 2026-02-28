"""Configuration globale du système de production podcast Papy Babou."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Chemins du projet ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
AUDIO_DIR = BASE_DIR / "audio"
SEGMENTS_DIR = AUDIO_DIR / "segments"
OUTPUT_DIR = BASE_DIR / "output" / "episodes"
SCRIPTS_DIR = BASE_DIR / "scripts" / "episodes"
LOGS_DIR = BASE_DIR / "logs"
RSS_DIR = BASE_DIR / "rss"
SFX_DIR = ASSETS_DIR / "sfx"
SFX_CACHE_DIR = AUDIO_DIR / "sfx_cache"

# Créer les répertoires s'ils n'existent pas
for d in [SEGMENTS_DIR, OUTPUT_DIR, SCRIPTS_DIR, LOGS_DIR, RSS_DIR, SFX_DIR, SFX_CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Clés API ───────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
BUZZSPROUT_API_KEY = os.getenv("BUZZSPROUT_API_KEY", "")
BUZZSPROUT_PODCAST_ID = os.getenv("BUZZSPROUT_PODCAST_ID", "")
FREESOUND_API_KEY = os.getenv("FREESOUND_API_KEY", "")

# ── Configuration du podcast ──────────────────────────────────────────────────

PODCAST_CONFIG = {
    "titre": "Les Histoires de Papy Babou",
    "auteur": "À compléter",
    "email_contact": "À compléter",
    "description": (
        "Des histoires bibliques racontées avec amour par Papy Babou "
        "à ses petits-enfants Antoine et Noémie."
    ),
    "langue": "fr",
    "categorie_itunes": "Kids & Family",
    "sous_categorie": "Stories for Kids",
    "explicit": False,
    "site_web": "À compléter",
    "cover_url": "À compléter",
}

# ── Voix ElevenLabs ───────────────────────────────────────────────────────────

VOICE_IDS = {
    "papy_babou": os.getenv("ELEVENLABS_VOICE_PAPY", "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"),
    "antoine": os.getenv("ELEVENLABS_VOICE_ANTOINE", "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"),
    "noemie": os.getenv("ELEVENLABS_VOICE_NOEMIE", "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"),
    "narrateur": os.getenv("ELEVENLABS_VOICE_NARRATEUR", "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"),
}

# Paramètres TTS par personnage
VOICE_SETTINGS = {
    "papy_babou": {
        "stability": 0.75,
        "similarity_boost": 0.85,
        "style": 0.2,
    },
    "antoine": {
        "stability": 0.60,
        "similarity_boost": 0.80,
        "style": 0.4,
    },
    "noemie": {
        "stability": 0.65,
        "similarity_boost": 0.80,
        "style": 0.35,
    },
    "narrateur": {
        "stability": 0.85,
        "similarity_boost": 0.75,
        "style": 0.1,
    },
}

# ── Paramètres de production ──────────────────────────────────────────────────

PRODUCTION = {
    "duree_cible_minutes": 13,
    "mots_cible": 1400,
    "mots_par_minute_enfant": 100,
    "mots_par_minute_adulte": 120,
    "intro_jingle_duree_ms": 10_000,
    "outro_jingle_duree_ms": 8_000,
    "musique_fond_db": -20,
    "lufs_cible": -16,
    "mp3_bitrate_final": "320k",
    "mp3_bitrate_preview": "128k",
    "max_retry_tts": 3,
    "max_secondes_sans_dialogue": 90,
}

# ── Assets audio ──────────────────────────────────────────────────────────────

AUDIO_ASSETS = {
    "fond_doux": ASSETS_DIR / "music" / "fond_doux.mp3",
    "intro_jingle": ASSETS_DIR / "music" / "intro_jingle.mp3",
    "outro_jingle": ASSETS_DIR / "music" / "outro_jingle.mp3",
}

# ── Configuration SFX (bruitages) ────────────────────────────────────────────

SFX_CONFIG = {
    "sfx_volume_db": -6,
    "sfx_duree_defaut_secondes": 5.0,
    "sfx_duree_max_secondes": 22.0,
    "sfx_fade_ms": 300,
}

# ── Modèle Claude ─────────────────────────────────────────────────────────────

CLAUDE_MODEL = "claude-sonnet-4-20250514"
