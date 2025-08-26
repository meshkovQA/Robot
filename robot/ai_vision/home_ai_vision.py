# robot/home_ai_vision.py
"""
Home AI Vision - Специализированное компьютерное зрение для домашнего робота
Оптимизировано для домашних объектов и ситуаций
"""

from __future__ import annotations
from typing import List, Dict, Optional
import time
import logging
import numpy as np
import cv2
from robot.ai_vision.ai_vision import AIVisionProcessor, DetectedObject, VisionState
import sys
from pathlib import Path

# Добавляем путь к маппингу
sys.path.insert(0, str(Path(__file__).parent.parent / "models" / "yolo"))

try:
    from robot.home_mapping import (
        HOME_OBJECT_MAPPING,
        SIMPLIFIED_NAMES,
        RUSSIAN_NAMES,
        get_home_object_name,
        is_important_for_home
    )
    MAPPING_AVAILABLE = True
except ImportError:
    MAPPING_AVAILABLE = False


logger = logging.getLogger(__name__)


class HomeAIVision(AIVisionProcessor):
    """Домашнее AI зрение, оптимизированное для дома"""

    def __init__(self, camera=None):
        super().__init__(camera)

        # Домашние настройки
        self.home_mode = True
        self.use_russian_names = True

        # Статистика домашних объектов
        self.home_object_history = {}
        self.room_context = "unknown"

        # Специальная логика для дома
        self.pet_detected = False
        self.owner_present = False

        logger.info("🏠 Домашнее AI зрение инициализировано")

    def _init_detectors(self):
        """Инициализация детекторов для домашнего использования"""
        super()._init_detectors()

        if not MAPPING_AVAILABLE:
            logger.warning(
                "Маппинг домашних объектов недоступен - используем стандартный COCO")
            self.home_mode = False

    def _detect_with_yolo(self, frame) -> List[DetectedObject]:
        """Детекция с фильтрацией домашних объектов"""
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

            home_objects = []

            for output in layer_outputs:
                for detection in output:
                    scores = detection[5:]
                    class_id = int(np.argmax(scores))
                    confidence = float(scores[class_id])

                    # Фильтруем только важные для дома объекты
                    # Снижаем порог для дома
                    if confidence > 0.4 and self._is_home_relevant(class_id):
                        center_x = int(detection[0] * width)
                        center_y = int(detection[1] * height)
                        w = int(detection[2] * width)
                        h = int(detection[3] * height)

                        x = int(center_x - w/2)
                        y = int(center_y - h/2)

                        # Получаем домашнее название объекта
                        home_name = self._get_home_object_name(class_id)

                        if home_name:
                            obj = DetectedObject(
                                class_name=home_name,
                                confidence=confidence,
                                bbox=(x, y, w, h),
                                center=(center_x, center_y),
                                area=w * h,
                                timestamp=time.time()
                            )
                            home_objects.append(obj)

                            # Обновляем домашний контекст
                            self._update_home_context(home_name, confidence)

            return home_objects

        except Exception as e:
            logger.error(f"Ошибка домашней YOLO детекции: {e}")
            return []

    def _is_home_relevant(self, coco_class_id: int) -> bool:
        """Проверяет релевантность объекта для дома"""
        if not MAPPING_AVAILABLE:
            # Без маппинга используем базовую логику
            HOME_CLASSES = [0, 15, 16, 39, 41, 46, 56, 57,
                            58, 59, 60, 61, 62, 63, 67, 72, 73, 74]
            return coco_class_id in HOME_CLASSES

        return is_important_for_home(coco_class_id)

    def _get_home_object_name(self, coco_class_id: int) -> Optional[str]:
        """Получает домашнее название объекта"""
        if not MAPPING_AVAILABLE:
            # Базовая логика без маппинга
            basic_mapping = {
                0: "person", 15: "cat", 16: "dog", 39: "bottle",
                41: "cup", 46: "bowl", 56: "chair", 57: "sofa",
                59: "bed", 62: "tv", 63: "laptop", 67: "phone"
            }
            return basic_mapping.get(coco_class_id)

        return get_home_object_name(coco_class_id, "")

    def _update_home_context(self, object_name: str, confidence: float):
        """Обновляет контекст домашней обстановки"""
        # Отслеживаем животных
        if object_name in ["cat", "dog"]:
            self.pet_detected = True

        # Отслеживаем присутствие человека
        if object_name == "person" and confidence > 0.7:
            self.owner_present = True

        # Определяем комнату по объектам
        room_indicators = {
            "kitchen": ["microwave", "fridge", "sink", "oven", "toaster"],
            "bedroom": ["bed"],
            "living_room": ["sofa", "tv", "remote"],
            "bathroom": ["toilet", "sink"],
            "office": ["laptop", "keyboard", "mouse"]
        }

        for room, indicators in room_indicators.items():
            if object_name in indicators:
                self.room_context = room
                break

        # Сохраняем историю объектов
        if object_name not in self.home_object_history:
            self.home_object_history[object_name] = []
        self.home_object_history[object_name].append({
            "timestamp": time.time(),
            "confidence": confidence
        })

        # Ограничиваем историю последними 100 записями
        if len(self.home_object_history[object_name]) > 100:
            self.home_object_history[object_name] = self.home_object_history[object_name][-100:]

    def _generate_scene_description(self) -> str:
        """Генерирует описание домашней сцены"""
        description_parts = []

        # Используем русские названия если включено
        name_map = RUSSIAN_NAMES if (
            self.use_russian_names and MAPPING_AVAILABLE) else {}

        # Люди (высший приоритет)
        people_count = len([f for f in self.state.faces])
        if people_count > 0:
            if self.use_russian_names:
                if people_count == 1:
                    description_parts.append("человек")
                else:
                    description_parts.append(f"{people_count} человека")
            else:
                description_parts.append(
                    f"{people_count} person{'s' if people_count > 1 else ''}")

        # Домашние животные
        pets = [obj for obj in self.state.objects if obj.class_name in ["cat", "dog"]]
        if pets:
            for pet in pets:
                pet_name = name_map.get(pet.class_name, pet.class_name)
                description_parts.append(pet_name)

        # Мебель и важные объекты
        important_objects = [obj for obj in self.state.objects
                             if obj.class_name not in ["cat", "dog", "person"]
                             and obj.confidence > 0.6]

        if important_objects:
            object_counts = {}
            for obj in important_objects:
                display_name = name_map.get(obj.class_name, obj.class_name)
                object_counts[display_name] = object_counts.get(
                    display_name, 0) + 1

            for obj_name, count in object_counts.items():
                if count == 1:
                    description_parts.append(obj_name)
                else:
                    description_parts.append(f"{count} {obj_name}")

        # Контекст комнаты
        room_prefix = ""
        if self.room_context != "unknown":
            room_names = {
                "kitchen": "кухня",
                "bedroom": "спальня",
                "living_room": "гостиная",
                "bathroom": "ванная",
                "office": "кабинет"
            }
            if self.use_russian_names and self.room_context in room_names:
                room_prefix = f"[{room_names[self.room_context]}] "
            else:
                room_prefix = f"[{self.room_context}] "

        # Движение
        if self.state.motion_detected:
            motion_text = "движение" if self.use_russian_names else "movement"
            description_parts.append(motion_text)

        if not description_parts:
            empty_text = "пустая комната" if self.use_russian_names else "empty room"
            return room_prefix + empty_text

        see_text = "Вижу: " if self.use_russian_names else "I see: "
        return room_prefix + see_text + ", ".join(description_parts)

    # ==================== ДОМАШНИЕ СПЕЦИАЛЬНЫЕ МЕТОДЫ ====================

    def is_pet_present(self) -> bool:
        """Проверка наличия домашних животных"""
        with self._lock:
            pets = [
                obj for obj in self.state.objects if obj.class_name in ["cat", "dog"]]
            return len(pets) > 0

    def get_pets_info(self) -> List[Dict]:
        """Информация о домашних животных"""
        with self._lock:
            pets_info = []
            for obj in self.state.objects:
                if obj.class_name in ["cat", "dog"]:
                    pet_info = {
                        "type": obj.class_name,
                        "confidence": obj.confidence,
                        "position": obj.center,
                        "size": "large" if obj.area > 5000 else "medium" if obj.area > 1000 else "small"
                    }
                    pets_info.append(pet_info)
            return pets_info

    def is_person_sitting(self) -> bool:
        """Определение сидит ли человек (по наличию стула/дивана рядом)"""
        with self._lock:
            people = [
                obj for obj in self.state.objects if obj.class_name == "person"]
            furniture = [
                obj for obj in self.state.objects if obj.class_name in ["chair", "sofa"]]

            for person in people:
                for chair in furniture:
                    # Проверяем близость человека к мебели
                    distance = ((person.center[0] - chair.center[0]) ** 2 +
                                (person.center[1] - chair.center[1]) ** 2) ** 0.5
                    if distance < 100:  # Человек рядом с мебелью
                        return True
            return False

    def get_room_context(self) -> str:
        """Получить текущий контекст комнаты"""
        return self.room_context

    def get_home_objects_stats(self) -> Dict:
        """Статистика домашних объектов"""
        stats = {}
        current_time = time.time()

        for obj_name, history in self.home_object_history.items():
            # Фильтруем последние 5 минут
            recent_detections = [
                h for h in history
                if current_time - h["timestamp"] < 300  # 5 минут
            ]

            if recent_detections:
                avg_confidence = sum(
                    h["confidence"] for h in recent_detections) / len(recent_detections)
                stats[obj_name] = {
                    "detections_count": len(recent_detections),
                    "avg_confidence": round(avg_confidence, 2),
                    "last_seen": max(h["timestamp"] for h in recent_detections)
                }

        return stats

    def is_safe_for_movement(self) -> Dict[str, bool]:
        """Проверка безопасности движения с учетом домашней обстановки"""
        safety = {
            "pets_clear": not self.is_pet_present(),
            "person_not_in_path": not self.is_person_in_front(),
            "furniture_clear": True,  # Базовая логика
            "overall_safe": True
        }

        # Проверяем мебель на пути
        furniture_ahead = []
        for obj in self.state.objects:
            # Центральная зона
            if obj.class_name in ["chair", "table"] and obj.center[0] > 200 and obj.center[0] < 440:
                furniture_ahead.append(obj)

        safety["furniture_clear"] = len(furniture_ahead) == 0

        # Общая безопасность
        safety["overall_safe"] = all([
            safety["pets_clear"],
            safety["person_not_in_path"],
            safety["furniture_clear"]
        ])

        return safety

    def get_navigation_hints(self) -> List[str]:
        """Подсказки для навигации в доме"""
        hints = []

        # Подсказки по домашним животным
        if self.is_pet_present():
            pets = self.get_pets_info()
            for pet in pets:
                if pet["type"] == "cat":
                    hints.append(
                        "Осторожно: кот в зоне видимости - двигайтесь медленно")
                elif pet["type"] == "dog":
                    hints.append(
                        "Внимание: собака рядом - возможна реакция на движение")

        # Подсказки по комнате
        if self.room_context == "kitchen":
            hints.append(
                "Кухня: осторожно с техникой и возможными жидкостями на полу")
        elif self.room_context == "bedroom":
            hints.append("Спальня: двигайтесь тихо, возможно кто-то спит")
        elif self.room_context == "living_room":
            hints.append(
                "Гостиная: много мебели - планируйте маршрут осторожно")

        # Подсказки по людям
        if self.owner_present:
            if self.is_person_sitting():
                hints.append("Человек сидит - можно двигаться, но не мешайте")
            else:
                hints.append("Человек стоит - дождитесь освобождения прохода")

        return hints
