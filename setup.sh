#!/bin/bash
# setup.sh — установка веб-интерфейса робота с USB камерой v2.1

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
ENV_FILE="$PROJECT_DIR/.env"
SERVICE_NAME="robot-web.service"

# Ваш репозиторий (raw):
GITHUB_RAW="https://raw.githubusercontent.com/meshkovQA/Robot/main"

# Файлы проекта с поддержкой камеры
declare -A PROJECT_FILES=(
    # Python модули
    ["run.py"]="run.py"
    ["robot/__init__.py"]="robot/__init__.py"
    ["robot/config.py"]="robot/config.py"
    ["robot/i2c_bus.py"]="robot/i2c_bus.py"
    ["robot/controller.py"]="robot/controller.py"
    ["robot/camera.py"]="robot/camera.py"
    ["robot/api.py"]="robot/api.py"
    
    # Веб-интерфейс
    ["templates/index.html"]="templates/index.html"
    ["static/style.css"]="static/style.css"
    ["static/script.js"]="static/script.js"
    ["static/camera.js"]="static/camera.js"
    
    # Документация
    ["README.md"]="README.md"
)

echo "=============================================="
info "🤖📹 Установка веб-интерфейса робота с USB камерой v2.1"
info "📁 Репозиторий: https://github.com/meshkovQA/Robot"
info "🎥 Новая поддержка USB камеры + видеозапись"
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

# Ищем USB камеры
USB_CAMERAS=$(lsusb | grep -i -E "(camera|webcam|uvc)" | wc -l || true)
V4L_DEVICES=$(ls /dev/video* 2>/dev/null | wc -l || echo "0")

if [[ $V4L_DEVICES -gt 0 ]]; then
    ok "Найдено USB камер: $V4L_DEVICES"
    info "Список видеоустройств:"
    ls -la /dev/video* 2>/dev/null || true
    
    # Показываем информацию о камерах
    for device in /dev/video*; do
        if [[ -c "$device" ]]; then
            info "Устройство: $device"
            v4l2-ctl --device="$device" --info 2>/dev/null | head -5 || true
        fi
    done
else
    warn "USB камеры не обнаружены"
    warn "Убедитесь что USB камера подключена и поддерживается"
    warn "Система продолжит установку, но камера будет недоступна"
fi

# Права доступа к видеоустройствам
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

# Добавляем пользователя в группы
sudo usermod -a -G i2c,gpio,spi,video "$USER_NAME" || true

# Проверка что пользователь действительно в группе video
if ! groups "$USER_NAME" | grep -q video; then
    warn "Пользователь не в группе video. Попробуем добавить принудительно..."
    sudo usermod -a -G video "$USER_NAME"
    warn "Требуется перезагрузка для применения прав доступа к камере"
fi

# --- создание структуры проекта ---
info "Создание структуры проекта в $PROJECT_DIR ..."
mkdir -p "$PROJECT_DIR"/{robot,templates,static,logs,photos,videos}

# Создаем символические ссылки для веб-доступа к медиафайлам
ln -sf "$PROJECT_DIR/photos" "$PROJECT_DIR/static/photos" 2>/dev/null || true
ln -sf "$PROJECT_DIR/videos" "$PROJECT_DIR/static/videos" 2>/dev/null || true

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

# Основные зависимости
pip install flask>=2.3.0 gunicorn>=20.1.0 

# I2C библиотека (может не установиться на некоторых системах)
pip install smbus2 || warn "smbus2 не установлен - будет работать в режиме эмуляции"

# OpenCV для Python (если не установлен через apt)
pip install opencv-python>=4.5.0 || warn "opencv-python не установлен через pip"

# Дополнительные зависимости
pip install requests python-dotenv numpy

# Проверяем доступность OpenCV
python3 -c "import cv2; print(f'✅ OpenCV {cv2.__version__} успешно импортирован')" || warn "OpenCV недоступен"

# --- создание расширенного .env файла ---
if [[ ! -f "$ENV_FILE" ]]; then
    info "Создание файла конфигурации .env ..."
    cat > "$ENV_FILE" <<'EOF'
# === Переменные окружения для Robot Web v2.1 с камерой ===

