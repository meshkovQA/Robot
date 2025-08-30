# robot/api/api.py

from __future__ import annotations
import logging
import signal
import time
from datetime import datetime
from flask import Flask, Blueprint, jsonify, request, render_template, Response
from flask_cors import CORS  # ДОБАВЛЯЕМ CORS
from pathlib import Path

from robot.controller import RobotController
from robot.devices.camera import USBCamera, CameraConfig, list_available_cameras
from robot.devices.imu import MPU6500
from robot.heading_controller import HeadingHoldService
from robot.ai_integration import AIRobotController
from robot.ai_vision.home_ai_vision import HomeAIVision
from robot.api.ai_api_extensions import add_ai_routes
from robot.config import LOG_LEVEL, LOG_FMT, API_KEY, SPEED_MIN, SPEED_MAX, CAMERA_SAVE_PATH, CAMERA_VIDEO_PATH, CAMERA_AVAILABLE, CAMERA_CONFIG, LIGHT_INIT, STATIC_DIR, TEMPLATES_DIR
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=LOG_LEVEL, format=LOG_FMT)
logger = logging.getLogger(__name__)


def create_app(controller: RobotController | None = None, camera_instance: USBCamera | None = None) -> Flask:
    app = Flask(__name__,
                template_folder=TEMPLATES_DIR,
                static_folder=STATIC_DIR)

    STATIC_ROOT = Path(app.static_folder).resolve()

    PHOTOS_DIR = Path(CAMERA_SAVE_PATH)
    VIDEOS_DIR = Path(CAMERA_VIDEO_PATH)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    # ВКЛЮЧАЕМ CORS ДЛЯ ВСЕХ МАРШРУТОВ
    CORS(app, origins="*", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

    robot = controller or RobotController()

    heading = None

    camera = camera_instance

    # инициализируем камеру ТОЛЬКО если лёгкий режим выключен
    if camera is None and not LIGHT_INIT:
        try:
            if CAMERA_AVAILABLE:
                # сначала пробуем выбранный в конфиге device_id
                preferred_id = CAMERA_CONFIG.get("device_id", 0)
                available_cameras = list_available_cameras()

                device_id = None
                if preferred_id in available_cameras:
                    device_id = preferred_id
                elif available_cameras:
                    device_id = available_cameras[0]

                if device_id is not None:
                    camera_config = CameraConfig(
                        device_id=device_id,
                        width=CAMERA_CONFIG['width'],
                        height=CAMERA_CONFIG['height'],
                        fps=CAMERA_CONFIG['fps'],
                        quality=CAMERA_CONFIG['quality'],
                        stream_quality=CAMERA_CONFIG['stream_quality'],
                        stream_fps=CAMERA_CONFIG['stream_fps'],
                        brightness=CAMERA_CONFIG['brightness'],
                        contrast=CAMERA_CONFIG['contrast'],
                        saturation=CAMERA_CONFIG['saturation'],
                        save_path=CAMERA_CONFIG['save_path'],
                        video_path=CAMERA_CONFIG['video_path'],
                        auto_start=True
                    )
                    camera = USBCamera(camera_config)
                    logger.info(
                        f"🎥 Камера инициализирована: /dev/video{device_id}")
                else:
                    logger.warning("🎥 USB камеры не найдены")
                    camera = None
            else:
                logger.warning("🎥 OpenCV недоступен")
                camera = None
        except Exception as e:
            logger.error(f"🎥 Ошибка инициализации камеры: {e}")
            camera = None

    # ==================== AI ИНТЕГРАЦИЯ ====================

    # Создаем AI контроллер робота
    ai_robot = AIRobotController(robot, camera)

    # Заменяем обычное AI зрение на домашнее
    if camera and CAMERA_AVAILABLE:
        try:
            home_ai_vision = HomeAIVision(camera)
            ai_robot.ai_vision = home_ai_vision
            ai_robot._setup_ai_callbacks()  # Переустанавливаем колбэки
            logger.info("🏠 Домашнее AI зрение установлено")
        except Exception as e:
            logger.error(f"Ошибка инициализации домашнего AI: {e}")

    # API Blueprint
    bp = Blueprint("api", __name__)

    # ==================== УТИЛИТЫ ОТВЕТОВ ====================

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

    # ==================== АУТЕНТИФИКАЦИЯ ====================

    @app.before_request
    def _auth():
        if API_KEY and request.path.startswith("/api/"):
            if request.headers.get("X-API-Key") != API_KEY:
                return err("unauthorized", 401)

    # ==================== ГЛАВНАЯ СТРАНИЦА ====================

    @app.route("/")
    def index():
        """Главная страница с веб-интерфейсом"""
        return render_template("index.html")

    # ==================== API МАРШРУТЫ ДВИЖЕНИЯ ====================

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

    # ==================== УПРАВЛЕНИЕ КАМЕРОЙ ====================

    @bp.route("/camera/pan", methods=["POST"])
    def camera_pan():
        """Установка угла поворота камеры по горизонтали"""
        data = request.get_json() or {}
        angle = data.get("angle")

        if angle is None:
            return err("Не указан угол поворота", 400)

        try:
            angle = int(angle)
        except (TypeError, ValueError):
            return err("Неверный формат угла", 400)

        success = robot.set_camera_pan(angle)
        pan_angle, tilt_angle = robot.get_camera_angles()

        return ok({
            "command": "set_camera_pan",
            "requested_angle": angle,
            "actual_angle": pan_angle,
            "success": success,
            "camera": {
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle
            }
        })

    @bp.route("/camera/tilt", methods=["POST"])
    def camera_tilt():
        """Установка угла наклона камеры по вертикали"""
        data = request.get_json() or {}
        angle = data.get("angle")

        if angle is None:
            return err("Не указан угол наклона", 400)

        try:
            angle = int(angle)
        except (TypeError, ValueError):
            return err("Неверный формат угла", 400)

        success = robot.set_camera_tilt(angle)
        pan_angle, tilt_angle = robot.get_camera_angles()

        return ok({
            "command": "set_camera_tilt",
            "requested_angle": angle,
            "actual_angle": tilt_angle,
            "success": success,
            "camera": {
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle
            }
        })

    @bp.route("/camera/angles", methods=["POST"])
    def camera_angles():
        """Установка обоих углов камеры одновременно"""
        data = request.get_json() or {}
        pan = data.get("pan")
        tilt = data.get("tilt")

        if pan is None or tilt is None:
            return err("Не указаны углы pan и tilt", 400)

        try:
            pan = int(pan)
            tilt = int(tilt)
        except (TypeError, ValueError):
            return err("Неверный формат углов", 400)

        success = robot.set_camera_angles(pan, tilt)
        actual_pan, actual_tilt = robot.get_camera_angles()

        return ok({
            "command": "set_camera_angles",
            "requested": {"pan": pan, "tilt": tilt},
            "actual": {"pan": actual_pan, "tilt": actual_tilt},
            "success": success,
            "camera": {
                "pan_angle": actual_pan,
                "tilt_angle": actual_tilt
            }
        })

    @bp.route("/camera/center", methods=["POST"])
    def camera_center():
        """Установка камеры в центральное положение"""
        success = robot.center_camera()
        pan_angle, tilt_angle = robot.get_camera_angles()

        return ok({
            "command": "center_camera",
            "success": success,
            "camera": {
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle
            }
        })

    @bp.route("/camera/pan/left", methods=["POST"])
    def camera_pan_left():
        """Повернуть камеру влево на шаг"""
        data = request.get_json() or {}
        step = data.get("step")  # опциональный параметр

        if step is not None:
            try:
                step = int(step)
            except (TypeError, ValueError):
                return err("Неверный формат шага", 400)

        success = robot.pan_left(step)
        pan_angle, tilt_angle = robot.get_camera_angles()

        return ok({
            "command": "pan_left",
            "step": step,
            "success": success,
            "camera": {
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle
            }
        })

    @bp.route("/camera/pan/right", methods=["POST"])
    def camera_pan_right():
        """Повернуть камеру вправо на шаг"""
        data = request.get_json() or {}
        step = data.get("step")  # опциональный параметр

        if step is not None:
            try:
                step = int(step)
            except (TypeError, ValueError):
                return err("Неверный формат шага", 400)

        success = robot.pan_right(step)
        pan_angle, tilt_angle = robot.get_camera_angles()

        return ok({
            "command": "pan_right",
            "step": step,
            "success": success,
            "camera": {
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle
            }
        })

    @bp.route("/camera/tilt/up", methods=["POST"])
    def camera_tilt_up():
        """Наклонить камеру вверх на шаг"""
        data = request.get_json() or {}
        step = data.get("step")  # опциональный параметр

        if step is not None:
            try:
                step = int(step)
            except (TypeError, ValueError):
                return err("Неверный формат шага", 400)

        success = robot.tilt_up(step)
        pan_angle, tilt_angle = robot.get_camera_angles()

        return ok({
            "command": "tilt_up",
            "step": step,
            "success": success,
            "camera": {
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle
            }
        })

    @bp.route("/camera/tilt/down", methods=["POST"])
    def camera_tilt_down():
        """Наклонить камеру вниз на шаг"""
        data = request.get_json() or {}
        step = data.get("step")  # опциональный параметр

        if step is not None:
            try:
                step = int(step)
            except (TypeError, ValueError):
                return err("Неверный формат шага", 400)

        success = robot.tilt_down(step)
        pan_angle, tilt_angle = robot.get_camera_angles()

        return ok({
            "command": "tilt_down",
            "step": step,
            "success": success,
            "camera": {
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle
            }
        })

    @bp.route("/camera/limits", methods=["GET"])
    def camera_limits():
        """Получить ограничения углов камеры"""
        limits = robot.get_camera_limits()
        current_pan, current_tilt = robot.get_camera_angles()

        return ok({
            "limits": limits,
            "current": {
                "pan_angle": current_pan,
                "tilt_angle": current_tilt
            }
        })

    @bp.route("/camera/position", methods=["GET"])
    def camera_position():
        """Получить текущую позицию камеры"""
        pan_angle, tilt_angle = robot.get_camera_angles()
        limits = robot.get_camera_limits()

        return ok({
            "camera": {
                "pan_angle": pan_angle,
                "tilt_angle": tilt_angle
            },
            "limits": limits,
            "is_centered": (pan_angle == limits["pan"]["default"] and
                            tilt_angle == limits["tilt"]["default"])
        })

    # ==================== КАМЕРА API ====================

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

    # ==================== ВИДЕОПОТОК ====================

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

    def _collect_files(dir_path: str | Path, exts: tuple[str, ...]) -> list[dict]:
        base = Path(dir_path)
        base.mkdir(parents=True, exist_ok=True)

        items = []
        for f in base.iterdir():
            if f.is_file() and f.suffix.lower() in exts:
                stat = f.stat()
                created = int(stat.st_mtime)
                # путь относительно /static
                rel = f.resolve().relative_to(STATIC_ROOT)
                url = f"/static/{rel.as_posix()}"
                items.append({
                    "filename": f.name,
                    "path": str(f.resolve()),     # для удаления
                    "url": url,                   # ← фронт будет использовать это
                    "size": stat.st_size,
                    "created": created,
                    "created_str": datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S"),
                })
        items.sort(key=lambda x: x["created"], reverse=True)
        return items

    @bp.route("/files/photos", methods=["GET"])
    def files_photos():
        try:
            files = _collect_files(PHOTOS_DIR, (".jpg", ".jpeg", ".png"))
            return ok({"files": files})
        except Exception as e:
            return err(f"Ошибка списка фото: {e}", 500)

    @bp.route("/files/videos", methods=["GET"])
    def files_videos():
        try:
            files = _collect_files(
                VIDEOS_DIR, (".mp4", ".avi", ".mov", ".mkv"))
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

    # ==================== СТАТУС И ДИАГНОСТИКА ====================

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

    # ==================== ДОБАВЛЯЕМ AI МАРШРУТЫ ====================

    # Добавляем все AI API эндпоинты
    add_ai_routes(bp, ai_robot)

    # Регистрируем API blueprint
    app.register_blueprint(bp, url_prefix="/api")

    # ==================== ОБРАБОТКА ОШИБОК ====================

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

    # ==================== GRACEFUL SHUTDOWN ====================

    def _graceful_shutdown(*_):
        logger.info("🔄 Завершение по сигналу...")
        try:
            # Останавливаем AI системы
            if ai_robot:
                ai_robot.stop_ai()

            if heading:
                heading.stop()

            # Останавливаем базовый робот
            if hasattr(ai_robot, 'robot'):
                ai_robot.robot.shutdown()
            else:
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
    app.robot = ai_robot.robot if ai_robot else robot
    app.ai_robot = ai_robot
    app.camera = camera

    logger.info("🤖🧠 Flask приложение создано успешно с поддержкой AI и камеры")
    return app
