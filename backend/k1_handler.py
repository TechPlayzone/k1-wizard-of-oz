"""
k1_handler.py
K1 robot control via ROS2 RPC service and button events.

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs

═══════════════════════════════════════════════════════════════
CONFIRMED RPC API IDs (tested 2026-06-17 on K1 firmware v1.6)
═══════════════════════════════════════════════════════════════
  api_id  body                              result
  ──────  ────────────────────────────────  ──────────────────────
  2000    {"mode": 0}                       → Damp  (status=0)
  2000    {"mode": 1}                       → Prep  (status=0)
  2001    {"vx": f, "vy": f, "vyaw": f}    → Move  (status=0)
  2004    {"pitch": f, "yaw": f}            → Head  (status=0)
  2008    {}                                → GetUp (status=0)
  2017    {}                                → GetMode → {"mode": N}
  2029    {"dance_id": N}                   → Dance (status=0) ✅

CONFIRMED DANCE IDs (api_id 2029):
  0 = head boppin
  1 = hip hop
  2 = kung fu
  3 = kick boxing  ⚠ needs clear space — robot kicks!
  4 = unknown
  5 = roundhouse karate  ⚠ needs clear space — robot kicks!

CONFIRMED RPC MODE VALUES:
  0 = Damp
  1 = Prep
  2 = Walk (after GetUp + button event)
  4 = Walk (alternate walk state — treat same as 2)

CONFIRMED BUTTON EVENTS (via /button_event topic):
  {event: 1, button: 1} → arms go down
  {event: 1, button: 2} → partial walk enable
  {event: 2, button: 2} → full Walk mode (green pulsing) ← REQUIRED for Move
  Publishing {event:2, button:2} AFTER GetUp enables RPC Move commands.
  Without it, Move returns status=400.

KNOWN RPC PARSER BUG (fixed here):
  ROS2 output contains TWO body= fields:
    body='{}'           ← request body (always empty — WRONG)
    body='{"mode":0}'  ← response body (correct)
  re.search() returns first match = wrong empty body.
  Fix: re.findall() + take LAST match = correct response body.

SAFE MODE SEQUENCE:
  Up:   Damp → Prep (RPC 2000 mode:1) → physical Stand button
        → button event {event:2, button:2} → Walk/Move enabled
  Down: Walk → Damp (RPC 2000 mode:0) from floor ONLY
        ⚠ NEVER Damp from standing — robot drops and may not recover

SAFETY RULES:
  - Always query actual robot mode via RPC before any transition
  - Never call GetUp from Damp — must Prep first
  - Never call Prep if robot is in Walk — Damp first
  - Never send Move unless robot is confirmed in Walk (mode 2 or 4)
  - Never Damp from standing — use Damp only when robot is on the floor
  - If mode cannot be verified, block the action — never assume safe
  - Dances (api_id 2029) need clear space — some involve kicks
"""

import json
import time
import subprocess
import re

# ── ROS2 setup ────────────────────────────────────────────────
ROS2_SETUP = (
    "source /opt/ros/humble/setup.bash && "
    "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
)

# ── Movement constants ────────────────────────────────────────
WALK_SPEED    = 0.15  # m/s — conservative for demos
TURN_SPEED    = 0.3   # rad/s turn
MOVE_DURATION = 2.0   # seconds per timed movement command

# ── RPC API IDs ───────────────────────────────────────────────
API_CHANGE_MODE = 2000
API_MOVE        = 2001
API_ROTATE_HEAD = 2004
API_GET_UP      = 2008
API_GET_MODE    = 2017
API_DANCE       = 2029   # confirmed working ✅

# ── Mode constants ────────────────────────────────────────────
MODE_DAMP     = 0
MODE_PREP     = 1
MODE_WALK     = 2
MODE_WALK_ALT = 4

WALK_MODES = (MODE_WALK, MODE_WALK_ALT)

