# robot/ai_agent/yandex_stt_client.py
from __future__ import annotations

from flask import logging
from yandex.cloud.ai.stt.v3 import stt_service_pb2_grpc
from yandex.cloud.ai.stt.v3 import stt_pb2
import grpc
from typing import Optional
import logging


# импортируй сгенерированные proto из твоего пути

_YC_ENDPOINT = "stt.api.cloud.yandex.net:443"
_CHUNK_SIZE = 4000  # байт; можно 8-16К


class YandexSTTClient:
    def __init__(self, api_key: Optional[str] = None, iam_token: Optional[str] = None,
                 sample_rate: int = 48000, channels: int = 1,
                 profanity_filter: bool = True, model: str = "general"):
        if not api_key and not iam_token:
            raise ValueError(
                "Provide either api_key or iam_token for Yandex STT")

        self._metadata = (
            ('authorization', f'Api-Key {api_key}') if api_key
            else ('authorization', f'Bearer {iam_token}')
        )
        self._sample_rate = int(sample_rate)
        self._channels = int(channels)
        self._profanity = bool(profanity_filter)
        self._model = model

        cred = grpc.ssl_channel_credentials()
        self._channel = grpc.secure_channel(_YC_ENDPOINT, cred)
        self._stub = stt_service_pb2_grpc.RecognizerStub(self._channel)

        # заранее соберём опции с нужным аудиоформатом
        self._session_opts = stt_pb2.StreamingOptions(
            recognition_model=stt_pb2.RecognitionModelOptions(
                model=self._model,
                audio_format=stt_pb2.AudioFormatOptions(
                    raw_audio=stt_pb2.RawAudio(
                        audio_encoding=stt_pb2.RawAudio.LINEAR16_PCM,
                        sample_rate_hertz=self._sample_rate,
                        audio_channel_count=self._channels,
                    )
                ),
                text_normalization=stt_pb2.TextNormalizationOptions(
                    text_normalization=stt_pb2.TextNormalizationOptions.TEXT_NORMALIZATION_ENABLED,
                    profanity_filter=self._profanity,
                    literature_text=False,
                ),
                language_restriction=stt_pb2.LanguageRestrictionOptions(
                    restriction_type=stt_pb2.LanguageRestrictionOptions.WHITELIST,
                    language_code=['ru-RU'],
                ),
                audio_processing_type=stt_pb2.RecognitionModelOptions.REAL_TIME,
            )
        )

    def _req_stream(self, wav_path: str):
        # 1) отправляем настройки сессии
        yield stt_pb2.StreamingRequest(session_options=self._session_opts)
        # 2) отсылаем аудиоданные
        with open(wav_path, "rb") as f:
            while True:
                data = f.read(_CHUNK_SIZE)
                if not data:
                    break
                yield stt_pb2.StreamingRequest(chunk=stt_pb2.AudioChunk(data=data))

    def recognize_wav(self, wav_path: str) -> str:
        logging.info(f"Yandex STT: start recognize {wav_path}")
        responses = self._stub.RecognizeStreaming(
            self._req_stream(wav_path), metadata=self._metadata
        )
        final_text = ""
        for r in responses:
            ev = r.WhichOneof("Event")
            logging.debug(f"Yandex STT event={ev}")
            if ev == "partial" and r.partial.alternatives:
                logging.debug(
                    f"Yandex STT partial: {r.partial.alternatives[0].text}")
            elif ev == "final" and r.final.alternatives:
                hypothesis = r.final.alternatives[0].text or ""
                logging.info(f"Yandex STT final: '{hypothesis}'")
                final_text = hypothesis or final_text
            elif ev == "final_refinement" and r.final_refinement.normalized_text.alternatives:
                refined = r.final_refinement.normalized_text.alternatives[0].text or ""
                logging.info(f"Yandex STT refined: '{refined}'")
                final_text = refined or final_text

        final_text = (final_text or "").strip()
        if final_text:
            logging.info(f"✅ Yandex STT recognized: '{final_text}'")
        else:
            logging.warning("⚠️ Yandex STT вернул пустой текст")
        return final_text
