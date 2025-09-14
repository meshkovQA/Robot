// encoder-arm-control.js - Управление энкодерами и роборукой

// ==================== ЭНКОДЕРЫ И СКОРОСТЬ ====================

let currentTargetVelocity = 0.0;
let encoderUpdateInterval = null;

// Обновление данных энкодеров
function updateEncoderData(encoderData) {
    if (!encoderData || !encoderData.encoders) return;

    const encoders = encoderData.encoders;

    // Обновляем скорости колес
    updateElement('left-wheel-speed', encoders.left_wheel_speed?.toFixed(2) || '0.00');
    updateElement('right-wheel-speed', encoders.right_wheel_speed?.toFixed(2) || '0.00');

    // Обновляем общие показатели
    updateElement('linear-velocity', encoders.linear_velocity?.toFixed(2) || '0.00');
    updateElement('angular-velocity', encoders.angular_velocity?.toFixed(2) || '0.00');

    // Цветовая индикация скорости
    updateWheelSpeedColors(encoders.left_wheel_speed, encoders.right_wheel_speed);

    // Обновляем слайдер целевой скорости если он не используется
    const velocitySlider = document.getElementById('velocity-slider');
    if (velocitySlider && !velocitySlider.matches(':focus')) {
        updateElement('target-velocity-value', `${currentTargetVelocity.toFixed(1)} м/с`);
    }
}

// Цветовая индикация скорости колес
function updateWheelSpeedColors(leftSpeed, rightSpeed) {
    const leftElement = document.getElementById('left-wheel-sensor');
    const rightElement = document.getElementById('right-wheel-sensor');
    const linearElement = document.getElementById('linear-velocity-sensor');
    const angularElement = document.getElementById('angular-velocity-sensor');

    if (leftElement) {
        leftElement.className = getSpeedColorClass(leftSpeed, 'left-wheel-sensor');
    }
    if (rightElement) {
        rightElement.className = getSpeedColorClass(rightSpeed, 'right-wheel-sensor');
    }
    if (linearElement) {
        const avgSpeed = (leftSpeed + rightSpeed) / 2;
        linearElement.className = getSpeedColorClass(avgSpeed, 'linear-velocity-sensor');
    }
    if (angularElement) {
        const angularSpeed = Math.abs(rightSpeed - leftSpeed);
        angularElement.className = getSpeedColorClass(angularSpeed, 'angular-velocity-sensor', true);
    }
}

function getSpeedColorClass(speed, baseClass, isAngular = false) {
    const absSpeed = Math.abs(speed);
    let colorClass = 'text-info'; // по умолчанию синий

    if (isAngular) {
        if (absSpeed > 0.2) colorClass = 'text-danger';      // быстрый поворот
        else if (absSpeed > 0.1) colorClass = 'text-warning'; // средний поворот
        else colorClass = 'text-success';                      // прямо
    } else {
        if (absSpeed > 0.2) colorClass = 'text-success';      // быстро
        else if (absSpeed > 0.05) colorClass = 'text-warning'; // средне
        else colorClass = 'text-muted';                        // медленно/стоп
    }

    return `compact-sensor sensor-card border rounded p-1 ${baseClass}`;
}

// Установка целевой скорости
async function setTargetVelocity(velocity) {
    try {
        currentTargetVelocity = parseFloat(velocity);

        const response = await fetch('/api/move/target_velocity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ velocity: currentTargetVelocity })
        });

        const result = await response.json();

        if (result.success) {
            showAlert(`Установлена скорость: ${currentTargetVelocity.toFixed(2)} м/с`, 'success');
            updateElement('target-velocity-value', `${currentTargetVelocity.toFixed(1)} м/с`);

            // Обновляем слайдер
            const slider = document.getElementById('velocity-slider');
            if (slider) {
                slider.value = currentTargetVelocity;
            }
        } else {
            showAlert('Ошибка установки скорости', 'danger');
        }
    } catch (error) {
        console.error('Ошибка установки скорости:', error);
        showAlert('Ошибка связи с роботом', 'danger');
    }
}

// Обработчик слайдера скорости
function initVelocitySlider() {
    const slider = document.getElementById('velocity-slider');
    if (slider) {
        slider.addEventListener('input', (e) => {
            const velocity = parseFloat(e.target.value);
            updateElement('target-velocity-value', `${velocity.toFixed(1)} м/с`);
        });

        slider.addEventListener('change', (e) => {
            const velocity = parseFloat(e.target.value);
            setTargetVelocity(velocity);
        });
    }
}

// ==================== УПРАВЛЕНИЕ РОБОРУКОЙ ====================

let currentArmAngles = [90, 90, 90, 90, 90];
let armUpdateInterval = null;

// Обновление статуса роборуки
function updateArmStatus(armData) {
    if (!armData || !armData.current_angles) return;

    currentArmAngles = armData.current_angles;

    // Обновляем отображение углов
    for (let i = 0; i < 5; i++) {
        const angle = currentArmAngles[i];
        updateElement(`servo-${i}-angle`, `${angle}°`);
        updateElement(`arm-servo-${i}-display`, `${angle}°`);

        // Обновляем слайдеры если они не используются
        const slider = document.getElementById(`servo-${i}-slider`);
        if (slider && !slider.matches(':focus')) {
            slider.value = angle;
        }
    }

    updateElement('arm-last-update', new Date().toLocaleTimeString());
}

