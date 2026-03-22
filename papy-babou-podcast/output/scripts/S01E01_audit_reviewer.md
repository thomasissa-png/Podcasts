# Audit de coherence — S01E01 "La creation du monde"

**Auditeur** : Reviewer senior qualite
**Date** : 2026-03-22
**Script** : `output/scripts/S01E01_script.json` — 151 segments voix + 39 SFX = 190 segments
**Score directeur** : 9.2/10 (feu vert)

---

## 1. Coherence avec le plan de saison — 8/10

### Conforme
- **Titre** : identique au plan ("La creation du monde -- quand Dieu a tout invente")
- **Morale** : presente et fidele (seg_139-140 : "le monde est un cadeau merveilleux dont il faut prendre soin")
- **Pretexte rentre/fleurs** : Noemie demande "c'est qui qui a fait les fleurs" dans le jardin (seg_009)
- **Arc Noemie/emerveillement** : moteur de l'episode, nombreuses reactions emerveillees, liens avec Lucas
- **Lien Lucas/bebe** (fil rouge) : Noemie compare Adam a Lucas (seg_100), Antoine mentionne "le bebe qui va arriver" (seg_141)
- **Recap 6 jours par Antoine** : seg_134-135, recite les 6 jours dans l'ordre
- **Anecdote Papy etoiles Dakar** : seg_061, "quand j'etais petit a Dakar [...] du sucre renverse sur une nappe noire"
- **Mamie Sonia / alphabet de Dieu** : seg_083, fidele au plan
- **Noemie / respiration Adam = Lucas** : seg_100-101, fidele

### Ecarts
- **Teasing E02** : Le plan dit "le plus grand bateau jamais construit" (Noe). Le script tease le jardin d'Eden / fruit defendu (seg_142-146). **Non conforme** au plan. Le teasing actuel pointe vers Adam & Eve, pas vers Noe E02.
  - **Severite** : IMPORTANT — le plan de saison a ete modifie (E02 = Noe), le teasing doit etre realigne.
- **Moments cles du plan d'episode (saison_01.json lignes 67-71)** : Le plan de l'episode demande "Noemie qui imite les animaux" et "Antoine fascine par les etoiles et combien il y en a". Noemie n'imite pas les animaux (elle les commente seulement). Antoine ne demande pas combien il y a d'etoiles. Ecart mineur, l'esprit est respecte.
- **Duree cible** : le plan de saison dit 20 min (ligne 54), le script dit 30 min (ligne 7). Incoherence entre les deux documents. Avec ~3300 mots, la duree reelle sera proche de 25-30 min.

---

## 2. Respect de la bible des personnages — 9/10

### Papy Babou
- **Tics utilises** : "mes petits loups" (x8+), "Figurez-vous" (absent), "formidable" (absent), "extraordinaire" (seg_012, seg_086), "mes tresors" (absent), "Et devinez quoi" (seg_047 variante "Devinez ce qui va se passer")
- **Ton** : chaleureux, bienveillant, grave — conforme
- **Pas d'argot** : conforme
- **Backstory** : Dakar (seg_061), Afrique du Sud/baobab (seg_059), Liban (seg_109) — excellent usage
- **Manque** : "figurez-vous" et "formidable" absents. Deux tics signature manquants.

### Antoine (8 ans)
- **Tics** : "Mais Papy pourquoi" (seg_033 variante), "Trop cool" (absent — remplace par "C'est genial" seg_149), "C'est incroyable" (seg_132 variante "C'est quand meme incroyable"), "Comme un super-heros" (seg_118)
- **Max 40 mots** : seg_072 = 39 mots (limite), seg_065 = 36 mots. Conforme.
- **Curiosite scientifique** : excellente (vitesse lumiere seg_025, taille soleil seg_053, baleine seg_065, dinosaures seg_069-071)

### Noemie (5 ans)
- **Tics** : "C'est trop drole" (seg_094), "Le pauvre" (absent). "C'est pas juste" (seg_082, seg_147 — coherent avec son gros caractere)
- **Max 40 mots** : seg_137 = 35 mots (max observe). Conforme.
- **Chipie/espiegle** : oui (pomme a croquer seg_035, Long-Cou/Gros-Nez seg_120, "C'est pas juste" x2)
- **Interdiction phrases longues (max 10-12 mots)** : seg_100 = 12 mots, seg_137 = 35 mots. **seg_137 depasse largement la limite de 12 mots** pour Noemie. Idem seg_094 (16 mots).
  - **Severite** : IMPORTANT — la bible dit "max 10-12 mots par replique" pour Noemie. Plusieurs repliques depassent.
- **"Le pauvre"** : absent. Un tic signature manquant.

### Mamie Sonia
- **Premiere apparition** : la bible dit `premiere_apparition: S01E02`. Le plan de saison (ligne 59-61) dit `personnages_secondaires_presents: []` pour E01. **Le script l'inclut avec 8 repliques substantielles.**
  - **Severite** : IMPORTANT — incoherence directe avec la bible ET le plan de saison. Cependant, les moments_cles du script JSON (ligne 25-26) la mentionnent, ce qui indique une decision deliberee au niveau du script. La qualite des interventions de Mamie est excellente (sables, alphabet de Dieu, rencontre au Liban).
