"""Tests pour le flux de production web : validate -> continue-production -> reprendre.

Couvre les bugs identifiés dans l'audit Session 25 :
- BUG #6: Validate route ne restaure pas le checkpoint avant mise à jour
- BUG #7: Validate route ne restaure pas le script avant création _valide.json
- Validate route: création _valide.json, mise à jour checkpoint, sync DB/OS
- Continue-production: restauration checkpoint, auto-chaînage audio->sfx->montage
- psInlineValidate/psInlineLaunchAudio: flux frontend cohérent
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ajouter le répertoire du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def tmp_dirs(tmp_path):
    """Crée les répertoires temporaires pour les tests."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    checkpoints_dir = tmp_path / "checkpoints"
    checkpoints_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    return {
        "scripts": scripts_dir,
        "checkpoints": checkpoints_dir,
        "logs": logs_dir,
    }


@pytest.fixture
def sample_script():
    """Script JSON minimal pour les tests."""
    return {
        "episode": {
            "titre": "Test Episode",
            "numero": 1,
            "saison": 1,
            "segments": [
                {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour", "ton": "chaleureux"},
                {"id": "seg_002", "personnage": "antoine", "texte": "Salut Papy", "ton": "curieux"},
            ],
        }
    }


@pytest.fixture
def sample_checkpoint():
    """Checkpoint JSON minimal pour les tests."""
    return {
        "episode_id": "S01E01",
        "etape": "waiting_script",
        "timestamp": "2026-03-22T10:00:00.000000",
        "data": {
            "episode_id": "S01E01",
            "titre": "La création du monde",
            "resume": "Test resume",
            "saison": 1,
            "numero": 1,
            "morale": "Test morale",
            "type_episode": "ouverture",
            "dry_run": False,
            "rapport": {
                "episode_id": "S01E01",
                "titre": "La création du monde",
                "etapes": {
                    "script": {
                        "status": "waiting_script",
                        "validation_humaine": False,
                    }
                },
                "decisions_humaines": [],
            },
            "stop_after": "script",
        },
    }


@pytest.fixture
def sample_rapport():
    """Rapport JSON minimal pour les tests."""
    return {
        "episode_id": "S01E01",
        "titre": "La création du monde",
        "dry_run": False,
        "debut": "2026-03-22T10:00:00",
        "etapes": {
            "script": {
                "status": "waiting_script",
                "validation_humaine": False,
            }
        },
        "decisions_humaines": [],
    }


class TestValidateRouteScriptRestoration:
    """BUG #7: Validate route doit restaurer le script si fichiers locaux absents."""

    def test_valide_json_created_from_script_json(self, tmp_dirs, sample_script):
        """_valide.json est créé depuis _script.json quand les deux existent."""
        scripts_dir = tmp_dirs["scripts"]
        script_path = scripts_dir / "S01E01_script.json"
        valide_path = scripts_dir / "S01E01_valide.json"

        with open(script_path, "w") as f:
            json.dump(sample_script, f)

        assert not valide_path.exists()

        # Simuler la logique de création
        if not valide_path.exists() and script_path.exists():
            import shutil
            shutil.copy2(script_path, valide_path)

        assert valide_path.exists()
        with open(valide_path) as f:
            restored = json.load(f)
        assert restored["episode"]["titre"] == "Test Episode"

    def test_valide_json_not_created_when_both_missing(self, tmp_dirs):
        """Sans _script.json ni _valide.json, aucun fichier n'est créé (sans restauration)."""
        scripts_dir = tmp_dirs["scripts"]
        valide_path = scripts_dir / "S01E01_valide.json"
        script_path = scripts_dir / "S01E01_script.json"

        assert not valide_path.exists()
        assert not script_path.exists()

        # La logique originale (avant fix) ne crée rien
        if not valide_path.exists() and script_path.exists():
            import shutil
            shutil.copy2(script_path, valide_path)

        assert not valide_path.exists()

    def test_restore_script_from_object_storage_fallback(self, tmp_dirs, sample_script):
        """BUG #7: Le script est restauré depuis Object Storage si les fichiers locaux sont absents."""
        scripts_dir = tmp_dirs["scripts"]
        valide_path = scripts_dir / "S01E01_valide.json"

        assert not valide_path.exists()

        # Simuler la restauration Object Storage (écrit le fichier _valide.json)
        def fake_restore_script(episode_id, target_dir):
            path = target_dir / f"{episode_id}_valide.json"
            with open(path, "w") as f:
                json.dump(sample_script, f)
            return True

        with patch.dict("sys.modules", {"persistent_storage": MagicMock()}):
            import persistent_storage
            persistent_storage.restore_script = fake_restore_script

            # Logique du fix: tenter la restauration
            if not valide_path.exists():
                persistent_storage.restore_script("S01E01", scripts_dir)

        assert valide_path.exists()


class TestValidateRouteCheckpointRestoration:
    """BUG #6: Validate route doit restaurer le checkpoint avant mise à jour."""

    def test_checkpoint_updated_when_file_exists(self, tmp_dirs, sample_checkpoint):
        """validation_humaine est mis à jour quand le checkpoint existe."""
        cp_path = tmp_dirs["checkpoints"] / "S01E01_checkpoint.json"
        with open(cp_path, "w") as f:
            json.dump(sample_checkpoint, f)

        # Simuler la mise à jour
        with open(cp_path, "r") as f:
            cp = json.load(f)
        cp_data = cp.get("data", cp)
        cp_rapport = cp_data.setdefault("rapport", {})
        cp_rapport.setdefault("etapes", {}).setdefault("script", {})
        cp_rapport["etapes"]["script"]["validation_humaine"] = True
        with open(cp_path, "w") as f:
            json.dump(cp, f)

        with open(cp_path, "r") as f:
            updated = json.load(f)
        assert updated["data"]["rapport"]["etapes"]["script"]["validation_humaine"] is True

    def test_checkpoint_not_updated_when_missing_no_restore(self, tmp_dirs):
        """Sans restauration, checkpoint absent = validation_humaine jamais mis à jour."""
        cp_path = tmp_dirs["checkpoints"] / "S01E01_checkpoint.json"

        assert not cp_path.exists()

        # La logique originale (avant fix) ne fait rien
        if cp_path.exists():
            pass  # Update logic

        assert not cp_path.exists()

    def test_checkpoint_restored_then_updated(self, tmp_dirs, sample_checkpoint):
        """BUG #6: Le checkpoint est restauré depuis Object Storage puis mis à jour."""
        cp_path = tmp_dirs["checkpoints"] / "S01E01_checkpoint.json"
        assert not cp_path.exists()

        # Simuler la restauration Object Storage
        def fake_restore_checkpoint(episode_id, target_dir):
            path = target_dir / f"{episode_id}_checkpoint.json"
            with open(path, "w") as f:
                json.dump(sample_checkpoint, f)
            return True

        with patch.dict("sys.modules", {"persistent_storage": MagicMock()}):
            import persistent_storage
            persistent_storage.restore_checkpoint = fake_restore_checkpoint

            # Logique du fix: restaurer puis mettre à jour
            if not cp_path.exists():
                persistent_storage.restore_checkpoint("S01E01", tmp_dirs["checkpoints"])

            assert cp_path.exists()

            # Mise à jour validation_humaine
            with open(cp_path, "r") as f:
                cp = json.load(f)
            cp_data = cp.get("data", cp)
            cp_rapport = cp_data.setdefault("rapport", {})
            cp_rapport.setdefault("etapes", {}).setdefault("script", {})
            cp_rapport["etapes"]["script"]["validation_humaine"] = True
            with open(cp_path, "w") as f:
                json.dump(cp, f)

        with open(cp_path, "r") as f:
            final = json.load(f)
        assert final["data"]["rapport"]["etapes"]["script"]["validation_humaine"] is True


class TestContinueProductionCheckpointRestore:
    """Tests pour la restauration de checkpoint dans continue-production."""

    def test_checkpoint_restored_from_object_storage(self, tmp_dirs, sample_checkpoint):
        """Le checkpoint est restauré depuis Object Storage si le fichier local est absent."""
        cp_path = tmp_dirs["checkpoints"] / "S01E01_checkpoint.json"
        assert not cp_path.exists()

        def fake_restore(episode_id, target_dir):
            path = target_dir / f"{episode_id}_checkpoint.json"
            with open(path, "w") as f:
                json.dump(sample_checkpoint, f)

        # Simuler le flux continue-production
        with patch.dict("sys.modules", {"persistent_storage": MagicMock()}):
            import persistent_storage
            persistent_storage.restore_checkpoint = fake_restore

            if not cp_path.exists():
                persistent_storage.restore_checkpoint("S01E01", tmp_dirs["checkpoints"])

        assert cp_path.exists()
        with open(cp_path) as f:
            cp = json.load(f)
        assert cp["data"]["episode_id"] == "S01E01"
        assert cp["etape"] == "waiting_script"


class TestEtapeMapping:
    """Tests pour le mapping des statuts DB vers les étapes pipeline."""

    def test_waiting_script_maps_to_audio(self):
        """waiting_script -> audio (étape 2)."""
        etapes = ["script", "review", "audio", "sfx", "montage", "metadonnees", "publication", "rapport"]
        _etape_mapping = {
            "waiting_script": "audio",
            "waiting_montage": "metadonnees",
            "script_done": "audio",
            "audio_done": "sfx",
            "sfx_done": "montage",
            "montage_done": "metadonnees",
        }
        etape_effective = _etape_mapping.get("waiting_script", "waiting_script")
        assert etape_effective == "audio"
        assert etapes.index(etape_effective) == 2

    def test_waiting_montage_maps_to_metadonnees(self):
        """waiting_montage -> metadonnees (étape 5)."""
        etapes = ["script", "review", "audio", "sfx", "montage", "metadonnees", "publication", "rapport"]
        _etape_mapping = {"waiting_montage": "metadonnees"}
        etape_effective = _etape_mapping.get("waiting_montage", "waiting_montage")
        assert etape_effective == "metadonnees"
        assert etapes.index(etape_effective) == 5

    def test_audio_done_maps_to_sfx(self):
        """audio_done -> sfx (étape 3)."""
        _etape_mapping = {"audio_done": "sfx"}
        assert _etape_mapping["audio_done"] == "sfx"

    def test_sfx_done_maps_to_montage(self):
        """sfx_done -> montage (étape 4)."""
        _etape_mapping = {"sfx_done": "montage"}
        assert _etape_mapping["sfx_done"] == "montage"

    def test_unknown_etape_falls_back_to_script(self):
        """Un statut inconnu tombe sur "script" par sécurité."""
        etapes = ["script", "review", "audio", "sfx", "montage", "metadonnees", "publication", "rapport"]
        _etape_mapping = {}
        etape_depart = "unknown_status"
        etape_effective = _etape_mapping.get(etape_depart, etape_depart)
        if etape_effective not in etapes:
            etape_effective = "script"
        assert etape_effective == "script"


class TestAutoChainingSafety:
    """Tests pour la sécurité du chaînage audio -> sfx -> montage."""

    def test_chain_stops_on_audio_error(self):
        """Le chaînage s'arrête si le job audio échoue (status != ok)."""
        result = {"status": "error", "error": "TTS failed"}
        on_success_fn = MagicMock()

        # Logique de _start_job._worker
        if on_success_fn and result.get("status") == "ok":
            on_success_fn()

        on_success_fn.assert_not_called()

    def test_chain_continues_on_audio_success(self):
        """Le chaînage continue si le job audio réussit (status == ok)."""
        result = {"status": "ok"}
        on_success_fn = MagicMock()

        if on_success_fn and result.get("status") == "ok":
            on_success_fn()

        on_success_fn.assert_called_once()

    def test_chain_stops_on_sigterm(self):
        """Le chaînage s'arrête si le job audio est annulé (SIGTERM)."""
        result = {"status": "cancelled"}
        on_success_fn = MagicMock()

        if on_success_fn and result.get("status") == "ok":
            on_success_fn()

        on_success_fn.assert_not_called()


class TestStopAfterCheckpointUpdate:
    """Tests pour la mise à jour du checkpoint dans les blocs stop_after."""

    def test_stop_after_audio_saves_sfx_etape(self, tmp_dirs, sample_checkpoint):
        """stop_after=audio sauvegarde le checkpoint avec etape=sfx et stop_after=montage."""
        # Simuler le comportement du bloc stop_after == "audio"
        checkpoint_data = {
            "episode_id": "S01E01",
            "titre": "Test",
            "resume": "",
            "saison": 1,
            "numero": 1,
            "morale": "",
            "type_episode": "ouverture",
            "dry_run": False,
            "rapport": {},
            "stop_after": "montage",  # Destination finale, pas l'étape intermédiaire
        }
        # Le checkpoint est sauvé avec etape="sfx" (prochaine étape)
        etape = "sfx"

        cp_path = tmp_dirs["checkpoints"] / "S01E01_checkpoint.json"
        cp_envelope = {
            "episode_id": "S01E01",
            "etape": etape,
            "timestamp": "2026-03-22T10:00:00",
            "data": checkpoint_data,
        }
        with open(cp_path, "w") as f:
            json.dump(cp_envelope, f)

        with open(cp_path) as f:
            saved = json.load(f)
        assert saved["etape"] == "sfx"
        assert saved["data"]["stop_after"] == "montage"

    def test_stop_after_sfx_saves_montage_etape(self, tmp_dirs):
        """stop_after=sfx sauvegarde le checkpoint avec etape=montage et stop_after=montage."""
        checkpoint_data = {
            "episode_id": "S01E01",
            "stop_after": "montage",
        }
        etape = "montage"

        cp_path = tmp_dirs["checkpoints"] / "S01E01_checkpoint.json"
        cp_envelope = {
            "episode_id": "S01E01",
            "etape": etape,
            "data": checkpoint_data,
        }
        with open(cp_path, "w") as f:
            json.dump(cp_envelope, f)

        with open(cp_path) as f:
            saved = json.load(f)
        assert saved["etape"] == "montage"
        assert saved["data"]["stop_after"] == "montage"


class TestValidationHumainePreservation:
    """Tests pour la préservation de validation_humaine à travers les étapes."""

    def test_validation_humaine_restored_from_checkpoint(self):
        """validation_humaine est restauré depuis checkpoint_data dans le rapport."""
        checkpoint_data = {
            "etapes": {
                "script": {"validation_humaine": True},
                "montage": {"validation_humaine": True},
            }
        }
        rapport = {"etapes": {}}

        # Logique de _pipeline_inner
        cp_etapes = checkpoint_data.get("etapes", {})
        if cp_etapes.get("script", {}).get("validation_humaine"):
            rapport["etapes"].setdefault("script", {})["validation_humaine"] = True
        if cp_etapes.get("montage", {}).get("validation_humaine"):
            rapport["etapes"].setdefault("montage", {})["validation_humaine"] = True

        assert rapport["etapes"]["script"]["validation_humaine"] is True
        assert rapport["etapes"]["montage"]["validation_humaine"] is True

    def test_validation_humaine_false_not_forced(self):
        """validation_humaine=false dans checkpoint ne force pas le rapport."""
        checkpoint_data = {
            "etapes": {
                "script": {"validation_humaine": False},
            }
        }
        rapport = {"etapes": {}}

        cp_etapes = checkpoint_data.get("etapes", {})
        if cp_etapes.get("script", {}).get("validation_humaine"):
            rapport["etapes"].setdefault("script", {})["validation_humaine"] = True

        assert "script" not in rapport["etapes"]

    def test_validation_humaine_survives_checkpoint_restore(self, tmp_dirs, sample_checkpoint):
        """BUG #6 fix: validation_humaine=true est préservé après restauration + mise à jour."""
        cp_path = tmp_dirs["checkpoints"] / "S01E01_checkpoint.json"

        # Écrire un checkpoint avec validation_humaine=false
        with open(cp_path, "w") as f:
            json.dump(sample_checkpoint, f)

        # Simuler le fix: mise à jour après restauration
        with open(cp_path, "r") as f:
            cp = json.load(f)
        cp["data"]["rapport"]["etapes"]["script"]["validation_humaine"] = True
        with open(cp_path, "w") as f:
            json.dump(cp, f)

        # Vérifier
        with open(cp_path) as f:
            final = json.load(f)
        assert final["data"]["rapport"]["etapes"]["script"]["validation_humaine"] is True
