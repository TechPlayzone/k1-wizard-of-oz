# Setup Guide for Partner Colleges

**K1 Wizard-of-Oz Dashboard**
Hillsborough College AI Innovation Center · AI PREP4WORK Initiative

---

This guide walks a new college through setting up the K1 Wizard-of-Oz Dashboard
from scratch. Estimated time: **1.5 to 2.5 hours** on first install.

---

## Prerequisites

Before you begin, confirm you have:

- [ ] A Booster K1 EDU robot (firmware v1.6+ recommended)
- [ ] A laptop or server with at least 16 GB RAM and a discrete NVIDIA GPU
- [ ] Python 3.10 or higher installed
- [ ] Git installed
- [ ] ffmpeg installed (see Step 3)
- [ ] A local WiFi network both your laptop and K1 can join

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/TechPlayzone/k1-wizard-of-oz.git
cd k1-wizard-of-oz
```

---

## Step 2 — Create your config file

```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in at minimum:

```
K1_IP=<your K1's IP address on the local network>
LLM_PROVIDER=ollama          # start with ollama — no API key needed
ADMIN_PASSWORD=<strong password of your choice>
```

To find the K1's IP address: check your router's connected devices list,
or SSH into the K1 (`ssh booster@<IP>`) and run `hostname -I`.

---

## Step 3 — Install ffmpeg

ffmpeg is required by Whisper for audio processing.

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install -y ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html and add to your PATH.

---

## Step 4 — Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs Flask, Whisper, Piper TTS, the Anthropic SDK, the OpenAI SDK,
and the Booster K1 Python SDK. Allow 5–10 minutes on first run.

---

## Step 5 — Install Ollama and pull Llama 3

Ollama runs the LLM locally with no internet or API key required.

```bash
# Linux / macOS
curl -fsSL https://ollama.com/install.sh | sh

# Windows: download installer from https://ollama.com/download
```

Pull the Llama 3 model (~4 GB download):

```bash
ollama pull llama3
```

Verify it works:
```bash
ollama run llama3 "Hello, are you working?"
```

---

## Step 6 — Download a Piper voice model

Piper TTS converts the LLM's text response to speech.
Create a `voices/` folder and download a voice:

```bash
mkdir -p voices
cd voices

# US English male (default)
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

Update `PIPER_VOICE_PATH` in your `.env` to match the downloaded file path.

Other available voices: see https://github.com/rhasspy/piper/blob/master/VOICES.md

---

## Step 7 — Power on and connect the K1

1. Place the K1 on a flat surface with room to stand.
2. Power on — wait approximately 60 seconds for full boot.
3. Connect the K1 to the same WiFi network as your laptop.
4. Confirm connectivity:

```bash
python scripts/test_connection.py
```

Expected output:
```
[OK] K1 reachable at 192.168.0.176
[OK] Ollama responding at http://localhost:11434
[OK] Dashboard will be available at http://localhost:5000
```

---

## Step 8 — Start the backend

```bash
python backend/app.py
```

Or use the convenience script:

```bash
bash scripts/run.sh
```

---

## Step 9 — Open the dashboard

Navigate to **http://localhost:5000** in Chrome or Firefox.

First-time setup: click **Admin** in the header and enter your admin password
to confirm K1 IP, network settings, and default LLM provider. Regular users
never see this screen.

---

## Network isolation (recommended)

The K1 EDU ships with ByteDance/Doubao as its default LLM. Even though this
pipeline bypasses Doubao entirely, we recommend connecting both the K1 and your
inference laptop to a **dedicated mobile hotspot** that is separate from your
institution's campus network. This prevents any potential data from reaching
the K1's firmware services.

Tested hardware: Franklin T10, Inseego 5G MiFi (available via T-Mobile
state contract in Florida).

---

## NVIDIA Isaac Sim (optional)

To use the Isaac Sim toggle in the Live panel:

1. Install NVIDIA Isaac Sim on your inference server (requires NVIDIA GPU).
   Docs: https://docs.omniverse.nvidia.com/isaacsim/latest/index.html

2. Launch Isaac Sim with WebRTC streaming enabled:
   ```bash
   ./isaac-sim.sh --/app/livestream/enabled=true
   ```

3. Update `ISAAC_SERVER_IP` in your `.env` to your server's local IP.

4. In the dashboard, click **Isaac sim** in the Live panel toggle.
   Then click **Connect to simulator**.

The K1 URDF (`K1_22dof.urdf`) is available at:
https://github.com/BoosterRobotics/booster_assets

---

## Using API providers (Anthropic / OpenAI)

The dashboard supports Anthropic Claude and OpenAI GPT-4o as drop-in LLM
replacements. API keys are **session-scoped** — they are stored in browser
memory only and cleared when the tab is closed. Keys are never written to
disk, logged, or transmitted outside the API call.

To use:
1. In the Conversation panel, click **Anthropic** or **OpenAI**.
2. Paste your API key into the key field and click **Apply**.
3. The robot status strip confirms the active provider.

The K1 must be on a network with internet access when using cloud providers.

---

## Troubleshooting

See [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for common issues including:

- K1 not reachable on network
- Whisper transcription errors
- Piper TTS silent output
- Ollama not responding
- Movement commands not executing

---

## Estimated setup times

| Task | First time | Subsequent |
|---|---|---|
| Clone + config | 5 min | — |
| pip install | 10 min | — |
| Ollama + pull Llama 3 | 20–30 min | — |
| Piper voice download | 5 min | — |
| K1 connection test | 5 min | 1 min |
| **Total** | **~1.5–2.5 hrs** | **~5 min** |

---

*Hillsborough College AI Innovation Center · AI PREP4WORK Initiative*
*Deshjuana Bagley, Associate Dean, A.S. Degree Programs*
