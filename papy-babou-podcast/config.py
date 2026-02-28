"""Configuration globale du système de production podcast Papy Babou."""

import json
import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_config_logger = logging.getLogger(__name__)

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
CHECKPOINTS_DIR = BASE_DIR / "checkpoints"
HISTORIQUE_DIR = BASE_DIR / "data"
SAISONS_DIR = HISTORIQUE_DIR / "saisons"
COVERS_DIR = ASSETS_DIR / "covers"
CHAPTERS_DIR = BASE_DIR / "output" / "chapters"
TRANSCRIPTS_DIR = BASE_DIR / "output" / "transcripts"

# Créer les répertoires s'ils n'existent pas
for d in [
    SEGMENTS_DIR, OUTPUT_DIR, SCRIPTS_DIR, LOGS_DIR, RSS_DIR,
    SFX_DIR, SFX_CACHE_DIR, CHECKPOINTS_DIR, HISTORIQUE_DIR, SAISONS_DIR,
    COVERS_DIR, CHAPTERS_DIR, TRANSCRIPTS_DIR,
]:
    d.mkdir(parents=True, exist_ok=True)

# ── Clés API ───────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
BUZZSPROUT_API_KEY = os.getenv("BUZZSPROUT_API_KEY", "")
BUZZSPROUT_PODCAST_ID = os.getenv("BUZZSPROUT_PODCAST_ID", "")
FREESOUND_API_KEY = os.getenv("FREESOUND_API_KEY", "")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def verifier_ffmpeg() -> bool:
    """Vérifie que ffmpeg est disponible dans le PATH.

    Returns:
        True si ffmpeg est trouvé.
    """
    return shutil.which("ffmpeg") is not None


def valider_cles_api(dry_run: bool = False) -> list[str]:
    """Valide que les clés API requises sont configurées.

    Args:
        dry_run: Si True, seules les clés essentielles sont vérifiées.

    Returns:
        Liste des erreurs de configuration (vide si tout est OK).
    """
    erreurs = []

    if not ANTHROPIC_API_KEY:
        erreurs.append(
            "ANTHROPIC_API_KEY non configurée. "
            "Ajoutez-la dans votre fichier .env ou en variable d'environnement."
        )

    if not dry_run:
        if not verifier_ffmpeg():
            erreurs.append(
                "ffmpeg non trouvé. Installez-le : "
                "apt install ffmpeg (Linux) / brew install ffmpeg (macOS)."
            )

        if not ELEVENLABS_API_KEY:
            erreurs.append(
                "ELEVENLABS_API_KEY non configurée. "
                "Requise pour la génération audio (sauf en mode --dry-run)."
            )

        placeholders = [
            (nom, vid) for nom, vid in VOICE_IDS.items()
            if vid == "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"
        ]
        if placeholders:
            noms = ", ".join(n for n, _ in placeholders)
            erreurs.append(
                f"Voice IDs non configurés pour : {noms}. "
                "Configurez les variables ELEVENLABS_VOICE_* dans .env."
            )

    return erreurs


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

# ── Panoramique stéréo par personnage ────────────────────────────────────────
# Valeurs de -1.0 (gauche) à 1.0 (droite), 0.0 = centre

STEREO_PAN = {
    "papy_babou": 0.0,
    "antoine": -0.3,
    "noemie": 0.3,
    "narrateur": 0.0,
    "sfx": 0.0,
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
    "mp3_bitrate_final": "192k",
    "mp3_bitrate_preview": "128k",
    "max_retry_tts": 3,
    "max_secondes_sans_dialogue": 90,
    "max_parallel_tts": 4,
}

# ── Assets audio ──────────────────────────────────────────────────────────────

AUDIO_ASSETS = {
    "fond_doux": ASSETS_DIR / "music" / "fond_doux.mp3",
    "intro_jingle": ASSETS_DIR / "music" / "intro_jingle.mp3",
    "outro_jingle": ASSETS_DIR / "music" / "outro_jingle.mp3",
}

