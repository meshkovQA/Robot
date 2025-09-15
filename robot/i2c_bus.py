# i2c_bus.py
from __future__ import annotations

import time
import logging
import threading
import queue
from typing import Protocol, Optional, Dict, Any, Tuple

from robot.config import (
    # базовые
    I2C_AVAILABLE, I2C_BUS, ARDUINO_ADDRESS,
    # нужно для арбитра
    ARDUINO_MEGA_ADDRESS,
    I2C_INTER_DEVICE_DELAY_MS,
    SENSOR_MAX_VALID, SENSOR_ERR,
    CAMERA_PAN_MIN, CAMERA_PAN_MAX, CAMERA_TILT_MIN, CAMERA_TILT_MAX,
)

logger = logging.getLogger(__name__)


# -------------------- Протокол шины и открытие SMBus --------------------

class I2CBus(Protocol):
    def write_i2c_block_data(self, addr: int, cmd: int,
                             vals: list[int]) -> None: ...

    def write_byte(self, addr: int, val: int) -> None: ...
    def read_i2c_block_data(self, addr: int, cmd: int,
                            length: int) -> list[int]: ...


def open_bus() -> Optional[I2CBus]:
    if not I2C_AVAILABLE:
        logger.warning("smbus2 недоступен — работаем в эмуляции")
        return None
    try:
        import smbus2  # type: ignore
        bus = smbus2.SMBus(I2C_BUS)
        logger.info("I2C подключение установлено (bus=%s, addr=0x%02X)",
                    I2C_BUS, ARDUINO_ADDRESS)
        time.sleep(0.2)
        return bus
    except Exception as e:
        logger.error("Не удалось открыть I2C: %s", e)
        return None


# -------------------- Арбитр I2C (единый владелец шины) --------------------

class _SyncResult:
    """Простой future для синхронной отправки команд через очередь."""

    def __init__(self):
        self._evt = threading.Event()
        self._ok: bool = False
        self._err: Optional[BaseException] = None

    def set(self, ok: bool, err: Optional[BaseException] = None):
        self._ok = ok
        self._err = err
        self._evt.set()

    def wait(self, timeout: Optional[float]) -> bool:
        return self._evt.wait(timeout)

    def result(self) -> bool:
        if self._err:
            raise self._err
        return self._ok


