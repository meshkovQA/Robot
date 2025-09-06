# robot/ai_agent/simple_kws.py
import wave
import numpy as np
from pathlib import Path
from python_speech_features import mfcc, delta


def _read_wav_mono_16le(path: str):
    with wave.open(path, 'rb') as wf:
        assert wf.getsampwidth() == 2, "need 16-bit PCM"
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        ch = wf.getnchannels()
        if ch > 1:
            data = data.reshape(-1, ch).mean(axis=1).astype(np.int16)
        sr = wf.getframerate()
    return data.astype(np.float32) / 32768.0, sr


def _mfcc_features(sig: np.ndarray, sr: int) -> np.ndarray:
    # 25ms окно / 10ms шаг — стандарт
    M = mfcc(sig, samplerate=sr, winlen=0.025, winstep=0.01,
             numcep=13, nfilt=26, nfft=512, lowfreq=50, highfreq=None, preemph=0.97)
    D = delta(M, 2)
    DD = delta(D, 2)
    FE = np.hstack([M, D, DD])  # 39-мерный вектор на кадр
    return FE


def _template_from_wav(path: str) -> np.ndarray:
    sig, sr = _read_wav_mono_16le(path)
    if len(sig) < sr * 0.15:   # короче 150мс — мусор
        return None
    F = _mfcc_features(sig, sr)
    return F.mean(axis=0)      # усредняем по времени — устойчиво и дёшево


class SimpleKWS:
    """
    Простейший офлайн кейворд-споттер по MFCC:
    - обучается на 3-10 твоих образцах "винди" (wav 16k..48k, mono, 16-bit)
    - во время работы сравнивает средний MFCC чанка с шаблонами
    - метрика: косинусная близость; выше порога — триггер
    """

    def __init__(self, threshold: float = 0.82):
        self.templates = []   # список средних MFCC (np.ndarray, shape=[39])
        self.threshold = float(threshold)

    def enroll_dir(self, dir_path: str):
        p = Path(dir_path)
        for wav in sorted(p.glob("*.wav")):
            t = _template_from_wav(str(wav))
            if t is not None:
                self.templates.append(t)
        return len(self.templates)

    def enroll_files(self, files: list[str]):
        for f in files:
            t = _template_from_wav(f)
            if t is not None:
                self.templates.append(t)
        return len(self.templates)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        na = np.linalg.norm(a) + 1e-9
        nb = np.linalg.norm(b) + 1e-9
        return float(np.dot(a, b) / (na * nb))

    def score_chunk(self, wav_path: str) -> float:
        if not self.templates:
            return 0.0
        sig, sr = _read_wav_mono_16le(wav_path)
        # слишком короткий/тихий — отвергаем
        if len(sig) < sr * 0.15 or float(np.abs(sig).mean()) < 0.005:
            return 0.0
        F = _mfcc_features(sig, sr).mean(axis=0)
        sims = [self._cosine(F, t) for t in self.templates]
        return max(sims) if sims else 0.0

    def is_hotword(self, wav_path: str) -> bool:
        return self.score_chunk(wav_path) >= self.threshold
