// Глобальные переменные
let lastUpdateTime = 0;
let obstacleDetected = false;
let connectionActive = false;

// Элементы интерфейса
const speedSlider = document.getElementById('speed-slider');
const steeringSlider = document.getElementById('steering-slider');
const speedValue = document.getElementById('speed-value');
const steeringValue = document.getElementById('steering-value');

// Обработчики ползунков
speedSlider.addEventListener('input', function () {
    const speed = parseInt(this.value);
    speedValue.textContent = speed;
    sendMovementCommand(speed, parseInt(steeringSlider.value));
});

steeringSlider.addEventListener('input', function () {
    const steering = parseInt(this.value);
    steeringValue.textContent = steering + '°';
    sendMovementCommand(parseInt(speedSlider.value), steering);
});

// Быстрые команды движения
function quickMove(action) {
    switch (action) {
        case 'forward':
            speedSlider.value = 200;
            speedValue.textContent = '200';
            sendSpecificCommand('move_forward', 200);
            break;
        case 'backward':
            speedSlider.value = -150;
            speedValue.textContent = '-150';
            sendSpecificCommand('move_backward', 150);
            break;
        case 'tank_left':
            speedSlider.value = 0;
            speedValue.textContent = '0';
            sendSpecificCommand('tank_turn_left', 150);
            break;
        case 'tank_right':
            speedSlider.value = 0;
            speedValue.textContent = '0';
            sendSpecificCommand('tank_turn_right', 150);
            break;
        case 'stop':
            speedSlider.value = 0;
            speedValue.textContent = '0';
            steeringSlider.value = 90;
            steeringValue.textContent = '90°';
            sendSpecificCommand('stop');
            break;
        case 'center':
            steeringSlider.value = 90;
            steeringValue.textContent = '90°';
            sendSpecificCommand('center_steering');
            break;
    }
}

// Отправка универсальной команды движения
function sendMovementCommand(speed, steering) {
    fetch('/api/move', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            speed: speed,
            steering: steering
        })
    })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                console.error('Ошибка команды движения:', data.error);
                showAlert('Ошибка команды движения', 'danger');
            }
        })
        .catch(error => {
            console.error('Ошибка сети:', error);
            showAlert('Ошибка соединения', 'danger');
        });
}

// Отправка специфических команд
function sendSpecificCommand(command, value = null) {
    const payload = { command: command };
    if (value !== null) {
        payload.value = value;
    }

    fetch('/api/command', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
    })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                console.error('Ошибка команды:', data.error);
                showAlert(`Ошибка команды: ${command}`, 'danger');
            }
        })
        .catch(error => {
            console.error('Ошибка сети:', error);
            showAlert('Ошибка соединения', 'danger');
        });
}

// Экстренная остановка
function emergencyStop() {
    speedSlider.value = 0;
    speedValue.textContent = '0';
    steeringSlider.value = 90;
    steeringValue.textContent = '90°';

    fetch('/api/emergency_stop', {
        method: 'POST'
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('🚨 ЭКСТРЕННАЯ ОСТАНОВКА АКТИВИРОВАНА', 'danger');
            }
        })
        .catch(error => {
            console.error('Ошибка экстренной остановки:', error);
            showAlert('Ошибка экстренной остановки', 'danger');
        });
}

// Обновление данных датчиков
function updateSensorData() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const status = data.data;

                // Обновление индикаторов состояния
                updateConnectionStatus(true);
                updateMovementStatus(status.current_speed !== 0);
                updateObstacleStatus(status.obstacles.front || status.obstacles.rear);

                // Обновление текущих значений
                document.getElementById('current-speed').textContent = status.current_speed;
                document.getElementById('current-steering').textContent = status.current_steering + '°';

                // Обновление датчиков расстояния
                updateSensorDisplay('front', status.front_distance);
                updateSensorDisplay('rear', status.rear_distance);

                // Предупреждения о препятствиях
                updateObstacleWarnings(status.obstacles, status.sensor_error);

                // Обновление времени
                const now = new Date();
                document.getElementById('last-update').textContent =
                    `Обновлено: ${now.toLocaleTimeString()}`;

                lastUpdateTime = Date.now();
                obstacleDetected = status.obstacles.front || status.obstacles.rear;
                connectionActive = true;
            } else {
                updateConnectionStatus(false);
                connectionActive = false;
            }
        })
        .catch(error => {
            console.error('Ошибка получения статуса:', error);
            updateConnectionStatus(false);
            connectionActive = false;
        });
}

// Обновление отображения датчика
function updateSensorDisplay(sensor, distance) {
    const valueElement = document.getElementById(`${sensor}-distance`);
    const cardElement = document.getElementById(`${sensor}-sensor`);

    // Сброс классов
    valueElement.className = 'sensor-value';
    cardElement.className = 'sensor-card';

    if (distance === 999) {
        valueElement.textContent = 'ERR';
        valueElement.classList.add('error');
    } else {
        valueElement.textContent = distance;

        if (distance < 10) {
            valueElement.classList.add('danger');
            cardElement.classList.add('danger');
        } else if (distance < 20) {
            valueElement.classList.add('warning');
            cardElement.classList.add('warning');
        }
    }
}

// Обновление индикаторов состояния
function updateConnectionStatus(connected) {
    const indicator = document.getElementById('connection-status');
    indicator.className = 'status-indicator' + (connected ? ' active' : '');
}

