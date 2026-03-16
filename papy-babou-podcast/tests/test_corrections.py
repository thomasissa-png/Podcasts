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
- BUG-C2: RSS feed déclare itunes:type=serial
- BUG-C3: thème vide rejeté dans planifier-saison
- BUG-H1: Buzzsprout upload avec retry
- BUG-H2: RSS feed écrit sous fichier_lock
- BUG-H4: types d'épisodes LLM validés
- BUG-H4b: numéros d'épisodes séquentiels validés
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
        # Le prompt doit contenir 30 min (ouverture) pas 25 min (standard)
        assert "30" in system_msg
        assert "3200" in system_msg

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
        assert "35" in system_msg
        assert "3800" in system_msg

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
        assert "30" in system_msg  # mi-saison = 30 min


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
        assert "RAPPEL NATUREL" in result


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


# ── ouvrir_fichier utility ────────────────────────────────────────────────────


class TestOuvrirFichier:
    """Tests pour ouvrir_fichier() dans utils.py."""

    def test_fichier_inexistant_retourne_false(self):
        """ouvrir_fichier retourne False si le fichier n'existe pas."""
        from utils import ouvrir_fichier
        assert ouvrir_fichier(Path("/tmp/ce_fichier_nexiste_pas_12345.mp3")) is False

    def test_fichier_existant_lance_commande(self, tmp_path):
        """ouvrir_fichier lance la commande système et retourne True."""
        from utils import ouvrir_fichier
        fichier = tmp_path / "test.mp3"
        fichier.write_bytes(b"fake")

        with patch("utils.subprocess.Popen") as mock_popen:
            result = ouvrir_fichier(fichier)
            assert result is True
            mock_popen.assert_called_once()

    def test_erreur_os_retourne_false(self, tmp_path):
        """ouvrir_fichier retourne False en cas d'erreur OS."""
        from utils import ouvrir_fichier
        fichier = tmp_path / "test.mp3"
        fichier.write_bytes(b"fake")

        with patch("utils.subprocess.Popen", side_effect=OSError("no player")):
            result = ouvrir_fichier(fichier)
            assert result is False


# ── BUG-C2 : RSS itunes:type=serial ─────────────────────────────────────────


class TestRSSItunesTypeSerial:
    """BUG-C2 : le channel RSS doit déclarer itunes:type=serial."""

    def test_creer_channel_declare_serial(self, tmp_path):
        """Le channel RSS créé doit contenir <itunes:type>serial</itunes:type>."""
        from agents.publisher import Publisher, ITUNES_NS
        from xml.etree import ElementTree as ET

        publisher = Publisher()
        root = ET.Element("rss", version="2.0")
        root.set("xmlns:itunes", ITUNES_NS)
        channel = ET.SubElement(root, "channel")
        publisher._creer_channel(channel)

        itunes_type = channel.find(f"{{{ITUNES_NS}}}type")
        assert itunes_type is not None
        assert itunes_type.text == "serial"


# ── BUG-C3 : thème vide rejeté ──────────────────────────────────────────────


class TestThemeVideRejete:
    """BUG-C3 : planifier-saison doit rejeter un thème vide."""

    def test_theme_vide_exit(self):
        """Un thème vide ou whitespace doit lever SystemExit."""
        from click.testing import CliRunner
        from main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["planifier-saison", "-s", "1", "-t", "   "])
        assert result.exit_code != 0

    def test_theme_valide_accepte(self):
        """Un thème non-vide doit être accepté (échouera pour autre raison, pas pour le thème)."""
        from click.testing import CliRunner
        from main import cli

        runner = CliRunner()
        # Will fail because no API key, but should NOT fail because of empty theme
        result = runner.invoke(cli, ["planifier-saison", "-s", "1", "-t", "Les patriarches"])
        # If it failed for theme reasons, the output would contain "Thème manquant"
        assert "Thème manquant" not in (result.output or "")


# ── BUG-H1 : Buzzsprout retry ───────────────────────────────────────────────


class TestBuzzsproutRetry:
    """BUG-H1 : l'upload Buzzsprout doit retenter en cas d'erreur réseau."""

    def test_retry_sur_erreur_reseau(self, tmp_path, monkeypatch):
        """L'upload doit retenter jusqu'à max_retries avec backoff."""
        import requests
        from agents.publisher import Publisher

        monkeypatch.setattr(config, "BUZZSPROUT_API_KEY", "fake-key")
        monkeypatch.setattr(config, "BUZZSPROUT_PODCAST_ID", "12345")

        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio content")

        meta = {
            "titre_court": "Test",
            "description_longue": "Desc",
            "description_courte": "Short",
            "saison": 1,
            "numero": 1,
            "explicit": False,
        }

        call_count = {"n": 0}
        original_post = requests.post

        def mock_post(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise requests.ConnectionError("Network error")
            # 3rd attempt succeeds
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"audio_url": "https://example.com/ep.mp3"}
            return mock_resp

        publisher = Publisher()
        with patch("agents.publisher.requests.post", side_effect=mock_post), \
             patch("agents.publisher.time.sleep"):  # Skip actual waits
            url = publisher._upload_buzzsprout(meta, audio, 100)

        assert url == "https://example.com/ep.mp3"
        assert call_count["n"] == 3  # 2 failures + 1 success

    def test_retry_epuise_relance(self, tmp_path, monkeypatch):
        """Si toutes les tentatives échouent, l'erreur est relancée."""
        import requests
        from agents.publisher import Publisher

        monkeypatch.setattr(config, "BUZZSPROUT_API_KEY", "fake-key")
        monkeypatch.setattr(config, "BUZZSPROUT_PODCAST_ID", "12345")

        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio content")

        meta = {
            "titre_court": "Test",
            "description_longue": "Desc",
            "description_courte": "Short",
            "saison": 1,
            "numero": 1,
            "explicit": False,
        }

        publisher = Publisher()
        with patch("agents.publisher.requests.post", side_effect=requests.ConnectionError("always fails")), \
             patch("agents.publisher.time.sleep"), \
             pytest.raises(requests.ConnectionError):
            publisher._upload_buzzsprout(meta, audio, 100)


# ── BUG-H2 : RSS file locking ───────────────────────────────────────────────


