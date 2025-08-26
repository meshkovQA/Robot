from __future__ import annotations
import time
import math
import threading
import logging
from typing import Optional

from robot.config import (
    IMU_ENABLED, IMU_I2C_BUS, IMU_ADDRESS, IMU_WHOAMI,
    IMU_CALIBRATION_TIME, IMU_LOOP_HZ, IMU_COMPLEMENTARY_ALPHA
)

logger = logging.getLogger(__name__)

WHO_AM_I_REG = 0x75
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H = 0x43


def _open_bus():
    try:
        import smbus2
        return smbus2.SMBus(IMU_I2C_BUS)
    except Exception as e:
        logger.error("IMU: failed to open I2C bus: %s", e)
        return None


def _read_word(bus, addr, reg):
    hi = bus.read_byte_data(addr, reg)
    lo = bus.read_byte_data(addr, reg + 1)
    val = (hi << 8) | lo
    if val >= 0x8000:
        val = -((65535 - val) + 1)
    return val


class IMUState:
    def __init__(self):
        self.roll = 0.0   # deg
        self.pitch = 0.0  # deg
        self.yaw = 0.0    # deg (integrated; will drift)
        self.gx = 0.0     # deg/s
        self.gy = 0.0
        self.gz = 0.0
        self.ax = 0.0     # g
        self.ay = 0.0
        self.az = 0.0
        self.ok = False
        self.whoami = None
        self.last_update = 0.0


class MPU6500:
    def __init__(self):
        self._bus = None
        self._addr = IMU_ADDRESS
        self._state = IMUState()
        self._gx_bias = 0.0
        self._gy_bias = 0.0
        self._gz_bias = 0.0
        self._alpha = IMU_COMPLEMENTARY_ALPHA
        self._run = False
        self._thr: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    def start(self) -> bool:
        if not IMU_ENABLED:
            logger.info("IMU disabled in config")
            return False
        self._bus = _open_bus()
        if not self._bus:
            return False

        try:
            who = self._bus.read_byte_data(self._addr, WHO_AM_I_REG)
            self._state.whoami = who
            if who != IMU_WHOAMI:
                logger.warning("IMU WHO_AM_I mismatch: got 0x%02X, expected 0x%02X",
                               who, IMU_WHOAMI)
            # Wake up device
            self._bus.write_byte_data(self._addr, PWR_MGMT_1, 0)
        except Exception as e:
            logger.error("IMU init failed: %s", e)
            return False

        self._calibrate_gyro()
        self._run = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        logger.info("IMU started")
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

    def _calibrate_gyro(self):
        t_end = time.time() + IMU_CALIBRATION_TIME
        cnt = 0
        sx = sy = sz = 0.0
        while time.time() < t_end:
            gx = _read_word(self._bus, self._addr, GYRO_XOUT_H) / 131.0
            gy = _read_word(self._bus, self._addr, GYRO_XOUT_H + 2) / 131.0
            gz = _read_word(self._bus, self._addr, GYRO_XOUT_H + 4) / 131.0
            sx += gx
            sy += gy
            sz += gz
            cnt += 1
            time.sleep(0.002)
        if cnt > 0:
            self._gx_bias = sx / cnt
            self._gy_bias = sy / cnt
            self._gz_bias = sz / cnt
        logger.info("IMU gyro bias: gx=%.3f gy=%.3f gz=%.3f deg/s",
                    self._gx_bias, self._gy_bias, self._gz_bias)

    def _loop(self):
        dt = 1.0 / max(10, IMU_LOOP_HZ)
        last = time.time()
        # initialize roll/pitch from accel
        try:
            ax = _read_word(self._bus, self._addr, ACCEL_XOUT_H) / 16384.0
            ay = _read_word(self._bus, self._addr, ACCEL_XOUT_H + 2) / 16384.0
            az = _read_word(self._bus, self._addr, ACCEL_XOUT_H + 4) / 16384.0
            roll_acc = math.degrees(math.atan2(ay, az))
            pitch_acc = math.degrees(math.atan2(-ax, math.sqrt(ay*ay + az*az)))
            with self._lock:
                self._state.roll = roll_acc
                self._state.pitch = pitch_acc
        except Exception:
            pass

        while self._run:
            now = time.time()
            dt = max(1e-4, now - last)
            last = now
            try:
                ax = _read_word(self._bus, self._addr, ACCEL_XOUT_H) / 16384.0
                ay = _read_word(self._bus, self._addr,
                                ACCEL_XOUT_H + 2) / 16384.0
                az = _read_word(self._bus, self._addr,
                                ACCEL_XOUT_H + 4) / 16384.0
                gx = _read_word(self._bus, self._addr, GYRO_XOUT_H) / 131.0
                gy = _read_word(self._bus, self._addr, GYRO_XOUT_H + 2) / 131.0
                gz = _read_word(self._bus, self._addr, GYRO_XOUT_H + 4) / 131.0

                gx -= self._gx_bias
                gy -= self._gy_bias
                gz -= self._gz_bias

                roll_acc = math.degrees(math.atan2(ay, az))
                pitch_acc = math.degrees(
                    math.atan2(-ax, math.sqrt(ay*ay + az*az)))

                with self._lock:
                    # complementary
                    self._state.roll = self._alpha * \
                        (self._state.roll + gx*dt) + (1-self._alpha)*roll_acc
                    self._state.pitch = self._alpha * \
                        (self._state.pitch + gy*dt) + (1-self._alpha)*pitch_acc
                    # yaw: integrate gyro Z (will drift)
                    self._state.yaw += gz * dt
                    # wrap
                    if self._state.yaw > 180.0:
                        self._state.yaw -= 360.0
                    if self._state.yaw < -180.0:
                        self._state.yaw += 360.0

                    self._state.gx, self._state.gy, self._state.gz = gx, gy, gz
                    self._state.ax, self._state.ay, self._state.az = ax, ay, az
                    self._state.ok = True
                    self._state.last_update = now
            except Exception as e:
                logger.error("IMU loop error: %s", e)
                time.sleep(0.01)

            # pacing
            sleep_left = (1.0 / IMU_LOOP_HZ) - (time.time() - now)
            if sleep_left > 0:
                time.sleep(sleep_left)

    def get_state(self) -> IMUState:
        with self._lock:
            return self._state
