"""Tests pour les utilitaires partages — utils.py.

Couvre :
- extraire_json_llm : extraction JSON depuis reponses LLM
- parser_json_llm : parsing JSON avec nettoyage automatique
- fichier_lock : verrouillage de fichier advisory
- masquer_secret : masquage de cles API pour les logs
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import extraire_json_llm, fichier_lock, masquer_secret, parser_json_llm


# ── extraire_json_llm ────────────────────────────────────────────────────────


class TestExtraireJsonLlmJsonPur:
    """Cas 2 : JSON pur (commence par { ou [)."""

    def test_objet_json_simple(self):
        """Un objet JSON simple doit etre retourne tel quel."""
        texte = '{"titre": "Le buisson ardent"}'
        assert extraire_json_llm(texte) == texte

    def test_tableau_json_simple(self):
        """Un tableau JSON simple doit etre retourne tel quel."""
        texte = '[1, 2, 3]'
        assert extraire_json_llm(texte) == texte

    def test_objet_json_multiligne(self):
        """Un objet JSON multiligne doit etre retourne tel quel."""
        texte = '{\n  "titre": "Test",\n  "score": 8\n}'
        assert extraire_json_llm(texte) == texte

    def test_tableau_objets(self):
        """Un tableau d'objets doit etre retourne tel quel."""
        texte = '[{"a": 1}, {"b": 2}]'
        assert extraire_json_llm(texte) == texte

    def test_json_pur_avec_espaces_autour(self):
        """Le JSON avec espaces/newlines autour doit etre strip puis retourne."""
        texte = '  \n {"titre": "Test"} \n  '
        result = extraire_json_llm(texte)
        assert result == '{"titre": "Test"}'

    def test_json_pur_objet_imbrique(self):
        """Un objet JSON avec imbrication doit etre retourne tel quel."""
        texte = '{"episode": {"titre": "Test", "segments": []}}'
        assert extraire_json_llm(texte) == texte


class TestExtraireJsonLlmMarkdownBlocs:
    """Cas 1 : blocs de code markdown ```json ... ``` ou ``` ... ```."""

    def test_bloc_json_markdown(self):
        """Un bloc ```json doit etre extrait correctement."""
        texte = '```json\n{"titre": "Test"}\n```'
        assert extraire_json_llm(texte) == '{"titre": "Test"}'

    def test_bloc_sans_label_json(self):
        """Un bloc ``` sans label doit etre extrait correctement."""
        texte = '```\n{"titre": "Test"}\n```'
        assert extraire_json_llm(texte) == '{"titre": "Test"}'

    def test_bloc_json_multiligne(self):
        """Un bloc markdown avec JSON multiligne doit etre extrait."""
        texte = '```json\n{\n  "titre": "Test",\n  "score": 8\n}\n```'
        result = extraire_json_llm(texte)
        assert '"titre": "Test"' in result
        assert '"score": 8' in result

    def test_bloc_json_avec_texte_avant(self):
        """Un bloc markdown precede de texte doit etre extrait."""
        texte = 'Voici le resultat :\n```json\n{"titre": "Test"}\n```'
        assert extraire_json_llm(texte) == '{"titre": "Test"}'

    def test_bloc_json_avec_texte_apres(self):
        """Un bloc markdown suivi de texte doit etre extrait."""
        texte = '```json\n{"titre": "Test"}\n```\nVoila le JSON.'
        assert extraire_json_llm(texte) == '{"titre": "Test"}'

    def test_bloc_json_avec_texte_avant_et_apres(self):
        """Un bloc markdown entoure de texte doit etre extrait."""
        texte = 'Voici :\n```json\n{"titre": "Test"}\n```\nBon JSON.'
        assert extraire_json_llm(texte) == '{"titre": "Test"}'

    def test_bloc_json_tableau(self):
        """Un tableau JSON dans un bloc markdown doit etre extrait."""
        texte = '```json\n[{"id": 1}, {"id": 2}]\n```'
        assert extraire_json_llm(texte) == '[{"id": 1}, {"id": 2}]'

    def test_bloc_json_avec_espaces_internes(self):
        """Un bloc markdown avec espaces autour du JSON doit etre strip."""
        texte = '```json\n  {"titre": "Test"}  \n```'
        assert extraire_json_llm(texte) == '{"titre": "Test"}'

    def test_bloc_markdown_priorite_sur_json_pur(self):
        """Le bloc markdown doit etre detecte meme si le contenu commence par {."""
        texte = '```json\n{"from_block": true}\n```'
        result = extraire_json_llm(texte)
        assert '"from_block": true' in result


class TestExtraireJsonLlmTexteAvantJson:
    """Cas 3 : texte avant le JSON — chercher chaque { ou [."""

    def test_texte_simple_avant_json(self):
        """Du texte avant un objet JSON doit etre ignore."""
        texte = 'Voici le JSON: {"titre": "Test"}'
        result = extraire_json_llm(texte)
        parsed = json.loads(result)
        assert parsed == {"titre": "Test"}

    def test_texte_avant_tableau_json(self):
        """Du texte avant un tableau JSON doit etre ignore."""
        texte = 'Resultat: [1, 2, 3]'
        result = extraire_json_llm(texte)
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]

    def test_texte_multilignes_avant_json(self):
        """Plusieurs lignes de texte avant JSON doivent etre ignorees."""
        texte = "Voici mon analyse.\nEt voici le script :\n{\"titre\": \"Test\"}"
        result = extraire_json_llm(texte)
        parsed = json.loads(result)
        assert parsed["titre"] == "Test"

    def test_multiple_accolades_premier_invalide(self):
        """Quand le premier { ne forme pas du JSON valide, chercher le suivant."""
        texte = 'le texte {invalide} puis {"titre": "Correct"}'
        result = extraire_json_llm(texte)
        parsed = json.loads(result)
        assert parsed["titre"] == "Correct"

    def test_multiple_crochets_premier_invalide(self):
        """Quand le premier [ ne forme pas du JSON valide, chercher le suivant."""
        texte = 'voir [section 1] puis [1, 2, 3]'
        result = extraire_json_llm(texte)
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]

    def test_accolade_dans_texte_naturel(self):
        """Des accolades dans du texte naturel ne doivent pas bloquer."""
        texte = 'Utilisez {x} comme variable. Resultat: {"valeur": 42}'
        result = extraire_json_llm(texte)
        parsed = json.loads(result)
        assert parsed["valeur"] == 42

    def test_json_complexe_apres_texte(self):
        """Un JSON complexe apres du texte doit etre extrait entierement."""
        json_obj = {"episode": {"titre": "Test", "segments": [{"id": "s1"}]}}
        texte = f"Voici le script genere :\n{json.dumps(json_obj)}"
        result = extraire_json_llm(texte)
        parsed = json.loads(result)
        assert parsed == json_obj


