# Windows Setup Guide

**K1 Wizard-of-Oz Dashboard — Running on Windows via WSL2**
Hillsborough College AI Innovation Center · AI PREP4WORK Initiative

---

## Overview

The K1 Wizard-of-Oz Dashboard backend requires Linux to run the Booster
Robotics SDK. On Windows, the cleanest solution is **WSL2 (Windows Subsystem
for Linux 2)** with Ubuntu 22.04. This guide documents every step required
to get the full pipeline running on a Windows laptop before your Linux server
arrives.

**What works on Windows via WSL2:**
- ✅ Flask backend
- ✅ Booster Robotics SDK (K1 movement commands)
- ✅ Ollama LLM (conversational AI)
- ✅ Anthropic / OpenAI API providers
- ✅ Dashboard (browser on Windows, backend in WSL2)

**What requires the Linux server (later):**
- ⚠️ Piper TTS (K1 voice output) — Linux only
- ⚠️ ROS2 + ZED camera feed — Linux only
- ⚠️ Isaac Sim — NVIDIA RTX GPU required

---

## Important notes before you start

- **Python version:** The backend requires Python 3.10+. Ubuntu 22.04 ships
  with Python 3.10 — do not use the Windows Python installation for the backend.
- **Ollama:** Run Ollama inside WSL2, not on Windows. This avoids network
  address conflicts between WSL2 and Windows localhost.
- **Model selection:** Choose your Ollama model based on your hardware:

| Hardware | Recommended model |
|---|---|
| Laptop CPU only | `llama3.2:1b` (fastest) |
| Workstation with GPU 8 GB | `llama3.2` or `mistral` |
| Dell R770 dual L40S | `llama3` or `llama3.1:70b` |
| Any machine (vision) | `moondream` (camera description) |

---

## Step 1 — Install WSL2 with Ubuntu 22.04

Open **Command Prompt as Administrator** and run:

```bash
wsl --install -d Ubuntu-22.04
```

> ⚠️ Do NOT use the default `wsl --install` — it installs Ubuntu 24.04
> which has compatibility issues with the Booster SDK.

When prompted, restart your laptop. After restart, run the same command again
to finish Ubuntu setup. You will be asked to create a Linux username and
password — keep these simple, you will need them.

Set `main` as the default Git branch going forward:
```bash
git config --global init.defaultBranch main
```

---

## Step 2 — Update Ubuntu and install build tools

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip git curl wget build-essential \
  cmake libboost-all-dev libeigen3-dev ninja-build zstd
```

---

## Step 3 — Install the Booster Robotics SDK

The Booster SDK is not available on PyPI for Windows. It must be installed
from source inside WSL2.

```bash
cd ~
git clone https://github.com/BoosterRobotics/booster_robotics_sdk.git
cd booster_robotics_sdk
sudo ./install.sh
```

Install the Python bindings via pip:
```bash
pip install booster_robotics_sdk_python --user
```

> This takes several minutes — it compiles 108 C++ files.

Add the local bin to your PATH:
```bash
echo 'export PATH=$PATH:/home/<your-username>/.local/bin' >> ~/.bashrc
source ~/.bashrc
```

Verify:
```bash
python3 -c "import booster_robotics_sdk_python; print('SDK ready')"
```

---

## Step 4 — Install Ollama inside WSL2

> Run Ollama inside WSL2 — NOT on Windows. This avoids network conflicts.
> If Ollama is running on Windows, quit it first (system tray → Quit).

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Pull your model (choose based on your hardware — see table above):
```bash
# Fast (CPU laptop)
ollama pull llama3.2:1b

# Standard
ollama pull llama3.2

# Vision (camera description feature)
ollama pull moondream
```

Start Ollama:
```bash
ollama serve
```

Leave this terminal open. Open a new WSL2 terminal for the next steps.

---

## Step 5 — Clone the repository

```bash
cd ~
git clone https://github.com/TechPlayzone/k1-wizard-of-oz.git
cd k1-wizard-of-oz
```

---

## Step 6 — Install Python dependencies

```bash
pip3 install flask flask-cors python-dotenv bcrypt anthropic ollama \
  requests soundfile numpy
