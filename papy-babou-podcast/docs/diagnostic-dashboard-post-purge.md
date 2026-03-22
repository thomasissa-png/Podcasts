# Diagnostic Dashboard Post-Purge DB + Redeploiement

**Date** : 2026-03-22
**Contexte** : Apres purge PostgreSQL + redeploiement Replit

## Etat des lieux

### Fichiers locaux presents (tous OK)

| Fichier | E01 | E02 |
|---------|-----|-----|
| `scripts/episodes/S01EXX_script.json` | OK | OK |
| `scripts/episodes/S01EXX_valide.json` | OK | OK |
| `checkpoints/S01EXX_checkpoint.json` | OK | OK |
| `logs/S01EXX_rapport.json` | OK | OK |
| `data/historique_episodes.json` | OK (2 entrees) | OK |

### Checkpoints

- **E01** : `etape: waiting_script`, `validation_humaine: true`, `type: ouverture`
- **E02** : `etape: waiting_script`, `validation_humaine: true`, `type: standard`

### Rapports

- **E01** : `validation_date: "2026-03-21T14:40:00"`, `validation_web: true`
- **E02** : `validation_date: "2026-03-22T20:04:00"`, `validation_web: true`

### Base de donnees PostgreSQL

**VIDE** apres purge. Aucune ligne dans `productions`, `scripts`, etc.

---

## Probleme 1 : E02 affiche "Script valide" SANS date

### Cause racine

Le dashboard HTML affiche les informations de validation depuis le rapport (charge via `charger_rapport()`). Apres purge DB, `charger_rapport()` :
1. Essaie la DB -> **VIDE** (purge)
2. Fallback fichier JSON -> `logs/S01E02_rapport.json` -> **TROUVE**

Le rapport E02 contient bien `validation_date` dans `etapes.script`. Si la date ne s'affiche pas, c'est un probleme d'affichage dans le template `dashboard.html` qui ne lit peut-etre pas `validation_date` de la meme facon pour E01 et E02.

**Impact** : Cosmetique uniquement. Les donnees sont la, l'affichage est incorrect.

### Correction

Verifier dans `dashboard.html` comment la date de validation script est affichee. S'assurer que le template lit `rapport.etapes.script.validation_date` de facon coherente.

---

## Probleme 2 : "Script valide introuvable pour S01E02"

### Cause racine

L'erreur vient de `web.py:2261` dans `api_continue_production()` :
```python
if not _restore_valide_script(episode_id):
    return {"error": "Script valide introuvable pour S01E02..."}
```

**`_restore_valide_script()` (web.py:444-490) fait :**
1. Verifie `S01E02_valide.json` existe -> si OUI, retourne True
2. Verifie `S01E02_script.json` existe -> copie vers `_valide.json`, retourne True
3. Object Storage `restore_script()` -> restaure `_valide.json`
4. DB `ScriptRepo.charger_valide()` -> DB VIDE apres purge

**Le fichier `_valide.json` existe maintenant** (Glob confirme). Deux scenarios possibles :

**Scenario A (le plus probable)** : L'erreur s'est produite pendant un redeploiement Replit AVANT que les fichiers ne soient recrees. Le filesystem etait vide (wipe Replit), la DB etait vide (purge manuelle), et Object Storage n'avait pas les fichiers (jamais uploades car les scripts ont ete crees manuellement dans des sessions Claude Code, pas via le pipeline web).

**Scenario B** : Les fichiers viennent d'etre restaures (git pull, ou recrees manuellement) et l'erreur ne se reproduira plus.

### Verification immediate

Cliquer "Lancer montage" pour E02 depuis le dashboard. Si l'erreur ne se reproduit plus, le probleme etait transitoire.

### Correction structurelle (2 actions)

**Action 1 : Uploader les scripts vers Object Storage MAINTENANT**

Les scripts E01/E02 n'ont jamais ete uploades vers Object Storage car ils ont ete crees/modifies dans des sessions Claude Code (pas via le pipeline web). Executer :

