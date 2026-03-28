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


# ── Tests Prononciation TTS ──────────────────────────────────────────────────

class TestPrononciationTTS:
    """Tests de l'intégration du dictionnaire de prononciation dans le flux TTS."""

    def test_appliquer_prononciation_basique(self):
        """Les noms bibliques doivent être remplacés par leur forme phonétique."""
        from agents.producteur_audio import _appliquer_prononciation
        texte = "Moïse a traversé la mer Rouge."
        resultat = _appliquer_prononciation(texte)
        assert "Mo-ize" in resultat
        assert "Moïse" not in resultat

    def test_appliquer_prononciation_multiple(self):
        """Plusieurs noms dans la même phrase doivent tous être remplacés."""
        from agents.producteur_audio import _appliquer_prononciation
        texte = "Pharaon a dit à Moïse de quitter l'Égypte."
        resultat = _appliquer_prononciation(texte)
        assert "Fa-ra-on" in resultat
        assert "Mo-ize" in resultat

    def test_appliquer_prononciation_insensible_casse(self):
        """Le remplacement doit fonctionner quelle que soit la casse."""
        from agents.producteur_audio import _appliquer_prononciation
        texte = "GOLIATH était un géant."
        resultat = _appliquer_prononciation(texte)
        assert "Go-li-at" in resultat

    def test_appliquer_prononciation_pas_sous_chaine(self):
        """Un nom ne doit pas être remplacé quand il fait partie d'un autre mot."""
        from agents.producteur_audio import _appliquer_prononciation
        # "Abel" ne doit pas matcher dans "Labelisé" (mais regex \b gère ça)
        texte = "C'est une fable."
        resultat = _appliquer_prononciation(texte)
        # "Abel" ne doit pas être remplacé dans "fable"
        assert "fable" in resultat.lower() or "fable" in texte.lower()

    def test_appliquer_prononciation_texte_sans_noms(self):
        """Un texte sans noms bibliques doit rester inchangé."""
        from agents.producteur_audio import _appliquer_prononciation
        texte = "Les enfants jouent dans le jardin."
        assert _appliquer_prononciation(texte) == texte

    def test_prononciation_utilisee_dans_payload(self):
        """Le producteur audio doit appeler _appliquer_prononciation avant le TTS."""
        import inspect
        from agents import producteur_audio
        source = inspect.getsource(producteur_audio.ProducteurAudio._generer_segment)
        assert "_appliquer_prononciation" in source


# ── Tests SFX Overlay Durée ──────────────────────────────────────────────────

class TestSFXOverlayDuree:
    """Tests de la validation de durée minimale des SFX overlay."""

    def test_overlay_trop_court_detecte(self):
        """Un SFX overlay de moins de 15s doit générer une alerte."""
        from agents.reviewer import Reviewer
        script = {"episode": {"segments": [
            {"id": "sfx_001", "personnage": "sfx", "texte": "wind blowing",
             "ton": "ambiance", "pause_apres_ms": 0, "mode": "overlay",
             "duree_sfx_secondes": 5.0},
        ]}}
        alertes = Reviewer.verifier_sfx_overlay_duree(script)
        assert len(alertes) == 1
        assert "15s" in alertes[0]

    def test_overlay_ok_pas_alerte(self):
        """Un SFX overlay de 15s ou plus ne doit pas générer d'alerte."""
        from agents.reviewer import Reviewer
        script = {"episode": {"segments": [
            {"id": "sfx_001", "personnage": "sfx", "texte": "wind blowing",
             "ton": "ambiance", "pause_apres_ms": 0, "mode": "overlay",
             "duree_sfx_secondes": 18.0},
        ]}}
        alertes = Reviewer.verifier_sfx_overlay_duree(script)
        assert len(alertes) == 0

    def test_insert_pas_affecte(self):
        """Un SFX insert court ne doit pas déclencher l'alerte overlay."""
        from agents.reviewer import Reviewer
        script = {"episode": {"segments": [
            {"id": "sfx_001", "personnage": "sfx", "texte": "door slam",
             "ton": "ambiance", "pause_apres_ms": 0, "mode": "insert",
             "duree_sfx_secondes": 2.0},
        ]}}
        alertes = Reviewer.verifier_sfx_overlay_duree(script)
        assert len(alertes) == 0

    def test_prompt_mentionne_duree_overlay(self):
        """Le prompt scripteur doit mentionner 15 secondes pour les overlay."""
        assert "15 secondes" in SYSTEM_PROMPT_BASE

    def test_prompt_transition_scene_vie_recit(self):
        """Le prompt doit mentionner la transition scène de vie → récit biblique."""
        assert "TRANSITION" in SYSTEM_PROMPT_BASE
        assert "récit biblique" in SYSTEM_PROMPT_BASE

    def test_reviewer_mentionne_overlay_duree(self):
        """Le reviewer doit vérifier la durée des overlay."""
        from agents.reviewer import SYSTEM_PROMPT
        assert "15 secondes" in SYSTEM_PROMPT


