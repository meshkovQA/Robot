# controller.py
from __future__ import annotations
import time


import threading
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from robot.config import (
    ARDUINO_ADDRESS, ARDUINO_MEGA_ADDRESS, SENSOR_ERR, SENSOR_MAX_VALID,
    SENSOR_FWD_STOP_CM, SENSOR_BWD_STOP_CM, SENSOR_SIDE_STOP_CM,
    SPEED_MIN, SPEED_MAX, DEFAULT_SPEED, CAMERA_PAN_MIN, CAMERA_PAN_MAX, CAMERA_PAN_DEFAULT,
    CAMERA_TILT_MIN, CAMERA_TILT_MAX, CAMERA_TILT_DEFAULT, CAMERA_STEP_SIZE, KICKSTART_DURATION, KICKSTART_SPEED, MIN_SPEED_FOR_KICKSTART, I2C_INTER_DEVICE_DELAY_MS
)
from robot.i2c_bus import I2CBus, open_bus

logger = logging.getLogger(__name__)


@dataclass
class RobotCommand:
    speed: int = 0
    direction: int = 0  # 0=stop, 1=fwd, 2=bwd, 3=turn_left, 4=turn_right
    pan_angle: int = 90   # угол поворота камеры по горизонтали (0-180)
    tilt_angle: int = 90  # угол наклона камеры по вертикали (50-150)


def _clip_speed(v: int) -> int:
    return max(SPEED_MIN, min(SPEED_MAX, int(v)))


def _clip_pan_angle(angle: int) -> int:
    """Ограничение угла поворота камеры (из конфига)"""
    return max(CAMERA_PAN_MIN, min(CAMERA_PAN_MAX, int(angle)))


def _clip_tilt_angle(angle: int) -> int:
    """Ограничение угла наклона камеры (из конфига)"""
    return max(CAMERA_TILT_MIN, min(CAMERA_TILT_MAX, int(angle)))


def _pack_command(cmd: RobotCommand) -> list[int]:
    """
    Упаковка команды в новый формат (8 байт):
    speed(2) + direction(2) + pan_angle(2) + tilt_angle(2)
    """
    data = []

    # Speed (2 байта, signed int16)
    speed_value = cmd.speed
    data.append(speed_value & 0xFF)           # speed low byte
    data.append((speed_value >> 8) & 0xFF)    # speed high byte

    # Direction (2 байта)
    data.append(cmd.direction & 0xFF)         # direction low byte
    data.append((cmd.direction >> 8) & 0xFF)  # direction high byte

    # Pan angle (2 байта)
    data.append(cmd.pan_angle & 0xFF)         # pan low byte
    data.append((cmd.pan_angle >> 8) & 0xFF)  # pan high byte

    # Tilt angle (2 байта)
    data.append(cmd.tilt_angle & 0xFF)        # tilt low byte
    data.append((cmd.tilt_angle >> 8) & 0xFF)  # tilt high byte

    logger.debug("Пакет команды (8 байт): %s", data)
    return data


