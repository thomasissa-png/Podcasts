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
_lock = threading.Lock()


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
        logger.info("Download Object Storage : %s → %s", storage_key, dest_path)
        return True
    except Exception as e:
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

    Returns:
        Chemin du fichier restauré, ou None si indisponible.
    """
    key = _storage_key(PREFIX_SCRIPT, f"{episode_id}_valide.json")
    dest = dest_dir / f"{episode_id}_valide.json"
    if dest.exists():
        return dest
    if download_file(key, dest):
        return dest
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
