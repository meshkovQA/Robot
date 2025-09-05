# robot/ai_agent/wake_word_service.py

import threading
import time
import logging
from pathlib import Path
import re
from .audio_manager import AudioManager
from .speech_handler import SpeechHandler
from robot.controllers.rgb_controller import RGBController
import subprocess
import tempfile
import wave
import numpy as np


class WakeWordService:
    """
    Сервис голосовой активации для робота Винди
    Постоянно слушает микрофон и активируется на слово "Винди"
    """

    def __init__(self, config, ai_orchestrator=None):
        self.config = config
        self.ai_orchestrator = ai_orchestrator

        # Настройки wake word
        self.wake_words = config.get('wake_words', ['винди', 'windy', 'венди'])
        self.activation_timeout = config.get(
            'activation_timeout', 10)  # секунд на команду
        self.sensitivity_threshold = config.get('sensitivity_threshold', 800)

        # Состояние сервиса
        self.is_running = False
        self.is_listening = False
        self.service_thread = None

        # Компоненты
        self.audio_manager = None
        self.speech_handler = None

        # Инициализация компонентов
        self._initialize_components()

        logging.info("🎤 WakeWordService инициализирован")
        logging.info(f"👂 Слова активации: {', '.join(self.wake_words)}")

    def _initialize_components(self):
        """Инициализация аудио компонентов"""
        try:
            # Инициализируем AudioManager
            self.audio_manager = AudioManager(self.config.get('audio', {}))

            # Инициализируем SpeechHandler
            self.speech_handler = SpeechHandler(self.config)
            self.speech_handler.audio_manager = self.audio_manager
            logging.info("✅ WakeWord компоненты готовы")

        except Exception as e:
            logging.error(f"❌ Ошибка инициализации WakeWord компонентов: {e}")

    def start_service(self):
        """Запуск сервиса голосовой активации"""
        if self.is_running:
            logging.warning("⚠️ WakeWord сервис уже запущен")
            return False

        if not self.audio_manager:
            logging.error("❌ AudioManager не инициализирован")
            return False

        if not self.speech_handler:
            logging.error(
                "❌ SpeechHandler не инициализирован")
            return False

        self.is_running = True
        self.service_thread = threading.Thread(
            target=self._wake_word_loop,
            daemon=True
        )
        self.service_thread.start()

        logging.info("🚀 WakeWord сервис запущен")
        logging.info(
            f"👂 Слушаю активационные слова: {', '.join(self.wake_words)}")
        return True

    def stop_service(self):
        """Остановка сервиса голосовой активации"""
        if not self.is_running:
            return

        self.is_running = False
        self.is_listening = False

        if self.audio_manager:
            self.audio_manager.stop_continuous_recording()

        if self.service_thread and self.service_thread.is_alive():
            self.service_thread.join(timeout=5)

        logging.info("⏹️ WakeWord сервис остановлен")

    def _wake_word_loop(self):
        """Основной цикл прослушивания wake word через arecord"""
        try:

            logging.info("🔄 НАЧИНАЮ _wake_word_loop")

            while self.is_running:
                try:
                    logging.info("🔄 Вошел в основной while цикл")
                    self.is_listening = True
                    logging.info("🎤 Начата непрерывная запись (через arecord)")

                    # Буфер для накопления аудио
                    audio_buffer = []
                    buffer_duration = 0
                    max_buffer_duration = 3.0  # максимум 3 секунды в буфере
                    chunk_duration = 1  # записываем по 1 секунде

                    while self.is_running and self.is_listening:
                        logging.info("🔄 Цикл прослушивания wake word...")
                       # Записываем короткие отрезки (1 секунды) для обнаружения wake word
                        temp_file = f"/tmp/wake_chunk_{int(time.time() * 1000)}.wav"

                        cmd = [
                            'arecord',
                            # PLUGHW!
                            '-D', f'plughw:{self.audio_manager.microphone_index},0',
                            '-r', str(self.audio_manager.sample_rate),
                            '-c', str(self.audio_manager.channels),
                            '-f', 'S16_LE',
                            '-d', str(chunk_duration),
                            temp_file
                        ]
                        logging.info(f"🔄 Запускаю команду: {' '.join(cmd)}")

                        try:

                            result = subprocess.run(
                                cmd, capture_output=True, timeout=1)

                            logging.info(
                                f"🔄 Результат выполнения команды: {result}")

                            if result.returncode == 0 and Path(temp_file).exists():
                                file_size = Path(temp_file).stat().st_size

                                if file_size > 500:  # Минимальный размер для 0.5 сек
                                    # Добавляем в буфер
                                    audio_buffer.append(temp_file)
                                    buffer_duration += chunk_duration

                                    # Удаляем старые файлы если буфер переполнен
                                    while buffer_duration > max_buffer_duration:
                                        old_file = audio_buffer.pop(0)
                                        Path(old_file).unlink(missing_ok=True)
                                        buffer_duration -= chunk_duration

                                    # Объединяем буфер и проверяем на wake word
                                    self._process_audio_buffer(
                                        audio_buffer.copy())
                                else:
                                    Path(temp_file).unlink(missing_ok=True)
                            else:
                                Path(temp_file).unlink(missing_ok=True)

                        except subprocess.TimeoutExpired:
                            Path(temp_file).unlink(missing_ok=True)
                            continue
                        except Exception as e:
                            logging.error(f"Ошибка записи chunk: {e}")
                            Path(temp_file).unlink(missing_ok=True)
                            time.sleep(0.1)

                    # Очищаем буфер при выходе
                    for temp_file in audio_buffer:
                        Path(temp_file).unlink(missing_ok=True)

                except Exception as e:
                    logging.error(f"❌ Ошибка в цикле прослушивания: {e}")
                    time.sleep(5)

        finally:
            logging.info("🔚 Цикл WakeWord завершен")

    def _check_audio_has_speech(self, audio_file):
        """Проверка наличия речи в аудиофайле по уровню громкости"""
        try:
            import wave
            import numpy as np

            with wave.open(audio_file, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
                audio_data = np.frombuffer(frames, dtype=np.int16)

                # Вычисляем среднюю громкость
                volume = np.abs(audio_data).mean()
                max_volume = np.abs(audio_data).max()

                # Проверяем пороги
                min_avg_volume = 100   # Минимальная средняя громкость
                min_max_volume = 1000  # Минимальная пиковая громкость

                has_speech = volume > min_avg_volume and max_volume > min_max_volume

                logging.debug(
                    f"🔊 Аудио проверка: avg={volume:.1f}, max={max_volume:.1f}, speech={has_speech}")

                return has_speech

        except Exception as e:
            logging.error(f"❌ Ошибка проверки аудио: {e}")
            return True  # В случае ошибки пропускаем проверку

    def _contains_wake_word(self, text):
        """Проверка текста на наличие wake word"""
        # Убираем знаки препинания и лишние пробелы
        clean_text = re.sub(r'[^\w\s]', '', text).strip()
        words = clean_text.split()

        # Ищем wake word в начале фразы (первые 3 слова)
        first_words = words[:3] if len(words) >= 3 else words

        for wake_word in self.wake_words:
            for word in first_words:
                if wake_word in word or word in wake_word:
                    return True

        # Альтернативная проверка - wake word в любом месте фразы
        for wake_word in self.wake_words:
            if wake_word in clean_text:
                return True

        return False

    def _handle_activation(self, activation_text):
        """Обработка активации - переход в режим диалога"""
        try:
            # Временно останавливаем прослушивание wake word
            self.is_listening = False

            # Извлекаем команду после wake word
            command = self._extract_command_after_wake_word(activation_text)

            if command:
                # Если есть команда сразу после "Винди" - выполняем её
                logging.info(f"🎯 Выполняю команду: '{command}'")
                self._process_voice_command(command)
            else:
                # Если только "Винди" - переходим в режим ожидания команды
                logging.info("👂 Слушаю команду...")
                self._enter_command_mode()

        except Exception as e:
            logging.error(f"❌ Ошибка обработки активации: {e}")
        finally:
            # Возобновляем прослушивание wake word через 3 секунды
            time.sleep(3)
            self.is_listening = True

    def _extract_command_after_wake_word(self, activation_text):
        """Извлечение команды после wake word"""
        text_lower = activation_text.lower().strip()

        # Ищем wake word и берем текст после него
        for wake_word in self.wake_words:
            if wake_word in text_lower:
                # Находим позицию wake word
                wake_pos = text_lower.find(wake_word)
                # Берем текст после wake word
                after_wake = text_lower[wake_pos + len(wake_word):].strip()

                # Убираем служебные слова
                command_words = after_wake.split()
                filtered_words = [w for w in command_words if w not in [
                    'пожалуйста', 'можешь', 'скажи']]

                if filtered_words:
                    command = ' '.join(filtered_words)
                    return command if len(command) > 2 else None

        return None

    def _enter_command_mode(self):
        """Режим ожидания команды после активации"""
        try:
            # Играем звуковой сигнал активации (опционально)
            self._play_activation_sound()

            # Временно останавливаем основное прослушивание
            if hasattr(self.audio_manager, 'stop_continuous_recording'):
                self.audio_manager.stop_continuous_recording()
            time.sleep(0.5)  # Небольшая пауза

            # Показать визуально, что идёт запись команды — зелёный
            try:
                robot = getattr(self.ai_orchestrator, "robot", None)
                if robot and hasattr(robot, "set_rgb_preset"):
                    robot.set_rgb_preset("green")
            except Exception as _:
                pass

            # Записываем команду пользователя
            logging.info("🎤 Записываю команду...")

            if not self.audio_manager:
                return

            # Умная запись с детекцией голоса
            audio_file = self.audio_manager.record_audio(
                duration_seconds=self.activation_timeout
            )

            if not audio_file:
                logging.info("🤫 Команда не услышана")
                return

            # Распознаем команду
            command_text = self.speech_handler.transcribe_audio(audio_file)

            if command_text:
                logging.info(f"👤 Команда: '{command_text}'")
                self._process_voice_command(command_text)
            else:
                logging.info("🤫 Не удалось распознать команду")

            # Удаляем временный файл
            try:
                Path(audio_file).unlink(missing_ok=True)
            except:
                pass

        except Exception as e:
            logging.error(f"❌ Ошибка режима команд: {e}")
        finally:
            # Гасим индикацию записи
            try:
                robot = getattr(self.ai_orchestrator, "robot", None)
                if robot and hasattr(robot, "set_rgb_preset"):
                    robot.set_rgb_preset("off")
            except Exception as _:
                pass

            # Всегда возобновляем прослушивание wake word
            self._resume_wake_word_listening()

    def _process_voice_command(self, command_text):
        """Обработка голосовой команды через AI оркестратор"""
        try:
            if not self.ai_orchestrator:
                # Fallback - простой ответ
                response_text = f"Понял команду: {command_text}. Но AI оркестратор не подключен."
                self._speak_response(response_text)
                return

            # Обрабатываем через AI оркестратор
            logging.info("🧠 Обрабатываю команду через AI...")

            result = self.ai_orchestrator.smart_process_request(
                text=command_text
            )

            if result.get("success"):
                response_text = result.get("ai_response", "Команда выполнена")

                # Озвучиваем ответ
                self._speak_response(response_text)

                # Логируем результат
                intent = result.get("intent", "unknown")
                logging.info(
                    f"✅ Команда обработана ({intent}): '{response_text[:50]}...'")

            else:
                error_text = "Извините, не смог обработать команду"
                self._speak_response(error_text)
                logging.error(
                    f"❌ Ошибка обработки команды: {result.get('error')}")

        except Exception as e:
            error_text = "Произошла ошибка при обработке команды"
            self._speak_response(error_text)
            logging.error(f"❌ Критическая ошибка обработки команды: {e}")

    def _speak_response(self, text):
        """Озвучивание ответа"""
        try:
            if not self.speech_handler or not self.audio_manager:
                logging.warning("⚠️ Компоненты для озвучивания недоступны")
                return

            logging.info(f"🔊 Озвучиваю: '{text[:50]}...'")

            # Генерируем аудио
            audio_file = self.speech_handler.text_to_speech(text)

            if audio_file:
                # Воспроизводим
                success = self.audio_manager.play_audio(audio_file)
                if success:
                    logging.info("✅ Ответ озвучен")
                else:
                    logging.error("❌ Не удалось воспроизвести ответ")
            else:
                logging.error("❌ Не удалось создать аудио файл")

        except Exception as e:
            logging.error(f"❌ Ошибка озвучивания: {e}")

    def _play_activation_sound(self):
        """Воспроизведение звука активации (опционально)"""
        try:
            # Можно воспроизвести короткий звуковой сигнал
            # Пока просто логируем
            logging.debug("🔔 Звук активации")
        except Exception as e:
            logging.debug(f"Ошибка звука активации: {e}")

    def get_status(self):
        """Получить статус сервиса"""
        return {
            "wake_word_service": {
                "running": self.is_running,
                "listening": self.is_listening,
                "wake_words": self.wake_words,
                "sensitivity_threshold": self.sensitivity_threshold,
                "audio_manager_available": self.audio_manager is not None,
                "speech_handler_available": self.speech_handler is not None,
                "ai_orchestrator_connected": self.ai_orchestrator is not None
            }
        }

    def test_wake_word_detection(self, test_phrases):
        """Тест системы обнаружения wake word"""
        results = []

        for phrase in test_phrases:
            detected = self._contains_wake_word(phrase.lower())
            results.append({
                "phrase": phrase,
                "detected": detected,
                "expected": any(wake in phrase.lower() for wake in self.wake_words)
            })

        return results

    def _resume_wake_word_listening(self):
        """Возобновление прослушивания wake word после команды"""
        try:
            # Пауза перед возобновлением
            time.sleep(2)

            if self.is_running:
                self.is_listening = True
                # Цикл сам перезапустится

        except Exception as e:
            logging.error(f"❌ Ошибка возобновления прослушивания: {e}")

    def _process_audio_buffer(self, audio_files):
        """Обработка буфера аудио файлов на наличие wake word"""
        try:
            # Обрабатываем только если накопилось достаточно данных
            if len(audio_files) < 2:  # Минимум один chunk
                return

            # Обрабатываем только последние 2-3 файла для эффективности
            recent_files = audio_files[-3:] if len(
                audio_files) >= 3 else audio_files

            combined_file = f"/tmp/wake_combined_{int(time.time() * 1000)}.wav"

            if self._combine_audio_files(recent_files, combined_file):
                if self._check_audio_has_speech(combined_file):
                    text = self.speech_handler.transcribe_audio(
                        combined_file) if self.speech_handler else None

                    if text and self._contains_wake_word(text.lower()):
                        logging.info(f"🗣️ Обнаружено wake word: '{text}'")

                        if self._wait_for_silence_after_wake_word():
                            self._handle_activation(text)

                Path(combined_file).unlink(missing_ok=True)

        except Exception as e:
            logging.error(f"❌ Ошибка обработки аудио буфера: {e}")

    def _wait_for_silence_after_wake_word(self):
        """Ждем тишину после произнесения wake word (максимум 1 секунда)"""
        try:
            import subprocess

            silence_threshold = 200  # Порог тишины (ниже - считается тишиной)
            silence_duration = 0
            max_silence_wait = 1.0  # Максимум 1 секунда ожидания
            check_interval = 0.2   # Проверяем каждые 0.2 секунды

            logging.debug("🤫 Проверяю тишину после wake word...")

            while silence_duration < max_silence_wait:
                # Записываем короткий отрезок для проверки
                temp_file = f"/tmp/silence_check_{int(time.time() * 1000)}.wav"

                cmd = [
                    'arecord',
                    '-D', f'plughw:{self.audio_manager.microphone_index},0',
                    '-r', str(self.audio_manager.sample_rate),
                    '-c', str(self.audio_manager.channels),
                    '-f', 'S16_LE',
                    '-d', str(check_interval),
                    temp_file
                ]

                try:
                    result = subprocess.run(
                        cmd, capture_output=True, timeout=0.5)

                    if result.returncode == 0 and Path(temp_file).exists():
                        # Проверяем уровень звука
                        if self._is_audio_silent(temp_file, silence_threshold):
                            silence_duration += check_interval
                            logging.debug(f"🤫 Тишина {silence_duration:.1f}s")
                        else:
                            # Есть звук - продолжается речь
                            logging.debug("🗣️ Речь продолжается...")
                            Path(temp_file).unlink(missing_ok=True)
                            return False

                        Path(temp_file).unlink(missing_ok=True)
                    else:
                        Path(temp_file).unlink(missing_ok=True)
                        time.sleep(check_interval)
                        silence_duration += check_interval

                except subprocess.TimeoutExpired:
                    Path(temp_file).unlink(missing_ok=True)
                    silence_duration += check_interval
                except Exception as e:
                    Path(temp_file).unlink(missing_ok=True)
                    logging.debug(f"Ошибка проверки тишины: {e}")
                    return True  # В случае ошибки считаем что тишина

            # Если дошли сюда - была достаточная тишина
            logging.debug("✅ Обнаружена тишина после wake word")
            return True

        except Exception as e:
            logging.error(f"❌ Ошибка детекции тишины: {e}")
            return True  # По умолчанию считаем что тишина есть

    def _combine_audio_files(self, audio_files, output_file):
        """Объединение нескольких WAV файлов в один"""
        try:
            import wave

            with wave.open(output_file, 'wb') as output_wav:
                # Настройки из первого файла
                with wave.open(audio_files[0], 'rb') as first_wav:
                    output_wav.setparams(first_wav.getparams())

                # Записываем данные из всех файлов
                for audio_file in audio_files:
                    with wave.open(audio_file, 'rb') as input_wav:
                        output_wav.writeframes(
                            input_wav.readframes(input_wav.getnframes()))

            return True

        except Exception as e:
            logging.error(f"❌ Ошибка объединения аудио файлов: {e}")
            return False

    def _is_audio_silent(self, audio_file, threshold=200):
        """Проверка является ли аудио тишиной"""
        try:
            import wave
            import numpy as np

            with wave.open(audio_file, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
                audio_data = np.frombuffer(frames, dtype=np.int16)

                # Вычисляем среднюю громкость
                volume = np.abs(audio_data).mean()

                is_silent = volume < threshold
                logging.debug(
                    f"🔊 Уровень звука: {volume:.1f}, тишина: {is_silent}")

                return is_silent

        except Exception as e:
            logging.error(f"❌ Ошибка проверки тишины: {e}")
            return True  # По умолчанию считаем тишиной
