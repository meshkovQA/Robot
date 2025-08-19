# config.py

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

STATIC_DIR = PROJECT_ROOT / "static"

HOME_DIR = Path.home()
# ==================== I2C НАСТРОЙКИ ====================
I2C_AVAILABLE = True
try:
    import smbus2  # noqa: F401
except ImportError:
    I2C_AVAILABLE = False

I2C_BUS = 1
ARDUINO_ADDRESS = 0x08

# ==================== СЕНСОРЫ/ПОРОГИ ====================
SENSOR_ERR = 999
SENSOR_FWD_STOP_CM = 30
SENSOR_BWD_STOP_CM = 30
SENSOR_MAX_VALID = 500

# ==================== СКОРОСТЬ (0..255) ====================
SPEED_MIN = 0
SPEED_MAX = 255
DEFAULT_SPEED = 70

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

# ==================== КАМЕРА ====================

# Проверка доступности OpenCV
CAMERA_AVAILABLE = True
try:
    import cv2  # noqa: F401
except ImportError:
    CAMERA_AVAILABLE = False

# Основные настройки камеры
CAMERA_DEVICE_ID = 0  # /dev/video0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30

# Качество изображения
CAMERA_QUALITY = 80  # JPEG качество (1-100)
CAMERA_STREAM_QUALITY = 60  # Для веб-стрима
CAMERA_STREAM_FPS = 15  # FPS веб-стрима

# Настройки изображения
CAMERA_BRIGHTNESS = 50  # 0-100
CAMERA_CONTRAST = 50      # 0-100
CAMERA_SATURATION = 65  # 0-100

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

# ==================== ПРЕДУСТАНОВКИ ====================


# Предустановки качества камеры
CAMERA_PRESETS = {
    "low": {
        "width": 320,
        "height": 240,
        "fps": 15,
        "quality": 50,
        "stream_quality": 40,
        "stream_fps": 10
    },
    "medium": {
        "width": 640,
        "height": 480,
        "fps": 30,
        "quality": 70,
        "stream_quality": 60,
        "stream_fps": 15
    },
    "high": {
        "width": 1280,
        "height": 720,
        "fps": 30,
        "quality": 90,
        "stream_quality": 75,
        "stream_fps": 20
    },
    "ultra": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "quality": 95,
        "stream_quality": 80,
        "stream_fps": 25
    }
}

# Текущая предустановка
CAMERA_PRESET = "medium"


def get_camera_preset(preset_name: str = None) -> dict:
    """Получить настройки камеры по предустановке"""
    preset = preset_name or CAMERA_PRESET
    if preset in CAMERA_PRESETS:
        return CAMERA_PRESETS[preset].copy()
    return CAMERA_PRESETS["medium"].copy()

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

# ==================== УТИЛИТЫ КОНФИГУРАЦИИ ====================


def load_preset(preset_name: str):
    """Загрузить предустановку камеры"""
    preset = get_camera_preset(preset_name)

    global CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS
    global CAMERA_QUALITY, CAMERA_STREAM_QUALITY, CAMERA_STREAM_FPS

    CAMERA_WIDTH = preset["width"]
    CAMERA_HEIGHT = preset["height"]
    CAMERA_FPS = preset["fps"]
    CAMERA_QUALITY = preset["quality"]
    CAMERA_STREAM_QUALITY = preset["stream_quality"]
    CAMERA_STREAM_FPS = preset["stream_fps"]

    # Обновляем словарь конфигурации
    CAMERA_CONFIG.update(preset)


def create_camera_config_dict():
    """Создать словарь конфигурации для передачи в камеру"""
    return {
        'device_id': CAMERA_DEVICE_ID,
        'width': CAMERA_WIDTH,
        'height': CAMERA_HEIGHT,
        'fps': CAMERA_FPS,
        'quality': CAMERA_QUALITY,
        'stream_quality': CAMERA_STREAM_QUALITY,
        'stream_fps': CAMERA_STREAM_FPS,
        'brightness': CAMERA_BRIGHTNESS,
        'contrast': CAMERA_CONTRAST,
        'saturation': CAMERA_SATURATION,
        'save_path': CAMERA_SAVE_PATH,
        'video_path': CAMERA_VIDEO_PATH,
        'auto_start': CAMERA_AUTO_START
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