class FastI2CController:
    """
    Единственный владелец I2C-шины:
      - Принимает команды (запись) через очередь с приоритетом.
      - Сам планирует чтение UNO/MEGA с небольшим интервалом.
      - После каждой записи делает короткий cooldown, чтобы не врезаться чтением.
    Частоту SCL не трогаем (управляется системой).
    """

    def __init__(self, bus: Optional[I2CBus]):
        self.bus = bus
        self._cmd_q: "queue.Queue[Optional[tuple]]" = queue.Queue(maxsize=32)
        self._cache: Dict[str, Any] = {}
        self._cache_lock = threading.RLock()
        self._running = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    # -------- Публичное API --------

    def stop(self):
        self._running = False
        try:
            self._cmd_q.put_nowait(None)
        except Exception:
            pass
        if self._thr.is_alive():
            self._thr.join(timeout=1.0)

    def write_command_sync(self, data: list[int], address: Optional[int] = None, timeout: float = 0.3) -> bool:
        """
        Синхронная отправка командного блока.
        address: адрес устройства (None = UNO по умолчанию, ARDUINO_MEGA_ADDRESS для MEGA)
        data: данные для отправки
        """
        target_addr = address if address is not None else ARDUINO_ADDRESS
        res = _SyncResult()
        try:
            self._cmd_q.put_nowait(("write", (target_addr, data), res))
        except queue.Full:
            logger.warning("I2C command queue full; executing inline")
            ok = self._do_write(target_addr, data)
            # короткий cooldown после записи
            time.sleep(max(0.015, I2C_INTER_DEVICE_DELAY_MS / 1000.0))
            return ok

        if not res.wait(timeout):
            logger.warning("I2C write timeout (queued)")
            return False
        return res.result()

    def write_uno_command(self, data: list[int], timeout: float = 0.3) -> bool:
        """Отправка команды на UNO"""
        return self.write_command_sync(data, ARDUINO_ADDRESS, timeout)

    def write_mega_command(self, data: list[int], timeout: float = 0.3) -> bool:
        """Отправка команды на MEGA"""
        return self.write_command_sync(data, ARDUINO_MEGA_ADDRESS, timeout)

    def get_cache(self) -> Dict[str, Any]:
        """Вернуть копию кэша датчиков/углов/климата."""
        with self._cache_lock:
            return dict(self._cache)

    # -------- Внутренности --------

    def _loop(self):
        # Частоты опроса датчиков
        uno_period = 0.2   # 200 мс
        mega_period = 0.2  # 200 мс

        last_uno = 0.0
        last_mega = 0.0

        while self._running:
            cycle_start = time.time()

            handled_cmd = False
            # 1) Команды — всегда приоритет
            try:
                item = self._cmd_q.get_nowait()
                if item is None:
                    break
                kind, args, res = item
                try:
                    if kind == "write":
                        addr, data = args
                        ok = self._do_write(addr, data)
                        # cooldown после записи
                        time.sleep(
                            max(0.015, I2C_INTER_DEVICE_DELAY_MS / 1000.0))
                        res.set(ok)
                    handled_cmd = True
                except Exception as e:
                    logger.error("I2C cmd error: %s", e)
                    res.set(False, e)
                    handled_cmd = True
            except queue.Empty:
                pass

            # 2) Плановые чтения (если не было команды прямо сейчас)
            now = time.time()
            if not handled_cmd:
                if now - last_uno >= uno_period:
                    try:
                        d = self._read_uno()
                        if d:
                            with self._cache_lock:
                                self._cache.update({"uno": d, "uno_ts": now})
                    except Exception as e:
                        logger.debug("UNO read error: %s", e)
                    last_uno = time.time()

                if time.time() - last_mega >= mega_period:
                    try:
                        time.sleep(I2C_INTER_DEVICE_DELAY_MS / 1000.0)
                        d = self._read_mega()
                        if d:
                            with self._cache_lock:
                                self._cache.update(
                                    {"mega": d, "mega_ts": time.time()})
                    except Exception as e:
                        logger.debug("MEGA read error: %s", e)
                    last_mega = time.time()

            # 3) Мягкая задержка цикла
            elapsed = time.time() - cycle_start
            time.sleep(max(0.005, 0.02 - elapsed))

    # --- Низкоуровневые операции ---

    def _do_write(self, addr: int, data: list[int]) -> bool:
        if not self.bus:
            logger.info("[I2C emu] write to 0x%02X: %s", addr, data)
            return True
        if len(data) > 1:
            logger.info("I2C block: addr=0x%02X reg=0x%02X data=%s",
                        addr, data)
            self.bus.write_i2c_block_data(addr, 0x00, data)
        else:
            logger.info("I2C byte: addr=0x%02X data=0x%02X", addr, data)
            self.bus.write_byte(addr, data)
        return True

    def _read_uno(self) -> Optional[Dict[str, Any]]:
        """
        Чтение данных от Arduino UNO согласно реальному коду Arduino:
        12 байт: pan(2) + tilt(2) + temp*10(2) + hum*10(2) + left_speed*100(2) + right_speed*100(2)
        """
        if not self.bus:
            # Эмуляция с новыми полями
            return {
                "pan": 90, "tilt": 90,
                "temp": 23.4, "hum": 45.0,
                "left_wheel_speed": 0.0, "right_wheel_speed": 0.0
            }

        try:
            raw = self.bus.read_i2c_block_data(ARDUINO_ADDRESS, 0x10, 12)
            if len(raw) != 12:
                logger.warning("UNO вернул %d байт вместо 12", len(raw))
                return None

            # Парсинг данных согласно структуре Arduino UNO
            pan = (raw[1] << 8) | raw[0]
            tilt = (raw[3] << 8) | raw[2]
            t10 = (raw[5] << 8) | raw[4]
            h10 = (raw[7] << 8) | raw[6]
            l100 = (raw[9] << 8) | raw[8]   # left wheel speed * 100
            r100 = (raw[11] << 8) | raw[10]  # right wheel speed * 100

            # Преобразование signed int16 для температуры, влажности и скоростей
            if t10 >= 32768:
                t10 -= 65536
            if h10 >= 32768:
                h10 -= 65536
            if l100 >= 32768:
                l100 -= 65536
            if r100 >= 32768:
                r100 -= 65536

            # Обработка температуры и влажности (из кода Arduino: -32768 = NAN)
            temp = None if t10 == -32768 else t10 / 10.0
            hum = None if h10 == -32768 else h10 / 10.0

            # Обработка скоростей энкодеров (м/с)
            left_wheel_speed = l100 / 100.0
            right_wheel_speed = r100 / 100.0

            # Валидация углов камеры
            if not (CAMERA_PAN_MIN <= pan <= CAMERA_PAN_MAX):
                pan = None
            if not (CAMERA_TILT_MIN <= tilt <= CAMERA_TILT_MAX):
                tilt = None

            logger.debug("UNO: pan=%s, tilt=%s, temp=%s, hum=%s, left_speed=%.3f, right_speed=%.3f",
                         pan, tilt, temp, hum, left_wheel_speed, right_wheel_speed)

            return {
                "pan": pan, "tilt": tilt,
                "temp": temp, "hum": hum,
                "left_wheel_speed": left_wheel_speed,
                "right_wheel_speed": right_wheel_speed
            }

        except Exception as e:
            logger.error("Ошибка чтения данных с UNO: %s", e)
            return None

    def _read_mega(self) -> Optional[Dict[str, Any]]:
        """
        Чтение данных от Arduino MEGA согласно реальному коду Arduino:
        10 байт: left_front(2) + right_front(2) + left_rear(2) + front_center(2) + rear_right(2)
        """
        if not self.bus:
            # Эмуляция с обновленными полями
            return {
                "left_front": 55, "right_front": 58, "left_rear": 62,
                "front_center": 50, "rear_right": 60
            }

        try:
            raw = self.bus.read_i2c_block_data(ARDUINO_MEGA_ADDRESS, 0x10, 10)
            if len(raw) != 10:
                logger.warning("MEGA вернул %d байт вместо 10", len(raw))
                return None

            # Парсинг данных согласно структуре Arduino MEGA (порядок как в sendSensorData())
            left_front = (raw[1] << 8) | raw[0]      # v0
            right_front = (raw[3] << 8) | raw[2]     # v1
            left_rear = (raw[5] << 8) | raw[4]       # v2
            front_center = (raw[7] << 8) | raw[6]    # v3
            rear_right = (raw[9] << 8) | raw[8]      # v4

            def sanitize_sensor(v: int) -> int:
                # Согласно коду Arduino: если расстояние 0 или >400, возвращается 999
                # Также проверяем на наш SENSOR_MAX_VALID
                if v == 0 or v > SENSOR_MAX_VALID:
                    return SENSOR_ERR
                return v

            left_front = sanitize_sensor(left_front)
            right_front = sanitize_sensor(right_front)
            left_rear = sanitize_sensor(left_rear)
            front_center = sanitize_sensor(front_center)
            rear_right = sanitize_sensor(rear_right)

            logger.debug("MEGA: lfront=%s, rfront=%s, lrear=%s, fcenter=%s, rrear=%s",
                         left_front, right_front, left_rear, front_center, rear_right)

            return {
                "left_front": left_front,
                "right_front": right_front,
                "left_rear": left_rear,
                "front_center": front_center,
                "rear_right": rear_right
            }

        except Exception as e:
            logger.error("Ошибка чтения данных с MEGA: %s", e)
            return None
