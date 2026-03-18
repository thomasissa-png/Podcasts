"""Configuration globale du système de production podcast Papy Babou."""

import json
import logging
import os
import shutil
import sys
import threading
import time
from datetime import datetime
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
PREFERENCES_PATH = HISTORIQUE_DIR / "preferences_producteur.json"
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
    "auteur": os.getenv("PODCAST_AUTEUR", "Les Histoires de Papy Babou"),
    "email_contact": os.getenv("PODCAST_EMAIL", "contact@papybabou.fr"),
    "description": (
        "Des histoires bibliques racontées avec amour par Papy Babou "
        "à ses petits-enfants Antoine et Noémie."
    ),
    "langue": "fr",
    "categorie_itunes": "Kids & Family",
    "sous_categorie": "Stories for Kids",
    "explicit": False,
    "site_web": os.getenv("PODCAST_SITE_WEB", "https://papybabou.fr"),
    "cover_url": os.getenv("PODCAST_COVER_URL", "/assets/artwork/cover.svg"),
}

# Avertir si des valeurs placeholder restent
_PLACEHOLDERS_CONFIG = [
    (k, v) for k, v in PODCAST_CONFIG.items()
    if isinstance(v, str) and v == "À compléter"
]
if _PLACEHOLDERS_CONFIG:
    _config_logger.warning(
        "PODCAST_CONFIG : champs non configurés : %s. "
        "Configurez-les via .env (PODCAST_AUTEUR, PODCAST_EMAIL, etc.) "
        "ou modifiez config.py.",
        ", ".join(k for k, _ in _PLACEHOLDERS_CONFIG),
    )

# ── Voix ElevenLabs ───────────────────────────────────────────────────────────

# Verrou pour les modifications dynamiques des dicts globaux (thread-safety Gunicorn)
_voice_config_lock = threading.Lock()

VOICE_IDS = {
    "papy_babou": os.getenv("ELEVENLABS_VOICE_PAPY", "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"),
    "antoine": os.getenv("ELEVENLABS_VOICE_ANTOINE", "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"),
    "noemie": os.getenv("ELEVENLABS_VOICE_NOEMIE", "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"),
    "mamie_sonia": os.getenv("ELEVENLABS_VOICE_MAMIE_SONIA", "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID"),
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
    "mamie_sonia": {
        "stability": 0.75,
        "similarity_boost": 0.85,
        "style": 0.25,
    },
    "narrateur": {
        "stability": 0.85,
        "similarity_boost": 0.75,
        "style": 0.1,
    },
}

# Ordre de fallback quand un personnage n'a pas de voice_id configuré.
# Le premier voice_id valide trouvé dans cette liste sera utilisé.
VOICE_FALLBACK_CHAIN = ["narrateur", "papy_babou", "antoine", "noemie", "mamie_sonia"]

# ── Panoramique stéréo par personnage ────────────────────────────────────────
# Valeurs de -1.0 (gauche) à 1.0 (droite), 0.0 = centre

STEREO_PAN = {
    "papy_babou": 0.0,
    "antoine": -0.2,
    "noemie": 0.2,
    "mamie_sonia": 0.15,
    "narrateur": 0.0,
    "sfx": 0.0,
}

# ── Gain de normalisation par personnage (dB) ─────────────────────────────────
# Compense les différences de volume entre voix ElevenLabs pour un rendu homogène.
VOICE_GAIN_DB = {
    "papy_babou": 0.0,
    "antoine": 1.5,
    "noemie": 2.0,
    "mamie_sonia": 1.0,
    "narrateur": 0.0,
    "sfx": 0.0,
}

# ── Vitesse vocale par personnage ──────────────────────────────────────────────
# Facteur de vitesse pour ElevenLabs TTS (0.7 = lent, 1.0 = normal, 1.3 = rapide)
# Un grand-père parle plus lentement que des enfants excités.
VOICE_SPEED = {
    "papy_babou": 0.92,    # Grand-père de 66 ans — rythme posé et chaleureux
    "antoine": 1.05,        # Garçon de 9 ans — dynamique
    "noemie": 1.08,         # Fille de 6 ans — enthousiaste et rapide
    "mamie_sonia": 0.95,    # Grand-mère — calme et douce
    "narrateur": 1.0,       # Vitesse standard
}

