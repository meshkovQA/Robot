# robot/ai_agent/audio_manager.py
import pyaudio
import wave
import threading
import time
import logging
import subprocess
from pathlib import Path


class AudioManager:
    """Управление микрофоном и динамиками на Raspberry Pi"""

    def __init__(self, config=None):
        self.config = config or {}

        # Настройки аудио
        self.sample_rate = self.config.get('sample_rate', 16000)
        self.channels = self.config.get('channels', 1)
        self.chunk = self.config.get('chunk_size', 1024)
        self.format = pyaudio.paInt16

        # Устройства
        self.microphone_index = self.config.get('microphone_index', None)
        self.speaker_index = self.config.get('speaker_index', None)

        # PyAudio instance
        self.audio = None
        self.is_recording = False
        self.recording_thread = None

        self._initialize_audio()

    def _initialize_audio(self):
        """Инициализация PyAudio"""
        try:
            self.audio = pyaudio.PyAudio()
            self._detect_audio_devices()
            logging.info("✅ AudioManager инициализирован")
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации аудио: {e}")
            self.audio = None

    def _detect_audio_devices(self):
        """Автоматическое определение аудио устройств"""
        if not self.audio:
            return

        logging.info("🔍 Поиск аудио устройств...")

        device_count = self.audio.get_device_count()
        usb_microphones = []
        speakers = []

        for i in range(device_count):
            try:
                device_info = self.audio.get_device_info_by_index(i)
                device_name = device_info['name'].lower()

                # Поиск USB микрофонов
                if ('usb' in device_name or 'microphone' in device_name) and device_info['maxInputChannels'] > 0:
                    usb_microphones.append((i, device_info['name']))
                    logging.info(
                        f"🎤 Найден микрофон: {device_info['name']} (index: {i})")

                # Поиск динамиков/MAX98357
                if ('max98357' in device_name or 'i2s' in device_name or
                        device_info['maxOutputChannels'] > 0):
                    speakers.append((i, device_info['name']))
                    logging.info(
                        f"🔊 Найден динамик: {device_info['name']} (index: {i})")

            except Exception as e:
                continue

        # Автоматический выбор устройств
        if usb_microphones and self.microphone_index is None:
            self.microphone_index = usb_microphones[0][0]
            logging.info(f"✅ Выбран микрофон: {usb_microphones[0][1]}")

        if speakers and self.speaker_index is None:
            self.speaker_index = speakers[0][0]
            logging.info(f"✅ Выбран динамик: {speakers[0][1]}")

    def record_audio(self, duration_seconds=5, output_file=None):
        """Запись аудио с микрофона через arecord (более надежно для USB Audio)"""
        if output_file is None:
            output_file = f"data/temp_recording_{int(time.time())}.wav"

        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        try:
            logging.info(f"🎤 Запись аудио {duration_seconds}с в {output_file}")

            # Используем arecord с plughw для USB микрофона
            cmd = [
                'arecord',
                '-D', f'plughw:{self.microphone_index},0',
                '-r', str(self.sample_rate),
                '-c', str(self.channels),
                '-f', 'S16_LE',
                '-d', str(duration_seconds),
                output_file
            ]

            result = subprocess.run(cmd, capture_output=True,
                                    text=True, timeout=duration_seconds + 5)

            if result.returncode == 0 and Path(output_file).exists():
                file_size = Path(output_file).stat().st_size
                logging.info(
                    f"✅ Запись сохранена: {output_file} ({file_size} байт)")
                return output_file
            else:
                logging.error(f"❌ Ошибка arecord: {result.stderr}")
                return None

        except Exception as e:
            logging.error(f"❌ Ошибка записи аудио: {e}")
            return None

    def start_continuous_recording(self, callback=None):
        """Начать непрерывную запись (для голосовой активации)"""
        if self.is_recording:
            logging.warning("Запись уже идет")
            return

        self.is_recording = True
        self.recording_thread = threading.Thread(
            target=self._continuous_recording_loop,
            args=(callback,)
        )
        self.recording_thread.daemon = True
        self.recording_thread.start()
        logging.info("🎤 Начата непрерывная запись")

    def stop_continuous_recording(self):
        """Остановить непрерывную запись"""
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.join()
        logging.info("⏹️ Остановлена непрерывная запись")

    def _continuous_recording_loop(self, callback):
        """Цикл непрерывной записи"""
        if not self.audio or self.microphone_index is None:
            return

        try:
            stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.microphone_index,
                frames_per_buffer=self.chunk
            )

            while self.is_recording:
                try:
                    data = stream.read(self.chunk, exception_on_overflow=False)

                    # Простая детекция уровня звука
                    import numpy as np
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    volume = np.abs(audio_data).mean()

                    # Если громкость выше порога - вызываем callback
                    if volume > 500 and callback:  # Настраиваемый порог
                        callback(data, volume)

                except Exception as e:
                    if self.is_recording:
                        logging.error(f"Ошибка в цикле записи: {e}")
                    break

            stream.stop_stream()
            stream.close()

        except Exception as e:
            logging.error(f"Ошибка непрерывной записи: {e}")

    def play_audio(self, audio_file):
        """Воспроизведение аудио через динамики"""
        if not audio_file or not Path(audio_file).exists():
            logging.error(f"❌ Файл не найден: {audio_file}")
            return False

        try:
            # Используем aplay для воспроизведения (стандартно в RPi OS)
            if self.speaker_index is not None:
                # Если знаем индекс устройства
                cmd = f"aplay -D plughw:{self.speaker_index},0 {audio_file}"
            else:
                # Используем дефолтное устройство
                cmd = f"aplay {audio_file}"

            logging.info(f"🔊 Воспроизведение: {audio_file}")
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                logging.info("✅ Воспроизведение завершено")
                return True
            else:
                logging.error(f"❌ Ошибка воспроизведения: {result.stderr}")
                return False

        except Exception as e:
            logging.error(f"❌ Ошибка воспроизведения: {e}")
            return False

    def play_audio_pyaudio(self, audio_file):
        """Воспроизведение через PyAudio (альтернативный метод)"""
        if not self.audio or not Path(audio_file).exists():
            return False

        try:
            # Открываем WAV файл
            with wave.open(audio_file, 'rb') as wf:
                # Настройки из файла
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()

                # Определяем формат
                if sample_width == 1:
                    format = pyaudio.paInt8
                elif sample_width == 2:
                    format = pyaudio.paInt16
                elif sample_width == 4:
                    format = pyaudio.paInt32
                else:
                    format = pyaudio.paInt16

                # Открываем поток для воспроизведения
                stream = self.audio.open(
                    format=format,
                    channels=channels,
                    rate=framerate,
                    output=True,
                    output_device_index=self.speaker_index,
                    frames_per_buffer=self.chunk
                )

                # Воспроизводим по частям
                data = wf.readframes(self.chunk)
                while data:
                    stream.write(data)
                    data = wf.readframes(self.chunk)

                # Закрываем поток
                stream.stop_stream()
                stream.close()

                logging.info(f"✅ Воспроизведение завершено: {audio_file}")
                return True

        except Exception as e:
            logging.error(f"❌ Ошибка воспроизведения PyAudio: {e}")
            return False

    def get_audio_devices_info(self):
        """Получить информацию об аудио устройствах"""
        if not self.audio:
            return {"error": "PyAudio не инициализирован"}

        devices = {
            "microphones": [],
            "speakers": [],
            "selected_microphone": self.microphone_index,
            "selected_speaker": self.speaker_index
        }

        try:
            device_count = self.audio.get_device_count()
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)

                device_data = {
                    "index": i,
                    "name": device_info['name'],
                    "max_input_channels": device_info['maxInputChannels'],
                    "max_output_channels": device_info['maxOutputChannels'],
                    "default_sample_rate": device_info['defaultSampleRate']
                }

                if device_info['maxInputChannels'] > 0:
                    devices["microphones"].append(device_data)

                if device_info['maxOutputChannels'] > 0:
                    devices["speakers"].append(device_data)

            return devices

        except Exception as e:
            logging.error(f"Ошибка получения списка устройств: {e}")
            return {"error": str(e)}

    def test_audio_system(self):
        """Тест аудио системы"""
        results = {
            "microphone_test": False,
            "speaker_test": False,
            "devices_detected": False
        }

        try:
            # Тест устройств
            devices = self.get_audio_devices_info()
            if not devices.get("error"):
                results["devices_detected"] = True
                logging.info(
                    f"Найдено микрофонов: {len(devices['microphones'])}")
                logging.info(f"Найдено динамиков: {len(devices['speakers'])}")

            # Тест записи
            if self.microphone_index is not None:
                test_file = "data/audio_test.wav"
                recorded_file = self.record_audio(
                    duration_seconds=2, output_file=test_file)
                if recorded_file and Path(recorded_file).exists():
                    results["microphone_test"] = True
                    logging.info("✅ Тест микрофона пройден")

                    # Тест воспроизведения
                    if self.play_audio(recorded_file):
                        results["speaker_test"] = True
                        logging.info("✅ Тест динамиков пройден")

                    # Удаляем тестовый файл
                    Path(recorded_file).unlink(missing_ok=True)

            return results

        except Exception as e:
            logging.error(f"Ошибка тестирования аудио: {e}")
            return results

    def __del__(self):
        """Очистка ресурсов"""
        if self.is_recording:
            self.stop_continuous_recording()

        if self.audio:
            self.audio.terminate()