# Jingles variés selon le type d'épisode (fallback vers les jingles standards)
JINGLES_PAR_TYPE = {
    "ouverture": {
        "intro": ASSETS_DIR / "music" / "intro_saison.mp3",
        "outro": ASSETS_DIR / "music" / "outro_jingle.mp3",
    },
    "final": {
        "intro": ASSETS_DIR / "music" / "intro_jingle.mp3",
        "outro": ASSETS_DIR / "music" / "outro_saison.mp3",
    },
}

# ── Multi-ambiances musicales ────────────────────────────────────────────────
# Le scripteur choisit l'ambiance dans le champ "ambiance" du script.
# Si l'asset n'existe pas, on fallback sur "fond_doux".

AMBIANCES_MUSICALES = {
    "joyeux": ASSETS_DIR / "music" / "ambiance_joyeux.mp3",
    "dramatique": ASSETS_DIR / "music" / "ambiance_dramatique.mp3",
    "calme": ASSETS_DIR / "music" / "ambiance_calme.mp3",
    "mystere": ASSETS_DIR / "music" / "ambiance_mystere.mp3",
    "fond_doux": ASSETS_DIR / "music" / "fond_doux.mp3",
}

# ── Configuration SFX (bruitages) ────────────────────────────────────────────

SFX_CONFIG = {
    "sfx_volume_db": -6,
    "sfx_duree_defaut_secondes": 5.0,
    "sfx_duree_max_secondes": 22.0,
    "sfx_fade_ms": 300,
}

# ── Mots interdits (vocabulaire inapproprié pour 6-10 ans) ───────────────────

MOTS_INTERDITS = [
    "tuer", "massacre", "massacrer", "égorger", "assassiner", "meurtre",
    "sang", "sanglant", "ensanglante", "cadavre", "dépouille",
    "enfer", "damnation", "damné", "châtiment éternel",
    "horreur", "horrible", "terrifiant", "terrifier", "cauchemar",
    "mourir", "mort", "mortelle", "agoniser", "agonie",
    "vengeance", "venger", "punition", "punir sévèrement",
    "haine", "haïr", "détester",
    "idiot", "stupide", "imbécile", "crétin",
    "sexuel", "sexualité", "prostitution",
    "alcool", "ivre", "soûl",
    "esclave", "esclavage",
    "torturer", "torture", "supplicier", "supplice",
    "décapiter", "mutiler", "amputer",
]

# ── Bible des personnages ────────────────────────────────────────────────────

PERSONNAGES_JSON_PATH = ASSETS_DIR / "bible" / "personnages.json"


def _db_disponible() -> bool:
    """Vérifie si PostgreSQL est disponible (sans crash si non configuré)."""
    try:
        from database import DATABASE_URL, verifier_connexion
        if not DATABASE_URL:
            return False
        return verifier_connexion()
    except Exception:
        return False


