# new_robot_controller.py - ОСНОВНОЙ ФАЙЛ ДЛЯ ЗАМЕНЫ
# =======================================================================================
"""
НОВЫЙ RobotController с модульной архитектурой

Использование:
from new_robot_controller import RobotController

robot = RobotController()
robot.move_forward(100)
robot.set_camera_pan(45)
status = robot.get_status()
"""

import logging
import warnings
from typing import Optional, Tuple
from app.services.robot_factory import RobotFactory

logger = logging.getLogger(__name__)


class RobotController:
    """
    Новый RobotController с модульной архитектурой
    Совместимый интерфейс со старым API
    """

    def __init__(self, bus=None):
        logger.info("🤖 Initializing new modular RobotController")

        # Создаем новый робот
        config = {'i2c_bus': bus} if bus else {}
        self._robot = RobotFactory.create_robot(config)

        # Legacy поля для совместимости
        self.current_speed = 0
        self.is_moving = False
        self.movement_direction = 0
        self.current_pan_angle = 90
        self.current_tilt_angle = 90
        self.last_command_time = 0.0

        self._update_legacy_fields()

    def _update_legacy_fields(self):
        """Обновляем legacy поля из нового статуса"""
        try:
            status = self._robot.get_full_status()
            self.current_speed = status['movement']['speed']
            self.is_moving = status['movement']['is_moving']
            self.movement_direction = status['movement']['direction']
            self.current_pan_angle = status['camera']['pan_angle']
            self.current_tilt_angle = status['camera']['tilt_angle']
            self.last_command_time = max(
                status['hardware']['last_command_time'],
                status.get('camera', {}).get('last_update_time', 0)
            )
        except Exception as e:
            logger.error(f"Error updating legacy fields: {e}")

    # =============== ДВИЖЕНИЕ ===============
    def move_forward(self, speed: int) -> bool:
        success = self._robot.navigation.move_forward(speed)
        self._update_legacy_fields()
        return success

    def move_backward(self, speed: int) -> bool:
        success = self._robot.navigation.move_backward(speed)
        self._update_legacy_fields()
        return success

    def turn_left(self, speed: int) -> bool:
        success = self._robot.navigation.turn_left(speed)
        self._update_legacy_fields()
        return success

    def turn_right(self, speed: int) -> bool:
        success = self._robot.navigation.turn_right(speed)
        self._update_legacy_fields()
        return success

    def stop(self) -> bool:
        success = self._robot.navigation.stop()
        self._update_legacy_fields()
        return success

    # =============== КАМЕРА ===============
    def set_camera_angles(self, pan: int, tilt: int) -> bool:
        success = self._robot.camera.set_angles(pan, tilt)
        self._update_legacy_fields()
        return success

    def set_camera_pan(self, angle: int) -> bool:
        success = self._robot.camera.set_pan(angle)
        self._update_legacy_fields()
        return success

    def set_camera_tilt(self, angle: int) -> bool:
        success = self._robot.camera.set_tilt(angle)
        self._update_legacy_fields()
        return success

    def center_camera(self) -> bool:
        success = self._robot.camera.center()
        self._update_legacy_fields()
        return success

    def pan_left(self, step: int = None) -> bool:
        success = self._robot.camera.pan_left(step)
        self._update_legacy_fields()
        return success

    def pan_right(self, step: int = None) -> bool:
        success = self._robot.camera.pan_right(step)
        self._update_legacy_fields()
        return success

    def tilt_up(self, step: int = None) -> bool:
        success = self._robot.camera.tilt_up(step)
        self._update_legacy_fields()
        return success

    def tilt_down(self, step: int = None) -> bool:
        success = self._robot.camera.tilt_down(step)
        self._update_legacy_fields()
        return success

    def get_camera_angles(self) -> Tuple[int, int]:
        return self._robot.camera.get_angles()

    def get_camera_limits(self) -> dict:
        return {
            "pan": {"min": 0, "max": 180, "default": 90},
            "tilt": {"min": 0, "max": 180, "default": 90},
            "step_size": 10
        }

    # =============== ДАТЧИКИ ===============
    def read_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        distances = self._robot.sensors.get_distance_sensors()
        env = self._robot.sensors.get_environmental_sensors()
        return (
            distances['center_front'],
            distances['right_rear'],
            env['temperature'],
            env['humidity']
        )

    def read_uno_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        return self.read_sensors()

    def read_mega_sensors(self) -> Tuple[int, int, int]:
        distances = self._robot.sensors.get_distance_sensors()
        return (
            distances['left_front'],
            distances['right_front'],
            distances['left_rear']
        )

    # =============== СТАТУС ===============
    def get_status(self) -> dict:
        try:
            full_status = self._robot.get_full_status()

            # Преобразуем в старый формат
            return {
                'speed': full_status['movement']['speed'],
                'direction': full_status['movement']['direction'],
                'is_moving': full_status['movement']['is_moving'],
                'pan_angle': full_status['camera']['pan_angle'],
                'tilt_angle': full_status['camera']['tilt_angle'],
                'sensors': full_status['sensors']['distances'],
                'environment': full_status['sensors']['environment'],
                'hardware': full_status['hardware'],
                'timestamp': full_status['system']['timestamp']
            }
        except Exception as e:
            return {'error': str(e)}

    # =============== СИСТЕМА ===============
    def reconnect(self) -> bool:
        return self._robot.hardware.reconnect()

    def shutdown(self):
        self._robot.shutdown()

    def send_command(self, cmd):
        """Прямая отправка команды (для совместимости)"""
        return self._robot.hardware.send_command(cmd)
