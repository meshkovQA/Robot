#!/bin/bash
# setup.sh — установка веб-интерфейса робота с USB камерой v2.1 (без .env файла)

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
info "⚙️ Конфигурация через robot/config.py (без .env)"
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
mkdir -p "$PROJECT_DIR/static"/{photos,videos}

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
pip install flask>=2.3.0 gunicorn>=20.1.0 requests python-dotenv numpy smbus2 opencv-python flask-cors || true

# Проверяем доступность OpenCV
python3 -c "import cv2; print(f'✅ OpenCV {cv2.__version__} успешно импортирован')" || warn "OpenCV недоступен"

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

# --- создание SVG заглушки для камеры ---
info "Создание SVG заглушки для камеры..."
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

# --- создание тестового скрипта камеры ---
info "Создание тестового скрипта..."
cat > "$PROJECT_DIR/test_frame.py" <<'EOF'
#!/usr/bin/env python3
"""Тест получения одного кадра с камеры"""

import requests
import base64
import time
from pathlib import Path

def test_camera_frame():
    """Тестируем получение кадра через API"""
    
    base_url = "http://localhost:5000"
    
    print("🎥 Тест получения кадра с камеры")
    print("=" * 40)
    
    # 1. Проверяем статус камеры
    print("1. Проверка статуса камеры...")
    try:
        response = requests.get(f"{base_url}/api/camera/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"   Статус API: ✅ {response.status_code}")
            
            if data.get('success'):
                camera_data = data.get('data', {})
                print(f"   Камера доступна: {'✅' if camera_data.get('available') else '❌'}")
                print(f"   Камера подключена: {'✅' if camera_data.get('connected') else '❌'}")
                print(f"   FPS: {camera_data.get('fps', 0)}")
                print(f"   Разрешение: {camera_data.get('config', {}).get('resolution', 'неизвестно')}")
                
                if camera_data.get('error'):
                    print(f"   Ошибка: {camera_data['error']}")
            else:
                print(f"   ❌ API ошибка: {data.get('error', 'неизвестно')}")
        else:
            print(f"   ❌ HTTP ошибка: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка соединения: {e}")
        return False
    
    # 2. Получаем кадр
    print("\n2. Получение кадра...")
    try:
        response = requests.get(f"{base_url}/api/camera/frame", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"   Статус API: ✅ {response.status_code}")
            
            if data.get('success'):
                frame_data = data.get('data', {})
                frame_b64 = frame_data.get('frame')
                
                if frame_b64:
                    print(f"   ✅ Получен кадр (base64), размер: {len(frame_b64)} символов")
                    
                    # Сохраняем кадр как JPEG
                    try:
                        jpeg_data = base64.b64decode(frame_b64)
                        output_path = Path("test_frame.jpg")
                        output_path.write_bytes(jpeg_data)
                        print(f"   ✅ Кадр сохранен: {output_path} ({len(jpeg_data)} байт)")
                        return True
                    except Exception as e:
                        print(f"   ❌ Ошибка сохранения: {e}")
                        return False
                else:
                    print("   ❌ Нет данных кадра в ответе")
                    return False
            else:
                print(f"   ❌ API ошибка: {data.get('error', 'неизвестно')}")
                return False
        else:
            print(f"   ❌ HTTP ошибка: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка соединения: {e}")
        return False

if __name__ == "__main__":
    print("🤖 Тестирование камеры робота")
    print("Убедитесь что веб-сервер запущен: ./start.sh")
    print()
    
    time.sleep(1)
    success = test_camera_frame()
    
    print("\n" + "=" * 40)
    if success:
        print("🎉 Тест прошел успешно!")
        print("Откройте: http://localhost:5000")
    else:
        print("❌ Тест провалился")
        print("Проверьте:")
        print("1. Запущен ли сервер: ./start.sh")
        print("2. Логи: ./logs.sh")
        print("3. Камеру: ./test_camera.sh")
EOF

chmod +x "$PROJECT_DIR/test_frame.py"

# --- создание файла настроек конфигурации ---
info "Создание файла настроек конфигурации..."
cat > "$PROJECT_DIR/config_local.py" <<'EOF'
# config_local.py - Локальные настройки робота
# Этот файл можно редактировать для изменения конфигурации
# Импортируется после основного config.py и переопределяет значения

# ==================== ОСНОВНЫЕ НАСТРОЙКИ ====================

# I2C адрес Arduino (по умолчанию 0x08)
# ARDUINO_ADDRESS = 0x08

# Пороги остановки (в сантиметрах)
# SENSOR_FWD_STOP_CM = 15  # остановка при движении вперед
# SENSOR_BWD_STOP_CM = 10  # остановка при движении назад

# Скорость по умолчанию (0-255)
# DEFAULT_SPEED = 70

# ==================== НАСТРОЙКИ КАМЕРЫ ====================

# Основные параметры камеры
# CAMERA_DEVICE_ID = 0     # /dev/video0
# CAMERA_WIDTH = 640
# CAMERA_HEIGHT = 480
# CAMERA_FPS = 15

# Качество изображения (1-100)
# CAMERA_QUALITY = 70           # качество фото
# CAMERA_STREAM_QUALITY = 50    # качество видеопотока

# Предустановка качества: "low", "medium", "high", "ultra"
# CAMERA_PRESET = "low"

# ==================== ПОВОРОТЫ КАМЕРЫ ====================

# Ограничения углов поворота (0-180 градусов)
# CAMERA_PAN_MIN = 0
# CAMERA_PAN_MAX = 180
# CAMERA_PAN_DEFAULT = 90

# Ограничения углов наклона (50-150 градусов)
# CAMERA_TILT_MIN = 50
# CAMERA_TILT_MAX = 150
# CAMERA_TILT_DEFAULT = 90

# Шаг поворота (градусы за одну команду)
# CAMERA_STEP_SIZE = 10

# ==================== БЕЗОПАСНОСТЬ ====================

# API ключ для защиты (оставьте пустым для отключения)
# API_KEY = ""

# ==================== ЛОГИРОВАНИЕ ====================

# Уровень логирования: "DEBUG", "INFO", "WARNING", "ERROR"
# LOG_LEVEL = "INFO"

# Отладка камеры
# ENABLE_CAMERA_DEBUG = False

# ==================== РАСШИРЕННЫЕ ФУНКЦИИ ====================

# Автоматические функции (True/False)
# RECORD_ON_ROBOT_MOVE = False      # запись при движении
# PHOTO_ON_OBSTACLE = False         # фото при препятствии
# SAVE_FRAME_ON_EMERGENCY = True   # кадр при аварийной остановке

# Детекция движения
# ENABLE_MOTION_DETECTION = False
# AUTO_RECORD_ON_MOTION = False

# Наложения на видео
# ENABLE_VIDEO_OVERLAY = False
# OVERLAY_TIMESTAMP = False

# ==================== ИНСТРУКЦИИ ====================

"""
Для изменения настроек:
1. Раскомментируйте нужную строку (уберите # в начале)
2. Измените значение
3. Перезапустите сервис: ./restart.sh

Примеры:

# Изменить разрешение камеры на HD
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_PRESET = "high"

# Изменить пороги остановки
SENSOR_FWD_STOP_CM = 20
SENSOR_BWD_STOP_CM = 15

# Включить отладку
LOG_LEVEL = "DEBUG"
ENABLE_CAMERA_DEBUG = True

# Ограничить углы камеры
CAMERA_PAN_MIN = 30
CAMERA_PAN_MAX = 150
CAMERA_TILT_MIN = 60
CAMERA_TILT_MAX = 120
"""
EOF

# --- установка прав доступа ---
info "Настройка прав доступа..."
chmod -R u+rwX "$PROJECT_DIR"
find "$PROJECT_DIR" -type f -name "*.py" -exec chmod +x {} \; 2>/dev/null || true

# Права для папок с медиафайлами
chmod 755 "$PROJECT_DIR/static"/{photos,videos}
chown -R "$USER_NAME:$USER_NAME" "$PROJECT_DIR/static"/{photos,videos} 2>/dev/null || true

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

# Gunicorn: один воркер, потоковый класс
ExecStart=$VENV_DIR/bin/gunicorn \
    --workers 1 \
    --worker-class gthread \
    --threads 4 \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --bind 0.0.0.0:5000 \
    --access-logfile $LOG_DIR/access.log \
    --error-logfile $LOG_DIR/error.log \
    --log-level info \
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

# Безопасность
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
echo "🎥 Расширенное тестирование USB камеры..."

echo "📋 Доступные видеоустройства:"
ls -la /dev/video* 2>/dev/null || echo "Видеоустройства не найдены"

echo ""
echo "🔍 Информация о камерах:"
for device in /dev/video*; do
    if [[ -c "$device" ]]; then
        echo "Устройство: $device"
        v4l2-ctl --device="$device" --info 2>/dev/null | head -5 || echo "Ошибка чтения $device"
        echo "Поддерживаемые форматы:"
        v4l2-ctl --device="$device" --list-formats-ext 2>/dev/null | head -10 || echo "Ошибка чтения форматов"
        echo "---"
    fi
done

echo ""
echo "👥 Права доступа:"
echo "Пользователь: $USER"
echo "Группы: $(groups $USER)"
echo "Права на /dev/video0:"
ls -la /dev/video0 2>/dev/null || echo "/dev/video0 не найден"

echo ""
echo "🐍 Тест Python OpenCV:"
python3 -c "
import cv2
import sys
import time

print(f'OpenCV версия: {cv2.__version__}')

# Проверяем доступные камеры
available_cameras = []
for i in range(5):
    cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
    if cap.isOpened():
        ret, _ = cap.read()
        if ret:
            available_cameras.append(i)
        cap.release()

print(f'Доступные камеры: {available_cameras}')

if available_cameras:
    device_id = available_cameras[0]
    print(f'Тестируем камеру /dev/video{device_id}...')
    
    cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)
    if cap.isOpened():
        print(f'✅ Камера /dev/video{device_id} открыта успешно')
        
        # Настраиваем камеру
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)
        
        # Читаем несколько кадров
        success_count = 0
        for i in range(5):
            ret, frame = cap.read()
            if ret and frame is not None:
                success_count += 1
            time.sleep(0.2)
        
        if success_count > 2:
            print(f'✅ Получено {success_count}/5 кадров - камера работает!')
            print(f'Размер кадра: {frame.shape if \"frame\" in locals() else \"неизвестно\"}')
        else:
            print(f'⚠️ Получено только {success_count}/5 кадров - возможны проблемы')
        
        cap.release()
    else:
        print(f'❌ Не удалось открыть камеру /dev/video{device_id}')
