"""Tests pour l'orchestrateur principal."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import (
    charger_historique,
    sauvegarder_historique,
    ajouter_historique,
    sauvegarder_checkpoint,
    charger_checkpoint,
    supprimer_checkpoint,
)


class TestHistorique:
    """Tests du système d'historique inter-épisodes."""

    def test_charger_historique_vide(self, tmp_path, monkeypatch):
        """Sans fichier, l'historique doit être vide."""
        import main
        monkeypatch.setattr(main, "HISTORIQUE_PATH", tmp_path / "historique.json")
        assert charger_historique() == []

    def test_sauvegarder_et_charger_historique(self, tmp_path, monkeypatch):
        """L'historique doit être sauvegardé et rechargé correctement."""
        import main
        chemin = tmp_path / "historique.json"
        monkeypatch.setattr(main, "HISTORIQUE_PATH", chemin)

        historique = [
            {"episode_id": "S01E01", "titre": "Le buisson ardent", "morale": "Confiance"},
        ]
        sauvegarder_historique(historique)

        recharge = charger_historique()
        assert len(recharge) == 1
        assert recharge[0]["titre"] == "Le buisson ardent"

    def test_ajouter_historique(self, tmp_path, monkeypatch):
        """Un épisode ajouté doit apparaître dans l'historique."""
        import main
        chemin = tmp_path / "historique.json"
        monkeypatch.setattr(main, "HISTORIQUE_PATH", chemin)

        rapport = {
            "episode_id": "S01E01",
            "titre": "Le buisson ardent",
            "debut": "2025-01-01T00:00:00",
            "etapes": {"script": {"score_review": 8}},
        }
        script = {
            "episode": {
                "titre": "Le buisson ardent",
                "morale": "La confiance en Dieu",
            }
        }

        ajouter_historique(rapport, script)

        historique = charger_historique()
        assert len(historique) == 1
        assert historique[0]["morale"] == "La confiance en Dieu"
        assert historique[0]["score_review"] == 8


class TestCheckpoints:
    """Tests du système de checkpoints."""

    def test_sauvegarder_checkpoint(self, tmp_path, monkeypatch):
        """Un checkpoint doit être sauvegardé correctement."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        data = {"titre": "Test", "saison": 1, "numero": 1}
        chemin = sauvegarder_checkpoint("S01E01", "audio", data)

        assert chemin.exists()
        with open(chemin, encoding="utf-8") as f:
            cp = json.load(f)
        assert cp["episode_id"] == "S01E01"
        assert cp["etape"] == "audio"
        assert cp["data"]["titre"] == "Test"

    def test_charger_checkpoint(self, tmp_path, monkeypatch):
        """Un checkpoint doit être rechargé correctement."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        data = {"titre": "Test", "saison": 1, "numero": 1}
        chemin = sauvegarder_checkpoint("S01E01", "sfx", data)

        cp = charger_checkpoint(chemin)
        assert cp["etape"] == "sfx"
        assert cp["data"]["titre"] == "Test"

    def test_supprimer_checkpoint(self, tmp_path, monkeypatch):
        """Un checkpoint supprimé ne doit plus exister."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        data = {"titre": "Test", "saison": 1, "numero": 1}
        chemin = sauvegarder_checkpoint("S01E01", "audio", data)
        assert chemin.exists()

        supprimer_checkpoint("S01E01")
        assert not chemin.exists()

    def test_supprimer_checkpoint_inexistant(self, tmp_path, monkeypatch):
        """Supprimer un checkpoint inexistant ne doit pas lever d'erreur."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)
        supprimer_checkpoint("S99E99")  # Ne devrait pas lever d'erreur

    def test_charger_checkpoint_corrompu(self, tmp_path, monkeypatch):
        """Un checkpoint JSON corrompu doit lever une ValueError."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        chemin = tmp_path / "S01E01_checkpoint.json"
        chemin.write_text("{ceci n'est pas du JSON valide}", encoding="utf-8")

        with pytest.raises(ValueError, match="corrompu"):
            charger_checkpoint(chemin)

    def test_charger_checkpoint_champ_manquant(self, tmp_path, monkeypatch):
        """Un checkpoint avec un champ manquant doit lever une ValueError."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        chemin = tmp_path / "S01E01_checkpoint.json"
        chemin.write_text('{"episode_id": "S01E01"}', encoding="utf-8")

        with pytest.raises(ValueError, match="champ manquant"):
            charger_checkpoint(chemin)
