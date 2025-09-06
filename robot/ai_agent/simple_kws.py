# robot/ai_agent/simple_kws.py
from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np


def _read_wav_mono_float(wav_path: str) -> Tuple[np.ndarray, int]:
    with wave.open(wav_path, "rb") as wf:
        n_ch = wf.getnchannels()
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_ch == 2:
        x = x.reshape(-1, 2).mean(axis=1)
    x = np.nan_to_num(x)
    return x, int(sr)


def _center_crop(audio: np.ndarray, sr: int, target_sec: float = 1.0) -> np.ndarray:
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
    # простая спектральная эмбеддинга + нормализация
    nfft = 4096
    x = audio_1s.astype(np.float32)
    if len(x) == 0:
        return np.zeros(64, dtype=np.float32)

    # лёгкая АЧХ: подчёркиваем 200–2500 Гц (речь)
    # делаем через маску в спектре
    spec = np.fft.rfft(x * np.hanning(len(x)), n=nfft)
    mag = np.abs(spec).astype(np.float32)

    freqs = np.fft.rfftfreq(nfft, d=1.0 / sr)
    mask = ((freqs >= 200) & (freqs <= 2500)).astype(np.float32)
    mag *= (0.7 + 0.3 * mask)  # слегка подавляем внеполосные частоты

    bands = 64
    usable = (len(mag) // bands) * bands
    if usable == 0:
        v = np.zeros(bands, dtype=np.float32)
    else:
        m = mag[:usable].reshape(bands, -1).mean(axis=1)
        v = np.log1p(m)

    v /= (np.linalg.norm(v) + 1e-8)
    return v.astype(np.float32)


def _wav_to_embedding(wav_path: str) -> Optional[np.ndarray]:
    try:
        audio, sr = _read_wav_mono_float(wav_path)
        a1 = _center_crop(audio, sr, 1.0)
        emb = _embed_1s(a1, sr)
        return emb
    except Exception as e:
        logging.error(
            "SimpleKWS: ошибка чтения/преобразования '%s': %s", wav_path, e)
        return None


class SimpleKWS:
    """
    KWS на косинусном сходстве эмбеддингов.
    - enroll_dir / enroll_file: добавляет ПОЛОЖИТЕЛЬНЫЕ шаблоны
    - enroll_neg_dir / enroll_neg_file: добавляет ОТРИЦАТЕЛЬНЫЕ (антишаблоны)
    - score(): возвращает (pos_max, neg_max, margin)
    - detect(): bool по margin и порогу
    """

    def __init__(self, threshold: float = 0.82, margin_alpha: float = 1.0):
        self.threshold = float(threshold)
        # вес "штрафа" за похожесть на антишаблоны
        self.alpha = float(margin_alpha)
        self._pos: List[np.ndarray] = []
        self._neg: List[np.ndarray] = []
        logging.info("SimpleKWS: threshold=%.3f, alpha=%.2f",
                     self.threshold, self.alpha)

    # --------- загрузка шаблонов ----------
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
                self._pos.append(emb)
                loaded += 1
                logging.info("SimpleKWS: добавлен POS шаблон %s", w.name)
        if loaded == 0:
            logging.warning("SimpleKWS: не найдено валидных WAV в %s", p)
        else:
            logging.info("SimpleKWS: загружено POS шаблонов: %d", loaded)
        return loaded

    def enroll_file(self, wav_path: str) -> bool:
        emb = _wav_to_embedding(wav_path)
        if emb is None:
            return False
        self._pos.append(emb)
        logging.info("SimpleKWS: добавлен POS шаблон из файла %s", wav_path)
        return True

    def enroll_neg_dir(self, directory: str) -> int:
        p = Path(directory)
        if not p.exists():
            return 0
        wavs = sorted([*p.glob("*.wav"), *p.glob("*.WAV")])
        loaded = 0
        for w in wavs:
            emb = _wav_to_embedding(str(w))
            if emb is not None:
                self._neg.append(emb)
                loaded += 1
                logging.info("SimpleKWS: добавлен NEG шаблон %s", w.name)
        if loaded:
            logging.info("SimpleKWS: загружено NEG шаблонов: %d", loaded)
        return loaded

    def enroll_neg_file(self, wav_path: str) -> bool:
        emb = _wav_to_embedding(wav_path)
        if emb is None:
            return False
        self._neg.append(emb)
        logging.info("SimpleKWS: добавлен NEG шаблон из файла %s", wav_path)
        return True

    # --------- инференс ----------
    def score(self, wav_path: str) -> Tuple[float, float, float]:
        """
        Возвращает (pos_max, neg_max, margin=pos_max - alpha*neg_max).
        Если нет шаблонов pos -> 0,0,0.
        """
        if not self._pos:
            logging.warning("SimpleKWS: нет POS шаблонов — score=0")
            return 0.0, 0.0, 0.0

        emb = _wav_to_embedding(wav_path)
        if emb is None:
            return 0.0, 0.0, 0.0

        pos = max((float(np.dot(emb, t)) for t in self._pos), default=0.0)
        neg = max((float(np.dot(emb, t))
                  for t in self._neg), default=0.0) if self._neg else 0.0
        margin = pos - self.alpha * neg
        logging.info("SimpleKWS: pos=%.3f neg=%.3f margin=%.3f thr=%.3f",
                     pos, neg, margin, self.threshold)
        return pos, neg, margin

    def detect(self, wav_path: str) -> Tuple[bool, float, float, float]:
        pos, neg, margin = self.score(wav_path)
        ok = margin >= self.threshold
        logging.info("SimpleKWS: detect -> %s (pos=%.3f, neg=%.3f, margin=%.3f ≥ thr=%.3f)",
                     ok, pos, neg, margin, self.threshold)
        return ok, pos, neg, margin
