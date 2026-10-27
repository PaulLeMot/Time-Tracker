import { employeeState } from './state.js';
import { showToast } from './core.js';
import { createElement, showMessage } from './dom.js';

let taskListLoader = null;

export function registerTaskListLoader(loader) {
    taskListLoader = loader;
}

// ========== УВЕДОМЛЕНИЯ СОТРУДНИКА ==========

    export async function loadNotifications() {
        try {
            const resp = await fetch('/api/employee/notifications', { credentials: 'include' });
            if (!resp.ok) throw new Error('Ошибка загрузки');
            const data = await resp.json();
            const badge = document.getElementById('notifBadge');
            if (badge) {
                const unansweredCount = data.filter(n => !n.has_explanation).length;
                badge.style.display = unansweredCount > 0 ? 'inline-block' : 'none';
                badge.innerText = unansweredCount;
            }
            renderNotifications(data);
            return data;
        } catch (err) {
            console.error(err);
            return [];
        }
    }

    export function renderNotifications(notifications) {
        const container = document.getElementById('notificationsContainer');
        if (!container) return;
        if (!notifications.length) {
            showMessage(container, 'Нет уведомлений');
            return;
        }
        const content = window.innerWidth <= 768
            ? createEmployeeNotificationCards(notifications)
            : createEmployeeNotificationTable(notifications);
        container.replaceChildren(content);
        bindEmployeeNotificationActions(container);
    }

    function notificationMeta(type) {
        return {
            reprimand: ['❌', 'Замечание'], warning: ['⚠️', 'Предупреждение'],
            commendation: ['✅', 'Похвала'], performance_review: ['⭐', 'Оценка работы']
        }[type] || ['', type || ''];
    }

    function createEmployeeNotificationTable(notifications) {
        const table = createElement('table', { className: 'report-table' });
        const header = createElement('tr');
        ['Тип', 'Сообщение', 'Дата', 'Статус объяснительной', 'Объяснительная', 'Действие']
            .forEach(label => header.append(createElement('th', { text: label })));
        table.append(createElement('thead', {}, header));
        const tbody = createElement('tbody');
        notifications.forEach(notification => {
            const [icon] = notificationMeta(notification.type);
            const row = createElement('tr', { className: notification.has_explanation ? 'notif-answered' : 'notif-pending' });
            const typeCell = createElement('td', { className: `notification-type notification-type-${notification.type}` });
            typeCell.append(document.createTextNode(icon));
            const grade = createGradeBadge(notification);
            if (grade) typeCell.append(grade);
            row.append(
                typeCell,
                createElement('td', { text: notification.message }),
                createElement('td', { text: new Date(notification.created_at).toLocaleString() }),
                createElement('td', { text: notification.has_explanation ? 'Отвечено' : 'Ожидает' }),
                createElement('td', {}, notification.has_explanation
                    ? createElement('span', { className: 'explanation-text', text: notification.explanation_text || '' }) : '—'),
                createElement('td', {}, createEmployeeNotificationAction(notification))
            );
            tbody.append(row);
        });
        table.append(tbody);
        return createElement('div', { className: 'recent-table' }, table);
    }

    function createEmployeeNotificationCards(notifications) {
        const accordion = createElement('div', { className: 'notifications-accordion' });
        notifications.forEach(notification => {
            const [icon, label] = notificationMeta(notification.type);
            const date = new Date(notification.created_at).toLocaleString();
            const item = createElement('div', {
                className: `notifications-accordion-item ${notification.has_explanation ? 'notif-answered' : 'notif-pending'}`,
                dataset: { id: notification.id }
            });
            const header = createElement('button', { className: 'notifications-accordion-header', attrs: { type: 'button' } },
                createElement('span', { className: 'notification-summary' }, [
                    createElement('span', { className: `notification-type notification-type-${notification.type}`, text: icon }),
                    createElement('span', { className: 'notification-date', text: date.split(',')[0] }),
                    createElement('span', { className: 'notification-preview', text: shorten(notification.message, 45) })
                ]));
            const details = createElement('div', { className: 'notifications-accordion-details' });
            appendNotificationDetail(details, 'Тип', `${icon} ${label}`, `notification-type notification-type-${notification.type}`);
            appendNotificationDetail(details, 'Дата', date);
            appendNotificationDetail(details, 'Статус', notification.has_explanation ? 'Отвечено' : 'Ожидает');
            appendNotificationDetail(details, 'Сообщение', notification.message);
            const grade = createGradeBadge(notification);
            if (grade) appendNotificationDetail(details, 'Оценка', grade);
            if (notification.has_explanation) {
                appendNotificationDetail(details, 'Объяснительная', createElement('div', { className: 'notif-explanation-text', text: notification.explanation_text || '' }));
            }
            const action = createEmployeeNotificationAction(notification, true);
            if (action.childNodes.length) appendNotificationDetail(details, 'Действие', action);
            header.addEventListener('click', event => {
                event.stopPropagation();
                const wasOpen = item.classList.contains('open');
                accordion.querySelectorAll('.notifications-accordion-item').forEach(card => card.classList.remove('open'));
                if (!wasOpen) item.classList.add('open');
            });
            item.append(header, details);
            accordion.append(item);
        });
        return accordion;
    }

    function createGradeBadge(notification) {
        const grade = notification.type === 'performance_review' ? notification.extra_data?.grade : null;
        if (!grade) return null;
        const labels = { red: '🔴 Неудовлетворительно', yellow: '🟡 Сойдёт, есть замечания', blue: '🔵 Всё ровно, так держать', green: '🟢 Молодец, ты супер!' };
        return createElement('div', { className: `notification-grade grade-${grade}`, text: labels[grade] || grade });
    }

    function createEmployeeNotificationAction(notification, mobile = false) {
        const wrapper = createElement('span');
        if (notification.has_explanation) return wrapper;
        if (notification.type === 'reprimand' || notification.type === 'performance_review') {
            wrapper.append(createElement('button', { className: `btn-sm ${mobile ? 'write-explanation' : 'write-explanation-desktop'}`, text: '✏️ Написать', dataset: { id: notification.id } }));
        } else if (notification.type === 'commendation' || (notification.type === 'warning' && notification.message !== 'Не был завершен рабочий день')) {
            wrapper.append(createElement('button', { className: 'btn-sm mark-as-read', text: '✅ Прочитано', dataset: { id: notification.id, type: notification.type } }));
        }
        if (notification.type === 'warning' && notification.message === 'Не был завершен рабочий день') {
            wrapper.append(createElement('button', {
                className: 'btn-sm fix-end-time', text: '✏️ Исправить',
                dataset: { id: notification.id, workdayDate: notificationWorkdayDate(notification) }
            }));
        }
        return wrapper;
    }

    function appendNotificationDetail(parent, label, value, valueClass = '') {
        const content = value instanceof Node ? value : document.createTextNode(String(value ?? ''));
        parent.append(createElement('div', { className: 'notif-detail-row' }, [
            createElement('div', { className: 'notif-detail-label', text: label }),
            createElement('div', { className: `notif-detail-value ${valueClass}`.trim() }, content)
        ]));
    }

    function shorten(value, length) {
        const text = String(value || '');
        return text.length > length ? `${text.slice(0, length - 3)}...` : text;
    }

    function notificationWorkdayDate(notification) {
        if (notification.extra_data?.workday_date) return notification.extra_data.workday_date;
        const created = new Date(notification.created_at);
        if (created.getHours() === 5 && created.getMinutes() === 0) created.setDate(created.getDate() - 1);
        return created.toISOString();
    }

    function bindEmployeeNotificationActions(container) {
        container.querySelectorAll('.write-explanation, .write-explanation-desktop').forEach(button => {
            button.addEventListener('click', event => { event.stopPropagation(); openExplanationModal(Number(button.dataset.id)); });
        });
        container.querySelectorAll('.mark-as-read').forEach(button => {
            button.addEventListener('click', event => { event.stopPropagation(); markAsRead(Number(button.dataset.id)); });
        });
        container.querySelectorAll('.fix-end-time').forEach(button => {
            button.addEventListener('click', event => {
                event.stopPropagation();
                const date = new Date(button.dataset.workdayDate);
                document.getElementById('fixEndDate').textContent = `${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}.${date.getFullYear()}`;
                document.getElementById('fixEndTime').value = '17:00';
                document.getElementById('fixEndError').textContent = '';
                const modal = document.getElementById('fixEndTimeModal');
                modal.dataset.entityId = button.dataset.id;
                modal.style.display = 'block';
                employeeState.currentFixNotificationId = button.dataset.id;
            });
        });
    }

    export function openExplanationModal(notificationId) {
        employeeState.currentNotificationId = notificationId;
        document.getElementById('explanationModal').dataset.entityId = notificationId;
        document.getElementById('explanationText').value = '';
        document.getElementById('explanationError').innerText = '';
        document.getElementById('explanationModal').style.display = 'block';
    };

    document.getElementById('submitExplanationBtn').addEventListener('click', async () => {
        const text = document.getElementById('explanationText').value.trim();
        if (!text) {
            document.getElementById('explanationError').innerText = 'Введите текст объяснительной';
            return;
        }
        try {
            const resp = await fetch(`/api/employee/notifications/${employeeState.currentNotificationId}/explanation`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ explanation_text: text }),
                credentials: 'include'
            });
            if (resp.ok) {
                showToast('Объяснительная отправлена');
                document.getElementById('explanationModal').style.display = 'none';
                await loadNotifications();
            } else {
                const err = await resp.json();
                document.getElementById('explanationError').innerText = err.detail || 'Ошибка отправки';
            }
        } catch (err) {
            document.getElementById('explanationError').innerText = 'Ошибка соединения';
        }
    });

    document.querySelector('.close-explanation').addEventListener('click', () => document.getElementById('explanationModal').style.display = 'none');
    window.addEventListener('click', (e) => {
        const expModal = document.getElementById('explanationModal');
        if (e.target === expModal) expModal.style.display = 'none';
    });

    // ========== ОТПРАВКА УВЕДОМЛЕНИЙ (монитор/админ) ==========
    let currentNotifyEmployeeName = '';

    export function openNotificationModal(empId, empName) {
        employeeState.currentNotifyEmployeeId = empId;
        document.getElementById('createNotificationModal').dataset.entityId = empId;
        currentNotifyEmployeeName = empName;
        document.getElementById('notifyEmployeeName').innerText = empName;
        document.getElementById('notifMessage').value = '';
        document.getElementById('createNotifError').innerText = '';
        document.getElementById('createNotificationModal').style.display = 'block';
    }

    document.getElementById('sendNotificationBtn').addEventListener('click', async () => {
        const type = document.getElementById('notifType').value;
        const message = document.getElementById('notifMessage').value.trim();
        if (!message) {
            document.getElementById('createNotifError').innerText = 'Введите сообщение';
            return;
        }
        try {
            const resp = await fetch('/api/admin/notifications/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ employee_id: employeeState.currentNotifyEmployeeId, type, message }),
                credentials: 'include'
            });
            if (resp.ok) {
                showToast('✅ Черновик уведомления создан. Админ может утвердить его.');
                document.getElementById('createNotificationModal').style.display = 'none';
            } else {
                const err = await resp.json();
                document.getElementById('createNotifError').innerText = err.detail || 'Ошибка отправки';
            }
        } catch (err) {
            document.getElementById('createNotifError').innerText = 'Ошибка сети';
        }
    });

    document.querySelector('.close-create-notif').addEventListener('click', () => {
        document.getElementById('createNotificationModal').style.display = 'none';
    });
    window.addEventListener('click', (e) => {
        const modal = document.getElementById('createNotificationModal');
        if (e.target === modal) modal.style.display = 'none';
    });

    // ========== ИСПРАВЛЕНИЕ ВРЕМЕНИ ==========
    document.getElementById('submitFixEndBtn').addEventListener('click', async () => {
        const time = document.getElementById('fixEndTime').value;
        if (!time) {
            document.getElementById('fixEndError').innerText = 'Выберите время';
            return;
        }
        const dateStr = document.getElementById('fixEndDate').innerText; // DD.MM.YYYY
        const [day, month, year] = dateStr.split('.');
        const isoDate = `${year}-${month}-${day}`;
        const proposedDateTime = `${isoDate}T${time}:00`;
        try {
            const resp = await fetch(`/api/employee/notifications/${employeeState.currentFixNotificationId}/propose-end-time`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ proposed_end_time: proposedDateTime }),
                credentials: 'include'
            });
            if (resp.ok) {
                showToast('Предложение отправлено администратору');
                document.getElementById('fixEndTimeModal').style.display = 'none';
                loadNotifications();
            } else {
                const err = await resp.json();
                document.getElementById('fixEndError').innerText = err.detail || 'Ошибка';
            }
        } catch (err) {
            document.getElementById('fixEndError').innerText = 'Ошибка сети';
        }
    });

    document.querySelector('#fixEndTimeModal .close-fix-end').addEventListener('click', () => {
        document.getElementById('fixEndTimeModal').style.display = 'none';
    });
    window.addEventListener('click', (e) => {
        const fixModal = document.getElementById('fixEndTimeModal');
        if (e.target === fixModal) fixModal.style.display = 'none';
    });

    // ========== ПРОСМОТР ОБЪЯСНИТЕЛЬНОЙ ==========
    document.querySelector('#explanationViewModal .close-explanation-view').addEventListener('click', () => {
        document.getElementById('explanationViewModal').style.display = 'none';
    });
    window.addEventListener('click', (e) => {
        const modal = document.getElementById('explanationViewModal');
        if (e.target === modal) modal.style.display = 'none';
    });

    // ========== УВЕДОМЛЕНИЯ (админ/монитор) ==========

    export async function loadAllNotifications() {
        const container = document.getElementById('allNotificationsContainer');
        const status = document.getElementById('allNotifStatusFilter').value;
        let url = '/api/admin/notifications';
        const params = new URLSearchParams();
        if (status) params.append('status', status);
        if (allNotifEmployeeId) params.append('employee_id', allNotifEmployeeId);
        if (allNotifStartDate) params.append('start_date', allNotifStartDate);
        if (allNotifEndDate) params.append('end_date', allNotifEndDate);
        if (params.toString()) url += '?' + params.toString();
        try {
            const resp = await fetch(url, { credentials: 'include' });
            if (!resp.ok) throw new Error('Ошибка загрузки');
            const data = await resp.json();
            renderAllNotifications(data);
        } catch (err) {
            showMessage(container, `Ошибка: ${err.message}`, 'error');
        }
    }

    export function renderAllNotifications(notifications) {
        const container = document.getElementById('allNotificationsContainer');
        if (!notifications.length) {
            showMessage(container, 'Нет уведомлений');
            return;
        }
        const content = window.innerWidth <= 768
            ? createAllNotificationCards(notifications)
            : createAllNotificationTable(notifications);
        container.replaceChildren(content);
        bindAdminNotificationActions(container);
    }

    function createAllNotificationTable(notifications) {
        const table = createElement('table', { className: 'report-table' });
        const header = createElement('tr');
        ['ФИО', 'Тип', 'Дата', 'Сообщение', 'Объяснительная', 'Статус', 'Действия']
            .forEach(label => header.append(createElement('th', { text: label })));
        table.append(createElement('thead', {}, header));
        const tbody = createElement('tbody');
        notifications.forEach(notification => {
            const [icon] = notificationMeta(notification.type);
            const row = createElement('tr');
            [notification.full_name, icon, formatNotificationDate(notification.created_at), notification.message, notification.explanation || '—', notificationStatus(notification.status)]
                .forEach(value => row.append(createElement('td', { text: value })));
            row.append(createElement('td', {}, createAdminNotificationActions(notification)));
            tbody.append(row);
        });
        table.append(tbody);
        return createElement('div', { className: 'recent-table' }, table);
    }

    function createAllNotificationCards(notifications) {
        const accordion = createElement('div', { className: 'notifications-accordion' });
        notifications.forEach(notification => {
            const [icon, typeLabel] = notificationMeta(notification.type);
            const item = createElement('div', { className: 'notifications-accordion-item', dataset: { id: notification.id } });
            const header = createElement('button', { className: 'notifications-accordion-header', attrs: { type: 'button' } }, [
                createElement('span', { className: `notification-type notification-type-${notification.type}`, text: icon }),
                createElement('span', { text: notification.full_name })
            ]);
            const details = createElement('div', { className: 'notifications-accordion-details' });
            appendNotificationDetail(details, 'Тип', typeLabel);
            appendNotificationDetail(details, 'Статус', notificationStatus(notification.status));
            appendNotificationDetail(details, 'Дата', formatNotificationDate(notification.created_at));
            appendNotificationDetail(details, 'Сообщение', notification.message);
            appendNotificationDetail(details, 'Объяснительная', notification.explanation || '—');
            appendNotificationDetail(details, 'Действия', createAdminNotificationActions(notification));
            header.addEventListener('click', () => item.classList.toggle('open'));
            item.append(header, details);
            accordion.append(item);
        });
        return accordion;
    }

    function createAdminNotificationActions(notification) {
        const actions = createElement('span', { className: 'notification-action-buttons' });
        if (notification.status !== 'draft' || employeeState.isAdmin !== true) {
            actions.append(createElement('span', { className: 'text-disabled', text: '—' }));
            return actions;
        }
        [['edit-notif', '✏️'], ['approve-notif', '✅'], ['reject-notif', '❌']].forEach(([className, label]) => {
            actions.append(createElement('button', { className: `btn-sm ${className}`, text: label, dataset: { id: notification.id } }));
        });
        return actions;
    }

    function notificationStatus(status) {
        return status === 'draft' ? 'Черновик' : status === 'sent' ? 'Отправлено' : 'Отклонено';
    }

    function formatNotificationDate(value) {
        return value ? new Date(value).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
    }

    function bindAdminNotificationActions(container) {
        container.querySelectorAll('.edit-notif').forEach(button => button.addEventListener('click', event => {
            event.stopPropagation(); openEditNotificationModal(Number(button.dataset.id));
        }));
        container.querySelectorAll('.approve-notif').forEach(button => button.addEventListener('click', event => {
            event.stopPropagation(); approveNotification(Number(button.dataset.id));
        }));
        container.querySelectorAll('.reject-notif').forEach(button => button.addEventListener('click', event => {
            event.stopPropagation(); rejectNotification(Number(button.dataset.id));
        }));
    }

    export async function openEditNotificationModal(notifId) {
        employeeState.currentEditNotificationId = notifId;
        const resp = await fetch('/api/admin/notifications', { credentials: 'include' });
        const list = await resp.json();
        const notif = list.find(n => n.id === notifId);
        if (!notif) return;
        // Для простоты, если нет модалки редактирования, можно использовать prompt
        const newType = prompt('Тип (reprimand/warning/commendation/performance_review):', notif.type);
        if (newType === null) return;
        const newMessage = prompt('Сообщение:', notif.message);
        if (newMessage === null) return;
        try {
            const resp2 = await fetch(`/api/admin/notifications/${notifId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: newType, message: newMessage }),
                credentials: 'include'
            });
            if (resp2.ok) {
                showToast('Уведомление обновлено');
                loadAllNotifications();
            } else {
                const err = await resp2.json();
                showToast(err.detail || 'Ошибка', true);
            }
        } catch (err) {
            showToast('Ошибка сети', true);
        }
    }

    export async function approveNotification(id) {
        if (!confirm('Утвердить уведомление?')) return;
        const resp = await fetch(`/api/admin/notifications/${id}/approve`, { method: 'POST', credentials: 'include' });
        if (resp.ok) {
            showToast('Утверждено');
            loadAllNotifications();
            loadNotifications();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Ошибка', true);
        }
    }

    export async function rejectNotification(id) {
        if (!confirm('Отклонить уведомление?')) return;
        const resp = await fetch(`/api/admin/notifications/${id}/reject`, { method: 'POST', credentials: 'include' });
        if (resp.ok) {
            showToast('Отклонено');
            loadAllNotifications();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Ошибка', true);
        }
    }

    export async function viewExplanation(notifId) {
        try {
            const resp = await fetch(`/api/admin/notifications/${notifId}/explanation`, { credentials: 'include' });
            if (!resp.ok) throw new Error('Объяснительная не найдена');
            const data = await resp.json();
            document.getElementById('explanationTextDisplay').innerText = data.explanation_text;
            document.getElementById('explanationViewModal').style.display = 'block';
        } catch (err) {
            showToast(err.message, true);
        }
    }

    // Фильтры для "всех уведомлений"
    let allNotifStartDate = '', allNotifEndDate = '', allNotifEmployeeId = '';

    document.getElementById('allNotifStatusFilter').addEventListener('change', loadAllNotifications);
    document.getElementById('allNotifEmployeeFilter').addEventListener('change', function() {
        allNotifEmployeeId = this.value;
        loadAllNotifications();
    });
    document.getElementById('refreshAllNotifBtn').addEventListener('click', loadAllNotifications);

    const allNotifDateRangeInput = document.getElementById('allNotifDateRange');
    flatpickr(allNotifDateRangeInput, {
        mode: "range",
        dateFormat: "Y-m-d",
        onChange: function(selectedDates, dateStr, instance) {
            if (selectedDates.length === 2) {
                allNotifStartDate = instance.formatDate(selectedDates[0], "Y-m-d");
                allNotifEndDate = instance.formatDate(selectedDates[1], "Y-m-d");
            } else {
                allNotifStartDate = '';
                allNotifEndDate = '';
            }
            loadAllNotifications();
        }
    });
    document.getElementById('clearAllNotifDateFilterBtn').addEventListener('click', () => {
        const picker = document.getElementById('allNotifDateRange')._flatpickr;
        if (picker) picker.clear();
        allNotifStartDate = '';
        allNotifEndDate = '';
        loadAllNotifications();
    });

    // Загрузка сотрудников для фильтра уведомлений
    export async function loadEmployeesForAllNotif() {
        try {
            const resp = await fetch('/api/employees?active_only=false', { credentials: 'include' });
            if (!resp.ok) throw new Error('Ошибка загрузки');
            let employees = await resp.json();
            employees.sort((a,b) => a.full_name.localeCompare(b.full_name, 'ru'));
            const select = document.getElementById('allNotifEmployeeFilter');
            if (select) {
                select.innerHTML = '<option value="">Все</option>';
                employees.forEach(emp => {
                    const option = document.createElement('option');
                    option.value = emp.id;
                    option.textContent = emp.full_name;
                    select.appendChild(option);
                });
            }
        } catch (err) {
            console.error(err);
        }
    }

    // ========== МЕТКА "ПРОЧИТАНО" ==========
    export async function markAsRead(notificationId) {
        try {
            const resp = await fetch(`/api/employee/notifications/${notificationId}/explanation`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ explanation_text: 'Прочитано' }),
                credentials: 'include'
            });
            if (resp.ok) {
                showToast('Уведомление отмечено как прочитанное');
                loadNotifications();
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка', true);
            }
        } catch (err) {
            showToast('Ошибка сети', true);
        }
    }

    // ========== SSE для уведомлений ==========
    let employeeEventSource = null;
    export function connectEmployeeSSE() {
        if (employeeEventSource) employeeEventSource.close();
        employeeEventSource = new EventSource('/api/employee/events', { withCredentials: true });
        employeeEventSource.addEventListener('update', () => {
            console.log('Обновление уведомлений');
            loadNotifications();
            taskListLoader?.();
        });
        employeeEventSource.onerror = () => {
            employeeEventSource.close();
            setTimeout(connectEmployeeSSE, 5000);
        };
    }
