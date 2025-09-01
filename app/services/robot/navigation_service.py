# app/services/robot/navigation_service.py
# =======================================================================================
import time
import threading
import logging
from app.core.entities.command import RobotCommand
from app.core.events.event_bus import EventBus
from robot.config import SPEED_MIN, SPEED_MAX

logger = logging.getLogger(__name__)


class NavigationController:
    def __init__(self, hardware, safety, camera, events: EventBus, config: dict = None):
        self.hardware = hardware
        self.safety = safety
        self.camera = camera
        self.events = events
        self.config = config or {}
        self._current_speed = 0
        self._current_direction = 0
        self._is_moving = False
        self._lock = threading.RLock()

    def _clip_speed(self, speed: int) -> int:
        return max(SPEED_MIN, min(SPEED_MAX, int(speed)))

    def move_forward(self, speed: int) -> bool:
        try:
            speed = self._clip_speed(speed)
            can_move, reason = self.safety.can_move_forward(speed)

            if not can_move:
                logger.warning(f"Cannot move forward: {reason}")
                return False

            camera_angles = self.camera.get_angles()

            if self.safety.needs_kickstart(speed, 1):
                success = self.safety.apply_kickstart(
                    speed, 1, self.hardware, camera_angles)
            else:
                cmd = RobotCommand(speed=speed, direction=1,
                                   pan_angle=camera_angles[0], tilt_angle=camera_angles[1])
                success = self.hardware.send_command(cmd)

            if success:
                with self._lock:
                    self._current_speed = speed
                    self._current_direction = 1
                    self._is_moving = True

            return success
        except Exception as e:
            logger.error(f"Error in move_forward: {e}")
            return False

    def move_backward(self, speed: int) -> bool:
        try:
            speed = self._clip_speed(speed)
            can_move, reason = self.safety.can_move_backward(speed)

            if not can_move:
                logger.warning(f"Cannot move backward: {reason}")
                return False

            camera_angles = self.camera.get_angles()

            if self.safety.needs_kickstart(speed, 2):
                success = self.safety.apply_kickstart(
                    speed, 2, self.hardware, camera_angles)
            else:
                cmd = RobotCommand(speed=speed, direction=2,
                                   pan_angle=camera_angles[0], tilt_angle=camera_angles[1])
                success = self.hardware.send_command(cmd)

            if success:
                with self._lock:
                    self._current_speed = speed
                    self._current_direction = 2
                    self._is_moving = True

            return success
        except Exception as e:
            logger.error(f"Error in move_backward: {e}")
            return False

    def turn_left(self, speed: int) -> bool:
        try:
            speed = self._clip_speed(speed)
            camera_angles = self.camera.get_angles()
            cmd = RobotCommand(speed=speed, direction=3,
                               pan_angle=camera_angles[0], tilt_angle=camera_angles[1])
            success = self.hardware.send_command(cmd)

            if success:
                with self._lock:
                    self._current_speed = speed
                    self._current_direction = 3
                    self._is_moving = True

            return success
        except Exception as e:
            logger.error(f"Error in turn_left: {e}")
            return False

    def turn_right(self, speed: int) -> bool:
        try:
            speed = self._clip_speed(speed)
            camera_angles = self.camera.get_angles()
            cmd = RobotCommand(speed=speed, direction=4,
                               pan_angle=camera_angles[0], tilt_angle=camera_angles[1])
            success = self.hardware.send_command(cmd)

            if success:
                with self._lock:
                    self._current_speed = speed
                    self._current_direction = 4
                    self._is_moving = True

            return success
        except Exception as e:
            logger.error(f"Error in turn_right: {e}")
            return False

    def stop(self) -> bool:
        try:
            camera_angles = self.camera.get_angles()
            cmd = RobotCommand(speed=0, direction=0,
                               pan_angle=camera_angles[0], tilt_angle=camera_angles[1])
            success = self.hardware.send_command(cmd)

            if success:
                with self._lock:
                    self._current_speed = 0
                    self._current_direction = 0
                    self._is_moving = False

            return success
        except Exception as e:
            logger.error(f"Error in stop: {e}")
            return False

    def get_movement_status(self) -> dict:
        with self._lock:
            return {
                'speed': self._current_speed,
                'direction': self._current_direction,
                'is_moving': self._is_moving,
                'last_command_time': time.time()
            }

    def shutdown(self):
        try:
            self.stop()
        except:
            pass
