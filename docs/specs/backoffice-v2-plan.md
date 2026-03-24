# Back-Office V2 — Plan complet de redesign

## 1. Resume executif

**Probleme** : Le back-office actuel est un monolithe (dashboard.html ~3000 lignes, web.py ~4000 lignes) construit sur 28 sessions. Il lance des subprocess `main.py` opaques sans visibilite segment par segment. L'edition de texte ne modifie pas le script source. Pas de gestion multi-montages.

**Solution** : 6 ecrans dedies, une table `segments_audio` pour le suivi granulaire, une table `montages` pour les versions. Le script JSON reste la source de verite. Chaque segment est editable/regenerable individuellement. Le montage produit une ligne en DB, le client choisit lequel publier.

**Stack** : Flask + Jinja2 + vanilla JS + PostgreSQL (Neon) + Object Storage. Pas de framework frontend.

---

## 2. Modele de donnees

### 2.1 Nouvelle table : `segments_audio`

```sql
CREATE TABLE IF NOT EXISTS segments_audio (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    segment_id      VARCHAR(20) NOT NULL,          -- "seg_003"
    segment_type    VARCHAR(10) DEFAULT 'voix',    -- "voix" | "sfx"
    personnage      VARCHAR(50),
    texte           TEXT,                           -- texte TTS actuel (editable)
    texte_original  TEXT,                           -- texte du script initial (immutable)
    ton             VARCHAR(30),
    rythme          VARCHAR(10),
    sfx_prompt      TEXT,                           -- pour les SFX uniquement
    audio_path      TEXT,                           -- chemin fichier MP3 local
    audio_os_key    TEXT,                           -- cle Object Storage
    duree_ms        INTEGER DEFAULT 0,
    nb_caracteres   INTEGER DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'pending',
        -- pending | generating | generated | validated | error
    version         INTEGER DEFAULT 1,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_seg_audio_uniq
    ON segments_audio(episode_id, segment_id, version);
CREATE INDEX IF NOT EXISTS idx_seg_audio_episode
    ON segments_audio(episode_id, status);
```

**Regles** :
- 1 ligne par segment du script (voix + SFX)
- `texte` = valeur courante (mutable). `texte_original` = valeur a la creation (immutable)
- Quand `texte` est edite, `version` s'incremente et `status` passe a `pending`
- Les SFX ont `segment_type='sfx'`, `sfx_prompt` rempli, `personnage='sfx'`

### 2.2 Nouvelle table : `montages`

```sql
CREATE TABLE IF NOT EXISTS montages (
    id              SERIAL PRIMARY KEY,
    episode_id      VARCHAR(10) NOT NULL,
    audio_path_hq   TEXT,                          -- chemin MP3 192k
    audio_path_preview TEXT,                       -- chemin MP3 128k
    audio_os_key_hq TEXT,
    audio_os_key_preview TEXT,
    duree_secondes  FLOAT DEFAULT 0,
    taille_bytes    BIGINT DEFAULT 0,
    nb_segments     INTEGER DEFAULT 0,
    chapitres_json  JSONB DEFAULT '[]',
    status          VARCHAR(20) DEFAULT 'pending',
        -- pending | processing | completed | error
    is_published    BOOLEAN DEFAULT FALSE,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_montage_episode ON montages(episode_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_montage_published
    ON montages(episode_id) WHERE is_published = TRUE;
```

**Regles** :
- N montages par episode, 1 seul `is_published=TRUE` a la fois (contrainte unique partielle)
- Le montage est lance quand tous les segments voix sont `validated` ou `generated`
- `chapitres_json` = snapshot des chapitres generes par `Monteur`

### 2.3 Tables existantes — modifications

| Table | Modification | SQL |
|-------|-------------|-----|
| `episodes` | Ajouter colonne | `ALTER TABLE episodes ADD COLUMN IF NOT EXISTS published_montage_id INT REFERENCES montages(id)` |
| `episodes` | Ajouter colonne | `ALTER TABLE episodes ADD COLUMN IF NOT EXISTS script_validated_at TIMESTAMPTZ` |

### 2.4 Tables conservees sans modification

