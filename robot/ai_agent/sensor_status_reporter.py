# robot/ai_agent/sensor_status_reporter.py
"""
Модуль для генерации текстовых отчетов о состоянии датчиков
для голосового воспроизведения через TTS
Работает с уже полученными данными из robot.get_status()
"""

import logging
from typing import Optional

from robot.config import SENSOR_ERR

logger = logging.getLogger(__name__)


class SensorStatusReporter:
    """
    Компонент для генерации текстовых отчетов о состоянии датчиков
    Принимает готовые данные статуса, не делает дополнительных запросов
    """

    def __init__(self):
        """Инициализация без зависимостей - работает с переданными данными"""
        pass

    def get_distance_sensors_text(self, status: dict) -> str:
        """Генерирует текстовое описание датчиков расстояния"""
        distance_sensors = status.get("distance_sensors", {})

        if not distance_sensors:
            return "Датчики расстояния недоступны"

        report_parts = []
        sensor_names_ru = {
            "left_front": "левый передний",
            "right_front": "правый передний",
            "front_center": "центральный передний",
            "left_rear": "левый задний",
            "rear_right": "правый задний"
        }

        # Проверяем каждый датчик
        for sensor_name, distance in distance_sensors.items():
            sensor_name_ru = sensor_names_ru.get(sensor_name, sensor_name)

            if distance == SENSOR_ERR:
                report_parts.append(f"{sensor_name_ru} датчик не отвечает")
            elif distance < 10:
                report_parts.append(
                    f"{sensor_name_ru} датчик показывает критическое расстояние {distance} сантиметров")
            elif distance < 30:
                report_parts.append(
                    f"{sensor_name_ru} датчик показывает близкое препятствие {distance} сантиметров")
            elif distance < 100:
                report_parts.append(
                    f"{sensor_name_ru} датчик показывает {distance} сантиметров до препятствия")

        if not report_parts:
            return "Все датчики расстояния работают нормально, препятствий не обнаружено"

        return ". ".join(report_parts)

    def get_environment_text(self, status: dict) -> str:
        """Генерирует текстовое описание климатических данных"""
        environment = status.get("environment", {})
        temp = environment.get("temperature")
        humidity = environment.get("humidity")

        report_parts = []

        # Температура
        if temp is not None:
            if temp < 0:
                report_parts.append(
                    f"температура {temp:.1f} градусов ниже нуля")
            elif temp > 30:
                report_parts.append(f"температура высокая {temp:.1f} градусов")
            else:
                report_parts.append(f"температура {temp:.1f} градусов")
        else:
            report_parts.append("датчик температуры не отвечает")

        # Влажность
        if humidity is not None:
            if humidity > 80:
                report_parts.append(
                    f"влажность высокая {humidity:.0f} процентов")
            elif humidity < 30:
                report_parts.append(
                    f"влажность низкая {humidity:.0f} процентов")
            else:
                report_parts.append(f"влажность {humidity:.0f} процентов")
        else:
            report_parts.append("датчик влажности не отвечает")

        return ", ".join(report_parts)

    def get_motion_text(self, status: dict) -> str:
        """Генерирует текстовое описание состояния движения"""
        motion = status.get("motion", {})
        encoders = status.get("encoders", {})

        is_moving = motion.get("is_moving", False)
        direction = motion.get("direction", 0)
        current_speed = motion.get("current_speed", 0)

        if not is_moving:
            return "Робот неподвижен"

        # Направление движения
        direction_names = {
            1: "вперед",
            2: "назад",
            3: "поворот влево",
            4: "поворот вправо"
        }
        direction_text = direction_names.get(
            direction, "неизвестное направление")

        # Данные энкодеров если есть
        speed_info = ""
        if encoders:
            left_speed = encoders.get("left_wheel_speed", 0)
            right_speed = encoders.get("right_wheel_speed", 0)

            if abs(left_speed) > 0.01 or abs(right_speed) > 0.01:
                avg_speed = (abs(left_speed) + abs(right_speed)) / 2
                speed_info = f", средняя скорость {avg_speed:.2f} метра в секунду"

        return f"Робот движется {direction_text} со скоростью {current_speed}{speed_info}"

    def get_camera_text(self, status: dict) -> str:
        """Генерирует текстовое описание положения камеры"""
        camera = status.get("camera", {})
        pan_angle = camera.get("pan_angle", 90)
        tilt_angle = camera.get("tilt_angle", 90)

        # Определяем положение по горизонтали
        if pan_angle < 80:
            pan_position = "повернута вправо"
        elif pan_angle > 100:
            pan_position = "повернута влево"
        else:
            pan_position = "смотрит прямо"

        # Определяем положение по вертикали
        if tilt_angle < 80:
            tilt_position = "наклонена вниз"
        elif tilt_angle > 100:
            tilt_position = "поднята вверх"
        else:
            tilt_position = "в горизонтальном положении"

        return f"Камера {pan_position} и {tilt_position}"

    def get_arm_text(self, status: dict) -> str:
        """Генерирует текстовое описание состояния роборуки"""
        arm = status.get("arm", {})

        if not arm.get("available", False):
            return "Роборука недоступна"

        current_angles = arm.get("current_angles", [])
        if not current_angles or len(current_angles) != 5:
            return "Данные роборуки недоступны"

        # Проверяем домашнюю позицию (примерные углы)
        home_angles = [90, 90, 90, 90, 90]
        is_home = all(abs(current - home) < 10 for current,
                      home in zip(current_angles, home_angles))

        if is_home:
            return "Роборука в исходном положении"

        # Описываем состояние захвата (5-й сервопривод)
        gripper_angle = current_angles[4]
        if gripper_angle < 75:
            gripper_status = "захват закрыт"
        elif gripper_angle > 105:
            gripper_status = "захват открыт"
        else:
            gripper_status = "захват в среднем положении"

        return f"Роборука активна, {gripper_status}"

    def get_imu_text(self, status: dict) -> str:
        """Генерирует текстовое описание данных IMU"""
        imu = status.get("imu", {})

        if not imu.get("available", False):
            return "Датчик ориентации недоступен"

        if not imu.get("ok", False):
            return "Датчик ориентации не отвечает"

        roll = imu.get("roll", 0)
        pitch = imu.get("pitch", 0)

        # Проверяем наклоны
        orientation_parts = []

        if abs(roll) > 15:
            direction = "влево" if roll > 0 else "вправо"
            orientation_parts.append(
                f"наклон {direction} {abs(roll):.0f} градусов")

        if abs(pitch) > 15:
            direction = "вперед" if pitch > 0 else "назад"
            orientation_parts.append(
                f"наклон {direction} {abs(pitch):.0f} градусов")

        if not orientation_parts:
            return "Робот стоит ровно"

        return "Обнаружен " + ", ".join(orientation_parts)

    def get_full_status_text(self, status: dict, include_sections: Optional[list] = None) -> str:
        """
        Генерирует полный текстовый отчет о состоянии всех датчиков

        Args:
            status: словарь с данными статуса робота
            include_sections: список разделов ['distances', 'environment', 'motion', 'camera', 'arm', 'imu']
        """
        try:
            # Все доступные разделы
            all_sections = ['distances', 'environment',
                            'motion', 'camera', 'arm', 'imu']
            sections = include_sections if include_sections is not None else all_sections

            report_parts = []

            # Генерируем отчеты по каждому разделу
            if 'distances' in sections:
                distances_text = self.get_distance_sensors_text(status)
                report_parts.append(f"Датчики расстояния: {distances_text}")

            if 'environment' in sections:
                env_text = self.get_environment_text(status)
                report_parts.append(f"Климат: {env_text}")

            if 'motion' in sections:
                motion_text = self.get_motion_text(status)
                report_parts.append(f"Движение: {motion_text}")

            if 'camera' in sections:
                camera_text = self.get_camera_text(status)
                report_parts.append(camera_text)

            if 'arm' in sections and status.get("arm", {}).get("available", False):
                arm_text = self.get_arm_text(status)
                report_parts.append(arm_text)

            if 'imu' in sections and status.get("imu", {}).get("available", False):
                imu_text = self.get_imu_text(status)
                report_parts.append(f"Ориентация: {imu_text}")

            if not report_parts:
                return "Нет доступных данных датчиков"

            # Объединяем все части отчета
            full_report = ". ".join(report_parts) + "."
            logger.info(
                f"Сгенерирован полный отчет датчиков ({len(report_parts)} разделов)")
            return full_report

        except Exception as e:
            logger.error(f"Ошибка генерации полного отчета: {e}")
            return "Ошибка обработки данных датчиков"

    def get_quick_status_text(self, status: dict) -> str:
        """Генерирует краткий статус для быстрого озвучивания"""
        try:
            parts = []

            # Критические препятствия
            obstacles = status.get("obstacles", {})
            close_obstacles = [name for name,
                               is_close in obstacles.items() if is_close]

            if close_obstacles:
                obstacle_names = {
                    "left_front": "слева спереди",
                    "right_front": "справа спереди",
                    "front_center": "прямо спереди",
                    "left_rear": "слева сзади",
                    "rear_right": "справа сзади"
                }
                obstacle_list = [obstacle_names.get(
                    obs, obs) for obs in close_obstacles]
                parts.append(f"Препятствия {', '.join(obstacle_list)}")

            # Состояние движения
            motion = status.get("motion", {})
            if motion.get("is_moving", False):
                direction_names = {1: "вперед",
                                   2: "назад", 3: "влево", 4: "вправо"}
                direction = direction_names.get(
                    motion.get("direction", 0), "неизвестно")
                parts.append(f"Движение {direction}")
            else:
                parts.append("Стоит")

            # Критическая температура
            env = status.get("environment", {})
            temp = env.get("temperature")
            if temp is not None and (temp > 35 or temp < 5):
                parts.append(f"Температура {temp:.0f} градусов")

            # Если ничего особенного нет
            if not parts:
                return "Все системы в норме"

            return ". ".join(parts) + "."

        except Exception as e:
            logger.error(f"Ошибка генерации краткого статуса: {e}")
            return "Ошибка получения статуса"

    def get_alerts_text(self, status: dict) -> str:
        """Генерирует текст только для критических предупреждений"""
        try:
            alerts = []

            # Критически близкие препятствия
            distance_sensors = status.get("distance_sensors", {})
            for sensor_name, distance in distance_sensors.items():
                if distance != SENSOR_ERR and distance < 15:
                    sensor_names_ru = {
                        "left_front": "слева спереди",
                        "right_front": "справа спереди",
                        "front_center": "прямо спереди",
                        "left_rear": "слева сзади",
                        "rear_right": "справа сзади"
                    }
                    sensor_name_ru = sensor_names_ru.get(
                        sensor_name, sensor_name)
                    alerts.append(
                        f"Близкое препятствие {sensor_name_ru} {distance} сантиметров")

            # Критическая температура
            env = status.get("environment", {})
            temp = env.get("temperature")
            if temp is not None:
                if temp > 40:
                    alerts.append(
                        f"Критически высокая температура {temp:.0f} градусов")
                elif temp < 0:
                    alerts.append(
                        f"Отрицательная температура {temp:.0f} градусов")

            # Неисправные датчики
            if temp is None and env.get("humidity") is None:
                alerts.append("Климатические датчики не отвечают")

            # Проблемы с IMU
            imu = status.get("imu", {})
            if imu.get("available", False) and not imu.get("ok", False):
                alerts.append("Датчик ориентации неисправен")

            # Критический наклон
            if imu.get("ok", False):
                roll = imu.get("roll", 0)
                pitch = imu.get("pitch", 0)
                if abs(roll) > 30 or abs(pitch) > 30:
                    alerts.append("Критический наклон робота")

            # Возвращаем результат
            if not alerts:
                return ""  # Нет предупреждений

            return "Внимание! " + ". ".join(alerts) + "."

        except Exception as e:
            logger.error(f"Ошибка генерации предупреждений: {e}")
            return "Ошибка проверки предупреждений"

    def get_section_text(self, status: dict, section: str) -> str:
        """
        Получить текст для конкретного раздела датчиков

        Args:
            status: данные статуса робота
            section: название раздела ('distances', 'environment', etc.)
        """
        section_methods = {
            'distances': self.get_distance_sensors_text,
            'environment': self.get_environment_text,
            'motion': self.get_motion_text,
            'camera': self.get_camera_text,
            'arm': self.get_arm_text,
            'imu': self.get_imu_text,
        }

        method = section_methods.get(section)
        if not method:
            return f"Неизвестный раздел: {section}"

        try:
            return method(status)
        except Exception as e:
            logger.error(f"Ошибка получения текста для раздела {section}: {e}")
            return f"Ошибка в разделе {section}"
