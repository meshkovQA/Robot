# robot/api/ai_api_extensions.py
"""
AI API Extensions - Дополнительные API эндпоинты для AI функций
Добавляется в существующий api.py
"""

from flask import Blueprint, jsonify, request, Response
import base64
import cv2
import numpy as np
import time
import logging

logger = logging.getLogger(__name__)


def add_ai_routes(bp: Blueprint, ai_robot):
    """Добавляет AI маршруты в Blueprint"""

    # ==================== AI СТАТУС И УПРАВЛЕНИЕ ====================

    @bp.route("/ai/status", methods=["GET"])
    def ai_status():
        """Получить статус AI систем"""
        try:
            status = ai_robot.get_ai_status()
            return jsonify({
                "success": True,
                "data": status,
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка получения AI статуса: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route("/ai/start", methods=["POST"])
    def ai_start():
        """Запуск AI обработки"""
        try:
            success = ai_robot.start_ai()
            return jsonify({
                "success": success,
                "message": "AI обработка запущена" if success else "Ошибка запуска AI",
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка запуска AI: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route("/ai/stop", methods=["POST"])
    def ai_stop():
        """Остановка AI обработки"""
        try:
            ai_robot.stop_ai()
            return jsonify({
                "success": True,
                "message": "AI обработка остановлена",
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка остановки AI: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    # ==================== AI РЕЖИМЫ ====================

    @bp.route("/ai/follow_person", methods=["POST"])
    def toggle_follow_person():
        """Включить/выключить режим следования за человеком"""
        try:
            data = request.get_json() or {}
            enable = data.get("enable", True)

            ai_robot.enable_follow_person_mode(enable)

            return jsonify({
                "success": True,
                "follow_person_mode": enable,
                "message": f"Режим следования за человеком {'включен' if enable else 'выключен'}",
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка переключения режима следования: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route("/ai/avoid_people", methods=["POST"])
    def toggle_avoid_people():
        """Включить/выключить автоматическое избежание людей"""
        try:
            data = request.get_json() or {}
            enable = data.get("enable", True)

            ai_robot.enable_auto_avoid_people(enable)

            return jsonify({
                "success": True,
                "auto_avoid_people": enable,
                "message": f"Автоматическое избежание людей {'включено' if enable else 'выключено'}",
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка переключения избежания людей: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route("/ai/smart_navigation", methods=["POST"])
    def toggle_smart_navigation():
        """Включить/выключить умную навигацию"""
        try:
            data = request.get_json() or {}
            enable = data.get("enable", True)

            ai_robot.enable_smart_navigation(enable)

            return jsonify({
                "success": True,
                "smart_navigation": enable,
                "message": f"Умная навигация {'включена' if enable else 'выключена'}",
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка переключения умной навигации: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    # ==================== AI ДВИЖЕНИЕ ====================

    @bp.route("/ai/smart_move/forward", methods=["POST"])
    def ai_smart_move_forward():
        """Умное движение вперед с AI проверками"""
        try:
            data = request.get_json() or {}
            speed = int(data.get("speed", 100))

            success = ai_robot.smart_move_forward(speed)

            return jsonify({
                "success": success,
                "command": "ai_smart_move_forward",
                "speed": speed,
                "message": "Движение выполнено" if success else "Движение заблокировано AI",
                **ai_robot.get_extended_status()
            })
        except Exception as e:
            logger.error(f"Ошибка умного движения: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route("/ai/navigate_to", methods=["POST"])
    def ai_navigate_to():
        """Навигация к цели по описанию"""
        try:
            data = request.get_json() or {}
            description = data.get("description", "")

            if not description:
                return jsonify({
                    "success": False,
                    "error": "Не указано описание цели"
                }), 400

            ai_robot.smart_navigate_to_target(description)

            return jsonify({
                "success": True,
                "command": "navigate_to",
                "target": description,
                "message": f"Попытка навигации к: {description}",
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка навигации к цели: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    # ==================== AI ВОСПРИЯТИЕ ====================

    @bp.route("/ai/scene_description", methods=["GET"])
    def get_scene_description():
        """Получить описание текущей сцены"""
        try:
            description = ai_robot.get_scene_description()

            return jsonify({
                "success": True,
                "scene_description": description,
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка получения описания сцены: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route("/ai/detected_objects", methods=["GET"])
    def get_detected_objects():
        """Получить список обнаруженных объектов"""
        try:
            if not ai_robot.ai_vision:
                return jsonify({
                    "success": False,
                    "error": "AI Vision не инициализирован"
                }), 400

            vision_state = ai_robot.ai_vision.get_state()

            objects_data = []
            for obj in vision_state.objects:
                objects_data.append({
                    "class_name": obj.class_name,
                    "confidence": obj.confidence,
                    "bbox": obj.bbox,
                    "center": obj.center,
                    "area": obj.area,
                    "timestamp": obj.timestamp
                })

            faces_data = []
            for face in vision_state.faces:
                faces_data.append({
                    "bbox": face["bbox"],
                    "center": face["center"],
                    "area": face["area"],
                    "confidence": face["confidence"],
                    "timestamp": face["timestamp"]
                })

            return jsonify({
                "success": True,
                "data": {
                    "objects": objects_data,
                    "faces": faces_data,
                    "motion_detected": vision_state.motion_detected,
                    "scene_description": vision_state.scene_description,
                    "processing_fps": vision_state.processing_fps,
                    "object_counts": ai_robot.ai_vision.count_detected_objects(),
                    "person_in_front": ai_robot.ai_vision.is_person_in_front()
                },
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка получения обнаруженных объектов: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route("/ai/annotated_frame", methods=["GET"])
    def get_annotated_frame():
        """Получить кадр с аннотациями объектов"""
        try:
            if not ai_robot.ai_vision or not ai_robot.camera:
                return jsonify({
                    "success": False,
                    "error": "AI Vision или камера недоступны"
                }), 400

            # Получаем текущий кадр
            frame = ai_robot.ai_vision._get_frame()
            if frame is None:
                return jsonify({
                    "success": False,
                    "error": "Нет доступных кадров"
                }), 400

            # Добавляем аннотации
            annotated_frame = ai_robot.ai_vision.get_annotated_frame(frame)

            # Кодируем в JPEG
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, 80]
            ret, buffer = cv2.imencode('.jpg', annotated_frame, encode_param)

            if not ret:
                return jsonify({
                    "success": False,
                    "error": "Ошибка кодирования кадра"
                }), 500

            # Конвертируем в base64
            frame_b64 = base64.b64encode(buffer).decode('utf-8')

            return jsonify({
                "success": True,
                "frame": frame_b64,
                "format": "base64_jpeg",
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка получения аннотированного кадра: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    # ==================== AI СТРИМ ====================

    @bp.route("/ai/annotated_stream", methods=["GET"])
    def ai_annotated_stream():
        """MJPEG стрим с AI аннотациями"""

        def generate():
            """Генератор аннотированных кадров"""
            logger.info("Запущен AI аннотированный стрим")

            # Заглушка - черный квадрат
            import base64
            BLACK_JPEG_B64 = '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/gA=='
            BLACK_JPEG = base64.b64decode(BLACK_JPEG_B64)

            while True:
                try:
                    frame_data = BLACK_JPEG  # По умолчанию

                    # Пытаемся получить аннотированный кадр
                    if (ai_robot.ai_vision and ai_robot.camera and
                        hasattr(ai_robot.ai_vision, '_processing_thread') and
                        ai_robot.ai_vision._processing_thread and
                            ai_robot.ai_vision._processing_thread.is_alive()):

                        frame = ai_robot.ai_vision._get_frame()
                        if frame is not None:
                            # Добавляем AI аннотации
                            annotated_frame = ai_robot.ai_vision.get_annotated_frame(
                                frame)

                            # Кодируем в JPEG
                            encode_param = [cv2.IMWRITE_JPEG_QUALITY, 60]
                            ret, buffer = cv2.imencode(
                                '.jpg', annotated_frame, encode_param)

                            if ret:
                                frame_data = buffer.tobytes()

                    # Отправляем кадр
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Content-Length: ' +
                           str(len(frame_data)).encode() + b'\r\n'
                           b'\r\n' + frame_data + b'\r\n')

                    time.sleep(1.0 / 10)  # 10 FPS

                except GeneratorExit:
                    logger.info("AI аннотированный стрим остановлен")
                    break
                except Exception as e:
                    logger.error(f"Ошибка в AI стриме: {e}")
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

    # ==================== РАСШИРЕННЫЙ СТАТУС ====================

    @bp.route("/status/extended", methods=["GET"])
    def extended_status():
        """Расширенный статус робота с AI данными"""
        try:
            status = ai_robot.get_extended_status()
            return jsonify({
                "success": True,
                "data": status,
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Ошибка получения расширенного статуса: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
