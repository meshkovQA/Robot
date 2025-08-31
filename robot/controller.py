# controller.py
from __future__ import annotations

import time
import threading
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from robot.config import (
    SENSOR_ERR, SENSOR_MAX_VALID,
    SENSOR_FWD_STOP_CM, SENSOR_BWD_STOP_CM, SENSOR_SIDE_STOP_CM,
    SPEED_MIN, SPEED_MAX, DEFAULT_SPEED,
    CAMERA_PAN_MIN, CAMERA_PAN_MAX, CAMERA_PAN_DEFAULT,
    CAMERA_TILT_MIN, CAMERA_TILT_MAX, CAMERA_TILT_DEFAULT, CAMERA_STEP_SIZE,
    KICKSTART_DURATION, KICKSTART_SPEED, MIN_SPEED_FOR_KICKSTART, IMU_ENABLED,
    LCD_ENABLED, LCD_I2C_BUS, LCD_I2C_ADDRESS, LCD_UPDATE_INTERVAL, LCD_DEBUG
)
from robot.i2c_bus import I2CBus, open_bus, FastI2CController
from robot.devices.imu import MPU6500, IMUState
from robot.devices.lcd_display import RobotLCDDisplay

logger = logging.getLogger(__name__)


@dataclass
class RobotCommand:
    speed: int = 0
    direction: int = 0  # 0=stop, 1=fwd, 2=bwd, 3=turn_left, 4=turn_right
    pan_angle: int = 90
    tilt_angle: int = 90


def _clip_speed(v: int) -> int:
    return max(SPEED_MIN, min(SPEED_MAX, int(v)))


def _clip_pan_angle(angle: int) -> int:
    return max(CAMERA_PAN_MIN, min(CAMERA_PAN_MAX, int(angle)))


def _clip_tilt_angle(angle: int) -> int:
    return max(CAMERA_TILT_MIN, min(CAMERA_TILT_MAX, int(angle)))


def _pack_command(cmd: RobotCommand) -> list[int]:
    """
    8 байт LE: speed(2) + direction(2) + pan(2) + tilt(2).
    Первый байт уходит как 'reg' в write_i2c_block_data — протокол не меняем.
    """
    data: list[int] = []
    sv = int(cmd.speed) & 0xFFFF
    dv = int(cmd.direction) & 0xFFFF
    pv = int(cmd.pan_angle) & 0xFFFF
    tv = int(cmd.tilt_angle) & 0xFFFF

    data.extend([sv & 0xFF, (sv >> 8) & 0xFF])
    data.extend([dv & 0xFF, (dv >> 8) & 0xFF])
    data.extend([pv & 0xFF, (pv >> 8) & 0xFF])
    data.extend([tv & 0xFF, (tv >> 8) & 0xFF])

    logger.debug("Пакет команды (8 байт): %s", data)
    return data


