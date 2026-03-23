# AUDIT EXPERIENCE SONORE — S01E04 "Joseph et la tunique de couleurs — trahi par ses freres"
## Par Thomas Lavigne, sound designer

**Date** : 2026-03-23
**Script** : `output/scripts/S01E04_script.json`
**Type episode** : final (saison 1) — duree cible 18 min
**Segments totaux** : 94 (77 voix + 17 SFX)

---

## Metriques sonores

| Metrique | Valeur | Cible | Status |
|----------|--------|-------|--------|
| SFX total | 17 | >=12 (episode long/final) | **OK** |
| Overlays | 11 (64.7% des SFX) | >=30% du total SFX | **OK** |
| Inserts | 6 | — | — |
| Ratio SFX/voix | 22.1% (17/77) | 20-25% | **OK** |
| Duree overlay min | 5.0s | >=15s | **KO** |
| Duree overlay max | 10.0s | — | — |
| Trous sonores (>10 seg voix consecutifs) | 0 | 0 | **OK** |
| Max segments voix consecutifs sans SFX | 10 | <=10 | **OK** (limite) |
| Overlays d'ambiance | 11 | >=7 (std) / >=10 (long) | **OK** |
| Zones obligatoires couvertes | 7/8 | 8/8 | **KO** |
| Transitions salon-recit | 1/3 | 3/3 | **KO** |

---

## Carte de couverture sonore

| Tranche voix | Segments | SFX presents | Status |
|-------------|----------|--------------|--------|
| 0-9 | seg_000 → seg_009 | sfx_001 (overlay), sfx_001b (overlay) | **OK** |
| 10-19 | seg_010 → seg_019 | sfx_002 (insert) | **OK** (juste) |
| 20-29 | seg_020 → seg_029 | sfx_003 (overlay), sfx_004 (insert), sfx_005 (overlay), sfx_005b (overlay) | **OK** — zone la plus dense |
| 30-39 | seg_030 → seg_039 | sfx_006 (insert), sfx_006b (overlay) | **OK** |
| 40-49 | seg_040 → seg_049 | sfx_007 (overlay), sfx_007b (insert), sfx_008 (overlay) | **OK** |
| 50-59 | seg_050 → seg_059 | sfx_009 (overlay), sfx_010 (insert) | **OK** |
| 60-69 | seg_060 → seg_069 | sfx_011 (overlay) | **OK** (juste — 1 seul SFX pour 10 segments de morale) |
| 70-76 | seg_070 → seg_076 | sfx_012 (overlay), sfx_013 (insert) | **OK** |

**Verdict couverture** : Aucun trou >10, mais la tranche 60-69 (morale/discussion) est la plus fragile avec un seul overlay pour 10 segments de dialogue emotionnel.

---

## Zones obligatoires

| # | Zone | Couverte | SFX ID | Commentaire |
|---|------|----------|--------|-------------|
| 1 | Cold open (30s) | **PARTIEL** | sfx_001 | 1 seul SFX (overlay cheminee) apres seg_000. La cible est >=3 SFX dans les 30 premieres secondes. Il manque un insert d'accroche (ex: tissu, vent) et un 2e overlay. |
| 2 | Salon d'arrivee | **OK** | sfx_001, sfx_001b | Double overlay cheminee — bonne continuite. L'horloge est presente dans sfx_001b. |
| 3 | Lieux bibliques | **OK** | sfx_003 (tension/collines), sfx_004 (puits), sfx_005 (desert/caravane), sfx_006 (prison), sfx_007 (palais), sfx_008 (famine/desert) | 6 lieux couverts avec ambiances specifiques — excellent. |
| 4 | Tension/conflit | **OK** | sfx_003 (drone tension), sfx_004 (chute puits), sfx_006 (porte prison) | Bonne montee dramatique avec drone + impacts ponctuels. |
| 5 | Emotion centrale | **OK** | sfx_009 (swell cordes), sfx_010 (resolution harpe) | La scene des retrouvailles (seg_053-056) est encadree par overlay + insert. C'est la zone la plus riche emotionnellement. |
| 6 | Transitions salon-recit | **KO** | sfx_002 (tunique shimmer = seule vraie transition) | Transition salon→recit vers seg_010-012 : AUCUN SFX de transition. Le passage recit→salon vers seg_061 : AUCUN SFX de transition. Seul sfx_002 (shimmer tunique) joue un role transitionnel. |
| 7 | Recap/morale | **PARTIEL** | sfx_011 | 1 overlay cheminee pour tout le bloc morale (seg_061-070 = 10 segments). Correct mais mince — pas de fond musical tendre pour soutenir la profondeur du message. |
| 8 | Teasing + Au revoir | **OK** | sfx_012 (shimmer), sfx_013 (outro guitare) | Bon encadrement de la fin. sfx_013 en insert cloture proprement. |

