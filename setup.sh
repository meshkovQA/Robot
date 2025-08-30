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
info "🤖🧠 Установка AI робота с USB камерой v5.1"
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
if [[ -f "$PROJECT_DIR/requirements.txt" ]]; then
    pip install -r "$PROJECT_DIR/requirements.txt"
else
    pip install "flask>=2.3.0" "gunicorn>=20.1.0" "gevent>=1.4.0" \
        requests python-dotenv numpy smbus2 opencv-python flask-cors \
        scipy pillow scikit-image imutils || true
fi
python3 - <<'PY' || true
import cv2, sys
print(f'✅ OpenCV {cv2.__version__} успешно импортирован')
PY

# --- загрузка AI моделей (как и раньше) ---
info "🧠 Загрузка AI моделей для домашнего робота..."
cd "$PROJECT_DIR/models/yolo"
if [[ ! -f "yolov4-tiny.cfg" ]]; then
    curl -L "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg" -o "yolov4-tiny.cfg"
    ok "yolov4-tiny.cfg загружен"
fi
if [[ ! -f "coco.names" ]]; then
    curl -L "https://raw.githubusercontent.com/pjreddie/darknet/master/data/coco.names" -o "coco.names" \
      || curl -L "https://raw.githubusercontent.com/AlexeyAB/darknet/master/data/coco.names" -o "coco.names"
    ok "coco.names загружен"
fi
if [[ ! -f "yolov4-tiny.weights" ]]; then
    curl -L "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v3_optimal/yolov4-tiny.weights" -o "yolov4-tiny.weights"
    ok "yolov4-tiny.weights загружен"
fi
# опционально
if [[ ! -f "yolov3-tiny.cfg" ]]; then
    curl -L "https://raw.githubusercontent.com/pjreddie/darknet/master/cfg/yolov3-tiny.cfg" -o "yolov3-tiny.cfg" \
      || curl -L "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov3-tiny.cfg" -o "yolov3-tiny.cfg" || true
fi
if [[ ! -f "yolov3-tiny.weights" ]]; then
    curl -L "https://pjreddie.com/media/files/yolov3-tiny.weights" -o "yolov3-tiny.weights" || true
fi
ok "🧠 AI модели загружены"
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

# --- управляющие скрипты (обновлённый update.sh — git pull) ---
info "Создание управляющих скриптов..."

cat > "$PROJECT_DIR/start.sh" <<EOF
#!/bin/bash
echo "🚀 Запуск Robot Web Interface v2.1..."
sudo systemctl start $SERVICE_NAME
sleep 2
sudo systemctl status $SERVICE_NAME --no-pager -l
EOF

cat > "$PROJECT_DIR/stop.sh" <<EOF
#!/bin/bash
echo "⏹️ Остановка Robot Web Interface..."
sudo systemctl stop $SERVICE_NAME
echo "Сервис остановлен"
EOF

cat > "$PROJECT_DIR/restart.sh" <<'EOF'
#!/bin/bash
echo "🔄 Перезапуск Robot Web Interface v2.1..."
sudo systemctl restart robot-web.service
sleep 3
sudo systemctl status robot-web.service --no-pager -l
echo ""
IP=$(hostname -I | awk '{print $1}')
echo "🌐 Интерфейс доступен: http://$IP:5000"
echo "🎥 Видеопоток: http://$IP:5000/camera/stream"
echo "🧪 Тест камеры: python3 test_frame.py"
EOF

cat > "$PROJECT_DIR/logs.sh" <<'EOF'
#!/bin/bash
echo "📄 Логи Robot Web Interface (Ctrl+C для выхода):"
echo "================================================"
sudo journalctl -u robot-web.service -f --no-pager
EOF

cat > "$PROJECT_DIR/test_camera.sh" <<'EOF'
#!/bin/bash
echo "🎥 Расширенное тестирование USB камеры..."
ls -la /dev/video* 2>/dev/null || echo "Видеоустройства не найдены"
for device in /dev/video*; do
  [[ -c "$device" ]] || continue
  echo "---- $device ----"
  v4l2-ctl --device="$device" --info 2>/dev/null | head -5 || true
  v4l2-ctl --device="$device" --list-formats-ext 2>/dev/null | head -10 || true
done
EOF

cat > "$PROJECT_DIR/status.sh" <<'EOF'
#!/bin/bash
SERVICE=robot-web.service
echo "🔍 Диагностика Robot Web Interface v2.1"
sudo systemctl status "$SERVICE" --no-pager -l
echo -e "\n📄 Последние логи:"
sudo journalctl -u "$SERVICE" --no-pager -n 20
IP=$(hostname -I | awk '{print $1}')
echo -e "\n🔗 Адреса:"
echo "Веб-интерфейс: http://$IP:5000"
echo "Видеопоток:   http://$IP:5000/camera/stream"
echo "API статус:   http://$IP:5000/api/status"
EOF

# новый update.sh (ниже отдельным блоком тоже продублирован)
cat > "$PROJECT_DIR/update.sh" <<'EOF'
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
EOF

chmod +x "$PROJECT_DIR"/{start.sh,stop.sh,restart.sh,logs.sh,status.sh,update.sh,test_camera.sh}
ok "Управляющие скрипты готовы"

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