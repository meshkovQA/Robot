# controller.py (рефакторинг с компонентами)
from __future__ import annotations

import time
import threading
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from robot.config import (
    SENSOR_ERR, IMU_ENABLED, LCD_ENABLED, LCD_I2C_BUS, LCD_I2C_ADDRESS,
    LCD_UPDATE_INTERVAL, LCD_DEBUG, CAMERA_PAN_DEFAULT, CAMERA_TILT_DEFAULT,
    KICKSTART_SPEED
)
from robot.i2c_bus import I2CBus, open_bus, FastI2CController
from robot.devices.imu import MPU6500

# Импорты компонентов
from robot.controllers.movement_controller import MovementController
from robot.controllers.camera_controller import CameraController
from robot.controllers.kickstart_manager import KickstartManager
from robot.controllers.rgb_controller import RGBController
from robot.controllers.sensor_monitor import SensorMonitor

logger = logging.getLogger(__name__)


@dataclass
class RobotCommand:
    speed: int = 0
    direction: int = 0  # 0=stop, 1=fwd, 2=bwd, 3=turn_left, 4=turn_right
    pan_angle: int = 90
    tilt_angle: int = 90


def _pack_command(cmd: RobotCommand) -> list[int]:
    """
    8 байт LE: speed(2) + direction(2) + pan(2) + tilt(2).
    Первый байт уходит как 'reg' в write_i2c_block_data — протокол не меняем.
    """
    data: list[int] = []
    sv = int(cmd.speed) & 0xFFFF
    dv = int(cmd.direction) & 0xFFFF
    pv = int(cmd.pan_angle) & 0xFFFF
    tv = int(cmd.tilt_angle) & 0xFFFF

    data.extend([sv & 0xFF, (sv >> 8) & 0xFF])
    data.extend([dv & 0xFF, (dv >> 8) & 0xFF])
    data.extend([pv & 0xFF, (pv >> 8) & 0xFF])
    data.extend([tv & 0xFF, (tv >> 8) & 0xFF])

    logger.debug("Пакет команды (8 байт): %s", data)
    return data


