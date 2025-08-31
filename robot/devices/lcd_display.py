# robot/devices/lcd_display.py

from __future__ import annotations

import time
import threading
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Команды LCD 1602
LCD_CLEARDISPLAY = 0x01
LCD_RETURNHOME = 0x02
LCD_ENTRYMODESET = 0x04
LCD_DISPLAYCONTROL = 0x08
LCD_CURSORSHIFT = 0x10
LCD_FUNCTIONSET = 0x20
LCD_SETCGRAMADDR = 0x40
LCD_SETDDRAMADDR = 0x80

# Флаги для display entry mode
LCD_ENTRYRIGHT = 0x00
LCD_ENTRYLEFT = 0x02
LCD_ENTRYSHIFTINCREMENT = 0x01
LCD_ENTRYSHIFTDECREMENT = 0x00

# Флаги для display on/off control
LCD_DISPLAYON = 0x04
LCD_DISPLAYOFF = 0x00
LCD_CURSORON = 0x02
LCD_CURSOROFF = 0x00
LCD_BLINKON = 0x01
LCD_BLINKOFF = 0x00

# Флаги для display/cursor shift
LCD_DISPLAYMOVE = 0x08
LCD_CURSORMOVE = 0x00
LCD_MOVERIGHT = 0x04
LCD_MOVELEFT = 0x00

# Флаги для function set
LCD_8BITMODE = 0x10
LCD_4BITMODE = 0x00
LCD_2LINE = 0x08
LCD_1LINE = 0x00
LCD_5x10DOTS = 0x04
LCD_5x8DOTS = 0x00

# Флаги для backlight control
LCD_BACKLIGHT = 0x08
LCD_NOBACKLIGHT = 0x00

En = 0b00000100  # Enable bit
Rw = 0b00000010  # Read/Write bit
Rs = 0b00000001  # Register select bit


class LCD1602I2C:
    """Класс для работы с LCD дисплеем 1602 через I2C."""

    def __init__(self, bus, address=0x27):
        self.bus = bus
        self.address = address
        self.backlight = LCD_BACKLIGHT
        self._lock = threading.Lock()
        self.display_active = False

        try:
            if self.bus:
                self._initialize_display()
                self.display_active = True
                logger.info(
                    f"LCD 1602 инициализирован на адресе 0x{address:02X}")
        except Exception as e:
            logger.error(f"Ошибка инициализации LCD: {e}")
            self.display_active = False

    def _write_4_bits(self, data):
        """Запись 4 бит в LCD через I2C"""
        try:
            self.bus.write_byte(self.address, data | self.backlight)
            self._lcd_strobe(data)
        except Exception as e:
            logger.error(f"Ошибка записи в LCD: {e}")
            self.display_active = False

    def _lcd_strobe(self, data):
        """Строб сигнал для LCD"""
        try:
            self.bus.write_byte(self.address, data | En | self.backlight)
            time.sleep(0.0005)
            self.bus.write_byte(self.address, data & ~En | self.backlight)
            time.sleep(0.0001)
        except Exception:
            pass

    def _lcd_write(self, command, mode=0):
        """Запись команды или данных в LCD"""
        if not self.display_active:
            return

        with self._lock:
            self._write_4_bits(mode | (command & 0xF0))
            self._write_4_bits(mode | ((command << 4) & 0xF0))

    def _initialize_display(self):
        """Инициализация LCD дисплея"""
        time.sleep(0.03)  # wait >15ms

        # Переход в 4-битный режим
        self._write_4_bits(0x30)
        time.sleep(0.005)  # wait >4.1ms

        self._write_4_bits(0x30)
        time.sleep(0.0001)  # wait >100µs

        self._write_4_bits(0x30)
        time.sleep(0.0001)

        self._write_4_bits(0x20)  # 4-bit mode
        time.sleep(0.0001)

        # Настройка дисплея
        self._lcd_write(LCD_FUNCTIONSET | LCD_2LINE |
                        LCD_5x8DOTS | LCD_4BITMODE)
        self._lcd_write(LCD_DISPLAYCONTROL | LCD_DISPLAYON |
                        LCD_CURSOROFF | LCD_BLINKOFF)
        self._lcd_write(LCD_CLEARDISPLAY)
        self._lcd_write(LCD_ENTRYMODESET | LCD_ENTRYLEFT)

        time.sleep(0.003)  # clear screen needs a long delay

    def clear(self):
        """Очистка дисплея"""
        if not self.display_active:
            return
        self._lcd_write(LCD_CLEARDISPLAY)
        time.sleep(0.003)

    def set_cursor(self, col, row):
        """Установка позиции курсора"""
        if not self.display_active:
            return
        if row == 0:
            self._lcd_write(LCD_SETDDRAMADDR | (col & 0x0F))
        else:
            self._lcd_write(LCD_SETDDRAMADDR | (0x40 + (col & 0x0F)))

    def write_string(self, message):
        """Вывод строки на дисплей"""
        if not self.display_active:
            return

        for char in message:
            self._lcd_write(ord(char), Rs)

    def display_two_lines(self, line1: str, line2: str):
        """Отображение двух строк на дисплее"""
        if not self.display_active:
            return

        with self._lock:
            # Ограничиваем длину строк до 16 символов
            line1 = line1[:16].ljust(16)
            line2 = line2[:16].ljust(16)

            # Первая строка
            self.set_cursor(0, 0)
            self.write_string(line1)

            # Вторая строка
            self.set_cursor(0, 1)
            self.write_string(line2)


