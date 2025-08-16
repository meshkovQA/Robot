# 🤖 Установка веб-интерфейса для робота

## Быстрая установка

### 1. Подготовка системы
```bash
# Скачайте и запустите скрипт установки
wget -O setup.sh [ссылка на setup.sh]
chmod +x setup.sh
./setup.sh
```

### 2. Копирование файлов проекта

После запуска скрипта установки создайте файлы в папке `/home/pi/robot_web/`:

#### Основной сервер (`robot_server.py`)
```bash
nano /home/pi/robot_web/robot_server.py
# Скопируйте код из артефакта robot_flask_server
```

#### HTML шаблон (`templates/index.html`)
```bash
nano /home/pi/robot_web/templates/index.html  
# Скопируйте код из артефакта html_template
```

#### CSS стили (`static/style.css`)
```bash
nano /home/pi/robot_web/static/style.css
# Скопируйте код из артефакта css_styles
```

#### JavaScript (`static/script.js`)
```bash
nano /home/pi/robot_web/static/script.js
# Скопируйте код из артефакта javascript_code
```

### 3. Перезагрузка и запуск
```bash
# Перезагрузка для применения настроек I2C
sudo reboot

# После перезагрузки проверка статуса
cd /home/pi/robot_web
./status.sh
```

### 4. Доступ к интерфейсу
Откройте браузер и перейдите на:
```
http://[IP-адрес-raspberry-pi]:5000
```

## Структура файлов проекта

```
/home/pi/robot_web/
├── robot_server.py      # Flask веб-сервер
├── templates/
│   └── index.html       # HTML шаблон
├── static/
│   ├── style.css        # CSS стили
│   └── script.js        # JavaScript код
├── logs/                # Папка для логов
├── start.sh            # Запуск сервиса
├── stop.sh             # Остановка сервиса  
├── restart.sh          # Перезапуск сервиса
├── status.sh           # Проверка статуса
├── logs.sh             # Просмотр логов
└── README.md           # Документация
```

## Управление сервисом

### Основные команды
```bash
cd /home/pi/robot_web

# Запуск
./start.sh

# Остановка  
./stop.sh

# Перезапуск
./restart.sh

# Статус
./status.sh

# Просмотр логов в реальном времени
./logs.sh
```

### Systemctl команды
```bash
# Статус сервиса
sudo systemctl status robot-web.service

# Запуск/остановка/перезапуск
sudo systemctl start robot-web.service
sudo systemctl stop robot-web.service  
sudo systemctl restart robot-web.service

# Включение/отключение автозапуска
sudo systemctl enable robot-web.service
sudo systemctl disable robot-web.service

# Просмотр логов
sudo journalctl -u robot-web.service -f
```

## Особенности веб-интерфейса

### Управление с клавиатуры
- **W / ↑** - движение вперед
- **S / ↓** - движение назад
- **A** - танковый поворот влево
- **D** - танковый поворот вправо  
- **← / →** - поворот руля влево/вправо
- **Пробел** - остановка
- **C** - центрирование руля
- **Escape** - экстренная остановка

### Ползунки управления
- **Скорость**: от -255 (назад) до +255 (вперед)
- **Угол руля**: от 10° (влево) до 140° (вправо)

### Мониторинг датчиков
- **Передний датчик**: расстояние в см
- **Задний датчик**: расстояние в см
- **Цветовая индикация**: 
  - Зеленый: безопасно (>20см)
  - Желтый: внимание (10-20см)  
  - Красный: опасно (<10см)

### Системы безопасности
- Автоматическая остановка при обнаружении препятствий
- Экстренная остановка при потере связи
- Предупреждения о закрытии страницы во время движения
- Автостоп при переключении вкладки браузера

## API интерфейс

### Основные эндпоинты
```bash
# Универсальное управление
POST /api/move
{
    "speed": -255...255,
    "steering": 10...140
}

# Специфические команды  
POST /api/command
{
    "command": "move_forward|move_backward|tank_turn_left|tank_turn_right|stop|center_steering",
    "value": 150  # опционально
}

# Экстренная остановка
POST /api/emergency_stop

# Статус системы
GET /api/status
```

### Примеры API запросов
```bash
# Движение вперед со скоростью 200
curl -X POST http://raspberry-pi:5000/api/move \
  -H "Content-Type: application/json" \
  -d '{"speed": 200, "steering": 90}'

# Танковый поворот влево
curl -X POST http://raspberry-pi:5000/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "tank_turn_left", "value": 150}'

# Получение статуса
curl http://raspberry-pi:5000/api/status
```

## Устранение неполадок

### Сервис не запускается
```bash
# Проверка логов
sudo journalctl -u robot-web.service -n 50

# Проверка файлов
ls -la /home/pi/robot_web/

# Тест Python зависимостей
python3 -c "import flask, smbus2"
```

### I2C не работает
```bash
# Проверка настроек
grep i2c /boot/config.txt
lsmod | grep i2c

# Сканирование устройств
sudo i2cdetect -y 1
```

### Arduino не отвечает
```bash
# Проверка подключения
dmesg | grep tty

# Загрузка кода Arduino из вашего файла paste.txt
```

### Веб-интерфейс недоступен
```bash
# Проверка порта
sudo netstat -tlnp | grep :5000

# Проверка процесса
ps aux | grep robot_server

# Проверка IP адреса
hostname -I
```

## Совместимость

### Требования
- **Raspberry Pi 4** (рекомендуется)
- **Arduino Uno** с вашим кодом из paste.txt
- **Python 3.7+**
- **I2C соединение** между RPi и Arduino

### Проверенные браузеры
- Chrome/Chromium
- Firefox  
- Safari (iOS)
- Mobile Chrome (Android)

## Безопасность

### Встроенные механизмы
- Проверка препятствий перед движением
- Автоматическая остановка при потере связи
- Ограничения скорости и углов поворота
- Экстренная остановка в критических ситуациях

### Рекомендации
1. Всегда тестируйте на малых скоростях
2. Убедитесь в работе датчиков
3. Проверьте аварийную остановку
4. Не оставляйте робота без присмотра
5. Используйте брандмауэр для ограничения доступа

## Расширение функционала

### Добавление новых команд
1. Расширьте Arduino код в вашем paste.txt
2. Добавьте новые методы в `RobotController`
3. Обновите API маршруты в `robot_server.py`
4. Добавьте кнопки в `index.html`
5. Обновите JavaScript в `script.js`

### Добавление камеры
```python
# Пример интеграции камеры в robot_server.py
@app.route('/video_feed')
def video_feed():
    # Реализация MJPEG стрима
    pass
```

Удачи с роботом! 🤖