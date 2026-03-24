# AUDIT EXPERIENCE SONORE — S01E03 "Abraham et le ciel plein d'etoiles"
## Par Thomas Lavigne, sound designer
### AUDIT v3

**Date** : 2026-03-23
**Episode** : S01E03 — Saison 1, Episode 3
**Duree cible** : 13 minutes (standard)
**Ambiance** : calme

---

### Metriques sonores

| Metrique | Valeur | Cible | Status |
|----------|--------|-------|--------|
| SFX total | 15 | >=10 (episode standard 13min) | OK |
| Overlays | 10 (66.7% des SFX) | >=30% | OK |
| Inserts | 5 | - | - |
| Ratio SFX/voix | 23.4% (15 SFX / 64 voix) | 20-25% | OK — pile dans la cible |
| Duree totale overlays | 52s | - | OK |
| Trous sonores (>6 seg voix consecutifs) | 4 | 0 | PROBLEME |
| SFX dans ouverture (30s) | 1 (sfx_001) | >=2 | MINEUR |
| Zones obligatoires couvertes | 6/8 | 8/8 | A CORRIGER |

---

### Carte de couverture sonore

| Fenetre | Segments voix | SFX presents | Trou | Status |
|---------|---------------|-------------|------|--------|
| 1 (pos 0-12) | seg_000 a seg_010b | sfx_001 (overlay, pos 1) | 11 voix entre sfx_001 et sfx_002 | TROU — 11 segments sans SFX |
| 2 (pos 13-19) | seg_011 a seg_015 | sfx_002 (overlay), sfx_003 (insert) | — | OK — dense |
| 3 (pos 20-27) | seg_016 a seg_018e | sfx_014 (overlay) | 7 voix entre sfx_014 et sfx_004 | TROU — 7 segments |
| 4 (pos 28-33) | seg_019 a seg_021 | sfx_004 (overlay), sfx_013 (overlay), sfx_015 (overlay) | — | OK — tres dense |
| 5 (pos 34-42) | seg_021b a seg_024 | — | 9 voix entre sfx_015 et sfx_005 | TROU — 9 segments, section famine + explication descendance |
| 6 (pos 43-51) | seg_025 a seg_031 | sfx_005 (overlay) | 8 voix entre sfx_005 et sfx_011 | TROU — 8 segments, scene etoiles + Mamie Sonia |
| 7 (pos 52-57) | seg_032 a seg_036 | sfx_011 (overlay) | — | OK |
| 8 (pos 58-65) | seg_037 a seg_044 | sfx_006 (insert), sfx_009 (overlay) | — | OK |
| 9 (pos 66-72) | seg_045 a seg_049 | sfx_010 (insert), sfx_007 (insert) | — | OK — section morale bien couverte |
| 10 (pos 73-78) | seg_050 a seg_055 | sfx_012 (overlay), sfx_008 (insert) | — | OK — teasing + outro |

**Trous identifies :**
1. **11 segments** (pos 1 → 13) : seg_001 a seg_010b. Toute la section d'exposition du salon (presentation des enfants, inquietude d'Antoine, rappel de Noe). sfx_001 est un overlay de 6s seulement — il couvre au mieux seg_001. Les 10 segments suivants sont nus.
2. **7 segments** (pos 20 → 28) : seg_016 a seg_018e. Section du voyage d'Abraham dans le desert, les etoiles comme GPS. sfx_014 est un overlay de 4s qui couvre seg_016 max. Le reste est a decouvert.
3. **9 segments** (pos 33 → 43) : seg_021b a seg_024. La famine a Canaan + explication de la descendance. Section dramatique laissee completement nue.
4. **8 segments** (pos 43 → 52) : seg_025 a seg_031. Scene emblematique des etoiles + arrivee de Mamie Sonia. sfx_005 est un overlay de 6s au debut de la fenetre. 7 segments restants sans habillage.

---

### Zones obligatoires

