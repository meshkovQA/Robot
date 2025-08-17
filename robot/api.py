# api.py

from __future__ import annotations
import logging
import signal
import time
from datetime import datetime
from flask import Flask, Blueprint, jsonify, request, render_template,  Response, stream_template
from pathlib import Path

from .controller import RobotController
from .camera import USBCamera, CameraConfig, list_available_cameras
from .config import LOG_LEVEL, LOG_FMT, API_KEY, SPEED_MIN, SPEED_MAX

logging.basicConfig(level=LOG_LEVEL, format=LOG_FMT)
logger = logging.getLogger(__name__)


def create_app(controller: RobotController | None = None) -> Flask:
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')
    robot = controller or RobotController()

    # Инициализация камеры
    if camera is None:
        try:
            available_cameras = list_available_cameras()
            if available_cameras:
                camera_config = CameraConfig(
                    # Используем первую найденную камеру
                    device_id=available_cameras[0],
                    width=640,
                    height=480,
                    fps=30,
                    auto_start=True
                )
                camera = USBCamera(camera_config)
                logger.info(
                    f"🎥 Камера инициализирована: /dev/video{available_cameras[0]}")
            else:
                logger.warning("🎥 USB камеры не найдены")
                camera = None
        except Exception as e:
            logger.error(f"🎥 Ошибка инициализации камеры: {e}")
            camera = None

    # API Blueprint
    bp = Blueprint("api", __name__)

    # --------- утилиты ответов ----------
    def ok(data=None, code=200):
        return jsonify({
            "success": True,
            "data": data or {},
            "timestamp": datetime.now().isoformat()
        }), code

    def err(msg, code=400):
        return jsonify({
            "success": False,
            "error": msg,
            "timestamp": datetime.now().isoformat()
        }), code

    # --------- простая аутентификация ----------
    @app.before_request
    def _auth():
        if API_KEY and request.path.startswith("/api/"):
            if request.headers.get("X-API-Key") != API_KEY:
                return err("unauthorized", 401)

    # --------- главная страница ----------
    @app.route("/")
    def index():
        """Главная страница с веб-интерфейсом"""
        return render_template("index.html")

    # --------- API маршруты движения ----------
    @bp.route("/move/forward", methods=["POST"])
    def move_forward():
        data = request.get_json() or {}
        speed = int(data.get("speed", 100))
        speed = max(SPEED_MIN, min(SPEED_MAX, speed))

        success = robot.move_forward(speed)
        return ok({
            "command": "move_forward",
            "speed": speed,
            "success": success,
            **robot.get_status()
        })

    @bp.route("/move/backward", methods=["POST"])
    def move_backward():
        data = request.get_json() or {}
        speed = int(data.get("speed", 100))
        speed = max(SPEED_MIN, min(SPEED_MAX, speed))

        success = robot.move_backward(speed)
        return ok({
            "command": "move_backward",
            "speed": speed,
            "success": success,
            **robot.get_status()
        })

    @bp.route("/turn/left", methods=["POST"])
    def turn_left():
        data = request.get_json() or {}
        speed = int(data.get("speed", 150))
        speed = max(SPEED_MIN, min(SPEED_MAX, speed))

        success = robot.tank_turn_left(speed)
        return ok({
            "command": "tank_turn_left",
            "speed": speed,
            "success": success,
            **robot.get_status()
        })

    @bp.route("/turn/right", methods=["POST"])
    def turn_right():
        data = request.get_json() or {}
        speed = int(data.get("speed", 150))
        speed = max(SPEED_MIN, min(SPEED_MAX, speed))

        success = robot.tank_turn_right(speed)
        return ok({
            "command": "tank_turn_right",
            "speed": speed,
            "success": success,
            **robot.get_status()
        })

    # --------- универсальное управление ----------
    @bp.route("/move", methods=["POST"])
    def universal_move():
        """Универсальное управление движением и рулем"""
        data = request.get_json() or {}
        speed = int(data.get("speed", 0))
        direction = int(data.get("direction", 0))  # 0=stop, 1=fwd, 2=bwd
        steering = int(data.get("steering", 90))   # 10-170, 90=center

        speed = max(SPEED_MIN, min(SPEED_MAX, speed))
        steering = max(10, min(170, steering))

        success = robot.move_with_steering(speed, direction, steering)
        return ok({
            "command": "universal_move",
            "speed": speed,
            "direction": direction,
            "steering": steering,
            "success": success,
            **robot.get_status()
        })

    @bp.route("/speed", methods=["POST"])
    def update_speed():
        data = request.get_json() or {}
        new_speed = int(data.get("speed", 0))
        new_speed = max(SPEED_MIN, min(SPEED_MAX, new_speed))

        success = robot.update_speed(new_speed)
        status = robot.get_status()

        return ok({
            "command": "update_speed",
            "new_speed": new_speed,
            "success": success,
            **status
        })

    @bp.route("/stop", methods=["POST"])
    def stop():
        success = robot.stop()
        return ok({
            "command": "stop",
            "success": success,
            **robot.get_status()
        })

    @bp.route("/emergency_stop", methods=["POST"])
    def emergency_stop():
        logger.warning("🚨 ЭКСТРЕННАЯ ОСТАНОВКА ВЫПОЛНЕНА!")
        success = robot.stop()
        return ok({
            "command": "emergency_stop",
            "success": success,
            **robot.get_status()
        })

    # --------- API маршруты камеры ----------

    @bp.route("/camera/status", methods=["GET"])
    def camera_status():
        """Статус камеры"""
        if not camera:
            return ok({
                "available": False,
                "error": "Камера не инициализирована"
            })

        return ok({
            "available": True,
            **camera.get_status()
        })

    @bp.route("/camera/photo", methods=["POST"])
    def take_photo():
        """Сделать фотографию"""
        if not camera:
            return err("Камера недоступна", 404)

        data = request.get_json() or {}
        filename = data.get("filename")

        success, result = camera.take_photo(filename)

        if success:
            return ok({
                "command": "take_photo",
                "filepath": result,
                "filename": Path(result).name
            })
        else:
            return err(f"Ошибка создания фото: {result}")

    @bp.route("/camera/recording/start", methods=["POST"])
    def start_recording():
        """Начать запись видео"""
        if not camera:
            return err("Камера недоступна", 404)

        data = request.get_json() or {}
        filename = data.get("filename")
        duration = data.get("duration")  # Максимальная длительность в секундах

        success, result = camera.start_recording(filename, duration)

        if success:
            return ok({
                "command": "start_recording",
                "filepath": result,
                "filename": Path(result).name,
                "duration_limit": duration
            })
        else:
            return err(f"Ошибка начала записи: {result}")

    @bp.route("/camera/recording/stop", methods=["POST"])
    def stop_recording():
        """Остановить запись видео"""
        if not camera:
            return err("Камера недоступна", 404)

        success, result = camera.stop_recording()

        if success:
            return ok({
                "command": "stop_recording",
                "filepath": result,
                "filename": Path(result).name if result else ""
            })
        else:
            return err(f"Ошибка остановки записи: {result}")

    @bp.route("/camera/restart", methods=["POST"])
    def restart_camera():
        """Перезапуск камеры"""
        if not camera:
            return err("Камера недоступна", 404)

        success = camera.restart()

        if success:
            return ok({
                "command": "restart_camera",
                "status": "Камера перезапущена"
            })
        else:
            return err("Ошибка перезапуска камеры")

    @bp.route("/camera/devices", methods=["GET"])
    def list_cameras():
        """Список доступных камер"""
        try:
            available = list_available_cameras()
            return ok({
                "available_cameras": available,
                "count": len(available)
            })
        except Exception as e:
            return err(f"Ошибка сканирования камер: {e}")

    # --------- Веб-стрим камеры ----------
    @app.route("/camera/stream")
    def camera_stream():
        """MJPEG стрим камеры"""
        if not camera or not camera.status.is_connected:
            # Возвращаем статическое изображение с ошибкой
            return Response(
                b'--frame\r\nContent-Type: text/plain\r\n\r\nCamera not available\r\n',
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )

        def generate():
            while True:
                frame_data = camera.get_frame_jpeg()
                if frame_data:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
                else:
                    # Если нет кадра, отправляем заглушку
                    yield (b'--frame\r\n'
                           b'Content-Type: text/plain\r\n\r\nNo frame available\r\n')

                time.sleep(1.0 / (camera.config.stream_fps if camera else 10))

        return Response(
            generate(),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )

    @bp.route("/camera/frame", methods=["GET"])
    def get_frame():
        """Получить один кадр в формате base64"""
        if not camera:
            return err("Камера недоступна", 404)

        frame_b64 = camera.get_frame_base64()

        if frame_b64:
            return ok({
                "frame": frame_b64,
                "format": "base64_jpeg",
                "timestamp": time.time()
            })
        else:
            return err("Нет доступных кадров")

    # --------- мониторинг и диагностика (существующие + расширенные) ----------
    @bp.route("/status", methods=["GET"])
    def status():
        robot_status = robot.get_status()

        # Добавляем статус камеры если доступна
        if camera:
            robot_status["camera"] = camera.get_status()
        else:
            robot_status["camera"] = {"available": False}

        return ok(robot_status)

    @bp.route("/health", methods=["GET"])
    def health():
        status = robot.get_status()
        status.update({
            "i2c_connected": robot.bus is not None,
            "controller_active": True,
            "camera_available": camera is not None,
            "camera_connected": camera.status.is_connected if camera else False,
            "api_version": "2.1"  # Обновили версию для поддержки камеры
        })
        return ok(status)

    @bp.route("/sensors", methods=["GET"])
    def sensors():
        front, rear = robot.read_sensors()
        sensor_data = {
            "front_distance": front,
            "rear_distance": rear,
            "front_obstacle": front != 999 and front < 15,
            "rear_obstacle": rear != 999 and rear < 10,
            "sensors_working": front != 999 and rear != 999
        }

        # Добавляем информацию о камере
        if camera:
            sensor_data["camera"] = {
                "connected": camera.status.is_connected,
                "fps": camera.status.fps_actual,
                "frame_count": camera.status.frame_count
            }

        return ok(sensor_data)

    # --------- файловая система (для фото/видео) ----------
    @bp.route("/files/photos", methods=["GET"])
    def list_photos():
        """Список сохраненных фотографий"""
        if not camera:
            return err("Камера недоступна", 404)

        try:
            photo_dir = Path(camera.config.save_path)
            if not photo_dir.exists():
                return ok({"files": [], "count": 0})

            photos = []
            for file in photo_dir.glob("*.jpg"):
                stat = file.stat()
                photos.append({
                    "filename": file.name,
                    "path": str(file),
                    "size": stat.st_size,
                    "created": stat.st_mtime,
                    "created_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })

            # Сортируем по времени создания (новые первые)
            photos.sort(key=lambda x: x["created"], reverse=True)

            return ok({
                "files": photos,
                "count": len(photos),
                "directory": str(photo_dir)
            })

        except Exception as e:
            return err(f"Ошибка чтения директории фото: {e}")

    @bp.route("/files/videos", methods=["GET"])
    def list_videos():
        """Список сохраненных видео"""
        if not camera:
            return err("Камера недоступна", 404)

        try:
            video_dir = Path(camera.config.video_path)
            if not video_dir.exists():
                return ok({"files": [], "count": 0})

            videos = []
            for file in video_dir.glob("*.mp4"):
                stat = file.stat()
                videos.append({
                    "filename": file.name,
                    "path": str(file),
                    "size": stat.st_size,
                    "created": stat.st_mtime,
                    "created_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })

            # Сортируем по времени создания (новые первые)
            videos.sort(key=lambda x: x["created"], reverse=True)

            return ok({
                "files": videos,
                "count": len(videos),
                "directory": str(video_dir)
            })

        except Exception as e:
            return err(f"Ошибка чтения директории видео: {e}")

    @bp.route("/files/delete", methods=["POST"])
    def delete_file():
        """Удаление файла"""
        data = request.get_json() or {}
        filepath = data.get("filepath")

        if not filepath:
            return err("Не указан путь к файлу")

        try:
            file_path = Path(filepath)

            # Проверяем что файл в разрешенных директориях
            if camera:
                allowed_dirs = [
                    Path(camera.config.save_path),
                    Path(camera.config.video_path)
                ]

                if not any(file_path.is_relative_to(dir) for dir in allowed_dirs):
                    return err("Файл вне разрешенных директорий", 403)

            if file_path.exists():
                file_path.unlink()
                return ok({
                    "command": "delete_file",
                    "filepath": str(file_path),
                    "status": "Файл удален"
                })
            else:
                return err("Файл не найден", 404)

        except Exception as e:
            return err(f"Ошибка удаления файла: {e}")

    # Регистрируем API blueprint
    app.register_blueprint(bp, url_prefix="/api")

    # --------- обработка ошибок ----------
    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return err("endpoint not found", 404)
        return render_template("index.html")  # Возвращаем главную для SPA

    @app.errorhandler(500)
    def internal_error(error):
        logger.error("Internal server error: %s", error)
        return err("internal server error", 500)

    # --------- корректное завершение ----------
    def _graceful_shutdown(*_):
        logger.info("🔄 Завершение по сигналу...")
        try:
            robot.shutdown()
            if camera:
                camera.stop()
        except Exception as e:
            logger.error("Ошибка при завершении: %s", e)
        finally:
            raise SystemExit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    # Сохраняем ссылки на компоненты для доступа извне
    app.robot = robot  # type: ignore[attr-defined]
    app.camera = camera  # type: ignore[attr-defined]

    logger.info("🤖 Flask приложение создано успешно с поддержкой камеры")
    return app
