"""
tts.py
Text-to-speech for the K1 using Piper TTS + sox audio processing.

Pipeline:
    Text → Piper TTS → WAV → sox EQ → K1 speaker (paplay)

Default voice: en_US-libritts_r-medium
Settings:
    length_scale = 0.8  (20% faster)
    treble       = +15  (brighter, less bass)

Voice models live in: ~/k1-wizard-of-oz/voices/

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import os
import subprocess
import tempfile
from config import cfg

# Speaker playback command confirmed working on K1
PAPLAY_CMD = (
    "espeak-ng '' --stdout | paplay "
    "--device=alsa_output.usb-C-Media_Electronics_Inc."
    "_USB_Audio_Device-00.analog-stereo < {wav}"
)


# Global speed — updated by /api/tts/settings
_current_length_scale: float = 0.8

def set_speed(length_scale: float) -> None:
    global _current_length_scale
    _current_length_scale = max(0.5, min(1.5, float(length_scale)))
    print(f"[TTS] Speed set to length_scale={_current_length_scale}")


def synthesize(text: str, voice_path=None,
               length_scale: float = None,
               treble: int = 15) -> str:
    """
    Convert text to a WAV file using Piper TTS with sox EQ.

    Args:
        text:         Text to speak
        voice_path:   Override default voice model path
        length_scale: Speech speed (0.8 = 20% faster, 1.0 = normal)
        treble:       Treble boost in dB (15 = brighter, less bass)

    Returns:
        Path to processed WAV file (caller must call cleanup() after use)

    Raises:
        FileNotFoundError: Voice model not found
        RuntimeError:      Piper synthesis failed
    """
    model = voice_path or cfg.PIPER_VOICE_PATH

    # Use global speed if not explicitly passed
    if length_scale is None:
        length_scale = _current_length_scale

    if not os.path.exists(model):
        # Fall back to espeak-ng if Piper voice not found
        print(f"[TTS] Piper voice not found at {model} — using espeak-ng")
        return _synthesize_espeak(text)

    # Create temp WAV file
    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav", prefix="k1_tts_", delete=False
    )
    tmp.close()
    wav_path = tmp.name

    # Run Piper TTS
    try:
        result = subprocess.run(
            [
                "piper",
                "--model",       model,
                "--length_scale", str(length_scale),
                "--output_file",  wav_path,
            ],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"[TTS] Piper failed — falling back to espeak-ng")
            return _synthesize_espeak(text)
    except FileNotFoundError:
        print("[TTS] piper not found — using espeak-ng fallback")
        return _synthesize_espeak(text)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Piper TTS timed out after 30 seconds")

    # Apply sox EQ (treble boost to reduce bass heaviness)
    if treble != 0:
        try:
            eq_path = wav_path.replace(".wav", "_eq.wav")
            sox_result = subprocess.run(
                ["sox", wav_path, eq_path, "treble", str(treble)],
                capture_output=True,
                timeout=10,
            )
            if sox_result.returncode == 0 and os.path.exists(eq_path):
                os.replace(eq_path, wav_path)
            else:
                print("[TTS] sox EQ skipped — using raw Piper output")
        except FileNotFoundError:
            print("[TTS] sox not installed — skipping EQ")
        except Exception as e:
            print(f"[TTS] sox error: {e} — using raw Piper output")

    return wav_path


def _synthesize_espeak(text: str) -> str:
    """Fallback TTS using espeak-ng."""
    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav", prefix="k1_espeak_", delete=False
    )
    tmp.close()
    wav_path = tmp.name
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
        raise RuntimeError(f"TTS failed (Piper and espeak-ng): {e}")


def speak_on_robot(wav_path: str) -> bool:
    """
    Play a WAV file through the K1 speaker using paplay.
    Running ON the K1 — no SSH/SCP needed.

    Confirmed working command on K1 firmware v1.6:
        espeak-ng '' --stdout | paplay --device=<usb_audio> < wav
    """
    try:
        cmd = PAPLAY_CMD.format(wav=wav_path)
        result = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("[TTS] Audio played via paplay")
            return True

        # Fallback: aplay
        print("[TTS] paplay failed — trying aplay")
        subprocess.run(
            ["aplay", wav_path],
            capture_output=True,
            timeout=30,
            check=True,
        )
        print("[TTS] Audio played via aplay")
        return True

    except subprocess.TimeoutExpired:
        print("[TTS] Audio playback timed out")
        return False
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
