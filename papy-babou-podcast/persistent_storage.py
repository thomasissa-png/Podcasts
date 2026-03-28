"""Stockage persistant des fichiers audio via Replit Object Storage.

Sur Replit, le filesystem local est éphémère (perdu au re-deploy).
Ce module utilise Replit Object Storage pour persister les fichiers
audio MP3, scripts validés, et rapports de production.

Quand Object Storage n'est pas disponible (dev local, tests),
les fonctions sont des no-ops silencieux — le pipeline fonctionne
normalement avec le filesystem local.

Usage :
    from persistent_storage import upload_file, download_file, file_exists

    # Après production audio
    upload_file("audio/S01E01_titre_192k.mp3", local_path)

    # Pour servir depuis le dashboard
    if not local_path.exists() and file_exists(storage_key):
        download_file(storage_key, local_path)
"""

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Initialisation paresseuse du client ──────────────────────────────────────

_client = None
_available: bool | None = None  # None = pas encore testé
_lock = threading.RLock()


def _get_client():
    """Retourne le client Object Storage, ou None si indisponible.

    Thread-safe grâce à un lock. Vérifie la disponibilité réelle en
    tentant une opération (list) plutôt que de se fier au constructeur.
    """
    global _client, _available
    # Fast path sans lock (lecture atomique de bool en CPython)
    if _available is False:
        return None
    if _client is not None:
        return _client
    with _lock:
        # Re-check sous lock (double-checked locking)
        if _available is False:
            return None
        if _client is not None:
            return _client
        try:
            from replit.object_storage import Client
            client = Client()
            # Vérifier que le service est réellement accessible
            # (le constructeur réussit même sans Object Storage)
            client.list(prefix="__ping__")
            _client = client
            _available = True
            logger.info("Replit Object Storage connecté.")
            return _client
        except Exception as e:
            _available = False
            logger.info("Replit Object Storage indisponible : %s (mode local)", e)
            return None


# ── Préfixes de stockage ─────────────────────────────────────────────────────

PREFIX_AUDIO = "audio/"
PREFIX_SCRIPT = "scripts/"
PREFIX_RAPPORT = "rapports/"
PREFIX_SAISON = "saisons/"
PREFIX_CHECKPOINT = "checkpoints/"


def _storage_key(prefix: str, filename: str) -> str:
    """Construit la clé de stockage."""
    return f"{prefix}{filename}"


# ── API publique ─────────────────────────────────────────────────────────────


def upload_file(storage_key: str, local_path: Path) -> bool:
    """Upload un fichier local vers Object Storage.

    Args:
        storage_key: Clé de stockage (ex: "audio/S01E01_titre_192k.mp3").
        local_path: Chemin du fichier local.

    Returns:
        True si l'upload a réussi, False sinon.
    """
    client = _get_client()
    if not client:
        return False
    try:
        client.upload_from_filename(storage_key, str(local_path))
        logger.info("Upload Object Storage : %s (%s)",
                     storage_key, _format_size(local_path))
        return True
    except Exception as e:
        logger.warning("Échec upload Object Storage %s : %s", storage_key, e)
        return False


def download_file(storage_key: str, dest_path: Path) -> bool:
    """Télécharge un fichier depuis Object Storage vers le filesystem local.

    Args:
        storage_key: Clé de stockage.
        dest_path: Chemin de destination local.

    Returns:
        True si le téléchargement a réussi, False sinon.
    """
    client = _get_client()
    if not client:
        return False
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        client.download_to_filename(storage_key, str(dest_path))
        # W12: Vérifier que le fichier n'est pas vide (téléchargement partiel)
        if dest_path.exists() and dest_path.stat().st_size == 0:
            dest_path.unlink(missing_ok=True)
            logger.warning("Download Object Storage %s : fichier vide supprimé", storage_key)
            return False
        logger.info("Download Object Storage : %s → %s", storage_key, dest_path)
        return True
    except Exception as e:
        # W12: Nettoyer le fichier partiel en cas d'erreur
        if dest_path.exists():
            try:
                dest_path.unlink()
            except OSError:
                pass
        logger.debug("Fichier absent dans Object Storage %s : %s", storage_key, e)
        return False


def download_as_bytes(storage_key: str) -> bytes | None:
    """Télécharge un fichier depuis Object Storage comme bytes.

    Args:
        storage_key: Clé de stockage.

    Returns:
        Contenu du fichier en bytes, ou None si indisponible.
    """
    client = _get_client()
    if not client:
        return None
    try:
        return client.download_as_bytes(storage_key)
    except Exception:
        return None


def file_exists(storage_key: str) -> bool:
    """Vérifie si un fichier existe dans Object Storage."""
    client = _get_client()
    if not client:
        return False
    try:
        return client.exists(storage_key)
    except Exception:
        return False


