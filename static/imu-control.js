// static/imu-control.js - Управление и отображение данных IMU

// ==================== IMU СОСТОЯНИЕ ====================

let imuAvailable = false;
let imuData = {
    available: false,
    ok: false,
    roll: 0,
    pitch: 0,
    yaw: 0,
    gx: 0, gy: 0, gz: 0,
    ax: 0, ay: 0, az: 0,
    timestamp: 0,
    whoami: null
};

// ==================== ПОЛУЧЕНИЕ ДАННЫХ IMU ====================

async function updateIMUData(fullStatus /* optional */) {
    try {
        let status = fullStatus;
        if (!status) {
            const resp = await fetch('/api/status');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            status = await resp.json();
        }
        // Если /api/status возвращает просто объект, используем его напрямую.
        // Если он обернут {"success":true,"data":{...}}, поправим:
        const data = status.data || status;

        const imu = data.imu || null;
        if (imu) {
            imuData = {
                available: typeof imu.available === 'boolean' ? imu.available : true,
                ok: !!imu.ok,
                roll: +imu.roll || 0,
                pitch: +imu.pitch || 0,
                yaw: +imu.yaw || 0,
                gx: +imu.gx || 0, gy: +imu.gy || 0, gz: +imu.gz || 0,
                ax: +imu.ax || 0, ay: +imu.ay || 0, az: +imu.az || 0,
                timestamp: imu.timestamp || imu.last_update || 0,
                whoami: imu.whoami ?? null
            };
            imuAvailable = (imuData.available && imuData.ok);
        } else {
            imuAvailable = false;
        }
        updateIMUDisplay();
    } catch (e) {
        console.debug('IMU (общий статус) недоступен:', e.message);
        imuAvailable = false;
        updateIMUDisplay();
    }
}

// ==================== ОТОБРАЖЕНИЕ ДАННЫХ ====================

function updateIMUDisplay() {
    // Обновление отображения IMU данных в интерфейсе

    // Обновляем индикатор состояния IMU
    updateIMUStatusIndicator();

    // Обновляем углы ориентации
    updateOrientationDisplay();

    // Обновляем гироскоп
    updateGyroscopeDisplay();

    // Обновляем акселерометр
    updateAccelerometerDisplay();

    // Обновляем время последнего обновления
    updateIMUTimestamp();
}

function updateIMUStatusIndicator() {
    // Обновление индикатора состояния IMU
    const statusIndicator = document.getElementById('imu-status-indicator');
    const deviceId = document.getElementById('imu-device-id');

    if (statusIndicator) {
        statusIndicator.classList.toggle('active', imuAvailable);
    }

    if (deviceId) {
        if (imuData.whoami) {
            deviceId.textContent = imuData.whoami;
            deviceId.className = 'badge text-bg-success';
        } else {
            deviceId.textContent = 'N/A';
            deviceId.className = 'badge text-bg-secondary';
        }
    }
}

function updateOrientationDisplay() {
    // Обновление отображения углов ориентации
    // Roll (крен) - поворот вокруг оси X
    const rollValue = document.getElementById('imu-roll');
    const rollBar = document.getElementById('imu-roll-bar');

    if (rollValue && imuAvailable) {
        const roll = imuData.roll || 0;
        rollValue.textContent = formatAngle(roll);

        if (rollBar) {
            const percentage = Math.max(-100, Math.min(100, roll * 100 / 90)); // ±90° = ±100%
            rollBar.style.width = Math.abs(percentage) + '%';
            rollBar.className = `progress-bar ${getAngleBarColor(Math.abs(roll))}`;
        }
    } else if (rollValue) {
        rollValue.textContent = '--°';
        if (rollBar) rollBar.style.width = '0%';
    }

    // Pitch (тангаж) - поворот вокруг оси Y  
    const pitchValue = document.getElementById('imu-pitch');
    const pitchBar = document.getElementById('imu-pitch-bar');

    if (pitchValue && imuAvailable) {
        const pitch = imuData.pitch || 0;
        pitchValue.textContent = formatAngle(pitch);

        if (pitchBar) {
            const percentage = Math.max(-100, Math.min(100, pitch * 100 / 90));
            pitchBar.style.width = Math.abs(percentage) + '%';
            pitchBar.className = `progress-bar ${getAngleBarColor(Math.abs(pitch))}`;
        }
    } else if (pitchValue) {
        pitchValue.textContent = '--°';
        if (pitchBar) pitchBar.style.width = '0%';
    }

    // Yaw (рыскание) - поворот вокруг оси Z (компас)
    const yawValue = document.getElementById('imu-yaw');
    const yawCompass = document.getElementById('imu-yaw-compass');

    if (yawValue && imuAvailable) {
        const yaw = imuData.yaw || 0;
        yawValue.textContent = formatAngle(yaw);

        // Обновляем компас (если есть)
        if (yawCompass) {
            yawCompass.style.transform = `rotate(${yaw}deg)`;
        }

        // Показываем направление
        const direction = getCompassDirection(yaw);
        const yawDirection = document.getElementById('imu-yaw-direction');
        if (yawDirection) {
            yawDirection.textContent = direction;
        }
    } else if (yawValue) {
        yawValue.textContent = '--°';
        if (yawCompass) yawCompass.style.transform = 'rotate(0deg)';
    }
}

