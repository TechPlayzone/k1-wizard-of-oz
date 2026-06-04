"""
stt.py
Speech-to-text for the K1 using Whisper.

Phase 1 (current): typed text passthrough
Phase 2 (future):  K1 mic → ROS2 audio topic → Whisper STT

The K1 microphone publishes audio via:
    /booster/audio/init_capture_streamReq
    /booster/audio/start_capture_streamReq

Since Flask runs ON the K1, audio capture is local — no
network transfer needed. Whisper runs directly on the K1.

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import os

_whisper_model = None


def transcribe_text(text: str) -> str:
    """Passthrough for typed input — Phase 1."""
    return text.strip()


def transcribe_audio(wav_path: str, model_size=None) -> str:
    """
    Transcribe audio using Whisper.
    Phase 2 — called when mic input is enabled in the dashboard.

    Args:
        wav_path:   Path to WAV file captured from K1 mic
        model_size: "tiny" | "base" | "small" | "medium"
                    Defaults to WHISPER_MODEL in .env

    Returns:
        Transcribed text string
    """
    global _whisper_model

    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    size = model_size or os.getenv("WHISPER_MODEL", "base")

    try:
        import whisper
    except ImportError:
        raise RuntimeError(
            "openai-whisper not installed. "
            "Run: pip3 install openai-whisper"
        )

    if _whisper_model is None:
        print(f"[STT] Loading Whisper model: {size}")
        _whisper_model = whisper.load_model(size)

    try:
        result = _whisper_model.transcribe(wav_path, language="en")
        text   = result["text"].strip()
        print(f"[STT] Transcribed: {text[:80]}")
        return text
    except Exception as e:
        raise RuntimeError(f"Whisper transcription failed: {e}")
