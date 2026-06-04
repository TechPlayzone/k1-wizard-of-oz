"""
camera.py
K1 camera feed handler via ROS2.

Subscribes to the K1's native camera topic:
    /boostercamera/head/rgb  (encoding: nv12)

Converts nv12 frames to JPEG and serves them as an MJPEG
stream at GET /api/camera/stream.

The dashboard displays the stream with:
    <img src="/api/camera/stream">

Runs directly on the K1 — no network bridging needed.

Hillsborough College AI Innovation Center
AI PREP4WORK Initiative — FIPSE Grant Program
Deshjuana Bagley, Associate Dean, A.S. Degree Programs
"""

import time
import threading
import numpy as np

# ROS2 + cv2 availability
_ros_available = False
_cv2_available = False
_latest_frame  = None
_frame_lock    = threading.Lock()

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    import cv2
    _ros_available = True
    _cv2_available = True
    print("[camera] ROS2 + cv2 available — K1 camera stream enabled")
except ImportError:
    try:
        import cv2
        _cv2_available = True
        print("[camera] ROS2 not available — offline placeholder active")
    except ImportError:
        print("[camera] cv2 not available — minimal placeholder active")


def _nv12_to_bgr(data: bytes, width: int, height: int):
    """
    Convert NV12 (YUV 4:2:0) raw bytes to a BGR OpenCV image.
    The K1 camera publishes in nv12 format.
    """
    yuv = np.frombuffer(data, dtype=np.uint8).reshape(
        (height * 3 // 2, width)
    )
    bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV12)
    return bgr


def _make_offline_frame(message="Live Camera Feed — K1"):
    if _cv2_available:
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        cv2.putText(
            img, message,
            (160, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8, (150, 150, 150), 2
        )
        _, jpeg = cv2.imencode('.jpg', img)
        return jpeg.tobytes()
    return b''


if _ros_available:
    class CameraNode(Node):
        CAMERA_TOPIC = "/boostercamera/head/rgb"

        def __init__(self):
            super().__init__("k1_camera_stream")
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
                w, h = msg.width, msg.height

                if msg.encoding == "nv12":
                    bgr = _nv12_to_bgr(bytes(msg.data), w, h)
                elif msg.encoding in ("rgb8", "bgr8"):
                    arr = np.frombuffer(msg.data, dtype=np.uint8)
                    bgr = arr.reshape((h, w, 3))
                    if msg.encoding == "rgb8":
                        bgr = cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR)
                else:
                    # Try nv12 as fallback
                    bgr = _nv12_to_bgr(bytes(msg.data), w, h)

                # Resize for dashboard display
                bgr = cv2.resize(bgr, (640, 480))

                _, jpeg = cv2.imencode(
                    '.jpg', bgr,
                    [cv2.IMWRITE_JPEG_QUALITY, 75]
                )
                with _frame_lock:
                    _latest_frame = jpeg.tobytes()

            except Exception as e:
                self.get_logger().warn(f"Frame error: {e}")


class CameraHandler:
    def __init__(self):
        self._running = False

    def start(self) -> bool:
        if not _ros_available:
            print("[camera] ROS2 unavailable — offline placeholder active")
            return False
        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            node = CameraNode()
            t = threading.Thread(
                target=lambda: rclpy.spin(node), daemon=True
            )
            t.start()
            self._running = True
            print("[camera] K1 camera subscriber started")
            return True
        except Exception as e:
            print(f"[camera] Failed to start: {e}")
            return False

    @property
    def has_frame(self) -> bool:
        return _latest_frame is not None


def camera_stream():
    """
    MJPEG stream generator for Flask.
    Yields JPEG frames at ~30fps, or offline placeholder at 2fps.
    """
    offline = _make_offline_frame()
    while True:
        with _frame_lock:
            frame = _latest_frame
        if frame is None:
            frame = offline
            time.sleep(0.5)
        else:
            time.sleep(1 / 30)
        if frame:
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + frame +
                b'\r\n'
            )


camera_handler = CameraHandler()
