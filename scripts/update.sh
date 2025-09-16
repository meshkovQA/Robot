#!/bin/bash
set -euo pipefail
BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
echo -e "${BLUE}🔄 Обновление Robot (git pull)${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_NAME="robot-web.service"

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  echo -e "${RED}❌ В каталоге нет git-репозитория. Запустите ./setup.sh заново.${NC}"
  exit 1
fi

echo -e "${YELLOW}⏸️ Остановка сервиса...${NC}"
sudo systemctl stop "$SERVICE_NAME" || true

cd "$PROJECT_DIR"
ts="$(date +%Y%m%d_%H%M%S)"

echo -e "${BLUE}📥 Получение обновлений из origin...${NC}"
git fetch --all --tags
git checkout main
git reset --hard origin/main

# Зависимости
source "$VENV_DIR/bin/activate"
if [[ -f "requirements.txt" ]]; then
  pip install --upgrade pip setuptools wheel
  pip install -r requirements.txt
fi


# --- VOSK MODEL SYNC ---------------------------------------------------------
echo -e "${BLUE}🧩 Проверка Vosk-модели (ru)${NC}"

# 1) Убедимся, что vosk установлен в venv
if ! python -c "import vosk" >/dev/null 2>&1; then
  echo -e "${YELLOW}↪️ Устанавливаю vosk в venv...${NC}"
  pip install --upgrade pip
  pip install vosk
fi

# 2) Папка моделей внутри проекта (в репозитории, без sudo)
MODELS_ROOT="$PROJECT_DIR/data/vosk"
mkdir -p "$MODELS_ROOT"

# 3) Какая модель нужна
VOSK_URL="https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
VOSK_ZIP="$MODELS_ROOT/vosk-model-small-ru-0.22.zip"
VOSK_DIR="$MODELS_ROOT/vosk-model-small-ru-0.22"
VOSK_LINK="$MODELS_ROOT/current"

# 4) Скачиваем при необходимости
if [[ ! -d "$VOSK_DIR" ]]; then
  echo -e "${YELLOW}⬇️ Скачиваю Vosk-модель (ru small 0.22)...${NC}"
  if ! command -v wget >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y wget
  fi
  if ! command -v unzip >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y unzip
  fi
  wget -q --show-progress -O "$VOSK_ZIP" "$VOSK_URL"
  echo -e "${YELLOW}📦 Распаковываю...${NC}"
  unzip -q "$VOSK_ZIP" -d "$MODELS_ROOT"
fi

# 5) Симлинк на актуальную модель
if [[ -d "$VOSK_DIR" ]]; then
  ln -sfn "$VOSK_DIR" "$VOSK_LINK"
  echo -e "${GREEN}✅ Vosk-модель готова: $VOSK_LINK${NC}"
else
  echo -e "${RED}❌ Не удалось подготовить модель Vosk${NC}"
fi
# --- VOSK MODEL SYNC END -----------------------------------------------------

# Быстрая проверка синтаксиса
python3 - <<'PY'
import compileall, sys
ok = compileall.compile_dir('.', force=False, quiet=1)
sys.exit(0 if ok else 1)
PY
echo -e "${GREEN}✅ Синтаксис корректен${NC}"