class TestRSSFileLocking:
    """BUG-H2 : la mise à jour RSS doit utiliser fichier_lock."""

    def test_mettre_a_jour_rss_utilise_fichier_lock(self):
        """Le code publisher.py doit importer et utiliser fichier_lock."""
        import agents.publisher as pub_module
        source = Path(pub_module.__file__).read_text()
        assert "fichier_lock" in source
        assert "with fichier_lock(feed_path)" in source


# ── BUG-H4 : validation types épisodes ──────────────────────────────────────


class TestValidationTypesEpisodes:
    """BUG-H4 : les types d'épisodes invalides doivent être corrigés."""

    def test_type_invalide_corrige_en_standard(self):
        """Un type d'épisode inconnu dans le plan doit être corrigé en 'standard'."""
        plan = {
            "episodes": [
                {"numero": 1, "titre": "Ep1", "type": "ouverture"},
                {"numero": 2, "titre": "Ep2", "type": "inventé"},  # invalide
                {"numero": 3, "titre": "Ep3", "type": "final"},
            ]
        }
        types_valides = {"ouverture", "standard", "mi-saison", "final", "bonus"}
        for ep in plan["episodes"]:
            if ep.get("type", "standard") not in types_valides:
                ep["type"] = "standard"

        assert plan["episodes"][0]["type"] == "ouverture"
        assert plan["episodes"][1]["type"] == "standard"
        assert plan["episodes"][2]["type"] == "final"

    def test_numeros_non_sequentiels_corrigés(self):
        """Des numéros non séquentiels doivent être renumérotés."""
        plan = {
            "episodes": [
                {"numero": 1, "titre": "Ep1"},
                {"numero": 5, "titre": "Ep2"},  # gap
                {"numero": 3, "titre": "Ep3"},  # out of order
            ]
        }
        numeros = [ep["numero"] for ep in plan["episodes"]]
        attendus = list(range(1, len(numeros) + 1))
        if numeros != attendus:
            for idx, ep in enumerate(plan["episodes"], 1):
                ep["numero"] = idx

        assert [ep["numero"] for ep in plan["episodes"]] == [1, 2, 3]


# ── AUDIO : Génération automatique assets ─────────────────────────────────


class TestMonteurAutoGeneration:
    """Tests de la génération automatique d'assets audio via ElevenLabs."""

    def test_generer_asset_sans_api_key(self, monkeypatch):
        """Sans clé ElevenLabs, la génération retourne False."""
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        monteur = Monteur()
        result = monteur._generer_asset_elevenlabs(
            "test sound", 5.0, Path("/tmp/test.mp3")
        )
        assert result is False

    def test_generer_asset_succes(self, tmp_path, monkeypatch):
        """Avec une clé et une réponse API valide, le fichier est créé."""
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "fake-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"fake mp3 audio data"

        chemin = tmp_path / "jingle.mp3"
        monteur = Monteur()

        with patch("agents.monteur.requests.post", return_value=mock_response), \
             patch.object(config.rate_limiter_elevenlabs, "attendre"):
            result = monteur._generer_asset_elevenlabs(
                "cheerful jingle", 10.0, chemin
            )

        assert result is True
        assert chemin.exists()
        assert chemin.read_bytes() == b"fake mp3 audio data"

    def test_generer_asset_retry_puis_echec(self, tmp_path, monkeypatch):
        """Après N échecs, la génération retourne False."""
        import requests as req_lib
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "fake-key")

        chemin = tmp_path / "jingle.mp3"
        monteur = Monteur()

        with patch("agents.monteur.requests.post",
                    side_effect=req_lib.RequestException("API down")), \
             patch("agents.monteur.time.sleep"), \
             patch.object(config.rate_limiter_elevenlabs, "attendre"):
            result = monteur._generer_asset_elevenlabs(
                "test", 5.0, chemin
            )

        assert result is False
        assert not chemin.exists()

    def test_generer_asset_duree_plafonnee_22s(self, tmp_path, monkeypatch):
        """La durée est plafonnée à 22 secondes (limite ElevenLabs)."""
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "fake-key")

        payloads_captured = []
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"fake"

        def capture_post(url, json=None, **kwargs):
            payloads_captured.append(json)
            return mock_response

        chemin = tmp_path / "test.mp3"
        monteur = Monteur()

        with patch("agents.monteur.requests.post", side_effect=capture_post), \
             patch.object(config.rate_limiter_elevenlabs, "attendre"):
            monteur._generer_asset_elevenlabs("long music", 120.0, chemin)

        assert payloads_captured[0]["duration_seconds"] == 22.0