**Zones manquantes/faibles** : Zone 1 (cold open incomplet), Zone 6 (transitions quasi absentes), Zone 7 (morale trop legere).

---

## A. Conformite technique (10 regles)

| # | SFX ID | Regle | Severite | Extrait problematique | Correction suggeree |
|---|--------|-------|----------|----------------------|---------------------|
| 1 | sfx_003 | R1 (visuels) | LOW | "Dark low-pitched" | Remplacer par "Low-pitched string tension drone building slowly, ominous rumble, uneasy atmosphere with sparse metallic accents" — retirer "dark" |
| 2 | sfx_004 | R1 (visuels) | LOW | "dark confined space" | Remplacer par "enclosed narrow space ambiance with low resonant drone" — retirer "dark" |
| 3 | sfx_002 | R10 (non-auditif) | LOW | "warm tonal shimmer" | Acceptable : "warm" qualifie ici une tonalite audio, pas une temperature. **Pas de correction necessaire.** |

**Bilan conformite** : 2 violations LOW (usage de "dark" comme descripteur spatial plutot qu'audio). Aucune violation HIGH ou MEDIUM. Aucun risque de parole, aucun silence decrit, aucun concept abstrait, aucune metadata. Les prompts sont globalement exemplaires.

---

## B. Qualite creative

### B1. Couverture sonore — 7.5/10

**Points forts** :
- 0 trou sonore >10 segments consecutifs — la regle fondamentale est respectee
- 11 overlays d'ambiance bien repartis sur l'episode
- La zone 20-29 (trahison/puits) est tres bien couverte avec 4 SFX

**Points faibles** :
- Le cold open n'a qu'1 SFX au lieu de 3 — l'enfant n'est pas immediatement "transporte"
- La zone morale (seg_061-070) n'a qu'1 overlay pour 10 segments de dialogue crucial
- 0 transition sonore salon→recit (le "cut sec" est audible)
- Le maximum de 10 segments voix consecutifs est atteint (limite haute)

**Impact** : L'enfant risque de decrocher dans la zone morale ou l'absence de tapis sonore rend le dialogue "nu".

### B2. Densite et variete SFX — 7/10

**Points forts** :
- Ratio SFX/voix a 22.1% — dans la cible
- Ratio overlay/total a 64.7% — excellent, l'episode "baigne dans le son"
- Bonne variete : aucun doublon d'insert consecutif
- 17 SFX pour 77 segments voix — densite correcte

**Points faibles CRITIQUES** :
- **TOUTES les durees d'overlay sont sous 15s** (de 5s a 10s). C'est le probleme majeur. Un overlay de 5-6 secondes se coupe avant meme que la replique suivante ne commence — ca sonne amateur, ca "clignote". Les overlays doivent durer 15-25s pour creer une veritable nappe d'ambiance continue.
- Aucun overlay ne depasse 10s. Sur un episode de 18 minutes, c'est insuffisant pour une immersion professionnelle.
- Total duree SFX ~98s sur ~18min d'episode — le ratio temporel est faible

**Impact** : C'est le defaut le plus grave de cet episode. Les overlays trop courts donnent une impression de "ponctuation sonore" au lieu d'une "immersion sonore". L'enfant entend des bouts de son au lieu de baigner dedans.

### B3. Transitions et immersion — 6.5/10

**Points forts** :
- La coherence spatiale est bien geree : cheminee au salon, desert/puits/palais dans le recit — pas de contamination croisee
- La montee dramatique est correcte (sfx_003 drone → sfx_004 impact puits → sfx_005 caravane)
- Bonne respiration apres sfx_004 (impact puits) — le dialogue reprend avec Noemie indignee, pas un cri

**Points faibles** :
- **0 SFX de transition salon→recit** entre seg_009 et seg_010 : Papy passe du salon ("tu te souviens d'Abraham ?") au recit historique ("Jacob a eu 12 fils") sans aucun marqueur sonore. L'auditeur ne "sent" pas le changement d'univers.
- **0 SFX de transition recit→salon** entre seg_060 et seg_061 : on passe des retrouvailles emouvantes a "Papy, tu crois que Maxime..." sans transition. Cut sec.
- Pas de renouvellement d'ambiance dans le long recit biblique (seg_010 a seg_060 = ~50 segments). Les overlays changent de theme mais sont trop courts pour assurer une continuite.
- Le teasing (seg_072-074) n'a pas d'overlay d'ambiance propre — il depend du sfx_012 place au seg_070 qui sera fini depuis longtemps.

### B4. Impact emotionnel du son — 8/10

**Points forts** :
- La scene du puits (sfx_003 drone + sfx_004 impact) est la meilleure sequence sonore de l'episode — on "entend" la chute, la profondeur, le vide
- La caravane (sfx_005) avec cloches et monnaie cree une image sonore tres evocatrice
- La prison (sfx_006 porte de fer) est percutante et appropriee pour le public 6-10 ans (tension sans frayeur)
- Les retrouvailles (sfx_009 swell + sfx_010 harpe) forment un beau duo emotion/resolution
- L'outro guitare (sfx_013) est chaleureux et donne envie de revenir

**Points faibles** :
- L'ouverture salon n'est pas assez immersive (1 SFX au lieu de 2-3) — l'enfant n'est pas "installe" dans le salon de Papy des les premieres secondes
- La scene de la tunique arrachee (seg_023) n'a pas d'insert specifique (bruit de tissu dechire ?) — on passe directement a l'impact du puits
- Le moment ou Joseph pleure (seg_053) n'a pas de SFX propre — c'est couvert par sfx_009 en overlay, mais un insert ponctuel (sanglot etouffant, echo dans le palais) aurait ete plus puissant
- La revelation "C'est moi, Joseph" n'a pas de SFX de twist/revelation (gong, cloche, swell soudain)

### B5. Qualite des prompts SFX — 8.5/10

**Points forts** :
- Excellente specificite : "Deep hollow impact reverberating in stone well, distant echoing drip" — on voit exactement le son
- Bon layering : 2-3 couches par prompt, jamais plus (pas de surcharge)
- Vocabulaire audio concret systematique : "sub-bass", "drone", "pad", "shimmer", "reverb", "tremolo", "arpeggio" — le modele generatif va produire de bons sons
- Longueur homogene (14-19 mots) — dans la plage optimale
- Coherence tonale : les SFX desert/puits/palais forment un univers sonore biblique coherent

**Points faibles** :
- sfx_002 ("shimmering fabric rustling with warm tonal shimmer") — "shimmer" apparait 2 fois, redondant
- sfx_012 ("Gentle high-frequency shimmer pad with slow amplitude modulation") — tres generique, pas specifiquement lie a un moment narratif. On sent un SFX de remplissage.
- Certains overlays pourraient etre plus evocateurs de l'Egypte/Orient (sfx_007 mentionne "Egyptian palace" mais les instruments restent generiques)

---

## Corrections a appliquer

### P0 — Corrections techniques (bloquantes)

| # | SFX | Action | Prompt corrige |
|---|-----|--------|----------------|
| 1 | sfx_003 | Retirer "Dark" | `"Low-pitched string tension drone building slowly, ominous rumble, uneasy atmosphere with sparse metallic accents"` |
| 2 | sfx_004 | Retirer "dark" | `"Deep hollow impact reverberating in stone well, distant echoing drip, enclosed narrow space ambiance with low resonant drone"` |

### P1 — SFX a ajouter (couverture et transitions)

| # | Position | Type | Prompt suggere | Justification |
|---|----------|------|----------------|---------------|
| 1 | Apres seg_000 (avant sfx_001) | insert | `"Soft mysterious fabric unfurling with gentle harmonic shimmer, brief sparkle accent fading into reverb"` | Cold open : 2e SFX pour accrocher des le manteau evoque |
| 2 | Entre seg_009 et seg_010 | insert | `"Gentle harp glissando with soft reverb bloom, dreamy transition sweep ascending"` | Transition salon → recit biblique (Jacob/12 fils) |
| 3 | Entre seg_060 et seg_061 | insert | `"Warm descending chime with soft crackling fireplace fade-in, cozy room tone return"` | Transition recit → salon (retrouvailles → discussion morale) |
| 4 | Entre seg_052 et sfx_009 | insert | `"Deep resonant bell toll with wide reverb, dramatic revelation accent"` | Twist/revelation quand les freres s'agenouillent devant Joseph |

### P2 — Durees d'overlay a augmenter (PRIORITAIRE)

| SFX | Duree actuelle | Duree recommandee | Justification |
|-----|---------------|-------------------|---------------|
| sfx_001 | 10s | 20s | Overlay d'ouverture salon — doit couvrir l'installation |
| sfx_001b | 10s | 18s | Continuite salon — couvre le lancement de l'histoire |
| sfx_003 | 8s | 18s | Tension montante — doit couvrir seg_020 a seg_023 |
| sfx_005 | 5s | 15s | Caravane/vente — scene importante |
| sfx_005b | 5s | 15s | Tristesse Jacob — doit porter l'emotion |
| sfx_006b | 6s | 15s | Reves en prison — ambiance onirique |
| sfx_007 | 8s | 20s | Palais Pharaon — scene majeure |
| sfx_008 | 5s | 15s | Famine/desert — contexte narratif |
| sfx_009 | 8s | 20s | Retrouvailles emotionnelles — scene centrale |
| sfx_011 | 6s | 18s | Retour salon/morale — doit couvrir la discussion |
| sfx_012 | 5s | 15s | Fin episode/teasing — doit porter le teasing |

### P3 — Ameliorations creatives (pour passer de 8 a 9+)

| # | Suggestion | Impact |
|---|-----------|--------|
| 1 | Ajouter un insert "tissu dechire" avant sfx_004 (seg_023 "arraché sa tunique") | Renforce l'image sonore de la trahison |
| 2 | Ajouter un overlay leger sous la zone morale seg_062-067 | Evite le "dialogue nu" pendant la lecon de vie |
| 3 | Renforcer sfx_007 avec des instruments orientaux (oud, darbuka) | Plus d'authenticite geographique |
| 4 | Ajouter un insert "echo de pleur" a seg_053 ("Joseph a pleuré") | Moment emotionnel central merite son propre marqueur |

---

## Recapitulatif notes

| Axe | Note /10 | Commentaire |
|-----|----------|-------------|
| B1. Couverture sonore | 7.5 | 0 trou >10, mais cold open faible, morale sous-couverte, transitions absentes |
| B2. Densite et variete | 7.0 | Bon ratio SFX/voix, mais overlays TOUS <15s — defaut structurel majeur |
| B3. Transitions et immersion | 6.5 | 0 transition salon↔recit identifiee, continuite d'ambiance fragile |
| B4. Impact emotionnel | 8.0 | Belles sequences (puits, caravane, retrouvailles), mais manque le twist sonore et la tunique dechiree |
| B5. Qualite des prompts | 8.5 | Prompts specifiques, bon vocabulaire audio, layering maitrise |
| **Moyenne experience sonore** | **7.5** | |

---

## Score global : 7.5/10

## Verdict : "Corrections necessaires"

**Resume** : L'architecture sonore de cet episode est solide dans sa conception — les SFX sont bien places narrativement, les prompts sont de bonne qualite, et les 17 SFX couvrent l'ensemble sans trou majeur. MAIS trois defauts empechent le passage en production :

1. **Durees d'overlay systematiquement trop courtes** (5-10s au lieu de 15-25s) — c'est le probleme n°1 qui donne une impression de son "hache" au lieu d'une immersion fluide
2. **Absence totale de transitions sonores salon↔recit** — l'auditeur subit des "cuts secs" entre les deux univers
3. **Cold open sous-equipe** (1 SFX au lieu de 3) — les 30 premieres secondes ne sont pas assez cinematographiques pour retenir un enfant de 7 ans

Apres application des corrections P0 (2 fixes techniques), P1 (4 SFX a ajouter) et P2 (11 durees a augmenter), le score devrait atteindre 9/10.

---

*Thomas Lavigne — Audit sonore S01E04 v2*