```

> Note: `piper-tts` and `booster_robotics_sdk_python` are NOT in this list —
> piper is Linux-server-only, and the Booster SDK was installed separately
> in Step 3.

---

## Step 7 — Configure your .env file

```bash
cp .env.example .env
nano .env
```

Set these values at minimum:

```
K1_IP=192.168.0.176          # Your K1's IP address
K1_PORT=6666
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b     # Match what you pulled in Step 4
ADMIN_PASSWORD=<strong password>
FLASK_SECRET_KEY=<random string>
```

Save with `Ctrl+X`, `Y`, `Enter`.

---

## Step 8 — Start the backend

```bash
cd ~/k1-wizard-of-oz/backend
python3 app.py
```

You should see:
```
[K1] Connected to 192.168.0.176:6666
[camera] ROS2 unavailable — offline placeholder active
Dashboard: http://localhost:5000
 * Running on http://127.0.0.1:5000
```

---

## Step 9 — Open the dashboard

Open **Chrome or Edge on Windows** and navigate to:
```
http://localhost:5000
```

The dashboard will load. You can:
- ✅ Chat with K1 via Ollama
- ✅ Send movement commands (when K1 is powered on)
- ✅ Trigger gestures
- ⚠️ Camera feed shows "offline" placeholder (needs ROS2 on Linux server)

---

## Step 10 — Test with K1 powered on

1. Power on the K1 and wait 60 seconds for full boot
2. Confirm K1 is on the same WiFi network as your laptop
3. In the dashboard, click **Walk** to set robot mode
4. Click **↑ Walk forward** — you should see movement in the Flask terminal:
   ```
   [K1] Mode → Walk
   [K1] Walk forward (2.0s)
   ```
5. The K1 should physically walk forward

---

## GitHub authentication in WSL2

GitHub no longer accepts passwords for Git push. Use a Personal Access Token:

1. Go to github.com → Settings → Developer settings
2. Personal access tokens → Tokens (classic) → Generate new token
3. Name: `WSL2-K1`, Expiration: 90 days, Scope: **repo**
4. Copy the token

When Git asks for a password, paste the token.

To avoid re-entering it every time:
```bash
git config --global credential.helper store
```

---

## Known Windows/WSL2 limitations

| Feature | Status | Workaround |
|---|---|---|
| Piper TTS (K1 voice) | ❌ Linux only | Use OpenAI TTS with API key |
| ZED camera feed | ❌ Needs ROS2 | Available on Linux server |
| Isaac Sim | ❌ Needs NVIDIA RTX | Available on Dell R770 |
| Python 3.8 type hints | ❌ Incompatible | Use Python 3.10 in WSL2 |
| `piper-tts` pip install | ❌ Windows fails | Skip on Windows |

---

## Startup sequence (every session)

```bash
# Terminal 1 — Start Ollama
ollama serve

# Terminal 2 — Start Flask backend
cd ~/k1-wizard-of-oz/backend
python3 app.py

# Browser (Windows) — Open dashboard
http://localhost:5000
```

---

## When your Linux server arrives

When your Dell R770 arrives, migrate the backend by:

1. Cloning the repo on the R770
2. Running `pip install -r requirements.txt` (all packages install cleanly on Linux)
3. Installing Piper TTS voice models
4. Installing ROS2 Humble for camera feed
5. Pointing your `.env` to the R770's IP

All the code is identical — no changes needed. The R770 will unlock:
- K1 voice output via Piper TTS
- Live ZED camera feed in dashboard
- Isaac Sim simulation view
- Faster LLM responses via L40S GPUs

---

*Hillsborough College AI Innovation Center · AI PREP4WORK Initiative*
*Deshjuana Bagley, Associate Dean, A.S. Degree Programs*
