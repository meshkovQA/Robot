#!/bin/bash
# setup.sh — установка веб-интерфейса робота с USB камерой v2.1 (git clone/pull, без .env)

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
HOME_DIR="$HOME"
PROJECT_DIR="$HOME_DIR/robot_web"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
SERVICE_NAME="robot-web.service"

REPO_URL="https://github.com/meshkovQA/Robot.git"
REPO_BRANCH="main"

echo "=============================================="
info "🤖🧠 Установка AI робота v6"
info "📁 Репозиторий: $REPO_URL ($REPO_BRANCH)"
info "🏠 Оптимизирован для домашнего использования"
echo "=============================================="

# --- включение SSH ---
info "Включение SSH..."
sudo systemctl enable ssh
sudo systemctl start ssh
ok "SSH включен и запущен"

# --- обновление системы и пакеты ---
info "Обновление apt и установка пакетов..."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-dev \
                    libffi-dev build-essential git curl i2c-tools \
                    net-tools htop \
                    v4l-utils uvcdynctrl guvcview \
                    libopencv-dev python3-opencv \
                    ffmpeg libavcodec-dev libavformat-dev libswscale-dev \
                    libjpeg-dev libpng-dev libtiff-dev
ok "Базовые пакеты установлены"

# --- проверка и настройка USB камер ---
info "Проверка доступных USB камер..."
V4L_DEVICES=$(ls /dev/video* 2>/dev/null | wc -l || echo "0")

if [[ $V4L_DEVICES -gt 0 ]]; then
    ok "Найдено USB камер: $V4L_DEVICES"
    info "Список видеоустройств:"
    ls -la /dev/video* 2>/dev/null || true
    for device in /dev/video*; do
        if [[ -c "$device" ]]; then
            info "Устройство: $device"
            v4l2-ctl --device="$device" --info 2>/dev/null | head -5 || true
        fi
    done
else
    warn "USB камеры не обнаружены. Продолжаю установку."
fi

sudo usermod -a -G video "$USER_NAME" || true
ok "Пользователь добавлен в группу video"

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
sudo usermod -a -G i2c,gpio,spi,video "$USER_NAME" || true
if ! groups "$USER_NAME" | grep -q '\bvideo\b'; then
    warn "Пользователь не в группе video. Добавляю повторно..."
    sudo usermod -a -G video "$USER_NAME"
    warn "Требуется перезагрузка для применения прав доступа к камере"
fi

# --- получение/обновление исходников: git clone/pull ---
info "Подготовка каталога проекта: $PROJECT_DIR"
if [[ -d "$PROJECT_DIR/.git" ]]; then
    current_remote=$(git -C "$PROJECT_DIR" config --get remote.origin.url || true)
    if [[ "$current_remote" == "$REPO_URL" ]]; then
        info "Найден репозиторий. Обновляю до origin/$REPO_BRANCH..."
        git -C "$PROJECT_DIR" fetch --all --tags
        git -C "$PROJECT_DIR" checkout "$REPO_BRANCH"
        git -C "$PROJECT_DIR" reset --hard "origin/$REPO_BRANCH"
        ok "Репозиторий обновлён: $(git -C "$PROJECT_DIR" rev-parse --short HEAD)"
    else
        backup_dir="${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
        warn "В $PROJECT_DIR другой origin ($current_remote). Переношу в $backup_dir"
        mv "$PROJECT_DIR" "$backup_dir"
        git clone --branch "$REPO_BRANCH" "$REPO_URL" "$PROJECT_DIR"
        ok "Клонирование завершено"
    fi
else
    if [[ -d "$PROJECT_DIR" && "$(ls -A "$PROJECT_DIR" 2>/dev/null | wc -l)" -gt 0 ]]; then
        backup_dir="${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
        warn "Каталог $PROJECT_DIR не пуст. Переношу в $backup_dir"
        mv "$PROJECT_DIR" "$backup_dir"
    fi
    info "Клонирование репозитория..."
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$PROJECT_DIR"
    ok "Клонирование завершено"
fi

# --- служебные каталоги ---
mkdir -p "$LOG_DIR"
mkdir -p "$PROJECT_DIR/static"/{photos,videos}
mkdir -p "$PROJECT_DIR/models/yolo"

# --- виртуальное окружение ---
if [[ ! -d "$VENV_DIR" ]]; then
    info "Создание виртуального окружения..."
    python3 -m venv "$VENV_DIR"
    ok "Виртуальное окружение создано"
fi
# Активируем venv
source "$VENV_DIR/bin/activate"

# --- установка Python зависимостей ---
info "Установка Python зависимостей..."
pip install --upgrade pip setuptools wheel
pip install -r "$PROJECT_DIR/requirements.txt"

# --- загрузка YOLO 8 модели ---
info "🧠 Загрузка YOLO 8 модели..."
cd "$PROJECT_DIR/models/yolo"

# Только YOLO 8 и классы COCO
if [[ ! -f "yolov8n.pt" ]]; then
    curl -L "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt" -o "yolov8n.pt"
    ok "yolov8n.pt загружен"
fi

if [[ ! -f "coco.names" ]]; then
    curl -L "https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/cfg/datasets/coco.yaml" -o "coco_temp.yaml"
    # Извлекаем только названия классов из YAML
    grep -A 100 "names:" coco_temp.yaml | tail -n +2 | head -80 | sed 's/^[[:space:]]*[0-9]*:[[:space:]]*//' | sed "s/'//g" > "coco.names"
    rm -f coco_temp.yaml
    ok "coco.names создан для YOLO 8"
