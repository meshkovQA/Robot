from __future__ import annotations
import time
import threading
import logging
from typing import Optional

from robot.devices.imu import MPU6500
from robot.controller import RobotController
from robot.config import (
    # Ваша базовая конфигурация
    HDG_HOLD_ENABLED, HDG_KP, HDG_KI, HDG_KD,
    HDG_ERR_DEADZONE_DEG, HDG_MAX_CORR_PULSE_MS, HDG_MIN_GAP_BETWEEN_PULSES_MS,
    HDG_CORR_SPEED,  # используется как fallback, базовая скорость
    UPHILL_BOOST_ENABLED, UPHILL_PITCH_THRESHOLD_DEG, UPHILL_HYSTERESIS_DEG,
    UPHILL_SPEED_MULTIPLIER, UPHILL_MIN_DURATION_S, UPHILL_MAX_SPEED,

    # Новые параметры для более корректных поворотов
    HDG_ERR_HYSTERESIS_DEG,  # гистерезис вокруг deadzone
    HDG_SIGN,                # полярность коррекции (+1/-1)
    HDG_MIN_PULSE_MS,        # минимальная длительность микро-импульса
    # максимальная длительность микро-импульса (мягче старого)
    HDG_MAX_PULSE_MS,
    HDG_MIN_GAP_MS,          # минимальная пауза между микро-импульсами
    HDG_MAX_U_ABS,           # нормировочная «большая ошибка» для шкалирования
    HDG_CORR_BASE_SPEED,     # базовая скорость поворота
    HDG_CORR_KSPEED,         # насколько скорость растёт с ошибкой
    HDG_I_CLAMP,             # ограничение интеграла (anti-windup)
    HDG_YAW_LPF_ALPHA,       # коэффициент сглаживания yaw (0..1)
)

logger = logging.getLogger(__name__)


def _clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v


