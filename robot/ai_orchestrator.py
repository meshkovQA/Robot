from curses import raw
import json
import logging
from openai import OpenAI
from datetime import datetime
from pathlib import Path
from robot.ai_agent.speech_handler import SpeechHandler
from robot.ai_agent.vision_analyzer import VisionAnalyzer
from robot.ai_agent.audio_manager import AudioManager
from robot.ai_agent.sensor_status_reporter import SensorStatusReporter


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
        self.wake_word_service = None
        self.openai_client = None

        self.sensor_reporter = SensorStatusReporter()

        self._initialize_agents()

        # История и контекст
        self.conversation_history = []
        self.current_context = {}

        # Загружаем системные промпты
        self._load_system_prompts()

        logging.info("🧠 AI Оркестратор инициализирован")

    def _load_config(self):
        """Загрузить конфигурацию AI"""
        import os

        config_path = Path("data/ai_config.json")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logging.info("📄 Конфигурация AI загружена")

        # Переопределяем API ключ из environment переменной
        env_api_key = os.getenv('OPENAI_API_KEY')
        if env_api_key:
            config['openai_api_key'] = env_api_key
            logging.info(
                "🔑 OpenAI API ключ загружен из environment переменной")

        return config

    def _load_system_prompts(self):
        """Загрузить системные промпты из JSON файла"""
        prompts_file = Path("data/system_prompts.json")

        with open(prompts_file, 'r', encoding='utf-8') as f:
            self.system_prompts = json.load(f)

        logging.info(
            f"📄 Загружено {len(self.system_prompts)} системных промптов")

    def _initialize_agents(self):
        """Инициализация всех AI агентов"""

        # Проверяем что конфигурация загружена
        if not self.config:
            logging.error("❌ Конфигурация AI не загружена! self.config = None")
            return

        # Проверяем API ключ
        api_key = self.config.get('openai_api_key')
        if not api_key:
            logging.warning("⚠️ OpenAI API ключ не настроен")
            return

        # Создаем OpenAI клиент для анализа намерений
        self.openai_client = OpenAI(api_key=api_key)

        # AudioManager (всегда инициализируем для тестов)
        try:
            self.audio_manager = AudioManager(self.config.get('audio', {}))
            logging.info("✅ AudioManager инициализирован")
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации AudioManager: {e}")

        # SpeechHandler (для голосового взаимодействия)
        if self.config.get('speech_enabled', True):
            try:
                self.speech = SpeechHandler(self.config)
                if self.audio_manager:
                    self.speech.audio_manager = self.audio_manager
                logging.info("✅ SpeechHandler инициализирован")
            except Exception as e:
                logging.error(f"❌ Ошибка инициализации SpeechHandler: {e}")

        # WakeWordService (для голосовой активации)
        if self.config.get('wake_word_enabled', True) and api_key:
            try:
                from robot.ai_agent.wake_word_service import WakeWordService
                self.wake_word_service = WakeWordService(
                    self.config, ai_orchestrator=self)

                # АВТОЗАПУСК WakeWordService
                if self.wake_word_service.start_service():
                    logging.info("🚀 WakeWordService автоматически запущен")
                else:
                    logging.warning("⚠️ Не удалось запустить WakeWordService")

            except Exception as e:
                logging.error(f"❌ Ошибка инициализации WakeWordService: {e}")
                self.wake_word_service = None
        else:
            self.wake_word_service = None
            if not api_key:
                logging.warning(
                    "⚠️ WakeWordService пропущен: нет OpenAI API ключа")

    def analyze_user_intent(self, user_text):
        """Определение намерения пользователя через ключевые слова"""
        user_text_lower = user_text.lower().strip()

        # Ключевые слова для определения намерения 'vision'
        vision_keywords = [
            'что ты видишь', 'опиши', 'описать', 'камера',
            'что перед тобой', 'анализируй изображение',
            'что на экране'
        ]

        # Ключевые слова для полного статуса датчиков
        full_status_keywords = [
            'полный статус', 'полная диагностика', 'проверь все системы',
            'отчет по всем датчикам', 'диагностика всех систем'
        ]

        # Ключевые слова для быстрого статуса
        quick_status_keywords = [
            'быстрый статус', 'краткий статус', 'состояние робота', 'сводка'
        ]

        # Ключевые слова для предупреждений
        alerts_keywords = [
            'есть ли проблемы', 'предупреждения', 'тревоги', 'опасность', 'ошибки', 'неисправности'
        ]

        # Ключевые слова для конкретных датчиков
        sensors_specific_keywords = [
            'датчики расстояния', 'препятствия', 'температура', 'влажность',
            'энкодеры', 'скорость колес', 'ориентация', 'наклон', 'роборука'
        ]

        # Проверяем на намерение 'vision'
        for keyword in vision_keywords:
            if keyword in user_text_lower:
                logging.info(
                    f"🎯 Определено намерение 'vision' по ключевому слову: '{keyword}'")
                return 'vision'

                # Проверяем на намерение 'status_full'
        for keyword in full_status_keywords:
            if keyword in user_text_lower:
                logging.info(
                    f"🎯 Определено намерение 'status_full' по ключевому слову: '{keyword}'")
                return 'status_full'

        # Проверяем на намерение 'status_quick'
        for keyword in quick_status_keywords:
            if keyword in user_text_lower:
                logging.info(
                    f"🎯 Определено намерение 'status_quick' по ключевому слову: '{keyword}'")
                return 'status_quick'

        # Проверяем на намерение 'status_alerts'
        for keyword in alerts_keywords:
            if keyword in user_text_lower:
                logging.info(
                    f"🎯 Определено намерение 'status_alerts' по ключевому слову: '{keyword}'")
                return 'status_alerts'

        # Проверяем на намерение 'status_specific'
        for keyword in sensors_specific_keywords:
            if keyword in user_text_lower:
                logging.info(
                    f"🎯 Определено намерение 'status_specific' по ключевому слову: '{keyword}'")
                return 'status_specific'

        # Если никакие ключевые слова не найдены - это обычный чат
        logging.info("🎯 Определено намерение 'chat' (по умолчанию)")
        return 'chat'

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

        tts_instructions = None
        if is_voice and self.config.get('tts_instructions', {}).get('vision'):
            tts_instructions = self.config['tts_instructions']['vision']

        return self._create_response(
            user_text=user_text,
            ai_response=response_text,
            intent='vision',
            is_voice=is_voice,
            extra_data=extra_data,
            tts_instructions=tts_instructions
        )

    def _handle_status_request(self, user_text, is_voice=False, status_type='status'):
        """Обработка запросов о состоянии робота через sensor_reporter"""
        try:

            if not self.robot:
                response_text = "Контроллер робота недоступен"
                return self._create_response(
                    user_text=user_text,
                    ai_response=response_text,
                    intent='status_error',
                    is_voice=is_voice,
                    extra_data={"error": "robot_unavailable"}
                )

            robot_status = self.robot.get_status()

            # Определяем тип статуса и генерируем соответствующий отчет
            if status_type == 'status_full':
                response_text = self.sensor_reporter.get_full_status_text(
                    robot_status)
                logging.info("📊 Сгенерирован полный статус датчиков")

            elif status_type == 'status_quick':
                response_text = self.sensor_reporter.get_quick_status_text(
                    robot_status)
                logging.info("⚡ Сгенерирован быстрый статус")

            elif status_type == 'status_alerts':
                response_text = self.sensor_reporter.get_alerts_text(
                    robot_status)
                if not response_text.strip():
                    response_text = "Предупреждений нет, все системы работают нормально"
                logging.info("🚨 Проверены предупреждения системы")

            elif status_type == 'status_specific':
                # Определяем какие конкретные датчики запрашиваются
                user_text_lower = user_text.lower()

                if 'температур' in user_text_lower or 'влажност' in user_text_lower:
                    sections = ['environment']
                elif 'препятств' in user_text_lower or 'расстоян' in user_text_lower:
                    sections = ['distances']
                elif 'движени' in user_text_lower or 'скорост' in user_text_lower or 'энкодер' in user_text_lower:
                    sections = ['motion']
                elif 'камер' in user_text_lower:
                    sections = ['camera']
                elif 'роборук' in user_text_lower or 'рук' in user_text_lower:
                    sections = ['arm']
                elif 'наклон' in user_text_lower or 'ориентац' in user_text_lower:
                    sections = ['imu']
                else:
                    sections = None

                response_text = self.sensor_reporter.get_full_status_text(
                    robot_status, sections)
                logging.info(f"🎯 Сгенерирован специфичный статус: {sections}")

            else:
                # Fallback - быстрый статус
                response_text = self.sensor_reporter.get_quick_status_text(
                    robot_status)
                logging.info("📋 Сгенерирован стандартный статус")

            # TTS инструкции из ai_config.json
            tts_instructions = None
            if is_voice and self.config.get('tts_instructions', {}).get('status'):
                tts_instructions = self.config['tts_instructions']['status']

            return self._create_response(
                user_text=user_text,
                ai_response=response_text,
                intent=status_type,
                is_voice=is_voice,
                extra_data={
                    "status_type": status_type,
                    "sensor_data_available": self.robot is not None
                },
                tts_instructions=tts_instructions
            )

        except Exception as e:
            logging.error(f"❌ Ошибка генерации статуса датчиков: {e}")
            return self._create_response(
                user_text=user_text,
                ai_response="Не могу получить информацию о состоянии систем",
                intent='status_error',
                is_voice=is_voice,
                extra_data={"error": str(e)}
            )

    def _handle_chat_request(self, user_text, is_voice=False):
        """Обработка обычных диалоговых запросов"""
        if not self.speech:
            ai_response = "Модуль общения не активен"
        else:
            # Промпт из system_prompts.json
            system_prompt = self.system_prompts['chat']
            ai_response = self.speech.generate_response(
                user_text, system_prompt=system_prompt)

        # TTS инструкции из ai_config.json
        tts_instructions = None
        if is_voice and self.config.get('tts_instructions', {}).get('chat'):
            tts_instructions = self.config['tts_instructions']['chat']

        return self._create_response(
            user_text=user_text,
            ai_response=ai_response,
            intent='chat',
            is_voice=is_voice,
            tts_instructions=tts_instructions
        )

    def _create_response(self, user_text, ai_response, intent, is_voice=False, extra_data=None, tts_instructions=None):
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
                audio_file = self.speech.text_to_speech(
                    ai_response, instructions=tts_instructions)
                response["audio_file"] = audio_file

                # Воспроизводим сразу для статусных команд
                if intent.startswith('status'):
                    speech_success = self.speech.audio_manager.play_audio(
                        audio_file)
                    response["speech_played"] = speech_success

                    if speech_success:
                        logging.info("🔊 Статус датчиков озвучен")
                    else:
                        logging.warning("⚠️ Не удалось озвучить статус")

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

    def speak_sensor_status(self, status_type='quick'):
        """
        Прямой метод для озвучивания статуса датчиков
        status_type: 'quick', 'full', 'alerts', или список секций для специфичного статуса
        """
        try:
            if not self.speech or not self.speech.audio_manager:
                return {"error": "Аудио система недоступна"}

            if not self.robot:
                return {"error": "Контроллер робота недоступен"}

            robot_status = self.robot.get_status()

            # Генерируем текст статуса
            if status_type == 'quick':
                status_text = self.sensor_reporter.get_quick_status_text(
                    robot_status)
            elif status_type == 'full':
                status_text = self.sensor_reporter.get_full_status_text(
                    robot_status)
            elif status_type == 'alerts':
                status_text = self.sensor_reporter.get_alerts_text(
                    robot_status)
                if not status_text.strip():
                    status_text = "Предупреждений нет"
            elif isinstance(status_type, list):
                status_text = self.sensor_reporter.get_full_status_text(
                    robot_status, status_type)
            else:
                status_text = self.sensor_reporter.get_quick_status_text(
                    robot_status)

            if not status_text.strip():
                return {"error": "Нет данных для озвучивания"}

            # Синтезируем и воспроизводим
            tts_instructions = self.config.get(
                'tts_instructions', {}).get('status')
            audio_file = self.speech.text_to_speech(
                status_text, instructions=tts_instructions)

            if not audio_file:
                return {"error": "Ошибка синтеза речи"}

            speech_success = self.speech.audio_manager.play_audio(audio_file)

            result = {
                "success": True,
                "status_type": status_type,
                "status_text": status_text,
                "audio_file": audio_file,
                "speech_played": speech_success,
                "timestamp": datetime.now().isoformat()
            }

            if speech_success:
                logging.info(f"🔊 Статус датчиков '{status_type}' озвучен")
            else:
                logging.warning("⚠️ Не удалось воспроизвести статус")
                result["error"] = "Ошибка воспроизведения"

            return result

        except Exception as e:
            logging.error(f"❌ Ошибка озвучивания статуса: {e}")
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
                "sensor_reporter_available": self.sensor_reporter is not None,
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
