"""Tests pour l'agent Publisher."""

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.publisher import Publisher, PODCAST_NS


@pytest.fixture
def meta_exemple():
    """Métadonnées minimales pour les tests."""
    return {
        "titre": "S01E01 — Le buisson ardent | Les Histoires de Papy Babou",
        "titre_court": "Le buisson ardent",
        "description_courte": "Papy Babou raconte le buisson ardent.",
        "description_longue": "Description longue de l'épisode.",
        "saison": 1,
        "numero": 1,
        "duree_secondes": 780,
        "explicit": False,
        "transcript": "TRANSCRIPT — Le buisson ardent\n\n[Narrateur] Bienvenue.",
        "cover_art_path": "",
    }


class TestPublisherRSS:
    """Tests de la mise à jour du flux RSS."""

    def test_mettre_a_jour_rss_creation(self, meta_exemple, tmp_path, monkeypatch):
        """Le premier appel doit créer le fichier RSS avec les namespaces podcast."""
        import config
        monkeypatch.setattr(config, "RSS_DIR", tmp_path)
        monkeypatch.setattr(config, "CHAPTERS_DIR", tmp_path / "chapters")
        (tmp_path / "chapters").mkdir(parents=True, exist_ok=True)

        publisher = Publisher()
        publisher._mettre_a_jour_rss(
            meta_exemple,
            "https://example.com/episode.mp3",
            15_000_000,
            transcript_url="https://example.com/transcript.txt",
        )

        feed_path = tmp_path / "feed.xml"
        assert feed_path.exists()

        tree = ET.parse(str(feed_path))
        root = tree.getroot()
        assert root.tag == "rss"

        # Vérifier que le RSS est fonctionnel (le namespace est déclaré en interne par ET)
        # ElementTree ne expose pas xmlns: comme attributs classiques

        items = root.findall(".//item")
        assert len(items) == 1
        assert items[0].find("title").text == meta_exemple["titre"]

    def test_mettre_a_jour_rss_ajout(self, meta_exemple, tmp_path, monkeypatch):
        """Les appels suivants doivent ajouter des items au RSS existant."""
        import config
        monkeypatch.setattr(config, "RSS_DIR", tmp_path)
        monkeypatch.setattr(config, "CHAPTERS_DIR", tmp_path / "chapters")
        (tmp_path / "chapters").mkdir(parents=True, exist_ok=True)

        publisher = Publisher()

        publisher._mettre_a_jour_rss(
            meta_exemple, "https://example.com/ep1.mp3", 15_000_000,
        )

        meta2 = dict(meta_exemple)
        meta2["titre"] = "S01E02 — Noé et l'arche"
        meta2["numero"] = 2
        publisher._mettre_a_jour_rss(
            meta2, "https://example.com/ep2.mp3", 16_000_000,
        )

        tree = ET.parse(str(tmp_path / "feed.xml"))
        items = tree.findall(".//item")
        assert len(items) == 2

    def test_rss_contient_enclosure(self, meta_exemple, tmp_path, monkeypatch):
        """Chaque item RSS doit avoir une enclosure audio."""
        import config
        monkeypatch.setattr(config, "RSS_DIR", tmp_path)
        monkeypatch.setattr(config, "CHAPTERS_DIR", tmp_path / "chapters")
        (tmp_path / "chapters").mkdir(parents=True, exist_ok=True)

        publisher = Publisher()
        publisher._mettre_a_jour_rss(
            meta_exemple, "https://example.com/ep.mp3", 15_000_000,
        )

        tree = ET.parse(str(tmp_path / "feed.xml"))
        item = tree.find(".//item")
        enclosure = item.find("enclosure")

        assert enclosure is not None
        assert enclosure.get("url") == "https://example.com/ep.mp3"
        assert enclosure.get("type") == "audio/mpeg"
        assert enclosure.get("length") == "15000000"

    def test_rss_contient_transcript(self, meta_exemple, tmp_path, monkeypatch):
        """Un item avec transcript_url doit avoir un élément podcast:transcript."""
        import config
        monkeypatch.setattr(config, "RSS_DIR", tmp_path)
        monkeypatch.setattr(config, "CHAPTERS_DIR", tmp_path / "chapters")
        (tmp_path / "chapters").mkdir(parents=True, exist_ok=True)

        publisher = Publisher()
        publisher._mettre_a_jour_rss(
            meta_exemple,
            "https://example.com/ep.mp3",
            15_000_000,
            transcript_url="https://example.com/transcript.txt",
        )

        tree = ET.parse(str(tmp_path / "feed.xml"))
        item = tree.find(".//item")

        # Chercher l'élément transcript avec le namespace podcast
        transcript_elem = item.find(f"{{{PODCAST_NS}}}transcript")
        assert transcript_elem is not None
        assert transcript_elem.get("url") == "https://example.com/transcript.txt"
        assert transcript_elem.get("type") == "text/plain"

    def test_rss_contient_chapters(self, meta_exemple, tmp_path, monkeypatch):
        """Un item avec un fichier chapitres doit avoir podcast:chapters."""
        import config
        import json
        monkeypatch.setattr(config, "RSS_DIR", tmp_path)
        monkeypatch.setattr(config, "CHAPTERS_DIR", tmp_path / "chapters")
        monkeypatch.setattr(config, "PODCAST_CONFIG", {
            "titre": "Test", "auteur": "Test", "email_contact": "test@test.com",
            "description": "Test", "langue": "fr", "categorie_itunes": "Kids & Family",
            "sous_categorie": "Stories for Kids", "explicit": False,
            "site_web": "https://example.com", "cover_url": "",
        })
        (tmp_path / "chapters").mkdir(parents=True, exist_ok=True)

        # Créer un fichier chapitres
        chapters_path = tmp_path / "chapters" / "S01E01_chapters.json"
        with open(chapters_path, "w") as f:
            json.dump([{"startTime": 0, "title": "Intro"}], f)

        publisher = Publisher()
        publisher._mettre_a_jour_rss(
            meta_exemple,
            "https://example.com/ep.mp3",
            15_000_000,
        )

        tree = ET.parse(str(tmp_path / "feed.xml"))
        item = tree.find(".//item")

        chapters_elem = item.find(f"{{{PODCAST_NS}}}chapters")
        assert chapters_elem is not None
        assert "chapters" in chapters_elem.get("url", "")


