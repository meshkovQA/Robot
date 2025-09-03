import json
import logging
import time
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify

# Пробуем импортировать AI компоненты
try:
    from robot.ai_orchestrator import AIOrchestrater
    AI_AVAILABLE = True
    logging.info("✅ AI компоненты загружены")
except ImportError as e:
    AI_AVAILABLE = False
    logging.warning(f"⚠️ AI компоненты недоступны: {e}")
    AIOrchestrater = None


def create_ai_blueprint(robot_controller=None, camera=None, ai_detector=None):
    """
    Создание Blueprint для AI функций робота

    Args:
        robot_controller: Контроллер робота
        camera: Объект камеры 
        ai_detector: SimpleAIDetector для YOLO

    Returns:
        Blueprint: Flask blueprint с AI endpoints
    """
    bp = Blueprint('ai_api', __name__, url_prefix='/api/ai')

    # Инициализация AI оркестратора
    ai_orchestrator = None
    if AI_AVAILABLE:
        try:
            ai_orchestrator = AIOrchestrater(
                camera=camera,
                robot_controller=robot_controller,
                ai_detector=ai_detector
            )
            logging.info("🧠 AI Оркестратор инициализирован для API")
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации AI Оркестратора: {e}")
            ai_orchestrator = None

    # Вспомогательные функции
    def ok(data, message=None):
        """Успешный ответ"""
        response = {"success": True, "data": data}
        if message:
            response["message"] = message
        return jsonify(response)

    def err(error_message, status_code=400):
        """Ответ с ошибкой"""
        return jsonify({
            "success": False,
            "error": error_message,
            "timestamp": datetime.now().isoformat()
        }), status_code

    def require_ai():
        """Декоратор для проверки доступности AI"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                if not AI_AVAILABLE:
                    return err("AI модули не установлены или не доступны", 503)
                if not ai_orchestrator:
                    return err("AI система не инициализирована", 503)
                return func(*args, **kwargs)
            wrapper.__name__ = func.__name__
            return wrapper
        return decorator

    # ==================== ОСНОВНЫЕ AI ENDPOINTS ====================

    @bp.route('/status', methods=['GET'])
    def ai_status():
        """Получить статус AI системы"""
        try:
            base_status = {
                "ai_available": AI_AVAILABLE,
                "ai_initialized": ai_orchestrator is not None,
                "timestamp": datetime.now().isoformat()
            }

            if ai_orchestrator:
                ai_status_data = ai_orchestrator.get_status()
                base_status.update(ai_status_data)
            else:
                base_status.update({
                    "reason": "AI система не инициализирована",
                    "components": {
                        "speech": False,
                        "vision": False,
                        "audio_hardware": False
                    }
                })

            return ok(base_status)

        except Exception as e:
            return err(f"Ошибка получения статуса AI: {e}", 500)

    @bp.route('/smart_chat', methods=['POST'])
    @require_ai()
    def smart_chat():
        """
        Умный чат с автоматическим определением намерений

        Body:
        {
            "text": "Что ты видишь?",
            "include_context": false
        }
        """
        try:
            data = request.get_json() or {}
            text_message = data.get('text')

            if not text_message:
                return err("Поле 'text' обязательно")

            # Обрабатываем через умный роутер
            result = ai_orchestrator.smart_process_request(text=text_message)

            if result.get("success"):
                return ok(result)
            else:
                return err(result.get("error", "Неизвестная ошибка AI"))

        except Exception as e:
            logging.error(f"Ошибка умного чата: {e}")
            return err(f"Ошибка обработки запроса: {e}", 500)

    @bp.route('/voice_chat', methods=['POST'])
    @require_ai()
    def voice_chat():
        """
        Полный голосовой чат: микрофон → AI → динамики

        Body:
        {
            "duration": 5,
            "use_voice_detection": false
        }
        """
        try:
            data = request.get_json() or {}
            duration = data.get('duration', 5)
            use_voice_detection = data.get('use_voice_detection', False)

            # Валидация параметров
            if not isinstance(duration, (int, float)) or duration < 1 or duration > 30:
                return err("Длительность записи должна быть от 1 до 30 секунд")

            logging.info(f"🎤 Начинаю голосовой чат ({duration}с)")

            # Выполняем голосовой цикл
            if use_voice_detection:
                # Используем умную запись с детекцией голоса
                if hasattr(ai_orchestrator, 'speech') and ai_orchestrator.speech:
                    result = ai_orchestrator.speech.full_voice_interaction(
                        recording_duration=duration,
                        use_voice_detection=True
                    )
                else:
                    return err("Speech Handler не инициализирован")
            else:
                # Обычная запись фиксированной длительности
                result = ai_orchestrator.voice_chat(
                    recording_duration=duration)

            if result.get("success"):
                return ok(result)
            else:
                return err(result.get("error", "Ошибка голосового чата"))

        except Exception as e:
            logging.error(f"Ошибка голосового чата: {e}")
            return err(f"Ошибка голосового взаимодействия: {e}", 500)

    @bp.route('/describe', methods=['GET'])
    @require_ai()
    def describe_scene():
        """Описать что видит робот через камеру"""
        try:
            result = ai_orchestrator.describe_scene()

            if result.get("success"):
                return ok(result)
            else:
                return err(result.get("error", "Не удалось описать сцену"))

        except Exception as e:
            logging.error(f"Ошибка описания сцены: {e}")
            return err(f"Ошибка анализа изображения: {e}", 500)

    @bp.route('/scene_summary', methods=['GET'])
    @require_ai()
    def scene_summary():
        """Краткая сводка о том что видит робот"""
        try:
            if not (ai_orchestrator.vision):
                return err("Vision система не активна")

            result = ai_orchestrator.vision.get_scene_summary()

            if result.get("success"):
                return ok(result)
            else:
                return err(result.get("error", "Не удалось получить сводку"))

        except Exception as e:
            return err(f"Ошибка получения сводки: {e}", 500)

    # ==================== КОНФИГУРАЦИЯ И УПРАВЛЕНИЕ ====================

    @bp.route('/config', methods=['GET'])
    @require_ai()
    def get_config():
        """Получить текущую конфигурацию AI"""
        try:
            config = ai_orchestrator.config

            # Скрываем чувствительные данные
            safe_config = config.copy()
            if 'openai_api_key' in safe_config:
                key = safe_config['openai_api_key']
                safe_config['openai_api_key'] = f"{key[:8]}***" if key else None

            return ok(safe_config)

        except Exception as e:
            return err(f"Ошибка получения конфигурации: {e}", 500)

    @bp.route('/config', methods=['POST'])
    @require_ai()
    def update_config():
        """
        Обновить конфигурацию AI

        Body:
        {
            "speech_enabled": true,
            "vision_enabled": true,
            "voice": "alloy",
            "temperature": 0.7
        }
        """
        try:
            data = request.get_json() or {}

            if not data:
                return err("Пустые данные конфигурации")

            # Обновляем конфигурацию
            result = ai_orchestrator.update_config(data)

            if result.get("success"):
                return ok(result, "Конфигурация обновлена")
            else:
                return err(result.get("error", "Не удалось обновить конфигурацию"))

        except Exception as e:
            return err(f"Ошибка обновления конфигурации: {e}", 500)

    # ==================== АУДИО СИСТЕМА ====================

    @bp.route('/audio/devices', methods=['GET'])
    @require_ai()
    def audio_devices():
        """Получить список аудио устройств"""
        try:
            if not (ai_orchestrator.speech and ai_orchestrator.speech.audio_manager):
                return err("Аудио система не инициализирована")

            devices = ai_orchestrator.speech.audio_manager.get_audio_devices_info()

            if devices.get("error"):
                return err(devices["error"])
            else:
                return ok(devices)

        except Exception as e:
            return err(f"Ошибка получения аудио устройств: {e}", 500)

    @bp.route('/audio/test', methods=['POST'])
    @require_ai()
    def audio_test():
        """Тест аудио системы"""
        try:
            if not (ai_orchestrator.speech and ai_orchestrator.speech.audio_manager):
                return err("Аудио система не инициализирована")

            test_results = ai_orchestrator.speech.audio_manager.test_audio_system()
            return ok(test_results)

        except Exception as e:
            return err(f"Ошибка тестирования аудио: {e}", 500)

    @bp.route('/audio/record', methods=['POST'])
    @require_ai()
    def record_audio():
        """
        Записать аудио с микрофона

        Body:
        {
            "duration": 5,
            "transcribe": true
        }
        """
        try:
            if not (ai_orchestrator.speech and ai_orchestrator.speech.audio_manager):
                return err("Аудио система не инициализирована")

            data = request.get_json() or {}
            duration = data.get('duration', 5)
            transcribe = data.get('transcribe', False)

            # Записываем аудио
            audio_file = ai_orchestrator.speech.audio_manager.record_audio(
                duration)

            if not audio_file:
                return err("Не удалось записать аудио")

            result = {
                "audio_file": audio_file,
                "duration": duration,
                "file_size": Path(audio_file).stat().st_size
            }

            # Опционально расшифровываем
            if transcribe:
                text = ai_orchestrator.speech.transcribe_audio(audio_file)
                result["transcribed_text"] = text

            return ok(result)

        except Exception as e:
            return err(f"Ошибка записи аудио: {e}", 500)

    @bp.route('/audio/speak', methods=['POST'])
    @require_ai()
    def speak_text():
        """
        Синтез речи и воспроизведение

        Body:
        {
            "text": "Привет, это тест",
            "voice": "alloy",
            "play": true
        }
        """
        try:
            if not ai_orchestrator.speech:
                return err("Speech система не инициализирована")

            data = request.get_json() or {}
            text = data.get('text')
            voice = data.get('voice')
            play = data.get('play', True)

            if not text:
                return err("Поле 'text' обязательно")

            # Генерируем аудио файл
            audio_file = ai_orchestrator.speech.text_to_speech(text, voice)

            if not audio_file:
                return err("Не удалось создать аудио файл")

            result = {
                "audio_file": audio_file,
                "text": text,
                "voice": voice or ai_orchestrator.speech.tts_voice,
                "file_size": Path(audio_file).stat().st_size
            }

            # Опционально воспроизводим
            if play and ai_orchestrator.speech.audio_manager:
                play_success = ai_orchestrator.speech.audio_manager.play_audio(
                    audio_file)
                result["played"] = play_success

            return ok(result)

        except Exception as e:
            return err(f"Ошибка синтеза речи: {e}", 500)

    @bp.route('/voices', methods=['GET'])
    @require_ai()
    def get_voices():
        """Получить доступные голоса для TTS"""
        try:
            if not ai_orchestrator.speech:
                return err("Speech система не инициализирована")

            voices = ai_orchestrator.speech.get_available_voices()
            return ok(voices)

        except Exception as e:
            return err(f"Ошибка получения голосов: {e}", 500)

    # ==================== ИСТОРИЯ И СТАТИСТИКА ====================

    @bp.route('/conversations', methods=['GET'])
    @require_ai()
    def get_conversations():
        """Получить историю диалогов"""
        try:
            history = ai_orchestrator.get_conversation_history()
            return ok(history)

        except Exception as e:
            return err(f"Ошибка получения истории: {e}", 500)

    @bp.route('/conversations/stats', methods=['GET'])
    @require_ai()
    def conversation_stats():
        """Статистика диалогов"""
        try:
            if not ai_orchestrator.speech:
                return err("Speech система не инициализирована")

            stats = ai_orchestrator.speech.get_conversation_stats()
            return ok(stats)

        except Exception as e:
            return err(f"Ошибка получения статистики: {e}", 500)

    @bp.route('/conversations/clear', methods=['POST'])
    @require_ai()
    def clear_conversations():
        """Очистить историю диалогов"""
        try:
            result = ai_orchestrator.clear_conversation_history()

            if result.get("success"):
                return ok(result, "История диалогов очищена")
            else:
                return err(result.get("error", "Не удалось очистить историю"))

        except Exception as e:
            return err(f"Ошибка очистки истории: {e}", 500)

    @bp.route('/conversations/export', methods=['POST'])
    @require_ai()
    def export_conversations():
        """
        Экспорт истории диалогов

        Body:
        {
            "format": "json"  // "json" или "txt"
        }
        """
        try:
            if not ai_orchestrator.speech:
                return err("Speech система не инициализирована")

            data = request.get_json() or {}
            format_type = data.get('format', 'json')

            result = ai_orchestrator.speech.export_conversations(format_type)

            if result.get("success"):
                return ok(result)
            else:
                return err(result.get("error", "Ошибка экспорта"))

        except Exception as e:
            return err(f"Ошибка экспорта: {e}", 500)

    # ==================== ДИАГНОСТИКА И ТЕСТИРОВАНИЕ ====================

    @bp.route('/test/full', methods=['POST'])
    @require_ai()
    def full_system_test():
        """Полный тест AI системы"""
        try:
            results = {
                "speech_test": None,
                "vision_test": None,
                "overall_success": False,
                "timestamp": datetime.now().isoformat()
            }

            # Тест речевой системы
            if ai_orchestrator.speech:
                try:
                    speech_results = ai_orchestrator.speech.test_speech_system()
                    results["speech_test"] = speech_results
                except Exception as e:
                    results["speech_test"] = {"error": str(e)}

            # Тест системы зрения
            if ai_orchestrator.vision:
                try:
                    vision_results = ai_orchestrator.vision.test_vision_system()
                    results["vision_test"] = vision_results
                except Exception as e:
                    results["vision_test"] = {"error": str(e)}

            # Оценка общего результата
            speech_ok = results["speech_test"] and results["speech_test"].get(
                "overall_success", False)
            vision_ok = results["vision_test"] and results["vision_test"].get(
                "overall_success", False)

            # Хотя бы одна система работает
            results["overall_success"] = speech_ok or vision_ok
            results["systems_working"] = {
                "speech": speech_ok,
                "vision": vision_ok
            }

            return ok(results)

        except Exception as e:
            return err(f"Ошибка полного тестирования: {e}", 500)

    @bp.route('/test/quick', methods=['GET'])
    @require_ai()
    def quick_test():
        """Быстрый тест доступности AI компонентов"""
        try:
            test_results = {
                "ai_orchestrator": ai_orchestrator is not None,
                "speech_handler": ai_orchestrator.speech is not None if ai_orchestrator else False,
                "vision_analyzer": ai_orchestrator.vision is not None if ai_orchestrator else False,
                "audio_manager": (
                    ai_orchestrator.speech.audio_manager is not None
                    if ai_orchestrator and ai_orchestrator.speech else False
                ),
                "camera_connected": camera is not None,
                "ai_detector_connected": ai_detector is not None,
                "timestamp": datetime.now().isoformat()
            }

            # Подсчитаем работающие компоненты
            working_components = sum(
                test_results[key] for key in test_results if isinstance(test_results[key], bool))
            total_components = 6

            test_results["score"] = f"{working_components}/{total_components}"
            # Минимум половина работает
            test_results["success"] = working_components >= 3

            return ok(test_results)

        except Exception as e:
            return err(f"Ошибка быстрого теста: {e}", 500)

    # ==================== ИНФОРМАЦИОННЫЕ ENDPOINTS ====================

    @bp.route('/info', methods=['GET'])
    def ai_info():
        """Общая информация о AI системе"""
        return ok({
            "ai_system": "Robot AI Assistant",
            "version": "1.0.0",
            "components": {
                "speech": "OpenAI Whisper + GPT + TTS",
                "vision": "YOLO8 + GPT-4V",
                "orchestrator": "Smart Intent Router"
            },
            "capabilities": [
                "Голосовое общение на русском языке",
                "Описание визуальной сцены",
                "Умное определение намерений пользователя",
                "Контекстные диалоги",
                "Интеграция с датчиками робота"
            ],
            "ai_available": AI_AVAILABLE,
            "timestamp": datetime.now().isoformat()
        })

    # Возвращаем blueprint
    return bp
