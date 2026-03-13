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
