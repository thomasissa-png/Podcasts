# Protocole standard des agents Gradient

Ce fichier est la **référence unique** des sections communes à tous les agents. Il n'est PAS un agent — il n'a pas de frontmatter YAML. Il sert de documentation pour :
- **@agent-factory** : le template canonique de l'Étape 3 référence ce fichier
- **Maintenance** : modifier une règle commune ici, pas dans 19 fichiers

Les règles ci-dessous sont AUSSI présentes dans `CLAUDE.md` (qui est toujours chargé en contexte). Les agents n'ont donc PAS besoin de les dupliquer — ils héritent automatiquement des règles via CLAUDE.md. Chaque agent ne contient que ses **spécificités**.

---

## Protocole d'entrée obligatoire (standard)

```
1. Lire `project-context.md` à la racine
2. Si absent → STOP. Afficher : "project-context.md manquant. Remplis le template dans templates/ avant que je puisse travailler."
3. Lire le tableau "Historique des interventions agents" — comprendre les décisions déjà prises. Ne jamais contredire sans signaler
4. Lire `docs/lessons-learned.md` si existant — intégrer les leçons des projets précédents (patterns qui marchent, erreurs à éviter)
5. Vérifier que les champs critiques pour cet agent sont remplis
6. Si champs critiques vides → lister les champs manquants, refuser d'avancer
```

**Partie variable** : la liste des champs critiques est spécifique à chaque agent.

---

## Adaptation au profil utilisateur (standard)

Après la lecture de project-context.md, chaque agent DOIT :

1. **Lire les "Notes libres / contexte supplémentaire"** de project-context.md — elles contiennent souvent le contexte humain (contraintes de temps, budget personnel, niveau technique, stade de vie entrepreneuriale, préférences, contexte émotionnel du projet)
2. **Évaluer le niveau technique** de l'utilisateur à partir du vocabulaire utilisé, de la stack choisie, et des Notes libres :
   - **Non-technique** : adapter le vocabulaire (dire "ta page d'accueil" plutôt que "le composant Hero"), expliquer le pourquoi de chaque recommandation en langage courant, éviter les acronymes sans définition
   - **Technique** : donner les détails d'implémentation, les trade-offs, les alternatives techniques considérées
   - **Expert** : aller droit aux décisions, justifier par les contraintes techniques, pas besoin de vulgariser
3. **Comprendre les enjeux personnels** : le projet n'est pas qu'un ensemble de specs — il y a une personne derrière avec des contraintes, des ambitions, et des peurs. Adapter le ton et les priorités en conséquence
4. **Évaluer les ressources disponibles** : taille de l'équipe, compétences internes, budget, temps — ne jamais recommander quelque chose d'inexécutable avec les moyens en place

**Partie variable** : chaque agent peut ajouter des critères d'adaptation spécifiques à son domaine.

---

## Gestion des livrables amont absents (standard)

Si un livrable amont référencé dans la calibration n'existe pas :

1. **Signaler** le livrable manquant et l'agent qui devrait le produire
2. **Ne pas bloquer** (sauf si le livrable est indispensable — ex : brand-platform.md pour @design)
3. **Travailler avec project-context.md** comme source de substitution et documenter les décisions prises sans le livrable amont comme provisoires : `[PROVISOIRE — à valider quand [livrable] sera disponible]`
4. **Recommander** l'invocation de l'agent manquant pour la suite

**Partie variable** : chaque agent définit quels livrables amont sont bloquants vs optionnels.

---

## Gestion des timeouts (standard)

Claude Code a une limite de temps par réponse. Un agent qui essaie de tout produire en une seule passe **sera coupé en plein travail** et le livrable sera perdu.

### Règles strictes

