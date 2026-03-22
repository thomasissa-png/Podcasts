# Audit IA Audio — S01E01 "La creation du monde"

**Date** : 2026-03-22
**Script** : `output/scripts/S01E01_script.json`
**Segments** : 190 (151 voix + 39 SFX)
**Mots** : ~3314 | **Score directeur** : 9.2/10

---

## 1. Note globale : 7.8 / 10

Le script est solide et bien structure. Les principaux problemes sont concentres sur les SFX (termes musicaux non generables par ElevenLabs, descriptions abstraites) et quelques trous sonores dans le dernier tiers. La partie voix est tres propre.

---

## 2. Notes par axe

### 2.1 TTS Voix : 8.5 / 10

**Tons utilises** : 13 tons distincts — `chaleureux` (42), `emerveille` (25), `curieux` (17), `espiegle` (15), `enthousiaste` (13), `joyeux` (11), `mysterieux` (10), `solennel` (7), `excite` (5), `dramatique` (3), `neutre` (1), `inquiet` (1), `rassurant` (1).

- Tous les 13 tons sont presents dans `TONE_VOICE_ADJUSTMENTS`. **0 ton manquant**.
- Bonne variete de tons, palette riche.
- Dominance de `chaleureux` (28%) coherente avec le personnage de Papy Babou.

**Longueur des segments** :
- Sweet spot 8-45 mots : **135 segments (89%)**. Excellent.
- Courts <8 mots : 13 segments (9%). Tous >=4 mots. Acceptables en contexte dialogique (reactions courtes des enfants). Pas de segment < 4 mots.
- Longs >45 mots : 3 segments (2%). Maximum 50 mots (seg_072). Tous sont de Papy Babou (voix adulte, limite 60 mots) donc dans les limites, mais a la frontiere du sweet spot.

**Formulations TTS** :
- 0 onomatopee detectee (nettoyage deja effectue en Session 19).
- 0 syllabification avec tirets.
- 0 ellipsis problematique (`...`).
- Noms propres bien traites : `Pichone` et `Guihone` deja en phonetique francaise (seg_107).
- `Mesopotamie` : mot rare mais prononciable par TTS francais sans probleme.

**Pauses** :
- 0 segment avec pause 0ms.
- 0 segment avec pause >3000ms.
- Plage de pauses : 200-600ms. Bien calibre.
- Pauses longues (500-600ms) placees aux moments narratifs cles (cold open, transitions de jours, moment solennel). Pertinent.

**Points d'attention mineurs** :
- La forte concentration de `chaleureux` (42 segments) pourrait creer une monotonie vocale sur le TTS de Papy. Les ajustements dynamiques sont faibles pour ce ton (+0.05 stability, +0.05 style). Suggerer d'alterner avec `rassurant` (seulement 1 occurrence) pour varier le rendu.

### 2.2 SFX ElevenLabs : 6.5 / 10

C'est l'axe le plus faible. Plusieurs SFX contiennent des termes musicaux qu'ElevenLabs SFX ne peut pas generer, des descriptions abstraites/visuelles, et des risques de parole humaine.

**Descriptions en anglais** : Oui, toutes en anglais. Bien.

**Durees et modes** :
- Overlays : 10 au total. 5 overlays ont une duree < 15s (sfx_008: 6s, sfx_017: 8s, sfx_018: 8s, sfx_027: 8s, sfx_038: 5s). Les overlays courts risquent de se terminer avant la fin des segments voix qu'ils accompagnent.
- Inserts : 29 au total. Toutes les durees sont entre 3-8s, correct.

**Problemes identifies** : voir tableau section 3.

### 2.3 Flow audio : 8.5 / 10

**Alternance voix/SFX** :
- 39 SFX pour 151 voix = ratio 1:3.9. Bon.
- Repartition des SFX dans le script : concentres dans le premier tiers (cold open + debuts de jours) puis de plus en plus espaces vers la fin.

**Trous sonores (>10 segments voix sans SFX)** :
- 3 trous detectes :
  - seg_063 a seg_077 (entre sfx_023 et sfx_024) : **11 segments sans SFX** — passage sur les etoiles/Dakar, transition vers le gouter Mamie.
  - seg_105 a seg_115 (entre sfx_032 et sfx_033) : **11 segments sans SFX** — jardin d'Eden, Adam/Eve, Mamie romance.
  - seg_134 a seg_150 (entre sfx_038 et sfx_039) : **13 segments sans SFX** — recapitulatif, teasing, au revoir. C'est le plus gros trou.

