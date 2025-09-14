# robot/controllers/arm_controller.py
import logging
from typing import TYPE_CHECKING, List, Optional

from robot.config import ARDUINO_MEGA_ADDRESS

if TYPE_CHECKING:
    from robot.controller import RobotController

logger = logging.getLogger(__name__)


class ArmController:
    """Компонент управления роботурукой через Arduino MEGA"""

    # Константы из Arduino кода MEGA
    REG_SERVO = 0x31

    # Ограничения углов (из Arduino кода)
    SERVO_MIN = [0, 10, 50, 0, 65]
    SERVO_MAX = [180, 140, 180, 180, 120]

    # Названия сервоприводов для удобства
    SERVO_NAMES = ["base", "shoulder", "elbow", "wrist", "gripper"]

    def __init__(self, controller: 'RobotController'):
        self.controller = controller

        # Текущие позиции (по умолчанию из Arduino кода)
        self.current_angles = [90, 90, 90, 90, 90]

    def _clamp_angle(self, servo_id: int, angle: int) -> int:
        """Ограничение угла сервопривода согласно лимитам"""
        if servo_id < 0 or servo_id > 4:
            return angle
        return max(self.SERVO_MIN[servo_id], min(self.SERVO_MAX[servo_id], angle))

    def set_servo_angle(self, servo_id: int, angle: int) -> bool:
        """
        Установить угол одного сервопривода
        servo_id: 0-4 (base, shoulder, elbow, wrist, gripper)
        angle: угол в градусах
        """
        if servo_id < 0 or servo_id > 4:
            logger.error(
                "Неверный ID сервопривода: %d (должен быть 0-4)", servo_id)
            return False

        angle = self._clamp_angle(servo_id, angle)

        # Обновляем только один сервопривод, остальные оставляем как есть
        new_angles = self.current_angles.copy()
        new_angles[servo_id] = angle

        return self._send_all_angles(new_angles)

    def set_all_angles(self, angles: List[int]) -> bool:
        """
        Установить углы всех сервоприводов
        angles: список из 5 углов [base, shoulder, elbow, wrist, gripper]
        """
        if len(angles) != 5:
            logger.error("Должно быть 5 углов, получено: %d", len(angles))
            return False

        # Применяем ограничения
        clamped_angles = [
            self._clamp_angle(i, angle) for i, angle in enumerate(angles)
        ]

        return self._send_all_angles(clamped_angles)

    def _send_all_angles(self, angles: List[int]) -> bool:
        """Отправка углов всех сервоприводов на MEGA"""
        try:
            # Формируем команду: регистр + 5 байт углов
            data = [self.REG_SERVO] + angles

            # Отправляем команду на MEGA
            ok = self.controller.fast_i2c.write_mega_command(data, timeout=0.3)

            if ok:
                self.current_angles = angles.copy()
                logger.debug("Углы роборуки установлены: %s", angles)
            else:
                logger.error("Ошибка отправки команды роборуке")

            return ok

        except Exception as e:
            logger.error("Ошибка управления роборукой: %s", e)
            return False

    def get_current_angles(self) -> List[int]:
        """Получить текущие углы сервоприводов"""
        return self.current_angles.copy()

    def reset_to_home(self) -> bool:
        """Вернуть роборуку в исходное положение"""
        home_angles = [90, 90, 90, 90, 90]
        return self.set_all_angles(home_angles)

    def get_servo_limits(self, servo_id: int) -> Optional[tuple]:
        """Получить лимиты углов для сервопривода"""
        if servo_id < 0 or servo_id > 4:
            return None
        return (self.SERVO_MIN[servo_id], self.SERVO_MAX[servo_id])

    def get_all_servo_limits(self) -> dict:
        """Получить лимиты всех сервоприводов"""
        return {
            name: {
                "min": self.SERVO_MIN[i],
                "max": self.SERVO_MAX[i],
                "current": self.current_angles[i]
            }
            for i, name in enumerate(self.SERVO_NAMES)
        }

    def move_servo_relative(self, servo_id: int, delta: int) -> bool:
        """
        Переместить сервопривод относительно текущего положения
        servo_id: 0-4
        delta: изменение угла (может быть отрицательным)
        """
        if servo_id < 0 or servo_id > 4:
            return False

        new_angle = self.current_angles[servo_id] + delta
        return self.set_servo_angle(servo_id, new_angle)

    def open_gripper(self) -> bool:
        """Открыть захват (максимальный угол)"""
        return self.set_servo_angle(4, self.SERVO_MAX[4])  # gripper = servo 4

    def close_gripper(self) -> bool:
        """Закрыть захват (минимальный угол)"""
        return self.set_servo_angle(4, self.SERVO_MIN[4])  # gripper = servo 4

    def get_status(self) -> dict:
        """Получить статус роборуки"""
        return {
            "current_angles": self.get_current_angles(),
            "servo_names": self.SERVO_NAMES,
            "limits": self.get_all_servo_limits(),
            "available": True
        }
