#!/bin/bash

# Скрипт установки веб-интерфейса для робота
# Настроен для репозитория https://github.com/meshkovQA/Robot.git

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка пользователя
if [[ $EUID -eq 0 ]]; then
    print_error "Не запускайте от root. Используйте обычного пользователя."
    exit 1
fi

print_info "🤖 Установка веб-интерфейса управления роботом"
print_info "📁 Репозиторий: https://github.com/meshkovQA/Robot.git"
echo "=============================================="

# Обновление системы
print_info "Обновление системы..."
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
print_info "Установка зависимостей..."
sudo apt install -y \
    python3-pip \
    python3-flask \
    python3-smbus \
    python3-smbus2 \
    i2c-tools \
    git \
    curl

# Python пакеты через apt (рекомендуемый способ)
print_info "Установка Python пакетов через apt..."
sudo apt install -y python3-flask python3-smbus2 || print_warning "Некоторые пакеты недоступны через apt"

# Настройка I2C
print_info "Настройка I2C..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt
    print_success "I2C включен в config.txt"
fi

if ! grep -q "^i2c-dev" /etc/modules; then
    echo "i2c-dev" | sudo tee -a /etc/modules
    print_success "Модуль i2c-dev добавлен"
fi

# Добавление пользователя в группы
sudo usermod -a -G i2c,gpio,spi $USER

# Создание структуры проекта
print_info "Создание структуры проекта..."
PROJECT_DIR="/home/$USER/robot_web"
mkdir -p $PROJECT_DIR/{templates,static,logs}

# Проверка доступности пакетов и создание виртуального окружения при необходимости
print_info "Проверка Python пакетов..."
if ! python3 -c "import smbus2" 2>/dev/null; then
    print_warning "smbus2 недоступен через apt, создаем виртуальное окружение"
    
    cd $PROJECT_DIR
    python3 -m venv venv
    source venv/bin/activate
    pip install smbus2 flask
    
    # Создание wrapper скрипта
    cat > $PROJECT_DIR/run_server.sh << 'EOF'
#!/bin/bash
cd /home/pi/robot_web
source venv/bin/activate
exec python3 robot_server.py
EOF
    chmod +x $PROJECT_DIR/run_server.sh
    EXEC_START="$PROJECT_DIR/run_server.sh"
    print_success "Виртуальное окружение создано"
else
    print_success "Пакеты доступны через системный Python"
    EXEC_START="/usr/bin/python3 $PROJECT_DIR/robot_server.py"
fi

# Скачивание файлов проекта с GitHub
print_info "Скачивание файлов проекта с GitHub..."

# URL вашего репозитория
GITHUB_REPO="https://raw.githubusercontent.com/meshkovQA/Robot/main"

# Функция скачивания
download_file() {
    local file_url="$1"
    local dest_path="$2"
    local file_name="$3"
    
    print_info "Скачивание $file_name..."
    if curl -fsSL "$file_url" -o "$dest_path"; then
        print_success "$file_name скачан"
        return 0
    else
        print_error "Не удалось скачать $file_name"
        print_warning "URL: $file_url"
        return 1
    fi
}

# Скачивание файлов
download_file "$GITHUB_REPO/robot_server.py" "$PROJECT_DIR/robot_server.py" "robot_server.py"
download_file "$GITHUB_REPO/templates/index.html" "$PROJECT_DIR/templates/index.html" "index.html"
download_file "$GITHUB_REPO/static/style.css" "$PROJECT_DIR/static/style.css" "style.css"
download_file "$GITHUB_REPO/static/script.js" "$PROJECT_DIR/static/script.js" "script.js"

# Делаем robot_server.py исполняемым
chmod +x $PROJECT_DIR/robot_server.py

# Создание systemd service
print_info "Создание systemd service..."
sudo tee /etc/systemd/system/robot-web.service > /dev/null << EOF
[Unit]
Description=Robot Web Interface
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$EXEC_START
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

Environment=PYTHONPATH=$PROJECT_DIR
Environment=PYTHONUNBUFFERED=1

SupplementaryGroups=i2c gpio spi

[Install]
WantedBy=multi-user.target
EOF

# Включение автозапуска
sudo systemctl daemon-reload
sudo systemctl enable robot-web.service

# Создание скриптов управления
print_info "Создание скриптов управления..."

cat > $PROJECT_DIR/start.sh << 'EOF'
#!/bin/bash
sudo systemctl start robot-web.service
sudo systemctl status robot-web.service --no-pager
EOF
chmod +x $PROJECT_DIR/start.sh

