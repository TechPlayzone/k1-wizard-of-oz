import io, time, threading

_ros_available = False
_cv2_available = False
_latest_frame  = None
_frame_lock    = threading.Lock()

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from cv_bridge import CvBridge
    import cv2
    _ros_available = True
    _cv2_available = True
except ImportError:
    try:
        import cv2
        _cv2_available = True
    except ImportError:
        pass

def _make_offline_frame():
    if _cv2_available:
        import numpy as np
        img = __import__('numpy').zeros((480,640,3), dtype=__import__('numpy').uint8)
        img[:] = (30,30,30)
        cv2.putText(img,"Camera offline",(220,240),cv2.FONT_HERSHEY_SIMPLEX,0.8,(150,150,150),2)
        _, jpeg = cv2.imencode('.jpg', img)
        return jpeg.tobytes()
    return b''

if _ros_available:
    class CameraNode(Node):
        CAMERA_TOPIC = "/zed/zed_node/rgb/image_rect_color"
        def __init__(self):
            super().__init__("k1_camera_bridge")
            self._bridge = CvBridge()
            self.create_subscription(Image, self.CAMERA_TOPIC, self._on_image, 10)
        def _on_image(self, msg):
            global _latest_frame
            try:
                frame = self._bridge.imgmsg_to_cv2(msg, "bgr8")
                frame = cv2.resize(frame, (640,480))
                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY,75])
                with _frame_lock:
                    _latest_frame = jpeg.tobytes()
            except Exception:
                pass

class CameraHandler:
    def __init__(self):
        self._running = False
    def start(self):
        if not _ros_available:
            print("[camera] ROS2 unavailable — offline placeholder active")
            return False
        try:
            rclpy.init(args=None)
            node = CameraNode()
            t = threading.Thread(target=lambda: rclpy.spin(node), daemon=True)
            t.start()
            self._running = True
            print("[camera] ZED camera subscriber started")
            return True
        except Exception as e:
            print(f"[camera] Failed to start: {e}")
            return False
    @property
    def has_frame(self):
        return _latest_frame is not None

def camera_stream():
    offline = _make_offline_frame()
    while True:
        with _frame_lock:
            frame = _latest_frame
        if frame is None:
            frame = offline
            time.sleep(0.5)
        else:
            time.sleep(1/30)
        if frame:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

camera_handler = CameraHandler()
