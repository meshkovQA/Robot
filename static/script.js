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

const SPEED_CONVERSION = {
    // Примерные значения - ТРЕБУЮТ КАЛИБРОВКИ
    MIN_MPS: 0.05,      // минимальная скорость м/с
    MAX_MPS: 0.5,       // максимальная скорость м/с
    MIN_PWM: 50,        // минимальный PWM
    MAX_PWM: 255        // максимальный PWM
};

// Преобразование м/с в PWM
function mpsToEwm(mps) {
    const ratio = (mps - SPEED_CONVERSION.MIN_MPS) / (SPEED_CONVERSION.MAX_MPS - SPEED_CONVERSION.MIN_MPS);
    const pwm = SPEED_CONVERSION.MIN_PWM + ratio * (SPEED_CONVERSION.MAX_PWM - SPEED_CONVERSION.MIN_PWM);
    return Math.round(Math.max(SPEED_CONVERSION.MIN_PWM, Math.min(SPEED_CONVERSION.MAX_PWM, pwm)));
}

// Преобразование PWM в м/с
function pwmToMps(pwm) {
    const ratio = (pwm - SPEED_CONVERSION.MIN_PWM) / (SPEED_CONVERSION.MAX_PWM - SPEED_CONVERSION.MIN_PWM);
    const mps = SPEED_CONVERSION.MIN_MPS + ratio * (SPEED_CONVERSION.MAX_MPS - SPEED_CONVERSION.MIN_MPS);
    return Math.max(SPEED_CONVERSION.MIN_MPS, Math.min(SPEED_CONVERSION.MAX_MPS, mps));
}

// Обработчик ползунка скорости
speedSlider.addEventListener('input', function () {
    const mpsValue = parseFloat(this.value);
    speedValue.textContent = mpsValue.toFixed(2) + ' м/с';

    // Преобразуем в PWM для отправки команд
    const pwmValue = mpsToEwm(mpsValue);
    console.log(`Speed: ${mpsValue.toFixed(2)} м/с → PWM: ${pwmValue}`);
});

// Функции управления движением
function moveForward() {
    const mpsSpeed = parseFloat(speedSlider.value);
    const pwmSpeed = mpsToEwm(mpsSpeed);

    sendCommand('/api/move/forward', 'POST', { speed: pwmSpeed })
        .then(data => {
            if (data.success) {
                showAlert(`Движение вперед (${mpsSpeed.toFixed(2)} м/с)`, 'success');
                updateMovementState(true, 'Движение вперед');
            }
        });
}

function moveBackward() {
    const mpsSpeed = parseFloat(speedSlider.value);
    const pwmSpeed = mpsToEwm(mpsSpeed);

    sendCommand('/api/move/backward', 'POST', { speed: pwmSpeed })
        .then(data => {
            if (data.success) {
                showAlert(`Движение назад (${mpsSpeed.toFixed(2)} м/с)`, 'success');
                updateMovementState(true, 'Движение назад');
            }
        });
}

function tankTurnLeft() {
    const mpsSpeed = parseFloat(speedSlider.value);
    const pwmSpeed = mpsToEwm(mpsSpeed);

    sendCommand('/api/turn/left', 'POST', { speed: pwmSpeed })
        .then(data => {
            if (data.success) {
                showAlert(`Поворот влево (${mpsSpeed.toFixed(2)} м/с)`, 'success');
                updateMovementState(false, 'Поворот влево');
            }
        });
}

