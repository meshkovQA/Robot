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
    ["robot/api/__init__.py"]="robot/api/__init__.py"
    ["robot/ai_vision/__init__.py"]="robot/ai_vision/__init__.py"
    ["robot/devices/__init__.py"]="robot/devices/__init__.py"
    ["robot/config.py"]="robot/config.py"
    ["robot/i2c_bus.py"]="robot/i2c_bus.py"
    ["robot/controller.py"]="robot/controller.py"
    ["robot/devices/camera.py"]="robot/devices/camera.py"
    ["robot/api/api.py"]="robot/api/api.py"
    ["robot/devices/imu.py"]="robot/devices/imu.py"
    ["robot/heading_controller.py"]="robot/heading_controller.py"
    ["robot/ai_vision/ai_vision.py"]="robot/ai_vision/ai_vision.py"
    ["robot/ai_vision/home_ai_vision.py"]="robot/ai_vision/home_ai_vision.py"
    ["robot/ai_integration.py"]="robot/ai_integration.py"
    ["robot/api/ai_api_extensions.py"]="robot/api/ai_api_extensions.py"

    # Веб-интерфейс
    ["templates/index.html"]="templates/index.html"
    ["static/style.css"]="static/style.css"
    ["static/script.js"]="static/script.js"
    ["static/camera.js"]="static/camera.js"
    ["static/ai-control.js"]="static/ai-control.js"
    ["static/imu-control.js"]="static/imu-control.js"
    ["static/camera-control.js"]="static/camera-control.js"
    
    # Документация
    ["README.md"]="README.md"
)

echo "=============================================="
info "🤖🧠 Установка AI робота с USB камерой v5.0"
info "📁 Репозиторий: https://github.com/meshkovQA/Robot"
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
pip install flask>=2.3.0 gunicorn>=20.1.0 requests python-dotenv numpy smbus2 opencv-python flask-cors scipy pillow scikit-image imutils || true

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

# --- загрузка AI моделей ---
info "🧠 Загрузка AI моделей для домашнего робота..."

mkdir -p "$PROJECT_DIR/models/yolo"
cd "$PROJECT_DIR/models/yolo"

# YOLOv4-tiny конфигурация
if [[ ! -f "yolov4-tiny.cfg" ]]; then
    info "Загрузка YOLOv4-tiny конфигурации..."
    curl -L "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg" -o "yolov4-tiny.cfg"
    ok "✅ yolov4-tiny.cfg загружен"
fi

# YOLOv4-tiny веса (23MB)
if [[ ! -f "yolov4-tiny.weights" ]]; then
    info "Загрузка YOLOv4-tiny весов (23MB)..."
    curl -L "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v3_optimal/yolov4-tiny.weights" -o "yolov4-tiny.weights"
    ok "✅ yolov4-tiny.weights загружен"
fi

# Домашние классы объектов
cat > "home.names" << 'HOME_CLASSES'
person
cat
dog
chair
sofa
bed
diningtable
bottle
cup
bowl
laptop
mouse
remote
keyboard
cell phone
microwave
oven
toaster
sink
refrigerator
book
clock
vase
scissors
backpack
handbag
umbrella
bicycle
car
plant
tv
toilet
HOME_CLASSES

# Домашний маппинг COCO -> домашние объекты
cat > "home_mapping.py" << 'MAPPING_CODE'
"""Маппинг COCO классов на домашние объекты"""

HOME_OBJECT_MAPPING = {
    0: "person", 15: "cat", 16: "dog", 39: "bottle", 41: "cup", 46: "bowl",
    56: "chair", 57: "sofa", 58: "plant", 59: "bed", 60: "diningtable", 
    61: "toilet", 62: "tv", 63: "laptop", 64: "mouse", 65: "remote", 
    66: "keyboard", 67: "cell phone", 68: "microwave", 69: "oven", 
    70: "toaster", 71: "sink", 72: "refrigerator", 73: "book", 
    74: "clock", 75: "vase", 76: "scissors", 24: "backpack", 
    26: "handbag", 25: "umbrella", 1: "bicycle", 2: "car"
}