```python
# Script a executer une fois pour uploader les scripts existants
import persistent_storage
import config

for eid in ["S01E01", "S01E02"]:
    for suffix in ["_valide.json", "_script.json"]:
        path = config.SCRIPTS_DIR / f"{eid}{suffix}"
        if path.exists():
            key = persistent_storage.upload_script(eid, path)
            print(f"Uploaded {path.name} -> {key}")

    # Uploader aussi rapport et checkpoint
    rapport_path = config.LOGS_DIR / f"{eid}_rapport.json"
    if rapport_path.exists():
        persistent_storage.upload_rapport(eid, rapport_path)
        print(f"Uploaded {rapport_path.name}")

    cp_path = config.CHECKPOINTS_DIR / f"{eid}_checkpoint.json"
    if cp_path.exists():
        persistent_storage.upload_checkpoint(eid, cp_path)
        print(f"Uploaded {cp_path.name}")
```

**Action 2 : Ameliorer `_restore_valide_script()` pour restaurer aussi `_script.json`**

`restore_script()` dans `persistent_storage.py` (ligne 304-316) ne restaure QUE `_valide.json`. Si ce fichier n'est pas dans Object Storage mais que `_script.json` l'est, la restauration echoue. Modifier `_restore_valide_script()` dans `web.py` pour aussi tenter de restaurer `_script.json` depuis Object Storage :

Fichier : `web.py`, dans `_restore_valide_script()`, apres la couche 2 (Object Storage), ajouter :
```python
# Couche 2b : Object Storage — restaurer _script.json si _valide.json absent
if not valide_path.exists():
    try:
        script_key = f"scripts/{episode_id}_script.json"
        if persistent_storage.download_file(script_key, script_source):
            import shutil
            shutil.copy2(script_source, valide_path)
            logger.info("_restore_valide_script: restaure _script.json depuis OS puis copie vers _valide pour %s", episode_id)
            return True
    except Exception as e:
        logger.debug("_restore_valide_script: OS _script.json pour %s : %s", episode_id, e)
```

**Action 3 : Synchroniser les donnees locales vers la DB**

Apres purge DB, les fichiers locaux (historique, rapports, checkpoints) contiennent des donnees que la DB n'a plus. Executer `migrate_json_to_db.py` si disponible, ou creer un script de re-sync :

```python
# Resynchroniser l'historique vers la DB
from db_models import HistoriqueRepo
import json, config

hist_path = config.HISTORIQUE_DIR / "historique_episodes.json"
if hist_path.exists():
    with open(hist_path) as f:
        historique = json.load(f)
    for ep in historique:
        try:
            HistoriqueRepo.sauvegarder(ep)
            print(f"Synced {ep['episode_id']}")
        except Exception as e:
            print(f"Error syncing {ep['episode_id']}: {e}")
```

---

## Probleme 3 : E01 affiche "Script : 2026-03-22 20:59"

### Cause

Le rapport E01 montre `validation_date: "2026-03-21T14:40:00"` mais le dashboard affiche "2026-03-22 20:59". Cette date ne correspond a aucune donnee dans le rapport local.

Deux explications possibles :
1. Le rapport a ete mis a jour en DB lors d'une validation web le 22/03 a 20:59, et la DB contenait cette date AVANT la purge
2. Le rapport local a ete recree manuellement avec la date de creation originale, pas la date de la derniere validation web

Apres purge DB, cette date est perdue. Le rapport local montre la date originale.

### Impact

Cosmetique. La date affichee n'est pas exacte, mais les flags `validation_humaine: true` sont corrects.

---

## Resume des actions

| # | Action | Priorite | Impact |
|---|--------|----------|--------|
| 1 | Tester "Lancer montage E02" maintenant | IMMEDIATE | Verifie si le probleme est resolu |
| 2 | Uploader scripts/rapports/checkpoints vers Object Storage | HAUTE | Previent la perte au prochain redeploiement |
| 3 | Ameliorer `_restore_valide_script()` pour `_script.json` | MOYENNE | Robustesse du fallback |
| 4 | Re-synchroniser historique vers la DB | MOYENNE | Dashboard complet apres purge |
| 5 | Verifier affichage date validation dans dashboard.html | BASSE | Cosmetique |
