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
LCD_BACKLIGHT = 0x10       # P4 — часто подсветка (многие платы PCF8574)
LCD_NOBACKLIGHT = 0x00


# Биты PCF8574 -> LCD
En = 0b00100000  # Enable bit  (P5)
Rw = 0b00000010  # Read/Write  (P1)
Rs = 0b00000001  # RegisterSel (P0)


class LCD1602I2C:
    """Класс для работы с LCD дисплеем 1602 через I2C."""

    def __init__(self, bus, address=0x27, debug: bool = False):
        self.bus = bus
        self.address = address
        self.backlight = LCD_BACKLIGHT
        self._lock = threading.Lock()
        self.display_active = False
        self.debug = bool(debug)

        if self.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug(
                f"LCD1602I2C.__init__: addr=0x{self.address:02X}, debug=on")

        try:
            if self.bus:
                logger.debug(
                    "LCD1602I2C.__init__: calling _initialize_display()")
                self._initialize_display()
                self.display_active = True
                logger.info(
                    f"LCD 1602 инициализирован на адресе 0x{address:02X}")
            else:
                logger.debug(
                    "LCD1602I2C.__init__: bus is None, skip init (lazy)")
        except Exception as e:
            logger.error(f"Ошибка инициализации LCD: {e!r}")
            self.display_active = False

    def _write_4_bits(self, data):
        """
        data уже содержит:
        - ниббл данных в битах 7..4,
        - флаги RS/RW в младших битах.
        НИЧЕГО не маскируем — сохраняем RS/RW, просто добавляем подсветку
        и стробим EN.
        """
        try:
            out = data | self.backlight  # сохранить RS/RW + ниббл
            if self.debug:
                logger.debug(
                    f"_write_4_bits: data=0x{data:02X} -> out=0x{out:02X}")
            self.bus.write_byte(self.address, out)
            self._lcd_strobe(out)        # стробим то же самое состояние
        except Exception as e:
            logger.error(f"Ошибка записи в LCD (4 bits): {e!r}")
            self.display_active = False
            raise

    def _lcd_strobe(self, out):
        """
        Строб EN при неизменённых RS/RW и линиях данных.
        Подаём EN=1, короткая пауза, затем EN=0.
        """
        try:
            hi = out | En
            lo = out & ~En
            if self.debug:
                logger.debug(f"_lcd_strobe: EN↑ 0x{hi:02X}, EN↓ 0x{lo:02X}")
            self.bus.write_byte(self.address, hi)   # EN = 1
            time.sleep(0.0005)
            self.bus.write_byte(self.address, lo)   # EN = 0
            time.sleep(0.0001)
        except Exception as e:
            logger.error(f"LCD: ошибка строба EN: {e!r}")
            self.display_active = False
            raise

    def _lcd_write(self, command, mode=0):
        """
        Отправка полного байта (команда или данные).
        mode=0 — команда; mode=Rs — данные.
        """
        if not self.display_active:
            if self.debug:
                logger.debug(
                    f"_lcd_write: skip (display_inactive) cmd=0x{command:02X}, mode=0x{mode:02X}")
            return

        high = (mode | (command & 0xF0))
        low = (mode | ((command << 4) & 0xF0))
        if self.debug:
            kind = "DATA" if (mode & Rs) else "CMD"
            logger.debug(
                f"_lcd_write: {kind} 0x{command:02X} -> high=0x{high:02X}, low=0x{low:02X}")
        self._write_4_bits(high)
        self._write_4_bits(low)

    def _initialize_display(self):
        """
        Жёсткая инициализация HD44780 в 4-битном режиме через PCF8574.
        Последовательность «3,3,3,2» + стандартные команды.
        Даём отчётливые логи и мигаем подсветкой для визуального контроля маппинга BL.
        """
        logger.debug("LCD init: start, addr=0x%02X", self.address)

        # начальная задержка после питания
        time.sleep(0.05)

        # пробный контроль подсветки — должен мигнуть экран
        try:
            self.bus.write_byte(self.address, LCD_NOBACKLIGHT)
            time.sleep(0.05)
            self.bus.write_byte(self.address, LCD_BACKLIGHT)
            time.sleep(0.05)
            logger.debug(
                "LCD init: backlight blinked (BL mask=0x%02X)", LCD_BACKLIGHT)
        except Exception as e:
            logger.error(
                "LCD: экспандер недоступен по адресу 0x%02X: %r", self.address, e)
            raise

        # трижды 0x30 (8-битная инициализация), затем 0x20 (переход в 4-бит)
        self._write_4_bits(0x30)  # 0b0011xxxx
        time.sleep(0.0045)
        self._write_4_bits(0x30)
        time.sleep(0.0045)
        self._write_4_bits(0x30)
        time.sleep(0.00015)
        self._write_4_bits(0x20)  # 0b0010xxxx -> 4-битный режим
        time.sleep(0.00015)

        # 4-бит, 2 строки, 5x8 точек
        self._lcd_write(LCD_FUNCTIONSET | LCD_4BITMODE |
                        LCD_2LINE | LCD_5x8DOTS, 0)
        logger.debug("LCD init: FUNCTIONSET 4bit,2line,5x8")

        # дисплей OFF перед очисткой (так рекомендует даташит)
        self._lcd_write(LCD_DISPLAYCONTROL | LCD_DISPLAYOFF |
                        LCD_CURSOROFF | LCD_BLINKOFF, 0)
        logger.debug("LCD init: DISPLAY OFF")

        # очистка
        self._lcd_write(LCD_CLEARDISPLAY, 0)
        time.sleep(0.003)
        logger.debug("LCD init: CLEAR")

        # режим ввода: курсор вправо, без сдвига
        self._lcd_write(LCD_ENTRYMODESET | LCD_ENTRYLEFT |
                        LCD_ENTRYSHIFTDECREMENT, 0)
        logger.debug("LCD init: ENTRYMODESET")

        # дисплей ON (без курсора/мигания)
        self._lcd_write(LCD_DISPLAYCONTROL | LCD_DISPLAYON |
                        LCD_CURSOROFF | LCD_BLINKOFF, 0)
        logger.debug("LCD init: DISPLAY ON")

        # Быстрый ASCII-самотест: 'HELLO 1602' / 'I2C OK       '
        try:
            self._lcd_write(LCD_SETDDRAMADDR | 0x00, 0)
            for ch in "HELLO 1602     "[:16]:
                self._lcd_write(ord(ch), Rs)
            self._lcd_write(LCD_SETDDRAMADDR | 0x40, 0)
            for ch in "I2C OK         "[:16]:
                self._lcd_write(ord(ch), Rs)
            logger.debug("LCD init: ASCII selftest written")
        except Exception as e:
            logger.error("LCD init: selftest write error: %r", e)

        logger.info("LCD 1602 инициализирован (EN=0x%02X, BL=0x%02X)",
                    En, LCD_BACKLIGHT)

    def clear(self):
        """Очистка дисплея"""
        if not self.display_active:
            return
        self._lcd_write(LCD_CLEARDISPLAY)
        time.sleep(0.003)

    def set_cursor(self, col, row):
        """Установка позиции курсора"""
        if not self.display_active:
            if self.debug:
                logger.debug(
                    f"set_cursor: skip (inactive) col={col}, row={row}")
            return
        addr = (col & 0x0F) if row == 0 else (0x40 + (col & 0x0F))
        if self.debug:
            logger.debug(
                f"set_cursor: col={col}, row={row}, ddram=0x{addr:02X}")
        self._lcd_write(LCD_SETDDRAMADDR | addr)

    def write_string(self, message):
        """Вывод строки на дисплей"""
        if not self.display_active:
            if self.debug:
                logger.debug("write_string: skip (display_inactive)")
            return
        if message is None:
            message = ""
        if self.debug:
            logger.debug(f"write_string: '{message}' (len={len(message)})")
        for ch in message:
            b = ord(ch) if ord(ch) < 256 else ord('?')
            self._lcd_write(b, Rs)

    def display_two_lines(self, line1: str, line2: str):
        """
        Печать двух строк. Приводим к 16 символам и пишем в адреса 0x00/0x40.
        """
        if not self.display_active:
            if self.debug:
                logger.debug("display_two_lines: skip (display_inactive)")
            return
        with self._lock:
            s1 = (line1 or "")[:16].ljust(16)
            s2 = (line2 or "")[:16].ljust(16)
            if self.debug:
                logger.debug(f"display_two_lines: L1='{s1}' | L2='{s2}'")

            self._lcd_write(LCD_SETDDRAMADDR | 0x00, 0)
            for ch in s1:
                b = ord(ch) if ord(ch) < 256 else ord('?')
                self._lcd_write(b, Rs)

            self._lcd_write(LCD_SETDDRAMADDR | 0x40, 0)
            for ch in s2:
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
        if self.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug(
                f"RobotLCDDisplay.start: bus_num={self.bus_num}, addr=0x{self.address:02X}, debug=on")
        self._running = True
        self._thread = threading.Thread(target=self._display_loop, daemon=True)
        self._thread.start()
        logger.info("Robot LCD Display запущен (ленивая инициализация)")

    def stop(self):
        """Остановка отображения"""
        if self.debug:
            logger.debug("RobotLCDDisplay.stop: requested")
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self.lcd and self.lcd.display_active:
            try:
                self.lcd.clear()
            except Exception as e:
                logger.warning(f"RobotLCDDisplay.stop: clear failed: {e!r}")
        logger.info("Robot LCD Display остановлен")

    def update_status(self, status: Dict[str, Any]):
        """Обновление статуса робота для отображения"""
        self._last_status = status

    def _get_direction_text(self, direction: int, is_moving: bool) -> str:
        """Преобразование кода направления в текст"""
        if not is_moving:
            return "Stopped"

        direction_map = {
            1: "Forward",
            2: "Backward",
            3: "Left",
            4: "Right"
        }
        return direction_map.get(direction, "Stop")

    def _get_obstacle_text(self, obstacles: Dict[str, bool]) -> str:
        """Получение текста о препятствиях"""
        if obstacles.get("center_front", False):
            return "Obstacle: Front"
        elif obstacles.get("left_front", False):
            return "Obstacle: L-F"
        elif obstacles.get("right_front", False):
            return "Obstacle: R-F"
        elif obstacles.get("left_rear", False):
            return "Obstacle: L-R"
        elif obstacles.get("right_rear", False):
            return "Obstacle: R-R"
        else:
            return "Clear"

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

        if first_run:
            try:
                self.lcd.display_two_lines("TEST 123", "ABC DEF")
                logger.info("Test message sent to LCD")
                time.sleep(5)  # Подольше показываем тест
                first_run = False
            except Exception as e:
                logger.error(f"Test message error: {e}")
                first_run = False

        while self._running:
            try:
                # ленивое открытие I²C и создание LCD
                if self.lcd is None:
                    try:
                        if self.bus is None:
                            import smbus2
                            bus_num = self.bus_num if self.bus_num is not None else 1
                            if self.debug:
                                logger.debug(
                                    f"_display_loop: opening SMBus({bus_num})")
                            self.bus = smbus2.SMBus(bus_num)
                            if self.debug:
                                logger.debug(
                                    f"_display_loop: SMBus({bus_num}) opened")

                        if self.debug:
                            logger.debug(
                                f"_display_loop: creating LCD1602I2C(addr=0x{self.address:02X})")
                        self.lcd = LCD1602I2C(
                            self.bus, self.address, debug=self.debug)

                        if self.lcd.display_active:
                            logger.info(
                                f"LCD готов: addr=0x{self.address:02X}")
                            self.lcd.display_two_lines(
                                "Robot Started", "LCD Ready")
                            time.sleep(1.5)
                        else:
                            logger.warning("LCD не активен после init")
                    except Exception as e:
                        logger.error(f"LCD init error: {e!r}")
                        # подождём и попробуем снова
                        time.sleep(self.update_interval)
                        continue

                if not self.lcd.display_active:
                    if self.debug:
                        logger.debug(
                            "_display_loop: lcd.display_active=False, retry later")
                    time.sleep(self.update_interval)
                    continue

                status = self._last_status
                if not status:
                    if self.debug:
                        logger.debug(
                            "_display_loop: no status yet -> 'Robot Ready / Waiting...'")
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

                if self.debug:
                    logger.debug(
                        f"_display_loop: show L1='{line1}' | L2='{line2}'")

                self.lcd.display_two_lines(line1, line2)

            except Exception as e:
                logger.error(f"Ошибка в цикле отображения LCD: {e!r}")

            time.sleep(self.update_interval)

    def is_active(self) -> bool:
        """Проверка активности LCD"""
        return self._running and self.lcd and self.lcd.display_active
