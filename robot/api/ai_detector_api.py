# robot/api/ai_detector_api.py
"""
Простое API для YOLO 8 детекции
"""

from flask import Blueprint, jsonify, Response
import base64
import cv2
import time
import logging
import numpy as np
from flask import request
logger = logging.getLogger(__name__)


def add_ai_detector_routes(bp: Blueprint, *, ai_detector, camera, ai_runtime, ok, err):
    @bp.route("/ai/annotated_frame", methods=["GET"])
    def ai_annotated_frame():
        """Получить кадр с аннотациями AI"""
        try:
            if not camera:
                return jsonify({
                    "success": False,
                    "error": "Камера недоступна"
                }), 400

            # Получаем JPEG кадр и декодируем в numpy array
            jpeg_data = camera.get_frame_jpeg()
            if jpeg_data is None:
                return jsonify({
                    "success": False,
                    "error": "Нет кадров с камеры"
                }), 400

            # Декодируем JPEG в numpy array
            nparr = np.frombuffer(jpeg_data, np.uint8)
            frame = ai_runtime.last_frame_bgr.copy(
            ) if ai_runtime and ai_runtime.last_frame_bgr is not None else None

            if frame is None:
                return jsonify({
                    "success": False,
                    "error": "Ошибка декодирования кадра"
                }), 400

            # Детекция и отрисовка
            detections = ai_runtime.last_detections if ai_runtime else []
            annotated_frame = ai_detector.draw_detections(
                frame.copy(), detections)

            # Кодируем в base64
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, 80]
            ret, buffer = cv2.imencode('.jpg', annotated_frame, encode_param)

            if not ret:
                return jsonify({
                    "success": False,
                    "error": "Ошибка кодирования"
                }), 500

            frame_b64 = base64.b64encode(buffer).decode('utf-8')

            return jsonify({
                "success": True,
                "frame": frame_b64,
                "detections": detections,
                "timestamp": time.time()
            })

        except Exception as e:
            logger.error(f"Ошибка аннотированного кадра: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route("/ai/stream", methods=["GET"])
    def ai_stream():
        """
        Быстрый MJPEG-стрим с аннотациями:
        - НЕ делает инференс в обработчике (берет last_frame_bgr/last_detections из ai_runtime)
        - Даунскейлит кадр (scale) и регулирует FPS (fps)
        - Кодирует JPEG с заданным quality
        Примеры:
        /api/ai/stream?fps=12&scale=0.75&quality=70
        /api/ai/stream  (по умолчанию ~12 FPS, 0.75, 70)
        """
        if not camera or not ai_runtime:
            return Response(status=503)

        # параметры стрима из query
        try:
            target_fps = float(request.args.get("fps", 12))
            target_fps = max(1.0, min(30.0, target_fps))
        except Exception:
            target_fps = 12.0

        try:
            # 0.5..1.0 обычно достаточно
            scale = float(request.args.get("scale", 0.75))
            scale = max(0.3, min(1.0, scale))
        except Exception:
            scale = 0.75

        try:
            quality = int(request.args.get("quality", 70))
            quality = max(40, min(90, quality))
        except Exception:
            quality = 70

        interval = 1.0 / target_fps

        def generate():
            import time
            last_ts_used = None
            cached_jpeg = None  # если кадр не обновился — повторно не кодируем

            while True:
                try:
                    # Берём последний кадр из рантайма
                    frame = ai_runtime.last_frame_bgr
                    detections = ai_runtime.last_detections or []

                    if frame is None:
                        time.sleep(0.05)
                        continue

                    # Определяем — обновился ли буфер
                    ts = ai_runtime.last_ts
                    need_reencode = (ts != last_ts_used) or (
                        cached_jpeg is None)

                    if need_reencode:
                        # Рисуем только по кэшированным детекциям
                        annotated = ai_detector.draw_detections(
                            frame.copy(), detections)

                        # Даунскейлим при необходимости
                        if scale != 1.0:
                            h, w = annotated.shape[:2]
                            new_w = max(1, int(w * scale))
                            new_h = max(1, int(h * scale))
                            annotated = cv2.resize(
                                annotated, (new_w, new_h), interpolation=cv2.INTER_AREA)

                        # Кодируем JPEG
                        ok, buffer = cv2.imencode(
                            ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, quality])
                        if not ok:
                            time.sleep(interval)
                            continue

                        cached_jpeg = buffer.tobytes()
                        last_ts_used = ts

                    # Отдаём последнюю закодированную версию
                    frame_data = cached_jpeg
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n"
                           b"Content-Length: " + str(len(frame_data)).encode() + b"\r\n\r\n" +
                           frame_data + b"\r\n")

                    time.sleep(interval)

                except GeneratorExit:
                    break
                except Exception as e:
                    logger.error(f"Ошибка в AI стриме: {e}")
                    time.sleep(0.2)

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Connection": "close",
                "Access-Control-Allow-Origin": "*",
            },
        )
