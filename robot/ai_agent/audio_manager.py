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

        rec = (self.config.get('record') or {}) if isinstance(self.config.get(
            'record'), dict) else (self.config.get('audio', {}).get('record') or {})

        trim = (self.config.get('trim') or {}) if isinstance(self.config.get(
            'trim'), dict) else (self.config.get('audio', {}).get('trim') or {})

        self._rec_cfg = {
            "chunk_ms": int(rec.get("chunk_ms", 20)),
            "max_duration": float(rec.get("max_duration", 10)),
            "silence_timeout": float(rec.get("silence_timeout", 0.45)),
            "pre_roll_sec": float(rec.get("pre_roll_sec", 0.35)),
            "tail_ms": int(rec.get("tail_ms", 300)),
            "end_peak_thr": float(rec.get("end_peak_thr", 1200.0)),
            "max_initial_silence": float(rec.get("max_initial_silence", 3.0)),
            "dynamic_end_avg": {
                "enabled": bool(((rec.get("dynamic_end_avg") or {}).get("enabled", True))),
                "base_silence_threshold": float(((rec.get("dynamic_end_avg") or {}).get("base_silence_threshold", self._sil_threshold))),
                "noise_std_mult": float(((rec.get("dynamic_end_avg") or {}).get("noise_std_mult", 1.5))),
            }
        }

        self._trim_cfg = {
            "enabled": bool(trim.get("enabled", True)),
            "window_ms": int(trim.get("window_ms", 20)),
            "head_ms": int(trim.get("head_ms", 400)),
            "min_speech_end_ms": int(trim.get("min_speech_end_ms", 150)),
            "base_threshold": float(trim.get("base_threshold", 200.0)),
            "noise_std_mult": float(trim.get("noise_std_mult", 1.5)),
        }

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

    def record_until_silence(
        self,
        max_duration=None,
        pre_roll_files: list[str] | None = None
    ):
        import subprocess
        import wave
        from collections import deque
        import numpy as np

        # значения из JSON
        cfg = self._rec_cfg
        chunk_ms = int(cfg["chunk_ms"])
        silence_timeout = float(cfg["silence_timeout"])
        pre_roll_sec = float(cfg["pre_roll_sec"])
        tail_ms = int(cfg["tail_ms"])
        end_peak_thr = float(cfg["end_peak_thr"])
        max_initial_sil = float(cfg["max_initial_silence"])
        dyn = cfg["dynamic_end_avg"]
        base_sil_thr = float(dyn["base_silence_threshold"])
        noise_k = float(dyn["noise_std_mult"])
        use_dyn = bool(dyn["enabled"])

        if max_duration is None:
            max_duration = float(cfg["max_duration"])

        output_file = f"data/temp_recording_{int(time.time())}.wav"
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        # базовые пороги старта речи из wake-секциии
        min_avg = float(self._min_avg)
        min_peak = float(self._min_peak)

        cmd = [
            'arecord',
            '-D', f'plughw:{self.microphone_index},0',
            '-r', str(self.sample_rate),
            '-c', str(self.channels),
            '-f', 'S16_LE',
            '-t', 'raw'
        ]
        logging.info("🎤 Потоковая запись до тишины: %s", " ".join(cmd))
        logging.info(
            "🎛️ record: chunk=%dms, pre_roll=%.2fs, tail=%dms, stop_silence=%.2fs, "
            "end_peak_thr=%.0f, base_sil_thr=%.1f, dyn_k=%.2f, max_init_sil=%.1fs",
            chunk_ms, pre_roll_sec, tail_ms, silence_timeout,
            end_peak_thr, base_sil_thr, noise_k, max_initial_sil
        )

        proc = None
        started_speaking = False
        silence_run = 0.0
        total_time = 0.0
        initial_sil = 0.0

        bytes_per_sample = 2
        frame_bytes = int(self.sample_rate * (chunk_ms / 1000.0)
                          ) * bytes_per_sample * int(self.channels)
        chunk_sec = chunk_ms / 1000.0

        preroll_chunks = deque(maxlen=max(1, int(pre_roll_sec / chunk_sec)))
        tail_chunks = deque(maxlen=max(1, int(tail_ms / chunk_ms)))
        body = bytearray()

        noise_levels = []                # средние до старта речи
        end_avg_thr = base_sil_thr       # инициализация

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            stdout = proc.stdout
            if stdout is None:
                raise RuntimeError("arecord stdout is None")

            while total_time < max_duration:
                data = stdout.read(frame_bytes)
                if not data:
                    time.sleep(0.003)
                    continue

                audio_i16 = np.frombuffer(data, dtype=np.int16)
                if audio_i16.size == 0:
                    total_time += chunk_sec
                    continue

                avg = float(np.abs(audio_i16).mean())
                peak = float(np.abs(audio_i16).max())

                if not started_speaking:
                    # копим фон и преролл
                    noise_levels.append(avg)
                    preroll_chunks.append(data)

                    # обновляем динамический порог конца речи после накопления фона
                    if use_dyn and len(noise_levels) >= max(3, int(pre_roll_sec / chunk_sec)):
                        nm = float(np.mean(noise_levels))
                        ns = float(np.std(noise_levels)) if len(
                            noise_levels) > 1 else 0.0
                        end_avg_thr = max(base_sil_thr, nm + noise_k * ns)

                    # старт речи по гейтам
                    if avg > min_avg and peak > min_peak:
                        for ch in preroll_chunks:
                            body.extend(ch)
                        body.extend(data)
                        started_speaking = True
                        silence_run = 0.0
                        tail_chunks.clear()
                    else:
                        # защиты от вечного ожидания речи
                        initial_sil += chunk_sec
                        if initial_sil >= max_initial_sil:
                            logging.info(
                                "🤫 Не дождались речи (%.1fs тишины) — выходим без записи", initial_sil)
                            break
                else:
                    # уже пишем
                    body.extend(data)
                    tail_chunks.append(data)

                    # критерий остановки: низкий avg И низкий peak достаточное время
                    if (avg < end_avg_thr) and (peak < end_peak_thr):
                        silence_run += chunk_sec
                        if silence_run >= silence_timeout:
                            logging.info("✅ Остановка: тишина %.2fs (thr_avg=%.1f, thr_peak=%.0f)",
                                         silence_run, end_avg_thr, end_peak_thr)
                            break
                    else:
                        silence_run = 0.0
                        tail_chunks.clear()

                total_time += chunk_sec

            # если речи не было — ничего не сохраняем
            if not started_speaking:
                try:
                    if proc and proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
                return None

            # удаляем хвост (накопленная тишина)
            for _ in range(len(tail_chunks)):
                last = tail_chunks.pop()
                body = body[:len(body)-len(last)]

            with wave.open(output_file, 'wb') as wf_out:
                wf_out.setnchannels(int(self.channels))
                wf_out.setsampwidth(2)
                wf_out.setframerate(int(self.sample_rate))
                wf_out.writeframes(body)

            return output_file

        except Exception as e:
            logging.error("❌ Ошибка потоковой записи: %s", e)
            try:
                Path(output_file).unlink(missing_ok=True)
            except Exception:
                pass
            return None
        finally:
            try:
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.2)
                    except Exception:
                        proc.kill()
            except Exception:
                pass

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

    def trim_silence_end(self, audio_file: str, threshold: float = 200, min_speech_end_ms: int = 150) -> str | None:
        try:
            import wave
            import numpy as np

            cfg = self._trim_cfg
            if not cfg["enabled"]:
                return audio_file

            window_ms = int(cfg["window_ms"])
            head_ms = int(cfg["head_ms"])
            base_threshold = float(cfg["base_threshold"])
            noise_std_mult = float(cfg["noise_std_mult"])
            min_speech_end_ms = int(cfg["min_speech_end_ms"])

            with wave.open(audio_file, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
                params = wf.getparams()

            if len(frames) == 0:
                return None

            audio = np.frombuffer(frames, dtype=np.int16)
            sr = params.framerate

            # фон по head_ms из JSON
            head_samples = max(1, int(sr * head_ms / 1000.0))
            head = np.abs(audio[:head_samples]).astype(np.float32)
            base = float(head.mean()) if head.size else 0.0
            std = float(head.std()) if head.size > 1 else 0.0
            dyn_thr = max(base_threshold, base + noise_std_mult * std)

            # окно из JSON
            win = max(1, int(sr * window_ms / 1000.0))
            last_pos = len(audio)

            for i in range(len(audio) - win, 0, -win):
                w = np.abs(audio[i:i+win]).astype(np.float32)
                if w.mean() > dyn_thr:
                    tail = int(sr * min_speech_end_ms / 1000.0)
                    last_pos = min(i + win + tail, len(audio))
                    break

            if last_pos == len(audio):
                return audio_file

            trimmed = audio[:last_pos]
            trimmed_file = audio_file.replace('.wav', '_trimmed.wav')
            with wave.open(trimmed_file, 'wb') as wf_out:
                wf_out.setparams(params)
                wf_out.writeframes(trimmed.tobytes())

            logging.info("✂️ Динамическая обрезка: было %.2fs → стало %.2fs",
                         len(audio)/sr, len(trimmed)/sr)
            return trimmed_file

        except Exception as e:
            logging.error(f"❌ Ошибка обрезки тишины: {e}")
            return audio_file
