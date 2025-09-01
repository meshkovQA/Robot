# app/services/robot/safety_service.py
# =======================================================================================
import time
import threading
import logging
from typing import Tuple, Optional
from app.core.entities.command import RobotCommand
from app.core.events.event_bus import EventBus
from robot.config import (
    SENSOR_ERR, SENSOR_FWD_STOP_CM, SENSOR_BWD_STOP_CM, SENSOR_SIDE_STOP_CM,
    KICKSTART_DURATION, KICKSTART_SPEED, MIN_SPEED_FOR_KICKSTART
)

logger = logging.getLogger(__name__)


class SafetyController:
    def __init__(self, sensor_manager, events: EventBus, config: dict = None):
        self.sensors = sensor_manager
        self.events = events
        self.config = config or {}
        self._kickstart_active = False
        self._kickstart_timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()

    def can_move_forward(self, speed: int) -> Tuple[bool, str]:
        try:
            distances = self.sensors.get_distance_sensors()

            center_dist = distances['center_front']
            if center_dist != SENSOR_ERR and center_dist < SENSOR_FWD_STOP_CM:
                return False, f"Obstacle ahead: {center_dist}cm"

            left_dist = distances['left_front']
            if left_dist != SENSOR_ERR and left_dist < SENSOR_SIDE_STOP_CM:
                return False, f"Obstacle on left: {left_dist}cm"

            right_dist = distances['right_front']
            if right_dist != SENSOR_ERR and right_dist < SENSOR_SIDE_STOP_CM:
                return False, f"Obstacle on right: {right_dist}cm"

            return True, ""
        except Exception as e:
            return False, f"Safety check error: {e}"

    def can_move_backward(self, speed: int) -> Tuple[bool, str]:
        try:
            distances = self.sensors.get_distance_sensors()

            left_rear = distances['left_rear']
            if left_rear != SENSOR_ERR and left_rear < SENSOR_BWD_STOP_CM:
                return False, f"Obstacle behind left: {left_rear}cm"

            right_rear = distances['right_rear']
            if right_rear != SENSOR_ERR and right_rear < SENSOR_BWD_STOP_CM:
                return False, f"Obstacle behind right: {right_rear}cm"

            return True, ""
        except Exception as e:
            return False, f"Safety check error: {e}"

    def needs_kickstart(self, speed: int, direction: int) -> bool:
        with self._lock:
            return (speed > 0 and speed < MIN_SPEED_FOR_KICKSTART and
                    direction in [1, 2] and not self._kickstart_active)

    def apply_kickstart(self, target_speed: int, direction: int, hardware, camera_angles: Tuple[int, int]) -> bool:
        try:
            with self._lock:
                if self._kickstart_active:
                    return False

                self._kickstart_active = True

                if self._kickstart_timer and self._kickstart_timer.is_alive():
                    self._kickstart_timer.cancel()

                kickstart_cmd = RobotCommand(
                    speed=KICKSTART_SPEED,
                    direction=direction,
                    pan_angle=camera_angles[0],
                    tilt_angle=camera_angles[1]
                )

                success = hardware.send_command(kickstart_cmd)

                if success:
                    self._kickstart_timer = threading.Timer(
                        KICKSTART_DURATION,
                        lambda: self._return_to_target_speed(
                            target_speed, direction, hardware, camera_angles)
                    )
                    self._kickstart_timer.start()
                else:
                    self._kickstart_active = False

                return success
        except Exception as e:
            logger.error(f"Error applying kickstart: {e}")
            self._kickstart_active = False
            return False

    def _return_to_target_speed(self, target_speed: int, direction: int, hardware, camera_angles: Tuple[int, int]):
        try:
            with self._lock:
                cmd = RobotCommand(
                    speed=target_speed,
                    direction=direction,
                    pan_angle=camera_angles[0],
                    tilt_angle=camera_angles[1]
                )
                hardware.send_command(cmd)
                self._kickstart_active = False
        except Exception as e:
            logger.error(f"Error returning to target speed: {e}")
            self._kickstart_active = False
