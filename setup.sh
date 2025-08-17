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

# Ваш репозиторий (raw):
GITHUB_RAW="https://raw.githubusercontent.com/meshkovQA/Robot/main"

# Файлы проекта с новой структурой
declare -A PROJECT_FILES=(
    # Python модули
    ["run.py"]="run.py"
    ["robot/__init__.py"]="robot/__init__.py"
    ["robot/config.py"]="robot/config.py"
    ["robot/i2c_bus.py"]="robot/i2c_bus.py"
    ["robot/controller.py"]="robot/controller.py"
    ["robot/api.py"]="robot/api.py"
    
    # Веб-интерфейс
    ["templates/index.html"]="templates/index.html"
    ["static/style.css"]="static/style.css"
    ["static/script.js"]="static/script.js"
    
    # Документация
    ["README.md"]="README.md"
)

echo "=============================================="
info "🤖 Установка веб-интерфейса управления роботом v2.0"
info "📁 Репозиторий: https://github.com/meshkovQA/Robot"
info "📂 Новая модульная структура проекта"
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
                    net-tools htop

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
sudo usermod -a -G i2c,gpio,spi "$USER_NAME" || true

# --- создание структуры проекта ---
info "Создание структуры проекта в $PROJECT_DIR ..."
mkdir -p "$PROJECT_DIR"/{robot,templates,static,logs}

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

# Дополнительные зависимости для расширения функционала
pip install requests python-dotenv

# --- создание .env файла ---
if [[ ! -f "$ENV_FILE" ]]; then
    info "Создание файла конфигурации .env ..."
    cat > "$ENV_FILE" <<'EOF'
# === Переменные окружения для Robot Web v2.0 ===

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

# Логирование
LOG_LEVEL=INFO

# Flask настройки
FLASK_ENV=production
FLASK_DEBUG=False
EOF
    ok "Создан .env файл с конфигурацией"
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
critical_files=("run.py" "robot/api.py" "robot/controller.py" "robot/config.py")
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

