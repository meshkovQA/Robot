# --- Spotify OAuth (однократная интерактивная авторизация) -----------------
echo -e "${BLUE}🔐 Авторизация Spotify...${NC}"

python3 - <<'PY'
from robot.ai_agent.spotify_agent import SpotifyAgent

try:
    a = SpotifyAgent()
    if not a.refresh_token:
        print("🌐 Требуется авторизация. Откройте URL ниже, войдите в Spotify, дождитесь 'You can close this tab'")
        a.start_user_auth()
        print("✅ Авторизация завершена, токены сохранены.")
    else:
        print("✅ Spotify уже авторизован.")
    print("Устройства:", a.get_devices())
except Exception as e:
    print("❌ Ошибка авторизации Spotify:", e)
PY