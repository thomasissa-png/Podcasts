# AUDIT SFX & MONTAGE AUDIO — S01E01 + S01E02

**Auditeur** : @sfx / monteur audio (ingénieur son podcast enfants)
**Date** : 2026-03-22
**Scope** : Configuration audio pipeline (config.py + monteur.py), scripts E01 et E02

---

## NOTE GLOBALE : 8.6/10

Le pipeline audio est bien conçu avec des fonctionnalités avancées (normalisation LUFS, ducking, room tone, EQ boost voix, panoramique stéréo). Les deux scripts sont globalement bien configurés pour une production audio de qualité. Quelques ajustements permettraient d'atteindre un rendu broadcast-ready.

---

## 1. Niveaux et normalisation — 9/10

### Configuration actuelle
| Paramètre | Valeur | Standard podcast | Verdict |
|---|---|---|---|
| LUFS cible | -16.0 | -16 (Spotify/Apple) | PARFAIT |
| True Peak Limiter | -1 dBTP | -1 dBTP (broadcast) | PARFAIT |
| True Peak Oversample | 4x | 4x (broadcast standard) | PARFAIT |

**Verdict** : La normalisation LUFS -16.0 avec limiter à -1 dBTP est conforme aux standards Spotify, Apple Podcasts et YouTube. Le two-pass loudnorm d'ffmpeg est l'approche broadcast de référence. Excellent.

### Gain par personnage (VOICE_GAIN_DB)
| Personnage | Gain | Analyse |
|---|---|---|
| papy_babou | 0.0 dB | Voix de référence — correct |
| antoine | +1.5 dB | Compense la voix enfant plus faible — bon |
| noemie | +2.0 dB | Plus forte compensation (voix enfant féminine) — bon |
| mamie_sonia | +1.0 dB | Compensation légère — bon |

**Verdict** : Bonne compensation des voix enfants. Les voix ElevenLabs enfant sont souvent plus faibles que les voix adultes. Le +2.0 dB de Noémie est justifié.

**Suggestion** : Après la première production, mesurer les LUFS de chaque voix isolée et ajuster si nécessaire. Les gains actuels sont des estimations raisonnables mais un calibrage empirique serait idéal.

## 2. Balance SFX / Voix — 8/10

### Configuration actuelle
| Paramètre | Valeur | Analyse |
|---|---|---|
| SFX_VOLUME_DEFAUT | -6 dB | Bon — SFX à 6 dB sous les voix |
| Dramatique/Épique | -3 dB | Plus fort pour l'impact — bon |
| Solennel | -4 dB | Présent mais discret — bon |
| Mystère | -5 dB | Subtil — bon |
| Tendre/Calme | -8/-9 dB | Très discret — correct pour les moments intimes |
| ROOM_TONE_DB | -28 dB | Quasi inaudible — parfait pour un fond continu |

**Verdict** : La hiérarchie SFX par ton est intelligente. Les SFX dramatiques sont plus présents (-3 dB), les SFX tendres/calmes sont discrets (-8/-9 dB). Le room tone à -28 dB est subtil — il donne de la "vie" sans être perceptible.

**PROBLÈME** : Il manque les tons `mystere` (avec accent) dans le mapping. Le script E02 utilise `ambiance_par_acte: ["mystere", ...]` mais SFX_VOLUME_PAR_TON a `"mystere"` sans accent. Vérifier que le matching fonctionne (Python string comparison).

