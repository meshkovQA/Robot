#!/bin/bash
set -euo pipefail
BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
echo -e "${BLUE}🔄 Обновление Robot Web Interface (git pull)${NC}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# Быстрая проверка синтаксиса
python3 - <<'PY'
import compileall, sys
ok = compileall.compile_dir('.', force=False, quiet=1)
sys.exit(0 if ok else 1)
PY
echo -e "${GREEN}✅ Синтаксис корректен${NC}"


# Применение прав выполнения для всех скриптов
echo -e "${BLUE}🔧 Применение прав выполнения для скриптов...${NC}"
chmod +x "$PROJECT_DIR"/*.sh 2>/dev/null || true
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