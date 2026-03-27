# Lessons Learned — Les Histoires de Papy Babou

## Session du 2026-03-25/26 — Orchestration Phase 0 + Phase 1

### Ce qui a bien fonctionne

- **@creative-strategy en premiere position** : produire brand-platform + personas + benchmark AVANT tout autre agent a donne un socle solide. Tous les agents aval (copywriter, product-manager, data-analyst) ont cite et respecte le positionnement, les personas, et le ton de marque. Zero contradiction inter-livrables.
- **Agents qui confirment l'existant = valeur reelle** : @fullstack a confirme que Umami etait deja implemente (tag JS present dans public.html). @infrastructure a confirme que les bugs P0 etaient deja corriges. Ces confirmations evitent du travail inutile et donnent confiance sur l'etat reel du systeme.
- **Audit parallele @infrastructure + @qa** : lancer les deux en meme temps a permis de croiser les vues (routes vs tests) et de detecter que F4 (tracking) etait deja resolue par Umami.
- **19 tests ecrits et passes en une seule passe** par @qa — couverture des routes critiques (launch-fresh, kill-productions, checkpoint fields, valide sync) validee sans iteration corrective.
- **Fix montage count mismatch en 6 lignes** : le diagnostic via Explore agent a identifie que la requete SQL ne filtrait pas par episode_id. Fix rapide, pas besoin d'agent specialise.

### Ce qui a mal fonctionne

- **@product-manager timeout sur functional-specs.md** : le CLAUDE.md fait ~2500 lignes. L'agent product-manager a subi un timeout a la premiere tentative car le contexte etait trop long (CLAUDE.md complet + project-context.md + livrables amont). Solution : a la deuxieme tentative, le prompt a ete raccourci en ne transmettant que les chemins des livrables (pas leur contenu). Lecon : pour ce projet specifique, toujours transmettre les CHEMINS des livrables dans le prompt Task, pas leur contenu — les agents les liront eux-memes via Read.
- **Duplication d'interventions @product-manager et @qa** : le product-manager et le QA ont ete invoques 2 fois chacun (une fois en Phase 0, une fois en Phase 1). La deuxieme invocation n'a pas toujours produit un livrable significativement different. Lecon : grouper les missions d'un meme agent quand possible, plutot que de le relancer phase par phase.
- **5 questions fondateur Phase 2 sans reponse** : le product-manager a correctement identifie 5 questions bloquantes pour la Phase 2 SaaS (B2B/B2C, pricing, customisation, no-code, timeline). Mais la session s'est terminee sans que le fondateur y reponde. Lecon : poser les questions bloquantes le plus tot possible dans la session, pas en fin de livrable.

### Preferences fondateur detectees (transferees dans docs/founder-preferences.md)

- Umami > GA4 pour le tracking
- Pas de mot "catechisme" dans la communication publique
- Veut un workflow bout-en-bout avant d'optimiser les details
- Commence par la strategie/specs avant le code
- Camille (parent non-pratiquant) = persona de croissance prioritaire

### Ameliorations a apporter au framework

1. **Prompts Task pour ce projet** : toujours transmettre les chemins de fichiers, jamais le contenu inline — le CLAUDE.md est trop long et explose le contexte des agents.
2. **Grouper les missions par agent** : si un agent doit intervenir en Phase 0 et Phase 1, lui donner les deux missions en une seule invocation (avec instruction de les separer en sections).
3. **Questions fondateur en debut de session** : l'orchestrateur devrait poser les questions bloquantes dans les 5 premieres minutes, pas apres 3 heures de travail.
4. **Explore agent = outil puissant pour le diagnostic** : sur un projet existant avec beaucoup de code, utiliser l'Explore agent pour comprendre l'etat reel avant de lancer des agents de production. Evite les faux diagnostics.
