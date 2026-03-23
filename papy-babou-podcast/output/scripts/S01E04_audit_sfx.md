# Audit SFX — S01E04 "Joseph et la tunique de couleurs"

**Auditeur** : Thomas Lavigne — Ingénieur son & sound designer
**Date** : 2026-03-23
**Cible qualité** : 9/10 minimum

---

## 1. Métriques sonores

| Métrique | Valeur | Cible | Statut |
|----------|--------|-------|--------|
| Segments totaux | 90 | — | — |
| Segments voix | 77 | — | — |
| Segments SFX | 13 | — | — |
| Overlays | 8 | min 7 | OK |
| Inserts | 5 | — | OK |
| Ratio overlay/SFX | 61.5% | >= 30% | OK |
| Durée totale SFX | 64.0s | — | — |
| Durée overlays | 42.0s | >= 15s | OK |
| Ratio SFX/voix | 16.9% | 20-25% | INSUFFISANT |
| Max voix consécutifs sans SFX | 13 | max 10 | VIOLATION |
| Longueur moy. prompts (mots) | ~14 | 8-30 | OK |

---

## 2. Carte de couverture (par tranche de 10 segments)

| Bloc | Segments | Voix | SFX | Densité | Verdict |
|------|----------|------|-----|---------|---------|
| 1 | seg_000 → seg_008 | 9 | 1 (sfx_001) | Faible | OK — ouverture couverte |
| 2 | seg_009 → seg_017 | 9 | 1 (sfx_002) | Faible | ATTENTION — 13 voix consec. (seg_001→seg_013) |
| 3 | seg_018 → seg_025 | 8 | 2 (sfx_003, sfx_004) | Correct | OK — tension + puits |
| 4 | seg_026 → seg_033 | 8 | 2 (sfx_005, sfx_006) | Correct | OK — caravane + prison |
| 5 | seg_034 → seg_042 | 9 | 1 (sfx_007) | Faible | ATTENTION — 8 voix consec. (seg_033→seg_040) |
| 6 | seg_043 → seg_051 | 9 | 1 (sfx_008) | Faible | ATTENTION — zone Pharaon sous-sonorisée |
| 7 | seg_052 → seg_059 | 8 | 2 (sfx_009, sfx_010) | Correct | OK — émotion + réconciliation |
| 8 | seg_060 → seg_068 | 9 | 1 (sfx_011) | Faible | ATTENTION — retour salon sous-sonorisé |
| 9 | seg_069 → sfx_013 | 8 | 2 (sfx_012, sfx_013) | Correct | OK — fermeture couverte |

---

## 3. Zones obligatoires (8/8)

| Zone | Attendue | SFX présent | Statut |
|------|----------|-------------|--------|
| 1. Ouverture immersive | Ambiance salon | sfx_001 — fireplace overlay 6s | OK |
| 2. Transition salon → récit | Bascule monde biblique | sfx_002 — tissu/shimmer insert 4s | OK |
| 3. Montée de tension | Jalousie des frères | sfx_003 — drone tension overlay 5s | OK |
| 4. Climax dramatique | Puits + trahison | sfx_004 — impact puits insert 4s | OK |
| 5. Voyage/dépaysement | Caravane marchands | sfx_005 — caravane overlay 5s | OK |
| 6. Point bas émotionnel | Prison de Joseph | sfx_006 — porte prison insert 4s | OK |
| 7. Retournement positif | Palais Pharaon | sfx_007 — fanfare palais overlay 5s | OK |
| 8. Fermeture/outro | Retour salon + clôture | sfx_011 + sfx_013 — fireplace + outro | OK |

**Résultat : 8/8** — Toutes les zones obligatoires sont couvertes.

---

## 4. Conformité technique — Volet A (10 règles)

| # | Règle | Violations | Détail |
|---|-------|------------|--------|
| R1 | Pas de descriptions visuelles | 1 | sfx_002 : "bright and colorful feeling" — visuel, pas sonore |
| R2 | Pas de concepts abstraits | 0 | — |
| R3 | Pas d'événements silencieux | 0 | — |
| R4 | Pas de métadonnées de montage | 1 | sfx_011 : "returning softly" — métadonnée de retour scénique |
| R5 | Pas de risque de parole | 1 | sfx_005 : "muffled voices" — risque de parole humaine générée |
| R6 | Pas de silence décrit | 1 | sfx_006 : "lonely silence" — silence décrit |
| R7 | Pas de couches spatiales contradictoires | 0 | — |
| R8 | Vocabulaire audio concret | 0 | Bon niveau général : fréquences, instruments, textures |
| R9 | birds singing → chirping | 0 | Aucun oiseau dans cet épisode |
| R10 | Pas de sensoriel non-auditif | 3 | sfx_004 : "cold emptiness" (tactile) ; sfx_005 : "hot sandy atmosphere" (thermique/tactile) ; sfx_008 : "Hot arid wind... dry cracked earth, famine desolation" (thermique + visuel + abstrait) |

**Total violations : 6 sur 13 prompts** — 46% de prompts non conformes. C'est trop.

---

## 5. Qualité créative — Volet B

### B1. Couverture sonore — 6/10

