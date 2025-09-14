# robot/controllers/sensor_monitor.py
import logging
import threading
import time
from typing import TYPE_CHECKING, Optional, Tuple

from robot.config import (
    SENSOR_ERR, SENSOR_FWD_STOP_CM, SENSOR_BWD_STOP_CM, SENSOR_SIDE_STOP_CM,
    CAMERA_PAN_MIN, CAMERA_PAN_MAX, CAMERA_TILT_MIN, CAMERA_TILT_MAX,
    IMU_ENABLED
)

if TYPE_CHECKING:
    from robot.controller import RobotController

logger = logging.getLogger(__name__)


class SensorMonitor:
    """Компонент мониторинга датчиков и автостопа"""

    def __init__(self, controller: 'RobotController'):
        self.controller = controller
        self._stop_event = threading.Event()

        # Датчики расстояния (все с MEGA)
        self._sensor_left_front = SENSOR_ERR
        self._sensor_right_front = SENSOR_ERR
        self._sensor_left_rear = SENSOR_ERR
        self._sensor_front_center = SENSOR_ERR
        self._sensor_rear_right = SENSOR_ERR

        # Климатические данные (с UNO)
        self._env_temp: Optional[float] = None
        self._env_hum: Optional[float] = None

        # Данные энкодеров (с UNO)
        self._left_wheel_speed: float = 0.0
        self._right_wheel_speed: float = 0.0

        # IMU
        from robot.devices.imu import IMUState
        self._imu_state = IMUState()
        self._imu_ok = False
        self._imu_last_ts = 0.0

        # мониторинг
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def get_climate_data(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Получить климатические данные с UNO
        Возвращает: (температура, влажность)
        """
        with self.controller._lock:
            return self._env_temp, self._env_hum

    def get_distance_sensors(self) -> dict:
        """
        Получить все датчики расстояния с MEGA
        Возвращает словарь с именованными датчиками
        """
        with self.controller._lock:
            return {
                "left_front": self._sensor_left_front,
                "right_front": self._sensor_right_front,
                "left_rear": self._sensor_left_rear,
                "front_center": self._sensor_front_center,
                "rear_right": self._sensor_rear_right
            }

    def get_wheel_speeds(self) -> Tuple[float, float]:
        """
        Получить скорости колес с энкодеров (с UNO)
        Возвращает: (left_speed, right_speed) в м/с
        """
        with self.controller._lock:
            return self._left_wheel_speed, self._right_wheel_speed

    def get_imu_data(self) -> dict:
        """Получить данные IMU"""
        with self.controller._lock:
            if IMU_ENABLED:
                s = self._imu_state
                return {
                    "available": True,
                    "ok": bool(self._imu_ok),
                    "roll": s.roll, "pitch": s.pitch, "yaw": s.yaw,
                    "gx": s.gx, "gy": s.gy, "gz": s.gz,
                    "ax": s.ax, "ay": s.ay, "az": s.az,
                    "timestamp": s.last_update or self._imu_last_ts,
                    "whoami": s.whoami,
                }
            return {"available": False}

    def _monitor_loop(self):
        """Фоновый мониторинг: обновляет локальный кэш датчиков и делает автостоп."""
        poll_interval = 0.25
        logger.info(
            "Запущен мониторинг датчиков (UNO: климат+энкодеры+камера, MEGA: расстояние)")

        while not self._stop_event.is_set():
            try:
                cache = self.controller.fast_i2c.get_cache()
                uno_data = cache.get("uno", {})
                mega_data = cache.get("mega", {})

                # Данные с UNO: углы камеры, климат, энкодеры
                pan = uno_data.get("pan", None)
                tilt = uno_data.get("tilt", None)
                temp = uno_data.get("temp", None)
                hum = uno_data.get("hum", None)
                left_wheel_speed = uno_data.get("left_wheel_speed", 0.0)
                right_wheel_speed = uno_data.get("right_wheel_speed", 0.0)

                # Данные с MEGA: все датчики расстояния
                left_front_dist = mega_data.get("left_front", SENSOR_ERR)
                right_front_dist = mega_data.get("right_front", SENSOR_ERR)
                left_rear_dist = mega_data.get("left_rear", SENSOR_ERR)
                front_center_dist = mega_data.get("front_center", SENSOR_ERR)
                rear_right_dist = mega_data.get("rear_right", SENSOR_ERR)

                with self.controller._lock:
                    # Обновляем датчики расстояния (все с MEGA)
                    self._sensor_left_front = left_front_dist
                    self._sensor_right_front = right_front_dist
                    self._sensor_left_rear = left_rear_dist
                    self._sensor_front_center = front_center_dist
                    self._sensor_rear_right = rear_right_dist

                    # Обновляем климат и энкодеры (с UNO)
                    self._env_temp, self._env_hum = temp, hum
                    self._left_wheel_speed = left_wheel_speed
                    self._right_wheel_speed = right_wheel_speed

                    # Обновляем углы камеры если они валидны
                    if pan is not None and (CAMERA_PAN_MIN <= pan <= CAMERA_PAN_MAX):
                        self.controller.current_pan_angle = pan
                    if tilt is not None and (CAMERA_TILT_MIN <= tilt <= CAMERA_TILT_MAX):
                        self.controller.current_tilt_angle = tilt

                    moving = self.controller.is_moving
                    direction = self.controller.movement_direction

                # IMU: копируем актуальное состояние из драйвера
                if IMU_ENABLED and self.controller._imu is not None:
                    st = self.controller._imu.get_state()
                    now = time.time()
                    fresh = (now - (st.last_update or 0.0)) < 2.0
                    with self.controller._lock:
                        self._imu_state = st
                        self._imu_last_ts = st.last_update or 0.0
                        self._imu_ok = bool(st.ok and fresh)

                # Автостоп
                self._check_autostop(moving, direction, front_center_dist,
                                     left_front_dist, right_front_dist,
                                     left_rear_dist, rear_right_dist)

                time.sleep(poll_interval)

            except Exception as e:
                logger.error("Ошибка в мониторинге: %s", e)
                self.controller.reconnect_bus()
                time.sleep(0.5)

        logger.info("Мониторинг датчиков завершен")

    def _check_autostop(self, moving: bool, direction: int,
                        front_center_dist: int, left_front_dist: int,
                        right_front_dist: int, left_rear_dist: int, rear_right_dist: int):
        """Проверка автостопа при обнаружении препятствий"""
        if not moving or direction not in (1, 2):
            return

        if direction == 1:  # движение вперед
            should_stop = False
            if front_center_dist != SENSOR_ERR and front_center_dist < SENSOR_FWD_STOP_CM:
                logger.warning(
                    "АВТОСТОП: препятствие по центру спереди %d см", front_center_dist)
                should_stop = True
            if left_front_dist != SENSOR_ERR and left_front_dist < SENSOR_SIDE_STOP_CM:
                logger.warning(
                    "АВТОСТОП: препятствие слева спереди %d см", left_front_dist)
                should_stop = True
            if right_front_dist != SENSOR_ERR and right_front_dist < SENSOR_SIDE_STOP_CM:
                logger.warning(
                    "АВТОСТОП: препятствие справа спереди %d см", right_front_dist)
                should_stop = True
            if should_stop:
                self.controller.movement.stop()

        else:  # движение назад
            should_stop = False
            if rear_right_dist != SENSOR_ERR and rear_right_dist < SENSOR_BWD_STOP_CM:
                logger.warning(
                    "АВТОСТОП: препятствие справа сзади %d см", rear_right_dist)
                should_stop = True
            if left_rear_dist != SENSOR_ERR and left_rear_dist < SENSOR_BWD_STOP_CM:
                logger.warning(
                    "АВТОСТОП: препятствие слева сзади %d см", left_rear_dist)
                should_stop = True
            if should_stop:
                self.controller.movement.stop()

    def stop(self):
        """Остановка мониторинга"""
        self._stop_event.set()
        if self._monitor_thread.is_alive():
            logger.info("Ожидание завершения мониторинга...")
            self._monitor_thread.join(timeout=1.5)
