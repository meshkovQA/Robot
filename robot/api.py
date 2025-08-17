from __future__ import annotations
import logging
import signal
from datetime import datetime
from flask import Flask, Blueprint, jsonify, request

from .controller import RobotController
from .config import LOG_LEVEL, LOG_FMT, API_KEY, SPEED_MIN, SPEED_MAX

logging.basicConfig(level=LOG_LEVEL, format=LOG_FMT)
logger = logging.getLogger(__name__)


def create_app(controller: RobotController | None = None) -> Flask:
    app = Flask(__name__)
    robot = controller or RobotController()

    bp = Blueprint("api", __name__)

    # --------- утилиты ответов ----------
    def ok(data=None, code=200):
        return jsonify({"success": True, "data": data or {}, "timestamp": datetime.now().isoformat()}), code

    def err(msg, code=400):
        return jsonify({"success": False, "error": msg, "timestamp": datetime.now().isoformat()}), code

    # --------- простая аутентификация ----------
    @app.before_request
    def _auth():
        if API_KEY:
            if request.path.startswith("/api/"):
                if request.headers.get("X-API-Key") != API_KEY:
                    return err("unauthorized", 401)

    # --------- маршруты ----------
    @bp.route("/move/forward", methods=["POST"])
    def move_forward():
        speed = int((request.get_json() or {}).get("speed", 100))
        speed = max(SPEED_MIN, min(SPEED_MAX, speed))
        return ok({"done": robot.move_forward(speed), "direction": "forward", "speed": speed})

    @bp.route("/move/backward", methods=["POST"])
    def move_backward():
        speed = int((request.get_json() or {}).get("speed", 100))
        speed = max(SPEED_MIN, min(SPEED_MAX, speed))
        return ok({"done": robot.move_backward(speed), "direction": "backward", "speed": speed})

    @bp.route("/turn/left", methods=["POST"])
    def turn_left():
        speed = int((request.get_json() or {}).get("speed", 150))
        return ok({"done": robot.tank_turn_left(speed), "turn": "left", "speed": speed})

    @bp.route("/turn/right", methods=["POST"])
    def turn_right():
        speed = int((request.get_json() or {}).get("speed", 150))
        return ok({"done": robot.tank_turn_right(speed), "turn": "right", "speed": speed})

    @bp.route("/speed", methods=["POST"])
    def update_speed():
        new_speed = int((request.get_json() or {}).get("speed", 0))
        new_speed = max(SPEED_MIN, min(SPEED_MAX, new_speed))
        done = robot.update_speed(new_speed)
        st = robot.get_status()
        return ok({"done": done, **st})

    @bp.route("/stop", methods=["POST"])
    def stop():
        return ok({"done": robot.stop()})

    @bp.route("/emergency_stop", methods=["POST"])
    def emergency_stop():
        logger.warning("Выполнена экстренная остановка!")
        return ok({"done": robot.stop()})

    @bp.route("/status", methods=["GET"])
    def status():
        return ok(robot.get_status())

    @bp.route("/health", methods=["GET"])
    def health():
        st = robot.get_status()
        st["i2c_connected"] = robot.bus is not None
        return ok(st)

    app.register_blueprint(bp, url_prefix="/api")

    # --------- корректное завершение ----------
    def _graceful_shutdown(*_):
        logger.info("Завершение по сигналу")
        robot.shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    # для доступа в gunicorn/etc:
    app.robot = robot  # type: ignore[attr-defined]
    return app
