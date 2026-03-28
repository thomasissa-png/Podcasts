# Plan d'action — Dashboard V2 Back-office

**Date** : 2026-03-24
**Etat actuel** : Phase 2 livree (tables DB, repos, 16 routes API, SPA frontend)
**QA** : tests en cours d'ecriture

---

## Analyse de l'existant

### Ce qui fonctionne
- Structure DB solide (`segments_audio`, `montages`) avec versioning et tracking granulaire
- 16 routes API V2 couvrant tout le workflow : push-script, validate, generate-audio, segments CRUD, montage, publish
- SPA frontend `admin_v2.html` avec 3 vues (hub saisons, episode detail, segments list)
- Job system V2 utilisant `_start_fn_job` (threads Python, pas de subprocess) — plus simple que V1
- Segment-by-segment edit + regenerate + validate
- Filtres segments (voix/sfx/erreurs), progress bars, toast notifications

### Problemes critiques identifies

---

## P0 — BLOQUANTS (a corriger avant toute production)

### P0-1 : `SfxProvider.generer()` n'existe pas
**Fichier** : `web.py:4291`
**Probleme** : La route V2 appelle `sfx_provider.generer(seg.get("texte", ""), chemin)` mais `SfxProvider` n'a PAS de methode `generer()`. Les methodes existantes sont `produire_sfx(script)` (batch) et `_generer_elevenlabs(segment, chemin, chemin_cache)` (private). La generation SFX va planter sur TOUS les segments SFX.
**Fix** : Ajouter une methode publique `SfxProvider.generer_segment(texte: str, chemin: Path)` qui encapsule la chaine local→cache→curatee→elevenlabs→freesound→silence pour un segment individuel. OU refactorer le code V2 pour utiliser `_generer_elevenlabs` directement avec la bonne signature.
**Agent** : @fullstack
**Risque regression V1** : Aucun si on ajoute une methode sans toucher aux existantes

### P0-2 : `ProducteurAudio._generer_segment()` est une methode privee
**Fichier** : `web.py:4293`
**Probleme** : Appel direct a `producteur._generer_segment(seg, chemin)`. C'est une methode privee qui s'attend a certaines pre-conditions (voice_id configure, compteur thread-safe, rate limiter). L'appel nu depuis la route V2 bypass le setup normal fait par `ProducteurAudio.produire()`.
**Fix** : Creer une methode publique `ProducteurAudio.generer_segment(segment: dict, chemin: Path)` qui fait le setup minimum puis appelle `_generer_segment`. Ou extraire proprement le code necessaire.
**Agent** : @fullstack
**Risque regression V1** : Faible si la methode publique wrappe la privee

### P0-3 : Pas de restauration Object Storage pour segments V2
**Fichier** : `web.py:4276`
**Probleme** : `_job_generate_audio` verifie `Path(db_seg["audio_path"]).exists()` pour skip les segments deja generes, mais apres un redeploy Replit les fichiers locaux sont perdus. Il faut restaurer depuis Object Storage (comme le fait V1 avec `restore_segments()`).
**Fix** : Ajouter une tentative de `restore_segment()` depuis OS quand `audio_path` existe en DB mais pas sur le filesystem.
**Agent** : @fullstack
**Risque regression V1** : Aucun

### P0-4 : Monteur.assembler() signature incompatible
**Fichier** : `web.py:4590`
**Probleme** : La route V2 appelle `monteur.assembler(script, dossier_segments=segments_dir, dossier_sortie=sortie_dir)` mais la signature reelle est `assembler(self, script: dict, dossier_segments: Path | None = None, dossier_sortie: Path | None = None)`. Le probleme potentiel est que `assembler()` utilise des chemins internes (`config.SEGMENTS_DIR / episode_id`) si les parametres ne sont pas passes. Il faut verifier que les keyword args sont bien pris en compte et que le monteur ne cherche pas les segments ailleurs.
**Fix** : Verifier la signature exacte, tester un appel. Si `assembler` ignore les kwargs et utilise ses propres chemins, il faut patcher. Aussi, le V2 ne gere pas le `numero_saison` pour le jingle selection.
**Agent** : @fullstack + @qa

### P0-5 : Auth manquante sur `/admin/v2`
**Fichier** : `web.py:4821-4824`
**Probleme** : La route `/admin/v2` rend le template sans aucune verification d'authentification. Contrairement au dashboard V1 (`/dashboard`) qui est protege. N'importe qui peut acceder au back-office V2.
**Fix** : Ajouter le decorateur `@require_auth` (ou equivalent utilise par V1).
**Agent** : @fullstack
**Risque regression V1** : Aucun

---

## P1 — IMPORTANTS (necessaires pour un workflow complet)

### P1-1 : Generation audio sequentielle (pas de parallelisme)
**Fichier** : `web.py:4266`
**Probleme** : `_job_generate_audio` genere les segments un par un dans une boucle `for`. L'existant V1 utilise `ProducteurAudio.produire()` avec `ThreadPoolExecutor` et `max_workers` pour paralleliser le TTS. Sur 150+ segments, la generation sequentielle prendra ~4x plus longtemps.
**Fix** : Utiliser `concurrent.futures.ThreadPoolExecutor` dans `_job_generate_audio` comme le fait V1.
**Agent** : @fullstack

### P1-2 : Pas de progress polling temps reel pendant la generation
**Probleme** : Le frontend poll `/api/job-status/<job_id>` qui ne retourne que "done" ou "running". Pendant la generation des ~190 segments (20-30 min), l'utilisateur voit juste un spinner sans progression.
**Fix** : Poll `/api/v2/episode/<eid>/audio-progress` en parallele du job status. Ajouter un `setInterval` cote frontend qui refresh la progress bar pendant que le job tourne.
**Agent** : @fullstack (frontend)

