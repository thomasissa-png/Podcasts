"""Utilitaires partagés — Parsing JSON, file locking, helpers communs."""

import fcntl
import hashlib
import json
import logging
import platform
import re
import subprocess
import unicodedata
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


def extraire_json_llm(texte_brut: str) -> str:
    """Extrait le JSON d'une réponse LLM qui peut contenir des backticks markdown.

    Gère les formats courants :
    - JSON pur
    - ```json\\n{...}\\n```
    - ```\\n{...}\\n```
    - Texte avant/après le JSON

    Args:
        texte_brut: Réponse brute du LLM.

    Returns:
        Chaîne JSON nettoyée prête à être parsée.
        Retourne le texte brut si aucun JSON n'est détecté.
    """
    texte = texte_brut.strip()

    # Cas 1 : Blocs de code markdown ```json ... ``` ou ``` ... ```
    match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", texte, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Cas 2 : JSON pur (commence par { ou [)
    if texte.startswith(("{", "[")):
        return texte

    # Cas 3 : Texte avant le JSON — chercher chaque { ou [
    for i, char in enumerate(texte):
        if char in ("{", "["):
            candidate = texte[i:]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

    # Cas 4 : Fallback — ancien comportement (supprimer les lignes ```)
    if "```" in texte:
        lignes = texte.split("\n")
        lignes = [l for l in lignes if not l.strip().startswith("```")]
        return "\n".join(lignes).strip()

    return texte


def reparer_json_llm(json_str: str) -> str:
    """Répare les erreurs JSON courantes générées par les LLM.

    Gère :
    - Virgules finales avant } ou ] (trailing commas)
    - Virgules multiples consécutives

    Args:
        json_str: Chaîne JSON potentiellement malformée.

    Returns:
        Chaîne JSON réparée.
    """
    # Supprimer les trailing commas avant } ou ] (avec espaces/newlines entre)
    repare = re.sub(r",(\s*[}\]])", r"\1", json_str)
    # Supprimer les virgules multiples consécutives (ex: ,,)
    repare = re.sub(r",(\s*,)+", ",", repare)
    return repare


def parser_json_llm(texte_brut: str) -> dict:
    """Parse une réponse LLM en JSON, avec nettoyage et réparation automatique.

    Tente d'abord un parsing direct, puis applique des réparations
    pour les erreurs JSON courantes des LLM (trailing commas, etc.).

    Args:
        texte_brut: Réponse brute du LLM.

    Returns:
        Dictionnaire JSON parsé.

    Raises:
        json.JSONDecodeError: Si le JSON est invalide après nettoyage et réparation.
    """
    json_str = extraire_json_llm(texte_brut)

    # Tentative 1 : parsing direct
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Tentative 2 : réparation des erreurs courantes
    json_repare = reparer_json_llm(json_str)
    try:
        resultat = json.loads(json_repare)
        logger.warning("JSON LLM réparé automatiquement (trailing commas ou erreurs mineures)")
        return resultat
    except json.JSONDecodeError:
        pass

    # Tentative 3 : échec — relancer l'erreur originale pour diagnostic
    return json.loads(json_str)


@contextmanager
def fichier_lock(chemin: Path):
    """Context manager pour verrouiller un fichier (advisory lock).

    Empêche les écritures concurrentes sur le même fichier JSON.

    Usage:
        with fichier_lock(chemin):
            data = json.load(open(chemin))
            data.append(...)
            json.dump(data, open(chemin, 'w'))
    """
    lock_path = chemin.with_suffix(chemin.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def masquer_secret(valeur: str, visible: int = 4) -> str:
    """Masque une clé API ou un secret pour les logs.

    Args:
        valeur: La valeur secrète.
        visible: Nombre de caractères visibles à la fin.

    Returns:
        Chaîne masquée (ex: "****abcd").
    """
    if not valeur or len(valeur) <= visible:
        return "****"
    return "*" * (len(valeur) - visible) + valeur[-visible:]


def ouvrir_fichier(chemin: Path) -> bool:
    """Ouvre un fichier avec l'application par défaut du système.

    Args:
        chemin: Chemin du fichier à ouvrir.

    Returns:
        True si la commande a été lancée avec succès, False sinon.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        logger.warning("Fichier introuvable pour ouverture : %s", chemin)
        return False

    try:
        systeme = platform.system()
        if systeme == "Darwin":
            subprocess.Popen(["open", str(chemin)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif systeme == "Windows":
            os.startfile(str(chemin))
        else:
            # Linux / autres
            subprocess.Popen(["xdg-open", str(chemin)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, FileNotFoundError) as e:
        logger.warning("Impossible d'ouvrir %s : %s", chemin, e)
        return False


def compute_script_hash(script: dict) -> str:
    """Calcule un hash du contenu audio-pertinent d'un script.

    Prend en compte pour chaque segment : id, personnage, texte, ton, rythme.
    Si le script est modifié (même si les IDs ne changent pas), le hash change,
    ce qui force la régénération audio.

    Returns:
        Hash SHA-256 tronqué à 16 caractères hex.
    """
    segments = script.get("episode", {}).get("segments", [])
    h = hashlib.sha256()
    for seg in segments:
        # Champs qui impactent l'audio généré
        h.update(seg.get("id", "").encode("utf-8"))
        h.update(seg.get("personnage", "").encode("utf-8"))
        h.update(seg.get("texte", "").encode("utf-8"))
        h.update(seg.get("ton", "").encode("utf-8"))
        h.update(seg.get("rythme", "").encode("utf-8"))
        # SFX prompts
        h.update(seg.get("description", "").encode("utf-8"))
    return h.hexdigest()[:16]


def slug(texte: str) -> str:
    """Convertit un texte en slug pour nom de fichier.

    Args:
        texte: Texte à convertir (ex: "Le Buisson Ardent").

    Returns:
        Slug ASCII (ex: "le_buisson_ardent").
    """
    texte = unicodedata.normalize("NFKD", texte)
    texte = texte.encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^\w\s-]", "", texte).strip().lower()
    return re.sub(r"[-\s]+", "_", texte)
