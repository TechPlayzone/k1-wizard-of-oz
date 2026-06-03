"""
camera.py
K1 ZED camera feed handler.

The K1 EDU uses a ZED stereo camera. The ZED ROS2 wrapper node
launches automatically when the robot powers on and publishes
color frames to:
    /zed/zed_node/rgb/image_rect_color

This module:
    1. Subscribes to the ZED ROS2 topic
    2. Converts frames to JPEG
    3. Yields them as a multipart MJPEG stream
    4. Flask serves the stream at GET /api/camera/stream

The dashboard displays it with:
    <img src="/api/camera/stream">

If ROS2 or the camera topic is unavailable (e.g. running on
Windows for development), the stream returns a "Camera offline"
placeholder frame gracefully.

Usage:
    from camera import camera_stream, camera_handler
    camera_handler.start()   # Call once at Flask startup
    # Flask route yields: camera_stream()
"""

import io
import time
import threading
import numpy as np

# ── ROS2 availability check ───────────────────────────────────────────────────
_ros_available = False
try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from cv_bridge import CvBridge
    import cv2
    _ros_available = True
    print("[camera] ROS2 + cv_bridge available — ZED stream enabled")
except ImportError:
    try:
        import cv2
        print("[camera] ROS2 not available — camera stream will show offline placeholder")
    except ImportError:
        print("[camera] cv2 not available — camera stream will show text placeholder")

# ── Camera state ──────────────────────────────────────────────────────────────
_latest_frame   = None   # Latest JPEG bytes
_frame_lock     = threading.Lock()
_frame_event    = threading.Event()  # Signals new frame available


def _make_offline_frame(message="Camera offline"):
    """
    Generate a simple placeholder JPEG frame when camera is unavailable.
    Returns JPEG bytes.
    """
    try:
        import cv2
        import numpy as np
        # Dark gray 640x480 frame with centered text
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        cv2.putText(
            img, message,
            (200, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8, (150, 150, 150), 2, cv2.LINE_AA
        )
        _, jpeg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return jpeg.tobytes()
    except Exception:
        # Minimal 1x1 gray JPEG if cv2 not available
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01'
            b'\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07'
            b'\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14'
            b'\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444'
            b'\x1f\'9=82<.342\x1edL\'E;=;YZ[abcdefgXXbbbbbbbbbbbbbbbb'
            b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4'
            b'\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
            b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xff\xd9'
        )


# ── ROS2 camera subscriber node ───────────────────────────────────────────────

class CameraNode(Node):
    """
    ROS2 node that subscribes to the K1 ZED camera topic and
    stores the latest frame as JPEG bytes for streaming.
    """
    # ZED ROS2 color image topic (published automatically on K1 boot)
    CAMERA_TOPIC = "/zed/zed_node/rgb/image_rect_color"

    def __init__(self):
        super().__init__("k1_camera_bridge")
        self._bridge = CvBridge()
        self._sub = self.create_subscription(
            Image,
            self.CAMERA_TOPIC,
            self._on_image,
            10,
        )
        self.get_logger().info(
            f"Subscribed to {self.CAMERA_TOPIC}"
        )

    def _on_image(self, msg: Image):
        global _latest_frame
        try:
            # Convert ROS2 Image message to OpenCV BGR frame
            cv_image = self._bridge.imgmsg_to_cv2(msg, "bgr8")

            # Resize to 640x480 for dashboard (ZED native is larger)
            cv_image = cv2.resize(cv_image, (640, 480))

            # Encode as JPEG
            _, jpeg = cv2.imencode(
                '.jpg', cv_image,
                [cv2.IMWRITE_JPEG_QUALITY, 75]
            )
            with _frame_lock:
                _latest_frame = jpeg.tobytes()
            _frame_event.set()
            _frame_event.clear()

        except Exception as e:
            self.get_logger().warn(f"Frame conversion error: {e}")


# ── Camera handler ────────────────────────────────────────────────────────────

class CameraHandler:
    """
    Manages the ROS2 camera node lifecycle.
    Call start() once at Flask startup.
    """

    def __init__(self):
        self._node     = None
        self._executor = None
        self._thread   = None
        self._running  = False

    def start(self) -> bool:
        """Start the ROS2 camera subscriber node."""
        if not _ros_available:
            print("[camera] Camera handler not started — ROS2 unavailable")
            return False
        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            self._node     = CameraNode()
            self._executor = rclpy.executors.SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._running  = True
            self._thread   = threading.Thread(
                target=self._spin, daemon=True
            )
            self._thread.start()
            print("[camera] ZED camera subscriber started")
            return True
        except Exception as e:
            print(f"[camera] Failed to start: {e}")
            return False

    def _spin(self):
        while self._running:
            try:
                self._executor.spin_once(timeout_sec=0.033)  # ~30fps
            except Exception:
                break

    def stop(self):
        self._running = False
        if self._executor:
            self._executor.shutdown()

    @property
    def has_frame(self) -> bool:
        return _latest_frame is not None


# ── MJPEG stream generator ────────────────────────────────────────────────────

def camera_stream():
    """
    Generator that yields MJPEG multipart frames for Flask streaming.

    Usage in Flask route:
        return Response(
            camera_stream(),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )
    """
    offline_frame = _make_offline_frame("Live Camera Feed — K1 ZED")
    fps_interval  = 1.0 / 30.0   # Target 30fps

    while True:
        with _frame_lock:
            frame = _latest_frame

        if frame is None:
            # No live frame — send offline placeholder at 2fps
            frame = offline_frame
            time.sleep(0.5)
        else:
            time.sleep(fps_interval)

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n'
            + frame +
            b'\r\n'
        )


# ── Module-level handler instance ─────────────────────────────────────────────
camera_handler = CameraHandler()
