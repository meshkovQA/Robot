# robot/ai_agent/simple_kws.py
from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np


def _read_wav_mono_float(wav_path: str) -> Tuple[np.ndarray, int]:
    """Чтение WAV PCM16 -> mono float32 [-1..1], возвращает (samples, sr)."""
    with wave.open(wav_path, "rb") as wf:
        n_ch = wf.getnchannels()
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_ch == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)
    audio = np.nan_to_num(audio)
    return audio, int(sr)


def _center_crop(audio: np.ndarray, sr: int, target_sec: float = 1.0) -> np.ndarray:
    """Берём центральное окно ~target_sec (если короче — паддинг нулями)."""
    target = int(target_sec * sr)
    if len(audio) == 0:
        return np.zeros(target, dtype=np.float32)
    if len(audio) >= target:
        start = (len(audio) - target) // 2
        return audio[start:start + target]
    out = np.zeros(target, dtype=np.float32)
    start = (target - len(audio)) // 2
    out[start:start + len(audio)] = audio
    return out


def _embed_1s(audio_1s: np.ndarray, sr: int) -> np.ndarray:
    """
    Простая компактная эмбеддинга:
    - Ханново окно
    - RFFT (n=4096)
    - усредняем по 64 диапазона частот
    - log(1 + mag), L2-нормализация
    """
    nfft = 4096
    x = audio_1s.astype(np.float32)
    if len(x) == 0:
        return np.zeros(64, dtype=np.float32)

    # окно той же длины, что и сигнал, если меньше nfft — нули дорисует rfft
    w = np.hanning(len(x)).astype(np.float32)
    xw = x * w
    spec = np.fft.rfft(xw, n=nfft)
    mag = np.abs(spec).astype(np.float32)

    # делим спектр на 64 "короба" и берём среднее в каждом
    bands = 64
    # чтобы ровно делилось, обрежем с конца
    usable = (len(mag) // bands) * bands
    if usable == 0:
        v = np.zeros(bands, dtype=np.float32)
    else:
        mag = mag[:usable]
        v = mag.reshape(bands, -1).mean(axis=1)

    v = np.log1p(v)  # log-компрессия
    norm = np.linalg.norm(v) + 1e-8
    v = v / norm
    return v.astype(np.float32)


def _wav_to_embedding(wav_path: str) -> Optional[np.ndarray]:
    try:
        audio, sr = _read_wav_mono_float(wav_path)
        # берём ~1с центр — устойчивее к начальным/конечным паузам
        a1 = _center_crop(audio, sr, target_sec=1.0)
        emb = _embed_1s(a1, sr)
        return emb
    except Exception as e:
        logging.error(
            "SimpleKWS: ошибка чтения/преобразования '%s': %s", wav_path, e)
        return None


class SimpleKWS:
    """
    Простейший KWS по косинусному сходству эмбеддингов.
    - enroll_*: загружаем эталоны слова (несколько WAV)
    - score(wav): максимум косинусного сходства с эталонами
    - detect(wav): (bool, score) по порогу
    """

    def __init__(self, threshold: float = 0.82):
        self.threshold = float(threshold)
        self._templates: List[np.ndarray] = []
        logging.info("SimpleKWS: threshold=%.3f", self.threshold)

    # ---------- обучение / загрузка шаблонов ----------
    def enroll_dir(self, directory: str) -> int:
        p = Path(directory)
        if not p.exists():
            logging.warning("SimpleKWS: каталог с шаблонами не найден: %s", p)
            return 0

        wavs = sorted([*p.glob("*.wav"), *p.glob("*.WAV")])
        loaded = 0
        for w in wavs:
            emb = _wav_to_embedding(str(w))
            if emb is not None:
                self._templates.append(emb)
                loaded += 1
                logging.info("SimpleKWS: добавлен шаблон %s", w.name)

        if loaded == 0:
            logging.warning("SimpleKWS: не найдено валидных WAV в %s", p)
        else:
            logging.info("SimpleKWS: загружено шаблонов: %d", loaded)
        return loaded

    def enroll_file(self, wav_path: str) -> bool:
        emb = _wav_to_embedding(wav_path)
        if emb is None:
            return False
        self._templates.append(emb)
        logging.info("SimpleKWS: добавлен шаблон из файла %s", wav_path)
        return True

    # ---------- инференс ----------
    def score(self, wav_path: str) -> float:
        """
        Возвращает максимум косинусного сходства [0..1] с шаблонами.
        Если шаблонов нет — вернёт 0.0.
        """
        if not self._templates:
            logging.warning("SimpleKWS: нет шаблонов — score=0.0")
            return 0.0

        emb = _wav_to_embedding(wav_path)
        if emb is None:
            return 0.0

        # косинус: dot(emb, tmpl) (оба L2-нормированы)
        sims = [float(np.dot(emb, t)) for t in self._templates]
        smax = max(sims) if sims else 0.0
        logging.info("SimpleKWS: score=%.3f (templates=%d)",
                     smax, len(self._templates))
        return smax

    def detect(self, wav_path: str) -> Tuple[bool, float]:
        """Удобный помощник: (passed, score)."""
        s = self.score(wav_path)
        ok = s >= self.threshold
        logging.info(
            "SimpleKWS: detect -> %s (score=%.3f, thr=%.3f)", ok, s, self.threshold)
        return ok, s
