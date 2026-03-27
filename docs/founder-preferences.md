# Preferences Fondateur — Les Histoires de Papy Babou

Detectees au fil des sessions. A respecter par tous les agents.

## Communication & Marque

- **"Catechisme" banni** : ne jamais utiliser ce mot dans la communication publique (site, reseaux sociaux, descriptions podcast, emails). Ecarte immediatement le persona Camille (parent non-pratiquant). Alternatives : "histoires bibliques", "grandes histoires de la Bible", "aventures bibliques".
- **Camille = persona de croissance prioritaire** : le marche des parents catho-culturels / non-pratiquants est 5x plus grand que les pratiquants reguliers. Toute communication doit parler aux deux personas (Sophie ET Camille) sans exclure l'un.
- **Ton bienveillant, jamais moralisateur** : le podcast n'est pas un cours de religion. C'est un moment familial d'emerveillement et de culture.

## Methode de travail

- **Workflow bout-en-bout d'abord** : le fondateur prefere avoir un flux complet qui fonctionne (de la generation de script a la publication) avant d'optimiser les details. Ne pas sur-polir une etape si la suivante n'est pas operationnelle.
- **Strategie et specs avant le code** : commencer par poser le cadre (positionnement, personas, specs) avant de coder. Les agents strategiques passent en premier.
- **Niveau technique expert** : communication en mode technique acceptee. Pas besoin de simplifier les explications techniques.

## Outils & Stack

- **Umami > GA4** : choix delibere pour le tracking analytics. Pas de Google Analytics, pas de cookie banner. Umami deja implemente dans public.html.
- **Replit** : hebergement principal. Contraintes connues et acceptees (redeploys SIGTERM, filesystem ephemere, Object Storage comme persistence).

## Production audio

- **Seuil 9/10 sur 4 auditeurs** : aucun script ne passe en production audio sans score >= 9/10 sur les 4 auditeurs (Thomas/SFX, Isabelle/Voix, Marc/Creatif, Claire/Creatif).
- **1 sujet biblique complet par episode** : jamais de multi-part, jamais de "suite au prochain episode" sur la meme histoire.
- **10 episodes par saison** : episodes imposes pour les 3 premieres saisons (pas de generation libre par le LLM).
- **Verification seg_003 obligatoire** : apres chaque lancement de production audio, verifier que seg_003 correspond au script attendu. Protocole non contournable apres 4 echecs historiques.

## Decisions irrevocables (ne pas remettre en question)

- Episodes S1 imposes (10 histoires bibliques specifiques)
- Archetype de marque : Sage Conteur
- Tagline : "Des histoires qui grandissent avec eux"
- 24 regles de production dans preferences_producteur.json
- Structure 5 actes pour chaque episode
