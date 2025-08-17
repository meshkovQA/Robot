# config.py

import os

# I2C
I2C_AVAILABLE = True
try:
    import smbus2  # noqa: F401
except Exception:
    I2C_AVAILABLE = False

I2C_BUS = int(os.getenv("I2C_BUS", "1"))
ARDUINO_ADDRESS = int(os.getenv("ARDUINO_ADDRESS", "0x08"), 16)

# Сенсоры/пороги
SENSOR_ERR = 999
SENSOR_FWD_STOP_CM = int(os.getenv("SENSOR_FWD_STOP_CM", "25"))
SENSOR_BWD_STOP_CM = int(os.getenv("SENSOR_BWD_STOP_CM", "20"))
SENSOR_MAX_VALID = int(os.getenv("SENSOR_MAX_VALID", "500"))

# Скорость (0..255)
SPEED_MIN = 0
SPEED_MAX = 255
DEFAULT_SPEED = int(os.getenv("DEFAULT_SPEED", "70"))

# Безопасность
API_KEY = os.getenv("API_KEY")  # если None, аутентификация выключена

# Логи
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