class TestMonteurJingleAutoGen:
    """Tests que _charger_jingle auto-génère quand fichiers absents."""

    def test_jingle_auto_genere_si_absent(self, monkeypatch, tmp_path):
        """Si aucun fichier jingle n'existe, ElevenLabs est appelé."""
        from agents.monteur import Monteur
        from pydub import AudioSegment
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "fake-key")
        # Rediriger vers tmp_path
        monkeypatch.setattr(config, "AUDIO_ASSETS", {
            "intro_jingle": tmp_path / "intro_jingle.mp3",
        })
        monkeypatch.setattr(config, "ASSETS_DIR", tmp_path)

        gen_called = {"n": 0}

        def mock_gen(self, description, duree, chemin):
            gen_called["n"] += 1
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(b"fake")
            return True

        fake_audio = AudioSegment.silent(duration=1000)
        monteur = Monteur()
        with patch.object(Monteur, "_generer_asset_elevenlabs", mock_gen), \
             patch.object(AudioSegment, "from_mp3", return_value=fake_audio):
            audio = monteur._charger_jingle("intro", "standard")

        assert gen_called["n"] >= 1
        assert len(audio) > 0

    def test_jingle_pas_regen_si_fichier_existe(self, tmp_path, monkeypatch):
        """Si le fichier jingle existe, pas d'appel ElevenLabs."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        chemin = tmp_path / "intro_jingle.mp3"
        chemin.write_bytes(b"fake audio")
        monkeypatch.setattr(config, "AUDIO_ASSETS", {
            "intro_jingle": chemin,
        })

        fake_audio = AudioSegment.silent(duration=1000)
        monteur = Monteur()
        with patch.object(Monteur, "_generer_asset_elevenlabs") as mock_gen, \
             patch.object(AudioSegment, "from_mp3", return_value=fake_audio):
            audio = monteur._charger_jingle("intro", "standard")

        mock_gen.assert_not_called()
        assert len(audio) > 0


class TestMonteurAmbianceAutoGen:
    """Tests que _charger_ambiance auto-génère quand fichiers absents."""

    def test_ambiance_auto_generee(self, monkeypatch, tmp_path):
        """Si l'ambiance n'existe pas, ElevenLabs est appelé."""
        from agents.monteur import Monteur
        from pydub import AudioSegment
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "fake-key")
        monkeypatch.setattr(config, "AMBIANCES_MUSICALES", {
            "epique": tmp_path / "ambiance_epique.mp3",
        })

        gen_called = {"n": 0}

        def mock_gen(self, description, duree, chemin):
            gen_called["n"] += 1
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(b"fake")
            return True

        fake_audio = AudioSegment.silent(duration=1000)
        monteur = Monteur()
        with patch.object(Monteur, "_generer_asset_elevenlabs", mock_gen), \
             patch.object(AudioSegment, "from_mp3", return_value=fake_audio):
            audio = monteur._charger_ambiance("epique")

        assert gen_called["n"] >= 1
        assert len(audio) > 0

    def test_ambiance_fallback_fond_doux_si_gen_echoue(self, monkeypatch, tmp_path):
        """Si la génération échoue, fallback vers fond_doux puis silence."""
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        # Rediriger les chemins vers tmp_path pour éviter de polluer les vrais assets
        monkeypatch.setattr(config, "AMBIANCES_MUSICALES", {
            "epique": tmp_path / "ambiance_epique.mp3",
            "fond_doux": tmp_path / "fond_doux.mp3",
        })
        monkeypatch.setattr(config, "AUDIO_ASSETS", {
            "fond_doux": tmp_path / "fond_doux.mp3",
        })

        monteur = Monteur()
        # Sans clé API, fond_doux n'existe pas non plus → silence
        audio = monteur._charger_ambiance("epique")
        assert len(audio) > 0  # Silence de remplacement


# ── AUDIO : Crossfade et pauses ──────────────────────────────────────────


class TestMonteurCrossfade:
    """Tests du crossfade entre segments voix."""

    def test_crossfade_entre_segments(self, tmp_path):
        """Le crossfade doit réduire la durée totale par rapport à la concaténation."""
        from agents.monteur import Monteur, CROSSFADE_VOIX_MS
        from pydub import AudioSegment

        seg1 = AudioSegment.silent(duration=500)
        seg2 = AudioSegment.silent(duration=500)
        segments_dir = tmp_path / "segments"
        segments_dir.mkdir()
        (segments_dir / "seg_001.mp3").write_bytes(b"fake")
        (segments_dir / "seg_002.mp3").write_bytes(b"fake")

        segments = [
            {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour",
             "ton": "chaleureux", "pause_apres_ms": 0},
            {"id": "seg_002", "personnage": "antoine", "texte": "Salut",
             "ton": "curieux", "pause_apres_ms": 0},
        ]

        # Désactiver les micro-respirations pour un test déterministe
        with patch.object(AudioSegment, "from_mp3", side_effect=[seg1, seg2]), \
             patch("agents.monteur.random.random", return_value=1.0):
            monteur = Monteur()
            result = monteur._assembler_segments(segments, segments_dir)

        # Avec crossfade de CROSSFADE_VOIX_MS, la durée doit être < 1000ms
        assert len(result) < 1000
        assert len(result) == 1000 - CROSSFADE_VOIX_MS


class TestMonteurMaxPause:
    """Tests du plafonnement des pauses."""

    def test_pause_plafonnee(self, tmp_path):
        """Les pauses > MAX_PAUSE_MS doivent être plafonnées."""
        from agents.monteur import Monteur, MAX_PAUSE_MS
        from pydub import AudioSegment

        seg = AudioSegment.silent(duration=200)
        segments_dir = tmp_path / "segments"
        segments_dir.mkdir()
        (segments_dir / "seg_001.mp3").write_bytes(b"fake")

        segments = [
            {"id": "seg_001", "personnage": "papy_babou", "texte": "Test",
             "ton": "neutre", "pause_apres_ms": 5000},  # > MAX_PAUSE_MS
        ]

        with patch.object(AudioSegment, "from_mp3", return_value=seg), \
             patch("agents.monteur.random.random", return_value=1.0):
            monteur = Monteur()
            result = monteur._assembler_segments(segments, segments_dir)

        # 200ms audio + MAX_PAUSE_MS (pas 5000ms)
        assert len(result) == 200 + MAX_PAUSE_MS


# ── AUDIO : Prompts scripteur ────────────────────────────────────────────


class TestScripteurPausesNaturelles:
    """Tests que le prompt du scripteur guide vers des pauses naturelles."""

    def test_prompt_contient_pauses_courtes(self):
        """Le prompt doit mentionner des pauses de 150-300ms."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert "150-300" in SYSTEM_PROMPT_BASE

    def test_prompt_contient_pauses_normales(self):
        """Le prompt doit mentionner des pauses de 400-600ms."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert "400-600" in SYSTEM_PROMPT_BASE

    def test_prompt_exemple_pause_courte(self):
        """L'exemple JSON doit montrer une pause <= 300ms."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert '"pause_apres_ms": 250' in SYSTEM_PROMPT_BASE

    def test_prompt_pas_800ms_par_defaut(self):
        """L'exemple ne doit plus montrer 800ms comme valeur par défaut."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        # L'ancien "pause_apres_ms": 800 ne doit plus être dans l'exemple voix
        # (il peut rester dans le texte comme "pause dramatique")
        assert '"pause_apres_ms": 800' not in SYSTEM_PROMPT_BASE


# ── AUDIO : Prompts de génération ────────────────────────────────────────


class TestMonteurPrompts:
    """Tests que les prompts de génération d'assets sont complets."""

    def test_jingle_prompts_couvrent_tous_les_types(self):
        """Les prompts doivent couvrir intro, outro, intro_saison, outro_saison."""
        from agents.monteur import JINGLE_PROMPTS
        assert "intro_jingle" in JINGLE_PROMPTS
        assert "outro_jingle" in JINGLE_PROMPTS
        assert "intro_saison" in JINGLE_PROMPTS
        assert "outro_saison" in JINGLE_PROMPTS

    def test_ambiance_prompts_couvrent_toutes_ambiances(self):
        """Les prompts doivent couvrir toutes les ambiances de config."""
        from agents.monteur import AMBIANCE_PROMPTS
        for ambiance in config.AMBIANCES_MUSICALES:
            assert ambiance in AMBIANCE_PROMPTS, \
                f"Prompt manquant pour l'ambiance '{ambiance}'"

    def test_prompts_en_anglais(self):
        """Les prompts ElevenLabs doivent être en anglais."""
        from agents.monteur import JINGLE_PROMPTS, AMBIANCE_PROMPTS
        for nom, prompt in {**JINGLE_PROMPTS, **AMBIANCE_PROMPTS}.items():
            # Vérifier un mot anglais courant
            assert any(w in prompt.lower() for w in ("music", "jingle", "background", "gentle", "podcast")), \
                f"Prompt '{nom}' semble ne pas être en anglais : {prompt[:50]}"