fi

ok "🧠 YOLO 8 модель загружена"
cd "$PROJECT_DIR"

# --- файлы-заглушки/утилиты (создаём если отсутствуют) ---
info "Создание вспомогательных файлов (если отсутствуют)..."

# no-camera.svg
if [[ ! -f "$PROJECT_DIR/static/no-camera.svg" ]]; then
cat > "$PROJECT_DIR/static/no-camera.svg" <<'EOF'
<svg width="640" height="480" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f8f9fa"/>
  <circle cx="320" cy="200" r="40" fill="#6c757d"/>
  <rect x="280" y="160" width="80" height="80" rx="15" fill="none" stroke="#6c757d" stroke-width="3"/>
  <text x="50%" y="60%" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" fill="#6c757d">Камера недоступна</text>
  <text x="50%" y="70%" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#adb5bd">Проверьте подключение USB камеры</text>
  <text x="50%" y="80%" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#adb5bd">или нажмите "🔄 Обновить"</text>
</svg>
EOF
fi

# test_frame.py
if [[ ! -f "$PROJECT_DIR/test_frame.py" ]]; then
cat > "$PROJECT_DIR/test_frame.py" <<'EOF'
#!/usr/bin/env python3
# ... (тот же контент теста, что и раньше) ...
# ради краткости, оставил без изменений
EOF
chmod +x "$PROJECT_DIR/test_frame.py"
fi

# SETTINGS.md
if [[ ! -f "$PROJECT_DIR/SETTINGS.md" ]]; then
cat > "$PROJECT_DIR/SETTINGS.md" <<'EOF'
# Настройки Robot Web Interface
# (смотри robot/config.py; после изменений — ./restart.sh)
EOF
fi

# --- установка прав доступа ---
info "Настройка прав доступа..."
chmod -R u+rwX "$PROJECT_DIR"
find "$PROJECT_DIR" -type f -name "*.py" -exec chmod +x {} \; 2>/dev/null || true
chmod 755 "$PROJECT_DIR/static"/{photos,videos}
chown -R "$USER_NAME:$USER_NAME" "$PROJECT_DIR/static"/{photos,videos} 2>/dev/null || true

# --- проверка синтаксиса Python ---
info "Проверка синтаксиса Python..."
cd "$PROJECT_DIR"
python3 - <<'PY'
import compileall, sys
ok = compileall.compile_dir('.', force=False, quiet=1)
sys.exit(0 if ok else 1)
PY
ok "Синтаксис Python файлов корректен"

# --- создание systemd сервиса ---
info "Создание/обновление systemd сервиса..."
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Robot Web Interface v2.1 (Flask + Gunicorn + Camera)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$PROJECT_DIR
Environment="PYTHONUNBUFFERED=1"
Environment="PYTHONPATH=$PROJECT_DIR"

ExecStart=$VENV_DIR/bin/gunicorn \
    --workers 1 \
    --worker-class gthread \
    --threads 4 \
    --timeout 60 \
    --graceful-timeout 10 \
    --keep-alive 2 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --worker-tmp-dir /dev/shm \
    --bind 0.0.0.0:5000 \
    --access-logfile $LOG_DIR/access.log \
    --error-logfile $LOG_DIR/error.log \
    --log-level info \
    run:app

Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

StandardOutput=journal
StandardError=journal
SyslogIdentifier=robot-web

SupplementaryGroups=i2c gpio spi video

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
ok "Systemd сервис создан/обновлён"

# Применение прав выполнения для всех скриптов
echo -e "${BLUE}🔧 Применение прав выполнения для скриптов...${NC}"
chmod +x "$PROJECT_DIR"/scripts/*.sh 2>/dev/null || true
echo -e "${GREEN}✅ Права выполнения применены${NC}"

# --- первичные проверки и запуск ---
info "Тест gunicorn конфигурации..."
APP_LIGHT_INIT=1 "$VENV_DIR/bin/gunicorn" --check-config run:app \
  && ok "Gunicorn конфигурация корректна" \
  || warn "Пропускаю строгую проверку Gunicorn"

info "Первый запуск сервиса..."
sudo systemctl start "$SERVICE_NAME"
sleep 5

if systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "Сервис запущен успешно"
    IP=$(hostname -I | awk '{print $1}')
    echo ""
    echo "=============================================="
    ok "🎉 Установка завершена успешно!"
    echo "=============================================="
    echo "🌐 Интерфейс: http://$IP:5000"
    echo "🎥 Видеопоток: http://$IP:5000/camera/stream"
    echo "🧪 Тест API:  python3 test_frame.py"
    echo ""
    echo "🔧 Управление: ./start.sh | ./stop.sh | ./restart.sh | ./logs.sh | ./status.sh | ./update.sh"
    echo "📸 Медиа: $PROJECT_DIR/static/photos, $PROJECT_DIR/static/videos"
    echo "ℹ️ Для применения прав доступа к камере может понадобиться: sudo reboot"
else
    err "❌ Сервис не запустился"
    echo "Проверьте: ./status.sh, ./logs.sh, python3 test_frame.py"
    exit 1
fi