function updateGyroscopeDisplay() {
    // Обновление отображения данных гироскопа
    const gxValue = document.getElementById('imu-gx');
    const gyValue = document.getElementById('imu-gy');
    const gzValue = document.getElementById('imu-gz');

    if (imuAvailable) {
        if (gxValue) gxValue.textContent = formatAngularVelocity(imuData.gx || 0);
        if (gyValue) gyValue.textContent = formatAngularVelocity(imuData.gy || 0);
        if (gzValue) gzValue.textContent = formatAngularVelocity(imuData.gz || 0);
    } else {
        if (gxValue) gxValue.textContent = '--';
        if (gyValue) gyValue.textContent = '--';
        if (gzValue) gzValue.textContent = '--';
    }
}

function updateAccelerometerDisplay() {
    // Обновление отображения данных акселерометра
    const axValue = document.getElementById('imu-ax');
    const ayValue = document.getElementById('imu-ay');
    const azValue = document.getElementById('imu-az');

    // Общее ускорение
    const totalAccel = document.getElementById('imu-total-accel');

    if (imuAvailable) {
        const ax = imuData.ax || 0;
        const ay = imuData.ay || 0;
        const az = imuData.az || 0;

        if (axValue) axValue.textContent = formatAcceleration(ax);
        if (ayValue) ayValue.textContent = formatAcceleration(ay);
        if (azValue) azValue.textContent = formatAcceleration(az);

        // Вычисляем общее ускорение
        if (totalAccel) {
            const total = Math.sqrt(ax * ax + ay * ay + az * az);
            totalAccel.textContent = formatAcceleration(total);

            // Цвет в зависимости от ускорения
            if (total > 1.5) {
                totalAccel.className = 'fw-bold text-danger';
            } else if (total > 1.2) {
                totalAccel.className = 'fw-bold text-warning';
            } else {
                totalAccel.className = 'fw-bold text-success';
            }
        }
    } else {
        if (axValue) axValue.textContent = '--';
        if (ayValue) ayValue.textContent = '--';
        if (azValue) azValue.textContent = '--';
        if (totalAccel) {
            totalAccel.textContent = '--';
            totalAccel.className = 'fw-bold text-muted';
        }
    }
}

function updateIMUTimestamp() {
    // Обновление времени последнего обновления IMU
    const timestampEl = document.getElementById('imu-timestamp');

    if (timestampEl && imuAvailable && imuData.timestamp) {
        const now = Date.now() / 1000;
        const age = now - imuData.timestamp;

        if (age < 1) {
            timestampEl.textContent = 'сейчас';
            timestampEl.className = 'small text-success';
        } else if (age < 5) {
            timestampEl.textContent = `${age.toFixed(1)}с назад`;
            timestampEl.className = 'small text-warning';
        } else {
            timestampEl.textContent = `${age.toFixed(0)}с назад`;
            timestampEl.className = 'small text-danger';
        }
    } else if (timestampEl) {
        timestampEl.textContent = 'недоступно';
        timestampEl.className = 'small text-muted';
    }
}

// ==================== ФОРМАТИРОВАНИЕ ДАННЫХ ====================

function formatAngle(angle) {
    // Форматирование угла в читаемый вид
    if (typeof angle !== 'number' || !isFinite(angle)) {
        return '--°';
    }
    return angle.toFixed(1) + '°';
}

function formatAngularVelocity(velocity) {
    // Форматирование угловой скорости
    if (typeof velocity !== 'number' || !isFinite(velocity)) {
        return '--';
    }
    return velocity.toFixed(1) + '°/s';
}

function formatAcceleration(accel) {
    // Форматирование ускорения
    if (typeof accel !== 'number' || !isFinite(accel)) {
        return '--';
    }
    return accel.toFixed(2) + 'g';
}

function getAngleBarColor(absAngle) {
    // Получение цвета прогресс-бара в зависимости от угла
    if (absAngle > 45) {
        return 'bg-danger';      // Красный - критический наклон
    } else if (absAngle > 20) {
        return 'bg-warning';     // Желтый - значительный наклон
    } else if (absAngle > 5) {
        return 'bg-info';        // Синий - небольшой наклон
    } else {
        return 'bg-success';     // Зеленый - ровно
    }
}

