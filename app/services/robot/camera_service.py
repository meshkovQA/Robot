# app/services/robot/camera_service.py
# =======================================================================================
import time
import threading
import logging
from typing import Dict, Optional, Tuple
from app.core.entities.command import RobotCommand
from app.core.events.event_bus import EventBus
from robot.config import (
    CAMERA_PAN_MIN, CAMERA_PAN_MAX, CAMERA_PAN_DEFAULT,
    CAMERA_TILT_MIN, CAMERA_TILT_MAX, CAMERA_TILT_DEFAULT, CAMERA_STEP_SIZE
)

logger = logging.getLogger(__name__)


class CameraController:
    def __init__(self, hardware, events: EventBus, config: Dict[str, any] = None):
        self.hardware = hardware
        self.events = events
        self.config = config or {}
        self._current_pan = CAMERA_PAN_DEFAULT
        self._current_tilt = CAMERA_TILT_DEFAULT
        self._lock = threading.RLock()

    def _clip_pan_angle(self, angle: int) -> int:
        return max(CAMERA_PAN_MIN, min(CAMERA_PAN_MAX, int(angle)))

    def _clip_tilt_angle(self, angle: int) -> int:
        return max(CAMERA_TILT_MIN, min(CAMERA_TILT_MAX, int(angle)))

    def set_angles(self, pan: int, tilt: int) -> bool:
        try:
            pan = self._clip_pan_angle(pan)
            tilt = self._clip_tilt_angle(tilt)

            cmd = RobotCommand(speed=0, direction=0,
                               pan_angle=pan, tilt_angle=tilt)
            success = self.hardware.send_command(cmd)

            if success:
                with self._lock:
                    self._current_pan = pan
                    self._current_tilt = tilt

            return success
        except Exception as e:
            logger.error(f"Error setting camera angles: {e}")
            return False

    def set_pan(self, angle: int) -> bool:
        with self._lock:
            current_tilt = self._current_tilt
        return self.set_angles(angle, current_tilt)

    def set_tilt(self, angle: int) -> bool:
        with self._lock:
            current_pan = self._current_pan
        return self.set_angles(current_pan, angle)

    def pan_left(self, step: Optional[int] = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        with self._lock:
            new_pan = self._current_pan + step
        return self.set_pan(new_pan)

    def pan_right(self, step: Optional[int] = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        with self._lock:
            new_pan = self._current_pan - step
        return self.set_pan(new_pan)

    def tilt_up(self, step: Optional[int] = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        with self._lock:
            new_tilt = self._current_tilt + step
        return self.set_tilt(new_tilt)

    def tilt_down(self, step: Optional[int] = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        with self._lock:
            new_tilt = self._current_tilt - step
        return self.set_tilt(new_tilt)

    def center(self) -> bool:
        return self.set_angles(CAMERA_PAN_DEFAULT, CAMERA_TILT_DEFAULT)

    def get_angles(self) -> Tuple[int, int]:
        with self._lock:
            return (self._current_pan, self._current_tilt)

    def shutdown(self):
        try:
            self.center()
        except:
            pass
