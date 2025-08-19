// ==================== УПРАВЛЕНИЕ ПОВОРОТАМИ КАМЕРЫ ====================

let cameraAngles = {
    pan: 90,    // текущий угол по горизонтали
    tilt: 90    // текущий угол по вертикали
};

let cameraLimits = {
    pan: { min: 0, max: 180, default: 90 },
    tilt: { min: 50, max: 150, default: 90 }
};

const CAMERA_STEP = 10; // шаг поворота

function showNotification(message, type) {
    // Используем существующую функцию showAlert из script.js
    if (typeof showAlert === 'function') {
        showAlert(message, type);
    } else {
        console.log(`[${type}] ${message}`);
    }
}

// ==================== ИНИЦИАЛИЗАЦИЯ ====================

function initCameraControl() {
    console.log('🎯 Инициализация управления камерой');

    // Получаем текущие углы и ограничения
    fetchCameraPosition();
    fetchCameraLimits();

    // Обновляем слайдеры
    updateAngleSliders();
}

// ==================== API ЗАПРОСЫ ====================

async function fetchCameraPosition() {
    try {
        const response = await fetch('/api/camera/position');
        const data = await response.json();

        if (data.success) {
            cameraAngles.pan = data.data.camera.pan_angle;
            cameraAngles.tilt = data.data.camera.tilt_angle;
            updateAngleDisplay();
            updateAngleSliders();
        }
    } catch (error) {
        console.error('Ошибка получения позиции камеры:', error);
    }
}

async function fetchCameraLimits() {
    try {
        const response = await fetch('/api/camera/limits');
        const data = await response.json();

        if (data.success) {
            cameraLimits = data.data.limits;

            // Обновляем ограничения слайдеров
            const panSlider = document.getElementById('pan-slider');
            const tiltSlider = document.getElementById('tilt-slider');

            if (panSlider) {
                panSlider.min = cameraLimits.pan.min;
                panSlider.max = cameraLimits.pan.max;
            }

            if (tiltSlider) {
                tiltSlider.min = cameraLimits.tilt.min;
                tiltSlider.max = cameraLimits.tilt.max;
            }
        }
    } catch (error) {
        console.error('Ошибка получения ограничений камеры:', error);
    }
}

async function sendCameraCommand(endpoint, data = {}) {
    try {
        showNotification('🎯 Поворачиваю камеру...', 'info');

        const response = await fetch(`/api/camera/${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            // Обновляем углы из ответа
            if (result.data.camera) {
                cameraAngles.pan = result.data.camera.pan_angle;
                cameraAngles.tilt = result.data.camera.tilt_angle;
                updateAngleDisplay();
                updateAngleSliders();
            }

            showNotification('✅ Камера повернута', 'success');
            return true;
        } else {
            showNotification(`❌ Ошибка: ${result.error}`, 'error');
            return false;
        }
    } catch (error) {
        console.error('Ошибка команды камеры:', error);
        showNotification('❌ Ошибка соединения', 'error');
        return false;
    }
}

// ==================== КНОПКИ УПРАВЛЕНИЯ ====================

async function cameraPanLeft() {
    await sendCameraCommand('pan/left', { step: CAMERA_STEP });
}

async function cameraPanRight() {
    await sendCameraCommand('pan/right', { step: CAMERA_STEP });
}

async function cameraTiltUp() {
    await sendCameraCommand('tilt/up', { step: CAMERA_STEP });
}

async function cameraTiltDown() {
    await sendCameraCommand('tilt/down', { step: CAMERA_STEP });
}

async function cameraCenter() {
    await sendCameraCommand('center');
}

// ==================== СЛАЙДЕРЫ ====================

async function setCameraPan(angle) {
    const numAngle = parseInt(angle);
    await sendCameraCommand('pan', { angle: numAngle });
}

async function setCameraTilt(angle) {
    const numAngle = parseInt(angle);
    await sendCameraCommand('tilt', { angle: numAngle });
}

// ==================== ОБНОВЛЕНИЕ UI ====================

function updateAngleDisplay() {
    const panElement = document.getElementById('pan-angle');
    const tiltElement = document.getElementById('tilt-angle');

    if (panElement) {
        panElement.textContent = `${cameraAngles.pan}°`;
    }

    if (tiltElement) {
        tiltElement.textContent = `${cameraAngles.tilt}°`;
    }
}

function updateAngleSliders() {
    const panSlider = document.getElementById('pan-slider');
    const tiltSlider = document.getElementById('tilt-slider');

    if (panSlider && panSlider.value != cameraAngles.pan) {
        panSlider.value = cameraAngles.pan;
    }

    if (tiltSlider && tiltSlider.value != cameraAngles.tilt) {
        tiltSlider.value = cameraAngles.tilt;
    }
}

// ==================== АВТООБНОВЛЕНИЕ ====================

function updateCameraAnglesInStatus(statusData) {
    // Вызывается из основного script.js при обновлении статуса
    if (statusData.camera && statusData.camera.pan_angle !== undefined) {
        cameraAngles.pan = statusData.camera.pan_angle;
        cameraAngles.tilt = statusData.camera.tilt_angle;
        updateAngleDisplay();
        updateAngleSliders();
    }
}

// ==================== ЭКСПОРТ ДЛЯ ДРУГИХ МОДУЛЕЙ ====================
window.cameraControl = {
    init: initCameraControl,
    updateAnglesFromStatus: updateCameraAnglesInStatus,
    panLeft: cameraPanLeft,
    panRight: cameraPanRight,
    tiltUp: cameraTiltUp,
    tiltDown: cameraTiltDown,
    center: cameraCenter,
    setPan: setCameraPan,
    setTilt: setCameraTilt
};

console.log('📹 Модуль управления камерой загружен');