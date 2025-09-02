// ====== ПОТОК КАМЕРЫ / ПЕРЕКЛЮЧЕНИЕ ======
const STREAMS = {
    normal: '/camera/stream',
    ai: '/api/ai/stream?fps=12&scale=0.75&quality=70'
};

// Глобально: доступно другим файлам
let cameraConnected = false;

let currentStream = 'normal';
let isSwitching = false;
let retryTimer = null;
let retries = 0;
const MAX_RETRIES = 3;

function updateCameraStatusIndicator(connected) {
    const cameraStatus = document.getElementById('camera-status');
    if (!cameraStatus) return;
    cameraStatus.className = connected ? 'status-indicator active' : 'status-indicator';
}

function setStream(kind) {
    const img = document.getElementById('video-stream');
    if (!img) { console.error('video-stream not found'); return; }

    if (isSwitching) return;

    // если уже тот же стрим активен — выходим; также убьём зависший ретрай
    if (currentStream === kind && img.src && img.src.includes(STREAMS[kind])) {
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        // console.log('stream already active:', kind);
        return;
    }

    // перед переключением убьём прошлый ретрай (если был)
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }

    isSwitching = true;
    currentStream = kind;
    retries = 0;

    // жестко обнуляем src, убираем слушатели
    img.onload = null;
    img.onerror = null;
    img.src = '';

    img.onload = () => {
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        isSwitching = false;
        cameraConnected = true;
        updateCameraStatusIndicator(true);
        retries = 0;
    };

    img.onerror = () => {
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        cameraConnected = false;
        updateCameraStatusIndicator(false);
        if (retries >= MAX_RETRIES) {
            isSwitching = false;
            if (img) img.src = '/static/no-camera.svg';
            if (typeof showAlert === 'function') showAlert('Камера недоступна. Нажмите "🔄 Обновить"', 'danger');
            return;
        }
        retries++;
        retryTimer = setTimeout(() => {
            retryTimer = null;
            img.src = STREAMS[currentStream] + (STREAMS[currentStream].includes('?') ? '&' : '?') + '_t=' + Date.now();
        }, 1000);
    };

    // ставим новый src с анти-кэшем
    setTimeout(() => {
        const url = STREAMS[kind] + (STREAMS[kind].includes('?') ? '&' : '?') + '_t=' + Date.now();
        img.src = url;
        // console.log('stream switched to', url);
    }, 50);
}

function initializeVideoStream() {
    setStream('normal');
}

function toggleAIStream() {
    const btn = document.getElementById('ai-stream-btn');
    if (currentStream === 'normal') {
        setStream('ai');
        if (btn) { btn.textContent = '📹 Обычное видео'; btn.className = 'btn btn-sm btn-info'; }
        if (typeof showAlert === 'function') showAlert('🔮 AI аннотации включены', 'info');
    } else {
        setStream('normal');
        if (btn) { btn.textContent = '🔮 AI Аннотации'; btn.className = 'btn btn-sm btn-outline-info'; }
        if (typeof showAlert === 'function') showAlert('📹 Обычное видео восстановлено', 'info');
    }
}

function refreshCamera() {
    if (typeof showAlert === 'function') showAlert('🔄 Перезапуск камеры...', 'warning');
    fetch('/api/camera/restart', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                if (typeof showAlert === 'function') showAlert('✅ Камера перезапущена', 'success');
                setTimeout(() => setStream('normal'), 1500);
            } else {
                if (typeof showAlert === 'function') showAlert(`Ошибка перезапуска: ${data.error}`, 'danger');
            }
        })
        .catch(err => {
            console.error('Camera restart error:', err);
            if (typeof showAlert === 'function') showAlert('Ошибка перезапуска камеры', 'danger');
        });
}

// На выгрузке/сворачивании — закрыть длинный запрос
window.addEventListener('beforeunload', () => {
    const img = document.getElementById('video-stream');
    if (img) img.src = '';
});
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        const img = document.getElementById('video-stream');
        if (img) img.src = '';
    }
});

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    initializeVideoStream();
    setTimeout(() => {
        if (typeof showAlert === 'function') showAlert('Камера: P - фото, R - запись, F - обновить файлы', 'success');
    }, 5000);
});

// Экспорт
window.cameraStream = {
    setStream, toggleAIStream, refreshCamera,
    isConnected: () => cameraConnected
};