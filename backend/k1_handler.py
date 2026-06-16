"""
k1_handler.py
K1 robot control via ROS2 RPC service — no Booster app required.

Confirmed working RPC calls (tested 2026-06-12):
    Prep:    api_id=2000, body={"mode": 1}
    GetUp:   api_id=2008, body={}
    Move:    api_id=2001, body={"vx": f, "vy": f, "vyaw": f}
    Stop:    api_id=2001, body={"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
    Damp:    api_id=2000, body={"mode": 0}
    GetMode: api_id=2017, body={}  → returns {"mode": N}
    Wave:    api_id=2005, body={}  (WaveHand via RPC)
    Head:    api_id=2004, body={"pitch": f, "yaw": f}

RPC mode values (confirmed):
    0 = Damp
    1 = Prep
    2 = Walk ready (after GetUp)
    4 = Walk (alternate walk state)

SAFETY RULES — enforced in every method:
    - Always verify ACTUAL robot mode via RPC before any transition
    - Never call GetUp unless robot is confirmed in Prep (mode 1)
    - Never call Prep if robot is in Walk (modes 2 or 4) — Damp first
    - Never send Move commands unless robot is confirmed in Walk
    - Damp is ALWAYS allowed from any state — it is the emergency stop

Startup sequence (confirmed working):
    1. Boot robot (wait for tone + green light) — starts in Damp
    2. Operator confirms position in dashboard safety modal
    3. Click Prep — robot stiffens (from Damp only)
    4. Click Walk — triggers GetUp (from Prep only)
    5. Use movement and gesture controls

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
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
WALK_SPEED    = 0.3   # m/s forward/backward
TURN_SPEED    = 0.5   # rad/s turn
MOVE_DURATION = 2.0   # seconds per movement command

# ── RPC API IDs ───────────────────────────────────────────────
API_CHANGE_MODE = 2000
API_MOVE        = 2001
API_ROTATE_HEAD = 2004
API_GET_UP      = 2008
API_GET_MODE    = 2017

# ── Mode constants ────────────────────────────────────────────
MODE_DAMP = 0
MODE_PREP = 1
MODE_WALK = 2   # confirmed walk states
MODE_WALK_ALT = 4

WALK_MODES = (MODE_WALK, MODE_WALK_ALT)

# ── Booster SDK (optional — used for gestures) ────────────────
_sdk_available = False
try:
    from booster_robotics_sdk_python import (
        B1LocoClient, ChannelFactory, B1HandAction,
    )
    _sdk_available = True
    print("[k1_handler] Booster SDK loaded successfully")
except ImportError:
    print("[k1_handler] WARNING: Booster SDK not found — gesture fallback to RPC")


# =============================================================================
# RPC CALL
# =============================================================================

def rpc_call(api_id: int, body: dict, timeout: int = 10) -> tuple:
    """
    Call the Booster RPC service via ROS2.
    Returns (status, response_body_dict).
    status == 0 means success.
    status == -1 means timeout or error.
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
        body_match   = re.search(r"body='([^']*)'", output)
        status       = int(status_match.group(1)) if status_match else -1
        resp_body    = {}
        if body_match and body_match.group(1):
            try:
                resp_body = json.loads(body_match.group(1))
            except Exception:
                pass
        return status, resp_body
    except subprocess.TimeoutExpired:
        print(f"[RPC] Timeout — api_id={api_id}")
        return -1, {}
    except Exception as e:
        print(f"[RPC] Error — api_id={api_id}: {e}")
        return -1, {}


def _get_actual_mode(timeout: int = 8) -> int:
    """
    Query the robot for its ACTUAL current mode via RPC.
    Returns the raw RPC mode integer, or -1 if the query fails.
    This is always called before mode transitions — never trust cached state.
    """
    status, resp = rpc_call(API_GET_MODE, {}, timeout=timeout)
    if status == 0 and resp:
        mode = resp.get("mode", -1)
        print(f"[K1] Actual mode from robot: {mode}")
        return mode
    print(f"[K1] GetMode RPC failed (status={status}) — cannot verify robot state")
    return -1


def _rpc_mode_to_str(rpc_mode: int) -> str:
    """Map RPC mode integer to internal mode string."""
    return {
        MODE_DAMP:    "damp",
        MODE_PREP:    "prep",
        MODE_WALK:    "walk",
        MODE_WALK_ALT: "walk",
    }.get(rpc_mode, "unknown")


# =============================================================================
# K1 ROBOT
# =============================================================================

