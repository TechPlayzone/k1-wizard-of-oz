#!/bin/bash
# k1_startup.sh
# Full K1 startup sequence — Damp → Prep → Stand → Walk
#
# Usage: bash ~/k1-wizard-of-oz/scripts/k1_startup.sh

echo "── K1 Startup Sequence ──────────────────────────────"
echo "   Hillsborough College AI Innovation Center"
echo "────────────────────────────────────────────────────"
echo ""
echo "SAFETY: Make sure robot is lying safely on the floor"
echo "        and a spotter is present before continuing."
echo ""
read -p "Ready to start? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    exit 1
fi

echo ""
echo "Step 1: Stopping services..."
booster-cli launch -c stop
sleep 5

echo "Step 2: Starting services (Damp mode)..."
booster-cli launch -c start
sleep 8

echo "Step 3: Checking status..."
booster-cli launch -c status

echo ""
echo "────────────────────────────────────────────────────"
echo "Services started. Robot is in DAMP mode."
echo ""
echo "Next steps in the dashboard:"
echo "  1. Click PREP  — robot stiffens"
echo "  2. Click STAND — robot stands up"  
echo "  3. Click WALK  — ready for movement"
echo "────────────────────────────────────────────────────"
echo ""
echo "Starting dashboard..."
cd ~/k1-wizard-of-oz
bash scripts/run.sh
