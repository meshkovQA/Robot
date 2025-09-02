# robot/api/ai_detector_api.py
"""
Простое API для YOLO 8 детекции
"""

from flask import Blueprint, jsonify, request, Response
import base64
import cv2
import time
import logging
import numpy as np

logger = logging.getLogger(__name__)


def add_ai_detector_routes(bp: Blueprint, ai_detector, camera):
    """Добавляет AI детекция маршруты в Blueprint"""

    @bp.route("/ai/detect", methods=["GET"])
    def ai_detect():
        """Получить текущие AI детекции"""
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
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                return jsonify({
                    "success": False,
                    "error": "Ошибка декодирования кадра"
                }), 400

            # Детекция
            detections = ai_detector.detect_objects(frame)

            return jsonify({
                "success": True,
                "detections": detections,
                "count": len(detections),
                "timestamp": time.time()
            })

        except Exception as e:
            logger.error(f"Ошибка AI детекции: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

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
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                return jsonify({
                    "success": False,
                    "error": "Ошибка декодирования кадра"
                }), 400

            # Детекция и отрисовка
            detections = ai_detector.detect_objects(frame)
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
        """MJPEG стрим с AI аннотациями"""
        def generate():
            while True:
                try:
                    if not camera:
                        break

                    # Получаем JPEG кадр и декодируем
                    jpeg_data = camera.get_frame_jpeg()
                    if jpeg_data is None:
                        time.sleep(0.1)
                        continue

                    # Декодируем в numpy array
                    nparr = np.frombuffer(jpeg_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if frame is None:
                        time.sleep(0.1)
                        continue

                    # Детекция и отрисовка
                    detections = ai_detector.detect_objects(frame)
                    annotated_frame = ai_detector.draw_detections(
                        frame.copy(), detections)

                    # Кодируем
                    encode_param = [cv2.IMWRITE_JPEG_QUALITY, 70]
                    ret, buffer = cv2.imencode(
                        '.jpg', annotated_frame, encode_param)

                    if ret:
                        frame_data = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n'
                               b'Content-Length: ' +
                               str(len(frame_data)).encode() + b'\r\n'
                               b'\r\n' + frame_data + b'\r\n')

                    time.sleep(1.0 / 15)  # 15 FPS

                except Exception as e:
                    logger.error(f"Ошибка в AI стриме: {e}")
                    break

        return Response(
            generate(),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )
