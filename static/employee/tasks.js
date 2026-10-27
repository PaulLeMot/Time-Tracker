import { employeeState, EMPLOYEE_STORAGE_KEYS } from './state.js';
import { showToast, fetchWithAuth, formatTaskDuration } from './core.js';
import { createElement, appendLabeledValue, showMessage } from './dom.js';

// ========== ЗАДАЧИ ==========
    let allTaskNotifications = [];

    export function fillTaskFilter(selectId, items) {
        const select = document.getElementById(selectId);
        if (!select) return;
        const previousValue = select.value;
        select.replaceChildren(new Option('Все', ''), ...items.map(item => new Option(item.label, item.value)));
        if (Array.from(select.options).some(option => option.value === previousValue)) select.value = previousValue;
    }

    export function populateTaskFilters(tasks) {
        const deals = new Map();
        const products = new Map();
        const mainAssignees = new Map();
        const coAssignees = new Map();
        tasks.forEach(task => {
            const parsed = parseTaskNotification(task);
            const dealId = task.extra_data?.deal_id;
            if (dealId) deals.set(String(dealId), parsed.dealTitle || `Сделка #${dealId}`);
            parsed.products.forEach(product => products.set(product.name, product.name));
            const assignees = task.assignees || [];
            if (assignees[0]) mainAssignees.set(String(assignees[0].employee_id), assignees[0].employee_name);
            assignees.slice(1).forEach(employee => coAssignees.set(String(employee.employee_id), employee.employee_name));
        });
        const toItems = map => Array.from(map, ([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, 'ru'));
        fillTaskFilter('taskDealFilter', toItems(deals));
        fillTaskFilter('taskProductFilter', toItems(products));
        fillTaskFilter('taskMainAssigneeFilter', toItems(mainAssignees));
        fillTaskFilter('taskCoAssigneeFilter', toItems(coAssignees));
    }

    export function applyTaskFilters() {
        const dealId = document.getElementById('taskDealFilter')?.value || '';
        const productName = document.getElementById('taskProductFilter')?.value || '';
        const date = document.getElementById('taskDateFilter')?.value || '';
        const mainAssigneeId = document.getElementById('taskMainAssigneeFilter')?.value || '';
        const coAssigneeId = document.getElementById('taskCoAssigneeFilter')?.value || '';
        const status = document.getElementById('taskStatusFilter')?.value ?? 'active';

        const filtered = allTaskNotifications.filter(task => {
            const parsed = parseTaskNotification(task);
            const assignees = task.assignees || [];
            const taskStatus = task.status || 'not_started';
            if (dealId && String(task.extra_data?.deal_id) !== dealId) return false;
            if (productName && !parsed.products.some(product => product.name === productName)) return false;
            if (date) {
                const created = new Date(task.created_at);
                const localDate = `${created.getFullYear()}-${String(created.getMonth() + 1).padStart(2, '0')}-${String(created.getDate()).padStart(2, '0')}`;
                if (localDate !== date) return false;
            }
            if (mainAssigneeId && String(assignees[0]?.employee_id || '') !== mainAssigneeId) return false;
            if (coAssigneeId && !assignees.slice(1).some(employee => String(employee.employee_id) === coAssigneeId)) return false;
            if (status === 'active' && taskStatus === 'completed') return false;
            if (status && status !== 'active' && taskStatus !== status) return false;
            return true;
        });
        renderTaskNotifications(filtered, document.getElementById('tasksContainer'));
    }

    export function initTaskFilters() {
        document.querySelectorAll('#taskFilters select, #taskFilters input').forEach(control => {
            control.addEventListener('change', applyTaskFilters);
        });
        document.querySelectorAll('.task-filter-clear').forEach(button => {
            button.addEventListener('click', () => {
                const control = document.getElementById(button.dataset.filter);
                if (!control) return;
                control.value = button.dataset.default || '';
                applyTaskFilters();
            });
        });
        document.getElementById('applyTaskFiltersBtn')?.addEventListener('click', applyTaskFilters);
        document.getElementById('resetAllTaskFiltersBtn')?.addEventListener('click', () => {
            ['taskDealFilter', 'taskProductFilter', 'taskDateFilter', 'taskMainAssigneeFilter', 'taskCoAssigneeFilter']
                .forEach(id => {
                    const control = document.getElementById(id);
                    if (control) control.value = '';
                });
            const statusFilter = document.getElementById('taskStatusFilter');
            if (statusFilter) statusFilter.value = 'active';
            applyTaskFilters();
        });
    }

    export function restoreTaskListScroll(position) {
        sessionStorage.setItem(EMPLOYEE_STORAGE_KEYS.scroll, String(position));
        requestAnimationFrame(() => {
            requestAnimationFrame(() => window.scrollTo(0, position));
        });
        setTimeout(() => window.scrollTo(0, position), 150);
    }

    export function updateTaskCounters(tasks) {
        const completedCount = tasks.filter(task => (task.status || 'not_started') === 'completed').length;
        const activeCount = tasks.length - completedCount;
        const activeElement = document.getElementById('activeTasksCount');
        const completedElement = document.getElementById('completedTasksCount');
        if (activeElement) activeElement.textContent = `Активные задачи: ${activeCount}`;
        if (completedElement) completedElement.textContent = `Завершенные задачи: ${completedCount}`;
    }

    export async function loadTaskNotifications() {
        const container = document.getElementById('tasksContainer');
        const preservedScrollPosition = window.scrollY;
        showMessage(container, 'Загрузка...');
        try {
            const resp = await fetch('/api/employee/tasks', { credentials: 'include' });
            if (!resp.ok) throw new Error('Ошибка загрузки');
            const tasks = await resp.json();

            if (!tasks.length) {
                allTaskNotifications = [];
                updateTaskCounters([]);
                populateTaskFilters([]);
                showMessage(container, 'Нет назначенных задач');
                restoreTaskListScroll(preservedScrollPosition);
                return;
            }

            const dealCache = new Map();

            const enrichedTasks = await Promise.all(tasks.map(async (task) => {
                const dealId = task.extra_data?.deal_id;
                const taskId = task.extra_data?.task_id;
                if (!dealId || !taskId) {
                    return { ...task, assignees: task.assignees || [] };
                }

                if (!dealCache.has(dealId)) {
                    try {
                        const dealResp = await fetch(`/api/sandbox/deals/${dealId}`, { credentials: 'include' });
                        if (!dealResp.ok) {
                            console.warn(`Сделка ${dealId} не найдена, используем пустые данные`);
                            dealCache.set(dealId, { tasks: [] });
                        } else {
                            const dealData = await dealResp.json();
                            dealCache.set(dealId, dealData);
                        }
                    } catch (err) {
                        console.error('Ошибка загрузки сделки', dealId, err);
                        dealCache.set(dealId, { tasks: [] });
                    }
                }

                const deal = dealCache.get(dealId);
                const taskInfo = deal.tasks?.find(t => t.task_id === taskId) || { assignees: [] };
                return { ...task, assignees: taskInfo.assignees || [] };
            }));

            allTaskNotifications = enrichedTasks;
            updateTaskCounters(enrichedTasks);
            populateTaskFilters(enrichedTasks);
            applyTaskFilters();
            restoreTaskListScroll(preservedScrollPosition);
        } catch (err) {
            showMessage(container, `Ошибка: ${err.message}`, 'error');
            restoreTaskListScroll(preservedScrollPosition);
        }
    }


    export function renderTaskNotifications(notifications, container) {
        if (!notifications.length) {
            showMessage(container, 'Нет назначенных задач');
            return;
        }
        const accordion = createElement('div', { className: 'task-accordion' });
        notifications.forEach(notification => accordion.append(createTaskCard(notification)));
        container.replaceChildren(accordion);
        bindTaskCardActions(container);
    }

    function createTaskCard(notification) {
        const notificationId = notification.notification_id || notification.id;
        const { taskName, dealTitle, products } = parseTaskNotification(notification);
        const dealId = notification.extra_data?.deal_id;
        const taskId = notification.extra_data?.task_id;
        const independentTaskId = notification.extra_data?.independent_task_id;
        const assignees = notification.assignees || [];
        const isMain = notification.is_main_executor === true;
        const status = notification.status || 'not_started';
        const statusLabels = { not_started: 'Не начата', in_progress: 'В процессе', on_break: 'В перерыве', completed: 'Выполнена' };
        const item = createElement('div', { className: 'task-accordion-item', dataset: { taskId } });
        const header = createElement('button', { className: 'task-accordion-header', attrs: { type: 'button' } });
        const headerContent = createElement('span', { className: 'task-header-content' }, [
            createElement('span', { className: 'task-title', text: `${dealTitle} ${taskName} : ${formatProductsSummary(products)}` }),
            createElement('span', { className: `task-status task-status-${status.replaceAll('_', '-')}`, text: statusLabels[status] || statusLabels.not_started })
        ]);
        header.append(headerContent);
        const details = createElement('div', { className: 'task-accordion-details' });
        header.addEventListener('click', () => {
            const open = item.classList.toggle('is-open');
            details.hidden = !open;
        });
        details.hidden = true;

        appendLabeledValue(details, 'Дата', new Date(notification.created_at).toLocaleString('ru-RU', {
            day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
        }));
        details.append(createElement('div', {}, createElement('strong', { text: 'Товары:' })));
        if (products.length) {
            const list = createElement('ul');
            products.forEach(product => list.append(createElement('li', { text: `${product.name} (${product.quantity})` })));
            details.append(list);
        } else {
            details.append(createElement('p', { text: 'Товары не указаны' }));
        }
        appendTaskTime(details, notification, isMain);
        details.append(createAssigneeRow(assignees, { dealId, taskId, status, isMain }));
        details.append(createTaskActions(notification, { notificationId, dealId, taskId, independentTaskId, products, status, isMain }));
        item.append(header, details);
        return item;
    }

    function formatProductsSummary(products) {
        return products.length ? products.map(product => `${product.name}(${product.quantity})`).join(', ') : 'нет товаров';
    }

    function appendTaskTime(parent, notification, isMain) {
        if (!isMain) return;
        const started = notification.started_at ? new Date(notification.started_at) : null;
        const completed = notification.completed_at ? new Date(notification.completed_at) : null;
        const includeDate = started && completed && started.toDateString() !== completed.toDateString();
        const options = includeDate
            ? { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }
            : { hour: '2-digit', minute: '2-digit' };
        if (started) appendLabeledValue(parent, 'Начало', started.toLocaleString('ru-RU', options));
        if (!completed) return;
        appendLabeledValue(parent, 'Завершение', completed.toLocaleString('ru-RU', options));
        if (notification.accounted_seconds !== null && notification.accounted_seconds !== undefined) {
            appendLabeledValue(parent, 'Учетное время', formatTaskDuration(notification.accounted_seconds));
        }
        if (notification.full_seconds !== null && notification.full_seconds !== undefined) {
            appendLabeledValue(parent, 'Полное время', formatTaskDuration(notification.full_seconds));
        }
    }

    function createAssigneeRow(assignees, context) {
        const row = createElement('div', { className: 'task-assignees' }, createElement('strong', { text: 'Исполнители:' }));
        const list = createElement('span', { attrs: { id: `assignees-list-${context.taskId}` } });
        if (!assignees.length) {
            list.textContent = '—';
        } else {
            list.append(createElement('span', { className: 'assignee-tag main-assignee', text: assignees[0].employee_name }));
            assignees.slice(1).forEach(assignee => {
                const tag = createElement('span', { className: 'assignee-tag co-assignee', text: assignee.employee_name });
                if (context.isMain) {
                    tag.append(createElement('button', {
                        className: 'remove-assignee', text: '✖', attrs: { type: 'button', 'aria-label': 'Удалить соисполнителя' },
                        dataset: { dealId: context.dealId, taskId: context.taskId, employeeId: assignee.employee_id }
                    }));
                }
                list.append(tag);
            });
        }
        row.append(list);
        if (context.dealId && context.status !== 'completed' && context.isMain) {
            row.append(createElement('button', {
                className: 'btn btn-sm btn-success add-assignee-btn', text: '➕', attrs: { type: 'button' },
                dataset: { dealId: context.dealId, taskId: context.taskId }
            }));
        }
        return row;
    }

    function createTaskActions(notification, context) {
        const actions = createElement('div', { className: 'task-actions' });
        const actionConfig = {
            not_started: ['task-start', '▶️ Начать'],
            in_progress: ['task-break', '⏸️ Перерыв'],
            on_break: ['task-resume', '▶️ Продолжить']
        };
        if (actionConfig[context.status]) {
            const [className, label] = actionConfig[context.status];
            actions.append(createElement('button', { className: `btn btn-sm ${className}`, text: label, dataset: { id: context.notificationId } }));
            const completeClass = context.isMain ? 'task-complete' : 'task-complete-simple';
            actions.append(createElement('button', {
                className: `btn btn-sm btn-warning ${completeClass}`, text: '⏹️ Завершить',
                dataset: {
                    id: context.notificationId, dealId: context.dealId || '', taskId: context.taskId,
                    independentTaskId: context.independentTaskId || '', products: JSON.stringify(context.products)
                }
            }));
        } else if (context.status === 'completed' && context.isMain) {
            const wrapper = createElement('span', { className: 'task-status-wrapper' }, createElement('span', { className: 'status-completed', text: '✅ Выполнена' }));
            wrapper.append(createElement('button', {
                className: 'edit-completion-btn', text: '✏️', attrs: { title: 'Исправить данные завершения' },
                dataset: {
                    deal: context.dealId || '', task: context.taskId, independentTaskId: context.independentTaskId || '',
                    notif: context.notificationId, products: JSON.stringify(context.products), generalComment: notification.general_comment || ''
                }
            }));
            actions.append(wrapper);
        }
        return actions;
    }

    function bindTaskCardActions(container) {
        const bind = (selector, callback) => container.querySelectorAll(selector).forEach(element => {
            element.addEventListener('click', event => { event.stopPropagation(); callback(element); });
        });
        bind('.task-start', button => startTask(button.dataset.id));
        bind('.task-break', button => taskBreak(button.dataset.id));
        bind('.task-resume', button => taskResume(button.dataset.id));
        bind('.task-complete', button => completeTask(button.dataset.id));
        bind('.task-complete-simple', button => completeTaskSimple(button.dataset.id));
        bind('.add-assignee-btn', button => openAddAssigneeModal(button.dataset.dealId, button.dataset.taskId));
        bind('.remove-assignee', button => removeAssignee(button.dataset.dealId, button.dataset.taskId, button.dataset.employeeId));
        bind('.edit-completion-btn', async button => {
            employeeState.isEditingCompletion = true;
            let products = [];
            try { products = JSON.parse(button.dataset.products || '[]'); } catch (_) {}
            await openCompletionModal(
                Number(button.dataset.deal) || null,
                Number(button.dataset.task),
                Number(button.dataset.notif),
                products,
                button.dataset.generalComment || '',
                Number(button.dataset.independentTaskId) || null
            );
        });
    }
    export function parseTaskNotification(notif) {
        const extra = notif.extra_data || {};
        let taskName = extra.task_name || '';
        let dealTitle = extra.deal_title || '—';
        let products = extra.products || [];

        if (!taskName && notif.message) {
            const msg = notif.message;
            const taskMatch = msg.match(/Задача:\s*(.*?)(?:\s*Товары:|$)/);
            if (taskMatch) taskName = taskMatch[1].trim();
            const productsMatch = msg.match(/Товары:\s*(.*)/);
            if (productsMatch) {
                const items = productsMatch[1].split(',').map(s => s.trim()).filter(s => s);
                products = items.map(item => {
                    const match = item.match(/^(.*?)\s*[—\-]\s*(\d+)\s*шт\.?/);
                    if (match) {
                        return { name: match[1].trim(), quantity: parseInt(match[2]) };
                    } else {
                        return { name: item, quantity: 1 };
                    }
                });
            }
        }
        return { taskName, dealTitle, products };
    }

    export async function startTask(notificationId) {
        try {
            const resp = await fetch(`/api/employee/tasks/${notificationId}/start`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' }
            });
            if (resp.ok) {
                showToast('Задача начата');
                loadTaskNotifications();
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка', true);
            }
        } catch (err) {
            showToast('Ошибка сети', true);
        }
    }

        // Унифицированная функция открытия модалки (для завершения и редактирования)
    export async function openCompletionModal(dealId, taskId, notificationId, products, generalComment = '', independentTaskId = null) {
        if ((!dealId && !independentTaskId) || !taskId || !notificationId) {
            showToast('Ошибка: не удалось определить задачу', true);
            return;
        }

        const modal = document.getElementById('completeTaskModal');
        sessionStorage.setItem(EMPLOYEE_STORAGE_KEYS.completion, JSON.stringify({
            dealId, taskId, notificationId, products, generalComment, independentTaskId,
            isEditing: Boolean(employeeState.isEditingCompletion)
        }));
        modal.style.display = 'block';
        document.getElementById('completeError').innerText = '';
        document.getElementById('finalCompleteBtn').disabled = false;
        
        // Меняем текст и цвет кнопки в зависимости от режима
        const finalBtn = document.getElementById('finalCompleteBtn');
        if (employeeState.isEditingCompletion) {
            finalBtn.textContent = '💾 Сохранить изменения';
            finalBtn.style.background = '#f59e0b'; // Оранжевый
        } else {
            finalBtn.textContent = '✅ Завершить задачу';
            finalBtn.style.background = '#22c55e'; // Зеленый
        }

        try {
            employeeState.completion.notificationId = notificationId;
            employeeState.completion.dealId = dealId;
            employeeState.completion.taskId = taskId;
            employeeState.completion.independentTaskId = independentTaskId;

            let deal = null;
            let taskInfo = null;
            let assignees = [];
            let productTypes = [];
            let completions = [];
            if (independentTaskId) {
                const detailsResp = await fetch(`/api/employee/tasks/${notificationId}/independent-details`, {credentials:'include'});
                if (!detailsResp.ok) throw new Error((await detailsResp.json()).detail || 'Ошибка загрузки независимой задачи');
                const details = await detailsResp.json();
                taskInfo = {task_name: details.task_name};
                assignees = details.assignees || [];
                productTypes = (details.products || []).map(product => ({
                    id: product.id,
                    name: product.name,
                    quantity: product.quantity,
                    defect_quantity: 0,
                    defect_comment: ''
                })).filter(product => product.id !== null && product.id !== undefined);
                completions = details.completions || [];
            } else {
                const dealResp = await fetch(`/api/sandbox/deals/${dealId}`, { credentials: 'include' });
                if (!dealResp.ok) throw new Error('Ошибка загрузки сделки');
                deal = await dealResp.json();
                taskInfo = deal.tasks?.find(t => t.task_id === taskId);
                if (!taskInfo) throw new Error('Задача не найдена в сделке');
                assignees = taskInfo.assignees || [];
                const productTypeMap = {};
                (deal.products || []).forEach(product => productTypeMap[product.name] = product.id);
                productTypes = products.map(product => ({
                    id: productTypeMap[product.name] || null,
                    name: product.name,
                    quantity: product.quantity,
                    defect_quantity: 0,
                    defect_comment: ''
                })).filter(product => product.id !== null);
                const completionsResp = await fetch(`/api/sandbox/deals/${dealId}/tasks/${taskId}/completions`, { credentials: 'include' });
                if (completionsResp.ok) completions = await completionsResp.json();
            }

            if (!productTypes.length && !independentTaskId) {
                throw new Error('Для задачи не найдены товары');
            }

            const compMap = {};
            completions.forEach(c => compMap[c.product_type_id] = c);

            const scoreResponse = await fetch(`/api/employee/tasks/${notificationId}/score-details`, {credentials:'include'});
            const scoreDetails = scoreResponse.ok ? await scoreResponse.json() : {total_points:0, assignees:[]};
            employeeState.completion.totalPoints = Number(scoreDetails.total_points || 0);
            employeeState.completion.percentages = {};
            (scoreDetails.assignees || []).forEach(item => {
                employeeState.completion.percentages[item.employee_id] = Number(item.percent || 0);
            });

            productTypes.forEach(pt => {
                const comp = compMap[pt.id];
                if (comp) {
                    pt.defect_quantity = comp.defect_quantity || 0;
                    pt.defect_comment = comp.defect_comment || '';
                    employeeState.completion.distributions[pt.id] = {};
                    if (comp.distributions && comp.distributions.length) {
                        comp.distributions.forEach(d => {
                            employeeState.completion.distributions[pt.id][d.employee_id] = d.quantity;
                        });
                    } else {
                        if (assignees.length > 0) {
                            employeeState.completion.distributions[pt.id][assignees[0].employee_id] = pt.quantity;
                            for (let i = 1; i < assignees.length; i++) {
                                employeeState.completion.distributions[pt.id][assignees[i].employee_id] = 0;
                            }
                        }
                    }
                } else {
                    employeeState.completion.distributions[pt.id] = {};
                    if (assignees.length > 0) {
                        employeeState.completion.distributions[pt.id][assignees[0].employee_id] = pt.quantity;
                        for (let i = 1; i < assignees.length; i++) {
                            employeeState.completion.distributions[pt.id][assignees[i].employee_id] = 0;
                        }
                    } else {
                        assignees.forEach(a => {
                            employeeState.completion.distributions[pt.id][a.employee_id] = 0;
                        });
                    }
                }
            });

            employeeState.completion.productTypes = productTypes;
            employeeState.completion.assignees = assignees;

            renderDefectTable();
            renderDistributionTable();

            // Инициализация поля общего комментария
            const commentTextarea = document.getElementById('generalTaskComment');
            if (commentTextarea) {
                // Используем переданный generalComment (при редактировании) или пустую строку
                commentTextarea.value = generalComment;
                
                // Автосохранение комментария при потере фокуса (blur)
                commentTextarea.onblur = function() {
                    const val = this.value;
                    employeeState.completion.generalComment = val; // <-- Сохраняем в глобальный объект
                    
                    // Отправляем на бэкенд через первый продукт
                    if (employeeState.completion.productTypes.length > 0) {
                        saveCompletionForProduct(employeeState.completion.productTypes[0].id);
                    } else {
                        fetch(`/api/employee/tasks/${employeeState.completion.notificationId}/comment`, {
                            method: 'PUT',
                            credentials: 'include',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ general_comment: val })
                        });
                    }
                };
            }

            const modeText = employeeState.isEditingCompletion ? 'Редактирование' : 'Завершение';
            document.getElementById('completeTaskTitle').innerText = `✅ ${modeText} задачи: ${taskInfo.task_name || 'Задача'}`;
            const taskInfoElement = document.getElementById('completeTaskInfo');
            taskInfoElement.replaceChildren();
            taskInfoElement.append(
                createElement('strong', { text: `${independentTaskId ? 'Тип' : 'Сделка'}:` }),
                document.createTextNode(` ${independentTaskId ? 'Независимая задача' : (deal.title || '—')} | `),
                createElement('strong', { text: 'Задача:' }),
                document.createTextNode(` ${taskInfo.task_name || '—'}`)
            );

            attachDefectHandlers();
            attachDistributionHandlers();
        } catch (err) {
            document.getElementById('completeError').innerText = 'Ошибка: ' + err.message;
            console.error(err);
        }
    }

    // Старая функция-обертка для совместимости (если вызывается из других мест)
    export async function completeTask(notificationId) {
        const btn = document.querySelector(`.task-complete[data-id="${notificationId}"]`);
        if (!btn) {
            showToast('Кнопка задачи не найдена', true);
            return;
        }
        const dealId = parseInt(btn.dataset.dealId);
        const taskId = parseInt(btn.dataset.taskId);
        const independentTaskId = parseInt(btn.dataset.independentTaskId) || null;
        let products = [];
        try { products = JSON.parse(btn.dataset.products || '[]'); } catch (e) {}
        
        employeeState.isEditingCompletion = false;
        await openCompletionModal(dealId, taskId, notificationId, products, '', independentTaskId);
    }
    // ===== ДОБАВЛЕНИЕ / УДАЛЕНИЕ СОИСПОЛНИТЕЛЕЙ =====
    export async function openAddAssigneeModal(dealId, taskId) {
        try {
            const response = await fetch('/api/employees/list?active_only=true', { credentials: 'include' });
            if (!response.ok) throw new Error('Не удалось загрузить сотрудников');
            const employees = await response.json();
            const list = document.getElementById(`assignees-list-${taskId}`);
            if (!list) {
                showToast('Не найден список исполнителей', true);
                return;
            }
            const existingNames = list.textContent.split(',').map(value => value.trim()).filter(Boolean);
            const available = employees.filter(employee => employee.is_active === 1 && !existingNames.includes(employee.full_name));
            if (!available.length) {
                showToast('Нет доступных сотрудников для добавления', true);
                return;
            }

            const modal = document.getElementById('addAssigneeModal');
            const select = document.getElementById('assigneeSelect');
            select.replaceChildren(...available.map(employee => new Option(employee.full_name, employee.id)));
            modal.style.display = 'block';

            const closeModal = () => { modal.style.display = 'none'; };
            document.getElementById('closeAssigneeModal').onclick = closeModal;
            document.getElementById('cancelAssignBtn').onclick = closeModal;
            modal.onclick = event => { if (event.target === modal) closeModal(); };
            document.getElementById('confirmAssignBtn').onclick = async () => {
                const employeeId = Number(select.value);
                if (!employeeId) {
                    showToast('Выберите сотрудника', true);
                    return;
                }
                try {
                    const saveResponse = await fetch(`/api/employee/tasks/${taskId}/assignees`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ deal_id: Number(dealId), employee_id: employeeId }),
                        credentials: 'include'
                    });
                    if (!saveResponse.ok) throw new Error((await saveResponse.json()).detail || 'Ошибка');
                    showToast('Соисполнитель добавлен');
                    closeModal();
                    refreshTaskListWithoutClosing();
                } catch (error) {
                    showToast(error.message || 'Ошибка сети', true);
                }
            };
        } catch (error) {
            showToast(error.message || 'Ошибка сети', true);
        }
    }

    export async function removeAssignee(dealId, taskId, employeeId) {
        if (!confirm('Удалить этого соисполнителя?')) return;
        try {
            const resp = await fetch(`/api/employee/tasks/${taskId}/assignees/${employeeId}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ deal_id: parseInt(dealId) }),
                credentials: 'include'
            });
            if (resp.ok) {
                showToast('Соисполнитель удалён');
                refreshTaskListWithoutClosing();
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка', true);
            }
        } catch (err) {
            showToast('Ошибка сети', true);
        }
    }

export function refreshTaskListWithoutClosing() {
    loadTaskNotifications();
}

export async function taskBreak(notificationId) {
    try {
        const resp = await fetch(`/api/employee/tasks/${notificationId}/break`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });
        if (resp.ok) {
            showToast('⏸️ Задача на перерыве');
            loadTaskNotifications();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Ошибка', true);
        }
    } catch (err) {
        showToast('Ошибка сети', true);
    }
}

export async function taskResume(notificationId) {
    try {
        const resp = await fetch(`/api/employee/tasks/${notificationId}/resume`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });
        if (resp.ok) {
            showToast('▶️ Задача продолжена');
            loadTaskNotifications();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Ошибка', true);
        }
    } catch (err) {
        showToast('Ошибка сети', true);
    }
}

export function renderDefectTable() {
    const tbody = document.getElementById('defectTableBody');
    const rows = employeeState.completion.productTypes.map(product => {
        const row = createElement('tr', { dataset: { productTypeId: product.id } });
        row.append(
            createElement('td', { text: product.name }),
            createElement('td', { text: product.quantity }),
            createElement('td', {}, createElement('input', {
                className: 'defect-input defect-quantity-input',
                attrs: { type: 'number', min: 0, max: product.quantity, value: product.defect_quantity },
                dataset: { productId: product.id }
            })),
            createElement('td', {}, createElement('input', {
                className: 'defect-comment-input control-full-width',
                attrs: { type: 'text', value: product.defect_comment || '' },
                dataset: { productId: product.id }
            }))
        );
        return row;
    });
    tbody.replaceChildren(...rows);
}

export function renderDistributionTable() {
    const thead = document.querySelector('#distributionTable thead');
    const tbody = document.getElementById('distributionTableBody');
    const tfoot = document.getElementById('distributionTableFoot');
    const headerRow = createElement('tr');
    headerRow.append(createElement('th', { className: 'table-cell-left', text: 'Исполнитель' }));
    employeeState.completion.productTypes.forEach(product => {
        headerRow.append(createElement('th', { className: 'table-cell-left', text: product.name }));
    });
    headerRow.append(
        createElement('th', { className: 'percentage-heading', text: 'Выполнение, %' }),
        createElement('th', { className: 'points-heading', text: 'Баллы' })
    );
    thead.replaceChildren(headerRow);

    const bodyRows = employeeState.completion.assignees.map(assignee => {
        const row = createElement('tr', { dataset: { employeeId: assignee.employee_id } });
        row.append(createElement('td', {}, createElement('strong', { text: assignee.employee_name })));
        employeeState.completion.productTypes.forEach(product => {
            row.append(createElement('td', {}, createElement('input', {
                className: 'distribution-input',
                attrs: { type: 'number', min: 0, value: employeeState.completion.distributions[product.id]?.[assignee.employee_id] || 0 },
                dataset: { productId: product.id, employeeId: assignee.employee_id }
            })));
        });
        const percent = employeeState.completion.percentages[assignee.employee_id] || 0;
        row.append(
            createElement('td', { className: 'percentage-input-cell' }, createElement('input', {
                className: 'completion-percent-input completion-percentage-input',
                attrs: { type: 'number', min: 0, max: 100, step: 1, value: percent },
                dataset: { employeeId: assignee.employee_id }
            })),
            createElement('td', {
                className: 'employee-points-cell', text: Math.round(employeeState.completion.totalPoints * percent / 100),
                dataset: { employeeId: assignee.employee_id }
            })
        );
        return row;
    });
    tbody.replaceChildren(...bodyRows);

    const totalRow = createElement('tr');
    totalRow.append(createElement('td', {}, createElement('strong', { text: 'Итого' })));
    employeeState.completion.productTypes.forEach(product => {
        const total = employeeState.completion.assignees.reduce(
            (sum, assignee) => sum + (employeeState.completion.distributions[product.id]?.[assignee.employee_id] || 0), 0
        );
        const cell = createElement('td', { className: 'distribution-total-cell', dataset: { productId: product.id } });
        cell.append(createElement('span', { className: 'expected-quantity', text: product.quantity }));
        if (total !== product.quantity) cell.append(document.createTextNode(' '), createElement('span', { className: 'task-form-error', text: `(${total})` }));
        totalRow.append(cell);
    });
    totalRow.append(
        createElement('td', { className: 'percentage-summary-cell' }),
        createElement('td', { className: 'points-summary-cell' }, createElement('strong', { text: employeeState.completion.totalPoints }))
    );

    const totalPercent = Object.values(employeeState.completion.percentages).reduce((sum, value) => sum + Number(value || 0), 0);
    const percentRow = createElement('tr', { attrs: { id: 'completionPercentTotalRow' } });
    percentRow.append(
        createElement('td', {}, createElement('strong', { text: 'Итого (%)' })),
        createElement('td', {
            className: 'text-secondary',
            attrs: { colspan: Math.max(1, employeeState.completion.productTypes.length) }
        }, [document.createTextNode('Всего баллов за задачу: '), createElement('strong', { className: 'points-value', text: employeeState.completion.totalPoints })]),
        createElement('td', {
            className: `percentage-total ${totalPercent === 100 ? 'is-valid' : 'is-invalid'}`,
            text: `${totalPercent}%`, attrs: { id: 'completionPercentTotal' }
        }),
        createElement('td', { className: 'points-total', text: employeeState.completion.totalPoints })
    );
    tfoot.replaceChildren(totalRow, percentRow);
}

export function attachDefectHandlers() {
    // Изменение брака
    document.querySelectorAll('.defect-input').forEach(inp => {
        inp.removeEventListener('input', onDefectChange);
        inp.addEventListener('input', onDefectChange);
    });
    // Изменение комментария
    document.querySelectorAll('.defect-comment-input').forEach(inp => {
        inp.removeEventListener('input', onDefectCommentChange);
        inp.addEventListener('input', onDefectCommentChange);
    });
}

export async function onDefectChange(e) {
    const input = e.target;
    const productTypeId = parseInt(input.dataset.productId);
    const val = parseInt(input.value) || 0;
    // Обновляем локальные данные
    const pt = employeeState.completion.productTypes.find(p => p.id === productTypeId);
    if (pt) pt.defect_quantity = val;
    await saveCompletionForProduct(productTypeId);
    // Обновим итоги (перерисовать таблицу распределения? можно обновить только итоговую строку)
    updateDistributionTotals();
}

export async function onDefectCommentChange(e) {
    const input = e.target;
    const productTypeId = parseInt(input.dataset.productId);
    const val = input.value;
    const pt = employeeState.completion.productTypes.find(p => p.id === productTypeId);
    if (pt) pt.defect_comment = val;
    await saveCompletionForProduct(productTypeId);
}

export function attachDistributionHandlers() {
    document.querySelectorAll('.distribution-input').forEach(inp => {
        inp.removeEventListener('input', onDistributionChange);
        inp.addEventListener('input', onDistributionChange);
    });
    document.querySelectorAll('.completion-percent-input').forEach(inp => {
        inp.addEventListener('input', onCompletionPercentChange);
        inp.addEventListener('change', saveCompletionPercentages);
    });
}

export function onCompletionPercentChange(event) {
    const employeeId = Number(event.target.dataset.employeeId);
    const value = Math.max(0, Math.min(100, parseInt(event.target.value) || 0));
    event.target.value = value;
    employeeState.completion.percentages[employeeId] = value;
    const pointsCell = document.querySelector(`.employee-points-cell[data-employee-id="${employeeId}"]`);
    if (pointsCell) pointsCell.textContent = Math.round(employeeState.completion.totalPoints * value / 100);
    const total = Object.values(employeeState.completion.percentages).reduce((sum, item) => sum + Number(item || 0), 0);
    const totalCell = document.getElementById('completionPercentTotal');
    if (totalCell) {
        totalCell.textContent = `${total}%`;
        totalCell.style.color = total === 100 ? '#16a34a' : '#dc2626';
    }
}

export async function saveCompletionPercentages() {
    const percentages = employeeState.completion.assignees.map(item => ({
        employee_id: item.employee_id,
        percent: employeeState.completion.percentages[item.employee_id] || 0
    }));
    try {
        const response = await fetch(`/api/employee/tasks/${employeeState.completion.notificationId}/completion-percentages`, {
            method:'PUT', credentials:'include', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({percentages})
        });
        if (!response.ok) throw new Error((await response.json()).detail || 'Ошибка сохранения процентов');
        document.getElementById('completeError').innerText = '';
    } catch (error) {
        document.getElementById('completeError').innerText = error.message;
    }
}

export async function onDistributionChange(e) {
    const input = e.target;
    const productTypeId = parseInt(input.dataset.productId);
    const employeeId = parseInt(input.dataset.employeeId);
    const val = parseInt(input.value) || 0;
    // Обновляем локальные данные
    if (!employeeState.completion.distributions[productTypeId]) {
        employeeState.completion.distributions[productTypeId] = {};
    }
    employeeState.completion.distributions[productTypeId][employeeId] = val;
    await saveCompletionForProduct(productTypeId);
    // Обновим итоговую строку
    updateDistributionTotals();
}

export function updateDistributionTotals() {
    const tfoot = document.getElementById('distributionTableFoot');
    employeeState.completion.productTypes.forEach(pt => {
        const td = tfoot.querySelector(`td[data-product-id="${pt.id}"]`);
        if (td) {
            let total = 0;
            employeeState.completion.assignees.forEach(a => {
                total += (employeeState.completion.distributions[pt.id]?.[a.employee_id] || 0);
            });
            td.replaceChildren(createElement('span', { className: 'expected-quantity', text: pt.quantity }));
            if (total !== pt.quantity) td.append(document.createTextNode(' '), createElement('span', { className: 'task-form-error', text: `(${total})` }));
        }
    });
}
export async function saveCompletionForProduct(productTypeId) {
    if (employeeState.completionSaving) return;
    employeeState.completionSaving = true;
    try {
        const pt = employeeState.completion.productTypes.find(p => p.id === productTypeId);
        if (!pt) return;
        // Собираем распределения для этого типа товара
        const dists = employeeState.completion.assignees.map(a => ({
            employee_id: a.employee_id,
            quantity: employeeState.completion.distributions[productTypeId]?.[a.employee_id] || 0
        }));
        // Проверяем, что сумма распределений не превышает количество товара
        const totalDist = dists.reduce((sum, d) => sum + d.quantity, 0);
        if (totalDist > pt.quantity) {
            document.getElementById('completeError').innerText = '';
            updateDistributionTotals();
            employeeState.completionSaving = false;
            return;
        }
        const payload = {
            product_type_id: productTypeId,
            defect_quantity: pt.defect_quantity,
            defect_comment: pt.defect_comment,
            distributions: dists,
            general_comment: employeeState.completion.generalComment
        };
        // Используем эндпоинт сотрудника, который проверяет права основного исполнителя
        const resp = await fetch(`/api/employee/tasks/${employeeState.completion.notificationId}/completion`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            credentials: 'include'
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Ошибка сохранения');
        }
        // Убираем ошибку, если была
        document.getElementById('completeError').innerText = '';
        // Обновим итоги (сумма может измениться из-за бэка, но мы уже обновили локально)
    } catch (err) {
        document.getElementById('completeError').innerText = err.message;
        console.error(err);
    } finally {
        employeeState.completionSaving = false;
    }
}
document.getElementById('finalCompleteBtn').addEventListener('click', async function() {
    const btn = this;
    btn.disabled = true;
    document.getElementById('completeError').innerText = '';
    try {
        const percentTotal = employeeState.completion.assignees.reduce(
            (sum, assignee) => sum + Number(employeeState.completion.percentages[assignee.employee_id] || 0), 0
        );
        if (percentTotal !== 100) {
            document.getElementById('completeError').innerText = `Распределение выполнения должно составлять 100%. Сейчас: ${percentTotal}%.`;
            btn.disabled = false;
            return;
        }
        await saveCompletionPercentages();
        // Проверим, что все распределения заполнены корректно (сумма равна количеству для каждого товара)
        let allValid = true;
        for (const pt of employeeState.completion.productTypes) {
            const total = employeeState.completion.assignees.reduce((sum, a) => sum + (employeeState.completion.distributions[pt.id]?.[a.employee_id] || 0), 0);
            if (total !== pt.quantity) {
                allValid = false;
                break;
            }
        }
        if (!allValid) {
            updateDistributionTotals();
            btn.disabled = false;
            return;
        }

        // Если мы в режиме редактирования, нам не нужно менять статус задачи, она уже завершена
        if (employeeState.isEditingCompletion) {
            showToast('✅ Данные успешно исправлены!');
            document.getElementById('completeTaskModal').style.display = 'none';
            employeeState.isEditingCompletion = false; // Сбрасываем флаг
            loadTaskNotifications(); 
            return;
        }

        // Обычный режим: отправляем запрос на завершение задачи
        const resp = await fetch(`/api/employee/tasks/${employeeState.completion.notificationId}/complete`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Ошибка завершения задачи');
        }
        showToast('✅ Задача успешно завершена');
        document.getElementById('completeTaskModal').style.display = 'none';
        employeeState.isEditingCompletion = false; // Сбрасываем флаг
        loadTaskNotifications(); 
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Ошибка завершения задачи');
        }
        showToast('✅ Задача успешно завершена');
        document.getElementById('completeTaskModal').style.display = 'none';
        loadTaskNotifications(); // обновляем список задач
    } catch (err) {
        document.getElementById('completeError').innerText = err.message;
        btn.disabled = false;
    }
});
document.getElementById('cancelCompleteBtn').addEventListener('click', function() {
    document.getElementById('completeTaskModal').style.display = 'none';
    employeeState.isEditingCompletion = false;
});
document.querySelector('#completeTaskModal .close-complete-modal').addEventListener('click', function() {
    document.getElementById('completeTaskModal').style.display = 'none';
    employeeState.isEditingCompletion = false;
});
window.addEventListener('click', function(e) {
    const modal = document.getElementById('completeTaskModal');
    if (e.target === modal) modal.style.display = 'none';
});

export async function completeTaskSimple(notificationId) {
    if (!notificationId) {
        showToast('Ошибка: идентификатор уведомления не найден', true);
        return;
    }
    try {
        const resp = await fetch(`/api/employee/tasks/${notificationId}/complete`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });
        if (resp.ok) {
            showToast('✅ Задача выполнена');
            loadTaskNotifications();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Ошибка завершения', true);
        }
    } catch (err) {
        showToast('Ошибка сети', true);
    }
}

export function initTaskCreationModal() {
    const modal = document.getElementById('taskCreationModal');
    const openButton = document.getElementById('openTaskCreationBtn');
    const binding = document.getElementById('newTaskBinding');
    if (!modal || !openButton || openButton.dataset.initialized) return;
    openButton.dataset.initialized = '1';

    const close = () => { modal.style.display = 'none'; };
    const updateBindingFields = () => {
        const dealMode = binding.value === 'deal';
        document.getElementById('newTaskDealRow').style.display = dealMode ? 'block' : 'none';
        document.getElementById('newTaskTitleRow').style.display = dealMode ? 'none' : 'block';
        document.getElementById('newTaskDescriptionRow').style.display = dealMode ? 'none' : 'block';
    };
    openButton.addEventListener('click', async () => {
        if (!employeeState.canCreateTasks) return;
        const error = document.getElementById('newTaskCreationError');
        error.textContent = '';
        modal.style.display = 'block';
        try {
            const response = await fetchWithAuth('/api/sandbox/task-creation-options');
            if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось загрузить данные');
            const data = await response.json();
            document.getElementById('newTaskDeal').replaceChildren(...data.deals.filter(item => item.status !== 'completed').map(item => new Option(item.title, item.id)));
            document.getElementById('newTaskTemplate').replaceChildren(...data.tasks.map(item => new Option(item.name, item.id)));
            document.getElementById('newTaskEmployees').replaceChildren(...data.employees.map(item => {
                const checkboxId = `newTaskEmployee${item.id}`;
                return createElement('div', { className: 'task-choice-row' }, [
                    createElement('input', { className: 'new-task-employee', attrs: { type: 'checkbox', value: item.id, id: checkboxId } }),
                    createElement('label', { className: 'task-choice-label', text: item.name, attrs: { for: checkboxId } }),
                    createElement('label', { attrs: { title: 'Основной исполнитель' } }, [
                        createElement('input', { attrs: { type: 'radio', name: 'newTaskMainEmployee', value: item.id } }), document.createTextNode(' основной')
                    ])
                ]);
            }));
            const productRows = data.products.map(item => createElement('div', { className: 'product-choice-row' }, [
                createElement('input', { className: 'new-task-product', attrs: { type: 'checkbox', value: item.id }, dataset: { name: item.name } }),
                createElement('span', { text: item.name }),
                createElement('input', { className: 'new-task-product-quantity', attrs: { type: 'number', min: 1, value: 1, title: 'Количество' }, dataset: { productId: item.id } })
            ]));
            document.getElementById('newTaskProducts').replaceChildren(...(productRows.length ? productRows : [createElement('span', { className: 'text-secondary', text: 'Нет товаров' })]));
        } catch (errorValue) {
            error.textContent = errorValue.message;
        }
        updateBindingFields();
    });
    binding.addEventListener('change', updateBindingFields);
    document.getElementById('closeTaskCreationModal').addEventListener('click', close);
    document.getElementById('cancelTaskCreationBtn').addEventListener('click', close);
    modal.addEventListener('click', event => { if (event.target === modal) close(); });
    document.getElementById('newTaskEmployees').addEventListener('change', event => {
        if (event.target.name === 'newTaskMainEmployee') {
            const checkbox = modal.querySelector(`.new-task-employee[value="${event.target.value}"]`);
            if (checkbox) checkbox.checked = true;
        }
    });
    document.getElementById('saveTaskCreationBtn').addEventListener('click', async () => {
        const saveButton = document.getElementById('saveTaskCreationBtn');
        const error = document.getElementById('newTaskCreationError');
        const employeeIds = [...modal.querySelectorAll('.new-task-employee:checked')].map(item => Number(item.value));
        const mainEmployee = modal.querySelector('input[name="newTaskMainEmployee"]:checked');
        const products = [...modal.querySelectorAll('.new-task-product:checked')].map(item => ({
            id: Number(item.value),
            name: item.dataset.name,
            quantity: Math.max(1, Number(modal.querySelector(`.new-task-product-quantity[data-product-id="${item.value}"]`)?.value || 1))
        }));
        if (!employeeIds.length) { error.textContent = 'Выберите хотя бы одного сотрудника'; return; }
        if (!mainEmployee || !employeeIds.includes(Number(mainEmployee.value))) { error.textContent = 'Выберите основного исполнителя'; return; }
        const taskId = Number(document.getElementById('newTaskTemplate').value);
        if (!taskId) { error.textContent = 'Выберите задачу'; return; }
        const dealMode = binding.value === 'deal';
        const payload = dealMode ? {
            deal_id: Number(document.getElementById('newTaskDeal').value), task_id: taskId,
            employee_ids: employeeIds, main_employee_id: Number(mainEmployee.value), products
        } : {
            task_id: taskId, employee_ids: employeeIds, main_employee_id: Number(mainEmployee.value), products,
            title: document.getElementById('newTaskTitle').value.trim() || null,
            description: document.getElementById('newTaskDescription').value.trim() || null
        };
        if (dealMode && !payload.deal_id) { error.textContent = 'Выберите сделку'; return; }
        saveButton.disabled = true;
        error.textContent = '';
        try {
            const response = await fetchWithAuth(dealMode ? '/api/sandbox/task-assignments' : '/api/sandbox/independent-tasks', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось создать задачу');
            close();
            showToast('Задача создана');
            sessionStorage.removeItem(EMPLOYEE_STORAGE_KEYS.modal);
            sessionStorage.removeItem(EMPLOYEE_STORAGE_KEYS.modalState);
            window.location.reload();
        } catch (errorValue) {
            error.textContent = errorValue.message;
        } finally {
            saveButton.disabled = false;
        }
    });
}
initTaskCreationModal();
