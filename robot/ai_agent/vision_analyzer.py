# robot/ai_agent/vision_analyzer.py

import json
import logging
from openai import OpenAI
import os
import cv2
import base64
from datetime import datetime
from pathlib import Path


class VisionAnalyzer:
    """
    Анализатор визуальной информации для робота
    Интегрируется с существующим SimpleAIDetector и OpenAI GPT-4V
    """

    def __init__(self, config, camera=None, ai_detector=None):
        self.config = config
        self.camera = camera
        self.ai_detector = ai_detector

        # Получаем ключ только из environment переменной
        self.api_key = os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError(
                "OpenAI API key не найден в переменной окружения OPENAI_API_KEY")

        # Создаем клиент с новым API
        self.client = OpenAI(api_key=self.api_key)

        # Настройки для GPT-4V (остается как есть)
        self.vision_model = config.get('vision_model', 'gpt-4o-mini')
        self.max_tokens = config.get('vision_max_tokens', 300)

        # Проверяем доступность компонентов (остается как есть)
        if not self.ai_detector:
            logging.warning(
                "⚠️ SimpleAIDetector не подключен - детекция объектов недоступна")
        else:
            logging.info(
                "✅ VisionAnalyzer использует существующий SimpleAIDetector")

        if not self.camera:
            logging.warning("⚠️ Камера не подключена")
        else:
            logging.info("✅ VisionAnalyzer подключен к камере")

        logging.info("👁️ VisionAnalyzer инициализирован с новым OpenAI API")

    def capture_frame(self):
        """Получить текущий кадр с камеры"""
        if not self.camera:
            logging.error("❌ Камера не подключена")
            return None

        try:
            # Получаем кадр из существующей системы камеры
            frame = self.camera.get_frame()
            if frame is not None:
                logging.debug("📷 Кадр получен с камеры")
                return frame
            else:
                logging.error("❌ Не удалось получить кадр с камеры")
                return None
        except Exception as e:
            logging.error(f"❌ Ошибка захвата кадра: {e}")
            return None

    def detect_objects(self, frame):
        """Детекция объектов через существующий SimpleAIDetector"""
        if not self.ai_detector:
            logging.warning("⚠️ AI детектор не подключен")
            return []

        try:
            # Используем существующий метод детекции
            detections = self.ai_detector.detect_objects(frame)

            # Адаптируем формат к нашему API
            detected_objects = []
            for det in detections:
                detected_objects.append({
                    'class': det.get('class_name', 'unknown'),
                    'confidence': det.get('confidence', 0.0),
                    'bbox': det.get('bbox', [0, 0, 0, 0]),  # [x, y, w, h]
                    'center': det.get('center', [0, 0])
                })

            logging.info(f"🔍 Обнаружено объектов: {len(detected_objects)}")
            for obj in detected_objects:
                logging.debug(f"   {obj['class']} ({obj['confidence']:.2f})")

            return detected_objects

        except Exception as e:
            logging.error(f"❌ Ошибка детекции объектов: {e}")
            return []

    def encode_image_to_base64(self, frame):
        """Конвертация кадра в base64 для отправки в OpenAI"""
        try:
            # Конвертируем в JPEG с хорошим качеством
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            success, buffer = cv2.imencode('.jpg', frame, encode_param)

            if not success:
                logging.error("❌ Не удалось закодировать изображение в JPEG")
                return None

            # Конвертируем в base64
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            # Проверяем размер (OpenAI имеет ограничения)
            size_mb = len(image_base64) * 0.75 / 1024 / \
                1024  # Примерный размер в MB
            if size_mb > 20:  # OpenAI лимит ~20MB
                logging.warning(
                    f"⚠️ Изображение слишком большое: {size_mb:.1f}MB")
                # Можно уменьшить качество или разрешение
                return None

            logging.debug(f"📷 Изображение закодировано: {size_mb:.1f}MB")
            return image_base64

        except Exception as e:
            logging.error(f"❌ Ошибка кодирования изображения: {e}")
            return None

    def describe_scene_with_llm(self, frame, detected_objects=None):
        """Описание сцены через GPT-4V с мультимодальным вводом"""
        try:
            # Подготавливаем информацию об обнаруженных объектах
            objects_text = ""
            if detected_objects:
                object_names = [obj['class'] for obj in detected_objects]
                objects_text = f"YOLO8 обнаружил объекты: {', '.join(object_names)}. "
            else:
                objects_text = "YOLO8 не обнаружил конкретных объектов. "

            # Кодируем изображение для OpenAI
            image_base64 = self.encode_image_to_base64(frame)

            if image_base64:
                # Используем GPT-4V с изображением
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"{objects_text}Опиши что ты видишь на этом изображении простыми словами, как если бы ты робот-помощник, который рассказывает хозяину что происходит вокруг. Ответ должен быть кратким и понятным."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "low"  # Экономим токены
                                }
                            }
                        ]
                    }
                ]

                logging.info("🧠 Отправляю изображение в GPT-4V...")

                response = self.client.chat.completions.create(
                    model=self.vision_model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=0.3  # Более стабильные описания
                )

                description = response.choices[0].message.content.strip()
                logging.info(
                    f"✅ GPT-4V описание получено: '{description[:100]}...'")
                return description

            else:
                # Fallback - описание только на основе YOLO данных
                if detected_objects:
                    object_names = [obj['class'] for obj in detected_objects]
                    confidence_info = []
                    for obj in detected_objects:
                        if obj['confidence'] > 0.8:
                            confidence_info.append(
                                f"{obj['class']} (уверенно)")
                        elif obj['confidence'] > 0.5:
                            confidence_info.append(
                                f"{obj['class']} (вероятно)")
                        else:
                            confidence_info.append(
                                f"{obj['class']} (возможно)")

                    return f"Я вижу: {', '.join(confidence_info)}. Изображение не удалось отправить для подробного анализа."
                else:
                    return "Я смотрю вокруг, но не могу четко определить конкретные объекты на текущем изображении."

        except Exception as e:
            logging.error(f"❌ Ошибка описания сцены через LLM: {e}")

            # Fallback - простое описание на основе YOLO
            if detected_objects:
                object_names = [obj['class'] for obj in detected_objects]
                return f"Анализ через ИИ недоступен, но детектор видит: {', '.join(object_names)}"
            else:
                return "Анализ изображения временно недоступен, попробуйте позже."

    def analyze_current_view(self):
        """Основная функция - полный анализ текущего вида"""
        try:
            logging.info("👁️ Начинаю анализ текущего вида...")

            # 1. Получаем кадр с камеры
            frame = self.capture_frame()
            if frame is None:
                return {"error": "Не удалось получить изображение с камеры"}

            # 2. Детектируем объекты через YOLO
            detected_objects = self.detect_objects(frame)

            # 3. Получаем описание от GPT-4V
            description = self.describe_scene_with_llm(frame, detected_objects)

            # 4. Сохраняем кадр для отладки (опционально)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            frame_path = Path(f"data/temp/vision_analysis_{timestamp}.jpg")
            frame_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                cv2.imwrite(str(frame_path), frame)
                logging.debug(f"💾 Кадр сохранен: {frame_path}")
            except Exception as e:
                logging.warning(f"⚠️ Не удалось сохранить кадр: {e}")
                frame_path = None

            # 5. Формируем результат
            result = {
                "success": True,
                "description": description,
                "detected_objects": detected_objects,
                "objects_count": len(detected_objects),
                "frame_saved": str(frame_path) if frame_path else None,
                "timestamp": datetime.now().isoformat(),
                "analysis_method": "yolo + gpt4v" if self.api_key else "yolo_only"
            }

            logging.info(
                f"✅ Анализ завершен: {len(detected_objects)} объектов, описание получено")
            return result

        except Exception as e:
            logging.error(f"❌ Ошибка анализа текущего вида: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def analyze_for_navigation(self, frame=None):
        """
        Анализ для навигации - определение препятствий и безопасных зон
        (Будущее расширение для автономного движения)
        """
        try:
            # Используем переданный кадр или получаем новый
            if frame is None:
                frame = self.capture_frame()
                if frame is None:
                    return {"error": "Не удалось получить кадр для анализа навигации"}

            # Детектируем объекты
            detected_objects = self.detect_objects(frame)

            # Классифицируем объекты по типам препятствий
            obstacles = []
            people = []
            furniture = []

            for obj in detected_objects:
                obj_class = obj['class'].lower()

                if obj_class in ['person', 'people']:
                    people.append(obj)
                elif obj_class in ['chair', 'table', 'sofa', 'bed', 'desk', 'couch']:
                    furniture.append(obj)
                elif obj_class in ['dog', 'cat', 'bottle', 'bag', 'box']:
                    obstacles.append(obj)
                else:
                    obstacles.append(obj)  # Все остальное как препятствие

            # Оценка безопасности движения
            total_obstacles = len(obstacles) + len(furniture)
            has_people = len(people) > 0

            # Простая логика оценки
            if has_people:
                safety_level = "осторожно"  # Люди рядом - нужна осторожность
            elif total_obstacles > 3:
                safety_level = "много_препятствий"
            elif total_obstacles > 0:
                safety_level = "есть_препятствия"
            else:
                safety_level = "путь_свободен"

            return {
                "success": True,
                "safety_level": safety_level,
                "obstacles_detected": total_obstacles > 0,
                "people_detected": has_people,
                "obstacles": obstacles,
                "people": people,
                "furniture": furniture,
                "total_objects": len(detected_objects),
                "recommendation": self._get_navigation_recommendation(safety_level, has_people, total_obstacles)
            }

        except Exception as e:
            logging.error(f"❌ Ошибка анализа для навигации: {e}")
            return {"error": str(e)}

    def _get_navigation_recommendation(self, safety_level, has_people, obstacle_count):
        """Получить рекомендацию для навигации"""
        if safety_level == "осторожно":
            return "Обнаружены люди - двигаться медленно и осторожно"
        elif safety_level == "много_препятствий":
            return f"Много препятствий ({obstacle_count}) - требуется планирование маршрута"
        elif safety_level == "есть_препятствия":
            return f"Есть препятствия ({obstacle_count}) - возможен объезд"
        else:
            return "Путь свободен - можно двигаться нормально"

    def get_scene_summary(self):
        """Получить краткую сводку о текущей сцене"""
        try:
            analysis = self.analyze_current_view()
            if not analysis.get("success"):
                return {"error": analysis.get("error", "Неизвестная ошибка")}

            detected_objects = analysis.get("detected_objects", [])

            # Создаем краткую сводку
            if detected_objects:
                object_counts = {}
                for obj in detected_objects:
                    class_name = obj['class']
                    object_counts[class_name] = object_counts.get(
                        class_name, 0) + 1

                summary_parts = []
                for obj_class, count in object_counts.items():
                    if count == 1:
                        summary_parts.append(obj_class)
                    else:
                        summary_parts.append(f"{obj_class} ({count})")

                summary = f"Вижу: {', '.join(summary_parts)}"
            else:
                summary = "Объекты не обнаружены"

            return {
                "success": True,
                "summary": summary,
                "object_count": len(detected_objects),
                "timestamp": analysis["timestamp"]
            }

        except Exception as e:
            return {"error": str(e)}

    def test_vision_system(self):
        """Тест системы компьютерного зрения"""
        results = {
            "camera_test": False,
            "yolo_detection_test": False,
            "gpt4v_test": False,
            "overall_test": False,
            "details": []
        }

        try:
            # 1. Тест камеры
            frame = self.capture_frame()
            if frame is not None:
                results["camera_test"] = True
                results["details"].append(
                    f"✅ Камера: кадр {frame.shape} получен")

                # 2. Тест YOLO детекции
                if self.ai_detector:
                    detections = self.detect_objects(frame)
                    results["yolo_detection_test"] = True
                    results["details"].append(
                        f"✅ YOLO: обнаружено {len(detections)} объектов")
                else:
                    results["details"].append("⚠️ YOLO детектор не подключен")

                # 3. Тест GPT-4V (если доступен API ключ)
                if self.api_key:
                    try:
                        description = self.describe_scene_with_llm(
                            frame, detections if 'detections' in locals() else [])
                        if description and len(description) > 10:
                            results["gpt4v_test"] = True
                            results["details"].append(
                                f"✅ GPT-4V: описание получено ({len(description)} символов)")
                        else:
                            results["details"].append(
                                "❌ GPT-4V: пустое или короткое описание")
                    except Exception as e:
                        results["details"].append(f"❌ GPT-4V: {e}")
                else:
                    results["details"].append("⚠️ OpenAI API ключ не настроен")

            else:
                results["details"].append("❌ Камера: не удалось получить кадр")

            # Общий результат
            total_tests = 3
            passed_tests = sum([
                results["camera_test"],
                results["yolo_detection_test"],
                results["gpt4v_test"]
            ])

            # Минимум камера + YOLO
            results["overall_test"] = passed_tests >= 2
            results["score"] = f"{passed_tests}/{total_tests}"

            logging.info(f"🧪 Тест системы зрения: {results['score']}")
            return results

        except Exception as e:
            logging.error(f"❌ Ошибка тестирования системы зрения: {e}")
            results["details"].append(f"Критическая ошибка: {e}")
            return results

    def get_status(self):
        """Получить статус системы компьютерного зрения"""
        return {
            "vision_analyzer": {
                "initialized": True,
                "camera_connected": self.camera is not None,
                "ai_detector_connected": self.ai_detector is not None,
                "openai_api_configured": bool(self.api_key),
                "vision_model": self.vision_model,
                "max_tokens": self.max_tokens
            }
        }