`saisons`, `scripts`, `reviews`, `productions`, `metadonnees`, `fichiers_audio`, `historique_episodes`, `preferences_producteur`, `personnages`, `couts_api`, `publications`, `audit_log`.

---

## 3. Routes API

Toutes les routes V2 sont sous le prefixe `/api/v2/`. Auth : `Authorization: Bearer <token>`.

### 3.1 Scripts

| Methode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `POST` | `/api/v2/episode/{eid}/push-script` | Push script JSON | `{script: {...}}` | `{ok, nb_segments, nb_sfx, nb_mots}` |
| `GET` | `/api/v2/episode/{eid}/script` | Lire script + stats | — | `{script, stats, validated}` |
| `POST` | `/api/v2/episode/{eid}/validate-script` | Valider le script | — | `{ok, validated_at}` |

**`push-script` details** :
1. Sauve dans `scripts/episodes/{eid}_script.json` + `_valide.json`
2. Upload Object Storage (`scripts/`)
3. Sauve en DB (`ScriptRepo.sauvegarder`, `is_validated=True`)
4. DELETE les anciennes lignes `segments_audio` pour cet episode (reset complet)
5. INSERT une ligne `segments_audio` par segment (status=pending, texte=texte du script)
6. Retourne stats : nb segments voix, SFX, mots, ratios personnages

### 3.2 Audio — Generation

| Methode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `POST` | `/api/v2/episode/{eid}/generate-audio` | Lance TTS pour tous les segments pending | — | `{job_id}` |
| `GET` | `/api/v2/episode/{eid}/segments` | Liste segments + statut | `?type=voix\|sfx\|all&status=pending,error` | `[{segment_id, personnage, texte, status, audio_url, duree_ms, ton, rythme}]` |
| `GET` | `/api/v2/episode/{eid}/audio-progress` | Progression generation | — | `{total, pending, generating, generated, validated, errors, percent}` |

**`generate-audio` job** :
1. Verifie script valide
2. Pour chaque segment voix `status IN (pending, error)` :
   - `status = generating`
   - Appelle `ProducteurAudio._generer_segment(segment_dict, chemin)`
   - Si succes : `status = generated`, met a jour `audio_path`, `duree_ms`, `nb_caracteres`
   - Si erreur : `status = error`, `error_message = str(e)`
3. Pour chaque SFX `status IN (pending, error)` :
   - Appelle `SfxProvider.generer(sfx_prompt, chemin)`
   - Meme pattern de mise a jour
4. Skip les segments deja `generated` ou `validated` (reprise apres interruption)

### 3.3 Audio — Segment individuel

| Methode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `GET` | `/api/v2/segment/{eid}/{seg_id}/audio` | Stream MP3 du segment | — | `audio/mpeg` |
| `POST` | `/api/v2/segment/{eid}/{seg_id}/edit` | Editer le texte | `{texte: "..."}` | `{ok, segment_id}` |
| `POST` | `/api/v2/segment/{eid}/{seg_id}/regenerate` | Regenerer le TTS | `{texte?: "..."}` | `{job_id}` |
| `POST` | `/api/v2/segment/{eid}/{seg_id}/validate` | Valider le segment | — | `{ok}` |
| `POST` | `/api/v2/episode/{eid}/validate-all-segments` | Valider tous d'un coup | — | `{ok, count}` |

**`edit` details** :
1. Met a jour `segments_audio.texte`
2. Charge le script JSON via `ScriptRepo.charger_valide(eid)`
3. Trouve le segment par `segment_id` dans `script.episode.segments`
4. Remplace le texte
5. Sauve le script modifie : fichier local + `_valide.json` + DB (`ScriptRepo.sauvegarder`) + Object Storage
6. Passe le segment en `status=pending` (necessite regeneration)

**`regenerate` details** :
1. Si `texte` fourni dans le body : execute la logique `edit` d'abord
2. Incremente `version` dans `segments_audio`
3. `status = generating`
4. Appelle `ProducteurAudio._generer_segment()`
5. Met a jour `audio_path`, `duree_ms`, `status = generated`

### 3.4 SFX

| Methode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `GET` | `/api/v2/episode/{eid}/sfx` | Liste SFX generes | — | `[{segment_id, sfx_prompt, status, audio_url}]` |

Pas de validation individuelle SFX. Generes automatiquement par `generate-audio`.

### 3.5 Montage

| Methode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `POST` | `/api/v2/episode/{eid}/montage` | Lancer un montage | — | `{job_id, montage_id}` |
| `GET` | `/api/v2/episode/{eid}/montages` | Liste montages | — | `[{id, status, duree, taille, is_published, audio_url, created_at}]` |
| `GET` | `/api/v2/montage/{mid}/audio` | Stream montage | `?quality=hq\|preview` | `audio/mpeg` |
| `GET` | `/api/v2/montage/{mid}/download` | Telecharger HD | — | `audio/mpeg` (attachment) |

**`montage` job (~20-30 min)** :
1. Verifie que tous segments voix ont `status IN (validated, generated)`
2. Cree une ligne `montages` (status=processing)
3. Appelle `Monteur.assembler(script, dossier_segments, dossier_sortie)`
4. Met a jour `montages` : paths, duree, taille, `status=completed`
5. Upload Object Storage (`audio/`)
6. Si erreur : `status=error`, `error_message`

### 3.6 Publication

| Methode | Route | Description | Body | Response |
|---------|-------|-------------|------|----------|
| `POST` | `/api/v2/montage/{mid}/publish` | Publier ce montage | — | `{ok}` |
| `POST` | `/api/v2/montage/{mid}/unpublish` | Depublier | — | `{ok}` |

**`publish` details** :
1. `UPDATE montages SET is_published=FALSE WHERE episode_id=X`
2. `UPDATE montages SET is_published=TRUE WHERE id=mid`
3. `UPDATE episodes SET published_montage_id=mid`
4. Copie audio HQ vers `output/audio/episodes/{eid}_*.mp3` (chemin attendu par le front public)
5. Met a jour `historique_episodes` si absent
6. L'episode apparait sur `/api/public/episodes`

### 3.7 Admin / Monitoring (conserves)

| Route | Statut |
|-------|--------|
| `/api/claude/query` | Conservee |
| `/api/job-status/{id}` | Conservee |
| `/api/running-jobs` | Conservee |
| `/api/storage-status` | Conservee |
| `/api/purge/saison/{num}` | Conservee — ajouter cleanup `segments_audio` + `montages` |
| `/api/purge/tout` | Conservee — ajouter cleanup `segments_audio` + `montages` |
| `/api/public/episodes` | Conservee |
| Auth routes | Conservees |

### 3.8 Routes supprimees

| Route v1 | Remplacement v2 |
|----------|-----------------|
| `/api/produire` | `push-script` + `generate-audio` |
| `/api/episode/{eid}/launch-fresh` | `push-script` + `generate-audio` |
| `/api/episode/{eid}/continue-production` | `generate-audio` / `montage` |
| `/api/episode/{eid}/regenerate` | `segment/{seg}/regenerate` |
| `/api/episode/{eid}/validate` | `validate-script` / `validate-all-segments` / `publish` |
| `/api/episode/{eid}/kill-productions` | Jobs V2 sont granulaires, pas besoin |
| `/api/reprendre` | Reprise implicite (segments pending = regenerer) |
| `/api/batch` | Hors scope |
| `/api/produire-saison` | Hors scope |
| `/api/planifier-saison` | Fait dans Claude Code |

---

## 4. Ecrans

### 4.1 Hub episodes (`/admin`)

**Composants** : Onglets par saison (S1, S2, S3). Tableau par saison :

| Colonne | Contenu |
|---------|---------|
| # | Numero |
| Titre | Depuis `saison_XX.json` |
| Type | Badge : ouverture / standard / mi-saison / final |
| Script | `--` / `Pousse` / `Valide` |
| Audio | `--` / `12/156` / `156/156` |
| Montage | `--` / `2 montages` |
| Publie | Badge vert si `is_published` |
| Action | Lien vers detail |