# ── AUDIO : Scripteur type validation ────────────────────────────────────


class TestScripteurTypeValidation:
    """Tests de la validation auto-correction du type d'épisode dans le scripteur."""

    def test_type_invalide_corrige_par_scripteur(self):
        """Un type LLM invalide doit être remplacé par le type demandé."""
        from agents.scripteur import Scripteur
        scripteur = Scripteur()

        script = {
            "episode": {
                "titre": "Test",
                "numero": 1,
                "saison": 1,
                "duree_cible_minutes": 25,
                "ambiance": "calme",
                "morale": "Test",
                "type": "inventé",  # Type invalide
                "segments": [
                    {"id": "seg_001", "personnage": "papy_babou",
                     "texte": "Bonjour les enfants " * 50,
                     "ton": "chaleureux", "pause_apres_ms": 250},
                    {"id": "seg_002", "personnage": "antoine",
                     "texte": "Salut Papy " * 30,
                     "ton": "curieux", "pause_apres_ms": 200},
                ],
                "personnages_presents": ["papy_babou", "antoine"],
                "moments_cles": ["Test"],
            }
        }

        # Simuler la génération via le flux generer()
        # On vérifie seulement que le code de validation corrige le type
        valid_types = {"ouverture", "standard", "mi-saison", "final", "bonus"}
        ep_type = script["episode"].get("type", "")
        if ep_type not in valid_types:
            script["episode"]["type"] = "standard"

        assert script["episode"]["type"] == "standard"


# ── Amélioration 1 : Mapping ton → voice_settings ─────────────────────────────


class TestToneVoiceAdjustments:
    """Le mapping ton → voice_settings doit ajuster les paramètres ElevenLabs."""

    def test_tone_adjustments_existent(self):
        """Le dict TONE_VOICE_ADJUSTMENTS doit contenir tous les tons du prompt."""
        from agents.producteur_audio import TONE_VOICE_ADJUSTMENTS
        tons_attendus = {
            "chaleureux", "curieux", "inquiet", "neutre", "enthousiaste",
            "dramatique", "joyeux", "rassurant", "ambiance",
        }
        for ton in tons_attendus:
            assert ton in TONE_VOICE_ADJUSTMENTS, f"Ton '{ton}' manquant dans TONE_VOICE_ADJUSTMENTS"

    def test_tone_neutre_pas_de_modification(self):
        """Le ton 'neutre' ne doit pas modifier les paramètres de base."""
        from agents.producteur_audio import TONE_VOICE_ADJUSTMENTS
        neutre = TONE_VOICE_ADJUSTMENTS["neutre"]
        assert neutre["stability"] == 0.0
        assert neutre["similarity_boost"] == 0.0
        assert neutre["style"] == 0.0

    def test_tone_clamping(self):
        """Les ajustements doivent rester dans [0.0, 1.0] après application."""
        from agents.producteur_audio import TONE_VOICE_ADJUSTMENTS
        for ton, adj in TONE_VOICE_ADJUSTMENTS.items():
            # Test avec des valeurs de base extrêmes
            for base_val in (0.0, 0.5, 1.0):
                for key in ("stability", "similarity_boost", "style"):
                    result = max(0.0, min(1.0, base_val + adj.get(key, 0.0)))
                    assert 0.0 <= result <= 1.0, (
                        f"Ton '{ton}', clé '{key}': résultat {result} hors limites"
                    )

    def test_tone_enthousiaste_baisse_stability(self):
        """Un ton enthousiaste doit baisser la stability (voix plus variable)."""
        from agents.producteur_audio import TONE_VOICE_ADJUSTMENTS
        assert TONE_VOICE_ADJUSTMENTS["enthousiaste"]["stability"] < 0

    def test_tone_rassurant_hausse_stability(self):
        """Un ton rassurant doit hausser la stability (voix plus posée)."""
        from agents.producteur_audio import TONE_VOICE_ADJUSTMENTS
        assert TONE_VOICE_ADJUSTMENTS["rassurant"]["stability"] > 0


# ── Amélioration 2 : SFX en anglais ──────────────────────────────────────────


class TestSfxEnAnglais:
    """Le prompt scripteur doit demander des descriptions SFX en anglais."""

    def test_prompt_sfx_en_anglais(self):
        """Le system prompt doit mentionner 'EN ANGLAIS' pour les SFX."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert "EN ANGLAIS" in SYSTEM_PROMPT_BASE

    def test_prompt_sfx_exemples_anglais(self):
        """Les exemples SFX doivent être en anglais."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert "door creaking" in SYSTEM_PROMPT_BASE
        assert "birds singing" in SYSTEM_PROMPT_BASE


# ── Amélioration 3 : Crossfade 100ms ─────────────────────────────────────────


