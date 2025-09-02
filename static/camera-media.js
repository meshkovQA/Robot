// ====== API ФОТО/ВИДЕО, ЗАПИСЬ, СПИСКИ ФАЙЛОВ, UI СТАТУС ======

// НЕ объявляем cameraConnected — он глобальный из camera-stream.js
let isRecording = false;
let recordingStartTime = 0;
let recordingTimer = null;
let currentFileTab = 'photos';

// Кнопки/индикаторы записи (могут отсутствовать на странице)
const recordingIndicator = document.getElementById('recording-indicator');
const recordingTime = document.getElementById('recording-time');
const recordBtn = document.getElementById('record-btn');

// Универсальная отправка (берём из script.js — там уже есть sendCommand; если нет — fallback)
async function _send(url, method, data = null) {
    if (typeof sendCommand === 'function') return await sendCommand(url, method, data);
    try {
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: data ? JSON.stringify(data) : undefined
        });
        return await res.json();
    } catch (e) {
        console.error('network error', e);
        return { success: false, error: 'network' };
    }
}

// ---------- Фото ----------
function takePhoto() {
    if (!window.cameraStream?.isConnected()) {
        if (typeof showAlert === 'function') showAlert('Камера не подключена', 'danger');
        return;
    }
    const filename = `photo_${new Date().toISOString().replace(/[:.]/g, '-')}.jpg`;
    _send('/api/camera/photo', 'POST', { filename })
        .then(data => {
            if (data.success) {
                if (typeof showAlert === 'function') showAlert(`📸 Фото сохранено: ${data.data.filename}`, 'success');
                refreshFiles();
            } else {
                if (typeof showAlert === 'function') showAlert(`Ошибка фото: ${data.error}`, 'danger');
            }
        })
        .catch(err => {
            console.error('Photo error:', err);
            if (typeof showAlert === 'function') showAlert('Ошибка создания фото', 'danger');
        });
}

// ---------- Запись ----------
function toggleRecording() {
    if (!window.cameraStream?.isConnected()) {
        if (typeof showAlert === 'function') showAlert('Камера не подключена', 'danger');
        return;
    }
    isRecording ? stopRecording() : startRecording();
}

function startRecording() {
    const filename = `video_${new Date().toISOString().replace(/[:.]/g, '-')}.mp4`;
    _send('/api/camera/recording/start', 'POST', { filename })
        .then(data => {
            if (data.success) {
                isRecording = true;
                recordingStartTime = Date.now();
                if (recordBtn) { recordBtn.textContent = '⏹️ Стоп'; recordBtn.className = 'camera-btn btn-stop-record'; }
                if (recordingIndicator) recordingIndicator.style.display = 'block';
                recordingTimer = setInterval(updateRecordingTime, 1000);
                if (typeof showAlert === 'function') showAlert(`🎥 Запись начата: ${data.data.filename}`, 'success');
            } else {
                if (typeof showAlert === 'function') showAlert(`Ошибка записи: ${data.error}`, 'danger');
            }
        })
        .catch(err => {
            console.error('Recording start error:', err);
            if (typeof showAlert === 'function') showAlert('Ошибка начала записи', 'danger');
        });
}

function stopRecording() {
    _send('/api/camera/recording/stop', 'POST')
        .then(data => {
            if (data.success) {
                isRecording = false;
                if (recordingTimer) { clearInterval(recordingTimer); recordingTimer = null; }
                if (recordBtn) { recordBtn.textContent = '🎥 Запись'; recordBtn.className = 'camera-btn btn-record'; }
                if (recordingIndicator) recordingIndicator.style.display = 'none';
                if (recordingTime) recordingTime.textContent = '00:00';
                if (typeof showAlert === 'function') showAlert(`⏹️ Запись остановлена: ${data.data.filename}`, 'success');
                refreshFiles();
            } else {
                if (typeof showAlert === 'function') showAlert(`Ошибка остановки записи: ${data.error}`, 'danger');
            }
        })
        .catch(err => {
            console.error('Recording stop error:', err);
            if (typeof showAlert === 'function') showAlert('Ошибка остановки записи', 'danger');
        });
}

function updateRecordingTime() {
    if (!isRecording || !recordingTime) return;
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const seconds = (elapsed % 60).toString().padStart(2, '0');
    recordingTime.textContent = `${minutes}:${seconds}`;
}

