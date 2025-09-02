# robot/ai_vision/ai_runtime.py
import time
import threading
import base64
import numpy as np
import cv2


class AIVisionRuntime:
    def __init__(self, ai_detector, camera, target_fps=10):
        self.detector = ai_detector
        self.camera = camera
        self.target_fps = target_fps
        self.last_detections = []
        self.last_ts = 0.0
        self.ai_fps = 0.0
        self._stop = False
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        self.last_frame_bgr = None

    def stop(self):
        self._stop = True
        self._thr.join(timeout=1)

    def _loop(self):
        prev = time.time()
        while not self._stop:
            try:
                jpeg = self.camera.get_frame_jpeg() if self.camera else None
                if not jpeg:
                    time.sleep(0.05)
                    continue
                frame = cv2.imdecode(np.frombuffer(
                    jpeg, np.uint8), cv2.IMREAD_COLOR)
                self.last_frame_bgr = frame
                if frame is None:
                    time.sleep(0.01)
                    continue

                dets = self.detector.detect_objects(frame)
                self.last_detections = dets
                self.last_ts = time.time()
                now = self.last_ts
                dt = now - prev
                if dt > 0:
                    self.ai_fps = 1.0 / dt
                prev = now

                # удерживаем целевой fps (насколько возможно)
                budget = 1.0 / self.target_fps
                extra = budget - (time.time() - now)
                if extra > 0:
                    time.sleep(extra)
            except Exception:
                time.sleep(0.1)
