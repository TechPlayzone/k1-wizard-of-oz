#!/usr/bin/env bash
# start_wsl.sh
# One-command launcher for the K1 Wizard-of-Oz Dashboard in WSL2.
#
# Usage:
#   bash ~/k1-wizard-of-oz/scripts/start_wsl.sh
#
# What this does:
#   1. Starts Ollama if not already running
#   2. Runs the pre-flight check
#   3. Starts the Flask backend
#   4. Prints the dashboard URL
#
# Hillsborough College AI Innovation Center
# AI PREP4WORK Initiative — FIPSE Grant Program
# Deshjuana Bagley, Associate Dean, A.S. Degree Programs

set -e

REPO_DIR="$HOME/k1-wizard-of-oz"
BACKEND_DIR="$REPO_DIR/backend"

echo ""
echo "── K1 Wizard-of-Oz Dashboard ────────────────────────────"
echo "   Hillsborough College AI Innovation Center"
echo "   AI PREP4WORK Initiative"
echo "─────────────────────────────────────────────────────────"
echo ""

# ── Check .env exists ─────────────────────────────────────────
if [ ! -f "$REPO_DIR/.env" ]; then
    echo "[ERROR] .env not found at $REPO_DIR/.env"
    echo "        Run: cp $REPO_DIR/.env.example $REPO_DIR/.env"
    echo "        Then fill in your K1 IP and other settings."
    exit 1
fi

# ── Start Ollama if not running ───────────────────────────────
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[OK] Ollama already running"
else
    echo "[  ] Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "[OK] Ollama started"
    else
        echo "[WARN] Ollama may not have started. Check: tail /tmp/ollama.log"
    fi
fi

# ── Run pre-flight check ──────────────────────────────────────
echo ""
echo "Running pre-flight checks..."
python3 "$REPO_DIR/scripts/test_connection.py" || {
    echo ""
    echo "Some checks failed. Continue anyway? (y/N)"
    read -r answer
    if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
        exit 1
    fi
}

# ── Start Flask ───────────────────────────────────────────────
echo ""
echo "Starting Flask backend..."
echo "Dashboard: http://localhost:5000"
echo "Press Ctrl+C to stop."
echo ""
cd "$BACKEND_DIR"
python3 app.py