# ── Voice cloning — IDs des voix clonées (Professional Voice Cloning) ────────
# Si configuré, ces voix sont utilisées à la place des voix standard.
# Pour cloner : utiliser l'API ElevenLabs /v1/voices/add avec des échantillons
# audio d'un comédien professionnel.
VOICE_CLONED_IDS = {
    "papy_babou": os.getenv("ELEVENLABS_CLONED_PAPY", ""),
    "antoine": os.getenv("ELEVENLABS_CLONED_ANTOINE", ""),
    "noemie": os.getenv("ELEVENLABS_CLONED_NOEMIE", ""),
    "mamie_sonia": os.getenv("ELEVENLABS_CLONED_MAMIE_SONIA", ""),
    "narrateur": os.getenv("ELEVENLABS_CLONED_NARRATEUR", ""),
}

# ── Speech Marks (timestamps ElevenLabs) ─────────────────────────────────────
# Active l'endpoint with-timestamps pour obtenir les timestamps mot-par-mot.
# Utile pour : sync SFX, sous-titres, format vidéo/YouTube.
SPEECH_MARKS_ENABLED = os.getenv("SPEECH_MARKS_ENABLED", "false").lower() == "true"

# ── Limites de longueur de segment (mots) pour voix IA ────────────────────────
SEGMENT_MAX_MOTS_ENFANT = 40   # Antoine, Noémie
SEGMENT_MAX_MOTS_ADULTE = 60   # Papy Babou, Mamie Sonia
PERSONNAGES_ENFANTS = {"antoine", "noemie"}

# ── Dictionnaire de prononciation pour noms bibliques ─────────────────────────
# Format : "orthographe" → "prononciation phonétique pour ElevenLabs"
PRONONCIATION_BIBLIQUE = {
    "Nebuchadnezzar": "Né-bu-cad-né-tsar",
    "Nabuchodonosor": "Na-bu-co-do-no-zor",
    "Melchisédech": "Mel-ki-zé-dèk",
    "Béershéba": "Bé-èr-ché-ba",
    "Bethléem": "Bèt-lé-em",
    "Nazareth": "Na-za-rèt",
    "Gethsémani": "Guèt-sé-ma-ni",
    "Golgotha": "Gol-go-ta",
    "Capharnaüm": "Ka-far-na-om",
    "Pharaon": "Fa-ra-on",
    "Moïse": "Mo-ize",
    "Noé": "No-é",
    "Josué": "Jo-zu-é",
    "Ézéchiel": "É-zé-ki-èl",
    "Jéricho": "Jé-ri-ko",
    "Isaïe": "I-za-i",
    "Éphèse": "É-fèze",
    "Canaan": "Ka-na-an",
    "Sinaï": "Si-na-i",
    "Goliath": "Go-li-at",
    "Zachée": "Za-ché",
    "Lazare": "La-zar",
    "Bartimée": "Bar-ti-mé",
    "Caïn": "Ka-in",
    "Abel": "A-bèl",
    "Samson": "Sam-son",
    "Dalila": "Da-li-la",
}

# ── Paramètres de production ──────────────────────────────────────────────────

