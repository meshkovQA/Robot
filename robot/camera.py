# robot/camera.py

from __future__ import annotations
import cv2
import threading
import time
import logging
import base64
import io
from typing import Optional, Tuple, Callable
from dataclasses import dataclass, field
from pathlib import Path
import os

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Конфигурация камеры"""
    device_id: int = 0  # /dev/video0
    width: int = 640
    height: int = 480
    fps: int = 30
    quality: int = 80  # JPEG качество (1-100)
    auto_start: bool = True
    save_path: str = f"{os.path.expanduser('~')}/robot_web/photos"
    video_path: str = f"{os.path.expanduser('~')}/robot_web/videos"

    # Настройки камеры
    brightness: int = 50  # 0-100
    contrast: int = 50    # 0-100
    saturation: int = 50  # 0-100

    # Настройки стрима
    stream_quality: int = 60  # Качество для веб-стрима
    stream_fps: int = 15      # FPS для веб-стрима


@dataclass
class CameraStatus:
    """Статус камеры"""
    is_connected: bool = False
    is_streaming: bool = False
    is_recording: bool = False
    frame_count: int = 0
    fps_actual: float = 0.0
    last_frame_time: float = 0.0
    error_message: str = ""
    recording_file: str = ""
    recording_duration: float = 0.0


class USBCamera:
    """Управление USB камерой с поддержкой стрима, записи и фото"""

    def __init__(self, config: CameraConfig = None):
        self.config = config or CameraConfig()
        self.status = CameraStatus()

        # OpenCV объекты
        self._cap: Optional[cv2.VideoCapture] = None
        self._writer: Optional[cv2.VideoWriter] = None

        # Потоки
        self._capture_thread: Optional[threading.Thread] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Синхронизация
        self._frame_lock = threading.RLock()
        self._current_frame: Optional[cv2.typing.MatLike] = None
        self._stream_frame: Optional[bytes] = None

        # Статистика
        self._frame_times: list[float] = []
        self._recording_start_time: float = 0.0

        # Колбэки
        self._frame_callbacks: list[Callable[[cv2.typing.MatLike], None]] = []

        # Создаем директории
        self._ensure_directories()

        if self.config.auto_start:
            self.start()

    def _ensure_directories(self):
        """Создание необходимых директорий"""
        for path in [self.config.save_path, self.config.video_path]:
            Path(path).mkdir(parents=True, exist_ok=True)
            logger.info(f"Директория создана/проверена: {path}")

    def start(self) -> bool:
        """Запуск камеры"""
        if self.status.is_connected:
            logger.warning("Камера уже запущена")
            return True

        try:
            logger.info(
                f"Попытка подключения к камере /dev/video{self.config.device_id}")

            # Открываем камеру
            self._cap = cv2.VideoCapture(self.config.device_id)

            if not self._cap.isOpened():
                raise Exception(
                    f"Не удалось открыть камеру /dev/video{self.config.device_id}")

            # Настройка параметров камеры
            self._setup_camera()

            # Тестовый кадр
            ret, frame = self._cap.read()
            if not ret or frame is None:
                raise Exception("Не удалось получить тестовый кадр")

            logger.info(f"Получен тестовый кадр: {frame.shape}")

            # Запуск потоков
            self._stop_event.clear()
            self._capture_thread = threading.Thread(
                target=self._capture_loop, daemon=True)
            self._stream_thread = threading.Thread(
                target=self._stream_loop, daemon=True)

            self._capture_thread.start()
            self._stream_thread.start()

            self.status.is_connected = True
            self.status.is_streaming = True
            self.status.error_message = ""

            logger.info("✅ Камера успешно запущена")
            return True

        except Exception as e:
            error_msg = f"Ошибка запуска камеры: {e}"
            logger.error(error_msg)
            self.status.error_message = error_msg
            self.status.is_connected = False
            self._cleanup_camera()
            return False

    def _setup_camera(self):
        """Настройка параметров камеры"""
        if not self._cap:
            return

        # Основные параметры
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.config.fps)

        # Настройки изображения (если поддерживаются)
        try:
            self._cap.set(cv2.CAP_PROP_BRIGHTNESS,
                          self.config.brightness / 100.0)
            self._cap.set(cv2.CAP_PROP_CONTRAST, self.config.contrast / 100.0)
            self._cap.set(cv2.CAP_PROP_SATURATION,
                          self.config.saturation / 100.0)
        except Exception as e:
            logger.warning(f"Не удалось установить параметры изображения: {e}")

        # Буферизация
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        logger.info("Параметры камеры настроены")

    def _capture_loop(self):
        """Основной цикл захвата кадров"""
        logger.info("Запущен поток захвата кадров")

        while not self._stop_event.is_set() and self._cap and self._cap.isOpened():
            try:
                ret, frame = self._cap.read()

                if not ret or frame is None:
                    logger.warning("Не удалось получить кадр")
                    time.sleep(0.1)
                    continue

                current_time = time.time()

                with self._frame_lock:
                    self._current_frame = frame.copy()
                    self.status.frame_count += 1
                    self.status.last_frame_time = current_time

                # Статистика FPS
                self._frame_times.append(current_time)
                if len(self._frame_times) > 30:  # Последние 30 кадров
                    self._frame_times.pop(0)

                if len(self._frame_times) > 1:
                    fps = len(self._frame_times) / \
                        (self._frame_times[-1] - self._frame_times[0])
                    self.status.fps_actual = round(fps, 1)

                # Колбэки для обработки кадров
                for callback in self._frame_callbacks:
                    try:
                        callback(frame)
                    except Exception as e:
                        logger.error(f"Ошибка в колбэке обработки кадра: {e}")

                # Запись видео
                if self.status.is_recording and self._writer:
                    self._writer.write(frame)
                    self.status.recording_duration = current_time - self._recording_start_time

                # Небольшая пауза для снижения нагрузки
                time.sleep(
                    1.0 / self.config.fps if self.config.fps > 0 else 0.033)

            except Exception as e:
                logger.error(f"Ошибка в цикле захвата: {e}")
                time.sleep(1.0)

        logger.info("Поток захвата кадров завершен")

    def _stream_loop(self):
        """Цикл подготовки кадров для веб-стрима"""
        logger.info("Запущен поток веб-стрима")

        while not self._stop_event.is_set():
            try:
                with self._frame_lock:
                    if self._current_frame is None:
                        time.sleep(0.1)
                        continue

                    frame = self._current_frame.copy()

                # Изменяем размер для стрима (экономим трафик)
                stream_width = min(self.config.width, 480)
                stream_height = int(
                    stream_width * self.config.height / self.config.width)

                if frame.shape[1] != stream_width:
                    frame = cv2.resize(frame, (stream_width, stream_height))

                # Кодируем в JPEG для веб-стрима
                encode_param = [cv2.IMWRITE_JPEG_QUALITY,
                                self.config.stream_quality]
                _, buffer = cv2.imencode('.jpg', frame, encode_param)

                with self._frame_lock:
                    self._stream_frame = buffer.tobytes()

                # Ограничиваем FPS стрима
                time.sleep(
                    1.0 / self.config.stream_fps if self.config.stream_fps > 0 else 0.066)

            except Exception as e:
                logger.error(f"Ошибка в потоке стрима: {e}")
                time.sleep(1.0)

        logger.info("Поток веб-стрима завершен")

    def get_frame_jpeg(self) -> Optional[bytes]:
        """Получение текущего кадра в формате JPEG для веб-стрима"""
        with self._frame_lock:
            return self._stream_frame

    def get_frame_base64(self) -> Optional[str]:
        """Получение текущего кадра в формате base64"""
        jpeg_data = self.get_frame_jpeg()
        if jpeg_data:
            return base64.b64encode(jpeg_data).decode('utf-8')
        return None

    def take_photo(self, filename: str = None) -> Tuple[bool, str]:
        """Сделать фотографию"""
        if not self.status.is_connected:
            return False, "Камера не подключена"

        with self._frame_lock:
            if self._current_frame is None:
                return False, "Нет доступных кадров"

            frame = self._current_frame.copy()

        try:
            if filename is None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"photo_{timestamp}.jpg"

            if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                filename += '.jpg'

            filepath = Path(self.config.save_path) / filename

            # Сохраняем с высоким качеством
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, self.config.quality]
            success = cv2.imwrite(str(filepath), frame, encode_param)

            if success:
                logger.info(f"Фото сохранено: {filepath}")
                return True, str(filepath)
            else:
                return False, "Ошибка сохранения файла"

        except Exception as e:
            error_msg = f"Ошибка при создании фото: {e}"
            logger.error(error_msg)
            return False, error_msg

    def start_recording(self, filename: str = None, duration: float = None) -> Tuple[bool, str]:
        """Начать запись видео"""
        if not self.status.is_connected:
            return False, "Камера не подключена"

        if self.status.is_recording:
            return False, "Запись уже идет"

        try:
            if filename is None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"video_{timestamp}.mp4"

            if not filename.lower().endswith(('.mp4', '.avi', '.mov')):
                filename += '.mp4'

            filepath = Path(self.config.video_path) / filename

            # Настройка кодека
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')

            self._writer = cv2.VideoWriter(
                str(filepath),
                fourcc,
                self.config.fps,
                (self.config.width, self.config.height)
            )

            if not self._writer.isOpened():
                raise Exception("Не удалось инициализировать запись видео")

            self.status.is_recording = True
            self.status.recording_file = str(filepath)
            self._recording_start_time = time.time()
            self.status.recording_duration = 0.0

            logger.info(f"Начата запись видео: {filepath}")

            # Автоостановка записи через заданное время
            if duration and duration > 0:
                def auto_stop():
                    time.sleep(duration)
                    if self.status.is_recording:
                        self.stop_recording()
                        logger.info(
                            f"Запись автоматически остановлена через {duration} сек")

                threading.Thread(target=auto_stop, daemon=True).start()

            return True, str(filepath)

        except Exception as e:
            error_msg = f"Ошибка начала записи: {e}"
            logger.error(error_msg)
            return False, error_msg

    def stop_recording(self) -> Tuple[bool, str]:
        """Остановить запись видео"""
        if not self.status.is_recording:
            return False, "Запись не идет"

        try:
            if self._writer:
                self._writer.release()
                self._writer = None

            filepath = self.status.recording_file
            duration = self.status.recording_duration

            self.status.is_recording = False
            self.status.recording_file = ""
            self.status.recording_duration = 0.0

            logger.info(f"Запись остановлена: {filepath} ({duration:.1f} сек)")
            return True, filepath

        except Exception as e:
            error_msg = f"Ошибка остановки записи: {e}"
            logger.error(error_msg)
            return False, error_msg

    def add_frame_callback(self, callback: Callable[[cv2.typing.MatLike], None]):
        """Добавить колбэк для обработки каждого кадра"""
        self._frame_callbacks.append(callback)

    def remove_frame_callback(self, callback: Callable[[cv2.typing.MatLike], None]):
        """Удалить колбэк обработки кадров"""
        if callback in self._frame_callbacks:
            self._frame_callbacks.remove(callback)

    def get_status(self) -> dict:
        """Получить статус камеры"""
        return {
            "connected": self.status.is_connected,
            "streaming": self.status.is_streaming,
            "recording": self.status.is_recording,
            "frame_count": self.status.frame_count,
            "fps": self.status.fps_actual,
            "last_frame_time": self.status.last_frame_time,
            "error": self.status.error_message,
            "recording_file": self.status.recording_file,
            "recording_duration": round(self.status.recording_duration, 1),
            "config": {
                "device_id": self.config.device_id,
                "resolution": f"{self.config.width}x{self.config.height}",
                "fps_target": self.config.fps,
                "quality": self.config.quality
            }
        }

    def _cleanup_camera(self):
        """Очистка ресурсов камеры"""
        if self._writer:
            self._writer.release()
            self._writer = None

        if self._cap:
            self._cap.release()
            self._cap = None

        self.status.is_connected = False
        self.status.is_streaming = False

    def stop(self):
        """Остановка камеры"""
        logger.info("Начало остановки камеры...")

        # Останавливаем запись если идет
        if self.status.is_recording:
            self.stop_recording()

        # Сигнал остановки потоков
        self._stop_event.set()

        # Ждем завершения потоков
        for thread in [self._capture_thread, self._stream_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)

        # Очистка ресурсов
        self._cleanup_camera()

        self.status.is_recording = False
        logger.info("Камера остановлена")

    def restart(self) -> bool:
        """Перезапуск камеры"""
        logger.info("Перезапуск камеры...")
        self.stop()
        time.sleep(1.0)
        return self.start()

    def __del__(self):
        """Деструктор"""
        self.stop()


# Удобные функции для быстрого использования
def create_camera(device_id: int = 0, width: int = 640, height: int = 480) -> USBCamera:
    """Создание камеры с базовыми настройками"""
    config = CameraConfig(
        device_id=device_id,
        width=width,
        height=height,
        auto_start=False
    )
    return USBCamera(config)


def list_available_cameras() -> list[int]:
    """Получение списка доступных камер"""
    available = []
    for i in range(5):  # Проверяем первые 5 устройств
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available.append(i)
                logger.info(f"Найдена камера: /dev/video{i}")
        cap.release()
    return available