class RobotController:
    def __init__(self, bus: Optional[I2CBus] = None):
        self.bus = bus if bus is not None else open_bus()
        self.current_speed = 0
        self.current_pan_angle = CAMERA_PAN_DEFAULT   # из конфига
        self.current_tilt_angle = CAMERA_TILT_DEFAULT  # из конфига
        self.is_moving = False
        self.movement_direction = 0  # 0 stop, 1 fwd, 2 bwd, 3 L, 4 R
        self.last_command_time = time.time()

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._sensor_center_front = SENSOR_ERR
        self._sensor_left_front = SENSOR_ERR
        self._sensor_right_front = SENSOR_ERR
        self._sensor_right_rear = SENSOR_ERR
        self._sensor_left_rear = SENSOR_ERR
        self._env_temp: Optional[float] = None
        self._env_hum: Optional[float] = None
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self._kickstart_timer: Optional[threading.Timer] = None
        self._kickstart_active = False
        self._target_speed = 0
        self._target_direction = 0

    # --------------------------------------------
    # Низкоуровневые I2C операции
    # -------------------------------------------

    def _i2c_write(self, data: list[int], retries: int = 3, backoff: float = 0.02) -> bool:
        """Отправка команды на Arduino через I2C"""
        logger.info("Попытка отправки I2C команды: %s", data)

        if not self.bus:
            logger.warning("[I2C] эмуляция записи: %s", data)
            return True

        try:
            if len(data) > 1:
                logger.info("I2C block: addr=0x%02X reg=0x%02X data=%s",
                            ARDUINO_ADDRESS, data[0], data[1:])
                self.bus.write_i2c_block_data(
                    ARDUINO_ADDRESS, data[0], data[1:])
            else:
                logger.info("I2C byte: addr=0x%02X data=0x%02X",
                            ARDUINO_ADDRESS, data[0])
                self.bus.write_byte(ARDUINO_ADDRESS, data[0])
            return True
        except Exception as e:
            logger.error("I2C write failed: %s", e)
            return False

    def _i2c_read_sensors(self) -> Tuple[int, int, int, int, Optional[float], Optional[float]]:
        """Чтение данных с датчиков и углов камеры"""
        if not self.bus:
            return 25, 30, 90, 90, 23.4, 45.0  # эмуляция

        try:
            # Читаем расширенные данные (12 байт): датчики + углы камеры
            raw = self.bus.read_i2c_block_data(ARDUINO_ADDRESS, 0x10, 12)
            if len(raw) != 12:
                logger.warning("Получено %d байт вместо 12", len(raw))
                return SENSOR_ERR, SENSOR_ERR, self.current_pan_angle, self.current_tilt_angle, None, None

            # Распаковываем little-endian uint16
            center_front = (raw[1] << 8) | raw[0]
            right_rear = (raw[3] << 8) | raw[2]
            pan = (raw[5] << 8) | raw[4]
            tilt = (raw[7] << 8) | raw[6]
            t10 = (raw[9] << 8) | raw[8]
            h10 = (raw[11] << 8) | raw[10]

            # Проверка валидности датчиков
            if center_front > SENSOR_MAX_VALID:
                center_front = SENSOR_ERR
            if right_rear > SENSOR_MAX_VALID:
                right_rear = SENSOR_ERR

            # sign-fix for int16
            if t10 >= 32768:
                t10 -= 65536
            if h10 >= 32768:
                h10 -= 65536
            temp = (None if t10 == -32768 else t10/10.0)
            hum = (None if h10 == -32768 else h10/10.0)

            logger.debug("Датчики: center_front=%d, right_rear=%d, pan=%d, tilt=%d, temp=%s, hum=%s",
                         center_front, right_rear, pan, tilt, temp, hum)
            return center_front, right_rear, pan, tilt, temp, hum

        except Exception as e:
            logger.error("I2C read failed: %s", e)
            return SENSOR_ERR, SENSOR_ERR, self.current_pan_angle, self.current_tilt_angle, None, None

    def _i2c_read_mega_sensors(self) -> Tuple[int, int, int]:
        """Чтение данных с датчиков Arduino Mega"""
        if not self.bus:
            return 25, 30, 35  # эмуляция

        try:
            # Читаем данные с Mega (6 байт): 3 датчика расстояния
            raw = self.bus.read_i2c_block_data(ARDUINO_MEGA_ADDRESS, 0x10, 6)
            if len(raw) != 6:
                logger.warning("Mega: получено %d байт вместо 6", len(raw))
                return SENSOR_ERR, SENSOR_ERR, SENSOR_ERR

            # Распаковываем little-endian uint16
            left_front = (raw[1] << 8) | raw[0]
            right_front = (raw[3] << 8) | raw[2]
            left_rear = (raw[5] << 8) | raw[4]

            # Проверка валидности датчиков
            if left_front > SENSOR_MAX_VALID:
                left_front = SENSOR_ERR
            if right_front > SENSOR_MAX_VALID:
                right_front = SENSOR_ERR
            if left_rear > SENSOR_MAX_VALID:
                left_rear = SENSOR_ERR

            logger.debug("Mega датчики: left_front=%d, right_front=%d, left_rear=%d",
                         left_front, right_front, left_rear)
            return left_front, right_front, left_rear

        except Exception as e:
            logger.error("I2C read Mega failed: %s", e)
            return SENSOR_ERR, SENSOR_ERR, SENSOR_ERR

    # --------------------------------------------
    # Работа с кикстартом для старта движения
    # --------------------------------------------

    def _needs_kickstart(self, speed: int, direction: int) -> bool:
        """Определяет, нужен ли кикстарт"""
        with self._lock:
            direction_changed = (self.movement_direction != direction and
                                 self.movement_direction != 0)
            was_stopped = not self.is_moving
            low_speed = speed < MIN_SPEED_FOR_KICKSTART

        return (was_stopped or direction_changed) and low_speed

    def _apply_kickstart(self, target_speed: int, direction: int):
        """Применяет кикстарт и возвращает к целевой скорости"""
        logger.debug("Применяем кикстарт: %d -> %d на %dмс",
                     target_speed, KICKSTART_SPEED, int(KICKSTART_DURATION * 1000))

        # Отменяем предыдущий таймер если есть
        if self._kickstart_timer and self._kickstart_timer.is_alive():
            self._kickstart_timer.cancel()

        # Сохраняем целевые параметры
        self._target_speed = target_speed
        self._target_direction = direction
        self._kickstart_active = True

        # Отправляем команду кикстарта
        cmd = RobotCommand(
            speed=KICKSTART_SPEED,
            direction=direction,
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        success = self.send_command(cmd)

        if success:
            # Устанавливаем таймер для возврата к целевой скорости
            self._kickstart_timer = threading.Timer(
                KICKSTART_DURATION,
                self._return_to_target_speed
            )
            self._kickstart_timer.start()
        else:
            self._kickstart_active = False

        return success

    def _return_to_target_speed(self):
        """Возвращает скорость к целевому значению после кикстарта"""
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
            logger.error("Не удалось вернуться к целевой скорости %d",
                         self._target_speed)

    def _send_movement_command(self, speed: int, direction: int) -> bool:
        """Отправляет команду движения с кикстартом если нужно"""
        # Проверяем нужен ли кикстарт
        if self._needs_kickstart(speed, direction):
            return self._apply_kickstart(speed, direction)
        else:
            # Обычная команда без кикстарта
            cmd = RobotCommand(
                speed=speed,
                direction=direction,
                pan_angle=self.current_pan_angle,
                tilt_angle=self.current_tilt_angle
            )
            return self.send_command(cmd)

    # --------------------------------------------
    # Отправка команды роботу на Adruino и чтение датчиков
    # --------------------------------------------

    def send_command(self, cmd: RobotCommand) -> bool:
        """Отправка команды роботу"""
        data = _pack_command(cmd)
        with self._lock:
            success = self._i2c_write(data)
            if success:
                self.last_command_time = time.time()
                self.current_pan_angle = cmd.pan_angle
                self.current_tilt_angle = cmd.tilt_angle
            return success

    def read_uno_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        """Получение показаний датчиков Arduino Uno"""
        with self._lock:
            return self._sensor_center_front, self._sensor_right_rear, self._env_temp, self._env_hum

    def read_mega_sensors(self) -> Tuple[int, int, int]:
        """Получение показаний датчиков Arduino Mega"""
        with self._lock:
            return self._sensor_left_front, self._sensor_right_front, self._sensor_left_rear

    def read_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        """Обратная совместимость - возвращает основные датчики Uno"""
        return self.read_uno_sensors()

    def get_camera_angles(self) -> Tuple[int, int]:
        """Получение текущих углов камеры"""
        with self._lock:
            return self.current_pan_angle, self.current_tilt_angle

    def get_status(self) -> dict:
        """Получение полного статуса робота"""
        center_front_dist, right_rear_dist, temp, hum = self.read_uno_sensors()
        left_front_dist, right_front_dist, left_rear_dist = self.read_mega_sensors()
        pan_angle, tilt_angle = self.get_camera_angles()

        with self._lock:
            return {
                "center_front_distance": center_front_dist,
                "left_front_distance": left_front_dist,
                "right_front_distance": right_front_dist,
                "right_rear_distance": right_rear_dist,
                "left_rear_distance": left_rear_dist,
                "obstacles": {
                    "center_front": center_front_dist != SENSOR_ERR and center_front_dist < SENSOR_FWD_STOP_CM,
                    "right_rear": right_rear_dist != SENSOR_ERR and right_rear_dist < SENSOR_BWD_STOP_CM,
                    "left_front": left_front_dist != SENSOR_ERR and left_front_dist < SENSOR_FWD_STOP_CM,
                    "right_front": right_front_dist != SENSOR_ERR and right_front_dist < SENSOR_FWD_STOP_CM,
                    "left_rear": left_rear_dist != SENSOR_ERR and left_rear_dist < SENSOR_BWD_STOP_CM,
                },
                "temperature": temp,
                "humidity": hum,
                "current_speed": self.current_speed,
                "effective_speed": self.get_effective_speed(),  # добавлено
                "kickstart_active": self.is_kickstart_active(),  # добавлено
                "camera": {
                    "pan_angle": pan_angle,
                    "tilt_angle": tilt_angle,
                },
                "is_moving": self.is_moving,
                "movement_direction": self.movement_direction,
                "last_command_time": self.last_command_time,
                "timestamp": time.time(),
            }

    def reconnect_bus(self) -> bool:
        """Переподключение к I2C-шине"""
        try:
            if self.bus:
                try:
                    self.bus.close()
                except Exception:
                    pass
            self.bus = open_bus()
            logger.info("♻️ I2C-шина переподключена успешно")
            return True
        except Exception as e:
            logger.error("❌ Ошибка переподключения I2C: %s", e)
            self.bus = None
            return False

    def shutdown(self):
        """Корректное завершение работы контроллера"""
        logger.info("Начало завершения работы контроллера...")

        # Отменяем кикстарт
        if self._kickstart_timer and self._kickstart_timer.is_alive():
            self._kickstart_timer.cancel()
        self._kickstart_active = False

        self._stop_event.set()

        # Останавливаем робота
        self.stop()
        time.sleep(0.1)

        # Ждем завершения мониторинга
        if self._monitor_thread.is_alive():
            logger.info("Ожидание завершения мониторинга...")
            self._monitor_thread.join(timeout=2.0)

        logger.info("Контроллер завершил работу")

    # --------------------------------------------
    # Движение робота
    # -------------------------------------------

    def move_forward(self, speed: int) -> bool:
        speed = _clip_speed(speed)

        # Читаем все передние датчики
        center_front_dist, *_ = self.read_uno_sensors()
        left_front_dist, right_front_dist, _ = self.read_mega_sensors()

        # Проверяем центральный передний датчик
        if center_front_dist != SENSOR_ERR and center_front_dist < SENSOR_FWD_STOP_CM:
            logger.warning("Вперёд нельзя: препятствие по центру на %d см (порог %d см)",
                           center_front_dist, SENSOR_FWD_STOP_CM)
            return False

        # Проверяем левый передний датчик
        if left_front_dist != SENSOR_ERR and left_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Вперёд нельзя: препятствие слева на %d см (порог %d см)",
                           left_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        # Проверяем правый передний датчик
        if right_front_dist != SENSOR_ERR and right_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Вперёд нельзя: препятствие справа на %d см (порог %d см)",
                           right_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        # ⬇️ отправляем, пока внутреннее состояние ещё "стоп"
        ok = self._send_movement_command(speed, 1)

        if ok:
            with self._lock:
                self.current_speed = speed
                self.is_moving = True
                self.movement_direction = 1
        return ok

    def move_backward(self, speed: int) -> bool:
        speed = _clip_speed(speed)

        # Читаем задние датчики
        _, right_rear_dist, *_ = self.read_uno_sensors()
        _, _, left_rear_dist = self.read_mega_sensors()

        # Проверяем правый задний датчик
        if right_rear_dist != SENSOR_ERR and right_rear_dist < SENSOR_BWD_STOP_CM:
            logger.warning("Назад нельзя: препятствие справа сзади на %d см (порог %d см)",
                           right_rear_dist, SENSOR_BWD_STOP_CM)
            return False

        # Проверяем левый задний датчик
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
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        return self.send_command(cmd)

    def tank_turn_left(self, speed: int) -> bool:
        """Танковый поворот влево"""
        speed = _clip_speed(speed)

        # Читаем боковые датчики
        left_front_dist, right_front_dist, _ = self.read_mega_sensors()

        # При повороте влево правая сторона движется вперед - проверяем правый датчик
        if right_front_dist != SENSOR_ERR and right_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Поворот влево нельзя: препятствие справа на %d см (порог %d см)",
                           right_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        with self._lock:
            self.is_moving = False  # поворот на месте
            self.movement_direction = 3

        cmd = RobotCommand(
            speed=speed,
            direction=3,
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        return self.send_command(cmd)

    def tank_turn_right(self, speed: int) -> bool:
        """Танковый поворот вправо"""
        speed = _clip_speed(speed)

        # Читаем боковые датчики
        left_front_dist, right_front_dist, _ = self.read_mega_sensors()

        # При повороте вправо левая сторона движется вперед - проверяем левый датчик
        if left_front_dist != SENSOR_ERR and left_front_dist < SENSOR_SIDE_STOP_CM:
            logger.warning("Поворот вправо нельзя: препятствие слева на %d см (порог %d см)",
                           left_front_dist, SENSOR_SIDE_STOP_CM)
            return False

        with self._lock:
            self.is_moving = False
            self.movement_direction = 4

        cmd = RobotCommand(
            speed=speed,
            direction=4,
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        return self.send_command(cmd)

    def stop(self) -> bool:
        """Полная остановка"""
        # Отменяем кикстарт если активен
        if self._kickstart_timer and self._kickstart_timer.is_alive():
            self._kickstart_timer.cancel()
        self._kickstart_active = False

        with self._lock:
            self.current_speed = 0
            self.is_moving = False
            self.movement_direction = 0

        cmd = RobotCommand(
            speed=0,
            direction=0,
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        return self.send_command(cmd)

    def is_kickstart_active(self) -> bool:
        """Проверяет, активен ли кикстарт"""
        return self._kickstart_active

    def get_effective_speed(self) -> int:
        """Возвращает текущую эффективную скорость (с учетом кикстарта)"""
        if self._kickstart_active:
            return KICKSTART_SPEED
        return self.current_speed

    # --------------------------------------------
    # Управление камерой
    # --------------------------------------------

    def set_camera_pan(self, angle: int) -> bool:
        """Установка угла поворота камеры по горизонтали"""
        angle = _clip_pan_angle(angle)

        with self._lock:
            speed = self.current_speed
            direction = self.movement_direction
            self.current_pan_angle = angle

        cmd = RobotCommand(
            speed=speed,
            direction=direction,
            pan_angle=angle,
            tilt_angle=self.current_tilt_angle
        )
        return self.send_command(cmd)

    def set_camera_tilt(self, angle: int) -> bool:
        """Установка угла наклона камеры по вертикали"""
        angle = _clip_tilt_angle(angle)

        with self._lock:
            speed = self.current_speed
            direction = self.movement_direction
            self.current_tilt_angle = angle

        cmd = RobotCommand(
            speed=speed,
            direction=direction,
            pan_angle=self.current_pan_angle,
            tilt_angle=angle
        )
        return self.send_command(cmd)

    def set_camera_angles(self, pan: int, tilt: int) -> bool:
        """Установка обоих углов камеры одновременно"""
        pan = _clip_pan_angle(pan)
        tilt = _clip_tilt_angle(tilt)

        with self._lock:
            speed = self.current_speed
            direction = self.movement_direction
            self.current_pan_angle = pan
            self.current_tilt_angle = tilt

        cmd = RobotCommand(
            speed=speed,
            direction=direction,
            pan_angle=pan,
            tilt_angle=tilt
        )
        return self.send_command(cmd)

    def center_camera(self) -> bool:
        """Установка камеры в центральное положение"""
        return self.set_camera_angles(CAMERA_PAN_DEFAULT, CAMERA_TILT_DEFAULT)

    def pan_left(self, step: int = None) -> bool:
        """Повернуть камеру влево на заданный шаг"""
        step = step or CAMERA_STEP_SIZE
        new_angle = self.current_pan_angle + step
        return self.set_camera_pan(new_angle)

    def pan_right(self, step: int = None) -> bool:
        """Повернуть камеру вправо на заданный шаг"""
        step = step or CAMERA_STEP_SIZE
        new_angle = self.current_pan_angle - step
        return self.set_camera_pan(new_angle)

    def tilt_up(self, step: int = None) -> bool:
        """Наклонить камеру вверх на заданный шаг"""
        step = step or CAMERA_STEP_SIZE
        new_angle = self.current_tilt_angle + step
        return self.set_camera_tilt(new_angle)

    def tilt_down(self, step: int = None) -> bool:
        """Наклонить камеру вниз на заданный шаг"""
        step = step or CAMERA_STEP_SIZE
        new_angle = self.current_tilt_angle - step
        return self.set_camera_tilt(new_angle)

    def get_camera_limits(self) -> dict:
        """Получить ограничения углов камеры"""
        return {
            "pan": {"min": CAMERA_PAN_MIN, "max": CAMERA_PAN_MAX, "default": CAMERA_PAN_DEFAULT},
            "tilt": {"min": CAMERA_TILT_MIN, "max": CAMERA_TILT_MAX, "default": CAMERA_TILT_DEFAULT},
            "step_size": CAMERA_STEP_SIZE
        }

    # --------------------------------------
    # Мониторинг состояния робота
    # --------------------------------------

    def _monitor_loop(self):
        """Фоновый мониторинг датчиков и автостоп"""
        poll_interval = 1.0  # 1 секунда - проверенная стабильная частота
        last_sensor_update = 0

        logger.info("Запущен мониторинг датчиков")

        while not self._stop_event.is_set():
            try:
                # Ограничиваем частоту опроса датчиков
                now = time.time()
                if now - last_sensor_update >= poll_interval:
                    # Читаем датчики с обеих Arduino
                    center_front_dist, right_rear_dist, pan, tilt, temp, hum = self._i2c_read_sensors()
                    time.sleep(0.01)  # небольшая пауза между Arduino
                    left_front_dist, right_front_dist, left_rear_dist = self._i2c_read_mega_sensors()

                    # Обновляем кеш датчиков
                    with self._lock:
                        self._sensor_center_front = center_front_dist
                        self._sensor_left_front = left_front_dist
                        self._sensor_right_front = right_front_dist
                        self._sensor_left_rear = left_rear_dist
                        self._sensor_right_rear = right_rear_dist
                        self._env_temp, self._env_hum = temp, hum

                        # Обновляем углы камеры из Arduino (актуальное состояние)
                        if pan != 0 and tilt != 0:  # проверяем что получили валидные данные
                            self.current_pan_angle = pan
                            self.current_tilt_angle = tilt

                        moving = self.is_moving
                        direction = self.movement_direction

                    last_sensor_update = now

                    # Проверка автостопа при движении
                    if moving and direction in (1, 2):
                        # Проверка препятствий при движении вперед
                        if direction == 1:
                            should_stop = False

                            # Центральный передний
                            if (center_front_dist != SENSOR_ERR and
                                    center_front_dist < SENSOR_FWD_STOP_CM):
                                logger.warning("АВТОСТОП: препятствие по центру спереди %d см",
                                               center_front_dist)
                                should_stop = True

                            # Левый передний
                            if (left_front_dist != SENSOR_ERR and
                                    left_front_dist < SENSOR_SIDE_STOP_CM):
                                logger.warning("АВТОСТОП: препятствие слева спереди %d см",
                                               left_front_dist)
                                should_stop = True

                            # Правый передний
                            if (right_front_dist != SENSOR_ERR and
                                    right_front_dist < SENSOR_SIDE_STOP_CM):
                                logger.warning("АВТОСТОП: препятствие справа спереди %d см",
                                               right_front_dist)
                                should_stop = True

                            if should_stop:
                                self.stop()

                        # Проверка препятствий при движении назад
                        elif direction == 2:
                            should_stop = False

                            # Правый задний
                            if (right_rear_dist != SENSOR_ERR and
                                    right_rear_dist < SENSOR_BWD_STOP_CM):
                                logger.warning("АВТОСТОП: препятствие справа сзади %d см",
                                               right_rear_dist)
                                should_stop = True

                            # Левый задний
                            if (left_rear_dist != SENSOR_ERR and
                                    left_rear_dist < SENSOR_BWD_STOP_CM):
                                logger.warning("АВТОСТОП: препятствие слева сзади %d см",
                                               left_rear_dist)
                                should_stop = True

                            if should_stop:
                                self.stop()

                time.sleep(0.2)  # Короткий сон между итерациями

            except Exception as e:
                logger.error("Ошибка в мониторинге: %s", e)
                # Простое переподключение без сложной логики
                self.reconnect_bus()
                time.sleep(1.0)  # Более долгая пауза при ошибке

        logger.info("Мониторинг датчиков завершен")
