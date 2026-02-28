"""Tests pour l'agent SFX Provider."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.sfx_provider import SfxProvider, _slug_sfx


@pytest.fixture
def script_avec_sfx():
    """Script JSON avec des segments SFX pour les tests."""
    return {
        "episode": {
            "titre": "Le buisson ardent",
            "numero": 1,
            "saison": 1,
            "duree_cible_minutes": 13,
            "ambiance": "mystere",
            "morale": "La confiance en Dieu",
            "segments": [
                {
                    "id": "seg_001",
                    "personnage": "narrateur",
                    "texte": "Bienvenue dans Les Histoires de Papy Babou.",
                    "ton": "neutre",
                    "pause_apres_ms": 1000,
                },
                {
                    "id": "sfx_001",
                    "personnage": "sfx",
                    "texte": "vent dans le desert",
                    "ton": "ambiance",
                    "pause_apres_ms": 300,
                    "duree_sfx_secondes": 5.0,
                    "mode": "overlay",
                },
                {
                    "id": "seg_002",
                    "personnage": "papy_babou",
                    "texte": "Ah mes petits loups !",
                    "ton": "chaleureux",
                    "pause_apres_ms": 800,
                },
                {
                    "id": "sfx_002",
                    "personnage": "sfx",
                    "texte": "crepitement de feu",
                    "ton": "ambiance",
                    "pause_apres_ms": 500,
                    "duree_sfx_secondes": 3.0,
                    "mode": "insert",
                },
            ],
        }
    }


class TestSlugSfx:
    """Tests de la fonction slug SFX."""

    def test_slug_simple(self):
        assert _slug_sfx("vent dans le desert") == "vent_dans_le_desert"

    def test_slug_avec_accents(self):
        assert _slug_sfx("bêlement de mouton") == "belement_de_mouton"

    def test_slug_avec_caracteres_speciaux(self):
        result = _slug_sfx("tonnerre !! (grondant)")
        assert "!" not in result
        assert "(" not in result


class TestSfxProviderInit:
    """Tests d'initialisation du SFX Provider."""

    def test_init(self, tmp_path):
        with patch("agents.sfx_provider.config") as mock_config:
            mock_config.ELEVENLABS_API_KEY = "test_key"
            mock_config.FREESOUND_API_KEY = "test_freesound"
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"
            provider = SfxProvider()
            assert provider.elevenlabs_api_key == "test_key"
            assert provider.freesound_api_key == "test_freesound"
            assert provider.cache_dir.exists()


class TestSfxProviderLocalFallback:
    """Tests du fallback vers les fichiers locaux."""

    def test_fichier_local_existant(self, script_avec_sfx, tmp_path):
        """Un SFX trouvé en local doit être copié sans appel API."""
        with patch("agents.sfx_provider.config") as mock_config:
            mock_config.ELEVENLABS_API_KEY = ""
            mock_config.FREESOUND_API_KEY = ""
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"
            mock_config.SFX_DIR = tmp_path / "sfx"
            mock_config.SEGMENTS_DIR = tmp_path / "segments"
            mock_config.PRODUCTION = {"max_retry_tts": 3}
            mock_config.SFX_CONFIG = {"sfx_volume_db": -6, "sfx_fade_ms": 300}

            # Créer un fichier SFX local
            sfx_dir = tmp_path / "sfx"
            sfx_dir.mkdir(parents=True)
            local_file = sfx_dir / "vent dans le desert.mp3"
            local_file.write_bytes(b"fake sfx audio data")

            provider = SfxProvider()
            # Mock _generer_silence to avoid ffmpeg dependency
            with patch.object(provider, "_generer_silence") as mock_silence:
                mock_silence.side_effect = lambda seg, chemin: chemin.write_bytes(b"silence")
                fichiers = provider.produire_sfx(script_avec_sfx)

            # Le premier SFX doit être trouvé en local
            assert provider.stats["sfx_001"] == "local"
            # Le deuxième SFX n'existe pas en local et pas d'API → silence
            assert provider.stats["sfx_002"] == "silence"
            assert len(fichiers) == 2