**Etats** :
- Vide : "Aucune saison planifiee" (improbable — 3 saisons imposees)
- Normal : badges couleur par statut

### 4.2 Detail episode (`/admin/episode/{eid}`)

4 sections verticales :

**Section A — Script**
- Stats : nb segments, nb mots, ratios personnages, score review
- Liste scrollable des segments (read-only ici)
- Bouton "Valider le script" (si pas encore valide)
- Si pas de script : message "En attente — poussez le script depuis Claude Code"

**Section B — Audio**
- Barre de progression : `42/156 segments generes (12 valides)`
- Bouton "Generer l'audio" (disabled si script non valide)
- Bouton "Voir les segments" → lien vers ecran 4.3
- Bouton "Tout valider" (disabled si pas tous generes)

**Section C — Montage**
- Bouton "Lancer montage" (disabled si segments non tous valides/generes)
- Liste montages avec player inline, duree, taille
- Bouton "Telecharger HD" et "Publier" par montage
- Badge "Publie" sur le montage actif

**Section D — Info**
- Saison, numero, type, histoire biblique
- Cover art (si existante)
- Lien front public si publie

### 4.3 Segments audio (`/admin/episode/{eid}/segments`)

**Composants** :
- **Filtres** en haut : Tous / Voix / SFX / A valider / Erreurs
- **Barre progression** sticky : `N/total valides`
- **Liste segments** :
  - Badge personnage (couleur : rouge Antoine, jaune Noemie, bleu Papy, rose Mamie, gris SFX)
  - Texte du segment (editable inline pour voix, read-only pour SFX)
  - Player audio mini (play/pause + duree)
  - Badges ton + rythme
  - Boutons : Valider (check) / Regenerer (refresh) / Editer (crayon)
- **Bouton "Tout valider"** en sticky bottom

**Etats par segment** :
| Status | Visuel |
|--------|--------|
| pending | Grise, pas de player |
| generating | Spinner anime |
| generated | Player actif, boutons visibles |
| validated | Check vert, texte verrouille (clic pour deverrouiller) |
| error | Rouge, message erreur, bouton "Regenerer" |

### 4.4 Montages (`/admin/episode/{eid}/montages`)

Integre dans la Section C de l'ecran 4.2. Pas d'ecran separe.

### 4.5 Login (`/admin/login`)

Inchange.

### 4.6 Dashboard stats (`/admin/dashboard`)

Stats globales : episodes par statut, segments generes total, montages, couts API.
Conserve les panels v1 (preferences producteur, retours humains).
Ajoute des stats depuis `segments_audio` et `montages`.

---

## 5. Workflow detaille

```
Claude Code                          Back-office V2                    Front public
-----------                          --------------                    ------------
1. Ecrit script (scripteur+audit)
2. POST push-script {script} ------> 3. Script sauve (DB+FS+OS)
                                         Segments crees (pending)
                                      4. Client ouvre /admin/episode/{id}
                                      5. Relit le script
                                      6. Clique "Valider le script"
                                      7. Clique "Generer l'audio"
                                      8. Job async demarre :
                                         seg_001 pending→generating→generated
                                         seg_002 pending→generating→generated
                                         ...
                                         sfx_001 pending→generating→generated
                                         (barre de progression en temps reel)
                                      9. Client ecoute segment par segment
                                     10. Edite texte si besoin :
                                         POST segment/edit → texte MAJ
                                         POST segment/regenerate → TTS relance
                                         Script JSON MAJ automatiquement
                                     11. Valide les segments (un par un ou tous)
                                     12. Clique "Lancer montage"
                                     13. Job async (~25 min) :
                                         Monteur.assembler()
                                         → ligne montages en DB
                                     14. Ecoute le montage
                                     15. Telecharge HD si besoin
                                     16. Clique "Publier" ------------>  Episode visible
                                                                         sur le site
```

### Resilience (redeploy Replit)

| Evenement | Consequence | Reprise |
|-----------|-------------|---------|
| Redeploy pendant generation TTS | Segments `generating` perdus | Client relance `generate-audio` — les segments `generated`/`validated` sont skip |
| Redeploy pendant montage | Montage `processing` perdu | Client relance `montage` — segments intacts |
| Filesystem wipe | Fichiers MP3 locaux perdus | Restauration automatique depuis Object Storage via `restore_segments()` |