else:
    print('❌ Камеры не найдены или недоступны')
"

echo ""
echo "🤖 Тест модуля робота:"
cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null || cd "$HOME/robot_web"

if [[ -f "robot/camera.py" ]]; then
    python3 -c "
import sys
sys.path.insert(0, '.')

try:
    from robot.camera import list_available_cameras, USBCamera, OPENCV_AVAILABLE
    print(f'OpenCV доступен: {OPENCV_AVAILABLE}')
    
    if OPENCV_AVAILABLE:
        cameras = list_available_cameras()
        print(f'Доступные камеры через модуль: {cameras}')
        
        if cameras:
            print('✅ Модуль камеры находит устройства')
        else:
            print('⚠️ Модуль не нашел камер')
    else:
        print('❌ OpenCV недоступен в модуле')
        
except Exception as e:
    print(f'❌ Ошибка модуля камеры: {e}')
"
else
    echo "❌ Файл robot/camera.py не найден"
fi

echo ""
echo "📝 Рекомендации:"
echo "1. Убедитесь что USB камера подключена"
echo "2. Проверьте права: groups \$USER (должно содержать video)"
echo "3. Если нет прав: sudo usermod -a -G video \$USER && sudo reboot"
echo "4. Попробуйте тест API: python3 test_frame.py"
echo "5. Проверьте логи: ./logs.sh | grep camera"
EOF

