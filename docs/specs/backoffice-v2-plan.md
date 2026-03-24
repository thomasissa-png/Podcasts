# Back-Office V2 — Specs complètes

## 1. Résumé

Le back-office actuel est un monolithe CLI-wrapper qui lance des subprocess `main.py` opaques. Le V2 le remplace par un workflow granulaire : push script → validation → génération audio segment par segment → écoute/regénération individuelle → montage → publication.

**Stack** : Flask + Jinja2 + vanilla JS + PostgreSQL (Neon) + Object Storage. Pas de framework frontend.

---

## 2. Décisions client (FINALES)

| # | Question | Réponse |
|---|----------|---------|
| Q1 | SFX validation individuelle ? | Non — générés automatiquement en batch |
| Q2 | Édition texte sync script JSON ? | Oui — le script JSON source est modifié |
| Q3 | Association montage/épisode | Contraint à l'épisode d'origine. N montages par épisode, 1 seul publié |
| Q4 | Routes Claude API | Garder `/api/claude/query` pour monitoring |
| Q5 | Publication = RSS/Buzzsprout ? | Non — juste rendre écoutable sur le site |
| Q6 | Purge | Garder |

---

## 3. Modèle de données

### Nouvelle table : `segments_audio`

```sql
CREATE TABLE segments_audio (
    id SERIAL PRIMARY KEY,
    episode_id VARCHAR(10) NOT NULL,
    segment_id VARCHAR(20) NOT NULL,          -- "seg_003"
    segment_type VARCHAR(10) DEFAULT 'voix',  -- "voix" | "sfx"
    personnage VARCHAR(50),
    texte TEXT,                                -- texte TTS actuel (éditable)
    texte_original TEXT,                       -- texte du script initial (immutable)
    ton VARCHAR(30),
    rythme VARCHAR(10),
    sfx_prompt TEXT,                           -- pour les SFX uniquement
    audio_path TEXT,                           -- chemin fichier MP3
    audio_os_key TEXT,                         -- clé Object Storage
    duree_ms INTEGER,
    nb_caracteres INTEGER,
    status VARCHAR(20) DEFAULT 'pending',      -- pending | generating | generated | validated | error
    version INTEGER DEFAULT 1,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_seg_audio_uniq ON segments_audio(episode_id, segment_id, version);
CREATE INDEX idx_seg_audio_episode ON segments_audio(episode_id, status);
```

### Nouvelle table : `montages`

```sql
CREATE TABLE montages (
    id SERIAL PRIMARY KEY,
    episode_id VARCHAR(10) NOT NULL,
    audio_path_hq TEXT,                       -- chemin MP3 192k
    audio_path_preview TEXT,                  -- chemin MP3 64k
    audio_os_key_hq TEXT,                     -- Object Storage key HQ
    audio_os_key_preview TEXT,
    duree_secondes FLOAT,
    taille_bytes BIGINT,
    nb_segments INTEGER,
    status VARCHAR(20) DEFAULT 'pending',     -- pending | processing | completed | error
    is_published BOOLEAN DEFAULT FALSE,       -- 1 seul par episode_id
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_montage_episode ON montages(episode_id);
-- Contrainte : max 1 published par episode
CREATE UNIQUE INDEX idx_montage_published ON montages(episode_id) WHERE is_published = TRUE;
```

### Tables existantes — pas de modification structurelle

Les tables `scripts`, `productions`, `fichiers_audio`, `episodes`, `saisons`, `historique_episodes` restent telles quelles. Le V2 écrit dans `segments_audio` et `montages` au lieu de passer par le pipeline monolithique.

---

## 4. Routes API

### 4.1 Scripts

| Méthode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `POST` | `/api/v2/episode/{id}/push-script` | Upload script JSON | `{script: {...}}` | `{ok, nb_segments, nb_sfx, nb_mots}` |
| `GET` | `/api/v2/episode/{id}/script` | Lire script avec stats | — | `{script, stats, status}` |
| `POST` | `/api/v2/episode/{id}/validate-script` | Valider le script | — | `{ok}` |

