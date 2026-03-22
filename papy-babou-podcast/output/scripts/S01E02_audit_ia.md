# AUDIT COMPATIBILITÉ IA — S01E02 "Noé et le déluge"

**Auditeur** : @ia (AI Engineer — spécialiste ElevenLabs TTS + Sound Effects)
**Date** : 2026-03-22
**Script audité** : `output/scripts/S01E02_script.json`
**Stats** : 161 segments (135 voix, 26 SFX), 2459 mots

---

## NOTE GLOBALE COMPATIBILITÉ IA : 8.3/10

---

## 1. Optimisation TTS ElevenLabs (voix) — 8.5/10

### Paramètres actuels (config.py)

| Personnage | stability | similarity_boost | style | Verdict |
|---|---|---|---|---|
| papy_babou | 0.75 | 0.85 | 0.2 | BON — voix stable de conteur, style bas = naturel |
| antoine | 0.60 | 0.80 | 0.4 | BON — stability basse = expressif, style élevé = enfant |
| noemie | 0.65 | 0.80 | 0.35 | À AJUSTER — stability trop haute pour une chipie de 5 ans |
| mamie_sonia | 0.75 | 0.85 | 0.25 | BON — stable, chaleureux |

### Recommandation Noémie
Noémie est décrite comme chipie, espiègle, avec un gros caractère. Ses répliques alternent entre excité, espiègle, inquiet et joyeux. Avec stability=0.65, les variations de ton seront trop lissées.

**Suggestion** : `stability: 0.55, similarity_boost: 0.75, style: 0.45` — plus expressif, plus de variations d'intonation.

### Système TONE_VOICE_ADJUSTMENTS

Le pipeline applique des ajustements dynamiques par ton. Vérification des tons utilisés dans S01E02 :

| Ton | Présent dans TONE_VOICE_ADJUSTMENTS ? | Occurrences E02 |
|---|---|---|
| chaleureux | OUI | 24 |
| curieux | OUI | 11 |
| dramatique | OUI | 7 |
| solennel | OUI | 6 |
| émerveillé | OUI | 6 |
| espiègle | OUI | 6 |
| joyeux | OUI | 6 |
| inquiet | OUI | 6 |
| enthousiaste | OUI | 5 |
| excite | OUI | 4 |
| triste | OUI | 4 |
| mystérieux | OUI | 4 |
| rassurant | OUI | 2 |
| déterminé | NON | 3 |
| moqueur | NON | 1 |
| boudeur | NON | 1 |
| admiratif | NON | 1 |
| indigné | NON | 1 |
| soulagé | NON | 1 |
| impatient | NON | 1 |

**PROBLÈME IMPORTANT** : 6 tons utilisés dans le script NE SONT PAS dans `TONE_VOICE_ADJUSTMENTS`. Ils tomberont sur les settings de base sans ajustement. Les plus impactants :

- **déterminé** (3 occurrences, seg_048/084/123) — moments clés d'Antoine. Suggestion : `{"stability": +0.10, "similarity_boost": +0.05, "style": +0.05}` — plus posé et affirmatif
- **moqueur** (1 occurrence, seg_039) — Papy imite les moqueurs. Suggestion : `{"stability": -0.15, "similarity_boost": -0.05, "style": +0.25}` — instable et expressif
- **indigné** (1 occurrence, seg_038) — Noémie outrée. Suggestion : `{"stability": -0.20, "similarity_boost": 0.0, "style": +0.20}` — vif et émotionnel
- **soulagé** (1 occurrence, seg_088) — Noémie. Suggestion : `{"stability": +0.05, "similarity_boost": 0.0, "style": +0.10}`
- **admiratif** (1 occurrence, seg_042) — Antoine. Suggestion : `{"stability": -0.05, "similarity_boost": +0.05, "style": +0.15}`
- **boudeur** (1 occurrence, seg_004) — Antoine. Suggestion : `{"stability": +0.05, "similarity_boost": 0.0, "style": +0.15}`
- **impatient** (1 occurrence, seg_064) — Antoine. Suggestion : `{"stability": -0.15, "similarity_boost": 0.0, "style": +0.20}`

