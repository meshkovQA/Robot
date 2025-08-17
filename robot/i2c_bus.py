# i2c_bus.py

from __future__ import annotations
import time
import logging
from typing import Protocol, Tuple, Optional

from .config import I2C_AVAILABLE, I2C_BUS, ARDUINO_ADDRESS

logger = logging.getLogger(__name__)


class I2CBus(Protocol):
    def write_i2c_block_data(self, addr: int, cmd: int,
                             vals: list[int]) -> None: ...

    def write_byte(self, addr: int, val: int) -> None: ...
    def read_i2c_block_data(self, addr: int, cmd: int,
                            length: int) -> list[int]: ...


def open_bus() -> Optional[I2CBus]:
    if not I2C_AVAILABLE:
        logger.warning("smbus2 недоступен — работаем в эмуляции")
        return None
    try:
        import smbus2  # type: ignore
        bus = smbus2.SMBus(I2C_BUS)
        logger.info("I2C подключение установлено (bus=%s, addr=0x%02X)",
                    I2C_BUS, ARDUINO_ADDRESS)
        time.sleep(0.2)
        return bus
    except Exception as e:
        logger.error("Не удалось открыть I2C: %s", e)
        return None