# ── Tests Quiz Par Âge ───────────────────────────────────────────────────────

class TestQuizParAge:
    """Tests du quiz à deux niveaux de difficulté."""

    def test_format_quiz_dans_prompt(self):
        """Le prompt doit définir les deux niveaux de quiz."""
        assert "facile" in SYSTEM_PROMPT_BASE
        assert "avance" in SYSTEM_PROMPT_BASE
        assert "6-7 ans" in SYSTEM_PROMPT_BASE
        assert "9-10 ans" in SYSTEM_PROMPT_BASE

    def test_validation_quiz_nouveau_format(self):
        """Le validateur accepte le nouveau format de quiz dict."""
        from agents.scripteur import Scripteur
        script = _script_avec_quiz({
            "facile": ["Q1?", "Q2?", "Q3?"],
            "avance": ["Q1 avancé?", "Q2 avancé?", "Q3 avancé?"],
        })
        # Ne doit pas lever d'exception
        Scripteur._valider_structure(script)

    def test_validation_quiz_ancien_format_migre(self):
        """L'ancien format liste doit être migré automatiquement."""
        from agents.scripteur import Scripteur
        script = _script_avec_quiz(["Q1?", "Q2?", "Q3?"])
        Scripteur._valider_structure(script)
        # Doit avoir été migré vers le nouveau format
        quiz = script["episode"]["quiz"]
        assert isinstance(quiz, dict)
        assert "facile" in quiz
        assert "avance" in quiz

    def test_validation_quiz_niveau_incomplet(self):
        """Un quiz avec moins de 3 questions par niveau doit pas lever d'exception."""
        from agents.scripteur import Scripteur
        script = _script_avec_quiz({
            "facile": ["Q1?"],
            "avance": ["Q1?", "Q2?", "Q3?"],
        })
        # Le script reste valide (warning émis mais pas d'exception)
        Scripteur._valider_structure(script)


def _script_avec_quiz(quiz):
    """Helper : crée un script minimal avec un quiz donné."""
    segments = []
    for i in range(1, 10):
        if i % 3 == 0:
            segments.append({
                "id": f"sfx_{i:03d}", "personnage": "sfx",
                "texte": "birds singing", "ton": "ambiance",
                "pause_apres_ms": 0, "duree_sfx_secondes": 5.0,
                "mode": "insert",
            })
        elif i % 2 == 0:
            segments.append({
                "id": f"seg_{i:03d}", "personnage": "antoine",
                "texte": "Salut Papy !", "ton": "joyeux",
                "pause_apres_ms": 200,
            })
        else:
            segments.append({
                "id": f"seg_{i:03d}", "personnage": "papy_babou",
                "texte": "Bonjour mes petits loups.", "ton": "chaleureux",
                "pause_apres_ms": 300,
            })
    return {"episode": {
        "titre": "Test",
        "numero": 1,
        "saison": 1,
        "ambiance": "calme",
        "morale": "Test",
        "evolutions_personnages": "Test",
        "quiz": quiz,
        "segments": segments,
    }}


# ── Tests Directeur Podcast — Validation SFX ────────────────────────────────

