import json
import logging
import openai
from datetime import datetime
from pathlib import Path
from robot.ai_agent.speech_handler import SpeechHandler
from robot.ai_agent.vision_analyzer import VisionAnalyzer
from robot.ai_agent.audio_manager import AudioManager


class AIOrchestrater:
    """
    Центральный AI оркестратор робота
    Координирует работу всех AI агентов и принимает решения
    """

    def __init__(self, camera=None, robot_controller=None, ai_detector=None):
        """
        Инициализация AI оркестратора
        :param camera: существующий объект камеры
        :param robot_controller: существующий контроллер робота  
        :param ai_detector: существующий SimpleAIDetector
        """
        self.config = self._load_config()
        self.camera = camera
        self.robot = robot_controller
        self.ai_detector = ai_detector

        # Инициализируем агентов
        self.speech = None
        self.vision = None
        self.audio_manager = None

        self._initialize_agents()

        # История и контекст
        self.conversation_history = []
        self.current_context = {}

        logging.info("🧠 AI Оркестратор инициализирован")

    def _load_config(self):
        """Загрузить конфигурацию AI"""
        config_path = Path("data/ai_config.json")
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logging.info("📄 Конфигурация AI загружена")
                return config
            else:
                # Дефолтная конфигурация
                default_config = {
                    "openai_api_key": "",
                    "model": "gpt-4o-mini",
                    "speech_enabled": True,
                    "vision_enabled": True,
                    "max_conversation_length": 10,
                    "audio": {
                        "sample_rate": 16000,
                        "channels": 1,
                        "chunk_size": 1024,
                        "microphone_index": None,
                        "speaker_index": None
                    },
                    "intents": {
                        "vision_keywords": ["видишь", "посмотри", "что там", "опиши", "сцена", "камера"],
                        "status_keywords": ["статус", "состояние", "как дела", "работает", "датчики", "системы"],
                        "action_keywords": ["поехали", "двигайся", "поверни", "остановись", "вперед", "назад"],
                        "context_keywords": ["расскажи", "анализ", "происходит", "ситуация", "обстановка"]
                    }
                }

                # Создаем конфигурацию
                config_path.parent.mkdir(exist_ok=True)
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
                logging.info("📄 Создана дефолтная конфигурация AI")
                return default_config

        except Exception as e:
            logging.error(f"❌ Ошибка загрузки конфигурации: {e}")
            return {
                "openai_api_key": "",
                "speech_enabled": False,
                "vision_enabled": False
            }

    def _initialize_agents(self):
        """Инициализация всех AI агентов"""

        # Проверяем API ключ
        api_key = self.config.get('openai_api_key')
        if not api_key:
            logging.warning("⚠️ OpenAI API ключ не настроен")
            return

        openai.api_key = api_key

        # AudioManager (всегда инициализируем для тестов)
        try:
            self.audio_manager = AudioManager(self.config.get('audio', {}))
            logging.info("✅ AudioManager инициализирован")
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации AudioManager: {e}")

        # Speech Agent
        if self.config.get('speech_enabled', True):
            try:
                self.speech = SpeechHandler(self.config)
                self.speech.audio_manager = self.audio_manager  # Связываем с аудио
                logging.info("✅ Speech Agent инициализирован")

                # Тестируем аудио если доступно
                if self.audio_manager:
                    audio_test = self.audio_manager.test_audio_system()
                    if audio_test["microphone_test"] and audio_test["speaker_test"]:
                        logging.info("✅ Аудио система протестирована успешно")
                    else:
                        logging.warning("⚠️ Проблемы с аудио системой")

            except Exception as e:
                logging.error(f"❌ Ошибка инициализации Speech Agent: {e}")

        # Vision Agent
        if self.config.get('vision_enabled', True):
            try:
                self.vision = VisionAnalyzer(
                    config=self.config,
                    camera=self.camera,
                    ai_detector=self.ai_detector
                )
                logging.info("✅ Vision Agent инициализирован")
            except Exception as e:
                logging.error(f"❌ Ошибка инициализации Vision Agent: {e}")

    def analyze_user_intent(self, user_text):
        """Определение намерения пользователя через ключевые слова и LLM"""
        if not user_text:
            return 'chat'

        user_text_lower = user_text.lower()

        # Сначала проверяем через ключевые слова (быстро)
        intents = self.config.get('intents', {})

        for keyword in intents.get('vision_keywords', []):
            if keyword in user_text_lower:
                return 'vision'

        for keyword in intents.get('status_keywords', []):
            if keyword in user_text_lower:
                return 'status'

        for keyword in intents.get('action_keywords', []):
            if keyword in user_text_lower:
                return 'action'

        for keyword in intents.get('context_keywords', []):
            if keyword in user_text_lower:
                return 'context'

        # Если не нашли через ключевые слова - используем LLM
        try:
            system_prompt = """Ты анализируешь запросы к роботу и определяешь тип ответа.

Возможные типы:
- "chat" - обычная беседа, вопросы, шутки
- "vision" - просьба посмотреть, описать что видишь
- "action" - команды движения, управления роботом  
- "status" - вопросы о состоянии робота, датчиках
- "context" - сложные вопросы требующие полной информации

Отвечай ТОЛЬКО одним словом типа."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Запрос: '{user_text}'"}
            ]

            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=10,
                temperature=0.1
            )

            intent = response.choices[0].message.content.strip().lower()
            valid_intents = ['chat', 'vision', 'action', 'status', 'context']

            if intent in valid_intents:
                logging.info(f"🎯 LLM определил намерение: {intent}")
                return intent
            else:
                logging.warning(f"⚠️ Неизвестное намерение от LLM: {intent}")
                return 'chat'

        except Exception as e:
            logging.error(f"❌ Ошибка анализа намерений через LLM: {e}")
            return 'chat'  # По умолчанию

    def get_sensor_context(self):
        """Получить контекст с датчиков и систем робота"""
        context = {
            "timestamp": datetime.now().isoformat(),
            "robot_systems": {}
        }

        # Данные с робота
        if self.robot:
            try:
                robot_status = self.robot.get_status()
                context["robot_systems"].update({
                    "status": robot_status.get("status", "unknown"),
                    "battery_voltage": robot_status.get("battery_voltage"),
                    "sensors": robot_status.get("sensors", {}),
                    "movement": robot_status.get("movement", "stopped")
                })
            except Exception as e:
                logging.error(f"Ошибка получения статуса робота: {e}")

        # Статус камеры
        if self.camera:
            try:
                camera_status = self.camera.get_status()
                context["camera"] = {
                    "available": camera_status.get("available", False),
                    "connected": camera_status.get("connected", False),
                    "resolution": camera_status.get("resolution", "unknown")
                }
            except Exception as e:
                logging.error(f"Ошибка получения статуса камеры: {e}")

        # Аудио система
        if self.audio_manager:
            try:
                devices = self.audio_manager.get_audio_devices_info()
                context["audio"] = {
                    "microphones_count": len(devices.get("microphones", [])),
                    "speakers_count": len(devices.get("speakers", [])),
                    "microphone_selected": devices.get("selected_microphone") is not None,
                    "speaker_selected": devices.get("selected_speaker") is not None
                }
            except Exception as e:
                logging.error(f"Ошибка получения статуса аудио: {e}")

        return context

    def smart_process_request(self, audio_file=None, text=None):
        """
        ГЛАВНЫЙ метод - умная обработка любого запроса пользователя
        Автоматически определяет намерение и выбирает подходящий обработчик
        """
        try:
            # 1. Получаем текст пользователя
            if audio_file:
                if not self.speech:
                    return {"error": "Голосовой модуль не активен"}

                user_text = self.speech.transcribe_audio(audio_file)
                if not user_text:
                    return {"error": "Не удалось распознать речь"}

            elif text:
                user_text = text
            else:
                return {"error": "Нет входных данных"}

            logging.info(f"👤 Пользователь: '{user_text}'")

            # 2. Определяем намерение
            intent = self.analyze_user_intent(user_text)
            logging.info(f"🎯 Определено намерение: {intent}")

            # 3. Маршрутизируем на нужный обработчик
            if intent == 'vision':
                return self._handle_vision_request(user_text, audio_file is not None)

            elif intent == 'status':
                return self._handle_status_request(user_text, audio_file is not None)

            elif intent == 'action':
                return self._handle_action_request(user_text, audio_file is not None)

            elif intent == 'context':
                return self._handle_context_request(user_text, audio_file is not None)

            else:  # intent == 'chat'
                return self._handle_chat_request(user_text, audio_file is not None)

        except Exception as e:
            logging.error(f"❌ Ошибка умной обработки запроса: {e}")
            return {"error": str(e)}

    def _handle_vision_request(self, user_text, is_voice=False):
        """Обработка запросов на описание того что видит робот"""
        if not self.vision:
            response_text = "Извини, модуль зрения не активен"
        else:
            vision_result = self.vision.analyze_current_view()
            if vision_result.get("success"):
                response_text = vision_result["description"]

                # Добавляем данные для веб-интерфейса
                extra_data = {
                    "vision_data": vision_result,
                    "detected_objects": vision_result.get("detected_objects", [])
                }
            else:
                response_text = "Не могу проанализировать изображение с камеры"
                extra_data = {}

        return self._create_response(
            user_text=user_text,
            ai_response=response_text,
            intent='vision',
            is_voice=is_voice,
            extra_data=extra_data
        )

    def _handle_status_request(self, user_text, is_voice=False):
        """Обработка запросов о состоянии робота"""
        try:
            context = self.get_sensor_context()

            # Формируем человеко-читаемый статус
            status_parts = []

            if context.get("robot_systems", {}).get("status"):
                status_parts.append(
                    f"Основные системы: {context['robot_systems']['status']}")

            if context.get("robot_systems", {}).get("battery_voltage"):
                battery = context['robot_systems']['battery_voltage']
                status_parts.append(f"Батарея: {battery}V")

            if context.get("camera", {}).get("connected"):
                status_parts.append("Камера подключена")

            if context.get("audio", {}).get("microphone_selected"):
                status_parts.append("Микрофон активен")

            if not status_parts:
                status_parts.append("Системы работают в штатном режиме")

            basic_status = ". ".join(status_parts)

            # Генерируем развернутый ответ через LLM
            if self.speech:
                enhanced_prompt = f"""Статус робота: {basic_status}
                Подробные данные: {json.dumps(context, ensure_ascii=False)}
                Вопрос пользователя: {user_text}
                
                Ответь как робот-помощник, кратко и понятно о своем состоянии."""

                ai_response = self.speech.generate_response(enhanced_prompt)
            else:
                ai_response = basic_status

            return self._create_response(
                user_text=user_text,
                ai_response=ai_response,
                intent='status',
                is_voice=is_voice,
                extra_data={"context_data": context}
            )

        except Exception as e:
            return self._create_response(
                user_text=user_text,
                ai_response="Не могу получить информацию о состоянии систем",
                intent='status',
                is_voice=is_voice,
                extra_data={"error": str(e)}
            )

    def _handle_action_request(self, user_text, is_voice=False):
        """Обработка команд движения и управления"""
        # TODO: Интеграция с системой управления роботом
        # Сейчас только заглушка

        action_response = "Понял команду управления, но выполнение движений пока не подключено к ИИ. Используй веб-интерфейс для управления."

        # В будущем здесь будет:
        # - Парсинг команды движения
        # - Вызов методов robot_controller
        # - Контроль безопасности

        return self._create_response(
            user_text=user_text,
            ai_response=action_response,
            intent='action',
            is_voice=is_voice,
            extra_data={"planned_action": "movement_control_not_implemented"}
        )

    def _handle_context_request(self, user_text, is_voice=False):
        """Обработка сложных запросов с полным контекстом"""
        try:
            # Собираем полный контекст
            sensor_context = self.get_sensor_context()

            # Добавляем информацию о том что видит робот
            vision_info = {}
            if self.vision:
                vision_result = self.vision.analyze_current_view()
                if vision_result.get("success"):
                    vision_info = {
                        "current_view": vision_result.get("description", ""),
                        "detected_objects": vision_result.get("detected_objects", [])
                    }

            # Формируем полный промпт для LLM
            full_context = {
                "sensors_and_systems": sensor_context,
                "vision": vision_info,
                "conversation_history": self.conversation_history[-3:] if self.conversation_history else []
            }

            context_prompt = f"""Ты робот-помощник. Вот полная информация о текущей ситуации:

