# robot/ai_agent/yandex_tts_client.py
from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests


class YandexTTSClient:
    ENDPOINT = "https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis"

    def __init__(
        self,
        api_key: Optional[str] = None,
        iam_token: Optional[str] = None,
        folder_id: Optional[str] = None,
        default_voice: str = "alexander",
        default_role: str = "good",
        default_container: str = "MP3",
        sample_rate_hz: int = 48000,
        unsafe_mode: bool = True,
        timeout: int = 30,
    ):
        if not api_key and not iam_token:
            raise ValueError("Для Yandex TTS нужен api_key или iam_token")

        self.api_key = api_key
        self.iam_token = iam_token
        self.folder_id = folder_id
        self.default_voice = default_voice
        self.default_role = default_role
        self.default_container = default_container
        self.sample_rate_hz = sample_rate_hz
        self.timeout = timeout
        self.unsafe_mode = unsafe_mode
        self._session = requests.Session()

    def synthesize_to_file(
        self,
        text: str,
        out_dir: str | Path = "data/temp",
        file_prefix: str = "yandex_tts_",
        voice: Optional[str] = None,
        role: Optional[str] = None,
        container: Optional[str] = None,
        speed: Optional[float] = None,
        volume_lufs: Optional[float] = None,
    ) -> str:
        if not text or not text.strip():
            raise ValueError("Пустой текст для синтеза")

        voice = voice or self.default_voice
        role = role or self.default_role
        container = (container or self.default_container).upper()

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = self._container_ext(container)
        ts = int(time.time() * 1000)
        out_path = out_dir / f"{file_prefix}{ts}.{ext}"

        logging.info(
            f"📝→🔊 Yandex TTS: voice={voice}, role={role}, fmt={container}, sr={self.sample_rate_hz}")

        self._request_and_write(
            text=text,
            outfile=out_path,
            voice=voice,
            role=role,
            container=container,
            speed=speed,
            volume_lufs=volume_lufs,
        )

        size = out_path.stat().st_size if out_path.exists() else 0
        if size < 1000:
            raise RuntimeError(
                f"Подозрительно маленький TTS файл: {size} байт")

        logging.info(f"✅ Yandex TTS файл создан: {out_path} ({size} байт)")
        return str(out_path)

    def _headers(self) -> dict:
        hdrs = {}
        if self.api_key:
            hdrs["Authorization"] = f"Api-Key {self.api_key}"
        elif self.iam_token:
            hdrs["Authorization"] = f"Bearer {self.iam_token}"
            if self.folder_id:
                hdrs["x-folder-id"] = self.folder_id
        return hdrs

    def _request_body(
        self,
        *,
        text: str,
        voice: str,
        role: Optional[str],
        container: str,
        speed: Optional[float],
        volume_lufs: Optional[float],
    ) -> dict:
        hints = [{"voice": voice}]
        if role:
            hints.append({"role": role})
        if speed is not None:
            hints.append({"speed": str(speed)})
        # if volume_lufs is not None:
        #     hints.append({"volume": str(volume_lufs)})

        return {
            "text": text,
            "hints": hints,
            "outputAudioSpec": {
                "containerAudio": {"containerAudioType": container},
            },
            "unsafeMode": bool(self.unsafe_mode)
        }

    def _request_and_write(
        self,
        *,
        text: str,
        outfile: Path,
        voice: str,
        role: Optional[str],
        container: str,
        speed: Optional[float],
        volume_lufs: Optional[float],
    ) -> None:
        body = self._request_body(
            text=text,
            voice=voice,
            role=role,
            container=container,
            speed=speed,
            volume_lufs=volume_lufs,
        )
        with self._session.post(
            self.ENDPOINT,
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                err = resp.text if hasattr(resp, "text") else "<no body>"
                raise RuntimeError(
                    f"Yandex TTS HTTP {resp.status_code}: {err}")

            with open(outfile, "wb") as f:
                for line in resp.iter_lines(decode_unicode=False):
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                        data_b64 = obj.get("result", {}).get(
                            "audioChunk", {}).get("data")
                        if data_b64:
                            f.write(base64.b64decode(data_b64))
                    except json.JSONDecodeError:
                        continue

    @staticmethod
    def _container_ext(container: str) -> str:
        c = container.upper()
        if c == "MP3":
            return "mp3"
        if c == "OGG_OPUS":
            return "ogg"
        return "wav"