class RobotController:
    """
    Все I2C-операции делает FastI2CController (единый поток-арбитр).
    Здесь только работа с кэшем датчиков и отправка команд через арбитра.
    """

    def __init__(self, bus: Optional[I2CBus] = None):
        self.bus = bus if bus is not None else open_bus()
        self.fast_i2c = FastI2CController(self.bus)

        # состояние
        self.current_speed = 0
        self.current_pan_angle = CAMERA_PAN_DEFAULT
        self.current_tilt_angle = CAMERA_TILT_DEFAULT
        self.is_moving = False
        self.movement_direction = 0  # 0 stop, 1 fwd, 2 bwd, 3 L, 4 R
        self.last_command_time = time.time()

        # кеш датчиков
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._sensor_center_front = SENSOR_ERR
        self._sensor_left_front = SENSOR_ERR
        self._sensor_right_front = SENSOR_ERR
        self._sensor_right_rear = SENSOR_ERR
        self._sensor_left_rear = SENSOR_ERR
        self._env_temp: Optional[float] = None
        self._env_hum: Optional[float] = None

        # kickstart
        self._kickstart_timer: Optional[threading.Timer] = None
        self._kickstart_active = False
        self._target_speed = 0
        self._target_direction = 0

        # мониторинг (читает только кэш fast_i2c)
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        # ---- IMU ----
        self._imu: Optional[MPU6500] = None
        self._imu_state = IMUState()
        self._imu_ok = False
        self._imu_last_ts = 0.0

        if IMU_ENABLED:
            try:
                self._imu = MPU6500()
                started = self._imu.start()
                logger.info("IMU %s", "started" if started else "not started")
            except Exception as e:
                logger.error("IMU init error: %s", e)
                self._imu = None

        self.lcd_display = None

        # ---- LCD (ленивый) ----
        self.lcd_display = None
        if LCD_ENABLED:
            try:
                # НИЧЕГО не открываем на I²C в конструкторе.
                # Дисплей сам откроет шину и инициализируется в своём фоновом потоке.
                self.lcd_display = RobotLCDDisplay(
                    bus=None,                              # ленивое открытие шины внутри
                    address=LCD_I2C_ADDRESS,
                    update_interval=LCD_UPDATE_INTERVAL,
                    bus_num=LCD_I2C_BUS,                   # берём из конфига
                    debug=LCD_DEBUG                        # берём из конфига
                )
                # start() не блокирует — он только запускает поток
                self.lcd_display.start()
                logger.info("LCD дисплей запускается (ленивый режим)")
            except Exception as e:
                logger.error(f"Ошибка при создании LCD дисплея: {e}")
                self.lcd_display = None
        else:
            logger.info("LCD дисплей отключен в конфигурации")

    # -------- Кикстарт --------

    def _needs_kickstart(self, speed: int, direction: int) -> bool:
        with self._lock:
            direction_changed = (self.movement_direction !=
                                 direction and self.movement_direction != 0)
            was_stopped = not self.is_moving
            low_speed = speed < MIN_SPEED_FOR_KICKSTART
        return (was_stopped or direction_changed) and low_speed

    def _apply_kickstart(self, target_speed: int, direction: int):
        logger.debug("Применяем кикстарт: %d -> %d на %dмс", target_speed,
                     KICKSTART_SPEED, int(KICKSTART_DURATION * 1000))

        if self._kickstart_timer and self._kickstart_timer.is_alive():
            self._kickstart_timer.cancel()

        self._target_speed = target_speed
        self._target_direction = direction
        self._kickstart_active = True

        cmd = RobotCommand(
            speed=KICKSTART_SPEED,
            direction=direction,
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        success = self.send_command(cmd)

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
        cmd = RobotCommand(
            speed=self._target_speed,
            direction=self._target_direction,
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        success = self.send_command(cmd)
        self._kickstart_active = False
        if not success:
            logger.error(
                "Не удалось вернуться к целевой скорости %d", self._target_speed)

    def _send_movement_command(self, speed: int, direction: int) -> bool:
        if self._needs_kickstart(speed, direction):
            return self._apply_kickstart(speed, direction)
        cmd = RobotCommand(
            speed=speed,
            direction=direction,
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        return self.send_command(cmd)

    # -------- Команды и статус --------

    def send_command(self, cmd: RobotCommand) -> bool:
        data = _pack_command(cmd)
        ok = self.fast_i2c.write_command_sync(data, timeout=0.3)
        if ok:
            with self._lock:
                self.last_command_time = time.time()
                self.current_pan_angle = cmd.pan_angle
                self.current_tilt_angle = cmd.tilt_angle
        return ok

    def read_uno_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        with self._lock:
            return self._sensor_center_front, self._sensor_right_rear, self._env_temp, self._env_hum

    def read_mega_sensors(self) -> Tuple[int, int, int]:
        with self._lock:
            return self._sensor_left_front, self._sensor_right_front, self._sensor_left_rear

    def read_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        return self.read_uno_sensors()

    def get_camera_angles(self) -> Tuple[int, int]:
        with self._lock:
            return self.current_pan_angle, self.current_tilt_angle

    def get_status(self) -> dict:
        center_front_dist, right_rear_dist, temp, hum = self.read_uno_sensors()
        left_front_dist, right_front_dist, left_rear_dist = self.read_mega_sensors()
        pan_angle, tilt_angle = self.get_camera_angles()

        with self._lock:
            imu_block = None
            if IMU_ENABLED:
                s = self._imu_state
                imu_block = {
                    "available": True,
                    "ok": bool(self._imu_ok),
                    "roll": s.roll, "pitch": s.pitch, "yaw": s.yaw,
                    "gx": s.gx, "gy": s.gy, "gz": s.gz,
                    "ax": s.ax, "ay": s.ay, "az": s.az,
                    "timestamp": s.last_update or self._imu_last_ts,
                    "whoami": s.whoami,
                }

        with self._lock:
            status = {
                "center_front_distance": center_front_dist,
                "left_front_distance": left_front_dist,
                "right_front_distance": right_front_dist,
                "right_rear_distance": right_rear_dist,
                "left_rear_distance": left_rear_dist,
                "obstacles": {
                    "center_front": center_front_dist != SENSOR_ERR and center_front_dist < SENSOR_FWD_STOP_CM,
                    "right_rear": right_rear_dist != SENSOR_ERR and right_rear_dist < SENSOR_BWD_STOP_CM,
                    "left_front": left_front_dist != SENSOR_ERR and left_front_dist < SENSOR_SIDE_STOP_CM,
                    "right_front": right_front_dist != SENSOR_ERR and right_front_dist < SENSOR_SIDE_STOP_CM,
                    "left_rear": left_rear_dist != SENSOR_ERR and left_rear_dist < SENSOR_BWD_STOP_CM,
                },
                "temperature": temp,
                "humidity": hum,
                "imu": imu_block,
                "current_speed": self.current_speed,
                "effective_speed": self.get_effective_speed(),
                "kickstart_active": self.is_kickstart_active(),
                "camera": {"pan_angle": pan_angle, "tilt_angle": tilt_angle},
                "is_moving": self.is_moving,
                "movement_direction": self.movement_direction,
                "last_command_time": self.last_command_time,
                "timestamp": time.time(),
            }

            # Автоматически обновляем LCD текущим статусом
            if self.lcd_display and self.lcd_display.is_active():
                self.lcd_display.update_status(status)

            return status

    def reconnect_bus(self) -> bool:
        """Переподключение I2C: перезапускаем bus и арбитра."""
        try:
            if self.bus:
                try:
                    self.bus.close()  # type: ignore[attr-defined]
                except Exception:
                    pass
            self.bus = open_bus()
            self.fast_i2c.stop()
            self.fast_i2c = FastI2CController(self.bus)
            logger.info("♻️ I2C-шина переподключена успешно")
            return True
        except Exception as e:
            logger.error("❌ Ошибка переподключения I2C: %s", e)
            self.bus = None
            return False

    def shutdown(self):
        logger.info("Начало завершения работы контроллера...")

        if self._kickstart_timer and self._kickstart_timer.is_alive():
            self._kickstart_timer.cancel()
        self._kickstart_active = False

        self._stop_event.set()
        self.stop()
        time.sleep(0.05)

        if self._monitor_thread.is_alive():
            logger.info("Ожидание завершения мониторинга...")
            self._monitor_thread.join(timeout=1.5)

        self.fast_i2c.stop()

        # IMU
        if self._imu:
            try:
                self._imu.stop()
            except Exception:
                pass
        logger.info("Контроллер завершил работу")

        if hasattr(self, 'lcd_display') and self.lcd_display:
            try:
                self.lcd_display.stop()
            except Exception:
                pass
        logger.info("LCD дисплей остановлен")

    # -------- Движение --------

    def move_forward(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        center_front_dist, *_ = self.read_uno_sensors()
        left_front_dist, right_front_dist, _ = self.read_mega_sensors()

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

        ok = self._send_movement_command(speed, 1)
        if ok:
            with self._lock:
                self.current_speed = speed
                self.is_moving = True
                self.movement_direction = 1
        return ok

    def move_backward(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        _, right_rear_dist, *_ = self.read_uno_sensors()
        _, _, left_rear_dist = self.read_mega_sensors()

        if right_rear_dist != SENSOR_ERR and right_rear_dist < SENSOR_BWD_STOP_CM:
            logger.warning("Назад нельзя: препятствие справа сзади на %d см (порог %d см)",
                           right_rear_dist, SENSOR_BWD_STOP_CM)
            return False
        if left_rear_dist != SENSOR_ERR and left_rear_dist < SENSOR_BWD_STOP_CM:
            logger.warning("Назад нельзя: препятствие слева сзади на %d см (порог %d см)",
                           left_rear_dist, SENSOR_BWD_STOP_CM)
            return False

        ok = self._send_movement_command(speed, 2)
        if ok:
            with self._lock:
                self.current_speed = speed
                self.is_moving = True
                self.movement_direction = 2
        return ok

    def update_speed(self, new_speed: int) -> bool:
        new_speed = _clip_speed(new_speed)
        with self._lock:
            moving = self.is_moving
            direction = self.movement_direction
            self.current_speed = new_speed

        if not moving or direction == 0:
            logger.info(
                "Скорость сохранена (%s), но движение не идёт", new_speed)
            return True

        cmd = RobotCommand(speed=new_speed, direction=direction,
                           pan_angle=self.current_pan_angle, tilt_angle=self.current_tilt_angle)
        return self.send_command(cmd)

    def tank_turn_left(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        left_front_dist, right_front_dist, _ = self.read_mega_sensors()
        if right_front_dist != SENSOR_ERR and right_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Поворот влево нельзя: препятствие справа на %d см (порог %d см)",
                           right_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        with self._lock:
            self.is_moving = False
            self.movement_direction = 3

        cmd = RobotCommand(speed=speed, direction=3,
                           pan_angle=self.current_pan_angle, tilt_angle=self.current_tilt_angle)
        return self.send_command(cmd)

    def tank_turn_right(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        left_front_dist, right_front_dist, _ = self.read_mega_sensors()
        if left_front_dist != SENSOR_ERR and left_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Поворот вправо нельзя: препятствие слева на %d см (порог %d см)",
                           left_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        with self._lock:
            self.is_moving = False
            self.movement_direction = 4

        cmd = RobotCommand(speed=speed, direction=4,
                           pan_angle=self.current_pan_angle, tilt_angle=self.current_tilt_angle)
        return self.send_command(cmd)

    def stop(self) -> bool:
        if self._kickstart_timer and self._kickstart_timer.is_alive():
            self._kickstart_timer.cancel()
        self._kickstart_active = False

        with self._lock:
            self.current_speed = 0
            self.is_moving = False
            self.movement_direction = 0

        cmd = RobotCommand(speed=0, direction=0,
                           pan_angle=self.current_pan_angle, tilt_angle=self.current_tilt_angle)
        return self.send_command(cmd)

    def is_kickstart_active(self) -> bool:
        return self._kickstart_active

    def get_effective_speed(self) -> int:
        return KICKSTART_SPEED if self._kickstart_active else self.current_speed

    # -------- Камера --------

    def set_camera_pan(self, angle: int) -> bool:
        angle = _clip_pan_angle(angle)
        with self._lock:
            speed = self.current_speed
            direction = self.movement_direction
            self.current_pan_angle = angle
        cmd = RobotCommand(speed=speed, direction=direction,
                           pan_angle=angle, tilt_angle=self.current_tilt_angle)
        return self.send_command(cmd)

    def set_camera_tilt(self, angle: int) -> bool:
        angle = _clip_tilt_angle(angle)
        with self._lock:
            speed = self.current_speed
            direction = self.movement_direction
            self.current_tilt_angle = angle
        cmd = RobotCommand(speed=self.current_speed, direction=direction,
                           pan_angle=self.current_pan_angle, tilt_angle=angle)
        return self.send_command(cmd)

    def set_camera_angles(self, pan: int, tilt: int) -> bool:
        pan = _clip_pan_angle(pan)
        tilt = _clip_tilt_angle(tilt)
        with self._lock:
            speed = self.current_speed
            direction = self.movement_direction
            self.current_pan_angle = pan
            self.current_tilt_angle = tilt
        cmd = RobotCommand(speed=speed, direction=direction,
                           pan_angle=pan, tilt_angle=tilt)
        return self.send_command(cmd)

    def center_camera(self) -> bool:
        return self.set_camera_angles(CAMERA_PAN_DEFAULT, CAMERA_TILT_DEFAULT)

    def pan_left(self, step: int | None = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        new_angle = self.current_pan_angle + step
        return self.set_camera_pan(new_angle)

    def pan_right(self, step: int | None = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        new_angle = self.current_pan_angle - step
        return self.set_camera_pan(new_angle)

    def tilt_up(self, step: int | None = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        new_angle = self.current_tilt_angle + step
        return self.set_camera_tilt(new_angle)

    def tilt_down(self, step: int | None = None) -> bool:
        step = step or CAMERA_STEP_SIZE
        new_angle = self.current_tilt_angle - step
        return self.set_camera_tilt(new_angle)

    def get_camera_limits(self) -> dict:
        return {
            "pan": {"min": CAMERA_PAN_MIN, "max": CAMERA_PAN_MAX, "default": CAMERA_PAN_DEFAULT},
            "tilt": {"min": CAMERA_TILT_MIN, "max": CAMERA_TILT_MAX, "default": CAMERA_TILT_DEFAULT},
            "step_size": CAMERA_STEP_SIZE
        }

    # -------- Мониторинг (читает КЭШ fast_i2c) --------

    def _monitor_loop(self):
        """Фоновый мониторинг: обновляет локальный кэш датчиков и делает автостоп.
        ВНИМАНИЕ: на шину не ходит — читает только кэш FastI2CController.
        """
        poll_interval = 0.25
        logger.info("Запущен мониторинг датчиков")

        while not self._stop_event.is_set():
            try:
                cache = self.fast_i2c.get_cache()
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

                with self._lock:
                    self._sensor_center_front = center_front_dist
                    self._sensor_left_front = left_front_dist
                    self._sensor_right_front = right_front_dist
                    self._sensor_left_rear = left_rear_dist
                    self._sensor_right_rear = right_rear_dist
                    self._env_temp, self._env_hum = temp, hum

                    # 0 — допустимо; валидируем по лимитам
                    if pan is not None and (CAMERA_PAN_MIN <= pan <= CAMERA_PAN_MAX):
                        self.current_pan_angle = pan
                    if tilt is not None and (CAMERA_TILT_MIN <= tilt <= CAMERA_TILT_MAX):
                        self.current_tilt_angle = tilt

                    moving = self.is_moving
                    direction = self.movement_direction

                # ---- IMU: копируем актуальное состояние из драйвера ----
                if IMU_ENABLED and self._imu is not None:
                    st = self._imu.get_state()
                    now = time.time()
                    fresh = (now - (st.last_update or 0.0)) < 2.0
                    # сохраним локально (под замком, чтобы брать в get_status)
                    with self._lock:
                        self._imu_state = st
                        self._imu_last_ts = st.last_update or 0.0
                        self._imu_ok = bool(st.ok and fresh)

                # Автостоп
                if moving and direction in (1, 2):
                    if direction == 1:
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
                            self.stop()
                    else:
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
                            self.stop()

                time.sleep(poll_interval)

            except Exception as e:
                logger.error("Ошибка в мониторинге: %s", e)
                self.reconnect_bus()
                time.sleep(0.5)

        logger.info("Мониторинг датчиков завершен")
