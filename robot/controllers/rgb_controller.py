# robot/controllers/rgb_controller.py
import logging
from typing import TYPE_CHECKING

from robot.config import ARDUINO_MEGA_ADDRESS

if TYPE_CHECKING:
    from robot.controller import RobotController

logger = logging.getLogger(__name__)


class RGBController:
    """Компонент управления RGB светодиодами через Arduino MEGA"""

    # Константы из Arduino кода MEGA
    REG_RGB = 0x10

    def __init__(self, controller: 'RobotController'):
        self.controller = controller

    def set_rgb_color(self, red: int, green: int, blue: int) -> bool:
        """
        Установить цвет RGB светодиода на Arduino MEGA
        Согласно протоколу MEGA: [REG_RGB, R, G, B]
        """
        red = max(0, min(255, int(red)))
        green = max(0, min(255, int(green)))
        blue = max(0, min(255, int(blue)))

        try:
            # Формируем команду согласно протоколу Arduino MEGA
            data = [self.REG_RGB, red, green, blue]

            # Отправляем команду через fast_i2c арбитр (он отправит на MEGA)
            ok = self.controller.fast_i2c.write_mega_command(data, timeout=0.3)

            if ok:
                logger.debug("RGB установлен: R=%d, G=%d, B=%d",
                             red, green, blue)
            else:
                logger.error("Ошибка установки RGB цвета")

            return ok

        except Exception as e:
            logger.error("Ошибка отправки RGB команды: %s", e)
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
            'lime': (50, 205, 50),
            'indigo': (75, 0, 130),
            'turquoise': (64, 224, 208),
            'off': (0, 0, 0)
        }

        if preset_name.lower() in presets:
            r, g, b = presets[preset_name.lower()]
            return self.set_rgb_color(r, g, b)
        else:
            logger.warning("Неизвестный RGB пресет: %s", preset_name)
            return False

    def get_available_presets(self) -> list:
        """Получить список доступных пресетов"""
        return ['red', 'green', 'blue', 'white', 'yellow', 'purple',
                'cyan', 'orange', 'pink', 'lime', 'indigo', 'turquoise', 'off']
