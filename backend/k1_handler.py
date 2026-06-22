"""
k1_handler.py
K1 robot control via native ROS2 Python client.

Uses a persistent ROS2 node and async service calls instead of subprocess,
giving much faster response times (~50ms vs 2-4s per command).

Confirmed API IDs (tested on K1 firmware v1.6.1.1, June 2026):
    2000 = ChangeMode       body: {"mode": N}
    2001 = Move             body: {"vx": f, "vy": f, "vyaw": f}
    2004 = RotateHead       body: {"pitch": f, "yaw": f}
    2005 = WaveHand         body: {}
    2007 = LieDown          body: {}
    2008 = GetUp            body: {}
    2015 = Handshake        body: {}
    2016 = Dance            body: {"dance_id": N}  (upper body)
    2017 = GetMode          body: {} → {"mode": N}
    2018 = GetStatus        body: {} → {"current_mode": N}
    2029 = WholeBodyDance   body: {"dance_id": N}

RobotMode values (confirmed):
    0 = Damp
    1 = Prep
    2 = Walk

Startup sequence — robot lying face-down after boot:
    Damp → Prep (mode 1, wait 3s) → GetUp (api 2008, wait 10s) → Walk

Startup sequence — robot already standing:
    Prep (mode 1, wait 3s) → ChangeMode Walk (mode 2) — no GetUp needed

Safe shutdown sequence:
    Walk → Prep → LieDown (api 2007) → Damp

DanceId (api 2016 — upper body, safe from standing):
    0=NewYear, 1=Nezha, 2=TowardsFuture, 3=Dabbing, 4=Ultraman,
    5=Respect, 6=Cheering, 7=LuckyCat, 1000=Stop

WholeBodyDanceId (api 2029 — requires clear space):
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

FIX LOG:
    2026-06 — Issue F: _publish_button_event() was only called inside
    _do_get_up(). If the operator confirmed 'walk' via the safety modal
    (skipping GetUp entirely), button_event was never published. Move RPC
    returned status=0 but the robot did not physically move.

    Fix: _publish_button_event() is now called at the end of ALL paths
    inside set_walk_mode() that result in current_mode = "walk":
      - already in walk (mode sync path)
      - ChangeMode Walk success (upright from Prep path)
      - _do_get_up() success (lying-down path — was already calling it)

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import json
import time
import threading
import re

# ── RobotMode values ──────────────────────────────────────────
MODE_DAMP = 0
MODE_PREP = 1
MODE_WALK = 2

# ── API IDs ───────────────────────────────────────────────────
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

# ── Movement parameters ───────────────────────────────────────
WALK_SPEED    = 0.3   # m/s
TURN_SPEED    = 0.5   # rad/s
MOVE_DURATION = 2.0   # seconds


# =============================================================================
# ROS2 RPC CLIENT
# Persistent node — one per process, thread-safe via lock
# =============================================================================

class _RpcNode:
    """
    Persistent ROS2 node for calling /booster_rpc_service.
    Runs in a background executor thread.
    All public methods are thread-safe.
    """

    def __init__(self):
        self._node        = None
        self._client      = None
        self._executor    = None
        self._spin_thread = None
        self._lock        = threading.Lock()
        self._ready       = False

    def start(self) -> bool:
        """Initialize ROS2 node and start background executor."""
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor

            rclpy.init()
            self._node   = rclpy.create_node("k1_dashboard_rpc")
            self._client = self._node.create_client(
                self._rpc_srv_type(),
                "booster_rpc_service"
            )

            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)

            self._spin_thread = threading.Thread(
                target=self._executor.spin,
                daemon=True,
                name="k1_rpc_executor"
            )
            self._spin_thread.start()
            self._ready = True
            print("[RPC] ROS2 node started — k1_dashboard_rpc")
            return True

        except Exception as e:
            print(f"[RPC] ROS2 node start failed: {e}")
            self._ready = False
            return False

    def _rpc_srv_type(self):
        """Import and return the RpcService type."""
        from booster_interface.srv import RpcService
        return RpcService

    def call(self, api_id: int, body: dict, timeout: float = 8.0) -> tuple:
        """
        Call the RPC service with api_id and body dict.
        Thread-safe. Returns (status, response_body_dict).
        Returns (-1, {}) on failure.
        """
        if not self._ready:
            return -1, {}

        try:
            from booster_interface.srv import RpcService

            request = RpcService.Request()
            request.msg.api_id = api_id
            request.msg.body   = json.dumps(body) if body else ""

            with self._lock:
                if not self._client.wait_for_service(timeout_sec=3.0):
                    print(f"[RPC] Service not available for api_id={api_id}")
                    return -1, {}

                future = self._client.call_async(request)

            # Wait for result outside lock so executor can spin
            deadline = time.time() + timeout
            while not future.done():
                if time.time() > deadline:
                    print(f"[RPC] Timeout waiting for api_id={api_id}")
                    return -1, {}
                time.sleep(0.01)

            result = future.result()
            if result is None:
                print(f"[RPC] Null result for api_id={api_id}")
                return -1, {}

            status    = result.msg.status
            resp_body = {}
            if result.msg.body:
                try:
                    resp_body = json.loads(result.msg.body)
                except Exception:
                    pass

            return status, resp_body

        except Exception as e:
            print(f"[RPC] Error on api_id={api_id}: {e}")
            return -1, {}


# ── Fallback subprocess RPC (used if ROS2 node fails to start) ───────────────

def _subprocess_rpc(api_id: int, body: dict, timeout: int = 10) -> tuple:
    """
    Subprocess fallback for rpc_call.
    Slower (~2-4s) but works without a persistent ROS2 node.
    """
    import subprocess

    ROS2_SETUP = (
        "source /opt/ros/humble/setup.bash && "
        "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
    )
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
        print(f"[RPC] Subprocess timeout on api_id={api_id}")
        return -1, {}
    except Exception as e:
        print(f"[RPC] Subprocess error on api_id={api_id}: {e}")
        return -1, {}


# ── Global RPC node instance ──────────────────────────────────
_rpc_node = _RpcNode()


def rpc_call(api_id: int, body: dict, timeout: float = 8.0) -> tuple:
    """
    Call the Booster RPC service.
    Uses native ROS2 Python client if available, falls back to subprocess.
    Returns (status, response_body_dict).
    """
    if _rpc_node._ready:
        status, resp = _rpc_node.call(api_id, body, timeout=timeout)
        if status >= 0:
            return status, resp
        print(f"[RPC] Native call failed for api_id={api_id} — trying subprocess")
    return _subprocess_rpc(api_id, body, timeout=int(timeout))


def rpc_mode_str(rpc_mode: int) -> str:
    """Convert RPC mode integer to dashboard mode string."""
    return {
        0: "damp",
        1: "prep",
        2: "walk",
        3: "custom",
        4: "soccer"
    }.get(rpc_mode, "damp")


def get_robot_mode() -> tuple:
    """
    Query actual robot mode via RPC.
    Returns (rpc_mode_int, mode_str) or (-1, 'unknown') on failure.
    """
    status, resp = rpc_call(API_GET_MODE, {}, timeout=8.0)
    if status == 0 and resp:
        rpc_mode = resp.get("mode", -1)
        return rpc_mode, rpc_mode_str(rpc_mode)
    return -1, "unknown"


# =============================================================================
# K1 ROBOT
# =============================================================================

class K1Robot:
    def __init__(self):
        self.connected    = False
        self.current_mode = "damp"
        self._battery     = None

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Start the ROS2 RPC node.
        Mode is set by the operator via the safety modal on dashboard load.
        No background sync — avoids blocking the ROS2 executor and camera.
        """
        ros2_ok = _rpc_node.start()
        if ros2_ok:
            print("[K1] ROS2 RPC client ready")
        else:
            print("[K1] ROS2 node failed — using subprocess fallback")
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False
        print("[K1] Disconnected")

    # ── Mode transitions ──────────────────────────────────────

    def set_damp_mode(self) -> bool:
        """
        Damp — motors relax, robot goes limp.
        Safe from Prep. Do NOT use directly from Walk — use Prep first.
        """
        print("[K1] Mode → Damp")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_DAMP})
        if status == 0:
            self.current_mode = "damp"
            return True
        print(f"[K1] Damp failed (status={status})")
        return False

    def set_prep_mode(self) -> bool:
        """
        Prep — robot stiffens and stabilizes.
        Works from Damp (crouches) or Walk (stabilizes in place).
        Wait 3s after for balance stabilization.
        """
        print("[K1] Mode → Prep")
        status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_PREP})
        if status == 0:
            self.current_mode = "prep"
            time.sleep(3)
            return True
        print(f"[K1] Prep failed (status={status})")
        return False

    def set_walk_mode(self) -> bool:
        """
        Walk mode — robot ready for movement.

        FIX (Issue F): _publish_button_event() is now called on ALL paths
        that result in walk mode, not just after GetUp. Without this, Move RPC
        returns status=0 but the robot ignores the command entirely.

        Paths:
          1. Already in walk  → sync cache + publish button_event
          2. In Prep, upright → ChangeMode Walk + publish button_event
          3. In Prep, lying   → GetUp (publishes button_event internally)
          4. In Damp          → reject, operator must Prep first
        """
        rpc_mode, _ = get_robot_mode()

        # ── Path 1: already in walk ───────────────────────────
        if rpc_mode == MODE_WALK:
            print("[K1] Already in walk mode — publishing button_event to ensure Move works")
            self.current_mode = "walk"
            self._publish_button_event()          # FIX: was missing on this path
            return True

        # ── Path 2 / 3: in prep ──────────────────────────────
        if rpc_mode == MODE_PREP:
            # Try direct ChangeMode Walk (works when already upright)
            status, _ = rpc_call(API_CHANGE_MODE, {"mode": MODE_WALK})
            if status == 0:
                time.sleep(2)
                self.current_mode = "walk"
                self._publish_button_event()      # FIX: was missing on this path
                print("[K1] Mode → Walk")
                return True
            # ChangeMode failed — robot likely lying down, need GetUp
            print("[K1] ChangeMode Walk failed — trying GetUp")
            return self._do_get_up()              # button_event published inside

        # ── Path 4: in damp ──────────────────────────────────
        if rpc_mode == MODE_DAMP:
            print("[K1] Cannot go to Walk from Damp — press Prep first")
            return False

        # ── Unknown state — try GetUp as last resort ──────────
        print(f"[K1] Unknown mode {rpc_mode} — attempting GetUp")
        return self._do_get_up()                  # button_event published inside

    def _do_get_up(self) -> bool:
        """Stand up from lying position using api 2008. Wait 10s for completion."""
        print("[K1] GetUp → standing (10s)")
        status, _ = rpc_call(API_GET_UP, {}, timeout=15.0)
        if status == 0:
            time.sleep(10)
            # Must publish button_event after GetUp or Move commands are ignored
            self._publish_button_event()
            self.current_mode = "walk"
            print("[K1] Mode → Walk ready")
            return True
        print(f"[K1] GetUp failed (status={status})")
        return False

    def _publish_button_event(self) -> None:
        """
        Publish {event:2, button:2} to /button_event.

        Required before ANY Move command will be obeyed by the robot.
        Without this, rpc_call(API_MOVE, ...) returns status=0 but the
        robot does not move.

        Previously this was only called inside _do_get_up(). It is now
        called at the end of every path in set_walk_mode() that sets
        current_mode = "walk".
        """
        try:
            import subprocess
            cmd = (
                "source /opt/ros/humble/setup.bash && "
                "source /opt/booster/BoosterRos2Interface/install/setup.bash && "
                "ros2 topic pub --once /button_event "
                "booster_interface/msg/ButtonEventMsg '{event: 2, button: 2}'"
            )
            subprocess.run(["bash", "-c", cmd], timeout=5, capture_output=True)
            print("[K1] button_event published — Move commands now active")
        except Exception as e:
            print(f"[K1] button_event publish failed: {e}")

    def get_up(self) -> bool:
        """
        Stand-up button. Skips if already in walk mode.
        """
        rpc_mode, _ = get_robot_mode()
        if rpc_mode == MODE_WALK:
            print("[K1] Already standing")
            self.current_mode = "walk"
            self._publish_button_event()          # ensure Move works after manual get_up call
            return True
        return self._do_get_up()

    def lie_down(self) -> bool:
        """
        Lie down safely via api 2007.
        Robot should be in Prep before calling this.
        Falls back to Damp if LieDown RPC fails.
        """
        print("[K1] LieDown")
        status, _ = rpc_call(API_LIE_DOWN, {}, timeout=15.0)
        if status == 0:
            time.sleep(5)
            self.current_mode = "damp"
            print("[K1] Robot lying down")
            return True
        print(f"[K1] LieDown failed (status={status}) — falling back to Damp")
        return self.set_damp_mode()

    # ── Movement ──────────────────────────────────────────────

    def move(self, command: str, duration: float = None) -> bool:
        """
        Move the robot. Must be in Walk mode.
        Sends stop automatically after duration seconds.
        """
        if not self.connected:
            print("[K1] Not connected")
            return False
        if self.current_mode != "walk":
            print("[K1] Must be in Walk mode to move")
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
            print(f"[K1] {command} complete — stopped")

        return status == 0

    # ── Gestures ──────────────────────────────────────────────

    def gesture(self, name: str) -> bool:
        """
        Execute a gesture.
            wave      → api 2005 WaveHand     body: {"hand_index": 0, "action": 0}
            nod       → api 2004 RotateHead   sequence
            thumbs_up → api 2015 Handshake    body: {"hand_index": 0, "action": 0}
            bow       → api 2006 Bow          body: {}
        """
        if not self.connected:
            print("[K1] Not connected")
            return False

        print(f"[K1] Gesture: {name}")

        try:
            if name == "wave":
                status, _ = rpc_call(API_WAVE_HAND, {"hand_index": 0, "action": 0})
                if status != 0:
                    print(f"[K1] Wave failed (status={status})")
                return status == 0

            elif name == "nod":
                rpc_call(API_ROTATE_HEAD, {"pitch":  0.3, "yaw": 0.0})
                time.sleep(0.6)
                rpc_call(API_ROTATE_HEAD, {"pitch": -0.3, "yaw": 0.0})
                time.sleep(0.6)
                rpc_call(API_ROTATE_HEAD, {"pitch":  0.0, "yaw": 0.0})
                return True

            elif name == "thumbs_up":
                status, _ = rpc_call(API_HANDSHAKE, {"hand_index": 0, "action": 0})
                if status != 0:
                    print(f"[K1] Thumbs up failed (status={status})")
                return status == 0

            elif name == "bow":
                status, _ = rpc_call(2006, {})
                if status != 0:
                    print(f"[K1] Bow failed (status={status})")
                return status == 0

            else:
                print(f"[K1] Unknown gesture: {name}")
                return False

        except Exception as e:
            print(f"[K1] Gesture error: {e}")
            return False

    # ── Dance ─────────────────────────────────────────────────

    def dance(self, dance_id: int, whole_body: bool = False) -> bool:
        """
        Trigger a dance. Operator-initiated only — not from LLM.

        whole_body=False → api 2016 upper body (safe from standing)
        whole_body=True  → api 2029 whole body (requires clear space)
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
        No live RPC call — keeps dashboard fast.
        """
        return {
            "connected":  self.connected,
            "mode":       self.current_mode,
            "battery":    self._battery,
            "latency_ms": None,
        }

    def refresh_battery(self) -> None:
        """
        Poll robot status via api 2018.
        Call from a background thread — not on every dashboard poll.
        """
        try:
            status, resp = rpc_call(API_GET_STATUS, {}, timeout=8.0)
            if status == 0 and resp:
                rpc_mode = resp.get("current_mode", -1)
                if rpc_mode >= 0:
                    self.current_mode = rpc_mode_str(rpc_mode)
                print(f"[K1] Status refreshed: mode={self.current_mode}")
        except Exception as e:
            print(f"[K1] Status refresh error: {e}")


# Single shared instance used by app.py
robot = K1Robot()
