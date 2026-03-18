"""Tests pour les améliorations de l'audit du directeur podcast."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agents.scripteur import (
    Scripteur,
    SYSTEM_PROMPT_BASE,
    STRUCTURES_NARRATIVES,
    _construire_bible_personnages,
)


# ── Tests Config ─────────────────────────────────────────────────────────────

class TestConfigAudit:
    """Tests des changements de configuration."""

    def test_stereo_pan_reduit(self):
        """Le stereo pan doit être réduit à -0.2/+0.2 (compatible casque/mono)."""
        assert config.STEREO_PAN["antoine"] == -0.2
        assert config.STEREO_PAN["noemie"] == 0.2
        assert config.STEREO_PAN["mamie_sonia"] == 0.15

    def test_voice_gain_db_existe(self):
        """Le gain de normalisation par personnage doit exister."""
        assert hasattr(config, "VOICE_GAIN_DB")
        assert "papy_babou" in config.VOICE_GAIN_DB
        assert "antoine" in config.VOICE_GAIN_DB
        assert "noemie" in config.VOICE_GAIN_DB

    def test_voice_gain_enfants_positif(self):
        """Les enfants doivent avoir un gain positif (voix plus faibles)."""
        assert config.VOICE_GAIN_DB["antoine"] > 0
        assert config.VOICE_GAIN_DB["noemie"] > 0

    def test_segment_max_mots(self):
        """Les limites de mots par segment doivent être définies."""
        assert config.SEGMENT_MAX_MOTS_ENFANT == 40
        assert config.SEGMENT_MAX_MOTS_ADULTE == 60

    def test_personnages_enfants(self):
        """La liste des personnages enfants doit être correcte."""
        assert "antoine" in config.PERSONNAGES_ENFANTS
        assert "noemie" in config.PERSONNAGES_ENFANTS
        assert "papy_babou" not in config.PERSONNAGES_ENFANTS

    def test_prononciation_biblique(self):
        """Le dictionnaire de prononciation doit contenir les noms courants."""
        assert hasattr(config, "PRONONCIATION_BIBLIQUE")
        assert "Moïse" in config.PRONONCIATION_BIBLIQUE
        assert "Pharaon" in config.PRONONCIATION_BIBLIQUE
        assert "Goliath" in config.PRONONCIATION_BIBLIQUE
        assert len(config.PRONONCIATION_BIBLIQUE) >= 20

    def test_mots_interdits_mort_autorise(self):
        """'mort' et 'mourir' doivent être retirés des mots interdits (usage biblique factuel)."""
        assert "mort" not in config.MOTS_INTERDITS
        assert "mourir" not in config.MOTS_INTERDITS
        assert "mortelle" not in config.MOTS_INTERDITS

    def test_mots_interdits_violence_reste(self):
        """Les mots de violence graphique doivent rester interdits."""
        assert "massacre" in config.MOTS_INTERDITS
        assert "égorger" in config.MOTS_INTERDITS
        assert "torturer" in config.MOTS_INTERDITS

    def test_mots_interdits_meta_reste(self):
        """Les mots méta doivent rester interdits."""
        assert "saison" in config.MOTS_INTERDITS
        assert "podcast" in config.MOTS_INTERDITS


# ── Tests Scripteur Prompt ───────────────────────────────────────────────────

class TestScripteurPromptAudit:
    """Tests des améliorations du prompt scripteur."""

    def test_cold_open_dans_prompt(self):
        """Le prompt doit mentionner le cold open."""
        assert "COLD OPEN" in SYSTEM_PROMPT_BASE

    def test_segment_longueur_dans_prompt(self):
        """Le prompt doit mentionner la limite de mots par segment."""
        assert "40 MOTS MAXIMUM" in SYSTEM_PROMPT_BASE
        assert "60 MOTS MAXIMUM" in SYSTEM_PROMPT_BASE

    def test_recap_dans_prompt(self):
        """Le prompt doit mentionner le récap de fin."""
        assert "RÉCAP" in SYSTEM_PROMPT_BASE or "récap" in SYSTEM_PROMPT_BASE.lower()
        assert "retenu" in SYSTEM_PROMPT_BASE.lower()

    def test_mamie_sonia_enrichie_dans_prompt(self):
        """Le prompt doit exiger un vrai moment pour Mamie Sonia."""
        assert "Mamie Sonia" in SYSTEM_PROMPT_BASE
        assert "AU MOINS un vrai moment" in SYSTEM_PROMPT_BASE

    def test_sfx_minimum_25(self):
        """Le prompt doit exiger au minimum 25 bruitages."""
        assert "25 bruitages" in SYSTEM_PROMPT_BASE

    def test_sfx_continus(self):
        """Le prompt doit mentionner les ambiances continues."""
        assert "CONTINUS" in SYSTEM_PROMPT_BASE or "CONTINU" in SYSTEM_PROMPT_BASE

    def test_quiz_dans_format(self):
        """Le format JSON doit inclure le champ quiz."""
        assert "quiz" in SYSTEM_PROMPT_BASE


# ── Tests Structures Narratives ──────────────────────────────────────────────

class TestStructuresNarratives:
    """Tests des structures narratives mises à jour."""

    def test_cold_open_standard(self):
        """La structure standard doit commencer par un cold open."""
        assert "COLD OPEN" in STRUCTURES_NARRATIVES["standard"]

    def test_cold_open_ouverture(self):
        """La structure ouverture doit commencer par un cold open."""
        assert "COLD OPEN" in STRUCTURES_NARRATIVES["ouverture"]

    def test_cold_open_mi_saison(self):
        """La structure mi-saison doit commencer par un cold open."""
        assert "COLD OPEN" in STRUCTURES_NARRATIVES["mi-saison"]

    def test_cold_open_final(self):
        """La structure final doit commencer par un cold open."""
        assert "COLD OPEN" in STRUCTURES_NARRATIVES["final"]

    def test_accroche_courte_standard(self):
        """L'accroche standard doit être de 90 secondes max."""
        assert "90 secondes" in STRUCTURES_NARRATIVES["standard"]

    def test_recap_standard(self):
        """La conclusion standard doit inclure un récap."""
        assert "RÉCAP" in STRUCTURES_NARRATIVES["standard"]

    def test_mamie_sonia_dans_developpement(self):
        """Le développement doit mentionner Mamie Sonia."""
        assert "Mamie Sonia" in STRUCTURES_NARRATIVES["standard"]

    def test_sfx_continus_dans_developpement(self):
        """Le développement doit mentionner les SFX continus."""
        assert "CONTINUS" in STRUCTURES_NARRATIVES["standard"]


