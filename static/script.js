//script.js

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

    robotState.textContent = state;


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

                // Обновление состояния движения
                const directionText = getDirectionText(status.movement_direction, status.is_moving);
                updateMovementState(status.is_moving, directionText);

                // Обновление датчиков расстояния
                updateSensorDisplay('center-front', status.center_front_distance);
                updateSensorDisplay('left-front', status.left_front_distance);
                updateSensorDisplay('right-front', status.right_front_distance);
                updateSensorDisplay('right-rear', status.right_rear_distance);
                updateSensorDisplay('left-rear', status.left_rear_distance);

                // Обновление температуры и влажности
                updateEnvDisplay(status.temperature, status.humidity);

                // Предупреждения о препятствиях - обновить для всех датчиков
                updateObstacleWarnings(status.obstacles);

                // Обновление времени
                const now = new Date();
                document.getElementById('last-update').textContent = `Обновлено: ${now.toLocaleTimeString()}`;

                // Обновление углов камеры
                if (window.cameraControl) {
                    window.cameraControl.updateAnglesFromStatus(status);
                }

                lastUpdateTime = Date.now();
                obstacleDetected = status.obstacles.front || status.obstacles.rear;

                if (!connectionActive) {
                    showAlert('✅ Соединение восстановлено', 'success');
                }

                connectionActive = true;
            } else {
                updateConnectionStatus(false);
                connectionActive = false;
            }
        })
        .catch(error => {
            console.error('Ошибка получения статуса:', error);
            updateConnectionStatus(false);

            if (connectionActive) {
                showAlert('Потеряно соединение с роботом. Переподключение...', 'danger');
            }

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

    if (!valueElement || !cardElement) return;

    // сброс только "сигнальных" классов
    valueElement.classList.remove('text-danger', 'text-warning');
    cardElement.classList.remove('border-danger', 'border-warning');

    if (distance === 999) {
        valueElement.textContent = 'ERR';
        valueElement.classList.add('text-danger');
        cardElement.classList.add('border-danger');
        return;
    }

    valueElement.textContent = distance;

    if (distance < 10) {
        valueElement.classList.add('text-danger');
        cardElement.classList.add('border-danger');
    } else if (distance < 20) {
        valueElement.classList.add('text-warning');
        cardElement.classList.add('border-warning');
    }
}

function updateEnvDisplay(temp, hum) {
    const tEl = document.getElementById('temperature-value');
    const hEl = document.getElementById('humidity-value');
    const tCard = document.getElementById('temp-sensor');
    const hCard = document.getElementById('hum-sensor');

    if (!tEl || !hEl || !tCard || !hCard) return;

    // сброс только сигнальных классов
    [tEl, hEl].forEach(el => el.classList.remove('text-danger', 'text-warning'));
    [tCard, hCard].forEach(el => el.classList.remove('border-danger', 'border-warning'));

    // Температура
    if (temp == null) {
        tEl.textContent = 'ERR';
        tEl.classList.add('text-danger');
        tCard.classList.add('border-danger');
    } else {
        tEl.textContent = temp.toFixed(1);
        if (temp >= 35) { tEl.classList.add('text-danger'); tCard.classList.add('border-danger'); }
        else if (temp >= 30) { tEl.classList.add('text-warning'); tCard.classList.add('border-warning'); }
    }

    // Влажность
    if (hum == null) {
        hEl.textContent = 'ERR';
        hEl.classList.add('text-danger');
        hCard.classList.add('border-danger');
    } else {
        hEl.textContent = hum.toFixed(1);
        if (hum <= 20) { hEl.classList.add('text-warning'); hCard.classList.add('border-warning'); }
    }
}

// Обновление индикаторов состояния
function updateConnectionStatus(connected) {
    const el = document.getElementById('connection-status');
    if (!el) return;
    el.classList.toggle('active', !!connected);
}

function updateMovementStatusIndicator(moving) {
    const el = document.getElementById('movement-status');
    if (!el) return;
    el.classList.toggle('active', !!moving);
}

function updateObstacleStatus(obstacles) {
    const el = document.getElementById('obstacle-status');
    if (!el) return;
    el.classList.toggle('warning', !!obstacles);
}

// Обновление предупреждений о препятствиях
function updateObstacleWarnings(obstacles) {
    const warningsContainer = document.getElementById('obstacle-warnings');
    warningsContainer.innerHTML = '';

    const warnings = [];

    if (obstacles.center_front) {
        warnings.push('🚫 ПРЕПЯТСТВИЕ ПО ЦЕНТРУ СПЕРЕДИ');
    }
    if (obstacles.left_front) {
        warnings.push('🚫 ПРЕПЯТСТВИЕ СЛЕВА СПЕРЕДИ');
    }
    if (obstacles.right_front) {
        warnings.push('🚫 ПРЕПЯТСТВИЕ СПРАВА СПЕРЕДИ');
    }
    if (obstacles.left_rear) {
        warnings.push('🚫 ПРЕПЯТСТВИЕ СЛЕВА СЗАДИ');
    }
    if (obstacles.right_rear) {
        warnings.push('🚫 ПРЕПЯТСТВИЕ СПРАВА СЗАДИ');
    }

    warnings.forEach(warning => {
        const warningDiv = document.createElement('div');
        warningDiv.className = 'alert alert-danger py-1 mb-1';
        warningDiv.textContent = warning;
        warningsContainer.appendChild(warningDiv);
    });

    if (warnings.length === 0) {
        const clearDiv = document.createElement('div');
        clearDiv.className = 'alert alert-success py-1 mb-0';
        clearDiv.textContent = '✅ Путь свободен';
        warningsContainer.appendChild(clearDiv);
    }
}

// Показ уведомлений
function showAlert(message, type = 'success') {
    const wrap = document.getElementById('alert-container');

    // очищаем все старые алерты
    wrap.innerHTML = '';

    // создаем новый
    const div = document.createElement('div');
    div.className = `alert alert-${type} shadow`;
    div.role = 'alert';
    div.textContent = message;

    wrap.appendChild(div);

    // автоудаление
    setTimeout(() => {
        if (div.parentNode) div.remove();
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

    // Инициализация управления камерой
    if (window.cameraControl) {
        window.cameraControl.init();
        console.log('🎯 Управление камерой инициализировано');
    }

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