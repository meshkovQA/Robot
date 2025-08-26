// static/ai-control.js - Управление AI функциями робота

// ==================== AI СОСТОЯНИЕ ====================

let aiActive = false;
let aiStreamActive = false;
let followPersonMode = false;
let avoidPeopleMode = true;
let smartNavigationMode = false;

// ==================== AI УПРАВЛЕНИЕ ====================

async function toggleAI() {
    //Запуск/остановка AI системы
    const btn = document.getElementById('ai-toggle-btn');

    if (!aiActive) {
        // Запускаем AI
        try {
            showAlert('🧠 Запуск AI системы...', 'info');

            const response = await fetch('/api/ai/start', { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                aiActive = true;
                btn.textContent = '⏹️ Остановить AI';
                btn.className = 'btn btn-sm btn-danger ms-auto';
                showAlert('🧠 AI система запущена успешно', 'success');

                // Автоматически обновляем данные
                setTimeout(updateAIData, 1000);
            } else {
                showAlert(`Ошибка запуска AI: ${data.error}`, 'danger');
            }
        } catch (error) {
            console.error('AI start error:', error);
            showAlert('Ошибка соединения с AI системой', 'danger');
        }
    } else {
        // Останавливаем AI
        try {
            showAlert('🛑 Остановка AI системы...', 'warning');

            const response = await fetch('/api/ai/stop', { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                aiActive = false;
                btn.textContent = '🚀 Запустить AI';
                btn.className = 'btn btn-sm btn-outline-primary ms-auto';
                showAlert('🛑 AI система остановлена', 'warning');

                // Очищаем AI данные в интерфейсе
                clearAIDisplay();
            }
        } catch (error) {
            console.error('AI stop error:', error);
            showAlert('Ошибка остановки AI системы', 'danger');
        }
    }
}

// ==================== AI РЕЖИМЫ ====================

async function toggleFollowPerson(enable) {
    // Переключение режима следования за человеком
    try {
        const response = await fetch('/api/ai/follow_person', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable })
        });

        const data = await response.json();
        if (data.success) {
            followPersonMode = enable;
            const message = enable ?
                '👤 Режим следования за человеком включен' :
                '👤 Режим следования за человеком выключен';
            showAlert(message, 'info');

            // Обновляем индикатор в интерфейсе
            updateFollowPersonIndicator(enable);
        } else {
            showAlert(`Ошибка переключения режима: ${data.error}`, 'danger');
            // Возвращаем чекбокс в предыдущее состояние
            document.getElementById('follow-person-mode').checked = !enable;
        }
    } catch (error) {
        console.error('Follow person toggle error:', error);
        showAlert('Ошибка переключения режима следования', 'danger');
        document.getElementById('follow-person-mode').checked = !enable;
    }
}

async function toggleAvoidPeople(enable) {
    // Переключение режима избежания людей
    try {
        const response = await fetch('/api/ai/avoid_people', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable })
        });

        const data = await response.json();
        if (data.success) {
            avoidPeopleMode = enable;
            const message = enable ?
                '🚶 Автоматическое избежание людей включено' :
                '🚶 Автоматическое избежание людей выключено';
            showAlert(message, 'info');
        } else {
            showAlert(`Ошибка переключения режима: ${data.error}`, 'danger');
            document.getElementById('avoid-people-mode').checked = !enable;
        }
    } catch (error) {
        console.error('Avoid people toggle error:', error);
        showAlert('Ошибка переключения режима избежания', 'danger');
        document.getElementById('avoid-people-mode').checked = !enable;
    }
}

async function toggleSmartNavigation(enable) {
    // Переключение режима умной навигации
    try {
        const response = await fetch('/api/ai/smart_navigation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable })
        });

        const data = await response.json();
        if (data.success) {
            smartNavigationMode = enable;
            const message = enable ?
                '🧭 Умная навигация включена' :
                '🧭 Умная навигация выключена';
            showAlert(message, 'info');
        } else {
            showAlert(`Ошибка переключения навигации: ${data.error}`, 'danger');
            document.getElementById('smart-navigation-mode').checked = !enable;
        }
    } catch (error) {
        console.error('Smart navigation toggle error:', error);
        showAlert('Ошибка переключения умной навигации', 'danger');
        document.getElementById('smart-navigation-mode').checked = !enable;
    }
}

