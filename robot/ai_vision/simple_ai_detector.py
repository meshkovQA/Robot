# robot/ai_vision/simple_ai_detector.py
"""
Упрощённая AI детекция объектов - только объекты на видео
"""

import cv2
import numpy as np
import logging
from typing import List, Tuple, Dict
from ultralytics import YOLO
import time

logger = logging.getLogger(__name__)


class SimpleAIDetector:
    """Простая AI детекция объектов"""

    def __init__(self):
        self.model = None
        self.confidence_threshold = 0.5
        self._load_model()

    def _load_model(self):
        """Загрузка AI модели"""
        try:
            model_path = "models/yolo/yolov8n.pt"
            self.model = YOLO(model_path)
            logger.info("✅ AI детекция модель загружена")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки AI модели: {e}")
            self.model = None

    def detect_objects(self, frame: np.ndarray) -> List[Dict]:
        """Детекция объектов на кадре"""
        if self.model is None:
            return []

        try:
            results = self.model(
                frame, conf=self.confidence_threshold, verbose=False)

            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = float(box.conf[0])
                        class_id = int(box.cls[0])
                        class_name = self.model.names[class_id]

                        detection = {
                            'class_name': class_name,
                            'confidence': confidence,
                            'bbox': (int(x1), int(y1), int(x2-x1), int(y2-y1)),
                            'center': (int((x1+x2)/2), int((y1+y2)/2)),
                            'timestamp': time.time()
                        }
                        detections.append(detection)

            return detections

        except Exception as e:
            logger.error(f"❌ Ошибка AI детекции: {e}")
            return []

    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """Отрисовка детекций на кадре"""
        for det in detections:
            x, y, w, h = det['bbox']
            confidence = det['confidence']
            class_name = det['class_name']

            # Рамка
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Подпись
            label = f"{class_name}: {confidence:.2f}"
            cv2.putText(frame, label, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return frame
