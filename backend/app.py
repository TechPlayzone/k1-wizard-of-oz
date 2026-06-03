"""
app.py
K1 Wizard-of-Oz Dashboard — Flask Backend
Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program

Deshjuana Bagley, Associate Dean, A.S. Degree Programs

─────────────────────────────────────────────────────────────
Routes
─────────────────────────────────────────────────────────────
  Static
    GET  /                          Serve the dashboard

  Chat
    POST /api/chat/send             Typed text → LLM → TTS → K1 speaker

  Robot movement
    POST /api/robot/move            Move command (walk_forward, turn_left, etc.)
    POST /api/robot/mode            Set mode (walk | damp)
    GET  /api/robot/status          Battery, mode, latency

  Gestures
    POST /api/robot/gesture         Trigger gesture (wave, nod, thumbs_up)

  Session (API keys — in-memory only)
    POST /api/session/set-key       Store session API key
    POST /api/session/clear-key     Clear session API key
    POST /api/session/logout        Clear all session keys

  Admin (password protected)
    POST /api/admin/login           Exchange password for admin token
    GET  /api/admin/config          Get current config (sanitized)
    POST /api/admin/config          Update K1 IP and LLM provider default
─────────────────────────────────────────────────────────────
"""

import os
import uuid
import bcrypt
from flask import (
    Flask, request, jsonify, send_from_directory, session
)
from flask_cors import CORS

from config          import cfg
from llm_router      import get_llm_response, extract_action
from k1_handler      import robot
from tts             import synthesize, cleanup
from stt             import transcribe_text
from session_manager import session_store

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
)
app.secret_key = cfg.FLASK_SECRET_KEY
CORS(app, supports_credentials=True)

# ── Startup ───────────────────────────────────────────────────────────────────

print("\n── K1 Wizard-of-Oz Dashboard ────────────────────────────")
print("   Hillsborough College AI Innovation Center")
print("   AI PREP4WORK Initiative — FIPSE Grant Program")
print("   Deshjuana Bagley, Associate Dean, A.S. Degree Programs")
print("─────────────────────────────────────────────────────────\n")

# Print any config warnings
warnings = cfg.validate()
for w in warnings:
    print(f"[CONFIG WARNING] {w}")
if warnings:
    print()

# Hash admin password for session comparison
_admin_pw_hash = bcrypt.hashpw(
    cfg.ADMIN_PASSWORD.encode("utf-8"),
    bcrypt.gensalt()
)

# Connect to K1 at startup
robot.connect()

# ── Static: serve dashboard ───────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ── Helper: get session ID ────────────────────────────────────────────────────