// ==================== AI ДВИЖЕНИЕ ====================

async function aiSmartMoveForward() {
    // Умное движение вперед с AI проверками
    if (!aiActive) {
        showAlert('⚠️ Сначала запустите AI систему', 'warning');
        return;
    }

    const speed = parseInt(document.getElementById('speed-slider').value);

    try {
        showAlert(`🧠 Выполняю умное движение вперед (${speed})...`, 'info');

        const response = await fetch('/api/ai/smart_move/forward', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ speed })
        });

        const data = await response.json();
        if (data.success) {
            showAlert(`🧠 Умное движение выполнено (${speed})`, 'success');
            updateMovementState(true, 'AI движение вперед');
        } else {
            showAlert(data.message || '🚫 AI заблокировал движение', 'warning');
        }
    } catch (error) {
        console.error('AI smart move error:', error);
        showAlert('Ошибка выполнения умного движения', 'danger');
    }
}

async function aiNavigateTo() {
    // Навигация к цели по описанию
    if (!aiActive) {
        showAlert('⚠️ Сначала запустите AI систему', 'warning');
        return;
    }

    const target = document.getElementById('ai-navigation-target').value.trim();

    if (!target) {
        showAlert('💭 Укажите цель для навигации (например: кухня, диван)', 'warning');
        document.getElementById('ai-navigation-target').focus();
        return;
    }

    try {
        showAlert(`🎯 Попытка навигации к: ${target}`, 'info');

        const response = await fetch('/api/ai/navigate_to', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description: target })
        });

        const data = await response.json();
        if (data.success) {
            showAlert(`🎯 Начинаю навигацию к: ${target}`, 'success');
            // Очищаем поле ввода
            document.getElementById('ai-navigation-target').value = '';
        } else {
            showAlert(`❌ Ошибка навигации: ${data.error}`, 'danger');
        }
    } catch (error) {
        console.error('AI navigation error:', error);
        showAlert('Ошибка системы навигации', 'danger');
    }
}

// ==================== AI ВИДЕОПОТОК ====================

function toggleAIStream() {
    // Переключение между обычным и AI видеопотоком
    const normalStream = document.getElementById('camera-stream');
    const aiStream = document.getElementById('ai-stream');
    const btn = document.getElementById('ai-stream-btn');

    if (!aiStream) {
        console.error('AI stream element not found');
        showAlert('❌ AI видеопоток недоступен', 'danger');
        return;
    }

    if (!aiStreamActive) {
        // Включаем AI поток
        normalStream.style.display = 'none';
        aiStream.style.display = 'block';
        btn.textContent = '📹 Обычное видео';
        btn.className = 'btn btn-sm btn-info';
        aiStreamActive = true;
        showAlert('🔮 AI аннотации включены', 'info');
    } else {
        // Возвращаемся к обычному потоку
        normalStream.style.display = 'block';
        aiStream.style.display = 'none';
        btn.textContent = '🔮 AI Аннотации';
        btn.className = 'btn btn-sm btn-outline-info';
        aiStreamActive = false;
        showAlert('📹 Обычное видео восстановлено', 'info');
    }
}

async function getAIFrame() {
    // Получение и показ AI аннотированного кадра
    if (!aiActive) {
        showAlert('⚠️ Сначала запустите AI систему', 'warning');
        return;
    }

    try {
        showAlert('🖼️ Получение AI кадра...', 'info');

        const response = await fetch('/api/ai/annotated_frame');
        const data = await response.json();

        if (data.success && data.frame) {
            // Создаем модальное окно с AI кадром
            showAIFrameModal(data.frame);
            showAlert('🖼️ AI кадр получен', 'success');
        } else {
            showAlert(`❌ Ошибка получения AI кадра: ${data.error || 'Нет данных'}`, 'danger');
        }
    } catch (error) {
        console.error('Get AI frame error:', error);
        showAlert('❌ Ошибка получения AI кадра', 'danger');
    }
}

