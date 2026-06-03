"""
stt.py
Speech-to-text using OpenAI Whisper.

Currently used as a passthrough for typed text (Phase 1).
The mic → Whisper path is scaffolded here and ready to enable
when audio input is added to the dashboard (Phase 2).

Usage (typed text — current):
    from stt import transcribe_text
    text = transcribe_text("Hello K1")   # returns as-is

Usage (audio file — future):
    from stt import transcribe_audio
    text = transcribe_audio("/tmp/recorded_audio.wav")
"""

import os

# Lazy-load Whisper only when transcribe_audio is actually called
# so the server starts fast even if Whisper is not installed
_whisper_model = None


def transcribe_text(text: str) -> str:
    """
    Passthrough for typed input.
    Strips whitespace and returns the text ready for the LLM.
    """
    return text.strip()


def transcribe_audio(wav_path: str, model_size: str | None = None) -> str:
    """
    Transcribe an audio file to text using Whisper.
    (Phase 2 — not called in the current typed-text implementation)

    Args:
        wav_path:   Path to WAV or MP3 audio file
        model_size: Whisper model size override
                    ("tiny" | "base" | "small" | "medium" | "large")
                    Defaults to WHISPER_MODEL in .env

    Returns:
        Transcribed text string

    Raises:
        FileNotFoundError: Audio file not found
        RuntimeError:      Whisper transcription failed
    """
    global _whisper_model

    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    from config import cfg
    size = model_size or os.getenv("WHISPER_MODEL", "base")

    try:
        import whisper
    except ImportError:
        raise RuntimeError(
            "openai-whisper not installed. "
            "Run: pip install openai-whisper"
        )

    # Load model once and reuse across requests
    if _whisper_model is None:
        print(f"[STT] Loading Whisper model: {size} (first load may take a moment)")
        _whisper_model = whisper.load_model(size)

    try:
        result = _whisper_model.transcribe(wav_path, language="en")
        text   = result["text"].strip()
        print(f"[STT] Transcribed: {text[:80]}{'...' if len(text) > 80 else ''}")
        return text
    except Exception as e:
        raise RuntimeError(f"Whisper transcription failed: {e}")