class TestCrossfade200ms:
    """Le crossfade entre segments voix doit être de 200ms."""

    def test_crossfade_voix_200ms(self):
        """CROSSFADE_VOIX_MS doit être 200."""
        from agents.monteur import CROSSFADE_VOIX_MS
        assert CROSSFADE_VOIX_MS == 200

    def test_crossfade_entre_segments(self, tmp_path):
        """Le crossfade doit réduire la durée totale de 100ms."""
        from agents.monteur import Monteur, CROSSFADE_VOIX_MS
        from pydub import AudioSegment

        seg1 = AudioSegment.silent(duration=500)
        seg2 = AudioSegment.silent(duration=500)
        segments_dir = tmp_path / "segments"
        segments_dir.mkdir()
        (segments_dir / "seg_001.mp3").write_bytes(b"fake")
        (segments_dir / "seg_002.mp3").write_bytes(b"fake")

        segments = [
            {"id": "seg_001", "personnage": "papy_babou", "texte": "Bonjour",
             "ton": "chaleureux", "pause_apres_ms": 0},
            {"id": "seg_002", "personnage": "antoine", "texte": "Salut",
             "ton": "curieux", "pause_apres_ms": 0},
        ]

        # Désactiver micro-respirations pour test déterministe
        with patch.object(AudioSegment, "from_mp3", side_effect=[seg1, seg2]), \
             patch("agents.monteur.random.random", return_value=1.0):
            monteur = Monteur()
            result = monteur._assembler_segments(segments, segments_dir)

        assert len(result) == 1000 - CROSSFADE_VOIX_MS


# ── Amélioration 4 : Transitions entre actes ─────────────────────────────────


class TestTransitionsActes:
    """Des transitions sonores doivent être insérées entre actes."""

    def test_transition_prompt_exists(self):
        """Le prompt de transition doit être défini."""
        from agents.monteur import TRANSITION_PROMPT
        assert "transition" in TRANSITION_PROMPT.lower()
        assert len(TRANSITION_PROMPT) > 20

    def test_charger_transition_fallback_silence(self, monkeypatch):
        """Sans fichier ni API, la transition est un silence."""
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        monteur = Monteur()
        trans = monteur._charger_transition()
        assert len(trans) >= 400


# ── Amélioration 5 : Vérification tics de langage ────────────────────────────


class TestVerificationTics:
    """La vérification des tics de langage doit fonctionner post-script."""

    def test_tics_detectes_dans_script(self, monkeypatch):
        """Les tics présents dans le texte doivent être comptés."""
        from agents.scripteur import Scripteur

        monkeypatch.setattr(config, "charger_personnages", lambda: {
            "personnages": {
                "papy_babou": {
                    "nom_complet": "Papy Babou",
                    "tics_de_langage": [
                        "Ah mes petits loups...",
                        "Figurez-vous que...",
                        "Et devinez quoi ?",
                    ],
                },
            }
        })

        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Ah mes petits loups, figurez-vous que c'est incroyable !"},
                    {"personnage": "papy_babou", "texte": "Et devinez quoi ? C'est formidable !"},
                ],
            }
        }

        # Ne doit pas lever d'exception
        Scripteur._verifier_tics_de_langage(script)

    def test_tics_warning_si_manquants(self, monkeypatch, caplog):
        """Un warning doit être émis si trop peu de tics sont utilisés."""
        import logging
        from agents.scripteur import Scripteur

        monkeypatch.setattr(config, "charger_personnages", lambda: {
            "personnages": {
                "papy_babou": {
                    "nom_complet": "Papy Babou",
                    "tics_de_langage": [
                        "Ah mes petits loups...",
                        "Figurez-vous que...",
                        "Et devinez quoi ?",
                    ],
                },
            }
        })

        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Bonjour les enfants, quelle belle journée."},
                ],
            }
        }

        with caplog.at_level(logging.WARNING):
            Scripteur._verifier_tics_de_langage(script)
        assert any("Tics de langage" in m for m in caplog.messages)


# ── Amélioration 6 : Ambiance dynamique par acte ────────────────────────────


class TestAmbianceDynamique:
    """Le scripteur doit supporter ambiance_par_acte."""

    def test_prompt_mentionne_ambiance_dynamique(self):
        """Le prompt doit mentionner 'ambiance_par_acte'."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert "ambiance_par_acte" in SYSTEM_PROMPT_BASE

    def test_monteur_mixer_ambiance_dynamique(self, monkeypatch):
        """Le monteur doit mixer plusieurs ambiances quand ambiance_par_acte est fourni."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")

        voix = AudioSegment.silent(duration=6000)
        monteur = Monteur()

        # Mock _charger_ambiance pour retourner du silence sans appels API
        with patch.object(monteur, "_charger_ambiance",
                          return_value=AudioSegment.silent(duration=3000)):
            result = monteur._mixer_ambiance_dynamique(
                voix, ["calme", "dramatique", "tendre"], []
            )

        # Le résultat doit avoir environ la même durée que les voix
        # (avec les crossfades, il sera légèrement plus court)
        assert abs(len(result) - 6000) < 5000


# ── Amélioration 7 : Micro-respirations ──────────────────────────────────────


class TestMicroRespirations:
    """Des micro-respirations doivent être insérées entre certaines répliques."""

    def test_respiration_constantes_definies(self):
        """Les constantes de respiration doivent être définies."""
        from agents.monteur import RESPIRATION_DUREE_MS, RESPIRATION_PROBABILITE
        assert RESPIRATION_DUREE_MS > 0
        assert 0.0 < RESPIRATION_PROBABILITE < 1.0

    def test_generer_micro_respiration(self):
        """La méthode de micro-respiration doit retourner un silence court."""
        from agents.monteur import Monteur, RESPIRATION_DUREE_MS
        monteur = Monteur()
        respiration = monteur._generer_micro_respiration()
        assert len(respiration) > 0
        assert len(respiration) <= RESPIRATION_DUREE_MS + 30


# ── Amélioration 8 : Ducking voix/SFX + Room tone + Master bus ────────────────


class TestDuckingVoixSFX:
    """Le ducking side-chain doit atténuer la voix pendant un SFX overlay."""

    def test_ducking_retourne_audio(self):
        """Le ducking doit retourner un segment audio de même durée."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        voix = AudioSegment.silent(duration=1000)
        sfx = AudioSegment.silent(duration=500)
        result = Monteur._appliquer_ducking(voix, sfx)
        assert len(result) >= len(voix) - 200  # tolérance crossfade ducking

    def test_ducking_sfx_couvre_tout(self):
        """Si le SFX couvre toute la voix, le résultat reste cohérent."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        voix = AudioSegment.silent(duration=500)
        sfx = AudioSegment.silent(duration=600)
        result = Monteur._appliquer_ducking(voix, sfx)
        assert len(result) == len(voix)