SIMPLIFIED_NAMES = {
    "wine glass": "glass", "cell phone": "phone", 
    "pottedplant": "plant", "tvmonitor": "tv",
    "diningtable": "table", "refrigerator": "fridge"
}

RUSSIAN_NAMES = {
    "person": "человек", "cat": "кот", "dog": "собака",
    "chair": "стул", "sofa": "диван", "plant": "растение", 
    "bed": "кровать", "table": "стол", "toilet": "туалет",
    "tv": "телевизор", "laptop": "ноутбук", "phone": "телефон",
    "fridge": "холодильник", "book": "книга", "cup": "чашка",
    "bottle": "бутылка", "remote": "пульт"
}

def get_home_object_name(coco_class_id: int, coco_name: str) -> str:
    if coco_class_id in HOME_OBJECT_MAPPING:
        name = HOME_OBJECT_MAPPING[coco_class_id]
        return SIMPLIFIED_NAMES.get(name, name)
    return None

def is_important_for_home(coco_class_id: int) -> bool:
    return coco_class_id in HOME_OBJECT_MAPPING
MAPPING_CODE

ok "🧠 AI модели и маппинг загружены"
cd "$PROJECT_DIR"

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
critical_files=("run.py" "robot/api/api.py" "robot/controller.py" "robot/devices/camera.py" "robot/config.py")
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

# --- создание документации по настройкам ---
info "Создание документации по настройкам..."
cat > "$PROJECT_DIR/SETTINGS.md" <<'EOF'
# Настройки Robot Web Interface

Все настройки находятся в файле `robot/config.py`.

## Основные параметры:

### I2C и датчики:
- `ARDUINO_ADDRESS = 0x08` - адрес Arduino
- `SENSOR_FWD_STOP_CM = 15` - порог остановки спереди (см)
- `SENSOR_BWD_STOP_CM = 10` - порог остановки сзади (см)

### Камера:
- `CAMERA_DEVICE_ID = 0` - номер устройства (/dev/video0)
- `CAMERA_WIDTH = 640` - ширина изображения
- `CAMERA_HEIGHT = 480` - высота изображения
- `CAMERA_FPS = 15` - частота кадров

### Повороты камеры:
- `CAMERA_PAN_MIN = 0` - минимальный угол поворота
- `CAMERA_PAN_MAX = 180` - максимальный угол поворота
- `CAMERA_PAN_DEFAULT = 90` - центральная позиция

- `CAMERA_TILT_MIN = 50` - минимальный угол наклона
- `CAMERA_TILT_MAX = 150` - максимальный угол наклона
- `CAMERA_TILT_DEFAULT = 90` - центральная позиция

- `CAMERA_STEP_SIZE = 10` - шаг поворота в градусах

### Логирование:
- `LOG_LEVEL = "INFO"` - уровень логов (DEBUG, INFO, WARNING, ERROR)

## Как изменить настройки:

1. Отредактируйте файл: `nano robot/config.py`
2. Найдите нужный параметр и измените его значение
3. Перезапустите сервис: `./restart.sh`

## Примеры изменений:

```python
# Изменить разрешение камеры на HD
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720

# Ужесточить пороги остановки
SENSOR_FWD_STOP_CM = 20
SENSOR_BWD_STOP_CM = 15

# Ограничить углы поворота камеры
CAMERA_PAN_MIN = 30
CAMERA_PAN_MAX = 150

# Включить отладку
LOG_LEVEL = "DEBUG"
```

После изменений всегда выполняйте: `./restart.sh`
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
if python3 -c "from robot.devices.camera import USBCamera; print('✅ Модуль камеры импортирован успешно')"; then
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

# Основные скрипты управления
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

