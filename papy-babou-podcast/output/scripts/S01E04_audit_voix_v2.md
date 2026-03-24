# AUDIT DIRECTION VOCALE — S01E04 "Joseph et la tunique de couleurs — trahi par ses freres"
## Par Isabelle Fontaine, directrice vocale

**Date** : 2026-03-23
**Version** : v2
**Note** : Mamie Sonia absente de cet episode (non penalise).

---

### Metriques vocales

| Metrique | Valeur | Cible | Status |
|----------|--------|-------|--------|
| Segments voix total | 77 | - | - |
| Mots total | 2111 | - | - |
| Ratio Papy | 71.7% | 55-70% | **KO** (+1.7%) |
| Ratio enfants | 28.3% | 25-40% | OK |
| Ratio Mamie | 0% (absente) | N/A | N/A |
| Max segment adulte (mots) | 62 (seg_028) | <=60 | **KO** |
| Max segment Antoine (mots) | 34 (seg_002) | <=40 | OK |
| Max segment Noemie (mots) | 21 (seg_015) | <=15 | **KO** |
| Tons distincts Papy | 9 | >=4 | OK |
| Tons distincts Antoine | 8 | >=4 | OK |
| Tons distincts Noemie | 8 | >=4 | OK |
| Segments rythme non-normal | 27.3% (21/77) | >=15% | OK |
| Streaks meme ton >3 (Papy) | 2 (grave x3, dramatique x3) | 0 | **KO** |
| Streaks meme ton >3 (enfants) | 0 | 0 | OK |
| Streaks meme perso >4 | 0 (max=2) | 0 | OK |
| Interruptions enfants | ~15 | >=3 | OK |
| Echanges Antoine<->Noemie | 8 | >=2 | OK |
| Interventions Mamie | 0 (absente) | N/A | N/A |
| Tics Antoine utilises | 3/5 | >=2 | OK |
| Tics Noemie utilises | 4/5 | >=2 | OK |

### Distribution par personnage

| Personnage | Segments | Mots | % mots | Tons utilises | Max mots/seg |
|------------|----------|------|--------|---------------|--------------|
| papy_babou | 37 | 1513 | 71.7% | chaleureux, dramatique, enthousiaste, grave, joyeux, mysterieux, rassurant, solennel, tendre (9) | 62 |
| antoine | 22 | 348 | 16.5% | admiratif, curieux, determine, enthousiaste, espiegle, impatient, inquiet, pensif (8) | 34 |
| noemie | 18 | 250 | 11.8% | curieux, enthousiaste, espiegle, indignee, inquiet, joyeux, triste, emerveillee (8) | 21 |

### Arc emotionnel vocal

**Phase 1 — Ouverture (seg_000 → seg_005)** : mysterieux → chaleureux → chaleureux. Accroche au mystere puis chaleur d'accueil. Enfants : inquiet → determine. Coherent avec la scene du conflit Maxime.

**Phase 2 — Mise en place (seg_006 → seg_018)** : mysterieux → dramatique → mysterieux → enthousiaste → grave → mysterieux. Bonne montee progressive avec alternance curiosite/tension. Enfants : curieux → enthousiaste → joyeux → espiegle → curieux. Bon ping-pong.

**Phase 3 — Tension / Trahison (seg_020 → seg_029)** : dramatique → dramatique → grave → grave → grave → chaleureux. Zone de tension maximale. Les trois "grave" consecutifs (seg_023, 026, 028) forment un plateau trop monochrome — c'est le point faible. Enfants : inquiet → indignee → inquiet → triste. Coherent et credible.

**Phase 4 — Prison et ascension (seg_030 → seg_046)** : chaleureux → dramatique → mysterieux → mysterieux → dramatique → dramatique → dramatique → enthousiaste. Trois "dramatique" consecutifs (seg_038, 040, 042) — deuxieme plateau. L'ascension de Joseph est bien amenee mais le rythme tonal est repetitif. Enfants : curieux → enthousiaste → espiegle → curieux → enthousiaste → enthousiaste. Bon dynamisme.