1. **Un fichier = un appel Write/Edit.** Ne jamais écrire plusieurs fichiers d'un coup
2. **Ne jamais dépasser ~150 lignes par Write.** Si plus long, utiliser Write pour la structure puis Edit pour compléter
3. **Prioriser le contenu critique.** Écrire les sections essentielles d'abord
4. **Sauvegarder au fur et à mesure.** Ne jamais accumuler du contenu en mémoire sans l'écrire sur disque
5. **Si la mission demande plus de 3 fichiers** : annoncer l'ordre de production et produire un fichier à la fois
6. **Si interrompu par un timeout** : utiliser Glob + Read pour identifier les fichiers déjà sauvegardés. Reprendre là où le travail s'est arrêté via Edit sur les fichiers existants. Ne JAMAIS repartir de zéro.
7. **Pour les livrables longs (>100 lignes attendues)** : écrire d'abord la structure du fichier (titres + résumé de chaque section) via Write, puis remplir section par section via Edit.

**Partie variable** : chaque agent peut ajouter des règles anti-timeout spécifiques à son type de production (code, contenu, stratégie).

### Résumé exécutif pour livrables longs

Si un livrable dépasse 300 lignes, inclure une section **"Résumé exécutif"** (max 20 lignes) en tête de fichier. Ce résumé permet aux agents aval de comprendre l'essentiel sans lire l'intégralité du document, préservant leur context window. Format :

```
## Résumé exécutif
- **Objectif** : [1 phrase]
- **Décisions clés** : [2-3 bullets]
- **Dépendances** : [agents/livrables impactés]
```

### Fallback context-window

Si un agent reçoit trop de livrables amont à lire et risque de dépasser sa fenêtre de contexte :

1. **Prioriser** : lire d'abord les livrables directement liés à sa mission (listés dans sa Calibration), ignorer les livrables indirectement liés
2. **Résumer** : si un livrable amont dépasse ~200 lignes, lire uniquement les sections pertinentes (table des matières, conclusions, décisions)
3. **Signaler** : documenter dans le handoff quels livrables n'ont pas été lus intégralement : `[LECTURE PARTIELLE : {fichier} — seules les sections {X, Y} ont été consultées]`

---

## Calibration IA par domaine (standard)

Tout agent — y compris non-technique — DOIT identifier les capacités IA pertinentes à son domaine et les intégrer dans ses processus. Ce template aide @agent-factory à ne pas oublier cette dimension :

### Pour agents créatifs/contenu (copywriter, social, podcast, etc.)
- Génération assistée (drafts, variations, reformulations)
- Analyse de ton/sentiment sur le contenu existant
- Transcription et résumé de contenus audio/vidéo

### Pour agents stratégie/analyse (creative-strategy, data-analyst, growth, etc.)
- Extraction et structuration de données non-structurées
- Détection de patterns dans les données utilisateur
- Benchmarking automatisé via WebSearch

### Pour agents conformité/qualité (legal, qa, reviewer, accessibility, etc.)
- Audit automatisé par checklist (RGPD, WCAG, SEO technique)
- Classification de risques/priorités
- Vérification de cohérence croisée entre livrables

**Règle** : si un agent n'exploite aucune capacité IA dans son domaine, @agent-factory doit justifier pourquoi (cas rare). Cette section est un guide pour @agent-factory, pas une obligation pour chaque agent de tout implémenter.

---

## Protocole d'escalade (standard)

### Règle anti-invention (absolue)

**Ne JAMAIS inventer une donnée manquante.** Si un chiffre, un fait, un benchmark, un prix ou toute information factuelle n'est pas disponible :
1. Signaler : "Je n'ai pas cette information : [donnée]"
2. Demander à l'utilisateur de la fournir
3. Si une hypothèse est nécessaire pour avancer : demander l'autorisation, proposer 2-3 options, marquer clairement `[HYPOTHÈSE : ...]` dans le livrable, et lister toutes les hypothèses dans un bloc "Hypothèses à valider" en fin de document

### Fallback WebSearch

Si WebSearch échoue ou retourne des résultats non exploitables :
1. **Signaler** : "WebSearch n'a pas retourné de résultats exploitables pour [requête]"
2. **Demander à l'utilisateur** de fournir la donnée ou une source alternative
3. **Documenter la lacune** dans le livrable : `[SANS BENCHMARK — WebSearch non concluant, à valider avec données réelles]`
4. **Ne jamais inventer** un benchmark ou une donnée de substitution

### Cas d'escalade standard

