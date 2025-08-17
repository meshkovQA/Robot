// Глобальные переменные
let lastUpdateTime = 0;
let obstacleDetected = false;
let connectionActive = false;
let robotMoving = false;
let currentDirection = 0;

// Элементы интерфейса (инициализируются после загрузки DOM)
let speedSlider, speedValue;

// Функции управления движением
function moveForward() {
    console.log('moveForward called');
    const speed = speedSlider ? parseInt(speedSlider.value) : 150;
    sendCommand('/api/move/forward', 'POST', { speed: speed })
        .then(data => {
            console.log('Move forward response:', data);
            if (data.success) {
                showAlert(`Движение вперед (${speed})`, 'success');
                updateMovementState(true, 'Движение вперед');
            }
        });
}

function moveBackward() {
    console.log('moveBackward called');
    const speed = speedSlider ? parseInt(speedSlider.value) : 150;
    sendCommand('/api/move/backward', 'POST', { speed: speed })
        .then(data => {
            if (data.success) {
                showAlert(`Движение назад (${speed})`, 'success');
                updateMovementState(true, 'Движение назад');
            }
        });
}

function tankTurnLeft() {
    console.log('tankTurnLeft called');
    const speed = speedSlider ? parseInt(speedSlider.value) : 150;
    sendCommand('/api/turn/left', 'POST', { speed: speed })
        .then(data => {
            if (data.success) {
                showAlert('Поворот влево', 'success');
                updateMovementState(false, 'Поворот влево');
            }
        });
}

function tankTurnRight() {
    console.log('tankTurnRight called');
    const speed = speedSlider ? parseInt(speedSlider.value) : 150;
    sendCommand('/api/turn/right', 'POST', { speed: speed })
        .then(data => {
            if (data.success) {
                showAlert('Поворот вправо', 'success');
                updateMovementState(false, 'Поворот вправо');
            }
        });
}

function stopRobot() {
    console.log('stopRobot called');
    sendCommand('/api/stop', 'POST')
        .then(data => {
            if (data.success) {
                showAlert('Остановка', 'warning');
                updateMovementState(false, 'Остановлен');
            }
        });
}

function emergencyStop() {
    console.log('emergencyStop called');
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

// Универсальная функция отправки команд
async function sendCommand(url, method, data = null) {
    console.log('Sending command:', url, method, data);
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
        console.log('Command response:', result);

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

// Обновление состояния движения в UI
function updateMovementState(moving, state) {
    robotMoving = moving;
    const statusDisplay = document.getElementById('movement-status-display');
    const robotState = document.getElementById('robot-state');
    const speedInfo = document.getElementById('speed-info');
    const movementDirection = document.getElementById('movement-direction');

    if (robotState) robotState.textContent = state;
    if (movementDirection) movementDirection.textContent = state;

    if (statusDisplay) {
        if (moving) {
            statusDisplay.className = 'movement-status moving';
            if (speedInfo) speedInfo.textContent = 'Используйте ползунок для изменения скорости';
        } else {
            statusDisplay.className = 'movement-status stopped';
            if (speedInfo) speedInfo.textContent = 'Установите скорость и нажмите направление';
        }
    }
}

// Показ уведомлений
function showAlert(message, type = 'success') {
    console.log('Alert:', message, type);
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

// Обновление данных датчиков
function updateSensorData() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const status = data.data;

                // Обновление текущих значений
                const currentSpeedEl = document.getElementById('current-speed');
                if (currentSpeedEl) currentSpeedEl.textContent = status.current_speed;

                // Обновление времени
                const lastUpdateEl = document.getElementById('last-update');
                if (lastUpdateEl) {
                    const now = new Date();
                    lastUpdateEl.textContent = `Обновлено: ${now.toLocaleTimeString()}`;
                }

                lastUpdateTime = Date.now();
                connectionActive = true;
            } else {
                connectionActive = false;
            }
        })
        .catch(error => {
            console.error('Ошибка получения статуса:', error);
            connectionActive = false;
        });
}

// Управление с клавиатуры
document.addEventListener('keydown', function (event) {
    console.log('Key pressed:', event.key);
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

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🤖 DOM загружен, инициализация...');

    // Инициализируем элементы интерфейса
    speedSlider = document.getElementById('speed-slider');
    speedValue = document.getElementById('speed-value');

    if (speedSlider && speedValue) {
        console.log('Slider elements found, adding event listener');
        // Обработчик ползунка скорости
        speedSlider.addEventListener('input', function () {
            const speed = parseInt(this.value);
            speedValue.textContent = speed;
            const currentSpeedEl = document.getElementById('current-speed');
            if (currentSpeedEl) currentSpeedEl.textContent = speed;
            updateSpeed(speed);
        });
    } else {
        console.error('Slider elements not found!');
    }

    // Запуск периодического обновления данных каждые 2 секунды
    setInterval(updateSensorData, 2000);

    // Первоначальное обновление
    updateSensorData();

    showAlert('Управление: W/S - движение, A/D - повороты, Пробел - стоп, Кнопки - мышью', 'success');
    console.log('🤖 Инициализация завершена');
});

// Сделаем функции глобальными для onclick
window.moveForward = moveForward;
window.moveBackward = moveBackward;
window.tankTurnLeft = tankTurnLeft;
window.tankTurnRight = tankTurnRight;
window.stopRobot = stopRobot;
window.emergencyStop = emergencyStop;

console.log('🤖 JavaScript файл загружен');