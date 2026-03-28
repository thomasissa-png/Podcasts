# Revue croisee — Workflow Montages V2 — 2026-03-24

## Resume executif (non-technique)

Le workflow montages → back-office → publication → homepage contient **2 bugs CRITIQUES qui empechent toute publication fonctionnelle**. Les deux endpoints de publication (V1 et V2) copient l'audio dans un sous-dossier errone (`output/episodes/audio/episodes/`) au lieu du dossier servi par le site (`output/episodes/`). En consequence, meme apres avoir clique "Publier" avec succes, l'episode n'apparait jamais sur la homepage publique. La depublication ne supprime pas non plus le fichier audio, donc un episode depublie resterait visible si le bug de chemin etait corrige. **Recommandation : NO-GO pour la publication tant que ces 2 bugs ne sont pas corriges.**

## Resume technique

Score global : **4.5/10**. La logique de listing des montages (V1+V2, deduplication, fallback DB/fichier/Object Storage) est bien construite. Mais la chaine publication → visibilite publique est cassee par une erreur de chemin filesystem. 2 bloquants, 3 hauts, 5 moyens. **NO-GO publication.**

## Contradictions detectees

| Livrable A | Livrable B | Contradiction | Criticite | Resolution proposee |
|---|---|---|---|---|
| `api_v2_publish` (web.py:5296) | `serve_episode_audio` (web.py:227) | `publish` copie vers `config.OUTPUT_DIR / "audio" / "episodes"` = `output/episodes/audio/episodes/` mais la route audio sert depuis `config.OUTPUT_DIR` = `output/episodes/`. Le fichier publie n'est JAMAIS accessible. | BLOQUANT | Remplacer `config.OUTPUT_DIR / "audio" / "episodes"` par `config.OUTPUT_DIR` dans les 2 endpoints publish (V1 et V2). Idem pour le commentaire docstring de `publish-v1`. |
| `api_v2_publish_v1` (web.py:5409) | `_build_v1_montage_dict` (web.py:5128) | `publish-v1` cherche le fichier source dans `config.OUTPUT_DIR / "episodes"` = `output/episodes/episodes/` (double "episodes"). Or le fichier V1 est dans `config.OUTPUT_DIR` = `output/episodes/`. Le fichier source ne sera JAMAIS trouve. | BLOQUANT | Ligne 5409 : remplacer `config.OUTPUT_DIR / "episodes" / audio_filename` par `config.OUTPUT_DIR / audio_filename`. |
| `api_v2_depublish` (web.py:5445-5461) | `api_public_episodes` (web.py:1195-1206) | `depublish` ne met a jour que le flag DB (`is_published=False`) mais ne supprime/renomme PAS le fichier audio public (`output/episodes/S01EXX_192k.mp3`). La homepage cherche les fichiers audio par glob — l'episode reste visible. | MAJEUR | Apres `MontageRepo.depublier()`, supprimer (ou renommer) le fichier `config.OUTPUT_DIR / f"{episode_id}_192k.mp3"` et le preview. |
| `_build_v1_montage_dict` (web.py:5146) | Stabilite inter-redeploy | Les IDs V1 utilisent `hash(chemin_hq)` de Python. `hash()` est NON deterministe entre processus (PYTHONHASHSEED aleatoire par defaut). Le meme montage V1 aura un ID different apres chaque restart Gunicorn/redeploy Replit. | MAJEUR | Utiliser `hashlib.md5(chemin_hq.encode()).hexdigest()[:8]` au lieu de `hash()`. |
| `api_v2_publish_v1` (web.py:5394-5441) | `api_v2_publish` (web.py:5281-5390) | `publish_v1` ne met PAS a jour le RSS et n'appelle PAS `ajouter_historique()`. Un episode publie via V1 n'apparaitra pas dans le flux RSS ni dans les plateformes podcast. | MAJEUR | Ajouter dans `publish_v1` : (1) bloc RSS identique a `publish_v2`, (2) appel `ajouter_historique()`. |

## Problemes supplementaires

### HAUTE severite

