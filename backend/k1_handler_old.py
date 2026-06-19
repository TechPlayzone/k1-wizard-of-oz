"""
k1_handler.py
K1 robot control via ROS2 RPC service — no Booster app required.

Confirmed API IDs (tested on K1 firmware v1.6.1.1, June 2026):
    2000 = ChangeMode       body: {"mode": N}
    2001 = Move             body: {"vx": f, "vy": f, "vyaw": f}
    2004 = RotateHead       body: {"pitch": f, "yaw": f}
    2005 = WaveHand         body: {}
    2007 = LieDown          body: {}
    2008 = GetUp            body: {}  ← only needed from lying down
    2015 = Handshake        body: {}
    2016 = Dance            body: {"dance_id": N}  (upper body)
    2017 = GetMode          body: {} → {"mode": N}
    2018 = GetStatus        body: {} → {"current_mode": N, "current_body_control": N}
    2029 = WholeBodyDance   body: {"dance_id": N}

RobotMode values (confirmed):
    0 = Damp
    1 = Prep
    2 = Walk

Startup sequence — robot lying face-down after boot:
    Damp → Prep (mode 1, wait 3s) → GetUp (api 2008, wait 10s) → Walk ready

Startup sequence — robot already standing:
    Prep (mode 1, wait 3s) → ChangeMode Walk (mode 2) — NO GetUp needed

Safe shutdown sequence:
    Walk → Prep (mode 1) → LieDown (api 2007) → Damp

DanceId (api 2016 — upper body, safe from standing):
    0=NewYear, 1=Nezha, 2=TowardsFuture, 3=Dabbing, 4=Ultraman,
    5=Respect, 6=Cheering, 7=LuckyCat, 1000=Stop

WholeBodyDanceId (api 2029 — needs clear space):
    0=ArabicDance, 1=MichaelDance1, 2=MichaelDance2, 3=MichaelDance3,
    4=MoonWalk, 5=BoxingStyleKick, 6=RoundhouseKick

RPC error codes:
    100 = DDS Timeout
    400 = Bad request / wrong state
    409 = Conflict
    429 = Too frequent
    500 = Internal server error
    501 = Server refused (already in that state)
    502 = State transition failed

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import json
import time
import subprocess
import re
import threading

ROS2_SETUP = (
    "source /opt/ros/humble/setup.bash && "
    "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
)

# Movement parameters
WALK_SPEED    = 0.3   # m/s forward/backward
TURN_SPEED    = 0.5   # rad/s rotation
MOVE_DURATION = 2.0   # seconds per move command

# API IDs
API_CHANGE_MODE      = 2000
API_MOVE             = 2001
API_ROTATE_HEAD      = 2004
API_WAVE_HAND        = 2005
API_LIE_DOWN         = 2007
API_GET_UP           = 2008
API_HANDSHAKE        = 2015
API_DANCE            = 2016
API_GET_MODE         = 2017
API_GET_STATUS       = 2018
API_WHOLE_BODY_DANCE = 2029

# RobotMode values
MODE_DAMP = 0
MODE_PREP = 1
MODE_WALK = 2

_sdk_available = False
try:
    from booster_robotics_sdk_python import (
        B1LocoClient, ChannelFactory, B1HandAction,
    )
    _sdk_available = True
    print("[k1_handler] Booster SDK loaded successfully")
except ImportError:
    print("[k1_handler] WARNING: Booster SDK not found — RPC only mode.")


def rpc_call(api_id: int, body: dict, timeout: int = 10) -> tuple:
    """
    Call the Booster RPC service via ros2 service call.
    Returns (status, response_body_dict).
    Status -1 means the call itself failed (timeout, subprocess error).
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
        status_match = re.search(r"status=(\d+)", output)
        body_match   = re.search(r"body='([^']*)'", output)
        status = int(status_match.group(1)) if status_match else -1
        resp_body = {}
        if body_match and body_match.group(1):
            try:
                resp_body = json.loads(body_match.group(1))
            except Exception:
                pass
        return status, resp_body
    except subprocess.TimeoutExpired:
        print(f"[RPC] Timeout on api_id={api_id}")
        return -1, {}
    except Exception as e:
        print(f"[RPC] Error on api_id={api_id}: {e}")
        return -1, {}


def rpc_mode_str(rpc_mode: int) -> str:
    """Convert RPC mode integer to dashboard mode string."""
    return {0: "damp", 1: "prep", 2: "walk", 3: "custom", 4: "soccer"}.get(rpc_mode, "damp")


def get_robot_mode() -> tuple:
    """
    Query actual robot mode via RPC.
    Returns (rpc_mode_int, mode_str) or (-1, "unknown") on failure.
    """
    status, resp = rpc_call(API_GET_MODE, {}, timeout=8)
    if status == 0 and resp:
        rpc_mode = resp.get("mode", -1)
        return rpc_mode, rpc_mode_str(rpc_mode)
    return -1, "unknown"


