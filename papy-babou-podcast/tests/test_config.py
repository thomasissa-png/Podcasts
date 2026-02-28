"""Tests pour la configuration et la validation des clés API."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


class TestValidationClesAPI:
    """Tests de la validation des clés API au démarrage."""

    def test_valider_sans_anthropic_key(self, monkeypatch):
        """Une clé Anthropic manquante doit retourner une erreur."""
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
        erreurs = config.valider_cles_api(dry_run=False)
        assert any("ANTHROPIC_API_KEY" in e for e in erreurs)

    def test_valider_avec_anthropic_key(self, monkeypatch):
        """Une clé Anthropic présente ne doit pas retourner d'erreur pour cette clé."""
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test-key")
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "el-test-key")
        monkeypatch.setattr(config, "VOICE_IDS", {
            "papy_babou": "voice_123",
            "antoine": "voice_456",
            "noemie": "voice_789",
            "narrateur": "voice_000",
        })
        erreurs = config.valider_cles_api(dry_run=False)
        assert not any("ANTHROPIC_API_KEY" in e for e in erreurs)

    def test_valider_dry_run_sans_elevenlabs(self, monkeypatch):
        """En dry-run, l'absence d'ElevenLabs ne doit PAS être une erreur."""
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        erreurs = config.valider_cles_api(dry_run=True)
        assert not any("ELEVENLABS" in e for e in erreurs)

    def test_valider_production_sans_elevenlabs(self, monkeypatch):
        """En production, l'absence d'ElevenLabs doit être une erreur."""
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        erreurs = config.valider_cles_api(dry_run=False)
        assert any("ELEVENLABS_API_KEY" in e for e in erreurs)

    def test_valider_voice_ids_placeholder(self, monkeypatch):
        """Des Voice IDs placeholder doivent être signalés."""
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "el-test")
        monkeypatch.setattr(config, "VOICE_IDS", {
            "papy_babou": "À_REMPLACER_PAR_ELEVENLABS_VOICE_ID",
        })
        erreurs = config.valider_cles_api(dry_run=False)
        assert any("Voice IDs" in e for e in erreurs)


class TestMotsInterdits:
    """Tests de la liste de mots interdits."""

    def test_mots_interdits_non_vide(self):
        """La liste de mots interdits ne doit pas être vide."""
        assert len(config.MOTS_INTERDITS) > 0

    def test_mots_interdits_contient_violence(self):
        """Les mots violents doivent être dans la liste."""
        assert "tuer" in config.MOTS_INTERDITS
        assert "massacre" in config.MOTS_INTERDITS

    def test_mots_interdits_contient_inapproprie(self):
        """Les mots inappropriés pour enfants doivent être dans la liste."""
        assert "idiot" in config.MOTS_INTERDITS
        assert "stupide" in config.MOTS_INTERDITS


class TestChargerPersonnages:
    """Tests du chargement de la bible des personnages."""

    def test_charger_personnages_fichier_existant(self):
        """La bible doit être chargée depuis le fichier existant."""
        data = config.charger_personnages()
        if config.PERSONNAGES_JSON_PATH.exists():
            assert "personnages" in data
            assert "papy_babou" in data["personnages"]

    def test_charger_personnages_fichier_inexistant(self, monkeypatch):
        """Sans fichier, un dictionnaire vide doit être retourné."""
        monkeypatch.setattr(config, "PERSONNAGES_JSON_PATH", Path("/nonexistent/path.json"))
        data = config.charger_personnages()
        assert data == {}


class TestConfigAmbiances:
    """Tests de la configuration des ambiances musicales."""

    def test_ambiances_definies(self):
        """Les 4 ambiances + fond_doux doivent être définies."""
        assert "joyeux" in config.AMBIANCES_MUSICALES
        assert "dramatique" in config.AMBIANCES_MUSICALES
        assert "calme" in config.AMBIANCES_MUSICALES
        assert "mystere" in config.AMBIANCES_MUSICALES
        assert "fond_doux" in config.AMBIANCES_MUSICALES