class HeadingHoldService:
    """
    Удерживает курс во время линейного движения:
    - Применяет короткие «микро-импульсы» танкового поворота, длительность/скорость ∝ ошибке.
    - Сглаживает yaw (LPF), deadzone + гистерезис, анти-windup для I.
    - Во время импульса проверяет препятствия и немедленно тормозит при их появлении.
    - Автобуст на подъёме (pitch).
    """

    def __init__(self, robot: RobotController, imu: MPU6500):
        self.robot = robot
        self.imu = imu
        self.enabled = HDG_HOLD_ENABLED

        self._run = False
        self._thr: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._yaw_ref: Optional[float] = None
        self._yaw_lpf: Optional[float] = None

        self._last_pulse_ts = 0.0
        self._e_int = 0.0
        self._e_prev = 0.0

        self._boost_active = False
        self._boost_started_at = 0.0
        self._saved_speed: Optional[int] = None

    # ------------------------------ Сервис ------------------------------

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
                self._yaw_lpf = None
                self._reset_pid()

   # ------------------------------ Вспомогательные ------------------------------

    def _reset_pid(self):
        self._e_int = 0.0
        self._e_prev = 0.0

    def _maybe_set_yaw_ref(self, yaw_now: float):
        if self._yaw_ref is None:
            self._yaw_ref = yaw_now
            self._reset_pid()

    def _lpf_yaw(self, yaw_now: float) -> float:
        """Простой эксп. фильтр yaw, чтобы убрать шум IMU."""
        if self._yaw_lpf is None:
            self._yaw_lpf = yaw_now
        else:
            a = _clamp(HDG_YAW_LPF_ALPHA, 0.0, 1.0)
            self._yaw_lpf = a * yaw_now + (1.0 - a) * self._yaw_lpf
        return self._yaw_lpf

    def _heading_error(self, yaw_now: float) -> float:
        """Ошибка курса в диапазоне [-180..180]."""
        if self._yaw_ref is None:
            return 0.0
        err = self._yaw_ref - yaw_now
        while err > 180.0:
            err -= 360.0
        while err < -180.0:
            err += 360.0
        return err

    # ------------------------------ Коррекция курса ------------------------------

    def _apply_correction_pulse(self, sign: int, direction: int, u_abs: float):
        """Короткий поворот с периодической проверкой препятствий."""
        now = time.time()
        min_gap_ms = max(HDG_MIN_GAP_BETWEEN_PULSES_MS, HDG_MIN_GAP_MS)
        if (now - self._last_pulse_ts) * 1000.0 < min_gap_ms:
            return
        self._last_pulse_ts = now

        st_before = self.robot.get_status()
        prev_moving = bool(st_before.get("is_moving"))
        prev_speed = int(st_before.get("current_speed", 0))
        obstacles = st_before.get("obstacles", {})

        # если уже видно опасность — тормозим и выходим
        if direction == 1 and (obstacles.get("center_front") or obstacles.get("left_front") or obstacles.get("right_front")):
            self.robot.stop()
            return
        if direction == 2 and (obstacles.get("left_rear") or obstacles.get("right_rear")):
            self.robot.stop()
            return

        # Длительность микро-импульса пропорциональна |u|
        k = min(u_abs / max(HDG_MAX_U_ABS, 1e-3), 1.0)
        dur_ms = int(_clamp(HDG_MIN_PULSE_MS + k * (HDG_MAX_PULSE_MS - HDG_MIN_PULSE_MS),
                            HDG_MIN_PULSE_MS, min(HDG_MAX_PULSE_MS, HDG_MAX_CORR_PULSE_MS)))
        dur_s = dur_ms / 1000.0

        # Скорость поворота: базовая + приращение от ошибки
        base = HDG_CORR_BASE_SPEED if 'HDG_CORR_BASE_SPEED' in globals() else HDG_CORR_SPEED
        speed = int(_clamp(base + HDG_CORR_KSPEED * u_abs, 60, 200))

        # Стартуем поворот
        if sign > 0:
            ok = self.robot.tank_turn_right(speed)
        else:
            ok = self.robot.tank_turn_left(speed)

        if not ok:
            if not ok:
                # не тормозим из-за единичного сбоя I²C — просто пропускаем импульс
                logger.warning(
                    "Correction pulse failed (I2C). Skipping pulse and resuming motion.")
                if prev_moving and prev_speed > 0:
                    if direction == 1:
                        self.robot.move_forward(prev_speed)
                    elif direction == 2:
                        self.robot.move_backward(prev_speed)
                return

        # Во время импульса проверяем препятствия каждые 20мс
        slice_s = 0.02
        elapsed = 0.0
        while elapsed < dur_s:
            time.sleep(slice_s)
            elapsed += slice_s
            st_now = self.robot.get_status()
            obs = st_now.get("obstacles", {})
            if direction == 1 and (obs.get("center_front") or obs.get("left_front") or obs.get("right_front")):
                self.robot.stop()
                break
            if direction == 2 and (obs.get("left_rear") or obs.get("right_rear")):
                self.robot.stop()
                break

        # Возвращаем линейное движение, если шли прямо до импульса
        if prev_moving and prev_speed > 0:
            if direction == 1:
                self.robot.move_forward(prev_speed)
            elif direction == 2:
                self.robot.move_backward(prev_speed)

    # ------------------------------ Автобуст ------------------------------

    def _uphill_boost_logic(self, pitch_deg: float):
        if not UPHILL_BOOST_ENABLED:
            return

        st = self.robot.get_status()
        moving_fwd = st.get("is_moving") and st.get("movement_direction") == 1
        if not moving_fwd:
            if self._boost_active and self._saved_speed is not None:
                self.robot.update_speed(self._saved_speed)
            self._boost_active = False
            self._saved_speed = None
            return

        # Принято: отрицательный pitch = «нос вверх» (если ориентация IMU иная — инвертируйте знак)
        uphill = pitch_deg <= -UPHILL_PITCH_THRESHOLD_DEG
        flat_enough = pitch_deg >= - \
            (UPHILL_PITCH_THRESHOLD_DEG - UPHILL_HYSTERESIS_DEG)

        if uphill and not self._boost_active:
            if self._boost_started_at == 0.0:
                self._boost_started_at = time.time()
            elif time.time() - self._boost_started_at >= UPHILL_MIN_DURATION_S:
                cur = st.get("current_speed", 0)
                boosted = int(
                    _clamp(cur * UPHILL_SPEED_MULTIPLIER, cur, UPHILL_MAX_SPEED))
                self._saved_speed = cur
                self.robot.update_speed(boosted)
                self._boost_active = True
        elif self._boost_active and flat_enough:
            if self._saved_speed is not None:
                self.robot.update_speed(self._saved_speed)
            self._boost_active = False
            self._saved_speed = None
            self._boost_started_at = 0.0
        elif not uphill:
            self._boost_started_at = 0.0

    # ------------------------------ Главный цикл ------------------------------

    def _loop(self):
        period = 0.02  # 50 Hz control loop
        while self._run:
            try:
                s = self.imu.get_state()
                if not s.ok:
                    time.sleep(period)
                    continue

                st = self.robot.get_status()
                direction = st.get("movement_direction")  # 1=fwd, 2=bwd
                moving = st.get("is_moving") and direction in (1, 2)

                if self.enabled and moving:
                    yaw_f = self._lpf_yaw(s.yaw)
                    self._maybe_set_yaw_ref(yaw_f)
                    err = self._heading_error(yaw_f)

                    # deadzone + гистерезис
                    dz = HDG_ERR_DEADZONE_DEG
                    hyst = HDG_ERR_HYSTERESIS_DEG
                    if abs(err) < dz:
                        self._reset_pid()
                        time.sleep(period)
                        self._uphill_boost_logic(s.pitch)
                        continue
                    elif abs(err) < (dz + hyst):
                        # в узкой зоне не накапливаем интеграл, чтобы не «уплывало»
                        self._e_int = 0.0

                    # PID с анти-windup
                    dt = period
                    self._e_int = _clamp(
                        self._e_int + err * dt, -HDG_I_CLAMP, HDG_I_CLAMP)
                    d = (err - self._e_prev) / dt
                    self._e_prev = err

                    u = HDG_KP * err + HDG_KI * self._e_int + HDG_KD * d
                    u *= HDG_SIGN  # быстрый тумблер полярности

                    # Направление коррекции (зеркалим при движении назад)
                    if direction == 1:      # forward
                        sign = 1 if u > 0 else -1
                    else:                   # backward
                        sign = -1 if u > 0 else 1

                    self._apply_correction_pulse(sign, direction, abs(u))
                else:
                    self._yaw_ref = None
                    self._yaw_lpf = None
                    self._reset_pid()

                # Uphill boost
                self._uphill_boost_logic(s.pitch)

            except Exception as e:
                logger.error("HeadingHold loop error: %s", e)

            time.sleep(period)

    # ------------------------------ Статус ------------------------------

    def status(self) -> dict:
        s = self.imu.get_state()
        return {
            "enabled": self.enabled,
            "yaw_ref": self._yaw_ref,
            "imu_ok": s.ok,
            "roll": s.roll,
            "pitch": s.pitch,
            "yaw": s.yaw,
            "gx": s.gx, "gy": s.gy, "gz": s.gz,
            "ax": s.ax, "ay": s.ay, "az": s.az,
            "boost_active": self._boost_active
        }