class K1Robot:
    def __init__(self):
        self.client       = None
        self.connected    = False
        self.current_mode = "damp"   # cached mode — synced on connect
        self._battery     = None

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Initialize SDK (for future use) and sync robot mode in background.
        Flask starts immediately — mode sync happens after 5s delay.
        """
        try:
            if _sdk_available:
                ChannelFactory.Instance().Init(0, "wlP5p1s0")
                self.client = B1LocoClient()
                self.client.Init()
                print("[K1] Connected via Booster SDK (local DDS)")
        except Exception as e:
            print(f"[K1] SDK connect warning: {e}")
        self.connected = True

        # Sync mode from robot in background so Flask starts immediately
        def sync_mode():
            time.sleep(5)  # Wait for ROS2 services to be ready
            for attempt in range(3):
                try:
                    rpc_mode, mode_str = get_robot_mode()
                    if rpc_mode >= 0:
                        self.current_mode = mode_str
                        print(f"[K1] Mode synced on startup: {mode_str} (rpc={rpc_mode})")
                        return
                    print(f"[K1] Mode sync attempt {attempt + 1} failed — retrying")
                    time.sleep(3)
                except Exception as e:
                    print(f"[K1] Mode sync warning: {e}")
                    time.sleep(3)
            print("[K1] Mode sync failed after 3 attempts — defaulting to damp")

        threading.Thread(target=sync_mode, daemon=True).start()
        return True

    def disconnect(self):
        self.connected = False
        self.client    = None
        print("[K1] Disconnected")

    # ── Mode transitions ──────────────────────────────────────

    def set_damp_mode(self) -> bool:
        """
        Damp — motors relax, robot goes limp.
        Safe to call from any mode EXCEPT Walk (use Prep → LieDown first).
        """
        print("[K1] Mode → Damp")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_DAMP})
        if status == 0:
            self.current_mode = "damp"
            return True
        print(f"[K1] Damp failed, status={status}")
        return False

    def set_prep_mode(self) -> bool:
        """
        Prep — robot stiffens joints, crouches/stabilizes.
        From damp (lying down): robot will crouch.
        From walk (standing): robot will stabilize in place.
        Wait 3s after for balance stabilization.
        """
        print("[K1] Mode → Prep")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_PREP})
        if status == 0:
            self.current_mode = "prep"
            time.sleep(3)  # Allow balance stabilization
            return True
        print(f"[K1] Prep failed, status={status}")
        return False

    def set_walk_mode(self) -> bool:
        """
        Walk mode — robot ready for movement commands.

        Decision logic based on actual robot state:
        - Already in walk (mode 2): update cache only, no action needed
        - In prep (mode 1) and upright: ChangeMode to Walk (no GetUp)
        - In damp/prep and lying down: GetUp first, then Walk
          (operator confirmed lying down via safety modal)

        The safety modal tells us if robot is lying down (damp_floor)
        or standing (prep/walk). We use current_mode as the guide.
        """
        # Query actual robot mode
        rpc_mode, mode_str = get_robot_mode()

        # Already in walk — just sync cache
        if rpc_mode == MODE_WALK:
            print("[K1] Already in walk mode — skipping GetUp")
            self.current_mode = "walk"
            return True

        # In prep — determine if standing or lying based on cached mode context
        if rpc_mode == MODE_PREP:
            # If operator confirmed robot was lying face-down (damp_floor),
            # we need GetUp to stand up
            # If robot was already standing, just change to Walk
            if self.current_mode in ("damp", "prep"):
                # Try ChangeMode Walk first (works if already upright)
                status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_WALK})
                if status == 0:
                    time.sleep(2)
                    self.current_mode = "walk"
                    print("[K1] Mode → Walk (ChangeMode)")
                    return True

                # ChangeMode Walk failed — robot needs GetUp (was lying down)
                print("[K1] ChangeMode Walk failed — trying GetUp")
                return self._do_get_up()

        # In damp — can't go directly to walk
        if rpc_mode == MODE_DAMP:
            print("[K1] Must Prep first before Walk")
            return False

        # Unknown state — try GetUp as last resort
        print(f"[K1] Unknown mode {rpc_mode} — attempting GetUp")
        return self._do_get_up()

    def _do_get_up(self) -> bool:
        """Internal GetUp sequence — only from lying position."""
        print("[K1] GetUp → standing (10s)")
        status, _ = rpc_call(API_GET_UP, {}, timeout=15)
        if status == 0:
            time.sleep(10)  # Allow full stand-up sequence
            self.current_mode = "walk"
            print("[K1] Mode → Walk ready")
            return True
        print(f"[K1] GetUp failed, status={status}")
        return False

    def get_up(self) -> bool:
        """
        Stand-up button on dashboard.
        Skips if already standing (walk mode).
        """
        print("[K1] GetUp requested")
        rpc_mode, _ = get_robot_mode()
        if rpc_mode == MODE_WALK:
            print("[K1] Already standing")
            self.current_mode = "walk"
            return True
        return self._do_get_up()

    def lie_down(self) -> bool:
        """
        Safe lie-down sequence.
        Robot should be in Prep mode before calling this.
        Uses api_id=2007 (confirmed from SDK source).
        Falls back to Damp if LieDown fails.
        """
        print("[K1] LieDown")
        status, _ = rpc_call(API_LIE_DOWN, {}, timeout=15)
        if status == 0:
            time.sleep(5)  # Allow lie-down sequence to complete
            self.current_mode = "damp"
            print("[K1] Robot lying down — Damp mode")
            return True
        print(f"[K1] LieDown failed (status={status}) — falling back to Damp")
        return self.set_damp_mode()

    # ── Movement ──────────────────────────────────────────────

    def move(self, command: str, duration=None) -> bool:
        """
        Execute a directional movement command.
        Robot must be in Walk mode.
        Automatically sends stop after duration seconds.
        """
        if not self.connected:
            print("[K1] Not connected")
            return False
        if self.current_mode != "walk":
            print("[K1] Must be in Walk mode to move.")
            return False

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
            print(f"[K1] Unknown command: {command}")
            return False

        vx, vy, vyaw = params
        print(f"[K1] {command} — vx={vx}, vyaw={vyaw}, {dur}s")

        status, _ = rpc_call(API_MOVE, {"vx": vx, "vy": vy, "vyaw": vyaw})
        if status == 0 and command != "stop":
            time.sleep(dur)
            rpc_call(API_MOVE, {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
            print(f"[K1] {command} — stopped")

        return status == 0

    # ── Gestures ──────────────────────────────────────────────

    def gesture(self, name: str) -> bool:
        """
        Execute a gesture.
        wave      → api 2005 (WaveHand)
        nod       → api 2004 (RotateHead sequence)
        thumbs_up → api 2015 (Handshake)
        """
        if not self.connected:
            print("[K1] Not connected")
            return False

        print(f"[K1] Gesture: {name}")

        try:
            if name == "wave":
                status, _ = rpc_call(API_WAVE_HAND, {})
                if status != 0:
                    print(f"[K1] Wave failed (status={status})")
                return status == 0

            elif name == "nod":
                # Head pitch sequence: down → up → center
                rpc_call(API_ROTATE_HEAD, {"pitch": 0.3, "yaw": 0.0})
                time.sleep(0.6)
                rpc_call(API_ROTATE_HEAD, {"pitch": -0.3, "yaw": 0.0})
                time.sleep(0.6)
                rpc_call(API_ROTATE_HEAD, {"pitch": 0.0, "yaw": 0.0})
                return True

            elif name == "thumbs_up":
                status, _ = rpc_call(API_HANDSHAKE, {})
                if status != 0:
                    print(f"[K1] Thumbs up failed (status={status})")
                return status == 0

            else:
                print(f"[K1] Unknown gesture: {name}")
                return False

        except Exception as e:
            print(f"[K1] Gesture error: {e}")
            return False

    def dance(self, dance_id: int, whole_body: bool = False) -> bool:
        """
        Trigger a dance.

        whole_body=False → api 2016 (upper body only, safe from standing)
        whole_body=True  → api 2029 (whole body, requires clear space)

        Upper body DanceId (api 2016):
            0=NewYear, 1=Nezha, 2=TowardsFuture, 3=Dabbing,
            4=Ultraman, 5=Respect, 6=Cheering, 7=LuckyCat, 1000=Stop

        Whole body WholeBodyDanceId (api 2029):
            0=ArabicDance, 1=MichaelDance1, 2=MichaelDance2,
            3=MichaelDance3, 4=MoonWalk, 5=BoxingStyleKick, 6=RoundhouseKick
        """
        api   = API_WHOLE_BODY_DANCE if whole_body else API_DANCE
        label = "whole_body" if whole_body else "upper_body"
        print(f"[K1] Dance {label} id={dance_id}")
        status, _ = rpc_call(api, {"dance_id": dance_id})
        if status != 0:
            print(f"[K1] Dance failed (status={status})")
        return status == 0

    # ── Status ────────────────────────────────────────────────

    def get_status(self) -> dict:
        """
        Return cached robot status for dashboard polling.
        No RPC call on every poll — keeps dashboard fast (24ms latency).
        Battery updated separately via refresh_battery().
        """
        return {
            "connected":  self.connected,
            "mode":       self.current_mode,
            "battery":    self._battery,
            "latency_ms": None,
        }

    def refresh_battery(self) -> None:
        """
        Poll battery via api 2018 (GetStatus).
        Call from a background thread — not on every dashboard poll.
        Updates self._battery for next get_status() call.
        """
        try:
            status, resp = rpc_call(API_GET_STATUS, {}, timeout=8)
            if status == 0 and resp:
                # GetStatus also gives us current mode — sync it
                rpc_mode = resp.get("current_mode", -1)
                if rpc_mode >= 0:
                    self.current_mode = rpc_mode_str(rpc_mode)
                # Battery not in GetStatus response — available via DDS
                # (rt/device_gateway topic) if cyclonedds is installed
                print(f"[K1] Status refresh: mode={self.current_mode}")
        except Exception as e:
            print(f"[K1] Battery refresh error: {e}")


# Single shared instance used by app.py
robot = K1Robot()
