"""
tts.py
Text-to-speech for the K1 using Piper TTS + ROS2 audio topics.

Pipeline:
    Text → Piper TTS → WAV → ROS2 /booster/audio topics → K1 speaker

Piper TTS runs locally on the K1 (ARM/aarch64 compatible).
No internet required. No SSH/SCP needed — audio goes via ROS2.

Fallback: if Piper not installed, uses espeak-ng directly.

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import os
import subprocess
import tempfile
from config import cfg

# Check for ROS2 audio support
_ros_available = False
try:
    import rclpy
    _ros_available = True
except ImportError:
    pass


def synthesize(text: str, voice_path=None) -> str:
    """
    Convert text to a WAV file using Piper TTS.
    Returns path to generated WAV file.
    Falls back to espeak-ng if Piper not installed.
    """
    model = voice_path or cfg.PIPER_VOICE_PATH

    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav", prefix="k1_tts_", delete=False
    )
    tmp.close()
    wav_path = tmp.name

    # Try Piper first
    if os.path.exists(model):
        try:
            result = subprocess.run(
                ["piper", "--model", model, "--output_file", wav_path],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                return wav_path
        except FileNotFoundError:
            pass  # Piper not installed, fall through to espeak

    # Fallback: espeak-ng (always available on K1)
    try:
        subprocess.run(
            ["espeak-ng", "-w", wav_path, text],
            capture_output=True,
            timeout=15,
            check=True,
        )
        print("[TTS] Using espeak-ng fallback")
        return wav_path
    except Exception as e:
        raise RuntimeError(f"TTS failed (both Piper and espeak-ng): {e}")


def speak_on_robot(wav_path: str) -> bool:
    """
    Play a WAV file through the K1 speaker.
    Since we're running ON the K1, we can play directly via paplay.
    No SSH/SCP needed.
    """
    try:
        # Try paplay with the K1's USB audio device
        result = subprocess.run(
            [
                "bash", "-c",
                f"espeak-ng '' --stdout | paplay "
                f"--device=alsa_output.usb-C-Media_Electronics_Inc."
                f"_USB_Audio_Device-00.analog-stereo < {wav_path}"
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("[TTS] Audio played via paplay")
            return True

        # Fallback: aplay
        subprocess.run(
            ["aplay", wav_path],
            capture_output=True,
            timeout=30,
            check=True,
        )
        print("[TTS] Audio played via aplay")
        return True

    except Exception as e:
        print(f"[TTS] speak_on_robot error: {e}")
        return False


def cleanup(wav_path: str) -> None:
    """Delete temp WAV file after playback."""
    try:
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)
    except OSError:
        pass