### Longueur des segments

Sweet spot ElevenLabs = 8-45 mots. Analyse :

| Plage | Count | Verdict |
|---|---|---|
| 1-4 mots | 12 | ATTENTION — risque d'intonation plate sur segments ultra-courts |
| 5-15 mots | 68 | EXCELLENT — zone optimale pour enfants |
| 16-30 mots | 42 | BON — zone optimale pour adultes |
| 31-45 mots | 12 | OK — limite haute, fonctionne avec les paramètres actuels |
| 46+ mots | 1 | ATTENTION — seg_050 Mamie (48 mots après correction) |

**Segments ultra-courts problématiques** :
- seg_088 "Enfin !" (1 mot) — ElevenLabs produira un rendu plat ou étrange sur un seul mot. **Suggestion** : allonger à "Enfin ! C'est fini la pluie !" (ton soulagé)
- seg_048 "Non. Il a continué." (4 mots) — OK car le rythme "lent" compense, mais borderline
- seg_096 "Un gâteau ?" (2 mots) — Fonctionne bien comme question courte avec ton espiègle

### Formulations problématiques TTS

| Segment | Problème | Suggestion |
|---|---|---|
| seg_077 | "cent cinquante jours en tout" — les grands nombres composés peuvent être mal articulés en TTS | Tester en production ; fallback : "plus de cent jours" |
| seg_050 | 48 mots — le plus long segment enfant/Mamie, frôle la limite | Acceptable pour Mamie (adulte, limit 60), mais surveiller le rendu |
| seg_117 | "Oui ! Le cake ! Le cake !" — la répétition avec exclamations peut sonner artificiel en TTS | Tester ; si problème, réduire à "Oui ! Le cake !" |

### Pauses (pause_apres_ms)

Les pauses vont de 200ms à 500ms. C'est bien calibré :
- 200ms pour les répliques rapides/excitées — correct
- 300-400ms pour les transitions narratives — correct
- 500ms pour les moments solennels/dramatiques — correct

**Suggestion d'amélioration** : les segments "solennel" et "dramatique" avec rythme "lent" pourraient bénéficier de pauses de 600-700ms pour plus de gravité. Notamment seg_022 (Dieu qui regrette) et seg_110 (promesse arc-en-ciel).

---

## 2. Optimisation SFX ElevenLabs Sound Effects — 7.5/10

### Analyse par SFX

