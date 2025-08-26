# robot/ai_integration.py
"""
AI Integration - Интеграция AI с существующей системой робота
"""

from __future__ import annotations
import logging
from typing import Optional
import time

from robot.ai_vision.ai_vision import AIVisionProcessor
from robot.controller import RobotController
from robot.devices.camera import USBCamera

logger = logging.getLogger(__name__)


class AIRobotController:
    """Расширенный контроллер робота с AI возможностями"""

    def __init__(self, robot: RobotController, camera: Optional[USBCamera] = None):
        self.robot = robot
        self.camera = camera
        self.ai_vision: Optional[AIVisionProcessor] = None

        # AI режимы
        self.follow_person_mode = False
        self.auto_avoid_people = True
        self.smart_navigation = False

        # Настройки поведения
        self.person_follow_distance = 100  # пикселей от центра кадра
        self.person_too_close_threshold = 200  # площадь bbox

        self._init_ai_vision()
        self._setup_ai_callbacks()

    def _init_ai_vision(self):
        """Инициализация AI зрения"""
        if not self.camera:
            logger.warning("Камера не доступна - AI функции ограничены")
            return

        try:
            self.ai_vision = AIVisionProcessor(self.camera)
            logger.info("✅ AI Vision инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации AI Vision: {e}")

    def _setup_ai_callbacks(self):
        """Настройка колбэков для AI событий"""
        if not self.ai_vision:
            return

        # Колбэк при обнаружении человека
        self.ai_vision.add_callback(
            'person_detected', self._on_person_detected)

        # Колбэк при обнаружении движения
        self.ai_vision.add_callback(
            'motion_detected', self._on_motion_detected)

        # Колбэк при обнаружении лица
        self.ai_vision.add_callback('face_detected', self._on_face_detected)

    def start_ai(self) -> bool:
        """Запуск AI обработки"""
        if not self.ai_vision:
            logger.warning("AI Vision не инициализирован")
            return False

        success = self.ai_vision.start_processing()
        if success:
            logger.info("🧠 AI системы запущены")
        return success

    def stop_ai(self):
        """Остановка AI обработки"""
        if self.ai_vision:
            self.ai_vision.stop_processing()
            logger.info("🛑 AI системы остановлены")

    # ==================== AI КОЛБЭКИ ====================

    def _on_person_detected(self, people, frame):
        """Обработка обнаружения человека"""
        try:
            if not people:
                return

            logger.debug(f"👤 Обнаружено людей: {len(people)}")

            # Режим следования за человеком
            if self.follow_person_mode:
                self._follow_person_logic(people)

            # Автоматическое избежание людей при движении
            if self.auto_avoid_people and self.robot.is_moving:
                self._avoid_people_logic(people)

        except Exception as e:
            logger.error(f"Ошибка в колбэке person_detected: {e}")

    def _on_motion_detected(self, frame):
        """Обработка обнаружения движения"""
        logger.debug("🏃 Обнаружено движение в кадре")
        # Здесь можно добавить реакцию на движение

    def _on_face_detected(self, faces, frame):
        """Обработка обнаружения лица"""
        logger.debug(f"😊 Обнаружено лиц: {len(faces)}")
        # Здесь можно добавить социальные взаимодействия

    # ==================== УМНЫЕ РЕЖИМЫ ДВИЖЕНИЯ ====================

    def _follow_person_logic(self, people):
        """Логика следования за человеком"""
        if not people:
            return

        # Находим ближайшего человека
        closest_person = max(people, key=lambda p: p.area)

        center_x = closest_person.center[0]
        frame_center = 320  # Предполагаем камеру 640px ширины

        # Вычисляем отклонение от центра
        deviation = center_x - frame_center

        # Пороги для поворотов
        turn_threshold = 80

        # Слишком близко - отодвигаемся
        if closest_person.area > self.person_too_close_threshold:
            logger.info("👤 Человек слишком близко, отодвигаюсь")
            self.robot.move_backward(80)
            time.sleep(0.5)
            self.robot.stop()

        # Поворачиваем к человеку
        elif abs(deviation) > turn_threshold:
            if deviation > 0:  # Человек справа
                logger.info("👤 Поворачиваю к человеку (вправо)")
                self.robot.tank_turn_right(100)
            else:  # Человек слева
                logger.info("👤 Поворачиваю к человеку (влево)")
                self.robot.tank_turn_left(100)
            time.sleep(0.3)
            self.robot.stop()

        # Двигаемся вперед к человеку
        elif closest_person.area < 150:  # Человек далеко
            logger.info("👤 Приближаюсь к человеку")
            self.robot.move_forward(70)
            time.sleep(0.5)
            self.robot.stop()

    def _avoid_people_logic(self, people):
        """Логика избежания людей"""
        if not people:
            return

        # Проверяем есть ли люди впереди по ходу движения
        people_ahead = []
        frame_center = 320
        frame_width = 200  # Зона впереди

        for person in people:
            center_x = person.center[0]
            if abs(center_x - frame_center) < frame_width:
                people_ahead.append(person)

        if people_ahead:
            logger.warning("👤 Человек впереди! Экстренная остановка")
            self.robot.stop()

            # Ждем пока человек не уйдет
            time.sleep(2)

 # ==================== ПУБЛИЧНЫЕ AI МЕТОДЫ ====================

    def enable_follow_person_mode(self, enable: bool = True):
        """Включить/выключить режим следования за человеком"""
        self.follow_person_mode = enable
        status = "включен" if enable else "выключен"
        logger.info(f"👤 Режим следования за человеком {status}")

    def enable_auto_avoid_people(self, enable: bool = True):
        """Включить/выключить автоматическое избежание людей"""
        self.auto_avoid_people = enable
        status = "включен" if enable else "выключен"
        logger.info(f"🚶 Автоматическое избежание людей {status}")

    def enable_smart_navigation(self, enable: bool = True):
        """Включить/выключить умную навигацию"""
        self.smart_navigation = enable
        status = "включен" if enable else "выключен"
        logger.info(f"🧠 Умная навигация {status}")

    def get_ai_status(self) -> dict:
        """Получить статус AI систем"""
        status = {
            "ai_vision_active": self.ai_vision is not None and hasattr(self.ai_vision, '_processing_thread') and self.ai_vision._processing_thread and self.ai_vision._processing_thread.is_alive(),
            "follow_person_mode": self.follow_person_mode,
            "auto_avoid_people": self.auto_avoid_people,
            "smart_navigation": self.smart_navigation,
        }

        if self.ai_vision:
            vision_state = self.ai_vision.get_state()
            status.update({
                "detected_objects": len(vision_state.objects),
                "detected_faces": len(vision_state.faces),
                "motion_detected": vision_state.motion_detected,
                "scene_description": vision_state.scene_description,
                "processing_fps": vision_state.processing_fps,
                "person_in_front": self.ai_vision.is_person_in_front(),
                "object_counts": self.ai_vision.count_detected_objects()
            })

        return status

    def get_scene_description(self) -> str:
        """Получить описание текущей сцены"""
        if not self.ai_vision:
            return "AI зрение недоступно"

        vision_state = self.ai_vision.get_state()
        return vision_state.scene_description

    def is_safe_to_move_forward(self) -> bool:
        """Проверка безопасности движения вперед с учетом AI"""
        # Базовая проверка датчиков
        robot_status = self.robot.get_status()
        if robot_status['obstacles']['front']:
            return False

        # AI проверка на людей впереди
        if self.auto_avoid_people and self.ai_vision:
            if self.ai_vision.is_person_in_front():
                logger.warning("👤 Человек впереди - движение заблокировано AI")
                return False

        return True

    def smart_move_forward(self, speed: int) -> bool:
        """Умное движение вперед с AI проверками"""
        if not self.is_safe_to_move_forward():
            logger.warning("🚫 AI блокирует движение вперед")
            return False

        return self.robot.move_forward(speed)

    def smart_navigate_to_target(self, description: str):
        """Навигация к цели по описанию (будущая функция)"""
        logger.info(f"🎯 Попытка навигации к: {description}")
        # Здесь будет логика поиска объектов и планирования пути
        # Пока что заглушка
        pass

    # ==================== ИНТЕГРАЦИЯ С СУЩЕСТВУЮЩИМ API ====================

    def get_extended_status(self) -> dict:
        """Расширенный статус робота с AI данными"""
        base_status = self.robot.get_status()
        ai_status = self.get_ai_status()

        # Объединяем статусы
        extended_status = {**base_status}
        extended_status['ai'] = ai_status

        return extended_status