def get_session_id() -> str:
    """Create or retrieve a unique session ID for this browser session."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.route("/api/chat/send", methods=["POST"])
def chat_send():
    """
    Typed text → LLM → TTS → K1 speaker

    Request JSON:
        {
            "message":  "Hello K1",
            "provider": "ollama",          // optional, overrides default
            "history":  [                  // optional conversation history
                {"role": "user",      "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }

    Response JSON:
        {
            "response": "I am K1, hello! [ACTION:wave]",
            "clean_response": "I am K1, hello!",
            "action": "wave",
            "provider": "ollama",
            "tts_ok": true
        }
    """
    data     = request.get_json(force=True)
    message  = (data.get("message") or "").strip()
    provider = data.get("provider") or cfg.LLM_PROVIDER
    history  = data.get("history",  [])

    if not message:
        return jsonify({"error": "message is required"}), 400

    # Validate typed text
    clean_input = transcribe_text(message)

    # Resolve session API key if needed
    sid     = get_session_id()
    api_key = None
    if provider in ("anthropic", "openai"):
        api_key = session_store.get_key(sid, provider)
        if not api_key:
            return jsonify({
                "error": f"No API key set for {provider}. "
                         "Enter your session key in the Conversation panel."
            }), 401

    # Get LLM response
    try:
        llm_response = get_llm_response(
            provider=provider,
            message=clean_input,
            api_key=api_key,
            conversation_history=history,
        )
    except (ValueError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 500

    # Parse action tag out of response
    clean_response, action = extract_action(llm_response)

    # TTS synthesis → K1 speaker
    tts_ok  = False
    wav_path = None
    try:
        wav_path = synthesize(clean_response)
        tts_ok   = robot.speak(wav_path)
    except Exception as e:
        print(f"[TTS/speak] {e}")
    finally:
        if wav_path:
            cleanup(wav_path)

    # Execute action if present
    if action:
        _dispatch_action(action)

    return jsonify({
        "response":       llm_response,
        "clean_response": clean_response,
        "action":         action,
        "provider":       provider,
        "tts_ok":         tts_ok,
    })


def _dispatch_action(action: str) -> None:
    """Route an action tag to movement or gesture."""
    movement_commands = {
        "walk_forward", "walk_backward",
        "turn_left", "turn_right", "stop"
    }
    gesture_commands = {"wave", "nod", "thumbs_up"}

    if action in movement_commands:
        robot.move(action)
    elif action in gesture_commands:
        robot.gesture(action)
    else:
        print(f"[action] Unknown action tag: {action}")


# ── Robot movement ────────────────────────────────────────────────────────────

@app.route("/api/robot/move", methods=["POST"])
def robot_move():
    """
    Execute a movement command from the dashboard direction pad.

    Request JSON:
        { "command": "walk_forward", "duration": 2.0 }
    """
    data     = request.get_json(force=True)
    command  = data.get("command", "")
    duration = data.get("duration", None)

    if not command:
        return jsonify({"error": "command is required"}), 400

    ok = robot.move(command, duration=duration)
    return jsonify({"ok": ok, "command": command})


@app.route("/api/robot/mode", methods=["POST"])
def robot_mode():
    """
    Set robot mode.

    Request JSON:
        { "mode": "walk" }   or   { "mode": "damp" }
    """
    data = request.get_json(force=True)
    mode = data.get("mode", "")

    if mode == "walk":
        robot.set_walk_mode()
    elif mode == "damp":
        robot.set_damp_mode()
    else:
        return jsonify({"error": f"Unknown mode: {mode}"}), 400

    return jsonify({"ok": True, "mode": mode})


@app.route("/api/robot/status", methods=["GET"])
def robot_status():
    """Return current robot status for the dashboard status strip."""
    return jsonify(robot.get_status())


# ── Gestures ──────────────────────────────────────────────────────────────────

@app.route("/api/robot/gesture", methods=["POST"])
def robot_gesture():
    """
    Trigger a gesture from the dashboard gesture panel.

    Request JSON:
        { "gesture": "wave" }
    """
    data    = request.get_json(force=True)
    name    = data.get("gesture", "")

    if not name:
        return jsonify({"error": "gesture name is required"}), 400

    ok = robot.gesture(name)
    return jsonify({"ok": ok, "gesture": name})


# ── Session API key management ────────────────────────────────────────────────

@app.route("/api/session/set-key", methods=["POST"])
def session_set_key():
    """
    Store a session-scoped API key (in memory only — never written to disk).

    Request JSON:
        { "provider": "anthropic", "api_key": "sk-ant-..." }
    """
    data     = request.get_json(force=True)
    provider = data.get("provider", "")
    api_key  = data.get("api_key",  "")

    if not provider or not api_key:
        return jsonify({"error": "provider and api_key are required"}), 400

    if provider not in ("anthropic", "openai"):
        return jsonify({"error": "provider must be 'anthropic' or 'openai'"}), 400

    sid = get_session_id()
    session_store.set_key(sid, provider, api_key)
    print(f"[session] API key set for provider: {provider} (session: {sid[:8]}...)")

    return jsonify({"ok": True, "provider": provider})


@app.route("/api/session/clear-key", methods=["POST"])
def session_clear_key():
    """Clear the API key for a specific provider."""
    data     = request.get_json(force=True)
    provider = data.get("provider", "")
    sid      = get_session_id()
    session_store.clear_key(sid, provider)
    return jsonify({"ok": True})


@app.route("/api/session/logout", methods=["POST"])
def session_logout():
    """Clear all session API keys (called when user closes dashboard)."""
    sid = get_session_id()
    session_store.clear_session(sid)
    session.clear()
    return jsonify({"ok": True})


# ── Admin console ─────────────────────────────────────────────────────────────

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    """
    Verify admin password and return a session admin token.

    Request JSON:
        { "password": "..." }
    """
    data     = request.get_json(force=True)
    password = (data.get("password") or "").encode("utf-8")

    if bcrypt.checkpw(password, _admin_pw_hash):
        session["is_admin"] = True
        return jsonify({"ok": True})
    else:
        return jsonify({"error": "Incorrect password"}), 401


@app.route("/api/admin/config", methods=["GET"])
def admin_get_config():
    """Return current config (no secrets) for the admin console."""
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403

    return jsonify({
        "k1_ip":          cfg.K1_IP,
        "k1_port":        cfg.K1_PORT,
        "llm_provider":   cfg.LLM_PROVIDER,
        "ollama_model":   cfg.OLLAMA_MODEL,
        "anthropic_model": cfg.ANTHROPIC_MODEL,
        "openai_model":   cfg.OPENAI_MODEL,
        "piper_voice":    cfg.PIPER_VOICE,
        "isaac_server_ip": cfg.ISAAC_SERVER_IP,
    })


@app.route("/api/admin/config", methods=["POST"])
def admin_set_config():
    """
    Update runtime config values.
    Only K1 IP and LLM provider can be changed at runtime.
    Other settings require editing .env and restarting.
    """
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(force=True)

    if "k1_ip" in data:
        cfg.K1_IP = data["k1_ip"]
        robot.disconnect()
        robot.connect()

    if "llm_provider" in data:
        p = data["llm_provider"]
        if p in ("ollama", "anthropic", "openai"):
            cfg.LLM_PROVIDER = p

    return jsonify({"ok": True, "k1_ip": cfg.K1_IP, "llm_provider": cfg.LLM_PROVIDER})


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Dashboard: http://localhost:{cfg.FLASK_PORT}\n")
    app.run(
        host=cfg.FLASK_HOST,
        port=cfg.FLASK_PORT,
        debug=False,  # Keep False — debug mode reloads and re-connects K1
    )
