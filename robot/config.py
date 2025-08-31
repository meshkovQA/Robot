# config.py

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

HOME_DIR = Path.home()
# ==================== I2C НАСТРОЙКИ ====================
I2C_AVAILABLE = True
try:
    import smbus2  # noqa: F401
except ImportError:
    I2C_AVAILABLE = False

I2C_BUS = 1
ARDUINO_ADDRESS = 0x08
ARDUINO_MEGA_ADDRESS = 0x09

# Настройки таймингов I2C для устранения ошибок
I2C_INTER_DEVICE_DELAY_MS = 10    # пауза между чтением разных Arduino (мс)

# ==================== СЕНСОРЫ/ПОРОГИ ====================
SENSOR_ERR = 999
SENSOR_FWD_STOP_CM = 30
SENSOR_BWD_STOP_CM = 30
SENSOR_SIDE_STOP_CM = 15
SENSOR_MAX_VALID = 500

# ==================== СКОРОСТЬ (0..255) ====================
SPEED_MIN = 0
SPEED_MAX = 255
DEFAULT_SPEED = 70

# Константы для кикстарта
KICKSTART_SPEED = 130
KICKSTART_DURATION = 0.3  # 300ms
MIN_SPEED_FOR_KICKSTART = 80  # Кикстарт только для скоростей ниже этого значения


# ==================== IMU / HEADING HOLD ====================

# Включение/выключение использования IMU
IMU_ENABLED = True

# Настройки I2C для MPU-6500
IMU_I2C_BUS = 1                  # номер I2C-шины (обычно 1 на Raspberry Pi)
# адрес IMU (0x68 по умолчанию, 0x69 если AD0=3.3V)
IMU_ADDRESS = 0x68
IMU_WHOAMI = 0x70                # ожидаемое значение регистра WHO_AM_I для MPU-6500
# время (сек), за которое усредняется смещение гироскопа
IMU_CALIBRATION_TIME = 2.0
# частота обновления (Гц) цикла чтения и фильтрации
IMU_LOOP_HZ = 100
# коэффициент комплементарного фильтра (0.0–1.0)
IMU_COMPLEMENTARY_ALPHA = 0.98

# =========================
# УДЕРЖАНИЕ КУРСА (Yaw PID)
# =========================

HDG_HOLD_ENABLED = True

# PID-коэффициенты
HDG_KP = 0.8          # было 0.9 — немного мягче
HDG_KI = 0.0          # интеграл лучше держать 0 на старте
HDG_KD = 0.05         # можно поднять до 0.08–0.1, если «рыщет»

# Зоны покоя/гистерезиса
HDG_ERR_DEADZONE_DEG = 2.0   # было 1.5; чуть больше — меньше дрожания

# --- Удержание курса ---
HDG_CORR_SPEED = 80   # базовая скорость корректирующих импульсов (PWM)

# Наследуемые «старыe» лимиты (используются как дополнительные ограничения)
HDG_MAX_CORR_PULSE_MS = 120    # твой старый максимум — оставляем как «крышу»
HDG_MIN_GAP_BETWEEN_PULSES_MS = 80  # было 150 — быстрее реагировать


# --- Автобуст на подъёме (по углу Pitch) ---
UPHILL_BOOST_ENABLED = True
# если наклон вперёд/назад превышает это значение → считаем подъёмом
UPHILL_PITCH_THRESHOLD_DEG = 5.0
# гистерезис для отключения буста (чтобы не дёргалось)
UPHILL_HYSTERESIS_DEG = 2.0
UPHILL_SPEED_MULTIPLIER = 2.0    # во сколько раз увеличить скорость на подъёме
# наклон должен сохраняться хотя бы столько секунд, чтобы включить буст
UPHILL_MIN_DURATION_S = 0.5
UPHILL_MAX_SPEED = 200           # ограничение максимальной скорости при бусте

# --- API ---
EXPOSE_IMU_API = True            # включить/выключить эндпоинт /api/imu/status


# ==================== LCD DISPLAY 1602 ====================

# Включение/выключение LCD дисплея
LCD_ENABLED = False

# I2C настройки для LCD
LCD_I2C_BUS = 1                    # номер I2C-шины (обычно 1 на Raspberry Pi)
LCD_I2C_ADDRESS = 0x27             # стандартный адрес для LCD 1602 с I2C модулем
# интервал обновления информации на дисплее (секунды)
LCD_UPDATE_INTERVAL = 1.5

# Отладка LCD
LCD_DEBUG = False                  # включить отладочные сообщения для LCD