function updateMovementStatus(moving) {
    const indicator = document.getElementById('movement-status');
    indicator.className = 'status-indicator' + (moving ? ' active' : '');
}

function updateObstacleStatus(obstacles) {
    const indicator = document.getElementById('obstacle-status');
    if (obstacles) {
        indicator.className = 'status-indicator warning';
    } else {
        indicator.className = 'status-indicator';
    }
}

// Обновление предупреждений о препятствиях
function updateObstacleWarnings(obstacles, sensorError) {
    const warningsContainer = document.getElementById('obstacle-warnings');
    warningsContainer.innerHTML = '';

    if (sensorError) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'obstacle-warning danger';
        errorDiv.textContent = '⚠️ ОШИБКА ДАТЧИКОВ! Проверьте подключение.';
        warningsContainer.appendChild(errorDiv);
        return;
    }

    if (obstacles.front) {
        const frontWarning = document.createElement('div');
        frontWarning.className = 'obstacle-warning danger';
        frontWarning.textContent = '🚫 ПРЕПЯТСТВИЕ СПЕРЕДИ! Движение вперед заблокировано.';
        warningsContainer.appendChild(frontWarning);
    }

    if (obstacles.rear) {
        const rearWarning = document.createElement('div');
        rearWarning.className = 'obstacle-warning danger';
        rearWarning.textContent = '🚫 ПРЕПЯТСТВИЕ СЗАДИ! Движение назад заблокировано.';
        warningsContainer.appendChild(rearWarning);
    }
}

// Показ уведомлений
function showAlert(message, type = 'success') {
    // Удаляем существующие уведомления
    const existingAlerts = document.querySelectorAll('.alert');
    existingAlerts.forEach(alert => alert.remove());

    // Создаем новое уведомление
    const alert = document.createElement('div');
    alert.className = `alert ${type}`;
    alert.textContent = message;

    document.body.appendChild(alert);

    // Автоматическое удаление через 3 секунды
    setTimeout(() => {
        alert.remove();
    }, 3000);
}

// Управление с клавиатуры
document.addEventListener('keydown', function (event) {
    // Игнорируем если фокус на input элементах
    if (event.target.tagName === 'INPUT') return;

    switch (event.key.toLowerCase()) {
        case 'w':
        case 'arrowup':
            event.preventDefault();
            if (!obstacleDetected) {
                quickMove('forward');
                showAlert('Движение вперед', 'success');
            } else {
                showAlert('Движение заблокировано - препятствие!', 'warning');
            }
            break;
        case 's':
        case 'arrowdown':
            event.preventDefault();
            quickMove('backward');
            showAlert('Движение назад', 'success');
            break;
        case 'a':
            event.preventDefault();
            quickMove('tank_left');
            showAlert('Танковый поворот влево', 'success');
            break;
        case 'd':
            event.preventDefault();
            quickMove('tank_right');
            showAlert('Танковый поворот вправо', 'success');
            break;
        case 'arrowleft':
            event.preventDefault();
            steeringSlider.value = Math.max(10, parseInt(steeringSlider.value) - 5);
            steeringValue.textContent = steeringSlider.value + '°';
            sendMovementCommand(parseInt(speedSlider.value), parseInt(steeringSlider.value));
            break;
        case 'arrowright':
            event.preventDefault();
            steeringSlider.value = Math.min(140, parseInt(steeringSlider.value) + 5);
            steeringValue.textContent = steeringSlider.value + '°';
            sendMovementCommand(parseInt(speedSlider.value), parseInt(steeringSlider.value));
            break;
        case ' ':
            event.preventDefault();
            quickMove('stop');
            showAlert('Остановка', 'warning');
            break;
        case 'c':
            event.preventDefault();
            quickMove('center');
            showAlert('Руль по центру', 'success');
            break;
        case 'escape':
            event.preventDefault();
            emergencyStop();
            break;
    }
});

// Предотвращение случайного закрытия страницы при движении
window.addEventListener('beforeunload', function (event) {
    if (parseInt(speedSlider.value) !== 0) {
        event.preventDefault();
        event.returnValue = 'Робот все еще движется. Вы уверены, что хотите закрыть страницу?';
        return event.returnValue;
    }
});

// Обработка потери фокуса окна (автоматическая остановка при переключении вкладки)
document.addEventListener('visibilitychange', function () {
    if (document.hidden && parseInt(speedSlider.value) !== 0) {
        console.log('Окно потеряло фокус - автоматическая остановка');
        quickMove('stop');
        showAlert('Автоматическая остановка - окно неактивно', 'warning');
    }
});

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🤖 Интерфейс управления роботом загружен');

    // Запуск периодического обновления данных каждые 500мс
    setInterval(updateSensorData, 500);

    // Первоначальное обновление
    updateSensorData();

    // Проверка соединения каждую секунду
    setInterval(() => {
        if (Date.now() - lastUpdateTime > 3000 && connectionActive) {
            updateConnectionStatus(false);
            showAlert('Потеряно соединение с роботом', 'danger');
            connectionActive = false;
        }
    }, 1000);

    // Показ справки по управлению
    showAlert('Управление: W/S - движение, A/D - танк повороты, ←/→ - руль, Пробел - стоп', 'success');

    console.log('Управление с клавиатуры активно');
});