**Push script** :
1. Sauvegarde dans `scripts/episodes/{id}_script.json` + `_valide.json`
2. Upload Object Storage (`scripts/`)
3. Sauvegarde en DB (`ScriptRepo`)
4. Crée les lignes `segments_audio` (status=pending) pour tous les segments
5. Retourne les stats (nb segments voix, SFX, mots, ratios personnages)

### 4.2 Audio — Génération

| Méthode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `POST` | `/api/v2/episode/{id}/generate-audio` | Lance TTS de tous les segments | — | `{job_id}` |
| `GET` | `/api/v2/episode/{id}/segments` | Liste segments + statut audio | `?type=voix\|sfx\|all` | `[{segment_id, personnage, texte, status, audio_url, duree_ms}]` |
| `GET` | `/api/v2/episode/{id}/audio-progress` | Progression génération | — | `{total, generated, validated, errors, percent}` |
| `GET` | `/api/v2/segment/{episode_id}/{segment_id}/audio` | Servir fichier audio segment | — | MP3 file |
| `POST` | `/api/v2/segment/{episode_id}/{segment_id}/regenerate` | Regénérer 1 segment | `{texte?: string}` | `{job_id}` |
| `POST` | `/api/v2/segment/{episode_id}/{segment_id}/validate` | Valider 1 segment | — | `{ok}` |
| `POST` | `/api/v2/episode/{id}/validate-all-segments` | Valider tous les segments d'un coup | — | `{ok, count}` |

**generate-audio** (job async) :
1. Vérifie script validé
2. Pour chaque segment voix : appelle `ProducteurAudio._generer_segment()`, met à jour `segments_audio` (status, audio_path, duree_ms)
3. Pour chaque SFX : appelle `SfxProvider.generer()`, met à jour `segments_audio`
4. Front-end poll `/audio-progress` pour la barre de progression

**regenerate** (job async ou sync selon durée) :
1. Si `texte` fourni : met à jour `segments_audio.texte` ET le script JSON source
2. Incrémente `version`
3. Appelle `_generer_segment()` avec le nouveau texte
4. Met à jour `audio_path`, `duree_ms`, reset `status=generated`

### 4.3 Montage

| Méthode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `POST` | `/api/v2/episode/{id}/montage` | Lancer le montage | — | `{job_id}` |
| `GET` | `/api/v2/episode/{id}/montages` | Liste des montages | — | `[{id, duree, taille, status, is_published, created_at}]` |
| `GET` | `/api/v2/montage/{montage_id}/audio` | Servir audio montage | `?quality=hq\|preview` | MP3 file |
| `GET` | `/api/v2/montage/{montage_id}/download` | Télécharger HD | — | MP3 file (Content-Disposition: attachment) |

**montage** (job async ~20-30 min) :
1. Vérifie que tous segments voix sont `validated` ou `generated`
2. Appelle `Monteur.assembler(script, dossier_segments, dossier_sortie)`
3. Crée ligne dans `montages` avec paths, durée, taille
4. Upload Object Storage (`audio/`)

### 4.4 Publication

| Méthode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `POST` | `/api/v2/montage/{montage_id}/publish` | Publier ce montage | — | `{ok}` |
| `GET` | `/api/v2/saisons/episodes` | Vue 30 épisodes (3 saisons) | — | `[{episode_id, titre, saison, numero, status, has_script, has_audio, is_published, montage_count}]` |

**publish** :
1. Dé-publie tout autre montage du même épisode (`is_published=FALSE`)
2. Met `is_published=TRUE` sur le montage choisi
3. Copie l'audio vers le chemin attendu par le front public (`output/audio/episodes/{id}_*.mp3`)
4. Met à jour `fichiers_audio` pour que `/api/public/episodes` le voit
5. Met à jour `historique_episodes` si besoin

### 4.5 Admin / Monitoring (conservées)

| Route | Statut |
|-------|--------|
| `/api/claude/query` | **Conservée** — monitoring SQL |
| `/api/job-status/{id}` | **Conservée** — polling jobs async |
| `/api/running-jobs` | **Conservée** — reconnexion browser |
| `/api/storage-status` | **Conservée** — diagnostic |
| `/api/purge/saison/{num}` | **Conservée** |
| `/api/purge/tout` | **Conservée** |
| `/api/public/episodes` | **Conservée** — front public |
| Auth routes | **Conservées** |

