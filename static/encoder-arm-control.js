// encoder-arm-control.js — управление энкодерами и роборукой, без дублирования логики UI
// Источник истины по данным — SSE из /api/events (скармливается из script.js через window.handleEncoderArmData).

// ==================== ВСПОМОГАТЕЛЬНОЕ ====================

function updateElement(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

// ==================== ЭНКОДЕРЫ ====================

// Получаем данные об энкодерах и делегируем их отрисовку функции из script.js
function updateEncoderData(payload) {
    if (!payload || !payload.encoders) return;
    if (typeof window.updateEncoderDisplay === 'function') {
        window.updateEncoderDisplay(payload.encoders); // единый рендер в script.js
    }
}

// (опционально) разовая подгрузка начального состояния, если нужно до прихода первого SSE
async function loadEncoderData() {
    try {
        const resp = await fetch('/api/encoders/status');
        const result = await resp.json();
        if (result?.success) {
            updateEncoderData(result.data);
        }
    } catch (e) {
        console.debug('Не удалось загрузить начальные данные энкодеров:', e.message);
    }
}

// ==================== РОБОРУКА ====================

let currentArmAngles = [90, 90, 90, 90, 90];

// Делегируем отрисовку статуса руки функции из script.js (updateArmDisplay)
function updateArmStatus(armData) {
    if (!armData || !Array.isArray(armData.current_angles)) return;

    currentArmAngles = armData.current_angles.slice();

    if (typeof window.updateArmDisplay === 'function') {
        window.updateArmDisplay(armData);
    }

    // Синхронизируем слайдеры, если пользователь их сейчас не двигает
    for (let i = 0; i < 5; i++) {
        const slider = document.getElementById(`servo-${i}-slider`);
        if (slider && !slider.matches(':focus')) {
            slider.value = currentArmAngles[i];
        }
    }
}

async function updateServoAngle(servoId, angle) {
    try {
        const resp = await fetch('/api/arm/servo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ servo_id: Number(servoId), angle: Number(angle) })
        });
        const result = await resp.json();
        if (result?.success) {
            currentArmAngles[servoId] = result.actual_angle;
            updateArmStatus({ current_angles: currentArmAngles });
        } else {
            if (typeof showAlert === 'function') showAlert(`Ошибка сервопривода ${servoId}`, 'warning');
        }
    } catch (e) {
        console.error('Ошибка управления сервоприводом:', e);
        if (typeof showAlert === 'function') showAlert('Ошибка связи с роботом', 'danger');
    }
}

async function moveServoRelative(servoId, delta) {
    try {
        const resp = await fetch('/api/arm/servo/relative', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ servo_id: Number(servoId), delta: Number(delta) })
        });
        const result = await resp.json();
        if (result?.success && Array.isArray(result.current_angles)) {
            updateArmStatus({ current_angles: result.current_angles });
            if (typeof showAlert === 'function') showAlert(`Серво ${servoId}: ${delta > 0 ? '+' : ''}${delta}°`, 'info');
        } else {
            if (typeof showAlert === 'function') showAlert(`Ошибка перемещения сервопривода ${servoId}`, 'warning');
        }
    } catch (e) {
        console.error('Ошибка перемещения сервопривода:', e);
        if (typeof showAlert === 'function') showAlert('Ошибка связи с роботом', 'danger');
    }
}

async function resetArm() {
    try {
        const resp = await fetch('/api/arm/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const result = await resp.json();
        if (result?.success && Array.isArray(result.current_angles)) {
            updateArmStatus({ current_angles: result.current_angles });
            if (typeof showAlert === 'function') showAlert('Роборука в исходном положении', 'success');
        } else {
            if (typeof showAlert === 'function') showAlert('Ошибка сброса роборуки', 'danger');
        }
    } catch (e) {
        console.error('Ошибка сброса роборуки:', e);
        if (typeof showAlert === 'function') showAlert('Ошибка связи с роботом', 'danger');
    }
}

async function openGripper() {
    try {
        const resp = await fetch('/api/arm/gripper/open', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const result = await resp.json();
        if (result?.success && Array.isArray(result.current_angles)) {
            updateArmStatus({ current_angles: result.current_angles });
            if (typeof showAlert === 'function') showAlert('Захват открыт', 'success');
        } else {
            if (typeof showAlert === 'function') showAlert('Ошибка открытия захвата', 'warning');
        }
    } catch (e) {
        console.error('Ошибка открытия захвата:', e);
        if (typeof showAlert === 'function') showAlert('Ошибка связи с роботом', 'danger');
    }
}

async function closeGripper() {
    try {
        const resp = await fetch('/api/arm/gripper/close', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const result = await resp.json();
        if (result?.success && Array.isArray(result.current_angles)) {
            updateArmStatus({ current_angles: result.current_angles });
            if (typeof showAlert === 'function') showAlert('Захват закрыт', 'warning');
        } else {
            if (typeof showAlert === 'function') showAlert('Ошибка закрытия захвата', 'warning');
        }
    } catch (e) {
        console.error('Ошибка закрытия захвата:', e);
        if (typeof showAlert === 'function') showAlert('Ошибка связи с роботом', 'danger');
    }
}

// Инициализация слайдеров роборуки (делает локальный превью и шлет команду по событию change)
function initArmSliders() {
    for (let i = 0; i < 5; i++) {
        const slider = document.getElementById(`servo-${i}-slider`);
        if (!slider) continue;

        slider.addEventListener('input', (e) => {
            const angle = Number(e.target.value);
            updateElement(`servo-${i}-angle`, `${angle}°`);
            updateElement(`arm-servo-${i}-display`, `${angle}°`);
        });

        slider.addEventListener('change', (e) => {
            const angle = Number(e.target.value);
            updateServoAngle(i, angle);
        });
    }
}

// (опционально) разовая подгрузка статуса руки, если нужно до первого SSE
async function loadArmStatus() {
    try {
        const resp = await fetch('/api/arm/status');
        const result = await resp.json();
        if (result?.success && result.data) {
            updateArmStatus(result.data);
        }
    } catch (e) {
        console.debug('Не удалось загрузить начальный статус роборуки:', e.message);
    }
}

// ==================== МОСТ ДЛЯ SSE ИЗ script.js ====================

function handleEncoderArmSSEData(data) {
    // Терпим формат: либо { robot: {...} }, либо сразу {...}
    const robot = data?.robot || data;
    if (!robot) return;

    if (robot.encoders) updateEncoderData({ encoders: robot.encoders });
    if (robot.arm) updateArmStatus(robot.arm);
}

if (typeof window !== 'undefined') {
    window.handleEncoderArmData = handleEncoderArmSSEData;
}

// ==================== ИНИЦИАЛИЗАЦИЯ ====================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🔧 Инициализация модуля encoder-arm-control...');
    initArmSliders();

    // Разовые запросы (fallback до первого SSE). Интервалы не ставим, чтобы не гонять с SSE.
    loadEncoderData();
    loadArmStatus();

    console.log('✅ encoder-arm-control готов (рендер — через функции из script.js, данные — из SSE).');
});