| SFX | Durée | Mode | Description | Verdict | Remarque |
|---|---|---|---|---|---|
| sfx_001 | 8s | insert | heavy rain + thunder + wind | BON | Spécifique et réaliste |
| sfx_002 | 5s | insert | thunder crack + bass rumble | BON | |
| sfx_003 | 6s | insert | massive wave + water surge | BON | |
| sfx_004 | 4s | insert | magical whoosh + harp + indoor ambiance | ATTENTION | Multi-sons complexe — ElevenLabs peut avoir du mal à combiner whoosh + harp + ambiance en 4s |
| sfx_005 | 6s | overlay | rain + fireplace + clock | BON | Mais 6s est COURT pour un overlay — devrait être 15-20s minimum |
| sfx_006 | 4s | insert | mugs clinking + fabric rustling | BON après correction | |
| sfx_007 | 4s | insert | orchestral swell + strings | ATTENTION | ElevenLabs Sound Effects n'est PAS optimisé pour la musique orchestrale — résultat souvent médiocre |
| sfx_008 | 6s | overlay | hammer + saw + wood | BON | |
| sfx_008b | 4s | insert | crowd laughing mockingly | ATTENTION | "laughing" peut générer de la parole. Suggestion : "crowd jeering and scoffing sounds, derisive group reaction" |
| sfx_009 | 4s | insert | final hammer + tools + creak | BON | |
| sfx_009b | 18s | overlay | outdoor + breeze + birds + footsteps | BON | Bonne durée overlay |
| sfx_010 | 8s | insert | animal sounds layered | BON | Spécifique et varié |
| sfx_011 | 5s | insert | heavy door closing + latch | EXCELLENT | Très spécifique, rendra très bien |
| sfx_012 | 10s | overlay | rain intensifying + wind + thunder | BON | Bonne durée |
| sfx_013 | 6s | insert | ship creaking + waves + wind | BON | |
| sfx_013b | 20s | overlay | ship interior + muffled rain + animals | BON | Bonne durée overlay |
| sfx_014 | 8s | insert | rain fading + wind dying | BON | |
| sfx_015 | 4s | insert | crow cawing + wing flap | BON | |
| sfx_016 | 3s | insert | dove cooing + wing flutter | BON | |
| sfx_017 | 4s | insert | wing flutter + bird landing + string chord | ATTENTION | Mélange son naturel (oiseau) + musique (string chord) — ElevenLabs va avoir du mal |
| sfx_019 | 6s | insert | orchestral swell + chimes + harp | ATTENTION | Même problème — musique orchestrale complexe |
| sfx_020b | 4s | insert | harp glissando + fireplace + clock | ATTENTION | Mélange musique + ambiance |
| sfx_021 | 4s | insert | plates + cake + laughing | BON après correction | |
| sfx_022 | 5s | insert | footsteps + car + birds | BON | |

### Problèmes critiques SFX

**1. SFX musicaux (sfx_007, sfx_017, sfx_019, sfx_020b)** : ElevenLabs Sound Effects produit des sons environnementaux et des bruitages, pas de la musique orchestrale. Les "orchestral swell", "string chord", "harp glissando" donneront un résultat médiocre ou bizarre.

**Recommandation** : Ces 4 SFX devraient utiliser des fichiers audio pré-enregistrés (royalty-free) plutôt que la génération IA. Sources : Artlist, Epidemic Sound, ou Freesound pour des stings/transitions orchestrales courtes.

Si génération IA obligatoire, reformuler :
- sfx_007 : "warm sustained pad chord slowly rising in volume, gentle resonant tone" (pas "orchestral")
- sfx_017 : "soft wing flutter approaching, delicate bird landing on wooden surface" (retirer le "string chord")
- sfx_019 : "bright shimmering chimes cascading upward, warm resonant bell tones ascending" (retirer "orchestral")
- sfx_020b : "soft melodic chime descending gently, cozy fireplace crackling, clock ticking" (retirer "harp glissando")

**2. Overlay sfx_005 trop court** : 6s pour un overlay d'ambiance salon est insuffisant. Quand le monteur boucle un overlay court, on entend le point de bouclage. **Suggestion** : passer à 20s.

**3. Risque parole sfx_008b** : "crowd laughing mockingly" → "group scoffing and jeering sounds, derisive crowd murmur without speech"

---

## 3. Flow audio global — 8.5/10

### Alternance voix/SFX
- Cold open (seg_001-003) : 3 segments narratifs entrecoupés de SFX tempête → EXCELLENT, immersif
- Transition salon (sfx_004-005) : smooth → BON
- Récit biblique : SFX bien placés aux moments clés (construction, animaux, porte, tempête, colombe, arc-en-ciel) → BON
- Trou sonore comblé (sfx_008b ajouté) → OK mais voir remarque parole ci-dessus

### Overlays
5 overlays au total :
- sfx_005 (salon, 6s) — TROP COURT, passer à 20s
- sfx_008 (construction, 6s) — OK car court passage
- sfx_009b (extérieur, 18s) — BON
- sfx_012 (tempête, 10s) — BON, pourrait être 15s
- sfx_013b (intérieur arche, 20s) — EXCELLENT

