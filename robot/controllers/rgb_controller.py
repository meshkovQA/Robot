# robot/controllers/rgb_controller.py
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from robot.controller import RobotController

logger = logging.getLogger(__name__)


class RGBController:
    """Компонент управления RGB светодиодами"""

    def __init__(self, controller: 'RobotController'):
        self.controller = controller

    def set_rgb_color(self, red: int, green: int, blue: int) -> bool:
        """Установить цвет RGB светодиода на Arduino Mega"""
        red = max(0, min(255, int(red)))
        green = max(0, min(255, int(green)))
        blue = max(0, min(255, int(blue)))

        # Отправляем на MEGA адрес
        data = [red, green, blue]
        try:
            # Используем прямую отправку на MEGA адрес через fast_i2c
            from robot.config import ARDUINO_MEGA_ADDRESS
            if hasattr(self.controller.fast_i2c, 'bus') and self.controller.fast_i2c.bus:
                self.controller.fast_i2c.bus.write_i2c_block_data(
                    ARDUINO_MEGA_ADDRESS, 0x10, data)
                logger.info(
                    f"RGB команда отправлена на Mega: R={red}, G={green}, B={blue}")
                return True
        except Exception as e:
            logger.error(f"Ошибка отправки RGB команды: {e}")
            return False
        return False

    def set_rgb_preset(self, preset_name: str) -> bool:
        """Установить предустановленный цвет RGB"""
        presets = {
            'red': (255, 0, 0),
            'green': (0, 255, 0),
            'blue': (0, 0, 255),
            'white': (255, 255, 255),
            'yellow': (255, 255, 0),
            'purple': (255, 0, 255),
            'cyan': (0, 255, 255),
            'orange': (255, 165, 0),
            'pink': (255, 192, 203),
            'off': (0, 0, 0)
        }

        if preset_name.lower() in presets:
            r, g, b = presets[preset_name.lower()]
            return self.set_rgb_color(r, g, b)
        return False