PRODUCTION = {
    "duree_cible_minutes": 25,
    "mots_cible": 3000,
    "mots_par_minute_enfant": 100,
    "mots_par_minute_adulte": 120,
    "intro_jingle_duree_ms": 10_000,
    "outro_jingle_duree_ms": 8_000,
    "musique_fond_db": -15,
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


def jingles_saison(numero_saison: int) -> dict[str, Path]:
    """Retourne les chemins des jingles custom d'une saison (si définis).

    Cherche dans le plan de saison le champ ``jingles_custom`` qui contient
    les chemins absolus vers les fichiers audio choisis par le producteur.

    Returns:
        Dict ``{"intro_saison": Path, "outro_saison": Path}`` ou dict vide.
    """
    plan = charger_saison(numero_saison)
    custom = plan.get("saison", {}).get("jingles_custom", {})
    result: dict[str, Path] = {}
    for key in ("intro_saison", "outro_saison"):
        chemin_str = custom.get(key)
        if chemin_str:
            chemin = Path(chemin_str)
            if chemin.exists():
                result[key] = chemin
            else:
                _config_logger.warning(
                    "Jingle custom '%s' introuvable : %s", key, chemin,
                )
    return result

# ── Multi-ambiances musicales ────────────────────────────────────────────────
# Le scripteur choisit l'ambiance dans le champ "ambiance" du script.
# Si l'asset n'existe pas, on fallback sur "fond_doux".

AMBIANCES_MUSICALES = {
    "joyeux": ASSETS_DIR / "music" / "ambiance_joyeux.mp3",
    "dramatique": ASSETS_DIR / "music" / "ambiance_dramatique.mp3",
    "calme": ASSETS_DIR / "music" / "ambiance_calme.mp3",
    "mystere": ASSETS_DIR / "music" / "ambiance_mystere.mp3",
    "epique": ASSETS_DIR / "music" / "ambiance_epique.mp3",
    "tendre": ASSETS_DIR / "music" / "ambiance_tendre.mp3",
    "humoristique": ASSETS_DIR / "music" / "ambiance_humoristique.mp3",
    "solennel": ASSETS_DIR / "music" / "ambiance_solennel.mp3",
    "fond_doux": ASSETS_DIR / "music" / "fond_doux.mp3",
}

# Ambiances valides (utilisées par le scripteur et la validation)
AMBIANCES_VALIDES = tuple(k for k in AMBIANCES_MUSICALES if k != "fond_doux")

# ── Configuration SFX (bruitages) ────────────────────────────────────────────

SFX_CONFIG = {
    "sfx_volume_db": -6,  # Legacy — monteur utilise SFX_VOLUME_PAR_TON (contextuel)
    "sfx_duree_defaut_secondes": 5.0,
    "sfx_duree_max_secondes": 22.0,
    "sfx_fade_ms": 300,
}

# ── Bibliothèque SFX curatée ────────────────────────────────────────────────
# Descriptions pré-validées (en anglais pour ElevenLabs) pour les bruitages
# récurrents. Le sfx_provider cherche ici AVANT de générer via l'API.
# Clé = mot-clé français que le scripteur utilise, Valeur = description anglaise.
SFX_CURATES = {
    # ── Maison de Papy Babou ──
    "cheminee": "warm crackling fireplace with occasional wood pops, cozy atmosphere",
    "horloge": "antique grandfather clock ticking slowly, gentle and rhythmic",
    "chat_ronronne": "cat purring softly and contentedly, warm and soothing",
    "pas_bois": "gentle footsteps on old wooden floor, warm creaking",
    "porte_bois": "old wooden door creaking open slowly, warm hinges",
    "pluie_fenetre": "gentle rain on window panes, cozy indoor atmosphere",
    "escalier_bois": "footsteps going up old wooden stairs, gentle creaking",
    "fenetre_ouvre": "window opening to let fresh air in, birds outside",
    "clochette_porte": "small door bell jingling as someone enters",
    "chaise_bois": "wooden chair creaking as someone sits down",
    "bouilloire": "kettle whistling softly, warm kitchen sounds",
    "cuillere_tasse": "spoon stirring in ceramic cup, gentle clinking",
    "bol_pose": "ceramic bowl being placed on wooden table gently",
    "tissu_froisse": "fabric rustling softly, someone adjusting clothes",
    "bruit_cuisine": "gentle kitchen sounds, pots and pans quietly clinking",
    # ── Nature et campagne normande ──
    "oiseaux_jardin": "garden birds singing in the morning, French countryside",
    "vent_arbres": "soft wind through leaves and branches, peaceful",
    "tonnerre_lointain": "distant thunder rumbling softly, not scary",
    "eau_ruisseau": "gentle stream flowing over pebbles, peaceful nature",
    "grillons_nuit": "crickets chirping at night, peaceful summer evening",
    "pluie_douce": "light rain falling on leaves, gentle and calming",
    "orage_lointain": "distant storm with soft thunder, safe indoors feeling",
    # ── Moments familiaux ──
    "rire_enfant": "child laughing happily and warmly, genuine joy",
    "bisou": "gentle kiss on the cheek, sweet and warm",
    "soupir_content": "contented sigh, relaxed and happy",
    "applaudissements": "warm applause from a small family group",
    "gateau_four": "oven door opening with warm bakery atmosphere",
    "bougies_souffle": "birthday candles being blown out with soft cheers",
    "emballage_cadeau": "gift wrapping paper being torn open excitedly",
    "berceuse_fredonnee": "grandmother humming a gentle lullaby quietly",
    "bebe_pleure": "baby crying softly then gradually calming down",
    # ── Bruitages bibliques ──
    "feu_camp": "campfire crackling under the stars, desert night",
    "chevaux_galop": "horses galloping on a dirt road, distant",
    "vagues_douces": "gentle ocean waves lapping on a sandy shore",
    "trompettes_fanfare": "triumphant trumpet fanfare, heroic and bright",
    "epee_metal": "sword being drawn from a sheath, metallic ring",
    "marche_desert": "footsteps trudging through sand in hot desert",
    "foule_marche": "crowd murmuring in an ancient marketplace",
    "ane_brait": "donkey braying in the distance, rural",
    "moutons_bele": "sheep bleating softly in a green field",
    "harpe_celeste": "ethereal harp glissando, heavenly and magical",
    "corne_berger": "shepherd horn echoing across rolling hills",
    "pierres_tombent": "stones falling and tumbling down a rocky cliff",
    "porte_temple": "massive stone temple door opening with reverb",
    "chorale_lointaine": "distant choir singing softly, sacred atmosphere",
    "eclair": "lightning crack followed by distant rolling thunder",
    "puits_eau": "drawing water from a stone well with rope and bucket",
    "chameau": "camel groaning and walking on sand, caravan",
    "marteau_forgeron": "blacksmith hammer hitting metal rhythmically",
    "cloches_eglise": "church bells ringing in the distance, French village",
    "pages_livre": "turning pages of an old book carefully, paper rustling",
}

# ── Mots interdits (vocabulaire inapproprié pour 6-10 ans) ───────────────────

MOTS_INTERDITS = [
    # Violence graphique (contexte violent interdit, pas le concept factuel)
    "massacre", "massacrer", "égorger", "assassiner", "meurtre",
    "sanglant", "ensanglante", "cadavre", "dépouille",
    "enfer", "damnation", "damné", "châtiment éternel",
    "horreur", "horrible", "terrifiant", "terrifier", "cauchemar",
    "agoniser", "agonie",
    # NOTE : "mourir", "mort" sont AUTORISÉS en contexte factuel biblique
    # ("Abraham est mort à 175 ans", "Moïse est mort sur le mont Nébo")
    # Cruauté et vengeance
    "vengeance", "venger", "haine", "haïr",
    # Insultes
    "idiot", "stupide", "imbécile", "crétin",
    # Thèmes adultes
    "sexuel", "sexualité", "prostitution",
    "alcool", "ivre", "soûl",
    # Violence physique graphique
    "torturer", "torture", "supplicier", "supplice",
    "décapiter", "mutiler", "amputer",
    "crever", "lapider", "brûler vif",
    "exterminer", "anéantir",
    "concubine", "fornication",
    # Mots méta interdits dans les dialogues (cassent l'immersion)
    "saison", "épisode", "podcast", "série", "émission",
]

# ── Bible des personnages ────────────────────────────────────────────────────

PERSONNAGES_JSON_PATH = ASSETS_DIR / "bible" / "personnages.json"


def _db_disponible() -> bool:
    """Vérifie si PostgreSQL est disponible (sans crash si non configuré).

    Retente une fois après 1s en cas d'échec (Neon scale-to-zero peut
    mettre quelques secondes à se réveiller après une période d'inactivité).
    """
    import time as _time
    try:
        from database import DATABASE_URL, verifier_connexion
        if not DATABASE_URL:
            return False
        for attempt in range(2):
            try:
                if verifier_connexion():
                    return True
            except Exception:
                pass
            if attempt == 0:
                _time.sleep(1)
        return False
    except ImportError:
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

    # Enregistrer la voix et le pan dynamiquement (thread-safe)
    with _voice_config_lock:
        if voice_id:
            VOICE_IDS[personnage_id] = voice_id
        if personnage_id not in VOICE_SETTINGS:
            VOICE_SETTINGS[personnage_id] = {
                "stability": 0.70,
                "similarity_boost": 0.80,
                "style": 0.2,
            }
        STEREO_PAN[personnage_id] = pan


def configurer_voix(
    personnage_id: str,
    voice_id: str = "",
    pan: float | None = None,
    stability: float | None = None,
    similarity_boost: float | None = None,
    style: float | None = None,
) -> None:
    """Configure la voix et le panoramique d'un personnage existant.

    Persiste les changements en JSON (personnages.json) et met à jour
    les dictionnaires runtime (VOICE_IDS, STEREO_PAN, VOICE_SETTINGS).

    Args:
        personnage_id: Identifiant du personnage.
        voice_id: ElevenLabs voice ID à assigner.
        pan: Panoramique stéréo (-1.0 à 1.0).
        stability: Paramètre TTS stability (0.0–1.0).
        similarity_boost: Paramètre TTS similarity_boost (0.0–1.0).
        style: Paramètre TTS style (0.0–1.0).
    """
    with _voice_config_lock:
        if voice_id:
            VOICE_IDS[personnage_id] = voice_id
        if pan is not None:
            STEREO_PAN[personnage_id] = pan

        # Mettre à jour les VOICE_SETTINGS si des paramètres TTS sont fournis
        if any(v is not None for v in (stability, similarity_boost, style)):
            settings = VOICE_SETTINGS.setdefault(personnage_id, {
                "stability": 0.70,
                "similarity_boost": 0.80,
                "style": 0.2,
            })
            if stability is not None:
                settings["stability"] = stability
            if similarity_boost is not None:
                settings["similarity_boost"] = similarity_boost
            if style is not None:
                settings["style"] = style

    # Persister dans le JSON de la bible des personnages
    bible = {}
    if PERSONNAGES_JSON_PATH.exists():
        with open(PERSONNAGES_JSON_PATH, "r", encoding="utf-8") as f:
            bible = json.load(f)

    perso_data = bible.setdefault("personnages", {}).setdefault(personnage_id, {})
    if voice_id:
        perso_data["voice_id"] = voice_id
    if pan is not None:
        perso_data["pan"] = pan
    if stability is not None or similarity_boost is not None or style is not None:
        voice_settings = perso_data.setdefault("voice_settings", {})
        if stability is not None:
            voice_settings["stability"] = stability
        if similarity_boost is not None:
            voice_settings["similarity_boost"] = similarity_boost
        if style is not None:
            voice_settings["style"] = style

    with open(PERSONNAGES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(bible, f, ensure_ascii=False, indent=2)

    _config_logger.info(
        "Voix configurée pour '%s' : voice_id=%s, pan=%s",
        personnage_id, voice_id or "(inchangé)", pan,
    )


def personnages_valides() -> set[str]:
    """Retourne l'ensemble des personnages connus (principaux + secondaires).

    Inclut dynamiquement tous les personnages de la bible.
    """
    base = {"papy_babou", "antoine", "noemie", "narrateur", "sfx"}
    bible = charger_personnages()
    if bible and "personnages" in bible:
        base.update(bible["personnages"].keys())
    return base


def age_personnage(personnage_id: str, saison: int) -> int | None:
    """Retourne l'âge d'un personnage pour une saison donnée.

    Utilise ``age_par_saison`` si défini, sinon extrapole depuis ``age``
    (âge de base = saison 1) et ajoute automatiquement l'entrée manquante.

    Args:
        personnage_id: Identifiant du personnage.
        saison: Numéro de la saison.

    Returns:
        Âge du personnage pour cette saison, ou None si inconnu.
    """
    bible = charger_personnages()
    perso = bible.get("personnages", {}).get(personnage_id)
    if not perso:
        return None

    ages = perso.get("age_par_saison", {})
    saison_str = str(saison)
    if saison_str in ages:
        return ages[saison_str]

    # Extrapoler : chaque 2 saisons = +1 an (production ~6 mois/saison)
    age_base = perso.get("age")
    if age_base is None:
        return None
    age_calcule = age_base + (saison - 1) // 2
    return age_calcule


# ── Gestion des saisons ──────────────────────────────────────────────────────


def charger_saison(numero: int) -> dict:
    """Charge le plan d'une saison (le plus récent entre DB et fichier JSON).

    Vérifie les deux sources et retourne la plus récente pour éviter que des
    données stale en DB ne masquent un plan fraîchement créé sur le filesystem
    (ou inversement).

    Args:
        numero: Numéro de la saison.

    Returns:
        Plan de saison ou dictionnaire vide si inexistant.
    """
    plan_db = {}
    db_updated_at = None

    if _db_disponible():
        try:
            from db_models import SaisonRepo
            from database import get_cursor
            # Charger plan + timestamp de la dernière version
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT plan_json, updated_at FROM saisons "
                    "WHERE numero = %s AND deleted_at IS NULL "
                    "ORDER BY version DESC LIMIT 1",
                    (numero,),
                )
                row = cur.fetchone()
            if row and row["plan_json"]:
                plan_db = row["plan_json"]
                db_updated_at = row["updated_at"]
        except Exception as e:
            _config_logger.warning("DB indisponible pour saison %d : %s", numero, e)

    # Fichier JSON (restaurer depuis Object Storage si absent)
    plan_fichier = {}
    fichier_mtime = None
    chemin = SAISONS_DIR / f"saison_{numero:02d}.json"
    if not chemin.exists():
        try:
            import persistent_storage
            persistent_storage.restore_saison(numero, SAISONS_DIR)
        except Exception:
            pass
    if chemin.exists():
        try:
            import os
            fichier_mtime = datetime.fromtimestamp(
                os.path.getmtime(chemin),
                tz=datetime.now().astimezone().tzinfo,
            )
            with open(chemin, "r", encoding="utf-8") as f:
                plan_fichier = json.load(f)
        except Exception as e:
            _config_logger.warning("Erreur lecture fichier saison %d : %s", numero, e)

    # Si les deux sources existent, retourner la plus récente
    if plan_db and plan_fichier:
        if db_updated_at and fichier_mtime:
            # Comparer les timestamps — fichier plus récent = fraîchement régénéré
            try:
                if fichier_mtime > db_updated_at:
                    _config_logger.info(
                        "Saison %d : fichier JSON plus récent que DB, utilisation du fichier",
                        numero,
                    )
                    return plan_fichier
            except TypeError:
                pass  # Comparaison impossible (timezone mismatch) → DB par défaut
        return plan_db

    # Une seule source disponible
    return plan_db or plan_fichier or {}


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
    """Retourne la liste des numéros de saisons existantes.

    Fusionne les saisons trouvées en DB ET sur le filesystem pour ne jamais
    perdre une saison créée localement mais pas encore synchronisée en DB.
    """
    numeros: set[int] = set()

    # 1. DB
    if _db_disponible():
        try:
            from db_models import SaisonRepo
            nums = SaisonRepo.liste_saisons()
            if nums:
                numeros.update(nums)
        except Exception as e:
            _config_logger.warning("DB indisponible pour liste saisons : %s", e)

    # 2. Object Storage (restaure les fichiers perdus après redéploiement Replit)
    try:
        import persistent_storage
        if persistent_storage.is_available():
            persistent_storage.restore_all_saisons(SAISONS_DIR)
    except Exception as e:
        _config_logger.debug("Object Storage indisponible pour saisons : %s", e)

    # 3. Fichiers JSON (toujours vérifiés, inclut ceux restaurés depuis Object Storage)
    for f in SAISONS_DIR.glob("saison_*.json"):
        try:
            num = int(f.stem.split("_")[1])
            numeros.add(num)
        except (IndexError, ValueError):
            pass

    return sorted(numeros)


# ── Formats d'épisodes ───────────────────────────────────────────────────────

# ── Périmètre biblique par saison ─────────────────────────────────────────
# Définit le corpus d'histoires autorisées pour chaque saison.
# Injecté automatiquement dans le prompt du planificateur.
PERIMETRES_SAISONS: dict[int, dict[str, str]] = {
    1: {
        "perimetre": "Ancien Testament uniquement — ordre chronologique — UN épisode par personnage biblique",
        "description": (
            "Histoires de l'Ancien Testament exclusivement, dans l'ORDRE "
            "CHRONOLOGIQUE de la Bible. CHAQUE ÉPISODE = UN PERSONNAGE BIBLIQUE DIFFÉRENT. "
            "Exemples de bonne répartition pour 10 épisodes : "
            "La Création du monde → Noé et le Déluge → Abraham et le sacrifice d'Isaac → "
            "Jacob et l'échelle céleste → Joseph vendu par ses frères → "
            "Moïse et le buisson ardent → Josué et les murs de Jéricho → "
            "Samson le colosse → David contre Goliath → Daniel dans la fosse aux lions. "
            "INTERDIT : plusieurs épisodes sur le même personnage (ex: 3 épisodes "
            "sur Moïse ou 2 épisodes sur Joseph). Choisir le moment le PLUS "
            "emblématique de chaque personnage et raconter l'histoire COMPLÈTE en 1 épisode. "
            "AUCUNE histoire du Nouveau Testament. "
            "L'épisode 1 DOIT commencer au début (Genèse) et le dernier "
            "DOIT se situer chronologiquement après tous les précédents."
        ),
    },
    2: {
        "perimetre": "Jésus — de la naissance à la mort — ordre chronologique",
        "description": (
            "La vie de Jésus-Christ dans l'ORDRE CHRONOLOGIQUE : "
            "l'Annonciation → la Nativité → la fuite en Égypte → "
            "l'enfance à Nazareth (Jésus au Temple à 12 ans) → "
            "le baptême par Jean-Baptiste → les premiers disciples → "
            "les miracles (noces de Cana, multiplication des pains, marche sur "
            "l'eau, guérisons, résurrection de Lazare) → les paraboles majeures "
            "(le bon Samaritain, le fils prodigue, les talents) → "
            "l'entrée triomphale à Jérusalem → la Cène → la Passion → "
            "la Crucifixion. "
            "Chaque épisode = un moment clé de la vie de Jésus, "
            "dans l'ordre où il s'est produit."
        ),
    },
    3: {
        "perimetre": "Nouveau Testament (après Jésus) et grands saints — ordre chronologique",
        "description": (
            "Dans l'ORDRE CHRONOLOGIQUE : la Résurrection et l'Ascension → "
            "la Pentecôte → Pierre et la première Église → Étienne le premier "
            "martyr → la conversion de Paul → les voyages missionnaires de Paul → "
            "Philippe et l'eunuque éthiopien → l'Apocalypse de Jean. "
            "Puis les grands saints chrétiens par ordre historique : "
            "Saint Martin (316) → Saint Patrick (385) → Saint François d'Assise "
            "(1181) → Sainte Jeanne d'Arc (1412) → Sainte Thérèse de Lisieux "
            "(1873) → Saint Nicolas, etc. "
            "Chaque épisode = un apôtre, un événement des Actes, ou un grand saint."
        ),
    },
}


# ── Événements spéciaux par saison/épisode ────────────────────────────────
# Clé : (saison, numéro_épisode) → événement spécial à intégrer dans le script
EVENEMENTS_SPECIAUX = {
    (1, 6): {
        "type": "anniversaire",
        "personnage": "noemie",
        "details": (
            "C'est l'anniversaire de Noémie ! Elle a 6 ans aujourd'hui. "
            "Elle demande à Babou une histoire spéciale pour son anniversaire. "
            "Intègre la fête d'anniversaire comme prétexte naturel de l'épisode : "
            "gâteau fait par mamie Sonia, bougies, cadeaux, et Noémie qui demande "
            "une histoire comme cadeau d'anniversaire. Les enfants sont surexcités."
        ),
    },
    (2, 4): {
        "type": "anniversaire",
        "personnage": "antoine",
        "details": (
            "C'est l'anniversaire d'Antoine ! Il a 10 ans aujourd'hui. "
            "Il se sent grand et veut une histoire de 'grand' pour son anniversaire. "
            "Intègre la fête comme prétexte naturel : Antoine est fier d'avoir 10 ans, "
            "il veut une histoire plus épique que d'habitude. Gâteau de mamie Sonia."
        ),
    },
    (1, 10): {
        "type": "naissance",
        "personnage": "lucas",
        "details": (
            "Lucas est né ! C'est le dernier épisode de la saison 1. "
            "Le prénom de Lucas est enfin révélé. Les enfants sont surexcités "
            "d'avoir un petit frère. Papy Babou est ému. C'est un moment "
            "de grande joie familiale qui clôture la saison."
        ),
    },
}

FORMATS_EPISODES = {
    "ouverture": {
        "duree_cible_minutes": 30,
        "mots_cible": 3200,
        "description": "Premier épisode de saison — présentation du thème et des enjeux",
    },
    "standard": {
        "duree_cible_minutes": 25,
        "mots_cible": 3000,
        "description": "Épisode classique de la saison",
    },
    "mi-saison": {
        "duree_cible_minutes": 30,
        "mots_cible": 3200,
        "description": "Épisode pivot — tournant dramatique ou récapitulatif",
    },
    "final": {
        "duree_cible_minutes": 35,
        "mots_cible": 3800,
        "description": "Dernier épisode — conclusion de l'arc de saison",
    },
    "bonus": {
        "duree_cible_minutes": 20,
        "mots_cible": 2000,
        "description": "Épisode bonus — Q&R, coulisses, ou récap",
    },
}


# ── Modèle Claude ─────────────────────────────────────────────────────────────

# ── Seuils de validation post-génération ───────────────────────────────────
RATIO_BIBLIQUE_MINIMUM = 0.60   # Papy Babou doit avoir ≥60% des mots
RATIO_ENFANTS_MIN = 0.25        # Les enfants doivent intervenir dans ≥25% des segments
RATIO_ENFANTS_MAX = 0.45        # Les enfants ne doivent pas dépasser 45% des segments
MAX_PAUSES_EXCESSIVES = 3       # Maximum de pauses > 3s par épisode

# ── Archives de saison ──────────────────────────────────────────────────────
ARCHIVES_DIR = HISTORIQUE_DIR / "archives"
ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# ── Coûts estimés (pour le suivi budgétaire) ─────────────────────────────────

# Tarifs par défaut, surchargeable via env pour suivre les évolutions de prix
COUTS = {
    "elevenlabs_par_caractere": float(os.getenv("COUT_ELEVENLABS_PAR_CHAR", "0.000018")),
    "elevenlabs_sfx_par_generation": float(os.getenv("COUT_ELEVENLABS_SFX", "0.01")),
    "claude_input_par_token": float(os.getenv("COUT_CLAUDE_INPUT", "0.000003")),
    "claude_output_par_token": float(os.getenv("COUT_CLAUDE_OUTPUT", "0.000015")),
    "openai_dalle3_par_image": float(os.getenv("COUT_DALLE3_IMAGE", "0.040")),
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
        attente = 0.0
        with self._lock:
            maintenant = time.monotonic()
            ecart = maintenant - self._dernier_appel
            if ecart < self._min_interval:
                attente = self._min_interval - ecart
            self._dernier_appel = maintenant + attente
        if attente > 0:
            time.sleep(attente)


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
            # Masquer les clés API potentiellement présentes dans l'erreur
            safe_err = err_str
            for secret in (ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, OPENAI_API_KEY):
                if secret and secret in safe_err:
                    safe_err = safe_err.replace(secret, "****")
            is_retryable = any(
                code in err_str for code in ("429", "500", "502", "503", "529", "overloaded")
            )
            if not is_retryable or tentative == max_tentatives:
                raise
            delai = (2 ** tentative) + random.uniform(0, 1)
            logger.warning(
                "API Claude tentative %d/%d échouée (%s) — retry dans %.1fs",
                tentative, max_tentatives, safe_err[:80], delai,
            )
            time.sleep(delai)