### Transitions
- Cold open → salon : sfx_004 (magical whoosh) → BON
- Salon → récit : pas de SFX de transition explicite → MINEUR, le changement de ton de Papy suffit
- Récit → salon final : sfx_020b ajouté → BON

### Paysage sonore évolutif
L'évolution est bonne : tempête extérieure → salon cosy → construction arche → procession animaux → porte fermée → tempête intérieure → calme → oiseaux → arc-en-ciel → salon. Le paysage sonore suit le récit.

---

## 4. Recommandations techniques — Résumé

### Paramètres ElevenLabs recommandés par personnage

| Personnage | stability | similarity_boost | style | Changement |
|---|---|---|---|---|
| papy_babou | 0.75 | 0.85 | 0.2 | Inchangé |
| antoine | 0.60 | 0.80 | 0.4 | Inchangé |
| noemie | **0.55** | **0.75** | **0.45** | Plus expressif pour chipie |
| mamie_sonia | 0.75 | 0.85 | 0.25 | Inchangé |

### Tons manquants à ajouter dans TONE_VOICE_ADJUSTMENTS

```python
"déterminé":  {"stability": +0.10, "similarity_boost": +0.05, "style": +0.05},
"moqueur":    {"stability": -0.15, "similarity_boost": -0.05, "style": +0.25},
"indigné":    {"stability": -0.20, "similarity_boost": 0.0,   "style": +0.20},
"soulagé":    {"stability": +0.05, "similarity_boost": 0.0,   "style": +0.10},
"admiratif":  {"stability": -0.05, "similarity_boost": +0.05, "style": +0.15},
"boudeur":    {"stability": +0.05, "similarity_boost": 0.0,   "style": +0.15},
"impatient":  {"stability": -0.15, "similarity_boost": 0.0,   "style": +0.20},
```

### SFX à remplacer par fichiers pré-enregistrés

| SFX | Raison | Type de fichier recommandé |
|---|---|---|
| sfx_007 | Musique orchestrale | Sting orchestral chaleureux, 4s |
| sfx_019 | Musique orchestrale | Swell orchestral triomphant, 6s |
| sfx_020b | Harpe + ambiance | Transition harpe douce, 4s |
| sfx_017 | Mélange oiseau + musique | Séparer en 2 : garder oiseau généré, ajouter accord musical pré-enregistré |

---

## Top 5 des améliorations à plus fort impact

| # | Impact | Action |
|---|---|---|
| 1 | **CRITIQUE** | Ajouter les 7 tons manquants dans `TONE_VOICE_ADJUSTMENTS` (producteur_audio.py) — sans ça, 13 segments tombent sur les settings par défaut et perdent leur expressivité |
| 2 | **IMPORTANT** | Remplacer les 4 SFX musicaux (sfx_007, 017, 019, 020b) par des fichiers pré-enregistrés ou reformuler sans termes musicaux |
| 3 | **IMPORTANT** | Allonger sfx_005 (overlay salon) de 6s à 20s pour éviter l'effet de boucle audible |
| 4 | **MINEUR** | Allonger seg_088 "Enfin !" à "Enfin ! C'est fini la pluie !" pour un meilleur rendu TTS |
| 5 | **MINEUR** | Ajuster les paramètres voix de Noémie (stability 0.55, style 0.45) pour plus d'expressivité |

---

### Verdict

Le script est **bien optimisé pour la production IA** dans l'ensemble. Les principaux risques sont :
1. Les tons non mappés dans le pipeline (corrigeable côté code, pas côté script)
2. Les SFX musicaux qui ne rendront pas bien en génération IA (corrigeable par des assets pré-enregistrés)
3. Un overlay trop court (corrigeable dans le script)

Aucun problème bloquant. Le script peut partir en production avec les ajustements mineurs ci-dessus.

---

*Rapport généré par @ia — audit compatibilité IA S01E02*