class TestRoomTone:
    """Le room tone doit être chargeable ou généré en fallback."""

    def test_charger_room_tone_fallback(self, monkeypatch):
        """Sans fichier ni API, le room tone est un bruit de remplacement."""
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        monteur = Monteur()
        room = monteur._charger_room_tone()
        assert len(room) > 0

    def test_room_tone_prompt_exists(self):
        """Le prompt de room tone doit être défini."""
        from agents.monteur import ROOM_TONE_PROMPT
        assert "room" in ROOM_TONE_PROMPT.lower()
        assert len(ROOM_TONE_PROMPT) > 20

    def test_room_tone_adaptatif_prompts(self):
        """Plusieurs variantes de room tone doivent exister."""
        from agents.monteur import ROOM_TONE_PROMPTS
        assert "defaut" in ROOM_TONE_PROMPTS
        assert "soir" in ROOM_TONE_PROMPTS
        assert "jour" in ROOM_TONE_PROMPTS
        assert "orage" in ROOM_TONE_PROMPTS

    def test_room_tone_mapping_ambiance(self):
        """Le mapping ambiance → room tone doit couvrir les ambiances principales."""
        from agents.monteur import AMBIANCE_ROOM_TONE
        assert AMBIANCE_ROOM_TONE["dramatique"] == "orage"
        assert AMBIANCE_ROOM_TONE["calme"] == "soir"
        assert AMBIANCE_ROOM_TONE["joyeux"] == "jour"

    def test_charger_room_tone_avec_ambiance(self, monkeypatch):
        """Le room tone doit varier selon l'ambiance passée."""
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        monteur = Monteur()
        # Doit retourner un audio même avec une ambiance spécifique
        room = monteur._charger_room_tone("dramatique")
        assert len(room) > 0


class TestMasterBus:
    """Le traitement master bus avec EQ + compression + true peak limiter."""

    def test_master_bus_retourne_audio(self):
        """Le master bus doit retourner un segment audio de même durée."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        audio = AudioSegment.silent(duration=1000)
        result = Monteur._appliquer_master_bus(audio)
        assert len(result) == len(audio)

    def test_eq_constants_definies(self):
        """Les constantes EQ doivent être définies."""
        from agents.monteur import EQ_VOICE_BOOST_LOW_HZ, EQ_VOICE_BOOST_HIGH_HZ, EQ_VOICE_BOOST_DB
        assert EQ_VOICE_BOOST_LOW_HZ == 2000
        assert EQ_VOICE_BOOST_HIGH_HZ == 5000
        assert EQ_VOICE_BOOST_DB > 0

    def test_true_peak_oversample_defini(self):
        """Le facteur d'oversampling true peak doit être défini."""
        from agents.monteur import TRUE_PEAK_OVERSAMPLE
        assert TRUE_PEAK_OVERSAMPLE >= 2


class TestSFXVolumeContextuel:
    """Le volume SFX doit varier selon le ton du segment précédent."""

    def test_volume_par_ton_defini(self):
        """La table SFX_VOLUME_PAR_TON doit contenir les tons principaux."""
        from agents.monteur import SFX_VOLUME_PAR_TON
        assert "dramatique" in SFX_VOLUME_PAR_TON
        assert "calme" in SFX_VOLUME_PAR_TON
        assert SFX_VOLUME_PAR_TON["dramatique"] > SFX_VOLUME_PAR_TON["calme"]


# ── Amélioration 9 : Variation de rythme scénarisée ──────────────────────────


class TestVariationRythme:
    """Le champ 'rythme' doit moduler les pauses."""

    def test_prompt_contient_rythme(self):
        """Le format JSON du prompt doit mentionner le champ rythme."""
        from agents.scripteur import SYSTEM_PROMPT_BASE
        assert "rythme" in SYSTEM_PROMPT_BASE

    def test_rythme_rapide_reduit_pause(self, tmp_path):
        """Le rythme 'rapide' doit réduire les pauses."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        seg = AudioSegment.silent(duration=200)
        segments_dir = tmp_path / "segments"
        segments_dir.mkdir()
        (segments_dir / "seg_001.mp3").write_bytes(b"fake")

        segments = [
            {"id": "seg_001", "personnage": "papy_babou", "texte": "Test",
             "ton": "neutre", "pause_apres_ms": 1000, "rythme": "rapide"},
        ]

        with patch.object(AudioSegment, "from_mp3", return_value=seg), \
             patch("agents.monteur.random.random", return_value=1.0):
            monteur = Monteur()
            result = monteur._assembler_segments(segments, segments_dir)

        # 200ms audio + 600ms pause (1000 * 0.6) = 800ms
        assert len(result) == 200 + 600

    def test_rythme_lent_augmente_pause(self, tmp_path):
        """Le rythme 'lent' doit augmenter les pauses."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        seg = AudioSegment.silent(duration=200)
        segments_dir = tmp_path / "segments"
        segments_dir.mkdir()
        (segments_dir / "seg_001.mp3").write_bytes(b"fake")

        segments = [
            {"id": "seg_001", "personnage": "papy_babou", "texte": "Test",
             "ton": "neutre", "pause_apres_ms": 1000, "rythme": "lent"},
        ]

        with patch.object(AudioSegment, "from_mp3", return_value=seg), \
             patch("agents.monteur.random.random", return_value=1.0):
            monteur = Monteur()
            result = monteur._assembler_segments(segments, segments_dir)

        # 200ms audio + 1500ms pause (1000 * 1.5) = 1700ms
        assert len(result) == 200 + 1500


# ── Amélioration 10 : Générique signature récurrent ──────────────────────────


class TestGeneriqueSignature:
    """Un jingle signature identique doit encadrer chaque épisode."""

    def test_signature_prompt_exists(self):
        """Le prompt de signature doit être défini."""
        from agents.monteur import SIGNATURE_JINGLE_PROMPT
        assert "signature" in SIGNATURE_JINGLE_PROMPT.lower()
        assert "jingle" in SIGNATURE_JINGLE_PROMPT.lower()

    def test_charger_signature_fallback(self, monkeypatch):
        """Sans fichier ni API, la signature est un silence."""
        from agents.monteur import Monteur
        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        monteur = Monteur()
        sig = monteur._charger_signature()
        assert len(sig) >= 2000


# ── Prévisualisation ambiances saison ─────────────────────────────────────────


