"""
config.py
Loads and validates all settings from .env

All other backend modules import from here:
    from config import cfg
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── K1 Robot ─────────────────────────────────────────────
    K1_IP:   str = os.getenv("K1_IP",   "192.168.0.176")
    K1_PORT: int = int(os.getenv("K1_PORT", 6666))

    # ── LLM Provider ─────────────────────────────────────────
    # Default provider set by admin. Users can override per session.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")

    # ── Ollama ────────────────────────────────────────────────
    OLLAMA_URL:   str = os.getenv("OLLAMA_URL",   "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")

    # ── Anthropic ─────────────────────────────────────────────
    # API key is session-scoped (never stored here)
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    # ── OpenAI ────────────────────────────────────────────────
    # API key is session-scoped (never stored here)
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # ── Piper TTS ─────────────────────────────────────────────
    PIPER_VOICE:      str = os.getenv("PIPER_VOICE",      "en_US-lessac-medium")
    PIPER_VOICE_PATH: str = os.getenv("PIPER_VOICE_PATH", "./voices/en_US-lessac-medium.onnx")

    # ── Flask ─────────────────────────────────────────────────
    FLASK_HOST:       str = os.getenv("FLASK_HOST",       "0.0.0.0")
    FLASK_PORT:       int = int(os.getenv("FLASK_PORT",   5000))
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "change-me-before-deploying")

    # ── Admin ─────────────────────────────────────────────────
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "changeme123")

    # ── Isaac Sim ─────────────────────────────────────────────
    ISAAC_SERVER_IP:  str = os.getenv("ISAAC_SERVER_IP",  "192.168.0.100")
    ISAAC_STREAM_PORT: int = int(os.getenv("ISAAC_STREAM_PORT", 8211))

    def validate(self):
        """
        Returns a list of warning strings for missing or default values.
        Called at startup so educators see clear guidance.
        """
        warnings = []

        if self.FLASK_SECRET_KEY == "change-me-before-deploying":
            warnings.append(
                "FLASK_SECRET_KEY is still the default. "
                "Set a strong random value in .env before sharing the dashboard."
            )
        if self.ADMIN_PASSWORD == "changeme123":
            warnings.append(
                "ADMIN_PASSWORD is still the default. "
                "Set a strong password in .env."
            )
        if not os.path.exists(self.PIPER_VOICE_PATH):
            warnings.append(
                f"Piper voice model not found at {self.PIPER_VOICE_PATH}. "
                "See docs/SETUP.md Step 6."
            )
        return warnings


# Single shared instance imported by all other modules
cfg = Config()
