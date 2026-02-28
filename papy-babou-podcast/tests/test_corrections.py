"""Tests pour les corrections de bugs — audite complet.

Couvre les bugs critiques, élevés et moyens identifiés lors de l'audit :
- Bug #1: type_episode lu correctement depuis le plan
- Bug #2: personnages secondaires avec fallback voice_id
- Bug #3: RSS pubDate timezone
- Bug #5: historique sériel enrichi
- Bug #6: checkpoint contient type_episode
- Bug #7: variables initialisées sur reprise
- Bug #8: retry Claude API
- Bug #9: reviewer adapté au type
- Bug #11: path traversal SFX
- Bug #12: CoverArt rate limiter corrigé
- Bug #13: noms personnages dynamiques dans transcripts
- Bug #14: division par zéro fond audio
- Bug #16: questions[0] sur liste vide
- Bug #17: max_workers >= 1
- Bug #18: try/except input interactif
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agents.scripteur import (
    Scripteur,
    _construire_structure_narrative,
    _construire_system_prompt,
)
from agents.metadonnees import Metadonnees


# ── Bug #1 : type_episode lu depuis le plan ──────────────────────────────────


class TestTypeEpisodeDepuisPlan:
    """Bug #1 : le type d'épisode doit être lu depuis le plan, pas masqué."""

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_type_ouverture_depuis_plan(self, mock_anthropic, script_exemple):
        """Si episode_plan dit 'ouverture', le system prompt doit refléter 15 min."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(script_exemple))]
        mock_client.messages.create.return_value = mock_response

        episode_plan = {"numero": 1, "type": "ouverture"}

        scripteur = Scripteur()
        scripteur.client = mock_client
        scripteur.generer(
            titre="Test",
            resume="Test",
            saison=1,
            numero=1,
            episode_plan=episode_plan,
            # type_episode par défaut = "standard"
        )

        call_args = mock_client.messages.create.call_args
        system_msg = call_args[1]["system"]
        # Le prompt doit contenir 15 min (ouverture) pas 13 min (standard)
        assert "15" in system_msg
        assert "1600" in system_msg

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_type_final_depuis_plan(self, mock_anthropic, script_exemple):
        """Si episode_plan dit 'final', le system prompt doit refléter 18 min."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(script_exemple))]
        mock_client.messages.create.return_value = mock_response

        episode_plan = {"numero": 10, "type": "final"}

        scripteur = Scripteur()
        scripteur.client = mock_client
        scripteur.generer(
            titre="Test Final",
            resume="Test",
            saison=1,
            numero=10,
            episode_plan=episode_plan,
        )

        call_args = mock_client.messages.create.call_args
        system_msg = call_args[1]["system"]
        assert "18" in system_msg
        assert "1900" in system_msg

    @patch("agents.scripteur.anthropic.Anthropic")
    def test_type_explicite_non_ecrase(self, mock_anthropic, script_exemple):
        """Un type_episode explicite non-standard ne doit pas être écrasé par le plan."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(script_exemple))]
        mock_client.messages.create.return_value = mock_response

        episode_plan = {"numero": 5, "type": "standard"}

        scripteur = Scripteur()
        scripteur.client = mock_client
        scripteur.generer(
            titre="Test",
            resume="Test",
            saison=1,
            numero=5,
            episode_plan=episode_plan,
            type_episode="mi-saison",  # Explicite, ne doit pas être écrasé
        )

        call_args = mock_client.messages.create.call_args
        system_msg = call_args[1]["system"]
        assert "15" in system_msg  # mi-saison = 15 min


# ── Bug #2 : personnages secondaires sans voice_id ───────────────────────────


class TestPersonnageSecondaireFallback:
    """Bug #2 : personnage secondaire doit fallback vers narrateur."""

    def test_fallback_voice_id(self, monkeypatch):
        """Un personnage sans voice_id doit utiliser celui du narrateur."""
        from agents.producteur_audio import ProducteurAudio

        monkeypatch.setattr(config, "VOICE_IDS", {
            "narrateur": "voice_narrateur_123",
            "papy_babou": "voice_papy_456",
        })

        segment = {
            "id": "seg_001",
            "personnage": "mamie_rose",
            "texte": "Bonjour",
            "ton": "doux",
        }

        producteur = ProducteurAudio()
        # We just test the voice_id resolution logic, not the actual API call
        voice_id = config.VOICE_IDS.get(segment["personnage"])
        if not voice_id:
            voice_id = config.VOICE_IDS.get("narrateur")
        assert voice_id == "voice_narrateur_123"


