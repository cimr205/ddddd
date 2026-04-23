#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Installing Playwright browser..."
playwright install chromium

echo "==> Creating data directory..."
mkdir -p data

echo ""
echo "Done! Setup complete."
echo ""
echo "Next steps:"
echo "  1. cp .env.example .env"
echo "  2. Edit .env with your API keys and SMTP details"
echo "  3. python main.py"
echo "  4. Open http://localhost:8000"