class TestConfigStereo:
    """Tests de la configuration stéréo."""

    def test_stereo_pan_defini(self):
        """Le panoramique stéréo doit être défini pour tous les personnages."""
        assert "papy_babou" in config.STEREO_PAN
        assert "antoine" in config.STEREO_PAN
        assert "noemie" in config.STEREO_PAN
        assert "narrateur" in config.STEREO_PAN
        assert "sfx" in config.STEREO_PAN

    def test_stereo_papy_centre(self):
        """Papy Babou doit être au centre."""
        assert config.STEREO_PAN["papy_babou"] == 0.0

    def test_stereo_antoine_gauche(self):
        """Antoine doit être légèrement à gauche."""
        assert config.STEREO_PAN["antoine"] < 0

    def test_stereo_noemie_droite(self):
        """Noémie doit être légèrement à droite."""
        assert config.STEREO_PAN["noemie"] > 0


class TestConfigBitrate:
    """Tests du bitrate."""

    def test_bitrate_final_192k(self):
        """Le bitrate final doit être 192k."""
        assert config.PRODUCTION["mp3_bitrate_final"] == "192k"


class TestVerifierFfmpeg:
    """Tests de la vérification ffmpeg."""

    def test_verifier_ffmpeg_retourne_bool(self):
        """verifier_ffmpeg doit retourner un booléen."""
        result = config.verifier_ffmpeg()
        assert isinstance(result, bool)

    def test_valider_cles_api_ffmpeg_check(self, monkeypatch):
        """En production, ffmpeg absent doit être signalé."""
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "el-test")
        monkeypatch.setattr(config, "VOICE_IDS", {"papy_babou": "v1", "antoine": "v2", "noemie": "v3", "narrateur": "v4"})
        monkeypatch.setattr("config.verifier_ffmpeg", lambda: False)
        erreurs = config.valider_cles_api(dry_run=False)
        assert any("ffmpeg" in e for e in erreurs)

    def test_valider_cles_api_dry_run_pas_ffmpeg(self, monkeypatch):
        """En dry-run, l'absence de ffmpeg ne doit PAS être signalée."""
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
        erreurs = config.valider_cles_api(dry_run=True)
        assert not any("ffmpeg" in e for e in erreurs)


class TestRateLimiter:
    """Tests du rate limiter."""

    def test_rate_limiter_creation(self):
        """Le rate limiter doit s'instancier correctement."""
        rl = config.RateLimiter(max_par_seconde=10.0)
        assert rl._min_interval == pytest.approx(0.1)

    def test_rate_limiter_attendre(self):
        """attendre() ne doit pas crasher."""
        rl = config.RateLimiter(max_par_seconde=100.0)
        rl.attendre()
        rl.attendre()

    def test_rate_limiter_globals_existent(self):
        """Les limiteurs globaux doivent exister."""
        assert hasattr(config, "rate_limiter_elevenlabs")
        assert hasattr(config, "rate_limiter_anthropic")


class TestConfigCouts:
    """Tests de la configuration des coûts."""

    def test_couts_definis(self):
        """Les coûts estimés doivent être définis."""
        assert "elevenlabs_par_caractere" in config.COUTS
        assert "claude_input_par_token" in config.COUTS
        assert "claude_output_par_token" in config.COUTS
        assert "openai_dalle3_par_image" in config.COUTS

    def test_couts_positifs(self):
        """Tous les coûts doivent être positifs."""
        for cle, val in config.COUTS.items():
            assert val > 0, f"Coût {cle} doit être > 0"


class TestCoverArtConfig:
    """Tests de la configuration cover art."""

    def test_cover_art_config_existe(self):
        """La config cover art doit exister."""
        assert hasattr(config, "COVER_ART_CONFIG")
        assert "model" in config.COVER_ART_CONFIG
        assert "size" in config.COVER_ART_CONFIG
        assert "style_prefix" in config.COVER_ART_CONFIG
