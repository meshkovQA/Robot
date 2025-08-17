// Глобальные переменные
let lastUpdateTime = 0;
let obstacleDetected = false;
let connectionActive = false;
let robotMoving = false;
let currentDirection = 0;

// Элементы интерфейса
const speedSlider = document.getElementById('speed-slider');
const speedValue = document.getElementById('speed-value');

// Обработчик ползунка скорости
speedSlider.addEventListener('input', function () {
    const speed = parseInt(this.value);
    speedValue.textContent = speed;
    document.getElementById('current-speed').textContent = speed;

    // Отправляем новую скорость только если робот движется
    updateSpeed(speed);
});

// Функции управления движением
function moveForward() {
    const speed = parseInt(speedSlider.value);
    sendCommand('/api/move/forward', 'POST', { speed: speed })
        .then(data => {
            if (data.success) {
                showAlert(`Движение вперед (${speed})`, 'success');
                updateMovementState(true, 'Движение вперед');
            }
        });
}

function moveBackward() {
    const speed = parseInt(speedSlider.value);
    sendCommand('/api/move/backward', 'POST', { speed: speed })
        .then(data => {
            if (data.success) {
                showAlert(`Движение назад (${speed})`, 'success');
                updateMovementState(true, 'Движение назад');
            }
        });
}

function tankTurnLeft() {
    const speed = parseInt(speedSlider.value);
    sendCommand('/api/turn/left', 'POST', { speed: speed })
        .then(data => {
            if (data.success) {
                showAlert('Поворот влево', 'success');
                updateMovementState(false, 'Поворот влево');
            }
        });
}

function tankTurnRight() {
    const speed = parseInt(speedSlider.value);
    sendCommand('/api/turn/right', 'POST', { speed: speed })
        .then(data => {
            if (data.success) {
                showAlert('Поворот вправо', 'success');
                updateMovementState(false, 'Поворот вправо');
            }
        });
}

function stopRobot() {
    sendCommand('/api/stop', 'POST')
        .then(data => {
            if (data.success) {
                showAlert('Остановка', 'warning');
                updateMovementState(false, 'Остановлен');
            }
        });
}

function emergencyStop() {
    sendCommand('/api/emergency_stop', 'POST')
        .then(data => {
            if (data.success) {
                showAlert('🚨 ЭКСТРЕННАЯ ОСТАНОВКА', 'danger');
                updateMovementState(false, 'Экстренная остановка');
            }
        });
}

function updateSpeed(newSpeed) {
    sendCommand('/api/speed', 'POST', { speed: newSpeed })
        .then(data => {
            if (data.success && data.is_moving) {
                showAlert(`Скорость изменена: ${newSpeed}`, 'success');
            }
        });
}

// Обновление состояния движения в UI
function updateMovementState(moving, state) {
    robotMoving = moving;
    const statusDisplay = document.getElementById('movement-status-display');
    const robotState = document.getElementById('robot-state');
    const speedInfo = document.getElementById('speed-info');
    const movementDirection = document.getElementById('movement-direction');

    robotState.textContent = state;
    movementDirection.textContent = state;

    if (moving) {
        statusDisplay.className = 'movement-status moving';
        speedInfo.textContent = 'Используйте ползунок для изменения скорости';
    } else {
        statusDisplay.className = 'movement-status stopped';
        speedInfo.textContent = 'Установите скорость и нажмите направление';
    }
}

// Универсальная функция отправки команд
async function sendCommand(url, method, data = null) {
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(url, options);
        const result = await response.json();

        if (!result.success) {
            showAlert(`Ошибка команды: ${result.error}`, 'danger');
        }

        return result;
    } catch (error) {
        console.error('Ошибка сети:', error);
        showAlert('Ошибка соединения', 'danger');
        return { success: false };
    }
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
                updateMovementStatusIndicator(status.is_moving);
                updateObstacleStatus(status.obstacles.front || status.obstacles.rear);

                // Обновление текущих значений
                document.getElementById('current-speed').textContent = status.current_speed;

                // Обновление состояния движения
                const directionText = getDirectionText(status.movement_direction, status.is_moving);
                updateMovementState(status.is_moving, directionText);

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

function getDirectionText(direction, isMoving) {
    if (!isMoving) return 'Остановлен';

    switch (direction) {
        case 1: return 'Движение вперед';
        case 2: return 'Движение назад';
        case 3: return 'Поворот влево';
        case 4: return 'Поворот вправо';
        default: return 'Остановлен';
    }
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

function updateMovementStatusIndicator(moving) {
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
            moveForward();
            break;
        case 's':
        case 'arrowdown':
            event.preventDefault();
            moveBackward();
            break;
        case 'a':
            event.preventDefault();
            tankTurnLeft();
            break;
        case 'd':
            event.preventDefault();
            tankTurnRight();
            break;
        case ' ':
            event.preventDefault();
            stopRobot();
            break;
        case 'escape':
            event.preventDefault();
            emergencyStop();
            break;
    }
});

// Предотвращение случайного закрытия страницы при движении
window.addEventListener('beforeunload', function (event) {
    if (robotMoving) {
        event.preventDefault();
        event.returnValue = 'Робот все еще движется. Вы уверены, что хотите закрыть страницу?';
        return event.returnValue;
    }
});

// Обработка потери фокуса окна
document.addEventListener('visibilitychange', function () {
    if (document.hidden && robotMoving) {
        console.log('Окно потеряло фокус - автоматическая остановка');
        stopRobot();
    }
});

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🤖 Интерфейс управления роботом загружен');

    // Запуск периодического обновления данных каждые 500мс
    setInterval(updateSensorData, 500);

    // Первоначальное обновление
    updateSensorData();

    // Проверка соединения
    setInterval(() => {
        if (Date.now() - lastUpdateTime > 3000 && connectionActive) {
            updateConnectionStatus(false);
            showAlert('Потеряно соединение с роботом', 'danger');
            connectionActive = false;
        }
    }, 1000);

    showAlert('Управление: W/S - движение, A/D - повороты, Пробел - стоп', 'success');
});