// camera.js - Управление камерой робота

// Глобальные переменные камеры
let cameraConnected = false;
let isRecording = false;
let recordingStartTime = 0;
let recordingTimer = null;
let currentFileTab = 'photos';

// Элементы интерфейса камеры
const cameraStream = document.getElementById('camera-stream');
const cameraStatus = document.getElementById('camera-status');
const recordingIndicator = document.getElementById('recording-indicator');
const recordingTime = document.getElementById('recording-time');
const recordBtn = document.getElementById('record-btn');

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
                refreshFiles(); // Обновляем список файлов
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
                refreshFiles(); // Обновляем список файлов
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

                // Перезагружаем стрим через небольшую задержку
                setTimeout(() => {
                    const streamUrl = '/camera/stream?' + Date.now();
                    cameraStream.src = streamUrl;
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

// ==================== УПРАВЛЕНИЕ ФАЙЛАМИ ====================

function showFileTab(tabName) {
    currentFileTab = tabName;

    // Обновляем активную вкладку
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Показываем соответствующий список
    document.getElementById('photos-list').style.display = tabName === 'photos' ? 'block' : 'none';
    document.getElementById('videos-list').style.display = tabName === 'videos' ? 'block' : 'none';

    // Загружаем файлы если еще не загружены
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

    fetch('/api/files/photos')
        .then(response => response.json())
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

    fetch('/api/files/videos')
        .then(response => response.json())
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
                    ${fileType === 'photo' ?
                `<button class="file-action-btn" onclick="viewPhoto('${file.path}', '${file.filename}', '${file.created_str}', '${sizeStr}')">👁️</button>`
                :
                `<button class="file-action-btn" onclick="downloadFile('${file.path}', '${file.filename}')">⬇️</button>`
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

function viewPhoto(filepath, filename, created, size) {
    // Создаем URL для просмотра фото через статический сервер
    const photoUrl = `/static/photos/${filename}`;

    document.getElementById('modal-photo').src = photoUrl;
    document.getElementById('modal-photo-name').textContent = filename;
    document.getElementById('modal-photo-details').textContent = `Создано: ${created} • Размер: ${size}`;
    document.getElementById('photo-modal').style.display = 'block';
}

function closePhotoModal() {
    document.getElementById('photo-modal').style.display = 'none';
}

function downloadFile(filepath, filename) {
    // Создаем временную ссылку для скачивания
    const link = document.createElement('a');
    link.href = `/static/videos/${filename}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showAlert(`⬇️ Скачивание: ${filename}`, 'success');
}

function deleteFile(filepath, filename) {
    if (!confirm(`Удалить файл "${filename}"?`)) {
        return;
    }

    sendCommand('/api/files/delete', 'POST', { filepath: filepath })
        .then(data => {
            if (data.success) {
                showAlert(`🗑️ Файл удален: ${filename}`, 'warning');
                refreshFiles(); // Обновляем список
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

    // Получаем список файлов и удаляем старые (старше 7 дней)
    const endpoint = currentFileTab === 'photos' ? '/api/files/photos' : '/api/files/videos';

    fetch(endpoint)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const files = data.data.files;
                const weekAgo = Date.now() / 1000 - (7 * 24 * 60 * 60); // 7 дней назад
                const oldFiles = files.filter(file => file.created < weekAgo);

                if (oldFiles.length === 0) {
                    showAlert('Нет файлов старше 7 дней', 'warning');
                    return;
                }

                // Удаляем файлы один за другим
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
    if (!cameraData) {
        cameraConnected = false;
        updateCameraStatusIndicator(false);
        document.getElementById('camera-fps').textContent = '-- FPS';
        document.getElementById('camera-resolution').textContent = '--x--';
        document.getElementById('current-camera-fps').textContent = '--';
        return;
    }

    cameraConnected = cameraData.connected || false;
    updateCameraStatusIndicator(cameraConnected);

    // Обновляем информацию о камере
    if (cameraData.fps !== undefined) {
        document.getElementById('camera-fps').textContent = `${cameraData.fps} FPS`;
        document.getElementById('current-camera-fps').textContent = cameraData.fps;
    }

    if (cameraData.config && cameraData.config.resolution) {
        document.getElementById('camera-resolution').textContent = cameraData.config.resolution;
    }

    // Обновляем состояние записи
    if (cameraData.recording !== isRecording) {
        isRecording = cameraData.recording;

        if (isRecording) {
            recordBtn.textContent = '⏹️ Стоп';
            recordBtn.className = 'camera-btn btn-stop-record';
            recordingIndicator.style.display = 'block';

            if (!recordingTimer) {
                recordingStartTime = Date.now() - (cameraData.recording_duration * 1000);
                recordingTimer = setInterval(updateRecordingTime, 1000);
            }
        } else {
            recordBtn.textContent = '🎥 Запись';
            recordBtn.className = 'camera-btn btn-record';
            recordingIndicator.style.display = 'none';

            if (recordingTimer) {
                clearInterval(recordingTimer);
                recordingTimer = null;
            }
        }
    }

    // Обновляем время записи если идет запись
    if (isRecording && cameraData.recording_duration !== undefined) {
        const duration = Math.floor(cameraData.recording_duration);
        const minutes = Math.floor(duration / 60).toString().padStart(2, '0');
        const seconds = (duration % 60).toString().padStart(2, '0');
        recordingTime.textContent = `${minutes}:${seconds}`;
    }
}

function updateCameraStatusIndicator(connected) {
    if (connected) {
        cameraStatus.className = 'status-indicator active';
    } else {
        cameraStatus.className = 'status-indicator';
    }
}

// ==================== КЛАВИАТУРНЫЕ ГОРЯЧИЕ КЛАВИШИ ====================

// Расширяем существующий обработчик клавиатуры
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

    // Добавляем обработчик ошибок для потока камеры
    cameraStream.addEventListener('error', function () {
        console.warn('Ошибка загрузки видеопотока');
        cameraConnected = false;
        updateCameraStatusIndicator(false);
    });

    cameraStream.addEventListener('load', function () {
        console.log('Видеопоток загружен');
        cameraConnected = true;
        updateCameraStatusIndicator(true);
    });

    // Загружаем начальный список фото
    setTimeout(() => {
        refreshFiles();
    }, 1000);

    // Показываем подсказку по горячим клавишам
    setTimeout(() => {
        showAlert('Камера: P - фото, R - запись, F - обновить файлы', 'success');
    }, 3000);
});

// ==================== ИНТЕГРАЦИЯ С ОСНОВНЫМ МОДУЛЕМ ====================

// Расширяем функцию updateSensorData из script.js
const originalUpdateSensorData = window.updateSensorData;
if (originalUpdateSensorData) {
    window.updateSensorData = function () {
        originalUpdateSensorData();

        // Получаем статус камеры
        fetch('/api/camera/status')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    updateCameraStatus(data.data);
                }
            })
            .catch(error => {
                // Тихо игнорируем ошибки статуса камеры
                // чтобы не засорять консоль если камера недоступна
            });
    };
}

// ==================== МОДАЛЬНОЕ ОКНО ====================

// Закрытие модального окна по Escape
document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
        closePhotoModal();
    }
});

// Предотвращаем закрытие модального окна при клике на изображение
document.getElementById('modal-photo').addEventListener('click', function (event) {
    event.stopPropagation();
});

// ==================== УТИЛИТЫ ====================

// Функция для проверки доступности камеры
function checkCameraAvailability() {
    return fetch('/api/camera/status')
        .then(response => response.json())
        .then(data => data.success && data.data.available)
        .catch(() => false);
}

// Функция для получения списка доступных камер
function getAvailableCameras() {
    return fetch('/api/camera/devices')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                return data.data.available_cameras;
            }
            return [];
        })
        .catch(() => []);
}

// Автоматическое обновление стрима при потере соединения
let streamReconnectAttempts = 0;
const maxReconnectAttempts = 5;

cameraStream.addEventListener('error', function () {
    if (streamReconnectAttempts < maxReconnectAttempts) {
        streamReconnectAttempts++;
        console.log(`Попытка переподключения к стриму: ${streamReconnectAttempts}/${maxReconnectAttempts}`);

        setTimeout(() => {
            const streamUrl = '/camera/stream?' + Date.now();
            cameraStream.src = streamUrl;
        }, 2000 * streamReconnectAttempts); // Увеличиваем задержку с каждой попыткой
    }
});

cameraStream.addEventListener('load', function () {
    streamReconnectAttempts = 0; // Сбрасываем счетчик при успешном подключении
});

console.log('🎥 Модуль управления камерой инициализирован');