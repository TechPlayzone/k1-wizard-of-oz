"""
session_manager.py
In-memory store for per-session API keys.

Keys are NEVER written to disk, logged, or persisted.
They exist only in memory and are cleared when:
  - The Flask server restarts
  - The user calls clear_key()
  - The browser tab closes (frontend clears sessionStorage)

Usage:
    from session_manager import session_store
    session_store.set_key(session_id, "anthropic", "sk-ant-...")
    key = session_store.get_key(session_id, "anthropic")
    session_store.clear_key(session_id, "anthropic")
    session_store.clear_session(session_id)
"""

import threading
from datetime import datetime, timedelta

# Session keys expire after this many minutes of inactivity
SESSION_TIMEOUT_MINUTES = 120


class SessionManager:
    def __init__(self):
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_key(self, session_id: str, provider: str, api_key: str) -> None:
        """Store a session-scoped API key for a provider."""
        with self._lock:
            if session_id not in self._store:
                self._store[session_id] = {}
            self._store[session_id][provider] = {
                "key":      api_key,
                "set_at":   datetime.utcnow(),
                "last_used": datetime.utcnow(),
            }

    def get_key(self, session_id: str, provider: str) -> object:
        """
        Retrieve a session API key.
        Returns None if not set or session has expired.
        """
        with self._lock:
            session = self._store.get(session_id, {})
            entry   = session.get(provider)
            if not entry:
                return None

            # Expire stale sessions
            if datetime.utcnow() - entry["last_used"] > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                del self._store[session_id][provider]
                return None

            # Update last used timestamp
            entry["last_used"] = datetime.utcnow()
            return entry["key"]

    def clear_key(self, session_id: str, provider: str) -> None:
        """Remove a single provider key for a session."""
        with self._lock:
            if session_id in self._store:
                self._store[session_id].pop(provider, None)

    def clear_session(self, session_id: str) -> None:
        """Remove all keys for a session (called on logout)."""
        with self._lock:
            self._store.pop(session_id, None)

    def has_key(self, session_id: str, provider: str) -> bool:
        return self.get_key(session_id, provider) is not None


# Single shared instance imported by app.py
session_store = SessionManager()
