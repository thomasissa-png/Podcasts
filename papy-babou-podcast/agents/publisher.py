"""Agent Publisher — Publie l'épisode sur le flux RSS et notifie les plateformes."""

import json
import logging
import uuid
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

import config

logger = logging.getLogger(__name__)

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
PODCAST_NS = "https://podcastindex.org/namespace/1.0"


class Publisher:
    """Gère la publication des épisodes via RSS et hébergeur."""

    def publier(
        self,
        meta: dict,
        chemin_audio: Path,
        taille_bytes: int,
    ) -> dict:
        """Publie un épisode complet.

        Args:
            meta: Métadonnées de l'épisode.
            chemin_audio: Chemin du fichier MP3 final.
            taille_bytes: Taille du fichier en bytes.

        Returns:
            Rapport de publication avec URLs et timestamps.
        """
        logger.info("Publication de l'épisode : %s", meta["titre"])

        # 1. Upload vers Buzzsprout
        url_audio = self._upload_buzzsprout(meta, chemin_audio, taille_bytes)

        # 2. Sauvegarder le transcript
        transcript_url = self._sauvegarder_transcript(meta)

        # 3. Mettre à jour le flux RSS local
        self._mettre_a_jour_rss(meta, url_audio, taille_bytes, transcript_url)

        # 4. Pinger les plateformes
        plateformes = self._pinger_plateformes()

        rapport = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "episode": f"S{meta['saison']:02d}E{meta['numero']:02d}",
            "titre": meta["titre"],
            "url_audio": url_audio,
            "transcript_url": transcript_url,
            "flux_rss": str(config.RSS_DIR / "feed.xml"),
            "plateformes_notifiees": plateformes,
        }

        logger.info("Publication terminée : %s", rapport["url_audio"])
        return rapport

    def _upload_buzzsprout(
        self, meta: dict, chemin_audio: Path, taille_bytes: int
    ) -> str:
        """Upload le MP3 vers Buzzsprout via leur API.

        Args:
            meta: Métadonnées de l'épisode.
            chemin_audio: Chemin du fichier MP3.
            taille_bytes: Taille du fichier.

        Returns:
            URL publique du fichier audio.
        """
        if not config.BUZZSPROUT_API_KEY or not config.BUZZSPROUT_PODCAST_ID:
            logger.warning(
                "Buzzsprout non configuré — publication simulée."
            )
            podcast_id = config.BUZZSPROUT_PODCAST_ID or "non-configure"
            return f"https://www.buzzsprout.com/{podcast_id}/episodes/simulated.mp3"

        url = (
            f"https://www.buzzsprout.com/api/{config.BUZZSPROUT_PODCAST_ID}/episodes.json"
        )
        headers = {
            "Authorization": f"Token token={config.BUZZSPROUT_API_KEY}",
        }

        with open(chemin_audio, "rb") as audio_file:
            data = {
                "title": meta["titre_court"],
                "description": meta["description_longue"],
                "summary": meta["description_courte"],
                "season_number": str(meta["saison"]),
                "episode_number": str(meta["numero"]),
                "explicit": str(meta["explicit"]).lower(),
                "private": "false",
            }
            files = {
                "audio_file": (chemin_audio.name, audio_file, "audio/mpeg"),
            }

            response = requests.post(
                url, headers=headers, data=data, files=files, timeout=300
            )
            response.raise_for_status()

        episode_data = response.json()
        url_audio = episode_data.get("audio_url", "")
        logger.info("Upload Buzzsprout réussi : %s", url_audio)
        return url_audio

    def _sauvegarder_transcript(self, meta: dict) -> str:
        """Sauvegarde le transcript en fichier texte et retourne l'URL relative.

        Args:
            meta: Métadonnées contenant le transcript.

        Returns:
            URL relative du transcript.
        """
        episode_id = f"S{meta['saison']:02d}E{meta['numero']:02d}"
        transcript = meta.get("transcript", "")
        if not transcript:
            return ""

        chemin = config.TRANSCRIPTS_DIR / f"{episode_id}_transcript.txt"
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(transcript)

        logger.info("Transcript sauvegardé : %s", chemin)

        site_web = config.PODCAST_CONFIG.get("site_web", "")
        return f"{site_web}/transcripts/{episode_id}_transcript.txt"

    def _mettre_a_jour_rss(
        self, meta: dict, url_audio: str, taille_bytes: int,
        transcript_url: str = "",
    ) -> None:
        """Met à jour le flux RSS local avec le nouvel épisode.

        Inclut les extensions podcast:transcript et podcast:chapters.

        Args:
            meta: Métadonnées de l'épisode.
            url_audio: URL publique du fichier audio.
            taille_bytes: Taille du fichier.
            transcript_url: URL du transcript (optionnel).
        """
        feed_path = config.RSS_DIR / "feed.xml"

        if feed_path.exists():
            tree = ET.parse(str(feed_path))
            root = tree.getroot()
            channel = root.find("channel")
        else:
            root = ET.Element("rss", version="2.0")
            root.set("xmlns:itunes", ITUNES_NS)
            root.set("xmlns:podcast", PODCAST_NS)
            root.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
            channel = ET.SubElement(root, "channel")
            self._creer_channel(channel)
            tree = ET.ElementTree(root)

        # S'assurer que le namespace podcast est déclaré
        if not root.get("xmlns:podcast"):
            root.set("xmlns:podcast", PODCAST_NS)

        # Ajouter le nouvel épisode
        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = meta["titre"]
        ET.SubElement(item, "description").text = meta["description_longue"]

        guid = ET.SubElement(item, "guid", isPermaLink="false")
        guid.text = str(uuid.uuid5(uuid.NAMESPACE_URL, meta["titre"]))

        now = datetime.now(timezone.utc)
        ET.SubElement(item, "pubDate").text = formatdate(
            now.timestamp(), usegmt=True
        )

        ET.SubElement(
            item,
            "enclosure",
            url=url_audio,
            length=str(taille_bytes),
            type="audio/mpeg",
        )

        ET.SubElement(
            item, f"{{{ITUNES_NS}}}duration"
        ).text = str(meta["duree_secondes"])
        ET.SubElement(
            item, f"{{{ITUNES_NS}}}season"
        ).text = str(meta["saison"])
        ET.SubElement(
            item, f"{{{ITUNES_NS}}}episode"
        ).text = str(meta["numero"])
        ET.SubElement(
            item, f"{{{ITUNES_NS}}}explicit"
        ).text = "no" if not meta["explicit"] else "yes"
        ET.SubElement(
            item, f"{{{ITUNES_NS}}}summary"
        ).text = meta["description_courte"]

        # Cover art par épisode (si disponible)
        cover_path = meta.get("cover_art_path", "")
        if cover_path:
            site_web = config.PODCAST_CONFIG.get("site_web", "")
            episode_id = f"S{meta['saison']:02d}E{meta['numero']:02d}"
            cover_url = f"{site_web}/covers/{episode_id}_cover.jpg"
            ET.SubElement(
                item, f"{{{ITUNES_NS}}}image",
                href=cover_url,
            )

        # podcast:transcript
        if transcript_url:
            ET.SubElement(
                item, f"{{{PODCAST_NS}}}transcript",
                url=transcript_url,
                type="text/plain",
                language="fr",
            )

        # podcast:chapters
        episode_id = f"S{meta['saison']:02d}E{meta['numero']:02d}"
        chapters_path = config.CHAPTERS_DIR / f"{episode_id}_chapters.json"
        if chapters_path.exists():
            site_web = config.PODCAST_CONFIG.get("site_web", "")
            chapters_url = f"{site_web}/chapters/{episode_id}_chapters.json"
            ET.SubElement(
                item, f"{{{PODCAST_NS}}}chapters",
                url=chapters_url,
                type="application/json+chapters",
            )

        # Indenter pour lisibilité
        ET.indent(tree, space="  ")
        tree.write(str(feed_path), encoding="unicode", xml_declaration=True)
        logger.info("Flux RSS mis à jour : %s", feed_path)

    def _creer_channel(self, channel: ET.Element) -> None:
        """Crée les éléments de base du channel RSS."""
        pc = config.PODCAST_CONFIG

        ET.SubElement(channel, "title").text = pc["titre"]
        ET.SubElement(channel, "link").text = pc.get("site_web", "")
        ET.SubElement(channel, "description").text = pc["description"]
        ET.SubElement(channel, "language").text = pc["langue"]

        ET.SubElement(
            channel, f"{{{ITUNES_NS}}}author"
        ).text = pc["auteur"]

        owner = ET.SubElement(channel, f"{{{ITUNES_NS}}}owner")
        ET.SubElement(
            owner, f"{{{ITUNES_NS}}}name"
        ).text = pc["auteur"]
        ET.SubElement(
            owner, f"{{{ITUNES_NS}}}email"
        ).text = pc["email_contact"]

        ET.SubElement(
            channel,
            f"{{{ITUNES_NS}}}image",
            href=pc.get("cover_url", ""),
        )

        ET.SubElement(
            channel,
            f"{{{ITUNES_NS}}}category",
            text=pc["categorie_itunes"],
        )
        ET.SubElement(
            channel, f"{{{ITUNES_NS}}}explicit"
        ).text = "no" if not pc["explicit"] else "yes"

    def _pinger_plateformes(self) -> list[str]:
        """Notifie les plateformes de distribution.

        Returns:
            Liste des plateformes notifiées avec succès.
        """
        plateformes_ok = []

        hubs = {
            "Podcast Index": "https://api.podcastindex.org/api/1.0/hub/pubnotify",
        }

        feed_url = config.PODCAST_CONFIG.get("site_web", "") + "/rss/feed.xml"

        for nom, hub_url in hubs.items():
            try:
                response = requests.post(
                    hub_url,
                    data={
                        "hub.mode": "publish",
                        "hub.url": feed_url,
                    },
                    timeout=10,
                )
                if response.status_code < 400:
                    plateformes_ok.append(nom)
                    logger.info("Ping %s : OK", nom)
                else:
                    logger.warning(
                        "Ping %s : HTTP %d", nom, response.status_code
                    )
            except requests.RequestException as e:
                logger.warning("Ping %s échoué : %s", nom, e)

        logger.info(
            "Apple Podcasts et Spotify détectent automatiquement "
            "les mises à jour du flux RSS. Deezer et Amazon Music "
            "nécessitent un enregistrement initial manuel de l'URL RSS."
        )

        return plateformes_ok