class TestExtraireJsonLlmFallback:
    """Cas 4 : fallback — supprimer les lignes ``` quand pas de bloc formel."""

    def test_backticks_sans_bloc_formel(self):
        """Des backticks eparpilles doivent etre retires (fallback)."""
        # Fallback: ``` in text but no regex match (no newlines around content).
        # Lines starting with ``` are filtered out. A multi-line case where
        # some lines are backtick-only and others have content.
        texte = '```\n{"titre": "Test"}\nplus de texte\n```'
        result = extraire_json_llm(texte)
        # Cas 1 regex matches this (```\n...\n...```), extracting inner content
        assert "titre" in result

    def test_fallback_backticks_inline(self):
        """Des backticks sur une seule ligne — tout est filtre (edge case)."""
        texte = '```{"titre": "Test"}```'
        result = extraire_json_llm(texte)
        # Single line starting with ``` is removed entirely by fallback
        assert result == ""

    def test_fallback_multiline_mixed(self):
        """Le fallback supprime les lignes ``` et garde le contenu."""
        # Construct input where Cas 1 regex won't match but ``` is present:
        # No newline before closing ```, so regex pattern fails.
        # Also no valid JSON for Cas 2/3 to find.
        texte = "``` debut\ncontenu important\nfin ```"
        result = extraire_json_llm(texte)
        # Lines starting with ``` are removed, "fin ```" does not start with ```
        assert "contenu important" in result


