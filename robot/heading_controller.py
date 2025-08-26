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
    Maintains straight heading while moving forward by sending short tank-turn pulses
    when yaw error exceeds threshold. Also applies uphill speed boost using pitch angle.
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

    def _heading_error(self, yaw_now: float) -> float:
        if self._yaw_ref is None:
            return 0.0
        err = self._yaw_ref - yaw_now
        # normalize to [-180..180]
        while err > 180.0:
            err -= 360.0
        while err < -180.0:
            err += 360.0
        return err

    def _apply_correction_pulse(self, sign: int, direction: int):
        now = time.time()
        if (now - self._last_pulse_ts) * 1000.0 < HDG_MIN_GAP_BETWEEN_PULSES_MS:
            return
        self._last_pulse_ts = now

        st_before = self.robot.get_status()
        prev_moving = bool(st_before.get("is_moving"))
        prev_speed = int(st_before.get("current_speed", 0))

        dur_s = HDG_MAX_CORR_PULSE_MS / 1000.0
        speed = HDG_CORR_SPEED

        if sign > 0:
            self.robot.tank_turn_right(speed)
        else:
            self.robot.tank_turn_left(speed)

        time.sleep(dur_s)

        # возвращаемся к движению в том же направлении
        if prev_moving and prev_speed > 0:
            if direction == 1:
                self.robot.move_forward(prev_speed)
            elif direction == 2:
                self.robot.move_backward(prev_speed)

    def _uphill_boost_logic(self, pitch_deg: float):
        if not UPHILL_BOOST_ENABLED:
            return

        st = self.robot.get_status()
        moving_fwd = st.get("is_moving") and st.get("movement_direction") == 1
        if not moving_fwd:
            # restore if needed
            if self._boost_active and self._saved_speed is not None:
                self.robot.update_speed(self._saved_speed)
            self._boost_active = False
            self._saved_speed = None
            return

        # uphill detection: pitch negative when nose up (depends on IMU orientation; invert if needed)
        uphill = pitch_deg <= -UPHILL_PITCH_THRESHOLD_DEG
        flat_enough = pitch_deg >= - \
            (UPHILL_PITCH_THRESHOLD_DEG - UPHILL_HYSTERESIS_DEG)

        if uphill and not self._boost_active:
            # start timing
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
            # stop boost
            if self._saved_speed is not None:
                self.robot.update_speed(self._saved_speed)
            self._boost_active = False
            self._saved_speed = None
            self._boost_started_at = 0.0
        elif not uphill:
            # reset arming timer
            self._boost_started_at = 0.0

    def _loop(self):
        period = 0.02  # 50 Hz control loop
        while self._run:
            try:
                s = self.imu.get_state()
                if not s.ok:
                    time.sleep(period)
                    continue

                # Heading hold only when moving forward
                st = self.robot.get_status()
                # 1=fwd, 2=bwd
                direction = st.get("movement_direction")
                moving = st.get("is_moving") and direction in (1, 2)

                if self.enabled and moving:
                    self._maybe_set_yaw_ref(s.yaw)
                    err = self._heading_error(s.yaw)

                    if abs(err) < HDG_ERR_DEADZONE_DEG:
                        self._reset_pid()
                    else:
                        dt = period
                        self._e_int += err * dt
                        d = (err - self._e_prev) / dt
                        self._e_prev = err

                        u = HDG_KP*err + HDG_KI*self._e_int + HDG_KD*d

                        # Направление коррекции:
                        # при движении ВПЕРЁД: u>0 -> крутим ВПРАВО (sign=+1), u<0 -> ВЛЕВО (sign=-1)
                        # при движении НАЗАД: зеркалим направление
                        if direction == 1:      # forward
                            sign = 1 if u > 0 else -1
                        else:                   # backward
                            sign = -1 if u > 0 else 1

                        self._apply_correction_pulse(sign, direction)
                else:
                    self._yaw_ref = None
                    self._reset_pid()

                # Uphill boost
                self._uphill_boost_logic(s.pitch)

            except Exception as e:
                logger.error("HeadingHold loop error: %s", e)

            time.sleep(period)

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