function showAIFrameModal(frameBase64) {
    // Показ модального окна с AI кадром
    // Удаляем предыдущий модал если есть
    const existingModal = document.getElementById('ai-frame-modal');
    if (existingModal) {
        existingModal.remove();
    }

    // Создаем новый модал
    const modal = document.createElement('div');
    modal.id = 'ai-frame-modal';
    modal.className = 'modal fade';
    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">🔮 AI Анализ кадра</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body text-center p-2">
                    <img src="data:image/jpeg;base64,${frameBase64}" 
                         class="img-fluid rounded shadow" 
                         alt="AI аннотированный кадр"
                         style="max-height: 70vh;">
                </div>
                <div class="modal-footer">
                    <small class="text-muted">AI обработка: объекты, лица, движение</small>
                    <button type="button" class="btn btn-primary" data-bs-dismiss="modal">Закрыть</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Показываем модал
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();

    // Удаляем модал после закрытия
    modal.addEventListener('hidden.bs.modal', () => {
        modal.remove();
    });
}

// ==================== ОБНОВЛЕНИЕ AI ДАННЫХ ====================

async function updateAIData() {
    // Обновление всех AI данных в интерфейсе
    if (!aiActive) {
        return; // Не обновляем если AI не активен
    }

    try {
        // Получаем статус AI системы
        const aiStatusResponse = await fetch('/api/ai/status');
        if (aiStatusResponse.ok) {
            const aiStatusData = await aiStatusResponse.json();
            if (aiStatusData.success) {
                updateAIStatus(aiStatusData.data);
            }
        }

        // Получаем обнаруженные объекты
        const objectsResponse = await fetch('/api/ai/detected_objects');
        if (objectsResponse.ok) {
            const objectsData = await objectsResponse.json();
            if (objectsData.success) {
                updateAIDetection(objectsData.data);
            }
        }

        // Получаем описание сцены
        const sceneResponse = await fetch('/api/ai/scene_description');
        if (sceneResponse.ok) {
            const sceneData = await sceneResponse.json();
            if (sceneData.success) {
                updateSceneDescription(sceneData.scene_description);
            }
        }

    } catch (error) {
        console.error('AI data update error:', error);
        // Не показываем ошибку пользователю, просто логируем
    }
}

function updateAIStatus(aiData) {
    // Обновление индикаторов состояния AI
    // AI Vision статус
    const aiVisionStatus = document.getElementById('ai-vision-status');
    if (aiVisionStatus) {
        aiVisionStatus.classList.toggle('active', aiData.ai_vision_active || false);
    }

    // Количество обнаруженных объектов
    const objectsCount = document.getElementById('ai-objects-count');
    if (objectsCount) {
        objectsCount.textContent = aiData.detected_objects || 0;
    }

    // Контекст комнаты
    const roomContext = document.getElementById('ai-room-context');
    if (roomContext && aiData.room_context) {
        roomContext.textContent = aiData.room_context;
    }

    // FPS обработки AI
    const aiFps = document.getElementById('ai-fps');
    if (aiFps && aiData.processing_fps !== undefined) {
        aiFps.textContent = aiData.processing_fps.toFixed(1);
    }

    // Синхронизируем состояние чекбоксов
    const followCheckbox = document.getElementById('follow-person-mode');
    const avoidCheckbox = document.getElementById('avoid-people-mode');
    const smartNavCheckbox = document.getElementById('smart-navigation-mode');

    if (followCheckbox) followCheckbox.checked = aiData.follow_person_mode || false;
    if (avoidCheckbox) avoidCheckbox.checked = aiData.auto_avoid_people !== false;
    if (smartNavCheckbox) smartNavCheckbox.checked = aiData.smart_navigation || false;

    // Обновляем внутреннее состояние
    followPersonMode = aiData.follow_person_mode || false;
    avoidPeopleMode = aiData.auto_avoid_people !== false;
    smartNavigationMode = aiData.smart_navigation || false;
}

