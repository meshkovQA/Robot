from __future__ import annotations

import time
import math
import threading
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from robot.config import (
    IMU_ENABLED, IMU_I2C_BUS, IMU_ADDRESS, IMU_WHOAMI,
    IMU_CALIBRATION_TIME, IMU_LOOP_HZ, IMU_COMPLEMENTARY_ALPHA,
)

logger = logging.getLogger(__name__)

# ---- Регистры MPU-6500 / MPU-6050 совместимые ----
WHO_AM_I_REG = 0x75
PWR_MGMT_1 = 0x6B
SMPLRT_DIV = 0x19
CONFIG_REG = 0x1A
GYRO_CONFIG = 0x1B
ACCEL_CONFIG = 0x1C
ACCEL_CONFIG2 = 0x1D

ACCEL_XOUT_H = 0x3B   # читаем блоком 14 байт: Ax..Az, Temp, Gx..Gz

# Масштабы по умолчанию после сброса:
#   Accel FS = ±2g  -> 16384 LSB/g
#   Gyro  FS = ±250°/s -> 131 LSB/(°/s)
ACCEL_LSB_PER_G = 16384.0
GYRO_LSB_PER_DPS = 131.0


def _open_bus():
    """Открытие I2C-шины для IMU (отдельно от арбитра UNO/MEGA)."""
    try:
        import smbus2
        return smbus2.SMBus(IMU_I2C_BUS)
    except Exception as e:
        logger.error("IMU: failed to open I2C bus %s: %s", IMU_I2C_BUS, e)
        return None


def _read_block(bus, addr: int, reg: int, length: int) -> Optional[list[int]]:
    """Безопасное блочное чтение (возвращает None при ошибке)."""
    try:
        return bus.read_i2c_block_data(addr, reg, length)
    except Exception as e:
        logger.error(
            "IMU: read block failed reg=0x%02X len=%d: %s", reg, length, e)
        return None


def _twos_compliment_16(hi: int, lo: int) -> int:
    val = (hi << 8) | lo
    if val >= 0x8000:
        val = -((0xFFFF - val) + 1)
    return val


@dataclass
class IMUState:
    roll: float = 0.0     # deg
    pitch: float = 0.0    # deg
    yaw: float = 0.0      # deg (интегрированная; утекает)
    gx: float = 0.0       # deg/s
    gy: float = 0.0
    gz: float = 0.0
    ax: float = 0.0       # g
    ay: float = 0.0
    az: float = 0.0
    ok: bool = False
    whoami: Optional[int] = None
    last_update: float = 0.0


