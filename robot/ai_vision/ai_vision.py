# robot/ai_vision.py
"""
AI Vision Module - Базовое компьютерное зрение для робота
Этап 1: Детекция объектов, лиц, движения
"""

from __future__ import annotations
import cv2
import numpy as np
import threading
import time
import logging
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DetectedObject:
    """Обнаруженный объект"""
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    center: Tuple[int, int]
    area: float
    timestamp: float


@dataclass
class VisionState:
    """Состояние системы компьютерного зрения"""
    objects: List[DetectedObject]
    faces: List[Dict]
    motion_detected: bool
    scene_description: str
    processing_fps: float
    last_update: float


class AIVisionProcessor:
    """Основной класс для обработки компьютерного зрения"""

    def __init__(self, camera=None):
        self.camera = camera
        self.state = VisionState(
            objects=[],
            faces=[],
            motion_detected=False,
            scene_description="",
            processing_fps=0.0,
            last_update=0.0
        )

        # Инициализация детекторов
        self._init_detectors()

        # Потоки обработки
        self._processing_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

        # Колбэки для событий
        self._callbacks: Dict[str, List[Callable]] = {
            'object_detected': [],
            'face_detected': [],
            'motion_detected': [],
            'person_detected': []
        }

        # Буферы для анализа движения
        self._motion_history = []
        self._background_subtractor = cv2.createBackgroundSubtractorMOG2(
            detectShadows=True)

        # Статистика FPS
        self._frame_times = []

    def _init_detectors(self):
        """Инициализация детекторов"""
        logger.info("🧠 Инициализация AI детекторов...")

        try:
            # Детектор лиц Haar Cascade
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            logger.info("✅ Haar Cascade детектор лиц загружен")

            # Детектор тела
            body_cascade_path = cv2.data.haarcascades + 'haarcascade_fullbody.xml'
            self.body_cascade = cv2.CascadeClassifier(body_cascade_path)
            logger.info("✅ Haar Cascade детектор тела загружен")

        except Exception as e:
            logger.error(f"Ошибка инициализации Haar детекторов: {e}")
            self.face_cascade = None
            self.body_cascade = None

        # Пытаемся загрузить YOLO (опционально)
        self._init_yolo()

        # Инициализация дополнительных детекторов
        self._init_advanced_detectors()

    def _init_yolo(self):
        """Инициализация YOLO детектора"""
        self.yolo_net = None
        self.yolo_classes = []

        try:
            # Пути к файлам YOLO (создадим скрипт загрузки)
            weights_path = "models/yolo/yolov4-tiny.weights"
            config_path = "models/yolo/yolov4-tiny.cfg"
            names_path = "models/yolo/coco.names"

            if Path(weights_path).exists() and Path(config_path).exists():
                self.yolo_net = cv2.dnn.readNet(weights_path, config_path)

                if Path(names_path).exists():
                    with open(names_path, 'r') as f:
                        self.yolo_classes = [line.strip()
                                             for line in f.readlines()]

                logger.info(
                    f"✅ YOLO загружен с {len(self.yolo_classes)} классами")
            else:
                logger.info(
                    "⚠️ YOLO файлы не найдены, используем только Haar детекторы")

        except Exception as e:
            logger.error(f"Ошибка загрузки YOLO: {e}")

    def _init_advanced_detectors(self):
        """Инициализация продвинутых детекторов"""
        # Детектор углов/особенностей для навигации
        self.corner_detector = cv2.goodFeaturesToTrack

        # Детектор контуров
        self.contour_detector = cv2.findContours

        # Оптический поток для отслеживания движения
        self.optical_flow = cv2.calcOpticalFlowPyrLK

        logger.info("✅ Дополнительные детекторы инициализированы")

    def start_processing(self) -> bool:
        """Запуск обработки в отдельном потоке"""
        if self._processing_thread and self._processing_thread.is_alive():
            logger.warning("Обработка уже запущена")
            return True

        if not self.camera:
            logger.error("Камера не инициализирована")
            return False

        self._stop_event.clear()
        self._processing_thread = threading.Thread(
            target=self._processing_loop, daemon=True)
        self._processing_thread.start()

        logger.info("🚀 AI Vision обработка запущена")
        return True

    def stop_processing(self):
        """Остановка обработки"""
        self._stop_event.set()
        if self._processing_thread:
            self._processing_thread.join(timeout=3.0)
        logger.info("⏹️ AI Vision обработка остановлена")

    def _processing_loop(self):
        """Основной цикл обработки"""
        logger.info("🔄 Запущен цикл AI обработки")

        while not self._stop_event.is_set():
            start_time = time.time()

            try:
                # Получаем кадр от камеры
                frame = self._get_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue

                # Обрабатываем кадр
                self._process_frame(frame)

                # Статистика FPS
                self._update_fps_stats(start_time)

                # Ограничиваем FPS обработки
                time.sleep(max(0, 1/10 - (time.time() - start_time)))  # 10 FPS

            except Exception as e:
                logger.error(f"Ошибка в цикле обработки: {e}")
                time.sleep(1.0)

        logger.info("🔚 Цикл AI обработки завершен")

    def _get_frame(self):
        """Получение кадра от камеры"""
        if not self.camera or not hasattr(self.camera, '_current_frame'):
            return None

        with self.camera._frame_lock:
            if self.camera._current_frame is not None:
                return self.camera._current_frame.copy()
        return None

    def _process_frame(self, frame):
        """Обработка одного кадра"""
        with self._lock:
            # Сброс состояния
            self.state.objects = []
            self.state.faces = []
            self.state.motion_detected = False

            # Детекция лиц
            faces = self._detect_faces(frame)
            self.state.faces = faces

            # Детекция объектов
            objects = self._detect_objects(frame)
            self.state.objects = objects

            # Детекция движения
            motion = self._detect_motion(frame)
            self.state.motion_detected = motion

            # Генерация описания сцены
            self.state.scene_description = self._generate_scene_description()

            self.state.last_update = time.time()

            # Вызов колбэков
            self._trigger_callbacks(frame)

    def _detect_faces(self, frame) -> List[Dict]:
        """Детекция лиц"""
        if not self.face_cascade:
            return []

        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )

            detected_faces = []
            for (x, y, w, h) in faces:
                face = {
                    'bbox': (x, y, w, h),
                    'center': (x + w//2, y + h//2),
                    'area': w * h,
                    'confidence': 0.8,  # Haar не дает точную уверенность
                    'timestamp': time.time()
                }
                detected_faces.append(face)

            if detected_faces:
                logger.debug(f"👤 Обнаружено лиц: {len(detected_faces)}")

            return detected_faces

        except Exception as e:
            logger.error(f"Ошибка детекции лиц: {e}")
            return []

    def _detect_objects(self, frame) -> List[DetectedObject]:
        """Детекция объектов"""
        detected_objects = []

        # YOLO детекция (если доступно)
        if self.yolo_net is not None:
            yolo_objects = self._detect_with_yolo(frame)
            detected_objects.extend(yolo_objects)

        # Детекция людей через Haar Cascade
        if self.body_cascade:
            people = self._detect_people_haar(frame)
            detected_objects.extend(people)

        return detected_objects

    def _detect_with_yolo(self, frame) -> List[DetectedObject]:
        """Детекция с помощью YOLO"""
        if not self.yolo_net:
            return []

        try:
            height, width = frame.shape[:2]

            # Подготовка блоба для YOLO
            blob = cv2.dnn.blobFromImage(
                frame, 1/255.0, (416, 416),
                swapRB=True, crop=False
            )
            self.yolo_net.setInput(blob)

            # Получение детекций
            layer_outputs = self.yolo_net.forward(
                self.yolo_net.getUnconnectedOutLayersNames()
            )

            objects = []
            for output in layer_outputs:
                for detection in output:
                    scores = detection[5:]
                    class_id = np.argmax(scores)
                    confidence = scores[class_id]

                    if confidence > 0.5:  # Порог уверенности
                        center_x = int(detection[0] * width)
                        center_y = int(detection[1] * height)
                        w = int(detection[2] * width)
                        h = int(detection[3] * height)

                        x = int(center_x - w/2)
                        y = int(center_y - h/2)

                        obj = DetectedObject(
                            class_name=self.yolo_classes[class_id] if class_id < len(
                                self.yolo_classes) else f"class_{class_id}",
                            confidence=float(confidence),
                            bbox=(x, y, w, h),
                            center=(center_x, center_y),
                            area=w * h,
                            timestamp=time.time()
                        )
                        objects.append(obj)

            return objects

        except Exception as e:
            logger.error(f"Ошибка YOLO детекции: {e}")
            return []

    def _detect_people_haar(self, frame) -> List[DetectedObject]:
        """Детекция людей через Haar Cascade"""
        if not self.body_cascade:
            return []

        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            people = self.body_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=3,
                minSize=(50, 100)
            )

            detected_people = []
            for (x, y, w, h) in people:
                person = DetectedObject(
                    class_name="person",
                    confidence=0.7,
                    bbox=(x, y, w, h),
                    center=(x + w//2, y + h//2),
                    area=w * h,
                    timestamp=time.time()
                )
                detected_people.append(person)

            return detected_people

        except Exception as e:
            logger.error(f"Ошибка детекции людей: {e}")
            return []

    def _detect_motion(self, frame) -> bool:
        """Детекция движения"""
        try:
            # Применяем Background Subtractor
            fg_mask = self._background_subtractor.apply(frame)

            # Убираем шум
            kernel = np.ones((5, 5), np.uint8)
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

            # Подсчитываем пиксели переднего плана
            motion_pixels = cv2.countNonZero(fg_mask)
            total_pixels = frame.shape[0] * frame.shape[1]
            motion_ratio = motion_pixels / total_pixels

            # Порог для детекции движения
            motion_detected = motion_ratio > 0.01  # 1% кадра

            if motion_detected:
                logger.debug(f"🏃 Обнаружено движение: {motion_ratio:.3f}")

            return motion_detected

        except Exception as e:
            logger.error(f"Ошибка детекции движения: {e}")
            return False

    def _generate_scene_description(self) -> str:
        """Генерация текстового описания сцены"""
        description_parts = []

        # Количество лиц
        if self.state.faces:
            face_count = len(self.state.faces)
            if face_count == 1:
                description_parts.append("человек")
            else:
                description_parts.append(f"{face_count} человека")

        # Объекты
        if self.state.objects:
            object_names = [obj.class_name for obj in self.state.objects]
            unique_objects = {}
            for name in object_names:
                unique_objects[name] = unique_objects.get(name, 0) + 1

            for obj_name, count in unique_objects.items():
                if count == 1:
                    description_parts.append(obj_name)
                else:
                    description_parts.append(f"{count} {obj_name}")

        # Движение
        if self.state.motion_detected:
            description_parts.append("движение")

        if not description_parts:
            return "пустая сцена"

        return "Вижу: " + ", ".join(description_parts)

    def _update_fps_stats(self, start_time):
        """Обновление статистики FPS"""
        processing_time = time.time() - start_time
        self._frame_times.append(processing_time)

        if len(self._frame_times) > 30:
            self._frame_times.pop(0)

        if len(self._frame_times) > 1:
            avg_time = sum(self._frame_times) / len(self._frame_times)
            self.state.processing_fps = 1.0 / max(avg_time, 0.001)

    def _trigger_callbacks(self, frame):
        """Вызов зарегистрированных колбэков"""
        try:
            # Колбэки для лиц
            if self.state.faces and 'face_detected' in self._callbacks:
                for callback in self._callbacks['face_detected']:
                    callback(self.state.faces, frame)

            # Колбэки для объектов
            if self.state.objects:
                for callback in self._callbacks.get('object_detected', []):
                    callback(self.state.objects, frame)

                # Специфичные колбэки для людей
                people = [
                    obj for obj in self.state.objects if obj.class_name == 'person']
                if people:
                    for callback in self._callbacks.get('person_detected', []):
                        callback(people, frame)

            # Колбэки для движения
            if self.state.motion_detected:
                for callback in self._callbacks.get('motion_detected', []):
                    callback(frame)

        except Exception as e:
            logger.error(f"Ошибка в колбэках: {e}")

    def add_callback(self, event_type: str, callback: Callable):
        """Добавление колбэка для события"""
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        self._callbacks[event_type].append(callback)
        logger.info(f"➕ Добавлен колбэк для события: {event_type}")

    def remove_callback(self, event_type: str, callback: Callable):
        """Удаление колбэка"""
        if event_type in self._callbacks and callback in self._callbacks[event_type]:
            self._callbacks[event_type].remove(callback)
            logger.info(f"➖ Удален колбэк для события: {event_type}")

    def get_annotated_frame(self, frame) -> np.ndarray:
        """Получение кадра с аннотациями"""
        annotated = frame.copy()

        with self._lock:
            # Рисуем лица
            for face in self.state.faces:
                x, y, w, h = face['bbox']
                cv2.rectangle(annotated, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(annotated, 'Face', (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # Рисуем объекты
            for obj in self.state.objects:
                x, y, w, h = obj.bbox
                cv2.rectangle(annotated, (x, y), (x+w, y+h), (255, 0, 0), 2)
                label = f"{obj.class_name}: {obj.confidence:.2f}"
                cv2.putText(annotated, label, (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

            # Индикатор движения
            if self.state.motion_detected:
                cv2.putText(annotated, 'MOTION DETECTED', (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            # Описание сцены
            cv2.putText(annotated, self.state.scene_description, (10, annotated.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        return annotated

    def get_state(self) -> VisionState:
        """Получение текущего состояния"""
        with self._lock:
            return self.state

    # Специальные методы для робота
    def is_person_in_front(self) -> bool:
        """Проверка наличия человека впереди"""
        with self._lock:
            for obj in self.state.objects:
                if obj.class_name == 'person':
                    # Проверяем что человек в центральной части кадра
                    center_x = obj.center[0]
                    frame_center = 320  # предполагаем 640px ширину
                    if abs(center_x - frame_center) < 100:  # в пределах 100px от центра
                        return True
            return False

    def get_closest_person(self) -> Optional[DetectedObject]:
        """Получение ближайшего человека (по размеру области)"""
        with self._lock:
            people = [
                obj for obj in self.state.objects if obj.class_name == 'person']
            if not people:
                return None
            return max(people, key=lambda p: p.area)

    def count_detected_objects(self) -> Dict[str, int]:
        """Подсчет обнаруженных объектов по типам"""
        with self._lock:
            counts = {}
            for obj in self.state.objects:
                counts[obj.class_name] = counts.get(obj.class_name, 0) + 1
            return counts