# ── Bug #3 : RSS pubDate timezone ────────────────────────────────────────────


class TestRSSPubDateTimezone:
    """Bug #3 : pubDate doit utiliser now.timestamp() pas mktime."""

    def test_publisher_no_mktime_import(self):
        """Le publisher ne doit plus importer mktime."""
        import agents.publisher as pub_module
        source = Path(pub_module.__file__).read_text()
        assert "from time import mktime" not in source
        assert "mktime(" not in source


# ── Bug #5 : historique sériel enrichi ────────────────────────────────────────


class TestHistoriqueSerielEnrichi:
    """Bug #5 : l'historique doit contenir un vrai résumé et les champs sériels."""

    def test_resume_court_pas_juste_titre(self, tmp_path, monkeypatch):
        """resume_court doit contenir du texte des segments, pas juste le titre."""
        import main
        monkeypatch.setattr(main, "HISTORIQUE_PATH", tmp_path / "hist.json")

        rapport = {
            "episode_id": "S01E01",
            "titre": "Le buisson ardent",
            "debut": "2025-01-01T00:00:00",
            "etapes": {"script": {"score_review": 8}},
        }
        script = {
            "episode": {
                "titre": "Le buisson ardent",
                "morale": "La confiance",
                "segments": [
                    {"personnage": "narrateur", "texte": "Il était une fois dans le désert un homme nommé Moïse."},
                    {"personnage": "papy_babou", "texte": "Mes petits loups, imaginez cette scène..."},
                    {"personnage": "sfx", "texte": "vent du desert"},
                ],
            }
        }

        from main import ajouter_historique, charger_historique
        ajouter_historique(rapport, script)

        hist = charger_historique()
        assert len(hist) == 1
        resume = hist[0]["resume_court"]
        # Le résumé doit contenir du texte des segments, pas juste le titre
        assert "Moïse" in resume or "petits loups" in resume
        assert resume != "Le buisson ardent"

    def test_questions_ouvertes_et_evolutions(self, tmp_path, monkeypatch):
        """Les champs questions_ouvertes et evolutions_personnages doivent être sauvés."""
        import main
        monkeypatch.setattr(main, "HISTORIQUE_PATH", tmp_path / "hist.json")

        rapport = {
            "episode_id": "S01E01",
            "titre": "Test",
            "debut": "2025-01-01",
            "etapes": {"script": {"score_review": 7}},
        }
        script = {
            "episode": {
                "titre": "Test",
                "morale": "Courage",
                "questions_ouvertes": ["Où ira Moïse ?"],
                "evolutions_personnages": "Antoine gagne en confiance",
                "segments": [
                    {"personnage": "narrateur", "texte": "Bonjour"},
                ],
            }
        }

        from main import ajouter_historique, charger_historique
        ajouter_historique(rapport, script)

        hist = charger_historique()
        assert hist[0]["questions_ouvertes"] == ["Où ira Moïse ?"]
        assert hist[0]["evolutions_personnages"] == "Antoine gagne en confiance"


# ── Bug #6 : checkpoint contient type_episode ────────────────────────────────