function tankTurnRight() {
    const mpsSpeed = parseFloat(speedSlider.value);
    const pwmSpeed = mpsToEwm(mpsSpeed);

    sendCommand('/api/turn/right', 'POST', { speed: pwmSpeed })
        .then(data => {
            if (data.success) {
                showAlert(`Поворот вправо (${mpsSpeed.toFixed(2)} м/с)`, 'success');
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

function updateSpeed(newMpsSpeed) {
    const pwmSpeed = mpsToEwm(newMpsSpeed);
    sendCommand('/api/speed', 'POST', { speed: pwmSpeed })
        .then(data => {
            if (data.success && data.is_moving) {
                showAlert(`Скорость изменена: ${newMpsSpeed.toFixed(2)} м/с`, 'success');
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
    // ожидали boolean — теперь подаём boolean (anyObstacle)
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

    const photoModal = document.getElementById('photo-modal');
    if (photoModal && photoModal.style.display === 'block') return;

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


// === НОВЫЕ ФУНКЦИИ ДЛЯ ЭНКОДЕРОВ И РОБОРУКИ ===

// Обновление отображения энкодеров
function updateEncoderDisplay(encoders) {
    if (!encoders) return;

    // Скорости колес
    updateElement('left-wheel-speed', (encoders.left_wheel_speed || 0).toFixed(3));
    updateElement('right-wheel-speed', (encoders.right_wheel_speed || 0).toFixed(3));

    // Общие показатели скорости
    updateElement('linear-velocity', (encoders.average_speed || 0).toFixed(3));

    // Рассчитываем угловую скорость (приблизительно)
    const wheelbase = 0.2; // метры, расстояние между колесами
    const angularVel = ((encoders.right_wheel_speed || 0) - (encoders.left_wheel_speed || 0)) / wheelbase;
    updateElement('angular-velocity', angularVel.toFixed(3));

    // Цветовые индикации
    updateEncoderColors(encoders);
}

// Обновление отображения роборуки  
function updateArmDisplay(arm) {
    if (!arm || !arm.current_angles) return;

    // Обновляем углы сервоприводов
    for (let i = 0; i < 5; i++) {
        if (arm.current_angles[i] !== undefined) {
            updateElement(`servo-${i}-angle`, `${arm.current_angles[i]}°`);
            updateElement(`arm-servo-${i}-display`, `${arm.current_angles[i]}°`);

            // Обновляем слайдеры если они не используются
            const slider = document.getElementById(`servo-${i}-slider`);
            if (slider && !slider.matches(':focus')) {
                slider.value = arm.current_angles[i];
            }
        }
    }

    // Индикатор статуса роборуки
    const statusIndicator = document.getElementById('arm-status-indicator');
    if (statusIndicator) {
        statusIndicator.className = arm.available ? 'status-indicator status-active' : 'status-indicator status-inactive';
    }

    updateElement('arm-last-update', new Date().toLocaleTimeString());
}

// Цветовые индикации энкодеров
function updateEncoderColors(encoders) {
    const leftSpeed = Math.abs(encoders.left_wheel_speed || 0);
    const rightSpeed = Math.abs(encoders.right_wheel_speed || 0);

    // Обновляем цвета в зависимости от скорости
    updateElementColor('left-wheel-sensor', getSpeedColor(leftSpeed));
    updateElementColor('right-wheel-sensor', getSpeedColor(rightSpeed));
    updateElementColor('linear-velocity-sensor', getSpeedColor(Math.abs(encoders.average_speed || 0)));

    // Угловая скорость (разность скоростей колес)
    const speedDiff = Math.abs(encoders.speed_difference || 0);
    updateElementColor('angular-velocity-sensor', getTurnColor(speedDiff));
}

// Цвет в зависимости от скорости
function getSpeedColor(speed) {
    if (speed > 0.15) return 'text-success';      // быстро (зеленый)
    if (speed > 0.05) return 'text-warning';     // средне (желтый)  
    if (speed > 0.01) return 'text-info';        // медленно (синий)
    return 'text-muted';                         // остановлен (серый)
}

// Цвет для поворота
function getTurnColor(speedDiff) {
    if (speedDiff > 0.1) return 'text-danger';   // сильный поворот (красный)
    if (speedDiff > 0.05) return 'text-warning'; // средний поворот (желтый)
    return 'text-success';                       // прямо (зеленый)
}

// Обновление цвета элемента
function updateElementColor(elementId, colorClass) {
    const element = document.getElementById(elementId);
    if (element) {
        // Сохраняем базовые классы, меняем только цвет текста
        const baseClasses = element.className.replace(/text-\w+/g, '').trim();
        element.className = `${baseClasses} ${colorClass}`.trim();
    }
}

// Вспомогательная функция для обновления элементов
function updateElement(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = value;
    }
}

// Обновление датчиков с новой структурой
function updateSensorDisplayNew(sensors) {
    if (!sensors) return;

    // Обновляем все 5 датчиков
    updateSensorDisplay('left-front', sensors.left_front);
    updateSensorDisplay('right-front', sensors.right_front);
    updateSensorDisplay('left-rear', sensors.left_rear);
    updateSensorDisplay('center-front', sensors.front_center);  // новое название
    updateSensorDisplay('right-rear', sensors.rear_right);     // новое название

    // Обновляем цвета индикаторов
    updateSensorColorsNew(sensors);
}

// Обновленная функция цветов датчиков (для новой структуры)
function updateSensorColorsNew(sensors) {
    const sensorElements = [
        { id: 'left-front-sensor', value: sensors.left_front, threshold: 20 },
        { id: 'right-front-sensor', value: sensors.right_front, threshold: 20 },
        { id: 'left-rear-sensor', value: sensors.left_rear, threshold: 25 },
        { id: 'center-front-sensor', value: sensors.front_center, threshold: 15 },
        { id: 'right-rear-sensor', value: sensors.rear_right, threshold: 25 }
    ];

    sensorElements.forEach(({ id, value, threshold }) => {
        const element = document.getElementById(id);
        if (element && value !== undefined) {
            let colorClass;
            if (value === 999) {
                colorClass = 'text-muted';      // ошибка датчика
            } else if (value < threshold) {
                colorClass = 'text-danger';     // препятствие близко
            } else if (value < threshold * 2) {
                colorClass = 'text-warning';    // предупреждение
            } else {
                colorClass = 'text-success';    // свободно
            }

            // Обновляем только цвет значения
            const valueElement = element.querySelector('.fw-bold') || element.querySelector('#' + id.replace('-sensor', '-distance'));
            if (valueElement) {
                valueElement.className = valueElement.className.replace(/text-\w+/g, '').trim() + ` ${colorClass}`;
            }
        }
    });
}


// Новый обработчик одного «среза» статуса
function applyRobotStatus(status) {
    if (!status) return;

    updateConnectionStatus(true);
    updateMovementStatusIndicator(status.is_moving || (status.motion && status.motion.is_moving));

    // === ОБРАБОТКА НОВОЙ СТРУКТУРЫ ДАННЫХ ===

    // Движение (новая структура)
    const motion = status.motion || status;
    const isMoving = motion.is_moving || status.is_moving;
    const direction = motion.direction || status.movement_direction;

    const directionText = getDirectionText(direction, isMoving);
    updateMovementState(isMoving, directionText);

    // === ДАТЧИКИ РАССТОЯНИЯ (новая структура) ===
    if (status.distance_sensors) {
        updateSensorDisplayNew(status.distance_sensors);
    } else {
        // Обратная совместимость со старой структурой
        updateSensorDisplay('center-front', status.center_front_distance);
        updateSensorDisplay('left-front', status.left_front_distance);
        updateSensorDisplay('right-front', status.right_front_distance);
        updateSensorDisplay('right-rear', status.right_rear_distance);
        updateSensorDisplay('left-rear', status.left_rear_distance);
    }

    // === КЛИМАТИЧЕСКИЕ ДАННЫЕ ===
    if (status.environment) {
        updateEnvDisplay(status.environment.temperature, status.environment.humidity);
    } else {
        // Обратная совместимость
        updateEnvDisplay(status.temperature, status.humidity);
    }

    // === НОВЫЕ ДАННЫЕ: ЭНКОДЕРЫ ===
    if (status.encoders) {
        updateEncoderDisplay(status.encoders);
    }

    // === НОВЫЕ ДАННЫЕ: РОБОРУКА ===
    if (status.arm) {
        updateArmDisplay(status.arm);
    }

    // === ПРЕПЯТСТВИЯ ===
    const obstacles = status.obstacles || {};
    updateObstacleWarnings(obstacles);
    const anyObstacle = Object.values(obstacles).some(Boolean);
    updateObstacleStatus(anyObstacle);

    // === ОСТАЛЬНОЕ (без изменений) ===

    // IMU (защита от отсутствия модуля)
    if (window.imuControl && typeof window.imuControl.updateIMUData === 'function') {
        window.imuControl.updateIMUData(status);
    }

    // время обновления
    const el = document.getElementById('last-update');
    if (el) el.textContent = new Date().toLocaleTimeString();

    // углы камеры
    if (window.cameraControl && typeof window.cameraControl.updateAnglesFromStatus === 'function') {
        window.cameraControl.updateAnglesFromStatus(status);
    }

    // Интеграция с новыми компонентами энкодеров/роборуки
    if (typeof window.handleEncoderArmData === 'function') {
        window.handleEncoderArmData({ robot: status });
    }

    lastUpdateTime = Date.now();
    connectionActive = true;
}

// Подписка на SSE (можно оставить в ai-detector.js, но логичнее держать в одном месте)
function startTelemetrySSE_All() {
    const es = new EventSource('/api/events');
    es.onmessage = (ev) => {
        const msg = JSON.parse(ev.data || '{}');
        if (msg.robot) applyRobotStatus(msg.robot);
        if (msg.camera) updateCameraStatus(msg.camera);
        if (msg.ai) {
            const aiFpsEl = document.getElementById('ai-processing-fps');
            if (aiFpsEl && typeof msg.ai.fps === 'number') {
                aiFpsEl.textContent = `AI: ${msg.ai.fps.toFixed(1)} FPS`;
            }

            const total = document.getElementById('ai-objects-count');
            if (total && typeof msg.ai.count === 'number') {
                total.textContent = msg.ai.count;
            }

            setAIDetectorStatus((msg.ai.count ?? 0) > 0);
            if (msg.ai.last_ts) setAiLastUpdate(msg.ai.last_ts * 1000);

            // 💡 новые строки — обновляем UI из SSE
            if (Array.isArray(msg.ai.detections)) {
                updateDetectionDisplay(msg.ai.detections);
                updateDetectionStats(msg.ai.detections);
                updateSimpleDetection(msg.ai.detections);
            }
        }
    };
    es.onerror = () => {
        updateConnectionStatus(false);
        // можно показать предупреждение; браузер будет пытаться переподключиться
    };
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🤖 UI загружен');

    // Переходим на SSE, без частого fetch('/api/status')
    startTelemetrySSE_All();

    if (typeof initVelocitySlider === 'function') {
        initVelocitySlider();
    }
    if (typeof initArmSliders === 'function') {
        initArmSliders();
    }

    console.log('✅ Система управления энкодерами и роборукой инициализирована');

    showAlert('Управление: W/S – вперёд/назад, A/D – повороты, Пробел – стоп', 'success');
});