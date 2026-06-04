"""
k1_handler.py
K1 robot movement and gesture handler via ROS2.

Runs directly on the K1 — publishes movement commands to ROS2 topics
natively. No Booster SDK required.

Movement topics:
    /LocoApiTopicReq  — high-level locomotion commands

Gesture topics:
    /booster/ros2_k2_joint_cmd — joint commands for gestures

Usage:
    from k1_handler import robot
    robot.connect()
    robot.set_walk_mode()
    robot.move("walk_forward", duration=2.0)
    robot.gesture("wave")
    robot.disconnect()

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import time
import threading
import json

# ROS2 availability check
_ros_available = False
try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    from geometry_msgs.msg import Twist
    _ros_available = True
    print("[k1_handler] ROS2 available — native K1 control enabled")
except ImportError:
    print("[k1_handler] WARNING: ROS2 not available. Movement commands will be logged only.")

WALK_SPEED = 0.3   # m/s
TURN_SPEED = 0.5   # rad/s
MOVE_DURATION = 2.0
TURN_DURATION = 1.5


class K1Robot:
    def __init__(self):
        self._node      = None
        self._executor  = None
        self._thread    = None
        self._running   = False
        self.connected  = False
        self.current_mode = "damp"

        # Publishers
        self._loco_pub  = None   # /LocoApiTopicReq
        self._twist_pub = None   # /cmd_vel fallback

    def connect(self) -> bool:
        if not _ros_available:
            print("[K1] Simulated connect (ROS2 not available)")
            self.connected = True
            return True
        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            self._node = rclpy.create_node("k1_wizard_handler")

            self._loco_pub  = self._node.create_publisher(
                String, "/LocoApiTopicReq", 10
            )
            self._twist_pub = self._node.create_publisher(
                Twist, "/cmd_vel", 10
            )

            self._executor = rclpy.executors.SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._running = True
            self._thread  = threading.Thread(
                target=self._spin, daemon=True
            )
            self._thread.start()

            self.connected = True
            print("[K1] Connected via ROS2")
            return True
        except Exception as e:
            print(f"[K1] Connection failed: {e}")
            self.connected = False
            return False

    def _spin(self):
        while self._running:
            try:
                self._executor.spin_once(timeout_sec=0.1)
            except Exception:
                break

    def disconnect(self):
        self._running  = False
        self.connected = False
        if self._executor:
            self._executor.shutdown()
        print("[K1] Disconnected")

    # ── Mode transitions ──────────────────────────────────────

    def set_damp_mode(self):
        self._publish_loco({"command": "damp"})
        self.current_mode = "damp"
        print("[K1] Mode → Damp")

    def set_prep_mode(self):
        self._publish_loco({"command": "prepare"})
        self.current_mode = "prep"
        print("[K1] Mode → Prep")
        time.sleep(3)

    def set_walk_mode(self):
        if self.current_mode == "damp":
            self.set_prep_mode()
        self._publish_loco({"command": "walk"})
        self.current_mode = "walk"
        print("[K1] Mode → Walk")

    def _publish_loco(self, payload: dict):
        if _ros_available and self._loco_pub:
            msg = String()
            msg.data = json.dumps(payload)
            self._loco_pub.publish(msg)

    # ── Movement ──────────────────────────────────────────────

    def move(self, command: str, duration=None) -> bool:
        if not self.connected:
            print("[K1] Not connected")
            return False
        if self.current_mode != "walk":
            print("[K1] Must be in Walk mode to move")
            return False

        dur = duration or MOVE_DURATION
        handlers = {
            "walk_forward":  self._walk_forward,
            "walk_backward": self._walk_backward,
            "turn_left":     self._turn_left,
            "turn_right":    self._turn_right,
            "stop":          self._stop,
        }
        fn = handlers.get(command)
        if not fn:
            print(f"[K1] Unknown command: {command}")
            return False
        fn(dur)
        return True

    def _publish_twist(self, vx, wz, duration):
        if not (_ros_available and self._twist_pub):
            print(f"[K1] Simulated twist: vx={vx} wz={wz} ({duration}s)")
            return
        twist = Twist()
        twist.linear.x  = float(vx)
        twist.angular.z = float(wz)
        self._twist_pub.publish(twist)
        time.sleep(duration)
        self._twist_pub.publish(Twist())  # Stop

    def _walk_forward(self, duration):
        print(f"[K1] Walk forward ({duration}s)")
        self._publish_twist(WALK_SPEED, 0, duration)

    def _walk_backward(self, duration):
        print(f"[K1] Walk backward ({duration}s)")
        self._publish_twist(-WALK_SPEED, 0, duration)

    def _turn_left(self, duration):
        print(f"[K1] Turn left ({duration}s)")
        self._publish_twist(0, TURN_SPEED, duration)

    def _turn_right(self, duration):
        print(f"[K1] Turn right ({duration}s)")
        self._publish_twist(0, -TURN_SPEED, duration)

    def _stop(self, _duration=0):
        print("[K1] Stop")
        if _ros_available and self._twist_pub:
            self._twist_pub.publish(Twist())

    # ── Gestures ──────────────────────────────────────────────

    def gesture(self, name: str) -> bool:
        if not self.connected:
            print("[K1] Not connected")
            return False
        gestures = {
            "wave":      self._gesture_wave,
            "nod":       self._gesture_nod,
            "thumbs_up": self._gesture_thumbs_up,
        }
        fn = gestures.get(name)
        if not fn:
            print(f"[K1] Unknown gesture: {name}")
            return False
        fn()
        return True

    def _gesture_wave(self):
        print("[K1] Gesture: wave")
        self._publish_loco({"command": "wave"})

    def _gesture_nod(self):
        print("[K1] Gesture: nod")
        self._publish_loco({"command": "nod"})

    def _gesture_thumbs_up(self):
        print("[K1] Gesture: thumbs_up")
        self._publish_loco({"command": "thumbs_up"})

    # ── Status ────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "connected":  self.connected,
            "mode":       self.current_mode,
            "battery":    None,
            "latency_ms": None,
        }


# Module-level robot instance
robot = K1Robot()