**H1 — Path traversal dans publish-v1** (web.py:5412)
Si `audio_url` ne correspond pas au premier chemin teste, le fallback fait `src = Path(audio_url.lstrip("/"))`. Un attaquant pourrait envoyer `audio_url = "/etc/passwd"` et copier n'importe quel fichier du serveur vers le dossier public. La route est protegee par `@_admin_required` (authentification), ce qui limite le risque, mais c'est une mauvaise pratique.
- **Suggestion** : Valider que `src.resolve()` reste dans `config.OUTPUT_DIR.resolve()` avant de copier. Rejeter tout chemin en dehors.

**H2 — depublish V1 impossible** (web.py:5444)
Le route `depublish` prend un `montage_id` de type `int` (`<int:montage_id>`). Or les IDs V1 sont des strings comme `"v1_abc12345"`. Cliquer "Depublier" sur un montage V1 retournera toujours 404 car Flask ne matchera jamais la route.
- **Suggestion** : Le bouton depublish ne devrait pas etre affiche pour les montages V1, OU creer une route `/api/v2/episode/<episode_id>/depublish-v1`.

**H3 — publish V1 ne marque pas `is_published` en DB** (web.py:5394-5441)
`publish-v1` copie le fichier et met a jour le rapport, mais ne touche a aucune table `montages` ni `episodes.published_montage_id`. La vue consolidee `api_v2_saisons_episodes` (line 5494) verifie `is_published` via `MontageRepo.lister()` — un episode publie via V1 n'apparaitra pas comme "publie" dans la vue saisons.
- **Suggestion** : Creer une ligne montage V2 dans la DB lors de la publication V1 (avec `is_published=True`), ou stocker le flag directement dans `episodes.published_montage_id`.

### MOYENNE severite

**M1 — Pas de confirmation double pour publication** (admin_v2.html:766-769)
Le bouton "Publier" (V2) n'a pas de `confirm()` — un clic accidentel publie immediatement. Depublier a bien un `confirm()` (line 785). Asymetrie UX.
- **Suggestion** : Ajouter `if (!confirm('Publier ce montage ?')) return;` avant l'appel API.

**M2 — trouver_audio_batch glob ne cherche pas dans le bon dossier** (dashboard_data.py:202)
`config.OUTPUT_DIR.glob("*.mp3")` cherche dans `output/episodes/`. Mais si le publish ecrivait au bon endroit, ca fonctionnerait. Ce n'est pas un bug supplementaire, c'est la meme cause racine (B1/B2).

**M3 — V1 montages : `is_published` toujours `False`** (web.py:5152)
`_build_v1_montage_dict` met `"is_published": False` en dur. Meme si l'episode a ete publie via V1 et que le fichier existe dans le dossier public, le montage V1 n'affiche jamais le check vert ni le bouton "Depublier". L'utilisateur ne sait pas qu'il est deja publie.
- **Suggestion** : Detecter si le fichier `config.OUTPUT_DIR / f"{episode_id}_192k.mp3"` existe et est le meme que le V1 audio → mettre `is_published = True`.

**M4 — Tri des montages non garanti** (web.py:4979-4990)
`MontageRepo.lister()` retourne les montages V2, puis les V1 sont appended a la fin. L'utilisateur attend le plus recent en premier. Aucun tri explicite du resultat final.
- **Suggestion** : Trier `montages` par `created_at DESC` apres la fusion V1+V2.

**M5 — Depublish ne met pas a jour le rapport** (web.py:5444-5461)
La publication (V2) cree un rapport avec `publication.status = "ok"`. La depublication ne retire pas ce statut. Si la homepage lisait aussi le rapport (via `trouver_fichier_audio`), l'episode pourrait rester visible.
- **Suggestion** : Mettre a jour le rapport en retirant `etapes.publication` lors de la depublication.

## Angles morts

1. **Pas de test E2E du flux complet publish → homepage** : Les tests verifient le listing des montages et la deduplication, mais aucun test ne verifie que la publication rend effectivement l'episode visible sur `api_public_episodes`. C'est exactement le flux casse par les bugs B1/B2.