cat > $PROJECT_DIR/stop.sh << 'EOF'
#!/bin/bash
sudo systemctl stop robot-web.service
EOF
chmod +x $PROJECT_DIR/stop.sh

cat > $PROJECT_DIR/restart.sh << 'EOF'
#!/bin/bash
sudo systemctl restart robot-web.service
sudo systemctl status robot-web.service --no-pager
EOF
chmod +x $PROJECT_DIR/restart.sh

cat > $PROJECT_DIR/logs.sh << 'EOF'
#!/bin/bash
sudo journalctl -u robot-web.service -f
EOF
chmod +x $PROJECT_DIR/logs.sh

cat > $PROJECT_DIR/status.sh << 'EOF'
#!/bin/bash
echo "=== Статус сервиса ==="
sudo systemctl status robot-web.service --no-pager

echo -e "\n=== Сетевые подключения ==="
sudo netstat -tlnp | grep :5000 || echo "Порт 5000 не занят"

echo -e "\n=== I2C устройства ==="
if command -v i2cdetect &> /dev/null; then
    sudo i2cdetect -y 1
else
    echo "i2c-tools не установлены"
fi

echo -e "\n=== IP адреса ==="
hostname -I

echo -e "\n=== Последние логи ==="
sudo journalctl -u robot-web.service --no-pager -n 10
EOF
chmod +x $PROJECT_DIR/status.sh

# Создание скрипта обновления
print_info "Создание скрипта обновления..."

cat > $PROJECT_DIR/update.sh << 'EOF'
#!/bin/bash

# Скрипт обновления файлов с GitHub репозитория
# Для репозитория https://github.com/meshkovQA/Robot.git

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🔄 Обновление файлов с GitHub${NC}"
echo "Репозиторий: https://github.com/meshkovQA/Robot.git"
echo "=============================================="

PROJECT_DIR="/home/pi/robot_web"
GITHUB_REPO="https://raw.githubusercontent.com/meshkovQA/Robot/main"

# Проверка что папка существует
if [[ ! -d "$PROJECT_DIR" ]]; then
    echo -e "${YELLOW}⚠️ Папка $PROJECT_DIR не найдена!${NC}"
    echo "Запустите сначала setup скрипт"
    exit 1
fi

cd $PROJECT_DIR

# Функция скачивания с бэкапом
download_with_backup() {
    local file_url="$1"
    local file_path="$2"
    local file_name="$3"
    
    echo -e "${BLUE}📥 Обновление $file_name...${NC}"
    
    # Создаем бэкап если файл существует
    if [[ -f "$file_path" ]]; then
        backup_name="$file_path.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$file_path" "$backup_name"
        echo "   💾 Создан бэкап: $backup_name"
    fi
    
    # Скачиваем новую версию
    if curl -fsSL "$file_url" -o "$file_path"; then
        echo -e "   ✅ $file_name обновлен"
        return 0
    else
        echo -e "   ${RED}❌ Ошибка скачивания $file_name${NC}"
        # Восстанавливаем из бэкапа если есть
        if [[ -f "$backup_name" ]]; then
            mv "$backup_name" "$file_path"
            echo "   🔄 Восстановлен из бэкапа"
        fi
        return 1
    fi
}

# Остановка сервера
echo -e "${BLUE}⏹️ Остановка сервера...${NC}"
sudo systemctl stop robot-web.service 2>/dev/null || echo "Сервис уже остановлен"

# Скачивание файлов
download_with_backup "$GITHUB_REPO/robot_server.py" "robot_server.py" "robot_server.py"
download_with_backup "$GITHUB_REPO/templates/index.html" "templates/index.html" "index.html"
download_with_backup "$GITHUB_REPO/static/style.css" "static/style.css" "style.css"
download_with_backup "$GITHUB_REPO/static/script.js" "static/script.js" "script.js"

# Права доступа
chmod +x robot_server.py

# Проверка синтаксиса Python
echo -e "${BLUE}🔍 Проверка синтаксиса Python...${NC}"
if python3 -m py_compile robot_server.py 2>/dev/null; then
    echo -e "   ✅ Синтаксис корректен"
else
    echo -e "   ${RED}❌ Ошибка синтаксиса в robot_server.py${NC}"
    echo "Восстанавливаем предыдущую версию..."
    latest_backup=$(ls -t robot_server.py.backup.* 2>/dev/null | head -1)
    if [[ -n "$latest_backup" ]]; then
        mv "$latest_backup" robot_server.py
        echo "Восстановлен из: $latest_backup"
    fi
    exit 1