### P1-3 : Publication V2 ne met pas a jour le RSS feed
**Fichier** : `web.py:4705-4764`
**Probleme** : `api_v2_publish` copie les fichiers audio et met a jour l'historique JSON, mais ne met PAS a jour le RSS feed via `Publisher.publier()`. Les episodes "publies" via V2 ne seront pas visibles sur les plateformes podcast (Apple, Spotify).
**Fix** : Appeler `Publisher._mettre_a_jour_rss()` ou le workflow complet de publication V1 apres la copie des fichiers.
**Agent** : @fullstack

### P1-4 : Pas de lien entre V2 et le systeme de rapport V1
**Probleme** : Les productions V2 ne creent pas de `rapport` V1 (pas de `ProductionRepo.creer()`, pas de `_rapport.json`). Le dashboard V1 ne voit pas les episodes produits via V2, et les mecanismes de resilience (SIGTERM handler, auto-resume) ne couvrent pas les jobs V2.
**Fix** : Creer une passerelle minimale : quand un montage V2 est publie, generer un `rapport` compatible V1 pour que le dashboard V1 et le site public voient les donnees.
**Agent** : @fullstack

### P1-5 : Segment edit ne gere pas les champs ton/rythme
**Fichier** : `web.py:4394`
**Probleme** : `api_v2_segment_edit` ne permet de modifier que le `texte`. Mais le frontend a des metadonnees `ton` et `rythme` affiches. L'utilisateur ne peut pas changer le ton ou le rythme d'un segment avant de le regenerer.
**Fix** : Ajouter `ton` et `rythme` comme champs editables dans le POST body + la route.
**Agent** : @fullstack

### P1-6 : Pas de mecanisme de retry sur erreur segment
**Probleme** : Quand un segment echoue (ElevenLabs timeout, rate limit), il est marque "error" et c'est tout. L'utilisateur doit manuellement cliquer "regenerer" sur chaque segment en erreur. Sur 190 segments avec le rate limiter ElevenLabs (3/s), des erreurs sont inévitables.
**Fix** : Ajouter un bouton "Regenerer les erreurs" qui relance tous les segments en status "error". Aussi, ajouter un retry automatique (max 2) dans `_job_generate_audio`.
**Agent** : @fullstack

---

## P2 — AMELIORATIONS UX (nice-to-have pour la V2 initiale)

### P2-1 : Pas de vue script dans le frontend
Le SPA n'affiche que les stats du script (segments, mots) mais pas le contenu. L'utilisateur doit ouvrir le JSON pour lire le script. Ajouter une vue script inline dans la page episode serait utile.

### P2-2 : Pas de comparaison avant/apres sur l'edition de segment
Quand un segment est edite, le `texte_original` est conserve en DB mais pas affiche. Montrer le diff aiderait a tracker les modifications.

### P2-3 : Pas de search dans la liste des segments
Avec 190+ segments, trouver un segment specifique necessite du scroll. Un champ recherche par personnage/texte serait utile.

### P2-4 : Pas de bulk actions sur les segments
Selectionner plusieurs segments pour les regenerer en batch ou changer leur ton.

### P2-5 : Dark mode
Le SPA n'a pas de toggle dark mode (coherent avec le site public qui n'en a pas non plus).

### P2-6 : Waveform/preview audio inline
Les mini players audio fonctionnent mais une waveform visuelle aiderait au QA audio.

---

## Risques de regression V1

| Zone | Risque | Mitigation |
|------|--------|------------|
| Routes V1 (`/api/episode`, `/api/produire`) | Aucun — routes V2 sous prefixe `/api/v2/` | Isolation par prefixe |
| DB schema | Faible — nouvelles tables, pas de modification des existantes | Migration additive |
| Monteur.assembler() | MOYEN — V2 appelle avec kwargs potentiellement differents de V1 | Tests specifiques |
| ProducteurAudio | MOYEN — V2 appelle `_generer_segment` hors contexte normal | Nouvelle methode publique |
| SfxProvider | ELEVE — V2 appelle une methode inexistante | Fix P0-1 obligatoire |
| Publication/RSS | MOYEN — V2 ne passe pas par Publisher | Fix P1-3 |
| Auth | ELEVE — V2 pas protege | Fix P0-5 immédiat |
| Job system V1 (subprocess) | Aucun — V2 utilise threads, V1 inchange | Systemes independants |

---

## Ordre d'execution recommande

1. **P0-5** Auth (5 min, @fullstack) — securite immediate
2. **P0-1 + P0-2** Methodes publiques SfxProvider + ProducteurAudio (30 min, @fullstack)
3. **P0-4** Verifier Monteur.assembler kwargs (15 min, @qa)
4. **P0-3** Object Storage restore pour segments V2 (20 min, @fullstack)
5. **P1-1** Paralleliser la generation audio (30 min, @fullstack)
6. **P1-2** Progress polling temps reel (20 min, @fullstack frontend)
7. **P1-6** Retry/bulk regenerate erreurs (20 min, @fullstack)
8. **P1-3** Publication RSS (30 min, @fullstack)
9. **P1-4** Passerelle rapport V1/V2 (45 min, @fullstack)
10. **P1-5** Edit ton/rythme (15 min, @fullstack)

**Estimation totale P0+P1** : ~4h de travail fullstack + tests QA
**Agent principal** : @fullstack
**Agent QA** : tests des routes V2, regression V1, integration Monteur
