# Audit SFX -- S01E03 "Abraham -- celui qui a tout quitte par confiance"

**Auditeur** : Thomas Lavigne, sound designer
**Date** : 2026-03-23
**Source** : donnees script (47 segments voix, 8 SFX)

---

## A. Conformite technique -- 10 regles

| # | Regle | Statut | Commentaire |
|---|-------|--------|-------------|
| R1 | Pas de reference visuelle (couleurs, lumiere, images) | OK | Aucun prompt ne contient de terme visuel. |
| R2 | Sons abstraits et texturaux, pas de sons figuratifs narratifs | OK | Les prompts restent dans le registre textural (drones, pads, shimmers, ambiances). |
| R3 | Silencieux / non-intrusif (pas de volume fort, pas de hits) | OK | Tous les prompts utilisent "soft", "gentle", "subtle". Aucun hit, impact ou element fort. |
| R4 | Respect du montage (durees 4-6s coherentes) | OK | 4s (x3), 5s (x2), 6s (x2), 5s (x1). Fourchette 4-6s respectee. |
| R5 | Pas de parole, voix, chant, choeur | OK | Aucun prompt ne mentionne de voix ou chant. |
| R6 | Pas de silence decrit ("silence", "quiet") | OK | Aucune occurrence de "silence" ou "quiet" dans les prompts. |
| R7 | Pas de contradiction spatiale (indoor/outdoor incoherent) | WARN | sfx_001 melange "fireplace" (interieur) et "bird chirps" (exterieur). Contradiction spatiale legere. |
| R8 | Vocabulaire audio correct (pas de termes visuels deguises) | OK | Terminologie audio coherente (drone, pad, reverb, shimmer, sustain, decay). |
| R9 | Pas de "birds singing" (interdit, "bird chirps" tolere) | OK | sfx_001 utilise "bird chirps", pas "birds singing". Conforme. |
| R10 | Pas de description sensorielle non-auditive (odeur, toucher, gout) | OK | Aucune reference non-auditive. |

**Resultat** : 9/10 regles OK, 1 WARN (R7 -- sfx_001 contradiction spatiale mineure).

---

## B. Qualite creative -- Notes /10

### B1. Couverture (repartition des SFX sur la timeline) -- 4/10

**Probleme majeur.** La couverture est tres inegale. Trois zones critiques :

- **seg_019 a seg_024** : 6 segments voix consecutifs sans aucun SFX a proximite.
- **seg_028 a seg_035** : 8 segments voix consecutifs sans SFX. Zone desertique.
- **seg_037 a seg_046** : 10 segments voix consecutifs sans SFX. Plus long trou de l'episode.
- **seg_048 a seg_054** : 7 segments voix consecutifs sans SFX.

Au total, environ 31 segments sur 47 (66%) se trouvent dans des zones sans habillage sonore. Le premier tiers de l'episode est correctement couvert, mais les deux derniers tiers sont quasi nus.

### B2. Densite (ratio SFX/voix) -- 5/10

- Ratio actuel : 8/47 = 17%.
- Cible : 20-25%, soit 10-12 SFX.
- Il manque 3 a 5 SFX pour atteindre la cible basse.
- Le ratio overlay/insert (50/50) est equilibre, ce qui est positif.

### B3. Transitions (fluidite entre segments) -- 5/10

- Les overlays (sfx_001, sfx_002, sfx_004, sfx_005) assurent de bonnes transitions dans le premier tiers.
- Les inserts (sfx_003, sfx_006, sfx_007, sfx_008) marquent bien les respirations narratives.
- Mais l'absence de SFX dans les trous identifies cree des ruptures seches, notamment entre seg_025 et seg_036 (transition tres abrupte du desert nocturne vers la harpe).

### B4. Emotion et arc narratif sonore -- 5/10

- L'arc sonore commence bien : feu de cheminee intime -> drone moyen-oriental -> sub-bass divin -> caravane -> nuit etoilee. Belle progression.
- Apres seg_025, l'arc s'effondre. La harpe (sfx_006) arrive trop tard et isolee. Le pad orchestral de fin (sfx_007) et la guitare (sfx_008) sont de bons choix mais flottent sans contexte sonore.
- L'episode manque d'un climax sonore identifiable dans le deuxieme tiers.

### B5. Qualite des prompts -- 7/10

- Les prompts sont bien rediges techniquement : descriptifs, multi-couches, avec des indications de spatialisation ("wide stereo field", "wide stereo reverb").
- Bon usage des termes de production (legato, sustain, decay, reverb tail, reverb bloom).
- Points d'amelioration : certains prompts pourraient preciser le registre frequentiel ou le tempo de maniere plus precise (BPM).
- sfx_001 gagnerait a etre debarrasse de la contradiction spatiale.

**Moyenne B : 5.2/10**

---

## C. Corrections

### P0 -- Critiques (trous > 8 segments)

