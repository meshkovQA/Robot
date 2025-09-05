# robot/ai_agent/audio_manager.py
import wave
import time
import logging
import subprocess
from pathlib import Path
import numpy as np


class AudioManager:
    """Управление микрофоном и динамиками на Raspberry Pi (только arecord/aplay)."""

    def __init__(self, config=None):
        self.config = config or {}

        # Настройки аудио
        self.sample_rate = self.config.get('sample_rate', 48000)
        self.channels = self.config.get('channels', 1)

        # Устройства
        self.microphone_index = self.config.get('microphone_index', None)
        self.speaker_index = self.config.get('speaker_index', None)

        # Настройки детекции речи/тишины

        self.wake_cfg = (self.config or {}).get('wake', {})
        self._min_avg = int(self.wake_cfg.get('min_avg_volume', 500))
        self._min_peak = int(self.wake_cfg.get('min_peak_volume', 4000))
        self._cont_min_ms = int(self.wake_cfg.get('continuous_min_ms', 300))
        self._cont_win_ms = int(self.wake_cfg.get('continuous_window_ms', 20))
        self._cont_mean = float(self.wake_cfg.get(
            'continuous_mean_threshold', 300))
        sil = self.wake_cfg.get('silence_check', {}) if isinstance(
            self.wake_cfg, dict) else {}
        self._sil_max_wait = float(sil.get('max_wait_ms', 1200)) / 1000.0
        self._sil_interval = float(sil.get('check_interval_s', 1))
        self._sil_threshold = float(sil.get('silence_threshold', 200))

        logging.info(f"AudioManager. Микрофон index: {self.microphone_index}")
        logging.info(f"AudioManager. Динамик  index: {self.speaker_index}")

    # ---------- низкоуровневые операции записи/проигрывания ----------

    def _arecord(self, duration_seconds: float, out_path: str) -> bool:
        """Вспомогательный вызов arecord."""
        logging.info(f"🎤 Запись {duration_seconds:.1f}s в {out_path}...")
        # arecord на некоторых системах не принимает дробные значения -d
        int_seconds = max(1, int(round(float(duration_seconds))))

        cmd = [
            'arecord',
            '-D', f'plughw:{self.microphone_index},0',
            '-r', str(self.sample_rate),
            '-c', str(self.channels),
            '-f', 'S16_LE',
            '-d', str(int_seconds),
            out_path
        ]

        logging.info(f"arecord cmd: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=duration_seconds + 2)
            logging.info(f"arecord returncode: {result.returncode}")
            if result.returncode == 0 and Path(out_path).exists():
                return True
            logging.warning(
                f"arecord stderr: {result.stderr.decode(errors='ignore') if result.stderr else ''}")
        except subprocess.TimeoutExpired:
            logging.warning("arecord timeout")
        except Exception as e:
            logging.error(f"arecord error: {e}")
        return False

    def record_chunk(self, duration_seconds=1, to_file: str | None = None) -> str | None:
        """Записать короткий кусок аудио в WAV и вернуть путь."""
        to_file = to_file or f"/tmp/chunk_{int(time.time()*1000)}.wav"
        ok = self._arecord(duration_seconds, to_file)
        return to_file if ok else None

    def record_audio(self, duration_seconds=5, output_file=None):
        """Запись фиксированной длительности (обертка над _arecord)."""
        output_file = output_file or f"data/temp_recording_{int(time.time())}.wav"
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        if self._arecord(duration_seconds, output_file):
            return output_file
        return None

    def play_audio(self, audio_file):
        """Воспроизведение аудио через динамики."""
        if not audio_file or not Path(audio_file).exists():
            logging.error(f"❌ Файл не найден: {audio_file}")
            return False
        try:
            if audio_file.lower().endswith('.mp3'):
                cmd = f"mpg123 -a plughw:{self.speaker_index},0 {audio_file}" if self.speaker_index is not None else f"mpg123 {audio_file}"
            else:
                cmd = f"aplay -D plughw:{self.speaker_index},0 {audio_file}" if self.speaker_index is not None else f"aplay {audio_file}"
            logging.info(f"🔊 Воспроизведение: {audio_file}")
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                return True
            logging.error(f"❌ Ошибка воспроизведения: {result.stderr}")
        except Exception as e:
            logging.error(f"❌ Ошибка воспроизведения: {e}")
        return False

    # ---------- анализ аудио ----------

    def detect_levels(self, audio_file: str) -> tuple[float, float]:
        """Вернуть (avg_abs, max_abs) амплитуды INT16."""
        try:
            with wave.open(audio_file, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)
            if audio.size == 0:
                return 0, 0
            return float(np.abs(audio).mean()), float(np.abs(audio).max())
        except Exception as e:
            logging.error(f"❌ detect_levels error: {e}")
            return 0, 0

    def is_audio_silent(self, audio_file, threshold=200):
        """Пороговая проверка «тишины» по средней амплитуде."""
        avg, _ = self.detect_levels(audio_file)
        return avg < threshold

    def has_speech(self, audio_file: str, min_avg_volume=None, min_max_volume=None) -> bool:
        min_avg = self._min_avg if min_avg_volume is None else min_avg_volume
        min_peak = self._min_peak if min_max_volume is None else min_max_volume
        avg, peak = self.detect_levels(audio_file)
        logging.debug(
            f"🔊 avg={avg:.1f}, max={peak:.1f}, thr=({min_avg},{min_peak})")
        return avg > min_avg and peak > min_peak

    def has_continuous_sound(self, audio_file: str,
                             min_ms=None, window_ms=None, mean_threshold=None) -> bool:
        min_ms = self._cont_min_ms if min_ms is None else int(min_ms)
        window_ms = self._cont_win_ms if window_ms is None else int(window_ms)
        mean_threshold = self._cont_mean if mean_threshold is None else float(
            mean_threshold)
        try:
            with wave.open(audio_file, 'rb') as wf:
                sr = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)
            win = max(1, int(sr * window_ms / 1000.0))
            need = max(1, int(min_ms / window_ms))
            consec = 0
            for i in range(0, len(audio) - win, win):
                if float(np.abs(audio[i:i+win]).mean()) > mean_threshold:
                    consec += 1
                    if consec >= need:
                        return True
                else:
                    consec = 0
            return False
        except Exception:
            return False

    def wait_for_silence(self, max_wait=None, check_interval=None, silence_threshold=None) -> bool:
        max_wait = self._sil_max_wait if max_wait is None else float(max_wait)
        check_interval = self._sil_interval if check_interval is None else float(
            check_interval)
        silence_threshold = self._sil_threshold if silence_threshold is None else float(
            silence_threshold)

        waited = 0.0
        logging.debug("🤫 Ожидание тишины...")
        while waited < max_wait:
            tmp = self.record_chunk(duration_seconds=check_interval)
            if not tmp:
                waited += check_interval
                continue
            try:
                if self.is_audio_silent(tmp, threshold=silence_threshold):
                    waited += check_interval
                    logging.debug(f"🤫 Тишина {waited:.1f}s")
                else:
                    logging.debug("🗣️ Речь продолжается...")
                    return False
            finally:
                Path(tmp).unlink(missing_ok=True)
        return True

    # ---------- операции записи более высокого уровня ----------

    def record_until_silence(self, max_duration=10, silence_timeout=1.5):
        """Запись до тишины, возвращает путь к итоговому WAV."""
        output_file = f"data/temp_recording_{int(time.time())}.wav"
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        total = 0
        silent = 0
        chunk_dur = 1
        chunks: list[str] = []
        logging.info(f"🎤 Запись до тишины (макс {max_duration}с)")

        try:
            while total < max_duration:
                chunk = self.record_chunk(duration_seconds=chunk_dur)
                if not chunk:
                    # считаем как тишину/пропуск
                    silent += chunk_dur
                    total += chunk_dur
                    if silent >= silence_timeout:
                        break
                    continue

                if self.is_audio_silent(chunk):
                    silent += chunk_dur
                    if silent >= silence_timeout:
                        Path(chunk).unlink(missing_ok=True)
                        break
                else:
                    silent = 0

                chunks.append(chunk)
                total += chunk_dur

            if chunks and self.combine_audio_files(chunks, output_file):
                return output_file
            return None
        finally:
            for f in chunks:
                Path(f).unlink(missing_ok=True)

    def combine_audio_files(self, audio_files, output_file):
        """Объединение нескольких WAV файлов в один."""
        try:
            with wave.open(output_file, 'wb') as out_wav:
                with wave.open(audio_files[0], 'rb') as first:
                    out_wav.setparams(first.getparams())
                for af in audio_files:
                    with wave.open(af, 'rb') as inp:
                        out_wav.writeframes(inp.readframes(inp.getnframes()))
            return True
        except Exception as e:
            logging.error(f"❌ Ошибка объединения аудио файлов: {e}")
            return False