class TestSfxProviderElevenLabs:
    """Tests de génération via ElevenLabs."""

    @patch("agents.sfx_provider.requests.post")
    def test_generer_elevenlabs_succes(self, mock_post, tmp_path):
        """Un appel ElevenLabs réussi doit sauvegarder le fichier et le cache."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake elevenlabs sfx"
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with patch("agents.sfx_provider.config") as mock_config:
            mock_config.ELEVENLABS_API_KEY = "test_key"
            mock_config.FREESOUND_API_KEY = ""
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"
            mock_config.SFX_DIR = tmp_path / "sfx_empty"
            mock_config.SEGMENTS_DIR = tmp_path / "segments"
            mock_config.PRODUCTION = {"max_retry_tts": 3}

            provider = SfxProvider()
            segment = {
                "id": "sfx_001",
                "personnage": "sfx",
                "texte": "tonnerre grondant",
                "ton": "ambiance",
                "pause_apres_ms": 300,
                "duree_sfx_secondes": 4.0,
                "mode": "insert",
            }
            chemin_sortie = tmp_path / "sfx_001.mp3"
            chemin_cache = tmp_path / "cache" / "tonnerre_grondant.mp3"

            ok = provider._generer_elevenlabs(segment, chemin_sortie, chemin_cache)

            assert ok is True
            assert chemin_sortie.exists()
            assert chemin_cache.exists()
            assert chemin_sortie.read_bytes() == b"fake elevenlabs sfx"

    @patch("agents.sfx_provider.requests.post")
    @patch("agents.sfx_provider.time.sleep")
    @patch("agents.sfx_provider.random.uniform", return_value=0.5)
    def test_generer_elevenlabs_retry_avec_jitter(self, mock_random, mock_sleep, mock_post, tmp_path):
        """En cas d'echec, le retry doit utiliser le jitter."""
        import requests as req

        mock_post.side_effect = [
            req.exceptions.ConnectionError("timeout"),
            MagicMock(
                status_code=200,
                content=b"fake elevenlabs sfx",
                raise_for_status=MagicMock(),
            ),
        ]

        with patch("agents.sfx_provider.config") as mock_config:
            mock_config.ELEVENLABS_API_KEY = "test_key"
            mock_config.FREESOUND_API_KEY = ""
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"
            mock_config.SFX_DIR = tmp_path / "sfx_empty"
            mock_config.PRODUCTION = {"max_retry_tts": 3}

            provider = SfxProvider()
            segment = {
                "id": "sfx_001",
                "personnage": "sfx",
                "texte": "tonnerre",
                "ton": "ambiance",
                "duree_sfx_secondes": 3.0,
                "mode": "insert",
            }
            chemin_sortie = tmp_path / "sfx_001.mp3"
            chemin_cache = tmp_path / "cache" / "tonnerre.mp3"

            ok = provider._generer_elevenlabs(segment, chemin_sortie, chemin_cache)

            assert ok is True
            assert mock_post.call_count == 2
            mock_sleep.assert_called_once()
            delai = mock_sleep.call_args[0][0]
            assert delai > 2  # 2^1 + jitter

    @patch("agents.sfx_provider.requests.post")
    @patch("agents.sfx_provider.time.sleep")
    @patch("agents.sfx_provider.random.uniform", return_value=0.5)
    def test_generer_elevenlabs_retry_echec(self, mock_random, mock_sleep, mock_post, tmp_path):
        """En cas d'echec total, la méthode doit retourner False."""
        import requests as req

        mock_post.side_effect = req.exceptions.ConnectionError("timeout")

        with patch("agents.sfx_provider.config") as mock_config:
            mock_config.ELEVENLABS_API_KEY = "test_key"
            mock_config.FREESOUND_API_KEY = ""
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"
            mock_config.SFX_DIR = tmp_path / "sfx_empty"
            mock_config.PRODUCTION = {"max_retry_tts": 2}

            provider = SfxProvider()
            segment = {
                "id": "sfx_001",
                "personnage": "sfx",
                "texte": "tonnerre",
                "ton": "ambiance",
                "duree_sfx_secondes": 3.0,
            }
            chemin_sortie = tmp_path / "sfx_001.mp3"
            chemin_cache = tmp_path / "cache" / "tonnerre.mp3"

            ok = provider._generer_elevenlabs(segment, chemin_sortie, chemin_cache)

            assert ok is False
            assert mock_post.call_count == 2