function updateAIDetection(detectionData) {
    // Обновление данных об обнаруженных объектах
    // Обнаруженные домашние объекты
    const objectsContainer = document.getElementById('detected-objects');
    if (objectsContainer) {
        if (detectionData.objects && detectionData.objects.length > 0) {
            const objectCounts = detectionData.object_counts || {};
            const badges = Object.entries(objectCounts).map(([name, count]) => {
                const displayCount = count > 1 ? ` (${count})` : '';
                return `<span class="badge text-bg-primary">${name}${displayCount}</span>`;
            }).join(' ');
            objectsContainer.innerHTML = badges;
        } else {
            objectsContainer.innerHTML = '<span class="badge text-bg-secondary">Нет объектов</span>';
        }
    }

    // Подсчет людей и питомцев
    const peopleCount = (detectionData.faces || []).length;
    const pets = (detectionData.objects || []).filter(obj => ['cat', 'dog', 'кот', 'собака'].includes(obj.class_name));
    const petsCount = pets.length;

    const peopleCountEl = document.getElementById('people-count');
    const petsCountEl = document.getElementById('pets-count');

    if (peopleCountEl) peopleCountEl.textContent = peopleCount;
    if (petsCountEl) petsCountEl.textContent = petsCount;

    // Обновление индикаторов безопасности пути
    updatePathSafety({
        pets_clear: petsCount === 0,
        person_not_in_path: !detectionData.person_in_front,
        furniture_clear: true, // TODO: реализовать детекцию мебели на пути
        motion_detected: detectionData.motion_detected || false
    });
}

function updateSceneDescription(description) {
    // Обновление описания сцены
    const sceneElement = document.getElementById('ai-scene-description');
    if (sceneElement) {
        sceneElement.textContent = description || 'AI обрабатывает сцену...';
    }
}

function updatePathSafety(safety) {
    // Обновление индикаторов безопасности движения
    const petsBadge = document.getElementById('path-safety-pets');
    const peopleBadge = document.getElementById('path-safety-people');
    const furnitureBadge = document.getElementById('path-safety-furniture');

    if (petsBadge) {
        petsBadge.className = `badge ${safety.pets_clear ? 'text-bg-success' : 'text-bg-warning'}`;
        petsBadge.textContent = `🐕 Питомцы: ${safety.pets_clear ? 'ОК' : '⚠️'}`;
    }

    if (peopleBadge) {
        peopleBadge.className = `badge ${safety.person_not_in_path ? 'text-bg-success' : 'text-bg-danger'}`;
        peopleBadge.textContent = `👤 Люди: ${safety.person_not_in_path ? 'ОК' : '❌'}`;
    }

    if (furnitureBadge) {
        furnitureBadge.className = `badge ${safety.furniture_clear ? 'text-bg-success' : 'text-bg-warning'}`;
        furnitureBadge.textContent = `🪑 Мебель: ${safety.furniture_clear ? 'ОК' : '⚠️'}`;
    }

    // Обновляем подсказки навигации
    updateNavigationHints(safety);
}

function updateNavigationHints(safety) {
    // Обновление подсказок для навигации
    const hintsContainer = document.getElementById('navigation-hints');
    if (!hintsContainer) return;

    const hints = [];

    if (!safety.pets_clear) {
        hints.push('🐕 Питомцы в зоне видимости - двигайтесь осторожно');
    }

    if (!safety.person_not_in_path) {
        hints.push('👤 Человек на пути - дождитесь освобождения прохода');
    }

    if (!safety.furniture_clear) {
        hints.push('🪑 Мебель может мешать - планируйте объезд');
    }

    if (safety.motion_detected) {
        hints.push('🏃 Обнаружено движение - повышенная осторожность');
    }

    if (hints.length === 0) {
        hintsContainer.innerHTML = '<div class="text-success">✅ Путь свободен, безопасно двигаться</div>';
    } else {
        hintsContainer.innerHTML = hints.map(hint =>
            `<div class="text-warning small">💡 ${hint}</div>`
        ).join('');
    }
}

function updateFollowPersonIndicator(enabled) {
    // Обновление индикатора режима следования за человеком
    // Можно добавить визуальные индикаторы в интерфейс
    const indicator = document.querySelector('.follow-person-indicator');
    if (indicator) {
        indicator.classList.toggle('active', enabled);
    }
}

