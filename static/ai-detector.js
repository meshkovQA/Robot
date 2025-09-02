// static/ai-detector.js - Простая AI детекция объектов

let lastDetectionUpdate = 0;
let lastAiTick = 0;

function setAIDetectorStatus(on) {
    const dot = document.getElementById('ai-detector-status');
    if (dot) dot.classList.toggle('active', !!on);
}

function setAiLastUpdate(ts = Date.now()) {
    const fmt = new Date(ts).toLocaleTimeString();
    const el1 = document.getElementById('ai-last-update');
    if (el1) el1.innerText = fmt;          // НЕЛЬЗЯ через ?.
    const el2 = document.getElementById('last-update');
    if (el2) el2.innerText = fmt;          // НЕЛЬЗЯ через ?.
}

function setAiFpsFromTick(now) {
    if (!lastAiTick) { lastAiTick = now; return; }
    const dt = (now - lastAiTick) / 1000;
    lastAiTick = now;
    const fps = dt > 0 ? (1 / dt) : 0;
    const el = document.getElementById('ai-processing-fps');
    if (el) el.textContent = `AI: ${fps.toFixed(1)} FPS`;
}

// --- ОСНОВНЫЕ ФУНКЦИИ ---

async function refreshAIDetection() {
    try {
        const resp = await fetch('/api/ai/detect');
        const json = await resp.json();
        if (!json.success) throw new Error(json.error || 'AI detect failed');

        const detections = json.detections || [];

        updateDetectionDisplay(detections);
        updateDetectionStats(detections);
        updateSimpleDetection(detections);

        const total = document.getElementById('ai-objects-count');
        if (total) total.textContent = detections.length;

        setAIDetectorStatus(true);
        setAiLastUpdate(json.timestamp ? json.timestamp * 1000 : Date.now());
        setAiFpsFromTick(Date.now());

        // чтобы таймер не дёргал часто
        lastDetectionUpdate = Date.now();

    } catch (e) {
        console.error('AI detection error:', e);
        setAIDetectorStatus(false);
        const el = document.getElementById('ai-processing-fps'); // НЕЛЬЗЯ через ?.
        if (el) el.textContent = 'AI: -- FPS';
    }
}
function updateSimpleDetection(detections) {
    // НОВАЯ простая функция обновления
    const objectsContainer = document.getElementById('detected-objects-list');
    if (!objectsContainer) return;

    if (!detections || detections.length === 0) {
        objectsContainer.innerHTML = '<span class="badge text-bg-secondary">Объекты не обнаружены</span>';
        return;
    }

    // Группируем объекты по классам
    const grouped = {};
    detections.forEach(det => {
        const className = det.class_name;
        if (!grouped[className]) grouped[className] = 0;
        grouped[className]++;
    });

    // Создаем бейджи
    const badges = Object.entries(grouped).map(([className, count]) => {
        const displayCount = count > 1 ? ` (${count})` : '';
        return `<span class="badge text-bg-primary">${className}${displayCount}</span>`;
    }).join(' ');

    objectsContainer.innerHTML = badges;

    // Обновляем общий счетчик
    const totalCount = document.getElementById('ai-objects-count');
    if (totalCount) totalCount.textContent = detections.length;
}

async function getAIFrame() {
    // Получение кадра с аннотациями
    try {
        showAlert('🖼️ Получение AI кадра...', 'info');

        const response = await fetch('/api/ai/annotated_frame');
        const data = await response.json();

        if (data.success && data.frame) {
            showAIFrameModal(data.frame, data.detections);
            showAlert('🖼️ AI кадр получен', 'success');
        } else {
            showAlert(`❌ Ошибка получения кадра: ${data.error || 'Нет данных'}`, 'danger');
        }
    } catch (error) {
        console.error('Get AI frame error:', error);
        showAlert('❌ Ошибка получения AI кадра', 'danger');
    }
}

function toggleAIStream() {
    const normalStream = document.getElementById('camera-stream');
    const aiStream = document.getElementById('ai-stream');
    const btn = document.getElementById('ai-stream-btn');

    if (!aiStream) return showAlert('❌ AI видеопоток недоступен', 'danger');

    const aiOn = normalStream.style.display !== 'none';
    if (aiOn) {
        normalStream.style.display = 'none';
        aiStream.style.display = 'block';
        // перезапуск с кэш-бастингом
        aiStream.src = `/api/ai/stream?_t=${Date.now()}`;
        btn.textContent = '📹 Обычное видео';
        btn.className = 'btn btn-sm btn-info';
        showAlert('🔮 AI аннотации включены', 'info');
    } else {
        normalStream.style.display = 'block';
        aiStream.style.display = 'none';
        btn.textContent = '🔮 AI Аннотации';
        btn.className = 'btn btn-sm btn-outline-info';
        showAlert('📹 Обычное видео восстановлено', 'info');
    }
}

