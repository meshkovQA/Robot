# robot/controllers/kickstart_manager.py
import logging
import threading
from typing import TYPE_CHECKING, Optional

from robot.config import (
    KICKSTART_DURATION, KICKSTART_SPEED, MIN_SPEED_FOR_KICKSTART
)

if TYPE_CHECKING:
    from robot.controller import RobotController

logger = logging.getLogger(__name__)


class KickstartManager:
    """Компонент управления кикстартом моторов"""

    def __init__(self, controller: 'RobotController'):
        self.controller = controller
        self._kickstart_timer: Optional[threading.Timer] = None
        self._kickstart_active = False
        self._target_speed = 0
        self._target_direction = 0

    def needs_kickstart(self, speed: int, direction: int) -> bool:
        with self.controller._lock:
            direction_changed = (self.controller.movement_direction !=
                                 direction and self.controller.movement_direction != 0)
            was_stopped = not self.controller.is_moving
            low_speed = speed < MIN_SPEED_FOR_KICKSTART
        return (was_stopped or direction_changed) and low_speed

    def apply_kickstart(self, target_speed: int, direction: int) -> bool:
        logger.debug("Применяем кикстарт: %d -> %d на %dмс", target_speed,
                     KICKSTART_SPEED, int(KICKSTART_DURATION * 1000))

        if self._kickstart_timer and self._kickstart_timer.is_alive():
            self._kickstart_timer.cancel()

        self._target_speed = target_speed
        self._target_direction = direction
        self._kickstart_active = True

        from robot.controller import RobotCommand
        cmd = RobotCommand(
            speed=KICKSTART_SPEED,
            direction=direction,
            pan_angle=self.controller.current_pan_angle,
            tilt_angle=self.controller.current_tilt_angle
        )
        success = self.controller.send_command(cmd)

        if success:
            self._kickstart_timer = threading.Timer(
                KICKSTART_DURATION, self._return_to_target_speed)
            self._kickstart_timer.start()
        else:
            self._kickstart_active = False

        return success

    def _return_to_target_speed(self):
        if not self._kickstart_active:
            return
        logger.debug("Возврат к целевой скорости: %d", self._target_speed)

        from robot.controller import RobotCommand
        cmd = RobotCommand(
            speed=self._target_speed,
            direction=self._target_direction,
            pan_angle=self.controller.current_pan_angle,
            tilt_angle=self.controller.current_tilt_angle
        )
        success = self.controller.send_command(cmd)
        self._kickstart_active = False
        if not success:
            logger.error(
                "Не удалось вернуться к целевой скорости %d", self._target_speed)

    def is_active(self) -> bool:
        return self._kickstart_active

    def get_effective_speed(self) -> int:
        return KICKSTART_SPEED if self._kickstart_active else self.controller.current_speed

    def stop(self):
        """Остановка кикстарта"""
        if self._kickstart_timer and self._kickstart_timer.is_alive():
            self._kickstart_timer.cancel()
        self._kickstart_active = False
