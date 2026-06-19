"""
battery_monitor.py
K1 battery monitoring via RPC GetStatus (api 2018).

Polls battery status every 30 seconds in a background thread.
Does NOT use ROS2 topic subscription — the booster_interface/msg/BatteryState
message type is not available in the installed ROS2 interface package.

Note: GetStatus (api 2018) returns current_mode and current_body_control
but does NOT include battery percentage. Battery level remains unavailable
until Booster provides the correct API or message type.

This module provides a placeholder that can be updated when battery
data becomes available (via Booster support response or DDS gateway).

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import threading
import time

_battery_level   = None
_battery_lock    = threading.Lock()

LOW_BATTERY      = 20
CRITICAL_BATTERY = 10


def get_battery_level():
    with _battery_lock:
        return _battery_level


def get_battery_status():
    level = get_battery_level()
    if level is None:
        return {"level": None, "status": "unknown", "warning": False, "critical": False}
    return {
        "level":    level,
        "status":   "ok" if level > LOW_BATTERY else ("low" if level > CRITICAL_BATTERY else "critical"),
        "warning":  level <= LOW_BATTERY,
        "critical": level <= CRITICAL_BATTERY,
    }


class BatteryMonitor:
    """
    Polls robot status via RPC in a background thread.
    Currently only syncs mode — battery percentage not available via RPC.
    """

    def __init__(self):
        self._running = False
        self._thread  = None

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print("[battery] Battery monitor started (RPC polling)")
        return True

    def stop(self):
        self._running = False

    def _poll_loop(self):
        """Poll every 30 seconds."""
        time.sleep(10)  # Wait for Flask and RPC to be ready
        while self._running:
            try:
                from k1_handler import rpc_call, rpc_mode_str, robot
                status, resp = rpc_call(2018, {}, timeout=8.0)
                if status == 0 and resp:
                    rpc_mode = resp.get("current_mode", -1)
                    if rpc_mode >= 0:
                        robot.current_mode = rpc_mode_str(rpc_mode)
            except Exception as e:
                print(f"[battery] Poll error: {e}")
            time.sleep(30)


battery_monitor = BatteryMonitor()
