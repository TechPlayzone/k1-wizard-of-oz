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

Startup sequence (no Booster app needed):
    1. Boot robot (wait for tone + green light)
    2. Press Prep button
    3. Press Walk button (triggers GetUp)
    4. Use movement buttons

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import json
import time
import subprocess
import os
import re

ROS2_SETUP = (
    "source /opt/ros/humble/setup.bash && "
    "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
)

WALK_SPEED    = 0.3
TURN_SPEED    = 0.5
MOVE_DURATION = 2.0

API_CHANGE_MODE = 2000
API_MOVE        = 2001
API_ROTATE_HEAD = 2004
API_GET_UP      = 2008
API_GET_MODE    = 2017

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
    print("[k1_handler] WARNING: Booster SDK not found.")


def rpc_call(api_id: int, body: dict, timeout: int = 10) -> tuple:
    """Call the Booster RPC service. Returns (status, response_body_dict)."""
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
        print(f"[RPC] Error: {e}")
        return -1, {}


def rpc_mode_map(rpc_mode: int) -> str:
    return {0: "damp", 1: "prep", 2: "walk", 4: "walk"}.get(rpc_mode, "damp")


class K1Robot:
    def __init__(self):
        self.client       = None
        self.connected    = False
        self.current_mode = "damp"

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """Initialize SDK for gestures and sync mode from robot."""
        try:
            if _sdk_available:
                ChannelFactory.Instance().Init(0, "wlP5p1s0")
                self.client = B1LocoClient()
                self.client.Init()
                print("[K1] Connected via Booster SDK (local DDS)")
        except Exception as e:
            print(f"[K1] SDK connect warning: {e}")
        self.connected = True

        # Sync actual mode from robot on startup
        try:
            status, resp = rpc_call(API_GET_MODE, {}, timeout=8)
            if status == 0 and resp:
                rpc_mode = resp.get("mode", -1)
                self.current_mode = rpc_mode_map(rpc_mode)
                print(f"[K1] Mode synced on startup: {self.current_mode} (rpc={rpc_mode})")
            else:
                print("[K1] Mode sync failed — defaulting to damp")
        except Exception as e:
            print(f"[K1] Mode sync warning: {e}")

        return True

    def disconnect(self):
        self.connected = False
        self.client    = None
        print("[K1] Disconnected")

    # ── Mode transitions ──────────────────────────────────────

    def set_damp_mode(self) -> bool:
        """Damp — motors relax. Safe from any mode."""
        print("[K1] Mode → Damp")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_DAMP})
        if status == 0:
            self.current_mode = "damp"
            return True
        print(f"[K1] Damp failed, status={status}")
        return False

    def set_prep_mode(self) -> bool:
        """Prep — robot stiffens. Only works from damp."""
        print("[K1] Mode → Prep")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_PREP})
        if status == 0:
            self.current_mode = "prep"
            time.sleep(3)
            return True
        print(f"[K1] Prep failed, status={status}")
        return False

    def set_walk_mode(self) -> bool:
        """
        Walk mode. Checks current robot state first:
        - If already in walk (mode 2): just update internal state
        - If in prep (mode 1): call GetUp
        - Otherwise: fail with message
        """
        # Check actual robot mode
        status, resp = rpc_call(API_GET_MODE, {}, timeout=8)
        if status == 0 and resp:
            rpc_mode = resp.get("mode", -1)
            if rpc_mode in (2, 4):
                print("[K1] Already in walk mode — skipping GetUp")
                self.current_mode = "walk"
                return True
            elif rpc_mode != 1:
                print(f"[K1] Walk requires Prep first (current rpc_mode={rpc_mode})")
                return False

        print("[K1] GetUp → standing")
        status, _ = rpc_call(API_GET_UP, {}, timeout=15)
        if status == 0:
            time.sleep(10)
            self.current_mode = "walk"
            print("[K1] Mode → Walk ready")
            return True
        print(f"[K1] GetUp failed, status={status}")
        return False

    def get_up(self) -> bool:
        """Stand up from current position."""
        print("[K1] GetUp")
        status, resp = rpc_call(API_GET_MODE, {}, timeout=5)
        if status == 0 and resp.get("mode") in (2, 4):
            print("[K1] Already standing — skipping GetUp")
            self.current_mode = "walk"
            return True
        status, _ = rpc_call(API_GET_UP, {}, timeout=15)
        if status == 0:
            time.sleep(8)
            self.current_mode = "walk"
            return True
        print(f"[K1] GetUp failed, status={status}")
        return False

    def lie_down(self) -> bool:
        """Damp and lie down safely."""
        return self.set_damp_mode()

    # ── Movement ──────────────────────────────────────────────

    def move(self, command: str, duration=None) -> bool:
        if not self.connected:
            print("[K1] Not connected")
            return False
        if self.current_mode != "walk":
            print("[K1] Must be in Walk mode to move. Click Walk button first.")
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

        return True

    # ── Gestures ──────────────────────────────────────────────

    def gesture(self, name: str) -> bool:
        if not self.connected:
            print("[K1] Not connected")
            return False

        print(f"[K1] Gesture: {name}")

        try:
            if name == "wave":
                # Try SDK first, fall back to RPC
                if _sdk_available and self.client:
                    ret = self.client.WaveHand(B1HandAction.kHandOpen)
                    if ret != 0:
                        print(f"[K1] SDK wave failed ({ret}) — trying RPC")
                        rpc_call(2005, {})
                else:
                    rpc_call(2005, {})

            elif name == "nod":
                rpc_call(API_ROTATE_HEAD, {"pitch": 0.3, "yaw": 0.0})
                time.sleep(0.5)
                rpc_call(API_ROTATE_HEAD, {"pitch": -0.3, "yaw": 0.0})
                time.sleep(0.5)
                rpc_call(API_ROTATE_HEAD, {"pitch": 0.0, "yaw": 0.0})

            elif name == "thumbs_up":
                if _sdk_available and self.client:
                    ret = self.client.Handshake(B1HandAction.kHandOpen)
                    if ret != 0:
                        print(f"[K1] SDK thumbs_up failed ({ret})")
                else:
                    print("[K1] SDK not available for thumbs_up")

            else:
                print(f"[K1] Unknown gesture: {name}")

        except Exception as e:
            print(f"[K1] Gesture error: {e}")

        return True

    # ── Status ────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return cached robot status — no RPC poll on every request."""
        return {
            "connected":  self.connected,
            "mode":       self.current_mode,
            "battery":    None,
            "latency_ms": None,
        }


robot = K1Robot()
