#!/usr/bin/env bash
# run.sh — Start the K1 Wizard-of-Oz Dashboard on the K1 robot
#
# Usage:
#   bash ~/k1-wizard-of-oz/scripts/run.sh
#
# Hillsborough College AI Innovation Center
# AI PREP4WORK Initiative — FIPSE Grant Program
# Deshjuana Bagley, Associate Dean, A.S. Degree Programs

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$REPO_DIR/backend"

echo ""
echo "── K1 Wizard-of-Oz Dashboard ────────────────────────────"
echo "   Hillsborough College AI Innovation Center"
echo "   AI PREP4WORK Initiative"
echo "─────────────────────────────────────────────────────────"
echo ""

# Source ROS2
if [ -f /opt/ros/humble/setup.bash ]; then
    source /opt/ros/humble/setup.bash
    echo "[OK] ROS2 Humble sourced"
else
    echo "[WARN] ROS2 not found at /opt/ros/humble/setup.bash"
fi

# Check .env
if [ ! -f "$REPO_DIR/.env" ]; then
    echo "[ERROR] .env not found. Run: cp $REPO_DIR/.env.example $REPO_DIR/.env"
    exit 1
fi

# Start Ollama if not running
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[OK] Ollama already running"
else
    echo "[ ] Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
    echo "[OK] Ollama started"
fi

# Pre-flight check
echo ""
python3 "$REPO_DIR/scripts/test_connection.py" || true

# Get robot IP
ROBOT_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "Dashboard: http://$ROBOT_IP:5000"
echo "Open this URL in any browser on the same network."
echo "Press Ctrl+C to stop."
echo ""

cd "$BACKEND_DIR"
python3 app.py