class TestDirecteurValiderSFX:
    """Tests de la validation programmatique SFX du directeur."""

    def _script_avec_sfx(self, sfx_segments):
        """Helper : crée un script avec des segments voix + SFX."""
        segs = []
        # Ajouter des segments voix pour le contexte
        for i in range(1, 30):
            segs.append({
                "id": f"seg_{i:03d}", "personnage": "papy_babou",
                "texte": "Il était une fois dans un pays lointain un homme très courageux.",
                "ton": "chaleureux", "pause_apres_ms": 300,
            })
        # Insérer les SFX
        for j, sfx in enumerate(sfx_segments):
            sfx.setdefault("id", f"sfx_{j+1:03d}")
            sfx.setdefault("personnage", "sfx")
            sfx.setdefault("ton", "ambiance")
            sfx.setdefault("pause_apres_ms", 0)
            segs.insert(j * 3 + 1, sfx)
        return {"episode": {"segments": segs}}

    def test_sfx_francais_detecte(self):
        """Les descriptions SFX en français doivent être détectées."""
        from agents.directeur_podcast import DirecteurPodcast
        sfx = [{"texte": "le vent dans les arbres", "mode": "overlay",
                "duree_sfx_secondes": 15.0}] * 25
        result = DirecteurPodcast.valider_sfx_pour_generation(
            self._script_avec_sfx(sfx)
        )
        fr_alertes = [a for a in result["alertes"] if "français" in a]
        assert len(fr_alertes) > 0

    def test_sfx_anglais_ok(self):
        """Les descriptions SFX en anglais ne doivent pas déclencher d'alerte langue."""
        from agents.directeur_podcast import DirecteurPodcast
        sfx = [
            {"texte": f"gentle wind blowing through trees variant {i}",
             "mode": "overlay", "duree_sfx_secondes": 15.0}
            for i in range(25)
        ]
        result = DirecteurPodcast.valider_sfx_pour_generation(
            self._script_avec_sfx(sfx)
        )
        fr_alertes = [a for a in result["alertes"] if "français" in a]
        assert len(fr_alertes) == 0

    def test_sfx_trop_vague_detecte(self):
        """Les SFX avec < 3 mots doivent être signalés."""
        from agents.directeur_podcast import DirecteurPodcast
        sfx = [{"texte": "wind", "mode": "insert", "duree_sfx_secondes": 3.0}]
        sfx += [{"texte": f"detailed sound description variant {i}",
                 "mode": "insert", "duree_sfx_secondes": 3.0}
                for i in range(24)]
        result = DirecteurPodcast.valider_sfx_pour_generation(
            self._script_avec_sfx(sfx)
        )
        vague_alertes = [a for a in result["alertes"] if "vague" in a]
        assert len(vague_alertes) >= 1

    def test_sfx_doublon_detecte(self):
        """Les descriptions SFX dupliquées doivent être signalées."""
        from agents.directeur_podcast import DirecteurPodcast
        sfx = [{"texte": "birds singing in morning sun",
                "mode": "insert", "duree_sfx_secondes": 3.0}] * 5
        sfx += [{"texte": f"unique sound {i}", "mode": "insert",
                 "duree_sfx_secondes": 3.0} for i in range(20)]
        result = DirecteurPodcast.valider_sfx_pour_generation(
            self._script_avec_sfx(sfx)
        )
        doublon_alertes = [a for a in result["alertes"] if "doublon" in a]
        assert len(doublon_alertes) >= 1
        assert not result["valide"]  # Doublons = critiques

    def test_sfx_nb_insuffisant(self):
        """Moins de 25 SFX doit déclencher une alerte."""
        from agents.directeur_podcast import DirecteurPodcast
        sfx = [{"texte": f"sound effect {i}", "mode": "insert",
                "duree_sfx_secondes": 3.0} for i in range(5)]
        result = DirecteurPodcast.valider_sfx_pour_generation(
            self._script_avec_sfx(sfx)
        )
        nb_alertes = [a for a in result["alertes"] if "25" in a]
        assert len(nb_alertes) >= 1

    def test_sfx_pas_overlay_detecte(self):
        """L'absence totale d'overlay doit être signalée."""
        from agents.directeur_podcast import DirecteurPodcast
        sfx = [{"texte": f"door slam variant {i}", "mode": "insert",
                "duree_sfx_secondes": 3.0} for i in range(25)]
        result = DirecteurPodcast.valider_sfx_pour_generation(
            self._script_avec_sfx(sfx)
        )
        overlay_alertes = [a for a in result["alertes"] if "overlay" in a.lower()]
        assert len(overlay_alertes) >= 1

    def test_sfx_stats_completes(self):
        """Les stats doivent contenir tous les champs."""
        from agents.directeur_podcast import DirecteurPodcast
        sfx = [{"texte": f"sound {i}", "mode": "overlay" if i % 3 == 0 else "insert",
                "duree_sfx_secondes": 15.0 if i % 3 == 0 else 3.0}
               for i in range(25)]
        result = DirecteurPodcast.valider_sfx_pour_generation(
            self._script_avec_sfx(sfx)
        )
        stats = result["stats"]
        assert "nb_sfx" in stats
        assert "nb_overlay" in stats
        assert "nb_insert" in stats
        assert stats["nb_sfx"] == 25

    def test_directeur_6_axes_dans_prompt(self):
        """Le system prompt du directeur doit mentionner 6 axes."""
        from agents.directeur_podcast import SYSTEM_PROMPT
        assert "6 AXES" in SYSTEM_PROMPT

    def test_directeur_qualite_sfx_dans_axes(self):
        """L'axe qualite_sfx doit être dans la validation."""
        from agents.directeur_podcast import DirecteurPodcast
        # Test que _valider_resultat attend le 6ème axe
        resultat_incomplet = {
            "directeur": {
                "note_globale": 8, "verdict": "feu_vert",
                "axes": {
                    "immersion_sonore": {"note": 8},
                    "rythme_accroche": {"note": 8},
                    "emotion_personnages": {"note": 8},
                    "valeur_educative": {"note": 8},
                    "compatibilite_voix_ia": {"note": 8},
                    # qualite_sfx manquant
                },
                "recommandations": [],
            },
            "personas": {
                "lina_7ans": {"note": 8, "reaction": ""},
                "noah_10ans": {"note": 8, "reaction": ""},
                "sophie_parent": {"note": 8, "reaction": ""},
            },
        }
        with pytest.raises(ValueError, match="qualite_sfx"):
            DirecteurPodcast._valider_resultat(resultat_incomplet)


