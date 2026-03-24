# SESSION BRIEFING — Prochaine session Claude Code

## Objectif : Produire les épisodes 1 à 4 de la Saison 1

---

## ÉTAT ACTUEL DES ÉPISODES

### S01E01 — "La création du monde — quand Dieu a tout inventé" (type: ouverture, 30 min)
- **Script** : VALIDÉ, audité 9.2/10, 214 segments (172 voix + 42 SFX), 3505 mots
- **Fichier** : `scripts/episodes/S01E01_script.json` + `_valide.json` (synced)
- **Cover** : `assets/covers/S01E01_cover.png` (1.7 MB)
- **Audio TTS** : FAIT (172 segments voix générés, seg_003=53 chars antoine vérifié)
- **SFX** : FAIT (42 SFX générés)
- **Montage** : EN COURS ou ÉCHOUÉ (timeout 3600s potentiel). Production #48 sur le serveur.
- **PROCHAINE ACTION** : Vérifier si le montage a réussi. Si non → relancer `launch-fresh` avec le script dans le body.
- **PROBLÈME IDENTIFIÉ** : Le montage prend >60 min sur Replit pour un épisode de 30 min / 214 segments. Le timeout `_TIMEOUT_PRODUIRE=3600s` est insuffisant pour la phase chaînée audio+sfx+montage. Solution possible : augmenter `_TIMEOUT_PRODUIRE` ou faire le montage en phase séparée.

### S01E02 — "Noé et le déluge" (type: standard, 25 min)
- **Script** : VALIDÉ, audité 9.0/10, 212 segments (165 voix + 47 SFX), 2854 mots
- **Fichier** : `scripts/episodes/S01E02_script.json` + `_valide.json` (synced)
- **Cover** : `assets/covers/S01E02_cover.png` (1.9 MB)
- **Audio** : PAS ENCORE PRODUIT
- **PROCHAINE ACTION** : Lancer la production audio via `launch-fresh`

### S01E03 — "Abraham — quitter tout par confiance" (type: standard, 25 min)
- **Script** : BROUILLON EXPANSÉ, 205 segments (162 voix + 43 sfx), 2360 mots
- **Fichier** : `scripts/episodes/S01E03_script.json` + `_valide.json` (synced depuis output/scripts/)
- **Cover** : `assets/covers/S01E03_cover.png` (1.9 MB)
- **Audio** : PAS PRODUIT
- **PROCHAINE ACTION** :
  1. Auditer avec `@audit-episode scripts/episodes/S01E03_script.json`
  2. Le script est potentiellement trop court en mots (2360 vs cible ~2800). Vérifier et enrichir si nécessaire.
  3. Appliquer corrections P0+P1
  4. Lancer production audio

### S01E04 — "Joseph et la tunique de couleurs" (type: standard, 25 min)
- **Script** : BROUILLON EXPANSÉ, 217 segments (169 voix + 48 sfx), 2762 mots
- **Fichier** : `scripts/episodes/S01E04_script.json` + `_valide.json` (synced depuis output/scripts/)
- **Cover** : `assets/covers/S01E04_cover.png` (2.0 MB)
- **Audio** : PAS PRODUIT
- **PROCHAINE ACTION** : Auditer et produire (même flow que E03)

---

## PROBLÈME CRITIQUE : TIMEOUT MONTAGE

Le montage audio dépasse 60 min sur Replit pour un épisode de 30 min (214 segments).

**Causes** :
- ffmpeg loudnorm + master bus + export MP3 = CPU-bound, très lent sur containers Replit
- `_TIMEOUT_PRODUIRE = 3600s` (1h) est partagé entre audio + SFX + montage quand lancé via `launch-fresh`
- Quand lancé en phase séparée (`continue-production phase=montage`), le montage a les 3600s pour lui seul mais ça peut encore ne pas suffire

**Solutions possibles** (à implémenter au début de la prochaine session) :
1. **Augmenter `_TIMEOUT_PRODUIRE`** à 5400s (1h30) ou 7200s (2h)
2. **Augmenter aussi `GUNICORN_TIMEOUT`** (actuellement 3900s, doit être > _TIMEOUT_PRODUIRE + marge)
3. **Simplifier le master bus** : désactiver EQ boost + true peak limiter (scipy) qui ajoutent du temps CPU
4. **Réduire la qualité intermédiaire** : WAV 44.1kHz au lieu de 48kHz pour accélérer le traitement

