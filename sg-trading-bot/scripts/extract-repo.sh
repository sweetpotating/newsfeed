#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# extract-repo.sh — move this project into its own standalone GitHub repo,
# giving it a clean home with no unrelated history.
#
# Why YOU run this (not an assistant): pushing to a GitHub repo needs YOUR
# GitHub credentials. This script automates everything else — and if you have
# the GitHub CLI (`gh`) installed, it will even create the empty repo for you.
#
# ── Easiest path (with GitHub CLI) ───────────────────────────────────────────
#   gh auth login                         # one-time, if not already logged in
#   bash scripts/extract-repo.sh          # creates + pushes to the default repo
#
# ── Manual path (no gh) ──────────────────────────────────────────────────────
#   1. Create an EMPTY repo at https://github.com/new (no README/.gitignore).
#   2. bash scripts/extract-repo.sh https://github.com/<you>/<repo>.git
#
# Options:
#   --history   Keep this folder's git history (uses `git subtree split`)
#               instead of a single clean initial commit.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Default destination — change here if you ever want a different target.
DEFAULT_OWNER="sweetpotating"
DEFAULT_REPO="AI-Investor"

REMOTE_URL=""
MODE="clean"
for arg in "$@"; do
  case "$arg" in
    --history) MODE="history" ;;
    --*)       echo "Unknown option: $arg"; exit 1 ;;
    *)         REMOTE_URL="$arg" ;;
  esac
done

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"

# ── Resolve the destination URL, creating the repo via gh if we can ──────────
if [[ -z "$REMOTE_URL" ]]; then
  if command -v gh >/dev/null 2>&1; then
    echo "==> No URL given; using GitHub CLI to ensure ${DEFAULT_OWNER}/${DEFAULT_REPO} exists…"
    if ! gh repo view "${DEFAULT_OWNER}/${DEFAULT_REPO}" >/dev/null 2>&1; then
      echo "    Creating ${DEFAULT_OWNER}/${DEFAULT_REPO} (private)…"
      gh repo create "${DEFAULT_OWNER}/${DEFAULT_REPO}" --private \
        --description "Automated, risk-managed multi-strategy investing engine for Interactive Brokers." \
        >/dev/null
    else
      echo "    Repo already exists — will push into it."
    fi
    REMOTE_URL="https://github.com/${DEFAULT_OWNER}/${DEFAULT_REPO}.git"
  else
    echo "GitHub CLI (gh) not found, and no repo URL was provided."
    echo
    echo "Either install gh (https://cli.github.com) and re-run, or:"
    echo "  1. Create an EMPTY repo at https://github.com/new"
    echo "  2. bash scripts/extract-repo.sh https://github.com/${DEFAULT_OWNER}/${DEFAULT_REPO}.git"
    exit 1
  fi
fi

echo "==> Destination: $REMOTE_URL   (mode: $MODE)"

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
  echo "✅ Pushed WITH history. Clone it fresh:"
  echo "     git clone $REMOTE_URL"
else
  # ── Clean single-commit copy (recommended) ────────────────────────────────
  TMP="$(mktemp -d)/${PROJECT_NAME}"
  echo "==> Copying project to a clean working tree: $TMP"
  mkdir -p "$TMP"
  # Copy everything except git metadata and local runtime junk.
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
  echo "✅ Done — clean standalone repo at: $REMOTE_URL"
  echo "   Local clean copy: $TMP"
  echo
  echo "Once you've confirmed the new repo looks right, you can remove this copy"
  echo "from the original repo (see scripts/README or ask the assistant to stage"
  echo "the deletion on the working branch)."
fi
