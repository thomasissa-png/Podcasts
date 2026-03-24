# Revue croisee -- Refactoring "Segment Namespacing" -- 2026-03-24

## Resume executif (non-technique)

Le refactoring segment namespacing (isolation des segments audio par production) est une bonne decision architecturale qui resout un probleme reel : la contamination croisee entre productions successives. L'implementation dans la branche principale (`main.py`) est solide et bien pensee. Cependant, la branche secondaire (`web.py` V2 admin) contient un bug BLOQUANT (arguments inverses dans `upload_file`) et une incoherence de chemin majeure (`OUTPUT_DIR` vs `SEGMENTS_DIR`). En l'etat, la production via `launch-fresh` + `reprendre` fonctionne correctement, mais les routes V2 admin (generation segment par segment) ecriront les fichiers au mauvais endroit et uploadent vers Object Storage avec des cles corrompues. Risque concret : perte de segments audio apres redeploy sur la route V2, montage qui ne trouve pas les fichiers.

## Resume technique

Coherence de la branche principale (`main.py` + `persistent_storage.py`) : 8/10 -- solide, fallbacks legacy corrects.
Coherence de la branche V2 web (`web.py` routes admin) : 4/10 -- bug critique d'inversion d'arguments + mauvais chemin racine.
Couverture tests du nouveau format : 0/10 -- aucun test ne couvre `production_run_id`.
Recommandation : **GO avec reserves** -- la production via `launch-fresh` est sure, mais les routes V2 admin doivent etre corrigees avant utilisation.

## Contradictions detectees

| Livrable A | Livrable B | Contradiction | Criticite | Resolution proposee |
|---|---|---|---|---|
| `persistent_storage.py:86-95` `upload_file(storage_key, local_path)` | `web.py:4502` `ps.upload_file(str(chemin), os_key)` | Arguments INVERSES : le chemin local est passe comme storage_key et vice versa. L'upload ecrit dans Object Storage avec une cle qui est un chemin filesystem (`/home/user/.../seg_001.mp3`) au lieu de `segments/S01E01/prod_xxx/seg_001.mp3`. | BLOQUANT | Inverser les arguments : `ps.upload_file(os_key, chemin)`. Meme correction aux lignes 5028 et 5031. |
| `main.py:2601` `config.SEGMENTS_DIR / episode_id / production_run_id` | `web.py:4421` `config.OUTPUT_DIR / "segments" / episode_id / _prod_run_id` | Chemins racine DIFFERENTS : `config.SEGMENTS_DIR` = `audio/segments/` vs `config.OUTPUT_DIR / "segments"` = `output/episodes/segments/`. Les segments ecrits par `main.py` (via `launch-fresh` / `reprendre`) ne seront pas trouves par les routes V2 de `web.py`. | BLOQUANT | Remplacer `config.OUTPUT_DIR / "segments"` par `config.SEGMENTS_DIR` dans toutes les routes V2 de `web.py` (lignes 2735, 4421, 4423, 4650, 4798, 4800, 4995, 4997). |
| `web.py:2735` purge locale apres `launch-fresh` | `main.py:2601` production_run_id namespacing | `launch-fresh` purge `config.OUTPUT_DIR / "segments" / episode_id` (mauvais chemin) au lieu de `config.SEGMENTS_DIR / episode_id`. La purge ne touche pas le bon repertoire. | MAJEUR | Remplacer par `config.SEGMENTS_DIR / episode_id`. |

## Points valides