**Overlays** :
- 10 overlays bien positionnes aux moments immersifs (ocean, foret, savane, jardin d'Eden).
- L'overlay sfx_038 (music box, 5s) est trop court pour couvrir le recapitulatif qui s'etend sur ~10 segments.
- Overlays longs (15-18s) sur les passages bibliques : bon design.

---

## 3. SFX problematiques

| ID | Probleme | Suggestion |
|----|----------|------------|
| sfx_004 | **Termes musicaux** : `orchestral swell`, `chimes cascading`, `string chord` — ElevenLabs SFX ne genere pas de musique orchestrale | `massive bright burst rising from silence, shimmering high-frequency metallic resonance cascading upward, warm sustained tonal hum expanding` |
| sfx_005 | **Termes musicaux** : `harp glissando` + **Abstrait** : `magical` | `bright descending metallic shimmer with sparkle texture, settling into warm indoor ambiance with soft fireplace crackling` |
| sfx_008 | **Risque parole** : `birds singing` + **Overlay trop court** : 6s pour couvrir 3+ segments | Remplacer `birds singing` par `birds chirping`. Augmenter duree a 15s minimum |
| sfx_010 | **Abstrait** : `magical transition`, `celestial atmosphere` — descriptions non-sonores | `low drone shifting upward in pitch with shimmering high-frequency shimmer, reverberant ambient pad building slowly over 5 seconds` |
| sfx_012 | **Termes musicaux** : `orchestral burst`, `chimes cascading`, `string chord` | `massive bright tonal burst rising from silence, shimmering high-frequency metallic resonance cascading outward, warm sustained low-frequency hum expanding` |
| sfx_013 | **Abstrait** : `celestial` — adjectif non-sonore | `single clear tubular bell chime ringing softly with long reverb tail, gentle resonance fading` |
| sfx_016 | **Abstrait** : `celestial`, `ethereal` | `single clear tubular bell chime ringing softly, bright metallic resonance with long reverb tail` |
| sfx_017 | **Overlay trop court** : 8s pour une ambiance foret qui devrait couvrir plusieurs segments | Augmenter a 18s minimum |
| sfx_018 | **Overlay trop court** : 8s | Augmenter a 15s minimum pour couvrir le passage Jour 4 |
| sfx_021 | **Couches spatiales conflictuelles** : `ocean depths bubbling` + `seagulls calling above waves` — sous l'eau ET mouettes au-dessus, impossible dans le meme prompt | Separer en 2 SFX ou retirer les mouettes : `ocean depths bubbling, whale song echoing, deep water ambiance with rising air bubbles` |
| sfx_025 | **Faux positif musical** : `elephants trumpeting` — c'est bien un son d'elephant, pas une trompette. **OK** | Aucune modification necessaire |
| sfx_027 | **Overlay trop court** : 8s pour un passage narratif long | Augmenter a 15s |
| sfx_030 | **Termes musicaux** : `choir singing`, `organ drone` + **Risque parole** : `choir singing sustained notes` — ElevenLabs va tenter de generer des voix chantees | `deep reverberant cathedral space ambiance, warm low-frequency tonal drone with harmonic overtones, sustained resonant pad` |
| sfx_031 | **Risque parole** : `first human breath` — pourrait generer du souffle vocal realiste | `slow deep inhalation followed by gentle exhale, heartbeat beginning with low rhythmic pulse, soft wind gust` |
| sfx_032 | **Abstrait** : `paradise garden` — non-sonore | `lush garden ambiance with gentle waterfall, exotic birds calling, warm peaceful breeze through tropical leaves` |
| sfx_035 | **Risque parole** : `various animal calls` est vague et pourrait produire des cris ambigus | `parade of soft hoofsteps on grass, low distant animal rumbles, gentle rustling in peaceful outdoor setting` |
| sfx_038 | **Termes musicaux** : `music box melody` + **Overlay trop court** : 5s pour couvrir le recapitulatif (~10 segments) | Remplacer par un SFX non-musical : `warm cozy room ambiance with soft clock ticking, gentle fireplace crackling, evening settling sounds`. Augmenter a 20s. |

---

## 4. Segments voix problematiques

| ID | Probleme | Suggestion |
|----|----------|------------|
| seg_013 | **Ultra-court** (4 mots) : "C'est quoi l'histoire ?" — TTS peut produire un rendu trop rapide/artificiel | Acceptable en contexte (question enfant), mais surveiller le rendu. Option : fusionner avec un segment adjacent |
| seg_115 | **Ultra-court** (4 mots) : "C'est romantique, Mamie !" | Idem, acceptable en dialogue naturel |
| seg_061 | **47 mots** (Papy) : passage Dakar/etoiles — segment long mais sous la limite 60 mots adulte | Acceptable. Envisager un split a la phrase "Quand j'etais petit a Dakar..." si le TTS perd en expressivite |
| seg_072 | **50 mots** (Papy) : passage Bible vs Science — le plus long du script | Proche de la limite. Candidate au split : "La Bible raconte le sens, le pourquoi." // "La science raconte le comment. Les deux sont importantes." |
| seg_111 | **48 mots** (Papy) : creation d'Eve — recit dense | Candidate au split apres "Dieu a pris une de ses cotes et il en a fait la femme. Eve." |
| seg_040 | Repetition "Firmament, firmament !" — le TTS pourrait produire un rendu mecanique sur la repetition | Acceptable, le ton `espiegle` + rythme `rapide` devrait aider. Surveiller le rendu |
| seg_099 | **47 mots** (Papy) : decouverte d'Adam — rythme `lent` sur un segment long pourrait etre monotone | Envisager un split apres "Et la premiere chose qu'il a vue, c'etait le ciel bleu et les arbres du jardin d'Eden." |

---

## 5. Top 5 ameliorations a plus fort impact

### 1. Remplacer tous les termes musicaux dans les SFX (CRITIQUE)
**Segments concernes** : sfx_004, sfx_005, sfx_012, sfx_030, sfx_038
**Impact** : ElevenLabs SFX ne genere pas de musique. Les termes `orchestral`, `harp`, `choir`, `organ`, `music box`, `strings` produiront soit du bruit incoherent, soit un silence. C'est le probleme le plus bloquant pour la production audio.
**Effort** : Faible — remplacer par des descriptions sonores concretes (drones, tonal bursts, metallic resonance).

### 2. Corriger les 5 overlays trop courts (HIGH)
**Segments concernes** : sfx_008 (6s), sfx_017 (8s), sfx_018 (8s), sfx_027 (8s), sfx_038 (5s)
**Impact** : Un overlay qui se termine avant la fin du dialogue cree un trou sonore brutal. L'ambiance disparait en plein milieu d'un passage, rompant l'immersion. Le monteur peut tronquer mais ne peut pas etendre.
**Effort** : Faible — augmenter les durees a 15-20s.

### 3. Combler les 3 trous sonores >10 segments (HIGH)
**Zones concernees** :
- seg_063-077 : Ajouter un overlay ambiance douce (salon, crackling fire) vers seg_068
- seg_105-115 : Ajouter un overlay jardin/nature vers seg_109
- seg_134-150 : Ajouter un overlay cozy room ambiance vers seg_136 (20s minimum pour couvrir le recapitulatif + au revoir)
**Impact** : 13 segments consecutifs sans SFX = ~2-3 minutes de voix seches. L'auditeur decroche. Ces zones correspondent a des moments emotionnels importants (recapitulatif, au revoir).

### 4. Eliminer le conflit spatial sfx_021 (MEDIUM)
**Impact** : `ocean depths` + `seagulls above waves` dans le meme prompt va confondre le modele. Le resultat sera incoherent car le modele ne peut pas generer simultanement un son sous-marin et un son aerien.
**Effort** : Faible — retirer les mouettes ou separer en 2 SFX.

### 5. Reduire le risque de parole humaine dans sfx_030 et sfx_031 (MEDIUM)
**Impact** : `choir singing sustained notes` et `first human breath` ont un risque eleve de generer du contenu vocal reconnaissable. Si le SFX contient de la parole, il entrera en conflit avec les segments TTS adjacents, creant une cacophonie.
**Effort** : Faible — reformuler avec des descriptions purement instrumentales/ambiantes.

---

## Annexe : Statistiques cles

| Metrique | Valeur | Statut |
|----------|--------|--------|
| Segments voix | 151 | OK |
| Segments SFX | 39 | OK (seuil min 8) |
| Tons dans TONE_VOICE_ADJUSTMENTS | 13/13 | OK |
| Segments sweet spot 8-45 mots | 89% | Excellent |
| Segments < 4 mots | 0 | OK |
| Segments > 60 mots (adulte) / > 40 (enfant) | 0 | OK |
| Onomatopees | 0 | OK |
| Pauses 0ms | 0 | OK |
| Pauses > 3s | 0 | OK |
| SFX avec termes musicaux | 6 | A corriger |
| SFX avec risque parole | 4 | A corriger |
| SFX avec descriptions abstraites | 6 | A corriger |
| Overlays < 15s | 5/10 | A corriger |
| Trous > 10 segments | 3 | A corriger |
| Conflit spatial | 1 | A corriger |
| Personnage dominant (Papy) | 52% | OK (ratio biblique) |
| Distribution enfants | 42% segments | OK (25-45%) |