# ── Tests Validation Longueur Segments ───────────────────────────────────────

class TestValiderLongueurSegments:
    """Tests de la validation de longueur des segments."""

    def test_segment_enfant_trop_long(self, caplog):
        """Un segment enfant de plus de 40 mots doit générer un warning."""
        import logging
        script = {"episode": {"segments": [
            {"id": "seg_001", "personnage": "antoine",
             "texte": " ".join(["mot"] * 50), "ton": "curieux"},
        ]}}
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_longueur_segments(script)
        assert any("trop long" in m for m in caplog.messages)

    def test_segment_adulte_trop_long(self, caplog):
        """Un segment adulte de plus de 60 mots doit générer un warning."""
        import logging
        script = {"episode": {"segments": [
            {"id": "seg_001", "personnage": "papy_babou",
             "texte": " ".join(["mot"] * 70), "ton": "chaleureux"},
        ]}}
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_longueur_segments(script)
        assert any("trop long" in m for m in caplog.messages)

    def test_segment_ok_pas_de_warning(self, caplog):
        """Un segment dans les limites ne doit pas générer de warning."""
        import logging
        script = {"episode": {"segments": [
            {"id": "seg_001", "personnage": "antoine",
             "texte": " ".join(["mot"] * 30), "ton": "curieux"},
            {"id": "seg_002", "personnage": "papy_babou",
             "texte": " ".join(["mot"] * 50), "ton": "chaleureux"},
        ]}}
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_longueur_segments(script)
        assert not any("trop long" in m for m in caplog.messages)

    def test_sfx_ignore(self, caplog):
        """Les segments SFX ne doivent pas être vérifiés."""
        import logging
        script = {"episode": {"segments": [
            {"id": "sfx_001", "personnage": "sfx",
             "texte": " ".join(["mot"] * 100), "ton": "ambiance"},
        ]}}
        with caplog.at_level(logging.WARNING, logger="agents.scripteur"):
            Scripteur._valider_longueur_segments(script)
        assert not any("trop long" in m for m in caplog.messages)