# API Key для защиты (оставьте пустым для отключения аутентификации)
API_KEY=

# I2C настройки
I2C_BUS=1
ARDUINO_ADDRESS=0x08

# Пороговые значения датчиков (см)
SENSOR_FWD_STOP_CM=15
SENSOR_BWD_STOP_CM=10
SENSOR_MAX_VALID=500

# Настройки скорости (0-255)
DEFAULT_SPEED=70
SPEED_MIN=0
SPEED_MAX=255

# === НАСТРОЙКИ КАМЕРЫ ===

# Основные параметры
CAMERA_DEVICE_ID=0
CAMERA_WIDTH=640
CAMERA_HEIGHT=480
CAMERA_FPS=30

# Качество изображения (1-100)
CAMERA_QUALITY=80
CAMERA_STREAM_QUALITY=60
CAMERA_STREAM_FPS=15

# Настройки изображения (0-100)
CAMERA_BRIGHTNESS=50
CAMERA_CONTRAST=50
CAMERA_SATURATION=50

# Пути сохранения
CAMERA_SAVE_PATH=$HOME_DIR/robot_web/photos
CAMERA_VIDEO_PATH=$HOME_DIR/robot_web/videos

# Автозапуск
CAMERA_AUTO_START=true

# Предустановка качества (low/medium/high/ultra)
CAMERA_PRESET=medium

# Ограничения файлов
MAX_PHOTOS=100
MAX_VIDEOS=20
MAX_PHOTO_SIZE=10485760
MAX_VIDEO_SIZE=104857600

# Автоочистка (дни)
AUTO_CLEANUP_DAYS=7

# === РАСШИРЕННЫЕ ФУНКЦИИ ===

# Детекция движения
ENABLE_MOTION_DETECTION=false
MOTION_THRESHOLD=30

# Автозапись
AUTO_RECORD_ON_MOTION=false
AUTO_RECORD_DURATION=30

# Интеграция с роботом
RECORD_ON_ROBOT_MOVE=false
PHOTO_ON_OBSTACLE=false
SAVE_FRAME_ON_EMERGENCY=true

# Наложения на видео
ENABLE_VIDEO_OVERLAY=true
OVERLAY_TIMESTAMP=true
OVERLAY_ROBOT_STATUS=false

# === СИСТЕМА ===

# Логирование
LOG_LEVEL=INFO
CAMERA_LOG_LEVEL=INFO
ENABLE_CAMERA_DEBUG=false

# Производительность
VIDEO_BUFFER_SIZE=1
CAMERA_THREADS=2
CAMERA_INIT_TIMEOUT=10
CAMERA_CAPTURE_TIMEOUT=5

# Flask настройки
FLASK_ENV=production
FLASK_DEBUG=False
EOF
    ok "Создан .env файл с конфигурацией камеры"
else
    warn ".env файл уже существует - пропускаю создание"
fi

# --- функция загрузки файлов ---
download_file() {
    local remote_path="$1"
    local local_path="$2"
    local url="$GITHUB_RAW/$remote_path"
    
    info "Скачивание $remote_path -> $local_path"
    
    # Создаем директорию если нужно
    mkdir -p "$(dirname "$PROJECT_DIR/$local_path")"
    
    # Скачиваем файл
    if curl -fsSL "$url" -o "$PROJECT_DIR/$local_path"; then
        ok "✓ $local_path"
    else
        err "✗ Не удалось скачать $remote_path"
        return 1
    fi
}

# --- загрузка файлов проекта ---
info "Загрузка файлов проекта из GitHub..."

failed_downloads=()
for remote_path in "${!PROJECT_FILES[@]}"; do
    local_path="${PROJECT_FILES[$remote_path]}"
    if ! download_file "$remote_path" "$local_path"; then
        failed_downloads+=("$remote_path")
    fi
done

# Проверяем критические файлы
critical_files=("run.py" "robot/api.py" "robot/controller.py" "robot/camera.py" "robot/config.py")
missing_critical=()

for file in "${critical_files[@]}"; do
    if [[ ! -f "$PROJECT_DIR/$file" ]]; then
        missing_critical+=("$file")
    fi
