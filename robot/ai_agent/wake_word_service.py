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
        self.sensitivity_threshold = config.get('sensitivity_threshold', 800)

        # Состояние сервиса
        self.is_running = False
        self.is_listening = False
        self.service_thread = None

        # Компоненты
        self.audio_manager: AudioManager | None = None
        self.speech_handler: SpeechHandler | None = None

        self.wake_cfg = self.config.get('wake', {}) or {}

        self._confirm_second_look = bool(
            self.wake_cfg.get('confirm_second_look', True))

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
        """Слушаем микрофон чанками, буферим последние ~3с, распознаём и ищем wake-word."""
        try:
            logging.info("🔄 НАЧИНАЮ _wake_word_loop")
            buffer_files: list[str] = []
            buffer_duration = 0
            max_buffer_duration = 3
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

                # пишем короткий чанк через AudioManager
                tmp = self.audio_manager.record_chunk(
                    duration_seconds=chunk_duration)
                logging.info(f"🎧 Записан чанк: {tmp}")
                if not tmp:
                    continue

                buffer_files.append(tmp)
                buffer_duration += chunk_duration

                logging.info(
                    f"🗣️ Буферизация: {buffer_duration}/{max_buffer_duration}с")

                # держим окно ~3с
                while buffer_duration > max_buffer_duration and buffer_files:
                    logging.info(f"🗑️ Удаляем старый буфер: {buffer_files[0]}")
                    old = buffer_files.pop(0)
                    Path(old).unlink(missing_ok=True)
                    logging.info(f"🗑️ Удалён файл: {old}")
                    buffer_duration -= chunk_duration

                # соберём последние куски в один файл и быстро проверим
                recent = buffer_files[-3:] if len(
                    buffer_files) >= 3 else buffer_files[:]
                logging.info(f"🔊 Комбинируем {len(recent)} файлов для анализа")
                combined = f"/tmp/wake_combined_{int(time.time()*1000)}.wav"

                if self.audio_manager.combine_audio_files(recent, combined):
                    # 1) есть ли речь
                    logging.info(f"🗣️ Анализируем файл: {combined}")
                    if self.audio_manager.has_speech(combined):
                        # 2) похожа ли на речь (не одиночный шум)
                        if self.audio_manager.has_continuous_sound(combined):
                            text = self.speech_handler.transcribe_audio(
                                combined)
                            if text and self._contains_wake_word(text):
                                logging.info(
                                    "✅ Первичный детект wake word. Фиксирую слушалку и подтверждаю на буфере")
                                # 1) замораживаем цикл, чтобы он не писал параллельно
                                self.is_listening = False

                                # 2) подтверждаем по последним файлам (без новой записи микрофона)
                                if self._confirm_wake_word_from_recent(recent_files=recent, primary_text=text):
                                    logging.info(
                                        "✅ Подтверждение wake word пройдено")
                                    # дальше он сам решит: парсить команду из фразы или записать новую
                                    self._handle_activation(text)
                                else:
                                    logging.info(
                                        "❌ Подтверждение wake word не прошло")
                                    # разблокируем слушалку только если сервис ещё работает
                                    if self.is_running:
                                        self.is_listening = True
                    Path(combined).unlink(missing_ok=True)

        except Exception as e:
            logging.error(f"❌ Ошибка в цикле прослушивания: {e}")
        finally:
            # очистим хвосты
            for f in buffer_files:
                Path(f).unlink(missing_ok=True)
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

    def _confirm_wake_word_from_recent(self, recent_files, primary_text: str) -> bool:
        """
        Подтверждаем wake word без arecord:
        - если в основном тексте уже есть триггер — ok;
        - иначе пробуем распознать самый свежий чанк из recent_files.
        """
        try:
            # если уже явно есть ключевое слово — считаем подтверждённым
            if self._contains_wake_word(primary_text):
                return True

            # иначе попробуем последний чанк (1 сек) из окна
            if not recent_files:
                return False

            last_chunk = recent_files[-1]
            text2 = self.speech_handler.transcribe_audio(last_chunk) or ""
            logging.info(
                f"🔁 Вторичная проверка wake word на последнем чанке: '{text2}'")
            return self._contains_wake_word(text2)
        except Exception as e:
            logging.error(f"❌ Ошибка second-look: {e}")
            # в случае ошибки — не подтверждаем
            return False

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
            # визуализация записи (опционально)
            try:
                robot = getattr(self.ai_orchestrator, "robot", None)
                if robot and hasattr(robot, "set_rgb_preset"):
                    robot.set_rgb_preset("green")
            except Exception:
                pass

            audio_file = self.audio_manager.record_until_silence(
                max_duration=self.activation_timeout,
                silence_timeout=1.5
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
                self.cooldown_until = time.time() + self._cd_after_tts
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

    def _confirm_wake_word(self) -> bool:
        if not self._confirm_second_look:
            return True
        tmp = self.audio_manager.record_chunk(duration_seconds=1)
        if not tmp:
            return False
        try:
            text2 = self.speech_handler.transcribe_audio(tmp) or ""
            return self._contains_wake_word(text2)
        finally:
            Path(tmp).unlink(missing_ok=True)
