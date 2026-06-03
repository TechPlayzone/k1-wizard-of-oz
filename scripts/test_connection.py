"""
test_connection.py
Pre-flight check for the K1 Wizard-of-Oz Dashboard.

Run this before your first demo to confirm all services are reachable.

Usage:
    python3 scripts/test_connection.py

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import os
import sys
import socket
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

import requests

K1_IP         = os.getenv("K1_IP",           "192.168.0.176")
K1_PORT       = int(os.getenv("K1_PORT",      6666))
OLLAMA_URL    = os.getenv("OLLAMA_URL",       "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL",     "llama3.2")
FLASK_PORT    = int(os.getenv("FLASK_PORT",   5000))
ISAAC_IP      = os.getenv("ISAAC_SERVER_IP",  "")
ISAAC_PORT    = int(os.getenv("ISAAC_STREAM_PORT", 8211))
PIPER_PATH    = os.getenv("PIPER_VOICE_PATH", "./voices/en_US-lessac-medium.onnx")

PASS = "\033[92m[OK  ]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
SKIP = "\033[94m[SKIP]\033[0m"

def check_python_version():
    major, minor = sys.version_info.major, sys.version_info.minor
    if major >= 3 and minor >= 10:
        print(f"{PASS} Python {major}.{minor} (3.10+ required)")
        return True
    print(f"{FAIL} Python {major}.{minor} — upgrade to Python 3.10+")
    return False

def check_env():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        print(f"{PASS} .env file found")
        return True
    print(f"{WARN} .env not found — copy .env.example to .env")
    return False

def check_booster_sdk():
    try:
        import booster_robotics_sdk_python
        print(f"{PASS} Booster Robotics SDK installed")
        return True
    except ImportError:
        print(f"{WARN} Booster SDK not installed — see docs/WINDOWS_SETUP.md Step 3")
        return False

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
        matched = [m for m in models if OLLAMA_MODEL.split(":")[0] in m]
        if matched:
            print(f"{PASS} Ollama responding — {matched[0]} found")
        else:
            print(f"{WARN} Ollama running but '{OLLAMA_MODEL}' not found — run: ollama pull {OLLAMA_MODEL}")
        return True
    except Exception as e:
        print(f"{FAIL} Ollama not reachable at {OLLAMA_URL} — run: ollama serve")
        return False

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print(f"{PASS} ffmpeg installed")
    except Exception:
        print(f"{SKIP} ffmpeg not found (optional — needed for Whisper mic input)")
    return True

def check_piper():
    if os.path.exists(PIPER_PATH):
        print(f"{PASS} Piper voice model found")
    else:
        print(f"{SKIP} Piper voice model not found (Linux server feature — skip on Windows)")
    return True

def check_isaac():
    if not ISAAC_IP:
        print(f"{SKIP} Isaac Sim — not configured (optional)")
        return True
    try:
        s = socket.create_connection((ISAAC_IP, ISAAC_PORT), timeout=3)
        s.close()
        print(f"{PASS} Isaac Sim reachable at {ISAAC_IP}:{ISAAC_PORT}")
    except Exception:
        print(f"{SKIP} Isaac Sim not reachable (optional)")
    return True

if __name__ == "__main__":
    print("\n── K1 Wizard-of-Oz Dashboard — Pre-flight Check ──────\n")

    results = [
        check_python_version(),
        check_env(),
        check_booster_sdk(),
        check_tcp(K1_IP, K1_PORT, "K1 robot"),
        check_ollama(),
        check_ffmpeg(),
        check_piper(),
        check_isaac(),
    ]

    print(f"\nDashboard: http://localhost:{FLASK_PORT}")
    print("Start backend: python3 backend/app.py\n")

    failed = results.count(False)
    if not failed:
        print("All checks passed. Ready to run.\n")
    else:
        print(f"{failed} critical check(s) failed. See messages above.\n")
        sys.exit(1)