- **Tics** : "Mes petits cheris" (seg_078, seg_151), "Votre Papy exagere toujours un peu" (seg_112) — conformes a la bible
- **Ton doux/chaleureux** : conforme

---

## 3. Respect des preferences producteur — 8.5/10

### SFX
- **En anglais** : tous les 39 SFX sont en anglais. Conforme.
- **Sons reproductibles** : grande majorite conforme. Quelques ecarts :
  - sfx_004 : "massive orchestral swell rising from silence to fortissimo" — contient de la **musique orchestrale**. Interdit par les preferences ("pas de musique orchestrale" implicite dans les regles SFX).
  - sfx_005 : "soft harp glissando descending" — instrument de musique, pas un bruitage.
  - sfx_012 : "bright orchestral burst" — meme probleme.
  - sfx_030 : "gentle ethereal choir singing" — risque de parole humaine. Les preferences disent "voices -> remplacer par laughing/cheering".
  - sfx_031 : "first human breath, heartbeat beginning, gentle wind of life" — "wind of life" est abstrait.
  - sfx_010 : "magical transition into ancient world, celestial atmosphere building slowly" — "magical" et "ancient world" sont abstraits, "celestial" est visuel/abstrait.
  - **Severite** : MINEUR a IMPORTANT selon le SFX — 6-7 SFX sur 39 ont des problemes de conformite.
- **Pas de descriptions visuelles** : sfx_027 "wolves howling at sunset" — "sunset" est visuel. Mineur.

### Voix TTS
- **Pas d'onomatopees** : conforme. Aucune detectee.
- **Pas d'ellipses** : conforme. Aucune "..." detectee.
- **Nombres en lettres** : seg_025 "sept fois", seg_053 "trente metres" — conforme.
- **Max 60 mots Papy** : seg_072 a 60 mots, seg_111 a 59 mots. Conforme (limite).
- **Max 40 mots enfants** : conforme (verifie ci-dessus).

### Un seul sujet biblique complet
- La Creation du monde en 6 jours + repos 7e jour. Complet de A a Z. Conforme.

---

## 4. Regles d'interaction — 9/10

### Frequence interventions enfants (~90s)
- Les enfants interviennent tres regulierement. Estimation : toutes les 60-90 secondes en moyenne. La plus longue sequence de Papy seul est seg_097-seg_099 (~3 segments, ~40s). Conforme.

### Alternance Antoine/Noemie
- Bonne alternance tout au long du script. Pas de longue sequence monopolisee par un seul enfant.
- Antoine : questions logiques/scientifiques (lumiere, dinosaures, soleil). Conforme.
- Noemie : blagues, chipie, emerveillement (pomme, bottes, marguerites). Conforme.

### Running gag gouter
- Installe par Mamie Sonia (seg_078 : sables etoiles), Noemie demande a manger (seg_080), Mamie dit "apres l'histoire" (seg_081), Noemie proteste "c'est pas juste" (seg_082). Running gag bien installe.
- Antoine ne dit pas explicitement "Chut, laisse Papy finir" (variante du rituel). Ecart mineur.

### Dynamique fratrie
- Antoine explique a Noemie (seg_010 "C'est la nature, Noemie"), interactions directes presentes mais limitees. La dynamique de taquinerie/protection est peu exploitee.
  - **Severite** : MINEUR — peu d'interactions directes entre frere et soeur.

---

## 5. Qualite SFX pour ElevenLabs — 7.5/10

### Points positifs
- 39 SFX au total — tres genereux
- Descriptions en anglais, majoritairement specifiques et concretes
- Durees variees et adaptees (3s a 18s)
- Bonne utilisation overlay/insert : overlays pour les ambiances longues, inserts pour les ponctuels
- Signature "celestial chime" entre chaque jour — excellent marqueur structurant

### Problemes detectes

| SFX | Probleme | Severite |
|-----|----------|----------|
| sfx_004 | "massive orchestral swell rising from silence to fortissimo, bright shimmering chimes" — musique orchestrale, pas un bruitage | IMPORTANT |
| sfx_005 | "soft harp glissando descending" — instrument musical | MINEUR |
| sfx_010 | "magical transition into ancient world" — abstrait, non reproductible | IMPORTANT |
| sfx_012 | "bright orchestral burst rising from silence, shimmering high-frequency chimes, warm sustained string chord" — musique orchestrale | IMPORTANT |
| sfx_021 | "ocean depths bubbling, whale song echoing, seagulls calling above waves" — couches spatiales conflictuelles (profondeur ocean + mouettes en surface) | MINEUR |
| sfx_027 | "wolves howling at sunset" — "sunset" = description visuelle | MINEUR |
| sfx_030 | "gentle ethereal choir singing sustained notes" — risque de parole humaine | IMPORTANT |
| sfx_031 | "first human breath, heartbeat beginning, gentle wind of life" — "wind of life" = abstrait | MINEUR |
| sfx_032 | "paradise garden ambiance" — "paradise" = concept abstrait | MINEUR |
| sfx_038 | "warm gentle music box melody playing softly" — musique, pas bruitage | MINEUR |