async function refreshAIDetection() {
    // Принудительное обновление AI данных
    showAlert('🔄 Обновление AI данных...', 'info');
    await updateAIData();
    showAlert('✅ AI данные обновлены', 'success');
}

function clearAIDisplay() {
    // Очистка AI данных в интерфейсе при остановке AI
    // Очищаем объекты
    const objectsContainer = document.getElementById('detected-objects');
    if (objectsContainer) {
        objectsContainer.innerHTML = '<span class="badge text-bg-secondary">AI не активен</span>';
    }

    // Очищаем счетчики
    const peopleCount = document.getElementById('people-count');
    const petsCount = document.getElementById('pets-count');
    if (peopleCount) peopleCount.textContent = '0';
    if (petsCount) petsCount.textContent = '0';

    // Очищаем описание сцены
    const sceneDescription = document.getElementById('ai-scene-description');
    if (sceneDescription) {
        sceneDescription.textContent = 'AI не активен';
    }

    // Сбрасываем индикаторы безопасности
    updatePathSafety({
        pets_clear: true,
        person_not_in_path: true,
        furniture_clear: true,
        motion_detected: false
    });
}

// ==================== ГОРЯЧИЕ КЛАВИШИ ДЛЯ AI ====================

function setupAIHotkeys() {
    // Настройка горячих клавиш для AI функций
    document.addEventListener('keydown', function (event) {
        // Игнорируем если фокус на полях ввода
        if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
            return;
        }

        const key = event.key.toLowerCase();

        switch (key) {
            case 'i':
                event.preventDefault();
                toggleAI();
                break;

            case 'f':
                event.preventDefault();
                const followCheckbox = document.getElementById('follow-person-mode');
                if (followCheckbox) {
                    followCheckbox.click();
                }
                break;

            case 'v':
                event.preventDefault();
                toggleAIStream();
                break;

            case 'g':
                event.preventDefault();
                getAIFrame();
                break;

            case 'n': // Navigate
                event.preventDefault();
                const navInput = document.getElementById('ai-navigation-target');
                if (navInput) {
                    navInput.focus();
                }
                break;

            case 'm': // Smart move
                event.preventDefault();
                aiSmartMoveForward();
                break;
        }
    });
}

// ==================== ИНТЕГРАЦИЯ С ОСНОВНОЙ СИСТЕМОЙ ====================

function initializeAI() {
    // Инициализация AI системы
    console.log('🧠 Инициализация AI управления...');

    // Настраиваем горячие клавиши
    setupAIHotkeys();

    // Интегрируемся с основной системой обновления
    const originalUpdateSensorData = window.updateSensorData;
    if (originalUpdateSensorData) {
        window.updateSensorData = function () {
            // Вызываем оригинальную функцию
            originalUpdateSensorData();

            // Добавляем AI обновления
            updateAIData();
        };

        console.log('✅ AI интегрирован с системой обновления датчиков');
    }

    // Показываем подсказки по горячим клавишам
    setTimeout(() => {
        if (typeof showAlert === 'function') {
            showAlert('🧠 AI горячие клавиши: I-вкл/выкл, F-следовать, V-AI видео, G-кадр, N-навигация, M-умное движение', 'info');
        }
    }, 8000);

    console.log('✅ AI управление инициализировано');
}

// ==================== ЭКСПОРТ ДЛЯ ДРУГИХ МОДУЛЕЙ ====================

// Экспортируем основные функции для использования в других скриптах
window.aiControl = {
    // Управление AI
    toggleAI,

    // Режимы
    toggleFollowPerson,
    toggleAvoidPeople,
    toggleSmartNavigation,

    // Движение
    aiSmartMoveForward,
    aiNavigateTo,

    // Видео
    toggleAIStream,
    getAIFrame,

    // Данные
    updateAIData,
    refreshAIDetection,

    // Состояние
    isAIActive: () => aiActive,
    getCurrentModes: () => ({
        followPerson: followPersonMode,
        avoidPeople: avoidPeopleMode,
        smartNavigation: smartNavigationMode
    })
};

// Автоматическая инициализация при загрузке DOM
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeAI);
} else {
    initializeAI();
}

console.log('🧠 AI Control модуль загружен');