| Zone | Couverte | SFX ID | Commentaire |
|------|----------|--------|-------------|
| 1. Cold open | PARTIEL | sfx_001 (overlay 6s) | sfx_001 arrive APRES seg_000 (le cold open vocal). Le cold open lui-meme n'a pas de SFX. Il manque un insert ou overlay pour habiller l'accroche "Devinez combien d'etoiles...". |
| 2. Salon arrivee | FAIBLE | sfx_001 (overlay 6s) | Un seul overlay de 6s pour toute la scene du salon (11 segments). Tres insuffisant. Il faudrait un overlay long (15-20s) ou un second overlay pour couvrir la scene d'exposition. |
| 3. Lieux bibliques | OK | sfx_002 (Mesopotamie), sfx_004 (caravane), sfx_013+sfx_015 (Canaan aride), sfx_005 (nuit etoilee), sfx_011 (campement) | 5 ambiances distinctes. Bon travail de localisation. |
| 4. Tension/conflit | FAIBLE | sfx_003 (appel divin) | Un seul SFX pour l'appel de Dieu. La famine (seg_021b-021g), moment de crise majeur, n'a aucun SFX. |
| 5. Emotion centrale | OK | sfx_005 (etoiles) + sfx_006 (naissance Isaac) | La scene des etoiles est le climax. sfx_005 fournit l'ambiance nocturne. sfx_006 (harpe) marque la naissance d'Isaac. |
| 6. Transitions salon-recit | PARTIEL | sfx_002 (salon→recit) + sfx_009 (recit→salon) | Transition entree dans le recit OK. Pas de transition explicite pour le retour au salon — sfx_009 fait office de transition implicite. |
| 7. Recap/morale | OK | sfx_010 (cello) + sfx_007 (pad resolution) | Morale bien habillée avec cello + resolution harmonique. |
| 8. Teasing + Au revoir | OK | sfx_012 (shimmer pad) + sfx_008 (outro oud) | Teasing couvert. Outro au oud = coherence MO. |

---

### A. Conformite technique (Volet A)

| # | Regle | Resultat | Detail |
|---|-------|----------|--------|
| R1 | Pas de descriptions visuelles | OK | Aucun "light", "bright", "dark", "color", "radiant". "evoking a desert landscape" dans sfx_002 est limite — "evoking" est un verbe d'evocation visuelle. **Alerte mineure.** |
| R2 | Sons texturaux, pas abstraits | OK | Tous les prompts decrivent des sons concrets : drones, pads, bells, crackling, footsteps, wind. |
| R3 | Non-intrusif | OK | Tous qualifies de "soft", "gentle", "subtle". Coherent avec l'ambiance "calme". |
| R4 | Durees coherentes | OK | Overlays 4-6s, inserts 4-5s. Coherent. Mais les overlays salon sont courts (6s pour sfx_001 — devrait etre 15-20s pour couvrir la scene). |
| R5 | Pas de voix/chant | OK | "melody" dans sfx_008 refere a l'oud (instrument). Pas de risque de parole. |
| R6 | Pas de "silence" | OK | sfx_014 contient "reverent stillness" — "stillness" n'est pas "silence" mais c'est proche. **Alerte mineure.** |
| R7 | Pas de contradiction spatiale | OK | Cheminee au salon, desert au recit, nuit aux etoiles. Coherence respectee. sfx_013 et sfx_015 sont dos-a-dos (meme scene aride) sans contradiction. |
| R8 | Vocabulaire audio | OK | Frequences (sub-bass, low-frequency, high-frequency, mid-frequency), instruments (harp, cello, oud, camel bells), textures (drone, pad, shimmer, swell, reverb, crackling, rustling), actions (gusting, howling, fading, twinkling). Vocabulaire riche et specifique. |
| R9 | Pas de "birds singing" | OK | Aucune occurrence. "cricket ambiance" (sfx_005) est correct. |
| R10 | Pas de sensoriel non-auditif | OK | "warm" utilise comme qualificatif tonal (warm room tone, warm reverb, warm harmonic). "sandy footsteps" = auditif. "hot arid wind" dans sfx_013 — "hot" est thermique. **Alerte mineure.** |

**Resultat Volet A : 0 violation bloquante. 3 alertes mineures (R1 "evoking", R6 "stillness", R10 "hot"). Score : 9/10.**

---

### B. Qualite creative (Volet B)