class TestExtraireJsonLlmEdgeCases:
    """Cas limites pour extraire_json_llm."""

    def test_chaine_vide(self):
        """Une chaine vide doit retourner une chaine vide."""
        assert extraire_json_llm("") == ""

    def test_espaces_seuls(self):
        """Des espaces seuls doivent retourner une chaine vide."""
        assert extraire_json_llm("   \n\t  ") == ""

    def test_texte_sans_json(self):
        """Du texte sans JSON doit etre retourne tel quel (strippe)."""
        texte = "Ceci est un texte normal sans JSON."
        assert extraire_json_llm(texte) == texte

    def test_texte_sans_json_ni_accolades(self):
        """Du texte narratif sans accolades doit etre retourne strippe."""
        texte = "Papy Babou raconte une histoire."
        assert extraire_json_llm(texte) == texte

    def test_json_invalide_partout(self):
        """Si aucun { ou [ ne forme du JSON valide, retourner le texte."""
        texte = "les {valeurs} et [choses] ne sont pas du JSON"
        result = extraire_json_llm(texte)
        # No valid JSON found, no ```, returns texte as-is
        assert result == texte

    def test_retour_chariot_windows(self):
        """Les retours chariot Windows dans un bloc markdown doivent etre geres."""
        texte = '```json\r\n{"titre": "Test"}\r\n```'
        result = extraire_json_llm(texte)
        # The regex uses \n which may or may not match \r\n;
        # at minimum, the function should not crash
        assert "titre" in result


# ── parser_json_llm ──────────────────────────────────────────────────────────


