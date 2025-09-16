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
echo -e "${GREEN}✅ Права выполнения применены${NC}"

# --- Spotify OAuth helper (только Web API, без playerctl/скриптов) ----------
echo -e "${BLUE}🔐 Проверка OAuth для Spotify...${NC}"

# 1) переменные окружения
if [[ -z "${SPOTIFY_CLIENT_ID:-}" || -z "${SPOTIFY_CLIENT_SECRET:-}" ]]; then
  echo -e "${RED}❌ Не заданы SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET${NC}"
  echo -e "${YELLOW}ℹ️  Пример:${NC} export SPOTIFY_CLIENT_ID=xxx; export SPOTIFY_CLIENT_SECRET=yyy"
  echo -e "${YELLOW}После задания переменных повторите запуск скрипта.${NC}"
  # Не фейлим деплой сервиса — просто пропускаем авторизацию
else
  # 2) порт редиректа
  REDIRECT_PORT="8888"
  if command -v lsof >/dev/null 2>&1 && lsof -Pi :${REDIRECT_PORT} -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${YELLOW}⚠️ Порт ${REDIRECT_PORT} занят. Пропущу интерактивную авторизацию сейчас.${NC}"
  else
    # 3) запустить авторизацию при необходимости
    python3 - <<'PY'
from pathlib import Path
from robot.ai_agent.spotify_agent import SpotifyAgent

def needs_auth(agent: SpotifyAgent) -> bool:
    if not agent.refresh_token:
        return True
    try:
        if not agent._ensure_user_token():
            return True
        devs = agent.get_devices()
        return False  # если дошли сюда — токен работает
    except Exception:
        return True

a = SpotifyAgent()
if needs_auth(a):
    print("🌐 Требуется авторизация Spotify. Откройте URL ниже, войдите, дождитесь 'You can close this tab'.")
    a.start_user_auth()
    print("✅ OAuth настроен.")
else:
    print("✅ OAuth уже настроен, пропускаю вход.")
PY
  fi
fi
echo -e "${GREEN}✅ Проверка/настройка OAuth завершена${NC}"


# --- Запуск сервиса ----------------------------------------------------------
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