2. **Pas de gestion d'erreur si la copie audio echoue** (publish V2, line 5301) : `shutil.copy2` peut echouer (disque plein, permissions). Pas de try/except autour — le code continue quand meme avec `MontageRepo.publier()` et `ajouter_historique()`. L'episode sera marque comme publie en DB sans audio accessible.

3. **Pas de rollback si le RSS echoue** (publish V2, line 5354) : Si la mise a jour RSS echoue, l'episode est quand meme marque comme publie. L'utilisateur pense avoir publie mais les plateformes (Apple, Spotify) ne le voient pas.

4. **Pas de validation `audio_url` dans publish-v1** : Le frontend passe `m.audio_url_hq` directement, qui pourrait etre `null` si l'audio n'a jamais ete charge. Cote backend la validation `if not audio_url` attrape `""` mais pas `None` (Python: `not None` is `True`, ok). En revanche, `audio_url.split("/")`  crashera si `audio_url` est un entier par exemple.

## Decisions a confirmer

1. **Chemin de publication** : La destination correcte est-elle `config.OUTPUT_DIR` (= `output/episodes/`) ou un autre dossier ? Verifier avec la route `serve_episode_audio` (line 227) qui sert depuis `config.OUTPUT_DIR`.

2. **Comportement souhaite apres depublication** : L'audio doit-il etre supprime/renomme, ou seulement masque via un flag ? Si masque, la homepage doit verifier un flag de publication, pas juste l'existence du fichier.

3. **Publication V1 vs V2** : L'utilisateur a-t-il besoin de deux endpoints distincts ou peut-on unifier en un seul endpoint qui gere les deux cas ?

## Recommandation

**NO-GO** — Les 2 bugs BLOQUANTS empechent toute publication fonctionnelle. Aucun episode publie via le back-office V2 (ni V1 ni V2) ne sera visible sur la homepage. Les corrections sont ciblees et ne necessitent pas de refactoring lourd :

### Actions prioritaires (par ordre)

1. **[BLOQUANT] Corriger le chemin de publication** (B1+B2) — Remplacer `config.OUTPUT_DIR / "audio" / "episodes"` par `config.OUTPUT_DIR` dans `api_v2_publish` et `api_v2_publish_v1`. Corriger aussi la source V1 (`config.OUTPUT_DIR / "episodes"` → `config.OUTPUT_DIR`). Estimation : 15 min.

2. **[MAJEUR] Depublish supprime le fichier** (B3) — Ajouter la suppression du fichier audio public dans `api_v2_depublish`. Estimation : 10 min.

3. **[MAJEUR] IDs V1 stables** (B4) — Remplacer `hash()` par `hashlib.md5().hexdigest()[:8]`. Estimation : 5 min.

4. **[MAJEUR] RSS + historique dans publish-v1** (B5) — Copier le bloc RSS de `api_v2_publish` dans `api_v2_publish_v1`. Estimation : 15 min.

5. **[HAUTE] Path traversal** (H1) — Ajouter validation `resolve()` dans publish-v1. Estimation : 5 min.

6. **[HAUTE] Depublish V1 impossible** (H2) — Masquer le bouton depublish pour V1, ou creer une route dediee. Estimation : 10 min.

7. **[HAUTE] Publish V1 DB flag** (H3) — Marquer `is_published` en DB lors de la publication V1. Estimation : 15 min.

8. **[MOYENNE] Tests E2E publish → homepage** — Ajouter un test qui verifie que `api_public_episodes` retourne un `audio_url` apres publication. Estimation : 20 min.

---
**Handoff → @orchestrator**
- Fichiers produits : `/home/user/Podcasts/papy-babou-podcast/docs/reviews/cross-review-montage-workflow.md`
- Decisions prises : NO-GO publication, 2 bloquants + 3 majeurs + 3 hauts + 5 moyens identifies
- Points d'attention : Les 2 bugs BLOQUANTS (chemin de copie errone) sont la cause racine. Les corriger devrait debloquer le flux complet. Agents a reinvoquer : @fullstack pour les corrections de code, @qa pour les tests E2E manquants.
