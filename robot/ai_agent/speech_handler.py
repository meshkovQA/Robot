import json
import logging
import openai
from datetime import datetime
from pathlib import Path
import time


class SpeechHandler:
    """
    Обработчик речи для робота
    Интеграция OpenAI Whisper STT, GPT для диалогов, OpenAI TTS
    """

    def __init__(self, config):
        self.config = config
        self.api_key = config.get('openai_api_key')

        if not self.api_key:
            raise ValueError("OpenAI API key не найден в конфигурации")

        openai.api_key = self.api_key

        # Настройки для OpenAI
        self.model = config.get('model', 'gpt-4o-mini')
        self.max_tokens = config.get('max_tokens', 1500)
        self.temperature = config.get('temperature', 0.7)

        # Настройки речи
        self.whisper_model = config.get('whisper_model', 'whisper-1')
        self.tts_model = config.get('tts_model', 'tts-1')
        # alloy, echo, fable, onyx, nova, shimmer
        self.tts_voice = config.get('voice', 'alloy')

        # История диалогов
        self.conversation_file = Path("data/conversations.json")
        self.conversation_history = self._load_conversations()

        # AudioManager будет подключен извне
        self.audio_manager = None

        # Системные промпты
        self.system_prompts = {
            'default': "Ты умный робот-помощник. Отвечай кратко и дружелюбно на русском языке. Ты можешь видеть через камеру, слышать через микрофон и двигаться по дому.",
            'vision': "Ты робот с камерой. Анализируй изображения и описывай что видишь простым языком.",
            'status': "Ты робот-диагност. Анализируй техническую информацию и отвечай понятно о состоянии систем.",
            'context': "Ты умный робот-аналитик. Обрабатывай всю доступную информацию и давай комплексные, но понятные ответы."
        }

        logging.info("🎤 SpeechHandler инициализирован")

    def _load_conversations(self):
        """Загрузить историю диалогов"""
        try:
            if self.conversation_file.exists():
                with open(self.conversation_file, 'r', encoding='utf-8') as f:
                    conversations = json.load(f)
                logging.info(
                    f"📖 Загружена история: {len(conversations)} записей")
                return conversations
            return []
        except Exception as e:
            logging.error(f"❌ Ошибка загрузки диалогов: {e}")
            return []

    def _save_conversations(self):
        """Сохранить историю диалогов"""
        try:
            self.conversation_file.parent.mkdir(exist_ok=True)
            with open(self.conversation_file, 'w', encoding='utf-8') as f:
                json.dump(self.conversation_history, f,
                          ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"❌ Ошибка сохранения диалогов: {e}")

    def transcribe_audio(self, audio_file_path):
        """Распознавание речи через OpenAI Whisper"""
        if not Path(audio_file_path).exists():
            logging.error(f"❌ Аудио файл не найден: {audio_file_path}")
            return None

        try:
            logging.info(f"🎤→📝 Распознавание речи: {audio_file_path}")

            with open(audio_file_path, 'rb') as audio_file:
                response = openai.audio.transcriptions.create(
                    model=self.whisper_model,
                    file=audio_file,
                    language="ru",  # Форсируем русский язык
                    response_format="text",
                    temperature=0.0  # Для более стабильного распознавания
                )

            # OpenAI возвращает текст напрямую при response_format="text"
            if isinstance(response, str):
                transcribed_text = response.strip()
            else:
                transcribed_text = response.text.strip()

            if transcribed_text:
                logging.info(f"✅ Распознано: '{transcribed_text}'")
                return transcribed_text
            else:
                logging.warning("⚠️ Пустой результат распознавания")
                return None

        except Exception as e:
            logging.error(f"❌ Ошибка Whisper: {e}")
            return None

    def generate_response(self, user_message, intent='default', context_data=None):
        """Генерация ответа через OpenAI GPT"""
        try:
            # Выбираем системный промпт по типу запроса
            system_prompt = self.system_prompts.get(
                intent, self.system_prompts['default'])

            # Собираем сообщения для OpenAI
            messages = [
                {"role": "system", "content": system_prompt}
            ]

            # Добавляем контекст если есть
            if context_data:
                context_message = f"Дополнительная информация: {json.dumps(context_data, ensure_ascii=False)}"
                messages.append({"role": "system", "content": context_message})

            # Добавляем историю диалогов (последние 5 сообщений)
            recent_conversations = self.conversation_history[-5:] if self.conversation_history else [
            ]
            for conv in recent_conversations:
                if conv.get('user_message'):
                    messages.append(
                        {"role": "user", "content": conv['user_message']})
                if conv.get('ai_response'):
                    messages.append(
                        {"role": "assistant", "content": conv['ai_response']})

            # Добавляем текущее сообщение пользователя
            messages.append({"role": "user", "content": user_message})

            logging.info(
                f"🧠 Генерация ответа ({intent}): '{user_message[:50]}...'")

            # Отправляем запрос в OpenAI
            response = openai.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                frequency_penalty=0.1,  # Снижаем повторения
                presence_penalty=0.1    # Поощряем новые темы
            )

            ai_response = response.choices[0].message.content.strip()

            if ai_response:
                logging.info(f"✅ Сгенерирован ответ: '{ai_response[:100]}...'")
                return ai_response
            else:
                fallback_response = "Извини, у меня проблемы с пониманием. Попробуй перефразировать вопрос."
                logging.warning("⚠️ Пустой ответ от GPT, использую fallback")
                return fallback_response

        except Exception as e:
            logging.error(f"❌ Ошибка генерации GPT: {e}")

            # Fallback ответы в зависимости от типа запроса
            fallback_responses = {
                'vision': "Извини, не могу сейчас проанализировать изображение.",
                'status': "Не могу получить информацию о системах в данный момент.",
                'action': "Команда понята, но сейчас не могу её выполнить.",
                'context': "Не могу провести полный анализ ситуации прямо сейчас.",
                'default': "Извини, у меня технические проблемы. Попробуй чуть позже."
            }

            return fallback_responses.get(intent, fallback_responses['default'])

    def text_to_speech(self, text, voice=None):
        """Синтез речи через OpenAI TTS"""
        if not text or not text.strip():
            logging.warning("⚠️ Пустой текст для синтеза")
            return None

        try:
            # Очищаем текст от лишних символов
            clean_text = text.strip()

            # Ограничиваем длину текста (OpenAI TTS имеет лимиты)
            if len(clean_text) > 4000:
                clean_text = clean_text[:4000] + "..."
                logging.warning(f"⚠️ Текст обрезан до 4000 символов")

            logging.info(f"📝→🔊 Синтез речи: '{clean_text[:50]}...'")

            response = openai.audio.speech.create(
                model=self.tts_model,
                voice=voice or self.tts_voice,
                input=clean_text,
                response_format="mp3",  # MP3 более компактный
                speed=1.0  # Нормальная скорость
            )

            # Сохраняем в файл
            timestamp = int(time.time())
            audio_file = Path(f"data/temp/tts_response_{timestamp}.mp3")
            audio_file.parent.mkdir(parents=True, exist_ok=True)

            # Записываем аудио данные
            with open(audio_file, 'wb') as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)

            # Проверяем размер файла
            file_size = audio_file.stat().st_size
            if file_size < 1000:
                logging.error(
                    f"❌ Подозрительно маленький TTS файл: {file_size} байт")
                return None

            logging.info(f"✅ TTS файл создан: {audio_file} ({file_size} байт)")
            return str(audio_file)

        except Exception as e:
            logging.error(f"❌ Ошибка синтеза TTS: {e}")
            return None

    def process_conversation(self, audio_file=None, text_message=None, intent='default', context_data=None):
        """
        Полный цикл обработки диалога: 
        аудио → текст → GPT → TTS (без воспроизведения)
        """
        try:
            # 1. Получаем текст пользователя
            if audio_file:
                user_text = self.transcribe_audio(audio_file)
                if not user_text:
                    return {"error": "Не удалось распознать речь"}
            elif text_message:
                user_text = text_message
            else:
                return {"error": "Нет входных данных"}

            # 2. Генерируем ответ
            ai_response = self.generate_response(
                user_message=user_text,
                intent=intent,
                context_data=context_data
            )

            # 3. Синтезируем речь
            audio_response_file = self.text_to_speech(ai_response)

            # 4. Сохраняем в историю
            conversation_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_message": user_text,
                "ai_response": ai_response,
                "intent": intent,
                "audio_file": audio_response_file,
                "has_context": context_data is not None
            }

            self.conversation_history.append(conversation_entry)

            # Ограничиваем размер истории
            max_length = self.config.get('max_conversation_length', 10)
            if len(self.conversation_history) > max_length:
                self.conversation_history = self.conversation_history[-max_length:]

            # Сохраняем историю
            self._save_conversations()

            result = {
                "success": True,
                "user_text": user_text,
                "ai_response": ai_response,
                "audio_file": audio_response_file,
                "intent": intent,
                "timestamp": conversation_entry["timestamp"]
            }

            logging.info(
                f"✅ Диалог обработан: '{user_text}' → '{ai_response[:50]}...'")
            return result

        except Exception as e:
            logging.error(f"❌ Ошибка обработки диалога: {e}")
            return {"error": str(e)}

    # ===== ИНТЕГРАЦИЯ С AUDIO MANAGER =====

    def record_and_transcribe(self, duration=5, use_voice_detection=False):
        """Записать с физического микрофона и распознать речь"""
        if not self.audio_manager:
            logging.error("❌ AudioManager не подключен")
            return None

        try:
            # Выбираем метод записи
            if use_voice_detection:
                logging.info("🎤 Запись с детекцией голоса...")
                audio_file = self.audio_manager.record_with_voice_detection(
                    max_duration=duration,
                    silence_timeout=2.0
                )
            else:
                logging.info(f"🎤 Запись {duration} секунд...")
                audio_file = self.audio_manager.record_audio(duration)

            if not audio_file:
                logging.warning("⚠️ Не удалось записать аудио")
                return None

            # Распознаем записанное
            text = self.transcribe_audio(audio_file)

            # Удаляем временный файл
            try:
                Path(audio_file).unlink(missing_ok=True)
            except:
                pass

            return text

        except Exception as e:
            logging.error(f"❌ Ошибка записи и распознавания: {e}")
            return None

    def speak_response(self, text, voice=None):
        """Синтез речи и воспроизведение через физические динамики"""
        if not self.audio_manager:
            logging.error("❌ AudioManager не подключен")
            return False

        try:
            # Генерируем аудио файл
            audio_file = self.text_to_speech(text, voice)
            if not audio_file:
                return False

            # Воспроизводим через динамики
            success = self.audio_manager.play_audio(audio_file)

            if success:
                logging.info(f"✅ Речь воспроизведена: '{text[:50]}...'")
            else:
                logging.error("❌ Не удалось воспроизвести речь")

            # Опционально: удаляем временный файл
            # Path(audio_file).unlink(missing_ok=True)

            return success

        except Exception as e:
            logging.error(f"❌ Ошибка воспроизведения речи: {e}")
            return False

    def full_voice_interaction(self, recording_duration=5, use_voice_detection=False,
                               intent='default', context_data=None):
        """
        Полный цикл голосового взаимодействия с физическими устройствами:
        микрофон → Whisper → GPT → TTS → динамики
        """
        if not self.audio_manager:
            return {"error": "AudioManager не подключен"}

        try:
            logging.info("🎤🤖🔊 Начинаю полный голосовой цикл...")

            # 1. Записываем с микрофона
            user_text = self.record_and_transcribe(
                duration=recording_duration,
                use_voice_detection=use_voice_detection
            )

            if not user_text:
                return {"error": "Не удалось записать или распознать речь"}

            logging.info(f"👤 Пользователь сказал: '{user_text}'")

            # 2. Обрабатываем через AI
            response = self.process_conversation(
                text_message=user_text,
                intent=intent,
                context_data=context_data
            )

            if not response.get("success"):
                return response

            # 3. Воспроизводим ответ
            if response.get("audio_file"):
                speech_success = self.audio_manager.play_audio(
                    response["audio_file"])
                response["speech_played"] = speech_success

                if speech_success:
                    logging.info(
                        f"🤖 Робот ответил: '{response['ai_response']}'")
                else:
                    logging.warning("⚠️ Не удалось воспроизвести ответ")

            return response

        except Exception as e:
            logging.error(f"❌ Ошибка полного голосового взаимодействия: {e}")
            return {"error": str(e)}

    # ===== УПРАВЛЕНИЕ И ДИАГНОСТИКА =====

    def get_conversation_stats(self):
        """Статистика диалогов"""
        if not self.conversation_history:
            return {"total": 0, "today": 0}

        try:
            total = len(self.conversation_history)
            today = 0

            today_date = datetime.now().date()
            for conv in self.conversation_history:
                try:
                    conv_date = datetime.fromisoformat(
                        conv["timestamp"]).date()
                    if conv_date == today_date:
                        today += 1
                except:
                    continue

            # Статистика по типам намерений
            intent_stats = {}
            for conv in self.conversation_history:
                intent = conv.get('intent', 'unknown')
                intent_stats[intent] = intent_stats.get(intent, 0) + 1

            return {
                "total": total,
                "today": today,
                "intent_distribution": intent_stats,
                "last_conversation": self.conversation_history[-1]["timestamp"] if self.conversation_history else None
            }

        except Exception as e:
            logging.error(f"Ошибка получения статистики: {e}")
            return {"error": str(e)}

    def clear_conversation_history(self):
        """Очистить историю диалогов"""
        try:
            self.conversation_history = []
            self._save_conversations()
            logging.info("🗑️ История диалогов очищена")
            return {"success": True, "message": "История очищена"}
        except Exception as e:
            logging.error(f"Ошибка очистки истории: {e}")
            return {"error": str(e)}

    def export_conversations(self, format='json'):
        """Экспорт диалогов"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if format.lower() == 'json':
                export_file = Path(
                    f"data/conversations_export_{timestamp}.json")
                with open(export_file, 'w', encoding='utf-8') as f:
                    json.dump(self.conversation_history, f,
                              ensure_ascii=False, indent=2)

            elif format.lower() == 'txt':
                export_file = Path(
                    f"data/conversations_export_{timestamp}.txt")
                with open(export_file, 'w', encoding='utf-8') as f:
                    for conv in self.conversation_history:
                        f.write(f"[{conv.get('timestamp', 'Unknown')}]\n")
                        f.write(
                            f"Пользователь: {conv.get('user_message', '')}\n")
                        f.write(f"Робот: {conv.get('ai_response', '')}\n")
                        f.write(f"Тип: {conv.get('intent', 'unknown')}\n")
                        f.write("-" * 50 + "\n\n")

            else:
                return {"error": "Поддерживаются форматы: json, txt"}

            return {
                "success": True,
                "file": str(export_file),
                "entries": len(self.conversation_history)
            }

        except Exception as e:
            return {"error": str(e)}

    def test_speech_system(self):
        """Тест речевой системы"""
        results = {
            "openai_api_test": False,
            "whisper_test": False,
            "gpt_test": False,
            "tts_test": False,
            "audio_hardware_test": False,
            "details": []
        }

        try:
            # 1. Тест подключения к OpenAI API
            try:
                response = openai.models.list()
                results["openai_api_test"] = True
                results["details"].append("✅ OpenAI API подключение работает")
            except Exception as e:
                results["details"].append(f"❌ OpenAI API: {e}")

            # 2. Тест GPT
            if results["openai_api_test"]:
                try:
                    test_response = self.generate_response(
                        "Привет, это тест", intent='default')
                    if test_response and len(test_response) > 5:
                        results["gpt_test"] = True
                        results["details"].append("✅ GPT генерация работает")
                    else:
                        results["details"].append(
                            "❌ GPT: пустой или короткий ответ")
                except Exception as e:
                    results["details"].append(f"❌ GPT: {e}")

            # 3. Тест TTS
            if results["openai_api_test"]:
                try:
                    test_audio = self.text_to_speech("Тест синтеза речи")
                    if test_audio and Path(test_audio).exists():
                        file_size = Path(test_audio).stat().st_size
                        if file_size > 1000:
                            results["tts_test"] = True
                            results["details"].append(
                                f"✅ TTS работает ({file_size} байт)")
                        else:
                            results["details"].append(
                                f"❌ TTS: слишком маленький файл ({file_size} байт)")

                        # Удаляем тестовый файл
                        Path(test_audio).unlink(missing_ok=True)
                    else:
                        results["details"].append(
                            "❌ TTS: не удалось создать файл")
                except Exception as e:
                    results["details"].append(f"❌ TTS: {e}")

            # 4. Тест аудио hardware
            if self.audio_manager:
                try:
                    audio_test = self.audio_manager.test_audio_system()
                    if audio_test.get("overall_success"):
                        results["audio_hardware_test"] = True
                        results["details"].append("✅ Аудио hardware работает")
                    else:
                        results["details"].append(
                            "⚠️ Проблемы с аудио hardware")
                        results["details"].extend(
                            audio_test.get("details", []))
                except Exception as e:
                    results["details"].append(f"❌ Аудио hardware тест: {e}")
            else:
                results["details"].append("⚠️ AudioManager не подключен")

            # 5. Общий результат
            total_tests = 4  # Исключаем Whisper, так как нужен аудио файл
            passed_tests = sum([
                results["openai_api_test"],
                results["gpt_test"],
                results["tts_test"],
                results["audio_hardware_test"]
            ])

            results["overall_success"] = passed_tests >= 3
            results["score"] = f"{passed_tests}/{total_tests}"

            logging.info(f"🧪 Тест речевой системы: {results['score']}")

            return results

        except Exception as e:
            logging.error(f"❌ Критическая ошибка тестирования: {e}")
            results["details"].append(f"Критическая ошибка: {e}")
            return results

    def get_available_voices(self):
        """Получить список доступных голосов TTS"""
        return {
            "voices": [
                {"id": "alloy", "name": "Alloy",
                    "description": "Сбалансированный голос"},
                {"id": "echo", "name": "Echo", "description": "Мужской голос"},
                {"id": "fable", "name": "Fable", "description": "Британский акцент"},
                {"id": "onyx", "name": "Onyx",
                    "description": "Глубокий мужской голос"},
                {"id": "nova", "name": "Nova",
                    "description": "Молодой женский голос"},
                {"id": "shimmer", "name": "Shimmer",
                    "description": "Мягкий женский голос"}
            ],
            "current_voice": self.tts_voice,
            "models": ["tts-1", "tts-1-hd"]
        }

    def set_voice(self, voice_id):
        """Установить голос для TTS"""
        available_voices = ["alloy", "echo",
                            "fable", "onyx", "nova", "shimmer"]

        if voice_id in available_voices:
            self.tts_voice = voice_id
            logging.info(f"🔊 Голос изменен на: {voice_id}")
            return {"success": True, "voice": voice_id}
        else:
            return {"error": f"Неизвестный голос. Доступные: {available_voices}"}

    def get_status(self):
        """Получить статус речевой системы"""
        return {
            "speech_handler": {
                "initialized": True,
                "api_key_configured": bool(self.api_key),
                "model": self.model,
                "tts_voice": self.tts_voice,
                "conversation_entries": len(self.conversation_history),
                "audio_manager_connected": self.audio_manager is not None,
                "last_conversation": (
                    self.conversation_history[-1]["timestamp"]
                    if self.conversation_history else None
                )
            }
        }