| Axe | Note /10 | Commentaire |
|-----|----------|-------------|
| B1. Couverture sonore | 6.5/10 | 4 trous de plus de 6 segments voix consecutifs. Le plus grave : 11 segments nus dans la scene du salon (exposition). La section famine (9 segments) est un moment dramatique cle laisse sans habillage sonore. La scene des etoiles + Mamie Sonia (8 segments) meritait au moins un overlay long. Seule la deuxieme moitie de l'episode (pos 58+) est bien couverte. Desequilibre net premiere/deuxieme moitie. |
| B2. Densite et variete | 8.5/10 | Ratio 23.4% = pile dans la cible 20-25%. Variete correcte : drones, pads, nature (crickets, wind, camel bells), instruments (harp, cello, oud), impacts (thunder). 10 overlays pour 64 voix est bon. Le probleme n'est pas le nombre total mais la repartition (cf. B1). sfx_013 et sfx_015 sont dos-a-dos et thematiquement proches (vent aride + vent desole) — risque de redondance perceptive. |
| B3. Transitions et immersion | 7/10 | Transition salon→recit via sfx_002 fonctionne bien. Pas de transition explicite recit→salon. Le retour au salon (sfx_009) est implicite. Les 4 trous cassent l'immersion — l'auditeur "sort" du monde sonore pendant les sections nues. sfx_013 et sfx_015 consecutifs sans segment voix entre eux creent un doublon, pas une transition. La scene de l'appel de Dieu (sfx_003) est bien isolee par un insert solennel. |
| B4. Emotion et arc narratif sonore | 7.5/10 | L'arc est present mais inegal. Progression : cheminee (confort) → desert (depart) → aridite (epreuve) → etoiles (promesse) → harpe (joie) → cello (reflexion) → oud (cloture). C'est le bon schema. MAIS : la famine (moment de crise) n'a aucun SFX — le nadir emotionnel est soniquement vide. La scene des etoiles (climax) a sfx_005 mais c'est un overlay de 6s pour un moment qui devrait etre le plus riche de l'episode. Pas d'insert "revelation" ou "emerveillement" a ce point precis. La naissance d'Isaac (sfx_006 harpe) est bien marquee. |
| B5. Qualite des prompts | 8.5/10 | Prompts entre 10 et 20 mots — fourchette correcte. Specificite variable : sfx_001 est excellent (4 couches detaillees), sfx_005 est bon (cricket + shimmer + stereo). Mais sfx_013 "hot arid wind gusting over sandy terrain, distant dry grass rustling, sparse desert landscape" contient "hot" (thermique, R10) et "landscape" (visuel implicite). sfx_015 "dry desolate wind howling over cracked earth" — "cracked earth" est visuel. Quelques prompts pourraient etre plus specifiques en frequences/textures. |
| **Moyenne experience sonore** | **7.6/10** | |

---

### Corrections a appliquer

#### P0 — Corrections techniques (bloquantes)

1. **sfx_013** : Remplacer "hot arid wind" par "harsh dry wind" et supprimer "sparse desert landscape" (visuel).
   - Avant : `"Hot arid wind gusting over sandy terrain, distant dry grass rustling, sparse desert landscape with wide open stereo field"`
   - Apres : `"Harsh dry wind gusting with grainy sand texture, distant dry grass rustling, wide open stereo field"`

2. **sfx_015** : Remplacer "cracked earth" par un descripteur auditif.
   - Avant : `"Dry desolate wind howling over cracked earth, distant low rumble of empty landscape, sparse dust movement, bleak atmosphere"`
   - Apres : `"Dry desolate wind howling with low ground-level rumble, distant hollow resonance, sparse dust-like granular texture, bleak atmosphere"`

3. **sfx_002** : Supprimer "evoking a desert landscape" (evocation visuelle).
   - Avant : `"Warm Middle Eastern string drone with soft wind layer, evoking a desert landscape, gentle reverb tail"`
   - Apres : `"Warm Middle Eastern string drone with soft wind layer, gentle reverb tail, wide stereo spread"`

4. **sfx_014** : Remplacer "reverent stillness" par un descripteur sonore.
   - Avant : `"Soft distant thunder rumble fading into reverent stillness, gentle low-pitched resonance settling, wide stereo atmosphere"`
   - Apres : `"Soft distant thunder rumble with slow decay, gentle low-pitched resonance settling into near-silence, wide stereo atmosphere"`

#### P1 — SFX a ajouter (couverture — haute priorite)

1. **AJOUTER sfx_001b** (salon long overlay) : Inserer apres sfx_001 (pos 1). Overlay 15s pour couvrir la scene d'exposition du salon.
   - Prompt : `"Crackling fireplace with gentle ember pops, soft fabric rustling, distant wall clock ticking slowly, warm analog room tone, cozy interior ambiance"`
   - Mode : overlay, duree : 15s
   - Justification : Comble le trou de 11 segments. Le salon doit etre immersif des le debut.

2. **AJOUTER sfx_000** (cold open insert) : Inserer AVANT seg_000 (position 0). Insert 3s d'accroche.
   - Prompt : `"Deep resonant low-frequency drone building from silence, gentle high-pitched crystalline shimmer fading in, mysterious and inviting"`
   - Mode : insert, duree : 3s
   - Justification : Le cold open "Devinez combien d'etoiles..." n'a aucun habillage. Un drone mysterieux cree l'attente.

3. **AJOUTER sfx_004b** (voyage desert overlay long) : Inserer entre seg_018c et seg_018d (dans le trou de 7 segments du voyage).
   - Prompt : `"Sustained low-frequency desert wind drone with soft sandy granular texture, distant camel groan, slow rhythmic footstep pattern in sand"`
   - Mode : overlay, duree : 12s
   - Justification : Le recit du voyage de 2000 km (seg_018c-018e) doit etre habille. Ce trou couvre le moment "GPS des etoiles".

