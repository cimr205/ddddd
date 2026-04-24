#!/bin/bash
# ═══════════════════════════════════════════
#  Lead Agent System – Mac Installer
#  Kør: bash start_mac.sh
# ═══════════════════════════════════════════

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Lead Agent System – Mac Setup        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── Homebrew ────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
  echo -e "${YELLOW}→ Installerer Homebrew...${NC}"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Apple Silicon path fix
  if [[ -f "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
  fi
else
  echo -e "${GREEN}✓ Homebrew allerede installeret${NC}"
fi

# ── Python ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo -e "${YELLOW}→ Installerer Python 3...${NC}"
  brew install python
else
  echo -e "${GREEN}✓ Python $(python3 --version) fundet${NC}"
fi

# ── pip deps ────────────────────────────────────────────────────────
echo -e "${YELLOW}→ Installerer Python pakker...${NC}"
pip3 install -r requirements.txt

# ── Playwright Chromium ─────────────────────────────────────────────
echo -e "${YELLOW}→ Installerer Playwright Chromium browser...${NC}"
python3 -m playwright install chromium

# ── .env ────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo -e "${GREEN}✓ .env fil oprettet${NC}"
  echo -e "${YELLOW}  Tip: Rediger .env og tilføj Groq API key + Gmail SMTP${NC}"
else
  echo -e "${GREEN}✓ .env fil eksisterer${NC}"
fi

mkdir -p data

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Setup færdig! Starter systemet...       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Dashboard: ${CYAN}http://localhost:8000${NC}"
echo -e "  Stop:      ${YELLOW}Ctrl+C${NC}"
echo ""

python3 main.py
