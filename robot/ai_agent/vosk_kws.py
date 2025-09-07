# robot/ai_agent/vosk_kws.py
from __future__ import annotations
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, List

try:
    from vosk import Model, KaldiRecognizer
except Exception as e:
    Model = None
    KaldiRecognizer = None
    logging.warning("Vosk недоступен: %s", e)


class VoskKWS:
    """
    Потоковый wake-детектор на Vosk:
    - слушает микрофон через arecord (16 kHz, mono, S16_LE, RAW)
    - ограничивает распознавание грамматикой (список wake-слов)
    - при финальном распознавании слова из списка -> HIT
    - можно требовать минимальную уверенность по словам
    """

    def __init__(
        self,
        model_dir: str,
        wake_words: List[str],
        device_index: int = 3,
        sample_rate: int = 16000,
        chunk_ms: int = 30,
        min_conf: float = 0.6
    ):
        if Model is None or KaldiRecognizer is None:
            raise RuntimeError("Vosk не установлен (pip install vosk)")

        self.model_dir = str(model_dir)
        if not Path(self.model_dir).exists():
            raise FileNotFoundError(
                f"Vosk model dir не найден: {self.model_dir}")

        if not wake_words:
            raise ValueError("Нужно указать хотя бы одно wake слово")

        # нормализуем слова (нижний регистр)
        self.wake_words = sorted({w.strip().lower()
                                 for w in wake_words if w.strip()})
        self.grammar_json = json.dumps(self.wake_words, ensure_ascii=False)

        self.device_hw = f"plughw:{int(device_index)},0"
        self.sample_rate = int(sample_rate)  # 16000 для модели small RU
        self.chunk_ms = int(chunk_ms)
        self.frame_bytes = int(
            self.sample_rate * (self.chunk_ms / 1000.0) * 2)  # 16-bit mono
        self.min_conf = float(min_conf)

        # Vosk модель и декодер
        self.model = Model(self.model_dir)
        self.rec = KaldiRecognizer(
            self.model, self.sample_rate, self.grammar_json)
        self.rec.SetWords(True)  # чтобы приходили конфиденсы токенов

        # внутренние поля потока
        self._proc: Optional[subprocess.Popen] = None
        self._thr: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # последняя сработка
        self._hit_lock = threading.Lock()
        self._last_hit_ts: float = 0.0
        self._last_hit_word: Optional[str] = None
        self._last_hit_conf: Optional[float] = None

        logging.info(
            "VoskKWS: init model=%s, words=%s, sr=%d, chunk=%dms, min_conf=%.2f",
            self.model_dir, self.wake_words, self.sample_rate, self.chunk_ms, self.min_conf
        )

    # ---- API ----

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()

        cmd = [
            "arecord",
            "-D", self.device_hw,
            "-r", str(self.sample_rate),
            "-c", "1",
            "-f", "S16_LE",
            "-t", "raw"
        ]
        logging.info("VoskKWS: запуск arecord: %s", " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0
        )

        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        logging.info("VoskKWS: поток запущен")

    def stop(self):
        self._stop.set()
        try:
            if self._thr and self._thr.is_alive():
                self._thr.join(timeout=2.0)
        except Exception:
            pass
        try:
            if self._proc:
                self._proc.terminate()
        except Exception:
            pass
        self._proc = None
        logging.info("VoskKWS: остановлен")

    def hit_recent(self, window_ms: int = 700) -> Tuple[bool, Optional[str], Optional[float], Optional[float]]:
        now = time.time()
        with self._hit_lock:
            if self._last_hit_ts and (now - self._last_hit_ts) <= (window_ms / 1000.0):
                return True, self._last_hit_word, self._last_hit_conf, self._last_hit_ts
        return False, None, None, None

    # ---- цикл ----

    def _loop(self):
        assert self._proc and self._proc.stdout
        stdout = self._proc.stdout

        while not self._stop.is_set():
            try:
                data = stdout.read(self.frame_bytes)
                if not data:
                    time.sleep(0.001)
                    continue

                # AcceptWaveform -> True, если готов финальный результат
                if self.rec.AcceptWaveform(data):
                    result = self.rec.Result()  # финальный JSON
                    self._handle_result_json(result, final=True)
                else:
                    # Можно смотреть partial (необязательно)
                    # partial = self.rec.PartialResult()
                    # не используем для хитов, чтобы не плодить ложняк
                    pass

            except Exception as e:
                logging.error("VoskKWS loop error: %s", e)
                time.sleep(0.01)

    def _handle_result_json(self, result_json: str, final: bool):
        try:
            obj = json.loads(result_json or "{}")
        except Exception:
            return

        text = (obj.get("text") or "").strip().lower()
        if not text:
            return

        # Пример obj["result"] = [{ "word": "...", "conf": 0.87, ...}, ...]
        words = obj.get("result") or []
        # берём макс. confidence по словам, которые входят в текст
        # (для wake-слов текст обычно одно слово)
        conf = 0.0
        for w in words:
            try:
                conf = max(conf, float(w.get("conf", 0.0)))
            except Exception:
                pass

        if text in self.wake_words and conf >= self.min_conf:
            ts = time.time()
            with self._hit_lock:
                self._last_hit_ts = ts
                self._last_hit_word = text
                self._last_hit_conf = conf
            logging.info("VoskKWS: HIT word=%r conf=%.3f", text, conf)
