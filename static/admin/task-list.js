/** Task list in process settings: filters, loading and table rendering. */
import { showToast } from './core.js';
import { viewDeal } from './deals.js';
import { registerTaskListLoader } from './mailing.js';
import { initTaskCreationModal } from './tasks.js';
import { openIndependentTaskEditor } from './independent-task-editor.js';
import { createElement, showMessage } from './dom.js';

async function apiFetch(url, options = {}) {
    const response = await fetch(url, {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options
    });
    if (!response.ok) {
        let message = 'Ошибка запроса';
        try { message = (await response.json()).detail || message; } catch (_) {}
        throw new Error(message);
    }
    return response.status === 204 ? null : response.json();
}

// ================================================
// 1. ГЕНЕРАЦИЯ ПАНЕЛИ ФИЛЬТРОВ
// ================================================
function renderMailingFilters(container) {
    let suppressMailingAutoApply = false;
    if (!document.getElementById('mailingFilters')) return;
    initTaskCreationModal();

    const addFilterClearButton = controlId => {
        const control = document.getElementById(controlId);
        if (!control || control.parentElement?.classList.contains('mailing-filter-control')) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'mailing-filter-control';
        control.parentNode.insertBefore(wrapper, control);
        wrapper.appendChild(control);
        control.classList.add('mailing-filter-input');
        const clearButton = document.createElement('button');
        clearButton.type = 'button';
        clearButton.textContent = '✖';
        clearButton.title = 'Сбросить фильтр';
        clearButton.className = 'mailing-filter-clear';
        clearButton.addEventListener('click', () => {
            if (controlId === 'filterDateRange' && control._flatpickr) {
                control._flatpickr.clear();
            } else {
                control.value = '';
                loadMailingNotifications();
            }
        });
        wrapper.appendChild(clearButton);
    };

    ['filterDateRange', 'filterDealType', 'filterTaskType', 'filterTask', 'filterProduct', 'filterEmployee', 'filterRole', 'filterStatus']
        .forEach(addFilterClearButton);

    // Инициализация календаря с автоматическим применением
    if (typeof flatpickr !== 'undefined') {
        flatpickr("#filterDateRange", {
            mode: "range",
            dateFormat: "Y-m-d",
            locale: { firstDayOfWeek: 1 },
            onChange: selectedDates => {
                if (!suppressMailingAutoApply && (selectedDates.length === 0 || selectedDates.length === 2)) loadMailingNotifications();
            }
        });
    }

    // Подгрузка типов задач
    fetch('/api/sandbox/task-types', { credentials: 'include' }).then(res => res.json()).then(types => {
        const sel = document.getElementById('filterTaskType');
        types.forEach(item => sel.add(new Option(item.name, item.id)));
    });

    // Подгрузка конкретных задач
    fetch('/api/sandbox/tasks', { credentials: 'include' }).then(res => res.json()).then(tasks => {
        const sel = document.getElementById('filterTask');
        // Сортируем по алфавиту для удобства
        tasks.sort((a, b) => a.name.localeCompare(b.name, 'ru'));
        tasks.forEach(item => sel.add(new Option(item.name, item.id)));
    });

    // Подгрузка товаров
    fetch('/api/sandbox/product-types', { credentials: 'include' }).then(res => res.json()).then(productTypes => {
        const sel = document.getElementById('filterProduct');
        productTypes.sort((a, b) => a.name.localeCompare(b.name, 'ru'));
        productTypes.forEach(product => {
            const option = document.createElement('option');
            option.value = product.name;
            option.textContent = product.full_name || product.name;
            sel.appendChild(option);
        });
    });

    // Подгрузка сотрудников
    fetch('/api/employees?active_only=false', { credentials: 'include' }).then(res => res.json()).then(emps => {
        const sel = document.getElementById('filterEmployee');
        emps.sort((a,b) => a.full_name.localeCompare(b.full_name, 'ru'));
        emps.forEach(item => sel.add(new Option(item.full_name, item.id)));
    });

    // Автоматическое применение и кнопки управления
    ['filterDealType', 'filterTaskType', 'filterTask', 'filterProduct', 'filterEmployee', 'filterRole', 'filterStatus'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', loadMailingNotifications);
    });
    document.getElementById('applyMailingFilters').addEventListener('click', loadMailingNotifications);
    document.getElementById('resetMailingFilters').addEventListener('click', () => {
        suppressMailingAutoApply = true;
        const picker = document.getElementById('filterDateRange')._flatpickr;
        if (picker) picker.clear();
        document.getElementById('filterDealType').value = '';
        document.getElementById('filterTaskType').value = '';
        document.getElementById('filterTask').value = '';
        document.getElementById('filterProduct').value = '';
        document.getElementById('filterEmployee').value = '';
        document.getElementById('filterRole').value = '';
        document.getElementById('filterStatus').value = '';
        suppressMailingAutoApply = false;
        loadMailingNotifications();
    });
}

