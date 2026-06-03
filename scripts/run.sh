#!/usr/bin/env bash
# run.sh — Start the K1 Wizard-of-Oz Dashboard
# Usage: bash scripts/run.sh

set -e

echo ""
echo "── K1 Wizard-of-Oz Dashboard ──────────────────────────"
echo "   Hillsborough College AI Innovation Center"
echo "   AI PREP4WORK Initiative"
echo "────────────────────────────────────────────────────────"
echo ""

# Confirm .env exists
if [ ! -f ".env" ]; then
  echo "[ERROR] .env not found. Copy .env.example to .env first."
  exit 1
fi

# Pre-flight check
echo "Running pre-flight checks..."
python scripts/test_connection.py || {
  echo ""
  echo "[WARN] Some checks failed. Continue anyway? (y/N)"
  read -r answer
  if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
    exit 1
  fi
}

# Start Ollama in background if not running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "Starting Ollama..."
  ollama serve &
  sleep 3
fi

# Start Flask backend
echo ""
echo "Starting backend server..."
echo "Dashboard: http://localhost:5000"
echo ""
python backend/app.py
