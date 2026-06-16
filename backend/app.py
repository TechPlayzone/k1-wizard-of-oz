#!/usr/bin/env python3
# =============================================================================
# K1 Flask Server — Full Wizard-of-Oz Backend
# AI Innovation Center @ Hillsborough College | In partnership with URG Americas
# AI PREP4WORK Initiative — FIPSE Grant Program
# Deshjuana Bagley, Associate Dean, A.S. Degree Programs
# =============================================================================
# Run:  python backend/app.py
# Dash: http://localhost:5000
# =============================================================================

import os
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ── Backend modules ───────────────────────────────────────────
from config          import cfg
from k1_handler      import robot
from battery_monitor import battery_monitor, get_battery_status
from camera          import camera_handler, camera_stream
from llm_router      import get_llm_response, extract_action
from tts             import synthesize, speak_on_robot, cleanup
from session_manager import session_store
from flask           import Response, session

# ── Flask setup ───────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR)
app.secret_key = cfg.FLASK_SECRET_KEY
CORS(app)

# ── Safety state ──────────────────────────────────────────────
# Tracks whether the operator has confirmed the robot's startup position.
# Controls are locked until this is set via POST /api/safety/confirm
_safety_confirmed   = False
_confirmed_position = None   # "damp_floor" | "prep" | "walk"
_safety_lock        = threading.Lock()


# =============================================================================
# STARTUP
# =============================================================================

def startup():
    print("=" * 58)
    print("  K1 Wizard-of-Oz Dashboard")
    print("  AI Innovation Center · Hillsborough College")
    print("  AI PREP4WORK Initiative — FIPSE Grant Program")
    print("=" * 58)

    # Validate config
    warnings = cfg.validate()
    for w in warnings:
        print(f"[WARN] {w}")

    # Connect to robot
    print("[startup] Connecting to K1...")
    robot.connect()

    # Start battery monitor
    battery_monitor.start()

    # Start camera subscriber
    camera_handler.start()

    print(f"[startup] Dashboard: http://{cfg.FLASK_HOST}:{cfg.FLASK_PORT}")
    print("[startup] Ready.\n")


# =============================================================================
# FRONTEND
# =============================================================================

@app.route('/')
def index():
    """Serve the Wizard-of-Oz dashboard."""
    return send_from_directory(FRONTEND_DIR, 'k1_dashboard.html')