# Остальные скрипты...
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
echo "🧪 Тест камеры: python3 test_frame.py"
EOF

cat > "$PROJECT_DIR/logs.sh" <<EOF
#!/bin/bash
echo "📄 Логи Robot Web Interface (Ctrl+C для выхода):"
echo "================================================"
sudo journalctl -u $SERVICE_NAME -f --no-pager
EOF

cat > "$PROJECT_DIR/config.sh" <<'EOF'
#!/bin/bash
# config.sh - Управление конфигурацией робота

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$PROJECT_DIR/robot/config.py"

echo "⚙️ Управление конфигурацией Robot Web Interface"
echo "==============================================="

case "${1:-help}" in
    "edit")
        echo "📝 Открытие файла настроек в nano..."
        nano "$CONFIG_FILE"
        echo ""
        echo "Для применения изменений выполните: ./restart.sh"
        ;;
    
    "show")
        echo "📋 Текущие настройки:"
        echo "--------------------"
        python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')

try:
    from robot import config
    
    # Показываем основные настройки
    print(f'I2C_BUS: {config.I2C_BUS}')
    print(f'ARDUINO_ADDRESS: 0x{config.ARDUINO_ADDRESS:02X}')
    print(f'SENSOR_FWD_STOP_CM: {config.SENSOR_FWD_STOP_CM}')
    print(f'SENSOR_BWD_STOP_CM: {config.SENSOR_BWD_STOP_CM}')
    print(f'DEFAULT_SPEED: {config.DEFAULT_SPEED}')
    print()
    print('Камера:')
    print(f'  CAMERA_DEVICE_ID: {config.CAMERA_DEVICE_ID}')
    print(f'  CAMERA_WIDTH: {config.CAMERA_WIDTH}')
    print(f'  CAMERA_HEIGHT: {config.CAMERA_HEIGHT}')
    print(f'  CAMERA_FPS: {config.CAMERA_FPS}')
    print(f'  CAMERA_QUALITY: {config.CAMERA_QUALITY}')
    print()
    print('Повороты камеры:')
    print(f'  PAN: {config.CAMERA_PAN_MIN}-{config.CAMERA_PAN_MAX} (по умолчанию {config.CAMERA_PAN_DEFAULT})')
    print(f'  TILT: {config.CAMERA_TILT_MIN}-{config.CAMERA_TILT_MAX} (по умолчанию {config.CAMERA_TILT_DEFAULT})')
    print(f'  STEP_SIZE: {config.CAMERA_STEP_SIZE}')
    print()
    print(f'LOG_LEVEL: {config.LOG_LEVEL}')
    print(f'API_KEY: {\"установлен\" if config.API_KEY else \"не установлен\"}')
    
