# robot/ai_agent/speech_handler.py

import json
import logging
from openai import OpenAI
import os
from datetime import datetime
from pathlib import Path
import time
from .yandex_stt_client import YandexSTTClient


class SpeechHandler:
    """
    Обработчик речи для робота
    Интеграция OpenAI Whisper STT, GPT для диалогов, OpenAI TTS
    """

    def __init__(self, config):
        self.config = config

        self._provider = (self.config.get("speech", {})
                          or {}).get("provider", "openai")

        yc = (self.config.get("speech", {}) or {}).get("yandex", {}) or {}
        self._yandex_client = None

        try:
            if self._provider == "yandex":
                auth = (yc.get("auth") or "api_key").lower()
                api_key = os.getenv(
                    "YANDEX_API_KEY") if auth == "api_key" else None
                iam_token = yc.get("iam_token") if auth == "iam" else None
                self._yandex_client = YandexSTTClient(
                    api_key=api_key,
                    iam_token=iam_token,
                    sample_rate=yc.get("sample_rate", 48000),
                    channels=yc.get("channels", 1),
                    profanity_filter=bool(yc.get("profanity_filter", True)),
                    model=yc.get("model", "general"),
                )
                logging.info("Yandex STT client initialized")
        except Exception as e:
            logging.error(f"Yandex STT init error: {e}")

        # Получаем ключ только из environment переменной
        self.api_key = os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError(
                "OpenAI API key не найден в переменной окружения OPENAI_API_KEY")

        # Создаем клиент с новым API
        self.client = OpenAI(api_key=self.api_key)

        # Настройки для OpenAI (остается как есть)
        self.model = config.get('model', 'gpt-4o-mini')
        self.max_tokens = config.get('max_tokens', 1500)
        self.temperature = config.get('temperature', 0.7)

        # Настройки речи (остается как есть)
        self.whisper_model = config.get('whisper_model', 'whisper-1')
        self.tts_model = config.get('tts_model', 'tts-1')
        self.tts_voice = config.get('voice', 'alloy')

        # История диалогов (остается как есть)
        self.conversation_file = Path("data/conversations.json")
        self.conversation_history = self._load_conversations()

        # AudioManager будет подключен извне
        self.audio_manager = None

        self._load_system_prompts()

        logging.info("🎤 SpeechHandler инициализирован с новым OpenAI API")

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

    def _load_system_prompts(self):
        """Загрузить системные промпты из JSON файла"""
        prompts_file = Path("data/system_prompts.json")

        with open(prompts_file, 'r', encoding='utf-8') as f:
            self.system_prompts = json.load(f)

        logging.info(
            f"📄 SpeechHandler загрузил {len(self.system_prompts)} промптов")

    def transcribe_audio(self, wav_path: str) -> str | None:
        logging.info(f"STT provider={self._provider} file={wav_path}")
        try:
            if self._provider == "yandex" and self._yandex_client:
                text = self._yandex_client.recognize_wav(wav_path) or None
                if text:
                    logging.info(f"✅ Распознано (Yandex): '{text}'")
                return text
            # --- фолбэк на OpenAI:
            text = self._transcribe_with_openai(wav_path)
            if text:
                logging.info(f"✅ Распознано (OpenAI): '{text}'")
            return text
        except Exception as e:
            logging.error(
                f"STT error ({self._provider}). Fallback to OpenAI. Reason: {e}")
            try:
                text = self._transcribe_with_openai(wav_path)
                if text:
                    logging.info(f"✅ Распознано (OpenAI фолбэк): '{text}'")
                return text
            except Exception as e2:
                logging.error(f"OpenAI STT failed: {e2}")
                return None

    def transcribe_with_openai(self, audio_file_path):
        """Распознавание речи через OpenAI Whisper"""
        if not Path(audio_file_path).exists():
            logging.error(f"❌ Аудио файл не найден: {audio_file_path}")
            return None

        try:
            logging.info(f"🎤→📝 Распознавание речи: {audio_file_path}")

            with open(audio_file_path, 'rb') as audio_file:
                response = self.client.audio.transcriptions.create(
                    model=self.whisper_model,  # Теперь это gpt-4o-transcribe
                    file=audio_file,
                    language="ru",  # Форсируем русский язык
                    response_format="text",
                    temperature=0.0,  # Для более стабильного распознавания
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

    def generate_response(self, user_message, context_data=None, system_prompt=None, intent=None):
        """Генерация ответа через OpenAI GPT"""

        system_prompt = system_prompt or self.system_prompts['default']

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

        # Отправляем запрос в OpenAI
        response = self.client.chat.completions.create(
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

    def text_to_speech(self, text, voice=None, instructions=None):
        """Синтез речи через OpenAI TTS"""
        if not text or not text.strip():
            logging.warning("⚠️ Пустой текст для синтеза")
            return None

        try:
            # Очищаем текст от лишних символов
            clean_text = text.strip()

            # Получаем инструкции для TTS
            tts_instructions = instructions
            if tts_instructions is None:
                tts_instructions = self.config.get('tts_instructions')
            if isinstance(tts_instructions, dict):
                tts_instructions = tts_instructions.get('default', "")

            if not isinstance(tts_instructions, str):
                tts_instructions = ""

            logging.info(
                f"📝→🔊 Синтез речи (новая модель): '{clean_text[:50]}...'")

            response = self.client.audio.speech.create(
                model=self.tts_model,  # Теперь это gpt-4o-mini-tts
                voice=voice or self.tts_voice,
                input=clean_text,
                response_format="mp3",
                speed=1.0,
                # НОВАЯ ФИЧА: инструкции для стиля речи
                instructions=tts_instructions
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

    def set_voice(self, voice_id):
        """Установить голос для TTS"""
        available_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer",
                            "marin", "cedar"]  # ←← ДОБАВЛЕНЫ НОВЫЕ ГОЛОСА

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

    def set_tts_instructions(self, instructions):
        """Установить инструкции для стиля речи TTS"""
        self.config['tts_instructions'] = instructions
        logging.info(f"🎭 Инструкции TTS обновлены: '{instructions[:50]}...'")
        return {"success": True, "instructions": instructions}