# Скрипт управления конфигурацией
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
    from robot.devices.camera import list_available_cameras
    
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
echo "🤖 Тест модуля робота:"
cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null || cd "$HOME/robot_web"

if [[ -f "robot/camera.py" ]]; then
    python3 -c "
import sys
sys.path.insert(0, '.')

try:
    from robot.devices.camera import list_available_cameras, USBCamera, OPENCV_AVAILABLE
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
EOF

# Расширенный скрипт диагностики
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
lsusb | grep -i -E "(camera|webcam|uvc)" || echo "USB камеры не найдены"

echo -e "\n⚙️ Конфигурация:"
python3 -c "
import sys
sys.path.insert(0, '$HOME/robot_web')
try:
    from robot.config import *
    print(f'Камера: {CAMERA_WIDTH}x{CAMERA_HEIGHT}@{CAMERA_FPS}fps')
    print(f'Пороги: FWD={SENSOR_FWD_STOP_CM}см, BWD={SENSOR_BWD_STOP_CM}см')
    print(f'Pan: {CAMERA_PAN_MIN}-{CAMERA_PAN_MAX}°, Tilt: {CAMERA_TILT_MIN}-{CAMERA_TILT_MAX}°')
    print(f'Логи: {LOG_LEVEL}')
except Exception as e:
    print(f'Ошибка конфигурации: {e}')
"

echo -e "\n📄 Последние логи:"
sudo journalctl -u "$SERVICE" --no-pager -n 10

IP=$(hostname -I | awk '{print $1}')
echo -e "\n🔗 Адреса:"
echo "Веб-интерфейс: http://$IP:5000"
echo "Видеопоток: http://$IP:5000/camera/stream"
echo "API статус: http://$IP:5000/api/status"

echo -e "\n🧪 Тестирование:"
echo "Настройки: ./config.sh show"
echo "Тест камеры: ./test_camera.sh"
echo "Тест API: python3 test_frame.py"
EOF

# Скрипт обновления
cat > "$PROJECT_DIR/update.sh" <<'EOF'
#!/bin/bash
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
echo -e "${BLUE}🔄 Обновление Robot Web Interface v2.1${NC}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_RAW="https://raw.githubusercontent.com/meshkovQA/Robot/main"