class TestSfxProviderFreesound:
    """Tests du fallback Freesound."""

    @patch("agents.sfx_provider.requests.get")
    def test_telecharger_freesound_succes(self, mock_get, tmp_path):
        """Un téléchargement Freesound réussi doit sauvegarder le fichier."""
        search_response = MagicMock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "results": [
                {
                    "id": 12345,
                    "name": "thunder.mp3",
                    "previews": {
                        "preview-hq-mp3": "https://freesound.org/preview/12345.mp3",
                    },
                    "license": "Creative Commons 0",
                }
            ]
        }
        search_response.raise_for_status = MagicMock()

        download_response = MagicMock()
        download_response.status_code = 200
        download_response.content = b"fake freesound audio"
        download_response.raise_for_status = MagicMock()

        mock_get.side_effect = [search_response, download_response]

        with patch("agents.sfx_provider.config") as mock_config:
            mock_config.ELEVENLABS_API_KEY = ""
            mock_config.FREESOUND_API_KEY = "test_freesound_key"
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"
            mock_config.SFX_DIR = tmp_path / "sfx_empty"
            mock_config.PRODUCTION = {"max_retry_tts": 3}

            provider = SfxProvider()
            segment = {
                "id": "sfx_001",
                "personnage": "sfx",
                "texte": "tonnerre",
                "ton": "ambiance",
                "duree_sfx_secondes": 5.0,
            }
            chemin_sortie = tmp_path / "sfx_001.mp3"
            chemin_cache = tmp_path / "cache" / "tonnerre.mp3"

            ok = provider._telecharger_freesound(segment, chemin_sortie, chemin_cache)

            assert ok is True
            assert chemin_sortie.exists()
            assert chemin_sortie.read_bytes() == b"fake freesound audio"

    @patch("agents.sfx_provider.requests.get")
    def test_telecharger_freesound_aucun_resultat(self, mock_get, tmp_path):
        """Aucun résultat Freesound doit retourner False."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch("agents.sfx_provider.config") as mock_config:
            mock_config.FREESOUND_API_KEY = "test_key"
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"
            mock_config.SFX_DIR = tmp_path / "sfx_empty"
            mock_config.PRODUCTION = {"max_retry_tts": 3}

            provider = SfxProvider()
            segment = {
                "id": "sfx_001",
                "personnage": "sfx",
                "texte": "son_introuvable_xyz",
                "ton": "ambiance",
                "duree_sfx_secondes": 3.0,
            }
            chemin_sortie = tmp_path / "sfx_001.mp3"
            chemin_cache = tmp_path / "cache" / "son.mp3"

            ok = provider._telecharger_freesound(segment, chemin_sortie, chemin_cache)
            assert ok is False


class TestSfxProviderSilence:
    """Tests de la génération de silence."""

    def test_generer_silence(self, tmp_path):
        mock_silence = MagicMock()
        mock_audio_segment = MagicMock()
        mock_audio_segment.silent.return_value = mock_silence

        with patch("agents.sfx_provider.config") as mock_config, \
             patch.dict("sys.modules", {"pydub": MagicMock(AudioSegment=mock_audio_segment)}):
            mock_config.ELEVENLABS_API_KEY = ""
            mock_config.FREESOUND_API_KEY = ""
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"

            provider = SfxProvider()
            segment = {
                "id": "sfx_001",
                "personnage": "sfx",
                "texte": "test",
                "ton": "ambiance",
                "duree_sfx_secondes": 2.0,
                "mode": "insert",
            }
            chemin = tmp_path / "silence.mp3"
            provider._generer_silence(segment, chemin)

            mock_audio_segment.silent.assert_called_once_with(duration=2000)
            mock_silence.export.assert_called_once_with(str(chemin), format="mp3")


class TestScripteurSfxValidation:
    """Tests que le scripteur accepte les segments SFX avec mode."""

    def test_valider_structure_avec_sfx(self):
        """Un script avec des segments SFX doit être valide."""
        from agents.scripteur import Scripteur

        script = {
            "episode": {
                "titre": "Test",
                "numero": 1,
                "saison": 1,
                "segments": [
                    {
                        "id": "seg_001",
                        "personnage": "narrateur",
                        "texte": "Bonjour",
                        "ton": "neutre",
                        "pause_apres_ms": 0,
                    },
                    {
                        "id": "sfx_001",
                        "personnage": "sfx",
                        "texte": "vent du desert",
                        "ton": "ambiance",
                        "pause_apres_ms": 300,
                        "mode": "overlay",
                    },
                ],
            }
        }
        Scripteur._valider_structure(script)
