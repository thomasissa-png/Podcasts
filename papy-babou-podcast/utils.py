"""Utilitaires partagés — Parsing JSON, file locking, helpers communs."""

import fcntl
import json
import logging
import re
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


def parser_json_llm(texte_brut: str) -> dict:
    """Parse une réponse LLM en JSON, avec nettoyage automatique.

    Args:
        texte_brut: Réponse brute du LLM.

    Returns:
        Dictionnaire JSON parsé.

    Raises:
        json.JSONDecodeError: Si le JSON est invalide après nettoyage.
    """
    json_str = extraire_json_llm(texte_brut)
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
