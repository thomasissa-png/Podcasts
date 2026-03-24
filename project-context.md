# Project Context — Les Histoires de Papy Babou

## Identite
- **Nom du projet** : Les Histoires de Papy Babou
- **Secteur** : Podcast pour enfants de 5 a 10 ans — histoires bibliques racontees en famille, format audio immersif avec personnages recurrents
- **Stade** : Beta (S01E01 script valide 9.2/10, S01E02 script valide 9.0/10, pipeline de production audio fonctionnel, site web public en ligne)
- **Type** : Podcast seriel (10 episodes/saison, arcs narratifs, personnages recurrents, rituels)

## Cible
- **Persona principal** : Sophie, 45 ans, parent catholique pratiquante, 3 enfants (6, 9, 12 ans). Cherche un podcast qui transmette la foi de maniere joyeuse sans moralisation. Compare la qualite audio avec Les Odyssees (France Inter). Frustration : les supports catechetiques existants sont ennuyeux pour ses enfants, les livres audio bibliques sont monotones, et il n'existe aucun podcast francais d'histoires bibliques en format narratif immersif. Poids dans les decisions : 40% (c'est elle qui decide d'installer le podcast, de l'ecouter en famille, et de le recommander).
- **Persona secondaire 1** : Lina, 7 ans (fille, CE1). Attention 15-20 min. Adore Noemie (identification). Sensible a la peur — les passages trop sombres la bloquent. Veut des histoires avec de l'humour, des animaux, et du merveilleux. Poids : 30%.
- **Persona secondaire 2** : Noah, 10 ans (garcon, CM2). Trouve les trucs "pour bebes" ennuyeux. Veut de l'action, des faits scientifiques, de la credibilite. Compare avec Les Odyssees et Quelle Histoire. Si c'est "trop bebe", il decroche en 3 minutes. Poids : 30%.
- **Probleme principal** : Il n'existe aucun podcast francais pour enfants qui raconte les histoires de la Bible en format narratif immersif (personnages, SFX, musique). Les parents catholiques doivent choisir entre : livres audio monotones, catechisme formel ennuyeux pour les enfants, ou podcasts laiques de qualite (Les Odyssees) qui ne couvrent pas la Bible.
- **Alternative actuelle** : Livres audio bibliques (Audible, CD paroissiaux), catechisme en paroisse, podcasts generalistes (Les Odyssees, Quelle Histoire — pas bibliques), videos YouTube (ecrans, pas audio)

## Positionnement
- **Promesse unique** : Le seul podcast ou vos enfants ne sont pas spectateurs — ils participent a l'aventure biblique avec Papy Babou, en posant des questions, en resolvant des enigmes, et en decouvrant des fun facts scientifiques. Un moment familial divertissant pour se cultiver et decouvrir les grandes histoires de la Bible, sans etre un cours de catechisme.
- **Ton de marque** : Bienveillant et chaleureux, adapte aux enfants. Expert sur le fond biblique mais jamais moralisateur. Emerveillement et humour plutot que lecons. "On guide sans jargon, on rassure sans simplifier."
- **3 mots** : Bienveillant, Aventures, Experience audio
- **Concurrent principal** : Podcast "Les aventures de Tina" (histoires pour enfants, pas biblique, excellents avis), Podcast "Les voyages d'Amelia" (histoires pour enfants, pas biblique, excellents avis). Benchmark qualite : Les Odyssees (France Inter — histoires historiques, pas biblique, reference production audio). Notre difference : seul podcast narratif immersif sur les histoires bibliques en francais, avec format interactif (questions des enfants, fun facts, running gags).

## Objectifs
- **Objectif principal a 6 mois** : 3000 ecoutes par mois, saison 1 complete (10 episodes produits et publies), presence sur Apple Podcasts + Spotify + site web
- **KPI North Star** : Nombre d'ecoutes completes mensuelles (3000 ecoutes completes/mois = seuil de visibilite pour les annonceurs podcast). Une ecoute complete = episode ecoute jusqu'au bout.

## Stack technique
- **Frontend** : Templates HTML/CSS/JS (Jinja2) servis par Flask — `public.html` (site public), `dashboard.html` (admin), `admin_login.html`
- **Backend** : Python 3 + Flask + Gunicorn (gthread, 1 worker x 8 threads, timeout 3900s). Pipeline de production complet : 10 agents Python specialises (scripteur, reviewer, directeur_podcast, producteur_audio, sfx_provider, monteur, metadonnees, publisher, cover_art, planificateur). 5 agents d'audit (audit-sfx, audit-voix, audit-marc, audit-claire, audit-episode). Systeme de checkpoints atomiques, SIGTERM survival, auto-resume apres redeploy.
- **Base de donnees** : PostgreSQL (Neon, scale-to-zero) comme stockage primaire + JSON files comme fallback + Replit Object Storage pour persistence apres redeploy. 9 prefixes Object Storage (audio/, scripts/, rapports/, saisons/, checkpoints/, segments/, metadonnees/, chapters/, covers/).
- **Hebergement** : Replit (https://podcasts-toum92.replit.app/)
- **IA utilisee** : Claude API (Anthropic) pour generation de scripts, review, metadonnees, planification de saison, direction creative. ElevenLabs pour TTS (voix par personnage, 17 tons dynamiques) + generation SFX. OpenAI DALL-E 3 pour cover art. Freesound pour SFX fallback. Systeme de preferences producteur (24 regles) injectees automatiquement dans les prompts.
- **Tests** : 577+ tests pytest (regression, qualite creative, integration)
- **Audio** : ffmpeg pour montage, LUFS normalization, master bus (EQ + compression + true peak limiter), room tone, crossfade 200ms, micro-respirations, ducking SFX, stereo panning par personnage

## Modele economique
- **Type** : Podcast gratuit — monetisation par publicites sur les plateformes de podcast (Apple Podcasts, Spotify), sponsoring potentiel de marques familiales/chretiennes
- **Pays** : France
- **Donnees sensibles** : Non (pas de comptes utilisateurs, pas de donnees enfants collectees — uniquement newsletter email optionnelle)

## Budget & Contraintes
- **Budget infra mensuel** : Pas de limite stricte, optimisation intelligente. Couts principaux : API Claude (~$2-5/episode script), ElevenLabs (~$5-10/episode TTS+SFX), Replit hosting, Neon PostgreSQL (free tier), OpenAI DALL-E 3 (~$0.04/cover si pas de cover custom)
- **Budget acquisition mensuel** : A definir (actuellement 0 — aucun reseau social, aucune base email)
- **Timeline** : Lancement apres production complete des 10 episodes de la saison 1. Distribution Apple Podcasts + Spotify une fois les 10 episodes prets.
- **Contraintes specifiques** : Production audio longue (~30-45 min par episode sur Replit, sujet aux redeploys SIGTERM). Episodes imposes pour les 3 premieres saisons (10 histoires bibliques par saison, pas de generation libre). Regle absolue : 1 sujet biblique complet par episode, jamais de multi-part.

## Presence existante
- **Reseaux sociaux** : Aucun
- **Site web existant** : https://podcasts-toum92.replit.app/ — site public fonctionnel avec lecteur audio, page episodes, FAQ, newsletter. Admin dashboard pour production et monitoring.
- **Base email** : Aucune (formulaire newsletter present mais pas de subscribers)
- **Plateformes podcast** : Non encore distribue (RSS genere mais pas soumis a Apple/Spotify)

## Contenu existant
- **Saison 1** : Plan valide (10 episodes imposes), S01E01 script 9.2/10, S01E02 script 9.0/10
- **Saison 2** : Plan defini (La vie de Jesus, 10 episodes imposes)
- **Saison 3** : Plan defini (Apotres et grands saints, 10 episodes imposes)
- **Bible personnages** : 4 personnages principaux documentes (Papy Babou, Antoine 8 ans, Noemie 5 ans, Mamie Sonia) avec relations, tics de langage, backstories
- **Preferences producteur** : 24 regles obligatoires pour la qualite des scripts
- **Design** : Identite visuelle complete (palette CSS, avatars, cover podcast, favicon, OG image)

## Notes libres
Projet personnel porte par un parent chretien. Pas de budget marketing pour l'instant — la priorite est de produire les 10 episodes de la saison 1 avec une qualite audio irreprochable, puis de distribuer sur les plateformes (Apple Podcasts, Spotify, Google Podcasts). L'acquisition viendra apres la production. Le site web est deja en ligne et fonctionnel.

Le pipeline de production est extremement sophistique (28 sessions de developpement, 577+ tests) mais la production audio elle-meme n'a pas encore demarre — les 2 premiers scripts sont valides et attendent la production TTS/SFX/montage.

Niveau technique de l'utilisateur : technique (gere le code, les API, le deploiement). Communication en mode technique acceptee.

## Historique des interventions agents
| Agent | Date | Fichiers | Decisions cles | Pourquoi |
|---|---|---|---|---|
| orchestrator | 2026-03-22 | docs/reviews/audit-59-prompts.md, docs/orchestration-plan.md | Audit des 59 prompts Gradient Agents (contexte framework, pas podcast) | Installation du framework Gradient Agents |
| @design + @ux + @copywriter | 2026-03-22 | templates/public.html | 22 fixes UX/design/copy sur le site public (score 7.5/10) | Audit 3-agents du site public |
| orchestrator (@design + @ux) | 2026-03-24 | templates/admin_v2.html, docs/reviews/admin-v2-mobile-audit.md | 16 fixes mobile (4 P0 + 12 P1), score 5.4 -> 8.3/10 | Audit UX+Design back-office V2 focus mobile : hamburger nav, touch targets 44px, card layout mobile, segment actions full-width |

## Performance des agents
| Agent | Date | Critere 1 (Pertinence) | Critere 2 (Completude) | Critere 3 (Coherence) | Critere 4 (Actionnable) | Critere 5 (Format) | Moyenne |
|---|---|---|---|---|---|---|---|
| (pas encore de donnees pour ce projet) | | | | | | | |