// ================================================
// 2. ЗАГРУЗКА ДАННЫХ С УЧЕТОМ ФИЛЬТРОВ И ГРУППИРОВКА
// ================================================
function updateAdminTaskCounters(notifications) {
    const tasks = new Map();
    notifications.forEach(notification => {
        const key = `${notification.deal_id}_${notification.task_id}`;
        if (!tasks.has(key)) tasks.set(key, []);
        tasks.get(key).push(notification.execution_status || 'not_started');
    });
    let completedCount = 0;
    tasks.forEach(statuses => {
        if (statuses.length > 0 && statuses.every(status => status === 'completed')) completedCount += 1;
    });
    const activeCount = tasks.size - completedCount;
    const activeElement = document.getElementById('adminActiveTasksCount');
    const completedElement = document.getElementById('adminCompletedTasksCount');
    if (activeElement) activeElement.textContent = `Активные задачи: ${activeCount}`;
    if (completedElement) completedElement.textContent = `Завершенные задачи: ${completedCount}`;
}

async function loadMailingNotifications() {
    const container = document.getElementById('mailingContainer');
    if (!container) return;

    // Рендерим фильтры при первом вызове
    if (!document.getElementById('mailingFilters')) {
        renderMailingFilters(container);
    }

    showMessage(container, 'Загрузка...');

    // Собираем параметры из UI фильтров
    const params = new URLSearchParams();
    const dateRange = document.getElementById('filterDateRange')?._flatpickr?.selectedDates;
    if (dateRange && dateRange.length === 2) {
        params.append('start_date', dateRange[0].toISOString().split('T')[0]);
        params.append('end_date', dateRange[1].toISOString().split('T')[0]);
    }

    const mappings = [
        ['filterDealType', 'deal_type'],
        ['filterTaskType', 'task_type_id'],
        ['filterTask', 'task_id'],
        ['filterProduct', 'product_name'],
        ['filterEmployee', 'employee_id'],
        ['filterRole', 'role'],
        ['filterStatus', 'status']
    ];

    mappings.forEach(([uiId, apiParam]) => {
        const val = document.getElementById(uiId)?.value;
        if (val) params.append(apiParam, val);
    });

    const queryString = params.toString() ? `?${params.toString()}` : '';

    try {
        const resp = await fetch(`/api/sandbox/mailing/notifications${queryString}`, { credentials: 'include' });
        if (!resp.ok) throw new Error('Ошибка загрузки');
        const data = await resp.json();

        if (queryString) {
            try {
                const countResp = await fetch('/api/sandbox/mailing/notifications', { credentials: 'include' });
                if (countResp.ok) updateAdminTaskCounters(await countResp.json());
            } catch (countError) {
                console.error('Ошибка загрузки счетчиков задач:', countError);
            }
        } else {
            updateAdminTaskCounters(data);
        }

        // --- 🚀 НОВЫЙ БЛОК: ГРУППИРОВКА ПО ЗАДАЧАМ ---
        const grouped = {};
        for (const n of data) {
            const key = n.independent_task_id ? `independent_${n.independent_task_id}` : `deal_${n.deal_id}_${n.task_id}`;
            if (!grouped[key]) {
                grouped[key] = {
                    deal_id: n.deal_id,
                    independent_task_id: n.independent_task_id,
                    deal_title: n.deal_title,
                    deal_type_name: n.deal_type_name,
                    task_id: n.task_id,
                    task_name: n.task_name,
                    task_type_name: n.task_type_name,
                    products: n.products || n.extra_data?.products || [],
                    created_at: n.created_at,
                    employees: []
                };
            }
            grouped[key].employees.push({
                id: n.id,
                employee_id: n.employee_id,
                employee_name: n.employee_name,
                role: n.role,
                execution_status: n.execution_status,
                started_at: n.started_at,
                completed_at: n.completed_at
            });
        }
        const groupedNotifications = Object.values(grouped);
        renderMailingTable(groupedNotifications, container);
    } catch (err) {
        showMessage(container, `Ошибка загрузки: ${err.message}`, 'error');
    }
}

    // ================================================
    // 3. ОТРИСОВКА ТАБЛИЦЫ
    // ================================================
