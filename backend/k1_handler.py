"""
k1_handler.py
K1 robot control via ROS2 RPC service and Booster SDK.

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs

═══════════════════════════════════════════════════════════════
CONFIRMED RPC API IDs (tested 2026-06-17 on K1 firmware v1.6)
═══════════════════════════════════════════════════════════════
  api_id  body                           result
  ──────  ─────────────────────────────  ──────────────────────
  2000    {"mode": 0}                    → Damp  (status=0)
  2000    {"mode": 1}                    → Prep  (status=0)
  2001    {"vx": f, "vy": f, "vyaw": f} → Move  (status=0)
  2004    {"pitch": f, "yaw": f}         → Head  (status=0)
  2005    {}                             → Wave  (status=0)
  2008    {}                             → GetUp (status=0)
  2017    {}                             → GetMode → {"mode": N}

CONFIRMED RPC MODE VALUES
  0 = Damp
  1 = Prep
  2 = Walk (after GetUp)
  4 = Walk (alternate walk state — treat same as 2)

CONFIRMED SDK METHODS (B1LocoClient — dir() on 2026-06-17)
  WaveHand(B1HandAction.kHandOpen)  → wave gesture
  Handshake(B1HandAction.kHandOpen) → thumbs up
  LieDown()                         → controlled lie down from Prep
  RotateHead(pitch, yaw)            → head movement

KNOWN RPC PARSER BUG (fixed here)
  ROS2 service call output contains TWO body= fields:
    body='{}'            ← request body (always empty — WRONG)
    body='{"mode":0}'   ← response body (correct)
  re.search() returns first match = wrong empty body.
  Fix: re.findall() + take LAST match = correct response body.

SAFE MODE SEQUENCE
  Up:   Damp → Prep → Stand Up (GetUp RPC 2008) → Walk
  Down: Walk → Prep → Lie Down (SDK LieDown)    → Damp

SAFETY RULES
  - Always query actual robot mode via RPC before any transition
  - Never call GetUp unless robot is confirmed in Prep (mode 1)
  - Never call Prep if robot is in Walk — must stop movement first
  - Never send Move unless robot is confirmed in Walk (mode 2 or 4)
  - Never call LieDown from Walk — must Prep first
  - Damp is always allowed from any state (emergency stop)
  - If mode cannot be verified, block the action — never assume safe
"""

import json
import re
import subprocess
import time

# ── ROS2 environment setup ────────────────────────────────────
ROS2_SETUP = (
    "source /opt/ros/humble/setup.bash && "
    "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
)

# ── Movement constants ────────────────────────────────────────
WALK_SPEED    = 0.3   # m/s forward / backward
TURN_SPEED    = 0.5   # rad/s rotation
MOVE_DURATION = 2.0   # seconds per timed movement command

# ── RPC API IDs ───────────────────────────────────────────────
API_CHANGE_MODE = 2000
API_MOVE        = 2001
API_ROTATE_HEAD = 2004
API_WAVE        = 2005
API_GET_UP      = 2008
API_GET_MODE    = 2017

# ── Mode integer constants ────────────────────────────────────
MODE_DAMP     = 0
MODE_PREP     = 1
MODE_WALK     = 2
MODE_WALK_ALT = 4
WALK_MODES    = (MODE_WALK, MODE_WALK_ALT)

# ── Booster SDK ───────────────────────────────────────────────
_sdk_available = False
try:
    from booster_robotics_sdk_python import (
        B1LocoClient, ChannelFactory, B1HandAction,
    )
    _sdk_available = True
    print("[k1_handler] Booster SDK loaded")
except ImportError:
    print("[k1_handler] Booster SDK not found — SDK gestures unavailable")


# =============================================================================
# RPC HELPERS
# =============================================================================