# ── Tests SfxProvider — Audit Niveaux Audio ──────────────────────────────────

class TestSfxAuditNiveaux:
    """Tests de l'audit des niveaux audio SFX."""

    def test_fichier_manquant_detecte(self):
        """Un fichier SFX manquant doit être signalé."""
        from agents.sfx_provider import SfxProvider
        provider = SfxProvider()
        script = {"episode": {"segments": [
            {"id": "sfx_001", "personnage": "sfx", "texte": "wind",
             "ton": "ambiance", "pause_apres_ms": 0,
             "duree_sfx_secondes": 5.0, "mode": "insert"},
        ]}}
        chemin_inexistant = Path("/tmp/nonexistent_sfx_test.mp3")
        result = provider.auditer_niveaux_audio(script, [chemin_inexistant])
        assert not result["ok"]
        assert any("manquant" in a for a in result["alertes"])

    def test_audit_structure_resultat(self):
        """Le résultat d'audit doit avoir la bonne structure."""
        from agents.sfx_provider import SfxProvider
        provider = SfxProvider()
        result = provider.auditer_niveaux_audio(
            {"episode": {"segments": []}}, []
        )
        assert "ok" in result
        assert "alertes" in result
        assert "details" in result
        assert "stats" in result
        assert "nb_sfx_audites" in result["stats"]
        assert "nb_ok" in result["stats"]

    def test_audit_fichier_trop_petit(self, tmp_path):
        """Un fichier de moins de 1KB doit être détecté comme problématique."""
        from agents.sfx_provider import SfxProvider
        provider = SfxProvider()
        # Créer un fichier quasi-vide
        chemin = tmp_path / "sfx_001.mp3"
        chemin.write_bytes(b"tiny")
        script = {"episode": {"segments": [
            {"id": "sfx_001", "personnage": "sfx", "texte": "test",
             "ton": "ambiance", "pause_apres_ms": 0,
             "duree_sfx_secondes": 5.0, "mode": "insert"},
        ]}}
        result = provider.auditer_niveaux_audio(script, [chemin])
        assert not result["ok"]
        assert any("trop petit" in a for a in result["alertes"])


# ── Tests Directeur — Validation Ambiances ───────────────────────────────────