function renderMailingTable(groupedNotifications, container) {
    if (!groupedNotifications?.length) {
        showMessage(container, 'Нет уведомлений по задачам');
        return;
    }

    const table = createElement('table');
    const headerRow = createElement('tr');
    ['Сделка', 'Задача', 'Товары', 'Сотрудники', 'Статусы и отметки', 'Действия']
        .forEach(label => headerRow.append(createElement('th', { text: label })));
    table.append(createElement('thead', {}, headerRow));
    const tbody = createElement('tbody');

    groupedNotifications.forEach(task => {
        const row = createElement('tr');

        const deal = createElement('div', { className: 'task-deal-summary' });
        if (task.deal_type_name && task.deal_type_name !== '—') {
            deal.append(createElement('span', { className: 'deal-type-badge', text: task.deal_type_name }));
        }
        deal.append(createElement('span', { text: task.deal_title || '—' }));
        row.append(createElement('td', {}, deal));

        const taskButton = createElement('button', {
            className: task.deal_id ? 'task-title-button open-task-detail' : 'task-title-button open-independent-task-detail',
            text: task.task_name || '—',
            attrs: { type: 'button' },
            dataset: task.deal_id
                ? { dealId: task.deal_id, taskId: task.task_id }
                : { independentTaskId: task.independent_task_id }
        });
        row.append(createElement('td', {}, taskButton));

        const productsCell = createElement('td');
        if (task.products.length) {
            task.products.forEach((product, index) => {
                if (index) productsCell.append(document.createElement('br'));
                productsCell.append(document.createTextNode(`${product.name} `));
                productsCell.append(createElement('span', { className: 'product-quantity', text: `(${product.quantity})` }));
            });
        } else {
            productsCell.textContent = '—';
        }
        row.append(productsCell);

        const employees = createElement('div', { className: 'task-employee-list' });
        const statuses = createElement('div', { className: 'task-status-list' });
        const sortedEmployees = [...task.employees].sort((left, right) => {
            if (left.role === 'Основной' && right.role !== 'Основной') return -1;
            if (left.role !== 'Основной' && right.role === 'Основной') return 1;
            return 0;
        });

        sortedEmployees.forEach(employee => {
            const employeeRow = createElement('div', { className: 'task-employee-row' }, [
                createElement('span', { className: 'task-employee-name', text: employee.employee_name }),
                createElement('span', {
                    className: employee.role === 'Основной' ? 'task-role-badge is-main' : 'task-role-badge is-assistant',
                    text: employee.role === 'Основной' ? 'Основной' : 'Соисполнитель'
                })
            ]);
            employees.append(employeeRow);

            if (employee.role !== 'Основной') return;
            const statusRow = createElement('div', { className: 'task-status-row' });
            const statusSelect = createElement('select', {
                className: `mailing-status-select task-status-${employee.execution_status || 'not_started'}`,
                dataset: { dealId: task.deal_id || '', taskId: task.task_id, notificationId: employee.id }
            });
            [
                ['not_started', '❌ Не начата'],
                ['in_progress', '🔄 В процессе'],
                ['on_break', '⏸️ Перерыв'],
                ['completed', '✅ Завершена']
            ].forEach(([value, label]) => {
                const option = new Option(label, value, false, employee.execution_status === value);
                statusSelect.add(option);
            });
            statusRow.append(statusSelect);

            const timeParts = [];
            if (employee.started_at) timeParts.push(`🟢 ${formatTaskTime(employee.started_at)}`);
            if (employee.completed_at) timeParts.push(`🏁 ${formatTaskTime(employee.completed_at)}`);
            if (timeParts.length) statusRow.append(createElement('span', { className: 'task-time-label', text: timeParts.join(' ') }));
            statuses.append(statusRow);
        });
        row.append(createElement('td', {}, employees));
        row.append(createElement('td', {}, statuses));

        const deleteButton = createElement('button', {
            className: 'btn-sm btn-danger delete-task-group-btn',
            text: '🗑️',
            attrs: { title: 'Удалить задачу у всех' },
            dataset: {
                ids: task.employees.map(employee => employee.id).join(','),
                independentTaskId: task.independent_task_id || ''
            }
        });
        row.append(createElement('td', {}, deleteButton));
        tbody.append(row);
    });

    table.append(tbody);
    container.replaceChildren(createElement('div', { className: 'recent-table' }, table));

    container.querySelectorAll('.open-task-detail').forEach(button => {
        button.addEventListener('click', () => viewDeal(Number(button.dataset.dealId), Number(button.dataset.taskId)));
    });
    container.querySelectorAll('.open-independent-task-detail').forEach(button => {
        button.addEventListener('click', () => openIndependentTaskEditor(Number(button.dataset.independentTaskId)));
    });
    container.querySelectorAll('.mailing-status-select').forEach(select => {
        select.addEventListener('change', async () => {
            try {
                const statusUrl = select.dataset.dealId
                    ? `/api/sandbox/deals/${select.dataset.dealId}/tasks/${select.dataset.taskId}/status`
                    : `/api/sandbox/task-assignments/${select.dataset.notificationId}/status`;
                await apiFetch(statusUrl, {
                    method: 'PUT',
                    body: JSON.stringify({ status: select.value, notification_id: Number(select.dataset.notificationId) })
                });
                showToast('Статус обновлён');
            } catch (error) {
                showToast(error.message, true);
            }
            loadMailingNotifications();
        });
    });
    container.querySelectorAll('.delete-task-group-btn').forEach(button => {
        button.addEventListener('click', async () => {
            if (!confirm('Удалить эту задачу у всех назначенных сотрудников?')) return;
            try {
                if (button.dataset.independentTaskId) {
                    const response = await fetch(`/api/sandbox/independent-tasks/${button.dataset.independentTaskId}`, { method: 'DELETE', credentials: 'include' });
                    if (!response.ok) throw new Error((await response.json()).detail || 'Ошибка удаления');
                } else {
                    const ids = button.dataset.ids.split(',').map(Number);
                    await Promise.all(ids.map(id => fetch(`/api/sandbox/mailing/notifications/${id}`, { method: 'DELETE', credentials: 'include' })));
                }
                showToast('✅ Задача удалена');
                loadMailingNotifications();
            } catch (error) {
                showToast(`Ошибка удаления: ${error.message}`, true);
            }
        });
    });
}

function formatTaskTime(value) {
    return new Date(value).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

registerTaskListLoader(loadMailingNotifications);