if [[ ${#failed_downloads[@]} -gt 0 ]]; then
    warn "Не удалось скачать некоторые файлы: ${failed_downloads[*]}"
    warn "Проект может работать не полностью"
fi

# --- установка прав доступа ---
info "Настройка прав доступа..."
chmod -R u+rwX "$PROJECT_DIR"
find "$PROJECT_DIR" -type f -name "*.py" -exec chmod +x {} \; 2>/dev/null || true

# --- проверка синтаксиса Python ---
info "Проверка синтаксиса Python файлов..."
cd "$PROJECT_DIR"

if python3 -m py_compile run.py robot/*.py; then
    ok "Синтаксис Python файлов корректен"
else
    err "Ошибки в синтаксисе Python файлов"
    exit 1
fi

# --- создание systemd сервиса ---
info "Создание systemd сервиса..."
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Robot Web Interface v2.0 (Flask + Gunicorn)
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

# Gunicorn с оптимизированными настройками
ExecStart=$VENV_DIR/bin/gunicorn \
    --workers 2 \
    --threads 4 \
    --timeout 30 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
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

# Доступ к I2C/GPIO
SupplementaryGroups=i2c gpio spi

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

# Скрипт запуска
cat > "$PROJECT_DIR/start.sh" <<EOF
#!/bin/bash
echo "🚀 Запуск Robot Web Interface..."
sudo systemctl start $SERVICE_NAME
sleep 2
sudo systemctl status $SERVICE_NAME --no-pager -l
EOF

# Скрипт остановки
cat > "$PROJECT_DIR/stop.sh" <<EOF
#!/bin/bash
echo "⏹️ Остановка Robot Web Interface..."
sudo systemctl stop $SERVICE_NAME
echo "Сервис остановлен"
EOF

# Скрипт перезапуска
cat > "$PROJECT_DIR/restart.sh" <<EOF
#!/bin/bash
echo "🔄 Перезапуск Robot Web Interface..."
sudo systemctl restart $SERVICE_NAME
sleep 3
sudo systemctl status $SERVICE_NAME --no-pager -l
echo ""
IP=\$(hostname -I | awk '{print \$1}')
echo "🌐 Интерфейс доступен: http://\$IP:5000"
EOF

# Скрипт просмотра логов
cat > "$PROJECT_DIR/logs.sh" <<EOF
#!/bin/bash
echo "📄 Логи Robot Web Interface (Ctrl+C для выхода):"
echo "================================================"
sudo journalctl -u $SERVICE_NAME -f --no-pager
EOF

# Расширенный скрипт диагностики
cat > "$PROJECT_DIR/status.sh" <<'EOF'
#!/bin/bash
SERVICE=robot-web.service
echo "🔍 Диагностика Robot Web Interface"
echo "=================================="

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

echo -e "\n💾 Использование ресурсов:"
if pgrep -f "robot.*gunicorn" >/dev/null; then
    ps aux | grep -E "(robot|gunicorn)" | grep -v grep
else
    echo "Процессы Robot Web не найдены"
fi

echo -e "\n📁 Файлы проекта:"
ls -la /home/*/robot_web/ 2>/dev/null | head -10

echo -e "\n📄 Последние логи:"
sudo journalctl -u "$SERVICE" --no-pager -n 10

echo -e "\n🌡️ Системная информация:"
echo "Время работы: $(uptime -p)"
echo "Нагрузка: $(upload | awk -F'load average:' '{print $2}')"
echo "Память: $(free -h | awk '/^Mem:/ {print $3 "/" $2}')"

IP=$(hostname -I | awk '{print $1}')
echo -e "\n🔗 Адрес интерфейса: http://$IP:5000"
EOF

# Скрипт обновления
cat > "$PROJECT_DIR/update.sh" <<'EOF'
#!/bin/bash
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
echo -e "${BLUE}🔄 Обновление Robot Web Interface v2.0${NC}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_RAW="https://raw.githubusercontent.com/meshkovQA/Robot/main"

# Список файлов для обновления
declare -A FILES=(
    ["run.py"]="run.py"
    ["robot/__init__.py"]="robot/__init__.py"
    ["robot/config.py"]="robot/config.py"
    ["robot/i2c_bus.py"]="robot/i2c_bus.py"
    ["robot/controller.py"]="robot/controller.py"
    ["robot/api.py"]="robot/api.py"
    ["templates/index.html"]="templates/index.html"
    ["static/style.css"]="static/style.css"
    ["static/script.js"]="static/script.js"
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
    echo -e "${GREEN}🌐 Интерфейс доступен: http://$IP:5000${NC}"
else
    echo -e "${RED}❌ Сервис не запустился после обновления${NC}"
    echo "Проверьте логи: ./logs.sh"
    exit 1
fi
EOF

# Установка прав на выполнение для всех скриптов
chmod +x "$PROJECT_DIR"/{start.sh,stop.sh,restart.sh,logs.sh,status.sh,update.sh}
ok "Управляющие скрипты созданы"

# --- проверка установки ---
info "Проверка установки..."

# Проверяем Python модули
cd "$PROJECT_DIR"
if python3 -c "from robot.api import create_app; print('✓ Импорт модулей успешен')"; then
    ok "Python модули работают корректно"
else
    err "Ошибка в Python модулях"
    exit 1
fi

# --- первый запуск ---
info "Первый запуск сервиса..."
sudo systemctl start "$SERVICE_NAME"
sleep 3

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
    echo "🎮 Управление сервисом:"
    echo "   ./start.sh    - запуск"
    echo "   ./stop.sh     - остановка"  
    echo "   ./restart.sh  - перезапуск"
    echo "   ./logs.sh     - просмотр логов"
    echo "   ./status.sh   - диагностика"
    echo "   ./update.sh   - обновление"
    echo ""
    echo "📂 Файлы проекта: $PROJECT_DIR"
    echo "⚙️ Конфигурация: $ENV_FILE"
    echo ""
    
    if [[ ${#failed_downloads[@]} -gt 0 ]]; then
        warn "⚠️ Некоторые файлы не загружены: ${failed_downloads[*]}"
        warn "Используйте ./update.sh для повторной загрузки"
    fi
    
    echo "🔧 Для применения прав доступа к I2C выполните:"
    echo "   sudo reboot"
    
else
    err "❌ Сервис не запустился"
    echo ""
    echo "🔍 Диагностика:"
    echo "   ./status.sh   - полная диагностика"
    echo "   ./logs.sh     - просмотр ошибок"
    echo ""
    echo "📄 Логи ошибок:"
    sudo journalctl -u "$SERVICE_NAME" --no-pager -n 20
    exit 1
fi