def delete_file(storage_key: str) -> bool:
    """Supprime un fichier depuis Object Storage."""
    client = _get_client()
    if not client:
        return False
    try:
        client.delete(storage_key, ignore_not_found=True)
        logger.info("Supprimé de Object Storage : %s", storage_key)
        return True
    except Exception as e:
        logger.warning("Échec suppression Object Storage %s : %s", storage_key, e)
        return False


def list_files(prefix: str) -> list[str]:
    """Liste les fichiers dans Object Storage avec un préfixe donné.

    Args:
        prefix: Préfixe de recherche (ex: "audio/S01E01").

    Returns:
        Liste des clés de stockage correspondantes.
    """
    client = _get_client()
    if not client:
        return []
    try:
        objects = client.list(prefix=prefix)
        return [obj.name for obj in objects]
    except Exception as e:
        logger.debug("Échec listing Object Storage %s : %s", prefix, e)
        return []


def delete_prefix(prefix: str) -> int:
    """Supprime tous les fichiers avec un préfixe donné. Retourne le nombre supprimé."""
    keys = list_files(prefix)
    deleted = 0
    for key in keys:
        if delete_file(key):
            deleted += 1
    if keys:
        logger.info("delete_prefix(%s) : %d/%d fichiers supprimés", prefix, deleted, len(keys))
    return deleted


def is_available() -> bool:
    """Vérifie si Object Storage est disponible."""
    return _get_client() is not None


# ── Fonctions de haut niveau ─────────────────────────────────────────────────


def upload_episode_audio(episode_id: str, hq_path: Path,
                         preview_path: Path | None = None) -> dict:
    """Upload les fichiers audio d'un épisode vers Object Storage.

    Args:
        episode_id: Identifiant de l'épisode (ex: S01E01).
        hq_path: Chemin du fichier HQ (192k).
        preview_path: Chemin du fichier preview (128k), optionnel.

    Returns:
        Dict avec les clés de stockage {"hq": "audio/...", "preview": "audio/..."}.
    """
    result = {}

    if hq_path and hq_path.exists():
        key = _storage_key(PREFIX_AUDIO, hq_path.name)
        if upload_file(key, hq_path):
            result["hq"] = key

    if preview_path and preview_path.exists():
        key = _storage_key(PREFIX_AUDIO, preview_path.name)
        if upload_file(key, preview_path):
            result["preview"] = key

    return result


def upload_script(episode_id: str, script_path: Path) -> str | None:
    """Upload le script validé vers Object Storage.

    Returns:
        Clé de stockage, ou None si échec.
    """
    if not script_path or not script_path.exists():
        return None
    key = _storage_key(PREFIX_SCRIPT, script_path.name)
    if upload_file(key, script_path):
        return key
    return None


def upload_rapport(episode_id: str, rapport_path: Path) -> str | None:
    """Upload le rapport de production vers Object Storage.

    Returns:
        Clé de stockage, ou None si échec.
    """
    if not rapport_path or not rapport_path.exists():
        return None
    key = _storage_key(PREFIX_RAPPORT, rapport_path.name)
    if upload_file(key, rapport_path):
        return key
    return None


def restore_episode_audio(episode_id: str, dest_dir: Path) -> dict:
    """Restaure les fichiers audio d'un épisode depuis Object Storage.

    Cherche les fichiers audio correspondant à l'episode_id dans
    Object Storage et les télécharge dans dest_dir.

    Args:
        episode_id: Identifiant de l'épisode.
        dest_dir: Répertoire de destination.

    Returns:
        Dict {"hq": Path|None, "preview": Path|None} des fichiers restaurés.
    """
    result = {"hq": None, "preview": None}
    keys = list_files(f"{PREFIX_AUDIO}{episode_id}")

    for key in keys:
        filename = key.removeprefix(PREFIX_AUDIO)
        dest = dest_dir / filename

        # Télécharger si absent localement
        if not dest.exists():
            if not download_file(key, dest):
                continue
            logger.info("Audio restauré : %s", dest)

        # Toujours ajouter au résultat (même si le fichier existait déjà)
        if "_192k.mp3" in filename or "_hq.mp3" in filename:
            result["hq"] = dest
        elif "_128k.mp3" in filename or "_preview.mp3" in filename:
            result["preview"] = dest

    return result