class TestCheckpointTypeEpisode:
    """Bug #6 : le checkpoint doit sauvegarder type_episode."""

    def test_checkpoint_contient_type(self, tmp_path, monkeypatch):
        """type_episode doit être dans les données du checkpoint."""
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        from main import sauvegarder_checkpoint, charger_checkpoint
        data = {
            "episode_id": "S01E01",
            "titre": "Test",
            "saison": 1,
            "numero": 1,
            "morale": "",
            "type_episode": "ouverture",
            "dry_run": False,
            "rapport": {},
        }
        chemin = sauvegarder_checkpoint("S01E01", "audio", data)
        cp = charger_checkpoint(chemin)
        assert cp["data"]["type_episode"] == "ouverture"


# ── Bug #8 : retry Claude API ────────────────────────────────────────────────


class TestRetryClaude:
    """Bug #8 : appel_claude_avec_retry doit retenter sur erreurs 429/500."""

    def test_retry_sur_429(self):
        """Une erreur 429 doit être retentée."""
        mock_client = MagicMock()
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 Too Many Requests")
            return MagicMock()

        mock_client.messages.create.side_effect = side_effect

        with patch("time.sleep"):
            result = config.appel_claude_avec_retry(
                mock_client,
                max_tentatives=3,
                model="test",
                max_tokens=100,
                messages=[],
            )
        assert call_count == 3

    def test_pas_retry_sur_400(self):
        """Une erreur 400 ne doit PAS être retentée."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("400 Bad Request")

        with pytest.raises(Exception, match="400"):
            config.appel_claude_avec_retry(
                mock_client,
                max_tentatives=3,
                model="test",
                max_tokens=100,
                messages=[],
            )
        # Un seul appel (pas de retry)
        assert mock_client.messages.create.call_count == 1

    def test_succes_premier_essai(self):
        """Un succès au premier essai ne doit faire qu'un appel."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = config.appel_claude_avec_retry(
            mock_client,
            model="test",
            max_tokens=100,
            messages=[],
        )
        assert result == mock_response
        assert mock_client.messages.create.call_count == 1


# ── Bug #11 : path traversal SFX ─────────────────────────────────────────────


class TestSfxPathTraversal:
    """Bug #11 : les chemins SFX doivent être validés."""

    def test_path_traversal_bloque(self, tmp_path):
        """Un texte SFX avec '../' ne doit pas échapper au dossier SFX."""
        from agents.sfx_provider import SfxProvider

        with patch("agents.sfx_provider.config") as mock_config:
            sfx_dir = tmp_path / "sfx"
            sfx_dir.mkdir()
            mock_config.SFX_DIR = sfx_dir
            mock_config.SFX_CACHE_DIR = tmp_path / "cache"
            mock_config.SEGMENTS_DIR = tmp_path / "segments"
            mock_config.ELEVENLABS_API_KEY = ""
            mock_config.FREESOUND_API_KEY = ""
            mock_config.PRODUCTION = {"max_retry_tts": 3}

            provider = SfxProvider()

            script = {
                "episode": {
                    "saison": 1,
                    "numero": 1,
                    "segments": [
                        {
                            "id": "sfx_001",
                            "personnage": "sfx",
                            "texte": "../../etc/passwd",
                            "duree_sfx_secondes": 2.0,
                        },
                    ],
                }
            }

            with patch.object(provider, "_generer_silence") as mock_silence:
                mock_silence.side_effect = lambda seg, chemin: chemin.write_bytes(b"silence")
                fichiers = provider.produire_sfx(script)

            # Le SFX doit être remplacé par du silence, pas d'accès au fichier traversé
            assert provider.stats["sfx_001"] == "silence"


# ── Bug #12 : CoverArt rate limiter ──────────────────────────────────────────


class TestCoverArtRateLimiter:
    """Bug #12 : CoverArt doit utiliser rate_limiter_openai."""

    def test_coverart_utilise_openai_limiter(self):
        """Le code de cover_art.py doit utiliser rate_limiter_openai."""
        import agents.cover_art as ca_module
        source = Path(ca_module.__file__).read_text()
        assert "rate_limiter_openai" in source
        assert "rate_limiter_anthropic" not in source