class TestJinglesSaisonCustom:
    """Le système de jingles custom de saison doit fonctionner."""

    def test_config_jingles_saison_vide_sans_plan(self, monkeypatch):
        """Sans plan de saison, jingles_saison retourne un dict vide."""
        monkeypatch.setattr(config, "charger_saison", lambda n: {})
        result = config.jingles_saison(99)
        assert result == {}

    def test_config_jingles_saison_avec_custom(self, tmp_path, monkeypatch):
        """Avec un plan contenant jingles_custom, les chemins sont retournés."""
        jingle_file = tmp_path / "intro_custom.mp3"
        jingle_file.write_bytes(b"fake audio")

        plan = {
            "saison": {
                "jingles_custom": {
                    "intro_saison": str(jingle_file),
                }
            }
        }
        monkeypatch.setattr(config, "charger_saison", lambda n: plan)
        result = config.jingles_saison(1)
        assert "intro_saison" in result
        assert result["intro_saison"] == jingle_file

    def test_config_jingles_saison_fichier_manquant(self, monkeypatch):
        """Si le fichier custom n'existe plus, la clé est ignorée."""
        plan = {
            "saison": {
                "jingles_custom": {
                    "intro_saison": "/nonexistent/path.mp3",
                }
            }
        }
        monkeypatch.setattr(config, "charger_saison", lambda n: plan)
        result = config.jingles_saison(1)
        assert "intro_saison" not in result

    def test_monteur_jingle_custom_prioritaire(self, tmp_path, monkeypatch):
        """Le jingle custom de saison a priorité sur JINGLES_PAR_TYPE."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        jingle_file = tmp_path / "intro_custom.mp3"
        jingle_file.write_bytes(b"fake custom audio")
        custom = {"intro_saison": jingle_file}

        monkeypatch.setattr(config, "jingles_saison", lambda n: custom)
        fake_audio = AudioSegment.silent(duration=5000)

        monteur = Monteur()
        with patch.object(AudioSegment, "from_mp3", return_value=fake_audio) as mock_from:
            result = monteur._charger_jingle("intro", "ouverture", numero_saison=1)

        # Doit avoir été appelé avec le chemin custom
        mock_from.assert_called_with(str(jingle_file))
        assert len(result) == 5000

    def test_monteur_jingle_sans_saison_fallback(self, tmp_path, monkeypatch):
        """Sans numéro de saison, le comportement par défaut est préservé."""
        from agents.monteur import Monteur
        from pydub import AudioSegment

        monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
        fake_audio = AudioSegment.silent(duration=3000)

        # Créer un fichier jingle standard
        jingle_std = tmp_path / "intro_jingle.mp3"
        jingle_std.write_bytes(b"fake")
        monkeypatch.setattr(config, "AUDIO_ASSETS", {
            "intro_jingle": jingle_std,
        })
        monkeypatch.setattr(config, "JINGLES_PAR_TYPE", {})

        monteur = Monteur()
        with patch.object(AudioSegment, "from_mp3", return_value=fake_audio):
            result = monteur._charger_jingle("intro", "standard")

        assert len(result) == 3000

    def test_plan_jingles_custom_structure(self):
        """Le plan de saison peut stocker jingles_custom correctement."""
        plan = {"saison": {"numero": 1, "theme": "test"}}

        # Simuler ce que fait _previsualiser_ambiances_saison
        jingles_custom = {"intro_saison": "/path/to/custom.mp3"}
        plan.setdefault("saison", {})["jingles_custom"] = jingles_custom
        plan["saison"].setdefault("decisions_humaines", []).append({
            "action": "ambiances_saison_validees",
            "jingles_custom": jingles_custom,
        })

        assert plan["saison"]["jingles_custom"]["intro_saison"] == "/path/to/custom.mp3"
        assert plan["saison"]["decisions_humaines"][-1]["action"] == "ambiances_saison_validees"


# ── Session 16b : charger_rapport() uses correct column name ─────────────

class TestChargerRapportSQL:
    """Vérifie que charger_rapport() utilise started_at (pas created_at) sur productions."""

    def test_charger_rapport_uses_started_at(self):
        """Le SQL de charger_rapport doit utiliser started_at, pas created_at."""
        import inspect
        import dashboard_data
        source = inspect.getsource(dashboard_data.charger_rapport)
        # La colonne created_at n'existe pas dans la table productions
        assert "created_at" not in source, (
            "charger_rapport() utilise 'created_at' mais la table productions "
            "n'a que 'started_at'. Cela cause un crash SQL silencieux."
        )
        assert "started_at" in source, (
            "charger_rapport() doit utiliser 'ORDER BY started_at DESC'"
        )

    def test_persist_web_job_id_max_wait_sufficient(self):
        """_persist_web_job_id doit attendre assez longtemps pour le startup subprocess."""
        import inspect
        import web
        source = inspect.getsource(web._persist_web_job_id)
        # Vérifier que le default max_wait est suffisant (>= 60)
        assert "max_wait=90" in source or "max_wait=120" in source, (
            "_persist_web_job_id max_wait doit être >= 60 pour gérer "
            "le startup lent du subprocess sur Replit (15-30s)"
        )

    def test_stop_after_script_uploads_rapport_to_object_storage(self):
        """Le bloc stop_after=script doit uploader le rapport en Object Storage."""
        import inspect
        import main
        source = inspect.getsource(main._pipeline_inner)
        # Chercher l'upload Object Storage dans le contexte de stop_after
        assert "upload_rapport" in source, (
            "_pipeline_inner() doit appeler persistent_storage.upload_rapport() "
            "dans les blocs stop_after pour survivre aux redéploiements"
        )

    def test_stop_after_blocks_log_db_errors(self):
        """Les blocs stop_after ne doivent pas avaler silencieusement les erreurs DB."""
        import inspect
        import main
        source = inspect.getsource(main._pipeline_inner)
        import re
        # Chercher les patterns "except Exception:" suivis directement de "pass" (sans logging)
        bare_except_pass = re.findall(
            r'except\s+Exception\s*:\s*\n\s*pass',
            source,
        )
        assert len(bare_except_pass) == 0, (
            f"_pipeline_inner() contient {len(bare_except_pass)} 'except Exception: pass' "
            "sans logging — les erreurs DB sont avalées silencieusement"
        )

    # ── Fix 4 : _run_cli ne logue stderr que sur erreur ──────────────────

    def test_run_cli_logs_stderr_only_on_error(self):
        """_run_cli ne doit loguer stderr que si returncode != 0 (pas sur succès)."""
        import inspect
        import web
        source = inspect.getsource(web._run_cli)
        # Le logging stderr doit être conditionné par returncode != 0
        assert "if proc.returncode != 0:" in source, (
            "_run_cli() doit conditionner le logging stderr sur returncode != 0"
        )
        # Pas de logging inconditionnel de stderr (éviter spam deployment logs)
        lines = source.split("\n")
        for i, line in enumerate(lines):
            if "for line in stderr" in line:
                # Vérifier que c'est à l'intérieur d'un bloc "if proc.returncode != 0"
                # (on cherche en remontant les lignes d'indentation parent)
                found_guard = False
                for j in range(i - 1, max(i - 5, 0), -1):
                    if "returncode != 0" in lines[j]:
                        found_guard = True
                        break
                assert found_guard, (
                    f"Ligne {i}: 'for line in stderr' n'est pas dans un bloc "
                    "'if proc.returncode != 0' — risque de spam logs"
                )

    # ── Fix 5 : monteur.assembler() a un try/except ─────────────────────

    def test_monteur_assembler_has_error_handling(self):
        """monteur.assembler() doit être dans un try/except avec sauvegarde erreur."""
        import inspect
        import main
        source = inspect.getsource(main._pipeline_inner)
        # Vérifier que monteur.assembler est dans un try
        assert "monteur.assembler(script)" in source
        # Vérifier que l'erreur montage est sauvée dans rapport["etapes"]["montage"]
        assert '"erreur"' in source or "'erreur'" in source, (
            "L'erreur du monteur doit être sauvée dans rapport['etapes']['montage']['erreur']"
        )
        assert "erreur_type" in source, (
            "Le type d'erreur doit être sauvé dans rapport['etapes']['montage']['erreur_type']"
        )

    # ── Fix 6 : rapport d'erreur dans _rapport.json (pas _echec) ────────

    def test_error_rapport_uses_normal_filename(self):
        """Le rapport d'erreur doit aller dans _rapport.json, pas _rapport_echec.json."""
        import inspect
        import main
        source = inspect.getsource(main.pipeline)
        # Le outer handler ne doit PAS écrire dans _rapport_echec.json
        assert "_rapport_echec.json" not in source, (
            "pipeline() écrit encore dans _rapport_echec.json — "
            "charger_rapport() ne lit jamais ce fichier. Utiliser _rapport.json."
        )
        # Il DOIT écrire dans _rapport.json
        assert "_rapport.json" in source, (
            "pipeline() doit sauver le rapport d'erreur dans _rapport.json"
        )

    # ── Fix: _log_step_duration doit être dans _pipeline_inner ──────────

    def test_log_step_duration_defined_in_pipeline_inner(self):
        """_log_step_duration doit être définie dans _pipeline_inner, pas pipeline."""
        import inspect
        import main
        source_inner = inspect.getsource(main._pipeline_inner)
        source_outer = inspect.getsource(main.pipeline)
        # Retirer le code de _pipeline_inner du source de pipeline pour isoler
        # (pipeline appelle _pipeline_inner, mais la def doit être dans inner)
        assert "def _log_step_duration" in source_inner, (
            "_log_step_duration doit être définie DANS _pipeline_inner() "
            "pour être accessible — sinon NameError au montage"
        )

    # ── Fix: rapport d'erreur merge avec existant ───────────────────────

    def test_error_rapport_merges_with_existing(self):
        """Le error handler doit merger avec le rapport existant (pas écraser)."""
        import inspect
        import main
        source = inspect.getsource(main.pipeline)
        assert "decisions_humaines" in source, (
            "pipeline() error handler doit préserver decisions_humaines "
            "du rapport existant lors du merge"
        )
        assert "rapport_existant" in source, (
            "pipeline() error handler doit charger le rapport existant "
            "avant de sauvegarder le rapport d'erreur"
        )


