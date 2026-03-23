# AUDIT DIRECTION VOCALE — S01E03 "Abraham — celui qui a tout quitté par confiance"
## Par Isabelle Fontaine, directrice vocale

### Métriques vocales

| Métrique | Valeur | Cible | Status |
|----------|--------|-------|--------|
| Segments voix total | 47 | - | - |
| Mots total | ~2100 | - | - |
| Ratio Papy | 53% (25 seg) | 55-70% | ⚠️ Limite basse |
| Ratio enfants | 51% (24 seg: Antoine 13 + Noémie 11) | 25-40% | ⚠️ Au-dessus |
| Ratio Mamie | 6% (3 seg) | 5-10% | ✅ OK |
| Ratio Narrateur | 4% (2 seg) | - | - |
| Max segment (mots) | ~55 (seg_048 Papy) | 60 adultes | ✅ OK |
| Max segment enfant (mots) | ~35 (seg_003 Antoine) | 40 enfants | ✅ OK |
| Tons distincts Papy | 5 (chaleureux, dramatique, rassurant, enthousiaste, joyeux) | >=4 | ✅ OK |
| Tons distincts Antoine | 4 (curieux, enthousiaste, inquiet, rassurant) | >=4 | ✅ OK |
| Tons distincts Noémie | 4 (curieux, enthousiaste, inquiet, joyeux) | >=4 | ✅ OK |
| Segments rythme non-normal | 0% | >=15% | ❌ CRITIQUE |
| Streaks même ton Papy >3 | 0 | 0 | ✅ OK |
| Streaks même perso >4 | 0 | 0 | ✅ OK |
| Interruptions enfants | 3 (seg_015, seg_033, seg_050) | >=3 | ✅ OK |
| Échanges Antoine↔Noémie | 1 (seg_033-034) | >=2 | ⚠️ Insuffisant |
| Interventions Mamie | 3 (seg_031, 035, 041) | >=3 | ✅ OK |
| Tics Antoine utilisés | 2 ("Attends" seg_015, "C'est pas possible" seg_015) | >=2 | ✅ OK |
| Tics Noémie utilisés | 2 ("Papy" seg_017/033, "Moi je" seg_044) | >=2 | ✅ OK |
| Pauses >2000ms | 3 (seg_014, seg_025, seg_048) | <=3 | ✅ OK |

### Distribution par personnage

| Personnage | Segments | Mots (est.) | % mots | Tons utilisés | Max mots/seg |
|------------|----------|-------------|--------|---------------|--------------|
| papy_babou | 25 | ~1150 | ~55% | chaleureux(13), dramatique(4), rassurant(5), enthousiaste(3), joyeux(2) | ~55 |
| antoine | 13 | ~350 | ~17% | curieux(5), enthousiaste(4), inquiet(2), rassurant(1) | ~35 |
| noemie | 11 | ~220 | ~10% | curieux(3), enthousiaste(3), inquiet(3), joyeux(2) | ~22 |
| mamie_sonia | 3 | ~100 | ~5% | joyeux(2), rassurant(1) | ~40 |
| narrateur | 2 | ~80 | ~4% | chaleureux(1), neutre(1) | ~45 |

### Arc émotionnel vocal

```
Début (seg_001-010)     : chaleureux → inquiet → enthousiaste → chaleureux
                          [accueil, bienveillance, mise en confiance]

Montée (seg_011-018)    : chaleureux → dramatique → DRAMATIQUE → rassurant → inquiet → chaleureux
                          [tension monte avec l'appel de Dieu, pause 2000ms au climax de l'appel]

Développement (seg_019-029) : neutre → curieux → enthousiaste → chaleureux → dramatique → enthousiaste
                              [alternance contemplation/excitation, scène étoiles = pic émotionnel]

Pivot (seg_030-038)     : curieux → joyeux → chaleureux → curieux → enthousiaste → chaleureux → joyeux → joyeux
                          [détente, humour Mamie, running gag, naissance Isaac = joie]

Résolution (seg_039-049): curieux → rassurant → rassurant → inquiet → rassurant → enthousiaste → rassurant → chaleureux → chaleureux → rassurant
                          [retour au calme, morale, Antoine résout son conflit interne]

Fin (seg_050-055)       : enthousiaste → enthousiaste → curieux → chaleureux → inquiet → joyeux
                          [teasing excitant, au revoir joyeux]
```

