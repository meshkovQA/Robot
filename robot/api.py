# api.py

from __future__ import annotations
import logging
import signal
from datetime import datetime
from flask import Flask, Blueprint, jsonify, request, render_template

from .controller import RobotController
from .config import LOG_LEVEL, LOG_FMT, API_KEY, SPEED_MIN, SPEED_MAX

logging.basicConfig(level=LOG_LEVEL, format=LOG_FMT)
logger = logging.getLogger(__name__)


def create_app(controller: RobotController | None = None) -> Flask:
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')
    robot = controller or RobotController()

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

    # --------- API маршруты рулевого управления ----------
    @bp.route("/steering/left", methods=["POST"])
    def steering_left():
        data = request.get_json() or {}
        angle = int(data.get("angle", 45))

        success = robot.turn_steering_left(angle)
        return ok({
            "command": "steering_left",
            "angle": angle,
            "success": success,
            **robot.get_status()
        })

    @bp.route("/steering/right", methods=["POST"])
    def steering_right():
        data = request.get_json() or {}
        angle = int(data.get("angle", 45))

        success = robot.turn_steering_right(angle)
        return ok({
            "command": "steering_right",
            "angle": angle,
            "success": success,
            **robot.get_status()
        })

    @bp.route("/steering/center", methods=["POST"])
    def center_steering():
        success = robot.center_steering()
        return ok({
            "command": "center_steering",
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

    # --------- мониторинг и диагностика ----------
    @bp.route("/status", methods=["GET"])
    def status():
        return ok(robot.get_status())

    @bp.route("/health", methods=["GET"])
    def health():
        status = robot.get_status()
        status.update({
            "i2c_connected": robot.bus is not None,
            "controller_active": True,
            "api_version": "2.0"
        })
        return ok(status)

    @bp.route("/sensors", methods=["GET"])
    def sensors():
        front, rear = robot.read_sensors()
        return ok({
            "front_distance": front,
            "rear_distance": rear,
            "front_obstacle": front != 999 and front < 15,
            "rear_obstacle": rear != 999 and rear < 10,
            "sensors_working": front != 999 and rear != 999
        })

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
        except Exception as e:
            logger.error("Ошибка при завершении: %s", e)
        finally:
            raise SystemExit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    # Сохраняем ссылку на робота для доступа извне
    app.robot = robot  # type: ignore[attr-defined]

    logger.info("🤖 Flask приложение создано успешно")
    return app