@app.route('/chat-only')
def chat_only():
    """Serve the BU chat-only interface."""
    return send_from_directory(FRONTEND_DIR, 'BU_Talk_index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# =============================================================================
# HEALTH
# =============================================================================

@app.route('/health')
def health():
    """System health check — Ollama, robot, battery."""
    import requests as req
    try:
        r = req.get(f"{cfg.OLLAMA_URL}/api/tags", timeout=3)
        models  = [m["name"] for m in r.json().get("models", [])]
        ollama  = "ok"
    except Exception:
        models = []
        ollama = "unreachable"

    battery = get_battery_status()

    return jsonify({
        "server":           "ok",
        "ollama":           ollama,
        "models":           models,
        "model":            cfg.OLLAMA_MODEL,
        "k1_ip":            cfg.K1_IP,
        "robot_connected":  robot.connected,
        "robot_mode":       robot.current_mode,
        "battery":          battery,
        "safety_confirmed": _safety_confirmed,
        "confirmed_position": _confirmed_position,
    })


# =============================================================================
# SAFETY STATE
# =============================================================================

@app.route('/api/safety/confirm', methods=['POST'])
def safety_confirm():
    """
    Operator confirms the robot's current physical position before
    any controls are unlocked. Called by the startup safety modal.

    Body: { "position": "damp_floor" | "prep" | "walk" | "unknown" }

    - damp_floor : Robot is lying face-down, motors relaxed. Safe.
    - prep       : Robot is stiff/kneeling but not standing. Moderate.
    - walk       : Robot is standing. Movement controls available.
    - unknown    : Operator does not know — dashboard stays locked,
                   safety instructions are shown.
    """
    global _safety_confirmed, _confirmed_position

    data     = request.get_json() or {}
    position = data.get('position', 'unknown')

    if position == 'unknown':
        # Do NOT unlock — return safety instructions
        return jsonify({
            "confirmed": False,
            "position":  "unknown",
            "message":   (
                "STOP — Do NOT touch the robot until you know its state. "
                "If it is standing and moving, do NOT approach. "
                "Power off from a safe distance, lay it face-down carefully, "
                "then reboot. After reboot it will be in Damp mode."
            ),
            "instructions": [
                "Look at K1 — is it standing or moving? Do NOT approach.",
                "Locate the power button. Power off from a safe distance.",
                "Once off, carefully lay K1 face-down on the floor.",
                "Power back on. Wait for startup tone and green light.",
                "Robot starts in Damp mode. Return here and select 'Lying face-down (Damp)'."
            ]
        }), 200

    # Sync robot handler mode to match confirmed position
    with _safety_lock:
        _safety_confirmed   = True
        _confirmed_position = position

    if position == 'damp_floor':
        robot.current_mode = 'damp'
    elif position == 'prep':
        robot.current_mode = 'prep'
    elif position == 'walk':
        robot.current_mode = 'walk'

    return jsonify({
        "confirmed": True,
        "position":  position,
        "mode":      robot.current_mode,
        "message":   f"Safety confirmed. Robot mode set to '{robot.current_mode}'."
    })


@app.route('/api/safety/reset', methods=['POST'])
def safety_reset():
    """Re-lock the dashboard — forces operator to re-confirm state."""
    global _safety_confirmed, _confirmed_position
    with _safety_lock:
        _safety_confirmed   = False
        _confirmed_position = None
    return jsonify({"confirmed": False, "message": "Safety state reset. Please re-confirm robot position."})


def require_safety(f):
    """Decorator — blocks robot control routes until safety is confirmed."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _safety_confirmed:
            return jsonify({
                "error": "Safety check required.",
                "detail": "Confirm the robot's current position before using controls."
            }), 403
    return decorated


# =============================================================================
# ROBOT STATUS
# =============================================================================

@app.route('/api/status')
def status():
    """Real-time robot status for the dashboard status strip."""
    battery = get_battery_status()
    return jsonify({
        "connected":        robot.connected,
        "mode":             robot.current_mode,
        "battery":          battery.get("level"),
        "battery_status":   battery.get("status"),
        "battery_warning":  battery.get("warning"),
        "battery_critical": battery.get("critical"),
        "safety_confirmed": _safety_confirmed,
        "confirmed_position": _confirmed_position,
    })


# =============================================================================
# MODE CONTROL
# =============================================================================

@app.route('/api/mode', methods=['POST'])
def set_mode():
    """
    Change robot mode. Safety confirmed required.

    Body: { "mode": "damp" | "prep" | "walk" }

    Safety rules enforced here:
      - Damp:  Always allowed — safe from any state
      - Prep:  Only from Damp
      - Walk:  Only from Prep (triggers GetUp)
    """
    if not _safety_confirmed:
        return jsonify({"error": "Confirm robot position first."}), 403

    data        = request.get_json() or {}
    target_mode = data.get('mode', '').lower()

    if target_mode not in ('damp', 'prep', 'walk'):
        return jsonify({"error": f"Unknown mode: {target_mode}"}), 400

    current = robot.current_mode

    # ── Safety guards ─────────────────────────────────────────
    if target_mode == 'prep' and current == 'walk':
        return jsonify({
            "error": "Cannot go directly from Walk to Prep.",
            "detail": "Click Damp first to safely lower the robot, then Prep."
        }), 400

    if target_mode == 'walk' and current == 'damp':
        return jsonify({
            "error": "Cannot go directly from Damp to Walk.",
            "detail": "Click Prep first, wait for robot to stiffen, then Walk."
        }), 400

    # ── Execute mode change ───────────────────────────────────
    try:
        if target_mode == 'damp':
            success = robot.set_damp_mode()
        elif target_mode == 'prep':
            success = robot.set_prep_mode()
        elif target_mode == 'walk':
            success = robot.set_walk_mode()

        if success:
            return jsonify({
                "ok":   True,
                "mode": robot.current_mode,
                "message": f"Mode changed to {robot.current_mode}"
            })
        else:
            return jsonify({
                "error": f"Mode change to '{target_mode}' failed.",
                "detail": "Check robot state and try again. Is it in the correct position?"
            }), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# MOVEMENT
# =============================================================================

@app.route('/api/move', methods=['POST'])
def move():
    """
    Send a movement command. Robot must be in Walk mode.

    Body: { "command": "walk_forward" | "walk_backward" |
                       "turn_left" | "turn_right" | "stop",
            "duration": 2.0  (optional, seconds) }
    """
    if not _safety_confirmed:
        return jsonify({"error": "Confirm robot position first."}), 403

    if robot.current_mode != 'walk':
        return jsonify({
            "error": "Robot must be in Walk mode to move.",
            "detail": f"Current mode is '{robot.current_mode}'. Click Walk first."
        }), 400

    data     = request.get_json() or {}
    command  = data.get('command', '')
    duration = data.get('duration', None)

    valid_commands = ['walk_forward', 'walk_backward', 'turn_left', 'turn_right', 'stop']
    if command not in valid_commands:
        return jsonify({"error": f"Unknown command: {command}"}), 400

    try:
        # Run movement in background thread so Flask doesn't block
        def _move():
            robot.move(command, duration)
        t = threading.Thread(target=_move, daemon=True)
        t.start()

        return jsonify({"ok": True, "command": command})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# GESTURES
# =============================================================================

@app.route('/api/gesture', methods=['POST'])
def gesture():
    """
    Trigger a robot gesture.

    Body: { "gesture": "wave" | "nod" | "thumbs_up" }
    """
    if not _safety_confirmed:
        return jsonify({"error": "Confirm robot position first."}), 403

    data         = request.get_json() or {}
    gesture_name = data.get('gesture', '')

    if gesture_name not in ('wave', 'nod', 'thumbs_up'):
        return jsonify({"error": f"Unknown gesture: {gesture_name}"}), 400

    try:
        def _gesture():
            robot.gesture(gesture_name)
        t = threading.Thread(target=_gesture, daemon=True)
        t.start()
        return jsonify({"ok": True, "gesture": gesture_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# LLM CHAT + TTS
# =============================================================================

# In-memory conversation history per session
_conversations = {}
_conv_lock     = threading.Lock()


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Send a message to the LLM. K1 speaks the response via Piper TTS.

    Body: {
        "message":  "Hello K1!",
        "provider": "ollama" | "anthropic" | "openai",   (optional, default from config)
        "session_id": "abc123"                            (optional)
    }
    """
    data       = request.get_json() or {}
    message    = data.get('message', '').strip()
    provider   = data.get('provider', cfg.LLM_PROVIDER)
    session_id = data.get('session_id', 'default')

    if not message:
        return jsonify({"error": "No message provided."}), 400

    # Get session API key if needed
    api_key = None
    if provider in ('anthropic', 'openai'):
        api_key = session_store.get_key(session_id, provider)
        if not api_key:
            return jsonify({
                "error": f"No {provider} API key in session.",
                "detail": "Enter your API key in the settings panel."
            }), 401

    # Get conversation history
    with _conv_lock:
        history = _conversations.get(session_id, [])

    try:
        # Get LLM response
        raw_response = get_llm_response(
            provider=provider,
            message=message,
            api_key=api_key,
            conversation_history=history,
        )

        # Extract action tag from response
        clean_text, action = extract_action(raw_response)

        # Update conversation history
        with _conv_lock:
            if session_id not in _conversations:
                _conversations[session_id] = []
            _conversations[session_id].append({"role": "user",      "content": message})
            _conversations[session_id].append({"role": "assistant", "content": clean_text})
            # Keep last 20 turns
            _conversations[session_id] = _conversations[session_id][-20:]

        # TTS — synthesize and speak on robot
        spoken     = False
        speak_error = None
        wav_path   = None
        try:
            wav_path = synthesize(clean_text)
            spoken   = speak_on_robot(wav_path)
        except Exception as e:
            speak_error = str(e)
            print(f"[TTS] Error: {e}")
        finally:
            if wav_path:
                cleanup(wav_path)

        # Execute robot action if present (in background)
        if action and _safety_confirmed:
            def _do_action():
                if action in ('wave', 'nod', 'thumbs_up'):
                    robot.gesture(action)
                elif action in ('walk_forward', 'walk_backward',
                                'turn_left', 'turn_right', 'stop'):
                    if robot.current_mode == 'walk':
                        robot.move(action)
            t = threading.Thread(target=_do_action, daemon=True)
            t.start()

        return jsonify({
            "response":    clean_text,
            "action":      action,
            "spoken":      spoken,
            "speak_error": speak_error,
            "provider":    provider,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat/reset', methods=['POST'])
def reset_conversation():
    """Clear conversation history for a session."""
    data       = request.get_json() or {}
    session_id = data.get('session_id', 'default')
    with _conv_lock:
        _conversations.pop(session_id, None)
    return jsonify({"ok": True, "message": "Conversation cleared."})


# =============================================================================
# SESSION API KEYS
# =============================================================================

@app.route('/api/session/key', methods=['POST'])
def set_session_key():
    """
    Store a session-scoped API key. Never written to disk.

    Body: { "session_id": "abc", "provider": "anthropic", "key": "sk-ant-..." }
    """
    data       = request.get_json() or {}
    session_id = data.get('session_id', 'default')
    provider   = data.get('provider', '')
    key        = data.get('key', '').strip()

    if provider not in ('anthropic', 'openai'):
        return jsonify({"error": "Provider must be 'anthropic' or 'openai'."}), 400
    if not key:
        return jsonify({"error": "No key provided."}), 400

    session_store.set_key(session_id, provider, key)
    return jsonify({"ok": True, "provider": provider, "message": "Key stored in memory only."})


@app.route('/api/session/key', methods=['DELETE'])
def clear_session_key():
    """Remove a session API key."""
    data       = request.get_json() or {}
    session_id = data.get('session_id', 'default')
    provider   = data.get('provider', '')
    session_store.clear_key(session_id, provider)
    return jsonify({"ok": True, "message": f"{provider} key cleared."})


# =============================================================================
# CAMERA
# =============================================================================

@app.route('/api/camera/stream')
def camera_stream_route():
    """MJPEG camera stream. Display with <img src='/api/camera/stream'>"""
    return Response(
        camera_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/camera/status')
def camera_status():
    return jsonify({
        "active":    camera_handler._running,
        "has_frame": camera_handler.has_frame,
    })


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    startup()
    app.run(
        host=cfg.FLASK_HOST,
        port=cfg.FLASK_PORT,
        debug=False,        # Never debug=True in lab — exposes reloader
        threaded=True,      # Required for MJPEG stream + concurrent requests
    )
