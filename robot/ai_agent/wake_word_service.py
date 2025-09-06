# robot/ai_agent/wake_word_service.py
import threading
import time
import logging
from pathlib import Path

from .audio_manager import AudioManager
from .speech_handler import SpeechHandler
from .simple_kws import SimpleKWS


class WakeWordService:
    """
    Сервис голосовой активации:
    - Постоянно пишет короткие чанки (1с)
    - Проверяет их SimpleKWS (без STT)
    - При детекте — записывает команду до тишины и отправляет в AI
    """

    def __init__(self, config, ai_orchestrator=None):
        self.config = config
        self.ai_orchestrator = ai_orchestrator

        # ---- KWS ----
        kws_cfg = (self.config.get("wake_kws", {}) or {})
        self._kws = SimpleKWS(threshold=float(kws_cfg.get("threshold", 0.82)))
        samples_dir = kws_cfg.get("samples_dir", "data/wake_samples")
        loaded = self._kws.enroll_dir(samples_dir)
        logging.info(
            f"🗝️ SimpleKWS: загружено шаблонов: {loaded} (threshold={self._kws.threshold})")

        # ---- поведение после активации ----
        self.activation_timeout = int(
            self.config.get("activation_timeout", 10))

        # ---- состояние ----
        self.is_running = False
        self.is_listening = False
        self.service_thread = None

        # ---- компоненты ----
        self.audio_manager: AudioManager | None = None
        self.speech_handler: SpeechHandler | None = None

        # ---- тайминги/кулдауны ----
        wake_cfg = self.config.get("wake", {}) or {}
        self.cooldown_until = 0.0
        self._cd_after_tts = float(wake_cfg.get(
            "cooldown_after_tts_ms", 2000)) / 1000.0
        self._cd_after_activation = float(wake_cfg.get(
            "cooldown_after_activation_ms", 1000)) / 1000.0

        self._initialize_components()
        logging.info("🎤 WakeWordService инициализирован (SimpleKWS)")

    def _initialize_components(self):
        try:
            self.audio_manager = AudioManager(self.config.get("audio", {}))
            self.speech_handler = SpeechHandler(self.config)
            self.speech_handler.audio_manager = self.audio_manager
            logging.info("✅ WakeWord компоненты готовы")
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации WakeWord компонентов: {e}")

    # ---------------- управление жизненным циклом ----------------

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

        logging.info("🚀 WakeWord сервис запущен (SimpleKWS)")
        return True

    def stop_service(self):
        if not self.is_running:
            return
        self.is_running = False
        self.is_listening = False
        if self.service_thread and self.service_thread.is_alive():
            self.service_thread.join(timeout=5)
        logging.info("⏹️ WakeWord сервис остановлен")

    # ---------------- основной цикл ----------------

    def _wake_word_loop(self):
        """Слушаем микрофон чанками по 1с и детектим ключевое слово через SimpleKWS."""
        try:
            logging.info("🔄 НАЧИНАЮ _wake_word_loop")
            chunk_duration = 1  # секунда

            while self.is_running:
                if time.time() < self.cooldown_until:
                    time.sleep(0.05)
                    continue

                if not self.is_listening:
                    time.sleep(0.1)
                    continue

                # 1) записываем 1-секундный чанк
                tmp = self.audio_manager.record_chunk(
                    duration_seconds=chunk_duration)
                if not tmp:
                    continue

                # 2) лёгкие пороги, чтобы не кормить KWS пустыми/шумными файлами
                try:
                    has_voice = self.audio_manager.has_speech(tmp)
                    cont = self.audio_manager.has_continuous_sound(tmp)
                    if not (has_voice and cont):
                        # тихо/шум — пропускаем
                        Path(tmp).unlink(missing_ok=True)
                        continue

                    # 3) KWS скорит чанк
                    score = self._kws.score(tmp)
                    logging.info(
                        f"🪄 KWS score={score:.3f} (thr={self._kws.threshold:.3f})")
                    if score >= self._kws.threshold:
                        logging.info("✅ Wake word детектирован (SimpleKWS)")
                        self.is_listening = False
                        # Переходим к записи команды (без прероллов/склеек)
                        self._handle_activation()
                        # cooldown после обработки
                        self.cooldown_until = time.time() + self._cd_after_activation
                        self.is_listening = True
                except Exception as e:
                    logging.error(f"❌ Ошибка KWS/обработки: {e}")
                finally:
                    Path(tmp).unlink(missing_ok=True)

        except Exception as e:
            logging.error(f"❌ Ошибка в цикле прослушивания: {e}")
        finally:
            logging.info("🔚 Цикл WakeWord завершен")

    # ---------------- сценарии после активации ----------------

    def _handle_activation(self):
        """После детекта: записать команду до тишины, распознать и выполнить."""
        try:
            # Визуальный сигнал (если доступен)
            try:
                robot = getattr(self.ai_orchestrator, "robot", None)
                if robot and hasattr(robot, "set_rgb_preset"):
                    robot.set_rgb_preset("green")
            except Exception:
                pass

            audio_file = self.audio_manager.record_until_silence(
                max_duration=self.activation_timeout,
                silence_timeout=1.8,
                pre_roll_files=None,
            )

            # Выключить индикацию
            try:
                robot = getattr(self.ai_orchestrator, "robot", None)
                if robot and hasattr(robot, "set_rgb_preset"):
                    robot.set_rgb_preset("off")
            except Exception:
                pass

            if not audio_file:
                logging.info("🤫 Команда не услышана")
                return

            # STT (выбор провайдера внутри SpeechHandler)
            command_text = self.speech_handler.transcribe_audio(audio_file)
            Path(audio_file).unlink(missing_ok=True)

            if not command_text:
                logging.info("🤫 Не удалось распознать команду")
                return

            cleaned = command_text.strip().strip(".!?,…").lower()
            if len(cleaned) < 2 or cleaned in {"всё", "все", "ок", "угу", "ага", "да", "нет"}:
                logging.info(
                    f"🤷 Пустая/служебная команда: {command_text!r} — не отправляю в AI")
                return

            logging.info(f"👤 Команда: '{command_text}'")
            self._process_voice_command(command_text)

        except Exception as e:
            logging.error(f"❌ Ошибка обработки активации: {e}")
        finally:
            self._resume_wake_word_listening()

    def _process_voice_command(self, command_text: str):
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

    def _speak_response(self, text: str):
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
            time.sleep(2)  # дать звуку затихнуть
        except Exception as e:
            logging.error(f"❌ Ошибка озвучивания: {e}")
        finally:
            if self.is_running:
                self.cooldown_until = time.time() + max(self._cd_after_tts, 2.5)
                self.is_listening = True

    def _resume_wake_word_listening(self):
        try:
            time.sleep(2)
            if self.is_running:
                self.is_listening = True
        except Exception as e:
            logging.error(f"❌ Ошибка возобновления прослушивания: {e}")

    def _play_activation_sound(self):
        # Заглушка для звука активации (если захочешь добавить сигнал)
        logging.debug("🔔 Звук активации (stub)")
