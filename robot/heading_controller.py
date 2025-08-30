# heading_controller.py
from __future__ import annotations
import time
import threading
import logging
from typing import Optional

from robot.controller import RobotController
from robot.config import (
    HDG_HOLD_ENABLED, HDG_KP, HDG_KI, HDG_KD,
    HDG_ERR_DEADZONE_DEG, HDG_MAX_CORR_PULSE_MS, HDG_MIN_GAP_BETWEEN_PULSES_MS,
    HDG_CORR_SPEED,
    UPHILL_BOOST_ENABLED, UPHILL_PITCH_THRESHOLD_DEG, UPHILL_HYSTERESIS_DEG,
    UPHILL_SPEED_MULTIPLIER, UPHILL_MIN_DURATION_S, UPHILL_MAX_SPEED
)

logger = logging.getLogger(__name__)


def _clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v


class HeadingHoldService:
    """
    Удержание курса короткими импульсами + автобуст на подъёме.
    Работает поверх ЕДИНОГО статуса от RobotController.get_status().
    """

    def __init__(self, robot: RobotController):
        self.robot = robot
        self.enabled = HDG_HOLD_ENABLED

        self._run = False
        self._thr: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._yaw_ref: Optional[float] = None
        self._last_pulse_ts = 0.0
        self._e_int = 0.0
        self._e_prev = 0.0

        self._boost_active = False
        self._boost_started_at = 0.0
        self._saved_speed: Optional[int] = None

        self._last_moving = False
        self._last_direction = 0  # 0,1,2

    # ---------- lifecycle ----------
    def start(self):
        if self._run:
            return
        self._run = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        logger.info("HeadingHold service started")

    def stop(self):
        self._run = False
        if self._thr:
            self._thr.join(timeout=1.5)
        logger.info("HeadingHold service stopped")

    def enable(self, on: bool):
        with self._lock:
            self.enabled = on
            if not on:
                self._yaw_ref = None
                self._reset_pid()

    # ---------- helpers ----------
    def _reset_pid(self):
        self._e_int = 0.0
        self._e_prev = 0.0

    def _maybe_set_yaw_ref(self, yaw_now: float, moving: bool, direction: int):
        """
        Устанавливаем/переустанавливаем референсный курс:
        - при первом входе в движение
        - при смене направления (1 <-> 2)
        """
        need_reset = False
        if self._yaw_ref is None:
            need_reset = True
        if moving and (not self._last_moving):
            need_reset = True
        if direction in (1, 2) and (direction != self._last_direction):
            # при смене направления пересобьём референс
            need_reset = True

        if need_reset and moving and direction in (1, 2):
            self._yaw_ref = yaw_now
            self._reset_pid()
            logger.info(f"[HDG] Референсный курс установлен: {yaw_now:.1f}°")

        self._last_moving = moving
        self._last_direction = direction

    def _heading_error(self, yaw_now: float) -> float:
        """Ошибка курса в диапазоне [-180..180]"""
        if self._yaw_ref is None:
            return 0.0
        err = self._yaw_ref - yaw_now
        while err > 180.0:
            err -= 360.0
        while err < -180.0:
            err += 360.0
        return err

    def _apply_correction_pulse(self, u_pid: float, direction: int):
        """Короткая коррекция курса на основе PID-выхода."""
        now = time.time()
        if (now - self._last_pulse_ts) * 1000.0 < HDG_MIN_GAP_BETWEEN_PULSES_MS:
            return

        st_before = self.robot.get_status()
        prev_moving = bool(st_before.get("is_moving"))
        prev_speed = int(st_before.get("current_speed", 0))
        obstacles = st_before.get("obstacles", {})

        # защита от столкновений
        if direction == 1:  # вперёд
            if obstacles.get("center_front") or obstacles.get("left_front") or obstacles.get("right_front"):
                logger.warning("[HDG] Коррекция отменена: препятствие впереди")
                return
        elif direction == 2:  # назад
            if obstacles.get("left_rear") or obstacles.get("right_rear"):
                logger.warning("[HDG] Коррекция отменена: препятствие сзади")
                return

        self._last_pulse_ts = now

        # знак коррекции
        if direction == 1:   # движемся вперёд
            turn_right = (u_pid > 0)    # положительная ошибка -> вправо
        else:                 # движемся назад (инверсия)
            turn_right = (u_pid < 0)

        pulse_duration_ms = min(abs(u_pid) * 10.0, HDG_MAX_CORR_PULSE_MS)
        pulse_duration_s = pulse_duration_ms / 1000.0

        if turn_right:
            ok = self.robot.tank_turn_right(HDG_CORR_SPEED)
            logger.debug(
                f"[HDG] Пульс вправо, u={u_pid:.2f}, t={pulse_duration_ms:.0f}мс")
        else:
            ok = self.robot.tank_turn_left(HDG_CORR_SPEED)
            logger.debug(
                f"[HDG] Пульс влево, u={u_pid:.2f}, t={pulse_duration_ms:.0f}мс")

        if not ok:
            logger.warning("[HDG] Поворот не удался (I2C)")
            return

        time.sleep(pulse_duration_s)

        # возвращаем прямолинейное движение, если оно было
        if prev_moving and prev_speed > 0:
            if direction == 1:
                self.robot.move_forward(prev_speed)
            elif direction == 2:
                self.robot.move_backward(prev_speed)

    def _uphill_boost_logic(self, pitch_deg: float):
        """Авто-boost на подъёме (нос вверх => pitch отрицательный в вашей системе)."""
        if not UPHILL_BOOST_ENABLED:
            return

        st = self.robot.get_status()
        moving_fwd = st.get("is_moving") and st.get("movement_direction") == 1
        if not moving_fwd:
            # откат буста, если стоим/едем не вперёд
            if self._boost_active and self._saved_speed is not None:
                self.robot.update_speed(self._saved_speed)
            self._boost_active = False
            self._saved_speed = None
            self._boost_started_at = 0.0
            return

        uphill = pitch_deg <= -UPHILL_PITCH_THRESHOLD_DEG
        flat_enough = pitch_deg >= - \
            (UPHILL_PITCH_THRESHOLD_DEG - UPHILL_HYSTERESIS_DEG)

        if uphill and not self._boost_active:
            if self._boost_started_at == 0.0:
                self._boost_started_at = time.time()
            elif time.time() - self._boost_started_at >= UPHILL_MIN_DURATION_S:
                cur = int(st.get("current_speed", 0))
                boosted = int(
                    _clamp(cur * UPHILL_SPEED_MULTIPLIER, cur, UPHILL_MAX_SPEED))
                if boosted > cur:
                    self._saved_speed = cur
                    self.robot.update_speed(boosted)
                    self._boost_active = True
                    logger.info(f"[UPHILL] Буст: {cur} → {boosted}")
        elif self._boost_active and flat_enough:
            if self._saved_speed is not None:
                self.robot.update_speed(self._saved_speed)
                logger.info(f"[UPHILL] Откат буста: {self._saved_speed}")
            self._boost_active = False
            self._saved_speed = None
            self._boost_started_at = 0.0
        elif not uphill:
            self._boost_started_at = 0.0

    # ---------- main loop ----------
    def _loop(self):
        period = 0.10  # 10 Гц: достаточно и не грузит CPU/I2C
        while self._run:
            try:
                status = self.robot.get_status()
                imu = (status.get("imu") or {}) if status else {}
                imu_ok = bool(imu.get("ok"))
                yaw = float(imu.get("yaw", 0.0))
                pitch = float(imu.get("pitch", 0.0))
                gz = float(imu.get("gz", 0.0))  # deg/s

                direction = status.get("movement_direction", 0)
                moving = bool(status.get("is_moving")) and direction in (1, 2)

                # автобуст по pitch — работает независимо от удержания курса
                if imu_ok:
                    self._uphill_boost_logic(pitch)

                if not (self.enabled and imu_ok and moving):
                    # при потере условий обнулим реф.курс чтобы не «тащить» старый
                    self._maybe_set_yaw_ref(yaw, moving, direction)
                    time.sleep(period)
                    continue

                # установка/пересброс yaw_ref
                self._maybe_set_yaw_ref(yaw, moving, direction)
                err = self._heading_error(yaw)

                # deadzone
                if abs(err) < HDG_ERR_DEADZONE_DEG:
                    self._reset_pid()
                    time.sleep(period)
                    continue

                # PID: используем гироскоп для D-слагаемого, чтобы уменьшить шум
                dt = period
                self._e_int += err * dt
                max_integral = 50.0
                self._e_int = _clamp(self._e_int, -max_integral, max_integral)

                # error = ref - yaw; d(error)/dt = - yaw_rate
                e_deriv = -gz

                u_pid = HDG_KP * err + HDG_KI * self._e_int + HDG_KD * e_deriv
                logger.debug(
                    f"[HDG] err={err:.2f}°, P={HDG_KP*err:.2f} I={HDG_KI*self._e_int:.2f} D={HDG_KD*e_deriv:.2f} -> u={u_pid:.2f}")

                self._e_prev = err

                self._apply_correction_pulse(u_pid, direction)

            except Exception as e:
                logger.error("HeadingHold loop error: %s", e)

            time.sleep(period)

    # ---------- debug/status ----------
    def status(self) -> dict:
        st = self.robot.get_status()
        imu = st.get("imu") or {}
        yaw = imu.get("yaw")
        err = self._heading_error(yaw) if imu.get(
            "ok") and yaw is not None else None
        gz = imu.get("gz", 0.0)
        return {
            "enabled": self.enabled,
            "yaw_ref": self._yaw_ref,
            "current_yaw": yaw,
            "heading_error": err,
            "pid_terms": {
                "P": HDG_KP * (err or 0.0),
                "I": HDG_KI * self._e_int,
                "D": HDG_KD * (-gz),
                "integral": self._e_int,
            },
            "imu_ok": bool(imu.get("ok")),
            "roll": imu.get("roll"), "pitch": imu.get("pitch"), "yaw": imu.get("yaw"),
            "boost_active": self._boost_active
        }