{json.dumps(full_context, ensure_ascii=False, indent=2)}

Вопрос пользователя: {user_text}

Проанализируй всю доступную информацию и дай развернутый, но понятный ответ о текущей ситуации."""

            if self.speech:
                ai_response = self.speech.generate_response(context_prompt)
            else:
                ai_response = "Для полного анализа ситуации необходим активный ИИ модуль"

            return self._create_response(
                user_text=user_text,
                ai_response=ai_response,
                intent='context',
                is_voice=is_voice,
                extra_data={
                    "full_context": full_context,
                    "vision_data": vision_info
                }
            )

        except Exception as e:
            return self._create_response(
                user_text=user_text,
                ai_response="Не могу провести полный анализ ситуации",
                intent='context',
                is_voice=is_voice,
                extra_data={"error": str(e)}
            )

    def _handle_chat_request(self, user_text, is_voice=False):
        """Обработка обычных диалоговых запросов"""
        if not self.speech:
            ai_response = "Модуль общения не активен"
        else:
            ai_response = self.speech.generate_response(user_text)

        return self._create_response(
            user_text=user_text,
            ai_response=ai_response,
            intent='chat',
            is_voice=is_voice
        )

    def _create_response(self, user_text, ai_response, intent, is_voice=False, extra_data=None):
        """Создание унифицированного ответа"""
        response = {
            "success": True,
            "user_text": user_text,
            "ai_response": ai_response,
            "intent": intent,
            "timestamp": datetime.now().isoformat(),
            "is_voice": is_voice
        }

        # Добавляем дополнительные данные
        if extra_data:
            response.update(extra_data)

        # Генерируем аудио если это голосовой запрос
        if is_voice and self.speech and self.speech.audio_manager:
            try:
                audio_file = self.speech.text_to_speech(ai_response)
                response["audio_file"] = audio_file

                # Можем сразу воспроизвести
                # speech_success = self.speech.audio_manager.play_audio(audio_file)
                # response["speech_played"] = speech_success

            except Exception as e:
                logging.error(f"Ошибка генерации аудио: {e}")

        # Сохраняем в историю
        self._add_to_history(user_text, ai_response, intent)

        logging.info(f"🤖 Ответ ({intent}): '{ai_response}'")
        return response

    def voice_chat(self, recording_duration=5):
        """Полный цикл голосового общения с физическими устройствами"""
        if not self.speech or not self.speech.audio_manager:
            return {"error": "Аудио система не активна"}

        try:
            logging.info("🎤 Начинаю голосовой чат...")

            # 1. Записываем с микрофона
            audio_file = self.speech.audio_manager.record_audio(
                duration_seconds=recording_duration,
                output_file=f"data/temp_voice_{int(datetime.now().timestamp())}.wav"
            )

            if not audio_file:
                return {"error": "Не удалось записать аудио"}

            # 2. Обрабатываем через умный роутер
            result = self.smart_process_request(audio_file=audio_file)

            if not result.get("success"):
                return result

            # 3. Воспроизводим ответ через динамики
            if result.get("audio_file"):
                speech_success = self.speech.audio_manager.play_audio(
                    result["audio_file"])
                result["speech_played"] = speech_success

                if speech_success:
                    logging.info("🔊 Ответ воспроизведен через динамики")
                else:
                    logging.warning("⚠️ Не удалось воспроизвести ответ")

            # Удаляем временный файл записи
            try:
                Path(audio_file).unlink(missing_ok=True)
            except:
                pass

            return result

        except Exception as e:
            logging.error(f"❌ Ошибка голосового чата: {e}")
            return {"error": str(e)}

    def _add_to_history(self, user_text, ai_response, intent):
        """Добавление в историю диалогов"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_text": user_text,
            "ai_response": ai_response,
            "intent": intent
        }

        self.conversation_history.append(entry)

        # Ограничиваем размер истории
        max_length = self.config.get('max_conversation_length', 10)
        if len(self.conversation_history) > max_length:
            self.conversation_history = self.conversation_history[-max_length:]

        # Сохраняем в файл (асинхронно)
        try:
            conversations_file = Path("data/conversations.json")
            conversations_file.parent.mkdir(exist_ok=True)

            with open(conversations_file, 'w', encoding='utf-8') as f:
                json.dump(self.conversation_history, f,
                          ensure_ascii=False, indent=2)

        except Exception as e:
            logging.error(f"Ошибка сохранения истории: {e}")

    # ====== ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ ======

    def chat(self, audio_file=None, text=None):
        """Простое общение (обратная совместимость)"""
        return self.smart_process_request(audio_file=audio_file, text=text)

    def describe_scene(self):
        """Описать что видит робот (обратная совместимость)"""
        if not self.vision:
            return {"error": "Видео модуль отключен"}
        return self.vision.analyze_current_view()

    def get_status(self):
        """Получить статус AI оркестратора"""
        return {
            "ai_orchestrator": {
                "initialized": True,
                "speech_available": self.speech is not None,
                "vision_available": self.vision is not None,
                "audio_hardware_available": (
                    self.audio_manager is not None and
                    self.audio_manager.microphone_index is not None and
                    self.audio_manager.speaker_index is not None
                ),
                "api_key_configured": bool(self.config.get('openai_api_key')),
                "conversation_entries": len(self.conversation_history),
                "config": {
                    "speech_enabled": self.config.get('speech_enabled', False),
                    "vision_enabled": self.config.get('vision_enabled', False),
                    "model": self.config.get('model', 'not set')
                }
            }
        }

    def update_config(self, new_config):
        """Обновить конфигурацию и переинициализировать агентов"""
        try:
            self.config.update(new_config)

            # Сохраняем обновленную конфигурацию
            config_path = Path("data/ai_config.json")
            config_path.parent.mkdir(exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)

            # Переинициализируем агентов с новой конфигурацией
            self._initialize_agents()

            logging.info(
                "✅ Конфигурация AI обновлена и агенты переинициализированы")
            return {"success": True, "message": "Конфигурация обновлена"}

        except Exception as e:
            logging.error(f"❌ Ошибка обновления конфигурации: {e}")
            return {"error": str(e)}

    def get_conversation_history(self):
        """Получить историю диалогов"""
        return {
            "history": self.conversation_history,
            "total_entries": len(self.conversation_history)
        }

    def clear_conversation_history(self):
        """Очистить историю диалогов"""
        self.conversation_history = []
        try:
            conversations_file = Path("data/conversations.json")
            if conversations_file.exists():
                conversations_file.unlink()
            return {"success": True, "message": "История диалогов очищена"}
        except Exception as e:
            return {"error": str(e)}