- [V] **production_run_id genere au bon endroit** : `main.py:2597-2599` le genere avec fallback depuis checkpoint_data -- correct
- [V] **production_run_id dans tous les checkpoints** : present dans tous les appels `sauvegarder_checkpoint()` (lignes 3204-3213, 3548-3557, 3564-3573, 3709-3718, 3723-3731, 3919-3924, 3984-3989, 4063-4068) -- exhaustif
- [V] **Restauration depuis checkpoint** : `main.py:2597-2599` lit `production_run_id` depuis `checkpoint_data` avec fallback vers generation d'un nouveau -- correct
- [V] **Fallback legacy** : `main.py:3352-3371` tente la restauration legacy (sans production_run_id) et deplace les fichiers vers le dossier namespace -- bien pense
- [V] **Object Storage upload coherent** : `persistent_storage.upload_segments()` et `restore_segments()` utilisent le meme format de cle (`segments/{episode_id}/{production_run_id}/`) -- symetrique
- [V] **Monteur recoit le bon chemin** : `main.py:3889` passe `dossier_segments=segments_production_dir` -- correct
- [V] **SFX dans le meme dossier** : `main.py:3631` passe `dossier_sortie=segments_production_dir` au sfx_provider -- correct
- [V] **web.py launch-fresh** : genere son propre `production_run_id` et le stocke dans le checkpoint -- correct
- [V] **launch-fresh ne purge plus segments/** dans Object Storage : commentaire explicite a la ligne 2721 -- correct, le namespacing rend la purge inutile
- [V] **producteur_audio.py** : nouveau param `dossier_episode` fonctionne correctement, fallback vers l'ancien comportement si non fourni -- retrocompatible
- [V] **sfx_provider.py** : nouveau param `dossier_sortie` fonctionne correctement -- retrocompatible
- [V] **Thread safety** : `production_run_id` est une variable locale dans `_pipeline_inner()`, pas de probleme Gunicorn
- [V] **Atomicite checkpoints** : inchangee, les checkpoints utilisent toujours tempfile + os.replace()

## Risques identifies

- [R1] **web.py V2 routes : fallback filesystem** (`web.py:4650`) -- Le fallback pour servir l'audio d'un segment utilise `config.OUTPUT_DIR / "segments" / episode_id` sans production_run_id. Meme si la DB a le bon `audio_path`, le fallback ne trouvera rien. Fichier: `web.py:4650`. Risque MOYEN -- le fallback est rarement utilise si la DB est disponible.

- [R2] **Accumulation Object Storage** -- Les anciens segments (sans production_run_id) restent dans Object Storage sous `segments/S01E01/seg_001.mp3` tandis que les nouveaux sont sous `segments/S01E01/prod_xxx/seg_001.mp3`. `restore_segments()` sans production_run_id restaurera les anciens. Pas de bug actif grace au fallback legacy dans `main.py:3352-3371`, mais l'espace Object Storage croit indefiniment. Risque MINEUR.

- [R3] **Pas de garbage collection** -- Les dossiers `segments/S01E01/prod_20260324_153042/` ne sont jamais nettoyes apres une production reussie. Sur 10 episodes x 3 tentatives, cela represente ~30 dossiers x 200 fichiers. Risque MINEUR pour l'espace disque.

- [R4] **web.py regenerate-segment** (`web.py:4786-4801`) -- Utilise le meme pattern `config.OUTPUT_DIR / "segments"` (mauvais chemin). Le segment regenere sera ecrit dans le mauvais dossier et le monteur ne le trouvera pas. Risque MAJEUR si cette route est utilisee.

## Bugs trouves

### BUG 1 (BLOQUANT) : Arguments inverses dans `ps.upload_file()`

**Fichier** : `web.py:4502`
**Ligne** : `ps.upload_file(str(chemin), os_key)`
**Attendu** : `ps.upload_file(os_key, str(chemin))`
**Impact** : Les segments uploades via la route V2 ont comme cle Object Storage le chemin filesystem local (ex: `/home/user/Podcasts/papy-babou-podcast/output/episodes/segments/S01E01/prod_xxx/seg_001.mp3`) au lieu de `segments/S01E01/prod_xxx/seg_001.mp3`. Lors d'un redeploy, `restore_segments()` cherche le bon prefixe et ne trouve rien -- perte de tous les segments.
**Fix** :
```python
# web.py:4502
ps.upload_file(os_key, str(chemin))
# web.py:5028
ps.upload_file(os_key_hq, chemin_hq)
# web.py:5031
ps.upload_file(os_key_preview, chemin_preview)
```

### BUG 2 (BLOQUANT) : Chemin racine incorrect dans web.py V2

**Fichier** : `web.py:4421,4423,4650,4798,4800,4995,4997,2735`
**Lignes** : `config.OUTPUT_DIR / "segments" / episode_id`
**Attendu** : `config.SEGMENTS_DIR / episode_id`
**Impact** : `config.OUTPUT_DIR` = `output/episodes/` tandis que `config.SEGMENTS_DIR` = `audio/segments/`. Les routes V2 ecrivent et lisent dans un dossier different de celui utilise par `main.py`. Le monteur V2 (`_job_montage`) ne trouvera aucun segment produit par `_pipeline_inner`.
**Fix** : Remplacer toutes les occurrences de `config.OUTPUT_DIR / "segments"` par `config.SEGMENTS_DIR`.

### BUG 3 (MAJEUR) : Purge locale apres launch-fresh au mauvais chemin

**Fichier** : `web.py:2735`
**Ligne** : `segments_dir = config.OUTPUT_DIR / "segments" / episode_id`
**Attendu** : `segments_dir = config.SEGMENTS_DIR / episode_id`
**Impact** : La purge ne nettoie pas le bon repertoire. Les anciens segments dans `audio/segments/S01E01/` survivent.

## Angles morts

1. **Aucun test** ne couvre le nouveau `production_run_id` : ni l'initialisation, ni le fallback depuis checkpoint, ni le legacy restore, ni le passage aux agents. Tout changement futur risque de casser le namespacing sans detection. Tests necessaires :
   - `TestProductionRunIdGeneration` : verifie le format `prod_YYYYMMDD_HHMMSS`
   - `TestProductionRunIdCheckpointPersistence` : verifie que le ID survit au checkpoint save/load
   - `TestProductionRunIdLegacyFallback` : verifie la restauration depuis ancien format
   - `TestSegmentsNamespacedDir` : verifie que les segments sont ecrits dans le bon sous-dossier
   - `TestUploadSegmentsNamespaced` : verifie les cles Object Storage

2. **CLAUDE.md non mis a jour** : Le refactoring n'est documente dans aucune section "When modifying" de CLAUDE.md. Les regles actuelles de CLAUDE.md decrivent l'ancien systeme (segments dans `segments/{episode_id}/` sans production_run_id).

## Decisions a confirmer

1. **Les routes V2 admin sont-elles utilisees en production ?** Si oui, les bugs 1, 2 et 3 sont BLOQUANTS. Si non (uniquement `launch-fresh` + `reprendre`), la production peut avancer mais les routes V2 restent cassees.

2. **Faut-il un mecanisme de garbage collection** pour les anciens dossiers `prod_YYYYMMDD_*` apres production reussie ?

3. **Faut-il migrer les anciens segments Object Storage** (format `segments/S01E01/seg_001.mp3`) vers le nouveau format namespace, ou laisser le fallback legacy indefiniment ?

## Recommandation

**GO avec reserves** pour la production via `launch-fresh` (qui utilise `main.py` / `reprendre`) -- cette branche est correcte.

**NO-GO** pour les routes V2 admin (`/api/v2/episode/.../generate-audio`, `/api/v2/montage/.../run`, `/api/v2/segment/.../regenerate`) jusqu'a correction des bugs 1, 2 et 3.

**Score de confiance global : 6.5/10**
- `main.py` + `persistent_storage.py` : 9/10
- `producteur_audio.py` + `sfx_provider.py` : 9/10
- `web.py` (launch-fresh) : 8/10
- `web.py` (V2 routes) : 3/10
- Tests : 0/10
- Documentation : 2/10

---
**Handoff -> @orchestrator**
- Fichiers produits : `/home/user/Podcasts/docs/reviews/cross-review-segment-namespacing.md`
- Decisions prises : GO avec reserves pour production via launch-fresh, NO-GO pour routes V2 admin
- Points d'attention :
  - BUG 1 BLOQUANT : arguments inverses dans `ps.upload_file()` a 3 endroits de web.py (lignes 4502, 5028, 5031)
  - BUG 2 BLOQUANT : chemin racine `OUTPUT_DIR` au lieu de `SEGMENTS_DIR` dans 8 endroits de web.py
  - BUG 3 MAJEUR : purge locale launch-fresh au mauvais chemin (web.py:2735)
  - 0 tests pour le nouveau production_run_id
  - CLAUDE.md non mis a jour avec les nouvelles conventions
---