### 4.6 Routes supprimées

| Route | Raison |
|-------|--------|
| `/api/produire` | Pipeline monolithique → remplacé par push-script + generate-audio |
| `/api/planifier-saison` | Fait dans Claude Code |
| `/api/produire-saison` | Pipeline monolithique |
| `/api/reprendre` | Remplacé par generate-audio / montage |
| `/api/batch` | Plus pertinent |
| `/api/episode/{id}/launch-fresh` | Remplacé par push-script + generate-audio |
| `/api/episode/{id}/continue-production` | Remplacé par generate-audio / montage |
| `/api/episode/{id}/kill-productions` | Simplifié — les jobs V2 sont granulaires |

---

## 5. Écrans

### Écran 1 : Hub épisodes (`/admin`)

**Vue** : Tableau des 30 épisodes (3 saisons), groupés par onglets saison.

| Colonne | Contenu |
|---------|---------|
| # | Numéro |
| Titre | Titre de l'épisode (depuis saison plan) |
| Type | ouverture / standard / mi-saison / final |
| Script | Badge : ✓ validé / ⏳ poussé / — aucun |
| Audio | Badge : ✓ N/N segments / ⏳ en cours / — |
| Montage | Badge : ✓ N montages / — |
| Publié | Badge vert si un montage est publié |
| Action | Bouton → détail épisode |

**États** :
- Vide : "Aucune saison planifiée" (ne devrait pas arriver — les 3 saisons sont imposées)
- Normal : tableau avec badges colorés

### Écran 2 : Détail épisode (`/admin/episode/{id}`)

Page unique avec 4 sections verticales (accordéon ou toujours visibles) :

**Section A — Script**
- Affichage du script : liste scrollable des segments (personnage, texte, ton, type)
- Stats : nb segments, nb mots, ratios personnages, score review
- Actions : "Pousser un script" (upload JSON), "Valider le script"
- Si pas de script : zone d'upload (drag & drop ou bouton)

**Section B — Audio**
- Barre de progression : "42/156 segments générés"
- Bouton "Lancer la génération audio" (disabled si script non validé)
- Liste des segments avec player audio inline :
  - Chaque ligne : `[▶] seg_003 | papy_babou | "Il était une fois..." | ✓ validé`
  - Clic sur texte → édition inline
  - Bouton "Regénérer" par segment
  - Bouton "Valider" par segment
  - Bouton "Tout valider" en haut
- Filtres : Tous / Voix seulement / SFX seulement / Erreurs

**Section C — Montage**
- Bouton "Lancer le montage" (disabled si segments non tous validés/générés)
- Liste des montages existants : player, durée, taille, date, bouton "Télécharger HD"
- Bouton "Publier" par montage (radio — 1 seul actif)

**Section D — Info**
- Épisode : saison, numéro, type, histoire biblique
- Cover art (si existante)
- Lien vers le front public si publié

### Écran 3 : Login (`/admin/login`)

Inchangé.

---

## 6. Workflow utilisateur

```
Claude Code                          Back-office V2
───────────                          ──────────────
1. Écrire script
2. Auditer (@audit-episode)
3. Itérer jusqu'à 9/10
4. POST /api/v2/episode/{id}/push-script ──→ Script sauvé + segments créés
                                          5. Client ouvre /admin/episode/{id}
                                          6. Relit le script (Section A)
                                          7. Clique "Valider le script"
                                          8. Clique "Lancer la génération audio"
                                          9. Attend (~15-25 min) — barre progression
                                         10. Écoute chaque segment (Section B)
                                         11. Édite texte + regénère si besoin
                                         12. Valide tous les segments
                                         13. Clique "Lancer le montage"
                                         14. Attend (~20-30 min)
                                         15. Écoute le montage final
                                         16. Télécharge en HD si besoin
                                         17. Clique "Publier" → épisode visible sur site public
```

---

