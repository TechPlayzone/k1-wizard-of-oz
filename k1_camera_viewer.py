#!/usr/bin/env python3
# =============================================================================
# K1 Camera Viewer
# Streams K1 camera to browser via Flask MJPEG
# Run on the K1: python3 k1_camera_viewer.py
# Then open: http://<K1_IP>:8080
# =============================================================================

import threading
import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from flask import Flask, Response, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Global latest frame
latest_frame = None
frame_lock = threading.Lock()

# =============================================================================
# ROS2 Camera Subscriber
# =============================================================================

class CameraSubscriber(Node):
    def __init__(self):
        super().__init__('k1_camera_viewer')
        self.subscription = self.create_subscription(
            Image,
            '/image_left_raw',
            self.image_callback,
            10
        )
        self.get_logger().info('Camera subscriber started, listening to /image_left_raw')

    def image_callback(self, msg):
        global latest_frame
        try:
            # Convert ROS2 Image to numpy array
            img_array = np.frombuffer(msg.data, dtype=np.uint8)

            # Handle different encodings
            if msg.encoding == 'rgb8':
                img = img_array.reshape((msg.height, msg.width, 3))
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif msg.encoding == 'bgr8':
                img = img_array.reshape((msg.height, msg.width, 3))
            elif msg.encoding == 'mono8':
                img = img_array.reshape((msg.height, msg.width))
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif msg.encoding == 'yuv422' or msg.encoding == 'yuyv':
                img = img_array.reshape((msg.height, msg.width, 2))
                img = cv2.cvtColor(img, cv2.COLOR_YUV2BGR_YUYV)
            else:
                # Try raw reshape
                img = img_array.reshape((msg.height, msg.width, -1))

            with frame_lock:
                latest_frame = img

        except Exception as e:
            print(f"Frame conversion error: {e} | encoding: {msg.encoding} | shape: {msg.height}x{msg.width}")


# =============================================================================
# MJPEG Stream Generator
# =============================================================================

def generate_frames():
    while True:
        with frame_lock:
            frame = latest_frame.copy() if latest_frame is not None else None

        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )
        else:
            # Send placeholder while waiting for first frame
            import time
            time.sleep(0.1)


# =============================================================================
# Flask Routes
# =============================================================================

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>K1 Camera — AI Innovation Center</title>
    <style>
        body { background: #050c18; color: #b8e8f0; font-family: sans-serif;
               display: flex; flex-direction: column; align-items: center;
               justify-content: center; min-height: 100vh; margin: 0; }
        h1 { font-size: 1.1rem; letter-spacing: 0.1em; margin-bottom: 16px;
             color: #7dcde0; }
        img { border: 2px solid #7dcde0; border-radius: 8px;
              max-width: 95vw; box-shadow: 0 0 30px rgba(125,205,224,0.2); }
        .sub { font-size: 0.7rem; color: rgba(184,232,240,0.4);
               margin-top: 10px; letter-spacing: 0.05em; }
    </style>
</head>
<body>
    <h1>🤖 K1 CAMERA FEED — AI INNOVATION CENTER</h1>
    <img src="/stream" />
    <div class="sub">HILLSBOROUGH COLLEGE · IN PARTNERSHIP WITH URG AMERICAS · /image_left_raw · 30fps</div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/stream')
def stream():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/health')
def health():
    return {'status': 'ok', 'frame': latest_frame is not None}


# =============================================================================
# MAIN — Run ROS2 in thread, Flask in main
# =============================================================================

def ros2_thread():
    rclpy.init()
    node = CameraSubscriber()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    print("=" * 50)
    print("K1 Camera Viewer")
    print("AI Innovation Center · Hillsborough College")
    print("=" * 50)
    print("Starting ROS2 camera subscriber...")

    t = threading.Thread(target=ros2_thread, daemon=True)
    t.start()

    print("Starting Flask server on port 8080...")
    print("Open your browser: http://<K1_IP>:8080")
    print("=" * 50)

    app.run(host='0.0.0.0', port=8080, threaded=True)
