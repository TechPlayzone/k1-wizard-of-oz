"""
tts.py
Convert text to speech using Piper TTS.

Piper runs locally with no internet connection required.
Output is a WAV file written to a temp path, then sent to the K1 speaker.

Usage:
    from tts import synthesize
    wav_path = synthesize("Hello, I am K1.")
"""

import os
import subprocess
import tempfile
from config import cfg


def synthesize(text: str, voice_path: str | None = None) -> str:
    """
    Convert text to a WAV file using Piper TTS.

    Args:
        text:       The text to speak
        voice_path: Override the default voice model path from .env

    Returns:
        Path to the generated WAV file (caller is responsible for cleanup)

    Raises:
        FileNotFoundError: Voice model .onnx file not found
        RuntimeError:      Piper synthesis failed
    """
    model = voice_path or cfg.PIPER_VOICE_PATH

    if not os.path.exists(model):
        raise FileNotFoundError(
            f"Piper voice model not found at: {model}\n"
            "See docs/SETUP.md Step 6 to download a voice model."
        )

    # Write to a named temp file — caller cleans up
    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav",
        prefix="k1_tts_",
        delete=False,
    )
    tmp.close()
    wav_path = tmp.name

    try:
        result = subprocess.run(
            ["piper", "--model", model, "--output_file", wav_path],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Piper TTS failed (exit {result.returncode}):\n"
                f"{result.stderr.decode('utf-8', errors='replace')}"
            )
        return wav_path

    except FileNotFoundError:
        raise RuntimeError(
            "piper command not found. "
            "Install with: pip install piper-tts"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Piper TTS timed out after 30 seconds.")


def cleanup(wav_path: str) -> None:
    """Delete a temp WAV file after it has been used."""
    try:
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)
    except OSError:
        pass  # Non-critical — file will be cleaned up on next restart
