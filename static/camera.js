// camera.js - Упрощенная версия для стабильной работы камеры

// Глобальные переменные камеры
let cameraConnected = false;
let isRecording = false;
let recordingStartTime = 0;
let recordingTimer = null;
let currentFileTab = 'photos';
let streamVersion = 0;

// Элементы интерфейса камеры
const cameraStatus = document.getElementById('camera-status');
const recordingIndicator = document.getElementById('recording-indicator');
const recordingTime = document.getElementById('recording-time');
const recordBtn = document.getElementById('record-btn');

// Переменные для стрима
let streamRetryCount = 0;
const maxStreamRetries = 3;
let streamRetryTimeout = null;

// ==================== УПРАВЛЕНИЕ КАМЕРОЙ ====================

function takePhoto() {
    if (!cameraConnected) {
        showAlert('Камера не подключена', 'danger');
        return;
    }

    const filename = `photo_${new Date().toISOString().replace(/[:.]/g, '-')}.jpg`;

    sendCommand('/api/camera/photo', 'POST', { filename: filename })
        .then(data => {
            if (data.success) {
                showAlert(`📸 Фото сохранено: ${data.data.filename}`, 'success');
                refreshFiles();
            } else {
                showAlert(`Ошибка фото: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            showAlert('Ошибка создания фото', 'danger');
            console.error('Photo error:', error);
        });
}

function toggleRecording() {
    if (!cameraConnected) {
        showAlert('Камера не подключена', 'danger');
        return;
    }

    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
}

function startRecording() {
    const filename = `video_${new Date().toISOString().replace(/[:.]/g, '-')}.mp4`;

    sendCommand('/api/camera/recording/start', 'POST', { filename: filename })
        .then(data => {
            if (data.success) {
                isRecording = true;
                recordingStartTime = Date.now();

                // Обновляем UI
                recordBtn.textContent = '⏹️ Стоп';
                recordBtn.className = 'camera-btn btn-stop-record';
                recordingIndicator.style.display = 'block';

                // Запускаем таймер записи
                recordingTimer = setInterval(updateRecordingTime, 1000);

                showAlert(`🎥 Запись начата: ${data.data.filename}`, 'success');
            } else {
                showAlert(`Ошибка записи: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            showAlert('Ошибка начала записи', 'danger');
            console.error('Recording start error:', error);
        });
}

function stopRecording() {
    sendCommand('/api/camera/recording/stop', 'POST')
        .then(data => {
            if (data.success) {
                isRecording = false;

                // Останавливаем таймер
                if (recordingTimer) {
                    clearInterval(recordingTimer);
                    recordingTimer = null;
                }

                // Обновляем UI
                recordBtn.textContent = '🎥 Запись';
                recordBtn.className = 'camera-btn btn-record';
                recordingIndicator.style.display = 'none';
                recordingTime.textContent = '00:00';

                showAlert(`⏹️ Запись остановлена: ${data.data.filename}`, 'success');
                refreshFiles();
            } else {
                showAlert(`Ошибка остановки записи: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            showAlert('Ошибка остановки записи', 'danger');
            console.error('Recording stop error:', error);
        });
}

function updateRecordingTime() {
    if (!isRecording) return;

    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const seconds = (elapsed % 60).toString().padStart(2, '0');
    recordingTime.textContent = `${minutes}:${seconds}`;
}

function refreshCamera() {
    showAlert('🔄 Перезапуск камеры...', 'warning');

    sendCommand('/api/camera/restart', 'POST')
        .then(data => {
            if (data.success) {
                showAlert('✅ Камера перезапущена', 'success');

                // Сбрасываем счетчики
                streamRetryCount = 0;

                // Перезагружаем стрим
                setTimeout(() => {
                    initializeVideoStream();
                }, 2000);
            } else {
                showAlert(`Ошибка перезапуска: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            showAlert('Ошибка перезапуска камеры', 'danger');
            console.error('Camera restart error:', error);
        });
}

// ==================== УПРОЩЕННОЕ УПРАВЛЕНИЕ ВИДЕОПОТОКОМ ====================

function initializeVideoStream() {
    let cameraStream = document.getElementById('camera-stream');
    if (!cameraStream) { console.error('Элемент camera-stream не найден'); return; }

    // выключаем AI, если был включён
    const aiStream = document.getElementById('ai-stream');
    if (aiStream && aiStream.style.display !== 'none') {
        hardStopImgStream(aiStream).style.display = 'none';
    }

    // новая версия стрима
    streamVersion++;
    streamRetryCount = 0;                   // сброс ретраев
    if (streamRetryTimeout) { clearTimeout(streamRetryTimeout); streamRetryTimeout = null; }

    console.log('Инициализация видеопотока...');
    const streamUrl = `/camera/stream?_t=${Date.now()}`;

    cameraStream = hardStopImgStream(cameraStream); // клонируем узел (старые слушатели исчезают)
    cameraStream = wireStreamEvents(cameraStream);  // навешиваем ровно 1 set onload/onerror
    cameraStream.style.display = 'block';
    cameraStream.src = streamUrl;

    console.log('Стрим URL установлен:', streamUrl);
}


function handleStreamError() {
    const img = document.getElementById('camera-stream');

    // если уже ждём ретрай — не дублируем
    if (streamRetryTimeout) return;

    const attempt = streamRetryCount + 1;
    console.warn(`Ошибка видеопотока (попытка ${attempt}/${maxStreamRetries})`);

    cameraConnected = false;
    updateCameraStatusIndicator(false);

    // закрываем текущее соединение
    if (img) img.src = '';

    if (streamRetryCount >= maxStreamRetries) {
        console.error('Максимальное количество попыток переподключения исчерпано');
        showAlert('Камера недоступна. Нажмите "🔄 Обновить"', 'danger');
        if (img) img.src = '/static/no-camera.svg';
        return;
    }

    streamRetryCount++;
    const delay = 5000;
    console.log(`Попытка переподключения через ${delay}ms`);
    streamRetryTimeout = setTimeout(() => {
        streamRetryTimeout = null;
        initializeVideoStream();
    }, delay);
}

function wireStreamEvents(img) {
    if (!img) return img;
    // убираем любые старые обработчики
    img.onload = null;
    img.onerror = null;

    const myVersion = streamVersion; // «прикалываем» версию к этому узлу

    img.onload = () => {
        // игнорим, если это событие от старого узла/версии
        if (myVersion !== streamVersion) return;
        handleStreamLoad();
    };
    img.onerror = () => {
        if (myVersion !== streamVersion) return;
        handleStreamError();
    };
    return img;
}

function handleStreamLoad() {
    console.log('✅ Видеопоток успешно загружен');
    streamRetryCount = 0;
    if (streamRetryTimeout) { clearTimeout(streamRetryTimeout); streamRetryTimeout = null; }
    cameraConnected = true;
    updateCameraStatusIndicator(true);
}

function hardStopImgStream(imgEl) {
    if (!imgEl) return null;
    try {
        imgEl.src = '';
        imgEl.removeAttribute('src');
    } catch (e) { }

    const clone = imgEl.cloneNode(false);
    // если это наш основной стрим — сразу вернём с обработчиками
    imgEl.replaceWith(clone);
    if (clone.id === 'camera-stream') wireStreamEvents(clone);
    return clone;
}


function toggleAIStream() {
    let normalStream = document.getElementById('camera-stream');
    let aiStream = document.getElementById('ai-stream');
    const btn = document.getElementById('ai-stream-btn');
    if (!aiStream) return showAlert('❌ AI видеопоток недоступен', 'danger');

    const aiIsOff = normalStream.style.display !== 'none';

    if (aiIsOff) {
        normalStream = hardStopImgStream(normalStream);
        normalStream.style.display = 'none';

        aiStream = hardStopImgStream(aiStream);
        aiStream.style.display = 'block';
        aiStream.src = `/api/ai/stream?fps=12&scale=0.75&quality=70&_t=${Date.now()}`;

        btn.textContent = '📹 Обычное видео';
        btn.className = 'btn btn-sm btn-info';
        showAlert('🔮 AI аннотации включены', 'info');
    } else {
        aiStream = hardStopImgStream(aiStream);
        aiStream.style.display = 'none';

        normalStream = hardStopImgStream(normalStream);
        normalStream = wireStreamEvents(normalStream); // <— ВАЖНО
        normalStream.style.display = 'block';
        normalStream.src = `/camera/stream?_t=${Date.now()}`;

        btn.textContent = '🔮 AI Аннотации';
        btn.className = 'btn btn-sm btn-outline-info';
        showAlert('📹 Обычное видео восстановлено', 'info');
    }
}

// ==================== УПРАВЛЕНИЕ ФАЙЛАМИ ====================

function showFileTab(tabName, event) {
    currentFileTab = tabName;

    // Обновляем активную вкладку
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    if (event && event.target) {
        event.target.classList.add('active');
    } else {
        // Fallback если event не передан
        document.querySelector(`.tab-btn[onclick*="${tabName}"]`)?.classList.add('active');
    }

    // Показываем нужный список
    document.getElementById('photos-list').style.display = tabName === 'photos' ? 'block' : 'none';
    document.getElementById('videos-list').style.display = tabName === 'videos' ? 'block' : 'none';

    refreshFiles();
}

function refreshFiles() {
    if (currentFileTab === 'photos') {
        loadPhotosList();
    } else {
        loadVideosList();
    }
}

function loadPhotosList() {
    const photosList = document.getElementById('photos-list');
    photosList.innerHTML = '<div class="file-loading">Загрузка...</div>';

    sendCommand('/api/files/photos', 'GET')
        .then(data => {
            if (data.success) {
                displayFileList(data.data.files, 'photos-list', 'photo');
            } else {
                photosList.innerHTML = `<div class="file-error">Ошибка: ${data.error}</div>`;
            }
        })
        .catch(error => {
            console.error('Photo list error:', error);
            photosList.innerHTML = '<div class="file-error">Ошибка загрузки списка фото</div>';
        });
}

function loadVideosList() {
    const videosList = document.getElementById('videos-list');
    videosList.innerHTML = '<div class="file-loading">Загрузка...</div>';

    sendCommand('/api/files/videos', 'GET')
        .then(data => {
            if (data.success) {
                displayFileList(data.data.files, 'videos-list', 'video');
            } else {
                videosList.innerHTML = `<div class="file-error">Ошибка: ${data.error}</div>`;
            }
        })
        .catch(error => {
            console.error('Video list error:', error);
            videosList.innerHTML = '<div class="file-error">Ошибка загрузки списка видео</div>';
        });
}

function displayFileList(files, containerId, fileType) {
    const container = document.getElementById(containerId);
    if (files.length === 0) {
        container.innerHTML = `<div class="file-empty">Нет сохраненных ${fileType === 'photo' ? 'фотографий' : 'видео'}</div>`;
        return;
    }

    let html = '';
    files.forEach(file => {
        const sizeStr = formatFileSize(file.size);
        const icon = fileType === 'photo' ? '📸' : '🎥';

        html += `
      <div class="file-item">
        <div class="file-info">
          <div class="file-name">${icon} ${file.filename}</div>
          <div class="file-details">${file.created_str} • ${sizeStr}</div>
        </div>
        <div class="file-actions">
          ${fileType === 'photo'
                ? `<button class="file-action-btn" onclick="viewPhoto('${file.url}', '${file.filename}', '${file.created_str}', '${sizeStr}')">👁️</button>`
                : `<button class="file-action-btn" onclick="downloadFile('${file.url}', '${file.filename}')">⬇️</button>`
            }
          <button class="file-action-btn btn-danger" onclick="deleteFile('${file.path}', '${file.filename}')">🗑️</button>
        </div>
      </div>`;
    });

    container.innerHTML = html;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Б';

    const k = 1024;
    const sizes = ['Б', 'КБ', 'МБ', 'ГБ'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function viewPhoto(url, filename, created, size) {
    const photoUrl = `${url}?_t=${Date.now()}`;
    document.getElementById('modal-photo').src = photoUrl;
    document.getElementById('modal-photo-name').textContent = filename;
    document.getElementById('modal-photo-details').textContent = `Создано: ${created} • Размер: ${size}`;
    document.getElementById('photo-modal').style.display = 'block';
}

function downloadFile(url, filename) {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showAlert(`⬇️ Скачивание: ${filename}`, 'success');
}

function closePhotoModal() {
    document.getElementById('photo-modal').style.display = 'none';
}

function deleteFile(filepath, filename) {
    if (!confirm(`Удалить файл "${filename}"?`)) {
        return;
    }

    sendCommand('/api/files/delete', 'POST', { filepath: filepath })
        .then(data => {
            if (data.success) {
                showAlert(`🗑️ Файл удален: ${filename}`, 'warning');
                refreshFiles();
            } else {
                showAlert(`Ошибка удаления: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            showAlert('Ошибка удаления файла', 'danger');
            console.error('Delete error:', error);
        });
}

function clearOldFiles() {
    const fileType = currentFileTab === 'photos' ? 'фотографий' : 'видео';

    if (!confirm(`Удалить все старые ${fileType}? Это действие нельзя отменить!`)) {
        return;
    }

    const endpoint = currentFileTab === 'photos' ? '/api/files/photos' : '/api/files/videos';

    sendCommand(endpoint, 'GET')
        .then(data => {
            if (data.success) {
                const files = data.data.files;
                const weekAgo = Date.now() / 1000 - (7 * 24 * 60 * 60);
                const oldFiles = files.filter(file => file.created < weekAgo);

                if (oldFiles.length === 0) {
                    showAlert('Нет файлов старше 7 дней', 'warning');
                    return;
                }

                let deleted = 0;
                oldFiles.forEach(file => {
                    sendCommand('/api/files/delete', 'POST', { filepath: file.path })
                        .then(deleteData => {
                            if (deleteData.success) {
                                deleted++;
                                if (deleted === oldFiles.length) {
                                    showAlert(`🗑️ Удалено ${deleted} старых файлов`, 'warning');
                                    refreshFiles();
                                }
                            }
                        });
                });
            } else {
                showAlert(`Ошибка получения списка файлов: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            showAlert('Ошибка очистки файлов', 'danger');
            console.error('Clear files error:', error);
        });
}

// ==================== ОБНОВЛЕНИЕ СТАТУСА КАМЕРЫ ====================

function updateCameraStatus(cameraData) {
    const overlayFpsEl = document.getElementById('camera-fps');          // может не существовать
    const overlayResEl = document.getElementById('camera-resolution');   // может не существовать
    const summaryFpsEl = document.getElementById('current-camera-fps');  // есть в карточке «Датчики»
    const statusDot = document.getElementById('camera-status');

    // helper: безопасное обновление текста, если элемент есть
    const setText = (el, text) => { if (el) el.textContent = text; };

    if (!cameraData) {
        setText(overlayFpsEl, '-- FPS');
        setText(overlayResEl, '--x--');
        setText(summaryFpsEl, '--');
        if (statusDot) statusDot.classList.remove('active');
        cameraConnected = false;
        return;
    }

    // -------- вытаскиваем connected ----------
    const connected = !!(
        cameraData.connected ||
        cameraData.is_connected ||
        cameraData.available
    );
    cameraConnected = connected;
    if (statusDot) statusDot.classList.toggle('active', connected);

    // -------- вытаскиваем FPS из разных возможных мест ----------
    let fps =
        cameraData.fps ??
        cameraData.stream_fps ??
        cameraData.stats?.fps ??
        cameraData.stream?.fps ??
        null;

    if (typeof fps === 'string') {
        const n = Number(fps);
        fps = Number.isFinite(n) ? n : null;
    }
    const fpsStr = fps == null ? '--' : (fps % 1 === 0 ? String(fps) : fps.toFixed(1));

    setText(overlayFpsEl, `${fpsStr} FPS`);
    setText(summaryFpsEl, fpsStr);

    // -------- вытаскиваем разрешение ----------
    let w, h;

    // варианты полей
    w = cameraData.width ?? cameraData.stream_width ?? cameraData.config?.width ?? cameraData.resolution?.width;
    h = cameraData.height ?? cameraData.stream_height ?? cameraData.config?.height ?? cameraData.resolution?.height;

    // если пришла строка вида "1280x720"
    const resStr = cameraData.config?.resolution || cameraData.resolution;
    if ((!w || !h) && typeof resStr === 'string') {
        const m = resStr.match(/(\d+)\s*[xX×]\s*(\d+)/);
        if (m) { w = Number(m[1]); h = Number(m[2]); }
    }

    setText(overlayResEl, (w && h) ? `${w}x${h}` : '--x--');

    // -------- состояние записи ----------
    const recording = !!cameraData.recording;
    if (recording !== isRecording) {
        isRecording = recording;

        if (isRecording) {
            recordBtn.textContent = '⏹️ Стоп';
            recordBtn.className = 'camera-btn btn-stop-record';
            recordingIndicator.style.display = 'block';

            const already = Number(cameraData.recording_duration) || 0;
            recordingStartTime = Date.now() - already * 1000;
            if (!recordingTimer) recordingTimer = setInterval(updateRecordingTime, 1000);
        } else {
            recordBtn.textContent = '🎥 Запись';
            recordBtn.className = 'camera-btn btn-record';
            recordingIndicator.style.display = 'none';
            if (recordingTimer) { clearInterval(recordingTimer); recordingTimer = null; }
            recordingTime.textContent = '00:00';
        }
    }

    if (isRecording && cameraData.recording_duration != null) {
        const duration = Math.floor(Number(cameraData.recording_duration));
        const mm = String(Math.floor(duration / 60)).padStart(2, '0');
        const ss = String(duration % 60).padStart(2, '0');
        recordingTime.textContent = `${mm}:${ss}`;
    }
}

function updateCameraStatusIndicator(connected) {
    if (!cameraStatus) return;
    cameraStatus.className = connected ? 'status-indicator active' : 'status-indicator';
}

// ==================== КЛАВИАТУРНЫЕ ГОРЯЧИЕ КЛАВИШИ ====================

document.addEventListener('keydown', function (event) {
    // Игнорируем если фокус на input элементах
    if (event.target.tagName === 'INPUT') return;

    // Добавляем горячие клавиши для камеры
    switch (event.key.toLowerCase()) {
        case 'p':
            event.preventDefault();
            takePhoto();
            break;
        case 'r':
            event.preventDefault();
            toggleRecording();
            break;
        case 'f':
            event.preventDefault();
            refreshFiles();
            break;
    }
});

// ==================== ИНИЦИАЛИЗАЦИЯ ====================

document.addEventListener('DOMContentLoaded', function () {
    console.log('🎥 Модуль камеры загружен');


    const el = document.getElementById('camera-stream');
    if (!el) { console.error('Элемент camera-stream не найден в DOM'); return; }

    wireStreamEvents(el);              // <— вместо прямых addEventListener на старый узел
    setTimeout(() => initializeVideoStream(), 2000);
    // Показываем подсказки
    setTimeout(() => {
        showAlert('Камера: P - фото, R - запись, F - обновить файлы', 'success');
    }, 5000);
});

// ==================== МОДАЛЬНОЕ ОКНО ====================

// Закрытие модального окна по Escape
document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
        const modal = document.getElementById('photo-modal');
        if (modal && modal.style.display === 'block') {
            event.preventDefault();
            event.stopPropagation(); // не отдаём наверх (в script.js)
            closePhotoModal();
        }
    }
});

window.addEventListener('beforeunload', () => {
    const cam = document.getElementById('camera-stream');
    const ai = document.getElementById('ai-stream');
    if (cam) hardStopImgStream(cam);
    if (ai) hardStopImgStream(ai);
});

document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
        // при сворачивании вкладки лучше разорвать длинные коннекты
        const cam = document.getElementById('camera-stream');
        const ai = document.getElementById('ai-stream');
        if (cam) hardStopImgStream(cam);
        if (ai) hardStopImgStream(ai);
    }
});

console.log('🎥 Модуль управления камерой инициализирован');