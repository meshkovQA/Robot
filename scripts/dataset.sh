#!/bin/bash
# Сбор датасета через /api/camera/frame
# Пример: ./dataset.sh --interval 1.0 --duration 600 --prefix walk1

set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info(){ echo -e "${BLUE}[INFO]${NC} $*"; }
ok(){ echo -e "${GREEN}[OK]${NC} $*"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $*"; }
err(){ echo -e "${RED}[ERR]${NC} $*"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="robot-web.service"
PY="$PROJECT_DIR/venv/bin/python"
COLLECT_PY="$PROJECT_DIR/robot/tools/collect_dataset_api.py"

# Проверки
[[ -x "$PY" ]] || { err "Виртуальное окружение не найдено: $PROJECT_DIR/venv"; exit 1; }
[[ -f "$COLLECT_PY" ]] || { err "Нет файла: $COLLECT_PY"; exit 1; }

# Убедимся, что сервис запущен (иначе /api/camera/frame не отдаст кадр)
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  warn "Сервис $SERVICE_NAME не запущен - запускаю..."
  sudo systemctl start "$SERVICE_NAME"
  sleep 3
  systemctl is-active --quiet "$SERVICE_NAME" || { err "Сервис не стартовал"; exit 1; }
fi
ok "Сервис активен"

# Параметры по умолчанию
INTERVAL="1.0"
DURATION="300"
PREFIX="dataset"
URL="http://127.0.0.1:5000/api/camera/frame"

# Разбор аргументов
while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL="${2:-1.0}"; shift 2;;
    --duration) DURATION="${2:-300}"; shift 2;;
    --prefix)   PREFIX="${2:-dataset}"; shift 2;;
    --url)      URL="${2:-$URL}"; shift 2;;
    *) err "Неизвестный аргумент: $1"; exit 1;;
  esac
done

info "Интервал: ${INTERVAL}s, Длительность: ${DURATION}s, Префикс: ${PREFIX}"
info "API: ${URL}"

set -x
"$PY" "$COLLECT_PY" \
  --interval "$INTERVAL" \
  --duration "$DURATION" \
  --prefix "$PREFIX" \
  --url "$URL" \
  --out "$PROJECT_DIR/photos/dataset"
set +x