// Установка угла одного сервопривода
async function updateServoAngle(servoId, angle) {
    try {
        const response = await fetch('/api/arm/servo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                servo_id: parseInt(servoId),
                angle: parseInt(angle)
            })
        });

        const result = await response.json();

        if (result.success) {
            currentArmAngles[servoId] = result.actual_angle;
            updateElement(`servo-${servoId}-angle`, `${result.actual_angle}°`);
            updateElement(`arm-servo-${servoId}-display`, `${result.actual_angle}°`);
        } else {
            showAlert(`Ошибка управления сервоприводом ${servoId}`, 'warning');
        }
    } catch (error) {
        console.error('Ошибка управления сервоприводом:', error);
        showAlert('Ошибка связи с роботом', 'danger');
    }
}

// Относительное перемещение сервопривода
async function moveServoRelative(servoId, delta) {
    try {
        const response = await fetch('/api/arm/servo/relative', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                servo_id: parseInt(servoId),
                delta: parseInt(delta)
            })
        });

        const result = await response.json();

        if (result.success) {
            updateArmStatus({ current_angles: result.current_angles });
            showAlert(`Сервопривод ${servoId}: ${delta > 0 ? '+' : ''}${delta}°`, 'info', 1000);
        } else {
            showAlert(`Ошибка перемещения сервопривода ${servoId}`, 'warning');
        }
    } catch (error) {
        console.error('Ошибка перемещения сервопривода:', error);
    }
}

// Сброс роборуки в исходное положение
async function resetArm() {
    try {
        const response = await fetch('/api/arm/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (result.success) {
            updateArmStatus({ current_angles: result.current_angles });
            showAlert('Роборука возвращена в исходное положение', 'success');
        } else {
            showAlert('Ошибка сброса роборуки', 'danger');
        }
    } catch (error) {
        console.error('Ошибка сброса роборуки:', error);
        showAlert('Ошибка связи с роботом', 'danger');
    }
}

// Открытие захвата
async function openGripper() {
    try {
        const response = await fetch('/api/arm/gripper/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (result.success) {
            updateArmStatus({ current_angles: result.current_angles });
            showAlert('Захват открыт', 'success', 1000);
        } else {
            showAlert('Ошибка открытия захвата', 'warning');
        }
    } catch (error) {
        console.error('Ошибка открытия захвата:', error);
    }
}

// Закрытие захвата
async function closeGripper() {
    try {
        const response = await fetch('/api/arm/gripper/close', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (result.success) {
            updateArmStatus({ current_angles: result.current_angles });
            showAlert('Захват закрыт', 'warning', 1000);
        } else {
            showAlert('Ошибка закрытия захвата', 'warning');
        }
    } catch (error) {
        console.error('Ошибка закрытия захвата:', error);
    }
}

// Инициализация слайдеров роборуки
function initArmSliders() {
    for (let i = 0; i < 5; i++) {
        const slider = document.getElementById(`servo-${i}-slider`);
        if (slider) {
            slider.addEventListener('input', (e) => {
                const angle = parseInt(e.target.value);
                updateElement(`servo-${i}-angle`, `${angle}°`);
            });

            slider.addEventListener('change', (e) => {
                const angle = parseInt(e.target.value);
                updateServoAngle(i, angle);
            });
        }
    }
}

// ==================== ЗАГРУЗКА ДАННЫХ ====================

// Загрузка данных энкодеров
async function loadEncoderData() {
    try {
        const response = await fetch('/api/encoders/status');
        const result = await response.json();

        if (result.success) {
            updateEncoderData(result.data);
        }
    } catch (error) {
        console.error('Ошибка загрузки данных энкодеров:', error);
    }
}

// Загрузка статуса роборуки
async function loadArmStatus() {
    try {
        const response = await fetch('/api/arm/status');
        const result = await response.json();

        if (result.success) {
            updateArmStatus(result.data);
        }
    } catch (error) {
        console.error('Ошибка загрузки статуса роборуки:', error);
    }
}

// ==================== ИНИЦИАЛИЗАЦИЯ ====================

// Инициализация компонентов при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('Инициализация управления энкодерами и роборукой...');

    // Инициализируем слайдеры
    initVelocitySlider();
    initArmSliders();

    // Загружаем начальные данные
    loadEncoderData();
    loadArmStatus();

    // Запускаем периодическое обновление
    encoderUpdateInterval = setInterval(loadEncoderData, 500);  // 2 Hz
    armUpdateInterval = setInterval(loadArmStatus, 1000);       // 1 Hz
});

// Очистка при выгрузке страницы
window.addEventListener('beforeunload', function () {
    if (encoderUpdateInterval) {
        clearInterval(encoderUpdateInterval);
    }
    if (armUpdateInterval) {
        clearInterval(armUpdateInterval);
    }
});

// ==================== ИНТЕГРАЦИЯ С ОСНОВНЫМ СОСТОЯНИЕМ ====================

// Функция для интеграции с основным EventSource потоком
function handleEncoderArmSSEData(data) {
    // Если в основном SSE потоке есть данные энкодеров, обрабатываем их
    if (data.robot && data.robot.encoders) {
        updateEncoderData({ encoders: data.robot.encoders });
    }

    // Если есть данные роборуки
    if (data.robot && data.robot.arm) {
        updateArmStatus(data.robot.arm);
    }
}

// Экспортируем функцию для использования в основном script.js
if (typeof window !== 'undefined') {
    window.handleEncoderArmData = handleEncoderArmSSEData;
}