**Cohérence inter-personnages** : ✅ Quand Papy est dramatique (seg_013-014), Noémie réagit avec inquiétude (seg_012, 017). Quand Papy est joyeux (seg_037), Noémie est joyeuse (seg_038). L'arc est cohérent.

### A. Conformité technique TTS

| # | Seg ID | Perso | Règle | Sévérité | Texte actuel | Correction |
|---|--------|-------|-------|----------|--------------|------------|
| 1 | seg_012 | noemie | R1 : onomatopée | MEDIUM | "**Oh** non, le pauvre." | "Le pauvre. Ils devaient être tristes." |
| 2 | seg_028 | antoine | R1 : interjection | LOW | "**Trop cool** ! Un nouveau nom..." | Acceptable en langage enfant — conserver |
| 3 | seg_018 | papy | R6 : nombre | LOW | "soixante-quinze" | ✅ Déjà en lettres |
| 4 | seg_029 | papy | R6 : nombre | LOW | "quatre-vingt-dix-neuf... quatre-vingt-dix" | ✅ Déjà en lettres |

**Bilan technique** : 1 correction MEDIUM (seg_012 "Oh non"), le reste est conforme. Score technique : **8/10**.

### B. Qualité de la direction vocale

| Axe | Note /10 | Commentaire détaillé |
|-----|----------|----------------------|
| B1. Variété et justesse des tons | **7.5** | 5 tons distincts pour Papy = bon. MAIS "chaleureux" domine massivement (13/25 = 52%). Risque de monotonie perçue. Manque de tons comme "espiègle", "mystérieux", "nostalgique". Antoine est trop "curieux" (5/13 = 38%). Il manque "impatient", "admiratif". Les tons correspondent au contenu MAIS on pourrait être plus nuancé : seg_021 "Attendez, attendez !" devrait être "espiègle" pas "enthousiaste". Seg_025 serait mieux en "mystérieux" qu'en "dramatique". |
| B2. Rythme et pauses | **4.0** | **PROBLÈME CRITIQUE : 0% de segments en rythme non-normal.** Cible >=15%. L'épisode entier est en rythme "normal" — c'est plat. La scène d'appel de Dieu (seg_014) devrait être en rythme "lent" pour la solennité. Le voyage caravane (seg_019) devrait être "lent" pour la contemplation. La scène des étoiles (seg_025-027) devrait être "lent" pour l'émerveillement. Les réactions enthousiastes (seg_006, 028, 034) devraient être "rapide". Le teasing (seg_051-053) devrait être "rapide" pour l'excitation. Les 3 pauses >2000ms sont bien placées (appel de Dieu, étoiles, mot de Papy). Mais sans variation de rythme, les pauses flottent dans un tempo uniforme. |
| B3. Naturalité dialogues enfants | **8.0** | Antoine sonne bien CE2 : questions pertinentes, vocabulaire adapté, "C'est pas possible !" est naturel. Noémie sonne bien GS/CP : phrases courtes, émotions directes, "Moi je l'aurais aidé" est charmant. Le running gag goûter (seg_033) est excellent — digression 100% naturelle. MAIS : seg_046 Antoine "peut-être que le déménagement, c'est un peu comme Abraham" → trop articulé pour 8 ans, sonne comme un adulte qui tire la morale. Seg_003 Antoine est un peu long (35 mots) mais acceptable. Noémie seg_007 est bien construite mais manque de spontanéité ("Et on avait demandé si..." = construction trop propre). |
| B4. Arc émotionnel vocal | **7.5** | Arc présent et cohérent (voir ci-dessus). La progression chaleureux → dramatique → rassurant → joyeux → chaleureux fonctionne. MAIS : le climax émotionnel (scène étoiles seg_025) n'est pas assez marqué vocalement — même ton "dramatique" qu'ailleurs. Il faudrait un ton "mystérieux" ou "émerveillé" pour différencier. La résolution (seg_039-049) est trop longue en "rassurant" — 5 segments rassurants quasi consécutifs, ça devient plat. L'absence de rythme "lent" aux moments d'émotion affaiblit tout l'arc. |
| B5. Dynamique des échanges | **7.5** | Max 3 segments Papy consécutifs (seg_036-037, seg_048-049) = OK. Ratio Papy/enfants acceptable. 3 interruptions = minimum atteint. MAIS : seulement 1 échange direct Antoine↔Noémie (seg_033-034, le goûter). Cible >=2. Il manque un moment de complicité ou de dispute fratrie. Mamie Sonia a 3 interventions (minimum) mais 2 sur 3 sont en ton "joyeux" — elle est unidimensionnelle. Son témoignage (seg_041) est le seul moment avec de la profondeur. |
| **Moyenne direction vocale** | **6.9** | |

