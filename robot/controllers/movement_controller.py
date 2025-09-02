# robot/controllers/movement_controller.py
import logging
import threading
from typing import TYPE_CHECKING

from robot.config import (
    SENSOR_ERR, SENSOR_FWD_STOP_CM, SENSOR_BWD_STOP_CM, SENSOR_SIDE_STOP_CM,
    SPEED_MIN, SPEED_MAX
)

if TYPE_CHECKING:
    from robot.controller import RobotController

logger = logging.getLogger(__name__)


def _clip_speed(v: int) -> int:
    return max(SPEED_MIN, min(SPEED_MAX, int(v)))


class MovementController:
    """Компонент управления движением робота"""

    def __init__(self, controller: 'RobotController'):
        self.controller = controller

    def move_forward(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        center_front_dist, *_ = self.controller.read_uno_sensors()
        left_front_dist, right_front_dist, _ = self.controller.read_mega_sensors()

        if center_front_dist != SENSOR_ERR and center_front_dist < SENSOR_FWD_STOP_CM:
            logger.warning("Вперёд нельзя: препятствие по центру на %d см (порог %d см)",
                           center_front_dist, SENSOR_FWD_STOP_CM)
            return False
        if left_front_dist != SENSOR_ERR and left_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Вперёд нельзя: препятствие слева на %d см (порог %d см)",
                           left_front_dist, SENSOR_SIDE_STOP_CM)
            return False
        if right_front_dist != SENSOR_ERR and right_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Вперёд нельзя: препятствие справа на %d см (порог %d см)",
                           right_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        ok = self.controller._send_movement_command(speed, 1)
        if ok:
            with self.controller._lock:
                self.controller.current_speed = speed
                self.controller.is_moving = True
                self.controller.movement_direction = 1
        return ok

    def move_backward(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        _, right_rear_dist, *_ = self.controller.read_uno_sensors()
        _, _, left_rear_dist = self.controller.read_mega_sensors()

        if right_rear_dist != SENSOR_ERR and right_rear_dist < SENSOR_BWD_STOP_CM:
            logger.warning("Назад нельзя: препятствие справа сзади на %d см (порог %d см)",
                           right_rear_dist, SENSOR_BWD_STOP_CM)
            return False
        if left_rear_dist != SENSOR_ERR and left_rear_dist < SENSOR_BWD_STOP_CM:
            logger.warning("Назад нельзя: препятствие слева сзади на %d см (порог %d см)",
                           left_rear_dist, SENSOR_BWD_STOP_CM)
            return False

        ok = self.controller._send_movement_command(speed, 2)
        if ok:
            with self.controller._lock:
                self.controller.current_speed = speed
                self.controller.is_moving = True
                self.controller.movement_direction = 2
        return ok

    def tank_turn_left(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        left_front_dist, right_front_dist, _ = self.controller.read_mega_sensors()
        if right_front_dist != SENSOR_ERR and right_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Поворот влево нельзя: препятствие справа на %d см (порог %d см)",
                           right_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        with self.controller._lock:
            self.controller.is_moving = False
            self.controller.movement_direction = 3

        from robot.controller import RobotCommand
        cmd = RobotCommand(speed=speed, direction=3,
                           pan_angle=self.controller.current_pan_angle,
                           tilt_angle=self.controller.current_tilt_angle)
        return self.controller.send_command(cmd)

    def tank_turn_right(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        left_front_dist, right_front_dist, _ = self.controller.read_mega_sensors()
        if left_front_dist != SENSOR_ERR and left_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Поворот вправо нельзя: препятствие слева на %d см (порог %d см)",
                           left_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        with self.controller._lock:
            self.controller.is_moving = False
            self.controller.movement_direction = 4

        from robot.controller import RobotCommand
        cmd = RobotCommand(speed=speed, direction=4,
                           pan_angle=self.controller.current_pan_angle,
                           tilt_angle=self.controller.current_tilt_angle)
        return self.controller.send_command(cmd)

    def update_speed(self, new_speed: int) -> bool:
        new_speed = _clip_speed(new_speed)
        with self.controller._lock:
            moving = self.controller.is_moving
            direction = self.controller.movement_direction
            self.controller.current_speed = new_speed

        if not moving or direction == 0:
            logger.info(
                "Скорость сохранена (%s), но движение не идёт", new_speed)
            return True

        from robot.controller import RobotCommand
        cmd = RobotCommand(speed=new_speed, direction=direction,
                           pan_angle=self.controller.current_pan_angle,
                           tilt_angle=self.controller.current_tilt_angle)
        return self.controller.send_command(cmd)

    def stop(self) -> bool:
        if self.controller._kickstart_timer and self.controller._kickstart_timer.is_alive():
            self.controller._kickstart_timer.cancel()
        self.controller._kickstart_active = False

        with self.controller._lock:
            self.controller.current_speed = 0
            self.controller.is_moving = False
            self.controller.movement_direction = 0

        from robot.controller import RobotCommand
        cmd = RobotCommand(speed=0, direction=0,
                           pan_angle=self.controller.current_pan_angle,
                           tilt_angle=self.controller.current_tilt_angle)
        return self.controller.send_command(cmd)
