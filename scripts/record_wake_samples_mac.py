# scripts/record_wake_samples_mac.py
import sounddevice as sd
import numpy as np
import wave
from pathlib import Path
import time

DEVICE_INDEX = 4          # <-- твой Usb_Mic на macOS
SAMPLE_RATE = 48000       # как в конфиге робота
CHANNELS = 1
DURATION = 1.0            # 1 секунда на сэмпл
SAVE_DIR = Path("data/wake_samples")  # запускай из корня проекта Robot


def record_once(idx: int):
    print(f"🎤 Скажи 'винди' — запись #{idx} (1 сек)")
    sd.default.device = (DEVICE_INDEX, None)  # (input, output)
    audio = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
    )
    sd.wait()

    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    path = SAVE_DIR / f"wake_{idx:02d}.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    print(f"✅ Сохранено: {path}")


def main():
    try:
        n = int(input("Сколько образцов записать? (рекомендую 10–15): "))
    except Exception:
        n = 10
    print("\nСовет: говори с разной громкостью/интонацией и немного разной дистанцией.\n")
    time.sleep(0.5)
    for i in range(1, n + 1):
        input(f"Нажми Enter и сразу произнеси 'винди' ({i}/{n})...")
        record_once(i)


if __name__ == "__main__":
    # На macOS убедись, что у Терминала есть доступ к микрофону:
    # System Settings → Privacy & Security → Microphone
    main()
