"""Agent SFX Provider — Fournit les bruitages via ElevenLabs ou Freesound."""

import logging
import random
import time
from pathlib import Path

import requests

import config
from utils import slug as _slug_util

logger = logging.getLogger(__name__)

ELEVENLABS_SFX_URL = "https://api.elevenlabs.io/v1/sound-generation"
FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"

# Suggestions SFX thématiques par ambiance — aide le scripteur et le reviewer
# à vérifier la cohérence des bruitages avec l'ambiance choisie.
SFX_PAR_AMBIANCE = {
    "joyeux": [
        "rires d'enfants", "oiseaux qui chantent", "clochettes",
        "musique festive au loin", "applaudissements",
    ],
    "dramatique": [
        "tonnerre au loin", "vent violent", "tambours graves",
        "craquement sinistre", "souffle de tempête",
    ],
    "calme": [
        "ruisseau qui coule", "vent doux dans les feuilles",
        "feu de cheminée", "grillons la nuit", "ronronnement de chat",
    ],
    "mystere": [
        "pas dans un couloir", "porte qui grince", "murmures lointains",
        "chouette dans la nuit", "écho dans une grotte",
    ],
    "epique": [
        "fanfare de trompettes", "galop de chevaux", "vagues sur la côte",
        "vent du désert", "pierres qui s'effondrent",
    ],
    "tendre": [
        "berceuse lointaine", "feu de cheminée doux", "pluie légère",
        "chat qui ronronne", "pages d'un livre qu'on tourne",
    ],
    "humoristique": [
        "boing comique", "glissade", "éternuement exagéré",
        "poule qui caquette", "ressort qui bondit",
    ],
    "solennel": [
        "cloches d'église", "chœur lointain", "vent sacré",
        "écho dans un temple", "tonnerre majestueux",
    ],
}


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
            # Valider que le chemin résolu reste dans SFX_DIR (protection path traversal)
            if not str(chemin_local.resolve()).startswith(str(config.SFX_DIR.resolve())):
                logger.warning(
                    "  SFX '%s' — chemin potentiellement dangereux, ignoré.",
                    segment["texte"],
                )
                chemin_local = config.SFX_DIR / "nonexistent.mp3"
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
                config.rate_limiter_elevenlabs.attendre()
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

    @staticmethod
    def suggerer_sfx(ambiance: str) -> list[str]:
        """Retourne les suggestions SFX adaptées à une ambiance.

        Args:
            ambiance: L'ambiance de l'épisode (joyeux, dramatique, etc.).

        Returns:
            Liste de descriptions SFX suggérées.
        """
        return SFX_PAR_AMBIANCE.get(ambiance, SFX_PAR_AMBIANCE.get("calme", []))

    def auditer_niveaux_audio(
        self, script: dict, fichiers_sfx: list[Path]
    ) -> dict:
        """Audite les niveaux audio des SFX générés.

        Vérifie que chaque fichier SFX a un volume correct, une durée
        cohérente avec la cible, et n'est pas du silence pur.

        Args:
            script: Script JSON structuré (pour les durées cibles).
            fichiers_sfx: Liste des chemins vers les fichiers SFX générés.

        Returns:
            Dict avec clés:
              - "ok" (bool): True si tous les SFX sont exploitables.
              - "alertes" (list[str]): Problèmes détectés.
              - "details" (list[dict]): Détails par SFX.
        """
        from pydub import AudioSegment

        alertes = []
        details = []

        # Construire la map segment_id → segment pour les durées cibles
        sfx_map = {}
        for seg in script.get("episode", {}).get("segments", []):
            if seg.get("personnage") == "sfx":
                sfx_map[seg["id"]] = seg

        for chemin in fichiers_sfx:
            seg_id = chemin.stem
            segment_info = sfx_map.get(seg_id, {})
            duree_cible = segment_info.get("duree_sfx_secondes", 5.0)
            mode = segment_info.get("mode", "insert")

            detail = {
                "id": seg_id,
                "fichier": str(chemin),
                "mode": mode,
                "duree_cible_s": duree_cible,
            }

            try:
                if not chemin.exists():
                    alertes.append(
                        f"SFX '{seg_id}' : fichier manquant ({chemin})."
                    )
                    detail["status"] = "manquant"
                    details.append(detail)
                    continue

                # Vérifier la taille (< 1KB = probablement vide/corrompu)
                taille = chemin.stat().st_size
                detail["taille_kb"] = round(taille / 1024, 1)
                if taille < 1024:
                    alertes.append(
                        f"SFX '{seg_id}' : fichier trop petit ({taille} octets), "
                        f"probablement du silence ou corrompu."
                    )
                    detail["status"] = "trop_petit"
                    details.append(detail)
                    continue

                audio = AudioSegment.from_mp3(str(chemin))
                duree_reelle = len(audio) / 1000.0
                detail["duree_reelle_s"] = round(duree_reelle, 1)

                # Niveau sonore (dBFS)
                dbfs = audio.dBFS
                detail["dbfs"] = round(dbfs, 1)

                # Vérifier si c'est du silence pur (< -50 dBFS)
                if dbfs < -50:
                    alertes.append(
                        f"SFX '{seg_id}' : niveau trop bas ({dbfs:.1f} dBFS), "
                        f"quasi-silence. Le SFX sera inaudible."
                    )
                    detail["status"] = "silence"
                elif dbfs > -3:
                    alertes.append(
                        f"SFX '{seg_id}' : niveau trop élevé ({dbfs:.1f} dBFS), "
                        f"risque de saturation et de masquer les voix."
                    )
                    detail["status"] = "trop_fort"
                else:
                    detail["status"] = "ok"

                # Vérifier l'écart de durée (> 50% d'écart)
                if duree_cible > 0:
                    ecart = abs(duree_reelle - duree_cible) / duree_cible
                    detail["ecart_duree_pct"] = round(ecart * 100, 0)
                    if ecart > 0.5:
                        alertes.append(
                            f"SFX '{seg_id}' : durée réelle {duree_reelle:.1f}s "
                            f"vs cible {duree_cible:.1f}s (écart {ecart:.0%})."
                        )

            except Exception as e:
                alertes.append(
                    f"SFX '{seg_id}' : erreur de lecture ({e})."
                )
                detail["status"] = "erreur"

            details.append(detail)

        # Vérifier la cohérence globale des niveaux
        niveaux = [d["dbfs"] for d in details if "dbfs" in d]
        if len(niveaux) >= 2:
            ecart_max = max(niveaux) - min(niveaux)
            if ecart_max > 20:
                alertes.append(
                    f"Écart de volume entre SFX trop important : "
                    f"{ecart_max:.1f} dB (de {min(niveaux):.1f} à "
                    f"{max(niveaux):.1f} dBFS). Normaliser les niveaux."
                )

        nb_problemes = sum(1 for d in details if d.get("status") not in ("ok",))
        return {
            "ok": nb_problemes == 0,
            "alertes": alertes,
            "details": details,
            "stats": {
                "nb_sfx_audites": len(details),
                "nb_ok": sum(1 for d in details if d.get("status") == "ok"),
                "nb_problemes": nb_problemes,
                "dbfs_moyen": round(
                    sum(niveaux) / len(niveaux), 1
                ) if niveaux else None,
            },
        }

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
    return _slug_util(texte)