def charger_personnages() -> dict:
    """Charge la bible des personnages (PostgreSQL prioritaire, JSON fallback)."""
    if _db_disponible():
        try:
            from db_models import PersonnageRepo
            bible = PersonnageRepo.charger_bible_complete()
            if bible.get("personnages"):
                # Enrichir avec le fichier JSON local (style_cover_art, décor, etc.)
                if PERSONNAGES_JSON_PATH.exists():
                    with open(PERSONNAGES_JSON_PATH, "r", encoding="utf-8") as f:
                        local = json.load(f)
                    for key in ("decor", "regles_interaction", "style_cover_art"):
                        if key in local:
                            bible[key] = local[key]
                return bible
        except Exception as e:
            _config_logger.warning("DB indisponible pour personnages : %s", e)

    # Fallback fichier JSON
    if PERSONNAGES_JSON_PATH.exists():
        with open(PERSONNAGES_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def ajouter_personnage(
    personnage_id: str,
    data: dict,
    voice_id: str = "",
    pan: float = 0.0,
) -> None:
    """Ajoute un personnage secondaire (DB + fichier JSON pour rétrocompatibilité).

    Args:
        personnage_id: Identifiant unique (ex: 'mamie_rose').
        data: Données du personnage (nom_complet, description, ton, etc.).
        voice_id: ElevenLabs voice ID (optionnel).
        pan: Panoramique stéréo (-1.0 à 1.0).
    """
    # Sauvegarder en DB si disponible
    if _db_disponible():
        try:
            from db_models import PersonnageRepo
            PersonnageRepo.sauvegarder(personnage_id, data, voice_id, pan)
        except Exception as e:
            _config_logger.warning("DB indisponible pour ajout personnage : %s", e)

    # Toujours sauvegarder en JSON (rétrocompatibilité)
    bible = {}
    if PERSONNAGES_JSON_PATH.exists():
        with open(PERSONNAGES_JSON_PATH, "r", encoding="utf-8") as f:
            bible = json.load(f)
    if "personnages" not in bible:
        bible["personnages"] = {}
    bible["personnages"][personnage_id] = data

    with open(PERSONNAGES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(bible, f, ensure_ascii=False, indent=2)

    # Enregistrer la voix et le pan dynamiquement
    if voice_id:
        VOICE_IDS[personnage_id] = voice_id
    if personnage_id not in VOICE_SETTINGS:
        VOICE_SETTINGS[personnage_id] = {
            "stability": 0.70,
            "similarity_boost": 0.80,
            "style": 0.2,
        }
    STEREO_PAN[personnage_id] = pan


def personnages_valides() -> set[str]:
    """Retourne l'ensemble des personnages connus (principaux + secondaires).

    Inclut dynamiquement tous les personnages de la bible.
    """
    base = {"papy_babou", "antoine", "noemie", "narrateur", "sfx"}
    bible = charger_personnages()
    if bible and "personnages" in bible:
        base.update(bible["personnages"].keys())
    return base


# ── Gestion des saisons ──────────────────────────────────────────────────────


def charger_saison(numero: int) -> dict:
    """Charge le plan d'une saison (PostgreSQL prioritaire, JSON fallback).

    Args:
        numero: Numéro de la saison.

    Returns:
        Plan de saison ou dictionnaire vide si inexistant.
    """
    if _db_disponible():
        try:
            from db_models import SaisonRepo
            plan = SaisonRepo.charger(numero)
            if plan:
                return plan
        except Exception as e:
            _config_logger.warning("DB indisponible pour saison %d : %s", numero, e)

    # Fallback fichier JSON
    chemin = SAISONS_DIR / f"saison_{numero:02d}.json"
    if chemin.exists():
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def charger_episode_saison(saison: int, numero: int) -> dict:
    """Charge les données d'un épisode spécifique depuis le plan de saison.

    Args:
        saison: Numéro de la saison.
        numero: Numéro de l'épisode.

    Returns:
        Données de l'épisode ou dictionnaire vide.
    """
    plan = charger_saison(saison)
    if not plan:
        return {}
    for ep in plan.get("saison", {}).get("episodes", []):
        if ep.get("numero") == numero:
            return ep
    return {}


def liste_saisons() -> list[int]:
    """Retourne la liste des numéros de saisons existantes."""
    if _db_disponible():
        try:
            from db_models import SaisonRepo
            nums = SaisonRepo.liste_saisons()
            if nums:
                return nums
        except Exception as e:
            _config_logger.warning("DB indisponible pour liste saisons : %s", e)

    # Fallback fichier JSON
    numeros = []
    for f in SAISONS_DIR.glob("saison_*.json"):
        try:
            num = int(f.stem.split("_")[1])
            numeros.append(num)
        except (IndexError, ValueError):
            pass
    return sorted(numeros)


# ── Formats d'épisodes ───────────────────────────────────────────────────────

FORMATS_EPISODES = {
    "ouverture": {
        "duree_cible_minutes": 15,
        "mots_cible": 1600,
        "description": "Premier épisode de saison — présentation du thème et des enjeux",
    },
    "standard": {
        "duree_cible_minutes": 13,
        "mots_cible": 1400,
        "description": "Épisode classique de la saison",
    },
    "mi-saison": {
        "duree_cible_minutes": 15,
        "mots_cible": 1600,
        "description": "Épisode pivot — tournant dramatique ou récapitulatif",
    },
    "final": {
        "duree_cible_minutes": 18,
        "mots_cible": 1900,
        "description": "Dernier épisode — conclusion de l'arc de saison",
    },
    "bonus": {
        "duree_cible_minutes": 10,
        "mots_cible": 1000,
        "description": "Épisode bonus — Q&R, coulisses, ou récap",
    },
}


# ── Modèle Claude ─────────────────────────────────────────────────────────────

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ── Coûts estimés (pour le suivi budgétaire) ─────────────────────────────────

COUTS = {
    "elevenlabs_par_caractere": 0.000018,   # ~$0.018 / 1000 chars
    "claude_input_par_token": 0.000003,     # $3 / 1M tokens (Sonnet)
    "claude_output_par_token": 0.000015,    # $15 / 1M tokens (Sonnet)
    "openai_dalle3_par_image": 0.040,       # $0.04 / image (1024x1024)
}

# ── Configuration cover art ──────────────────────────────────────────────────

COVER_ART_CONFIG = {
    "enabled": bool(OPENAI_API_KEY),
    "model": "dall-e-3",
    "size": "1024x1024",
    "quality": "standard",
    "style_prefix": (
        "Flat design illustration for children ages 6-10. "
        "Clean geometric shapes with soft rounded corners. "
        "Warm pastel color palette: golden ochre (#D4A054), sky blue (#7BAFD4), "
        "powder pink (#D4869A), olive green (#8BAF6E), warm beige (#F5E6D0), "
        "lavender (#9B8EC4), terracotta (#C47A5A). "
        "Provence countryside atmosphere with golden light. "
        "Minimalist style with bold outlines and flat color fills, no gradients. "
        "Inspired by modern children's book illustrations (Oliver Jeffers, Jon Klassen). "
        "Include a subtle golden frame border evoking an old storybook. "
    ),
}

# ── Rate limiter global ──────────────────────────────────────────────────────


class RateLimiter:
    """Rate limiter à fenêtre glissante pour les appels API.

    Limite le nombre d'appels par seconde pour éviter les erreurs 429.
    Thread-safe pour l'utilisation avec ThreadPoolExecutor.
    """

    def __init__(self, max_par_seconde: float = 5.0):
        self._min_interval = 1.0 / max_par_seconde
        self._lock = threading.Lock()
        self._dernier_appel = 0.0

    def attendre(self) -> None:
        """Attend le temps nécessaire avant le prochain appel."""
        with self._lock:
            maintenant = time.monotonic()
            ecart = maintenant - self._dernier_appel
            if ecart < self._min_interval:
                time.sleep(self._min_interval - ecart)
            self._dernier_appel = time.monotonic()


# Limiteurs globaux (partagés entre agents)
rate_limiter_elevenlabs = RateLimiter(max_par_seconde=3.0)
rate_limiter_anthropic = RateLimiter(max_par_seconde=5.0)
rate_limiter_openai = RateLimiter(max_par_seconde=3.0)


def appel_claude_avec_retry(
    client,
    max_tentatives: int = 3,
    **kwargs,
):
    """Appelle l'API Claude avec retry et backoff exponentiel.

    Args:
        client: Instance anthropic.Anthropic.
        max_tentatives: Nombre maximum de tentatives.
        **kwargs: Arguments passés à client.messages.create().

    Returns:
        Réponse de l'API Claude.

    Raises:
        Exception: Si toutes les tentatives échouent.
    """
    import logging
    import random

    logger = logging.getLogger(__name__)

    for tentative in range(1, max_tentatives + 1):
        try:
            rate_limiter_anthropic.attendre()
            return client.messages.create(**kwargs)
        except Exception as e:
            err_str = str(e)
            is_retryable = any(
                code in err_str for code in ("429", "500", "502", "503", "529", "overloaded")
            )
            if not is_retryable or tentative == max_tentatives:
                raise
            delai = (2 ** tentative) + random.uniform(0, 1)
            logger.warning(
                "API Claude tentative %d/%d échouée (%s) — retry dans %.1fs",
                tentative, max_tentatives, err_str[:80], delai,
            )
            time.sleep(delai)
