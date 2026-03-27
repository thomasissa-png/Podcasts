# Installer l'équipe Gradient Agents dans un projet

Ce repo est le **repo source** de l'équipe Gradient Agents. Pour utiliser l'équipe dans un projet existant :

## Scénario A — Nouveau projet (pas encore de code)

Ouvrir une session Claude Code **sur le dossier du nouveau projet** et dire :

> "Installe l'équipe Gradient Agents depuis `/chemin/vers/Agent-Team` dans ce projet. C'est un nouveau projet."

Claude Code va :
1. **Détecter la racine du repo git** via `git rev-parse --show-toplevel` — installer `.claude/agents/` là, pas dans un sous-dossier
2. Copier les 19 agents dans `.claude/agents/` à la racine du repo git
3. Copier `.claude/settings.json` (permissions pré-approuvées pour les agents) — **indispensable** pour que les sous-agents puissent écrire des fichiers
4. Copier le `CLAUDE.md` (instructions globales) à la racine du repo git
5. Copier le template et créer `project-context.md` à la racine du repo git
6. Créer la structure `docs/` et `src/` si absentes

**Ensuite :** remplir `project-context.md` → invoquer `@orchestrator` pour lancer le projet complet.

## Scénario B — Projet existant (code déjà en place)

Ouvrir une session Claude Code **sur le projet existant** et dire :

> "Installe l'équipe Gradient Agents depuis `/chemin/vers/Agent-Team` dans ce projet. C'est un projet existant, ne rien écraser."

Claude Code va :
1. **Détecter la racine du repo git** via `git rev-parse --show-toplevel` — c'est là que `.claude/agents/` DOIT être installé, PAS dans un sous-dossier du repo
2. Copier les 19 agents dans `.claude/agents/` **à la racine du repo git** (crée le dossier s'il n'existe pas, ne touche pas aux agents déjà présents)
3. Copier `.claude/settings.json` (permissions pré-approuvées) — **fusionner** avec le `settings.json` existant s'il y en a un (ajouter les permissions manquantes, ne pas écraser les permissions existantes)
4. **Fusionner** le `CLAUDE.md` Gradient Agents avec le `CLAUDE.md` existant **à la racine du repo git** (ajouter les instructions en fin de fichier, ne pas écraser)
5. Copier le template dans `templates/` et créer `project-context.md` à la racine du repo git
6. **Ne pas toucher** à `src/`, `docs/`, `.replit`, `.github/`, `package.json` ni à aucun fichier existant

> **ATTENTION — Piège fréquent :** si le projet est un sous-dossier d'un repo git parent (ex : `monorepo/mon-projet/`), les agents DOIVENT être installés à la racine du repo git (`monorepo/.claude/agents/`), PAS dans le sous-dossier. Claude Code cherche `.claude/agents/` uniquement à la racine du repo git détectée par `git rev-parse --show-toplevel`.

**Différences clés sur un projet existant :**

| Aspect | Nouveau projet | Projet existant |
|---|---|---|
| `CLAUDE.md` | Copié tel quel | **Fusionné** — les instructions Gradient sont ajoutées au CLAUDE.md existant |
| `.claude/agents/` | Créé de zéro | Agents ajoutés sans écraser les agents custom déjà présents |
| `src/` | Créé vide | **Pas touché** — le code existant est préservé |
| `docs/` | Créé vide | **Pas touché** — les agents créeront leurs sous-dossiers au fur et à mesure |
| `project-context.md` | Template vierge | Template vierge — **mais il faut documenter l'existant** (stack, décisions déjà prises, code en place) |
| `package.json` | N'existe pas encore | **Pas touché** — les agents respectent les dépendances existantes |

**Ensuite :** remplir `project-context.md` en documentant ce qui existe déjà (stack actuelle, architecture, conventions de code, décisions passées) → invoquer l'agent adapté à la tâche ciblée.

**Important :** sur un projet existant, le premier réflexe n'est généralement pas `@orchestrator` (qui planifie un projet complet), mais l'agent spécifique au besoin : `@fullstack` pour du code, `@qa` pour des tests, `@seo` pour du référencement, etc.

## Scénario C — Mise à jour (l'équipe est déjà installée)

L'équipe Gradient Agents évolue régulièrement. Pour mettre à jour les agents dans un projet où ils sont déjà installés :

### Option 1 — Script automatisé (recommandé)

Si `update.sh` est déjà dans le projet :

```bash
bash update.sh        # mise à jour interactive (agent par agent)
bash update.sh --all  # tout mettre à jour d'un coup
bash update.sh --rollback  # annuler la dernière mise à jour
```

Si `update.sh` n'est pas dans le projet, l'installer d'abord :
```bash
curl -fsSL https://raw.githubusercontent.com/thomasissa-png/Agent-Team/claude/improve-frontend-prompts-BdBIK/update.sh -o update.sh && chmod +x update.sh
```

### Option 2 — Via Claude Code (prompt à copier tel quel)

Ouvrir une session Claude Code **sur le projet cible** et copier ce prompt :

