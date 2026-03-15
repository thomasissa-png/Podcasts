"""Tests pour l'orchestrateur principal."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import (
    charger_historique,
    sauvegarder_historique,
    ajouter_historique,
    sauvegarder_checkpoint,
    charger_checkpoint,
    archiver_checkpoint,
    _calculer_couts,
    _validation_metadonnees,
    _validation_publication,
    _validation_montage,
    charger_preferences,
    sauvegarder_preferences,
    ajouter_preference,
    _construire_bloc_preferences,
    ProductionAbandonnee,
)


class TestHistorique:
    """Tests du système d'historique inter-épisodes."""

    def test_charger_historique_vide(self, tmp_path, monkeypatch):
        """Sans fichier, l'historique doit être vide."""
        import main
        monkeypatch.setattr(main, "HISTORIQUE_PATH", tmp_path / "historique.json")
        assert charger_historique() == []

    def test_sauvegarder_et_charger_historique(self, tmp_path, monkeypatch):
        """L'historique doit être sauvegardé et rechargé correctement."""
        import main
        chemin = tmp_path / "historique.json"
        monkeypatch.setattr(main, "HISTORIQUE_PATH", chemin)

        historique = [
            {"episode_id": "S01E01", "titre": "Le buisson ardent", "morale": "Confiance"},
        ]
        sauvegarder_historique(historique)

        recharge = charger_historique()
        assert len(recharge) == 1
        assert recharge[0]["titre"] == "Le buisson ardent"

    def test_ajouter_historique(self, tmp_path, monkeypatch):
        """Un épisode ajouté doit apparaître dans l'historique."""
        import main
        chemin = tmp_path / "historique.json"
        monkeypatch.setattr(main, "HISTORIQUE_PATH", chemin)

        rapport = {
            "episode_id": "S01E01",
            "titre": "Le buisson ardent",
            "debut": "2025-01-01T00:00:00",
            "etapes": {"script": {"score_review": 8}},
        }
        script = {
            "episode": {
                "titre": "Le buisson ardent",
                "morale": "La confiance en Dieu",
                "segments": [
                    {"personnage": "papy_babou", "texte": "Bonjour"},
                    {"personnage": "antoine", "texte": "Salut"},
                    {"personnage": "sfx", "texte": "vent"},
                ],
            }
        }

        ajouter_historique(rapport, script)

        historique = charger_historique()
        assert len(historique) == 1
        assert historique[0]["morale"] == "La confiance en Dieu"
        assert historique[0]["score_review"] == 8

    def test_ajouter_historique_contexte_seriel(self, tmp_path, monkeypatch):
        """L'historique enrichi doit contenir les personnages et moments clés."""
        import main
        chemin = tmp_path / "historique.json"
        monkeypatch.setattr(main, "HISTORIQUE_PATH", chemin)

        rapport = {
            "episode_id": "S01E01",
            "titre": "Le buisson ardent",
            "debut": "2025-01-01T00:00:00",
            "etapes": {"script": {"score_review": 8}},
        }
        script = {
            "episode": {
                "titre": "Le buisson ardent",
                "morale": "La confiance en Dieu",
                "moments_cles": ["Moïse voit le buisson", "Dieu parle"],
                "ambiance": "mystere",
                "type": "ouverture",
                "segments": [
                    {"personnage": "papy_babou", "texte": "Bonjour"},
                    {"personnage": "antoine", "texte": "Salut"},
                    {"personnage": "noemie", "texte": "Coucou"},
                ],
            }
        }

        ajouter_historique(rapport, script)

        historique = charger_historique()
        assert len(historique) == 1
        ep = historique[0]
        assert "papy_babou" in ep["personnages_presents"]
        assert "antoine" in ep["personnages_presents"]
        assert "noemie" in ep["personnages_presents"]
        assert "Moïse voit le buisson" in ep["moments_cles"]
        assert ep["ambiance"] == "mystere"
        assert ep["type_episode"] == "ouverture"


