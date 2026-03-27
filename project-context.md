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

### Memo de reprise — Session du 2026-03-26

**Etat global** : Phase 0 (Strategie) et Phase 1 partielle (Specs/QA) terminees. 16 livrables produits dans docs/. Pipeline de production audio pret mais aucun episode en production audio.

**Travaux termines cette session** :
- Brand platform, personas, benchmark concurrentiel, creative brief (@creative-strategy)
- KPI framework avec mapping features (@data-analyst)
- Product vision, roadmap, backlog, functional specs (@product-manager)
- Value proposition, brand voice (@creative-strategy, @copywriter)
- QA strategy + 19 tests routes critiques (@qa)
- Backend audit (@infrastructure) — bugs P0 confirmes deja corriges
- Umami tracking confirme operationnel (@fullstack)
- Fix montage count mismatch dans web.py (6 lignes)
- Protocole de cloture : docs/lessons-learned.md, docs/founder-preferences.md

**Travaux en cours / a faire** :
1. **PRIORITE 1** : Lancer production audio S01E01 via web dashboard (script valide 9.2/10, checkpoint pret)
2. **PRIORITE 2** : Auditer scripts E03 (Abraham) et E04 (Joseph) — scripts presents mais non audites par @audit-episode
3. **PRIORITE 3** : Ecrire scripts E05-E10 (Moise, David, Salomon, Daniel, Jonas, Esther)
4. **PRIORITE 4** : 5 questions fondateur Phase 2 SaaS (docs/product/product-vision.md section Phase 2)
5. **P2** : CSRF + rate limiting login, newsletter backend, V2 admin JS incomplet

**Decisions a ne pas revenir dessus** :
- Umami (pas GA4) pour le tracking
- "catechisme" banni de toute communication publique
- Camille (parent non-pratiquant) = persona de croissance prioritaire
- 1 sujet biblique complet par episode, jamais de multi-part
- Seuil 9/10 sur 4 auditeurs avant production audio

**Branche git actuelle** : `claude/install-gradient-agents-23sK6`