# ==================== ПОВОРОТЫ КАМЕРЫ ====================

# Ограничения углов поворота камеры
CAMERA_PAN_MIN = 0      # минимальный угол горизонтального поворота
CAMERA_PAN_MAX = 180    # максимальный угол горизонтального поворота
CAMERA_PAN_DEFAULT = 90  # центральная позиция по горизонтали

CAMERA_TILT_MIN = 50    # минимальный угол вертикального наклона
CAMERA_TILT_MAX = 150   # максимальный угол вертикального наклона
CAMERA_TILT_DEFAULT = 90  # центральная позиция по вертикали

# Шаг поворота камеры (градусы за одну команду)
CAMERA_STEP_SIZE = 10

# --- РЕЖИМ ИНИЦИАЛИЗАЦИИ ПРИ СТАРТЕ ПРИЛОЖЕНИЯ ---

# Если True — приложение стартует без инициализации камеры (лёгкий режим).
# Если False — камера инициализируется при старте Flask-приложения.
LIGHT_INIT = False

# ==================== КАМЕРА ====================

# Проверка доступности OpenCV
CAMERA_AVAILABLE = True
try:
    import cv2  # noqa: F401
except ImportError:
    CAMERA_AVAILABLE = False

# Основные настройки камеры
CAMERA_DEVICE_ID = 0  # /dev/video0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

# Качество изображения
CAMERA_QUALITY = 100  # JPEG качество (1-100)
CAMERA_STREAM_QUALITY = 100  # Для веб-стрима
CAMERA_STREAM_FPS = 30  # FPS веб-стрима

# Настройки изображения
CAMERA_BRIGHTNESS = 40  # 0-100
CAMERA_CONTRAST = 60      # 0-100
CAMERA_SATURATION = 55  # 0-100

# Пути сохранения
CAMERA_SAVE_PATH = str(STATIC_DIR / "photos")
CAMERA_VIDEO_PATH = str(STATIC_DIR / "videos")

# Автозапуск камеры
CAMERA_AUTO_START = True

# Максимальные размеры файлов (в байтах)
MAX_PHOTO_SIZE = 10485760  # 10MB
MAX_VIDEO_SIZE = 104857600  # 100MB

# Максимальное количество файлов
MAX_PHOTOS = 100
MAX_VIDEOS = 20

# Автоочистка старых файлов (в днях)
AUTO_CLEANUP_DAYS = 7

# ==================== БЕЗОПАСНОСТЬ ====================
API_KEY = None  # если None, аутентификация выключена

# ==================== ЛОГИРОВАНИЕ ====================
LOG_LEVEL = "INFO"
LOG_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Специальное логирование для камеры
CAMERA_LOG_LEVEL = "INFO"
ENABLE_CAMERA_DEBUG = False

# ==================== ПРОИЗВОДИТЕЛЬНОСТЬ ====================

# Буферизация видео
VIDEO_BUFFER_SIZE = 1

# Таймауты (в секундах)
CAMERA_INIT_TIMEOUT = 10
CAMERA_CAPTURE_TIMEOUT = 5

# Количество потоков для обработки видео
CAMERA_THREADS = 1

# ==================== РАСШИРЕННЫЕ ФУНКЦИИ ====================

# Детекция движения
ENABLE_MOTION_DETECTION = False
MOTION_THRESHOLD = 30

# Автоматическая запись при движении
AUTO_RECORD_ON_MOTION = False
AUTO_RECORD_DURATION = 30  # секунд

# Наложение текста на видео
ENABLE_VIDEO_OVERLAY = True
OVERLAY_TIMESTAMP = True
OVERLAY_ROBOT_STATUS = False

# ==================== ВАЛИДАЦИЯ НАСТРОЕК ====================


def validate_camera_config():
    """Проверка корректности настроек камеры"""
    errors = []

    # Проверка размеров
    if CAMERA_WIDTH <= 0 or CAMERA_HEIGHT <= 0:
        errors.append("Неверные размеры камеры")

    if not (1 <= CAMERA_QUALITY <= 100):
        errors.append("Качество камеры должно быть от 1 до 100")

    if not (1 <= CAMERA_STREAM_QUALITY <= 100):
        errors.append("Качество стрима должно быть от 1 до 100")

    # Проверка FPS
    if CAMERA_FPS <= 0 or CAMERA_FPS > 60:
        errors.append("FPS камеры должен быть от 1 до 60")

    if CAMERA_STREAM_FPS <= 0 or CAMERA_STREAM_FPS > 30:
        errors.append("FPS стрима должен быть от 1 до 30")

    # Проверка путей
    try:
        import pathlib
        pathlib.Path(CAMERA_SAVE_PATH).mkdir(parents=True, exist_ok=True)
        pathlib.Path(CAMERA_VIDEO_PATH).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        errors.append(f"Ошибка создания директорий: {e}")

    return errors