// ---------- Файлы ----------
function showFileTab(tabName, event) {
    currentFileTab = tabName;
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    if (event?.target) event.target.classList.add('active');
    else document.querySelector(`.tab-btn[onclick*="${tabName}"]`)?.classList.add('active');

    document.getElementById('photos-list').style.display = tabName === 'photos' ? 'block' : 'none';
    document.getElementById('videos-list').style.display = tabName === 'videos' ? 'block' : 'none';
    refreshFiles();
}

function refreshFiles() {
    if (currentFileTab === 'photos') loadPhotosList(); else loadVideosList();
}

function loadPhotosList() {
    const photosList = document.getElementById('photos-list');
    photosList.innerHTML = '<div class="file-loading">Загрузка...</div>';
    _send('/api/files/photos', 'GET')
        .then(data => {
            if (data.success) displayFileList(data.data.files, 'photos-list', 'photo');
            else photosList.innerHTML = `<div class="file-error">Ошибка: ${data.error}</div>`;
        })
        .catch(err => {
            console.error('Photo list error:', err);
            photosList.innerHTML = '<div class="file-error">Ошибка загрузки списка фото</div>';
        });
}

function loadVideosList() {
    const videosList = document.getElementById('videos-list');
    videosList.innerHTML = '<div class="file-loading">Загрузка...</div>';
    _send('/api/files/videos', 'GET')
        .then(data => {
            if (data.success) displayFileList(data.data.files, 'videos-list', 'video');
            else videosList.innerHTML = `<div class="file-error">Ошибка: ${data.error}</div>`;
        })
        .catch(err => {
            console.error('Video list error:', err);
            videosList.innerHTML = '<div class="file-error">Ошибка загрузки списка видео</div>';
        });
}

