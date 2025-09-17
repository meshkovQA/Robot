#!/bin/bash
set -e

BLUE='\033[1;34m'; NC='\033[0m'
echo -e "${BLUE}--- Spotify OAuth (однократная интерактивная авторизация) ---${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

python3 - <<'PY'
import json, sys, traceback
from pathlib import Path
from config import PROJECT_ROOT

# гарантируем папку data
(PROJECT_ROOT / "data").mkdir(parents=True, exist_ok=True)

# миграция старого токена из scripts/data -> data
legacy = PROJECT_ROOT / "scripts" / "data" / "spotify_tokens.json"
new    = PROJECT_ROOT / "data" / "spotify_tokens.json"
if legacy.exists() and not new.exists():
    try:
        new.write_bytes(legacy.read_bytes())
        legacy.unlink()
        print(f"↪️ Перенёс токен: {legacy} -> {new}")
    except Exception as e:
        print(f"⚠️ Не удалось перенести токен: {e}")

# читаем конфиг и подставляем scope если пуст
cfg_path = PROJECT_ROOT / "data" / "ai_config.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
cfg.setdefault("spotify", {})
if not cfg["spotify"].get("scopes"):
    cfg["spotify"]["scopes"] = [
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
    ]

from robot.ai_agent.spotify_agent import SpotifyAgent

try:
    a = SpotifyAgent(config=cfg)
    if not a.refresh_token:
        print("🌐 Требуется авторизация. Откройте URL ниже, войдите в Spotify, дождитесь 'You can close this tab'")
        a.start_user_auth()
        print("✅ Авторизация завершена, токены сохранены.")
    else:
        print("✅ Spotify уже авторизован (refresh_token найден).")

    print("📄 Токен-файл:", a.token_file, "| exists:", a.token_file.exists())
    devs = a.get_devices()
    if devs:
        print("🎵 Доступные устройства:")
        for d in devs:
            print(f" - {d.get('name')} (id={d.get('id')}, active={d.get('is_active')})")
    else:
        print("⚠️ Устройства не найдены. Убедись, что запущен Spotify-клиент (или librespot).")

except Exception as e:
    print("❌ Ошибка авторизации Spotify:", e)
    traceback.print_exc()
    sys.exit(1)
PY