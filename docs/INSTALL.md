# INSTALL.md — K1 Wizard-of-Oz Dashboard & Jupyter Notebook

**Hillsborough College AI Innovation Center**
AI PREP4WORK Initiative — FIPSE Grant #P116S230007
Dale Mabry Campus · Tampa, Florida

> Follow these steps on any new Windows, macOS, or Linux laptop before running the dashboard or the K1 Control Notebook.

---

## Prerequisites Checklist

- [ ] Python 3.10 or higher
- [ ] Git
- [ ] Ollama + models
- [ ] ffmpeg
- [ ] Piper voice model downloaded
- [ ] Booster Robotics SDK built and installed
- [ ] Python packages installed
- [ ] Franklin T10 hotspot available (college WiFi blocks robot traffic)

---

## Step 1 — Python

Install Python 3.10 or higher from https://python.org

> **Windows:** During install, check ✅ **"Add Python to PATH"** before clicking Install Now.

Verify:
```bash
python --version
# Should return Python 3.10.x or higher
```

---

## Step 2 — Git

Download and install from https://git-scm.com

Verify:
```bash
git --version
```

---

## Step 3 — Clone the Repository

```bash
git clone https://github.com/TechPlayzone/k1-wizard-of-oz.git
cd k1-wizard-of-oz
```

---

## Step 4 — Ollama + Language Models

### Install Ollama
Download from https://ollama.com and run the installer.

### Pull Models

```bash
# Lightweight conversational LLM — recommended for demos and limited RAM
ollama pull llama3.1:2b

# Full LLM — better responses, requires 16GB+ RAM
ollama pull llama3.1:8b

# Vision model — analyzes K1 camera feed (object/scene description)
ollama pull moondream

# Verify all models are ready
ollama list
```

**Model reference:**

| Model | Size | Type | Best For |
|---|---|---|---|
| `llama3.1:2b` | ~1.5 GB | Language | Live demos, fast responses, 8GB+ RAM |
| `llama3.1:8b` | ~4.7 GB | Language | Better reasoning, 16GB+ RAM |
| `moondream` | ~1.7 GB | Vision (image + text) | K1 camera feed analysis, student demos |

> **Moondream note:** Pass a frame from the K1's camera and ask "What do you see?" — great for interactive student demos. Runs alongside `llama3.1:2b` on most laptops.

> **Model name in scripts:** If using `llama3.1:2b`, update `"model": "llama3"` → `"model": "llama3.1:2b"` in `backend/app.py` and the Jupyter notebook.

---

## Step 5 — ffmpeg

Required by Whisper for audio processing.

**Windows:**
```bash
winget install ffmpeg
```
Or download manually from https://ffmpeg.org and add to PATH.

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt-get install -y ffmpeg
```

Verify:
```bash
ffmpeg -version
```

---

## Step 6 — Python Packages

```bash
pip install flask
pip install openai-whisper
pip install numpy scipy soundfile
pip install piper-tts
pip install anthropic
pip install openai
pip install python-dotenv
pip install jupyter notebook
pip install requests paramiko
pip install booster_robotics_sdk_python
```

Or install everything at once from the repo root:
```bash
pip install -r requirements.txt
```

---

## Step 7 — Piper Voice Model (One-Time Download)

```bash
mkdir ~/piper_voices
cd ~/piper_voices

# Download the voice model and its config file
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

> **Windows:** If `wget` is not available, download both files manually from the URLs above and place them in a `piper_voices` folder in your home directory.

Test Piper:
```bash
echo "Hello from K1." | piper \
  --model ~/piper_voices/en_US-lessac-medium.onnx \
  --output_file /tmp/test.wav

aplay /tmp/test.wav      # Linux
afplay /tmp/test.wav     # macOS
# Windows: open test.wav manually or use a Python audio player
```

---

## Step 8 — Booster Robotics SDK

The SDK provides Python access to K1 movement controls and audio hardware.