- **Max voix consécutifs** : 13 (seg_001 → seg_013) — VIOLATION du seuil de 10.
- Seconde zone longue : 8 consécutifs (seg_033 → seg_040) — au seuil, pas de violation mais inconfortable.
- 8/8 zones obligatoires couvertes — bon point.
- 8 overlays, au-dessus du minimum de 7 — OK.
- **Problème majeur** : toute la phase d'installation (dialogue salon, rappel Abraham, présentation de Jacob) est un désert sonore de 13 segments. L'enfant n'a que la voix pendant plus de 2 minutes. Il faut un overlay d'ambiance salon prolongé ou un SFX ponctuel (horloge, craquement fauteuil).

### B2. Densité et variété — 6.5/10

- Ratio overlay 61.5% — OK (cible >= 30%).
- Durée overlays 42s — OK (cible >= 15s).
- **Ratio SFX/voix 16.9%** — en dessous de la fourchette 20-25%. Il manque 3-4 SFX pour atteindre le seuil minimal de 20%.
- Variété des textures : bonne palette (fireplace, cordes, percussion, vent, harpe, guitare).
- Durées trop uniformes : 11 SFX sur 13 entre 4-5s, seulement 2 a 6s. Pas assez de variation. Certains overlays d'ambiance devraient durer 8-12s pour habiller correctement une scène longue.

### B3. Transitions et immersion — 7/10

- Transition salon → récit : sfx_002 (shimmer tissu) — efficace et poétique.
- Transition récit → salon : sfx_011 (fireplace returning) — bonne idée, mais le prompt contient "returning" qui est une métadonnée, pas un son.
- Cohérence spatiale : globalement cohérente. Progression désert → puits → caravane → prison → palais → famine → réconciliation → salon. L'arc spatial tient.
- Montée dramatique : sfx_003 (drone tension) bien placé avant le climax. sfx_004 (impact puits) percutant.
- **Manque** : pas de SFX de transition entre la prison et le palais du Pharaon (sfx_006 → sfx_007 espacés de 8 segments voix). Le passage est trop sec.

### B4. Impact émotionnel — 7.5/10

- Ouverture immersive avec fireplace — classique et efficace.
- Scène du puits (sfx_004) — impact émotionnel fort, le "deep hollow impact" est bien pensé.
- Scène de réconciliation (sfx_009 + sfx_010) — duo cordes + harpe, très beau. Le moment émotionnel le plus riche de l'épisode.
- Scène de la caravane (sfx_005) — bonne ambiance de dépaysement malgré les violations R5/R10.
- **Manque** : la scène de la famine (sfx_008) est trop courte (5s) et mal placée pour un moment qui devrait être oppressant. La scène où Jacob pleure (seg_028-029) n'a aucun SFX — c'est un moment émotionnel fort laissé à nu.
- Adapté 6-10 ans : oui, pas de son effrayant, la tension reste dans l'atmosphère.

### B5. Qualité des prompts — 6.5/10

- **Spécificité** : bonne en général. Les prompts nomment des instruments (cello, harp, guitar), des fréquences (low-frequency, high-frequency), des textures (shimmer, reverb, drone).
- **Longueur** : 12-18 mots en moyenne — dans la fourchette 8-30. OK.
- **Layering** : la plupart des prompts ont 2-3 couches (fond + détail + atmosphère). Bon point.
- **Cohérence tonale** : globalement cohérente. Les prompts sombres sont pour les moments sombres.
- **Problèmes** : 6 violations techniques détaillées au Volet A. Trop de descripteurs sensoriels non-auditifs. Certains prompts sont plus "littéraires" qu'"audio" (ex: "famine desolation", "cold emptiness", "bright and colorful feeling").

---

## 6. Corrections

### P0 — Bloquantes (conformité technique)

| # | SFX | Problème | Correction proposée |
|---|-----|----------|---------------------|
| P0-1 | sfx_005 | R5 : "muffled voices" — risque de parole humaine | Remplacer par : `"Distant camel caravan bells with dry desert wind gusts, jingling metal coins, shuffling hooves on sand, sparse percussive accents"` |
| P0-2 | sfx_006 | R6 : "lonely silence" — silence décrit | Remplacer par : `"Heavy iron door slamming shut with deep metallic echo, distant dripping water in stone chamber, low resonant room tone"` |
| P0-3 | sfx_002 | R1 : "bright and colorful feeling" — visuel | Remplacer par : `"Soft shimmering fabric rustling with warm tonal shimmer, gentle high-register sparkle chimes, layered silk texture"` |
| P0-4 | sfx_008 | R10 : "Hot arid wind", "dry cracked earth", "famine desolation" — thermique + visuel + abstrait | Remplacer par : `"Sustained low-frequency wind drone with gritty sand texture, distant rumbling sub-bass, sparse hollow gusts, desolate empty reverb"` |
| P0-5 | sfx_004 | R10 : "cold emptiness" — tactile | Remplacer par : `"Deep hollow impact reverberating in stone well, distant echoing drip, dark confined space ambiance with low resonant drone"` |
| P0-6 | sfx_011 | R4 : "returning softly" — métadonnée montage | Remplacer par : `"Crackling fireplace with warm low-frequency room tone, gentle clock ticking, soft ember pops, cozy interior settling sounds"` |

