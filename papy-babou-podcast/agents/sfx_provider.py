"""Agent SFX Provider — Fournit les bruitages via ElevenLabs ou Freesound."""

import logging
import random
import time
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

ELEVENLABS_SFX_URL = "https://api.elevenlabs.io/v1/sound-generation"
FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"


class SfxProvider:
    """Fournit les bruitages : ElevenLabs SFX en priorité, Freesound en fallback."""

    def __init__(self):
        self.elevenlabs_api_key = config.ELEVENLABS_API_KEY
        self.freesound_api_key = config.FREESOUND_API_KEY
        self.cache_dir = config.SFX_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stats: dict[str, str] = {}  # segment_id → source utilisée

    def produire_sfx(self, script: dict) -> list[Path]:
        """Produit tous les fichiers SFX pour les segments 'sfx' du script.

        Args:
            script: Script JSON validé.

        Returns:
            Liste des chemins vers les fichiers SFX générés.
        """
        episode = script["episode"]
        episode_id = f"S{episode['saison']:02d}E{episode['numero']:02d}"
        dossier = config.SEGMENTS_DIR / episode_id
        dossier.mkdir(parents=True, exist_ok=True)

        fichiers = []
        segments_sfx = [s for s in episode["segments"] if s["personnage"] == "sfx"]

        if not segments_sfx:
            logger.info("[%s] Aucun segment SFX dans le script.", episode_id)
            return fichiers

        logger.info(
            "[%s] %d bruitages à générer", episode_id, len(segments_sfx)
        )

        for segment in segments_sfx:
            chemin = dossier / f"{segment['id']}.mp3"

            # Vérifier le cache local (assets/sfx/)
            chemin_local = config.SFX_DIR / f"{segment['texte']}.mp3"
            if chemin_local.exists():
                logger.info(
                    "  SFX '%s' trouvé en local : %s",
                    segment["texte"],
                    chemin_local,
                )
                _copier_fichier(chemin_local, chemin)
                self.stats[segment["id"]] = "local"
                fichiers.append(chemin)
                continue

            # Vérifier le cache de génération
            chemin_cache = self.cache_dir / f"{_slug_sfx(segment['texte'])}.mp3"
            if chemin_cache.exists():
                logger.info(
                    "  SFX '%s' trouvé en cache : %s",
                    segment["texte"],
                    chemin_cache,
                )
                _copier_fichier(chemin_cache, chemin)
                self.stats[segment["id"]] = "cache"
                fichiers.append(chemin)
                continue

            # Essayer ElevenLabs SFX d'abord
            if self.elevenlabs_api_key:
                ok = self._generer_elevenlabs(segment, chemin, chemin_cache)
                if ok:
                    fichiers.append(chemin)
                    continue

            # Fallback : Freesound
            if self.freesound_api_key:
                ok = self._telecharger_freesound(segment, chemin, chemin_cache)
                if ok:
                    fichiers.append(chemin)
                    continue

            # Dernier recours : silence
            logger.warning(
                "  SFX '%s' introuvable — remplacement par du silence.",
                segment["texte"],
            )
            self._generer_silence(segment, chemin)
            self.stats[segment["id"]] = "silence"
            fichiers.append(chemin)

        self._logger_stats(episode_id)
        return fichiers

    def _generer_elevenlabs(
        self, segment: dict, chemin_sortie: Path, chemin_cache: Path
    ) -> bool:
        """Génère un bruitage via ElevenLabs Text-to-Sound-Effects.

        Utilise un backoff exponentiel avec jitter.

        Args:
            segment: Segment SFX du script.
            chemin_sortie: Chemin du fichier MP3 final.
            chemin_cache: Chemin du fichier en cache.

        Returns:
            True si la génération a réussi.
        """
        description = segment["texte"]
        duree = min(segment.get("duree_sfx_secondes", 5.0), 22.0)

        headers = {
            "xi-api-key": self.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": description,
            "duration_seconds": duree,
            "prompt_influence": 0.7,
        }

        max_tentatives = config.PRODUCTION.get("max_retry_tts", 3)

        for tentative in range(1, max_tentatives + 1):
            try:
                response = requests.post(
                    ELEVENLABS_SFX_URL,
                    json=payload,
                    headers=headers,
                    timeout=60,
                )
                response.raise_for_status()

                # Sauvegarder en cache et à destination
                chemin_cache.parent.mkdir(parents=True, exist_ok=True)
                with open(chemin_cache, "wb") as f:
                    f.write(response.content)
                _copier_fichier(chemin_cache, chemin_sortie)

                logger.info(
                    "  SFX '%s' généré via ElevenLabs (%.1f KB)",
                    description,
                    len(response.content) / 1024,
                )
                self.stats[segment["id"]] = "elevenlabs"
                return True

            except requests.RequestException as e:
                logger.warning(
                    "  ElevenLabs SFX tentative %d/%d échouée pour '%s' : %s",
                    tentative,
                    max_tentatives,
                    description,
                    e,
                )
                if tentative < max_tentatives:
                    delai = (2 ** tentative) + random.uniform(0, 1)
                    time.sleep(delai)

        return False

    def _telecharger_freesound(
        self, segment: dict, chemin_sortie: Path, chemin_cache: Path
    ) -> bool:
        """Télécharge un bruitage depuis Freesound.org.

        Args:
            segment: Segment SFX du script.
            chemin_sortie: Chemin du fichier MP3 final.
            chemin_cache: Chemin du fichier en cache.

        Returns:
            True si le téléchargement a réussi.
        """
        description = segment["texte"]
        duree_max = segment.get("duree_sfx_secondes", 10.0)

        params = {
            "query": description,
            "filter": f"duration:[0.5 TO {duree_max}]",
            "sort": "rating_desc",
            "fields": "id,name,previews,license",
            "page_size": 5,
            "token": self.freesound_api_key,
        }

        try:
            response = requests.get(
                FREESOUND_SEARCH_URL, params=params, timeout=15
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("results"):
                logger.warning(
                    "  Freesound : aucun résultat pour '%s'", description
                )
                return False

            # Prendre le premier résultat
            son = data["results"][0]
            preview_url = son["previews"].get(
                "preview-hq-mp3",
                son["previews"].get("preview-lq-mp3", ""),
            )

            if not preview_url:
                logger.warning(
                    "  Freesound : pas de preview MP3 pour '%s'", son["name"]
                )
                return False

            # Télécharger le preview
            resp_audio = requests.get(preview_url, timeout=30)
            resp_audio.raise_for_status()

            chemin_cache.parent.mkdir(parents=True, exist_ok=True)
            with open(chemin_cache, "wb") as f:
                f.write(resp_audio.content)
            _copier_fichier(chemin_cache, chemin_sortie)

            logger.info(
                "  SFX '%s' téléchargé depuis Freesound (%s, %.1f KB)",
                description,
                son["name"],
                len(resp_audio.content) / 1024,
            )
            self.stats[segment["id"]] = f"freesound ({son['name']})"
            return True

        except requests.RequestException as e:
            logger.warning(
                "  Freesound échoué pour '%s' : %s", description, e
            )
            return False

    def _generer_silence(self, segment: dict, chemin_sortie: Path) -> None:
        """Génère un fichier de silence en remplacement d'un SFX introuvable."""
        from pydub import AudioSegment

        duree_ms = int(segment.get("duree_sfx_secondes", 2.0) * 1000)
        silence = AudioSegment.silent(duration=duree_ms)
        silence.export(str(chemin_sortie), format="mp3")

    def _logger_stats(self, episode_id: str) -> None:
        """Affiche un résumé des sources SFX utilisées."""
        if not self.stats:
            return
        logger.info("── Sources SFX pour %s ──", episode_id)
        for seg_id, source in sorted(self.stats.items()):
            logger.info("  %s : %s", seg_id, source)


def _copier_fichier(source: Path, destination: Path) -> None:
    """Copie un fichier source vers destination."""
    import shutil

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(destination))


def _slug_sfx(texte: str) -> str:
    """Convertit une description SFX en slug pour nom de fichier cache."""
    import re
    import unicodedata

    texte = unicodedata.normalize("NFKD", texte)
    texte = texte.encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^\w\s-]", "", texte).strip().lower()
    return re.sub(r"[-\s]+", "_", texte)