## Historique des interventions agents
| Agent | Date | Fichiers | Decisions cles | Pourquoi |
|---|---|---|---|---|
| orchestrator | 2026-03-22 | docs/reviews/audit-59-prompts.md, docs/orchestration-plan.md | Audit des 59 prompts Gradient Agents (contexte framework, pas podcast) | Installation du framework Gradient Agents |
| @design + @ux + @copywriter | 2026-03-22 | templates/public.html | 22 fixes UX/design/copy sur le site public (score 7.5/10) | Audit 3-agents du site public |
| orchestrator (@design + @ux) | 2026-03-24 | templates/admin_v2.html, docs/reviews/admin-v2-mobile-audit.md | 16 fixes mobile (4 P0 + 12 P1), score 5.4 -> 8.3/10 | Audit UX+Design back-office V2 focus mobile : hamburger nav, touch targets 44px, card layout mobile, segment actions full-width |
| @reviewer | 2026-03-24 | docs/reviews/cross-review-montage-workflow.md | NO-GO publication : 2 BLOQUANTS (chemin copie audio errone dans publish V1+V2), 3 MAJEURS (depublish sans suppression fichier, IDs V1 instables, publish-v1 sans RSS/historique), 3 HAUTS (path traversal, depublish V1 impossible, publish V1 sans flag DB). Score 4.5/10. | Revue croisee du workflow montages → publication → homepage. Bugs de chemin filesystem decouverts : les 2 endpoints publish copient vers output/episodes/audio/episodes/ au lieu de output/episodes/ |
| @reviewer | 2026-03-24 | docs/reviews/cross-review-segment-namespacing.md | GO avec reserves (main.py 9/10), NO-GO routes V2 admin (3/10). 2 BLOQUANTS : arguments inverses upload_file web.py:4502/5028/5031, chemin OUTPUT_DIR au lieu de SEGMENTS_DIR dans 8 endroits web.py. 1 MAJEUR : purge launch-fresh au mauvais chemin. 0 tests. Score global 6.5/10. | Revue croisee du refactoring segment namespacing (isolation segments audio par production_run_id). Branche principale solide, routes V2 admin cassees. |
| @creative-strategy | 2026-03-25 | docs/strategy/brand-platform.md, docs/strategy/personas.md, docs/strategy/competitive-benchmark.md, docs/strategy/creative-brief.md | Positionnement : espace libre identifie (Bible + seriel + immersif + voix multiples + 25-35 min = aucun concurrent). Archetype Sage Conteur. Tagline "Des histoires qui grandissent avec eux". 4 personas (Sophie/Lina/Noah + Camille parent non-pratiquant). Competitor Biblus comme seul concurrent direct. Deux registres de communication identifies (catholique pratiquant vs catho-culturel). | Benchmark 5 concurrents (WebSearch mars 2026). Camille (parent non-pratiquant) identifie comme levier de croissance majeur : marche 5x plus grand que les pratiquants reguliers. Mot "catechisme" banni de la communication publique. Claims LLM-ready rediges pour citabilite Perplexity/ChatGPT. |
| @data-analyst | 2026-03-25 | docs/analytics/kpi-framework.md | North Star = 3 000 ecoutes completes/mois (>= 80% duree). 4 personas avec metriques de validation indirectes. Outils retenus : GA4 + Spotify for Podcasters + Apple Podcasts Connect (budget 0). A/B testing non viable avant 6 mois (trafic < 1 000/mois au lancement). | Projet pre-lancement sans donnees — toutes cibles marquees [HYPOTHESE]. Lina/Noah = comportements observables indirects sur l'appareil parental. Camille valide via proportion trafic non-confessionnel (KPI actionnable sans budget). |
| @product-manager | 2026-03-25 | docs/product/product-vision.md (mis a jour), docs/product/roadmap.md (mis a jour), docs/product/backlog.md (cree) | Vision 2 phases (S1 production → SaaS). 3 bugs P0 BLOQUANTS identifies (chemins publish, arguments upload_file inverses, SEGMENTS_DIR V2). 5 questions fondateur pour Phase 2. Backlog 15 stories avec priorisation MoSCoW + RICE. Connexion explicite au North Star 3 000 ecoutes. | Les 2 premiers livrables existaient deja (produits plus tot dans la journee) — mis a jour pour corriger le statut reel E03/E04 (scripts valides presents mais audit manquant). Backlog cree de zero. Pas de Phase 2 detaillee : les 5 questions fondateur (B2B/B2C, pricing, customisation, no-code, timeline) doivent etre repondues avant tout dev. Bugs P0 priorises absolus avant toute production audio — sans eux aucun episode n'est publiable. |
| @data-analyst | 2026-03-25 | docs/analytics/kpi-framework.md (section 3 ajoutee) | Mapping feature→KPI pour les 14 stories du backlog. 5 features P0/P1 avec chemin de causalite vers la North Star. 4 features orphelines Phase 2 identifiees. Chemin critique KPI en 5 etapes ordonnees. | Enrichissement du kpi-framework.md existant — section 3 ajoutee sans réécriture. Cibles [HYPOTHESE] conservees. Features Phase 2 (E5-S1/S2/S3) declarees orphelines car aucun KPI mesurable avant premier client SaaS. |
| @product-manager | 2026-03-25 | docs/product/functional-specs.md | 4 features specifiees (F1 audit E03/E04, F2 audio E01, F3 scripts E05-E10, F4 GA4). Seuil 9/10 bloquant sur 4 auditeurs pour F1/F3. Verification seg_003 non contournable pour F2. GA4 anonymise sans cookie banner pour F4. | P0 (E1-S1/S2/S3) deja corriges — non respecifies. Decisions prises : F2 conditionne F1 (workflow audit doit etre valide avant de generer E05-E10) ; seg_003 obligatoire apres 4 echecs de production historiques ; GA4 anonymize_ip=true = RGPD compliant sans bandeau. |
| @qa | 2026-03-25 | docs/qa/qa-strategy.md | Audit 16 criteres d'acceptation (12 testables auto, 4 manuels). 5 tests prioritaires identifies (launch-fresh, seg_003, checkpoint fields, valide sync, GA4). F4#1 reformule (non testable tel quel). Pas de Playwright — tout pytest. | Scores LLM des auditeurs non testables automatiquement — seules les mecaniques (sync fichier, checkpoint, compteur) sont couvertes. Les 5 tests prioritaires ciblent les 4 bugs de production historiques. GA4 teste par inspection HTML, pas par navigateur headless. Trous critiques identifies : aucun test existant pour launch-fresh ni seg_003 verification. |
| @creative-strategy | 2026-03-25 | docs/strategy/value-proposition.md | UVP en 2 formulations (courte 18 mots / longue 3 phrases). 7 criteres differenciants valides par test concurrentiel (Les Odyssees, Biblus, Encore une histoire). Double registre Sophie/Camille documente avec vocabulaire propre. Claim "premier podcast" juge verifiable (espace libre confirme par benchmark). | Traduction operationnelle du positionnement brand-platform en UVP actionnable pour @copywriter. Le mot "podcast" evite dans les accroches (designe le format, pas l'experience). "Fun facts scientifiques" identifie comme levier principal pour Noah et Camille. Toutes les hypotheses de chiffres marquees [HYPOTHESE]. |
| @copywriter | 2026-03-25 | docs/copy/brand-voice.md | Double registre Sophie/Camille formalise avec vocabulaires distincts. 8 mots interdits listes avec alternatives. Univers lexical mission/equipage/aventure consolide. 3 variantes UVP calibrees par persona (hero landing, email Camille, bio social cold discovery). 20 formulations DO/DON'T sur 5 contextes. | Calibration sectorielle sur brand-platform.md + personas.md avant production. Le mot "catechisme" banni de la communication publique — ecarte Camille immediatement. Titre hero (9 mots) conserve "Bible" + "aventure" en position forte pour SEO. Variante email ouvre sur un fun fact chiffre (135 m arche Noe) — levier Camille et Noah documente dans les personas. |
| @product-manager | 2026-03-26 | docs/product/functional-specs.md | 4 features specifiees en Given/When/Then (F1 audit E03/E04, F2 audio E01, F3 scripts E05-E10, F4 tracking). Seuil 9/10 bloquant. seg_003 non contournable. | P0 deja corriges — non respecifies. F2 conditionne F1. GA4 anonymize_ip=true = RGPD sans bandeau. |
| @qa | 2026-03-26 | docs/qa/qa-strategy.md | Matrice 16 criteres (12 auto, 4 manuels). 5 tests prioritaires. F4#1 reformule. Pas de Playwright. | Scores LLM non testables auto. 5 tests ciblent les 4 bugs historiques. |
| @infrastructure | 2026-03-26 | docs/infra/backend-audit.md | Audit routes web.py : F1-F3 couvertes, F4 GA4 = seul gap majeur (0%). Resilience checkpoints OK. | Audit parallele avec @qa. launch-fresh + kill-productions confirmes fonctionnels. |
| @qa | 2026-03-26 | docs/qa/qa-strategy.md (enrichi), papy-babou-podcast/tests/test_web_routes_critiques.py | 19 tests ecrits et passes. Couverture launch-fresh, kill-productions, checkpoint fields, valide sync. | Tests de non-regression sur les routes critiques identifiees par @infrastructure. |
| @fullstack | 2026-03-26 | (confirmation) | Umami deja implemente sur le site (tag JS present dans public.html). Pas de GA4 — choix fondateur Umami. | Agent confirme l'existant sans modifier le code. Fondateur prefere Umami a GA4. |
| orchestrator | 2026-03-26 | docs/orchestration-plan.md (mis a jour), web.py (fix 6 lignes montage count) | Audit backend confirme : bugs P0 deja corriges, F4 resolue par Umami existant. Fix montage count mismatch (filter par episode_id dans requete SQL). | Session de cloture : diagnostic + fix rapide. 5 questions Phase 2 SaaS en attente. Production audio S01E01 prete mais pas encore lancee. |
| orchestrator (explore) | 2026-03-26 | (documentation interne) | Workflow episode generation documente. Audit back-office V2 : template JS incomplet, routes V2 non prioritaires. Audit site public : episodes affiches correctement, cover + audio servis. Debug montage count mismatch : requete SQL ne filtrait pas par episode_id. Debug montage playback E01 : pas de bug, production audio pas encore lancee. | Exploration diagnostique sans agents — lecture directe du code pour comprendre l'etat reel du systeme. |
| orchestrator | 2026-03-26 | .claude/agents/ (15 fichiers mis a jour) | Mise a jour Gradient Agents depuis Agent-Team (2 branches). Agents preserves : copywriter.md, designer.md, ux.md (specifiques au projet). | Mise a jour de routine du framework — pas d'impact sur les livrables projet. |

## Performance des agents
| Agent | Date | Critere 1 (Pertinence) | Critere 2 (Completude) | Critere 3 (Coherence) | Critere 4 (Actionnable) | Critere 5 (Format) | Moyenne |
|---|---|---|---|---|---|---|---|
| (pas encore de donnees pour ce projet) | | | | | | | |