def rpc_call(api_id: int, body: dict, timeout: int = 10) -> tuple:
    """
    Call the Booster RPC service via ROS2 subprocess.

    Returns (status, response_body_dict).
      status == 0   → success
      status == 400 → robot rejected command (wrong mode or invalid params)
      status == 501 → command not implemented on this firmware
      status == -1  → timeout, subprocess error, or parse failure

    PARSER FIX: ROS2 output contains two body= fields. We use re.findall()
    and take the LAST match to get the response body (not the request body).
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
        output = result.stdout

        # Parse status
        status_match = re.search(r"status=(\d+)", output)
        status = int(status_match.group(1)) if status_match else -1

        # Parse response body — LAST match is the response (first is request)
        body_matches = re.findall(r"body='([^']*)'", output)
        resp_body = {}
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


def _get_actual_mode(timeout: int = 8) -> int:
    """
    Query the robot's actual current mode via RPC api_id=2017.

    Returns mode integer (0=Damp, 1=Prep, 2/4=Walk) or -1 on failure.
    Always called before mode transitions — never trust cached state.
    """
    status, resp = rpc_call(API_GET_MODE, {}, timeout=timeout)
    if status == 0 and resp:
        mode = resp.get("mode", -1)
        print(f"[K1] Actual mode: {mode}")
        return mode
    print(f"[K1] GetMode failed (status={status}, resp={resp})")
    return -1


def _mode_to_str(rpc_mode: int) -> str:
    """Map RPC mode integer to internal string label."""
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
        self.client       = None     # B1LocoClient SDK instance
        self.connected    = False
        self.current_mode = "unknown"  # unknown until verified on connect

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def connect(self) -> bool:
        """
        Initialize SDK and sync actual mode from robot.

        Sets current_mode to 'unknown' if mode cannot be verified,
        keeping the dashboard locked until operator confirms position.
        Never defaults to 'damp' — robot could be standing.
        """
        try:
            if _sdk_available:
                ChannelFactory.Instance().Init(0, "wlP5p1s0")
                self.client = B1LocoClient()
                self.client.Init()
                print("[K1] Booster SDK connected")
        except Exception as e:
            print(f"[K1] SDK init warning (non-fatal): {e}")

        self.connected = True

        actual = _get_actual_mode()
        if actual >= 0:
            self.current_mode = _mode_to_str(actual)
            print(f"[K1] Mode synced: {self.current_mode} (rpc={actual})")
        else:
            self.current_mode = "unknown"
            print("[K1] WARNING: Cannot verify robot mode.")
            print("[K1] Dashboard locked until operator confirms position.")

        return True

    def disconnect(self):
        self.connected    = False
        self.client       = None
        print("[K1] Disconnected")

    # =========================================================================
    # MODE TRANSITIONS
    # =========================================================================

    def set_damp_mode(self) -> bool:
        """
        Damp — all motors relax immediately.

        Always allowed from any state. Use as emergency stop.
        Does NOT pre-check mode — intentional for safety-critical use.

        WARNING: If robot is standing, Damp causes uncontrolled collapse.
        Use set_prep_mode() → lie_down() for controlled shutdown from Walk.
        """
        print("[K1] → Damp")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_DAMP})
        if status == 0:
            self.current_mode = "damp"
            print("[K1] Damp confirmed")
            return True
        print(f"[K1] Damp failed (status={status})")
        return False

    def set_prep_mode(self) -> bool:
        """
        Prep — motors stiffen, robot holds crouched position.

        Safe from Damp only. Blocks if robot is in Walk.
        Also used as the controlled 'sit down' step going from Walk → Damp.
        """
        actual = _get_actual_mode()

        if actual < 0:
            print("[K1] Cannot verify mode — Prep blocked for safety")
            return False

        if actual in WALK_MODES:
            print(f"[K1] SAFETY BLOCK: In Walk (rpc={actual}). "
                  "Stop movement first, then click Prep.")
            return False

        if actual == MODE_PREP:
            print("[K1] Already in Prep")
            self.current_mode = "prep"
            return True

        # Confirmed Damp — safe to Prep
        print("[K1] → Prep")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_PREP})
        if status == 0:
            self.current_mode = "prep"
            print("[K1] Prep confirmed — waiting 3s for motors to stiffen")
            time.sleep(3)
            return True

        print(f"[K1] Prep failed (status={status})")
        return False

    def set_walk_mode(self) -> bool:
        """
        Stand Up — triggers GetUp (api_id=2008), robot rises from Prep.

        Only safe from Prep (mode=1).
        Blocks from Damp (must Prep first) and unknown mode.
        Verifies robot actually stood up after GetUp before returning True.
        """
        actual = _get_actual_mode()

        if actual < 0:
            print("[K1] Cannot verify mode — Stand Up blocked for safety")
            return False

        if actual in WALK_MODES:
            print("[K1] Already standing — syncing state")
            self.current_mode = "walk"
            return True

        if actual == MODE_DAMP:
            print("[K1] SAFETY BLOCK: In Damp. Click Prep first, then Stand Up.")
            return False

        if actual != MODE_PREP:
            print(f"[K1] SAFETY BLOCK: Unexpected mode (rpc={actual}). "
                  "Robot must be in Prep before standing.")
            return False

        # Confirmed Prep — safe to GetUp
        print("[K1] → GetUp (robot will stand)")
        status, _ = rpc_call(API_GET_UP, {}, timeout=15)
        if status != 0:
            print(f"[K1] GetUp RPC failed (status={status})")
            return False

        print("[K1] GetUp sent — waiting 10s for robot to stand")
        time.sleep(10)

        # Verify robot actually stood up
        actual_after = _get_actual_mode()
        if actual_after in WALK_MODES:
            self.current_mode = "walk"
            print("[K1] Stand Up confirmed — robot is standing")
            return True

        print(f"[K1] GetUp sent but robot mode is {actual_after} — check robot")
        return False

    def lie_down(self) -> bool:
        """
        Controlled lie down via SDK B1LocoClient.LieDown().

        Must be called from Prep mode only.
        Safe down sequence: Walk → set_prep_mode() → lie_down()

        Blocks if in Walk. Falls back to set_damp_mode() if SDK unavailable.
        """
        actual = _get_actual_mode()

        if actual < 0:
            print("[K1] Cannot verify mode — LieDown blocked for safety")
            return False

        if actual in WALK_MODES:
            print("[K1] SAFETY BLOCK: In Walk. Click Prep first, then Lie Down.")
            return False

        if actual == MODE_DAMP:
            print("[K1] Already in Damp / lying down")
            self.current_mode = "damp"
            return True

        if actual != MODE_PREP:
            print(f"[K1] SAFETY BLOCK: LieDown requires Prep (rpc={actual})")
            return False

        # Confirmed Prep — safe to lie down
        if _sdk_available and self.client:
            print("[K1] → LieDown (SDK)")
            ret = self.client.LieDown()
            if ret == 0:
                self.current_mode = "damp"
                print("[K1] LieDown complete — robot on floor")
                return True
            print(f"[K1] SDK LieDown failed (ret={ret}) — Damp fallback")
            return self.set_damp_mode()

        print("[K1] SDK unavailable — Damp fallback")
        return self.set_damp_mode()

    # =========================================================================
    # MOVEMENT
    # =========================================================================

    def move(self, command: str, duration: float = None) -> bool:
        """
        Send a directional movement command via RPC api_id=2001.

        Always verifies actual robot mode via RPC before moving.
        Never trusts cached current_mode for movement decisions.

        Commands: walk_forward | walk_backward | turn_left | turn_right | stop
        """
        if not self.connected:
            print("[K1] Not connected")
            return False

        actual = _get_actual_mode(timeout=5)
        if actual < 0:
            print("[K1] Cannot verify mode — move blocked for safety")
            return False

        if actual not in WALK_MODES:
            self.current_mode = _mode_to_str(actual)
            print(f"[K1] SAFETY BLOCK: Not in Walk (rpc={actual}). Stand Up first.")
            return False

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
        print(f"[K1] Move: {command} vx={vx} vyaw={vyaw} dur={dur}s")

        status, _ = rpc_call(API_MOVE, {"vx": vx, "vy": vy, "vyaw": vyaw})
        if status != 0:
            print(f"[K1] Move RPC failed (status={status})")
            return False

        if command != "stop":
            time.sleep(dur)
            rpc_call(API_MOVE, {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
            print("[K1] Move complete — stopped")

        return True

    # =========================================================================
    # GESTURES
    # =========================================================================

    def gesture(self, name: str) -> bool:
        """
        Execute a named gesture.

        wave      — SDK WaveHand(), RPC api_id=2005 fallback
        nod       — RPC head pitch sequence via api_id=2004
        thumbs_up — SDK Handshake()
        """
        if not self.connected:
            print("[K1] Not connected")
            return False

        print(f"[K1] Gesture: {name}")

        try:
            if name == "wave":
                if _sdk_available and self.client:
                    ret = self.client.WaveHand(B1HandAction.kHandOpen)
                    if ret != 0:
                        print(f"[K1] SDK wave failed (ret={ret}) — RPC fallback")
                        rpc_call(API_WAVE, {})
                else:
                    rpc_call(API_WAVE, {})

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
                    print("[K1] thumbs_up requires SDK — not available")

            else:
                print(f"[K1] Unknown gesture: {name}")
                return False

        except Exception as e:
            print(f"[K1] Gesture error: {e}")
            return False

        return True

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> dict:
        """Return current robot status with live mode query."""
        actual = _get_actual_mode(timeout=5)
        if actual >= 0:
            self.current_mode = _mode_to_str(actual)

        return {
            "connected":  self.connected,
            "mode":       self.current_mode,
            "rpc_mode":   actual if actual >= 0 else None,
        }


# Single shared instance — imported by app.py
robot = K1Robot()