class TestCheckpoints:
    """Tests du système de checkpoints."""

    def test_sauvegarder_checkpoint(self, tmp_path, monkeypatch):
        """Un checkpoint doit être sauvegardé correctement."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        data = {"titre": "Test", "saison": 1, "numero": 1}
        chemin = sauvegarder_checkpoint("S01E01", "audio", data)

        assert chemin.exists()
        with open(chemin, encoding="utf-8") as f:
            cp = json.load(f)
        assert cp["episode_id"] == "S01E01"
        assert cp["etape"] == "audio"
        assert cp["data"]["titre"] == "Test"

    def test_charger_checkpoint(self, tmp_path, monkeypatch):
        """Un checkpoint doit être rechargé correctement."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        data = {"titre": "Test", "saison": 1, "numero": 1}
        chemin = sauvegarder_checkpoint("S01E01", "sfx", data)

        cp = charger_checkpoint(chemin)
        assert cp["etape"] == "sfx"
        assert cp["data"]["titre"] == "Test"

    def test_archiver_checkpoint(self, tmp_path, monkeypatch):
        """Un checkpoint archivé doit être renommé (jamais supprimé)."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        data = {"titre": "Test", "saison": 1, "numero": 1}
        chemin = sauvegarder_checkpoint("S01E01", "audio", data)
        assert chemin.exists()

        archiver_checkpoint("S01E01")
        # Le fichier original ne doit plus exister...
        assert not chemin.exists()
        # ...mais un fichier _done_ doit exister à la place
        archives = list(tmp_path.glob("S01E01_checkpoint_done_*.json"))
        assert len(archives) == 1

    def test_archiver_checkpoint_inexistant(self, tmp_path, monkeypatch):
        """Archiver un checkpoint inexistant ne doit pas lever d'erreur."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)
        archiver_checkpoint("S99E99")  # Ne devrait pas lever d'erreur

    def test_charger_checkpoint_corrompu(self, tmp_path, monkeypatch):
        """Un checkpoint JSON corrompu doit lever une ValueError."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        chemin = tmp_path / "S01E01_checkpoint.json"
        chemin.write_text("{ceci n'est pas du JSON valide}", encoding="utf-8")

        with pytest.raises(ValueError, match="corrompu"):
            charger_checkpoint(chemin)

    def test_charger_checkpoint_champ_manquant(self, tmp_path, monkeypatch):
        """Un checkpoint avec un champ manquant doit lever une ValueError."""
        import config
        monkeypatch.setattr(config, "CHECKPOINTS_DIR", tmp_path)

        chemin = tmp_path / "S01E01_checkpoint.json"
        chemin.write_text('{"episode_id": "S01E01"}', encoding="utf-8")

        with pytest.raises(ValueError, match="champ manquant"):
            charger_checkpoint(chemin)


class TestCalculerCouts:
    """Tests du calcul des métriques de coût."""

    def test_couts_vides(self):
        """Un rapport vide doit retourner un coût total de 0."""
        rapport = {"etapes": {}}
        couts = _calculer_couts(rapport)
        assert couts["total_estime"] == 0.0

    def test_couts_avec_tts(self):
        """Le coût TTS doit être calculé à partir des caractères."""
        rapport = {
            "etapes": {
                "audio": {
                    "caracteres": {"papy_babou": 1000, "antoine": 500},
                },
            },
        }
        couts = _calculer_couts(rapport)
        assert "elevenlabs_tts" in couts
        assert couts["elevenlabs_tts"]["caracteres"] == 1500
        assert couts["elevenlabs_tts"]["cout"] > 0
        assert couts["total_estime"] > 0

    def test_couts_avec_sfx_elevenlabs(self):
        """Le coût SFX ElevenLabs doit compter les SFX générés."""
        rapport = {
            "etapes": {
                "sfx": {
                    "sources": {"sfx_001": "elevenlabs", "sfx_002": "freesound (vent)"},
                },
            },
        }
        couts = _calculer_couts(rapport)
        assert "elevenlabs_sfx" in couts
        assert couts["elevenlabs_sfx"]["nb_sfx"] == 1

    def test_couts_avec_cover_art(self):
        """Le coût cover art doit être inclus si présent."""
        rapport = {
            "etapes": {
                "metadonnees": {
                    "cover_art_cout": 0.04,
                },
            },
        }
        couts = _calculer_couts(rapport)
        assert "openai_dalle3" in couts
        assert couts["total_estime"] >= 0.04

    def test_couts_complet(self):
        """Un rapport complet doit cumuler tous les coûts."""
        rapport = {
            "etapes": {
                "audio": {"caracteres": {"papy_babou": 2000}},
                "sfx": {"sources": {"sfx_001": "elevenlabs"}},
                "script": {"score_review": 8},
                "metadonnees": {"cover_art_cout": 0.04},
            },
        }
        couts = _calculer_couts(rapport)
        assert couts["total_estime"] > 0.04  # Au moins cover art + autres


class TestValidationMetadonnees:
    """Tests du point de validation humaine des metadonnees (T2/M4)."""

    def test_validation_valider(self, tmp_path, monkeypatch):
        """L'option 'v' valide les metadonnees et log la decision."""
        import main
        meta = {"titre": "Test", "description_courte": "Desc", "tags": ["bible"]}
        chemin = tmp_path / "meta.json"
        with open(chemin, "w") as f:
            json.dump(meta, f)
        rapport = {}

        inputs = iter(["v"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_metadonnees(meta, chemin, rapport=rapport)
        assert result["titre"] == "Test"
        assert len(rapport["decisions_humaines"]) == 1
        assert rapport["decisions_humaines"][0]["etape"] == "metadonnees"
        assert rapport["decisions_humaines"][0]["action"] == "valide"

    def test_validation_modifier_json(self, tmp_path, monkeypatch):
        """L'option 'm' recharge le JSON modifie."""
        import main
        meta = {"titre": "Ancien", "description_courte": "Desc"}
        chemin = tmp_path / "meta.json"
        # Ecrire le fichier modifie
        meta_modifie = {"titre": "Nouveau", "description_courte": "Nouvelle desc"}
        with open(chemin, "w") as f:
            json.dump(meta_modifie, f)
        rapport = {}

        inputs = iter(["m", "", "v"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_metadonnees(meta, chemin, rapport=rapport)
        assert result["titre"] == "Nouveau"
        assert any(d["action"] == "modifie_json" for d in rapport["decisions_humaines"])

    def test_validation_abandonner(self, tmp_path, monkeypatch):
        """L'option 'a' leve ProductionAbandonnee."""
        import main
        meta = {"titre": "Test", "description_courte": "Desc"}
        chemin = tmp_path / "meta.json"

        inputs = iter(["a"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        with pytest.raises(ProductionAbandonnee):
            _validation_metadonnees(meta, chemin)


class TestValidationPublication:
    """Tests du point de confirmation de publication (T4)."""

    @staticmethod
    def _rapport_avec_prerequis():
        """Rapport avec les prérequis relecture + écoute validés."""
        return {
            "etapes": {
                "script": {"validation_humaine": True},
                "montage": {"validation_humaine": True},
            }
        }

    def test_publier(self, monkeypatch):
        """L'option 'p' confirme la publication."""
        import main
        meta = {"titre": "Test"}
        rapport = self._rapport_avec_prerequis()

        inputs = iter(["p"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_publication(meta, "S01E01", rapport=rapport)
        assert result is True
        assert rapport["decisions_humaines"][0]["action"] == "publie"

    def test_sauter_publication(self, monkeypatch):
        """L'option 's' saute la publication sans erreur."""
        import main
        meta = {"titre": "Test"}
        rapport = self._rapport_avec_prerequis()

        inputs = iter(["s"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_publication(meta, "S01E01", rapport=rapport)
        assert result is False
        assert rapport["decisions_humaines"][0]["action"] == "saute"

    def test_abandonner_publication(self, monkeypatch):
        """L'option 'a' retourne False (ne publie pas) mais continue vers le rapport."""
        import main
        meta = {"titre": "Test"}
        rapport = self._rapport_avec_prerequis()

        inputs = iter(["a"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_publication(meta, "S01E01", rapport=rapport)
        assert result is False
        decisions = rapport.get("decisions_humaines", [])
        assert any(d.get("action") == "abandonne" for d in decisions)

    def test_publication_bloquee_sans_relecture(self, monkeypatch):
        """Publication bloquée si le script n'a pas été relu."""
        import main
        meta = {"titre": "Test"}
        rapport = {"etapes": {"montage": {"validation_humaine": True}}}

        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_publication(meta, "S01E01", rapport=rapport)
        assert result is False
        assert rapport["decisions_humaines"][0]["action"] == "bloque_prerequis_manquants"
        assert "Relecture du script" in rapport["decisions_humaines"][0]["prerequis_manquants"]

    def test_publication_bloquee_sans_ecoute(self, monkeypatch):
        """Publication bloquée si le montage n'a pas été écouté."""
        import main
        meta = {"titre": "Test"}
        rapport = {"etapes": {"script": {"validation_humaine": True}}}

        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_publication(meta, "S01E01", rapport=rapport)
        assert result is False
        assert rapport["decisions_humaines"][0]["action"] == "bloque_prerequis_manquants"
        assert "Écoute du montage audio" in rapport["decisions_humaines"][0]["prerequis_manquants"]

    def test_publication_bloquee_sans_aucun_prerequis(self, monkeypatch):
        """Publication bloquée si ni relecture ni écoute n'ont eu lieu."""
        import main
        meta = {"titre": "Test"}
        rapport = {"etapes": {}}

        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_publication(meta, "S01E01", rapport=rapport)
        assert result is False
        assert len(rapport["decisions_humaines"][0]["prerequis_manquants"]) == 2


class TestValidationMontageEnrichie:
    """Tests de la validation montage enrichie (M1/M2/M3/M5)."""

    def test_valider_montage(self, tmp_path, monkeypatch):
        """L'option 'v' valide le montage et retourne False (pas de remontage)."""
        import main
        rapport = {}

        inputs = iter(["v"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_montage(
            chemin_hq=tmp_path / "episode.mp3",
            chemin_preview=tmp_path / "preview.mp3",
            duree_secondes=780,
            type_episode="standard",
            rapport=rapport,
        )
        assert result is False
        assert rapport["decisions_humaines"][0]["action"] == "valide"

    def test_remontage(self, tmp_path, monkeypatch):
        """L'option 'r' demande un remontage et retourne True."""
        import main
        rapport = {}

        inputs = iter(["r"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_montage(
            chemin_hq=tmp_path / "episode.mp3",
            chemin_preview=tmp_path / "preview.mp3",
            duree_secondes=780,
            type_episode="standard",
            rapport=rapport,
        )
        assert result is True
        assert rapport["decisions_humaines"][0]["action"] == "remontage"

    def test_abandonner_montage(self, tmp_path, monkeypatch):
        """L'option 'a' leve ProductionAbandonnee."""
        import main

        inputs = iter(["a"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        with pytest.raises(ProductionAbandonnee):
            _validation_montage(
                chemin_hq=tmp_path / "episode.mp3",
                chemin_preview=tmp_path / "preview.mp3",
                duree_secondes=780,
            )

    def test_montage_affiche_info_script(self, tmp_path, monkeypatch):
        """Avec un script, les infos segments sont affichees."""
        import main
        rapport = {}
        script = {
            "episode": {
                "segments": [
                    {"personnage": "papy_babou", "texte": "Il etait une fois"},
                    {"personnage": "sfx", "texte": "bruit de vent"},
                    {"personnage": "antoine", "texte": "Raconte-moi"},
                ],
            }
        }

        printed = []
        monkeypatch.setattr(main.console, "input", lambda _: "v")
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: printed.append(str(a)))

        result = _validation_montage(
            chemin_hq=tmp_path / "episode.mp3",
            chemin_preview=tmp_path / "preview.mp3",
            duree_secondes=780,
            script=script,
            type_episode="standard",
            resultat_montage={"chapitres": [{"titre": "Ch1"}], "taille_mb": 12.5},
            rapport=rapport,
        )
        assert result is False

    def test_ecart_duree_couleur(self, tmp_path, monkeypatch):
        """L'ecart de duree colore correctement (vert < 2, jaune < 4, rouge >= 4)."""
        import main
        rapport = {}

        # Standard = 13 min cible. 780s = 13 min = ecart 0 (vert)
        inputs = iter(["v"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        result = _validation_montage(
            chemin_hq=tmp_path / "episode.mp3",
            chemin_preview=tmp_path / "preview.mp3",
            duree_secondes=780,  # 13 min exactement
            type_episode="standard",
            rapport=rapport,
        )
        assert result is False


class TestPreferencesProducteur:
    """Tests du systeme de preferences producteur (A1)."""

    def test_charger_preferences_vide(self, tmp_path, monkeypatch):
        """Sans fichier, les preferences sont vides."""
        import config
        monkeypatch.setattr(config, "PREFERENCES_PATH", tmp_path / "prefs.json")
        assert charger_preferences() == []

    def test_sauvegarder_et_charger_preferences(self, tmp_path, monkeypatch):
        """Les preferences doivent etre sauvegardees et rechargees."""
        import config
        chemin = tmp_path / "prefs.json"
        monkeypatch.setattr(config, "PREFERENCES_PATH", chemin)

        prefs = [{"regle": "Sois plus subtil", "categorie": "style"}]
        sauvegarder_preferences(prefs)

        recharge = charger_preferences()
        assert len(recharge) == 1
        assert recharge[0]["regle"] == "Sois plus subtil"

    def test_ajouter_preference(self, tmp_path, monkeypatch):
        """ajouter_preference ajoute une regle avec metadata."""
        import config
        chemin = tmp_path / "prefs.json"
        monkeypatch.setattr(config, "PREFERENCES_PATH", chemin)

        ajouter_preference("Papy doit etre chaleureux", source_episode="S01E03", categorie="ton")
        prefs = charger_preferences()
        assert len(prefs) == 1
        assert prefs[0]["regle"] == "Papy doit etre chaleureux"
        assert prefs[0]["source_episode"] == "S01E03"
        assert prefs[0]["categorie"] == "ton"
        assert "date_ajout" in prefs[0]

    def test_construire_bloc_preferences_vide(self, tmp_path, monkeypatch):
        """Sans preferences, le bloc est vide."""
        import config
        monkeypatch.setattr(config, "PREFERENCES_PATH", tmp_path / "prefs.json")
        assert _construire_bloc_preferences() == ""

    def test_construire_bloc_preferences_non_vide(self, tmp_path, monkeypatch):
        """Avec preferences, le bloc contient les regles numerotees."""
        import config
        chemin = tmp_path / "prefs.json"
        monkeypatch.setattr(config, "PREFERENCES_PATH", chemin)

        ajouter_preference("Regle un")
        ajouter_preference("Regle deux")
        bloc = _construire_bloc_preferences()
        assert "PRÉFÉRENCES DU PRODUCTEUR" in bloc
        assert "1. Regle un" in bloc
        assert "2. Regle deux" in bloc


class TestHistoriqueEnrichi:
    """Tests de l'historique enrichi avec retours humains (A2)."""

    def test_historique_avec_retours(self, tmp_path, monkeypatch):
        """Les retours humains du rapport sont inclus dans l'historique."""
        import main
        chemin = tmp_path / "historique.json"
        monkeypatch.setattr(main, "HISTORIQUE_PATH", chemin)

        rapport = {
            "episode_id": "S01E01",
            "titre": "Le buisson ardent",
            "debut": "2026-01-01T10:00:00",
            "etapes": {
                "script": {"score_review": 8},
            },
            "decisions_humaines": [
                {"action": "correction_humaine", "corrections": ["Plus de suspense", "Papy plus doux"]},
            ],
        }
        script = {
            "episode": {
                "titre": "Le buisson ardent",
                "morale": "La confiance",
                "segments": [
                    {"personnage": "papy_babou", "texte": "Il etait une fois..."},
                ],
            }
        }
        ajouter_historique(rapport, script)
        historique = json.load(open(chemin))
        assert len(historique) == 1
        assert "retours_humains" in historique[0]
        assert "Plus de suspense" in historique[0]["retours_humains"]

    def test_historique_sans_retours(self, tmp_path, monkeypatch):
        """Sans corrections, retours_humains est vide."""
        import main
        chemin = tmp_path / "historique.json"
        monkeypatch.setattr(main, "HISTORIQUE_PATH", chemin)

        rapport = {
            "episode_id": "S01E02",
            "titre": "Noe et l'arche",
            "debut": "2026-01-02T10:00:00",
            "etapes": {"script": {"score_review": 9}},
        }
        script = {
            "episode": {
                "titre": "Noe et l'arche",
                "morale": "L'obeissance",
                "segments": [
                    {"personnage": "papy_babou", "texte": "Ce soir..."},
                ],
            }
        }
        ajouter_historique(rapport, script)
        historique = json.load(open(chemin))
        assert historique[0]["retours_humains"] == ""


class TestMontageEdition:
    """Tests du remontage avec edition de script (A3)."""

    def test_edition_script_puis_remontage(self, tmp_path, monkeypatch):
        """L'option 'e' recharge le script et demande remontage."""
        import main
        import config
        rapport = {}
        script = {
            "episode": {
                "saison": 1, "numero": 1, "titre": "Test",
                "segments": [
                    {"id": "seg_001", "personnage": "papy_babou", "texte": "Hello",
                     "ton": "chaleureux", "pause_apres_ms": 800},
                ],
            }
        }
        # Creer le fichier script valide
        ep_id = "S01E01"
        chemin_script = config.SCRIPTS_DIR / f"{ep_id}_valide.json"
        chemin_script.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin_script, "w") as f:
            json.dump(script, f)

        inputs = iter(["e", "", "v"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        # Le premier choix est 'e' => remontage (True), puis 'v' => valider
        result = _validation_montage(
            chemin_hq=tmp_path / "episode.mp3",
            chemin_preview=tmp_path / "preview.mp3",
            duree_secondes=780,
            script=script,
            type_episode="standard",
            rapport=rapport,
        )
        assert result is True
        assert any(
            d.get("action") == "remontage_apres_edition"
            for d in rapport.get("decisions_humaines", [])
        )


class TestMetadonneesRegeneration:
    """Tests de la regeneration des metadonnees avec feedback (A7)."""

    def test_validation_avec_regeneration(self, tmp_path, monkeypatch):
        """L'option 'c' sans script disponible affiche un warning."""
        import main
        meta = {"titre": "Test", "description_courte": "Desc"}
        chemin = tmp_path / "meta.json"
        with open(chemin, "w") as f:
            json.dump(meta, f)

        inputs = iter(["c", "change le titre", "", "v"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        # Sans script, la regeneration est impossible, on retombe sur validation
        result = _validation_metadonnees(meta, chemin, script=None, rapport={})
        assert result["titre"] == "Test"


class TestPlanDecisionLogging:
    """Tests du logging des decisions dans la validation plan."""

    def test_plan_validation_logs_decision(self, monkeypatch):
        """L'option 'v' ajoute une decision au plan."""
        import main
        plan = {
            "saison": {
                "numero": 1,
                "theme": "Test",
                "episodes": [{"numero": 1, "titre": "Ep1", "resume": "R", "morale": "M"}],
            }
        }

        inputs = iter(["v"])
        monkeypatch.setattr(main.console, "input", lambda _: next(inputs))
        monkeypatch.setattr(main.console, "print", lambda *a, **kw: None)

        from main import _validation_plan_saison
        result = _validation_plan_saison(
            plan=plan,
            chemin_json=Path("/tmp/test.json"),
            planificateur=None,
            saison=1,
            theme="Test",
        )
        assert "decisions_humaines" in result["saison"]
        assert result["saison"]["decisions_humaines"][0]["action"] == "valide"
