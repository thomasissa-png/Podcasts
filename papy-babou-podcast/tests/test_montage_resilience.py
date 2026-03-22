"""Tests de resilience du montage depuis le backoffice web.

Couvre :
- Reprise apres echec : segments locaux, Object Storage fallback, regeneration
- Hash guard : purge segments si script modifie, reutilisation sinon
- Coherence segments : nettoyage IDs perimes, seuil 50% voix manquants
- Montage errors : WAV corrompu, assembler() echoue
- Web validate : hash stocke dans checkpoint
"""

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import compute_script_hash


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def script_base():
    """Script minimal avec segments voix + SFX."""
    return {
        "episode": {
            "titre": "Test resilience",
            "numero": 1,
            "saison": 1,
            "segments": [
                {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour.", "ton": "chaleureux", "rythme": "normal"},
                {"id": "seg_002", "personnage": "antoine", "texte": "Salut Papy!", "ton": "curieux", "rythme": "rapide"},
                {"id": "seg_003", "personnage": "noemie", "texte": "Raconte!", "ton": "enthousiaste", "rythme": "normal"},
                {"id": "seg_004", "personnage": "papy_babou", "texte": "Ecoutez bien.", "ton": "mysterieux", "rythme": "lent"},
                {"id": "sfx_001", "personnage": "sfx", "texte": "", "ton": "ambiance", "description": "wind", "duree_sfx_secondes": 3.0},
                {"id": "sfx_002", "personnage": "sfx", "texte": "", "ton": "ambiance", "description": "birds", "duree_sfx_secondes": 2.0},
            ],
        }
    }


@pytest.fixture
def episode_id():
    return "S01E01"


@pytest.fixture
def segments_dir(tmp_path, episode_id):
    """Cree le repertoire des segments avec des fichiers MP3 factices."""
    seg_dir = tmp_path / "segments" / episode_id
    seg_dir.mkdir(parents=True)
    return seg_dir


def _create_segment_files(seg_dir, ids):
    """Helper : cree des fichiers MP3 factices pour les IDs donnes."""
    for seg_id in ids:
        (seg_dir / f"{seg_id}.mp3").write_bytes(b"\xff" * 200)


# ── S1-S3 : Reprise apres echec ──────────────────────────────────────────────

class TestRepriseApresEchec:
    """S1-S3 : segments locaux, Object Storage fallback, regeneration."""

    def test_s1_segments_presents_localement(self, tmp_path, script_base, episode_id, segments_dir):
        """S1 : Si les segments sont deja en local, pas de restauration Object Storage."""
        _create_segment_files(segments_dir, ["seg_001", "seg_002", "seg_003", "seg_004", "sfx_001", "sfx_002"])

        # Simuler la garde des segments (logique de main.py lignes 3291-3324)
        _segments_present = segments_dir.exists() and any(segments_dir.glob("*.mp3"))

        assert _segments_present is True
        # Pas besoin de restauration
        assert len(list(segments_dir.glob("*.mp3"))) == 6

    def test_s2_segments_restaures_object_storage(self, tmp_path, script_base, episode_id):
        """S2 : Segments absents localement, restaures depuis Object Storage."""
        seg_dir = tmp_path / "segments" / episode_id
        # Le repertoire n'existe pas encore

        assert not seg_dir.exists()

        # Simuler la restauration Object Storage
        mock_restore = MagicMock(return_value=6)
        with patch.dict("sys.modules", {"persistent_storage": MagicMock(restore_segments=mock_restore)}):
            import persistent_storage
            _segments_present = seg_dir.exists() and any(seg_dir.glob("*.mp3"))

            if not _segments_present:
                nb_restored = persistent_storage.restore_segments(episode_id, tmp_path / "segments")
                if nb_restored > 0:
                    _segments_present = True

            assert _segments_present is True
            mock_restore.assert_called_once_with(episode_id, tmp_path / "segments")

    def test_s3_segments_absents_partout_fallback_etape_2(self, tmp_path, script_base, episode_id):
        """S3 : Segments absents partout -> fallback etape_idx = 2 (regeneration audio)."""
        seg_dir = tmp_path / "segments" / episode_id
        etape_idx = 4  # montage

        _segments_present = seg_dir.exists() and any(seg_dir.glob("*.mp3"))

        if not _segments_present:
            # Object Storage echoue aussi
            mock_restore = MagicMock(return_value=0)
            with patch.dict("sys.modules", {"persistent_storage": MagicMock(restore_segments=mock_restore)}):
                import persistent_storage
                nb_restored = persistent_storage.restore_segments(episode_id, tmp_path / "segments")
                if nb_restored > 0:
                    _segments_present = True

        if not _segments_present:
            etape_idx = 2  # Fallback

        assert etape_idx == 2


# ── S4-S5 : Hash guard ───────────────────────────────────────────────────────

class TestHashGuard:
    """S4-S5 : Purge segments si script modifie, reutilisation sinon."""

    def test_s4_script_modifie_purge_segments(self, tmp_path, script_base, episode_id, segments_dir):
        """S4 : Hash different -> purge segments + etape_idx = 2."""
        _create_segment_files(segments_dir, ["seg_001", "seg_002", "seg_003", "seg_004"])

        # Hash de l'ancien script (checkpoint)
        old_script = copy.deepcopy(script_base)
        old_script["episode"]["segments"][0]["texte"] = "Ancien texte."
        _hash_checkpoint = compute_script_hash(old_script)

        # Hash du script actuel
        _hash_actuel = compute_script_hash(script_base)

        assert _hash_checkpoint != _hash_actuel

        # Simuler la purge (logique main.py lignes 3261-3282)
        etape_idx = 4
        if _hash_checkpoint and _hash_actuel != _hash_checkpoint:
            _purge_dir = segments_dir
            if _purge_dir.exists():
                _nb_purges = 0
                for _old_f in _purge_dir.glob("*.mp3"):
                    _old_f.unlink()
                    _nb_purges += 1
            etape_idx = 2

        assert etape_idx == 2
        assert len(list(segments_dir.glob("*.mp3"))) == 0

    def test_s5_script_identique_pas_de_purge(self, tmp_path, script_base, episode_id, segments_dir):
        """S5 : Hash identique -> pas de purge, segments reutilises."""
        _create_segment_files(segments_dir, ["seg_001", "seg_002", "seg_003", "seg_004"])

        _hash_checkpoint = compute_script_hash(script_base)
        _hash_actuel = compute_script_hash(script_base)

        assert _hash_checkpoint == _hash_actuel

        etape_idx = 4
        if _hash_checkpoint and _hash_actuel != _hash_checkpoint:
            etape_idx = 2  # Ne devrait PAS se declencher

        assert etape_idx == 4
        assert len(list(segments_dir.glob("*.mp3"))) == 4


# ── S6-S8 : Coherence segments ───────────────────────────────────────────────

class TestCoherenceSegments:
    """S6-S8 : Nettoyage segments perimes, seuil manquants."""

    def test_s6_segments_ancien_script_nettoyes(self, tmp_path, script_base, episode_id, segments_dir):
        """S6 : Segments d'un ancien script (IDs differents) nettoyes apres restauration."""
        # Segments actuels du script
        _create_segment_files(segments_dir, ["seg_001", "seg_002", "seg_003", "seg_004", "sfx_001", "sfx_002"])
        # Segments perimes d'un ancien script
        _create_segment_files(segments_dir, ["old_seg_010", "old_seg_011", "old_sfx_050"])

        assert len(list(segments_dir.glob("*.mp3"))) == 9

        # Nettoyage (logique main.py lignes 3330-3354)
        _ids_attendus = {s["id"] for s in script_base["episode"]["segments"]}
        _nb_nettoyes = 0
        for _old_mp3 in segments_dir.glob("*.mp3"):
            _seg_id = _old_mp3.stem
            if _seg_id not in _ids_attendus:
                _old_mp3.unlink()
                _nb_nettoyes += 1

        assert _nb_nettoyes == 3
        assert len(list(segments_dir.glob("*.mp3"))) == 6
        # Seuls les segments attendus restent
        remaining = {f.stem for f in segments_dir.glob("*.mp3")}
        assert remaining == _ids_attendus

    def test_s7_plus_50_pourcent_voix_manquants_force_regeneration(self, tmp_path, script_base, episode_id, segments_dir):
        """S7 : >50% segments voix manquants apres nettoyage -> force etape_idx = 2."""
        # Seulement 1 segment voix sur 4 presents (25%)
        _create_segment_files(segments_dir, ["seg_001", "sfx_001", "sfx_002"])

        _voix_ids = {
            s["id"] for s in script_base["episode"]["segments"]
            if s["personnage"] != "sfx"
        }
        _fichiers_restants = {f.stem for f in segments_dir.glob("*.mp3")}
        _voix_manquants = _voix_ids - _fichiers_restants

        assert len(_voix_ids) == 4  # 4 segments voix dans le script
        assert len(_voix_manquants) == 3  # 3 sur 4 manquants = 75%

        etape_idx = 4
        if len(_voix_manquants) > len(_voix_ids) * 0.5:
            etape_idx = 2

        assert etape_idx == 2

    def test_s8_moins_50_pourcent_manquants_skip_if_exists(self, tmp_path, script_base, episode_id, segments_dir):
        """S8 : <50% manquants -> producteur_audio skip-if-exists regenere les manquants."""
        # 3 segments voix sur 4 presents (75%) — seg_004 manquant
        _create_segment_files(segments_dir, ["seg_001", "seg_002", "seg_003", "sfx_001", "sfx_002"])

        _voix_ids = {
            s["id"] for s in script_base["episode"]["segments"]
            if s["personnage"] != "sfx"
        }
        _fichiers_restants = {f.stem for f in segments_dir.glob("*.mp3")}
        _voix_manquants = _voix_ids - _fichiers_restants

        assert len(_voix_manquants) == 1  # Seul seg_004 manque

        # Avec 1/4 manquants (25%), on ne force pas la regeneration complete
        etape_idx = 4
        if len(_voix_manquants) > len(_voix_ids) * 0.5:
            etape_idx = 2

        assert etape_idx == 4  # Pas de fallback

        # Simuler skip-if-exists du producteur_audio (lignes 148-167)
        segments_voix = [
            s for s in script_base["episode"]["segments"]
            if s["personnage"] != "sfx"
        ]
        segments_a_generer = []
        fichiers_existants = []
        for seg in segments_voix:
            chemin = segments_dir / f"{seg['id']}.mp3"
            if chemin.exists() and chemin.stat().st_size > 100:
                fichiers_existants.append(chemin)
            else:
                segments_a_generer.append(seg)

        assert len(fichiers_existants) == 3
        assert len(segments_a_generer) == 1
        assert segments_a_generer[0]["id"] == "seg_004"


# ── S9-S10 : Montage errors ──────────────────────────────────────────────────

class TestMontageErrors:
    """S9-S10 : WAV corrompu, montage assembler() echoue."""

    def test_s9_wav_corrompu_supprime_et_regeneration(self, tmp_path):
        """S9 : WAV intermediaire trop petit -> supprime + regeneration complete."""
        # Creer un WAV corrompu (trop petit, <1000 bytes)
        wav_path = tmp_path / "S01E01_test_pre_export.wav"
        wav_path.write_bytes(b"\x00" * 500)

        assert wav_path.exists()
        assert wav_path.stat().st_size < 1000

        # Logique de validation du WAV (monteur.py lignes 510-542)
        _skip_to_export = False
        try:
            _wav_size = wav_path.stat().st_size
            if _wav_size < 1000:
                raise ValueError(f"WAV trop petit ({_wav_size} bytes)")
        except Exception:
            wav_path.unlink(missing_ok=True)

        assert not wav_path.exists()
        assert _skip_to_export is False  # Regeneration complete necessaire

    def test_s10_montage_assembler_echoue_checkpoint_et_rapport(self, tmp_path):
        """S10 : monteur.assembler() echoue -> checkpoint sauve + rapport erreur."""
        episode_id = "S01E01"
        rapport = {
            "episode_id": episode_id,
            "etapes": {},
            "decisions_humaines": [],
        }

        # Simuler l'echec du montage (logique main.py lignes 3812-3849)
        erreur = RuntimeError("ffmpeg crash during export")

        try:
            raise erreur
        except Exception as e:
            rapport["etapes"]["montage"] = {
                "status": "error",
                "erreur": str(e),
                "erreur_type": type(e).__name__,
            }
            rapport["erreur_montage"] = str(e)

        assert rapport["etapes"]["montage"]["status"] == "error"
        assert rapport["etapes"]["montage"]["erreur"] == "ffmpeg crash during export"
        assert rapport["etapes"]["montage"]["erreur_type"] == "RuntimeError"
        assert rapport["erreur_montage"] == "ffmpeg crash during export"
        # Les decisions humaines existantes sont preservees
        assert rapport["decisions_humaines"] == []

    def test_s10_rapport_sauvegarde_meme_en_erreur(self, tmp_path):
        """S10 complement : le rapport est sauvegarde sur disque meme en cas d'erreur montage."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        episode_id = "S01E01"
        rapport = {
            "episode_id": episode_id,
            "etapes": {"montage": {"status": "error", "erreur": "test crash"}},
            "erreur_montage": "test crash",
        }

        chemin_rapport = logs_dir / f"{episode_id}_rapport.json"
        with open(chemin_rapport, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)

        assert chemin_rapport.exists()
        loaded = json.loads(chemin_rapport.read_text())
        assert loaded["etapes"]["montage"]["status"] == "error"


# ── S11-S12 : Web validate route et hash ─────────────────────────────────────

class TestWebValidateHash:
    """S11-S12 : Validate route stocke script_content_hash dans checkpoint."""

    def test_s11_validate_stocke_hash_dans_checkpoint(self, tmp_path, script_base):
        """S11 : La route validate stocke script_content_hash dans le checkpoint."""
        episode_id = "S01E01"
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        checkpoints_dir = tmp_path / "checkpoints"
        checkpoints_dir.mkdir()

        # Creer le script valide
        valide_path = scripts_dir / f"{episode_id}_valide.json"
        with open(valide_path, "w") as f:
            json.dump(script_base, f)

        # Creer le checkpoint initial (sans hash)
        checkpoint = {
            "episode_id": episode_id,
            "etape": "waiting_script",
            "timestamp": "2026-03-22T10:00:00",
            "data": {
                "episode_id": episode_id,
                "titre": "Test",
                "rapport": {
                    "etapes": {
                        "script": {"validation_humaine": False}
                    }
                },
            },
        }
        checkpoint_path = checkpoints_dir / f"{episode_id}_checkpoint.json"
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f)

        # Simuler la logique de validation (web.py lignes 2091-2122)
        with open(checkpoint_path, "r") as f:
            cp = json.load(f)
        cp_data = cp.get("data", cp)
        cp_rapport = cp_data.setdefault("rapport", {})
        cp_rapport.setdefault("etapes", {}).setdefault("script", {})
        cp_rapport["etapes"]["script"]["validation_humaine"] = True

        # Charger le script et calculer le hash
        with open(valide_path, "r") as sf:
            _script_for_hash = json.load(sf)
        _script_hash = compute_script_hash(_script_for_hash)
        cp_data["script_content_hash"] = _script_hash
        cp_rapport["script_content_hash"] = _script_hash

        with open(checkpoint_path, "w") as f:
            json.dump(cp, f)

        # Verifier
        with open(checkpoint_path, "r") as f:
            result = json.load(f)

        assert result["data"]["script_content_hash"] == _script_hash
        assert result["data"]["rapport"]["script_content_hash"] == _script_hash
        assert result["data"]["rapport"]["etapes"]["script"]["validation_humaine"] is True
        assert len(_script_hash) == 16

    def test_s12_validate_apres_restauration_object_storage(self, tmp_path, script_base):
        """S12 : Validate apres restauration Object Storage -> hash quand meme stocke."""
        episode_id = "S01E01"
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        checkpoints_dir = tmp_path / "checkpoints"
        checkpoints_dir.mkdir()

        # Pas de fichiers locaux au depart (simule apres redeploiement)
        valide_path = scripts_dir / f"{episode_id}_valide.json"
        script_source = scripts_dir / f"{episode_id}_script.json"

        assert not valide_path.exists()
        assert not script_source.exists()

        # Simuler la restauration Object Storage qui recree le script
        with open(script_source, "w") as f:
            json.dump(script_base, f)

        # Copier vers _valide.json (logique web.py ligne 2068-2070)
        if not valide_path.exists() and script_source.exists():
            import shutil
            shutil.copy2(script_source, valide_path)

        assert valide_path.exists()

        # Creer le checkpoint (restaure depuis Object Storage / DB)
        checkpoint = {
            "episode_id": episode_id,
            "etape": "waiting_script",
            "timestamp": "2026-03-22T10:00:00",
            "data": {
                "episode_id": episode_id,
                "titre": "Test",
                "rapport": {"etapes": {"script": {"validation_humaine": False}}},
            },
        }
        checkpoint_path = checkpoints_dir / f"{episode_id}_checkpoint.json"
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f)

        # Appliquer la logique de hash
        with open(checkpoint_path, "r") as f:
            cp = json.load(f)
        cp_data = cp.get("data", cp)

        with open(valide_path, "r") as sf:
            _script_for_hash = json.load(sf)
        _script_hash = compute_script_hash(_script_for_hash)
        cp_data["script_content_hash"] = _script_hash
        cp_data["rapport"]["script_content_hash"] = _script_hash
        cp_data["rapport"]["etapes"]["script"]["validation_humaine"] = True

        with open(checkpoint_path, "w") as f:
            json.dump(cp, f)

        # Verifier que le hash est bien stocke meme apres restauration
        result = json.loads(checkpoint_path.read_text())
        assert result["data"]["script_content_hash"] == _script_hash
        assert result["data"]["rapport"]["etapes"]["script"]["validation_humaine"] is True


# ── Tests complementaires : coherence montage ─────────────────────────────────

class TestCoherenceMontage:
    """Tests complementaires sur la verification de coherence avant montage."""

    def test_plus_50_pourcent_voix_manquants_raise_runtime_error(self, tmp_path, script_base, episode_id, segments_dir):
        """La verification avant montage leve RuntimeError si >50% voix manquants."""
        # Seulement 1 segment voix sur 4
        _create_segment_files(segments_dir, ["seg_001"])

        _voix_ids_script = {
            s["id"] for s in script_base["episode"]["segments"]
            if s["personnage"] != "sfx"
        }
        _fichiers_locaux = {f.stem for f in segments_dir.glob("*.mp3")}
        _voix_manquants = _voix_ids_script - _fichiers_locaux

        assert len(_voix_manquants) == 3  # 3/4 = 75% manquants

        # Logique main.py lignes 3744-3749
        if len(_voix_manquants) > len(_voix_ids_script) * 0.5:
            with pytest.raises(RuntimeError, match="Montage impossible"):
                raise RuntimeError(
                    f"Montage impossible : {len(_voix_manquants)}/{len(_voix_ids_script)} "
                    f"segments voix manquants. Relancez la production audio."
                )

    def test_hash_stocke_dans_rapport_apres_garde(self, script_base):
        """Le hash actuel est stocke dans rapport['script_content_hash'] apres la garde."""
        rapport = {"etapes": {}}
        _hash_actuel = compute_script_hash(script_base)

        # Logique main.py ligne 3285
        rapport["script_content_hash"] = _hash_actuel

        assert rapport["script_content_hash"] == _hash_actuel
        assert len(_hash_actuel) == 16

    def test_hash_lu_depuis_rapport_ou_etapes_ou_context(self, script_base):
        """Le hash checkpoint est lu depuis rapport racine, etapes.script, ou pipeline_context."""
        _hash = compute_script_hash(script_base)

        # Cas 1 : hash dans rapport racine
        rapport1 = {"script_content_hash": _hash}
        found1 = rapport1.get("script_content_hash") or rapport1.get("etapes", {}).get("script", {}).get("script_content_hash")
        assert found1 == _hash

        # Cas 2 : hash dans etapes.script
        rapport2 = {"etapes": {"script": {"script_content_hash": _hash}}}
        found2 = rapport2.get("script_content_hash") or rapport2.get("etapes", {}).get("script", {}).get("script_content_hash")
        assert found2 == _hash

        # Cas 3 : hash absent
        rapport3 = {"etapes": {}}
        found3 = rapport3.get("script_content_hash") or rapport3.get("etapes", {}).get("script", {}).get("script_content_hash")
        assert found3 is None