def restore_script(episode_id: str, dest_dir: Path) -> Path | None:
    """Restaure le script validé depuis Object Storage.

    Tente d'abord _valide.json, puis _script.json comme fallback.

    Returns:
        Chemin du fichier restauré, ou None si indisponible.
    """
    # Essayer _valide.json d'abord
    key_valide = _storage_key(PREFIX_SCRIPT, f"{episode_id}_valide.json")
    dest_valide = dest_dir / f"{episode_id}_valide.json"
    if dest_valide.exists():
        return dest_valide
    if download_file(key_valide, dest_valide):
        return dest_valide
    # Fallback : _script.json
    key_script = _storage_key(PREFIX_SCRIPT, f"{episode_id}_script.json")
    dest_script = dest_dir / f"{episode_id}_script.json"
    if dest_script.exists():
        return dest_script
    if download_file(key_script, dest_script):
        logger.info("restore_script: fallback _script.json pour %s", episode_id)
        return dest_script
    return None


def restore_rapport(episode_id: str, dest_dir: Path) -> Path | None:
    """Restaure le rapport de production depuis Object Storage.

    Returns:
        Chemin du fichier restauré, ou None si indisponible.
    """
    key = _storage_key(PREFIX_RAPPORT, f"{episode_id}_rapport.json")
    dest = dest_dir / f"{episode_id}_rapport.json"
    if dest.exists():
        return dest
    if download_file(key, dest):
        return dest
    return None


PREFIX_SEGMENTS = "segments/"
PREFIX_MONTAGE_WAV = "montage_wav/"
PREFIX_METADONNEES = "metadonnees/"
PREFIX_CHAPTERS = "chapters/"
PREFIX_COVERS = "covers/"


def upload_segments(
    episode_id: str,
    segments_dir: Path,
    production_run_id: str | None = None,
) -> int:
    """Upload tous les segments audio d'un épisode vers Object Storage.

    Parcourt le dossier de segments et uploade chaque fichier MP3.

    Args:
        episode_id: Identifiant de l'épisode (ex: S01E01).
        segments_dir: Répertoire racine des segments (config.SEGMENTS_DIR).
        production_run_id: Identifiant de la production (ex: prod_20260324_153042).
            Quand fourni, uploade depuis {segments_dir}/{episode_id}/{production_run_id}/
            vers segments/{episode_id}/{production_run_id}/.
            Quand absent, comportement legacy : {segments_dir}/{episode_id}/ vers
            segments/{episode_id}/.

    Returns:
        Nombre de fichiers uploadés.
    """
    if production_run_id:
        episode_dir = segments_dir / episode_id / production_run_id
        key_prefix = f"{episode_id}/{production_run_id}"
    else:
        episode_dir = segments_dir / episode_id
        key_prefix = episode_id
    if not episode_dir.is_dir():
        return 0
    count = 0
    for mp3_file in episode_dir.glob("*.mp3"):
        key = _storage_key(PREFIX_SEGMENTS, f"{key_prefix}/{mp3_file.name}")
        if upload_file(key, mp3_file):
            count += 1
    if count > 0:
        logger.info("Segments uploadés pour %s : %d fichiers", episode_id, count)
    return count


def restore_segments(
    episode_id: str,
    segments_dir: Path,
    production_run_id: str | None = None,
) -> int:
    """Restaure les segments audio d'un épisode depuis Object Storage.

    Args:
        episode_id: Identifiant de l'épisode.
        segments_dir: Répertoire racine des segments (config.SEGMENTS_DIR).
        production_run_id: Identifiant de la production (ex: prod_20260324_153042).
            Quand fourni, télécharge depuis segments/{episode_id}/{production_run_id}/
            vers {segments_dir}/{episode_id}/{production_run_id}/.
            Quand absent, comportement legacy.

    Returns:
        Nombre de fichiers restaurés.
    """
    if production_run_id:
        prefix = _storage_key(PREFIX_SEGMENTS, f"{episode_id}/{production_run_id}/")
        dest_dir = segments_dir / episode_id / production_run_id
    else:
        prefix = _storage_key(PREFIX_SEGMENTS, f"{episode_id}/")
        dest_dir = segments_dir / episode_id
    keys = list_files(prefix)
    if not keys:
        return 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for key in keys:
        filename = key.split("/")[-1]  # segments/S01E01/prod_xxx/seg_001.mp3 → seg_001.mp3
        dest = dest_dir / filename
        if dest.exists():
            count += 1
            continue
        if download_file(key, dest):
            count += 1
    if count > 0:
        logger.info("Segments restaurés pour %s : %d fichiers", episode_id, count)
    return count


def upload_metadonnees(episode_id: str, meta_path: Path) -> str | None:
    """Upload le fichier métadonnées vers Object Storage.

    Returns:
        Clé de stockage, ou None si échec.
    """
    if not meta_path or not meta_path.exists():
        return None
    key = _storage_key(PREFIX_METADONNEES, meta_path.name)
    if upload_file(key, meta_path):
        return key
    return None