> Mets à jour l'équipe Gradient Agents. Voici les étapes exactes à suivre :
>
> 1. `git clone https://github.com/thomasissa-png/Agent-Team -b claude/improve-frontend-prompts-BdBIK /tmp/Agent-Team 2>/dev/null || (cd /tmp/Agent-Team && git pull origin claude/improve-frontend-prompts-BdBIK)`
> 2. `cp /tmp/Agent-Team/.claude/agents/*.md .claude/agents/` — écraser tous les agents
> 3. `cp /tmp/Agent-Team/.claude/settings.json .claude/settings.json` — écraser les permissions
> 4. Pour le CLAUDE.md, vérifie si le fichier contient le marqueur `<!-- GRADIENT-AGENTS-START -->` :
>    - **Si oui** : remplace tout le bloc entre `<!-- GRADIENT-AGENTS-START -->` et `<!-- GRADIENT-AGENTS-END -->` par le contenu du CLAUDE.md source (qui contient ces mêmes marqueurs)
>    - **Si non** : le CLAUDE.md actuel est soit un ancien CLAUDE.md Gradient (sans marqueurs), soit un CLAUDE.md custom du projet. Demande-moi si je veux le remplacer entièrement ou ajouter la section Gradient en fin de fichier
> 5. `cp /tmp/Agent-Team/update.sh ./update.sh && chmod +x update.sh` — installer le script de mise à jour
> 6. Ne touche PAS à `project-context.md`, `docs/`, `src/`, `package.json`

### Option 3 — Manuelle

```bash
cd $(git rev-parse --show-toplevel)

# 1. Récupérer la dernière version
git clone https://github.com/thomasissa-png/Agent-Team -b claude/improve-frontend-prompts-BdBIK /tmp/Agent-Team 2>/dev/null || \
  (cd /tmp/Agent-Team && git pull)

# 2. Écraser les agents
cp /tmp/Agent-Team/.claude/agents/*.md .claude/agents/

# 3. Mettre à jour les permissions
cp /tmp/Agent-Team/.claude/settings.json .claude/settings.json

# 4. Remplacer le CLAUDE.md entièrement (si pas de contenu custom)
cp /tmp/Agent-Team/CLAUDE.md ./CLAUDE.md

# 4bis. OU fusionner (si le projet a du contenu custom dans CLAUDE.md)
#   → Garder le contenu custom du projet
#   → Remplacer uniquement la section entre les marqueurs GRADIENT-AGENTS-START/END
#   → Si pas de marqueurs : ajouter le contenu de Agent-Team/CLAUDE.md en fin de fichier

# 5. Installer update.sh pour les prochaines fois
cp /tmp/Agent-Team/update.sh ./update.sh && chmod +x update.sh

# 6. Vérifier les nouveaux champs du template
diff /tmp/Agent-Team/templates/project-context.md project-context.md
```

### Ce qui est écrasé vs préservé

| Écrasé | Préservé |
|---|---|
| `.claude/agents/*.md` (prompts améliorés) | `project-context.md` (historique projet) |
| `.claude/settings.json` (permissions) | `docs/` (livrables des agents) |
| `CLAUDE.md` (nouvelles règles) | `src/` (code du projet) |
| `templates/project-context.md` (template) | Agents custom (noms différents des 19 Gradient) |

**Après la mise à jour :** vérifier que `project-context.md` est toujours compatible avec le nouveau template. Si de nouveaux champs ont été ajoutés, les remplir.

## Variante — Si le repo Agent-Team n'est pas cloné localement

> "Clone `<url-du-repo-agent-team>` dans /tmp et installe l'équipe Gradient Agents dans ce projet. C'est un [nouveau projet / projet existant]."

## Méthode manuelle — Copier les fichiers à la main

Si tu préfères ne pas passer par Claude Code :

```bash
# 0. Se placer à la racine du repo git (IMPORTANT)
cd $(git rev-parse --show-toplevel)

# 1. Cloner le repo Agent-Team
git clone <url-agent-team> /tmp/Agent-Team

# 2. Copier les agents (à la RACINE du repo git, pas dans un sous-dossier)
mkdir -p .claude/agents
cp /tmp/Agent-Team/.claude/agents/*.md .claude/agents/

# 2b. Copier les permissions (INDISPENSABLE pour que les agents puissent écrire)
cp /tmp/Agent-Team/.claude/settings.json .claude/settings.json

# 3. CLAUDE.md
#    → Nouveau projet : copier directement
cp /tmp/Agent-Team/CLAUDE.md ./CLAUDE.md
#    → Projet existant : ajouter en fin de fichier
cat /tmp/Agent-Team/CLAUDE.md >> ./CLAUDE.md

# 4. Template et project-context
mkdir -p templates
cp /tmp/Agent-Team/templates/project-context.md templates/
cp templates/project-context.md ./project-context.md
# → Remplir project-context.md avant de lancer un agent
```

## Structure résultante

```
ton-projet/
├── .claude/
│   ├── agents/          ← les 19 agents Gradient
│   └── settings.json    ← permissions pré-approuvées (Write, Edit, Bash, etc.)
├── templates/
│   └── project-context.md  ← template vierge (référence)
├── project-context.md      ← contexte rempli pour CE projet
├── CLAUDE.md               ← instructions Gradient (seul ou fusionné avec l'existant)
├── docs/                   ← livrables des agents (créés au fur et à mesure)
└── src/                    ← code existant ou à créer
```

## Invocation des agents dans Claude Code

Dans une session Claude Code sur ton projet :

- **Via le menu** : taper `/` puis sélectionner l'agent dans la liste
- **Dans le prompt** : mentionner `@orchestrator`, `@fullstack`, `@design`, etc.
- **Directement** : demander une tâche et Claude routera vers le bon agent si le CLAUDE.md est présent

## Mise à jour des agents

Voir **Scénario C** ci-dessus pour la procédure complète (prompt à copier, méthode manuelle, ce qui est préservé vs écrasé).
