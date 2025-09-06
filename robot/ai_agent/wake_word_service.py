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
    Сервис голосовой активации (wake):
    - Пишет короткие чанки (1 сек)
    - Фильтрует их по простым аудио-гейтам (есть речь/непрерывность)
    - Прогоняет через SimpleKWS (без STT и без тяжёлых моделей)
    - Подтверждает wake по N попаданиям за окно T
    - После активации пишет команду «до тишины» и отправляет в AI
    """

    def __init__(self, config, ai_orchestrator=None):
        self.config = config
        self.ai_orchestrator = ai_orchestrator

        # ---- компоненты ----
        self.audio_manager: AudioManager | None = None
        self.speech_handler: SpeechHandler | None = None

        # ---- поведение после активации ----
        self.activation_timeout = int(
            self.config.get("activation_timeout", 10))

        # ---- тайминги/кулдауны ----
        wake_cfg = (self.config.get("wake", {}) or {})
        self.cooldown_until = 0.0
        self._cd_after_tts = float(wake_cfg.get(
            "cooldown_after_tts_ms", 2000)) / 1000.0
        self._cd_after_activation = float(wake_cfg.get(
            "cooldown_after_activation_ms", 1000)) / 1000.0

        # ---- KWS ----
        kws_cfg = (self.config.get("wake_kws", {}) or {})
        self._kws = SimpleKWS(
            threshold=float(kws_cfg.get("threshold", 0.85)),
            margin_alpha=float(kws_cfg.get("margin_alpha", 1.0)),
        )
        pos_dir = kws_cfg.get("samples_dir", "data/wake_samples")
        neg_dir = kws_cfg.get("negatives_dir", "data/wake_negatives")
        pos_loaded = self._kws.enroll_dir(pos_dir)
        neg_loaded = self._kws.enroll_neg_dir(neg_dir)
        logging.info(
            "🗝️ SimpleKWS: POS=%d NEG=%d (thr=%.3f, alpha=%.2f)",
            pos_loaded, neg_loaded, self._kws.threshold, self._kws.alpha
        )

        # Подтверждение wake: N попаданий в окне T
        self._kws_min_hits = int(kws_cfg.get(
            "min_hits", 2))          # рекомендую 2..3
        self._kws_window = float(kws_cfg.get(
            "window_sec", 1.5))      # 1.5–2.0 сек
        self._kws_hits: list[float] = []

        # ---- состояние ----
        self.is_running = False
        self.is_listening = False
        self.service_thread = None

        self._initialize_components()
        logging.info("🎤 WakeWordService инициализирован (KWS-only)")

    # ---------------- инициализация ----------------

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
        """
        Wake только по KWS (без STT).
        1) 1c чанк → проверка has_speech/has_continuous_sound
        2) SimpleKWS.detect -> (ok, pos, neg, margin)
        3) Подтверждение по N попаданиям в окне T
        """
        try:
            logging.info("🔄 НАЧИНАЮ _wake_word_loop (KWS-only)")
            chunk_duration = 1.0

            while self.is_running:
                # кулдаун: игнор чанк
                if time.time() < self.cooldown_until:
                    time.sleep(0.03)
                    continue

                # временно не слушаем (например, во время TTS)
                if not self.is_listening:
                    time.sleep(0.05)
                    continue

                # 1) записываем 1 сек
                tmp = self.audio_manager.record_chunk(
                    duration_seconds=chunk_duration)
                if not tmp:
                    continue

                try:
                    # 2) предварительный гейт по аудио, чтобы не кормить KWS шумом
                    has_voice = self.audio_manager.has_speech(tmp)
                    cont = self.audio_manager.has_continuous_sound(tmp)
                    logging.info(
                        "🎚️ Гейт: has_voice=%s cont=%s файл=%s", has_voice, cont, tmp)
                    if not (has_voice and cont):
                        Path(tmp).unlink(missing_ok=True)
                        continue

                    # 3) KWS
                    ok, pos, neg, margin = self._kws.detect(tmp)
                    logging.info(
                        "🔎 KWS: ok=%s pos=%.3f neg=%.3f margin=%.3f thr=%.3f",
                        ok, pos, neg, margin, self._kws.threshold
                    )

                    # sliding window по попаданиям
                    now = time.time()
                    self._kws_hits = [t for t in self._kws_hits if (
                        now - t) <= self._kws_window]
                    if ok:
                        self._kws_hits.append(now)
                        logging.info("✅ KWS hit %d/%d (окно %.1fs)",
                                     len(self._kws_hits), self._kws_min_hits, self._kws_window)

                    if len(self._kws_hits) >= self._kws_min_hits:
                        logging.info(
                            "🎯 Wake CONFIRMED по KWS (hits=%d)", len(self._kws_hits))
                        self._kws_hits.clear()
                        self.is_listening = False
                        self._handle_activation()  # текст не нужен
                        # небольшой кулдаун после активации
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
        """
        После детекта: записать команду до тишины, распознать через SpeechHandler (тот сам выберет провайдера),
        отфильтровать служебные/пустые, затем отправить в AI.
        """
        try:
            # Визуальный сигнал (если доступен)
            try:
                robot = getattr(self.ai_orchestrator, "robot", None)
                if robot and hasattr(robot, "set_rgb_preset"):
                    robot.set_rgb_preset("green")
            except Exception:
                pass

            logging.info("🎤 Запись команды до тишины (max=%ss)",
                         self.activation_timeout)
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

            logging.info("🗣️ STT для файла: %s", audio_file)
            command_text = self.speech_handler.transcribe_audio(audio_file)
            Path(audio_file).unlink(missing_ok=True)

            if not command_text:
                logging.info("🤫 Не удалось распознать команду")
                return

            cleaned = command_text.strip().strip(".!?,…").lower()
            if len(cleaned) < 2 or cleaned in {"всё", "все", "ок", "угу", "ага", "да", "нет"}:
                logging.info(
                    "🤷 Служебная/пустая команда: %r — пропускаю", command_text)
                return

            logging.info("👤 Команда: %r", command_text)
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
                logging.error("❌ Не удалось создать аудио файл")
            time.sleep(2)  # дать звуку затихнуть
        except Exception as e:
            logging.error(f"❌ Ошибка озвучивания: {e}")
        finally:
            if self.is_running:
                # глухое окно после TTS
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