# ── Tests Personnages Bible ──────────────────────────────────────────────────

class TestPersonnagesBible:
    """Tests des mises à jour du fichier personnages.json."""

    def test_noemie_maligne(self):
        """Noémie doit être décrite comme maligne/intelligente."""
        data = config.charger_personnages()
        if not data:
            pytest.skip("personnages.json non disponible")
        noemie = data["personnages"]["noemie"]
        assert "maligne" in noemie["description"].lower() or "futée" in noemie["description"].lower()

    def test_mamie_sonia_enrichie(self):
        """Mamie Sonia doit avoir des interventions enrichies."""
        data = config.charger_personnages()
        if not data:
            pytest.skip("personnages.json non disponible")
        sonia = data["personnages"]["mamie_sonia"]
        interventions = " ".join(sonia.get("interventions_typiques", []))
        assert "souvenir" in interventions.lower() or "Caire" in interventions

    def test_mamie_sonia_frequence_enrichie(self):
        """La fréquence de Mamie Sonia doit mentionner au moins une vraie intervention."""
        data = config.charger_personnages()
        if not data:
            pytest.skip("personnages.json non disponible")
        sonia = data["personnages"]["mamie_sonia"]
        assert "AU MOINS" in sonia.get("frequence", "")


# ── Tests Monteur ────────────────────────────────────────────────────────────

class TestMonteurAudit:
    """Tests des améliorations audio du monteur."""

    def test_ambiance_prompts_plus_riches(self):
        """Les prompts d'ambiance doivent être plus descriptifs et aventureux."""
        from agents.monteur import AMBIANCE_PROMPTS
        # epique doit être cinématique/aventure
        assert "adventure" in AMBIANCE_PROMPTS["epique"].lower() or "cinematic" in AMBIANCE_PROMPTS["epique"].lower()
        # dramatique doit être plus intense
        assert "cinematic" in AMBIANCE_PROMPTS["dramatique"].lower() or "tension" in AMBIANCE_PROMPTS["dramatique"].lower()
        # Chaque prompt doit être substantiel (pas une ligne générique)
        for key, prompt in AMBIANCE_PROMPTS.items():
            assert len(prompt) > 80, f"Prompt '{key}' trop court : {len(prompt)} chars"

    def test_transition_pas_chime_mecanique(self):
        """La transition ne doit plus être un simple chime mécanique."""
        from agents.monteur import TRANSITION_PROMPT
        assert "chime" not in TRANSITION_PROMPT.lower() or "whoosh" in TRANSITION_PROMPT.lower()

    def test_voice_gain_applique(self):
        """Le monteur doit appliquer le gain par personnage (vérification grep)."""
        import agents.monteur as monteur_module
        import inspect
        source = inspect.getsource(monteur_module)
        assert "VOICE_GAIN_DB" in source


# ── Tests Metadonnees Quiz ───────────────────────────────────────────────────

class TestMetadonneesQuiz:
    """Tests de la génération de quiz dans les métadonnées."""

    def test_quiz_dans_system_prompt(self):
        """Le system prompt des métadonnées doit mentionner le quiz."""
        from agents.metadonnees import SYSTEM_PROMPT
        assert "quiz" in SYSTEM_PROMPT.lower()

    def test_quiz_3_questions(self):
        """Le system prompt doit demander 3 questions."""
        from agents.metadonnees import SYSTEM_PROMPT
        assert "3 questions" in SYSTEM_PROMPT
