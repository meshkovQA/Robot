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