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

        # кеш датчиков
        self._sensor_center_front = SENSOR_ERR
        self._sensor_left_front = SENSOR_ERR
        self._sensor_right_front = SENSOR_ERR
        self._sensor_right_rear = SENSOR_ERR
        self._sensor_left_rear = SENSOR_ERR
        self._env_temp: Optional[float] = None
        self._env_hum: Optional[float] = None

        # IMU
        from robot.devices.imu import IMUState
        self._imu_state = IMUState()
        self._imu_ok = False
        self._imu_last_ts = 0.0

        # мониторинг
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def read_uno_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        with self.controller._lock:
            return self._sensor_center_front, self._sensor_right_rear, self._env_temp, self._env_hum

    def read_mega_sensors(self) -> Tuple[int, int, int]:
        with self.controller._lock:
            return self._sensor_left_front, self._sensor_right_front, self._sensor_left_rear

    def read_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        return self.read_uno_sensors()

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
        logger.info("Запущен мониторинг датчиков")

        while not self._stop_event.is_set():
            try:
                cache = self.controller.fast_i2c.get_cache()
                uno = cache.get("uno", {})
                mega = cache.get("mega", {})

                center_front_dist = uno.get("center_front", SENSOR_ERR)
                right_rear_dist = uno.get("right_rear",   SENSOR_ERR)
                left_front_dist = mega.get("left_front",  SENSOR_ERR)
                right_front_dist = mega.get("right_front", SENSOR_ERR)
                left_rear_dist = mega.get("left_rear",   SENSOR_ERR)

                pan = uno.get("pan",  None)
                tilt = uno.get("tilt", None)
                temp = uno.get("temp", None)
                hum = uno.get("hum",  None)

                with self.controller._lock:
                    self._sensor_center_front = center_front_dist
                    self._sensor_left_front = left_front_dist
                    self._sensor_right_front = right_front_dist
                    self._sensor_left_rear = left_rear_dist
                    self._sensor_right_rear = right_rear_dist
                    self._env_temp, self._env_hum = temp, hum

                    # Обновляем углы камеры если они валидны
                    if pan is not None and (CAMERA_PAN_MIN <= pan <= CAMERA_PAN_MAX):
                        self.controller.current_pan_angle = pan
                    if tilt is not None and (CAMERA_TILT_MIN <= tilt <= CAMERA_TILT_MAX):
                        self.controller.current_tilt_angle = tilt

                    moving = self.controller.is_moving
                    direction = self.controller.movement_direction

                # ---- IMU: копируем актуальное состояние из драйвера ----
                if IMU_ENABLED and self.controller._imu is not None:
                    st = self.controller._imu.get_state()
                    now = time.time()
                    fresh = (now - (st.last_update or 0.0)) < 2.0
                    with self.controller._lock:
                        self._imu_state = st
                        self._imu_last_ts = st.last_update or 0.0
                        self._imu_ok = bool(st.ok and fresh)

                # Автостоп
                self._check_autostop(moving, direction, center_front_dist,
                                     left_front_dist, right_front_dist,
                                     left_rear_dist, right_rear_dist)

                time.sleep(poll_interval)

            except Exception as e:
                logger.error("Ошибка в мониторинге: %s", e)
                self.controller.reconnect_bus()
                time.sleep(0.5)

        logger.info("Мониторинг датчиков завершен")

    def _check_autostop(self, moving: bool, direction: int,
                        center_front_dist: int, left_front_dist: int,
                        right_front_dist: int, left_rear_dist: int, right_rear_dist: int):
        """Проверка автостопа при обнаружении препятствий"""
        if not moving or direction not in (1, 2):
            return

        if direction == 1:  # движение вперед
            should_stop = False
            if center_front_dist != SENSOR_ERR and center_front_dist < SENSOR_FWD_STOP_CM:
                logger.warning(
                    "АВТОСТОП: препятствие по центру спереди %d см", center_front_dist)
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
            if right_rear_dist != SENSOR_ERR and right_rear_dist < SENSOR_BWD_STOP_CM:
                logger.warning(
                    "АВТОСТОП: препятствие справа сзади %d см", right_rear_dist)
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