## 7. Détails techniques

### 7.1 Génération audio — réutilisation du code existant

```python
# producteur_audio.py — méthode existante réutilisée directement
ProducteurAudio._generer_segment(segment: dict, chemin_sortie: Path) -> None

# sfx_provider.py — méthode existante
SfxProvider.generer(description: str, chemin_sortie: Path) -> Path

# monteur.py — méthode existante
Monteur.assembler(script: dict, dossier_segments: Path, dossier_sortie: Path) -> dict
```

Le V2 appelle ces méthodes directement depuis les routes Flask (via jobs async), au lieu de lancer un subprocess `main.py`.

### 7.2 Jobs async

Pattern existant conservé : `_start_job(job_id, target_fn, args)` + `_jobs` dict en mémoire + polling `/api/job-status/{id}`.

Nouveaux jobs :
- `generate-audio-{episode_id}` : itère sur les segments, appelle `_generer_segment()` pour chacun
- `regenerate-{episode_id}-{segment_id}` : regénère 1 segment
- `montage-{episode_id}` : appelle `Monteur.assembler()`

### 7.3 SIGTERM resilience

Chaque segment généré est immédiatement persisté (DB + Object Storage). Sur redeploy :
- Les segments `generated`/`validated` survivent
- Les segments `generating` sont reset à `pending`
- Le client relance `generate-audio` qui ne regénère que les `pending`

### 7.4 Script sync on text edit

Quand un segment est regénéré avec un texte modifié :
1. `segments_audio.texte` mis à jour en DB
2. Le script JSON source est rechargé, le segment trouvé par `segment_id`, le texte remplacé
3. Le script est resauvé dans `_script.json` + `_valide.json` + Object Storage
4. Ceci garantit que le montage utilise toujours le texte le plus récent

---

## 8. Migration

### Phase 1 : Nouvelles routes et nouveau template
- Créer `web_v2.py` (ou ajouter les routes V2 dans `web.py` avec préfixe `/api/v2/`)
- Créer `templates/admin_v2.html` (nouveau dashboard)
- Ajouter tables `segments_audio` et `montages` dans `database.py`

### Phase 2 : Basculement
- `/admin` → sert `admin_v2.html` au lieu de `dashboard.html`
- Anciennes routes conservées temporairement (préfixe `/api/legacy/`) puis supprimées

### Ce qui est conservé tel quel
- `public.html` et toutes ses routes
- Auth (Bearer token)
- `_start_job` / `_jobs` / `pollJob` pattern
- Object Storage (persistent_storage.py)
- Tous les agents Python (producteur_audio, sfx_provider, monteur)

---

## 9. Répartition agents

| Phase | Agent | Mission | Fichiers |
|-------|-------|---------|----------|
| 1 | @product-manager | User stories + critères d'acceptation détaillés | `docs/specs/backoffice-v2-stories.md` |
| 2 | @fullstack | Migration DB (tables segments_audio, montages) | `database.py` |
| 3 | @fullstack | Routes API V2 (scripts, audio, montage, publication) | `web.py` ou `web_v2.py` |
| 4 | @fullstack | Template admin V2 (HTML/JS/CSS) | `templates/admin_v2.html` |
| 5 | @design | Audit visuel du dashboard V2 vs charte graphique | Corrections CSS |
| 6 | @qa | Tests routes API + workflow E2E | `tests/test_web_v2.py` |

**Phase 1 optionnelle** — le plan actuel est suffisamment détaillé pour que @fullstack commence directement en Phase 2.

---

## 10. Risques et mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| `_generer_segment()` hors pipeline perd SIGTERM handler | Segments perdus | Chaque segment persisté immédiatement en DB + OS |
| Replit redeploy pendant génération | Job interrompu | Segments `generating` → reset `pending` au restart |
| Monteur attend segments dans un dossier | Path mismatch | Convention conservée : `output/segments/{episode_id}/` |
| Édition texte désynchronise script | Montage incohérent | Sync automatique script JSON sur chaque regénération |
| 30+ min de montage dépasse timeout | Job tué | Timeout Gunicorn 3900s > montage max 30 min |
