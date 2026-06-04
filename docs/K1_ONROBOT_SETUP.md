# K1 On-Robot Setup Guide

**Running the Wizard-of-Oz Dashboard directly on the K1**
Hillsborough College AI Innovation Center · AI PREP4WORK Initiative

---

## Overview

This guide documents the complete setup for running the K1 Wizard-of-Oz
Dashboard directly on the Booster K1 robot. Since Flask runs ON the K1,
the robot becomes a self-contained AI demo unit accessible from any browser
on the same WiFi network.

**Architecture:**
```
Browser (laptop/tablet/phone)
         ↓
http://192.168.0.176:5000
         ↓
Flask (running on K1 — Jetson Orin NX, Ubuntu 22.04)
         ↓
┌─────────────────────────────────────────────┐
│  Booster SDK    ROS2 Humble    Ollama        │
│  (movement)     (camera/mic)   (LLM)         │
└─────────────────────────────────────────────┘
         ↓
K1 hardware (motors, ZED camera, speaker, mic array)
```

---

## Hardware

- **Robot:** Booster K1 EDU
- **CPU:** NVIDIA Jetson Orin NX
- **OS:** Ubuntu 22.04.5 LTS (aarch64)
- **Storage:** 467GB NVMe
- **RAM:** 29GB
- **Battery:** 5Ah (order 2 per robot — see Battery Safety below)
- **Camera:** ZED stereo camera (topic: `/boostercamera/head/rgb`, encoding: `nv12`)
- **Speaker:** USB Audio Device (C-Media Electronics)
- **Mic:** Booster audio array (requires C++ SDK — see Known Limitations)
- **WiFi:** `wlP5p1s0` interface

---

## Network interfaces

| Interface | IP | Purpose |
|---|---|---|
| `wlP5p1s0` | 192.168.0.176 | WiFi — hotspot connection |
| `nv_eth0` | 192.168.13.101 | Internal NVIDIA interface |
| `usb_eth0` | 192.168.127.101 | USB ethernet |

> ⚠️ Always use `wlP5p1s0` for ChannelFactory initialization:
> `ChannelFactory.Instance().Init(0, "wlP5p1s0")`

---

## Step 1 — Prerequisites

SSH into the K1:
```bash
ssh booster@192.168.0.176
```

Install required packages:
```bash
sudo apt install -y nano sox espeak-ng

pip3 install flask flask-cors python-dotenv bcrypt \
  anthropic ollama requests soundfile numpy \
  piper-tts openai-whisper --user
```

Install Ollama:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b
```

---

## Step 2 — Clone the repository

```bash
cd ~
git clone https://github.com/TechPlayzone/k1-wizard-of-oz.git
cd k1-wizard-of-oz
```

---

## Step 3 — Download Piper voice model

```bash
mkdir -p ~/k1-wizard-of-oz/voices
cd ~/k1-wizard-of-oz/voices

wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx.json
```

---

## Step 4 — Configure .env

```bash
cp ~/k1-wizard-of-oz/.env.example ~/k1-wizard-of-oz/.env
nano ~/k1-wizard-of-oz/.env
```

Set these values:
```
K1_IP=192.168.0.176
K1_PORT=6868
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
PIPER_VOICE=en_US-libritts_r-medium
PIPER_VOICE_PATH=/home/booster/k1-wizard-of-oz/voices/en_US-libritts_r-medium.onnx
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_SECRET_KEY=<strong-random-key>
ADMIN_PASSWORD=<strong-password>
```

> ⚠️ `PIPER_VOICE_PATH` must be an **absolute path** starting with `/home/booster/`.
> Using `./voices/` will fail because Flask runs from the `backend/` directory.

---

## Step 5 — WiFi auto-connect (skip Booster app)

Configure the K1 to auto-connect to your hotspot on boot:
```bash
sudo nmcli device wifi connect "YourHotspotSSID" \
  password "YourPassword" ifname wlP5p1s0