# Список файлов для обновления
declare -A FILES=(
    ["run.py"]="run.py"
    ["robot/__init__.py"]="robot/__init__.py"
    ["robot/api/__init__.py"]="robot/api/__init__.py"
    ["robot/ai_vision/__init__.py"]="robot/ai_vision/__init__.py"
    ["robot/devices/__init__.py"]="robot/devices/__init__.py"
    ["robot/config.py"]="robot/config.py"
    ["robot/i2c_bus.py"]="robot/i2c_bus.py"
    ["robot/controller.py"]="robot/controller.py"
    ["robot/devices/camera.py"]="robot/devices/camera.py"
    ["robot/api/api.py"]="robot/api/api.py"
    ["robot/devices/imu.py"]="robot/devices/imu.py"
    ["robot/heading_controller.py"]="robot/heading_controller.py"
    ["robot/ai_vision/ai_vision.py"]="robot/ai_vision/ai_vision.py"
    ["robot/ai_vision/home_ai_vision.py"]="robot/ai_vision/home_ai_vision.py"
    ["robot/ai_integration.py"]="robot/ai_integration.py"
    ["robot/api/ai_api_extensions.py"]="robot/api/ai_api_extensions.py"
    ["templates/index.html"]="templates/index.html"
    ["static/style.css"]="static/style.css"
    ["static/script.js"]="static/script.js"
    ["static/camera.js"]="static/camera.js"
    ["static/ai-control.js"]="static/ai-control.js"
    ["static/imu-control.js"]="static/imu-control.js"
    ["static/camera-control.js"]="static/camera-control.js"
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

echo -e "${BLUE}🚀 Запуск сервиса...${NC}"
sudo systemctl start robot-web.service

sleep 3

if systemctl is-active --quiet robot-web.service; then
    echo -e "${GREEN}✅ Обновление завершено успешно!${NC}"
    IP=$(hostname -I | awk '{print $1}')
    echo -e "${GREEN}🌐 Интерфейс: http://$IP:5000${NC}"
else
    echo -e "${RED}❌ Сервис не запустился после обновления${NC}"
    echo "Проверьте логи: ./logs.sh"
    exit 1
fi
EOF

# Установка прав на выполнение для всех скриптов
chmod +x "$PROJECT_DIR"/{start.sh,stop.sh,restart.sh,logs.sh,status.sh,update.sh,test_camera.sh,config.sh}
ok "Управляющие скрипты созданы"

# --- тестирование камеры ---
info "Первичное тестирование камеры..."
cd "$PROJECT_DIR"
bash test_camera.sh

# --- проверка установки ---
info "Проверка установки..."

# Проверяем Python модули
cd "$PROJECT_DIR"
if python3 -c "from robot.api.api import create_app; from robot.devices.camera import USBCamera; print('✓ Все модули импортированы успешно')"; then
    ok "Python модули работают корректно"
else
    warn "Есть проблемы с Python модулями, но основная функциональность может работать"
fi


# Проверяем импорт AI модулей
if python3 -c "from robot.devices.camera import USBCamera; from robot.ai_vision.ai_vision import AIVisionProcessor; from robot.ai_vision.home_ai_vision import HomeAIVision; print('✅ AI модули импортированы успешно')"; then
    ok "AI модули работают"
else
    warn "Проблемы с AI модулями - некоторые функции могут быть недоступны"
fi


info "Тестирование запуска приложения..."
cd "$PROJECT_DIR"
if timeout 10 python3 run.py --help >/dev/null 2>&1; then
    ok "run.py доступен"
else
    warn "Проблемы с run.py"
fi

# Тест gunicorn
APP_LIGHT_INIT=1 "$VENV_DIR/bin/gunicorn" --check-config run:app \
  && ok "Gunicorn конфигурация корректна" \
  || warn "Пропускаю строгую проверку Gunicorn (камера отключена для check-config)"

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
    echo "   ./config.sh      - управление настройками"
    echo ""
    echo "🧪 Тестирование:"
    echo "   python3 test_frame.py - тест API камеры"
    echo ""
    echo "⚙️ Конфигурация:"
    echo "   ./config.sh edit - редактировать настройки"
    echo "   ./config.sh show - показать текущие настройки"
    echo "   Файл: $PROJECT_DIR/robot/config.py"
    echo "   Документация: cat SETTINGS.md"
    echo ""
    echo "📂 Файлы проекта: $PROJECT_DIR"
    echo "📸 Фотографии: $PROJECT_DIR/static/photos"
    echo "🎬 Видео: $PROJECT_DIR/static/videos"
    echo ""
    
    # Информация о камере
    if [[ $V4L_DEVICES -gt 0 ]]; then
        echo "📹 Камера:"
        echo "   Найдено устройств: $V4L_DEVICES"
        echo "   Основное устройство: /dev/video0"
        echo "   Управление поворотами: Pan (0-180°), Tilt (50-150°)"
        echo "   API управления: /api/camera/pan, /api/camera/tilt"
        echo "   Тест API: python3 test_frame.py"
    else
        echo "⚠️ Камера:"
        echo "   USB камеры не обнаружены"
        echo "   Подключите USB камеру и перезапустите сервис"
        echo "   Или проверьте права: groups \$USER"
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
    echo "   python3 test_frame.py - тест API камеры"
    echo "   ./logs.sh        - просмотр ошибок"
    echo ""
    echo "📄 Логи ошибок:"
    sudo journalctl -u "$SERVICE_NAME" --no-pager -n 20
    exit 1
fi