class RobotLCDDisplay:
    """
    Класс для автоматического отображения статуса робота на LCD дисплее.
    Показывает движение, препятствия, температуру и влажность.
    """

    def __init__(self, bus=None, address=0x27, update_interval=1.5):
        self.bus = bus
        self.address = address
        self.update_interval = update_interval
        self.lcd = None
        self._running = False
        self._thread = None
        self._last_status = {}

        if self.bus:
            try:
                self.lcd = LCD1602I2C(self.bus, self.address)
                logger.info(f"Robot LCD Display инициализирован")
            except Exception as e:
                logger.error(f"Ошибка инициализации Robot LCD Display: {e}")

    def start(self):
        """Запуск автоматического отображения"""
        if self.lcd and self.lcd.display_active and not self._running:
            self._running = True
            self._thread = threading.Thread(
                target=self._display_loop, daemon=True)
            self._thread.start()

            # Показываем приветствие
            self.lcd.display_two_lines("Robot Started", "LCD Ready")
            time.sleep(2)

            logger.info("Robot LCD Display запущен")

    def stop(self):
        """Остановка отображения"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self.lcd and self.lcd.display_active:
            self.lcd.clear()
        logger.info("Robot LCD Display остановлен")

    def update_status(self, status: Dict[str, Any]):
        """Обновление статуса робота для отображения"""
        self._last_status = status

    def _get_direction_text(self, direction: int, is_moving: bool) -> str:
        """Преобразование кода направления в текст"""
        if not is_moving:
            return "Остановлен"

        direction_map = {
            1: "Вперед",
            2: "Назад",
            3: "Влево",
            4: "Вправо"
        }
        return direction_map.get(direction, "Стоп")

    def _get_obstacle_text(self, obstacles: Dict[str, bool]) -> str:
        """Получение текста о препятствиях"""
        if obstacles.get("center_front", False):
            return "Препят: Перед"
        elif obstacles.get("left_front", False):
            return "Препят: Лев-П"
        elif obstacles.get("right_front", False):
            return "Препят: Пр-П"
        elif obstacles.get("left_rear", False):
            return "Препят: Лев-З"
        elif obstacles.get("right_rear", False):
            return "Препят: Пр-З"
        else:
            return "Препят: Нет"

    def _format_sensor_line(self, temp: Optional[float], humidity: Optional[float]) -> str:
        """Форматирование строки с данными датчиков"""
        temp_str = f"{temp:.1f}C" if temp is not None else "ERR"
        hum_str = f"{humidity:.0f}%" if humidity is not None else "ERR"
        return f"T:{temp_str} H:{hum_str}"

    def _display_loop(self):
        """Основной цикл автоматического отображения информации"""
        while self._running:
            try:
                if not self.lcd or not self.lcd.display_active:
                    time.sleep(self.update_interval)
                    continue

                status = self._last_status
                if not status:
                    # Показываем статус ожидания
                    self.lcd.display_two_lines("Robot Ready", "Waiting...")
                    time.sleep(self.update_interval)
                    continue

                # Получаем данные из статуса
                is_moving = status.get("is_moving", False)
                direction = status.get("movement_direction", 0)
                temperature = status.get("temperature")
                humidity = status.get("humidity")
                obstacles = status.get("obstacles", {})

                # Формируем строки для отображения
                # Первая строка: состояние движения/препятствия
                if any(obstacles.values()):
                    line1 = self._get_obstacle_text(obstacles)
                else:
                    line1 = self._get_direction_text(direction, is_moving)

                # Вторая строка: температура и влажность
                line2 = self._format_sensor_line(temperature, humidity)

                # Отображаем на LCD
                self.lcd.display_two_lines(line1, line2)

            except Exception as e:
                logger.error(f"Ошибка в цикле отображения LCD: {e}")

            time.sleep(self.update_interval)

    def is_active(self) -> bool:
        """Проверка активности LCD"""
        return self._running and self.lcd and self.lcd.display_active