**Action recommandée** : Option 1+2 d'abord (augmenter les timeouts), c'est le changement le plus simple et le moins risqué.

---

## PROTOCOLE DE PRODUCTION (copier-coller)

### Étape 1 : Vérifier / Relancer E01
```bash
# Vérifier le status
curl -s -H "Authorization: Bearer allezpsg" -H "Content-Type: application/json" \
  "https://podcasts-toum92.replit.app/api/claude/query" \
  -d '{"sql": "SELECT id, etape_courante, status FROM productions WHERE episode_id='\''S01E01'\'' ORDER BY id DESC LIMIT 1"}'

# Si completed → vérifier l'audio
curl -s -o /dev/null -w "%{http_code}_%{size_download}" \
  "https://podcasts-toum92.replit.app/audio/episodes/S01E01_la_creation_du_monde_quand_dieu_a_tout_invente_192k.mp3?v=$(date +%s)"

# Si failed/interrupted → kill + relaunch
curl -s -X POST -H "Authorization: Bearer allezpsg" \
  "https://podcasts-toum92.replit.app/api/episode/S01E01/kill-productions"

python3 -c "
import json, subprocess
with open('papy-babou-podcast/scripts/episodes/S01E01_script.json') as f:
    script = json.load(f)
body = json.dumps({'script': script})
r = subprocess.run(['curl', '-s', '-X', 'POST', '-H', 'Authorization: Bearer allezpsg',
    '-H', 'Content-Type: application/json',
    'https://podcasts-toum92.replit.app/api/episode/S01E01/launch-fresh',
    '-d', body], capture_output=True, text=True, timeout=30)
print(r.stdout)
"
```

### Étape 2 : Lancer E02 en parallèle
```bash
curl -s -X POST -H "Authorization: Bearer allezpsg" \
  "https://podcasts-toum92.replit.app/api/episode/S01E02/kill-productions"

python3 -c "
import json, subprocess
with open('papy-babou-podcast/scripts/episodes/S01E02_script.json') as f:
    script = json.load(f)
body = json.dumps({'script': script})
r = subprocess.run(['curl', '-s', '-X', 'POST', '-H', 'Authorization: Bearer allezpsg',
    '-H', 'Content-Type: application/json',
    'https://podcasts-toum92.replit.app/api/episode/S01E02/launch-fresh',
    '-d', body], capture_output=True, text=True, timeout=30)
print(r.stdout)
"
```

### Étape 3 : Auditer E03 et E04
```
@audit-episode scripts/episodes/S01E03_script.json
# Appliquer corrections P0+P1, itérer jusqu'à 9/10

@audit-episode scripts/episodes/S01E04_script.json
# Appliquer corrections P0+P1, itérer jusqu'à 9/10
```

### Étape 4 : Produire E03 et E04
Même protocole launch-fresh que E01/E02 ci-dessus.

---

## FICHIERS CLÉS À LIRE EN DÉBUT DE SESSION

1. `CLAUDE.md` — règles absolues du projet (LONG mais contient toutes les sessions)
2. `data/preferences_producteur.json` — les 24 règles de qualité des scripts
3. `data/personnages.json` — bible des personnages
4. `data/saisons/saison_01.json` — plan de saison (titres, résumés, teasings)
5. Ce fichier `SESSION_BRIEFING.md`

---

## GOÛTERS THÉMATIQUES (ne pas dupliquer)
- E01 : Sablés en forme d'étoiles (Création)
- E02 : Chocolat chaud à la cannelle (Noé / pluie)
- E03 : À définir (Abraham / voyage / confiance)
- E04 : À définir (Joseph / tunique de couleurs)

## PREVIOUSLY-ON (continuité inter-épisodes)
- E02 previously-on : E01 Création (7 jours, dinosaures, fun facts)
- E03 previously-on : E02 Noé (déluge, animaux, arc-en-ciel)
- E04 previously-on : E03 Abraham (voyage, promesse, étoiles)

---

## BRANCHE GIT
- `claude/episode-2-script-QbSiY`
- `git push -u origin claude/episode-2-script-QbSiY`

## URLs
- Public : https://podcasts-toum92.replit.app/
- Admin : https://podcasts-toum92.replit.app/dashboard
- Auth : `Authorization: Bearer allezpsg`
- SQL : `POST /api/claude/query` avec `{"sql": "..."}`
