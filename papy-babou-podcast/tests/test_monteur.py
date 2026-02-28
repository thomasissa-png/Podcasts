"""Tests pour l'agent Monteur."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.monteur import Monteur, _appliquer_pan


class TestMonteurSlug:
    """Tests de la fonction slug."""

    def test_slug_simple(self):
        """Un titre simple doit être correctement converti en slug."""
        monteur = Monteur()
        assert monteur._slug("Le buisson ardent") == "le_buisson_ardent"

    def test_slug_avec_accents(self):
        """Les accents doivent être retirés."""
        monteur = Monteur()
        assert monteur._slug("Moïse et la Mer Rouge") == "moise_et_la_mer_rouge"

    def test_slug_avec_caracteres_speciaux(self):
        """Les caractères spéciaux doivent être retirés."""
        monteur = Monteur()
        result = monteur._slug("L'arche de Noé !")
        assert "'" not in result
        assert "!" not in result


class TestMonteurAssets:
    """Tests du chargement d'assets."""

    def test_charger_asset_inexistant(self):
        """Un asset inexistant doit retourner un silence de remplacement."""
        monteur = Monteur()
        audio = monteur._charger_asset("intro_jingle")
        assert len(audio) > 0

    def test_charger_asset_inconnu(self):
        """Un nom d'asset inconnu doit retourner un silence par défaut."""
        monteur = Monteur()
        audio = monteur._charger_asset("inexistant")
        assert len(audio) > 0


class TestMonteurAmbiance:
    """Tests du chargement d'ambiance musicale."""

    def test_charger_ambiance_inexistante(self):
        """Une ambiance inexistante doit fallback vers fond_doux."""
        monteur = Monteur()
        audio = monteur._charger_ambiance("joyeux")
        # Même si l'ambiance n'existe pas, on doit avoir du silence
        assert len(audio) > 0

    def test_charger_ambiance_inconnue(self):
        """Un nom d'ambiance inconnu doit fallback vers fond_doux."""
        monteur = Monteur()
        audio = monteur._charger_ambiance("ambiance_inconnue_xyz")
        assert len(audio) > 0


class TestMonteurAssemblage:
    """Tests de l'assemblage des segments."""

    def test_assembler_segments_manquants(self, script_exemple, tmp_path):
        """Des segments manquants doivent lever une erreur."""
        monteur = Monteur()
        with pytest.raises(FileNotFoundError, match="introuvable"):
            monteur._assembler_segments(
                script_exemple["episode"]["segments"],
                tmp_path,
            )


class TestMonteurOverlaysPending:
    """Tests du nettoyage des overlays en fin de script."""

    def test_overlay_en_fin_de_script(self, tmp_path):
        """Un SFX overlay en fin de script doit être inséré séquentiellement."""
        from unittest.mock import patch, MagicMock
        from pydub import AudioSegment

        voix = AudioSegment.silent(duration=500)
        sfx = AudioSegment.silent(duration=300)

        segments_dir = tmp_path / "segments"
        segments_dir.mkdir()
        # Créer des fichiers factices (le contenu n'importe pas car on mock from_mp3)
        (segments_dir / "seg_001.mp3").write_bytes(b"fake")
        (segments_dir / "sfx_001.mp3").write_bytes(b"fake")

        segments = [
            {"id": "seg_001", "personnage": "narrateur", "texte": "Bonjour", "ton": "neutre", "pause_apres_ms": 0},
            {"id": "sfx_001", "personnage": "sfx", "texte": "vent", "ton": "ambiance", "pause_apres_ms": 0, "duree_sfx_secondes": 0.5, "mode": "overlay"},
        ]

        with patch.object(AudioSegment, "from_mp3", side_effect=[voix, sfx]):
            monteur = Monteur()
            result = monteur._assembler_segments(segments, segments_dir)

        # L'overlay en fin de script doit être ajouté (voix 500ms + sfx 300ms)
        assert len(result) >= len(voix) + len(sfx)


class TestMonteurJingles:
    """Tests de la sélection dynamique de jingles."""

    def test_charger_jingle_standard_fallback(self):
        """Un type standard doit fallback vers le jingle par défaut."""
        monteur = Monteur()
        audio = monteur._charger_jingle("intro", "standard")
        assert len(audio) > 0

    def test_charger_jingle_type_inconnu_fallback(self):
        """Un type inconnu doit fallback vers le jingle par défaut."""
        monteur = Monteur()
        audio = monteur._charger_jingle("intro", "type_inconnu")
        assert len(audio) > 0

    def test_charger_jingle_ouverture(self, tmp_path, monkeypatch):
        """Un type ouverture avec jingle existant doit le charger."""
        import config
        from pydub import AudioSegment
        from unittest.mock import patch

        chemin = tmp_path / "intro_saison.mp3"
        chemin.write_bytes(b"fake")

        monkeypatch.setattr(config, "JINGLES_PAR_TYPE", {
            "ouverture": {"intro": chemin},
        })

        fake_audio = AudioSegment.silent(duration=1000)
        with patch.object(AudioSegment, "from_mp3", return_value=fake_audio):
            monteur = Monteur()
            audio = monteur._charger_jingle("intro", "ouverture")
        assert len(audio) > 0


class TestAppliquerPan:
    """Tests du panoramique stéréo."""

    def test_pan_centre(self):
        """Un pan à 0.0 doit retourner un audio stéréo."""
        from pydub import AudioSegment
        audio = AudioSegment.silent(duration=100)
        result = _appliquer_pan(audio, 0.0)
        assert result.channels == 2

    def test_pan_gauche(self):
        """Un pan négatif doit fonctionner."""
        from pydub import AudioSegment
        audio = AudioSegment.silent(duration=100)
        result = _appliquer_pan(audio, -0.3)
        assert result.channels == 2

    def test_pan_droite(self):
        """Un pan positif doit fonctionner."""
        from pydub import AudioSegment
        audio = AudioSegment.silent(duration=100)
        result = _appliquer_pan(audio, 0.3)
        assert result.channels == 2