**Phase 5 — Retrouvailles et pardon (seg_047 → seg_060)** : mysterieux → dramatique → grave → grave → dramatique → solennel → rassurant → tendre. Belle descente emotionnelle, le "solennel" sur le pardon est parfait. Enfants : curieux → emerveillee → admiratif → inquiet → joyeux. Transition reussie.

**Phase 6 — Retour au present et cloture (seg_061 → seg_076)** : rassurant → solennel → chaleureux → tendre → mysterieux → enthousiaste → joyeux. Arc de cloture tres reussi : du serieux de la morale vers la legerete du teasing. Enfants : curieux → pensif → curieux → joyeux → enthousiaste → inquiet. Naturel.

**Bilan arc** : L'arc global est clair et bien structure. Le probleme se concentre sur les phases 3-4 ou les tons "grave" et "dramatique" saturent sans respiration.

---

### A. Conformite technique TTS

| # | Seg ID | Perso | Regle | Severite | Texte actuel | Correction proposee |
|---|--------|-------|-------|----------|--------------|---------------------|
| 1 | seg_044 | antoine | R1 Onomatopee | **HIGH** | "**Chut**, Noemie ! Laisse Papy finir !" | "Arrete, Noemie ! Laisse Papy finir ! Je veux savoir ce que le Pharaon a fait !" |
| 2 | seg_023 | papy_babou | R3 Ellipsis mid | **HIGH** | "Et ils l'ont jete**...** au fond d'un puits." | "Et ils l'ont jete au fond d'un puits." (ajouter `"rythme": "lent"` + `pause_apres_ms: 2000` pour l'effet dramatique) |
| 3 | seg_048 | antoine | R3 Ellipsis mid | **MEDIUM** | "Non**...** Ses freres ?!" | "Non. Ses freres ?!" (la pause naturelle du point suffit) |
| 4 | seg_061 | antoine | R3 Ellipsis mid | **MEDIUM** | "Papy**...** tu crois que Maxime" | "Papy, tu crois que Maxime, il savait que c'etait mechant ce qu'il faisait ? Les freres de Joseph, ils savaient ?" |
| 5 | seg_028 | papy_babou | R5 Limite mots | **MEDIUM** | 62 mots | Splitter en 2 segments : seg_028a "Les freres ont pris la tunique de Joseph, ils l'ont trempee dans du sang de chevre, et ils l'ont rapportee a leur pere." (ton: grave, rythme: lent) + seg_028b "Ils lui ont dit : on a trouve ca. C'est pas la tunique de Joseph ? Jacob a cru que son fils avait ete devore par une bete sauvage. Il a pleure, pleure, pendant des jours et des nuits." (ton: grave, rythme: lent) |
| 6 | seg_021 | papy_babou | R3 Ellipsis fin >15 mots | **LOW** | "...de loin**...**" (38 mots) | Acceptable si TTS gere bien, mais segment long — envisager un split ou retirer les `...` et ajouter une pause de 1500ms |
| 7 | seg_015 | noemie | R5 Limite mots enfant | **MEDIUM** | 21 mots (limite 15 pour Noemie 5 ans) | Splitter : seg_015a "Moi aussi je veux un manteau arc-en-ciel !" (ton: enthousiaste) + seg_015b "Le bebe Lucas il en aura un quand il naitra ?" (ton: curieux) |
| 8 | seg_022 | noemie | R5 Limite mots enfant | **LOW** | 17 mots | Acceptable — deux phrases courtes enchainees, naturel pour une enfant emue |
| 9 | seg_024 | noemie | R5 Limite mots enfant | **LOW** | 19 mots | Trois exclamations courtes — passe en TTS mais a surveiller |
| 10 | seg_068 | noemie | R5 Limite mots enfant | **MEDIUM** | 20 mots | Splitter : seg_068a "Dis Papy, est-ce que le bebe Lucas il aura un manteau de couleurs quand il naitra ?" + seg_068b "Comme Joseph ?" |
| 11 | seg_071 | noemie | R5 Limite mots enfant | **LOW** | 17 mots | Limite mais deux phrases courtes, acceptable |
| 12 | seg_075 | noemie | R5 Limite mots enfant | **LOW** | 18 mots | Trois questions courtes, acceptable en TTS |

**Bilan conformite** : 2 HIGH, 5 MEDIUM, 5 LOW. Les deux HIGH (onomatopee "Chut" et ellipsis milieu seg_023) sont bloquants pour la production TTS.

---

### B. Qualite de la direction vocale

| Axe | Note /10 | Commentaire detaille |
|-----|----------|----------------------|
| B1. Variete et justesse des tons | **8/10** | **Points forts** : 9 tons Papy, 8 tons par enfant — excellente palette. Tons coherents avec le contenu (grave pour la trahison, solennel pour le pardon, tendre pour les retrouvailles). **Points faibles** : Deux streaks de 3 tons identiques pour Papy — "grave" (seg_023→026→028) durant la scene de la trahison, et "dramatique" (seg_038→040→042) durant la scene du Pharaon. Ces plateaux creent une monotonie locale. Il manque un ton "pose" ou "narratif" pour respirer entre les moments intenses. Suggestion : seg_026 passer de "grave" a "dramatique" ; seg_040 passer de "dramatique" a "mysterieux". |
| B2. Rythme et pauses | **9/10** | **Points forts** : 27.3% de segments non-normal, bien au-dessus du seuil de 15%. Distribution intelligente : "lent" sur les moments de suspense et d'emotion (trahison, pardon), "rapide" sur les reactions des enfants. 4 pauses de 2000ms bien placees (puits, retrouvailles, pardon). Aucune pause >3000ms. **Point faible mineur** : Pas de rythme "rapide" entre seg_046 et seg_074 — la section resolution/morale manque un peu d'energie. Le teasing final (seg_074) est "rapide", bon reflexe. |
| B3. Naturalite dialogues enfants | **8/10** | **Points forts** : Antoine parle comme un vrai CE2 — "C'est meme pas vrai !", "verts de jalousie", "retournement de situation". Noemie a des digressions adorables (le gouter seg_043, le bebe Lucas). Tics de langage presents des deux cotes (3/5 Antoine, 4/5 Noemie). L'interaction fratrie fonctionne (seg_003-004 Noemie balance, Antoine nie). **Points faibles** : (1) seg_002 Antoine 34 mots — trop long pour une seule replique d'enfant excite, un vrai gamin dirait ca en 2 souffles. (2) seg_008 Antoine 24 mots et seg_016 24 mots — phrases bien construites mais un poil trop articulees pour du 8 ans spontane. (3) seg_050 Noemie "C'est comme dans le reve ! Les gerbes de ble qui s'inclinaient !" — une gamine de 5 ans ne dirait pas "gerbes de ble qui s'inclinaient", c'est du vocabulaire adulte. (4) seg_009 Noemie explique l'etymologie d'Isaac — un peu trop didactique pour 5 ans, sauf si Papy l'a deja explique dans un episode precedent. (5) Plusieurs segments Noemie depassent 15 mots (8 sur 18). |
| B4. Arc emotionnel vocal | **9/10** | **Points forts** : Arc tres clair en 6 phases — ouverture chaleureuse → mise en place mysterieuse → tension grave/dramatique → prison et ascension → pardon solennel → cloture tendre et joyeuse. La coherence inter-personnages est excellente : quand Papy est grave, les enfants sont inquiets ; quand Papy est enthousiaste, les enfants suivent. Le moment du pardon (seg_056 solennel) est le sommet emotionnel, bien amene. Le retour au present (seg_061→066) est magnifique — Antoine connecte Joseph a Maxime, Noemie pousse son frere. **Point faible** : Les phases 3-4 (seg_020→046) sont un bloc trop long de tensions sans respiration — 26 segments de drame quasi continu. Un moment de legerete (une blague d'enfant, un apart) aurait aere l'arc. |
| B5. Dynamique des echanges | **8/10** | **Points forts** : Max 2 segments consecutifs du meme personnage — excellente alternance. 8 echanges directs Antoine/Noemie — tres au-dessus du minimum de 2. Interruptions nombreuses (~15). Rebonds naturels — quand Antoine demande, Papy repond en 1 segment max. Les enfants ne sont pas des lanceurs de balle : Noemie digresse (gouter, bebe Lucas), Antoine compare a ses super-heros, les deux se chamaillent. **Points faibles** : (1) Ratio Papy 71.7% — depasse la cible de 70% de 1.7 points. Pas dramatique mais a surveiller. (2) Antoine (16.5%) et Noemie (11.8%) sont un peu desequilibres — Noemie meriterait 2-3 repliques de plus pour equilibrer. (3) Papy a 4 doublons consecutifs (seg_000-001, seg_017-018, seg_020-021, seg_055-056) ou il enchaine 2 segments — acceptable mais la derniere paire (seg_055-056) fait 2 segments denses de suite. |

| **Moyenne direction vocale** | **8.4/10** | |

---

### Corrections techniques P0 — bloquantes

**P0-1** : seg_044 — Supprimer "Chut"
```json
{
  "id": "seg_044",
  "personnage": "antoine",
  "texte": "Arrete, Noemie ! Laisse Papy finir ! Je veux savoir ce que le Pharaon a fait !",
  "ton": "impatient",
  "rythme": "rapide",
  "pause_apres_ms": 600
}
```

**P0-2** : seg_023 — Supprimer ellipsis milieu de phrase
```json
{
  "id": "seg_023",
  "personnage": "papy_babou",
  "texte": "Ils l'ont attrape, ma puce. Ils lui ont arrache sa tunique de couleurs. Et ils l'ont jete au fond d'un puits. Un trou noir, profond, dans la terre seche.",
  "ton": "grave",
  "rythme": "lent",
  "pause_apres_ms": 2000
}
```

### Corrections de direction vocale P1 — pour atteindre 9/10

**P1-1** : Casser le streak "grave" x3 — seg_026 passer de "grave" a "dramatique"
```json
{
  "id": "seg_026",
  "personnage": "papy_babou",
  "texte": "Et ce n'est pas fini, mon grand. Des marchands qui passaient par la, avec leurs chameaux charges d'epices, ont vu le puits. Les freres leur ont vendu Joseph. Vendu ! Comme on vendrait un animal au marche. Pour vingt pieces d'argent.",
  "ton": "dramatique",
  "pause_apres_ms": 1500
}
```

**P1-2** : Casser le streak "dramatique" x3 — seg_040 passer de "dramatique" a "mysterieux"
```json
{
  "id": "seg_040",
  "personnage": "papy_babou",
  "texte": "Personne ne pouvait expliquer ce reve au Pharaon. Personne ! Jusqu'a ce qu'on se souvienne de Joseph, le prisonnier qui savait lire les reves. On l'a fait sortir de prison, on l'a lave, habille, et amene devant le roi.",
  "ton": "mysterieux",
  "pause_apres_ms": 1000
}
```

**P1-3** : seg_028 — Splitter le segment de 62 mots en 2
```json
{
  "id": "seg_028a",
  "personnage": "papy_babou",
  "texte": "Les freres ont pris la tunique de Joseph, ils l'ont trempee dans du sang de chevre, et ils l'ont rapportee a leur pere.",
  "ton": "grave",
  "rythme": "lent",
  "pause_apres_ms": 800
}
```
```json
{
  "id": "seg_028b",
  "personnage": "papy_babou",
  "texte": "Ils lui ont dit : on a trouve ca. C'est pas la tunique de Joseph ? Jacob a cru que son fils avait ete devore par une bete sauvage. Il a pleure, pleure, pendant des jours et des nuits.",
  "ton": "grave",
  "rythme": "lent",
  "pause_apres_ms": 1500
}
```

**P1-4** : seg_048 et seg_061 — Corriger ellipsis milieu de phrase
```json
{
  "id": "seg_048",
  "personnage": "antoine",
  "texte": "Non. Ses freres ?!",
  "ton": "curieux",
  "pause_apres_ms": 800
}
```
```json
{
  "id": "seg_061",
  "personnage": "antoine",
  "texte": "Papy, tu crois que Maxime, il savait que c'etait mechant ce qu'il faisait ? Les freres de Joseph, ils savaient ?",
  "ton": "pensif",
  "pause_apres_ms": 1000
}
```

**P1-5** : seg_044 — Changer ton de "enthousiaste" a "impatient" (un enfant qui fait taire sa soeur n'est pas enthousiaste)
> Deja corrige dans P0-1 ci-dessus.

### Segments enfants a reecrire P1 — naturalite

**P1-6** : seg_050 — Vocabulaire trop adulte pour Noemie (5 ans)
- Actuel : "C'est comme dans le reve ! Les gerbes de ble qui s'inclinaient !"
- Propose : "C'est comme dans le reve ! Le ble qui se baissait devant lui !"

**P1-7** : seg_015 — Splitter pour Noemie (21 mots)
- seg_015a : "Moi aussi je veux un manteau arc-en-ciel !" (ton: enthousiaste)
- seg_015b : "Le bebe Lucas il en aura un ?" (ton: curieux)

**P1-8** : seg_068 — Splitter pour Noemie (20 mots)
- seg_068a : "Dis Papy, le bebe Lucas il aura un manteau de couleurs ?" (ton: joyeux)
- seg_068b : "Comme Joseph ?" (ton: curieux)

**P1-9** : seg_002 — Antoine 34 mots, splitter
- seg_002a : "C'est Maxime, Papy. Il a dit a tout le monde que j'avais triche au controle de maths." (ton: inquiet, rythme: rapide)
- seg_002b : "Alors que c'est meme pas vrai ! Et maintenant, personne veut jouer avec moi a la recre." (ton: determine, rythme: rapide)

### Corrections P2 — ameliorations souhaitables

**P2-1** : Ajouter 2-3 repliques Noemie supplementaires dans la section milieu (seg_030→045) pour equilibrer le ratio Antoine/Noemie.

**P2-2** : Inserer une micro-digression enfantine entre seg_035 et seg_038 pour aerer le bloc dramatique (ex: Noemie demande si Joseph avait un doudou en prison).

**P2-3** : seg_009 — "parce que ca veut dire 'il rit'" sonne un peu didactique pour Noemie. Reformuler en : "Isaac ! Parce que ca veut dire qu'on rigole !"

**P2-4** : seg_021 — Les `...` en fin de phrase sur un segment de 38 mots sont risques en TTS. Retirer et ajouter une pause de 1500ms.

---

### Score global direction vocale : 8.4/10

| Axe | Note |
|-----|------|
| B1. Variete et justesse des tons | 8/10 |
| B2. Rythme et pauses | 9/10 |
| B3. Naturalite dialogues enfants | 8/10 |
| B4. Arc emotionnel vocal | 9/10 |
| B5. Dynamique des echanges | 8/10 |
| **Moyenne** | **8.4/10** |

### Verdict : "Corrections necessaires"

**Resume** : Le script a une direction vocale solide — l'arc emotionnel est clair, le rythme est bien travaille, et les enfants sont globalement credibles. Les deux problemes principaux sont : (1) deux streaks de tons identiques pour Papy dans les zones de tension, qui creent des plateaux monotones ; (2) plusieurs segments Noemie depassent la limite de 15 mots pour une enfant de 5 ans, et un segment utilise un vocabulaire trop adulte ("gerbes de ble qui s'inclinaient"). Les corrections P0 (2 bloquantes TTS) et P1 (9 ameliorations) permettraient d'atteindre le 9/10 vise.

**Apres application des P0 + P1** : score estime **9.0-9.2/10** — pret pour production.