#### P0-1 : Trou seg_037 a seg_046 (10 segments sans SFX)

C'est le plus long desert sonore de l'episode. Cette zone correspond probablement a un moment narratif important (promesse, epreuve ou enseignement d'Abraham).

**Action : Ajouter 2 SFX**

**SFX a ajouter -- sfx_009** (overlay, 6s) apres seg_040 :
```
Warm low-frequency pad drone with gentle breath-like modulation, slow evolving texture, subtle room tone warmth, mono-compatible stereo width
```

**SFX a ajouter -- sfx_010** (insert, 4s) apres seg_044 :
```
Soft sustained cello harmonic with gentle reverb bloom, single note fading slowly, warm mid-frequency resonance
```

#### P0-2 : Trou seg_028 a seg_035 (8 segments sans SFX)

**Action : Ajouter 1 SFX**

**SFX a ajouter -- sfx_011** (overlay, 5s) apres seg_031 :
```
Soft arid wind ambiance with distant low-pitched drone, subtle sand texture movement, gentle stereo panning, warm analog pad undertone
```

---

### P1 -- Importants (trous 5-7 segments)

#### P1-1 : Trou seg_048 a seg_054 (7 segments sans SFX)

Zone de conclusion avant le SFX de fin (sfx_008). Trop long sans habillage.

**Action : Ajouter 1 SFX**

**SFX a ajouter -- sfx_012** (overlay, 5s) apres seg_051 :
```
Gentle high-frequency shimmer pad with slow amplitude modulation, soft reverb wash, warm harmonic overtones, wide stereo field
```

#### P1-2 : Trou seg_019 a seg_024 (6 segments sans SFX)

Zone intermediaire entre la caravane (sfx_004) et la nuit etoilee (sfx_005). Manque de continuite.

**Action : Ajouter 1 SFX**

**SFX a ajouter -- sfx_013** (overlay, 5s) apres seg_021 :
```
Soft distant wind whisper with gentle low-frequency rumble, subtle dust movement texture, slow evolving stereo ambiance
```

---

### P2 -- Mineurs (ameliorations qualitatives)

#### P2-1 : sfx_001 -- Contradiction spatiale (R7)

**Action : Corriger le prompt**

Prompt actuel :
```
Crackling fireplace ambiance with soft bird chirps in background, low-frequency pad drone, subtle room tone
```

Prompt corrige :
```
Crackling fireplace ambiance with low-frequency pad drone, subtle room tone warmth, gentle ember pops, soft analog hiss undertone
```

Retrait des "bird chirps" qui contredisent l'ambiance interieure du feu de cheminee.

#### P2-2 : Trou seg_014 a seg_017 (4 segments sans SFX)

Zone courte mais qui beneficierait d'un habillage leger.

**Action : Ajouter 1 SFX (optionnel)**

**SFX a ajouter -- sfx_014** (overlay, 4s) apres seg_015 :
```
Subtle low-frequency drone with gentle analog warmth, soft room tone ambiance, slow stereo movement, minimal texture
```

---

## Synthese des corrections

| Priorite | Action | Position | Type | Duree |
|----------|--------|----------|------|-------|
| P0-1a | Ajouter sfx_009 | apres seg_040 | overlay | 6s |
| P0-1b | Ajouter sfx_010 | apres seg_044 | insert | 4s |
| P0-2 | Ajouter sfx_011 | apres seg_031 | overlay | 5s |
| P1-1 | Ajouter sfx_012 | apres seg_051 | overlay | 5s |
| P1-2 | Ajouter sfx_013 | apres seg_021 | overlay | 5s |
| P2-1 | Corriger sfx_001 | position inchangee | overlay | 6s |
| P2-2 | Ajouter sfx_014 (opt.) | apres seg_015 | overlay | 4s |

**Apres corrections P0+P1** : 13 SFX / 47 segments = 28% (dans la cible haute).
**Apres toutes corrections** : 14 SFX / 47 segments = 30% (au-dessus de la cible, acceptable car les overlays restent subtils).

Ratio overlay apres corrections P0+P1 : 8 overlays / 13 SFX = 62% (acceptable, les overlays couvrent plus de surface).

---

## Score final

| Critere | Note |
|---------|------|
| B1. Couverture | 4/10 |
| B2. Densite | 5/10 |
| B3. Transitions | 5/10 |
| B4. Emotion / arc | 5/10 |
| B5. Qualite prompts | 7/10 |
| **Moyenne** | **5.2/10** |

**Verdict** : L'habillage sonore du premier tiers est soigne et bien pense. L'arc sonore initial (feu -> Moyen-Orient -> divin -> caravane -> etoiles) est excellent. Mais l'episode s'effondre sonorement apres seg_025. Les corrections P0 sont indispensables avant publication. Apres application des 5 SFX P0+P1, la note estimee passerait a environ 7.5/10.

---

*Thomas Lavigne -- Sound Design Audit*
*Episode S01E03 -- Mars 2026*