def restore_metadonnees(episode_id: str, dest_dir: Path) -> Path | None:
    """Restaure le fichier métadonnées depuis Object Storage.

    Returns:
        Chemin du fichier restauré, ou None si indisponible.
    """
    key = _storage_key(PREFIX_METADONNEES, f"{episode_id}_meta.json")
    dest = dest_dir / f"{episode_id}_meta.json"
    if dest.exists():
        return dest
    if download_file(key, dest):
        return dest
    return None


def upload_chapters(episode_id: str, chapters_path: Path) -> str | None:
    """Upload le fichier chapitres vers Object Storage.

    Returns:
        Clé de stockage, ou None si échec.
    """
    if not chapters_path or not chapters_path.exists():
        return None
    key = _storage_key(PREFIX_CHAPTERS, chapters_path.name)
    if upload_file(key, chapters_path):
        return key
    return None


def restore_chapters(episode_id: str, dest_dir: Path) -> Path | None:
    """Restaure le fichier chapitres depuis Object Storage.

    Returns:
        Chemin du fichier restauré, ou None si indisponible.
    """
    key = _storage_key(PREFIX_CHAPTERS, f"{episode_id}_chapters.json")
    dest = dest_dir / f"{episode_id}_chapters.json"
    if dest.exists():
        return dest
    if download_file(key, dest):
        return dest
    return None


def upload_cover(episode_id: str, cover_path: Path) -> str | None:
    """Upload le cover art vers Object Storage.

    Returns:
        Clé de stockage, ou None si échec.
    """
    if not cover_path or not cover_path.exists():
        return None
    key = _storage_key(PREFIX_COVERS, cover_path.name)
    if upload_file(key, cover_path):
        return key
    return None


def restore_cover(episode_id: str, dest_dir: Path) -> Path | None:
    """Restaure le cover art depuis Object Storage.

    Cherche PNG puis JPG.

    Returns:
        Chemin du fichier restauré, ou None si indisponible.
    """
    for ext in ("png", "jpg"):
        dest = dest_dir / f"{episode_id}_cover.{ext}"
        if dest.exists():
            return dest
        key = _storage_key(PREFIX_COVERS, f"{episode_id}_cover.{ext}")
        if download_file(key, dest):
            return dest
    return None


def upload_saison(numero: int, saison_path: Path) -> str | None:
    """Upload le plan de saison vers Object Storage.

    Returns:
        Clé de stockage, ou None si échec.
    """
    if not saison_path or not saison_path.exists():
        return None
    key = _storage_key(PREFIX_SAISON, saison_path.name)
    if upload_file(key, saison_path):
        return key
    return None


def restore_saison(numero: int, dest_dir: Path) -> Path | None:
    """Restaure le plan de saison depuis Object Storage.

    Returns:
        Chemin du fichier restauré, ou None si indisponible.
    """
    filename = f"saison_{numero:02d}.json"
    key = _storage_key(PREFIX_SAISON, filename)
    dest = dest_dir / filename
    if dest.exists():
        return dest
    if download_file(key, dest):
        return dest
    return None


def restore_all_saisons(dest_dir: Path) -> list[Path]:
    """Restaure tous les plans de saisons depuis Object Storage.

    Returns:
        Liste des chemins de fichiers restaurés.
    """
    keys = list_files(PREFIX_SAISON)
    restored = []
    for key in keys:
        filename = key.removeprefix(PREFIX_SAISON)
        if not filename.startswith("saison_") or not filename.endswith(".json"):
            continue
        dest = dest_dir / filename
        if dest.exists():
            restored.append(dest)
            continue
        if download_file(key, dest):
            restored.append(dest)
            logger.info("Saison restaurée : %s", dest)
    return restored


def upload_checkpoint(episode_id: str, checkpoint_path: Path) -> str | None:
    """Upload un checkpoint vers Object Storage.

    Returns:
        Clé de stockage, ou None si échec.
    """
    if not checkpoint_path or not checkpoint_path.exists():
        return None
    key = _storage_key(PREFIX_CHECKPOINT, checkpoint_path.name)
    if upload_file(key, checkpoint_path):
        return key
    return None


def restore_checkpoint(episode_id: str, dest_dir: Path) -> Path | None:
    """Restaure un checkpoint depuis Object Storage.

    Returns:
        Chemin du fichier restauré, ou None si indisponible.
    """
    filename = f"{episode_id}_checkpoint.json"
    key = _storage_key(PREFIX_CHECKPOINT, filename)
    dest = dest_dir / filename
    if dest.exists():
        return dest
    if download_file(key, dest):
        return dest
    return None


# ── Utilitaires ──────────────────────────────────────────────────────────────


def _format_size(path: Path) -> str:
    """Formate la taille d'un fichier pour le logging."""
    try:
        size = path.stat().st_size
        if size > 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        return f"{size / 1024:.0f} KB"
    except OSError:
        return "?"