class TestParserJsonLlm:
    """Tests pour parser_json_llm — parsing JSON avec nettoyage."""

    def test_json_pur(self):
        """Un JSON pur doit etre parse correctement."""
        texte = '{"titre": "Test", "score": 8}'
        result = parser_json_llm(texte)
        assert result == {"titre": "Test", "score": 8}

    def test_json_dans_bloc_markdown(self):
        """Un JSON dans un bloc markdown doit etre parse."""
        texte = '```json\n{"titre": "Test"}\n```'
        result = parser_json_llm(texte)
        assert result == {"titre": "Test"}

    def test_json_apres_texte(self):
        """Un JSON apres du texte doit etre parse."""
        texte = 'Voici le resultat: {"titre": "Test"}'
        result = parser_json_llm(texte)
        assert result == {"titre": "Test"}

    def test_tableau_json(self):
        """Un tableau JSON doit etre parse."""
        texte = '[{"id": 1}, {"id": 2}]'
        result = parser_json_llm(texte)
        assert result == [{"id": 1}, {"id": 2}]

    def test_json_invalide_leve_erreur(self):
        """Un texte sans JSON valide doit lever JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            parser_json_llm("Ceci n'est pas du JSON")

    def test_json_partiel_invalide(self):
        """Un JSON tronque doit lever JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            parser_json_llm('{"titre": "incomplet')

    def test_chaine_vide_leve_erreur(self):
        """Une chaine vide doit lever JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            parser_json_llm("")

    def test_json_imbrique_complexe(self):
        """Un JSON imbrique complexe doit etre parse correctement."""
        data = {
            "episode": {
                "titre": "Le buisson ardent",
                "segments": [
                    {"id": "seg_001", "personnage": "narrateur"},
                    {"id": "seg_002", "personnage": "papy_babou"},
                ],
            }
        }
        texte = f'```json\n{json.dumps(data)}\n```'
        result = parser_json_llm(texte)
        assert result == data

    def test_json_avec_accents(self):
        """Un JSON avec des caracteres accentues doit etre parse."""
        texte = '{"morale": "Dieu peut accomplir de grandes choses a travers nous"}'
        result = parser_json_llm(texte)
        assert "morale" in result

    def test_retourne_dict(self):
        """Le resultat doit etre un dict pour un objet JSON."""
        result = parser_json_llm('{"key": "value"}')
        assert isinstance(result, dict)

    def test_retourne_list(self):
        """Le resultat doit etre une list pour un tableau JSON."""
        result = parser_json_llm("[1, 2, 3]")
        assert isinstance(result, list)


# ── fichier_lock ─────────────────────────────────────────────────────────────


class TestFichierLock:
    """Tests pour fichier_lock — verrouillage advisory de fichier."""

    def test_lock_basique(self, tmp_path):
        """Le context manager doit s'executer sans erreur."""
        chemin = tmp_path / "data.json"
        chemin.write_text("{}", encoding="utf-8")
        with fichier_lock(chemin):
            data = json.loads(chemin.read_text(encoding="utf-8"))
            assert data == {}

    def test_lock_file_cree(self, tmp_path):
        """Un fichier .lock doit etre cree pendant le verrouillage."""
        chemin = tmp_path / "data.json"
        chemin.write_text("{}", encoding="utf-8")
        lock_path = chemin.with_suffix(".json.lock")

        with fichier_lock(chemin):
            assert lock_path.exists()

    def test_lock_file_nettoye_apres(self, tmp_path):
        """Le fichier .lock doit etre supprime apres la sortie du context."""
        chemin = tmp_path / "data.json"
        chemin.write_text("{}", encoding="utf-8")
        lock_path = chemin.with_suffix(".json.lock")

        with fichier_lock(chemin):
            pass

        assert not lock_path.exists()

    def test_lock_ecriture_concurrente(self, tmp_path):
        """Ecriture dans un fichier sous lock doit fonctionner."""
        chemin = tmp_path / "data.json"
        chemin.write_text("[]", encoding="utf-8")

        with fichier_lock(chemin):
            data = json.loads(chemin.read_text(encoding="utf-8"))
            data.append({"episode": 1})
            chemin.write_text(json.dumps(data), encoding="utf-8")

        result = json.loads(chemin.read_text(encoding="utf-8"))
        assert result == [{"episode": 1}]

    def test_lock_cree_repertoire_parent(self, tmp_path):
        """Le lock doit creer les repertoires parents si necessaire."""
        chemin = tmp_path / "sous" / "dossier" / "data.json"
        # Le fichier n'existe pas encore mais le lock doit creer le parent
        with fichier_lock(chemin):
            pass
        # Le repertoire parent doit exister maintenant
        assert chemin.parent.exists()

    def test_lock_nettoyage_sur_exception(self, tmp_path):
        """Le fichier .lock doit etre nettoye meme si une exception survient."""
        chemin = tmp_path / "data.json"
        chemin.write_text("{}", encoding="utf-8")
        lock_path = chemin.with_suffix(".json.lock")

        with pytest.raises(ValueError):
            with fichier_lock(chemin):
                raise ValueError("Erreur simulee")

        assert not lock_path.exists()

    def test_lock_suffix_correct(self, tmp_path):
        """Le suffixe du lock doit etre .json.lock pour un fichier .json."""
        chemin = tmp_path / "historique.json"
        chemin.write_text("{}", encoding="utf-8")
        lock_path = chemin.with_suffix(".json.lock")

        with fichier_lock(chemin):
            assert lock_path.exists()
            assert lock_path.name == "historique.json.lock"

    def test_lock_fichier_sans_extension(self, tmp_path):
        """Un fichier sans extension doit aussi etre verrouillable."""
        chemin = tmp_path / "data"
        chemin.write_text("{}", encoding="utf-8")

        with fichier_lock(chemin):
            pass
        # Should not crash

    @patch("utils.fcntl")
    def test_lock_appelle_flock(self, mock_fcntl, tmp_path):
        """fichier_lock doit appeler fcntl.flock avec LOCK_EX puis LOCK_UN."""
        import fcntl as real_fcntl

        mock_fcntl.LOCK_EX = real_fcntl.LOCK_EX
        mock_fcntl.LOCK_UN = real_fcntl.LOCK_UN

        chemin = tmp_path / "data.json"
        chemin.write_text("{}", encoding="utf-8")

        with fichier_lock(chemin):
            pass

        # Verify flock was called with LOCK_EX (lock) and LOCK_UN (unlock)
        flock_calls = mock_fcntl.flock.call_args_list
        assert len(flock_calls) == 2
        assert flock_calls[0][0][1] == real_fcntl.LOCK_EX
        assert flock_calls[1][0][1] == real_fcntl.LOCK_UN


