"""
test_connection.py
Pre-flight check for the K1 Wizard-of-Oz Dashboard.

Run this before your first demo to confirm all services are reachable.

Usage:
    python scripts/test_connection.py
"""

import os
import sys
import socket
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv()

K1_IP        = os.getenv("K1_IP", "192.168.0.176")
K1_PORT      = int(os.getenv("K1_PORT", 6666))
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
FLASK_PORT   = int(os.getenv("FLASK_PORT", 5000))
ISAAC_IP     = os.getenv("ISAAC_SERVER_IP", "")
ISAAC_PORT   = int(os.getenv("ISAAC_STREAM_PORT", 8211))

PASS = "\033[92m[OK]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"

def check_tcp(host, port, label):
    try:
        s = socket.create_connection((host, port), timeout=3)
        s.close()
        print(f"{PASS} {label} reachable at {host}:{port}")
        return True
    except Exception as e:
        print(f"{FAIL} {label} NOT reachable at {host}:{port}  ({e})")
        return False

def check_ollama():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        if any("llama3" in m for m in models):
            print(f"{PASS} Ollama responding — llama3 model found")
        else:
            print(f"{WARN} Ollama responding but llama3 not found. Run: ollama pull llama3")
        return True
    except Exception as e:
        print(f"{FAIL} Ollama not reachable at {OLLAMA_URL}  ({e})")
        print("       Start Ollama with: ollama serve")
        return False

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"],
                       capture_output=True, check=True)
        print(f"{PASS} ffmpeg installed")
        return True
    except Exception:
        print(f"{FAIL} ffmpeg not found — required by Whisper")
        print("       Install: sudo apt install ffmpeg  (or brew install ffmpeg)")
        return False

def check_piper_voice():
    voice_path = os.getenv("PIPER_VOICE_PATH", "./voices/en_US-lessac-medium.onnx")
    if os.path.exists(voice_path):
        print(f"{PASS} Piper voice model found at {voice_path}")
        return True
    else:
        print(f"{WARN} Piper voice model not found at {voice_path}")
        print("       See docs/SETUP.md Step 6 to download a voice model")
        return False

def check_env():
    if not os.path.exists(".env"):
        print(f"{WARN} .env file not found — copy .env.example to .env and fill in your values")
        return False
    print(f"{PASS} .env file found")
    return True

if __name__ == "__main__":
    print("\n── K1 Wizard-of-Oz Dashboard — Pre-flight Check ──\n")

    results = []
    results.append(check_env())
    results.append(check_tcp(K1_IP, K1_PORT, "K1 robot"))
    results.append(check_ollama())
    results.append(check_ffmpeg())
    results.append(check_piper_voice())

    if ISAAC_IP:
        results.append(check_tcp(ISAAC_IP, ISAAC_PORT, "Isaac Sim"))

    print(f"\nDashboard will be available at: http://localhost:{FLASK_PORT}")
    print("Start the backend with: python backend/app.py\n")

    failed = results.count(False)
    if failed == 0:
        print("All checks passed. Ready to run.\n")
    else:
        print(f"{failed} check(s) failed. See messages above.\n")
        sys.exit(1)