**Principe** : chaque segment genere est immediatement persiste en DB + Object Storage. La reprise est implicite — relancer `generate-audio` ne regenere que les `pending`.

---

## 6. Migration

### Phase 1 — Coexistence (zero downtime)

1. Ajouter les 2 tables SQL (`segments_audio`, `montages`) + ALTER TABLE episodes
2. Ajouter les routes `/api/v2/*` dans `web.py` (le v1 reste fonctionnel)
3. Creer les templates Jinja2 dans `templates/admin/`
4. Brancher `/admin` sur le nouveau template

### Phase 2 — Nettoyage

1. Supprimer `dashboard.html`
2. Supprimer les routes v1 obsoletes (voir 3.8)
3. Supprimer les fonctions helper v1 (`_chain_sfx_then_montage`, `_chain_montage`, etc.)

### Conserve tel quel

| Element | Raison |
|---------|--------|
| `public.html` + routes publiques | Front public inchange |
| `admin_login.html` | Auth inchangee |
| `producteur_audio.py` (`_generer_segment`) | Reutilise directement |
| `sfx_provider.py` (`generer`) | Reutilise directement |
| `monteur.py` (`assembler`) | Reutilise directement |
| `persistent_storage.py` | Upload/restore inchange |
| `db_models.py` classes existantes | Backward compat |
| `database.py` schema existant | Additif uniquement |
| Routes `/api/claude/*` | Debug/monitoring |
| Routes `/api/purge/*` | Admin |
| Job system (`_jobs` dict, `_start_job`) | Pattern reutilise |
| SIGTERM handler | Conserve pour montage (20-30 min) |

### Episodes v1 deja produits

Les episodes produits en v1 restent visibles. Les donnees sont dans `productions`, `fichiers_audio`, `historique_episodes` — non touches. Le front public (`/api/public/episodes`) continue de lire `historique_episodes`.

---

## 7. Repartition agents

| Phase | Agent | Mission | Fichiers a produire |
|-------|-------|---------|---------------------|
| 1 | @fullstack | Migration SQL : 2 tables + ALTER | `database.py` |
| 2 | @fullstack | Repos DB : `SegmentAudioRepo`, `MontageRepo` | `db_models.py` |
| 3 | @fullstack | Routes API V2 : scripts, audio, segments, montage, publication | `web.py` (section v2) |
| 4 | @fullstack | Jobs async : generate-audio, regenerate, montage | `web.py` (section jobs v2) |
| 5 | @fullstack + @design | Templates Jinja2 + CSS + JS | `templates/admin/base.html`, `episode.html`, `segments.html`, `static/admin_v2.js`, `static/admin_v2.css` |
| 6 | @qa | Tests API + workflow E2E | `tests/test_backoffice_v2.py` |
| 7 | @infrastructure | Basculement routes, cleanup v1, verification Object Storage | `web.py` |

---

## 8. Questions resolues

| # | Question | Reponse |
|---|----------|---------|
| Q1 | SFX : validation individuelle ? | **Non.** Generes automatiquement en batch par `generate-audio`. Affiches en gris dans la liste, non editables. |
| Q2 | Edit texte → sync script ? | **Oui.** `POST segment/edit` met a jour le segment en DB ET le script JSON source (nouvelle version via `ScriptRepo`). |
| Q3 | Association montage ↔ episode | **Contraint.** Un montage appartient a son episode. N montages par episode. Le client choisit lequel publier. Pas de desassociation. |
| Q4 | Routes Claude API | **Conservees.** `/api/claude/query` reste pour le monitoring. Pas de nouvelles routes IA. |
| Q5 | Publication = quoi ? | **Rendre ecoutable sur le site.** Pas de RSS, pas de Buzzsprout. `is_published=TRUE` sur le montage + copie audio vers le chemin front public. |
| Q6 | Purge | **Conservee.** `/api/purge/*` inchanges + cleanup `segments_audio` et `montages`. |
