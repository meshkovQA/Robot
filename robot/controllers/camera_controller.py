# robot/controllers/camera_controller.py
import logging
from typing import TYPE_CHECKING, Tuple

from robot.config import (
    CAMERA_PAN_MIN, CAMERA_PAN_MAX, CAMERA_PAN_DEFAULT,
    CAMERA_TILT_MIN, CAMERA_TILT_MAX, CAMERA_TILT_DEFAULT,
    CAMERA_STEP_SIZE
)

if TYPE_CHECKING:
    from robot.controller import RobotController

logger = logging.getLogger(__name__)


def _clip_pan_angle(angle: int) -> int:
    return max(CAMERA_PAN_MIN, min(CAMERA_PAN_MAX, int(angle)))


def _clip_tilt_angle(angle: int) -> int:
    return max(CAMERA_TILT_MIN, min(CAMERA_TILT_MAX, int(angle)))


class CameraController:
    """Компонент управления камерой"""

    def __init__(self, controller: 'RobotController'):
        self.controller = controller

    def set_camera_pan(self, angle: int) -> bool:
        angle = _clip_pan_angle(angle)
        with self.controller._lock:
            speed = self.controller.current_speed
            direction = self.controller.movement_direction
            self.controller.current_pan_angle = angle

        from robot.controller import RobotCommand
        cmd = RobotCommand(speed=speed, direction=direction,
                           pan_angle=angle, tilt_angle=self.controller.current_tilt_angle)
        return self.controller.send_command(cmd)

    def set_camera_tilt(self, angle: int) -> bool:
        angle = _clip_tilt_angle(angle)
        with self.controller._lock:
            speed = self.controller.current_speed
            direction = self.controller.movement_direction
            self.controller.current_tilt_angle = angle

        from robot.controller import RobotCommand
        cmd = RobotCommand(speed=self.controller.current_speed, direction=direction,
                           pan_angle=self.controller.current_pan_angle, tilt_angle=angle)
        return self.controller.send_command(cmd)

    def set_camera_angles(self, pan: int, tilt: int) -> bool:
        pan = _clip_pan_angle(pan)
        tilt = _clip_tilt_angle(tilt)
        with self.controller._lock:
            speed = self.controller.current_speed
            direction = self.controller.movement_direction
            self.controller.current_pan_angle = pan
            self.controller.current_tilt_angle = tilt

        from robot.controller import RobotCommand
        cmd = RobotCommand(speed=speed, direction=direction,
                           pan_angle=pan, tilt_angle=tilt)
        return self.controller.send_command(cmd)

    def center_camera(self) -> bool:
        return self.set_camera_angles(CAMERA_PAN_DEFAULT, CAMERA_TILT_DEFAULT)

    def pan_left(self, step: int | None = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        new_angle = self.controller.current_pan_angle + step
        return self.set_camera_pan(new_angle)

    def pan_right(self, step: int | None = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        new_angle = self.controller.current_pan_angle - step
        return self.set_camera_pan(new_angle)

    def tilt_up(self, step: int | None = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        new_angle = self.controller.current_tilt_angle + step
        return self.set_camera_tilt(new_angle)

    def tilt_down(self, step: int | None = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        new_angle = self.controller.current_tilt_angle - step
        return self.set_camera_tilt(new_angle)

    def get_camera_angles(self) -> Tuple[int, int]:
        with self.controller._lock:
            return self.controller.current_pan_angle, self.controller.current_tilt_angle

    def get_camera_limits(self) -> dict:
        return {
            "pan": {"min": CAMERA_PAN_MIN, "max": CAMERA_PAN_MAX, "default": CAMERA_PAN_DEFAULT},
            "tilt": {"min": CAMERA_TILT_MIN, "max": CAMERA_TILT_MAX, "default": CAMERA_TILT_DEFAULT},
            "step_size": CAMERA_STEP_SIZE
        }
