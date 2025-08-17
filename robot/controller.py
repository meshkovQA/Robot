# controller.py
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
    steering_angle: int = 90  # угол поворота руля (10-170)
    front_wheels: bool = True
    rear_wheels: bool = True


def _clip_speed(v: int) -> int:
    return max(SPEED_MIN, min(SPEED_MAX, int(v)))


def _clip_steering(angle: int) -> int:
    return max(10, min(170, int(angle)))


def _pack_command(cmd: RobotCommand) -> list[int]:
    """
    Упаковка команды в формат, ожидаемый Arduino (совместимость с рабочим кодом)
    """
    data = []
    speed_value = cmd.speed
    data.append(speed_value & 0xFF)           # speed low byte
    data.append((speed_value >> 8) & 0xFF)    # speed high byte
    data.append(cmd.direction & 0xFF)         # direction low byte
    data.append((cmd.direction >> 8) & 0xFF)  # direction high byte
    data.append(90)  # Фиксированное значение для совместимости (steering)
    data.append(0)   # Фиксированное значение для совместимости
    data.append(1 if cmd.front_wheels else 0)  # front wheels enable
    data.append(1 if cmd.rear_wheels else 0)   # rear wheels enable

    logger.debug("Пакет команды (8 байт): %s", data)
    return data