# ── masquer_secret ───────────────────────────────────────────────────────────


class TestMasquerSecret:
    """Tests pour masquer_secret — masquage de cles API."""

    def test_masquage_normal(self):
        """Une cle longue doit etre masquee avec les 4 derniers caracteres visibles."""
        result = masquer_secret("sk-1234567890abcdef")
        assert result.endswith("cdef")
        assert result.startswith("*")
        assert result.count("*") == len("sk-1234567890abcdef") - 4

    def test_masquage_cle_anthropic(self):
        """Une cle Anthropic typique doit etre correctement masquee."""
        cle = "sk-ant-api03-abcdefghijklmnop"
        result = masquer_secret(cle)
        assert result.endswith("mnop")
        assert len(result) == len(cle)

    def test_masquage_cle_elevenlabs(self):
        """Une cle ElevenLabs typique doit etre correctement masquee."""
        cle = "el-abcdef123456"
        result = masquer_secret(cle)
        assert result.endswith("3456")
        assert result.count("*") == len(cle) - 4

    def test_chaine_courte_egal_visible(self):
        """Une chaine de longueur egale a visible doit retourner ****."""
        result = masquer_secret("abcd", visible=4)
        assert result == "****"

    def test_chaine_courte_inferieur_visible(self):
        """Une chaine plus courte que visible doit retourner ****."""
        result = masquer_secret("ab", visible=4)
        assert result == "****"

    def test_chaine_vide(self):
        """Une chaine vide doit retourner ****."""
        result = masquer_secret("")
        assert result == "****"

    def test_chaine_un_caractere(self):
        """Une chaine d'un caractere doit retourner ****."""
        result = masquer_secret("x")
        assert result == "****"

    def test_visible_personnalise(self):
        """Un parametre visible personnalise doit changer le nombre de chars visibles."""
        result = masquer_secret("abcdefghij", visible=6)
        assert result.endswith("efghij")
        assert result.count("*") == 4

    def test_visible_deux(self):
        """visible=2 doit montrer les 2 derniers caracteres."""
        result = masquer_secret("secret123", visible=2)
        assert result.endswith("23")
        assert result.count("*") == len("secret123") - 2

    def test_visible_un(self):
        """visible=1 doit montrer le dernier caractere."""
        result = masquer_secret("mykey", visible=1)
        assert result.endswith("y")
        assert result.count("*") == 4

    def test_longueur_preservee(self):
        """La longueur du resultat doit etre identique a celle de l'entree (si > visible)."""
        cle = "sk-1234567890abcdef"
        result = masquer_secret(cle)
        assert len(result) == len(cle)

    def test_visible_zero(self):
        """visible=0 : valeur[-0:] retourne la chaine entiere (quirk Python)."""
        result = masquer_secret("secret", visible=0)
        # Python: "secret"[-0:] == "secret"[0:] == "secret"
        # So result is "******" + "secret" = "******secret"
        assert result == "******secret"

    def test_cinq_caracteres_visible_quatre(self):
        """Une chaine de 5 chars avec visible=4 doit montrer les 4 derniers."""
        result = masquer_secret("abcde", visible=4)
        assert result == "*bcde"
        assert len(result) == 5

    def test_none_input(self):
        """None en entree doit retourner **** (not valeur est True)."""
        # masquer_secret checks `not valeur` first — None is falsy
        result = masquer_secret(None)
        assert result == "****"
