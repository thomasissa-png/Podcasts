"""Tests pour l'agent Monteur."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.monteur import Monteur


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
        # Doit retourner un AudioSegment de silence (pas d'erreur)
        assert len(audio) > 0

    def test_charger_asset_inconnu(self):
        """Un nom d'asset inconnu doit retourner un silence par défaut."""
        monteur = Monteur()
        audio = monteur._charger_asset("inexistant")
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