class RobotController:
    def __init__(self, bus: Optional[I2CBus] = None):
        self.bus = bus if bus is not None else open_bus()
        self.current_speed = 0
        self.current_steering = 90  # центральное положение
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
        """Отправка команды на Arduino через I2C"""
        logger.info("Попытка отправки I2C команды: %s", data)

        if not self.bus:
            logger.warning("[I2C] эмуляция записи: %s", data)
            return True

        for i in range(retries):
            try:
                # Отправляем все данные как block data с первым байтом как регистром
                if len(data) > 1:
                    logger.info("Отправка I2C block data: addr=0x%02X, reg=0x%02X, data=%s",
                                ARDUINO_ADDRESS, data[0], data[1:])
                    self.bus.write_i2c_block_data(
                        ARDUINO_ADDRESS, data[0], data[1:])
                else:
                    logger.info("Отправка I2C byte: addr=0x%02X, data=0x%02X",
                                ARDUINO_ADDRESS, data[0])
                    self.bus.write_byte(ARDUINO_ADDRESS, data[0])
                logger.info("I2C write успешно: %s", data)
                return True
            except Exception as e:
                logger.error("I2C write fail %d/%d: %s", i+1, retries, e)
                time.sleep(backoff * (i + 1))

        logger.error(
            "I2C write полностью провалился после %d попыток", retries)
        return False

    def _i2c_read_sensors(self) -> Tuple[int, int]:
        """Чтение данных с датчиков расстояния"""
        if not self.bus:
            return 25, 30  # эмуляция

        try:
            # Читаем данные датчиков (регистр 0x10 для данных датчиков)
            raw = self.bus.read_i2c_block_data(ARDUINO_ADDRESS, 0x10, 4)
            if len(raw) != 4:
                logger.warning("Получено %d байт вместо 4", len(raw))
                return SENSOR_ERR, SENSOR_ERR

            # Распаковываем little-endian uint16
            front = (raw[1] << 8) | raw[0]
            rear = (raw[3] << 8) | raw[2]

            # Проверка валидности
            if front > SENSOR_MAX_VALID:
                front = SENSOR_ERR
            if rear > SENSOR_MAX_VALID:
                rear = SENSOR_ERR

            logger.debug("Датчики: front=%d, rear=%d", front, rear)
            return front, rear

        except Exception as e:
            logger.error("I2C read failed: %s", e)
            return SENSOR_ERR, SENSOR_ERR

    # ---------- публичный API контроллера ----------
    def send_command(self, cmd: RobotCommand) -> bool:
        """Отправка команды роботу"""
        data = _pack_command(cmd)
        with self._lock:
            success = self._i2c_write(data)
            if success:
                self.last_command_time = time.time()
                self.current_steering = cmd.steering_angle
            return success

    def read_sensors(self) -> Tuple[int, int]:
        """Получение текущих показаний датчиков"""
        with self._lock:
            return self._sensor_front, self._sensor_rear

    def move_forward(self, speed: int) -> bool:
        """Движение вперед с заданной скоростью"""
        speed = _clip_speed(speed)
        with self._lock:
            self.current_speed = speed
            self.is_moving = True
            self.movement_direction = 1

        cmd = RobotCommand(
            speed=speed,
            direction=1,
            steering_angle=self.current_steering
        )
        return self.send_command(cmd)

    def move_backward(self, speed: int) -> bool:
        """Движение назад с заданной скоростью"""
        speed = _clip_speed(speed)
        with self._lock:
            self.current_speed = speed
            self.is_moving = True
            self.movement_direction = 2

        cmd = RobotCommand(
            speed=speed,
            direction=2,
            steering_angle=self.current_steering
        )
        return self.send_command(cmd)

    def tank_turn_left(self, speed: int) -> bool:
        """Танковый поворот влево"""
        speed = _clip_speed(speed)
        with self._lock:
            self.is_moving = False  # поворот на месте
            self.movement_direction = 3

        cmd = RobotCommand(
            speed=speed,
            direction=3,
            steering_angle=self.current_steering
        )
        return self.send_command(cmd)

    def tank_turn_right(self, speed: int) -> bool:
        """Танковый поворот вправо"""
        speed = _clip_speed(speed)
        with self._lock:
            self.is_moving = False
            self.movement_direction = 4

        cmd = RobotCommand(
            speed=speed,
            direction=4,
            steering_angle=self.current_steering
        )
        return self.send_command(cmd)

    def stop(self) -> bool:
        """Полная остановка"""
        with self._lock:
            self.current_speed = 0
            self.is_moving = False
            self.movement_direction = 0

        cmd = RobotCommand(
            speed=0,
            direction=0,
            steering_angle=self.current_steering
        )
        return self.send_command(cmd)

    def update_speed(self, new_speed: int) -> bool:
        """Обновление скорости без изменения направления"""
        new_speed = _clip_speed(new_speed)
        with self._lock:
            moving = self.is_moving
            direction = self.movement_direction
            self.current_speed = new_speed

        if not moving or direction == 0:
            logger.info(
                "Скорость сохранена (%s), но движение не идёт", new_speed)
            return True

        cmd = RobotCommand(
            speed=new_speed,
            direction=direction,
            steering_angle=self.current_steering
        )
        return self.send_command(cmd)

    def get_status(self) -> dict:
        """Получение полного статуса робота"""
        front_dist, rear_dist = self.read_sensors()
        with self._lock:
            return {
                "front_distance": front_dist,
                "rear_distance": rear_dist,
                "obstacles": {
                    "front": front_dist != SENSOR_ERR and front_dist < SENSOR_FWD_STOP_CM,
                    "rear": rear_dist != SENSOR_ERR and rear_dist < SENSOR_BWD_STOP_CM,
                },
                "sensor_error": front_dist == SENSOR_ERR or rear_dist == SENSOR_ERR,
                "current_speed": self.current_speed,
                "current_steering": self.current_steering,
                "is_moving": self.is_moving,
                "movement_direction": self.movement_direction,
                "last_command_time": self.last_command_time,
                "timestamp": time.time(),
            }

    def shutdown(self):
        """Корректное завершение работы контроллера"""
        logger.info("Начало завершения работы контроллера...")
        self._stop_event.set()

        # Останавливаем робота
        self.stop()
        time.sleep(0.1)

        # Ждем завершения мониторинга
        if self._monitor_thread.is_alive():
            logger.info("Ожидание завершения мониторинга...")
            self._monitor_thread.join(timeout=2.0)

        logger.info("Контроллер завершил работу")

    # ---------- мониторинг препятствий + кэш сенсоров ----------
    def _monitor_loop(self):
        """Фоновый мониторинг датчиков и автостоп"""
        poll_interval = 0.2  # 200мс
        last_sensor_update = 0

        logger.info("Запущен мониторинг датчиков")

        while not self._stop_event.is_set():
            try:
                # Ограничиваем частоту опроса датчиков
                now = time.time()
                if now - last_sensor_update >= poll_interval:
                    front_dist, rear_dist = self._i2c_read_sensors()

                    with self._lock:
                        self._sensor_front, self._sensor_rear = front_dist, rear_dist
                        moving = self.is_moving
                        direction = self.movement_direction

                    last_sensor_update = now

                    # Проверка автостопа
                    if moving and direction in (1, 2):
                        if (direction == 1 and
                            front_dist != SENSOR_ERR and
                                front_dist < SENSOR_FWD_STOP_CM):
                            logger.warning(
                                "АВТОСТОП: препятствие спереди %d см", front_dist)
                            self.stop()

                        elif (direction == 2 and
                              rear_dist != SENSOR_ERR and
                              rear_dist < SENSOR_BWD_STOP_CM):
                            logger.warning(
                                "АВТОСТОП: препятствие сзади %d см", rear_dist)
                            self.stop()

                time.sleep(0.05)  # Короткий сон между итерациями

            except Exception as e:
                logger.error("Ошибка в мониторинге: %s", e)
                time.sleep(1.0)  # Более долгая пауза при ошибке

        logger.info("Мониторинг датчиков завершен")
