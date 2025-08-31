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
        """
        Отправка половинного байта (старшие 4 бита) + управляющие биты (RS/RW/EN).
        Здесь data уже содержит RS (если нужно) и верхний полубайт команды/данных.
        """
        try:
            # выставляем шину (данные + подсветка)
            self.bus.write_byte(self.address, (data & 0xF0) | self.backlight)
            # импульс EN
            self._lcd_strobe(data)
        except Exception as e:
            logger.error(f"Ошибка записи в LCD (4 bits): {e}")
            self.display_active = False
            raise

    def _lcd_strobe(self, data):
        """
        Импульс Enable: высокий фронт EN, короткая пауза, низкий.
        RS/RW/данные должны быть установлены ДО строба.
        """
        try:
            # EN=1
            self.bus.write_byte(
                self.address, ((data & 0xF0) | En | self.backlight))
            time.sleep(0.0005)
            # EN=0
            self.bus.write_byte(self.address, ((data & 0xF0) | self.backlight))
            time.sleep(0.0001)
        except Exception as e:
            logger.error(f"LCD: ошибка строба EN: {e}")
            self.display_active = False
            raise

    def _lcd_write(self, command, mode=0):
        """
        Отправка полного байта (команда или данные).
        mode=0 — команда; mode=Rs — данные.
        """
        if not self.display_active:
            return
        # формируем старший и младший полубайты с учётом бита RS
        high = (mode | (command & 0xF0))
        low = (mode | ((command << 4) & 0xF0))
        self._write_4_bits(high)
        self._write_4_bits(low)

    def _initialize_display(self):
        """
        Жёсткая инициализация HD44780 в 4-битном режиме через PCF8574.
        Последовательность соответствует даташиту:
        1) 0x30, пауза, 0x30, пауза, 0x30, пауза, 0x20 (переход в 4-бит)
        2) FUNCTIONSET (4-bit, 2 lines, 5x8)
        3) DISPLAY ON, CURSOR OFF, BLINK OFF
        4) CLEAR
        5) ENTRYMODESET (инкремент курсора, без сдвига)
        """
        # начальная задержка после питания
        time.sleep(0.05)

        # гарантируем состояние подсветки (бит PCF8574 P3=1 — обычно backlight)
        try:
            self.bus.write_byte(self.address, self.backlight)
        except Exception as e:
            logger.error(
                f"LCD: экспандер недоступен по адресу 0x{self.address:02X}: {e}")
            raise

        # трижды 0x30 (8-битная инициализация), затем 0x20 (переход в 4-бит)
        self._write_4_bits(0x30)
        time.sleep(0.0045)
        self._write_4_bits(0x30)
        time.sleep(0.0045)
        self._write_4_bits(0x30)
        time.sleep(0.00015)
        self._write_4_bits(0x20)  # 4-битный режим
        time.sleep(0.00015)

        # 4-бит, 2 строки, 5x8 точек
        self._lcd_write(LCD_FUNCTIONSET | LCD_4BITMODE |
                        LCD_2LINE | LCD_5x8DOTS, 0)
        # дисплей включен, курсор/мигание выкл
        self._lcd_write(LCD_DISPLAYCONTROL | LCD_DISPLAYON |
                        LCD_CURSOROFF | LCD_BLINKOFF, 0)
        # очистка
        self._lcd_write(LCD_CLEARDISPLAY, 0)
        time.sleep(0.003)
        # режим ввода: курсор вправо, без сдвига
        self._lcd_write(LCD_ENTRYMODESET | LCD_ENTRYLEFT |
                        LCD_ENTRYSHIFTDECREMENT, 0)
        time.sleep(0.002)

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
        """
        Печать двух строк. Жёстко приводим к 16 символам и пишем в заданные адреса.
        (Очистка всего дисплея не выполняется, чтобы не мигал — только позиционирование.)
        """
        if not self.display_active:
            return
        with self._lock:
            line1 = (line1 or "")[:16].ljust(16)
            line2 = (line2 or "")[:16].ljust(16)

            # Первая строка (адрес 0x00)
            self._lcd_write(LCD_SETDDRAMADDR | 0x00, 0)
            for ch in line1:
                b = ord(ch) if ord(ch) < 256 else ord('?')
                self._lcd_write(b, Rs)

            # Вторая строка (адрес 0x40)
            self._lcd_write(LCD_SETDDRAMADDR | 0x40, 0)
            for ch in line2:
                b = ord(ch) if ord(ch) < 256 else ord('?')
                self._lcd_write(b, Rs)


class RobotLCDDisplay:
    """
    Класс для автоматического отображения статуса робота на LCD дисплее.
    Показывает движение, препятствия, температуру и влажность.
    """

    def __init__(self, bus=None, address=0x27, update_interval=1.5, bus_num: int | None = None, debug: bool = False):
        self.bus = bus
        self.bus_num = bus_num
        self.address = address
        self.update_interval = update_interval
        self.debug = debug

        self.lcd = None
        self._running = False
        self._thread = None
        self._last_status = {}
        self._greet_pending = True  # одноразовое приветствие

    def start(self):
        """Запуск фонового отображения (ленивая инициализация дисплея внутри потока)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._display_loop, daemon=True)
        self._thread.start()
        logger.info("Robot LCD Display запущен (ленивая инициализация)")

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
        """
        Фоновый цикл:
        - лениво открывает I²C-шину (bus_num из конфигурации);
        - инициализирует LCD;
        - выводит приветствие и далее текущий статус.
        """
        while self._running:
            try:
                # ленивое открытие I²C и создание LCD
                if self.lcd is None:
                    try:
                        if self.bus is None:
                            import smbus2
                            bus_num = self.bus_num if self.bus_num is not None else 1
                            self.bus = smbus2.SMBus(bus_num)
                        self.lcd = LCD1602I2C(self.bus, self.address)
                        if self.lcd.display_active:
                            logger.info(
                                f"LCD готов: addr=0x{self.address:02X}")
                            # приветствие ASCII (чтобы избежать проблем с кириллицей ПЗУ)
                            self.lcd.display_two_lines(
                                "Robot Started", "LCD Ready")
                            time.sleep(1.5)
                        else:
                            logger.warning("LCD не активен после init")
                    except Exception as e:
                        logger.error(f"LCD init error: {e}")
                        # подождём и попробуем снова
                        time.sleep(self.update_interval)
                        continue

                if not self.lcd.display_active:
                    time.sleep(self.update_interval)
                    continue

                status = self._last_status
                if not status:
                    self.lcd.display_two_lines("Robot Ready", "Waiting...")
                    time.sleep(self.update_interval)
                    continue

                # читаем статус
                is_moving = status.get("is_moving", False)
                direction = status.get("movement_direction", 0)
                temperature = status.get("temperature")
                humidity = status.get("humidity")
                obstacles = status.get("obstacles", {})

                # первая строка: препятствие приоритетнее
                if any(obstacles.values()):
                    line1 = self._get_obstacle_text(obstacles)
                else:
                    line1 = self._get_direction_text(direction, is_moving)

                # вторая строка: T/H
                line2 = self._format_sensor_line(temperature, humidity)

                self.lcd.display_two_lines(line1, line2)

            except Exception as e:
                logger.error(f"Ошибка в цикле отображения LCD: {e}")

            time.sleep(self.update_interval)

    def is_active(self) -> bool:
        """Проверка активности LCD"""
        return self._running and self.lcd and self.lcd.display_active