4. **AJOUTER sfx_famine** (famine/epreuve) : Inserer avant seg_021b (debut de la famine).
   - Prompt : `"Low ominous sustained drone with dry crackling texture, sparse hollow wind gusts, desolate and tense atmosphere building slowly"`
   - Mode : overlay, duree : 10s
   - Justification : La famine est le nadir emotionnel de l'episode. 9 segments sans SFX a cet endroit est un manque majeur. L'overlay doit couvrir seg_021b a seg_021g.

5. **AJOUTER sfx_005b** (scene etoiles — renfort climax) : Inserer juste apres sfx_005 ou avant seg_027.
   - Prompt : `"Gentle ascending chime arpeggio with wide reverb bloom, ethereal high-register shimmer, sense of vastness and wonder"`
   - Mode : insert, duree : 3s
   - Justification : La scene des etoiles est LE climax de l'episode. sfx_005 (ambiance cricket) pose le decor mais il manque un insert "revelation" quand Dieu dit "ta descendance sera aussi nombreuse que les etoiles".

6. **SUPPRIMER sfx_015** ou fusionner avec sfx_013 : Les deux sont des overlays vent aride places dos-a-dos (positions 32-33) sans segment voix entre eux. Redondance. Garder sfx_013 (plus specifique) et supprimer sfx_015, ou fusionner les prompts.

#### P2 — Ameliorations creatives (optionnelles)

1. **sfx_001 duree** : Passer de 6s a 15-20s. Un overlay salon de 6s est trop court pour etre percu comme ambiance continue.

2. **sfx_005 duree** : Passer de 6s a 10-12s. La scene des etoiles (climax) merite un overlay plus long pour couvrir les 3-4 segments de dialogue.

3. **Transition retour salon** : Ajouter un insert chime ou tintement entre la section biblique et le retour au salon (autour de seg_041, arrivee de Mamie Sonia). Actuellement, la transition est implicite.

#### P3 — Suggestions cosmetiques

1. sfx_005 "twinkling high-frequency shimmer pads evoking starlight" — "evoking starlight" est visuel. Remplacer par "twinkling high-frequency shimmer pads with crystalline overtones".
2. Numerotation des SFX desordonnee (sfx_013, sfx_014, sfx_015 ne suivent pas l'ordre de la timeline). Renumeroter pour lisibilite.

---

### Score global

| Dimension | Note |
|-----------|------|
| A. Conformite technique | 9/10 (3 alertes mineures) |
| B1. Couverture sonore | 6.5/10 |
| B2. Densite et variete | 8.5/10 |
| B3. Transitions et immersion | 7/10 |
| B4. Emotion et arc narratif sonore | 7.5/10 |
| B5. Qualite des prompts | 8.5/10 |
| **Score global** | **7.8/10** |

**Calcul** : (9 + 6.5 + 8.5 + 7 + 7.5 + 8.5) / 6 = 47 / 6 = 7.83 → **7.8/10**

---

### Verdict : retravailler

Le score de **7.8/10** est en dessous du seuil de 9.0/10. Deux axes sont sous 8.0 (B1 Couverture a 6.5 et B3 Transitions a 7.0). Le probleme principal est structurel : la premiere moitie de l'episode est sous-habilee avec 4 trous de 7 a 11 segments voix consecutifs sans SFX.

**Problemes bloquants :**
- 4 trous sonores majeurs (>6 segments) dont 1 de 11 segments dans l'exposition du salon
- La scene de la famine (nadir emotionnel) n'a aucun habillage sonore
- La scene des etoiles (climax) est sous-habilee (1 overlay de 6s)
- Pas de SFX en cold open
- 2 SFX vent aride consecutifs redondants (sfx_013 + sfx_015)
- 3 alertes de vocabulaire (R1, R6, R10) dans les prompts

**Pour atteindre 9.0/10 :**
1. Appliquer les 4 corrections P0 (vocabulaire des prompts)
2. Ajouter les 5-6 SFX P1 (cold open, salon long, desert voyage, famine, climax etoiles)
3. Supprimer ou fusionner le doublon sfx_013/sfx_015
4. Allonger sfx_001 et sfx_005
5. Ajouter une transition explicite retour au salon

Apres ces corrections, le score devrait passer a 9.0-9.2/10 avec une couverture homogene et un arc sonore complet.

---
*Thomas Lavigne — Sound Designer*
*Audit v3 — 2026-03-23*