fi

# Запуск сервера
echo -e "${BLUE}🚀 Запуск сервера...${NC}"
sudo systemctl start robot-web.service

# Ожидание запуска
sleep 3

# Проверка статуса
echo -e "${BLUE}📊 Проверка статуса...${NC}"
if sudo systemctl is-active --quiet robot-web.service; then
    echo -e "✅ Сервер успешно запущен"
    
    # Показать IP для доступа
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    echo -e "\n🌐 Сервер доступен по адресу:"
    echo -e "   http://localhost:5000"
    echo -e "   http://$LOCAL_IP:5000"
    
    # Проверка доступности
    sleep 2
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:5000" | grep -q "200"; then
        echo -e "✅ Веб-интерфейс отвечает"
    else
        echo -e "⚠️ Веб-интерфейс не отвечает, проверьте логи"
    fi
else
    echo -e "❌ Ошибка запуска сервера"
    echo -e "\n📝 Последние логи:"
    sudo journalctl -u robot-web.service --no-pager -n 10
    exit 1
fi

# Показать статус
echo -e "\n📊 Финальный статус:"
sudo systemctl status robot-web.service --no-pager -l | head -15

echo -e "\n${GREEN}🎉 Обновление завершено!${NC}"
echo -e "\n💡 Полезные команды:"
echo -e "   ./logs.sh    - просмотр логов в реальном времени"
echo -e "   ./status.sh  - полная диагностика"
echo -e "   ./restart.sh - перезапуск при проблемах"

# Очистка старых бэкапов (оставляем только последние 5)
echo -e "\n🧹 Очистка старых бэкапов..."
find . -name "*.backup.*" -type f | sort | head -n -5 | xargs rm -f 2>/dev/null || true
EOF
chmod +x $PROJECT_DIR/update.sh

# Проверка скачанных файлов
print_info "Проверка скачанных файлов..."
files_ok=true

for file in "robot_server.py" "templates/index.html" "static/style.css" "static/script.js"; do
    if [[ -f "$PROJECT_DIR/$file" ]] && [[ -s "$PROJECT_DIR/$file" ]]; then
        print_success "✓ $file"
    else
        print_error "✗ $file (отсутствует или пустой)"
        files_ok=false
    fi
done

echo
echo "=============================================="
if [[ "$files_ok" == "true" ]]; then
    print_success "🎉 Установка завершена успешно!"
else
    print_warning "⚠️ Установка завершена с предупреждениями"
fi
echo
print_info "Что было сделано:"
echo "✅ Установлены зависимости"
echo "✅ Настроен I2C"
echo "✅ Создана структура проекта в $PROJECT_DIR"
if [[ "$files_ok" == "true" ]]; then
    echo "✅ Файлы скачаны с GitHub"
else
    echo "⚠️ Некоторые файлы не скачались (проверьте репозиторий)"
fi
echo "✅ Настроен автозапуск systemd service"
echo "✅ Созданы скрипты управления"
echo "✅ Создан скрипт обновления (./update.sh)"
echo
print_info "Следующие шаги:"
echo "1. Убедитесь, что все файлы на месте:"
echo "   ls -la $PROJECT_DIR"
echo "   ls -la $PROJECT_DIR/templates/"
echo "   ls -la $PROJECT_DIR/static/"
echo
if [[ "$files_ok" != "true" ]]; then
    echo "2. Загрузите недостающие файлы в репозиторий:"
    echo "   https://github.com/meshkovQA/Robot.git"
    echo "   Структура должна быть:"
    echo "   Robot/"
    echo "   ├── robot_server.py"
    echo "   ├── templates/index.html"
    echo "   ├── static/style.css"
    echo "   └── static/script.js"
    echo
fi
echo "3. Перезагрузите систему:"
echo "   sudo reboot"
echo  
echo "4. После перезагрузки проверьте статус:"
echo "   cd $PROJECT_DIR && ./status.sh"
echo
echo "5. Откройте в браузере:"
echo "   http://$(hostname -I | awk '{print $1}'):5000"
echo
echo "💡 Для обновления файлов из GitHub в будущем:"
echo "   cd $PROJECT_DIR && ./update.sh"
echo
print_warning "ВАЖНО: Перезагрузите систему для применения настроек I2C!"
print_info "Сервис будет автоматически запускаться при загрузке."