done

if [[ ${#missing_critical[@]} -gt 0 ]]; then
    err "Критические файлы не найдены: ${missing_critical[*]}"
    err "Установка не может продолжиться"
    exit 1
fi

# --- создание заглушки для отсутствующей камеры ---
info "Создание изображения-заглушки для камеры..."
cat > "$PROJECT_DIR/static/no-camera.png" <<'EOF'
# Создаем простое SVG изображение как заглушку
<svg width="640" height="480" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f8f9fa"/>
  <text x="50%" y="40%" text-anchor="middle" font-family="Arial" font-size="24" fill="#6c757d">📹</text>
  <text x="50%" y="55%" text-anchor="middle" font-family="Arial" font-size="16" fill="#6c757d">Камера недоступна</text>
  <text x="50%" y="70%" text-anchor="middle" font-family="Arial" font-size="12" fill="#adb5bd">Проверьте подключение USB камеры</text>
</svg>
EOF

# --- установка прав доступа ---
info "Настройка прав доступа..."
chmod -R u+rwX "$PROJECT_DIR"
find "$PROJECT_DIR" -type f -name "*.py" -exec chmod +x {} \; 2>/dev/null || true

# Права для папок с медиафайлами
chmod 755 "$PROJECT_DIR"/{photos,videos}
chown -R "$USER_NAME:$USER_NAME" "$PROJECT_DIR"/{photos,videos} 2>/dev/null || true

# --- проверка синтаксиса Python ---
info "Проверка синтаксиса Python файлов..."
cd "$PROJECT_DIR"

if python3 -m py_compile run.py robot/*.py; then
    ok "Синтаксис Python файлов корректен"
else
    err "Ошибки в синтаксисе Python файлов"
    exit 1
fi

# Проверяем импорт камеры
if python3 -c "from robot.camera import USBCamera; print('✅ Модуль камеры импортирован успешно')"; then
    ok "Модуль камеры работает"
else
    warn "Проблемы с модулем камеры - некоторые функции могут быть недоступны"
fi

# --- создание systemd сервиса ---
info "Создание systemd сервиса..."
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
EnvironmentFile=$ENV_FILE

# Gunicorn с оптимизированными настройками для камеры
ExecStart=$VENV_DIR/bin/gunicorn \
    --workers 2 \
    --threads 4 \
    --timeout 60 \
    --keep-alive 10 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --bind 0.0.0.0:5000 \
    --access-logfile $LOG_DIR/access.log \
    --error-logfile $LOG_DIR/error.log \
    --log-level info \
    --worker-class sync \
    run:app

# Перезапуск при сбоях
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

# Логирование
StandardOutput=journal
StandardError=journal
SyslogIdentifier=robot-web

# Доступ к устройствам
SupplementaryGroups=i2c gpio spi video

# Безопасность (ослаблены для доступа к камере)
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Перезагружаем systemd и включаем автозапуск
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
ok "Systemd сервис создан и включен для автозапуска"

# --- создание вспомогательных скриптов ---
info "Создание управляющих скриптов..."

# Скрипт тестирования камеры
cat > "$PROJECT_DIR/test_camera.sh" <<'EOF'
#!/bin/bash
echo "🎥 Тестирование USB камеры..."

echo "📋 Доступные видеоустройства:"
ls -la /dev/video* 2>/dev/null || echo "Видеоустройства не найдены"

echo ""
echo "🔍 Информация о камерах:"
for device in /dev/video*; do
    if [[ -c "$device" ]]; then
        echo "Устройство: $device"
        v4l2-ctl --device="$device" --info 2>/dev/null | head -5 || echo "Ошибка чтения $device"
        echo "---"
    fi
done

echo ""
echo "🐍 Тест Python OpenCV:"
python3 -c "
import cv2
import sys

print(f'OpenCV версия: {cv2.__version__}')

# Пробуем открыть камеру
cap = cv2.VideoCapture(0)
if cap.isOpened():
    ret, frame = cap.read()
    if ret:
        print('✅ Камера работает, получен кадр:', frame.shape)
    else:
        print('❌ Камера открыта, но не может захватить кадр')
    cap.release()
else:
    print('❌ Не удалось открыть камеру')
"

echo ""
echo "🤖 Тест модуля робота:"
cd /home/pi/robot_web
python3 -c "
from robot.camera import list_available_cameras, create_camera
try:
    cameras = list_available_cameras()
    print(f'Доступные камеры: {cameras}')
    if cameras:
        print('✅ Модуль камеры робота работает')
    else:
        print('⚠️ Камеры найдены, но модуль не может их использовать')
except Exception as e:
    print(f'❌ Ошибка модуля камеры: {e}')
"
EOF

# Остальные скрипты (start.sh, stop.sh, restart.sh) такие же как раньше...
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

cat > "$PROJECT_DIR/restart.sh" <<EOF
#!/bin/bash
echo "🔄 Перезапуск Robot Web Interface v2.1..."
sudo systemctl restart $SERVICE_NAME
sleep 3
sudo systemctl status $SERVICE_NAME --no-pager -l
echo ""
IP=\$(hostname -I | awk '{print \$1}')
echo "🌐 Интерфейс доступен: http://\$IP:5000"
echo "🎥 Видеопоток: http://\$IP:5000/camera/stream"
EOF

cat > "$PROJECT_DIR/logs.sh" <<EOF
#!/bin/bash
echo "📄 Логи Robot Web Interface (Ctrl+C для выхода):"
echo "================================================"
sudo journalctl -u $SERVICE_NAME -f --no-pager
EOF

# Расширенный скрипт диагностики с камерой
cat > "$PROJECT_DIR/status.sh" <<'EOF'
#!/bin/bash
SERVICE=robot-web.service
echo "🔍 Диагностика Robot Web Interface v2.1"
echo "========================================"

echo "📊 Статус сервиса:"
sudo systemctl status "$SERVICE" --no-pager -l

echo -e "\n🌐 Сетевые подключения:"
sudo netstat -tlnp 2>/dev/null | grep :5000 || echo "Порт 5000 не занят"

echo -e "\n🔌 I2C устройства:"
if command -v i2cdetect &>/dev/null; then 
    sudo i2cdetect -y 1 2>/dev/null || echo "Ошибка чтения I2C шины"
else 
    echo "i2c-tools не установлены"
fi

echo -e "\n🎥 USB камеры:"
ls -la /dev/video* 2>/dev/null || echo "Видеоустройства не найдены"

echo -e "\n📹 Информация о камерах:"
for device in /dev/video*; do
    if [[ -c "$device" ]]; then
        echo "├─ $device:"
        v4l2-ctl --device="$device" --info 2>/dev/null | head -3 | sed 's/^/│  /' || echo "│  Ошибка чтения"
    fi
done

echo -e "\n💾 Использование ресурсов:"
if pgrep -f "robot.*gunicorn" >/dev/null; then
    ps aux | grep -E "(robot|gunicorn)" | grep -v grep
else
    echo "Процессы Robot Web не найдены"
fi

echo -e "\n📁 Файлы проекта:"
ls -la /home/*/robot_web/ 2>/dev/null | head -10

echo -e "\n📸 Медиафайлы:"
PHOTOS_COUNT=$(find $HOME_DIR/robot_web/photos -name "*.jpg" 2>/dev/null | wc -l || echo "0")
VIDEOS_COUNT=$(find $HOME_DIR/robot_web/videos -name "*.mp4" 2>/dev/null | wc -l || echo "0")
echo "Фотографий: $PHOTOS_COUNT"
echo "Видеофайлов: $VIDEOS_COUNT"

echo -e "\n🐍 Python модули:"
python3 -c "
try:
    import cv2
    print(f'✅ OpenCV {cv2.__version__}')
except:
    print('❌ OpenCV недоступен')

try:
    import smbus2
    print('✅ smbus2 (I2C)')
except:
    print('❌ smbus2 недоступен')

try:
    from robot.camera import USBCamera
    print('✅ robot.camera')
except Exception as e:
    print(f'❌ robot.camera: {e}')
"

echo -e "\n📄 Последние логи:"
sudo journalctl -u "$SERVICE" --no-pager -n 10

echo -e "\n🌡️ Системная информация:"
echo "Время работы: $(uptime -p)"
echo "Нагрузка: $(uptime | awk -F'load average:' '{print $2}')"
echo "Память: $(free -h | awk '/^Mem:/ {print $3 "/" $2}')"
echo "Диск: $(df -h / | awk 'NR==2 {print $3 "/" $2 " (" $5 ")"}')"

IP=$(hostname -I | awk '{print $1}')
echo -e "\n🔗 Адреса:"
echo "Веб-интерфейс: http://$IP:5000"
echo "Видеопоток: http://$IP:5000/camera/stream"
echo "API статус: http://$IP:5000/api/status"
echo "API камера: http://$IP:5000/api/camera/status"
EOF

# Скрипт обновления (расширенный)
cat > "$PROJECT_DIR/update.sh" <<'EOF'
#!/bin/bash
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
echo -e "${BLUE}🔄 Обновление Robot Web Interface v2.1${NC}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_RAW="https://raw.githubusercontent.com/meshkovQA/Robot/main"

# Список файлов для обновления (включая камеру)
declare -A FILES=(
    ["run.py"]="run.py"
    ["robot/__init__.py"]="robot/__init__.py"
    ["robot/config.py"]="robot/config.py"
    ["robot/i2c_bus.py"]="robot/i2c_bus.py"
    ["robot/controller.py"]="robot/controller.py"
    ["robot/camera.py"]="robot/camera.py"
    ["robot/api.py"]="robot/api.py"
    ["templates/index.html"]="templates/index.html"
    ["static/style.css"]="static/style.css"
    ["static/script.js"]="static/script.js"
    ["static/camera.js"]="static/camera.js"
    ["README.md"]="README.md"
)

backup_and_download() {
    local remote="$1"
    local local="$2"
    local url="$GITHUB_RAW/$remote"
    local full_path="$PROJECT_DIR/$local"
    
    # Создаем директорию
    mkdir -p "$(dirname "$full_path")"
    
    # Бэкап существующего файла
    if [[ -f "$full_path" ]]; then
        cp "$full_path" "$full_path.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # Скачиваем новую версию
    if curl -fsSL "$url" -o "$full_path"; then
        echo -e "✅ $local"
        return 0
    else
        echo -e "${RED}❌ $local${NC}"
        return 1
    fi
}

echo -e "${YELLOW}⏸️ Остановка сервиса...${NC}"
sudo systemctl stop robot-web.service || true

echo -e "${BLUE}📥 Загрузка файлов...${NC}"
failed_files=()

for remote in "${!FILES[@]}"; do
    local="${FILES[$remote]}"
    if ! backup_and_download "$remote" "$local"; then
        failed_files+=("$local")
    fi
done

if [[ ${#failed_files[@]} -gt 0 ]]; then
    echo -e "${YELLOW}⚠️ Не удалось обновить: ${failed_files[*]}${NC}"
fi

echo -e "${BLUE}🔍 Проверка синтаксиса...${NC}"
cd "$PROJECT_DIR"
if python3 -m py_compile run.py robot/*.py; then
    echo -e "${GREEN}✅ Синтаксис корректен${NC}"
else
    echo -e "${RED}❌ Ошибки в синтаксисе!${NC}"
    exit 1
fi

echo -e "${BLUE}🎥 Проверка модуля камеры...${NC}"
if python3 -c "from robot.camera import USBCamera; print('Камера OK')"; then
    echo -e "${GREEN}✅ Модуль камеры работает${NC}"
else
    echo -e "${YELLOW}⚠️ Проблемы с модулем камеры${NC}"
fi

echo -e "${BLUE}🚀 Запуск сервиса...${NC}"
sudo systemctl start robot-web.service

sleep 3

if systemctl is-active --quiet robot-web.service; then
    echo -e "${GREEN}✅ Обновление завершено успешно!${NC}"
    IP=$(hostname -I | awk '{print $1}')
    echo -e "${GREEN}🌐 Интерфейс: http://$IP:5000${NC}"
    echo -e "${GREEN}🎥 Видеопоток: http://$IP:5000/camera/stream${NC}"
else
    echo -e "${RED}❌ Сервис не запустился после обновления${NC}"
    echo "Проверьте логи: ./logs.sh"
    exit 1
fi
EOF

# Установка прав на выполнение для всех скриптов
chmod +x "$PROJECT_DIR"/{start.sh,stop.sh,restart.sh,logs.sh,status.sh,update.sh,test_camera.sh}
ok "Управляющие скрипты созданы"

# --- тестирование камеры ---
info "Тестирование камеры..."
cd "$PROJECT_DIR"
bash test_camera.sh

# --- проверка установки ---
info "Проверка установки..."

# Проверяем Python модули
cd "$PROJECT_DIR"
if python3 -c "from robot.api import create_app; from robot.camera import USBCamera; print('✓ Все модули импортированы успешно')"; then
    ok "Python модули работают корректно"
else
    warn "Есть проблемы с Python модулями, но основная функциональность может работать"
fi

info "Тестирование запуска приложения..."
cd "$PROJECT_DIR"
if timeout 10 python3 run.py --help >/dev/null 2>&1; then
    ok "run.py доступен"
else
    warn "Проблемы с run.py"
fi

# Тест gunicorn
if timeout 5 "$VENV_DIR/bin/gunicorn" --check-config run:app; then
    ok "Gunicorn конфигурация корректна"
else
    err "Проблемы с конфигурацией Gunicorn"
fi

# --- первый запуск ---
info "Первый запуск сервиса..."
sudo systemctl start "$SERVICE_NAME"
sleep 5

# Проверяем статус
if systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "Сервис запущен успешно"
    
    # Получаем IP адрес
    IP=$(hostname -I | awk '{print $1}')
    
    echo ""
    echo "=============================================="
    ok "🎉 Установка завершена успешно!"
    echo "=============================================="
    echo ""
    echo "🌐 Веб-интерфейс доступен по адресу:"
    echo "   http://$IP:5000"
    echo ""
    echo "🎥 Прямой видеопоток:"
    echo "   http://$IP:5000/camera/stream"
    echo ""
    echo "🎮 Управление сервисом:"
    echo "   ./start.sh       - запуск"
    echo "   ./stop.sh        - остановка"  
    echo "   ./restart.sh     - перезапуск"
    echo "   ./logs.sh        - просмотр логов"
    echo "   ./status.sh      - диагностика"
    echo "   ./update.sh      - обновление"
    echo "   ./test_camera.sh - тест камеры"
    echo ""
    echo "📂 Файлы проекта: $PROJECT_DIR"
    echo "⚙️ Конфигурация: $ENV_FILE"
    echo "📸 Фотографии: $PROJECT_DIR/photos"
    echo "🎬 Видео: $PROJECT_DIR/videos"
    echo ""
    
    # Информация о камере
    if [[ $V4L_DEVICES -gt 0 ]]; then
        echo "📹 Камера:"
        echo "   Найдено устройств: $V4L_DEVICES"
        echo "   Основное устройство: /dev/video0"
        echo "   Управление: P - фото, R - запись"
    else
        echo "⚠️ Камера:"
        echo "   USB камеры не обнаружены"
        echo "   Подключите USB камеру и перезапустите сервис"
    fi
    
    echo ""
    
    if [[ ${#failed_downloads[@]} -gt 0 ]]; then
        warn "⚠️ Некоторые файлы не загружены: ${failed_downloads[*]}"
        warn "Используйте ./update.sh для повторной загрузки"
    fi
    
    echo "🔧 Для применения всех прав доступа выполните:"
    echo "   sudo reboot"
    echo ""
    echo "📚 Документация и примеры:"
    echo "   https://github.com/meshkovQA/Robot"
    
else
    err "❌ Сервис не запустился"
    echo ""
    echo "🔍 Диагностика:"
    echo "   ./status.sh      - полная диагностика"
    echo "   ./test_camera.sh - тест камеры"
    echo "   ./logs.sh        - просмотр ошибок"
    echo ""
    echo "📄 Логи ошибок:"
    sudo journalctl -u "$SERVICE_NAME" --no-pager -n 20
    exit 1
fi