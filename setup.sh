#!/bin/bash
# setup.sh — установка веб-интерфейса робота с новой Python-структурой

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info(){ echo -e "${BLUE}[INFO]${NC} $*"; }
ok(){ echo -e "${GREEN}[OK]${NC} $*"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $*"; }
err(){ echo -e "${RED}[ERR]${NC} $*"; }

# --- проверки ---
if [[ $EUID -eq 0 ]]; then err "Не запускайте от root. Запустите под обычным пользователем."; exit 1; fi
command -v sudo >/dev/null || { err "sudo не найден"; exit 1; }

# --- конфигурация путей/репо ---
USER_NAME="$USER"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
PROJECT_DIR="$HOME_DIR/robot_web"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
ENV_FILE="$PROJECT_DIR/.env"
SERVICE_NAME="robot-web.service"

# ваш репозиторий (raw):
GITHUB_RAW="https://raw.githubusercontent.com/meshkovQA/Robot/main"
# относительные пути файлов в репо (под новую структуру)
PY_FILES=(
  "run.py"
  "robot/__init__.py"
  "robot/config.py"
  "robot/i2c_bus.py"
  "robot/controller.py"
  "robot/api.py"
)
STATIC_FILES=(
  "templates/index.html"
  "static/style.css"
  "static/script.js"
)

echo "=============================================="
info "🤖 Установка веб-интерфейса управления роботом"
info "📁 Репозиторий: https://github.com/meshkovQA/Robot"
echo "=============================================="

# --- обновление системы и пакеты ---
info "Обновление apt и установка пакетов..."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-dev \
                    libffi-dev build-essential git curl i2c-tools \
                    net-tools

# --- включение I2C ---
info "Настройка I2C..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null; then
  echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt >/dev/null
  ok "I2C включён в /boot/config.txt"
fi
if ! grep -q "^i2c-dev" /etc/modules 2>/dev/null; then
  echo "i2c-dev" | sudo tee -a /etc/modules >/dev/null
  ok "Модуль i2c-dev добавлен в /etc/modules"
fi
sudo usermod -a -G i2c,gpio,spi "$USER_NAME" || true

# --- структура проекта ---
info "Создание структуры в $PROJECT_DIR ..."
mkdir -p "$PROJECT_DIR"/{robot,templates,static} "$LOG_DIR"

# --- виртуальное окружение ---
if [[ ! -d "$VENV_DIR" ]]; then
  info "Создание виртуального окружения..."
  python3 -m venv "$VENV_DIR"
  ok "venv создан"
fi
source "$VENV_DIR/bin/activate"

# --- зависимости python ---
info "Установка Python-зависимостей в venv..."
pip install --upgrade pip
# минимальный набор
pip install flask gunicorn smbus2

# --- .env (переменные окружения для приложения) ---
if [[ ! -f "$ENV_FILE" ]]; then
  info "Создание $ENV_FILE ..."
  cat > "$ENV_FILE" <<'EOF'
# === Переменные окружения для Robot Web ===
# Секрет для API (передавайте в заголовке X-API-Key)
API_KEY=

# I2C настройки (по умолчанию для Raspberry Pi)
I2C_BUS=1
ARDUINO_ADDRESS=0x08

# Пороговые значения датчиков (см)
SENSOR_FWD_STOP_CM=15
SENSOR_BWD_STOP_CM=10
SENSOR_MAX_VALID=500

# Скорость
DEFAULT_SPEED=50
LOG_LEVEL=INFO
EOF
  ok "Создан .env (заполните API_KEY при необходимости)"
fi

# --- скачивание файлов из репозитория ---
download() {
  local src="$1" dst="$2"
  local url="$GITHUB_RAW/$src"
  info "Скачивание $src -> $dst"
  curl -fsSL "$url" -o "$dst" || { err "Не удалось скачать $url"; return 1; }
}
info "Загрузка Python-файлов проекта..."
for rel in "${PY_FILES[@]}"; do
  mkdir -p "$(dirname "$PROJECT_DIR/$rel")"
  download "$rel" "$PROJECT_DIR/$rel"
done

info "Загрузка шаблонов/статик (если есть в репо)..."
for rel in "${STATIC_FILES[@]}"; do
  mkdir -p "$(dirname "$PROJECT_DIR/$rel")"
  if ! download "$rel" "$PROJECT_DIR/$rel"; then
    warn "$rel не найден в репо — пропускаю"
  fi
done

# права
chmod -R u+rwX "$PROJECT_DIR"
find "$PROJECT_DIR" -type f -name "*.py" -exec chmod +x {} \; || true

# --- systemd unit для gunicorn ---
info "Создание systemd юнита..."
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Robot Web (Flask + gunicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$PROJECT_DIR
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=$ENV_FILE
ExecStart=$PROJECT_DIR/venv/bin/gunicorn --workers 2 --threads 2 --timeout 30 --bind 0.0.0.0:5000 run:app
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
# доступ к i2c/gpio
SupplementaryGroups=i2c gpio spi

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

# --- вспомогательные скрипты ---
info "Создание сервисных скриптов..."
cat > "$PROJECT_DIR/start.sh" <<EOF
#!/bin/bash
sudo systemctl start $SERVICE_NAME
sudo systemctl status $SERVICE_NAME --no-pager
EOF
cat > "$PROJECT_DIR/stop.sh" <<EOF
#!/bin/bash
sudo systemctl stop $SERVICE_NAME
EOF
cat > "$PROJECT_DIR/restart.sh" <<EOF
#!/bin/bash
sudo systemctl restart $SERVICE_NAME
sudo systemctl status $SERVICE_NAME --no-pager
EOF
cat > "$PROJECT_DIR/logs.sh" <<EOF
#!/bin/bash
sudo journalctl -u $SERVICE_NAME -f
EOF
cat > "$PROJECT_DIR/status.sh" <<'EOF'
#!/bin/bash
SERVICE=robot-web.service
echo "=== Статус сервиса ==="
sudo systemctl status "$SERVICE" --no-pager
echo -e "\n=== Порт 5000 ==="
sudo netstat -tlnp 2>/dev/null | grep :5000 || echo "Порт 5000 не занят"
echo -e "\n=== I2C устройства (шина 1) ==="
if command -v i2cdetect &>/dev/null; then sudo i2cdetect -y 1; else echo "i2c-tools не установлены"; fi
echo -e "\n=== Последние логи ==="
sudo journalctl -u "$SERVICE" --no-pager -n 50
EOF
chmod +x "$PROJECT_DIR/"{start.sh,stop.sh,restart.sh,logs.sh,status.sh}

# --- скрипт обновления под новую структуру ---
info "Создание update.sh..."
cat > "$PROJECT_DIR/update.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
echo -e "${BLUE}🔄 Обновление проекта из GitHub${NC}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_RAW="https://raw.githubusercontent.com/meshkovQA/Robot/main"

declare -a PY_FILES=(
  "run.py"
  "robot/__init__.py"
  "robot/config.py"
  "robot/i2c_bus.py"
  "robot/controller.py"
  "robot/api.py"
)
declare -a STATIC_FILES=(
  "templates/index.html"
  "static/style.css"
  "static/script.js"
)

backup_and_fetch () {
  local rel="$1"
  local url="$GITHUB_RAW/$rel"
  local dst="$PROJECT_DIR/$rel"
  mkdir -p "$(dirname "$dst")"
  if [[ -f "$dst" ]]; then cp "$dst" "$dst.backup.$(date +%Y%m%d_%H%M%S)"; fi
  curl -fsSL "$url" -o "$dst" || { echo -e "${RED}Ошибка скачивания $url${NC}"; return 1; }
  echo "✓ $rel"
}

sudo systemctl stop robot-web.service || true

for f in "${PY_FILES[@]}"; do backup_and_fetch "$f"; done
for f in "${STATIC_FILES[@]}"; do
  backup_and_fetch "$f" || echo "… пропущено"
done

# Проверка синтаксиса
python3 -m py_compile "$PROJECT_DIR"/run.py "$PROJECT_DIR"/robot/*.py

sudo systemctl start robot-web.service
sleep 2
systemctl is-active --quiet robot-web.service && echo -e "${GREEN}✅ Запущено${NC}" || (echo -e "${RED}❌ Не запущено${NC}"; exit 1)
EOF
chmod +x "$PROJECT_DIR/update.sh"

# --- финальные сообщения ---
ok "Файлы установлены в $PROJECT_DIR"
info "Включён автозапуск сервиса: $SERVICE_NAME"
echo
warn "Для применения групп (i2c/gpio/spi) рекомендуется перелогиниться или перезагрузить систему."
echo
info "Запуск сервиса сейчас:"
sudo systemctl restart "$SERVICE_NAME"
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  ok "Сервис запущен"
  IP=$(hostname -I | awk '{print $1}')
  echo -e "🌐 Откройте: http://$IP:5000"
else
  err "Сервис не стартовал. Посмотрите логи: $PROJECT_DIR/logs.sh"
fi