// ====== ПОТОК КАМЕРЫ / ПЕРЕКЛЮЧЕНИЕ ======
const STREAMS = {
    normal: '/camera/stream',
    ai: '/api/ai/stream?fps=12&scale=0.75&quality=70'
};

let cameraConnected = false;

let currentStream = 'normal';
let isSwitching = false;
let retryTimer = null;
let retries = 0;
const MAX_RETRIES = 3;

// версия (поколение) стрима — чтобы игнорировать события от старых узлов/таймеров
let streamGen = 0;

function updateCameraStatusIndicator(connected) {
    const cameraStatus = document.getElementById('camera-status');
    if (!cameraStatus) return;
    cameraStatus.className = connected ? 'status-indicator active' : 'status-indicator';
}

// Жёстко останавливаем текущее изображение и возвращаем СВЕЖИЙ клон узла
function killStreamImg() {
    const img = document.getElementById('video-stream');
    if (!img) return null;
    try {
        img.onload = null;
        img.onerror = null;
        img.src = '';
        img.removeAttribute('src');
    } catch (_) { }
    const clone = img.cloneNode(false); // без детей/обработчиков
    img.replaceWith(clone);
    return clone;
}

function setStream(kind) {
    let img = document.getElementById('video-stream');
    if (!img) { console.error('video-stream not found'); return; }

    if (isSwitching) return;

    // уже активен тот же — выходим (и отменяем возможный старый ретрай)
    if (currentStream === kind && img.src && img.src.includes(STREAMS[kind])) {
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        return;
    }

    // стопаем старые ретраи
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }

    isSwitching = true;
    currentStream = kind;
    retries = 0;

    // увеличиваем поколение и берём свежий узел
    const myGen = ++streamGen;
    img = killStreamImg(); // теперь img — новый клон

    // навешиваем обработчики, которые игнорят чужие поколения
    img.onload = () => {
        if (myGen !== streamGen) return;
        isSwitching = false;
        cameraConnected = true;
        updateCameraStatusIndicator(true);
        retries = 0;
        // console.log('stream loaded gen', myGen);
    };

    img.onerror = () => {
        if (myGen !== streamGen) return; // событие от старого узла — игнорим
        cameraConnected = false;
        updateCameraStatusIndicator(false);

        if (retries >= MAX_RETRIES) {
            isSwitching = false;
            img.src = '/static/no-camera.svg';
            window.showAlert?.('Камера недоступна. Нажмите "🔄 Обновить"', 'danger');
            return;
        }
        retries++;
        retryTimer = setTimeout(() => {
            // если поколение поменялось — не ретраим
            if (myGen !== streamGen) return;
            retryTimer = null;
            img.src = STREAMS[currentStream] + (STREAMS[currentStream].includes('?') ? '&' : '?') + '_t=' + Date.now();
        }, 1000);
    };

    // ставим src с анти-кэшем
    setTimeout(() => {
        if (myGen !== streamGen) return; // на всякий случай
        const url = STREAMS[kind] + (STREAMS[kind].includes('?') ? '&' : '?') + '_t=' + Date.now();
        img.src = url;
        // console.log('switch to', kind, 'gen', myGen);
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
        window.showAlert?.('🔮 AI аннотации включены', 'info');
    } else {
        setStream('normal');
        if (btn) { btn.textContent = '🔮 AI Аннотации'; btn.className = 'btn btn-sm btn-outline-info'; }
        window.showAlert?.('📹 Обычное видео восстановлено', 'info');
    }
}

function refreshCamera() {
    window.showAlert?.('🔄 Перезапуск камеры...', 'warning');
    fetch('/api/camera/restart', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                window.showAlert?.('✅ Камера перезапущена', 'success');
                setTimeout(() => setStream('normal'), 1500);
            } else {
                window.showAlert?.(`Ошибка перезапуска: ${data.error}`, 'danger');
            }
        })
        .catch(err => {
            console.error('Camera restart error:', err);
            window.showAlert?.('Ошибка перезапуска камеры', 'danger');
        });
}

// Завершение стрима при выгрузке/сворачивании
window.addEventListener('beforeunload', () => { killStreamImg(); });
document.addEventListener('visibilitychange', () => {
    if (document.hidden) killStreamImg();
});

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    initializeVideoStream();
    setTimeout(() => window.showAlert?.('Камера: P - фото, R - запись, F - обновить файлы', 'success'), 5000);
});

// Экспорт
window.cameraStream = {
    setStream, toggleAIStream, refreshCamera,
    isConnected: () => cameraConnected
};