# ==================== ИНТЕГРАЦИЯ С РОБОТОМ ====================


# Автоматическая запись при движении робота
RECORD_ON_ROBOT_MOVE = False

# Автоматическое фото при препятствиях
PHOTO_ON_OBSTACLE = False

# Сохранение кадров при экстренной остановке
SAVE_FRAME_ON_EMERGENCY = True

# ==================== СИСТЕМНЫЕ НАСТРОЙКИ ====================

# Проверка доступности USB камер


def check_usb_cameras():
    """Проверка доступных USB камер"""
    if not CAMERA_AVAILABLE:
        return []

    try:
        import cv2
        available_cameras = []

        # Проверяем первые 5 устройств
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    available_cameras.append(i)
            cap.release()

        return available_cameras
    except Exception:
        return []

# Получение информации о системе


def get_system_info():
    """Получение информации о системе для диагностики"""
    info = {
        "opencv_available": CAMERA_AVAILABLE,
        "i2c_available": I2C_AVAILABLE,
        "camera_devices": check_usb_cameras(),
        "config_valid": len(validate_camera_config()) == 0
    }

    if CAMERA_AVAILABLE:
        try:
            import cv2
            info["opencv_version"] = cv2.__version__
        except Exception:
            info["opencv_version"] = "unknown"

    return info

# ==================== ЭКСПОРТ НАСТРОЕК ====================


# Все настройки камеры в одном словаре для удобства
CAMERA_CONFIG = {
    "device_id": CAMERA_DEVICE_ID,
    "width": CAMERA_WIDTH,
    "height": CAMERA_HEIGHT,
    "fps": CAMERA_FPS,
    "quality": CAMERA_QUALITY,
    "stream_quality": CAMERA_STREAM_QUALITY,
    "stream_fps": CAMERA_STREAM_FPS,
    "brightness": CAMERA_BRIGHTNESS,
    "contrast": CAMERA_CONTRAST,
    "saturation": CAMERA_SATURATION,
    "save_path": CAMERA_SAVE_PATH,
    "video_path": CAMERA_VIDEO_PATH,
    "auto_start": CAMERA_AUTO_START,
    "max_photo_size": MAX_PHOTO_SIZE,
    "max_video_size": MAX_VIDEO_SIZE,
    "max_photos": MAX_PHOTOS,
    "max_videos": MAX_VIDEOS,
    "auto_cleanup_days": AUTO_CLEANUP_DAYS,
    "buffer_size": VIDEO_BUFFER_SIZE,
    "init_timeout": CAMERA_INIT_TIMEOUT,
    "capture_timeout": CAMERA_CAPTURE_TIMEOUT,
    "threads": CAMERA_THREADS,
    "motion_detection": ENABLE_MOTION_DETECTION,
    "motion_threshold": MOTION_THRESHOLD,
    "auto_record_on_motion": AUTO_RECORD_ON_MOTION,
    "auto_record_duration": AUTO_RECORD_DURATION,
    "video_overlay": ENABLE_VIDEO_OVERLAY,
    "overlay_timestamp": OVERLAY_TIMESTAMP,
    "overlay_robot_status": OVERLAY_ROBOT_STATUS,
    "record_on_robot_move": RECORD_ON_ROBOT_MOVE,
    "photo_on_obstacle": PHOTO_ON_OBSTACLE,
    "save_frame_on_emergency": SAVE_FRAME_ON_EMERGENCY
}


# ==================== ОТЛАДКА ====================


if ENABLE_CAMERA_DEBUG:
    import logging
    logging.getLogger('robot.camera').setLevel(logging.DEBUG)
    print("🎥 Camera debug mode enabled")

# Проверка конфигурации при импорте
_config_errors = validate_camera_config()
if _config_errors:
    import logging
    logger = logging.getLogger(__name__)
    for error in _config_errors:
        logger.warning(f"Camera config warning: {error}")

# Вывод информации о системе при импорте (только в DEBUG режиме)
if ENABLE_CAMERA_DEBUG:
    _system_info = get_system_info()
    print(f"🔍 System info: {_system_info}")