// ==================== ОБНОВЛЕНИЕ ИНТЕРФЕЙСА ====================

function updateDetectionDisplay(detections) {
    // Обновление списка обнаруженных объектов
    const container = document.getElementById('detected-objects-list');
    if (!container) return;

    if (!detections || detections.length === 0) {
        container.innerHTML = '<span class="badge text-bg-secondary">Объекты не обнаружены</span>';
        return;
    }

    // Группируем объекты по классам
    const grouped = {};
    detections.forEach(det => {
        const className = det.class_name;
        if (!grouped[className]) {
            grouped[className] = { count: 0, maxConfidence: 0 };
        }
        grouped[className].count++;
        grouped[className].maxConfidence = Math.max(
            grouped[className].maxConfidence,
            det.confidence
        );
    });

    // Создаем бейджи
    const badges = Object.entries(grouped).map(([className, info]) => {
        const count = info.count > 1 ? ` (${info.count})` : '';
        const confidence = (info.maxConfidence * 100).toFixed(0);
        return `<span class="badge text-bg-primary" title="Уверенность: ${confidence}%">
            ${className}${count}
        </span>`;
    }).join(' ');

    container.innerHTML = badges;
}

function updateDetectionStats(detections) {
    // Обновление статистики по категориям
    const categories = {
        people: ['person'],
        vehicles: ['car', 'truck', 'bus', 'motorcycle', 'bicycle', 'airplane', 'boat', 'train'],
        animals: ['cat', 'dog', 'bird', 'horse', 'cow', 'sheep', 'elephant', 'bear', 'zebra', 'giraffe'],
        objects: [] // все остальные
    };

    const counts = {
        people: 0,
        vehicles: 0,
        animals: 0,
        objects: 0
    };

    detections.forEach(det => {
        const className = det.class_name.toLowerCase();
        let classified = false;

        for (const [category, classes] of Object.entries(categories)) {
            if (category !== 'objects' && classes.includes(className)) {
                counts[category]++;
                classified = true;
                break;
            }
        }

        if (!classified) {
            counts.objects++;
        }
    });

    // Обновляем счетчики в интерфейсе
    document.getElementById('people-count').textContent = counts.people;
    document.getElementById('vehicles-count').textContent = counts.vehicles;
    document.getElementById('animals-count').textContent = counts.animals;
    document.getElementById('objects-count').textContent = counts.objects;

    // Обновляем общий счетчик в статусе
    const totalCount = document.getElementById('ai-objects-count');
    if (totalCount) {
        totalCount.textContent = detections.length;
    }
}

function showAIFrameModal(frameBase64, detections = []) {
    // Показ модального окна с AI кадром
    const existingModal = document.getElementById('ai-frame-modal');
    if (existingModal) existingModal.remove();

    const detectionsList = detections.map(det =>
        `<span class="badge text-bg-primary me-1">${det.class_name} (${(det.confidence * 100).toFixed(0)}%)</span>`
    ).join('');

    const modal = document.createElement('div');
    modal.id = 'ai-frame-modal';
    modal.className = 'modal fade';
    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">🔍 AI Детекция объектов</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body text-center p-2">
                    <img src="data:image/jpeg;base64,${frameBase64}" 
                         class="img-fluid rounded shadow mb-3" 
                         alt="AI детекция"
                         style="max-height: 60vh;">
                    <div class="text-start">
                        <h6 class="text-muted mb-2">Обнаруженные объекты (${detections.length}):</h6>
                        <div>${detectionsList || '<span class="text-muted">Объекты не обнаружены</span>'}</div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-primary" data-bs-dismiss="modal">Закрыть</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();

    modal.addEventListener('hidden.bs.modal', () => modal.remove());
}

// ==================== АВТООБНОВЛЕНИЕ ====================

function startAutoUpdate() {
    setInterval(() => {
        if (Date.now() - lastDetectionUpdate > 5000) {
            refreshAIDetection();
        }
    }, 5000);
}

// ==================== ИНИЦИАЛИЗАЦИЯ ====================

function initializeAIDetector() {
    console.log('🔍 Инициализация AI детектора...');

    // Первое обновление
    setTimeout(refreshAIDetection, 1000);

    // Запускаем автообновление
    startAutoUpdate();

    console.log('✅ AI детектор инициализирован');
}

// Автоматическая инициализация
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeAIDetector);
} else {
    initializeAIDetector();
}

console.log('🔍 AI Detector модуль загружен');

window.toggleAIStream = toggleAIStream;
window.refreshAIDetection = refreshAIDetection;
window.getAIFrame = getAIFrame;