/**
 * Модуль админ-панели: Сделки и настройки процессов.
 * Подключается через main.js и использует явные ES module зависимости.
 */
import { STORAGE_KEYS } from './state.js';
import { showToast, observeAdminModals, restoreAdminModal } from './core.js';
import { escapeHtml } from './reports.js';
import { saveProductQuantity } from './traffic-light.js';
import { loadPointsMatrix } from './tasks.js';
import { registerDealViewer } from './deals.js';
import { loadMailingNotifications } from './mailing.js';
import { createDealDetailContent } from './deal-view.js';
import { createElement, showMessage } from './dom.js';

const initializedProcsetsContainers = new WeakSet();

export function initProcsetsTab() {
    const container = document.getElementById('procsets-tab');
    if (!container || initializedProcsetsContainers.has(container)) return;
    initializedProcsetsContainers.add(container);

    let mainAssigneeHandler = null;
    let removeAssigneeHandler = null;
    let addAssigneeHandler = null;
    let matrixChangeHandler = null;
    let closeDetailHandler = null;
    let detailWindowClickHandler = null;
    // ---- Локальное состояние раздела ----
    let deals = [];
    let dealTypes = [];
    let ips = [];
    let mps = [];
    let taskTypes = [];
    let allTasks = [];
    let products = [];
    let techCards = [];
    let roles = [];
    let allEmployees = [];
    let constructorTasks = [];
    let currentTechCardId = null;
    let techCardNameInput = null;
    let techCardSelect = null;
    let constructorListEl = null;
    let saveConstructorBtn = null;
    let deleteConstructorBtn = null;
    let clearConstructorBtn = null;
    let constructorInitialized = false;

    // ---- Переменные для импорта товаров ----
    let importedProducts = [];

    // ---- Базовый путь для импорта ----
    const BASE_PATH = "W:\\!МП_(FSk)";

    // ---- Элементы ----
    const dealsListEl = container.querySelector('#dealsList');
    const refreshBtn = container.querySelector('#refreshDealsBtn');
    const createBtn = container.querySelector('#createDealBtn');
    const modalCreate = container.querySelector('#createDealModal');
    const closeCreate = container.querySelector('#closeCreateModal');
    const cancelCreate = container.querySelector('#cancelCreateBtn');
    const createForm = container.querySelector('#createDealForm');
    const createError = container.querySelector('#createError');
    const detailModal = container.querySelector('#detailModal');
    const closeDetail = container.querySelector('#closeDetailModal');
    const detailBody = container.querySelector('#detailBody');
    const detailTitle = container.querySelector('#detailTitle');
    const dealsCount = container.querySelector('#dealsCount');

    // ---- Импорт товаров: элементы ----
    const importBtn = container.querySelector('#importProductsBtn');
    const importStatus = container.querySelector('#importStatus');
    const importPreviewContainer = container.querySelector('#importPreviewContainer');
    const importPreviewBody = container.querySelector('#importPreviewBody');
    const clearImportBtn = container.querySelector('#clearImportBtn');
    const importPathInput = container.querySelector('#importPathInput');
    const resetPathBtn = container.querySelector('#resetPathBtn');

    // ---- Вспомогательная функция apiFetch ----
    async function apiFetch(url, options = {}) {
        const resp = await fetch(url, {
            ...options,
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', ...(options.headers || {}) },
            credentials: 'include'
        });
        if (!resp.ok) {
            let detail = '';
            try {
                const errData = await resp.json();
                detail = errData.detail || resp.statusText;
            } catch (e) {
                detail = await resp.text() || resp.statusText;
            }
            throw new Error(`Ошибка ${resp.status}: ${detail}`);
        }
        return resp;
    }

    // ---- Обновление названия сделки (автозаполнение) ----
    function updateDealTitle() {
        const typeSelect = container.querySelector('#dealType');
        const ipSelect = container.querySelector('#dealIp');
        const mpSelect = container.querySelector('#dealMp');
        const titleInput = container.querySelector('#dealTitle');
        if (!typeSelect || !titleInput) return;

        const typeId = parseInt(typeSelect.value);
        const typeObj = dealTypes.find(t => t.id === typeId);
        const typeName = typeObj ? typeObj.name : '';

        const ip = ipSelect ? ipSelect.value : '';
        const mp = mpSelect ? mpSelect.value : '';

        const now = new Date();
        const year = String(now.getFullYear()).slice(2);
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        const dateStr = year + month + day;

        let title = '';
        if (typeName === 'FBS' || typeName === 'FSK') {
            title = dateStr + '_' + typeName;
        } else if (typeName === 'FBO') {
            if (ip && mp) {
                const ipText = ipSelect.options[ipSelect.selectedIndex]?.text || '';
                const mpText = mpSelect.options[mpSelect.selectedIndex]?.text || '';
                title = dateStr + '_' + ipText + '_' + mpText;
            } else {
                title = '';
            }
        }
        titleInput.value = title;
    }

    // ---- Обновление пути импорта ----
    function updateImportPath() {
        if (!importPathInput) return;

        const typeSelect = container.querySelector('#dealType');
        const ipSelect = container.querySelector('#dealIp');
        const mpSelect = container.querySelector('#dealMp');
        const titleInput = container.querySelector('#dealTitle');

        const typeId = parseInt(typeSelect?.value || 0);
        const typeObj = dealTypes.find(t => t.id === typeId);
        const typeName = typeObj ? typeObj.name : '';
        const ipText = ipSelect ? ipSelect.options[ipSelect.selectedIndex]?.text || '' : '';
        const mpText = mpSelect ? mpSelect.options[mpSelect.selectedIndex]?.text || '' : '';
        const title = titleInput ? titleInput.value : '';
        const dateMatch = title.match(/^(\d{6})/);
        const date = dateMatch ? dateMatch[1] : new Date().toISOString().slice(2,10).replace(/-/g,'');

        let path = '';
        if (typeName === 'FBS') {
            path = `${BASE_PATH}\\!FBS\\${date}_FBS\\Книга1.xlsx`;
        } else if (typeName === 'FSK') {
            path = `${BASE_PATH}\\${date}_FSk\\b24.xlsx`;
        } else if (typeName === 'FBO') {
            if (ipText && mpText) {
                path = `${BASE_PATH}\\${date}_${ipText}_${mpText}\\b24.xlsx`;
            }
        }
        importPathInput.value = path;
    }

    function toggleIpMpVisibility() {
        const typeSelect = container.querySelector('#dealType');
        const ipSelect = container.querySelector('#dealIp');
        const mpSelect = container.querySelector('#dealMp');
        const ipGroup = ipSelect?.closest('.form-group');
        const mpGroup = mpSelect?.closest('.form-group');
        if (!typeSelect || !ipGroup || !mpGroup) return;

        const typeId = parseInt(typeSelect.value);
        const typeObj = dealTypes.find(t => t.id === typeId);
        const typeName = typeObj ? typeObj.name : '';

        if (typeName === 'FBS' || typeName === 'FSK') {
            ipGroup.style.display = 'none';
            mpGroup.style.display = 'none';
            ipSelect.removeAttribute('required');
            mpSelect.removeAttribute('required');
            // Сбрасываем значения, чтобы не передавались
            ipSelect.value = '';
            mpSelect.value = '';
        } else {
            ipGroup.style.display = '';
            mpGroup.style.display = '';
            ipSelect.setAttribute('required', 'required');
            mpSelect.setAttribute('required', 'required');
        }
    }

    // ---- Функция, вызываемая при изменении параметров ----
    function onParametersChanged() {
        updateDealTitle();
        updateImportPath();
        toggleIpMpVisibility();
    }

    // ---- Загрузка типов сделок ----
    async function loadDealTypes() {
        try {
            const resp = await apiFetch('/api/sandbox/deal-types');
            dealTypes = await resp.json();
            renderList('dealTypesList', dealTypes);
            populateDealTypeSelect();
        } catch (err) {
            console.error('Ошибка загрузки типов сделок:', err);
            showToast('Не удалось загрузить типы сделок', true);
        }
    }

    function populateDealTypeSelect() {
        const typeSelect = container.querySelector('#dealType');
        if (typeSelect) {
            typeSelect.innerHTML = dealTypes.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
        }
    }

    // ---- Загрузка сделок ----
    async function loadDeals() {
        try {
            const resp = await apiFetch('/api/sandbox/deals?limit=100');
            deals = await resp.json();
            renderDeals(deals);
        } catch (err) {
            showMessage(dealsListEl, `Ошибка загрузки: ${err.message}`, 'error');
            showToast(err.message, true);
        }
    }

    function renderDeals(dealsList) {
        if (!dealsList?.length) {
            showMessage(dealsListEl, 'Нет сделок');
            dealsCount.textContent = '0';
            return;
        }
        dealsCount.textContent = dealsList.length;
        const table = createElement('table');
        const header = createElement('tr');
        ['ID', 'Название', 'Тип', 'Действия'].forEach(label => header.append(createElement('th', { text: label })));
        table.append(createElement('thead', {}, header));
        const tbody = createElement('tbody');
        dealsList.forEach(deal => {
            const typeName = dealTypes.find(type => type.id === deal.deal_type_id)?.name || '—';
            tbody.append(createElement('tr', {}, [
                createElement('td', { text: deal.id }),
                createElement('td', {}, createElement('button', {
                    className: 'deal-title-link', text: deal.title, attrs: { type: 'button' }, dataset: { id: deal.id }
                })),
                createElement('td', { text: typeName }),
                createElement('td', {}, createElement('button', {
                    className: 'delete-deal-btn', text: '🗑️', attrs: { type: 'button' }, dataset: { id: deal.id }
                }))
            ]));
        });
        table.append(tbody);
        dealsListEl.replaceChildren(table);
        dealsListEl.querySelectorAll('.delete-deal-btn').forEach(button => {
            button.addEventListener('click', () => deleteDeal(Number(button.dataset.id)));
        });
    }

    // ---- Просмотр сделки ----
    async function viewDeal(dealId, taskId = null) {
        const expandedTaskIds = new Set();
        const currentContextRaw = sessionStorage.getItem(STORAGE_KEYS.dealModalContext);
        const modalIsOpen = detailModal && detailModal.style.display === 'block';
        if (modalIsOpen && currentContextRaw) {
            try {
                const currentContext = JSON.parse(currentContextRaw);
                if (Number(currentContext.dealId) === Number(dealId)) {
                    detailBody.querySelectorAll('.task-accordion-item').forEach(item => {
                        const details = item.querySelector('.task-accordion-details');
                        if (details && details.style.display !== 'none') {
                            expandedTaskIds.add(Number(item.dataset.taskId));
                        }
                    });
                }
            } catch (e) {
                console.warn('Не удалось восстановить состояние задач сделки', e);
            }
        }
        sessionStorage.setItem(STORAGE_KEYS.dealModalContext, JSON.stringify({ dealId, taskId }));
        try {
            const resp = await apiFetch(`/api/sandbox/deals/${dealId}`);
            const deal = await resp.json();
            showDetail(deal, taskId, expandedTaskIds);
        } catch (err) {
            showToast(err.message, true);
        }
    }
    registerDealViewer(viewDeal);
function showDetail(deal, selectedTaskId = null, expandedTaskIds = new Set()) {
    // ---- Заголовок с редактированием названия ----
    const titleSpan = document.createElement('span');
    const selectedTask = selectedTaskId
        ? (deal.tasks || []).find(task => Number(task.task_id) === Number(selectedTaskId))
        : null;
    titleSpan.textContent = selectedTask
        ? `Задача: ${selectedTask.task_name} — ${deal.title}`
        : `Сделка: ${deal.title}`;
    titleSpan.style.cursor = 'pointer';
    titleSpan.title = selectedTask ? '' : 'Кликните, чтобы изменить название';

    function enableTitleEditing() {
        const currentTitle = titleSpan.textContent.replace(/^Сделка: /, '');
        const input = document.createElement('input');
        input.type = 'text';
        input.value = currentTitle;
        input.style.fontSize = '1.5rem';
        input.style.fontWeight = 'bold';
        input.style.border = '1px solid #3b82f6';
        input.style.borderRadius = '8px';
        input.style.padding = '4px 12px';
        input.style.width = '80%';
        input.style.background = 'white';

        titleSpan.replaceWith(input);
        input.focus();
        input.select();

        function saveTitle() {
            const newTitle = input.value.trim();
            if (newTitle && newTitle !== currentTitle) {
                updateDealTitle(deal.id, newTitle);
            }
            titleSpan.textContent = `Сделка: ${newTitle || currentTitle}`;
            input.replaceWith(titleSpan);
        }

        function cancelEdit() {
            input.replaceWith(titleSpan);
        }

        input.addEventListener('blur', saveTitle);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                input.blur();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cancelEdit();
            }
        });
    }

    if (!selectedTask) titleSpan.addEventListener('click', enableTitleEditing);
    detailTitle.innerHTML = '';
    detailTitle.appendChild(titleSpan);

    const detailContent = createDealDetailContent(deal, selectedTask, expandedTaskIds, products);
    detailBody.replaceChildren(detailContent);
    detailModal.style.display = 'block';

    function setTaskAccordionOpen(item, isOpen) {
        const details = item.querySelector('.task-accordion-details');
        const header = item.querySelector('.task-accordion-header');
        const toggle = item.querySelector('.task-accordion-toggle');
        if (!details || !header || !toggle) return;
        details.style.display = isOpen ? 'block' : 'none';
        header.style.borderRadius = isOpen ? '12px 12px 0 0' : '12px';
        toggle.setAttribute('aria-expanded', String(isOpen));
    }

    detailBody.querySelectorAll('.task-accordion-toggle').forEach(toggle => {
        toggle.addEventListener('click', () => {
            const item = toggle.closest('.task-accordion-item');
            if (!item) return;
            const isOpen = item.querySelector('.task-accordion-details')?.style.display !== 'none';
            setTaskAccordionOpen(item, !isOpen);
        });
    });

    // ---- Заполняем select для добавления товара ----
    populateAddProductSelect();

    // ---- Активируем редактирование (количество, статус, время) ----
    enableInlineEditing(deal.id);

    if (selectedTask) {
        const taskContainer = detailBody.querySelector('.task-accordion-item');
        const productSelect = taskContainer?.querySelector('.task-product-add-select');
        const assignedProductIds = new Set((selectedTask.products || []).map(product => Number(product.id)));
        if (productSelect) {
            productSelect.innerHTML = '<option value="">-- Выберите товар --</option>' + products
                .filter(product => !assignedProductIds.has(Number(product.id)))
                .map(product => `<option value="${product.id}">${escapeHtml(product.full_name || product.name)}</option>`)
                .join('');
        }
        taskContainer?.querySelector('.task-product-add')?.addEventListener('click', async () => {
            const productId = Number(productSelect?.value);
            const rawQuantity = taskContainer.querySelector('.task-product-add-quantity')?.value.trim() || '';
            const quantity = rawQuantity === '' ? null : Number(rawQuantity);
            if (!productId) return showToast('Выберите товар', true);
            if (quantity !== null && (!Number.isInteger(quantity) || quantity < 0)) {
                return showToast('Количество должно быть целым неотрицательным числом', true);
            }
            try {
                await apiFetch(`/api/sandbox/deals/${deal.id}/tasks/${selectedTask.task_id}/products`, {
                    method: 'PUT',
                    body: JSON.stringify([{ product_id: productId, quantity }])
                });
                showToast('Товар добавлен в задачу');
                viewDeal(deal.id, selectedTask.task_id);
                loadMailingNotifications();
            } catch (err) {
                showToast(err.message, true);
            }
        });
        taskContainer?.querySelectorAll('.task-product-delete').forEach(button => {
            button.addEventListener('click', async () => {
                if (!confirm('Удалить товар из этой задачи?')) return;
                try {
                    await apiFetch(`/api/sandbox/deals/${deal.id}/tasks/${selectedTask.task_id}/products/${button.dataset.productId}`, { method: 'DELETE' });
                    showToast('Товар удалён из задачи');
                    viewDeal(deal.id, selectedTask.task_id);
                    loadMailingNotifications();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
        taskContainer?.querySelectorAll('.task-product-quantity').forEach(input => {
            input.addEventListener('change', async () => {
                const quantity = input.value.trim() === '' ? null : Number(input.value);
                if (quantity !== null && (!Number.isInteger(quantity) || quantity < 0)) {
                    return viewDeal(deal.id, selectedTask.task_id);
                }
                try {
                    await apiFetch(`/api/sandbox/deals/${deal.id}/tasks/${selectedTask.task_id}/products`, {
                        method: 'PUT',
                        body: JSON.stringify([{ product_id: Number(input.dataset.productId), quantity }])
                    });
                    showToast('Количество обновлено');
                    loadMailingNotifications();
                } catch (err) {
                    showToast(err.message, true);
                    viewDeal(deal.id, selectedTask.task_id);
                }
            });
        });
    }

    // ---- Обработчик добавления товара ----
    const addBtn = document.getElementById('addProductToDealBtn');
    if (addBtn) {
        addBtn.addEventListener('click', function() {
            addProductToDeal(deal.id);
        });
    }

    // ---- Обработчики удаления товара ----
    detailBody.querySelectorAll('.delete-product-from-deal').forEach(btn => {
        btn.addEventListener('click', async function(e) {
            e.stopPropagation();
            const productId = parseInt(this.dataset.productId);
            if (!confirm('Удалить этот товар из сделки?')) return;
            try {
                await deleteProductFromDeal(deal.id, productId);
                showToast('Товар удалён из сделки');
                viewDeal(deal.id, selectedTaskId);
            } catch (err) {
                showToast(err.message, true);
            }
        });
    });

    // ---- Обработчик кнопки запуска ----
    const startBtn = document.getElementById('startDealBtn');
    if (startBtn) {
        startBtn.addEventListener('click', async function() {
            try {
                const resp = await fetch(`/api/sandbox/deals/${deal.id}/start`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || 'Ошибка запуска');
                }
                const data = await resp.json();
                showToast(`✅ ${data.message}`);
                loadDeals();
                viewDeal(deal.id, selectedTaskId);
            } catch (err) {
                showToast(`❌ Ошибка: ${err.message}`, true);
            }
        });
    }

    // ---- Обработчик кнопки завершения сделки ----
    const completeBtn = document.getElementById('completeDealBtn');
    if (completeBtn) {
        completeBtn.addEventListener('click', async function() {
            if (!confirm('Вы уверены, что хотите завершить сделку? Все задачи будут считаться закрытыми.')) return;
            try {
                const resp = await fetch(`/api/sandbox/deals/${deal.id}/complete`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || 'Ошибка завершения');
                }
                const data = await resp.json();
                showToast(`✅ ${data.message}`);
                loadDeals(); // обновляем список сделок в таблице
                viewDeal(deal.id, selectedTaskId); // обновляем модалку, чтобы кнопка сменилась на "Сделка завершена"
            } catch (err) {
                showToast(`❌ Ошибка: ${err.message}`, true);
            }
        });
    }

    // ============================================================
    //  ОБРАБОТЧИКИ (делегирование) – оставляем ТОЧНО ТАКИЕ ЖЕ, как в оригинале,
    //  чтобы они работали с новыми элементами.
    //  Они уже привязаны к detailBody, но мы пересоздаём их каждый раз,
    //  чтобы избежать дублирования.
    // ============================================================

    // ---- Замена основного исполнителя (клик по .main-assignee) ----
    if (mainAssigneeHandler) {
        detailBody.removeEventListener('click', mainAssigneeHandler);
    }
    mainAssigneeHandler = async function(e) {
        const target = e.target.closest('.main-assignee');
        if (!target) return;
        e.preventDefault();
        e.stopPropagation();

        const taskId = parseInt(target.dataset.taskId);
        const container = target.closest('.task-accordion-item');
        if (!container) return;

        // Собираем имена всех исполнителей из этого блока
        const assigneeSpans = container.querySelectorAll('.assignee-tag');
        const assignedNames = [];
        assigneeSpans.forEach(span => {
            const name = span.textContent.trim();
            if (name) assignedNames.push(name);
        });

        if (!allEmployees || allEmployees.length === 0) {
            await loadAllEmployees();
        }
        const assignedIds = [];
        allEmployees.forEach(emp => {
            if (assignedNames.includes(emp.full_name)) {
                assignedIds.push(emp.id);
            }
        });
        const available = allEmployees.filter(e => !assignedIds.includes(e.id) && e.is_active === 1);
        if (available.length === 0) {
            showToast('Нет доступных сотрудников для замены', true);
            return;
        }

        const select = document.createElement('select');
        select.style.cssText = 'width:100%; padding:4px; border-radius:8px; border:1px solid #cbd5e1;';
        select.innerHTML = '<option value="">-- Выберите нового основного --</option>';
        available.forEach(emp => {
            select.innerHTML += `<option value="${emp.id}">${escapeHtml(emp.full_name)}</option>`;
        });

        const form = document.createElement('div');
        form.style.cssText = 'margin-top:4px; display:flex; gap:6px; align-items:center; flex-wrap:wrap;';
        form.appendChild(select);
        const saveBtn = document.createElement('button');
        saveBtn.textContent = '💾 Назначить';
        saveBtn.style.cssText = 'background:#3b82f6; border:none; color:white; padding:4px 12px; border-radius:16px; cursor:pointer;';
        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '❌ Отмена';
        cancelBtn.style.cssText = 'background:#94a3b8; border:none; color:white; padding:4px 12px; border-radius:16px; cursor:pointer;';
        form.appendChild(saveBtn);
        form.appendChild(cancelBtn);

        const originalName = target.textContent;
        form.dataset.originalName = originalName;
        const parentSpan = target.closest('.assignee-tag');
        if (parentSpan) {
            parentSpan.innerHTML = '';
            parentSpan.appendChild(form);
            select.focus();
        }

        saveBtn.addEventListener('click', async function() {
            const empId = parseInt(select.value);
            if (!empId) {
                showToast('Выберите сотрудника', true);
                return;
            }
            try {
                const resp = await fetch(`/api/sandbox/deals/${deal.id}/tasks/${taskId}/assignee`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ employee_id: empId }),
                    credentials: 'include'
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || 'Ошибка обновления');
                }
                showToast('✅ Основной исполнитель обновлён');
                viewDeal(deal.id, selectedTaskId);
            } catch (err) {
                showToast(err.message, true);
            }
        });

        cancelBtn.addEventListener('click', function() {
            const name = form.dataset.originalName || '—';
            const newSpan = document.createElement('span');
            newSpan.className = 'assignee-tag main-assignee';
            newSpan.dataset.taskId = taskId;
            newSpan.style.cssText = 'cursor:pointer; background:#dbeafe; font-weight:bold; padding:2px 12px; border-radius:16px; margin-right:4px; display:inline-block;';
            newSpan.textContent = name;
            if (parentSpan) {
                parentSpan.innerHTML = '';
                parentSpan.appendChild(newSpan);
            }
        });
    };
    detailBody.addEventListener('click', mainAssigneeHandler);

    // ---- Удаление соисполнителя (клик по .remove-assignee-btn) ----
    if (removeAssigneeHandler) {
        detailBody.removeEventListener('click', removeAssigneeHandler);
    }
    removeAssigneeHandler = async function(e) {
        const removeBtn = e.target.closest('.remove-assignee-btn');
        if (!removeBtn) return;
        e.stopPropagation();

        const taskId = parseInt(removeBtn.dataset.taskId);
        const employeeId = parseInt(removeBtn.dataset.employeeId);
        const notificationId = removeBtn.dataset.notificationId;
        const dealId = deal.id;

        if (!confirm('Удалить этого соисполнителя?')) return;

        try {
            const resp = await fetch(`/api/sandbox/deals/${dealId}/tasks/${taskId}/assignees/${employeeId}`, {
                method: 'DELETE',
                credentials: 'include'
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Ошибка удаления');
            }
            showToast('✅ Соисполнитель удалён');
            viewDeal(dealId, selectedTaskId);
        } catch (err) {
            showToast(err.message, true);
        }
    };
    detailBody.addEventListener('click', removeAssigneeHandler);

    // ---- Добавление соисполнителя (клик по .add-assignee-btn) ----
    if (addAssigneeHandler) {
        detailBody.removeEventListener('click', addAssigneeHandler);
    }
    addAssigneeHandler = function(e) {
        const btn = e.target.closest('.add-assignee-btn');
        if (!btn) return;
        e.stopPropagation();
        const taskId = parseInt(btn.dataset.taskId);
        const container = btn.closest('.task-accordion-item');
        if (!container) return;

        // Собираем текущие имена исполнителей
        const assigneeSpans = container.querySelectorAll('.assignee-tag');
        const assignedNames = [];
        assigneeSpans.forEach(span => {
            const name = span.textContent.trim();
            if (name) assignedNames.push(name);
        });

        if (!allEmployees || allEmployees.length === 0) {
            loadAllEmployees().then(() => openAddAssigneeModal(deal.id, taskId, assignedNames));
        } else {
            openAddAssigneeModal(deal.id, taskId, assignedNames);
        }
    };
    detailBody.addEventListener('click', addAssigneeHandler);

    // ---- Вспомогательная функция для модалки добавления соисполнителя ----
    function openAddAssigneeModal(dealId, taskId, assignedNames) {
        const assignedIds = [];
        allEmployees.forEach(emp => {
            if (assignedNames.includes(emp.full_name)) {
                assignedIds.push(emp.id);
            }
        });
        const available = allEmployees.filter(e => !assignedIds.includes(e.id) && e.is_active === 1);
        if (available.length === 0) {
            showToast('Нет доступных сотрудников для добавления', true);
            return;
        }

        const modal = createSelectionModal({
            title: 'Добавить соисполнителя для задачи',
            selectId: 'assigneeSelect',
            options: available.map(employee => ({ value: employee.id, label: employee.full_name })),
            cancelId: 'cancelAssignBtn',
            confirmId: 'confirmAssignBtn',
            confirmLabel: 'Добавить'
        });
        document.body.appendChild(modal);

        const closeModal = () => modal.remove();
        modal.querySelector('.modal-close').addEventListener('click', closeModal);
        modal.querySelector('#cancelAssignBtn').addEventListener('click', closeModal);
        window.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

        modal.querySelector('#confirmAssignBtn').addEventListener('click', async () => {
            const empId = parseInt(modal.querySelector('#assigneeSelect').value);
            if (!empId) {
                showToast('Выберите сотрудника', true);
                return;
            }
            try {
                const resp = await fetch(`/api/sandbox/deals/${dealId}/tasks/${taskId}/assignees`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ employee_id: empId }),
                    credentials: 'include'
                });
                if (resp.ok) {
                    showToast('Соисполнитель добавлен');
                    closeModal();
                    viewDeal(dealId, selectedTaskId);
                } else {
                    const err = await resp.json();
                    showToast(err.detail || 'Ошибка', true);
                }
            } catch (err) {
                showToast('Ошибка сети', true);
            }
        });
    }

    // ---- Сохранение изменений при закрытии модалки (та же логика, что в оригинале) ----
    function saveAllFields() {
        const dealId = deal.id;

        document.querySelectorAll('.product-quantity-input').forEach(input => {
            if (input.style.display !== 'none') {
                const display = input.closest('td').querySelector('.product-quantity-display');
                if (display && parseInt(input.value) !== parseInt(display.textContent)) {
                    saveProductQuantity(input, dealId);
                } else {
                    input.style.display = 'none';
                    if (display) display.style.display = 'inline';
                }
            }
        });

        document.querySelectorAll('.task-status-select').forEach(select => {
            if (select.style.display !== 'none') {
                const notificationId = select.dataset.notificationId;
                saveTaskStatus(select, dealId, notificationId);
            }
        });

        document.querySelectorAll('.task-started-input').forEach(input => {
            if (input.style.display !== 'none') {
                const display = input.closest('div').querySelector('.task-started-display');
                const newVal = input.value;
                const oldIso = display.dataset.iso || '';
                let oldVal = '';
                if (oldIso) {
                    oldVal = new Date(oldIso).toISOString().slice(0,16);
                }
                if (newVal !== oldVal) {
                    const notificationId = input.dataset.notificationId;
                    saveTaskTime(input, dealId, 'started_at', notificationId);
                } else {
                    input.style.display = 'none';
                    if (display) display.style.display = 'inline';
                }
            }
        });

        document.querySelectorAll('.task-completed-input').forEach(input => {
            if (input.style.display !== 'none') {
                const display = input.closest('div').querySelector('.task-completed-display');
                const newVal = input.value;
                const oldIso = display.dataset.iso || '';
                let oldVal = '';
                if (oldIso) {
                    oldVal = new Date(oldIso).toISOString().slice(0,16);
                }
                if (newVal !== oldVal) {
                    const notificationId = input.dataset.notificationId;
                    saveTaskTime(input, dealId, 'completed_at', notificationId);
                } else {
                    input.style.display = 'none';
                    if (display) display.style.display = 'inline';
                }
            }
        });
    }

    // ============================================================
    // ОБРАБОТЧИК РЕДАКТИРОВАНИЯ МАТРИЦЫ (АВТОСОХРАНЕНИЕ)
    // ============================================================
    if (matrixChangeHandler) {
        detailBody.removeEventListener('change', matrixChangeHandler);
    }

    matrixChangeHandler = async function(e) {
        const target = e.target;
        
        // 1. Обработка общего комментария к задаче
        if (target.classList.contains('matrix-general-comment')) {
            const taskId = parseInt(target.dataset.taskId);
            const dealId = parseInt(target.dataset.dealId);
            const commentText = target.value;

            try {
                target.disabled = true; // Блокируем на время запроса
                const resp = await fetch(`/api/sandbox/deals/${dealId}/tasks/${taskId}/comment`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ general_comment: commentText }),
                    credentials: 'include'
                });
                
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || 'Ошибка сохранения комментария');
                }
                showToast('✅ Комментарий сохранён', false);
            } catch (err) {
                showToast(`❌ ${err.message}`, true);
            } finally {
                target.disabled = false;
            }
            return; // Выходим, логика для товаров ниже
        }

        if (target.classList.contains('matrix-percent-input')) {
            const block = target.closest('.task-score-distribution');
            const totalPoints = Number(block.dataset.totalPoints || 0);
            const percentages = [...block.querySelectorAll('.matrix-percent-input')].map(input => ({
                employee_id: Number(input.dataset.employeeId),
                percent: Math.max(0, Math.min(100, parseInt(input.value) || 0))
            }));
            percentages.forEach(item => {
                const pointsCell = block.querySelector(`.matrix-employee-points[data-employee-id="${item.employee_id}"]`);
                if (pointsCell) pointsCell.textContent = Math.round(totalPoints * item.percent / 100);
            });
            const totalPercent = percentages.reduce((sum, item) => sum + item.percent, 0);
            const totalCell = block.querySelector('.matrix-total-percent');
            if (totalCell) {
                totalCell.textContent = `${totalPercent}%`;
                totalCell.style.color = totalPercent === 100 ? '#16a34a' : '#dc2626';
            }
            try {
                const response = await fetch(`/api/sandbox/task-assignments/${block.dataset.notificationId}/completion-percentages`, {
                    method:'PUT', credentials:'include', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({percentages})
                });
                if (!response.ok) throw new Error((await response.json()).detail || 'Ошибка сохранения процентов');
                showToast('Проценты и баллы обновлены');
            } catch (error) {
                showToast(error.message, true);
            }
            return;
        }

        // 2. Обработка ячеек матрицы (товары, брак, распределение)
        if (!target.matches('.matrix-defect-qty, .matrix-defect-comment, .matrix-dist-qty')) return;

        const row = target.closest('tr');
        if (!row) return;

        const productId = parseInt(row.dataset.productId);
        const expectedQty = row.dataset.expectedQty === '' ? null : parseInt(row.dataset.expectedQty);
        const taskId = parseInt(row.dataset.taskId);
        const dealId = parseInt(row.dataset.dealId);

        // 1. Собираем текущие значения строки
        const defectQty = parseInt(row.querySelector('.matrix-defect-qty').value) || 0;
        const defectComment = row.querySelector('.matrix-defect-comment').value;
        
        const distributions = [];
        let sumDist = 0;
        row.querySelectorAll('.matrix-dist-qty').forEach(inp => {
            const qty = parseInt(inp.value) || 0;
            sumDist += qty;
            distributions.push({
                employee_id: parseInt(inp.dataset.employeeId),
                quantity: qty
            });
        });

        // 2. Жесткая валидация: сумма распределений должна равняться количеству товара
        if (expectedQty !== null && sumDist !== expectedQty) {
            showToast(`❌ Ошибка: сумма распределений (${sumDist}) не равна количеству товара (${expectedQty})`, true);
            row.style.backgroundColor = '#fef2f2'; // Подсвечиваем строку красным
            return;
        } else {
            row.style.backgroundColor = ''; // Убираем подсветку, если всё верно
        }

        // 3. Формируем payload
        const payload = {
            product_type_id: productId,
            defect_quantity: defectQty,
            defect_comment: defectComment,
            distributions: distributions
        };

        // 4. Отправляем на бэкенд
        try {
            // Блокируем инпуты на время запроса, чтобы избежать гонок
            row.querySelectorAll('input').forEach(inp => inp.disabled = true);
            
            const resp = await fetch(`/api/sandbox/deals/${dealId}/tasks/${taskId}/products/${productId}/completion`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                credentials: 'include'
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Ошибка сохранения');
            }
            
            showToast(`✅ Данные по товару сохранены`, false);
        } catch (err) {
            showToast(`❌ ${err.message}`, true);
        } finally {
            row.querySelectorAll('input').forEach(inp => inp.disabled = false);
        }
    };

    detailBody.addEventListener('change', matrixChangeHandler);

    // ---- Закрытие модалки с сохранением ----
    if (closeDetailHandler) {
        closeDetail.removeEventListener('click', closeDetailHandler);
    }
    if (detailWindowClickHandler) {
        window.removeEventListener('click', detailWindowClickHandler);
    }

    closeDetailHandler = function(e) {
        e.preventDefault();
        saveAllFields();
        detailModal.style.display = 'none';
    };

    detailWindowClickHandler = function(e) {
        if (e.target === detailModal) {
            saveAllFields();
            detailModal.style.display = 'none';
        }
    };

    closeDetail.addEventListener('click', closeDetailHandler);
    window.addEventListener('click', detailWindowClickHandler);
    document.addEventListener('keydown', function escHandler(e) {
        if (e.key === 'Escape' && detailModal.style.display === 'block') {
            saveAllFields();
            detailModal.style.display = 'none';
            document.removeEventListener('keydown', escHandler);
        }
    });
}

