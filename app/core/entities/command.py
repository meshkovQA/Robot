# app/core/entities/command.py
"""Базовые команды и сущности робота"""

from dataclasses import dataclass
from typing import Optional
import logging

from robot.config import (
    SPEED_MIN, SPEED_MAX,
    CAMERA_PAN_MIN, CAMERA_PAN_MAX, CAMERA_PAN_DEFAULT,
    CAMERA_TILT_MIN, CAMERA_TILT_MAX, CAMERA_TILT_DEFAULT
)

logger = logging.getLogger(__name__)


@dataclass
class RobotCommand:
    """Команда для отправки на Arduino"""
    speed: int = 0
    direction: int = 0  # 0=stop, 1=forward, 2=backward, 3=left, 4=right
    pan_angle: int = CAMERA_PAN_DEFAULT
    tilt_angle: int = CAMERA_TILT_DEFAULT

    def __post_init__(self):
        """Валидация и обрезка значений"""
        self.speed = max(SPEED_MIN, min(SPEED_MAX, self.speed))
        self.direction = max(0, min(4, self.direction))
        self.pan_angle = max(CAMERA_PAN_MIN, min(
            CAMERA_PAN_MAX, self.pan_angle))
        self.tilt_angle = max(CAMERA_TILT_MIN, min(
            CAMERA_TILT_MAX, self.tilt_angle))

    def pack_to_bytes(self) -> list[int]:
        """Упаковка команды в байты для I2C"""
        data: list[int] = []

        # Упаковываем в Little Endian формат
        sv = int(self.speed) & 0xFFFF
        dv = int(self.direction) & 0xFFFF
        pv = int(self.pan_angle) & 0xFFFF
        tv = int(self.tilt_angle) & 0xFFFF

        data.extend([sv & 0xFF, (sv >> 8) & 0xFF])
        data.extend([dv & 0xFF, (dv >> 8) & 0xFF])
        data.extend([pv & 0xFF, (pv >> 8) & 0xFF])
        data.extend([tv & 0xFF, (tv >> 8) & 0xFF])

        logger.debug(f"Packed command: {data}")
        return data