class RobotController:
    """
    Основной контроллер робота с компонентной архитектурой.
    Сохраняет прежний API, но использует компоненты внутри.
    """

    def __init__(self, bus: Optional[I2CBus] = None):
        self.bus = bus if bus is not None else open_bus()
        self.fast_i2c = FastI2CController(self.bus)

        # основное состояние
        self.current_speed = 0
        self.current_pan_angle = CAMERA_PAN_DEFAULT
        self.current_tilt_angle = CAMERA_TILT_DEFAULT
        self.is_moving = False
        self.movement_direction = 0
        self.last_command_time = time.time()
        self._lock = threading.RLock()

        # Инициализация компонентов
        self.movement = MovementController(self)
        self.camera = CameraController(self)
        self.kickstart = KickstartManager(self)
        self.rgb = RGBController(self)
        self.sensors = SensorMonitor(self)

        # --- IMU (инициализация перенесена из компонента) ---
        self._imu: Optional[MPU6500] = None
        if IMU_ENABLED:
            try:
                self._imu = MPU6500()
                started = self._imu.start()
                logger.info("IMU %s", "started" if started else "not started")
            except Exception as e:
                logger.error("IMU init error: %s", e)
                self._imu = None

        # --- LCD дисплей ---
        self.lcd_display = None
        if LCD_ENABLED:
            try:
                from robot.devices.lcd_display import RobotLCDDisplay
                self.lcd_display = RobotLCDDisplay(
                    bus=None,
                    address=LCD_I2C_ADDRESS,
                    update_interval=LCD_UPDATE_INTERVAL,
                    bus_num=LCD_I2C_BUS,
                    debug=LCD_DEBUG
                )
                self.lcd_display.start()
                logger.info("LCD дисплей запускается (ленивый режим)")
            except Exception as e:
                logger.error(f"Ошибка при создании LCD дисплея: {e}")
                self.lcd_display = None

    # -------- Приватные методы для компонентов --------

    @property
    def _kickstart_timer(self):
        return self.kickstart._kickstart_timer

    @_kickstart_timer.setter
    def _kickstart_timer(self, value):
        self.kickstart._kickstart_timer = value

    @property
    def _kickstart_active(self):
        return self.kickstart._kickstart_active

    @_kickstart_active.setter
    def _kickstart_active(self, value):
        self.kickstart._kickstart_active = value

    def _send_movement_command(self, speed: int, direction: int) -> bool:
        """Отправка команды движения с проверкой кикстарта"""
        if self.kickstart.needs_kickstart(speed, direction):
            return self.kickstart.apply_kickstart(speed, direction)
        cmd = RobotCommand(
            speed=speed,
            direction=direction,
            pan_angle=self.current_pan_angle,
            tilt_angle=self.current_tilt_angle
        )
        return self.send_command(cmd)

    # -------- Команды и статус --------

    def send_command(self, cmd: RobotCommand) -> bool:
        data = _pack_command(cmd)
        ok = self.fast_i2c.write_command_sync(data, timeout=0.3)
        if ok:
            with self._lock:
                self.last_command_time = time.time()
                self.current_pan_angle = cmd.pan_angle
                self.current_tilt_angle = cmd.tilt_angle
        return ok

    def read_uno_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        return self.sensors.read_uno_sensors()

    def read_mega_sensors(self) -> Tuple[int, int, int]:
        return self.sensors.read_mega_sensors()

    def read_sensors(self) -> Tuple[int, int, Optional[float], Optional[float]]:
        return self.sensors.read_sensors()

    def get_camera_angles(self) -> Tuple[int, int]:
        return self.camera.get_camera_angles()

    def get_status(self) -> dict:
        center_front_dist, right_rear_dist, temp, hum = self.read_uno_sensors()
        left_front_dist, right_front_dist, left_rear_dist = self.read_mega_sensors()
        pan_angle, tilt_angle = self.get_camera_angles()
        imu_block = self.sensors.get_imu_data()

        with self._lock:
            status = {
                "center_front_distance": center_front_dist,
                "left_front_distance": left_front_dist,
                "right_front_distance": right_front_dist,
                "right_rear_distance": right_rear_dist,
                "left_rear_distance": left_rear_dist,
                "obstacles": {
                    "center_front": center_front_dist != SENSOR_ERR and center_front_dist < 20,
                    "right_rear": right_rear_dist != SENSOR_ERR and right_rear_dist < 20,
                    "left_front": left_front_dist != SENSOR_ERR and left_front_dist < 15,
                    "right_front": right_front_dist != SENSOR_ERR and right_front_dist < 15,
                    "left_rear": left_rear_dist != SENSOR_ERR and left_rear_dist < 20,
                },
                "temperature": temp,
                "humidity": hum,
                "imu": imu_block,
                "current_speed": self.current_speed,
                "effective_speed": self.get_effective_speed(),
                "kickstart_active": self.is_kickstart_active(),
                "camera": {"pan_angle": pan_angle, "tilt_angle": tilt_angle},
                "is_moving": self.is_moving,
                "movement_direction": self.movement_direction,
                "last_command_time": self.last_command_time,
                "timestamp": time.time(),
            }

            # Автоматически обновляем LCD текущим статусом
            if self.lcd_display and self.lcd_display.is_active():
                self.lcd_display.update_status(status)

            return status

    # -------- API движения (делегирует в MovementController) --------

    def move_forward(self, speed: int) -> bool:
        return self.movement.move_forward(speed)

    def move_backward(self, speed: int) -> bool:
        return self.movement.move_backward(speed)

    def tank_turn_left(self, speed: int) -> bool:
        return self.movement.tank_turn_left(speed)

    def tank_turn_right(self, speed: int) -> bool:
        return self.movement.tank_turn_right(speed)

    def update_speed(self, new_speed: int) -> bool:
        return self.movement.update_speed(new_speed)

    def stop(self) -> bool:
        return self.movement.stop()

    # -------- API камеры (делегирует в CameraController) --------

    def set_camera_pan(self, angle: int) -> bool:
        return self.camera.set_camera_pan(angle)

    def set_camera_tilt(self, angle: int) -> bool:
        return self.camera.set_camera_tilt(angle)

    def set_camera_angles(self, pan: int, tilt: int) -> bool:
        return self.camera.set_camera_angles(pan, tilt)

    def center_camera(self) -> bool:
        return self.camera.center_camera()

    def pan_left(self, step: int | None = None) -> bool:
        return self.camera.pan_left(step)

    def pan_right(self, step: int | None = None) -> bool:
        return self.camera.pan_right(step)

    def tilt_up(self, step: int | None = None) -> bool:
        return self.camera.tilt_up(step)

    def tilt_down(self, step: int | None = None) -> bool:
        return self.camera.tilt_down(step)

    def get_camera_limits(self) -> dict:
        return self.camera.get_camera_limits()

    # -------- API RGB (делегирует в RGBController) --------

    def set_rgb_color(self, red: int, green: int, blue: int) -> bool:
        return self.rgb.set_rgb_color(red, green, blue)

    def set_rgb_preset(self, preset_name: str) -> bool:
        return self.rgb.set_rgb_preset(preset_name)

    # -------- API кикстарта (делегирует в KickstartManager) --------

    def is_kickstart_active(self) -> bool:
        return self.kickstart.is_active()

    def get_effective_speed(self) -> int:
        return self.kickstart.get_effective_speed()

    # -------- Системные методы --------

    def reconnect_bus(self) -> bool:
        """Переподключение I2C: перезапускаем bus и арбитра."""
        try:
            if self.bus:
                try:
                    self.bus.close()
                except Exception:
                    pass
            self.bus = open_bus()
            self.fast_i2c.stop()
            self.fast_i2c = FastI2CController(self.bus)
            logger.info("♻️ I2C-шина переподключена успешно")
            return True
        except Exception as e:
            logger.error("❌ Ошибка переподключения I2C: %s", e)
            self.bus = None
            return False

    def shutdown(self):
        logger.info("Начало завершения работы контроллера...")

        # Остановка компонентов
        self.kickstart.stop()
        self.sensors.stop()

        self.stop()
        time.sleep(0.05)
        self.fast_i2c.stop()

        # IMU
        if self._imu:
            try:
                self._imu.stop()
            except Exception:
                pass

        # LCD
        if self.lcd_display:
            try:
                self.lcd_display.stop()
            except Exception:
                pass

        logger.info("Контроллер завершил работу")