### P1 — Couverture (zones manquantes)

| # | Position | Problème | SFX a ajouter |
|---|----------|----------|---------------|
| P1-1 | Apres seg_005 | 13 voix consecutifs — desert sonore installation salon | Ajouter overlay 8s : `"Soft crackling fireplace with gentle low-frequency hum, distant muffled outdoor wind, warm analog room tone, slow ticking clock"` |
| P1-2 | Apres seg_028 | Jacob pleure — moment emotionnel sans habillage | Ajouter overlay 5s : `"Soft sustained minor-key string pad with gentle tremolo, low cello drone, melancholic reverb wash, slow fading"` |
| P1-3 | Apres seg_037 | Super-pouvoir des reves — 8 voix consecutifs | Ajouter overlay 5s : `"Ethereal high-register synth pad with soft granular shimmer, slow pitch modulation, dreamy wide reverb, delicate chime accents"` |
| P1-4 | Apres seg_045 | Joseph nomme gouverneur — moment triomphal sans ponctuation | Ajouter insert 3s : `"Ascending brass fanfare stab with percussive accent, wide reverb tail, triumphant short motif resolving upward"` |

### P2 — Ameliorations (qualite creative)

| # | SFX | Amelioration |
|---|-----|-------------|
| P2-1 | sfx_003 | Allonger de 5s a 8s — le drone de tension doit couvrir tout seg_020 + seg_021 pour un effet d'oppression continue |
| P2-2 | sfx_007 | Allonger de 5s a 8s — l'ambiance palais merite plus de duree pour installer la grandeur |
| P2-3 | sfx_009 | Allonger de 5s a 8s — la montee emotionnelle des retrouvailles doit durer plus |
| P2-4 | sfx_001 | Allonger de 6s a 10s — l'ambiance d'ouverture salon doit habiller toute l'intro de Papy |
| P2-5 | sfx_013 | Allonger de 5s a 8s — l'outro doit avoir le temps de s'installer et fader proprement |
| P2-6 | Tous les overlays | Varier davantage les durees : alterner 5s / 8s / 12s selon l'importance narrative du moment |

---

## 7. Recapitulatif des notes

| Critere | Note | Commentaire |
|---------|------|-------------|
| B1. Couverture sonore | 6/10 | 13 voix consecutifs = violation ; 2 zones sous-sonorisees |
| B2. Densite et variete | 6.5/10 | Ratio SFX/voix 16.9% < 20% ; durees trop uniformes |
| B3. Transitions et immersion | 7/10 | Bonnes transitions salon/recit, manque entre prison et palais |
| B4. Impact emotionnel | 7.5/10 | Reconciliation excellente, Jacob qui pleure oublie |
| B5. Qualite des prompts | 6.5/10 | 6 violations techniques sur 13 prompts (46%) |
| **Conformite technique (Volet A)** | **5.5/10** | **6 violations sur 5 regles differentes** |

---

## 8. Score global

| Dimension | Poids | Note | Pondere |
|-----------|-------|------|---------|
| Conformite technique | 30% | 5.5 | 1.65 |
| Couverture (B1) | 20% | 6.0 | 1.20 |
| Densite/variete (B2) | 15% | 6.5 | 0.98 |
| Transitions (B3) | 10% | 7.0 | 0.70 |
| Impact emotionnel (B4) | 15% | 7.5 | 1.13 |
| Qualite prompts (B5) | 10% | 6.5 | 0.65 |
| **TOTAL** | **100%** | | **6.3/10** |

---

## 9. Verdict

### RETRAVAILLER — 6.3/10 (cible 9/10)

L'architecture sonore de cet episode est **structurellement correcte** : les 8 zones obligatoires sont couvertes, les overlays sont presents, et l'arc emotionnel general tient la route. La scene de reconciliation (sfx_009 + sfx_010) est le point fort, avec un duo cordes/harpe qui porte magnifiquement le moment.

**Mais trois problemes majeurs empechent d'atteindre le 9/10 :**

1. **Conformite technique catastrophique (46% de prompts non conformes)** : descriptions visuelles, tactiles, thermiques, silence decrit, risque de parole. Ce sont des erreurs qui vont generer des sons inadequats ou du speech parasite. Les 6 corrections P0 sont imperatives.

2. **Trou de couverture massif en debut d'episode** : 13 segments voix sans aucun SFX entre seg_001 et seg_013. C'est plus de 2 minutes de voix nue dans la phase d'installation. L'enfant decroche. Il faut au minimum un overlay d'ambiance salon prolonge (P1-1).

3. **Densite insuffisante** : avec un ratio SFX/voix de 16.9%, on est sous le seuil minimal de 20%. Il manque 3-4 SFX pour habiller les zones creuses (P1-1 a P1-4).

**Apres application des corrections P0 + P1, le score projete monte a ~8.2/10. Avec les P2, on vise le 9/10.**

---

*Rapport genere par Thomas Lavigne — Audit SFX pre-production*
*Pipeline Papy Babou — S01E04*
