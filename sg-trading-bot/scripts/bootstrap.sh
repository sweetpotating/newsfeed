#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# sg-trading-bot — VPS bootstrap for Ubuntu 22.04 / 24.04 LTS.
#
# Installs Python + the bot, Java + xvfb (for IB Gateway), and IBC (to keep IB
# Gateway logged in and alive). It does NOT download IB Gateway itself or enter
# any credentials — those steps need you (see the printed next-steps).
#
# Usage:
#   git clone <your-repo-url> && cd <repo>/sg-trading-bot
#   bash scripts/bootstrap.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
echo "==> Project: $PROJECT_DIR"

echo "==> Installing system packages…"
sudo apt-get update -y
sudo apt-get install -y \
  python3 python3-venv python3-pip \
  openjdk-17-jre-headless \
  xvfb x11-utils \
  unzip wget curl

echo "==> Creating Python virtualenv…"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt ib_async yfinance requests
echo "==> Python deps installed."

echo "==> Setting up .env…"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "    Created .env from template — EDIT IT before running (credentials, ports)."
else
  echo "    .env already exists — leaving it untouched."
fi

echo "==> Installing IBC (keeps IB Gateway logged in & alive)…"
IBC_VERSION="3.20.0"
IBC_DIR="$HOME/ibc"
if [[ ! -d "$IBC_DIR" ]]; then
  mkdir -p "$IBC_DIR"
  wget -q "https://github.com/IbcAlpha/IBC/releases/download/${IBC_VERSION}/IBCLinux-${IBC_VERSION}.zip" \
    -O /tmp/ibc.zip || {
      echo "    ! Could not auto-download IBC ${IBC_VERSION}. Grab the latest from"
      echo "      https://github.com/IbcAlpha/IBC/releases and unzip into $IBC_DIR"
    }
  if [[ -f /tmp/ibc.zip ]]; then
    unzip -oq /tmp/ibc.zip -d "$IBC_DIR"
    chmod +x "$IBC_DIR"/*.sh || true
    echo "    IBC installed to $IBC_DIR"
  fi
else
  echo "    IBC already present at $IBC_DIR"
fi

cat <<'NEXT'

────────────────────────────────────────────────────────────────────────────
✅ Bootstrap done. What YOU must do next (these need your account/credentials):

 1. Install IB Gateway (the broker connection app):
      wget https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh
      chmod +x ibgateway-stable-standalone-linux-x64.sh && ./ibgateway-stable-standalone-linux-x64.sh

 2. Configure IBC with your IBKR login + paper port:
      edit ~/ibc/config.ini   (set IbLoginId, IbPassword, TradingMode=paper)
    Then start Gateway under a virtual display:
      xvfb-run -a ~/ibc/gatewaystart.sh &

 3. Edit this project's .env:
      SGTRADER_MODE=paper
      SGTRADER_PAPER_BROKER=ibkr     # route paper orders to your IBKR paper acct
      SGTRADER_DATA_PROVIDER=ibkr
      IBKR_PORT=4002                 # IB Gateway paper (TWS paper = 7497)
      TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...

 4. Verify everything is wired:
      source .venv/bin/activate && python -m sgtrader doctor

 5. Schedule daily runs (systemd):
      see scripts/sgtrader.service / scripts/sgtrader.timer and DEPLOY.md

 Go live only after watching paper for a few weeks. See DEPLOY.md.
────────────────────────────────────────────────────────────────────────────
NEXT