// ---- Вспомогательные функции для работы с товарами и названием ----

// Обновление названия сделки
async function updateDealTitle(dealId, newTitle) {
    try {
        const resp = await fetch(`/api/sandbox/deals/${dealId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle }),
            credentials: 'include'
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Ошибка обновления названия');
        }
        showToast('Название сделки обновлено');
        viewDeal(dealId);
        loadDeals(); // обновить список сделок
    } catch (err) {
        showToast(err.message, true);
    }
}

// Удаление товара из сделки
async function deleteProductFromDeal(dealId, productId) {
    const resp = await fetch(`/api/sandbox/deals/${dealId}/products/${productId}`, {
        method: 'DELETE',
        credentials: 'include'
    });
    if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Ошибка удаления товара');
    }
}

// Добавление товара в сделку
async function addProductToDeal(dealId) {
    const select = document.getElementById('addProductSelect');
    const quantityInput = document.getElementById('addProductQuantity');
    const errorDiv = document.getElementById('addProductError');
    if (!select || !quantityInput) return;

    const productId = parseInt(select.value);
    const quantity = quantityInput.value.trim() === '' ? null : Number(quantityInput.value);
    if (!productId) {
        errorDiv.textContent = 'Выберите товар';
        return;
    }
    if (quantity !== null && (!Number.isInteger(quantity) || quantity < 0)) {
        errorDiv.textContent = 'Количество должно быть целым неотрицательным числом';
        return;
    }

    errorDiv.textContent = '';
    try {
        const resp = await fetch(`/api/sandbox/deals/${dealId}/products`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([{ product_id: productId, quantity: quantity }]),
            credentials: 'include'
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Ошибка добавления товара');
        }
        showToast('Товар добавлен в сделку');
        viewDeal(dealId);
        // Сбросить выбор
        select.value = '';
        quantityInput.value = '';
    } catch (err) {
        errorDiv.textContent = err.message;
    }
}

// Заполнение select доступными товарами (не входящими в сделку)
function populateAddProductSelect() {
    const select = document.getElementById('addProductSelect');
    if (!select) return;
    // Получаем список всех товаров (можно использовать глобальную переменную products из procsets)
    // Если products не загружены, загружаем их
    if (typeof products === 'undefined' || products.length === 0) {
        // Загружаем товары через apiFetch (если она доступна)
        fetch('/api/sandbox/product-types', { credentials: 'include' })
            .then(res => res.json())
            .then(data => {
                products = data;
                fillSelect(select);
            })
            .catch(err => {
                console.error('Не удалось загрузить товары:', err);
                showToast('Ошибка загрузки списка товаров', true);
            });
    } else {
        fillSelect(select);
    }
}

function fillSelect(select) {
    const currentProductIds = Array.from(document.querySelectorAll('#deal-products-table tbody tr'))
        .map(tr => parseInt(tr.dataset.productId));
    select.innerHTML = '<option value="">-- Выберите товар --</option>';
    products.forEach(p => {
        if (!currentProductIds.includes(p.id)) {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.full_name || p.name;
            select.appendChild(opt);
        }
    });
}
// ---- Включение редактирования по клику ----
function enableInlineEditing(dealId) {
    // ---- Товары: количество (без изменений) ----
    document.querySelectorAll('.product-quantity-display').forEach(span => {
        span.style.cursor = 'pointer';
        span.addEventListener('click', function(e) {
            e.stopPropagation();
            const td = this.closest('td');
            const input = td.querySelector('.product-quantity-input');
            if (!input) return;
            this.style.display = 'none';
            input.style.display = 'inline';
            input.focus();
            input.select();
        });
        const input = span.closest('td').querySelector('.product-quantity-input');
        if (input) {
            input.addEventListener('blur', function() {
                saveProductQuantity(this, dealId);
            });
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
                if (e.key === 'Escape') { this.value = this.defaultValue; this.blur(); }
            });
        }
    });

    // ---- Задачи: статус (исправлено для аккордеона) ----
    document.querySelectorAll('.task-status-display').forEach(span => {
        span.style.cursor = 'pointer';
        const container = span.closest('.task-accordion-item');
        const notificationId = span.dataset.notificationId;
        const taskId = container ? container.dataset.taskId : null;

        span.addEventListener('click', function(e) {
            e.stopPropagation();
            const td = this.closest('div'); // родительский div с сеткой
            const select = td.querySelector('.task-status-select');
            if (!select) return;
            this.style.display = 'none';
            select.style.display = 'inline';
            select.focus();
        });

        const select = span.closest('div').querySelector('.task-status-select');
        if (select) {
            select.addEventListener('change', function() {
                // Находим контейнер задачи по ближайшему .task-accordion-item
                const container = this.closest('.task-accordion-item');
                const taskId = container ? container.dataset.taskId : null;
                saveTaskStatus(this, dealId, notificationId, taskId);
            });
            select.addEventListener('blur', function() {
                const span = this.closest('div').querySelector('.task-status-display');
                if (span) {
                    const selectedOption = this.options[this.selectedIndex];
                    span.textContent = selectedOption.textContent;
                    span.style.display = 'inline';
                    this.style.display = 'none';
                }
            });
        }
    });

    // ---- Время начала (исправлено для аккордеона) ----
    document.querySelectorAll('.task-started-display').forEach(span => {
        span.style.cursor = 'pointer';
        const container = span.closest('.task-accordion-item');
        const notificationId = span.dataset.notificationId;
        const taskId = container ? container.dataset.taskId : null;

        span.addEventListener('click', function(e) {
            e.stopPropagation();
            const td = this.closest('div');
            const input = td.querySelector('.task-started-input');
            if (!input) return;
            this.style.display = 'none';
            input.style.display = 'inline';
            input.focus();
            input.select();
        });
        const input = span.closest('div').querySelector('.task-started-input');
        if (input) {
            input.addEventListener('blur', function() {
                saveTaskTime(this, dealId, 'started_at', notificationId, taskId);
            });
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
                if (e.key === 'Escape') { this.value = this.defaultValue; this.blur(); }
            });
        }
    });

    // ---- Время завершения (исправлено для аккордеона) ----
    document.querySelectorAll('.task-completed-display').forEach(span => {
        span.style.cursor = 'pointer';
        const container = span.closest('.task-accordion-item');
        const notificationId = span.dataset.notificationId;
        const taskId = container ? container.dataset.taskId : null;

        span.addEventListener('click', function(e) {
            e.stopPropagation();
            const td = this.closest('div');
            const input = td.querySelector('.task-completed-input');
            if (!input) return;
            this.style.display = 'none';
            input.style.display = 'inline';
            input.focus();
            input.select();
        });
        const input = span.closest('div').querySelector('.task-completed-input');
        if (input) {
            input.addEventListener('blur', function() {
                saveTaskTime(this, dealId, 'completed_at', notificationId, taskId);
            });
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
                if (e.key === 'Escape') { this.value = this.defaultValue; this.blur(); }
            });
        }
    });
}

async function saveTaskEmployee(select, dealId) {
    const row = select.closest('tr');
    const taskId = parseInt(row.dataset.taskId);
    const employeeId = parseInt(select.value);
    if (isNaN(taskId) || isNaN(employeeId)) return;
    try {
        await apiFetch(`/api/sandbox/deals/${dealId}/tasks/${taskId}/assignee`, {
            method: 'PUT',
            body: JSON.stringify({ employee_id: employeeId })
        });
        showToast('Исполнитель обновлён');
    } catch (err) {
        showToast('Ошибка: ' + err.message, true);
        const span = select.closest('td').querySelector('.task-employee-display');
        const originalEmployee = span.textContent;
        for (let opt of select.options) {
            if (opt.textContent === originalEmployee) {
                select.value = opt.value;
                break;
            }
        }
        span.style.display = 'inline';
        select.style.display = 'none';
    }
}

async function saveTaskStatus(select, dealId, notificationId = null, taskId = null) {
    const status = select.value;
    if (!notificationId) {
        // Если не передан notificationId, пробуем найти его по data-атрибуту
        const container = select.closest('.task-accordion-item');
        if (container) {
            const notifSpan = container.querySelector('.task-status-display');
            if (notifSpan) notificationId = notifSpan.dataset.notificationId;
        }
        if (!notificationId) {
            showToast('Не удалось определить уведомление', true);
            return;
        }
    }
    if (!taskId) {
        const container = select.closest('.task-accordion-item');
        if (container) taskId = container.dataset.taskId;
        if (!taskId) {
            showToast('Не удалось определить задачу', true);
            return;
        }
    }
    try {
        const payload = { status: status };
        if (notificationId) payload.notification_id = parseInt(notificationId);
        await apiFetch(`/api/sandbox/deals/${dealId}/tasks/${taskId}/status`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
        const statusDisplayMap = {
            'not_started': '❌ Не начата',
            'in_progress': '🔄 В процессе',
            'on_break': '⏸️ В перерыве',
            'completed': '✅ Завершена'
        };
        const statusColorMap = {
            'not_started': '#64748b',
            'in_progress': '#f59e0b',
            'on_break': '#8b5cf6',
            'completed': '#22c55e'
        };
        const container = select.closest('.task-accordion-item');
        container.querySelectorAll('.task-status-display').forEach(statusSpan => {
            statusSpan.textContent = statusDisplayMap[status] || status;
            statusSpan.style.display = 'inline';
            if (statusSpan.classList.contains('task-status-header-display')) {
                statusSpan.style.color = statusColorMap[status] || '#64748b';
            }
        });
        container.querySelectorAll('.task-status-select').forEach(statusSelect => {
            statusSelect.value = status;
            statusSelect.dataset.savedValue = status;
            statusSelect.style.display = 'none';
        });
        showToast('Статус обновлён');
    } catch (err) {
        showToast('Ошибка: ' + err.message, true);
        select.value = select.dataset.savedValue || 'not_started';
        const span = select.parentElement.querySelector('.task-status-display');
        if (span) span.style.display = 'inline';
        select.style.display = 'none';
    }
}

async function saveTaskTime(input, dealId, field, notificationId = null, taskId = null) {
    const value = input.value;
    if (!notificationId) {
        const container = input.closest('.task-accordion-item');
        if (container) {
            const displaySpan = container.querySelector(`.task-${field === 'started_at' ? 'started' : 'completed'}-display`);
            if (displaySpan) notificationId = displaySpan.dataset.notificationId;
        }
        if (!notificationId) {
            showToast('Не удалось определить уведомление', true);
            return;
        }
    }
    if (!taskId) {
        const container = input.closest('.task-accordion-item');
        if (container) taskId = container.dataset.taskId;
        if (!taskId) {
            showToast('Не удалось определить задачу', true);
            return;
        }
    }
    const payload = {};
    payload[field] = value || null;
    if (notificationId) payload.notification_id = parseInt(notificationId);
    try {
        await apiFetch(`/api/sandbox/deals/${dealId}/tasks/${taskId}/time`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
        const span = input.closest('div').querySelector(`.task-${field === 'started_at' ? 'started' : 'completed'}-display`);
        if (value) {
            span.textContent = new Date(value).toLocaleString();
        } else {
            span.textContent = '—';
        }
        span.style.display = 'inline';
        input.style.display = 'none';
        showToast('Время обновлено');
    } catch (err) {
        showToast('Ошибка: ' + err.message, true);
        const span = input.closest('div').querySelector(`.task-${field === 'started_at' ? 'started' : 'completed'}-display`);
        input.value = span.textContent === '—' ? '' : new Date(span.textContent).toISOString().slice(0,16);
        span.style.display = 'inline';
        input.style.display = 'none';
    }
}

    async function deleteDeal(dealId) {
        if (!confirm('Удалить эту сделку?')) return;
        try {
            await apiFetch(`/api/sandbox/deals/${dealId}`, { method: 'DELETE' });
            showToast('Сделка удалена');
            loadDeals();
        } catch (err) {
            showToast(err.message, true);
        }
    }

    // ---- Открытие модалки создания ----
    async function openCreateModal() {
        // Сбросить любые глобальные переменные, связанные с редактированием сделки
        // (если у вас есть переменная currentDealId – обнулите её)
        if (typeof currentDealId !== 'undefined') currentDealId = null;

        // Загружаем типы сделок, если их ещё нет
        if (dealTypes.length === 0) {
            await loadDealTypes();
        }

        // Показываем модальное окно
        modalCreate.style.display = 'block';
        const titleInput = container.querySelector('#dealTitle');
        titleInput.value = '';
        createError.textContent = '';
        populateDealTypeSelect();

        // Сбрасываем импортированные товары
        importedProducts = [];
        importPreviewBody.innerHTML = '';
        importPreviewContainer.style.display = 'none';
        clearImportBtn.style.display = 'none';
        importStatus.textContent = '';

        try {
            // Загружаем списки ИП и МП
            const [ipsResp, mpsResp] = await Promise.all([
                apiFetch('/api/sandbox/ips'),
                apiFetch('/api/sandbox/mps')
            ]);
            const ips = await ipsResp.json();
            const mps = await mpsResp.json();

            const ipSelect = container.querySelector('#dealIp');
            ipSelect.innerHTML = '<option value="">ИП</option>' + 
                ips.map(ip => `<option value="${ip.id}">${escapeHtml(ip.name)}</option>`).join('');

            const mpSelect = container.querySelector('#dealMp');
            mpSelect.innerHTML = '<option value="">МП</option>' + 
                mps.map(mp => `<option value="${mp.id}">${escapeHtml(mp.name)}</option>`).join('');

            const typeSelect = container.querySelector('#dealType');

            // Удаляем старые обработчики, чтобы не было конфликтов
            typeSelect.removeEventListener('change', onParametersChanged);
            ipSelect.removeEventListener('change', onParametersChanged);
            mpSelect.removeEventListener('change', onParametersChanged);

            // ---- ЛОКАЛЬНАЯ ФУНКЦИЯ ОБНОВЛЕНИЯ UI (БЕЗ API) ----
            const updateCreateUI = () => {
                const typeId = parseInt(typeSelect.value);
                const typeObj = dealTypes.find(t => t.id === typeId);
                const typeName = typeObj ? typeObj.name : '';

                // Генерация названия сделки
                const now = new Date();
                const year = String(now.getFullYear()).slice(2);
                const month = String(now.getMonth() + 1).padStart(2, '0');
                const day = String(now.getDate()).padStart(2, '0');
                const dateStr = year + month + day;

                let title = '';
                if (typeName === 'FBS' || typeName === 'FSK') {
                    title = dateStr + '_' + typeName;
                } else if (typeName === 'FBO') {
                    const ipText = ipSelect.options[ipSelect.selectedIndex]?.text || '';
                    const mpText = mpSelect.options[mpSelect.selectedIndex]?.text || '';
                    if (ipText && mpText) {
                        title = dateStr + '_' + ipText + '_' + mpText;
                    }
                }
                titleInput.value = title;

                // ---- Обновление пути импорта (локально) ----
                const importPathInput = container.querySelector('#importPathInput');
                if (importPathInput) {
                    const basePath = "W:\\!МП_(FSk)";
                    let path = '';
                    if (typeName === 'FBS') {
                        path = basePath + '\\!FBS\\' + dateStr + '_FBS\\Книга1.xlsx';
                    } else if (typeName === 'FSK') {
                        path = basePath + '\\' + dateStr + '_FSk\\b24.xlsx';
                    } else if (typeName === 'FBO') {
                        const ipText = ipSelect.options[ipSelect.selectedIndex]?.text || '';
                        const mpText = mpSelect.options[mpSelect.selectedIndex]?.text || '';
                        if (ipText && mpText) {
                            path = basePath + '\\' + dateStr + '_' + ipText + '_' + mpText + '\\b24.xlsx';
                        }
                    }
                    importPathInput.value = path;
                }

                // ---- Показать/скрыть поля ИП и МП ----
                const ipGroup = ipSelect?.closest('.form-group');
                const mpGroup = mpSelect?.closest('.form-group');
                if (ipGroup && mpGroup) {
                    if (typeName === 'FBS' || typeName === 'FSK') {
                        ipGroup.style.display = 'none';
                        mpGroup.style.display = 'none';
                        ipSelect.removeAttribute('required');
                        mpSelect.removeAttribute('required');
                        ipSelect.value = '';
                        mpSelect.value = '';
                    } else {
                        ipGroup.style.display = '';
                        mpGroup.style.display = '';
                        ipSelect.setAttribute('required', 'required');
                        mpSelect.setAttribute('required', 'required');
                    }
                }
            };

            // Назначаем новые обработчики (только для UI)
            typeSelect.addEventListener('change', updateCreateUI);
            ipSelect.addEventListener('change', updateCreateUI);
            mpSelect.addEventListener('change', updateCreateUI);

            // Инициализируем UI при открытии
            updateCreateUI();

        } catch (err) {
            showToast('Не удалось загрузить ИП/МП', true);
        }
    }

    function closeCreateModal() {
        modalCreate.style.display = 'none';
        importedProducts = [];
        importPreviewBody.innerHTML = '';
        importPreviewContainer.style.display = 'none';
        clearImportBtn.style.display = 'none';
        importStatus.textContent = '';
    }

    // ---- Загрузка ИП и МП (для вкладки контрагентов) ----
    async function loadIPs() {
        try {
            const resp = await apiFetch('/api/sandbox/ips');
            ips = await resp.json();
            renderList('ipsList', ips);
        } catch (err) {
            showToast('Ошибка загрузки ИП: ' + err.message, true);
        }
    }

    async function loadMPs() {
        try {
            const resp = await apiFetch('/api/sandbox/mps');
            mps = await resp.json();
            renderList('mpsList', mps);
        } catch (err) {
            showToast('Ошибка загрузки МП: ' + err.message, true);
        }
    }

    function renderList(elementId, items) {
        const containerEl = document.getElementById(elementId);
        if (!containerEl) return;
        if (!items || items.length === 0) {
            showMessage(containerEl, 'Нет записей');
            return;
        }
        const table = createElement('table');
        const header = createElement('tr', {}, [
            createElement('th', { text: 'Название' }),
            createElement('th', { text: 'Действия' })
        ]);
        table.append(createElement('thead', {}, header));
        const tbody = createElement('tbody');
        for (const item of items) {
            tbody.append(createElement('tr', {}, [
                createElement('td', {}, createElement('strong', { text: item.name })),
                createElement('td', {}, createElement('button', {
                    className: 'delete-item icon-delete-button',
                    text: '🗑️',
                    attrs: { type: 'button' },
                    dataset: { id: item.id, list: elementId }
                }))
            ]));
        }
        table.append(tbody);
        containerEl.replaceChildren(table);

        containerEl.querySelectorAll('.delete-item').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = parseInt(btn.dataset.id);
                const listType = btn.dataset.list;
                if (!confirm('Удалить?')) return;
                try {
                    let url = '';
                    if (listType === 'ipsList') url = `/api/sandbox/ips/${id}`;
                    else if (listType === 'mpsList') url = `/api/sandbox/mps/${id}`;
                    else if (listType === 'dealTypesList') url = `/api/sandbox/deal-types/${id}`;
                    if (url) {
                        await apiFetch(url, { method: 'DELETE' });
                        showToast('Удалено');
                        if (listType === 'ipsList') loadIPs();
                        else if (listType === 'mpsList') loadMPs();
                        else if (listType === 'dealTypesList') loadDealTypes();
                    }
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
    }

    // ---- Инициализация обработчиков контрагентов ----
    function initCounterpartiesHandlers() {
        const saveDealTypeBtn = document.getElementById('saveDealTypeBtn');
        if (saveDealTypeBtn) {
            saveDealTypeBtn.addEventListener('click', async () => {
                const nameInput = document.getElementById('newDealTypeName');
                const name = nameInput?.value.trim();
                if (!name) return showToast('Введите название', true);
                try {
                    await apiFetch('/api/sandbox/deal-types', { method: 'POST', body: JSON.stringify({ name }) });
                    showToast('Тип сделки добавлен');
                    if (nameInput) nameInput.value = '';
                    loadDealTypes();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        }
        const saveIPBtn = document.getElementById('saveIPBtn');
        if (saveIPBtn) {
            saveIPBtn.addEventListener('click', async () => {
                const nameInput = document.getElementById('newIPName');
                const name = nameInput?.value.trim();
                if (!name) return showToast('Введите название', true);
                try {
                    await apiFetch('/api/sandbox/ips', { method: 'POST', body: JSON.stringify({ name }) });
                    showToast('ИП добавлен');
                    if (nameInput) nameInput.value = '';
                    loadIPs();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        }
        const saveMPBtn = document.getElementById('saveMPBtn');
        if (saveMPBtn) {
            saveMPBtn.addEventListener('click', async () => {
                const nameInput = document.getElementById('newMPName');
                const name = nameInput?.value.trim();
                if (!name) return showToast('Введите название', true);
                try {
                    await apiFetch('/api/sandbox/mps', { method: 'POST', body: JSON.stringify({ name }) });
                    showToast('МП добавлен');
                    if (nameInput) nameInput.value = '';
                    loadMPs();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        }
        const refreshBtn = document.getElementById('refreshCounterpartiesBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                loadDealTypes();
                loadIPs();
                loadMPs();
            });
        }
    }

    // ---- Импорт товаров: обработчики (автоматический) ----
    if (importBtn) {
        importBtn.addEventListener('click', async function() {
            const path = importPathInput ? importPathInput.value.trim() : '';
            if (!path) {
                showToast('Путь не указан. Сгенерируйте его автоматически или введите вручную.', true);
                return;
            }

            importStatus.textContent = 'Загрузка...';
            try {
                const resp = await fetch('/api/sandbox/import/by-path', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: path }),
                    credentials: 'include'
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || 'Ошибка импорта');
                }
                const data = await resp.json();
                importedProducts = data.products;
                renderImportPreview(importedProducts);
                importStatus.textContent = `Загружено ${importedProducts.length} товаров`;
                clearImportBtn.style.display = 'inline-block';
                importPreviewContainer.style.display = 'block';
            } catch (err) {
                showToast(err.message, true);
                importStatus.textContent = 'Ошибка загрузки';
            }
        });
    }

    // ---- Ручное добавление товара (всегда доступно) ----
    const manualAddBtn = container.querySelector('#manualAddBtn');
    const manualAddForm = container.querySelector('#manualAddForm');
    const manualProductSelect = container.querySelector('#manualProductSelect');
    const manualProductQuantity = container.querySelector('#manualProductQuantity');
    const manualAddConfirmBtn = container.querySelector('#manualAddConfirmBtn');
    const manualAddCancelBtn = container.querySelector('#manualAddCancelBtn');

    // Загрузка списка товаров для select
    async function loadManualProductSelect() {
        if (!manualProductSelect) return;
        try {
            const resp = await apiFetch('/api/sandbox/product-types');
            const products = await resp.json();
            manualProductSelect.innerHTML = '<option value="">-- Выберите товар --</option>';
            products.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.full_name || p.name;
                opt.dataset.name = p.name;
                opt.dataset.fullName = p.full_name || p.name;
                manualProductSelect.appendChild(opt);
            });
        } catch (err) {
            console.error('Ошибка загрузки списка товаров:', err);
            showToast('Не удалось загрузить список товаров', true);
        }
    }

    // Скрываем кнопку "Добавить вручную" и показываем форму всегда
    if (manualAddForm) {
        manualAddForm.style.display = 'flex';
    }

    // Загружаем список товаров при инициализации
    loadManualProductSelect();

    // Обработчик отмены – очищает поля, форма остаётся видимой
    if (manualAddCancelBtn) {
        manualAddCancelBtn.addEventListener('click', function() {
            if (manualProductSelect) manualProductSelect.selectedIndex = 0;
            if (manualProductQuantity) manualProductQuantity.value = '';
        });
    }

    // Обработчик добавления товара
    if (manualAddConfirmBtn) {
        manualAddConfirmBtn.addEventListener('click', function() {
            const select = manualProductSelect;
            const selectedOption = select.options[select.selectedIndex];
            if (!selectedOption || !selectedOption.value) {
                showToast('Выберите товар из списка', true);
                return;
            }
            const rawQuantity = manualProductQuantity.value.trim();
            const quantity = rawQuantity === '' ? null : Number(rawQuantity);
            if (quantity !== null && (!Number.isInteger(quantity) || quantity < 0)) {
                showToast('Количество должно быть целым неотрицательным числом', true);
                return;
            }
            const name = selectedOption.dataset.name;
            const fullName = selectedOption.dataset.fullName;
            importedProducts.push({
                name: name,
                full_name: fullName,
                quantity: quantity
            });
            renderImportPreview(importedProducts);
            importStatus.textContent = `Загружено ${importedProducts.length} товаров`;
            clearImportBtn.style.display = 'inline-block';
            importPreviewContainer.style.display = 'block';
            // Очищаем поля, но не скрываем форму
            if (manualProductSelect) manualProductSelect.selectedIndex = 0;
            if (manualProductQuantity) manualProductQuantity.value = '';
            showToast(`✅ Товар "${name}" добавлен`);
        });

        // Enter в поле количества
        if (manualProductQuantity) {
            manualProductQuantity.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    manualAddConfirmBtn.click();
                }
            });
        }
    }

    if (resetPathBtn) {
        resetPathBtn.addEventListener('click', function() {
            updateImportPath();
            showToast('Путь обновлён по текущим параметрам');
        });
    }

    if (clearImportBtn) {
        clearImportBtn.addEventListener('click', function() {
            importedProducts = [];
            importPreviewBody.innerHTML = '';
            importPreviewContainer.style.display = 'none';
            this.style.display = 'none';
            importStatus.textContent = '';
        });
    }

    function renderImportPreview(products) {
        importPreviewBody.innerHTML = '';
        products.forEach((p, index) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${escapeHtml(p.name)}</td>
                <td>${escapeHtml(p.full_name || '')}</td>
                <td>
                    <input type="number" class="quantity-input import-quantity-input" value="${p.quantity ?? ''}" data-index="${index}" min="0">
                </td>
                <td><button class="btn-sm btn-danger remove-import-item" data-index="${index}">✖</button></td>
            `;
            importPreviewBody.appendChild(tr);
        });

        // Обработчики изменения количества
        importPreviewBody.querySelectorAll('.quantity-input').forEach(input => {
            input.addEventListener('change', function() {
                const idx = parseInt(this.dataset.index, 10);
                const rawValue = this.value.trim();
                let val = rawValue === '' ? null : Number(rawValue);
                if (val !== null && (!Number.isInteger(val) || val < 0)) {
                    val = null;
                    this.value = '';
                }
                importedProducts[idx].quantity = val;
                updateImportStatus();
            });
        });

        // Обработчики удаления (уже были, но переопределим)
        importPreviewBody.querySelectorAll('.remove-import-item').forEach(btn => {
            btn.addEventListener('click', function() {
                const idx = parseInt(this.dataset.index, 10);
                importedProducts.splice(idx, 1);
                renderImportPreview(importedProducts);
                if (importedProducts.length === 0) {
                    clearImportBtn.style.display = 'none';
                    importPreviewContainer.style.display = 'none';
                    importStatus.textContent = '';
                } else {
                    updateImportStatus();
                }
            });
        });
    }

    function updateImportStatus() {
        importStatus.textContent = `Загружено ${importedProducts.length} товаров`;
    }

    // ---- Обработчик создания сделки ----
    if (createForm) {
        createForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const title = container.querySelector('#dealTitle').value.trim();
            const dealTypeId = parseInt(container.querySelector('#dealType').value);
            const ipSelect = container.querySelector('#dealIp');
            const mpSelect = container.querySelector('#dealMp');
            const ipId = ipSelect ? parseInt(ipSelect.value) || null : null;
            const mpId = mpSelect ? parseInt(mpSelect.value) || null : null;

            if (!title || !dealTypeId) {
                createError.textContent = 'Заполните все поля';
                return;
            }

            const payload = {
                title: title,
                deal_type_id: dealTypeId,
                ip_id: ipId,
                mp_id: mpId,
                products: importedProducts
            };

            try {
                const resp = await apiFetch('/api/sandbox/deals', {
                    method: 'POST',
                    body: JSON.stringify(payload)
                });
                const data = await resp.json();
                showToast(`Сделка создана, ID: ${data.id}`);
                closeCreateModal();
                loadDeals();
                importedProducts = [];
                importPreviewBody.innerHTML = '';
                importPreviewContainer.style.display = 'none';
                clearImportBtn.style.display = 'none';
                importStatus.textContent = '';
                container.querySelector('#dealTitle').value = '';
                container.querySelector('#dealType').selectedIndex = 0;
                if (ipSelect) ipSelect.selectedIndex = 0;
                if (mpSelect) mpSelect.selectedIndex = 0;
            } catch (err) {
                createError.textContent = err.message;
                showToast(err.message, true);
            }
        });
    }

    // ================================================
    //   ВКЛАДКА «ТОВАРЫ»
    // ================================================

    async function loadProducts() {
        try {
            const resp = await apiFetch('/api/sandbox/product-types');
            products = await resp.json();
            const techResp = await apiFetch('/api/sandbox/tech-cards');
            techCards = await techResp.json();
            renderProductsGrouped();
        } catch (err) {
            showToast('Ошибка загрузки товаров: ' + err.message, true);
        }
    }

    function renderProductsGrouped() {
        const containerEl = document.getElementById('productsList');
        if (!containerEl) return;
        if (!products.length) {
            showMessage(containerEl, 'Нет товаров. Создайте товары в справочнике.');
            return;
        }
        const groups = groupProductsByTechCard(products, techCards);
        if (groups.length === 0) {
            showMessage(containerEl, 'Нет товаров с техкартами.');
            return;
        }
        const groupsContainer = createElement('div', { className: 'product-groups-container' });
        for (const group of groups) {
            const isNoTech = group.tech_card === null;
            const groupActions = createElement('span', { className: 'product-group-actions' });
            groupActions.append(createElement('button', {
                className: 'add-product-btn', text: '➕', attrs: { type: 'button', title: 'Добавить товар' },
                dataset: { techId: isNoTech ? '' : group.tech_card.id }
            }));
            if (!isNoTech) {
                groupActions.append(
                    createElement('button', {
                        className: 'edit-techcard-btn', text: '✏️', attrs: { type: 'button', title: 'Редактировать техкарту' },
                        dataset: { id: group.tech_card.id }
                    }),
                    createElement('button', {
                        className: 'delete-techcard-btn', text: '🗑️', attrs: { type: 'button', title: 'Удалить техкарту' },
                        dataset: { id: group.tech_card.id }
                    })
                );
            }
            const groupBody = createElement('div', { className: 'product-group-body' });
            for (const product of group.products) {
                const productInfo = createElement('div', { className: 'product-info' }, createElement('span', { className: 'product-name', text: product.name }));
                if (product.full_name) productInfo.append(createElement('span', { className: 'product-fullname', text: product.full_name }));
                const productActions = createElement('span', { className: 'product-actions' }, [
                    createElement('button', {
                        className: 'edit-product-btn', text: '✏️', attrs: { type: 'button', title: 'Редактировать' }, dataset: { id: product.id }
                    }),
                    createElement('button', {
                        className: 'delete-product-btn', text: '🗑️', attrs: { type: 'button', title: 'Удалить' }, dataset: { id: product.id }
                    })
                ]);
                groupBody.append(createElement('div', { className: 'product-item', dataset: { id: product.id } }, [productInfo, productActions]));
            }
            groupsContainer.append(createElement('div', {
                className: 'product-group', dataset: { groupId: isNoTech ? 'no_tech' : group.tech_card.id }
            }, [
                createElement('div', { className: 'product-group-header' }, [
                    createElement('span', { className: 'product-group-title', text: isNoTech ? '📦 Без техкарты' : group.tech_card.name }),
                    groupActions
                ]),
                groupBody
            ]));
        }
        containerEl.replaceChildren(groupsContainer);

        containerEl.querySelectorAll('.add-product-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const techCardId = this.dataset.techId ? parseInt(this.dataset.techId) : null;
                openProductModal(null, techCardId);
            });
        });
        containerEl.querySelectorAll('.edit-product-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const productId = parseInt(this.dataset.id);
                const product = products.find(p => p.id === productId);
                if (product) openProductModal(product);
            });
        });
        containerEl.querySelectorAll('.delete-product-btn').forEach(btn => {
            btn.addEventListener('click', async function() {
                const productId = parseInt(this.dataset.id);
                if (!confirm('Удалить товар?')) return;
                try {
                    await apiFetch(`/api/sandbox/product-types/${productId}`, { method: 'DELETE' });
                    showToast('Товар удалён');
                    loadProducts();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
        containerEl.querySelectorAll('.edit-techcard-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const techCardId = parseInt(this.dataset.id);
                document.querySelector('.sandbox-sidebar .nav-btn[data-target="tasks"]').click();
                setTimeout(() => {
                    if (techCardSelect) {
                        techCardSelect.value = techCardId;
                        techCardSelect.dispatchEvent(new Event('change'));
                    }
                }, 300);
            });
        });
        containerEl.querySelectorAll('.delete-techcard-btn').forEach(btn => {
            btn.addEventListener('click', async function() {
                const techCardId = parseInt(this.dataset.id);
                if (!confirm('Удалить техкарту? Все товары, привязанные к ней, потеряют техкарту.')) return;
                try {
                    await apiFetch(`/api/sandbox/tech-cards/${techCardId}`, { method: 'DELETE' });
                    showToast('Техкарта удалена');
                    loadProducts();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
    }

    function groupProductsByTechCard(products, techCards) {
        const groups = {};
        techCards.forEach(tc => { groups[tc.id] = { tech_card: tc, products: [] }; });
        groups['no_tech'] = { tech_card: null, products: [] };
        products.forEach(p => {
            if (p.tech_card_id && groups[p.tech_card_id]) {
                groups[p.tech_card_id].products.push(p);
            } else {
                groups['no_tech'].products.push(p);
            }
        });
        const sorted = Object.values(groups);
        sorted.sort((a, b) => {
            if (a.tech_card === null) return 1;
            if (b.tech_card === null) return -1;
            return a.tech_card.name.localeCompare(b.tech_card.name);
        });
        return sorted;
    }

    // Модальное окно товаров
    const productModal = document.getElementById('productModal');
    const productForm = document.getElementById('productForm');
    const productNameInput = document.getElementById('productNameInput');
    const productFullNameInput = document.getElementById('productFullNameInput');
    const productTechCardSelect = document.getElementById('productTechCardSelect');
    const productModalTitle = document.getElementById('productModalTitle');
    const productFormError = document.getElementById('productFormError');
    const closeProductModalBtn = document.querySelector('.close-product-modal');
    const cancelProductBtn = document.getElementById('cancelProductBtn');
    let editingProductId = null;

    function openProductModal(product = null, defaultTechCardId = null) {
        editingProductId = product ? product.id : null;
        productFormError.textContent = '';
        productNameInput.value = product ? product.name : '';
        productFullNameInput.value = product ? (product.full_name || '') : '';
        populateProductTechCardSelect(product ? product.tech_card_id : defaultTechCardId);
        productModalTitle.textContent = product ? 'Редактирование товара' : 'Создание товара';
        productModal.style.display = 'block';
    }

    function closeProductModal() {
        productModal.style.display = 'none';
        editingProductId = null;
    }

    function populateProductTechCardSelect(selectedId) {
        const select = productTechCardSelect;
        select.innerHTML = '<option value="">Без техкарты</option>';
        techCards.forEach(tc => {
            const opt = document.createElement('option');
            opt.value = tc.id;
            opt.textContent = tc.name;
            if (tc.id === selectedId) opt.selected = true;
            select.appendChild(opt);
        });
    }

    if (productForm) {
        productForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const name = productNameInput.value.trim();
            if (!name) {
                productFormError.textContent = 'Название обязательно';
                return;
            }
            const fullName = productFullNameInput.value.trim() || null;
            const techCardId = parseInt(productTechCardSelect.value) || null;
            const payload = { name, full_name: fullName, tech_card_id: techCardId };
            const method = editingProductId ? 'PUT' : 'POST';
            const url = editingProductId ? `/api/sandbox/product-types/${editingProductId}` : '/api/sandbox/product-types';
            try {
                const resp = await apiFetch(url, { method, body: JSON.stringify(payload) });
                const data = await resp.json();
                showToast(`Товар "${data.name}" ${editingProductId ? 'обновлён' : 'создан'}`);
                closeProductModal();
                loadProducts();
            } catch (err) {
                productFormError.textContent = err.message;
            }
        });
    }

    if (closeProductModalBtn) closeProductModalBtn.addEventListener('click', closeProductModal);
    if (cancelProductBtn) cancelProductBtn.addEventListener('click', closeProductModal);
    window.addEventListener('click', function(e) {
        if (e.target === productModal) closeProductModal();
    });

    // ================================================
    //   ВКЛАДКА «ЗАДАЧИ» (конструктор, типы, задачи)
    // ================================================

    async function loadTaskTypes() {
        try {
            const resp = await apiFetch('/api/sandbox/task-types');
            taskTypes = await resp.json();
            renderTaskTypes();
            renderTasksGrouped();
        } catch (err) {
            showToast('Ошибка загрузки типов задач: ' + err.message, true);
        }
    }

    async function loadTasks() {
        try {
            const resp = await apiFetch('/api/sandbox/tasks');
            allTasks = await resp.json();
            renderTasksGrouped();
        } catch (err) {
            showToast('Ошибка загрузки задач: ' + err.message, true);
        }
    }

    function renderTaskTypes() {
        const container = document.getElementById('taskTypeList');
        if (!container) return;
        if (!taskTypes || taskTypes.length === 0) {
            showMessage(container, 'Нет типов задач');
            return;
        }
        container.replaceChildren(...taskTypes.map(taskType => createElement('span', { className: 'task-type-item' }, [
            document.createTextNode(`${taskType.name} `),
            createElement('span', {
                className: 'remove-type', text: '✖', attrs: { role: 'button', tabindex: '0', 'aria-label': `Удалить тип ${taskType.name}` }, dataset: { id: taskType.id }
            })
        ])));
        container.querySelectorAll('.remove-type').forEach(el => {
            el.addEventListener('click', async () => {
                const id = parseInt(el.dataset.id);
                if (!confirm('Удалить тип задачи?')) return;
                try {
                    await apiFetch(`/api/sandbox/task-types/${id}`, { method: 'DELETE' });
                    showToast('Тип удалён');
                    await loadTaskTypes();
                    await loadTasks();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
    }

    function groupTasksByType(tasks, types) {
        const groups = {};
        types.forEach(t => { groups[t.id] = { type: t, tasks: [] }; });
        groups['other'] = { type: { id: 'other', name: 'Без типа' }, tasks: [] };
        tasks.forEach(task => {
            if (task.task_type_id && groups[task.task_type_id]) {
                groups[task.task_type_id].tasks.push(task);
            } else {
                groups['other'].tasks.push(task);
            }
        });
        return Object.values(groups).sort((a, b) => a.type.name.localeCompare(b.type.name));
    }

    function renderTasksGrouped() {
        const leftPanel = document.getElementById('tasksLeftPanel');
        if (!leftPanel) return;
        if (!allTasks.length && !taskTypes.length) {
            showMessage(leftPanel, 'Нет задач. Создайте типы и задачи.');
            return;
        }
        let groups = groupTasksByType(allTasks, taskTypes);
        groups = groups.filter(g => g.type.id !== 'other');
        if (groups.length === 0) {
            showMessage(leftPanel, 'Нет задач с типами. Создайте типы и задачи.');
            return;
        }

        const taskToRoles = {};
        roles.forEach(role => {
            role.tasks.forEach(task => {
                if (!taskToRoles[task.id]) taskToRoles[task.id] = [];
                taskToRoles[task.id].push(role);
            });
        });

        const groupsContainer = createElement('div', { className: 'task-groups-container' });
        groups.forEach(group => {
            const typeId = group.type.id;
            const groupBody = createElement('div', { className: 'task-group-body' });
            group.tasks.forEach(task => {
                const taskInfo = createElement('div', { className: 'task-info' }, createElement('span', { className: 'task-name', text: task.name }));
                const assignedRoles = taskToRoles[task.id] || [];
                if (assignedRoles.length) {
                    const roleList = createElement('div', { className: 'task-roles' });
                    assignedRoles.forEach(role => roleList.append(createElement('span', { className: 'role-tag' }, [
                        document.createTextNode(role.name),
                        createElement('button', {
                            className: 'remove-task-from-role', text: '✖', attrs: { type: 'button' },
                            dataset: { taskId: task.id, roleId: role.id }
                        })
                    ])));
                    taskInfo.append(roleList);
                }
                const actions = createElement('span', { className: 'task-actions' }, [
                    createElement('button', { className: 'edit-task-btn', text: '✏️', attrs: { type: 'button', title: 'Редактировать задачу' }, dataset: { id: task.id } }),
                    createElement('button', { className: 'delete-task-btn', text: '🗑️', attrs: { type: 'button', title: 'Удалить задачу' }, dataset: { id: task.id } }),
                    createElement('button', { className: 'add-task-to-role-btn', text: '➕', attrs: { type: 'button', title: 'Добавить в роль' }, dataset: { taskId: task.id, taskName: task.name } })
                ]);
                groupBody.append(createElement('div', { className: 'task-item', attrs: { draggable: true }, dataset: { id: task.id } }, [taskInfo, actions]));
            });
            groupBody.append(createElement('div', { className: 'add-task-area' }, [
                createElement('input', { className: 'new-task-input', attrs: { type: 'text', placeholder: 'Название новой задачи' }, dataset: { typeId } }),
                createElement('button', { className: 'add-task-btn', text: '➕', attrs: { type: 'button' }, dataset: { typeId } })
            ]));
            const groupNode = createElement('section', { className: 'task-group', dataset: { typeId } }, [
                createElement('div', { className: 'task-group-header', dataset: { id: typeId } }, [
                    createElement('span', { className: 'task-group-title', text: group.type.name }),
                    createElement('span', { className: 'task-group-actions' }, [
                        createElement('button', { className: 'edit-type-btn', text: '✏️', attrs: { type: 'button', title: 'Редактировать тип' }, dataset: { id: typeId } }),
                        createElement('button', { className: 'delete-type-btn', text: '🗑️', attrs: { type: 'button', title: 'Удалить тип' }, dataset: { id: typeId } })
                    ])
                ]),
                groupBody
            ]);
            groupsContainer.append(groupNode);
        });
        leftPanel.replaceChildren(groupsContainer);

        leftPanel.querySelectorAll('.task-item[draggable="true"]').forEach(el => {
            el.removeEventListener('dragstart', handleDragStart);
            el.removeEventListener('dragend', handleDragEnd);
            el.addEventListener('dragstart', handleDragStart);
            el.addEventListener('dragend', handleDragEnd);
        });

        leftPanel.querySelectorAll('.edit-task-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const taskId = parseInt(btn.dataset.id);
                const task = allTasks.find(t => t.id === taskId);
                if (!task) return;
                const newName = prompt('Введите новое название задачи:', task.name);
                if (newName !== null && newName.trim() !== '') {
                    try {
                        await apiFetch(`/api/sandbox/tasks/${taskId}`, {
                            method: 'PUT',
                            body: JSON.stringify({ name: newName.trim() })
                        });
                        showToast('Задача обновлена');
                        loadTasks();
                    } catch (err) {
                        showToast(err.message, true);
                    }
                }
            });
        });

        leftPanel.querySelectorAll('.delete-task-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const taskId = parseInt(btn.dataset.id);
                if (!confirm('Удалить задачу?')) return;
                try {
                    await apiFetch(`/api/sandbox/tasks/${taskId}`, { method: 'DELETE' });
                    showToast('Задача удалена');
                    loadTasks();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });

        leftPanel.querySelectorAll('.add-task-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const typeId = parseInt(btn.dataset.typeId);
                const input = btn.closest('.add-task-area').querySelector('.new-task-input');
                const name = input?.value.trim();
                if (!name) return showToast('Введите название задачи', true);
                try {
                    await apiFetch('/api/sandbox/tasks', {
                        method: 'POST',
                        body: JSON.stringify({ name, task_type_id: typeId })
                    });
                    showToast('Задача создана');
                    if (input) input.value = '';
                    loadTasks();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });

        leftPanel.querySelectorAll('.edit-type-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const typeId = parseInt(btn.dataset.id);
                const type = taskTypes.find(t => t.id === typeId);
                if (!type) return;
                const newName = prompt('Введите новое название типа:', type.name);
                if (newName !== null && newName.trim() !== '') {
                    try {
                        await apiFetch(`/api/sandbox/task-types/${typeId}`, {
                            method: 'PUT',
                            body: JSON.stringify({ name: newName.trim() })
                        });
                        showToast('Тип обновлён');
                        loadTaskTypes();
                    } catch (err) {
                        showToast(err.message, true);
                    }
                }
            });
        });

        leftPanel.querySelectorAll('.delete-type-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const typeId = parseInt(btn.dataset.id);
                if (!confirm('Удалить тип задач? Все задачи этого типа останутся без типа.')) return;
                try {
                    await apiFetch(`/api/sandbox/task-types/${typeId}`, { method: 'DELETE' });
                    showToast('Тип удалён');
                    loadTaskTypes();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });

        leftPanel.querySelectorAll('.add-task-to-role-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const taskId = parseInt(btn.dataset.taskId);
                const taskName = btn.dataset.taskName;
                openAddTaskToRoleModal(taskId, taskName);
            });
        });

        leftPanel.querySelectorAll('.remove-task-from-role').forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.stopPropagation();
                const taskId = parseInt(this.dataset.taskId);
                const roleId = parseInt(this.dataset.roleId);
                if (!confirm('Удалить эту задачу из роли?')) return;
                try {
                    await apiFetch(`/api/sandbox/roles/${roleId}/tasks/${taskId}`, { method: 'DELETE' });
                    showToast('Задача удалена из роли');
                    await loadRoles();
                    await loadTasks();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
    }

    let draggedTaskId = null;
    function handleDragStart(e) {
        const item = e.target.closest('.task-item');
        if (!item) return;
        const taskId = item.dataset.id;
        if (!taskId) return;
        e.dataTransfer.setData('text/plain', String(taskId));
        e.dataTransfer.effectAllowed = 'copy';
        draggedTaskId = taskId;
    }
    function handleDragEnd(e) {
        draggedTaskId = null;
    }

    async function openAddTaskToRoleModal(taskId, taskName) {
        const resp = await apiFetch('/api/sandbox/roles');
        const allRoles = await resp.json();
        const available = allRoles.filter(r => !r.tasks.some(t => t.id === taskId));
        if (available.length === 0) {
            showToast('Задача уже во всех ролях', true);
            return;
        }
        const modal = createSelectionModal({
            title: 'Добавить задачу в роль',
            description: `Задача: ${taskName}`,
            selectId: 'roleSelectForTask',
            options: available.map(role => ({ value: role.id, label: role.name })),
            cancelId: 'cancelAddTaskToRole',
            confirmId: 'confirmAddTaskToRole',
            confirmLabel: 'Добавить'
        });
        document.body.appendChild(modal);

        const closeModal = () => modal.remove();
        modal.querySelector('.modal-close').addEventListener('click', closeModal);
        modal.querySelector('#cancelAddTaskToRole').addEventListener('click', closeModal);
        window.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

        modal.querySelector('#confirmAddTaskToRole').addEventListener('click', async () => {
            const roleId = parseInt(modal.querySelector('#roleSelectForTask').value);
            if (!roleId) { showToast('Выберите роль', true); return; }
            try {
                await apiFetch(`/api/sandbox/roles/${roleId}/tasks`, {
                    method: 'POST',
                    body: JSON.stringify({ task_id: taskId })
                });
                showToast('Задача добавлена в роль');
                closeModal();
                await loadRoles();
                await loadTasks();
            } catch (err) {
                showToast(err.message, true);
            }
        });
    }

    // ================================================
    //   КОНСТРУКТОР ТЕХКАРТ
    // ================================================

    function initConstructorUI() {
        const rightPanel = document.getElementById('tasksRightPanel');
        if (!rightPanel) return;

        techCardNameInput = document.getElementById('techCardNameInput');
        techCardSelect = document.getElementById('techCardSelect');
        constructorListEl = document.getElementById('constructorTasksList');
        saveConstructorBtn = document.getElementById('saveConstructorBtn');
        deleteConstructorBtn = document.getElementById('deleteConstructorBtn');
        clearConstructorBtn = document.getElementById('clearConstructorBtn');

        if (!constructorListEl) return;
        if (constructorInitialized) return;

        populateTechCardSelect();

        if (techCardSelect) {
            techCardSelect.addEventListener('change', async function() {
                const val = this.value;
                if (val === '') {
                    clearConstructor();
                    return;
                }
                const techCardId = parseInt(val);
                await loadTechCardToConstructor(techCardId);
            });
        }

        if (saveConstructorBtn) {
            saveConstructorBtn.addEventListener('click', saveTechCard);
        }
        if (deleteConstructorBtn) {
            deleteConstructorBtn.addEventListener('click', deleteCurrentTechCard);
        }
        if (clearConstructorBtn) {
            clearConstructorBtn.addEventListener('click', clearConstructor);
        }

        constructorListEl.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'all';
            constructorListEl.style.borderColor = '#3b82f6';
        });
        constructorListEl.addEventListener('dragleave', (e) => {
            e.preventDefault();
            constructorListEl.style.borderColor = '#cbd5e1';
        });
        constructorListEl.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            constructorListEl.style.borderColor = '#cbd5e1';
            const data = e.dataTransfer.getData('text/plain');
            if (!data) return;

            if (data.startsWith('reorder:')) {
                const fromIndex = parseInt(data.split(':')[1]);
                const items = constructorListEl.querySelectorAll('.constructor-task-item');
                let toIndex = items.length;
                for (let i = 0; i < items.length; i++) {
                    const rect = items[i].getBoundingClientRect();
                    if (e.clientY < rect.top + rect.height / 2) {
                        toIndex = i;
                        break;
                    }
                }
                if (fromIndex === toIndex) return;
                const [moved] = constructorTasks.splice(fromIndex, 1);
                constructorTasks.splice(toIndex, 0, moved);
                renderConstructorTasks();
                showToast(`Задача перемещена на позицию ${toIndex+1}`);
                return;
            }

            const taskId = parseInt(data, 10);
            if (isNaN(taskId)) return;
            if (constructorTasks.some(t => t.id === taskId)) {
                showToast('Эта задача уже добавлена в конструктор', true);
                return;
            }
            const task = allTasks.find(t => t.id === taskId);
            if (!task) {
                showToast('Задача не найдена', true);
                return;
            }
            constructorTasks.push({ id: task.id, name: task.name });
            renderConstructorTasks();
            showToast(`Задача "${task.name}" добавлена в конструктор`);
        });

        constructorInitialized = true;
    }

    function populateTechCardSelect() {
        if (!techCardSelect) return;
        const currentVal = techCardSelect.value;
        techCardSelect.innerHTML = '<option value="">-- Создать новую --</option>';
        techCards.forEach(tc => {
            techCardSelect.innerHTML += `<option value="${tc.id}">${escapeHtml(tc.name)}</option>`;
        });
        if (currentVal) techCardSelect.value = currentVal;
    }

    async function loadTechCardToConstructor(techCardId) {
        try {
            const resp = await apiFetch(`/api/sandbox/tech-cards/${techCardId}`);
            const data = await resp.json();
            if (!data) {
                showToast('Техкарта не найдена', true);
                return;
            }
            if (techCardNameInput) techCardNameInput.value = data.name || '';
            constructorTasks = data.tasks.map(t => ({ id: t.id, name: t.name }));
            currentTechCardId = techCardId;
            renderConstructorTasks();
        } catch (err) {
            showToast('Ошибка загрузки техкарты: ' + err.message, true);
        }
    }

    function renderConstructorTasks() {
        if (!constructorListEl) return;
        if (!constructorTasks.length) {
            showMessage(constructorListEl, 'Перетащите сюда задачи');
            return;
        }
        const rows = constructorTasks.map((task, index) => createElement('div', {
            className: 'constructor-task-item', attrs: { draggable: true }, dataset: { index }
        }, [
            createElement('span', { text: `${index + 1}. ${task.name}` }),
            createElement('button', { className: 'remove-constructor-task icon-delete-button', text: '✖', attrs: { type: 'button' }, dataset: { index } })
        ]));
        constructorListEl.replaceChildren(...rows);

        constructorListEl.querySelectorAll('.constructor-task-item').forEach(el => {
            el.addEventListener('dragstart', (e) => {
                const idx = el.dataset.index;
                e.dataTransfer.setData('text/plain', `reorder:${idx}`);
                e.dataTransfer.effectAllowed = 'move';
            });
        });

        constructorListEl.querySelectorAll('.remove-constructor-task').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.index);
                constructorTasks.splice(idx, 1);
                renderConstructorTasks();
            });
        });
    }

    function clearConstructor() {
        constructorTasks = [];
        currentTechCardId = null;
        if (techCardNameInput) techCardNameInput.value = '';
        if (techCardSelect) techCardSelect.value = '';
        renderConstructorTasks();
    }

    async function deleteCurrentTechCard() {
        if (!currentTechCardId) {
            showToast('Нет открытой техкарты для удаления', true);
            return;
        }
        const name = techCardNameInput ? techCardNameInput.value.trim() : 'без названия';
        if (!confirm(`Удалить техкарту "${name}" (ID: ${currentTechCardId})?`)) return;
        try {
            await apiFetch(`/api/sandbox/tech-cards/${currentTechCardId}`, { method: 'DELETE' });
            showToast('Техкарта удалена');
            await loadProducts();
            clearConstructor();
        } catch (err) {
            showToast('Ошибка удаления: ' + err.message, true);
        }
    }

    async function saveTechCard() {
        const name = techCardNameInput ? techCardNameInput.value.trim() : '';
        if (!name) {
            showToast('Введите название техкарты', true);
            return;
        }
        if (constructorTasks.length === 0) {
            showToast('Добавьте хотя бы одну задачу в конструктор', true);
            return;
        }
        const taskIds = constructorTasks.map(t => t.id);
        try {
            let resp;
            if (currentTechCardId) {
                resp = await apiFetch(`/api/sandbox/tech-cards/${currentTechCardId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name, task_ids: taskIds })
                });
            } else {
                resp = await apiFetch('/api/sandbox/tech-cards', {
                    method: 'POST',
                    body: JSON.stringify({ name, task_ids: taskIds })
                });
            }
            const data = await resp.json();
            showToast(`Техкарта "${data.name}" сохранена`);
            await loadProducts();
            clearConstructor();
        } catch (err) {
            showToast('Ошибка сохранения: ' + err.message, true);
        }
    }

    // ================================================
    //   ВКЛАДКА «РОЛИ»
    // ================================================

    async function loadRoles() {
        try {
            const resp = await apiFetch('/api/sandbox/roles');
            roles = await resp.json();
            renderRoles();
            renderRolesSimpleList();
            renderTasksGrouped();
        } catch (err) {
            showToast('Ошибка загрузки ролей: ' + err.message, true);
        }
    }

    async function loadAllEmployees() {
        try {
            const resp = await fetch('/api/employees?active_only=true', { credentials: 'include' });
            if (!resp.ok) throw new Error('Ошибка загрузки сотрудников');
            allEmployees = await resp.json();
            allEmployees.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
        } catch (err) {
            showToast('Ошибка загрузки сотрудников: ' + err.message, true);
        }
    }

    function renderRoles() {
        const containerEl = document.getElementById('rolesList');
        if (!containerEl) return;
        if (!roles || roles.length === 0) {
            showMessage(containerEl, 'Нет ролей.');
            return;
        }
        const grid = createElement('div', { className: 'roles-grid' });
        for (const role of roles) {
            const employees = role.employees || [];
            const employeeList = createElement('span', { className: 'employee-list' });
            if (!employees.length) {
                employeeList.textContent = '—';
            } else {
                employees.forEach(employee => employeeList.append(createElement('span', { className: 'employee-tag' }, [
                    document.createTextNode(`${employee.full_name} `),
                    createElement('button', {
                        className: 'remove-employee-btn', text: '✖', attrs: { type: 'button', title: 'Удалить' },
                        dataset: { roleId: role.id, employeeId: employee.id }
                    })
                ])));
            }
            const card = createElement('div', { className: 'role-card', dataset: { roleId: role.id } });
            card.append(createElement('div', { className: 'role-card-header' }, [
                createElement('div', { className: 'role-title', text: role.name }),
                createElement('div', { className: 'role-actions' }, createElement('button', {
                    className: 'role-add-employee-btn', text: '➕', attrs: { type: 'button', title: 'Добавить сотрудника' }, dataset: { roleId: role.id }
                }))
            ]));
            if (role.description) card.append(createElement('div', { className: 'role-description', text: role.description }));
            card.append(
                createElement('div', { className: 'role-tasks' }, [
                    createElement('strong', { text: 'Задачи:' }),
                    document.createTextNode(` ${(role.tasks || []).map(task => task.name).join(', ') || '—'}`)
                ]),
                createElement('div', { className: 'role-employees' }, [
                    createElement('strong', { text: 'Сотрудники:' }),
                    document.createTextNode(' '),
                    employeeList
                ])
            );
            grid.append(card);
        }
        containerEl.replaceChildren(grid);

        containerEl.querySelectorAll('.role-add-employee-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const roleId = parseInt(btn.dataset.roleId);
                await showEmployeeSelectionModal(roleId);
            });
        });

        containerEl.querySelectorAll('.remove-employee-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const roleId = parseInt(btn.dataset.roleId);
                const employeeId = parseInt(btn.dataset.employeeId);
                if (!confirm('Удалить этого сотрудника из роли?')) return;
                try {
                    await apiFetch(`/api/sandbox/roles/${roleId}/employees/${employeeId}`, { method: 'DELETE' });
                    showToast('Сотрудник удалён из роли');
                    await loadRoles();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
    }

    async function showEmployeeSelectionModal(roleId) {
        if (!allEmployees || allEmployees.length === 0) {
            await loadAllEmployees();
        }
        const role = roles.find(r => r.id === roleId);
        if (!role) {
            showToast('Должность не найдена', true);
            return;
        }
        if (!role.allow_multiple && role.employees && role.employees.length > 0) {
            showToast('Эта должность уже назначена сотруднику, множественное назначение запрещено', true);
            return;
        }
        const assignedIds = (role.employees || []).map(e => e.id);
        const available = allEmployees.filter(e => !assignedIds.includes(e.id));
        if (available.length === 0) {
            showToast('Все сотрудники уже назначены на эту должность', true);
            return;
        }

        const selected = await new Promise((resolve) => {
            const modal = createSelectionModal({
                title: 'Назначить сотрудника на должность',
                selectId: 'employeeSelect',
                options: available.map(employee => ({ value: employee.id, label: employee.full_name })),
                cancelId: 'cancelSelectBtn',
                confirmId: 'confirmSelectBtn',
                confirmLabel: 'Добавить'
            });
            document.body.appendChild(modal);
            const closeModal = () => { modal.remove(); resolve(null); };
            modal.querySelector('.modal-close').addEventListener('click', closeModal);
            modal.querySelector('#cancelSelectBtn').addEventListener('click', closeModal);
            window.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
            modal.querySelector('#confirmSelectBtn').addEventListener('click', () => {
                const select = modal.querySelector('#employeeSelect');
                const empId = parseInt(select.value);
                modal.remove();
                resolve(empId);
            });
        });

        if (selected) {
            try {
                await apiFetch(`/api/sandbox/roles/${roleId}/employees`, {
                    method: 'POST',
                    body: JSON.stringify({ employee_id: selected })
                });
                showToast('Сотрудник назначен на должность');
                await loadRoles();
            } catch (err) {
                showToast(err.message, true);
            }
        }
    }

    function renderRolesSimpleList() {
        const tbody = document.getElementById('rolesSimpleList');
        if (!tbody) return;
        const sortedRoles = [...roles].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
        if (!sortedRoles.length) {
            const cell = createElement('td', { className: 'empty-table-cell', text: 'Нет должностей', attrs: { colspan: 3 } });
            tbody.replaceChildren(createElement('tr', {}, cell));
            return;
        }
        const rows = sortedRoles.map(role => {
            const nameInput = createElement('input', { className: 'role-name-input', attrs: { type: 'text', value: role.name }, dataset: { roleId: role.id } });
            const multipleInput = createElement('input', { className: 'role-allow-multiple', attrs: { type: 'checkbox' }, dataset: { roleId: role.id } });
            multipleInput.checked = role.allow_multiple !== false;
            return createElement('tr', { dataset: { roleId: role.id } }, [
                createElement('td', { className: 'role-name-cell' }, nameInput),
                createElement('td', { className: 'role-option-cell' }, multipleInput),
                createElement('td', { className: 'role-action-cell' }, createElement('button', {
                    className: 'remove-role-simple-btn icon-delete-button', text: '✖', attrs: { type: 'button' }, dataset: { roleId: role.id }
                }))
            ]);
        });
        tbody.replaceChildren(...rows);

        tbody.querySelectorAll('.role-name-input').forEach(input => {
            const roleId = parseInt(input.dataset.roleId);
            const originalName = input.value;
            const save = async () => {
                const newName = input.value.trim();
                if (newName === originalName) return;
                if (!newName) {
                    showToast('Название не может быть пустым', true);
                    input.value = originalName;
                    return;
                }
                try {
                    await apiFetch(`/api/sandbox/roles/${roleId}`, {
                        method: 'PUT',
                        body: JSON.stringify({ name: newName })
                    });
                    showToast('Должность переименована');
                    await loadRoles();
                } catch (err) {
                    showToast(err.message, true);
                    input.value = originalName;
                }
            };
            input.addEventListener('blur', save);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
                if (e.key === 'Escape') { input.value = originalName; input.blur(); }
            });
        });

        tbody.querySelectorAll('.role-allow-multiple').forEach(cb => {
            cb.addEventListener('change', async function() {
                const roleId = parseInt(this.dataset.roleId);
                const allowMultiple = this.checked;
                try {
                    await apiFetch(`/api/sandbox/roles/${roleId}`, {
                        method: 'PUT',
                        body: JSON.stringify({ allow_multiple: allowMultiple })
                    });
                    showToast('Настройка обновлена');
                    await loadRoles();
                } catch (err) {
                    showToast(err.message, true);
                    this.checked = !this.checked;
                }
            });
        });

        tbody.querySelectorAll('.remove-role-simple-btn').forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.stopPropagation();
                const roleId = parseInt(this.dataset.roleId);
                if (!confirm('Удалить эту должность?')) return;
                try {
                    await apiFetch(`/api/sandbox/roles/${roleId}`, { method: 'DELETE' });
                    showToast('Должность удалена');
                    await loadRoles();
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
    }

    function initRolesTabButtons() {
        const refreshRolesBtn = document.getElementById('refreshRolesBtn');
        if (refreshRolesBtn) {
            refreshRolesBtn.addEventListener('click', loadRoles);
        }
        const addRoleBtn = document.getElementById('addRoleBtn');
        if (addRoleBtn) {
            addRoleBtn.addEventListener('click', () => {
                document.querySelector('.sandbox-sidebar .nav-btn[data-target="tasks"]').click();
            });
        }
    }

    // ================================================
    //   НАВИГАЦИЯ ПО ВКЛАДКАМ
    // ================================================

    document.querySelectorAll('.sandbox-sidebar .nav-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const target = this.dataset.target;
            localStorage.setItem(STORAGE_KEYS.processTab, target);
            document.querySelectorAll('.sandbox-sidebar .nav-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            document.querySelectorAll('.sandbox-panel').forEach(p => p.classList.remove('active'));
            const panel = document.getElementById(`panel-${target}`);
            if (panel) panel.classList.add('active');

            if (target === 'deals') {
                loadDeals();
            } else if (target === 'counterparties') {
                loadDealTypes();
                loadIPs();
                loadMPs();
            } else if (target === 'tasks') {
                loadTaskTypes();
                loadTasks();
                if (!constructorInitialized) initConstructorUI();
                else populateTechCardSelect();
                loadRoles();
            } else if (target === 'products') {
                loadProducts();
            } else if (target === 'points') {
                loadPointsMatrix();
            } else if (target === 'roles') {
                if (!allEmployees.length) loadAllEmployees();
                loadRoles();
            } else if (target === 'mailing') {
                loadMailingNotifications();
            }
        });
    });

    const savedProcsetsTab = localStorage.getItem(STORAGE_KEYS.processTab);
    const savedProcsetsBtn = savedProcsetsTab
        ? document.querySelector(`.sandbox-sidebar .nav-btn[data-target="${savedProcsetsTab}"]`)
        : null;
    if (savedProcsetsBtn) savedProcsetsBtn.click();
    observeAdminModals();
    setTimeout(restoreAdminModal, 0);

    // ---- Первоначальная загрузка ----
    loadDealTypes().then(() => loadDeals());
    loadIPs();
    loadMPs();
    loadTaskTypes();
    loadTasks();
    loadProducts();
    loadAllEmployees();
    loadRoles();

    initCounterpartiesHandlers();

    if (createBtn) createBtn.addEventListener('click', openCreateModal);
    if (closeCreate) closeCreate.addEventListener('click', closeCreateModal);
    if (cancelCreate) cancelCreate.addEventListener('click', closeCreateModal);
    window.addEventListener('click', (e) => {
        if (e.target === modalCreate) closeCreateModal();
        if (e.target === detailModal) detailModal.style.display = 'none';
    });
    if (closeDetail) closeDetail.addEventListener('click', () => detailModal.style.display = 'none');
    if (refreshBtn) refreshBtn.addEventListener('click', loadDeals);

    // ---- Обработчик клика по названию сделки ----
    if (dealsListEl) {
        dealsListEl.addEventListener('click', function(e) {
            const target = e.target.closest('.deal-title-link');
            if (target) {
                const dealId = parseInt(target.dataset.id, 10);
                if (!isNaN(dealId)) {
                    viewDeal(dealId);
                }
            }
        });
    }

    if (!constructorInitialized) {
        if (document.getElementById('panel-tasks').classList.contains('active')) {
            initConstructorUI();
        }
    }

    // ---- Загрузка уведомлений для вкладки "Рассылка" ----
    // ---- Настройки типа сделки ----
    function initDealTypeSettings() {
        const settingsBtn = container.querySelector('#dealTypeSettingsBtn');
        const settingsModal = document.getElementById('dealTypeSettingsModal');
        const closeSettings = document.querySelector('.close-deal-type-settings');

        if (!settingsBtn || !settingsModal) {
            console.warn('Элементы настроек типа сделки не найдены');
            return;
        }

        // ---- Загрузка данных с бекенда ----
        async function loadDealTypeSettings() {
            const body = document.getElementById('dealTypeSettingsBody');
            if (!body) return;
            body.innerHTML = '<p>Загрузка...</p>';
            try {
                const resp = await apiFetch('/api/sandbox/deal-types/tasks');
                const data = await resp.json();
                renderSettingsTable(data);
            } catch (err) {
                showMessage(body, `Ошибка загрузки: ${err.message}`, 'error');
                showToast(err.message, true);
            }
        }

        // ---- Отрисовка таблицы ----
        function renderSettingsTable(data) {
            const body = document.getElementById('dealTypeSettingsBody');
            if (!body) return;

            const types = data.types || [];
            const tasks = data.tasks || [];

            if (!types.length || !tasks.length) {
                showMessage(body, 'Нет типов сделок или задач для настройки');
                return;
            }
            const table = createElement('table', { className: 'deal-type-settings-table' });
            const header = createElement('tr');
            header.append(createElement('th', { text: 'Задача' }));
            types.forEach(type => header.append(createElement('th', { text: type.name })));
            table.append(createElement('thead', {}, header));
            const tbody = createElement('tbody');
            tasks.forEach(task => {
                const row = createElement('tr');
                row.append(createElement('td', { text: task.name }));
                types.forEach(type => {
                    const checkbox = createElement('input', {
                        className: 'deal-type-task-checkbox', attrs: { type: 'checkbox' },
                        dataset: { taskId: task.id, typeId: type.id }
                    });
                    checkbox.checked = Boolean(task[`type_${type.id}`]);
                    row.append(createElement('td', { className: 'cell-center' }, checkbox));
                });
                tbody.append(row);
            });
            table.append(tbody);
            body.replaceChildren(table, createElement('div', { className: 'settings-save-row' }, createElement('button', {
                className: 'success button-submit-wide', text: '💾 Сохранить', attrs: { id: 'saveDealTypeSettingsBtn', type: 'button' }
            })));

            // Обработчик сохранения
            const saveBtn = document.getElementById('saveDealTypeSettingsBtn');
            if (saveBtn) {
                saveBtn.removeEventListener('click', saveDealTypeSettings);
                saveBtn.addEventListener('click', saveDealTypeSettings);
            }
        }

        // ---- Сохранение настроек ----
        async function saveDealTypeSettings() {
            const checkboxes = document.querySelectorAll('.deal-type-task-checkbox:checked');
            const data = {};

            // Собираем выбранные задачи по типам
            checkboxes.forEach(cb => {
                const typeId = parseInt(cb.dataset.typeId);
                const taskId = parseInt(cb.dataset.taskId);
                if (!data[typeId]) data[typeId] = [];
                data[typeId].push(taskId);
            });

            // Получаем все типы, которые есть в таблице (для типов без галочек отправляем пустой массив)
            const allCheckboxes = document.querySelectorAll('.deal-type-task-checkbox');
            const allTypeIds = new Set();
            allCheckboxes.forEach(cb => {
                allTypeIds.add(parseInt(cb.dataset.typeId));
            });
            for (const typeId of allTypeIds) {
                if (!data[typeId]) data[typeId] = [];
            }

            try {
                await apiFetch('/api/sandbox/deal-types/tasks', {
                    method: 'PUT',
                    body: JSON.stringify({ tasks: data })
                });
                showToast('Настройки сохранены');
            } catch (err) {
                showToast(err.message, true);
            }
        }

        // ---- Открытие модалки ----
        settingsBtn.addEventListener('click', () => {
            settingsModal.style.display = 'block';
            loadDealTypeSettings();
        });

        // ---- Закрытие по крестику ----
        if (closeSettings) {
            closeSettings.addEventListener('click', () => {
                settingsModal.style.display = 'none';
            });
        }

        // ---- Закрытие по клику вне модалки ----
        window.addEventListener('click', (e) => {
            if (e.target === settingsModal) {
                settingsModal.style.display = 'none';
            }
        });
    }

    initRolesTabButtons();
    initDealTypeSettings();
    setInterval(loadDeals, 30000);
}


function createSelectionModal({ title, description = '', selectId, options, cancelId, confirmId, confirmLabel }) {
    const modal = createElement('div', { className: 'modal' });
    modal.style.display = 'block';
    const select = createElement('select', { className: 'selection-modal-select', attrs: { id: selectId } });
    options.forEach(option => select.add(new Option(option.label, option.value)));
    const content = createElement('div', { className: 'modal-content modal-size-sm' });
    content.append(createElement('button', { className: 'modal-close', text: '×', attrs: { type: 'button', 'aria-label': 'Закрыть' } }));
    content.append(createElement('h3', { text: title }));
    if (description) content.append(createElement('p', {}, [createElement('strong', { text: description.split(':')[0] + ':' }), document.createTextNode(description.slice(description.indexOf(':') + 1))]));
    content.append(select, createElement('div', { className: 'selection-modal-actions' }, [
        createElement('button', { className: 'button-cancel-form', text: 'Отмена', attrs: { id: cancelId, type: 'button' } }),
        createElement('button', { className: 'button-save-form', text: confirmLabel, attrs: { id: confirmId, type: 'button' } })
    ]));
    modal.append(content);
    return modal;
}