class MPU6500:
    """
    Новая логика:
      - единый поток-воркер читает IMU блоком 14 байт по I2C (меньше транзакций),
      - калибровка гироскопа по среднему за заданное время,
      - комплементарный фильтр (alpha из конфига) для roll/pitch,
      - интеграция yaw с ограничением [-180..180],
      - авто-восстановление при ошибках чтения/шины,
      - методы zero_yaw(), set_alpha(), set_loop_rate().
    """

    def __init__(self):
        self._bus = None
        self._addr = IMU_ADDRESS
        self._state = IMUState()
        self._gx_bias = 0.0
        self._gy_bias = 0.0
        self._gz_bias = 0.0
        self._alpha = float(IMU_COMPLEMENTARY_ALPHA)
        self._target_hz = max(10, int(IMU_LOOP_HZ))
        self._run = False
        self._thr: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._last_ok_ts = 0.0

    # -------- Публичное API --------

    def start(self) -> bool:
        if not IMU_ENABLED:
            logger.info("IMU disabled in config")
            return False
        if not self._open_and_init():
            return False

        if not self._calibrate_gyro(IMU_CALIBRATION_TIME):
            logger.warning(
                "IMU: calibration skipped/failed — продолжаем с нулевыми смещениями")

        self._run = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        logger.info("IMU started (addr=0x%02X, hz=%d)",
                    self._addr, self._target_hz)
        return True

    def stop(self):
        self._run = False
        if self._thr:
            self._thr.join(timeout=1.5)
        try:
            if self._bus:
                self._bus.close()
        except Exception:
            pass

    def get_state(self) -> IMUState:
        with self._lock:
            # возвращаем тот же объект (как было), чтобы не ломать внешние вызовы
            return self._state

    def zero_yaw(self):
        """Сброс текущего курса (выставить yaw=0)."""
        with self._lock:
            self._state.yaw = 0.0

    def set_alpha(self, alpha: float):
        """Обновить коэффициент комплементарного фильтра (0..1)."""
        alpha = float(alpha)
        if not (0.0 <= alpha <= 1.0):
            raise ValueError("alpha must be in [0, 1]")
        self._alpha = alpha

    def set_loop_rate(self, hz: int):
        """Изменить целевую частоту цикла чтения IMU."""
        hz = int(hz)
        self._target_hz = max(10, min(500, hz))  # здравый предел

    # -------- Внутреннее --------

    def _open_and_init(self) -> bool:
        self._bus = _open_bus()
        if not self._bus:
            return False

        try:
            who = self._bus.read_byte_data(self._addr, WHO_AM_I_REG)
            self._state.whoami = who
            if IMU_WHOAMI is not None and who != IMU_WHOAMI:
                logger.warning(
                    "IMU WHO_AM_I mismatch: got 0x%02X, expected 0x%02X", who, IMU_WHOAMI)

            # Выводим из сна
            self._bus.write_byte_data(self._addr, PWR_MGMT_1, 0x00)
            time.sleep(0.03)

            # Базовая конфигурация (достаточно мягкая фильтрация, дефолтные масштабы):
            # DLPF_CFG=3 (~44 Hz для гироскопа), SMPLRT_DIV такт от регистров по умолчанию
            try:
                self._bus.write_byte_data(self._addr, CONFIG_REG, 0x03)
                self._bus.write_byte_data(
                    self._addr, ACCEL_CONFIG2, 0x03)  # Accel DLPF ~44 Hz
                # масштабы не меняем (±250 dps и ±2g)
            except Exception as e:
                logger.debug("IMU optional cfg skipped: %s", e)

            # Инициализируем roll/pitch из акселя
            block = _read_block(self._bus, self._addr, ACCEL_XOUT_H, 14)
            if block and len(block) == 14:
                ax = _twos_compliment_16(block[0], block[1]) / ACCEL_LSB_PER_G
                ay = _twos_compliment_16(block[2], block[3]) / ACCEL_LSB_PER_G
                az = _twos_compliment_16(block[4], block[5]) / ACCEL_LSB_PER_G
                roll_acc = math.degrees(math.atan2(ay, az))
                pitch_acc = math.degrees(
                    math.atan2(-ax, math.sqrt(ay*ay + az*az)))
                with self._lock:
                    self._state.roll = roll_acc
                    self._state.pitch = pitch_acc
        except Exception as e:
            logger.error("IMU init failed: %s", e)
            try:
                if self._bus:
                    self._bus.close()
            except Exception:
                pass
            self._bus = None
            return False

        return True

    def _calibrate_gyro(self, duration_s: float) -> bool:
        """Короткая калибровка гиросмещения по среднему (робот неподвижен)."""
        if not self._bus:
            return False

        t_end = time.time() + max(0.1, float(duration_s))
        cnt = 0
        sx = sy = sz = 0.0

        while time.time() < t_end:
            block = _read_block(self._bus, self._addr, ACCEL_XOUT_H, 14)
            if not block or len(block) != 14:
                time.sleep(0.005)
                continue
            gx = _twos_compliment_16(block[8],  block[9]) / GYRO_LSB_PER_DPS
            gy = _twos_compliment_16(block[10], block[11]) / GYRO_LSB_PER_DPS
            gz = _twos_compliment_16(block[12], block[13]) / GYRO_LSB_PER_DPS
            sx += gx
            sy += gy
            sz += gz
            cnt += 1
            time.sleep(0.002)

        if cnt == 0:
            return False

        self._gx_bias = sx / cnt
        self._gy_bias = sy / cnt
        self._gz_bias = sz / cnt
        logger.info("IMU gyro bias: gx=%.3f gy=%.3f gz=%.3f deg/s",
                    self._gx_bias, self._gy_bias, self._gz_bias)
        return True

    def _loop(self):
        """Основной цикл: блочное чтение, фильтрация, авто-восстановление."""
        # Защитимся от слишком длинных dt (сон/лаг)
        max_dt = 0.2
        target_period = 1.0 / float(self._target_hz)
        last = time.time()

        while self._run:
            now = time.time()
            dt = now - last
            if dt <= 0.0 or dt > max_dt:
                dt = target_period
            last = now

            try:
                if not self._bus:
                    # Пытаемся пересоздать шину
                    if not self._open_and_init():
                        time.sleep(0.1)
                        continue

                block = _read_block(self._bus, self._addr, ACCEL_XOUT_H, 14)
                if not block or len(block) != 14:
                    raise IOError("bad block")

                ax = _twos_compliment_16(block[0],  block[1]) / ACCEL_LSB_PER_G
                ay = _twos_compliment_16(block[2],  block[3]) / ACCEL_LSB_PER_G
                az = _twos_compliment_16(block[4],  block[5]) / ACCEL_LSB_PER_G
                gx = _twos_compliment_16(
                    block[8],  block[9]) / GYRO_LSB_PER_DPS
                gy = _twos_compliment_16(
                    block[10], block[11]) / GYRO_LSB_PER_DPS
                gz = _twos_compliment_16(
                    block[12], block[13]) / GYRO_LSB_PER_DPS

                # вычитаем смещения гироскопа
                gx -= self._gx_bias
                gy -= self._gy_bias
                gz -= self._gz_bias

                # аксельные углы
                roll_acc = math.degrees(math.atan2(ay, az))
                pitch_acc = math.degrees(
                    math.atan2(-ax, math.sqrt(ay*ay + az*az)))

                with self._lock:
                    a = self._alpha
                    # complementary filter для roll/pitch
                    self._state.roll = a * \
                        (self._state.roll + gx * dt) + (1.0 - a) * roll_acc
                    self._state.pitch = a * \
                        (self._state.pitch + gy * dt) + (1.0 - a) * pitch_acc

                    # yaw — чистая интеграция gz (дрейфует)
                    self._state.yaw += gz * dt
                    if self._state.yaw > 180.0:
                        self._state.yaw -= 360.0
                    elif self._state.yaw < -180.0:
                        self._state.yaw += 360.0

                    self._state.gx, self._state.gy, self._state.gz = gx, gy, gz
                    self._state.ax, self._state.ay, self._state.az = ax, ay, az
                    self._state.ok = True
                    self._state.last_update = now

                self._last_ok_ts = now

            except Exception as e:
                logger.error("IMU loop error: %s", e)
                with self._lock:
                    self._state.ok = False
                # мягкая попытка переподключиться
                try:
                    if self._bus:
                        self._bus.close()
                except Exception:
                    pass
                self._bus = None
                time.sleep(0.05)

            # Регулируем частоту цикла
            target_period = 1.0 / float(self._target_hz)
            sleep_left = target_period - (time.time() - now)
            if sleep_left > 0:
                time.sleep(sleep_left)