function displayFileList(files, containerId, fileType) {
    const container = document.getElementById(containerId);
    if (!files?.length) {
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
                : `<button class="file-action-btn" onclick="downloadFile('${file.url}', '${file.filename}')">⬇️</button>`}
          <button class="file-action-btn btn-danger" onclick="deleteFile('${file.path}', '${file.filename}')">🗑️</button>
        </div>
      </div>`;
    });
    container.innerHTML = html;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Б';
    const k = 1024, sizes = ['Б', 'КБ', 'МБ', 'ГБ'];
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
    if (typeof showAlert === 'function') showAlert(`⬇️ Скачивание: ${filename}`, 'success');
}

function closePhotoModal() {
    document.getElementById('photo-modal').style.display = 'none';
}

function deleteFile(filepath, filename) {
    if (!confirm(`Удалить файл "${filename}"?`)) return;
    _send('/api/files/delete', 'POST', { filepath })
        .then(data => {
            if (data.success) {
                if (typeof showAlert === 'function') showAlert(`🗑️ Файл удален: ${filename}`, 'warning');
                refreshFiles();
            } else {
                if (typeof showAlert === 'function') showAlert(`Ошибка удаления: ${data.error}`, 'danger');
            }
        })
        .catch(err => {
            console.error('Delete error:', err);
            if (typeof showAlert === 'function') showAlert('Ошибка удаления файла', 'danger');
        });
}

function clearOldFiles() {
    const fileType = currentFileTab === 'photos' ? 'фотографий' : 'видео';
    if (!confirm(`Удалить все старые ${fileType}? Это действие нельзя отменить!`)) return;

    const endpoint = currentFileTab === 'photos' ? '/api/files/photos' : '/api/files/videos';
    _send(endpoint, 'GET')
        .then(data => {
            if (!data.success) {
                if (typeof showAlert === 'function') showAlert(`Ошибка получения списка файлов: ${data.error}`, 'danger');
                return;
            }
            const files = data.data.files;
            const weekAgo = Date.now() / 1000 - (7 * 24 * 60 * 60);
            const oldFiles = files.filter(f => f.created < weekAgo);
            if (!oldFiles.length) {
                if (typeof showAlert === 'function') showAlert('Нет файлов старше 7 дней', 'warning');
                return;
            }
            let deleted = 0;
            oldFiles.forEach(file => {
                _send('/api/files/delete', 'POST', { filepath: file.path })
                    .then(del => {
                        if (del.success) {
                            deleted++;
                            if (deleted === oldFiles.length) {
                                if (typeof showAlert === 'function') showAlert(`🗑️ Удалено ${deleted} старых файлов`, 'warning');
                                refreshFiles();
                            }
                        }
                    });
            });
        })
        .catch(err => {
            console.error('Clear files error:', err);
            if (typeof showAlert === 'function') showAlert('Ошибка очистки файлов', 'danger');
        });
}

// ---------- Статус камеры из SSE ----------
function updateCameraStatus(cameraData) {
    const overlayFpsEl = document.getElementById('camera-fps');
    const overlayResEl = document.getElementById('camera-resolution');
    const summaryFpsEl = document.getElementById('current-camera-fps');
    const statusDot = document.getElementById('camera-status');

    const setText = (el, text) => { if (el) el.textContent = text; };

    if (!cameraData) {
        setText(overlayFpsEl, '-- FPS');
        setText(overlayResEl, '--x--');
        setText(summaryFpsEl, '--');
        if (statusDot) statusDot.classList.remove('active');
        cameraConnected = false;
        return;
    }

    const connected = !!(cameraData.connected || cameraData.is_connected || cameraData.available);
    cameraConnected = connected;
    if (statusDot) statusDot.classList.toggle('active', connected);

    let fps = cameraData.fps ?? cameraData.stream_fps ?? cameraData.stats?.fps ?? cameraData.stream?.fps ?? null;
    if (typeof fps === 'string') { const n = Number(fps); fps = Number.isFinite(n) ? n : null; }
    const fpsStr = fps == null ? '--' : (fps % 1 === 0 ? String(fps) : fps.toFixed(1));

    setText(overlayFpsEl, `${fpsStr} FPS`);
    setText(summaryFpsEl, fpsStr);

    let w, h;
    w = cameraData.width ?? cameraData.stream_width ?? cameraData.config?.width ?? cameraData.resolution?.width;
    h = cameraData.height ?? cameraData.stream_height ?? cameraData.config?.height ?? cameraData.resolution?.height;
    const resStr = cameraData.config?.resolution || cameraData.resolution;
    if ((!w || !h) && typeof resStr === 'string') {
        const m = resStr.match(/(\d+)\s*[xX×]\s*(\d+)/);
        if (m) { w = Number(m[1]); h = Number(m[2]); }
    }
    setText(overlayResEl, (w && h) ? `${w}x${h}` : '--x--');

    // Состояние записи по телеметрии
    const recording = !!cameraData.recording;
    if (recording !== isRecording) {
        isRecording = recording;
        if (isRecording) {
            if (recordBtn) { recordBtn.textContent = '⏹️ Стоп'; recordBtn.className = 'camera-btn btn-stop-record'; }
            if (recordingIndicator) recordingIndicator.style.display = 'block';
            const already = Number(cameraData.recording_duration) || 0;
            recordingStartTime = Date.now() - already * 1000;
            if (!recordingTimer) recordingTimer = setInterval(updateRecordingTime, 1000);
        } else {
            if (recordBtn) { recordBtn.textContent = '🎥 Запись'; recordBtn.className = 'camera-btn btn-record'; }
            if (recordingIndicator) recordingIndicator.style.display = 'none';
            if (recordingTimer) { clearInterval(recordingTimer); recordingTimer = null; }
            if (recordingTime) recordingTime.textContent = '00:00';
        }
    }

    if (isRecording && cameraData.recording_duration != null && recordingTime) {
        const duration = Math.floor(Number(cameraData.recording_duration));
        const mm = String(Math.floor(duration / 60)).padStart(2, '0');
        const ss = String(duration % 60).padStart(2, '0');
        recordingTime.textContent = `${mm}:${ss}`;
    }
}

// ---------- Горячие клавиши только для медиа ----------
document.addEventListener('keydown', (event) => {
    if (event.target.tagName === 'INPUT') return;
    const photoModal = document.getElementById('photo-modal');
    if (photoModal && photoModal.style.display === 'block') return;

    switch (event.key.toLowerCase()) {
        case 'p': event.preventDefault(); takePhoto(); break;
        case 'r': event.preventDefault(); toggleRecording(); break;
        case 'f': event.preventDefault(); refreshFiles(); break;
    }
});

// Экспорт
window.cameraMedia = {
    takePhoto, toggleRecording, startRecording, stopRecording,
    showFileTab, refreshFiles, clearOldFiles,
    updateCameraStatus
};

console.log('📸 camera-media.js loaded');