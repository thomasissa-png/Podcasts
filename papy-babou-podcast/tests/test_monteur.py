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
