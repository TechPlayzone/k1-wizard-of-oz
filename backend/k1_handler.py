"""
k1_handler.py
K1 robot movement and gesture handler using the official Booster SDK.

Verified against:
    /usr/local/lib/python3.10/dist-packages/booster_robotics_sdk_python.pyi

Correct API (confirmed from .pyi stub):
    ChannelFactory.Instance().Init(0)    — MUST call before B1LocoClient
    client = B1LocoClient()
    client.Init()                         — no args when running locally on K1
    client.ChangeMode(RobotMode.kDamping) — NOT SetMode, NOT kDamp
    client.ChangeMode(RobotMode.kPrepare)
    client.ChangeMode(RobotMode.kWalking) — NOT kWalk
    client.Move(vx, vy, vyaw)             — float, float, float
    client.WaveHand(B1HandAction.kHandOpen)
    client.RotateHead(pitch, yaw)
    client.Handshake(B1HandAction.kHandOpen)
    client.GetUp()
    client.LieDown()
    client.GetMode() -> (ret, GetModeResponse)

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import time

_sdk_available = False
try:
    from booster_robotics_sdk_python import (
        B1LocoClient,
        RobotMode,
        ChannelFactory,
        B1HandAction,
        B1HandIndex,
    )
    _sdk_available = True
    print("[k1_handler] Booster SDK loaded successfully")
except ImportError:
    print("[k1_handler] WARNING: Booster SDK not found. "
          "Commands will be logged only.")

# Movement parameters
WALK_SPEED    = 0.3   # m/s
TURN_SPEED    = 0.5   # rad/s
MOVE_DURATION = 2.0   # seconds


class K1Robot:
    def __init__(self):
        self.client       = None
        self.connected    = False
        self.current_mode = "damp"

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Initialize SDK connection.
        ChannelFactory MUST be initialized before B1LocoClient.
        Running ON the K1 — no IP or port needed.
        """
        if not _sdk_available:
            print("[K1] SDK not available — simulating commands")
            self.connected = True
            return True
        try:
            # Required first step — initializes DDS channel factory
            ChannelFactory.Instance().Init(0, "wlP5p1s0")
            self.client = B1LocoClient()
            self.client.Init()
            self.connected = True
            print("[K1] Connected via Booster SDK (local DDS)")
            return True
        except Exception as e:
            print(f"[K1] Connection failed: {e}")
            # Still mark connected so dashboard works for chat/camera
            self.connected = True
            return False

    def disconnect(self):
        self.connected = False
        self.client    = None
        print("[K1] Disconnected")

    # ── Mode transitions ──────────────────────────────────────

    def set_damp_mode(self):
        """Damp — motors relax. Safe resting state."""
        print("[K1] Mode → Damp")
        if _sdk_available and self.client:
            try:
                self.client.ChangeMode(RobotMode.kDamping)
            except Exception as e:
                print(f"[K1] ChangeMode error: {e}")
        self.current_mode = "damp"

    def set_prep_mode(self):
        """Prep — robot stands up and stiffens. Required before Walking."""
        print("[K1] Mode → Prep")
        if _sdk_available and self.client:
            try:
                self.client.ChangeMode(RobotMode.kPrepare)
            except Exception as e:
                print(f"[K1] ChangeMode error: {e}")
        self.current_mode = "prep"
        time.sleep(3)  # Allow standup sequence to complete

    def set_walk_mode(self):
        """Walk — robot ready for movement commands."""
        if self.current_mode == "damp":
            self.set_prep_mode()
        print("[K1] Mode → Walk")
        if _sdk_available and self.client:
            try:
                self.client.ChangeMode(RobotMode.kWalking)
            except Exception as e:
                print(f"[K1] ChangeMode error: {e}")
        self.current_mode = "walk"

    # ── Movement ──────────────────────────────────────────────

    def move(self, command: str, duration=None) -> bool:
        """
        Execute a movement command.

        Args:
            command:  "walk_forward" | "walk_backward" |
                      "turn_left"    | "turn_right"    | "stop"
            duration: Seconds to move (uses MOVE_DURATION if None)
        """
        if not self.connected:
            print("[K1] Not connected")
            return False
        if self.current_mode != "walk":
            print("[K1] Must be in Walk mode to move. "
                  "Click Walk button first.")
            return False

        dur = duration or MOVE_DURATION

        # Map command → (vx, vy, vyaw)
        # vx   = forward/backward (m/s)
        # vy   = lateral (m/s) — not used for basic navigation
        # vyaw = rotation (rad/s)
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

        if _sdk_available and self.client:
            try:
                self.client.Move(vx, vy, vyaw)
                if command != "stop" and dur > 0:
                    time.sleep(dur)
                    self.client.Move(0.0, 0.0, 0.0)  # Stop
            except Exception as e:
                print(f"[K1] Move error: {e}")

        return True

    # ── Gestures ──────────────────────────────────────────────

    def gesture(self, name: str) -> bool:
        """
        Execute a gesture.

        Gestures confirmed in .pyi stub:
            wave      → WaveHand(B1HandAction.kHandOpen)
            nod       → RotateHead(pitch, yaw) sequence
            thumbs_up → Handshake(B1HandAction.kHandOpen)
        """
        if not self.connected:
            print("[K1] Not connected")
            return False

        print(f"[K1] Gesture: {name}")

        if not (_sdk_available and self.client):
            return True

        try:
            if name == "wave":
                self.client.WaveHand(B1HandAction.kHandOpen)

            elif name == "nod":
                # Nod: pitch head down then back to center
                self.client.RotateHead(0.3, 0.0)   # pitch forward
                time.sleep(0.5)
                self.client.RotateHead(-0.3, 0.0)  # pitch back
                time.sleep(0.5)
                self.client.RotateHead(0.0, 0.0)   # center

            elif name == "thumbs_up":
                # Closest SDK gesture to thumbs up
                self.client.Handshake(B1HandAction.kHandOpen)

            else:
                print(f"[K1] Unknown gesture: {name}")

        except Exception as e:
            print(f"[K1] Gesture error: {e}")

        return True

    # ── Utility ───────────────────────────────────────────────

    def get_up(self) -> bool:
        """Command robot to stand up from fallen position."""
        if _sdk_available and self.client:
            try:
                self.client.GetUp()
                return True
            except Exception as e:
                print(f"[K1] GetUp error: {e}")
        return False

    def lie_down(self) -> bool:
        """Command robot to lie down safely."""
        if _sdk_available and self.client:
            try:
                self.client.LieDown()
                return True
            except Exception as e:
                print(f"[K1] LieDown error: {e}")
        return False

    # ── Status ────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return robot status for the dashboard status strip."""
        status = {
            "connected":  self.connected,
            "mode":       self.current_mode,
            "battery":    None,
            "latency_ms": None,
        }

        if _sdk_available and self.client:
            try:
                import time as _t
                start = _t.time()
                ret, mode_resp = self.client.GetMode()
                status["latency_ms"] = round((_t.time() - start) * 1000)

                if ret == 0:
                    mode_map = {
                        RobotMode.kDamping: "damp",
                        RobotMode.kPrepare: "prep",
                        RobotMode.kWalking: "walk",
                    }
                    actual_mode = mode_map.get(
                        mode_resp.mode, self.current_mode
                    )
                    self.current_mode  = actual_mode
                    status["mode"]     = actual_mode
            except Exception:
                pass

        return status


# Module-level robot instance shared by app.py
robot = K1Robot()
