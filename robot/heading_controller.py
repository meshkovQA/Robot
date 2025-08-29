from __future__ import annotations
import time
import threading
import logging
from typing import Optional

from robot.devices.imu import MPU6500
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
    Простое удержание курса короткими импульсами поворота
    """

    def __init__(self, robot: RobotController, imu: MPU6500):
        self.robot = robot
        self.imu = imu
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

    def _reset_pid(self):
        self._e_int = 0.0
        self._e_prev = 0.0

    def _maybe_set_yaw_ref(self, yaw_now: float):
        if self._yaw_ref is None:
            self._yaw_ref = yaw_now
            self._reset_pid()
            logger.info(f"Установлен референсный курс: {yaw_now:.1f}°")

    def _heading_error(self, yaw_now: float) -> float:
        """Ошибка курса в диапазоне [-180..180]"""
        if self._yaw_ref is None:
            return 0.0
        err = self._yaw_ref - yaw_now
        # Нормализация к [-180..180]
        while err > 180.0:
            err -= 360.0
        while err < -180.0:
            err += 360.0
        return err

    def _apply_correction_pulse(self, u_pid: float, direction: int):
        """Короткая коррекция курса на основе PID выхода"""
        now = time.time()
        if (now - self._last_pulse_ts) * 1000.0 < HDG_MIN_GAP_BETWEEN_PULSES_MS:
            return

        # Сохраняем состояние до коррекции
        st_before = self.robot.get_status()
        prev_moving = bool(st_before.get("is_moving"))
        prev_speed = int(st_before.get("current_speed", 0))

        # Проверяем препятствия перед коррекцией
        obstacles = st_before.get("obstacles", {})
        if direction == 1:  # движение вперед
            if obstacles.get("center_front") or obstacles.get("left_front") or obstacles.get("right_front"):
                logger.warning(
                    "Коррекция курса отменена - препятствие впереди")
                return
        elif direction == 2:  # движение назад
            if obstacles.get("left_rear") or obstacles.get("right_rear"):
                logger.warning("Коррекция курса отменена - препятствие сзади")
                return

        self._last_pulse_ts = now

        # Определяем направление коррекции на основе PID выхода
        if direction == 1:  # движение вперед
            if u_pid > 0:  # нужен поворот вправо
                turn_right = True
            else:  # нужен поворот влево
                turn_right = False
        else:  # движение назад - инвертируем логику
            if u_pid > 0:  # нужен поворот влево при движении назад
                turn_right = False
            else:  # нужен поворот вправо при движении назад
                turn_right = True

        # Длительность импульса пропорциональна величине PID выхода
        # масштабируем PID выход
        pulse_duration_ms = min(abs(u_pid) * 10, HDG_MAX_CORR_PULSE_MS)
        pulse_duration_s = pulse_duration_ms / 1000.0

        # Выполняем короткий поворот
        if turn_right:
            success = self.robot.tank_turn_right(HDG_CORR_SPEED)
            logger.debug(
                f"Коррекция вправо, PID={u_pid:.2f}, длительность={pulse_duration_ms:.0f}мс")
        else:
            success = self.robot.tank_turn_left(HDG_CORR_SPEED)
            logger.debug(
                f"Коррекция влево, PID={u_pid:.2f}, длительность={pulse_duration_ms:.0f}мс")

        if not success:
            logger.warning("Коррекция курса не удалась (I2C ошибка)")
            return

        # Пауза для поворота
        time.sleep(pulse_duration_s)

        # Возвращаемся к прямолинейному движению
        if prev_moving and prev_speed > 0:
            if direction == 1:
                self.robot.move_forward(prev_speed)
            elif direction == 2:
                self.robot.move_backward(prev_speed)

    def _uphill_boost_logic(self, pitch_deg: float):
        """Автобуст скорости на подъеме"""
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

        # Подъем: pitch отрицательный когда нос вверх
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
                logger.info(f"Автобуст активирован: {cur} → {boosted}")
        elif self._boost_active and flat_enough:
            if self._saved_speed is not None:
                self.robot.update_speed(self._saved_speed)
                logger.info(f"Автобуст отключен: {self._saved_speed}")
            self._boost_active = False
            self._saved_speed = None
            self._boost_started_at = 0.0
        elif not uphill:
            self._boost_started_at = 0.0

    def _loop(self):
        period = 0.1  # 10 Hz - снижена частота для меньшей нагрузки на I2C
        while self._run:
            try:
                s = self.imu.get_state()
                if not s.ok:
                    time.sleep(period)
                    continue

                st = self.robot.get_status()
                direction = st.get("movement_direction")  # 1=вперед, 2=назад
                moving = st.get("is_moving") and direction in (1, 2)

                if self.enabled and moving:
                    self._maybe_set_yaw_ref(s.yaw)
                    error_deg = self._heading_error(s.yaw)

                    # Deadzone - не корректируем маленькие отклонения
                    if abs(error_deg) < HDG_ERR_DEADZONE_DEG:
                        self._reset_pid()
                    else:
                        # Правильный PID расчет
                        dt = period
                        self._e_int += error_deg * dt  # интеграл
                        e_deriv = (error_deg - self._e_prev) / \
                            dt  # производная
                        self._e_prev = error_deg

                        # PID формула
                        u_pid = HDG_KP * error_deg + HDG_KI * self._e_int + HDG_KD * e_deriv

                        # Ограничиваем интеграл (анти-windup)
                        max_integral = 50.0  # максимальное накопление интеграла
                        self._e_int = max(-max_integral,
                                          min(max_integral, self._e_int))

                        logger.debug(
                            f"Отклонение: {error_deg:.1f}°, PID: P={HDG_KP*error_deg:.2f} I={HDG_KI*self._e_int:.2f} D={HDG_KD*e_deriv:.2f} = {u_pid:.2f}")

                        self._apply_correction_pulse(u_pid, direction)

                # Автобуст на подъеме
                self._uphill_boost_logic(s.pitch)

            except Exception as e:
                logger.error("HeadingHold loop error: %s", e)

            time.sleep(period)

    def status(self) -> dict:
        s = self.imu.get_state()
        error = self._heading_error(s.yaw) if s.ok else None
        return {
            "enabled": self.enabled,
            "yaw_ref": self._yaw_ref,
            "current_yaw": s.yaw,
            "heading_error": error,
            "pid_terms": {
                "P": HDG_KP * error if error else 0,
                "I": HDG_KI * self._e_int,
                "D": HDG_KD * (error - self._e_prev) if error else 0,
                "integral": self._e_int,
            },
            "imu_ok": s.ok,
            "roll": s.roll,
            "pitch": s.pitch,
            "yaw": s.yaw,
            "boost_active": self._boost_active
        }
