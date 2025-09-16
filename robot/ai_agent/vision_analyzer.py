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
    Умная логика: YOLO детекции → фиксированные шаблоны, нет детекций → OpenAI Vision
    """

    def __init__(self, config, camera=None, ai_detector=None):
        self.config = config
        self.camera = camera
        self.ai_detector = ai_detector

        # OpenAI API для случаев когда YOLO ничего не видит
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
            logging.info("✅ OpenAI Vision API подключен для fallback")
        else:
            logging.warning(
                "⚠️ OpenAI API ключ не найден - только YOLO анализ")

        # Настройки для GPT-4V
        self.vision_model = config.get('vision_model', 'gpt-4o-mini')
        self.max_tokens = config.get('vision_max_tokens', 300)

        # Шаблоны для генерации описаний на основе YOLO
        self._init_description_templates()

        # Проверяем доступность компонентов
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

        logging.info("👁️ VisionAnalyzer с умной логикой инициализирован")

    def _init_description_templates(self):
        """Инициализация шаблонов описаний для разных типов объектов"""
        self.description_templates = {
            # Люди
            'person': [
                "Я вижу человека в поле зрения",
                "В кадре находится человек",
                "Обнаружен человек"
            ],
            'people': [
                "Я вижу несколько человек",
                "В кадре находятся люди",
                "Обнаружена группа людей"
            ],

            # Животные
            'cat': [
                "Я вижу кота",
                "В кадре находится кот",
                "Обнаружен кот"
            ],
            'dog': [
                "Я вижу собаку",
                "В кадре находится собака",
                "Обнаружена собака"
            ],

            # Мебель
            'chair': [
                "Я вижу стул",
                "В кадре находится стул"
            ],
            'sofa': [
                "Я вижу диван",
                "В кадре находится диван"
            ],
            'bed': [
                "Я вижу кровать",
                "В кадре находится кровать"
            ],
            'table': [
                "Я вижу стол",
                "В кадре находится стол"
            ],

            # Техника
            'tv': [
                "Я вижу телевизор",
                "В кадре находится телевизор"
            ],
            'laptop': [
                "Я вижу ноутбук",
                "В кадре находится ноутбук"
            ],
            'cell phone': [
                "Я вижу телефон",
                "В кадре находится телефон"
            ],

            # Транспорт
            'car': [
                "Я вижу автомобиль",
                "В кадре находится машина"
            ],
            'bicycle': [
                "Я вижу велосипед",
                "В кадре находится велосипед"
            ],

            # Общие объекты
            'bottle': [
                "Я вижу бутылку",
                "В кадре находится бутылка"
            ],
            'cup': [
                "Я вижу чашку",
                "В кадре находится чашка"
            ],
            'book': [
                "Я вижу книгу",
                "В кадре находится книга"
            ],

            # Еда
            'banana': [
                "Я вижу банан",
                "В кадре находится банан"
            ],
            'apple': [
                "Я вижу яблоко",
                "В кадре находится яблоко"
            ],

            # Fallback для неизвестных объектов
            'default': [
                "Я обнаружил объект",
                "В кадре находится предмет"
            ]
        }

    def capture_frame(self):
        """Получить текущий кадр с камеры"""
        if not self.camera:
            logging.error("❌ Камера не подключена")
            return None

        try:
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

    def detect_objects_yolo(self, frame):
        """Детекция объектов через YOLO"""
        if not self.ai_detector:
            logging.warning("⚠️ AI детектор не подключен")
            return []

        try:
            detections = self.ai_detector.detect_objects(frame)

            # Адаптируем формат
            detected_objects = []
            for det in detections:
                detected_objects.append({
                    'class': det.get('class_name', 'unknown'),
                    'confidence': det.get('confidence', 0.0),
                    'bbox': det.get('bbox', [0, 0, 0, 0]),
                    'center': det.get('center', [0, 0])
                })

            logging.info(f"🔍 YOLO обнаружил объектов: {len(detected_objects)}")
            for obj in detected_objects:
                logging.debug(f"   {obj['class']} ({obj['confidence']:.2f})")

            return detected_objects

        except Exception as e:
            logging.error(f"❌ Ошибка YOLO детекции: {e}")
            return []

    def generate_yolo_description(self, detected_objects):
        """Генерация описания на основе YOLO детекций с фиксированными шаблонами"""
        if not detected_objects:
            return None

        try:
            # Группируем объекты по классам
            object_counts = {}
            high_confidence_objects = []

            for obj in detected_objects:
                class_name = obj['class'].lower()
                confidence = obj['confidence']

                # Считаем только объекты с хорошей уверенностью
                if confidence > 0.5:
                    object_counts[class_name] = object_counts.get(
                        class_name, 0) + 1
                    if confidence > 0.7:
                        high_confidence_objects.append(
                            (class_name, confidence))

            if not object_counts:
                return None

            # Генерируем описание
            description_parts = []

            # Сначала наиболее уверенные объекты
            processed_classes = set()

            for class_name, confidence in sorted(high_confidence_objects, key=lambda x: x[1], reverse=True):
                if class_name in processed_classes:
                    continue

                count = object_counts[class_name]

                # Выбираем подходящий шаблон
                if count > 1 and class_name == 'person':
                    template_key = 'people'
                else:
                    template_key = class_name

                templates = self.description_templates.get(
                    template_key, self.description_templates['default'])

                # Выбираем шаблон (можно добавить рандом для разнообразия)
                template = templates[0]

                # Адаптируем для множественного числа
                if count > 1 and template_key != 'people':
                    if class_name in ['chair', 'table', 'bottle', 'cup', 'book']:
                        if 'стул' in template:
                            template = template.replace(
                                'стул', f"{count} стула")
                        elif 'стол' in template:
                            template = template.replace(
                                'стол', f"{count} стола")
                        elif 'бутылку' in template:
                            template = template.replace(
                                'бутылку', f"{count} бутылки")
                        elif 'чашку' in template:
                            template = template.replace(
                                'чашку', f"{count} чашки")
                        elif 'книгу' in template:
                            template = template.replace(
                                'книгу', f"{count} книги")
                        else:
                            template = f"Я вижу {count} предмета класса {class_name}"
                    else:
                        template = f"Я вижу несколько объектов: {class_name}"

                description_parts.append(template)
                processed_classes.add(class_name)

                # Ограничиваем количество объектов в описании
                if len(description_parts) >= 3:
                    break

            # Добавляем оставшиеся объекты общим списком если есть
            remaining_objects = [
                cls for cls in object_counts.keys() if cls not in processed_classes]
            if remaining_objects and len(description_parts) < 3:
                if len(remaining_objects) == 1:
                    description_parts.append(
                        f"Также вижу {remaining_objects[0]}")
                else:
                    description_parts.append(
                        f"Также вижу: {', '.join(remaining_objects[:2])}")

            # Формируем итоговое описание
            if len(description_parts) == 1:
                final_description = description_parts[0]
            elif len(description_parts) == 2:
                final_description = f"{description_parts[0]}. {description_parts[1]}"
            else:
                final_description = f"{description_parts[0]}. {description_parts[1]}. {description_parts[2]}"

            # Добавляем информацию об уверенности если нужно
            max_confidence = max([obj['confidence']
                                 for obj in detected_objects])
            if max_confidence < 0.7:
                final_description += ". Уверенность детекции средняя"

            logging.info(
                f"✅ Сгенерировано YOLO описание: '{final_description}'")
            return final_description

        except Exception as e:
            logging.error(f"❌ Ошибка генерации YOLO описания: {e}")
            return None

    def describe_scene_with_openai(self, frame):
        """Описание сцены через OpenAI Vision API когда YOLO ничего не нашел"""
        if not self.client:
            return "Детекция объектов не показала результатов, а OpenAI Vision API недоступен"

        try:
            logging.info(
                "🧠 YOLO ничего не нашел, отправляю фото в OpenAI Vision...")

            # Кодируем изображение
            image_base64 = self._encode_image_to_base64(frame)
            if not image_base64:
                return "Не удалось обработать изображение для анализа"

            # Отправляем в OpenAI с специальным промптом
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Мой робот смотрит камерой, но детектор объектов YOLO ничего конкретного не обнаружил. Опиши простыми словами что ты видишь на этом изображении - обстановку, цвета, формы, любые детали которые могут быть интересны. Ответь как робот-помощник, кратко и понятно."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ]

            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.3
            )

            description = response.choices[0].message.content.strip()
            logging.info(f"✅ OpenAI Vision описание: '{description[:100]}...'")
            return description

        except Exception as e:
            logging.error(f"❌ Ошибка OpenAI Vision: {e}")
            return "Не могу проанализировать изображение - попробуйте позже"

    def _encode_image_to_base64(self, frame):
        """Конвертация кадра в base64 для OpenAI"""
        try:
            # Уменьшаем размер для экономии токенов
            height, width = frame.shape[:2]
            if width > 800:  # Уменьшаем если слишком большое
                scale = 800 / width
                new_width = 800
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height))

            # Конвертируем в JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
            success, buffer = cv2.imencode('.jpg', frame, encode_param)

            if not success:
                return None

            # В base64
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            # Проверяем размер
            size_mb = len(image_base64) * 0.75 / 1024 / 1024
            if size_mb > 10:  # Ограничиваем размер
                logging.warning(f"⚠️ Изображение большое: {size_mb:.1f}MB")
                return None

            return image_base64

        except Exception as e:
            logging.error(f"❌ Ошибка кодирования: {e}")
            return None

    def analyze_current_view(self):
        """
        ГЛАВНАЯ ФУНКЦИЯ: Умный анализ текущего вида
        Логика: YOLO сначала → фиксированные шаблоны, нет детекций → OpenAI
        """
        try:
            logging.info("👁️ Начинаю умный анализ текущего вида...")

            # 1. Получаем кадр с камеры
            frame = self.capture_frame()
            if frame is None:
                return {
                    "success": False,
                    "error": "Не удалось получить изображение с камеры"
                }

            # 2. Пробуем YOLO детекцию
            detected_objects = self.detect_objects_yolo(frame)

            # 3. УМНАЯ ЛОГИКА: если есть детекции → фиксированные шаблоны
            if detected_objects:
                yolo_description = self.generate_yolo_description(
                    detected_objects)

                if yolo_description:
                    # Используем результат YOLO без обращения к OpenAI
                    result = {
                        "success": True,
                        "description": yolo_description,
                        "detected_objects": detected_objects,
                        "objects_count": len(detected_objects),
                        "analysis_method": "yolo_templates",
                        "timestamp": datetime.now().isoformat(),
                        "openai_used": False
                    }

                    logging.info(
                        f"✅ Анализ через YOLO шаблоны: {len(detected_objects)} объектов")
                    return result

            # 4. Если YOLO ничего не нашел → отправляем в OpenAI
            logging.info(
                "🔄 YOLO не дал результатов, используем OpenAI Vision...")

            openai_description = self.describe_scene_with_openai(frame)

            result = {
                "success": True,
                "description": openai_description,
                "detected_objects": detected_objects,  # Может быть пустой список
                "objects_count": len(detected_objects),
                "analysis_method": "openai_vision",
                "timestamp": datetime.now().isoformat(),
                "openai_used": True
            }

            logging.info("✅ Анализ через OpenAI Vision завершен")
            return result

        except Exception as e:
            logging.error(f"❌ Ошибка умного анализа: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def get_quick_scene_summary(self):
        """Быстрая сводка о сцене только через YOLO"""
        try:
            frame = self.capture_frame()
            if frame is None:
                return {"error": "Камера недоступна"}

            detected_objects = self.detect_objects_yolo(frame)

            if detected_objects:
                # Краткая сводка
                object_counts = {}
                for obj in detected_objects:
                    if obj['confidence'] > 0.5:
                        class_name = obj['class']
                        object_counts[class_name] = object_counts.get(
                            class_name, 0) + 1

                if object_counts:
                    summary_parts = []
                    for obj_class, count in object_counts.items():
                        if count == 1:
                            summary_parts.append(obj_class)
                        else:
                            summary_parts.append(f"{obj_class} ({count})")

                    summary = f"Быстрый обзор: {', '.join(summary_parts)}"
                else:
                    summary = "Объекты обнаружены, но с низкой уверенностью"
            else:
                summary = "Конкретные объекты не обнаружены"

            return {
                "success": True,
                "summary": summary,
                "object_count": len(detected_objects),
                "method": "yolo_only"
            }

        except Exception as e:
            return {"error": str(e)}

    def test_vision_system(self):
        """Тест всей системы зрения"""
        results = {
            "camera_test": False,
            "yolo_test": False,
            "openai_test": False,
            "templates_test": False,
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

                # 2. Тест YOLO
                if self.ai_detector:
                    detections = self.detect_objects_yolo(frame)
                    results["yolo_test"] = True
                    results["details"].append(
                        f"✅ YOLO: {len(detections)} детекций")

                    # 3. Тест шаблонов
                    if detections:
                        template_desc = self.generate_yolo_description(
                            detections)
                        if template_desc:
                            results["templates_test"] = True
                            results["details"].append(
                                "✅ Шаблоны: описание сгенерировано")
                        else:
                            results["details"].append(
                                "❌ Шаблоны: не удалось сгенерировать")
                    else:
                        results["details"].append(
                            "ℹ️ Шаблоны: нет объектов для тестирования")

                    # 4. Тест OpenAI (если доступен)
                    if self.client:
                        try:
                            openai_desc = self.describe_scene_with_openai(
                                frame)
                            if openai_desc and len(openai_desc) > 10:
                                results["openai_test"] = True
                                results["details"].append(
                                    "✅ OpenAI Vision: работает")
                            else:
                                results["details"].append(
                                    "❌ OpenAI Vision: короткий ответ")
                        except Exception as e:
                            results["details"].append(f"❌ OpenAI Vision: {e}")
                    else:
                        results["details"].append(
                            "⚠️ OpenAI Vision: API ключ не настроен")

                else:
                    results["details"].append("❌ YOLO детектор не подключен")
            else:
                results["details"].append("❌ Камера: не удалось получить кадр")

            # Общий результат
            results["overall_test"] = results["camera_test"] and results["yolo_test"]

            passed = sum([results["camera_test"], results["yolo_test"],
                         results["templates_test"], results["openai_test"]])
            results["score"] = f"{passed}/4"

            logging.info(f"🧪 Тест умной системы зрения: {results['score']}")
            return results

        except Exception as e:
            results["details"].append(f"Критическая ошибка: {e}")
            return results

    def get_status(self):
        """Статус умной системы зрения"""
        return {
            "smart_vision_analyzer": {
                "initialized": True,
                "camera_connected": self.camera is not None,
                "yolo_detector_connected": self.ai_detector is not None,
                "openai_available": self.client is not None,
                "templates_loaded": len(self.description_templates) > 0,
                "vision_model": self.vision_model,
                "analysis_strategy": "yolo_first_then_openai"
            }
        }
