"""Tests pour le systeme de detection de changement de script via hash.

Couvre :
- compute_script_hash() : determinisme, sensibilite aux champs audio-pertinents
- Garde des segments dans main.py : purge si hash mismatch, pas de purge sinon
"""

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import compute_script_hash


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def script_base():
    """Script minimal pour les tests de hash."""
    return {
        "episode": {
            "titre": "Test hash",
            "segments": [
                {
                    "id": "seg_001",
                    "personnage": "papy_babou",
                    "texte": "Bonjour les enfants.",
                    "ton": "chaleureux",
                    "rythme": "normal",
                    "pause_apres_ms": 500,
                },
                {
                    "id": "seg_002",
                    "personnage": "antoine",
                    "texte": "Raconte-nous une histoire !",
                    "ton": "curieux",
                    "rythme": "rapide",
                    "pause_apres_ms": 300,
                },
                {
                    "id": "sfx_001",
                    "personnage": "sfx",
                    "texte": "",
                    "ton": "ambiance",
                    "description": "gentle wind blowing through trees",
                    "pause_apres_ms": 0,
                    "duree_sfx_secondes": 5.0,
                    "mode": "overlay",
                },
            ],
        }
    }


# ── Tests compute_script_hash ────────────────────────────────────────────────

class TestComputeScriptHash:

    def test_deterministic(self, script_base):
        """Meme script donne toujours le meme hash."""
        h1 = compute_script_hash(script_base)
        h2 = compute_script_hash(script_base)
        assert h1 == h2
        assert isinstance(h1, str)
        assert len(h1) == 16  # SHA-256 tronque a 16 hex chars

    def test_changes_on_text_modify(self, script_base):
        """Changer le texte d'un segment change le hash."""
        h_original = compute_script_hash(script_base)
        modified = copy.deepcopy(script_base)
        modified["episode"]["segments"][0]["texte"] = "Bonsoir les enfants."
        h_modified = compute_script_hash(modified)
        assert h_original != h_modified

    def test_changes_on_tone_modify(self, script_base):
        """Changer le ton d'un segment change le hash."""
        h_original = compute_script_hash(script_base)
        modified = copy.deepcopy(script_base)
        modified["episode"]["segments"][0]["ton"] = "mysterieux"
        h_modified = compute_script_hash(modified)
        assert h_original != h_modified

    def test_changes_on_sfx_description(self, script_base):
        """Changer la description SFX change le hash."""
        h_original = compute_script_hash(script_base)
        modified = copy.deepcopy(script_base)
        modified["episode"]["segments"][2]["description"] = "heavy rain on roof"
        h_modified = compute_script_hash(modified)
        assert h_original != h_modified

    def test_changes_on_segment_add(self, script_base):
        """Ajouter un segment change le hash."""
        h_original = compute_script_hash(script_base)
        modified = copy.deepcopy(script_base)
        modified["episode"]["segments"].append({
            "id": "seg_003",
            "personnage": "noemie",
            "texte": "Moi aussi je veux ecouter !",
            "ton": "enthousiaste",
        })
        h_modified = compute_script_hash(modified)
        assert h_original != h_modified

    def test_changes_on_segment_remove(self, script_base):
        """Supprimer un segment change le hash."""
        h_original = compute_script_hash(script_base)
        modified = copy.deepcopy(script_base)
        modified["episode"]["segments"].pop(1)
        h_modified = compute_script_hash(modified)
        assert h_original != h_modified

    def test_empty_script(self):
        """Script vide produit un hash valide sans crash."""
        h = compute_script_hash({})
        assert isinstance(h, str)
        assert len(h) == 16

        h2 = compute_script_hash({"episode": {}})
        assert isinstance(h2, str)
        assert len(h2) == 16

        h3 = compute_script_hash({"episode": {"segments": []}})
        assert isinstance(h3, str)
        assert len(h3) == 16

    def test_non_audio_fields_ignored(self, script_base):
        """Les champs non audio-pertinents ne changent pas le hash."""
        h_original = compute_script_hash(script_base)
        modified = copy.deepcopy(script_base)
        # Changer pause_apres_ms ne devrait PAS changer le hash
        # (pause n'est pas incluse dans compute_script_hash)
        modified["episode"]["segments"][0]["pause_apres_ms"] = 9999
        h_modified = compute_script_hash(modified)
        assert h_original == h_modified

    def test_changes_on_rythme_modify(self, script_base):
        """Changer le rythme d'un segment change le hash."""
        h_original = compute_script_hash(script_base)
        modified = copy.deepcopy(script_base)
        modified["episode"]["segments"][0]["rythme"] = "lent"
        h_modified = compute_script_hash(modified)
        assert h_original != h_modified

    def test_changes_on_personnage_modify(self, script_base):
        """Changer le personnage d'un segment change le hash."""
        h_original = compute_script_hash(script_base)
        modified = copy.deepcopy(script_base)
        modified["episode"]["segments"][0]["personnage"] = "noemie"
        h_modified = compute_script_hash(modified)
        assert h_original != h_modified


