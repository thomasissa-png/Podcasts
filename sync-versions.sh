#!/usr/bin/env bash
# sync-versions.sh — Synchronise les métadonnées agents (.md → index.html)
# Synchro automatique : version, model, champs critiques
# Appelé automatiquement par le pre-commit hook ou manuellement
#
# Données synchronisées depuis le frontmatter YAML :
#   - version: "X.Y" → AGENTS[].version
#   - model: claude-xxx → AGENTS[].model
# Données synchronisées depuis le corps :
#   - "Champs critiques pour cet agent :" → AGENTS[].required
#
# NOTE: Les descriptions HTML (AGENTS[].desc) sont des descriptions narratives
# différentes des descriptions frontmatter (mots-clés). Elles ne sont PAS synchronisées
# automatiquement car elles servent des usages différents.

set -euo pipefail

AGENTS_DIR=".claude/agents"
INDEX_FILE="index.html"

if [[ ! -f "$INDEX_FILE" ]]; then
  echo "Erreur : $INDEX_FILE introuvable. Exécuter depuis la racine du repo."
  exit 1
fi

changed=0

for md_file in "$AGENTS_DIR"/*.md; do
  filename=$(basename "$md_file" .md)

  # Skip base protocol (not an agent)
  [[ "$filename" == "_base-agent-protocol" ]] && continue

  # ── Extract version from YAML frontmatter ──
  version=$(grep -m1 '^version:' "$md_file" 2>/dev/null | sed 's/version: *"\{0,1\}\([^"]*\)"\{0,1\}/\1/' || true)
  [[ -z "$version" ]] && continue

  # ── Extract model from YAML frontmatter ──
  model=$(grep -m1 '^model:' "$md_file" 2>/dev/null | awk '{print $2}' || true)

  # ── Extract champs critiques ──
  critiques=$(grep -m1 "Champs critiques pour cet agent" "$md_file" 2>/dev/null | sed 's/.*: *//' || true)

  # ── Check if agent exists in index.html ──
  if ! grep -q "id:\"${filename}\"" "$INDEX_FILE" 2>/dev/null; then
    echo "  Attention : @${filename} n'existe pas dans $INDEX_FILE"
    continue
  fi

  # ── Sync version ──
  current_version=$(grep -oP "id:\"${filename}\"[^}]*version:\"\K[^\"]*" "$INDEX_FILE" 2>/dev/null || true)
  if [[ -n "$current_version" && "$current_version" != "$version" ]]; then
    sed -i "s/\(id:\"${filename}\"[^}]*version:\"\)[^\"]*/\1${version}/" "$INDEX_FILE"
    echo "  Mis à jour : @${filename} version v${current_version} → v${version}"
    changed=$((changed + 1))
  fi

  # ── Sync model ──
  if [[ -n "$model" ]]; then
    has_model=$(grep -oP "id:\"${filename}\"[^}]*model:\"\K[^\"]*" "$INDEX_FILE" 2>/dev/null || true)
    if [[ -n "$has_model" && "$has_model" != "$model" ]]; then
      sed -i "s/\(id:\"${filename}\"[^}]*model:\"\)[^\"]*/\1${model}/" "$INDEX_FILE"
      echo "  Mis à jour : @${filename} model → ${model}"
      changed=$((changed + 1))
    fi
  fi

  # ── Sync champs critiques → required array ──
  if [[ -n "$critiques" ]]; then
    current_required=$(grep -oP "id:\"${filename}\"[^}]*required:\[\K[^\]]*" "$INDEX_FILE" 2>/dev/null || true)
    expected_inner=$(echo "$critiques" | sed 's/, */","/g' | sed 's/^/"/' | sed 's/$/"/')
    if [[ -n "$current_required" && "$current_required" != "$expected_inner" ]]; then
      escaped_inner=$(echo "$expected_inner" | sed 's/[&/\]/\\&/g')
      sed -i "s|\(id:\"${filename}\"[^}]*required:\[\)[^\]]*|\1${escaped_inner}|" "$INDEX_FILE"
      echo "  Mis à jour : @${filename} champs requis"
      changed=$((changed + 1))
    fi
  fi

done

if [[ $changed -gt 0 ]]; then
  echo "✓ ${changed} champ(s) synchronisé(s) dans $INDEX_FILE"
  # Re-stage index.html if we're in a git commit context
  if git rev-parse --git-dir > /dev/null 2>&1; then
    git add "$INDEX_FILE" 2>/dev/null || true
  fi
else
  echo "✓ Toutes les métadonnées agents sont déjà synchronisées"
fi
