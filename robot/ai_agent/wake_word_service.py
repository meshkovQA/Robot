# robot/ai_agent/wake_word_service.py
import threading
import time
import logging
from pathlib import Path
import re
from .audio_manager import AudioManager
from .speech_handler import SpeechHandler


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

        # Состояние сервиса
        self.is_running = False
        self.is_listening = False
        self.service_thread = None

        # Компоненты
        self.audio_manager: AudioManager | None = None
        self.speech_handler: SpeechHandler | None = None

        self.wake_cfg = self.config.get('wake', {}) or {}

        match_cfg = self.wake_cfg.get('match', {}) if isinstance(
            self.wake_cfg, dict) else {}
        self._match_start_only = bool(match_cfg.get('start_only', True))
        self._max_prefix_words = int(match_cfg.get('max_prefix_words', 2))
        self._use_word_boundary = bool(match_cfg.get('word_boundary', True))

        # cooldown
        self.cooldown_until = 0.0
        self._cd_after_tts = float(self.wake_cfg.get(
            'cooldown_after_tts_ms', 2000))/1000.0
        self._cd_after_activation = float(self.wake_cfg.get(
            'cooldown_after_activation_ms', 1000))/1000.0

        self._initialize_components()
        logging.info("🎤 WakeWordService инициализирован")
        logging.info(f"👂 Слова активации: {', '.join(self.wake_words)}")

    def _initialize_components(self):
        try:
            self.audio_manager = AudioManager(self.config.get('audio', {}))
            self.speech_handler = SpeechHandler(self.config)
            self.speech_handler.audio_manager = self.audio_manager
            logging.info("✅ WakeWord компоненты готовы")
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации WakeWord компонентов: {e}")

    def start_service(self):
        if self.is_running:
            logging.warning("⚠️ WakeWord сервис уже запущен")
            return False
        if not self.audio_manager or not self.speech_handler:
            logging.error("❌ Компоненты не инициализированы")
            return False

        self.is_running = True
        self.is_listening = True
        self.service_thread = threading.Thread(
            target=self._wake_word_loop, daemon=True)
        self.service_thread.start()

        logging.info("🚀 WakeWord сервис запущен")
        logging.info(
            f"👂 Слушаю активационные слова: {', '.join(self.wake_words)}")
        return True

    def stop_service(self):
        if not self.is_running:
            return
        self.is_running = False
        self.is_listening = False
        if self.service_thread and self.service_thread.is_alive():
            self.service_thread.join(timeout=5)
        logging.info("⏹️ WakeWord сервис остановлен")

    # ------------ основной цикл ------------

    def _wake_word_loop(self):
        """Слушаем микрофон чанками и проверяем wake-word по последнему чанку без объединения файлов."""
        try:
            logging.info("🔄 НАЧИНАЮ _wake_word_loop")
            chunk_duration = 1

            while self.is_running:
                logging.info("👂 Жду wake word...")
                if time.time() < self.cooldown_until:
                    logging.info(
                        f"⏳ Ожидание окончания кулдауна: {self.cooldown_until - time.time():.1f}с")
                    time.sleep(0.05)
                    continue

                if not self.is_listening:
                    logging.info("👂 Ожидание активации...")
                    time.sleep(0.1)
                    continue

                # Пишем короткий чанк
                tmp = self.audio_manager.record_chunk(
                    duration_seconds=chunk_duration)
                logging.info(f"🎧 Записан чанк: {tmp}")
                if not tmp:
                    continue

                # Анализируем ТОЛЬКО этот чанк
                logging.info(f"🗣️ Анализируем файл: {tmp}")
                try:
                    if self.audio_manager.has_speech(tmp) and self.audio_manager.has_continuous_sound(tmp):
                        text = self.speech_handler.transcribe_audio(tmp)
                        if text and self._contains_wake_word(text):
                            logging.info(
                                "✅ Первичный детект wake word. Фиксирую слушалку и подтверждаю по последнему чанку")
                            self.is_listening = False

                            # Подтверждаем на том же файле, без дозаписи и без склейки
                            if self._confirm_wake_word_on_chunk(last_chunk=tmp, primary_text=text):
                                logging.info(
                                    "✅ Подтверждение wake word пройдено")
                                self._pre_roll_files = []  # преролл не используем
                                self._handle_activation(text)
                            else:
                                logging.info(
                                    "❌ Подтверждение wake word не прошло")
                                if self.is_running:
                                    self.is_listening = True
                finally:
                    # Удаляем обработанный чанк
                    Path(tmp).unlink(missing_ok=True)

        except Exception as e:
            logging.error(f"❌ Ошибка в цикле прослушивания: {e}")
        finally:
            logging.info("🔚 Цикл WakeWord завершен")

    # ------------ текстовая логика ------------

    def _contains_wake_word(self, text: str) -> bool:
        clean = re.sub(r'[^\w\s]', ' ', text.lower()).strip()
        if not clean:
            return False
        tokens = clean.split()
        head = " ".join(tokens[:max(1, self._max_prefix_words)])
        for ww in self.wake_words:
            ww = ww.lower()
            if self._use_word_boundary:
                pat = r'^\b' + \
                    re.escape(
                        ww) + r'\b' if self._match_start_only else r'\b' + re.escape(ww) + r'\b'
                if re.search(pat, head if self._match_start_only else clean):
                    return True
            else:
                to_scan = head if self._match_start_only else clean
                if ww in to_scan:
                    return True
        return False

    def _extract_command_after_wake_word(self, activation_text):
        text_lower = activation_text.lower().strip()
        for wake_word in self.wake_words:
            if wake_word in text_lower:
                wake_pos = text_lower.find(wake_word)
                after_wake = text_lower[wake_pos + len(wake_word):].strip()
                filtered = [w for w in after_wake.split() if w not in [
                    'пожалуйста', 'можешь', 'скажи']]
                if filtered:
                    cmd = ' '.join(filtered)
                    return cmd if len(cmd) > 2 else None
        return None

    # ------------ сценарии после активации ------------

    def _handle_activation(self, activation_text):
        try:
            self.is_listening = False
            command = self._extract_command_after_wake_word(activation_text)
            if command:
                logging.info(f"🎯 Выполняю команду: '{command}'")
                self._process_voice_command(command)
            else:
                logging.info("👂 Слушаю команду...")
                self._enter_command_mode()
        except Exception as e:
            logging.error(f"❌ Ошибка обработки активации: {e}")
        finally:
            time.sleep(3)
            self.cooldown_until = time.time() + self._cd_after_activation
            self.is_listening = True

    def _enter_command_mode(self):
        try:
            # Визуализация записи (по желанию)
            try:
                robot = getattr(self.ai_orchestrator, "robot", None)
                if robot and hasattr(robot, "set_rgb_preset"):
                    robot.set_rgb_preset("green")
            except Exception:
                pass

            # Пишем команду без преролла
            audio_file = self.audio_manager.record_until_silence(
                max_duration=self.activation_timeout,
                silence_timeout=1.8,
                pre_roll_files=None  # ключевой момент: НЕ передаём преролл
            )

            try:
                robot = getattr(self.ai_orchestrator, "robot", None)
                if robot and hasattr(robot, "set_rgb_preset"):
                    robot.set_rgb_preset("off")
            except Exception:
                pass

            if not audio_file:
                logging.info("🤫 Команда не услышана")
                return

            command_text = self.speech_handler.transcribe_audio(audio_file)
            Path(audio_file).unlink(missing_ok=True)

            if command_text:
                cleaned = command_text.strip().strip(".!?,…").lower()
                if len(cleaned) < 2 or cleaned in {"всё", "все", "ок", "угу", "ага", "да", "нет"}:
                    logging.info(
                        f"🤷 Пустая/служебная команда: {command_text!r} — не отправляю в AI")
                    return
                logging.info(f"👤 Команда: '{command_text}'")
                self._process_voice_command(command_text)
            else:
                logging.info("🤫 Не удалось распознать команду")

        except Exception as e:
            logging.error(f"❌ Ошибка режима команд: {e}")
        finally:
            self._resume_wake_word_listening()

    def _process_voice_command(self, command_text):
        try:
            if not self.ai_orchestrator:
                self._speak_response(
                    f"Понял команду: {command_text}. Но AI оркестратор не подключен.")
                return

            logging.info("🧠 Обрабатываю команду через AI...")
            result = self.ai_orchestrator.smart_process_request(
                text=command_text)

            if result.get("success"):
                response_text = result.get("ai_response", "Команда выполнена")
                self._speak_response(response_text)
                logging.info(
                    f"✅ Команда обработана ({result.get('intent', 'unknown')}): '{response_text[:50]}...'")
            else:
                self._speak_response("Извините, не смог обработать команду")
                logging.error(
                    f"❌ Ошибка обработки команды: {result.get('error')}")
        except Exception as e:
            self._speak_response("Произошла ошибка при обработке команды")
            logging.error(f"❌ Критическая ошибка обработки команды: {e}")

    def _speak_response(self, text):
        try:
            if not self.speech_handler or not self.audio_manager:
                logging.warning("⚠️ Компоненты для озвучивания недоступны")
                return
            self.is_listening = False
            logging.info(f"🔊 Озвучиваю: '{text[:50]}...'")
            audio_file = self.speech_handler.text_to_speech(text)
            if audio_file:
                ok = self.audio_manager.play_audio(audio_file)
                if not ok:
                    logging.error("❌ Не удалось воспроизвести ответ")
            else:
                logging.error("❌ Не удалось создать аудио файл")
            time.sleep(2)  # даём звуку затихнуть
        except Exception as e:
            logging.error(f"❌ Ошибка озвучивания: {e}")
        finally:
            if self.is_running:
                # очистим кольцевой буфер прослушки (если он у тебя хранится в полях — у тебя локальный, так что ок)
                self.cooldown_until = time.time() + max(self._cd_after_tts, 2.5)  # 2.5с глухое окно
                self.is_listening = True

    def _resume_wake_word_listening(self):
        try:
            time.sleep(2)
            if self.is_running:
                self.is_listening = True
        except Exception as e:
            logging.error(f"❌ Ошибка возобновления прослушивания: {e}")

    # Заглушка для звука активации (оставляем, если захочешь добавить сигнал)
    def _play_activation_sound(self):
        logging.debug("🔔 Звук активации (stub)")

    def _confirm_wake_word_on_chunk(self, last_chunk: str, primary_text: str) -> bool:
        """
        Подтверждаем wake word по тому же последнему чанку (без объединения и без дозаписи).
        """
        try:
            # Уже есть ключевое слово — этого достаточно
            if self._contains_wake_word(primary_text):
                return True

            # Ещё раз распознаём тот же файл и проверяем триггер
            text2 = self.speech_handler.transcribe_audio(last_chunk) or ""
            logging.info(f"🔁 Вторичная проверка wake word: '{text2}'")
            return self._contains_wake_word(text2)
        except Exception as e:
            logging.error(f"❌ Ошибка second-look: {e}")
            return False