# ── Dance IDs (api_id 2029) ───────────────────────────────────
DANCE_IDS = {
    "head_bop":  0,
    "hip_hop":   1,
    "kung_fu":   2,
    "kickbox":   3,   # ⚠ kicks — needs clear space
    "dance4":    4,   # unknown — test carefully
    "karate":    5,   # ⚠ kicks — needs clear space
}

# ── Booster SDK (optional) ────────────────────────────────────
_sdk_available = False
try:
    from booster_robotics_sdk_python import (
        B1LocoClient, ChannelFactory, B1HandAction,
    )
    _sdk_available = True
    print("[k1_handler] Booster SDK loaded")
except ImportError:
    print("[k1_handler] Booster SDK not found — RPC only mode")


# =============================================================================
# RPC CALL — with parser bug fix
# =============================================================================

def rpc_call(api_id: int, body: dict, timeout: int = 10) -> tuple:
    """
    Call the Booster RPC service via ROS2.
    Returns (status, response_body_dict).
    status == 0 means success.
    status == -1 means timeout or subprocess error.

    PARSER BUG FIX: ROS2 output contains TWO body= fields.
    re.search() returns the first (always empty request body).
    We use re.findall() and take the LAST match (response body).
    """
    body_str = json.dumps(body)
    cmd = (
        f"{ROS2_SETUP}"
        f"ros2 service call /booster_rpc_service "
        f"booster_interface/srv/RpcService "
        f"\"{{msg: {{api_id: {api_id}, body: '{body_str}'}}}}\""
    )
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout, executable="/bin/bash"
        )
        output       = result.stdout
        status_match = re.search(r"status=(\d+)", output)
        status       = int(status_match.group(1)) if status_match else -1

        # Parser bug fix — take LAST body= match (response, not request)
        body_matches = re.findall(r"body='([^']*)'", output)
        resp_body    = {}
        if body_matches:
            last_body = body_matches[-1]
            if last_body:
                try:
                    resp_body = json.loads(last_body)
                except Exception:
                    pass

        return status, resp_body

    except subprocess.TimeoutExpired:
        print(f"[RPC] Timeout — api_id={api_id}")
        return -1, {}
    except Exception as e:
        print(f"[RPC] Error — api_id={api_id}: {e}")
        return -1, {}


def _publish_button_event(event: int, button: int, timeout: int = 8) -> bool:
    """
    Publish a button event to /button_event topic.
    Required after GetUp to enable Walk/Move commands.
    {event:2, button:2} = full Walk mode (green pulsing light).
    Without this, Move RPC returns status=400.
    """
    cmd = (
        f"{ROS2_SETUP}"
        f"ros2 topic pub --once /button_event "
        f"booster_interface/msg/ButtonEventMsg "
        f"\"{{event: {event}, button: {button}}}\""
    )
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout, executable="/bin/bash"
        )
        success = "publishing" in result.stdout.lower()
        print(f"[K1] Button event {{event:{event}, button:{button}}} — {'OK' if success else 'FAILED'}")
        return success
    except Exception as e:
        print(f"[K1] Button event error: {e}")
        return False


def _get_actual_mode(timeout: int = 8) -> int:
    """
    Query the robot for its ACTUAL current mode via RPC.
    Returns raw RPC mode integer, or -1 if query fails.
    Always called before mode transitions — never trust cached state.
    """
    status, resp = rpc_call(API_GET_MODE, {}, timeout=timeout)
    if status == 0 and resp:
        mode = resp.get("mode", -1)
        print(f"[K1] Actual mode: {mode}")
        return mode
    print(f"[K1] GetMode failed (status={status})")
    return -1


def _rpc_mode_to_str(rpc_mode: int) -> str:
    return {
        MODE_DAMP:     "damp",
        MODE_PREP:     "prep",
        MODE_WALK:     "walk",
        MODE_WALK_ALT: "walk",
    }.get(rpc_mode, "unknown")


# =============================================================================
# K1 ROBOT
# =============================================================================