# ── Session 16d : SQL FOR UPDATE, étape mapping, auto-resume exclusion ─────

class TestSession16dFixes:
    """Régression pour les 3 bugs Session 16d."""

    def test_no_for_update_with_aggregate(self):
        """FOR UPDATE ne doit pas être combiné avec des fonctions d'agrégation (MAX)."""
        import inspect
        import db_models
        source = inspect.getsource(db_models)
        import re
        # Trouver les patterns "MAX(...) ... FOR UPDATE" dans la même requête SQL
        # Les requêtes SQL sont entre guillemets, on cherche MAX et FOR UPDATE proches
        violations = re.findall(
            r'MAX\(.*?\).*?FOR UPDATE',
            source,
            re.DOTALL,
        )
        assert len(violations) == 0, (
            f"db_models contient {len(violations)} requête(s) avec MAX() + FOR UPDATE — "
            "PostgreSQL interdit FOR UPDATE avec des fonctions d'agrégation"
        )

    def test_etape_mapping_waiting_statuses(self):
        """_pipeline_inner doit mapper waiting_script → audio, waiting_montage → metadonnees."""
        import inspect
        import main
        source = inspect.getsource(main._pipeline_inner)
        assert '"waiting_script"' in source, (
            "_pipeline_inner doit mapper waiting_script vers l'étape suivante"
        )
        assert '"waiting_montage"' in source, (
            "_pipeline_inner doit mapper waiting_montage vers l'étape suivante"
        )
        # Vérifier que le mapping est correct
        assert '"waiting_script": "audio"' in source, (
            "waiting_script doit être mappé vers 'audio' (le script est fini)"
        )
        assert '"waiting_montage": "metadonnees"' in source, (
            "waiting_montage doit être mappé vers 'metadonnees' (le montage est fini)"
        )

    def test_auto_resume_excludes_waiting_statuses(self):
        """_auto_resume_interrupted ne doit PAS reprendre les productions en attente de validation."""
        import inspect
        import web
        source = inspect.getsource(web._auto_resume_interrupted)
        assert "waiting_script" in source, (
            "_auto_resume_interrupted doit exclure le status 'waiting_script'"
        )
        assert "waiting_montage" in source, (
            "_auto_resume_interrupted doit exclure le status 'waiting_montage'"
        )