function getCompassDirection(yaw) {
    // Получение направления по компасу
    if (typeof yaw !== 'number') return '';

    // Нормализуем угол к 0-360
    let normalizedYaw = ((yaw % 360) + 360) % 360;

    const directions = [
        { angle: 0, name: 'С', desc: 'Север' },
        { angle: 45, name: 'СВ', desc: 'Северо-Восток' },
        { angle: 90, name: 'В', desc: 'Восток' },
        { angle: 135, name: 'ЮВ', desc: 'Юго-Восток' },
        { angle: 180, name: 'Ю', desc: 'Юг' },
        { angle: 225, name: 'ЮЗ', desc: 'Юго-Запад' },
        { angle: 270, name: 'З', desc: 'Запад' },
        { angle: 315, name: 'СЗ', desc: 'Северо-Запад' }
    ];

    // Находим ближайшее направление
    let closestDirection = directions[0];
    let minDiff = Math.abs(normalizedYaw - 0);

    for (let dir of directions) {
        let diff = Math.min(
            Math.abs(normalizedYaw - dir.angle),
            360 - Math.abs(normalizedYaw - dir.angle)
        );

        if (diff < minDiff) {
            minDiff = diff;
            closestDirection = dir;
        }
    }

    return closestDirection.name;
}

// ==================== АНАЛИЗ ДВИЖЕНИЯ ====================

function analyzeRobotMovement() {
    // Анализ движения робота по IMU данным
    if (!imuAvailable) return null;

    const analysis = {
        stability: 'stable',
        movement: 'stationary',
        warnings: []
    };

    const roll = Math.abs(imuData.roll || 0);
    const pitch = Math.abs(imuData.pitch || 0);
    const totalGyro = Math.sqrt(
        (imuData.gx || 0) ** 2 +
        (imuData.gy || 0) ** 2 +
        (imuData.gz || 0) ** 2
    );
    const totalAccel = Math.sqrt(
        (imuData.ax || 0) ** 2 +
        (imuData.ay || 0) ** 2 +
        (imuData.az || 0) ** 2
    );

    // Анализ стабильности
    if (roll > 30 || pitch > 30) {
        analysis.stability = 'critical';
        analysis.warnings.push('Критический наклон робота!');
    } else if (roll > 15 || pitch > 15) {
        analysis.stability = 'unstable';
        analysis.warnings.push('Робот наклонен');
    }

    // Анализ движения
    if (totalGyro > 50) {
        analysis.movement = 'rotating';
    } else if (totalAccel > 1.3) {
        analysis.movement = 'accelerating';
    } else if (totalGyro > 10) {
        analysis.movement = 'moving';
    }

    return analysis;
}

function updateMovementAnalysis() {
    // Обновление анализа движения в интерфейсе
    const analysis = analyzeRobotMovement();
    const analysisEl = document.getElementById('imu-movement-analysis');

    if (!analysisEl) return;

    if (!analysis) {
        analysisEl.innerHTML = '<span class="text-muted">IMU недоступен</span>';
        return;
    }

    let html = '';

    // Индикатор стабильности
    const stabilityColors = {
        'stable': 'success',
        'unstable': 'warning',
        'critical': 'danger'
    };

    const stabilityTexts = {
        'stable': '✅ Стабильно',
        'unstable': '⚠️ Неустойчиво',
        'critical': '🚨 Критично'
    };

    html += `<span class="badge text-bg-${stabilityColors[analysis.stability]} me-2">
        ${stabilityTexts[analysis.stability]}
    </span>`;

    // Индикатор движения
    const movementTexts = {
        'stationary': '⏸️ Стоит',
        'moving': '🚶 Движется',
        'rotating': '🔄 Поворачивается',
        'accelerating': '🚀 Ускоряется'
    };

    html += `<span class="badge text-bg-info">
        ${movementTexts[analysis.movement] || '❓ Неизвестно'}
    </span>`;

    // Предупреждения
    if (analysis.warnings.length > 0) {
        html += '<br><small class="text-warning">';
        html += analysis.warnings.join(', ');
        html += '</small>';
    }

    analysisEl.innerHTML = html;
}

// ==================== ИНТЕГРАЦИЯ ====================

function initializeIMU() {
    // Инициализация IMU модуля
    console.log('🧭 Инициализация IMU управления...');

    // Интегрируемся с основной системой обновления
    const originalUpdateSensorData = window.updateSensorData;
    if (originalUpdateSensorData) {
        window.updateSensorData = function () {
            // Вызываем оригинальную функцию
            originalUpdateSensorData();

            // Добавляем IMU обновления
            updateIMUData();
        };

        console.log('✅ IMU интегрирован с системой обновления датчиков');
    }

    // Первоначальное обновление
    updateIMUData();

    console.log('✅ IMU управление инициализировано');
}

// ==================== ЭКСПОРТ ====================

window.imuControl = {
    updateIMUData,
    analyzeRobotMovement,
    isAvailable: () => imuAvailable,
    getCurrentData: () => ({ ...imuData })
};

// Автоматическая инициализация при загрузке DOM
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeIMU);
} else {
    initializeIMU();
}

// Добавляем обновление анализа движения к основному циклу
setInterval(() => {
    if (imuAvailable) {
        updateMovementAnalysis();
    }
}, 1000);

console.log('🧭 IMU Control модуль загружен');