```

This saves the network permanently. The robot connects automatically
on every boot without needing the Booster app. Run once per hotspot SSID.

---

## Step 6 — Start the dashboard

```bash
bash ~/k1-wizard-of-oz/scripts/k1_startup.sh
```

Then open in any browser on the same network:
```
http://192.168.0.176:5000
```

---

## Robot mode sequence (CRITICAL)

Always follow this sequence in the dashboard:

```
Damp → Prep → Stand → Walk
```

| Button | SDK call | Description |
|---|---|---|
| **Damp** | `ChangeMode(kDamping)` | Motors relax — safe resting state |
| **Prep** | `ChangeMode(kPrepare)` | Robot stiffens — prepares to stand |
| **Stand** | `GetUp()` | Robot stands up from floor |
| **Walk** | `ChangeMode(kWalking)` | Ready for movement commands |

> ⚠️ Never run movement commands before completing the full sequence.
> Never click Prep or Stand without a spotter present.

---

## Verified SDK API

From `/usr/local/lib/python3.10/dist-packages/booster_robotics_sdk_python.pyi`:

```python
from booster_robotics_sdk_python import (
    B1LocoClient, RobotMode, ChannelFactory, B1HandAction
)

# REQUIRED first step
ChannelFactory.Instance().Init(0, "wlP5p1s0")

client = B1LocoClient()
client.Init()                              # no arguments on K1

client.ChangeMode(RobotMode.kDamping)     # NOT kDamp
client.ChangeMode(RobotMode.kPrepare)
client.ChangeMode(RobotMode.kWalking)     # NOT kWalk

client.Move(vx, vy, vyaw)                 # float, float, float
client.WaveHand(B1HandAction.kHandOpen)
client.RotateHead(pitch, yaw)
client.Handshake(B1HandAction.kHandOpen)
client.GetUp()
client.LieDown()
ret, mode_resp = client.GetMode()         # returns tuple
```

---

## TTS configuration

Voice: `en_US-libritts_r-medium` (cheery, clear, less bass)
Speed: `length_scale=0.9`
EQ: `treble=+15` via sox

Playback command (confirmed working on K1 firmware v1.6):
```bash
espeak-ng '' --stdout | paplay \
  --device=alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo \
  < audio.wav
```

---

## Battery Safety

> ⚠️ **CRITICAL: Order 2 batteries per K1 robot.**

- The K1 EDU uses a 5Ah removable battery
- Battery must be charged separately from the robot
- When using the dashboard, Booster app battery warnings are bypassed
- The dashboard battery monitor reads `/battery_state` ROS2 topic
- Warning at < 20%, critical at < 10%
- Robot will fall without warning when battery dies
- Always monitor the battery indicator in the dashboard status strip
- Keep a spotter present during all demos

---

## Known limitations

| Feature | Status | Notes |
|---|---|---|
| Microphone | ⚠️ Partial | Requires C++ AudioManager SDK — Python bindings don't expose audio capture |
| Battery topic | ⚠️ Custom type | `/battery_state` uses `booster_interface/msg/BatteryState` — not standard ROS2 |
| GetMode() | ⚠️ Unreliable | Returns JSON parse error intermittently — use `/motion_state` ROS2 topic instead |
| Perception machine | ⚠️ Needs upright robot | Returns status 400 if robot not standing when services start |

---

## Installed packages on K1

```
nano, sox, espeak-ng           — utilities
piper-tts, onnxruntime         — TTS
openai-whisper                 — STT (mic pipeline pending)
flask, flask-cors              — web server
anthropic, ollama              — LLM providers
numpy, soundfile               — audio processing
ollama model: llama3.2:1b      — local LLM
```

---

## Restore to factory state

To remove all Wizard-of-Oz files from the K1:
```bash
rm -rf ~/k1-wizard-of-oz
rm -rf ~/voices
pip3 uninstall piper-tts onnxruntime openai-whisper \
  flask flask-cors anthropic ollama -y
ollama rm llama3.2:1b
sudo rm /usr/local/bin/ollama
sudo apt remove -y sox
```

---

*Hillsborough College AI Innovation Center · AI PREP4WORK Initiative*
*Deshjuana Bagley, Associate Dean, A.S. Degree Programs*