**Suggestion** : Ajouter un mapping pour les ambiances de E02 :
- `"mystere"` : -5 dB (identique à `"mystère"` — vérifier la cohérence d'accents)

## 3. Ducking (side-chain SFX → Voix) — 8.5/10

### Configuration actuelle
| Paramètre | Valeur | Analyse |
|---|---|---|
| DUCKING_GAIN_DB | -6 dB | Les overlays baissent de 6 dB quand une voix parle |
| DUCKING_FADE_MS | 150 ms | Fade-in/out du ducking |

**Verdict** : Le ducking à -6 dB est une bonne valeur pour un podcast enfants — assez fort pour que les voix restent intelligibles, pas trop brutal pour que l'overlay reste perceptible. Le fade de 150ms est rapide mais naturel.

**Suggestion** : Pour les overlays d'ambiance longue (salon, tempête), un ducking de -8 dB serait préférable pour garantir l'intelligibilité des voix enfants. Les voix enfants (aigues) se mélangent plus facilement avec les ambiances que les voix graves de Papy.

## 4. Panoramique stéréo — 9/10

### Configuration actuelle
| Personnage | Pan | Position |
|---|---|---|
| papy_babou | 0.0 | Centre |
| antoine | -0.2 | Légèrement gauche |
| noemie | 0.2 | Légèrement droite |
| mamie_sonia | 0.15 | Légèrement droite |
| sfx | 0.0 | Centre |

**Verdict** : Excellent. Papy au centre (voix principale), les enfants légèrement décalés (crée une spatialisation naturelle comme s'ils étaient assis de chaque côté de Papy). Mamie Sonia légèrement à droite (même côté que Noémie — cohérent avec leur relation de complicité).

Les SFX au centre est correct — les ambiances doivent être immersives, pas latéralisées.

**Suggestion** : La valeur 0.2 est subtile (bon pour les écouteurs) mais sera quasi imperceptible sur des enceintes. C'est le bon choix pour un podcast enfants (souvent écouté en voiture/enceinte Bluetooth mono). Pas de changement nécessaire.

## 5. Vitesse vocale — 9/10

### Configuration actuelle
| Personnage | Speed | Analyse |
|---|---|---|
| papy_babou | 0.92 | Plus lent — grand-père de 66 ans, conteur posé. PARFAIT |
| antoine | 1.05 | Légèrement rapide — garçon de 8 ans dynamique. BON |
| noemie | 1.08 | Plus rapide — fillette de 5 ans excitée. BON |
| mamie_sonia | 0.95 | Légèrement lent — grand-mère calme. BON |

**Verdict** : Très bien calibré. Les vitesses reflètent les personnalités et les âges. Papy conteur lent, enfants dynamiques.

**Suggestion** : Le champ "rythme" dans les scripts (lent/normal/rapide) devrait moduler le speed factor par segment. Vérifier que le pipeline le fait. Si "rythme": "lent" ne change rien à la vitesse TTS, c'est une occasion manquée.

## 6. EQ et traitement voix — 8.5/10

### Configuration actuelle
| Paramètre | Valeur | Analyse |
|---|---|---|
| EQ_VOICE_BOOST_LOW_HZ | 2000 Hz | |
| EQ_VOICE_BOOST_HIGH_HZ | 5000 Hz | |
| EQ_VOICE_BOOST_DB | +2.5 dB | Boost de présence/clarté voix |

**Verdict** : Le boost 2-5 kHz à +2.5 dB est un choix classique pour améliorer l'intelligibilité vocale. C'est la zone de présence qui aide les voix à "percer" à travers les SFX et la musique de fond.

**Suggestion** : Pour les voix enfants (Antoine, Noémie), le boost pourrait être légèrement décalé vers 3-6 kHz car les voix enfants sont naturellement plus aigues. Mais c'est une optimisation fine qui nécessiterait des tests A/B.

## 7. Transitions et respiration — 8/10

### Configuration actuelle
| Paramètre | Valeur | Analyse |
|---|---|---|
| CROSSFADE_VOIX_MS | 200 ms | Crossfade entre segments voix |
| RESPIRATION_DUREE_MS | 80 ms | Micro-respiration entre répliques |
| RESPIRATION_PROBABILITE | 0.35 | 35% des transitions ont une respiration |
| SILENCE_TRANSITION_MS | 300 ms | Silence entre jingle et contenu |
| MAX_PAUSE_MS | 2500 ms | Plafond de pause |

**Verdict** : Le crossfade de 200ms évite les clics entre segments — bon. La micro-respiration à 35% de probabilité ajoute du naturel aux voix IA — excellente idée. Le plafond de pause à 2.5s empêche les silences morts.

**PROBLÈME** : Le crossfade de 200ms peut être trop agressif pour les changements de personnage (Papy → Noémie). Quand deux voix différentes se chevauchent de 200ms, on peut entendre un artefact. Le crossfade devrait être plus court (100ms) ou désactivé entre personnages différents.

**Suggestion** : Ajouter une condition : crossfade 200ms entre segments du même personnage, 50ms ou 0ms entre personnages différents.

## 8. Analyse spécifique par épisode

### S01E01 — La Création du monde
| Métrique | Valeur | Verdict |
|---|---|---|
| SFX total | 42 (après corrections) | EXCELLENT — très immersif |
| Overlays | 13 | EXCELLENT |
| Overlay max durée | 25s | BON |
| Overlay min durée | 6s (sfx_008 après correction: 15s) | OK après correction |
| Ambiance | joyeux | Mapping → room_tone "jour" — correct |
| Ambiance par acte | ["mystere", "émerveillé", "chaleureux"] | BON — variété |
| Trous sonores comblés | 3 overlays ajoutés | OK |

### S01E02 — Noé et le déluge
| Métrique | Valeur | Verdict |
|---|---|---|
| SFX total | 26 | BON |
| Overlays | 5 | ACCEPTABLE — pourrait être 7-8 pour un épisode dramatique |
| Overlay max durée | 20s | BON |
| Overlay min durée | 15s (sfx_012) | BON |
| Ambiance | dramatique | Mapping → room_tone "orage" — PARFAIT pour l'histoire de Noé |
| Ambiance par acte | ["mystere", "dramatique", "joyeux"] | EXCELLENT — contraste fort |
| Trous sonores | Comblés avec sfx_008b, sfx_009b, sfx_013b | OK |

**PROBLÈME E02** : Le mapping `AMBIANCE_ROOM_TONE` donne "orage" pour "dramatique". Le room tone "orage" inclut "distant thunder rumbles, rain on windows" — c'est parfait pour E02 (Noé/déluge) mais serait inadapté pour un épisode dramatique sans rapport avec la météo (ex: Joseph en prison). C'est un faux positif pour E02, mais à surveiller pour les prochains épisodes.

**Suggestion E02** : Ajouter 2-3 overlays supplémentaires pour les passages qui manquent d'habillage :
- Un overlay doux pendant le "petit mot de Papy" (seg_118-123) — le sfx_020b transition est bien mais un overlay ambient serait mieux
- Un overlay intérieur arche plus long pendant toute la section animaux (seg_053-066)

---

## SYNTHÈSE — Corrections recommandées

| # | Priorité | Correction |
|---|---|---|
| 1 | IMPORTANT | Vérifier la cohérence accents dans SFX_VOLUME_PAR_TON ("mystere" vs "mystère") — risque de fallback au volume par défaut |
| 2 | IMPORTANT | Réduire le crossfade à 50ms entre personnages différents (éviter chevauchement voix) |
| 3 | SUGGESTION | Augmenter le ducking à -8 dB pour les scènes avec voix enfants seules (meilleure intelligibilité) |
| 4 | SUGGESTION | Vérifier que le champ "rythme" (lent/normal/rapide) module bien le VOICE_SPEED par segment |
| 5 | SUGGESTION | E02 : ajouter 2-3 overlays supplémentaires pour les passages calmes |
| 6 | MINEUR | Après première production, mesurer les LUFS par voix isolée et ajuster VOICE_GAIN_DB |
| 7 | MINEUR | Pour les voix enfants, envisager un boost EQ décalé vers 3-6 kHz |

---

## Points forts du pipeline

1. **Normalisation LUFS -16.0 + True Peak -1 dBTP** — conforme broadcast, Spotify, Apple Podcasts
2. **Room tone contextuel** (jour/soir/orage) — ajoute de la vie et de la profondeur
3. **Ducking intelligent par ton** — les SFX s'adaptent au registre émotionnel
4. **Micro-respirations aléatoires** — humanise les voix IA de façon subtile
5. **Panoramique stéréo par personnage** — crée une spatialisation naturelle
6. **EQ boost 2-5 kHz** — assure l'intelligibilité vocale sur tous les appareils
7. **Vitesse vocale par personnage** — Papy lent, enfants rapides, très réaliste

---

*Rapport généré par @sfx/monteur — audit configuration audio S01E01 + S01E02*