# Применение прав выполнения для всех скриптов
echo -e "${BLUE}🔧 Применение прав выполнения для скриптов...${NC}"
chmod +x "$PROJECT_DIR"/scripts/*.sh 2>/dev/null || true
chmod +x "$PROJECT_DIR"/scripts/spotify/*.sh 2>/dev/null || true
echo -e "${GREEN}✅ Права выполнения применены${NC}"

#  Установка зависимостей Spotify
echo -e "${BLUE}📦 Установка зависимостей Spotify...${NC}"
"$PROJECT_DIR"/scripts/spotify/spotify_install_deps.sh
echo -e "${GREEN}✅ Зависимости установлены${NC}"

# 📊 Проверка статуса Spotify
echo -e "${BLUE}🔎 Проверка статуса Spotify...${NC}"
"$PROJECT_DIR"/scripts/spotify/spotify_status.sh
echo -e "${GREEN}✅ Статус получен${NC}"

# 📡 OAuth авторизация Spotify (если требуется)
echo -e "${BLUE}🔐 Проверка OAuth для Spotify...${NC}"

# 1) проверка переменных окружения
if [[ -z "${SPOTIFY_CLIENT_ID:-}" || -z "${SPOTIFY_CLIENT_SECRET:-}" ]]; then
  echo -e "${RED}❌ Не заданы SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET${NC}"
  echo -e "${YELLOW}ℹ️  Пример:${NC} export SPOTIFY_CLIENT_ID=xxx; export SPOTIFY_CLIENT_SECRET=yyy"
  exit 1
fi

# 2) убеждаемся, что порт редиректа свободен (127.0.0.1:8888)
REDIRECT_HOST="127.0.0.1"
REDIRECT_PORT="8888"
if command -v lsof >/dev/null 2>&1 && lsof -Pi :${REDIRECT_PORT} -sTCP:LISTEN -t >/dev/null ; then
  echo -e "${RED}❌ Порт ${REDIRECT_PORT} уже занят (редирект URI)${NC}"
  echo -e "${YELLOW}Закрой процесс на этом порту или измени redirect_uri в конфиге/дешборде Spotify.${NC}"
  exit 1
fi

# 3) запустить помощь авторизации (только если необходимо)
python3 - <<'PY'
import os, json, sys, time
from pathlib import Path
from robot.ai_agent.spotify_agent import SpotifyAgent

def needs_auth(agent: SpotifyAgent) -> bool:
    # если нет refresh_token — точно нужна авторизация
    if not agent.refresh_token:
        return True
    try:
        # пробуем освежить и дернуть список устройств
        if not agent._ensure_user_token():
            return True
        devs = agent.get_devices()
        return not isinstance(devs, list)  # если не список — что-то не то
    except Exception:
        return True

try:
    a = SpotifyAgent()
except Exception as e:
    print(f"❌ Не удалось инициализировать SpotifyAgent: {e}")
    sys.exit(1)

if needs_auth(a):
    print("🌐 Требуется авторизация Spotify. Сейчас будет выведен URL для входа.")
    print("   После логина вы увидите 'You can close this tab. Return to the app.'")
    a.start_user_auth()   # поднимет локальный HTTP на redirect_uri и поймает код
    print("✅ OAuth настроен.")
else:
    print("✅ OAuth уже настроен, пропускаю вход.")

# Печатаем устройства для проверки
try:
    devs = a.get_devices()
    if devs:
        print("🖥️ Найдены устройства Spotify:")
        for d in devs:
            print(f" - {d.get('name')} | active={d.get('is_active')} | type={d.get('type')}")
    else:
        print("⚠️ Устройства не найдены. Убедись, что Spotify запущен на ПК/телефоне.")
except Exception as e:
    print(f"⚠️ Не удалось получить устройства: {e}")

# (опционально) тестовый запуск трека — закомментировано:
# try:
#     print(a.search_and_play("Daft Punk Harder Better Faster Stronger"))
# except Exception as e:
#     print(f"⚠️ Тестовое воспроизведение не удалось: {e}")
PY
echo -e "${GREEN}✅ Проверка/настройка OAuth завершена${NC}"

echo -e "${BLUE}🚀 Запуск сервиса...${NC}"
sudo systemctl start "$SERVICE_NAME"
sleep 3
if systemctl is-active --quiet "$SERVICE_NAME"; then
  COMMIT=$(git rev-parse --short HEAD)
  IP=$(hostname -I | awk '{print $1}')
  echo -e "${GREEN}✅ Обновление успешно. Коммит: $COMMIT${NC}"
  echo -e "${GREEN}🌐 Интерфейс: http://$IP:5000${NC}"
else
  echo -e "${RED}❌ Сервис не запустился после обновления${NC}"
  echo "Проверьте логи: ./logs.sh"
  exit 1
fi