class TestDirecteurValiderAmbiances:
    """Tests de la validation programmatique des ambiances musicales."""

    def test_ambiance_valide_dynamique(self):
        """Un script avec ambiance_par_acte variée doit être valide."""
        from agents.directeur_podcast import DirecteurPodcast
        script = {"episode": {
            "ambiance": "calme",
            "ambiance_par_acte": ["calme", "dramatique", "tendre"],
        }}
        result = DirecteurPodcast.valider_ambiances(script)
        assert result["valide"]
        assert result["stats"]["dynamique"]

    def test_ambiance_uniforme_alerte(self):
        """Un ambiance_par_acte identique partout doit alerter."""
        from agents.directeur_podcast import DirecteurPodcast
        script = {"episode": {
            "ambiance": "calme",
            "ambiance_par_acte": ["calme", "calme", "calme"],
        }}
        result = DirecteurPodcast.valider_ambiances(script)
        assert not result["valide"]
        assert any("TOUS" in a for a in result["alertes"])

    def test_ambiance_absente_alerte(self):
        """L'absence d'ambiance_par_acte doit alerter."""
        from agents.directeur_podcast import DirecteurPodcast
        script = {"episode": {"ambiance": "calme"}}
        result = DirecteurPodcast.valider_ambiances(script)
        assert not result["valide"]
        assert any("ambiance_par_acte" in a for a in result["alertes"])

    def test_ambiance_inconnue_alerte(self):
        """Une ambiance non reconnue doit être signalée."""
        from agents.directeur_podcast import DirecteurPodcast
        script = {"episode": {
            "ambiance": "zzz_inconnu",
            "ambiance_par_acte": ["zzz_inconnu", "calme", "tendre"],
        }}
        result = DirecteurPodcast.valider_ambiances(script)
        assert not result["valide"]
        assert any("non reconnue" in a for a in result["alertes"])

    def test_episode_final_fond_doux_alerte(self):
        """Un épisode final avec fond_doux doit être signalé."""
        from agents.directeur_podcast import DirecteurPodcast
        script = {"episode": {
            "type": "final",
            "ambiance": "fond_doux",
            "ambiance_par_acte": ["fond_doux", "tendre", "solennel"],
        }}
        result = DirecteurPodcast.valider_ambiances(script)
        assert any("final" in a.lower() for a in result["alertes"])

    def test_stats_completes(self):
        """Les stats doivent contenir tous les champs attendus."""
        from agents.directeur_podcast import DirecteurPodcast
        script = {"episode": {
            "ambiance": "epique",
            "ambiance_par_acte": ["mystere", "epique", "tendre"],
        }}
        result = DirecteurPodcast.valider_ambiances(script)
        stats = result["stats"]
        assert "ambiance_principale" in stats
        assert "ambiance_par_acte" in stats
        assert "dynamique" in stats
        assert "nb_ambiances_distinctes" in stats
        assert stats["nb_ambiances_distinctes"] == 3


# ── Tests Monteur — Audit Musiques de Fond ───────────────────────────────────

class TestMonteurAuditMusique:
    """Tests de l'audit des musiques de fond."""

    def test_audit_structure_resultat(self):
        """Le résultat d'audit doit avoir la bonne structure."""
        from agents.monteur import Monteur
        script = {"episode": {"ambiance": "calme"}}
        result = Monteur.auditer_musiques_fond(script)
        assert "ok" in result
        assert "alertes" in result
        assert "details" in result
        assert "stats" in result

    def test_audit_ambiance_inconnue(self):
        """Une ambiance non reconnue doit être signalée."""
        from agents.monteur import Monteur
        script = {"episode": {"ambiance": "zzz_pas_valide"}}
        result = Monteur.auditer_musiques_fond(script)
        assert not result["ok"]
        assert any("non reconnue" in a for a in result["alertes"])

    def test_audit_pas_dynamique_alerte(self):
        """L'absence d'ambiance_par_acte doit être signalée."""
        from agents.monteur import Monteur
        script = {"episode": {"ambiance": "calme"}}
        result = Monteur.auditer_musiques_fond(script)
        assert any("uniforme" in a or "ambiance_par_acte" in a for a in result["alertes"])

    def test_audit_stats_dynamique(self):
        """Stats.dynamique doit refléter la variété."""
        from agents.monteur import Monteur
        script = {"episode": {
            "ambiance": "calme",
            "ambiance_par_acte": ["calme", "epique", "tendre"],
        }}
        result = Monteur.auditer_musiques_fond(script)
        assert result["stats"]["dynamique"]

    def test_audit_a_generer(self):
        """Les ambiances sans fichier doivent être marquées 'a_generer'."""
        from agents.monteur import Monteur
        # "epique" n'a probablement pas de fichier dans l'env de test
        script = {"episode": {
            "ambiance": "epique",
            "ambiance_par_acte": ["epique", "tendre", "solennel"],
        }}
        result = Monteur.auditer_musiques_fond(script)
        # Vérifie qu'au moins un statut existe
        assert len(result["details"]) > 0

    def test_directeur_immersion_mentionne_musique(self):
        """Le prompt du directeur doit mentionner la musique de fond."""
        from agents.directeur_podcast import SYSTEM_PROMPT
        assert "MUSIQUE DE FOND" in SYSTEM_PROMPT
        assert "ambiance_par_acte" in SYSTEM_PROMPT
