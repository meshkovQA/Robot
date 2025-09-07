# robot/ai_agent/wake_word_service.py
import threading
import time
import logging
from pathlib import Path
from .audio_manager import AudioManager
from .speech_handler import SpeechHandler
from .vosk_kws import VoskKWS


class WakeWordService:
    """
    Wake Word через VoskKWS:
    - Vosk слушает микрофон в отдельном потоке
    - при hit сразу активация
    """

    def __init__(self, config, ai_orchestrator=None):
        self.config = config
        self.ai_orchestrator = ai_orchestrator

        self.audio_manager: AudioManager | None = None
        self.speech_handler: SpeechHandler | None = None

        self.activation_timeout = int(
            self.config.get("activation_timeout", 10))
        self.cooldown_until = 0.0
        self._cd_after_tts = float(self.config.get("wake", {}).get(
            "cooldown_after_tts_ms", 2000)) / 1000.0
        self._cd_after_activation = float(self.config.get("wake", {}).get(
            "cooldown_after_activation_ms", 1000)) / 1000.0

        vcfg = (self.config.get("vosk_kws") or {})
        model_dir = vcfg.get("model_dir") or Path(
            "/opt/robot/models/vosk/current")

        self._kws = VoskKWS(
            model_dir=str(model_dir),
            wake_words=list(self.config.get("wake_words") or []),
            device_index=int(self.config.get(
                "audio", {}).get("microphone_index", 3)),
            sample_rate=int(vcfg.get("sample_rate", 16000)),
            chunk_ms=int(vcfg.get("chunk_ms", 30)),
            min_conf=float(vcfg.get("min_conf", 0.6)),
        )
        self._confirm_window_ms = int(vcfg.get("confirm_window_ms", 700))

        self.is_running = False
        self.is_listening = False
        self.service_thread = None

        self._initialize_components()
        logging.info("🎤 WakeWordService (VoskKWS) инициализирован")

    def _initialize_components(self):
        try:
            self.audio_manager = AudioManager(self.config.get("audio", {}))
            self.speech_handler = SpeechHandler(self.config)
            self.speech_handler.audio_manager = self.audio_manager
            logging.info("✅ Компоненты вывода/озвучки готовы")
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации: {e}")

    def start_service(self):
        if self.is_running:
            logging.warning("⚠️ Уже запущен")
            return False
        self.is_running = True
        self.is_listening = True
        self._kws.start()
        self.service_thread = threading.Thread(
            target=self._wake_word_loop, daemon=True)
        self.service_thread.start()
        logging.info("🚀 Vosk WakeWord запущен")
        return True

    def stop_service(self):
        if not self.is_running:
            return
        self.is_running = False
        self.is_listening = False
        try:
            self._kws.stop()
        except Exception:
            pass
        if self.service_thread and self.service_thread.is_alive():
            self.service_thread.join(timeout=5)
        logging.info("⏹️ Остановлен")

    def _wake_word_loop(self):
        try:
            logging.info("🔄 НАЧИНАЮ _wake_word_loop (vosk)")
            while self.is_running:
                if time.time() < self.cooldown_until:
                    time.sleep(0.02)
                    continue
                if not self.is_listening:
                    time.sleep(0.05)
                    continue

                ok, word, conf, ts = self._kws.hit_recent(
                    self._confirm_window_ms)
                if ok:
                    logging.info("🎯 Wake HIT: %r conf=%.3f", word, conf)
                    self.is_listening = False
                    self._handle_activation()
                    self.cooldown_until = time.time() + self._cd_after_activation
                    self.is_listening = True
                else:
                    time.sleep(0.01)
        except Exception as e:
            logging.error(f"❌ Ошибка в цикле: {e}")
        finally:
            logging.info("🔚 Цикл завершен")

    def _handle_activation(self):
        try:
            robot = getattr(self.ai_orchestrator, "robot", None)
            if robot and hasattr(robot, "set_rgb_preset"):
                robot.set_rgb_preset("green")

            try:
                self._kws.stop()
                time.sleep(0.08)
            except Exception:
                pass

            logging.info("🎤 Запись команды до тишины (max=%ss)",
                         self.activation_timeout)
            audio_file = self.audio_manager.record_until_silence(
                max_duration=self.activation_timeout,
                silence_timeout=1.8,
                pre_roll_files=None,
            )

            if robot and hasattr(robot, "set_rgb_preset"):
                robot.set_rgb_preset("off")

            if not audio_file:
                logging.info("🤫 Команда не услышана")
                return

            logging.info("🗣️ STT для файла: %s", audio_file)
            text = self.speech_handler.transcribe_audio(audio_file)
            Path(audio_file).unlink(missing_ok=True)

            if not text:
                logging.info("🤫 Не удалось распознать команду")
                return

            cleaned = text.strip().strip(".!?,…").lower()
            if len(cleaned) < 2 or cleaned in {"всё", "все", "ок", "угу", "ага", "да", "нет"}:
                logging.info(
                    "🤷 Служебная/пустая команда: %r — пропускаю", text)
                return

            logging.info("👤 Команда: %r", text)
            self._process_voice_command(text)

        except Exception as e:
            logging.error(f"❌ Ошибка обработки активации: {e}")
        finally:
            if self.is_running:
                try:
                    time.sleep(0.08)
                    self._kws.start()
                except Exception as e:
                    logging.error("❌ Не удалось перезапустить VoskKWS: %s", e)
            self.cooldown_until = time.time() + max(self._cd_after_activation, 0.5)
            self._resume_wake_word_listening()

    def _process_voice_command(self, command_text: str):
        try:
            if not self.ai_orchestrator:
                self._speak_response(
                    f"Понял команду: {command_text}. Но AI оркестратор не подключен.")
                return

            logging.info("🧠 Обработка команды AI...")
            result = self.ai_orchestrator.smart_process_request(
                text=command_text)

            if result.get("success"):
                response_text = result.get("ai_response", "Команда выполнена")
                logging.info("✅ AI intent=%s", result.get("intent", "unknown"))
                self._speak_response(response_text)
            else:
                logging.error("❌ Ошибка обработки команды: %s",
                              result.get("error"))
                self._speak_response("Извините, не смог обработать команду")
        except Exception as e:
            logging.error(f"❌ Критическая ошибка обработки команды: {e}")
            self._speak_response("Произошла ошибка при обработке команды")

    def _speak_response(self, text: str):
        try:
            if not self.speech_handler or not self.audio_manager:
                logging.warning("⚠️ Компоненты для озвучивания недоступны")
                return
            self.is_listening = False
            logging.info("🔊 Озвучиваю: %r", text[:80])
            audio_file = self.speech_handler.text_to_speech(text)
            if audio_file:
                ok = self.audio_manager.play_audio(audio_file)
                if not ok:
                    logging.error("❌ Не удалось воспроизвести ответ")
            else:
                logging.error("❌ Не удалось создать аудиофайл")
            time.sleep(2)
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
