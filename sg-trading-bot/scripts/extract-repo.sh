#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# extract-repo.sh — move sg-trading-bot into its own standalone GitHub repo.
#
# Why you run this (not the assistant): creating/pushing to a new GitHub repo
# needs YOUR GitHub credentials. This script automates everything else.
#
# FIRST, create an EMPTY repo on github.com (no README/.gitignore/licence):
#   → https://github.com/new   e.g. name it "sg-trading-bot"
#
# THEN run, from inside the sg-trading-bot directory:
#   bash scripts/extract-repo.sh https://github.com/<you>/sg-trading-bot.git
#
# Options:
#   --history   Keep this folder's git history (uses `git subtree split`).
#               Default is a clean single initial commit.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REMOTE_URL="${1:-}"
MODE="clean"
for arg in "$@"; do
  [[ "$arg" == "--history" ]] && MODE="history"
done

if [[ -z "$REMOTE_URL" || "$REMOTE_URL" == --* ]]; then
  echo "Usage: bash scripts/extract-repo.sh <new-repo-git-url> [--history]"
  echo "Example: bash scripts/extract-repo.sh https://github.com/me/sg-trading-bot.git"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"

if [[ "$MODE" == "history" ]]; then
  # ── Preserve git history via subtree split ────────────────────────────────
  REPO_ROOT="$(git -C "$PROJECT_DIR" rev-parse --show-toplevel)"
  PREFIX="$(realpath --relative-to="$REPO_ROOT" "$PROJECT_DIR")"
  echo "==> Splitting history for '$PREFIX' from $REPO_ROOT…"
  cd "$REPO_ROOT"
  BRANCH="extract-${PROJECT_NAME}-$$"
  git subtree split --prefix="$PREFIX" -b "$BRANCH"
  echo "==> Pushing history to $REMOTE_URL (branch main)…"
  git push "$REMOTE_URL" "$BRANCH:main"
  git branch -D "$BRANCH"
  echo "✅ Pushed with history. Clone it fresh elsewhere:"
  echo "     git clone $REMOTE_URL"
else
  # ── Clean single-commit copy (recommended) ────────────────────────────────
  TMP="$(mktemp -d)/${PROJECT_NAME}"
  echo "==> Copying project to a clean working tree: $TMP"
  mkdir -p "$TMP"
  # Copy everything except any existing git metadata and local runtime junk.
  rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
        --exclude='state/*.json' --exclude='*.log' \
        "$PROJECT_DIR"/ "$TMP"/
  cd "$TMP"
  git init -q
  git add .
  git commit -q -m "Initial commit: automated multi-strategy IBKR investing bot"
  git branch -M main
  git remote add origin "$REMOTE_URL"
  echo "==> Pushing to $REMOTE_URL …"
  git push -u origin main
  echo "✅ Done. Your standalone repo lives at: $REMOTE_URL"
  echo "   Clean working copy: $TMP   (you can keep developing here, or re-clone)"
fi