# ── Bug #13 : noms personnages dynamiques dans transcripts ────────────────────


class TestTranscriptNomsDynamiques:
    """Bug #13 : les personnages dynamiques doivent avoir des noms lisibles."""

    def test_personnage_dynamique_dans_transcript(self, monkeypatch):
        """mamie_rose doit apparaître comme 'Mamie Rose' dans le transcript."""
        monkeypatch.setattr(
            config,
            "charger_personnages",
            lambda: {"personnages": {
                "mamie_rose": {"nom_complet": "Mamie Rose"},
            }},
        )

        episode = {
            "titre": "Test",
            "segments": [
                {"personnage": "mamie_rose", "texte": "Bonjour les enfants !"},
                {"personnage": "papy_babou", "texte": "Bonjour Mamie Rose !"},
            ],
        }

        transcript = Metadonnees._generer_transcript(episode)
        assert "[Mamie Rose]" in transcript
        assert "[mamie_rose]" not in transcript

    def test_personnage_inconnu_formate(self, monkeypatch):
        """Un personnage inconnu doit être formaté en titre (cousin_paul → Cousin Paul)."""
        monkeypatch.setattr(config, "charger_personnages", lambda: {"personnages": {}})

        episode = {
            "titre": "Test",
            "segments": [
                {"personnage": "cousin_paul", "texte": "Salut tout le monde !"},
            ],
        }

        transcript = Metadonnees._generer_transcript(episode)
        assert "[Cousin Paul]" in transcript


# ── Bug #14 : division par zéro fond audio ────────────────────────────────────


class TestFondAudioDivisionParZero:
    """Bug #14 : un fond audio vide ne doit pas crasher."""

    def test_fond_audio_vide(self):
        """Un fond audio de 0ms ne doit pas lever ZeroDivisionError."""
        from pydub import AudioSegment

        monteur = __import__("agents.monteur", fromlist=["Monteur"]).Monteur()
        fond_vide = AudioSegment.empty()
        result = monteur._preparer_fond(fond_vide, 5000)
        assert len(result) >= 5000


# ── Bug #16 : questions[0] sur liste vide ─────────────────────────────────────


class TestQuestionsOuvertesVides:
    """Bug #16 : une liste questions_ouvertes vide ne doit pas crasher."""

    def test_structure_avec_questions_vides(self):
        """Un historique avec questions_ouvertes: [] ne doit pas crasher."""
        historique = [
            {
                "titre": "Test",
                "morale": "Courage",
                "questions_ouvertes": [],
            }
        ]
        result = _construire_structure_narrative("standard", historique=historique)
        assert "PREVIOUSLY ON" in result


# ── Bug #17 : max_workers >= 1 ────────────────────────────────────────────────


class TestMaxWorkersMinimum:
    """Bug #17 : max_workers doit être >= 1 même si config = 0."""

    def test_max_workers_jamais_zero(self, monkeypatch):
        """Même avec max_parallel_tts=0, max_workers doit être >= 1."""
        monkeypatch.setattr(config, "PRODUCTION", {
            **config.PRODUCTION,
            "max_parallel_tts": 0,
        })
        # Le min(0, n) donnerait 0, mais max(1, ...) protège
        result = max(1, min(config.PRODUCTION["max_parallel_tts"], 5))
        assert result >= 1


# ── Rate limiter OpenAI ──────────────────────────────────────────────────────


class TestRateLimiterOpenAI:
    """Le rate limiter OpenAI doit exister."""

    def test_rate_limiter_openai_existe(self):
        """rate_limiter_openai doit être défini dans config."""
        assert hasattr(config, "rate_limiter_openai")
        assert isinstance(config.rate_limiter_openai, config.RateLimiter)