except Exception as e:
    print(f'Ошибка чтения конфигурации: {e}')
"
        ;;
    
    "test")
        echo "🧪 Тест конфигурации:"
        echo "--------------------"
        python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')

try:
    from robot.config import *
    from robot.camera import list_available_cameras
    
    print(f'✅ Конфигурация загружена')
    print(f'✅ I2C доступен: {I2C_AVAILABLE}')
    print(f'✅ OpenCV доступен: {CAMERA_AVAILABLE}')
    
    if CAMERA_AVAILABLE:
        cameras = list_available_cameras()
        print(f'✅ Найдено камер: {len(cameras)} {cameras}')
    
    # Проверка валидности настроек
    errors = validate_camera_config()
    if errors:
        print('⚠️ Предупреждения конфигурации:')
        for error in errors:
            print(f'   - {error}')
    else:
        print('✅ Конфигурация камеры валидна')
        
except Exception as e:
    print(f'❌ Ошибка: {e}')
"
        ;;
    
    "backup")
        BACKUP_FILE="$PROJECT_DIR/config_backup_$(date +%Y%m%d_%H%M%S).py"
        cp "$CONFIG_FILE" "$BACKUP_FILE" 2>/dev/null && echo "✅ Бэкап создан: $BACKUP_FILE" || echo "❌ Ошибка создания бэкапа"
        ;;
    
    "help"|*)
        echo "Использование: ./config.sh [команда]"
        echo ""
        echo "Команды:"
        echo "  edit    - редактировать robot/config.py в nano"
        echo "  show    - показать текущие настройки"
        echo "  test    - проверить конфигурацию"
        echo "  backup  - создать бэкап настроек"
        echo "  help    - показать эту справку"
        echo ""
        echo "Файл настроек: $CONFIG_FILE"
        echo "После изменений: ./restart.sh"
        echo ""
        echo "📖 Документация по настройкам: cat SETTINGS.md"
        ;;
esac
EOF