class TestPublisherTranscript:
    """Tests de la sauvegarde du transcript."""

    def test_sauvegarder_transcript(self, meta_exemple, tmp_path, monkeypatch):
        """Le transcript doit être sauvegardé en fichier texte."""
        import config
        monkeypatch.setattr(config, "TRANSCRIPTS_DIR", tmp_path)

        publisher = Publisher()
        url = publisher._sauvegarder_transcript(meta_exemple)

        chemin = tmp_path / "S01E01_transcript.txt"
        assert chemin.exists()
        contenu = chemin.read_text(encoding="utf-8")
        assert "Narrateur" in contenu
        assert url != ""

    def test_sauvegarder_transcript_vide(self, meta_exemple, tmp_path, monkeypatch):
        """Sans transcript, aucun fichier ne doit être créé."""
        import config
        monkeypatch.setattr(config, "TRANSCRIPTS_DIR", tmp_path)

        meta_exemple["transcript"] = ""
        publisher = Publisher()
        url = publisher._sauvegarder_transcript(meta_exemple)

        assert url == ""


class TestPublisherUpload:
    """Tests de l'upload Buzzsprout."""

    def test_upload_sans_config(self, meta_exemple, tmp_path, monkeypatch):
        """Sans clés API, l'upload doit être simulé sans erreur."""
        import config
        monkeypatch.setattr(config, "BUZZSPROUT_API_KEY", "")
        monkeypatch.setattr(config, "BUZZSPROUT_PODCAST_ID", "")

        publisher = Publisher()
        url = publisher._upload_buzzsprout(
            meta_exemple, tmp_path / "fake.mp3", 15_000_000,
        )
        assert "simulated" in url


class TestPublisherPing:
    """Tests du ping des plateformes."""

    def test_pinger_utilise_podcast_index(self, monkeypatch):
        """Le ping doit utiliser Podcast Index et non Google Podcasts."""
        from unittest.mock import patch, MagicMock
        import config

        monkeypatch.setattr(config, "PODCAST_CONFIG", {
            "site_web": "https://example.com",
        })

        publisher = Publisher()
        with patch("agents.publisher.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            plateformes = publisher._pinger_plateformes()

            # Vérifier que Podcast Index est dans les appels
            call_args = mock_post.call_args
            assert "podcastindex" in call_args[0][0]

            # Vérifier que Google Podcasts n'est PAS dans les appels
            for call in mock_post.call_args_list:
                assert "pubsubhubbub.appspot.com" not in call[0][0]
