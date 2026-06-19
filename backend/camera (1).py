"""
camera.py
K1 camera stream via ROS2 — MJPEG for browser dashboard.

Subscribes to /image_left_raw (confirmed working topic on K1).
Handles multiple encodings: rgb8, bgr8, mono8, yuv422/yuyv.
Streams as MJPEG multipart via Flask /api/camera/stream route.

Important: Does NOT call rclpy.init() — that is handled by k1_handler.py.
This module shares the ROS2 context initialized there.

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import threading
import time
import numpy as np

# ── Availability flags ────────────────────────────────────────
_ros_available = False
_cv_available  = False

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    _ros_available = True
except ImportError:
    print("[camera] ROS2 not available — camera offline")

try:
    import cv2
    _cv_available = True
except ImportError:
    print("[camera] OpenCV not available — camera offline")

# ── Frame state ───────────────────────────────────────────────
_latest_frame = None
_frame_lock   = threading.Lock()

# Offline placeholder JPEG (1x1 dark gray pixel)
_OFFLINE_JPEG = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
    0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
    0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
    0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
    0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xFB, 0xFF,
    0xD9
])


# =============================================================================
# CAMERA NODE
# =============================================================================

if _ros_available and _cv_available:
    class _CameraNode(Node):
        """
        ROS2 subscriber node for K1 camera stream.
        Topic: /image_left_raw (confirmed working on K1)
        Handles rgb8, bgr8, mono8, yuv422/yuyv encodings.
        """
        CAMERA_TOPIC   = "/image_left_raw"
        JPEG_QUALITY   = 80
        STREAM_WIDTH   = 640
        STREAM_HEIGHT  = 480

        def __init__(self):
            super().__init__("k1_camera_stream")
            self._sub = self.create_subscription(
                Image,
                self.CAMERA_TOPIC,
                self._on_image,
                10,
            )
            self.get_logger().info(f"Camera subscribed to {self.CAMERA_TOPIC}")

        def _on_image(self, msg: Image):
            global _latest_frame
            try:
                img = self._decode(msg)
                if img is None:
                    return

                # Resize for stream
                img = cv2.resize(img, (self.STREAM_WIDTH, self.STREAM_HEIGHT))

                # Encode to JPEG
                ok, buf = cv2.imencode(
                    ".jpg", img,
                    [cv2.IMWRITE_JPEG_QUALITY, self.JPEG_QUALITY]
                )
                if ok:
                    with _frame_lock:
                        _latest_frame = buf.tobytes()

            except Exception as e:
                self.get_logger().warn(f"Frame error: {e}")

        def _decode(self, msg: Image):
            """Convert ROS2 Image message to BGR numpy array."""
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            enc = msg.encoding.lower()

            if enc == "rgb8":
                img = arr.reshape((msg.height, msg.width, 3))
                return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            elif enc == "bgr8":
                return arr.reshape((msg.height, msg.width, 3))

            elif enc == "mono8":
                img = arr.reshape((msg.height, msg.width))
                return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

            elif enc in ("yuv422", "yuyv", "yuv422_yuy2"):
                img = arr.reshape((msg.height, msg.width, 2))
                return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_YUYV)

            else:
                # Try raw reshape as last resort
                try:
                    channels = len(arr) // (msg.height * msg.width)
                    img = arr.reshape((msg.height, msg.width, channels))
                    if channels == 3:
                        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                    return img
                except Exception:
                    self.get_logger().warn(
                        f"Unknown encoding: {msg.encoding} "
                        f"({msg.height}x{msg.width})"
                    )
                    return None


# =============================================================================
# CAMERA HANDLER
# =============================================================================

class CameraHandler:
    """
    Manages the camera ROS2 node lifecycle.
    Call start() once at Flask startup.
    """

    def __init__(self):
        self._node    = None
        self._running = False

    @property
    def has_frame(self) -> bool:
        with _frame_lock:
            return _latest_frame is not None

    def start(self) -> None:
        """
        Start the camera subscriber node.
        Adds to the existing ROS2 executor in k1_handler.
        """
        if not (_ros_available and _cv_available):
            print("[camera] ROS2 or OpenCV not available — camera disabled")
            return

        try:
            from k1_handler import _rpc_node

            if not _rpc_node._ready or _rpc_node._executor is None:
                print("[camera] ROS2 executor not ready — camera disabled")
                return

            self._node = _CameraNode()
            _rpc_node._executor.add_node(self._node)
            self._running = True
            print("[camera] Camera node started — streaming /image_left_raw")

        except Exception as e:
            print(f"[camera] Failed to start: {e}")

    def stop(self) -> None:
        if self._node:
            try:
                from k1_handler import _rpc_node
                _rpc_node._executor.remove_node(self._node)
                self._node.destroy_node()
            except Exception:
                pass
            self._node    = None
            self._running = False
            print("[camera] Camera node stopped")


# =============================================================================
# MJPEG STREAM GENERATOR
# =============================================================================

def camera_stream():
    """
    Generator for Flask MJPEG response.
    Yields JPEG frames at ~15fps.
    Falls back to offline placeholder when no frame available.
    """
    while True:
        with _frame_lock:
            frame = _latest_frame

        jpeg = frame if frame is not None else _OFFLINE_JPEG

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            jpeg +
            b"\r\n"
        )
        time.sleep(1 / 15)  # ~15fps


# Single shared instance used by app.py
camera_handler = CameraHandler()