### 8a. Install Build Dependencies

**Windows:**
- Install Git: https://git-scm.com
- Install CMake: https://cmake.org/download
- Install Visual Studio Build Tools — select the **C++ workload**

**macOS:**
```bash
brew install cmake git
```

**Linux/Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install -y cmake build-essential git
```

### 8b. Clone and Build

```bash
git clone https://github.com/BoosterRobotics/booster_robotics_sdk.git
cd booster_robotics_sdk
mkdir build && cd build
cmake .. -DBUILD_PYTHON_BINDING=ON
make -j$(nproc)
sudo make install
```

### 8c. Verify

```bash
python3 -c "import booster_robotics_sdk_python; print('SDK OK')"
# Should print: SDK OK
```

> **Troubleshooting:** If the import fails, run:
> ```bash
> export PYTHONPATH=/usr/local/lib/python3.x/site-packages:$PYTHONPATH
> ```
> Replace `3.x` with your Python version.

---

## Step 9 — Jupyter Notebook

Jupyter is installed as part of Step 6. Launch the K1 Control Notebook:

```bash
# From the repo root
jupyter notebook K1_Control_Notebook.ipynb
```

Or launch Jupyter and navigate to the file:
```bash
jupyter notebook
```

---

## Step 10 — Configure Your K1 IP

Copy the example config and set your K1's WiFi IP:

```bash
cp .env.example .env
```

Edit `.env`:
```
K1_IP=192.168.x.xxx        # Replace with your K1's current IP
LLM_PROVIDER=ollama        # ollama | anthropic | openai
OLLAMA_URL=http://localhost:11434
```

> **Finding the K1's IP:** Use the Booster mobile app (Settings page) or SSH over Ethernet:
> ```bash
> ssh booster@192.168.10.102   # Password: 123456
> ip addr show wlan0
> ```

---

## Step 11 — Start the Dashboard

```bash
# Terminal 1 — start Ollama
ollama serve

# Terminal 2 — start the Flask backend
python backend/app.py

# Open in browser
# http://localhost:5000
```

---

## ⚠️ Important Notes

### Network — Franklin T10 Hotspot Required
College WiFi blocks device-to-device traffic. The laptop **and** K1 must both be on the **Franklin T10 hotspot** (or equivalent isolated hotspot) for SSH and audio connections to work.

### espeak-ng (K1 side only)
If using fallback TTS on the K1 robot itself, `espeak-ng` must be manually installed — it is **not** pre-installed on the K1:
```bash
# Run on the K1 over SSH
sudo apt-get install -y espeak-ng
```

### Firmware File
The K1 firmware file (`v1.6.1.1-release...run`, ~3.1 GB) is **not** stored in this repository. Download it separately from Booster Robotics if needed on a new laptop.

### API Keys
Never paste API keys directly into script files. Use environment variables or a `.env` file:
```bash
# .env (never commit this to GitHub)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

---

## Quick Reference — Startup Checklist

| # | Step |
|---|---|
| 1 | Connect laptop to Franklin T10 hotspot |
| 2 | Power on K1, wait 60 seconds |
| 3 | Confirm K1 is on the same hotspot network |
| 4 | Terminal 1: `ollama serve` |
| 5 | Terminal 2: `python backend/app.py` |
| 6 | Browser: `http://localhost:5000` |
| 7 | Click **Connect & Wake Up** in the dashboard |

---

## Estimated Setup Time (First Time)

| Task | Time |
|---|---|
| Python + Git + ffmpeg | 10 min |
| Ollama install + pull models (~7 GB total) | 20–45 min (depends on connection) |
| Python packages | 10 min |
| Piper voice model download | 5 min |
| Booster SDK build | 30–60 min |
| Configure `.env` + test connection | 15 min |
| **Total** | **~2–3 hours** |

---

*Hillsborough College — AI Innovation Center — AI PREP4WORK Initiative*
*This document may be shared freely with partner institutions.*