class K1Robot:
    def __init__(self):
        self.client       = None
        self.connected    = False
        self.current_mode = "unknown"

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Connect to K1. Syncs actual mode from robot via RPC.
        SDK init attempted for future gesture support but not required.
        """
        try:
            if _sdk_available:
                ChannelFactory.Instance().Init(0, "wlP5p1s0")
                self.client = B1LocoClient()
                self.client.Init()
                print("[K1] Booster SDK connected")
        except Exception as e:
            print(f"[K1] SDK connect warning (non-fatal): {e}")

        self.connected = True

        # Sync actual mode — use "unknown" not "damp" if query fails
        # so dashboard stays locked until mode is confirmed
        actual = _get_actual_mode()
        if actual >= 0:
            self.current_mode = _rpc_mode_to_str(actual)
            print(f"[K1] Mode synced: {self.current_mode} (rpc={actual})")
        else:
            self.current_mode = "unknown"
            print("[K1] Mode sync failed — controls locked until mode confirmed")

        return True

    def disconnect(self):
        self.connected    = False
        self.client       = None
        print("[K1] Disconnected")

    # ── Mode transitions ──────────────────────────────────────

    def set_damp_mode(self) -> dict:
        """
        Damp — motors relax.
        ⚠ ONLY SAFE WHEN ROBOT IS ALREADY ON THE FLOOR.
        From standing: causes uncontrolled drop and robot may not recover.
        Emergency stop use only from floor position.
        """
        print("[K1] → Damp")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_DAMP})
        if status == 0:
            self.current_mode = "damp"
            print("[K1] Damp confirmed")
            return {"ok": True, "mode": "damp"}
        print(f"[K1] Damp RPC failed (status={status})")
        return {"ok": False, "error": "Damp command failed", "detail": f"status={status}"}

    def set_prep_mode(self) -> dict:
        """
        Prep — stiffens motors. ONLY safe from Damp.
        Robot stays in current physical position — does not move.
        """
        actual = _get_actual_mode()

        if actual < 0:
            return {"ok": False, "error": "Cannot verify robot mode — Prep blocked"}

        if actual in WALK_MODES:
            return {"ok": False, "error": "Robot is in Walk mode",
                    "detail": "Use Damp first, then Prep"}

        if actual == MODE_PREP:
            print("[K1] Already in Prep")
            self.current_mode = "prep"
            return {"ok": True, "mode": "prep"}

        print("[K1] → Prep")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_PREP})
        if status == 0:
            self.current_mode = "prep"
            print("[K1] Prep confirmed")
            return {"ok": True, "mode": "prep"}

        return {"ok": False, "error": "Prep command failed", "detail": f"status={status}"}

    def set_walk_mode(self) -> dict:
        """
        Stand Up — triggers GetUp sequence then enables Walk via button event.
        ONLY safe from Prep (mode 1) with robot in proper position.

        NOTE: Physical Stand button on K1's back is MORE RELIABLE than RPC GetUp.
        If GetUp RPC fails, use physical button then call enable_walk_move().
        """
        actual = _get_actual_mode()

        if actual < 0:
            return {"ok": False, "error": "Cannot verify robot mode — Walk blocked"}

        if actual in WALK_MODES:
            # Already standing — ensure walk/move is enabled
            self._enable_walk_move()
            self.current_mode = "walk"
            return {"ok": True, "mode": "walk"}

        if actual == MODE_DAMP:
            return {"ok": False, "error": "Robot is in Damp mode",
                    "detail": "Click Prep first, then Stand Up"}

        if actual != MODE_PREP:
            return {"ok": False, "error": f"Unexpected mode (rpc={actual})",
                    "detail": "Robot must be in Prep before standing"}

        # Robot is in Prep — attempt GetUp
        print("[K1] → GetUp (robot will stand)")
        status, _ = rpc_call(API_GET_UP, {}, timeout=15)
        if status != 0:
            return {"ok": False, "error": "GetUp command failed",
                    "detail": f"status={status} — try physical Stand button on robot"}

        print("[K1] GetUp sent — waiting 10s for robot to stand")
        time.sleep(10)

        # Enable Walk/Move via button event — REQUIRED after GetUp
        self._enable_walk_move()

        # Verify mode
        actual_after = _get_actual_mode()
        if actual_after in WALK_MODES:
            self.current_mode = "walk"
            print("[K1] Stand Up confirmed — robot is standing")
            return {"ok": True, "mode": "walk"}

        return {"ok": False, "error": "GetUp sent but robot not in Walk mode",
                "detail": "Check robot physical position"}

    def _enable_walk_move(self):
        """
        Publish button event {event:2, button:2} to enable Walk/Move via RPC.
        REQUIRED after GetUp — without this, Move RPC returns status=400.
        Green pulsing light confirms Walk mode is enabled.
        """
        print("[K1] Enabling Walk/Move via button event...")
        _publish_button_event(event=2, button=2)
        time.sleep(1)

    def lie_down(self) -> dict:
        """
        Lie Down — NOT fully implemented via software.
        From standing: there is no confirmed safe software lie-down sequence.
        Damp from standing causes uncontrolled drop.
        Use physical robot controls to bring K1 to floor safely.
        """
        actual = _get_actual_mode()
        if actual in WALK_MODES:
            return {
                "ok": False,
                "error": "Cannot safely lie down from Walk via software",
                "detail": "Use physical robot controls to bring K1 to floor, then Damp"
            }
        # From Prep or Damp — just Damp
        return self.set_damp_mode()

    # ── Movement ──────────────────────────────────────────────

    def move(self, command: str, duration: float = None) -> dict:
        """
        Send a movement command. Verifies Walk mode first.
        Requires button event {event:2, button:2} to have been sent after GetUp.

        Commands: walk_forward | walk_backward | turn_left | turn_right | stop
        """
        if not self.connected:
            return {"ok": False, "error": "Not connected"}

        actual = _get_actual_mode(timeout=5)
        if actual < 0:
            return {"ok": False, "error": "Cannot verify mode — move blocked"}

        if actual not in WALK_MODES:
            self.current_mode = _rpc_mode_to_str(actual)
            return {"ok": False, "error": f"Robot not in Walk mode (mode={actual})",
                    "detail": "Click Stand Up first"}

        self.current_mode = "walk"
        dur = duration or MOVE_DURATION

        commands = {
            "walk_forward":  ( WALK_SPEED, 0.0,  0.0        ),
            "walk_backward": (-WALK_SPEED, 0.0,  0.0        ),
            "turn_left":     ( 0.0,        0.0,  TURN_SPEED ),
            "turn_right":    ( 0.0,        0.0, -TURN_SPEED ),
            "stop":          ( 0.0,        0.0,  0.0        ),
        }
        params = commands.get(command)
        if not params:
            return {"ok": False, "error": f"Unknown command: {command}"}

        vx, vy, vyaw = params
        print(f"[K1] Move: {command} vx={vx} vyaw={vyaw} dur={dur}s")

        status, _ = rpc_call(API_MOVE, {"vx": vx, "vy": vy, "vyaw": vyaw})
        if status == 0:
            if command != "stop":
                time.sleep(dur)
                rpc_call(API_MOVE, {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
            return {"ok": True}

        if status == 400:
            return {"ok": False, "error": "Move rejected (status=400)",
                    "detail": "Robot may not be in Walk mode — try Stand Up again"}

        return {"ok": False, "error": f"Move RPC failed (status={status})"}

    # ── Gestures ──────────────────────────────────────────────

    def gesture(self, name: str) -> dict:
        """
        Trigger a named gesture.

        Working:
          nod       — head movement via RPC 2004 ✅
          dance     — full body dances via RPC 2029 ✅ (see dance() method)

        Not working alongside booster-daemon:
          wave      — SDK WaveHand returns 100 (daemon conflict) ❌
          thumbs_up — SDK Handshake returns 100 (daemon conflict) ❌
        """
        if not self.connected:
            return {"ok": False, "error": "Not connected"}

        print(f"[K1] Gesture: {name}")

        if name == "nod":
            rpc_call(API_ROTATE_HEAD, {"pitch":  0.3, "yaw": 0.0})
            time.sleep(0.5)
            rpc_call(API_ROTATE_HEAD, {"pitch": -0.3, "yaw": 0.0})
            time.sleep(0.5)
            rpc_call(API_ROTATE_HEAD, {"pitch":  0.0, "yaw": 0.0})
            return {"ok": True}

        elif name == "wave":
            # SDK WaveHand returns 100 when booster-daemon is running
            # Booster daemon owns motion control and blocks SDK gesture commands
            # TODO: find RPC or topic-based wave command
            if _sdk_available and self.client:
                ret = self.client.WaveHand(B1HandAction.kHandOpen)
                if ret == 0:
                    return {"ok": True}
                print(f"[K1] SDK wave failed (ret={ret}) — daemon conflict")
            return {"ok": False, "error": "Wave not available",
                    "detail": "SDK gesture blocked by booster-daemon. Research ongoing."}

        elif name == "thumbs_up":
            if _sdk_available and self.client:
                ret = self.client.Handshake(B1HandAction.kHandOpen)
                if ret == 0:
                    return {"ok": True}
                print(f"[K1] SDK thumbs_up failed (ret={ret}) — daemon conflict")
            return {"ok": False, "error": "Thumbs up not available",
                    "detail": "SDK gesture blocked by booster-daemon. Research ongoing."}

        else:
            return {"ok": False, "error": f"Unknown gesture: {name}"}

    def dance(self, dance_name: str) -> dict:
        """
        Trigger a dance via RPC 2029.
        ⚠ Some dances involve kicks — ensure clear space around K1!

        Available: head_bop, hip_hop, kung_fu, kickbox, karate
        """
        if not self.connected:
            return {"ok": False, "error": "Not connected"}

        dance_id = DANCE_IDS.get(dance_name)
        if dance_id is None:
            return {"ok": False, "error": f"Unknown dance: {dance_name}",
                    "detail": f"Available: {list(DANCE_IDS.keys())}"}

        # Warn about kick dances
        if dance_name in ("kickbox", "karate"):
            print(f"[K1] ⚠ Dance '{dance_name}' involves kicks — ensure clear space!")

        print(f"[K1] Dance: {dance_name} (dance_id={dance_id})")
        status, _ = rpc_call(API_DANCE, {"dance_id": dance_id}, timeout=30)

        if status == 0:
            return {"ok": True}

        return {"ok": False, "error": f"Dance RPC failed (status={status})"}

    # ── Head control ──────────────────────────────────────────

    def rotate_head(self, pitch: float = 0.0, yaw: float = 0.0) -> dict:
        """
        Rotate K1's head.
        pitch: negative = look up, positive = look down (radians)
        yaw:   negative = look right, positive = look left (radians)
        """
        if not self.connected:
            return {"ok": False, "error": "Not connected"}

        # Clamp to safe ranges
        pitch = max(-0.5, min(1.0,   pitch))
        yaw   = max(-0.785, min(0.785, yaw))

        status, _ = rpc_call(API_ROTATE_HEAD, {"pitch": pitch, "yaw": yaw})
        if status == 0:
            return {"ok": True}
        return {"ok": False, "error": f"Head rotate failed (status={status})"}

    # ── Status ────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return current robot status with actual mode from RPC."""
        actual = _get_actual_mode(timeout=5)
        if actual >= 0:
            self.current_mode = _rpc_mode_to_str(actual)

        return {
            "connected":  self.connected,
            "mode":       self.current_mode,
            "rpc_mode":   actual if actual >= 0 else None,
        }


# Single shared instance imported by app.py
robot = K1Robot()
