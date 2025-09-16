# robot/ai_agent/spotify_agent.py
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import time
import json
import requests
import subprocess
import os
import logging
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs


logger = logging.getLogger(__name__)


class SpotifyAgent:
    """
    Простой агент для управления Spotify по голосовым командам

    Ключи API берутся из переменных окружения (как для Yandex)
    Остальные настройки - из JSON конфига
    """

    def __init__(self, audio_manager=None, config: Dict[str, Any] = None):
        self.audio_manager = audio_manager
        self.config = config or {}

        # Spotify настройки из конфига
        spotify_config = (self.config.get("speech", {})
                          or {}).get("spotify", {}) or {}

        # Ключи API ТОЛЬКО из переменных окружения (как для Yandex)
        self.client_id = os.getenv('SPOTIFY_CLIENT_ID')
        self.client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Spotify API ключи не найдены в переменных окружения. "
                "Установите SPOTIFY_CLIENT_ID и SPOTIFY_CLIENT_SECRET"
            )

        # Остальные настройки из JSON конфига (как у Yandex)
        self.scopes = spotify_config.get("scopes", [])
        self.redirect_uri = spotify_config.get(
            'redirect_uri', 'http://127.0.0.1:8888/callback')
        self.default_volume = spotify_config.get('default_volume', 50)
        self.search_limit = spotify_config.get('search_limit', 10)
        self.control_method = spotify_config.get(
            'control_method', 'auto')  # auto, playerctl, osascript
        self.preferred_device = spotify_config.get('preferred_device')

        # Состояние плеера
        self.is_playing = False
        self.current_track = "Неизвестно"
        self.current_volume = self.default_volume
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = 0

        # Файл для сохранения токенов
        self.token_file = Path("data/spotify_tokens.json")

        # API endpoints
        self.api_base = "https://api.spotify.com/v1"

        # Голосовые команды из конфига или по умолчанию
        default_commands = {
            "включи музыку": "play",
            "выключи музыку": "pause",
            "поставь на паузу": "pause",
            "продолжи музыку": "play",
            "следующая песня": "next_track",
            "предыдущая песня": "previous_track",
            "что играет": "current_track_info",
            "тише": "volume_down",
            "громче": "volume_up",
            "поставь": "search_and_play"
        }

        # Команды из конфига или по умолчанию
        configured_commands = spotify_config.get(
            'voice_commands', default_commands)
        self.voice_commands = {cmd: getattr(
            self, action) for cmd, action in configured_commands.items()}

        # Загружаем сохраненные токены
        self._load_tokens()

        logger.info("🎵 Spotify Agent initialized")

    def _load_tokens(self):
        """Загрузка сохраненных токенов"""
        try:
            if self.token_file.exists():
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get('access_token')
                    self.refresh_token = data.get('refresh_token')
                    self.token_expires_at = data.get('expires_at', 0)
                logger.info("✅ Spotify токены загружены")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить токены: {e}")

    def _save_tokens(self):
        """Сохранение токенов"""
        try:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'expires_at': self.token_expires_at
            }
            with open(self.token_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("✅ Spotify токены сохранены")
        except Exception as e:
            logger.error(f"❌ Не удалось сохранить токены: {e}")

    def start_user_auth(self):
        """Открыть браузер для OAuth и поймать код на локальном редиректе"""
        auth_url = "https://accounts.spotify.com/authorize"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "show_dialog": "true",
        }
        full_url = f"{auth_url}?{urlencode(params)}"
        print(f"Открой URL для входа в Spotify:\n{full_url}")

        code_holder = {"code": None, "error": None}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                qs = parse_qs(urlparse(self.path).query)
                code_holder["code"] = qs.get("code", [None])[0]
                code_holder["error"] = qs.get("error", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"You can close this tab. Return to the app.")

            def log_message(self, *args, **kwargs):
                return  # тишина

        host, port = urlparse(self.redirect_uri).hostname, urlparse(
            self.redirect_uri).port
        httpd = HTTPServer((host, port), Handler)
        httpd.handle_request()  # ждём один заход

        if code_holder["error"]:
            raise RuntimeError(f"Spotify OAuth error: {code_holder['error']}")
        if not code_holder["code"]:
            raise RuntimeError("No authorization code received")

        self._exchange_code_for_token(code_holder["code"])
        print("✅ Пользователь авторизован, токены сохранены.")

    def _exchange_code_for_token(self, code: str):
        token_url = "https://accounts.spotify.com/api/token"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        r = requests.post(token_url, data=data)
        r.raise_for_status()
        td = r.json()
        self.access_token = td["access_token"]
        self.refresh_token = td.get("refresh_token", self.refresh_token)
        self.token_expires_at = time.time() + int(td.get("expires_in", 3600))
        self._save_tokens()

    def _refresh_user_token(self) -> bool:
        if not self.refresh_token:
            return False
        token_url = "https://accounts.spotify.com/api/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        r = requests.post(token_url, data=data)
        if r.status_code != 200:
            logging.error("Refresh token failed: %s %s", r.status_code, r.text)
            return False
        td = r.json()
        self.access_token = td["access_token"]
        self.token_expires_at = time.time() + int(td.get("expires_in", 3600))
        self._save_tokens()
        return True

    def _ensure_user_token(self) -> bool:
        if not self.access_token:
            return False
        if time.time() > self.token_expires_at - 60:
            return self._refresh_user_token()
        return True

    # ===== Вспомогалка для вызовов Web API от лица пользователя =====

    def _api(self, method: str, path: str, **kwargs):
        if not self._ensure_user_token():
            return False, "User token invalid or missing. Run start_user_auth()."
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        url = f"https://api.spotify.com/v1{path}"
        resp = requests.request(method.upper(), url,
                                headers=headers, timeout=10, **kwargs)
        if 200 <= resp.status_code < 300:
            return True, (resp.json() if resp.content else None)
        return False, f"{resp.status_code}: {resp.text}"

    # ===== Управление устройствами и плеером через Web API =====

    def get_devices(self):
        ok, data = self._api("GET", "/me/player/devices")
        return data.get("devices", []) if ok and data else []

    def _pick_device(self):
        devices = self.get_devices()
        if not devices:
            return None
        if self.preferred_device:
            for d in devices:
                if self.preferred_device.lower() in d.get("name", "").lower():
                    return d
        for d in devices:
            if d.get("is_active"):
                return d
        return devices[0]

    def transfer_playback(self, device_id: str, play: bool = True):
        body = {"device_ids": [device_id], "play": play}
        ok, err = self._api("PUT", "/me/player", json=body)
        return ok

    def play_uri(self, uri: str, position_ms: int = 0) -> str:
        device = self._pick_device()
        if not device:
            return "Нет доступных устройств Spotify. Открой Spotify-клиент."
        self.transfer_playback(device["id"], play=True)
        payload = {"uris": [uri], "position_ms": int(position_ms)}
        ok, err = self._api("PUT", "/me/player/play", json=payload)
        if ok:
            self.is_playing = True
            return "Воспроизвожу трек"
        return f"Не удалось запустить трек: {err}"

    def play_context(self, context_uri: str, position_ms: int = 0, offset: Optional[int] = None) -> str:
        device = self._pick_device()
        if not device:
            return "Нет доступных устройств Spotify."
        self.transfer_playback(device["id"], play=True)
        body = {"context_uri": context_uri, "position_ms": int(position_ms)}
        if offset is not None:
            body["offset"] = {"position": int(offset)}
        ok, err = self._api("PUT", "/me/player/play", json=body)
        self.is_playing = bool(ok)
        return "Воспроизвожу" if ok else f"Не удалось начать воспроизведение: {err}"

    def _get_access_token(self) -> bool:
        """Получение access token через Client Credentials Flow"""
        try:
            auth_url = "https://accounts.spotify.com/api/token"

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            data = {
                'grant_type': 'client_credentials'
            }

            response = requests.post(
                auth_url,
                headers=headers,
                data=data,
                auth=(self.client_id, self.client_secret)
            )

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires_at = time.time() + expires_in

                self._save_tokens()
                logger.info("✅ Spotify access token получен")
                return True
            else:
                logger.error(
                    f"❌ Ошибка получения токена: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка авторизации Spotify: {e}")
            return False

    def _ensure_token(self) -> bool:
        """Проверка и обновление токена при необходимости"""
        current_time = time.time()

        if not self.access_token or current_time >= self.token_expires_at - 60:
            return self._get_access_token()

        return True

    # Основные команды управления

    def play(self) -> str:
        try:
            ok, err = self._api("PUT", "/me/player/play", json={})
            if ok:
                self.is_playing = True
                return "Музыка включена"
        except Exception:
            pass
        success, output = self._run_spotify_script("play")
        if success:
            self.is_playing = True
            return "Музыка включена (fallback)"
        return f"Не удалось включить музыку: {output}"

    def pause(self) -> str:
        try:
            ok, err = self._api("PUT", "/me/player/pause")
            if ok:
                self.is_playing = False
                return "Музыка поставлена на паузу"
        except Exception:
            pass
        success, output = self._run_spotify_script("pause")
        if success:
            self.is_playing = False
            return "Музыка поставлена на паузу (fallback)"
        return f"Не удалось поставить на паузу: {output}"

    def next_track(self) -> str:
        try:
            ok, err = self._api("POST", "/me/player/next")
            if ok:
                return "Переключено на следующий трек"
        except Exception:
            pass
        success, output = self._run_spotify_script("next")
        return "Переключено (fallback)" if success else f"Не удалось переключить трек: {output}"

    def previous_track(self) -> str:
        try:
            ok, err = self._api("POST", "/me/player/previous")
            if ok:
                return "Переключено на предыдущий трек"
        except Exception:
            pass
        success, output = self._run_spotify_script("previous")
        return "Переключено (fallback)" if success else f"Не удалось переключить: {output}"

    def set_volume(self, percent: int) -> str:
        percent = max(0, min(100, int(percent)))
        try:
            ok, err = self._api(
                "PUT", f"/me/player/volume?volume_percent={percent}")
            if ok:
                self.current_volume = percent
                return f"Громкость установлена: {percent}%"
        except Exception:
            pass
        ok, out = self._run_spotify_script("set_volume", str(percent))
        if ok:
            self.current_volume = percent
            return f"Громкость установлена: {percent}% (fallback)"
        return f"Не удалось установить громкость: {out}"

    def volume_up(self) -> str:
        """Увеличить громкость"""
        try:
            success, output = self._run_spotify_script("volume", "up")
            if success:
                self.current_volume = min(100, self.current_volume + 10)
                return f"Громкость увеличена до {self.current_volume}%"
            else:
                return f"Не удалось увеличить громкость: {output}"

        except Exception as e:
            logger.error(f"❌ Ошибка увеличения громкости: {e}")
            return "Не удалось увеличить громкость"

    def volume_down(self) -> str:
        """Уменьшить громкость"""
        try:
            success, output = self._run_spotify_script("volume", "down")
            if success:
                self.current_volume = max(0, self.current_volume - 10)
                return f"Громкость уменьшена до {self.current_volume}%"
            else:
                return f"Не удалось уменьшить громкость: {output}"

        except Exception as e:
            logger.error(f"❌ Ошибка уменьшения громкости: {e}")
            return "Не удалось уменьшить громкость"

    def current_track_info(self) -> str:
        try:
            ok, data = self._api("GET", "/me/player/currently-playing")
            if ok and data and data.get("item"):
                item = data["item"]
                name = item.get("name")
                artist = ", ".join(a["name"] for a in item.get("artists", []))
                is_playing = data.get("is_playing", False)
                return f"Сейчас играет: {name} — {artist} ({'playing' if is_playing else 'paused'})"
        except Exception:
            pass
        success, output = self._run_spotify_script("status")
        return output if success else "Не удалось получить информацию о треке"

    def search_and_play(self, query: str) -> str:
        try:
            tracks = self.search_tracks(query, limit=1)
            if not tracks:
                return f"Не найдено треков по запросу: {query}"
            track = tracks[0]
            uri = track["uri"]  # spotify:track:...
            title = f"{track['name']} - {track['artists'][0]['name']}"
            msg = self.play_uri(uri)
            if msg.startswith("Воспроизвожу"):
                return f"{msg}: {title}"
            return f"{msg}. Убедись, что Spotify-клиент активен и выполнен вход через OAuth."
        except Exception as e:
            logging.error(f"❌ Ошибка поиска/запуска: {e}")
            return "Не удалось воспроизвести по запросу"

    # Вспомогательные методы

    def _run_spotify_script(self, script_name: str, *args) -> Tuple[bool, str]:
        """Запуск bash-скрипта для управления Spotify"""
        try:
            script_path = Path("scripts/spotify") / f"spotify_{script_name}.sh"

            # Проверяем существование скрипта
            if not script_path.exists():
                logger.error(f"❌ Скрипт не найден: {script_path}")
                return False, f"Скрипт {script_name} не найден"

            # Делаем скрипт исполняемым
            script_path.chmod(0o755)

            # Запускаем скрипт с аргументами
            cmd = [str(script_path)] + list(args)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            output = result.stdout.strip() if result.stdout else ""
            error = result.stderr.strip() if result.stderr else ""

            if result.returncode == 0:
                logger.info(
                    f"✅ Скрипт {script_name} выполнен успешно: {output}")
                return True, output
            else:
                logger.error(
                    f"❌ Скрипт {script_name} завершился с ошибкой: {error}")
                return False, error

        except subprocess.TimeoutExpired:
            logger.error(f"❌ Таймаут выполнения скрипта {script_name}")
            return False, "Превышено время ожидания"
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения скрипта {script_name}: {e}")
            return False, str(e)

    def _get_current_track(self) -> Optional[str]:
        """Получение информации о текущем треке"""
        try:
            result = subprocess.run(
                ["playerctl", "--player=spotify", "metadata",
                    "--format", "{{ title }} - {{ artist }}"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

        except:
            pass

        return None

    def search_tracks(self, query: str, limit: int = 10) -> List[Dict]:
        """Поиск треков через Spotify API"""
        try:
            params = {
                'q': query,
                'type': 'track',
                'limit': limit
            }

            # Формируем URL с параметрами
            url = f"{self.api_base}/search"

            if not self._ensure_token():
                return []

            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }

            response = requests.get(url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                tracks = data.get('tracks', {}).get('items', [])
                logger.info(f"🔍 Найдено треков: {len(tracks)}")
                return tracks
            else:
                logger.error(f"❌ Ошибка поиска: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"❌ Ошибка поиска треков: {e}")
            return []

    def process_voice_command(self, text: str) -> str:
        """Обработка голосовой команды"""
        text_lower = text.lower().strip()
        logger.info(f"🎵 Обработка команды: '{text}'")

        # Проверяем точные совпадения
        for command, handler in self.voice_commands.items():
            if command in text_lower:
                if command == "поставь" and len(text_lower) > len(command):
                    # Извлекаем поисковый запрос
                    query = text_lower.replace("поставь", "").strip()
                    return handler(query)
                else:
                    return handler()

        # Если команда не распознана
        return f"Команда не распознана: {text}. Доступные команды: {', '.join(self.voice_commands.keys())}"

    def get_status(self) -> Dict[str, Any]:
        """Получить статус Spotify агента"""
        return {
            "spotify_agent": {
                "initialized": True,
                "client_id_configured": bool(self.client_id),
                "client_secret_configured": bool(self.client_secret),
                "access_token_valid": bool(self.access_token and time.time() < self.token_expires_at),
                "is_playing": self.is_playing,
                "current_volume": self.current_volume,
                "current_track": self.current_track,
                "available_commands": list(self.voice_commands.keys())
            }
        }

    def set_volume(self, percent: int) -> str:
        """Установить абсолютную громкость (0-100)"""
        percent = max(0, min(100, int(percent)))
        ok, out = self._run_spotify_script("set_volume", str(percent))
        if ok:
            self.current_volume = percent
            return f"Громкость установлена: {percent}%"
        return f"Не удалось установить громкость: {out}"

    def duck(self, target_percent: int = 20) -> None:
        """Мягко приглушить музыку (без логов/ответов)"""
        try:
            self.set_volume(target_percent)
        except Exception:
            pass

    def unduck(self, previous_percent: Optional[int] = None) -> None:
        """Вернуть громкость"""
        try:
            self.set_volume(previous_percent or self.default_volume)
        except Exception:
            pass

    def test_connection(self) -> Dict[str, Any]:
        """Тест подключения к Spotify API"""
        try:
            # Тестовый поиск
            results = self.search_tracks("test", limit=1)

            return {
                "success": True,
                "message": "Подключение к Spotify API работает",
                "search_results": len(results)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка подключения к Spotify API"
            }
