#!/bin/bash
set -e

BLUE='\033[1;34m'
GREEN='\033[1;32m'
RED='\033[1;31m'
NC='\033[0m'

PROJECT_ROOT="/home/aleksandrmeshkov/robot_web"
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo -e "${BLUE}--- Spotify OAuth (однократная интерактивная авторизация) ---${NC}"

python3 - <<'PY'
import sys
import traceback
from robot.ai_agent.spotify_agent import SpotifyAgent

try:
    agent = SpotifyAgent()
    if not agent.refresh_token:
        print("🌐 Требуется авторизация.")
        print("Откройте URL ниже, войдите в Spotify, дождитесь 'You can close this tab'")
        agent.start_user_auth()
        print("✅ Авторизация завершена, токены сохранены.")
    else:
        print("✅ Spotify уже авторизован (refresh_token найден).")

    devices = agent.get_devices()
    if not devices:
        print("⚠️ Устройства не найдены. Убедитесь, что запущен Spotify-клиент или librespot.")
    else:
        print("🎵 Доступные устройства:")
        for d in devices:
            print(f" - {d['name']} (id={d['id']}, active={d['is_active']})")

except Exception as e:
    print("❌ Ошибка авторизации Spotify:", e)
    traceback.print_exc(file=sys.stdout)
    sys.exit(1)
PY