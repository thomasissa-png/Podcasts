"""Tests pour l'agent Publisher."""

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.publisher import Publisher


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
    }


class TestPublisherRSS:
    """Tests de la mise à jour du flux RSS."""

    def test_mettre_a_jour_rss_creation(self, meta_exemple, tmp_path, monkeypatch):
        """Le premier appel doit créer le fichier RSS."""
        import config
        monkeypatch.setattr(config, "RSS_DIR", tmp_path)

        publisher = Publisher()
        publisher._mettre_a_jour_rss(
            meta_exemple,
            "https://example.com/episode.mp3",
            15_000_000,
        )

        feed_path = tmp_path / "feed.xml"
        assert feed_path.exists()

        tree = ET.parse(str(feed_path))
        root = tree.getroot()
        assert root.tag == "rss"

        items = root.findall(".//item")
        assert len(items) == 1
        assert items[0].find("title").text == meta_exemple["titre"]

    def test_mettre_a_jour_rss_ajout(self, meta_exemple, tmp_path, monkeypatch):
        """Les appels suivants doivent ajouter des items au RSS existant."""
        import config
        monkeypatch.setattr(config, "RSS_DIR", tmp_path)

        publisher = Publisher()

        # Premier épisode
        publisher._mettre_a_jour_rss(
            meta_exemple, "https://example.com/ep1.mp3", 15_000_000,
        )

        # Deuxième épisode
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
