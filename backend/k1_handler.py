"""
k1_handler.py
Wrapper around the Booster Robotics K1 Python SDK.

Handles:
    - Robot connection and mode management (Damp → Prep → Walk)
    - Movement commands (walk forward/backward, turn left/right, stop)
    - Gesture commands (wave, nod, thumbs_up)
    - Audio playback (copy WAV to robot and play via speaker)
    - Robot status polling (mode, battery)

Usage:
    from k1_handler import K1Robot
    robot = K1Robot()
    robot.connect()
    robot.set_walk_mode()
    robot.move("walk_forward", duration=2.0)
    robot.gesture("wave")
    robot.speak("/tmp/k1_tts_abc123.wav")
    robot.disconnect()
"""

import time
import subprocess
from config import cfg

# Booster SDK import — will raise ImportError if SDK not installed
try:
    from booster_robotics_sdk_python import (
        B1LocoClient,
        RobotMode,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    print("[k1_handler] WARNING: Booster SDK not installed. "
          "Movement commands will be simulated (logged only).")


# ── Movement durations (seconds) ─────────────────────────────────────────────
MOVE_DURATION = 2.0   # Default walk step duration
TURN_DURATION = 1.5   # Default turn duration

# ── Walk velocities ───────────────────────────────────────────────────────────
WALK_SPEED    = 0.3   # m/s forward/backward
TURN_SPEED    = 0.5   # rad/s


class K1Robot:
    def __init__(self):
        self.client       = None
        self.connected    = False
        self.current_mode = "damp"  # damp | prep | walk

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Initialize connection to the K1 via Booster SDK."""
        if not SDK_AVAILABLE:
            print(f"[K1] Simulated connect to {cfg.K1_IP}:{cfg.K1_PORT}")
            self.connected = True
            return True
        try:
            self.client = B1LocoClient(cfg.K1_IP, cfg.K1_PORT)
            self.client.Init()
            self.connected = True
            print(f"[K1] Connected to {cfg.K1_IP}:{cfg.K1_PORT}")
            return True
        except Exception as e:
            print(f"[K1] Connection failed: {e}")
            self.connected = False
            return False

    def disconnect(self) -> None:
        self.connected = False
        self.client    = None
        print("[K1] Disconnected")

    # ── Mode transitions ──────────────────────────────────────────────────────

    def set_damp_mode(self) -> None:
        """Damp mode — motors relaxed. Safe resting state."""
        self._send_mode(RobotMode.kDamp if SDK_AVAILABLE else "kDamp")
        self.current_mode = "damp"
        print("[K1] Mode → Damp")

    def set_prep_mode(self) -> None:
        """Prep mode — robot stands and stiffens. Required before Walk."""
        self._send_mode(RobotMode.kPrepare if SDK_AVAILABLE else "kPrepare")
        self.current_mode = "prep"
        print("[K1] Mode → Prep")
        time.sleep(3)  # Allow robot to complete standup

    def set_walk_mode(self) -> None:
        """Walk mode — robot ready for movement commands."""
        if self.current_mode == "damp":
            self.set_prep_mode()
        self._send_mode(RobotMode.kWalk if SDK_AVAILABLE else "kWalk")
        self.current_mode = "walk"
        print("[K1] Mode → Walk")

    def _send_mode(self, mode) -> None:
        if SDK_AVAILABLE and self.client:
            self.client.SetMode(mode)
        # If SDK not available, log only (simulation mode)

    # ── Movement commands ─────────────────────────────────────────────────────

    def move(self, command: str, duration: object = None) -> bool:
        """
        Execute a movement command.

        Args:
            command:  "walk_forward" | "walk_backward" |
                      "turn_left"    | "turn_right"    | "stop"
            duration: Seconds to run the movement (uses default if None)

        Returns:
            True if command was sent successfully
        """
        if not self.connected:
            print("[K1] Not connected — cannot move")
            return False

        if self.current_mode != "walk":
            print("[K1] Must be in Walk mode to move. Call set_walk_mode() first.")
            return False

        handlers = {
            "walk_forward":  self._walk_forward,
            "walk_backward": self._walk_backward,
            "turn_left":     self._turn_left,
            "turn_right":    self._turn_right,
            "stop":          self._stop,
        }

        fn = handlers.get(command)
        if not fn:
            print(f"[K1] Unknown movement command: {command}")
            return False

        fn(duration or MOVE_DURATION)
        return True

    def _walk_forward(self, duration: float) -> None:
        print(f"[K1] Walk forward ({duration}s)")
        if SDK_AVAILABLE and self.client:
            self.client.Move(WALK_SPEED, 0, 0)
            time.sleep(duration)
            self.client.Move(0, 0, 0)

    def _walk_backward(self, duration: float) -> None:
        print(f"[K1] Walk backward ({duration}s)")
        if SDK_AVAILABLE and self.client:
            self.client.Move(-WALK_SPEED, 0, 0)
            time.sleep(duration)
            self.client.Move(0, 0, 0)

    def _turn_left(self, duration: float) -> None:
        print(f"[K1] Turn left ({duration}s)")
        if SDK_AVAILABLE and self.client:
            self.client.Move(0, 0, TURN_SPEED)
            time.sleep(duration)
            self.client.Move(0, 0, 0)

    def _turn_right(self, duration: float) -> None:
        print(f"[K1] Turn right ({duration}s)")
        if SDK_AVAILABLE and self.client:
            self.client.Move(0, 0, -TURN_SPEED)
            time.sleep(duration)
            self.client.Move(0, 0, 0)

    def _stop(self, _duration: float = 0) -> None:
        print("[K1] Stop")
        if SDK_AVAILABLE and self.client:
            self.client.Move(0, 0, 0)

    # ── Gestures ──────────────────────────────────────────────────────────────

    def gesture(self, name: str) -> bool:
        """
        Execute a pre-built gesture.

        Args:
            name: "wave" | "nod" | "thumbs_up"

        Returns:
            True if gesture was triggered
        """
        if not self.connected:
            print("[K1] Not connected — cannot gesture")
            return False

        gestures = {
            "wave":       self._gesture_wave,
            "nod":        self._gesture_nod,
            "thumbs_up":  self._gesture_thumbs_up,
        }

        fn = gestures.get(name)
        if not fn:
            print(f"[K1] Unknown gesture: {name}")
            return False

        fn()
        return True

    def _gesture_wave(self) -> None:
        print("[K1] Gesture: wave")
        # SDK custom motion call — implementation depends on your K1 firmware
        # and any custom motion files loaded onto the robot.
        # Replace with your specific SDK gesture call when available.
        if SDK_AVAILABLE and self.client:
            try:
                self.client.PlayCustomMotion("wave")
            except Exception:
                # Fallback: raise right arm via joint control if PlayCustomMotion
                # is not available in your SDK version
                print("[K1] PlayCustomMotion not available — gesture logged only")

    def _gesture_nod(self) -> None:
        print("[K1] Gesture: nod")
        if SDK_AVAILABLE and self.client:
            try:
                self.client.PlayCustomMotion("nod")
            except Exception:
                print("[K1] PlayCustomMotion not available — gesture logged only")

    def _gesture_thumbs_up(self) -> None:
        print("[K1] Gesture: thumbs_up")
        if SDK_AVAILABLE and self.client:
            try:
                self.client.PlayCustomMotion("thumbs_up")
            except Exception:
                print("[K1] PlayCustomMotion not available — gesture logged only")

    # ── Audio ─────────────────────────────────────────────────────────────────

    def speak(self, wav_path: str) -> bool:
        """
        Copy a WAV file to the K1 and play it through the robot's speaker.

        Args:
            wav_path: Local path to the synthesized WAV file

        Returns:
            True if audio was played successfully
        """
        remote_path = "/tmp/k1_response.wav"

        try:
            # Copy WAV to robot via SCP
            scp_result = subprocess.run(
                [
                    "scp", "-o", "StrictHostKeyChecking=no",
                    wav_path,
                    f"booster@{cfg.K1_IP}:{remote_path}",
                ],
                capture_output=True,
                timeout=10,
            )
            if scp_result.returncode != 0:
                print(f"[K1] SCP failed: {scp_result.stderr.decode()}")
                return False

            # Play audio on K1 speaker via SSH
            ssh_result = subprocess.run(
                [
                    "ssh", "-o", "StrictHostKeyChecking=no",
                    f"booster@{cfg.K1_IP}",
                    f"espeak-ng '' --stdout | paplay "
                    f"--device=alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device"
                    f"-00.analog-stereo < {remote_path}",
                ],
                capture_output=True,
                timeout=30,
            )

            if ssh_result.returncode != 0:
                # Fallback: try aplay
                subprocess.run(
                    ["ssh", "-o", "StrictHostKeyChecking=no",
                     f"booster@{cfg.K1_IP}",
                     f"aplay {remote_path}"],
                    timeout=30,
                )

            print("[K1] Audio played")
            return True

        except subprocess.TimeoutExpired:
            print("[K1] Audio playback timed out")
            return False
        except Exception as e:
            print(f"[K1] speak() error: {e}")
            return False

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """
        Return current robot status for the dashboard status strip.

        Returns a dict with: connected, mode, battery, latency_ms
        """
        import time as _time
        start = _time.time()

        status = {
            "connected":  self.connected,
            "mode":       self.current_mode,
            "battery":    None,
            "latency_ms": None,
        }

        if SDK_AVAILABLE and self.client and self.connected:
            try:
                state = self.client.GetRobotState()
                status["battery"]    = round(state.battery_level * 100)
                status["latency_ms"] = round((_time.time() - start) * 1000)
            except Exception:
                pass

        return status


# ── Module-level robot instance ───────────────────────────────────────────────
# Shared by app.py across all requests
robot = K1Robot()
