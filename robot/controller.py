from __future__ import annotations
import time
import struct
import threading
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from .config import (
    ARDUINO_ADDRESS, SENSOR_ERR, SENSOR_MAX_VALID,
    SENSOR_FWD_STOP_CM, SENSOR_BWD_STOP_CM,
    SPEED_MIN, SPEED_MAX, DEFAULT_SPEED,
)
from .i2c_bus import I2CBus, open_bus

logger = logging.getLogger(__name__)


@dataclass
class RobotCommand:
    speed: int = 0
    direction: int = 0  # 0=stop, 1=fwd, 2=bwd, 3=turn_left, 4=turn_right
    front_wheels: bool = True
    rear_wheels: bool = True


def _clip_speed(v: int) -> int:
    return max(SPEED_MIN, min(SPEED_MAX, int(v)))


def _pack_command(cmd: RobotCommand) -> list[int]:
    # speed: uint16, direction: uint16, pad1, pad2, front, rear, checksum
    payload = struct.pack(
        "<HHBBBB",
        cmd.speed & 0xFFFF,
        cmd.direction & 0xFFFF,
        90, 0,
        1 if cmd.front_wheels else 0,
        1 if cmd.rear_wheels else 0,
    )
    checksum = sum(payload) & 0xFF
    return list(payload + bytes([checksum]))


class RobotController:
    def __init__(self, bus: Optional[I2CBus] = None):
        self.bus = bus if bus is not None else open_bus()
        self.current_speed = 0
        self.is_moving = False
        self.movement_direction = 0  # 0 stop, 1 fwd, 2 bwd, 3 L, 4 R
        self.last_command_time = time.time()

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._sensor_front = SENSOR_ERR
        self._sensor_rear = SENSOR_ERR
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    # ---------- низкоуровневые I2C ----------
    def _i2c_write(self, data: list[int], retries: int = 3, backoff: float = 0.02) -> bool:
        if not self.bus:
            logger.debug("[I2C] эмуляция записи: %s", data)
            return True
        for i in range(retries):
            try:
                self.bus.write_i2c_block_data(
                    ARDUINO_ADDRESS, data[0], data[1:])
                return True
            except Exception as e:
                logger.warning("I2C write fail %d/%d: %s", i+1, retries, e)
                time.sleep(backoff * (i + 1))
        return False

    def _i2c_read_sensors(self) -> Tuple[int, int]:
        if not self.bus:
            return 25, 30  # эмуляция
        try:
            # ожидаем 4 байта: F_L F_H R_L R_H (little-endian)
            raw = self.bus.read_i2c_block_data(ARDUINO_ADDRESS, 0, 4)
            if len(raw) != 4:
                return SENSOR_ERR, SENSOR_ERR
            f = (raw[1] << 8) | raw[0]
            r = (raw[3] << 8) | raw[2]
            if f > SENSOR_MAX_VALID or r > SENSOR_MAX_VALID:
                return SENSOR_ERR, SENSOR_ERR
            return f, r
        except Exception as e:
            logger.error("I2C read failed: %s", e)
            return SENSOR_ERR, SENSOR_ERR

    # ---------- публичный API контроллера ----------
    def send_command(self, cmd: RobotCommand) -> bool:
        data = _pack_command(cmd)
        with self._lock:
            ok = self._i2c_write(data)
            if ok:
                self.last_command_time = time.time()
            return ok

    def read_sensors(self) -> Tuple[int, int]:
        with self._lock:
            return self._sensor_front, self._sensor_rear

    def move_forward(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        with self._lock:
            self.current_speed = speed
            self.is_moving = True
            self.movement_direction = 1
        return self.send_command(RobotCommand(speed=speed, direction=1))

    def move_backward(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        with self._lock:
            self.current_speed = speed
            self.is_moving = True
            self.movement_direction = 2
        return self.send_command(RobotCommand(speed=speed, direction=2))

    def tank_turn_left(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        with self._lock:
            self.is_moving = False  # поворот на месте — считаем как не-линейное движение
            self.movement_direction = 3
        return self.send_command(RobotCommand(speed=speed, direction=3))

    def tank_turn_right(self, speed: int) -> bool:
        speed = _clip_speed(speed)
        with self._lock:
            self.is_moving = False
            self.movement_direction = 4
        return self.send_command(RobotCommand(speed=speed, direction=4))

    def stop(self) -> bool:
        with self._lock:
            self.current_speed = 0
            self.is_moving = False
            self.movement_direction = 0
        return self.send_command(RobotCommand(speed=0, direction=0))

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
        return self.send_command(RobotCommand(speed=new_speed, direction=direction))

    def get_status(self) -> dict:
        f, r = self.read_sensors()
        with self._lock:
            return {
                "front_distance": f,
                "rear_distance": r,
                "obstacles": {
                    "front": f != SENSOR_ERR and f < SENSOR_FWD_STOP_CM,
                    "rear":  r != SENSOR_ERR and r < SENSOR_BWD_STOP_CM,
                },
                "sensor_error": f == SENSOR_ERR or r == SENSOR_ERR,
                "current_speed": self.current_speed,
                "is_moving": self.is_moving,
                "movement_direction": self.movement_direction,
                "timestamp": time.time(),
            }

    def shutdown(self):
        self._stop_event.set()
        self.stop()
        logger.info("Контроллер завершает работу")
        # дождаться фонового потока
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)

    # ---------- мониторинг препятствий + кэш сенсоров ----------
    def _monitor_loop(self):
        # периодический опрос датчиков + автостоп по препятствиям
        poll_interval = 0.1
        while not self._stop_event.is_set():
            f, r = self._i2c_read_sensors()
            with self._lock:
                self._sensor_front, self._sensor_rear = f, r
                moving = self.is_moving
                direction = self.movement_direction
            try:
                if moving and direction in (1, 2):
                    if direction == 1 and f != SENSOR_ERR and f < SENSOR_FWD_STOP_CM:
                        logger.warning("Автостоп: препятствие спереди %scм", f)
                        self.stop()
                    elif direction == 2 and r != SENSOR_ERR and r < SENSOR_BWD_STOP_CM:
                        logger.warning("Автостоп: препятствие сзади %scм", r)
                        self.stop()
            except Exception as e:
                logger.error("Ошибка в автостопе: %s", e)
            time.sleep(poll_interval)
