"""
test_connection.py
Pre-flight check for the K1 Wizard-of-Oz Dashboard.

Run from the K1 robot before starting the backend:
    python3 scripts/test_connection.py

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

import requests

OLLAMA_URL   = os.getenv("OLLAMA_URL",    "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL",  "llama3.2:1b")
FLASK_PORT   = int(os.getenv("FLASK_PORT", 5000))
PIPER_PATH   = os.getenv("PIPER_VOICE_PATH", "./voices/en_US-lessac-medium.onnx")

PASS = "\033[92m[OK  ]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
SKIP = "\033[94m[SKIP]\033[0m"

def check_python():
    major, minor = sys.version_info.major, sys.version_info.minor
    if major >= 3 and minor >= 10:
        print(f"{PASS} Python {major}.{minor}")
        return True
    print(f"{FAIL} Python {major}.{minor} — need 3.10+")
    return False

def check_env():
    path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(path):
        print(f"{PASS} .env file found")
        return True
    print(f"{WARN} .env not found — run: cp .env.example .env")
    return False

def check_ros2():
    try:
        result = subprocess.run(
            ["ros2", "topic", "list"],
            capture_output=True, timeout=5
        )
        output = result.stdout.decode()
        if "/boostercamera/head/rgb" in output:
            print(f"{PASS} ROS2 active — K1 camera topic found")
        elif "/LocoApiTopicReq" in output:
            print(f"{PASS} ROS2 active — K1 loco topic found")
        else:
            print(f"{WARN} ROS2 active but K1 topics not visible yet")
            print(f"       Is the robot fully booted?")
        return True
    except FileNotFoundError:
        print(f"{FAIL} ROS2 not found — run: source /opt/ros/humble/setup.bash")
        return False
    except Exception as e:
        print(f"{FAIL} ROS2 check failed: {e}")
        return False

def check_ollama():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        matched = [m for m in models if OLLAMA_MODEL.split(":")[0] in m]
        if matched:
            print(f"{PASS} Ollama — {matched[0]} ready")
        else:
            print(f"{WARN} Ollama running but '{OLLAMA_MODEL}' not pulled")
            print(f"       Run: ollama pull {OLLAMA_MODEL}")
        return True
    except Exception as e:
        print(f"{FAIL} Ollama not running — run: ollama serve")
        return False

def check_piper():
    if os.path.exists(PIPER_PATH):
        print(f"{PASS} Piper voice model found")
    else:
        print(f"{SKIP} Piper voice model not found — using espeak-ng fallback")
    return True

def check_espeak():
    try:
        subprocess.run(["espeak-ng", "--version"], capture_output=True, check=True)
        print(f"{PASS} espeak-ng installed (TTS fallback ready)")
    except Exception:
        print(f"{WARN} espeak-ng not found — install: sudo apt install espeak-ng")
    return True

def check_cv2():
    try:
        import cv2
        print(f"{PASS} OpenCV (cv2) installed — camera stream ready")
    except ImportError:
        print(f"{WARN} OpenCV not installed — install: pip3 install opencv-python-headless")
    return True

if __name__ == "__main__":
    print("\n── K1 Wizard-of-Oz Dashboard — Pre-flight Check ──────\n")

    results = [
        check_python(),
        check_env(),
        check_ros2(),
        check_ollama(),
        check_piper(),
        check_espeak(),
        check_cv2(),
    ]

    print(f"\nDashboard: http://$(hostname -I | awk '{{print $1}}'):{FLASK_PORT}")
    print("Start backend: cd ~/k1-wizard-of-oz/backend && python3 app.py\n")

    failed = results.count(False)
    if not failed:
        print("All checks passed. Ready to run.\n")
    else:
        print(f"{failed} critical check(s) failed. See messages above.\n")
        sys.exit(1)