---

## Notes par axe

| Axe | Note | Justification |
|-----|------|---------------|
| 1. Coherence plan de saison | **8/10** | Teasing E02 non conforme (Eden au lieu de Noe), duree cible incoherente (20 vs 30 min), 2 moments cles manquants |
| 2. Bible personnages | **9/10** | Tres bon respect global. Noemie depasse la limite 12 mots. Mamie presente malgre S01E02 prevu. Tics mineurs absents |
| 3. Preferences producteur | **8.5/10** | SFX en anglais, TTS propre, 1 sujet complet. Quelques SFX avec musique orchestrale/abstrait |
| 4. Regles d'interaction | **9/10** | Frequence, alternance et running gag bien respectes. Dynamique fratrie un peu faible |
| 5. Qualite SFX ElevenLabs | **7.5/10** | 39 SFX genereux, mais 4 contiennent de la musique orchestrale et 3 ont des descriptions abstraites |

### Note globale : 8.4/10

---

## Problemes par severite

### CRITIQUES (0)
Aucun probleme bloquant la production.

### IMPORTANTS (5)

| # | Axe | Probleme | Correction proposee |
|---|-----|----------|-------------------|
| I1 | Plan | Teasing E02 pointe vers Eden/fruit defendu au lieu de Noe/deluge | Remplacer seg_142-146 : "la prochaine fois, je vous raconterai l'histoire du plus grand bateau jamais construit et pourquoi il a fallu le construire" |
| I2 | Bible | Noemie seg_137 = 35 mots (max bible = 10-12 mots/replique) | Decouper en 2 repliques ou simplifier : "Moi j'ai retenu que Dieu il a dit que c'etait tres beau. Et il s'est repose !" |
| I3 | Bible | Mamie Sonia presente en E01 alors que bible dit premiere_apparition = S01E02 et plan dit personnages_secondaires = [] | Decision a prendre : soit modifier la bible/plan pour officialiser sa presence en E01, soit retirer ses 8 repliques. Vu la qualite, recommandation = mettre a jour la bible. |
| I4 | SFX | sfx_004, sfx_012 : musique orchestrale ("orchestral swell", "orchestral burst", "string chord") | Remplacer par des equivalents non-musicaux : "massive low-frequency swell building with resonant sub-bass" / "bright shimmering high-pitched tones cascading upward with warm reverberant pad" |
| I5 | SFX | sfx_030 : "choir singing" = risque de parole humaine generee par IA | Remplacer par "sustained warm organ drone with layered harmonic overtones, reverberant cathedral space ambiance" |

### MINEURS (8)

| # | Axe | Probleme | Correction proposee |
|---|-----|----------|-------------------|
| M1 | Bible | "figurez-vous" et "formidable" absents (tics signature Papy) | Inserer au moins 1 "figurez-vous que" et 1 "formidable" dans les segments de Papy |
| M2 | Bible | "Trop cool" absent pour Antoine | Remplacer "c'etait genial" (seg_149) par "C'etait trop cool, Papy !" |
| M3 | Bible | "Le pauvre" absent pour Noemie | Ajouter une replique "Le pauvre Adam, il etait tout seul !" avant seg_110 |
| M4 | Plan | Noemie n'imite pas les animaux (moment cle prevu) | Ajouter une replique ou Noemie fait des bruits d'animaux (attention : SFX doit le faire, pas le TTS) |
| M5 | Plan | Duree cible 20 min dans le plan vs 30 min dans le script | Harmoniser — le format "ouverture" fait 30 min selon les regles, mettre a jour le plan de saison |
| M6 | SFX | sfx_010 : "magical transition into ancient world" — abstrait | Remplacer par "ethereal shimmer pad rising slowly with tubular bell resonance fading in" |
| M7 | SFX | sfx_021 : couches spatiales conflictuelles (ocean profond + mouettes) | Separer en 2 SFX ou retirer "seagulls calling above waves" |
| M8 | Interaction | Peu d'interactions directes Antoine-Noemie (taquinerie, protection) | Ajouter 1-2 echanges frere-soeur (ex: Antoine qui leve les yeux au ciel quand Noemie dit "Long-Cou") |

---

## Resume des corrections prioritaires

1. **Realigner le teasing E02** sur Noe/deluge (obligatoire si E02 = Noe)
2. **Decouper les repliques longues de Noemie** (seg_137, seg_094, seg_100)
3. **Officialiser Mamie Sonia en E01** dans la bible et le plan de saison
4. **Corriger les 4-5 SFX orchestraux/abstraits** pour conformite ElevenLabs
5. **Ajouter les tics manquants** ("figurez-vous", "formidable", "trop cool", "le pauvre")
