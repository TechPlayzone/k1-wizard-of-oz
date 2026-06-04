"""
battery_monitor.py
K1 battery state monitor via ROS2.

Subscribes to /battery_state and provides:
    - Current battery percentage
    - Low battery warning (< 20%)
    - Critical battery warning (< 10%)

The Booster app normally handles battery warnings but is
bypassed when using the Wizard-of-Oz Dashboard. This module
replaces that functionality.

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import threading
import time

_ros_available = False
try:
    import rclpy
    from rclpy.node import Node
    _ros_available = True
except ImportError:
    pass

# Battery state
_battery_level    = None   # 0-100 percentage
_battery_lock     = threading.Lock()
_warning_sent     = False  # Prevent repeated warnings
_critical_sent    = False

LOW_BATTERY      = 20  # % — show warning
CRITICAL_BATTERY = 10  # % — urgent warning


def get_battery_level():
    """Return current battery percentage or None if unknown."""
    with _battery_lock:
        return _battery_level


def get_battery_status():
    """
    Return battery status dict for dashboard status strip.
    """
    level = get_battery_level()
    if level is None:
        return {"level": None, "status": "unknown", "warning": False, "critical": False}
    return {
        "level":    level,
        "status":   "ok" if level > LOW_BATTERY else ("low" if level > CRITICAL_BATTERY else "critical"),
        "warning":  level <= LOW_BATTERY,
        "critical": level <= CRITICAL_BATTERY,
    }


if _ros_available:
    class BatteryNode(Node):
        """
        ROS2 node that subscribes to /battery_state.
        The K1 publishes battery info on this topic continuously.
        """
        def __init__(self):
            super().__init__("k1_battery_monitor")

            # Try standard sensor_msgs BatteryState first
            try:
                from sensor_msgs.msg import BatteryState
                self._sub = self.create_subscription(
                    BatteryState,
                    "/battery_state",
                    self._on_battery,
                    10,
                )
                self.get_logger().info("Battery monitor subscribed to /battery_state")
            except Exception as e:
                self.get_logger().warn(f"Battery subscription failed: {e}")

        def _on_battery(self, msg):
            global _battery_level, _warning_sent, _critical_sent
            try:
                # sensor_msgs/BatteryState uses percentage 0.0-1.0
                # Some robots publish 0-100
                pct = msg.percentage
                if pct <= 1.0:
                    pct = pct * 100
                level = round(pct)

                with _battery_lock:
                    _battery_level = level

                # Log warnings
                if level <= CRITICAL_BATTERY and not _critical_sent:
                    self.get_logger().error(
                        f"CRITICAL BATTERY: {level}% — Robot may fall soon! Charge immediately."
                    )
                    _critical_sent = True
                elif level <= LOW_BATTERY and not _warning_sent:
                    self.get_logger().warn(
                        f"LOW BATTERY: {level}% — Save your work and prepare to charge."
                    )
                    _warning_sent = True
                elif level > LOW_BATTERY:
                    _warning_sent  = False
                    _critical_sent = False

            except Exception as e:
                self.get_logger().warn(f"Battery parse error: {e}")


class BatteryMonitor:
    def __init__(self):
        self._node    = None
        self._running = False

    def start(self) -> bool:
        if not _ros_available:
            print("[battery] ROS2 unavailable — battery monitoring disabled")
            return False
        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            self._node = BatteryNode()
            t = threading.Thread(
                target=lambda: rclpy.spin(self._node), daemon=True
            )
            t.start()
            self._running = True
            print("[battery] Battery monitor started")
            return True
        except Exception as e:
            print(f"[battery] Failed to start: {e}")
            return False


battery_monitor = BatteryMonitor()
