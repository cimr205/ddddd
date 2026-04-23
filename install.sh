#!/bin/bash
set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Lead Generation System – Install       ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Python deps
echo "→ Installerer Python pakker..."
pip install -r requirements.txt -q

# Playwright Chromium (bruges til Google Maps scraping)
echo "→ Installerer Playwright Chromium (headless browser til scraping)..."
playwright install chromium

# Data folder
mkdir -p data

echo ""
echo "✓ Installation færdig!"
echo ""
echo "Næste trin:"
echo "  1. python setup_wizard.py    ← interaktiv guide til gratis keys"
echo "     ELLER"
echo "  1. cp .env.example .env && nano .env   ← manuel konfiguration"
echo ""
echo "  2. python main.py            ← start systemet"
echo "  3. Åbn http://localhost:8000"
echo ""
echo "Se SETUP.md for fuld guide til alle gratis muligheder."
