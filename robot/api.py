# api.py - ИСПРАВЛЕНИЕ CORS

from __future__ import annotations
import logging
import signal
import os
import time
from datetime import datetime
from flask import Flask, Blueprint, jsonify, request, render_template, Response
from flask_cors import CORS  # ДОБАВЛЯЕМ CORS
from pathlib import Path

from .controller import RobotController
from .camera import USBCamera, CameraConfig, list_available_cameras
from .config import LOG_LEVEL, LOG_FMT, API_KEY, SPEED_MIN, SPEED_MAX
from datetime import datetime
from pathlib import Path
from .config import CAMERA_SAVE_PATH, CAMERA_VIDEO_PATH

logging.basicConfig(level=LOG_LEVEL, format=LOG_FMT)
logger = logging.getLogger(__name__)


def create_app(controller: RobotController | None = None, camera_instance: USBCamera | None = None) -> Flask:
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    # ВКЛЮЧАЕМ CORS ДЛЯ ВСЕХ МАРШРУТОВ
    CORS(app, origins="*", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

    robot = controller or RobotController()

    # Если включён «лёгкий» режим – не поднимаем камеру
    LIGHT_INIT = os.getenv("APP_LIGHT_INIT", "0") == "1"

    camera = camera_instance
    if camera is None and not LIGHT_INIT:
        try:
            from .config import CAMERA_AVAILABLE, CAMERA_CONFIG
            if CAMERA_AVAILABLE:
                available_cameras = list_available_cameras()
                if available_cameras:
                    camera_config = CameraConfig(
                        device_id=available_cameras[0],
                        width=CAMERA_CONFIG.get('width', 640),
                        height=CAMERA_CONFIG.get('height', 480),
                        fps=CAMERA_CONFIG.get('fps', 30),
                        auto_start=True
                    )
                    camera = USBCamera(camera_config)
                    logger.info(
                        f"🎥 Камера инициализирована: /dev/video{available_cameras[0]}")
                else:
                    logger.warning("🎥 USB камеры не найдены")
                    camera = None
            else:
                logger.warning("🎥 OpenCV недоступен")
                camera = None
        except Exception as e:
            logger.error(f"🎥 Ошибка инициализации камеры: {e}")
            camera = None

    # API Blueprint
    bp = Blueprint("api", __name__)

    # --------- утилиты ответов ----------
    def ok(data=None, code=200):
        response = jsonify({
            "success": True,
            "data": data or {},
            "timestamp": datetime.now().isoformat()
        })
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response, code

    def err(msg, code=400):
        response = jsonify({
            "success": False,
            "error": msg,
            "timestamp": datetime.now().isoformat()
        })
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response, code

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
                "connected": False,
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
        duration = data.get("duration")

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

        def generate():
            """Генератор кадров для MJPEG стрима"""
            # Заглушка - черный квадрат в JPEG
            import base64
            BLACK_JPEG_B64 = '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/gA=='
            BLACK_JPEG = base64.b64decode(BLACK_JPEG_B64)

            logger.info("Запущен MJPEG генератор")

            while True:
                try:
                    frame_data = None

                    # Пытаемся получить кадр от камеры
                    if camera and camera.status.is_connected:
                        frame_data = camera.get_frame_jpeg()

                    # Если нет кадра - используем заглушку
                    if not frame_data:
                        frame_data = BLACK_JPEG

                    # Отправляем кадр в MJPEG формате
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Content-Length: ' +
                           str(len(frame_data)).encode() + b'\r\n'
                           b'\r\n' + frame_data + b'\r\n')

                    # Контролируем FPS
                    if camera and hasattr(camera.config, 'stream_fps'):
                        fps = max(camera.config.stream_fps, 5)
                    else:
                        fps = 10

                    time.sleep(1.0 / fps)

                except GeneratorExit:
                    logger.info("MJPEG генератор остановлен")
                    break
                except Exception as e:
                    logger.error(f"Ошибка в MJPEG генераторе: {e}")
                    # При ошибке отправляем заглушку
                    try:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n'
                               b'Content-Length: ' +
                               str(len(BLACK_JPEG)).encode() + b'\r\n'
                               b'\r\n' + BLACK_JPEG + b'\r\n')
                    except:
                        break
                    time.sleep(1.0)

        response = Response(
            generate(),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Connection': 'close',
                'Access-Control-Allow-Origin': '*'
            }
        )
        return response

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

    # --------- мониторинг и диагностика ----------

    def _collect_files(dir_path: str, exts: tuple[str, ...]) -> list[dict]:
        p = Path(dir_path)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)

        items = []
        for f in p.iterdir():
            if f.is_file() and f.suffix.lower() in exts:
                stat = f.stat()
                created = int(stat.st_mtime)
                items.append({
                    "filename": f.name,
                    "path": str(f.resolve()),
                    "size": stat.st_size,
                    "created": created,
                    "created_str": datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S"),
                })
        # новые сверху
        items.sort(key=lambda x: x["created"], reverse=True)
        return items

    @bp.route("/files/photos", methods=["GET"])
    def files_photos():
        try:
            files = _collect_files(CAMERA_SAVE_PATH, (".jpg", ".jpeg", ".png"))
            return ok({"files": files})
        except Exception as e:
            return err(f"Ошибка списка фото: {e}", 500)

    @bp.route("/files/videos", methods=["GET"])
    def files_videos():
        try:
            files = _collect_files(
                CAMERA_VIDEO_PATH, (".mp4", ".avi", ".mov", ".mkv"))
            return ok({"files": files})
        except Exception as e:
            return err(f"Ошибка списка видео: {e}", 500)

    @bp.route("/files/delete", methods=["POST"])
    def files_delete():
        data = request.get_json() or {}
        filepath = data.get("filepath")
        if not filepath:
            return err("Не указан filepath", 400)

        try:
            target = Path(filepath).resolve()
            photos_root = Path(CAMERA_SAVE_PATH).resolve()
            videos_root = Path(CAMERA_VIDEO_PATH).resolve()

            # защита: удаляем только из наших директорий
            if not (str(target).startswith(str(photos_root)) or str(target).startswith(str(videos_root))):
                return err("Недопустимый путь", 400)

            if target.exists() and target.is_file():
                target.unlink()
                return ok({"deleted": str(target.name)})
            else:
                return err("Файл не найден", 404)
        except Exception as e:
            return err(f"Ошибка удаления: {e}", 500)

    @bp.route("/status", methods=["GET"])
    def status():
        robot_status = robot.get_status()

        # Добавляем статус камеры если доступна
        if camera:
            robot_status["camera"] = camera.get_status()
        else:
            robot_status["camera"] = {"available": False, "connected": False}

        return ok(robot_status)

    @bp.route("/health", methods=["GET"])
    def health():
        status = robot.get_status()
        status.update({
            "i2c_connected": robot.bus is not None,
            "controller_active": True,
            "camera_available": camera is not None,
            "camera_connected": camera.status.is_connected if camera else False,
            "api_version": "2.1"
        })
        return ok(status)

    # Остальные маршруты остаются такими же...
    # (сократил для краткости, добавьте остальные из предыдущего кода)

    # Регистрируем API blueprint
    app.register_blueprint(bp, url_prefix="/api")

    # --------- обработка ошибок ----------
    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return err("endpoint not found", 404)
        return render_template("index.html")

    @app.errorhandler(500)
    def internal_error(error):
        logger.error("Internal server error: %s", error)
        if request.path.startswith("/api/"):
            return err("internal server error", 500)
        return render_template("index.html")

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
    app.robot = robot
    app.camera = camera

    logger.info("🤖 Flask приложение создано успешно с поддержкой камеры")
    return app
