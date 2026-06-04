# Troubleshooting Guide

**K1 Wizard-of-Oz Dashboard**
Hillsborough College AI Innovation Center · AI PREP4WORK Initiative

---

## Robot falls without warning

**Cause:** Battery died while using the dashboard. The Booster app's battery
warnings are bypassed when using the Wizard-of-Oz Dashboard.

**Fix:**
- Always monitor the battery indicator in the dashboard status strip
- Warning shows at < 20%, critical at < 10%
- Order 2 batteries per K1 — charge one while using the other
- The K1 5Ah battery must be charged separately from the robot

---

## WaveHand never stops

**Cause:** `WaveHand()` is a pre-programmed continuous motion. The SDK has
no `StopGesture()` method.

**Fix:** Click the **Stand** button — `GetUp()` interrupts the current motion
and returns the robot to neutral standing position.

---

## Perception machine fails (status code 400)

**Cause:** `booster-cli launch -c start` was run while the robot was not
upright. The perception machine requires the robot to be standing.

**Fix:**
1. Physically stand the robot upright (have spotter ready)
2. `booster-cli launch -c stop` — wait 5 seconds
3. `booster-cli launch -c start` — keep robot steady
4. Wait for both motion and perception `start succeeded`

---

## Robot doesn't respond to movement commands

**Cause:** Robot is not in the correct mode sequence.

**Fix:** Always follow this exact sequence in the dashboard:
```
Damp → Prep → Stand → Walk
```
Do not skip steps. The robot must be physically standing before Walk mode.

---

## Dashboard shows wrong mode

**Cause:** `GetMode()` returns a JSON parse error intermittently, so the
dashboard shows the internally-tracked mode, not the actual robot mode.

**Fix:** Use the `/motion_state` ROS2 topic to get real mode:
```bash
ros2 topic echo /motion_state --once
```

---

## Piper TTS using espeak-ng instead

**Cause:** `PIPER_VOICE_PATH` in `.env` uses a relative path (`./voices/`)
instead of an absolute path. Flask runs from `backend/` so relative paths
resolve incorrectly.

**Fix:** Use absolute path in `.env`:
```
PIPER_VOICE_PATH=/home/booster/k1-wizard-of-oz/voices/en_US-libritts_r-medium.onnx
```

Verify:
```bash
cd ~/k1-wizard-of-oz/backend
python3 -c "from config import cfg; print(cfg.PIPER_VOICE_PATH)"
```
Output must start with `/home/booster/` not `./home/booster/`.

---

## SSH connection drops when robot falls

**Cause:** Robot loses WiFi when it falls and the connection resets.

**Fix:**
1. Wait for robot to be physically stabilized
2. Reconnect to hotspot if needed
3. SSH back in: `ssh booster@192.168.0.176`
4. Check git status: `cd ~/k1-wizard-of-oz && git status`

---

## Robot won't connect to hotspot without Booster app

**Fix:** Configure auto-connect once per hotspot SSID:
```bash
sudo nmcli device wifi connect "YourSSID" \
  password "YourPassword" ifname wlP5p1s0
```
Robot will auto-connect on every boot. No app needed.

---

## Port 5000 already in use

**Cause:** Previous Flask session didn't exit cleanly.

**Fix:**
```bash
pkill -f "python3 app.py"
bash scripts/run.sh
```

---

## Booster SDK `GetMode()` JSON parse error

**Cause:** Known intermittent issue with the SDK RPC response parsing.

**Fix:** The error is non-fatal — ignore it. The dashboard falls back to
internally-tracked mode. For accurate mode reading use:
```bash
ros2 topic echo /motion_state --once
```

---

## Camera feed not showing

**Cause:** ROS2 not sourced, or K1 services not running.

**Fix:**
```bash
source /opt/ros/humble/setup.bash
booster-cli launch -c status
```
If perception machine shows 400, see "Perception machine fails" above.

---

## Ollama not responding

**Cause:** Ollama service not running.

**Fix:**
```bash
ollama serve &
sleep 3
ollama list
```

---

## ChannelFactory not initialized error

**Cause:** `B1LocoClient()` called before `ChannelFactory.Instance().Init()`.

**Fix:** Always initialize ChannelFactory first:
```python
ChannelFactory.Instance().Init(0, "wlP5p1s0")
client = B1LocoClient()
client.Init()
```

---

*Hillsborough College AI Innovation Center · AI PREP4WORK Initiative*
*Deshjuana Bagley, Associate Dean, A.S. Degree Programs*