class K1Robot:
    def __init__(self):
        self.client       = None
        self.connected    = False
        self.current_mode = "damp"   # Assume damp until verified

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Connect to K1. Initializes SDK for gestures and syncs
        actual mode from the robot via RPC.
        """
        # Try SDK init (needed for wave/thumbs_up gestures)
        try:
            if _sdk_available:
                ChannelFactory.Instance().Init(0, "wlP5p1s0")
                self.client = B1LocoClient()
                self.client.Init()
                print("[K1] Connected via Booster SDK (local DDS)")
        except Exception as e:
            print(f"[K1] SDK connect warning (non-fatal): {e}")

        self.connected = True

        # Sync actual mode from robot
        actual = _get_actual_mode()
        if actual >= 0:
            self.current_mode = _rpc_mode_to_str(actual)
            print(f"[K1] Mode synced on connect: {self.current_mode} (rpc={actual})")
        else:
            self.current_mode = "damp"
            print("[K1] Mode sync failed — defaulting to 'damp' for safety")

        return True

    def disconnect(self):
        self.connected    = False
        self.client       = None
        print("[K1] Disconnected")

    # ── Mode transitions ──────────────────────────────────────

    def set_damp_mode(self) -> bool:
        """
        Damp — motors relax, robot sinks to floor.
        ALWAYS allowed from any state. Use as emergency stop.
        Does NOT require mode verification first — safety-critical.
        """
        print("[K1] → Damp (motors off)")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_DAMP})
        if status == 0:
            self.current_mode = "damp"
            print("[K1] Damp confirmed")
            return True
        print(f"[K1] Damp RPC failed (status={status})")
        return False

    def set_prep_mode(self) -> bool:
        """
        Prep — robot stiffens motors, ready to stand.
        ONLY safe from Damp. If robot is in Walk, returns False
        with a clear error — caller must Damp first.
        """
        # Verify actual robot mode before attempting Prep
        actual = _get_actual_mode()

        if actual < 0:
            print("[K1] Cannot verify robot mode — Prep blocked for safety")
            return False

        if actual in WALK_MODES:
            print(f"[K1] SAFETY BLOCK: Robot is in Walk (rpc={actual}). "
                  "Cannot go directly to Prep. Click Damp first.")
            return False

        if actual == MODE_PREP:
            print("[K1] Already in Prep — no action needed")
            self.current_mode = "prep"
            return True

        # Robot is in Damp — safe to Prep
        print("[K1] → Prep")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_PREP})
        if status == 0:
            self.current_mode = "prep"
            print("[K1] Prep confirmed — waiting 3s for motors to stiffen")
            time.sleep(3)
            return True

        print(f"[K1] Prep RPC failed (status={status})")
        return False

    def set_walk_mode(self) -> bool:
        """
        Walk mode — triggers GetUp sequence. Robot stands up.
        ONLY safe from Prep (mode 1). Blocks if robot is in Damp
        or already in Walk.
        """
        # Always verify actual mode before GetUp — most safety-critical check
        actual = _get_actual_mode()

        if actual < 0:
            print("[K1] Cannot verify robot mode — Walk blocked for safety")
            return False

        if actual in WALK_MODES:
            # Already standing — just sync internal state
            print("[K1] Robot already in Walk mode — syncing state")
            self.current_mode = "walk"
            return True

        if actual == MODE_DAMP:
            print("[K1] SAFETY BLOCK: Robot is in Damp. "
                  "Cannot trigger GetUp from Damp — click Prep first.")
            return False

        if actual != MODE_PREP:
            print(f"[K1] SAFETY BLOCK: Unexpected mode (rpc={actual}). "
                  "Robot must be in Prep before Walk.")
            return False

        # Robot is confirmed in Prep — safe to GetUp
        print("[K1] → GetUp (robot will stand)")
        status, _ = rpc_call(API_GET_UP, {}, timeout=15)
        if status == 0:
            print("[K1] GetUp sent — waiting 10s for robot to stand")
            time.sleep(10)
            # Verify robot actually stood up
            actual_after = _get_actual_mode()
            if actual_after in WALK_MODES:
                self.current_mode = "walk"
                print("[K1] Walk confirmed — robot is standing")
                return True
            else:
                print(f"[K1] GetUp sent but robot mode is {actual_after} — check robot")
                return False

        print(f"[K1] GetUp RPC failed (status={status})")
        return False

    def lie_down(self) -> bool:
        """
        Controlled lie down via SDK LieDown().
        Must be called from Prep mode only — robot crouches then lies
        down safely in a controlled motion.

        SAFETY: Never call from Walk mode.
        Safe down sequence: Walk → Prep → LieDown → robot on floor
        """
        actual = _get_actual_mode()

        if actual < 0:
            print("[K1] Cannot verify mode — LieDown blocked for safety")
            return False

        if actual in WALK_MODES:
            print("[K1] SAFETY BLOCK: Cannot LieDown from Walk. "
                  "Click Prep first to crouch, then Lie Down.")
            return False

        if actual == MODE_DAMP:
            print("[K1] Already in Damp/lying down — no action needed")
            self.current_mode = "damp"
            return True

        if actual != MODE_PREP:
            print(f"[K1] SAFETY BLOCK: LieDown requires Prep mode (rpc={actual})")
            return False

        # Robot is confirmed in Prep — safe to lie down
        if _sdk_available and self.client:
            print("[K1] → LieDown (controlled via SDK)")
            ret = self.client.LieDown()
            if ret == 0:
                self.current_mode = "damp"
                print("[K1] LieDown complete — robot is lying safely on floor")
                return True
            else:
                print(f"[K1] SDK LieDown failed (ret={ret}) — falling back to Damp")
                return self.set_damp_mode()
        else:
            print("[K1] SDK not available — using Damp fallback")
            return self.set_damp_mode()

    # ── Movement ──────────────────────────────────────────────

    def move(self, command: str, duration: float = None) -> bool:
        """
        Send a movement command to the robot.
        Verifies actual robot mode before moving — never trusts cache alone.

        Commands: walk_forward | walk_backward | turn_left | turn_right | stop
        """
        if not self.connected:
            print("[K1] Not connected")
            return False

        # Verify actual mode — never trust cached mode for movement
        actual = _get_actual_mode(timeout=5)
        if actual < 0:
            print("[K1] Cannot verify mode — move blocked for safety")
            return False

        if actual not in WALK_MODES:
            self.current_mode = _rpc_mode_to_str(actual)
            print(f"[K1] SAFETY BLOCK: Robot is not in Walk mode (rpc={actual}). "
                  "Click Walk first.")
            return False

        # Sync cached mode
        self.current_mode = "walk"

        dur = duration or MOVE_DURATION

        commands = {
            "walk_forward":  ( WALK_SPEED, 0.0,  0.0       ),
            "walk_backward": (-WALK_SPEED, 0.0,  0.0       ),
            "turn_left":     ( 0.0,        0.0,  TURN_SPEED),
            "turn_right":    ( 0.0,        0.0, -TURN_SPEED),
            "stop":          ( 0.0,        0.0,  0.0       ),
        }
        params = commands.get(command)
        if not params:
            print(f"[K1] Unknown command: {command}")
            return False

        vx, vy, vyaw = params
        print(f"[K1] Move: {command} — vx={vx}, vyaw={vyaw}, {dur}s")

        status, _ = rpc_call(API_MOVE, {"vx": vx, "vy": vy, "vyaw": vyaw})
        if status == 0:
            if command != "stop":
                time.sleep(dur)
                # Always send stop after timed move
                rpc_call(API_MOVE, {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
                print(f"[K1] Move complete — stopped")
            return True

        print(f"[K1] Move RPC failed (status={status})")
        return False

    # ── Gestures ──────────────────────────────────────────────

    def gesture(self, name: str) -> bool:
        """
        Trigger a named gesture. Robot does not need to be in Walk mode
        for head movements. Wave and thumbs_up work best in Walk/Prep.
        """
        if not self.connected:
            print("[K1] Not connected")
            return False

        print(f"[K1] Gesture: {name}")

        try:
            if name == "wave":
                # SDK first, RPC fallback
                if _sdk_available and self.client:
                    ret = self.client.WaveHand(B1HandAction.kHandOpen)
                    if ret != 0:
                        print(f"[K1] SDK wave failed (ret={ret}) — trying RPC fallback")
                        rpc_call(2005, {})
                else:
                    rpc_call(2005, {})

            elif name == "nod":
                rpc_call(API_ROTATE_HEAD, {"pitch":  0.3, "yaw": 0.0})
                time.sleep(0.5)
                rpc_call(API_ROTATE_HEAD, {"pitch": -0.3, "yaw": 0.0})
                time.sleep(0.5)
                rpc_call(API_ROTATE_HEAD, {"pitch":  0.0, "yaw": 0.0})

            elif name == "thumbs_up":
                if _sdk_available and self.client:
                    ret = self.client.Handshake(B1HandAction.kHandOpen)
                    if ret != 0:
                        print(f"[K1] SDK thumbs_up failed (ret={ret})")
                else:
                    print("[K1] SDK not available — thumbs_up requires SDK")

            else:
                print(f"[K1] Unknown gesture: {name}")
                return False

        except Exception as e:
            print(f"[K1] Gesture error: {e}")
            return False

        return True

    # ── Status ────────────────────────────────────────────────

    def get_status(self) -> dict:
        """
        Return current robot status.
        Queries actual mode from robot — not just cached value.
        """
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