### Corrections techniques (P0 — bloquantes)

| # | Action | Segment | Correction |
|---|--------|---------|------------|
| 1 | Modifier ton | seg_012 | "Oh non, le pauvre." → "Le pauvre. Ils devaient être tristes." (suppression onomatopée) |

### Corrections de direction vocale (P1 — pour atteindre 9/10)

| # | Action | Segments | Correction |
|---|--------|----------|------------|
| 1 | **AJOUTER RYTHME** | seg_014 | `"rythme": "lent"` — l'appel de Dieu est solennel |
| 2 | **AJOUTER RYTHME** | seg_019 | `"rythme": "lent"` — narration contemplative du voyage |
| 3 | **AJOUTER RYTHME** | seg_025 | `"rythme": "lent"` — scène des étoiles, émerveillement |
| 4 | **AJOUTER RYTHME** | seg_027 | `"rythme": "lent"` — révélation descendance/étoiles |
| 5 | **AJOUTER RYTHME** | seg_006 | `"rythme": "rapide"` — enthousiasme Antoine previously-on |
| 6 | **AJOUTER RYTHME** | seg_028 | `"rythme": "rapide"` — excitation nouveau nom |
| 7 | **AJOUTER RYTHME** | seg_034 | `"rythme": "rapide"` — impatience "laisse Papy finir !" |
| 8 | **AJOUTER RYTHME** | seg_051 | `"rythme": "rapide"` — teasing excitant |
| 9 | **MODIFIER TON** | seg_025 | `"ton": "mystérieux"` au lieu de "dramatique" — les étoiles c'est du mystère, pas du drame |
| 10 | **MODIFIER TON** | seg_021 | `"ton": "espiègle"` au lieu de "enthousiaste" — "Attendez, attendez !" c'est taquin |
| 11 | **MODIFIER TON** | seg_048 | `"ton": "solennel"` au lieu de "chaleureux" — le mot de Papy est un moment grave |
| 12 | **AJOUTER pause** | seg_037 | `"pause_apres_ms": 2000` — la révélation Isaac = "il rit" mérite une pause |

### Segments enfants à réécrire (P1 — naturalité)

| # | Seg | Actuel | Proposition |
|---|-----|--------|-------------|
| 1 | seg_046 | "Alors peut-être que le déménagement, c'est un peu comme Abraham. On part, on a peur, mais peut-être qu'on va trouver des trucs encore mieux." | "Alors en fait, le déménagement, c'est pareil que Abraham ? On a peur mais après c'est bien ?" (plus CE2) |
| 2 | seg_007 | "Et on avait demandé si les animaux s'entendaient bien dans l'arche. Moi je suis sûre que oui." | "Les animaux dans l'arche, ils étaient copains ou pas ? Moi je dis que oui !" (plus GS/CP) |

### Score global direction vocale : 6.9/10
### Verdict : "Corrections nécessaires"

**Problème n°1** : le rythme à 0% non-normal est rédhibitoire. C'est la différence entre une lecture plate et une performance vivante. 8 ajouts de rythme (P1) résoudraient ce problème et feraient gagner 1.5 à 2 points sur B2.

**Projection après corrections P0+P1** : ~8.5/10 (B1: 8.5, B2: 7.5, B3: 8.5, B4: 8.5, B5: 8.0)