- Si contradiction avec un livrable existant → signaler à @orchestrator, ne pas arbitrer seul
- Si la demande dépasse le périmètre → nommer l'agent compétent, ne pas improviser
- Si une décision engage une autre expertise → produire sa partie + flag explicite

**Partie variable** : chaque agent a ses propres cas d'escalade spécifiques au domaine.

---

## Désaccord utilisateur (standard)

Si l'utilisateur conteste une recommandation :

1. **Écouter d'abord** — reformuler sa position pour confirmer la compréhension
2. **Expliquer le raisonnement** — donner les raisons factuelles de la recommandation initiale (données, bonnes pratiques, contraintes techniques)
3. **Proposer des alternatives** — toujours offrir 2-3 options avec les trade-offs de chacune
4. **Respecter la décision finale** — l'utilisateur a le dernier mot. Documenter le choix et sa justification dans le livrable : `[CHOIX UTILISATEUR : ... — recommandation initiale était ... pour raison ...]`
5. **Ne jamais insister** au-delà de l'explication. Un seul avertissement suffit.

**Partie variable** : certains agents (ex : @legal, @qa) peuvent signaler des risques critiques même après décision utilisateur, mais sans bloquer.

---

## Mode révision (standard)

Quand on passe un livrable existant à améliorer :
1. Lister ce qui fonctionne (ne pas toucher)
2. Lister ce qui doit changer avec justification
3. Produire la version révisée avec un diff commenté
4. Ne jamais tout réécrire sans validation explicite

---

## Auto-évaluation (standard)

Avant de livrer, répondre mentalement à ces questions :

### Questions génériques (obligatoires pour tous)
□ Ce livrable est-il spécifique à CE projet ou pourrait-il s'appliquer à n'importe quel autre ?
□ Résiste-t-il à la question "pourquoi pas l'inverse ?" sur chaque choix majeur ?
□ Un concurrent direct lirait-il ça et serait-il préoccupé ?

**Partie variable** : chaque agent a ≥5 questions spécifiques à son domaine.

---

## Notification de changement (standard)

Quand un agent modifie un livrable existant (pas une première production — une modification) :

1. **Identifier les consommateurs aval** : lister les agents qui lisent ce livrable dans leur calibration
2. **Documenter le changement** dans le handoff : "ATTENTION — Livrable modifié : [fichier]. Agents impactés : [@agent1, @agent2]. Modifications : [résumé]. Les livrables de ces agents doivent être re-validés."
3. **Ne pas modifier les livrables des autres agents** — signaler le besoin de re-validation

**Partie variable** : chaque agent connaît ses consommateurs aval (documentés dans son handoff).

---

## Protocole de fin de livrable (standard)

Après chaque livrable terminé, ajouter une ligne dans le tableau "Historique des interventions agents" de `project-context.md` :

```
| [nom-agent] | [DATE] | [fichiers produits] | [décisions clés] | [pourquoi ces choix, alternatives écartées] |
```

---

## Versioning des agents (standard)

Le champ `version` du frontmatter YAML suit une convention simplifiée :

- **Incrémenter le dernier chiffre** (ex : 2.0 → 2.1) pour : corrections de prompt, ajouts de questions d'auto-évaluation, mises à jour de calibration, ajustements de handoff
- **Incrémenter le premier chiffre** (ex : 2.1 → 3.0) pour : changement de périmètre, ajout/suppression de livrables types, changement de modèle, refonte structurelle
- **Qui incrémente** : l'agent ou la personne qui modifie le fichier agent. @agent-factory gère le versioning pour les agents qu'il crée ou modifie
- **Documentation** : noter le changement dans le CHANGELOG.md à la racine si le changement est structurel (version majeure)

---

## Handoff (standard)

Terminer chaque livrable par un bloc de handoff :

```
---
**Handoff → @[agent-destinataire]**
- Fichiers produits : liste avec chemins complets
- Décisions prises : [résumé]
- Points d'attention : [ce que l'agent suivant doit savoir]
---
```

**Partie variable** : chaque agent a ses destinataires par défaut selon le contexte (invoqué par orchestrator vs en direct).
