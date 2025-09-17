#!/bin/bash
set -e

BLUE='\033[1;34m'; NC='\033[0m'
echo -e "${BLUE}--- Spotify OAuth (однократная интерактивная авторизация) ---${NC}"

# Определяем корень проекта относительно скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

python3 - <<'PY'
import json, sys, traceback
from pathlib import Path

# Грузим конфиг проекта
PROJECT_ROOT = Path(__file__).resolve().parents[1]
config_path = PROJECT_ROOT / "data" / "ai_config.json"
try:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
except Exception as e:
    print("❌ Не удалось прочитать data/ai_config.json:", e)
    sys.exit(1)

# Подстрахуем scopes: если нет — подставим нужные
scopes = cfg.get("spotify", {}).get("scopes") or [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
]
cfg.setdefault("spotify", {})["scopes"] = scopes

from robot.ai_agent.spotify_agent import SpotifyAgent

try:
    agent = SpotifyAgent(config=cfg)   # <-- ПЕРЕДАЁМ КОНФИГ
    # если уже авторизованы, но без нужных скоупов — переавторизуемся
    need_reauth = (not agent.refresh_token) or not agent.scopes
    if need_reauth:
        print("🌐 Требуется авторизация. Откройте URL ниже, войдите в Spotify, дождитесь 'You can close this tab'")
        agent.start_user_auth()
        print("✅ Авторизация завершена, токены сохранены.")
    else:
        print("✅ Spotify уже авторизован (refresh_token найден).")

    devs = agent.get_devices()
    if not isinstance(devs, list) or not devs:
        print("⚠️ Устройства не найдены. Убедись, что запущен Spotify-клиент (или librespot).")
    else:
        print("🎵 Доступные устройства:")
        for d in devs:
            print(f" - {d.get('name')} (id={d.get('id')}, active={d.get('is_active')})")

except Exception as e:
    print("❌ Ошибка авторизации Spotify:", e)
    traceback.print_exc()
    sys.exit(1)
PY