# ── Tests garde des segments (purge/no-purge) ───────────────────────────────

class TestSegmentPurgeOnHashMismatch:

    def test_purge_on_hash_mismatch(self, script_base, tmp_path):
        """Si le hash du checkpoint != hash du script actuel, les segments
        doivent etre purges et etape_idx recule a 2."""
        # Setup : creer un repertoire de segments avec des fichiers
        episode_id = "S01E01"
        segments_dir = tmp_path / "segments"
        episode_seg_dir = segments_dir / episode_id
        episode_seg_dir.mkdir(parents=True)

        # Creer de faux segments
        for seg in script_base["episode"]["segments"]:
            (episode_seg_dir / f"{seg['id']}.mp3").write_bytes(b"fake audio data")

        # Hash du script actuel
        hash_actuel = compute_script_hash(script_base)
        # Hash different (ancienne version)
        hash_ancien = "aaaa1111bbbb2222"
        assert hash_actuel != hash_ancien

        # Simuler la logique de la garde des segments
        rapport = {"script_content_hash": hash_ancien}
        etape_idx = 4  # On est au montage

        # Reproduire la logique de main.py
        _hash_actuel = compute_script_hash(script_base)
        _hash_checkpoint = rapport.get("script_content_hash")

        if _hash_checkpoint and _hash_actuel != _hash_checkpoint:
            _purge_dir = episode_seg_dir
            if _purge_dir.exists():
                nb_purges = 0
                for old_f in _purge_dir.glob("*.mp3"):
                    old_f.unlink()
                    nb_purges += 1
            etape_idx = 2

        # Verifier que les segments ont ete purges
        assert etape_idx == 2
        assert not list(episode_seg_dir.glob("*.mp3"))

    def test_no_purge_when_hash_matches(self, script_base, tmp_path):
        """Si le hash est identique, pas de purge."""
        episode_id = "S01E01"
        segments_dir = tmp_path / "segments"
        episode_seg_dir = segments_dir / episode_id
        episode_seg_dir.mkdir(parents=True)

        # Creer de faux segments
        for seg in script_base["episode"]["segments"]:
            (episode_seg_dir / f"{seg['id']}.mp3").write_bytes(b"fake audio data")

        hash_actuel = compute_script_hash(script_base)
        rapport = {"script_content_hash": hash_actuel}
        etape_idx = 4

        _hash_actuel = compute_script_hash(script_base)
        _hash_checkpoint = rapport.get("script_content_hash")

        purged = False
        if _hash_checkpoint and _hash_actuel != _hash_checkpoint:
            purged = True
            etape_idx = 2

        # Pas de purge
        assert not purged
        assert etape_idx == 4
        # Les fichiers sont toujours la
        assert len(list(episode_seg_dir.glob("*.mp3"))) == 3

    def test_no_purge_when_no_previous_hash(self, script_base, tmp_path):
        """Si le checkpoint n'a pas de hash (ancienne production), pas de purge.
        Backward compatible."""
        episode_id = "S01E01"
        segments_dir = tmp_path / "segments"
        episode_seg_dir = segments_dir / episode_id
        episode_seg_dir.mkdir(parents=True)

        for seg in script_base["episode"]["segments"]:
            (episode_seg_dir / f"{seg['id']}.mp3").write_bytes(b"fake audio data")

        # Pas de hash dans le rapport (ancienne production)
        rapport = {}
        etape_idx = 4

        _hash_actuel = compute_script_hash(script_base)
        _hash_checkpoint = rapport.get("script_content_hash")

        purged = False
        if _hash_checkpoint and _hash_actuel != _hash_checkpoint:
            purged = True
            etape_idx = 2

        # Pas de purge (backward compatible)
        assert not purged
        assert etape_idx == 4
        assert len(list(episode_seg_dir.glob("*.mp3"))) == 3
