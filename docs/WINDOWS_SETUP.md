# Windows Setup Guide

**K1 Wizard-of-Oz Dashboard — Development on Windows via WSL2**
Hillsborough College AI Innovation Center · AI PREP4WORK Initiative

---

## Overview

The K1 Wizard-of-Oz Dashboard runs directly ON the K1 robot in production.
Windows/WSL2 is used for development only — editing code, pushing to GitHub,
and testing the chat pipeline without the physical robot.

**Production:** Flask runs on K1 → open `http://192.168.0.176:5000`
**Development:** Flask runs in WSL2 → open `http://localhost:5000`

---

## Important notes

- **Python version:** Ubuntu 22.04 ships with Python 3.10 — required
- **Do NOT use Windows Python** for the backend
- **Ollama:** Run inside WSL2, not on Windows (avoids network conflicts)
- **Booster SDK:** x86_64 build available for WSL2 (movement won't work
  remotely due to DDS networking, but dashboard/chat can be tested)

**Model selection by hardware:**

| Hardware | Recommended model |
|---|---|
| Laptop CPU only | `llama3.2:1b` (fastest) |
| Workstation GPU 8GB | `llama3.2` or `mistral` |
| Dell R770 dual L40S | `llama3` or `llama3.1:70b` |
| Any machine (vision) | `moondream` (camera description) |

---

## Step 1 — Install WSL2 with Ubuntu 22.04

Open **Command Prompt as Administrator**:
```cmd
wsl --install -d Ubuntu-22.04
```

> ⚠️ Do NOT use `wsl --install` without `-d Ubuntu-22.04` — the default
> Ubuntu 24.04 has compatibility issues with the Booster SDK.

Restart your laptop when prompted. After restart, run the same command
again to finish Ubuntu setup. Create a Linux username and password.

---

## Step 2 — Update Ubuntu and install build tools

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip git curl wget \
  build-essential cmake libboost-all-dev libeigen3-dev \
  ninja-build zstd nano sox espeak-ng
```

---

## Step 3 — Install the Booster Robotics SDK

```bash
cd ~
git clone https://github.com/BoosterRobotics/booster_robotics_sdk.git
cd booster_robotics_sdk
sudo ./install.sh
pip install booster_robotics_sdk_python --user
```

Add to PATH:
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

> Run Ollama inside WSL2 — NOT on Windows. Quit Windows Ollama first
> if it's running (system tray → Quit).

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b
ollama serve &
```

---

## Step 5 — Install ROS2 Humble

ROS2 is required to receive camera feed, battery state, and other K1 topics.
Due to WSL2 network isolation (NAT), ROS2 topics from the K1 are NOT visible
in WSL2. ROS2 in WSL2 is useful for testing only.

```bash
sudo apt install -y software-properties-common curl
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu \
  $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update
sudo apt install -y ros-humble-desktop
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

> ⚠️ WSL2 uses NAT networking — ROS2 topics from the K1 are NOT visible
> in WSL2. For full ROS2 integration, run the backend ON the K1 (production)
> or on a Linux machine on the same network.

---

## Step 6 — Clone the repository

```bash
cd ~
git clone https://github.com/TechPlayzone/k1-wizard-of-oz.git
cd k1-wizard-of-oz
```

---

## Step 7 — Install Python dependencies

```bash
pip3 install flask flask-cors python-dotenv bcrypt \
  anthropic ollama requests soundfile numpy --user
```

> Note: `piper-tts` is not needed in WSL2 — TTS runs on the K1. The
> dashboard will use text responses without audio in development mode.

---

## Step 8 — Configure .env

```bash
cp .env.example .env
nano .env
```

```
K1_IP=192.168.0.176
K1_PORT=6868
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_SECRET_KEY=dev-only-change-for-production
ADMIN_PASSWORD=changeme123
```

---

## Step 9 — Start the backend

```bash
# Terminal 1 — Ollama
ollama serve

# Terminal 2 — Flask
cd ~/k1-wizard-of-oz/backend
python3 app.py
```

Open in browser:
```
http://localhost:5000
```

---

## GitHub authentication in WSL2

GitHub no longer accepts passwords. Use a Personal Access Token:

1. github.com → Settings → Developer settings
2. Personal access tokens → Tokens (classic) → Generate new token
3. Name: `WSL2-K1`, Expiration: 90 days, Scope: **repo**
4. Copy the token

Save permanently:
```bash
git config --global credential.helper store
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

When Git asks for password, paste the token once — saved forever.

---

## Known WSL2 limitations

| Feature | Status | Notes |
|---|---|---|
| K1 movement | ❌ | DDS multicast can't cross WSL2 NAT |
| Camera feed | ❌ | ROS2 topics not visible across NAT |
| Battery monitor | ❌ | Same ROS2 networking issue |
| Piper TTS | ❌ | Linux only — use espeak-ng or skip |
| Chat pipeline | ✅ | Ollama in WSL2 works fine |
| Dashboard UI | ✅ | Full dashboard available |
| SDK import | ✅ | Booster SDK installs on x86_64 |

---

## When your Linux server arrives

When the Dell R770 arrives, migrate by:

1. Clone repo on R770
2. `pip install -r requirements.txt`
3. Install Piper TTS voice models
4. Install ROS2 Humble
5. Point `.env` to R770's IP

The R770 will be on the same network as the K1, enabling full ROS2
integration including camera feed and battery monitoring.

---

## Startup sequence (WSL2 development)

```bash
# Terminal 1
ollama serve

# Terminal 2
cd ~/k1-wizard-of-oz/backend
python3 app.py

# Browser
http://localhost:5000
```

---

*Hillsborough College AI Innovation Center · AI PREP4WORK Initiative*
*Deshjuana Bagley, Associate Dean, A.S. Degree Programs*
