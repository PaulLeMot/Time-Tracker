/**
 * Модуль админ-панели: Уведомления и запросы на изменение отметок.
 * Подключается через main.js и использует явные ES module зависимости.
 */
import { adminState } from './state.js';
import { showToast } from './core.js';
import { loadRecentEntries, refreshCurrentReport, renderCurrentRoles } from './actions.js';
import { createElement, showMessage } from './dom.js';

const roleModal = document.getElementById('roleModal');
const roleSelect = document.getElementById('roleSelect');
const newRoleNameInput = document.getElementById('newRoleNameInput');
const roleModalEmployeeFullName = document.getElementById('roleModalEmployeeFullName');
const roleModalError = document.getElementById('roleModalError');


export async function loadNotifications() {
    const container = document.getElementById('notificationsContainer');
    const status = document.getElementById('notifStatusFilter').value;
    const employeeId = document.getElementById('notifEmployeeFilter').value;
    
    let url = '/api/admin/notifications';
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (employeeId) params.append('employee_id', employeeId);
    if (adminState.notificationStartDate) params.append('start_date', adminState.notificationStartDate);
    if (adminState.notificationEndDate) params.append('end_date', adminState.notificationEndDate);
    if (params.toString()) url += '?' + params.toString();
    
    try {
        const resp = await fetch(url, { credentials: 'include' });
        if (!resp.ok) throw new Error('Ошибка загрузки');
        const data = await resp.json();
        renderNotifications(data);
    } catch (err) {
        showMessage(container, `Ошибка: ${err.message}`, 'error');
    }
}

export function renderNotifications(notifications) {
    const container = document.getElementById('notificationsContainer');
    if (!notifications.length) {
        showMessage(container, 'Нет уведомлений');
        return;
    }
    const table = createElement('table', { className: 'report-table' });
    const header = createElement('tr');
    ['ФИО', 'Тип', 'Дата создания', 'Автор', 'Сообщение', 'Объяснительная', 'Статус', 'Действия']
        .forEach(label => header.append(createElement('th', { text: label })));
    table.append(createElement('thead', {}, header));
    const tbody = createElement('tbody');
    notifications.forEach(notification => {
        const icon = { reprimand: '❌', warning: '⚠️', commendation: '✅', performance_review: '⭐' }[notification.type] || '';
        const typeCell = createElement('td', { text: icon });
        const grade = notification.type === 'performance_review' ? notification.extra_data?.grade : null;
        if (grade) {
            const labels = { red: '🔴 Неудовлетворительно', yellow: '🟡 Сойдёт, есть замечания', blue: '🔵 Всё ровно, так держать', green: '🟢 Молодец, ты супер!' };
            typeCell.append(createElement('div', { className: 'notification-grade-label', text: labels[grade] || grade }));
        }
        const employeeButton = createElement('button', {
            className: 'employee-recent-link', text: notification.full_name, attrs: { type: 'button' },
            dataset: { employeeId: notification.employee_id, employeeName: notification.full_name }
        });
        const created = notification.created_at
            ? new Date(notification.created_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
        tbody.append(createElement('tr', {}, [
            createElement('td', {}, employeeButton), typeCell, createElement('td', { text: created }),
            createElement('td', { text: notification.created_by || '—' }), createElement('td', { text: notification.message }),
            createElement('td', { text: notification.explanation || '—' }),
            createElement('td', { text: notification.status === 'draft' ? 'Черновик' : notification.status === 'sent' ? 'Отправлено' : 'Отклонено' }),
            createElement('td', {}, createNotificationActions(notification))
        ]));
    });
    table.append(tbody);
    container.replaceChildren(createElement('div', { className: 'recent-table' }, table));
    container.querySelectorAll('.approve-end').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const notifId = btn.dataset.id;
            const proposedTime = btn.dataset.time;
            if (!confirm(`Утвердить завершение дня в ${new Date(proposedTime).toLocaleString()}?`)) return;
            try {
                const resp = await fetch(`/api/admin/notifications/${notifId}/approve-end-time`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ end_time: proposedTime }),
                    credentials: 'include'
                });
                if (resp.ok) {
                    showToast('Время завершения обновлено');
                    loadNotifications(); // перезагрузить таблицу
                } else {
                    const err = await resp.json();
                    showToast(err.detail || 'Ошибка', true);
                }
            } catch (err) {
                showToast('Ошибка сети', true);
            }
        });
    });

    // Обработчик отклонения предложения
    container.querySelectorAll('.reject-end').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const notifId = btn.dataset.id;
            if (!confirm('Отклонить предложение?')) return;
            try {
                const resp = await fetch(`/api/admin/notifications/${notifId}/proposed-time`, {
                    method: 'DELETE',
                    credentials: 'include'
                });
                if (resp.ok) {
                    showToast('Предложение отклонено');
                    loadNotifications();
                } else {
                    const err = await resp.json();
                    showToast(err.detail || 'Ошибка', true);
                }
            } catch (err) {
                showToast('Ошибка сети', true);
            }
        });
    });

    // Обработчик редактирования предложения (открыть модалку)
    container.querySelectorAll('.edit-end').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const notifId = btn.dataset.id;
            const currentTime = btn.dataset.time;
            openEditProposedTimeModal(notifId, currentTime);
        });
    });
    container.querySelectorAll('.delete-notif').forEach(btn => {
        btn.addEventListener('click', () => deleteNotification(parseInt(btn.dataset.id)));
    });
    document.querySelectorAll('.edit-notif').forEach(btn => {
        btn.addEventListener('click', () => openEditNotificationModal(parseInt(btn.dataset.id)));
    });
    document.querySelectorAll('.approve-notif').forEach(btn => {
        btn.addEventListener('click', () => approveNotification(parseInt(btn.dataset.id)));
    });
    document.querySelectorAll('.reject-notif').forEach(btn => {
        btn.addEventListener('click', () => rejectNotification(parseInt(btn.dataset.id)));
    });
}


function createNotificationActions(notification) {
    const actions = createElement('div', { className: 'notification-actions' });
    actions.append(
        createActionButton('edit-notif', '✏️', notification.id),
        createActionButton('delete-notif', '🗑️', notification.id)
    );
    if (notification.status === 'draft') {
        if (!notification.extra_data?.proposed_end_time) actions.append(createActionButton('approve-notif', '✅', notification.id));
        actions.append(createActionButton('reject-notif', '❌', notification.id));
    } else {
        actions.append(createElement('span', { className: 'text-disabled', text: '—' }));
    }
    const proposedTime = notification.extra_data?.proposed_end_time;
    if (proposedTime) {
        actions.append(
            createActionButton('approve-end', '✅ Утвердить', notification.id, proposedTime),
            createActionButton('edit-end', '✏️ Ред.', notification.id, proposedTime),
            createActionButton('reject-end', '❌ Отклонить', notification.id)
        );
    }
    return actions;
}

function createActionButton(className, label, id, time = null) {
    return createElement('button', { className: `btn-sm ${className}`, text: label, attrs: { type: 'button' }, dataset: { id, time } });
}

export async function openEditNotificationModal(notifId) {
    adminState.currentEditNotificationId = notifId;
    document.getElementById('editNotificationModal').dataset.entityId = notifId;
    const resp = await fetch(`/api/admin/notifications`, { credentials: 'include' });
    const list = await resp.json();
    const notif = list.find(n => n.id === notifId);
    if (!notif) return;
    document.getElementById('editNotifType').value = notif.type;
    document.getElementById('editNotifMessage').value = notif.message;
    const empSelect = document.getElementById('editNotifEmployee');
    const explanationTextarea = document.getElementById('editNotifExplanation');
    if (explanationTextarea) {
        explanationTextarea.value = notif.explanation || '';
    }
    if (empSelect && allEmployees.length) {
        empSelect.value = notif.employee_id;
    }
    document.getElementById('editNotificationModal').style.display = 'block';
}

export async function saveEditedNotification() {
    const newType = document.getElementById('editNotifType').value;
    const newMessage = document.getElementById('editNotifMessage').value.trim();
    const newEmployeeId = document.getElementById('editNotifEmployee').value;
    const newExplanation = document.getElementById('editNotifExplanation').value.trim();

    if (!newMessage) {
        document.getElementById('editNotifError').innerText = 'Сообщение не может быть пустым';
        return;
    }
    if (!newEmployeeId) {
        document.getElementById('editNotifError').innerText = 'Выберите сотрудника';
        return;
    }
    try {
        const resp = await fetch(`/api/admin/notifications/${adminState.currentEditNotificationId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: newType,
                message: newMessage,
                employee_id: parseInt(newEmployeeId)
            }),
            credentials: 'include'
        });

        if (!resp.ok) {
            const err = await resp.json();
            document.getElementById('editNotifError').innerText = err.detail || 'Ошибка обновления уведомления';
            return;
        }

        // Работа с объяснительной
        if (newExplanation !== '') {
            // Если поле не пустое – сохраняем или обновляем
            let expResp = await fetch(`/api/admin/notifications/${adminState.currentEditNotificationId}/explanation`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ explanation_text: newExplanation }),
                credentials: 'include'
            });
            if (expResp.status === 404) {
                expResp = await fetch(`/api/admin/notifications/${adminState.currentEditNotificationId}/explanation`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ explanation_text: newExplanation }),
                    credentials: 'include'
                });
            }
            if (!expResp.ok) {
                const err = await expResp.json();
                document.getElementById('editNotifError').innerText = err.detail || 'Ошибка сохранения объяснительной';
                return;
            }
        } else {
            const delResp = await fetch(`/api/admin/notifications/${adminState.currentEditNotificationId}/explanation`, {
                method: 'DELETE',
                credentials: 'include'
            });
            if (!delResp.ok && delResp.status !== 404) {
                const err = await delResp.json();
                document.getElementById('editNotifError').innerText = err.detail || 'Ошибка удаления объяснительной';
                return;
            }
        }

        showToast('Уведомление обновлено');
        document.getElementById('editNotificationModal').style.display = 'none';
        await loadNotifications();
        updateDraftBadge();

    } catch (err) {
        document.getElementById('editNotifError').innerText = 'Ошибка сети';
    }
}

export async function approveNotification(id) {
    if (!confirm('Утвердить уведомление? Оно станет доступно сотруднику.')) return;
    const resp = await fetch(`/api/admin/notifications/${id}/approve`, { method: 'POST', credentials: 'include' });
    if (resp.ok) {
        showToast('Уведомление утверждено');
        loadNotifications();
        updateDraftBadge();
    } else {
        const err = await resp.json();
        showToast(err.detail || 'Ошибка', true);
    }
}

export async function rejectNotification(id) {
    if (!confirm('Отклонить уведомление?')) return;
    const resp = await fetch(`/api/admin/notifications/${id}/reject`, { method: 'POST', credentials: 'include' });
    if (resp.ok) {
        showToast('Уведомление отклонено');
        loadNotifications();
        updateDraftBadge();
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

document.querySelector('#editNotificationModal .close-edit-notif')?.addEventListener('click', () => {
    document.getElementById('editNotificationModal').style.display = 'none';
});
document.querySelector('#explanationViewModal .close-explanation-view')?.addEventListener('click', () => {
    document.getElementById('explanationViewModal').style.display = 'none';
});
document.getElementById('saveNotifEditBtn')?.addEventListener('click', saveEditedNotification);
document.getElementById('refreshNotificationsBtn')?.addEventListener('click', loadNotifications);
document.getElementById('notifStatusFilter')?.addEventListener('change', loadNotifications);
document.getElementById('notifEmployeeFilter').addEventListener('change', loadNotifications);
document.addEventListener('click', function(event) {
    if (event.target.classList && event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
});

let currentNotifyEmployeeId = null;
let currentNotifyEmployeeName = '';

export function openNotificationModal(empId, empName) {
    currentNotifyEmployeeId = empId;
    currentNotifyEmployeeName = empName;
    const nameSpan = document.getElementById('notifyEmployeeName');
    if (nameSpan) nameSpan.innerText = empName;
    const msgField = document.getElementById('notifMessage');
    if (msgField) msgField.value = '';
    const errorDiv = document.getElementById('createNotifError');
    if (errorDiv) errorDiv.innerText = '';
    const modal = document.getElementById('createNotificationModal');
    if (modal) modal.style.display = 'block';
};

export async function sendNotification() {
    const type = document.getElementById('notifType').value;
    const message = document.getElementById('notifMessage').value.trim();
    if (!message) {
        document.getElementById('createNotifError').innerText = 'Введите сообщение';
        return;
    }

    let grade = null;
    if (type === 'performance_review') {
        const selected = document.querySelector('input[name="grade"]:checked');
        if (!selected) {
            document.getElementById('createNotifError').innerText = 'Выберите оценку';
            return;
        }
        grade = selected.value;
    }

    try {
        const resp = await fetch('/api/admin/notifications/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                employee_id: currentNotifyEmployeeId,
                type: type,
                message: message,
                grade: grade
            }),
            credentials: 'include'
        });
        if (resp.ok) {
            showToast('✅ Уведомление создано (черновик)', false);
            document.getElementById('createNotificationModal').style.display = 'none';
            updateDraftBadge();
        } else {
            const err = await resp.json();
            document.getElementById('createNotifError').innerText = err.detail || 'Ошибка отправки';
        }
    } catch (err) {
        document.getElementById('createNotifError').innerText = 'Ошибка сети';
    }
};
document.getElementById('notifType').addEventListener('change', function() {
    const gradeContainer = document.getElementById('gradeContainer');
    if (this.value === 'performance_review') {
        gradeContainer.style.display = 'block';
    } else {
        gradeContainer.style.display = 'none';
        const checked = document.querySelector('input[name="grade"]:checked');
        if (checked) checked.checked = false;
    }
});
document.getElementById('sendNotificationBtn')?.addEventListener('click', sendNotification);
document.querySelector('.close-create-notif')?.addEventListener('click', () => {
    document.getElementById('createNotificationModal').style.display = 'none';
    document.getElementById('notifyEmployeeName').innerText = '—';
});
window.addEventListener('click', (e) => {
    const modal = document.getElementById('createNotificationModal');
    if (e.target === modal) modal.style.display = 'none';
});
window.addEventListener('beforeunload', function() {
    if (adminState.eventSource) adminState.eventSource.close();
});

export async function loadEmployeeListForFilter() {
    try {
        const resp = await fetch('/api/employees?active_only=false', { credentials: 'include' });
        if (!resp.ok) throw new Error('Ошибка загрузки сотрудников');
        let employees = await resp.json();
        employees.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
        const select = document.getElementById('notifEmployeeFilter');
        select.innerHTML = '<option value="">Все</option>';
        employees.forEach(emp => {
            const option = document.createElement('option');
            option.value = emp.id;
            option.textContent = emp.full_name;
            select.appendChild(option);
        });
    } catch (err) {
        console.error('Ошибка загрузки списка сотрудников', err);
    }
}
export async function loadRecentEmployeeFilter() {
    try {
        const resp = await fetch('/api/employees?active_only=false', { credentials: 'include' });
        if (!resp.ok) throw new Error('Ошибка загрузки сотрудников');
        let employees = await resp.json();
        employees.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
        const select = document.getElementById('recentEmployeeFilter');
        select.innerHTML = '<option value="">Все</option>';
        employees.forEach(emp => {
            const option = document.createElement('option');
            option.value = emp.id;
            option.textContent = emp.full_name;
            select.appendChild(option);
        });
    } catch (err) {
        console.error('Ошибка загрузки списка сотрудников', err);
    }
}
export async function goToEmployeeRecentEntries(employeeId, employeeName) {
    const recentTabBtn = document.querySelector('.tab-btn[data-tab="recent"]');
    if (!recentTabBtn) {
        console.error('Вкладка "Последние отметки" не найдена');
        return;
    }
    recentTabBtn.click();

    setTimeout(() => {
        adminState.recentEmployeeId = employeeId;
        const select = document.getElementById('recentEmployeeFilter');
        if (select) select.value = employeeId;

        const clearBtn = document.getElementById('clearRecentDateFilterBtn');
        if (clearBtn) {
            clearBtn.click();
        } else {
            adminState.recentStartDate = '';
            adminState.recentEndDate = '';
            const picker = document.getElementById('recentDateRange');
            if (picker && picker._flatpickr) picker._flatpickr.clear();
        }

        const limit = document.getElementById('recentLimit').value;
        loadRecentEntries(parseInt(limit));
    }, 200);
};
export async function updateDraftBadge() {
    try {
        const resp = await fetch('/api/admin/notifications?status=draft', { credentials: 'include' });
        if (!resp.ok) return;
        const data = await resp.json();
        const draftCount = data.length;
        const badge = document.getElementById('draftBadge');
        if (badge) {
            if (draftCount > 0) {
                badge.textContent = draftCount;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
    } catch (err) {
        console.error('Ошибка загрузки количества черновиков', err);
    }
}

export async function loadEmployeesForSelect() {
    try {
        const resp = await fetch('/api/employees?active_only=true');
        if (!resp.ok) throw new Error();
        allEmployees = await resp.json();
        allEmployees.sort((a,b) => a.full_name.localeCompare(b.full_name));
        const select = document.getElementById('editNotifEmployee');
        if (select) {
            select.innerHTML = '<option value="">Выберите сотрудника</option>';
            allEmployees.forEach(emp => {
                const opt = document.createElement('option');
                opt.value = emp.id;
                opt.textContent = emp.full_name;
                select.appendChild(opt);
            });
        }
    } catch(err) { console.error(err); }
}

export async function deleteNotification(id) {
    if (!confirm('Удалить это уведомление навсегда? Действие необратимо.')) return;
    try {
        const resp = await fetch(`/api/admin/notifications/${id}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        if (resp.ok) {
            showToast('Уведомление удалено');
            await loadNotifications();
            updateDraftBadge();
        } else {
            const err = await resp.json();
            showToast(err.detail || 'Ошибка удаления', true);
        }
    } catch (err) {
        showToast('Ошибка сети', true);
    }
}

export function openEditProposedTimeModal(notifId, currentIsoTime) {
    adminState.currentEditProposedNotifId = notifId;
    document.getElementById('editProposedTimeModal').dataset.entityId = notifId;
    const input = document.getElementById('editProposedTimeInput');
    if (currentIsoTime) {
        // input datetime-local ожидает формат "YYYY-MM-DDThh:mm"
        let val = currentIsoTime.slice(0, 16);
        input.value = val;
    } else {
        input.value = '';
    }
    document.getElementById('editProposedTimeError').innerText = '';
    document.getElementById('editProposedTimeModal').style.display = 'block';
}

export async function openRoleModal(employeeId, employeeFullName) {
    adminState.currentEmployeeIdForRole = employeeId;
    roleModal.dataset.entityId = employeeId;
    roleModalEmployeeFullName.textContent = employeeFullName;
    roleModalError.textContent = '';
    newRoleNameInput.value = '';
    roleSelect.value = '';

    // ПОКАЗЫВАЕМ МОДАЛЬНОЕ ОКНО
    roleModal.style.display = 'block';

    try {
        // Загружаем все должноти для выпадающего списка
        const resp = await fetch('/api/sandbox/roles', { credentials: 'include' });
        if (!resp.ok) throw new Error('Ошибка загрузки должностей');
        const roles = await resp.json();

        // Заполняем select
        roleSelect.innerHTML = '<option value="">-- Выберите должность --</option>';
        roles.forEach(r => {
            const opt = document.createElement('option');
            opt.value = r.id;
            opt.textContent = r.name;
            roleSelect.appendChild(opt);
        });

        // ОТОБРАЖАЕМ ТЕКУЩИЕ ДОЛЖНОСТИ СОТРУДНИКА (теги с крестиками)
        await renderCurrentRoles(employeeId);
    } catch (err) {
        // Показываем ошибку, но модалка уже открыта
        roleModalError.textContent = err.message;
        showToast('Ошибка загрузки должностей: ' + err.message, true);
    }
}

export function closeRoleModal() {
    roleModal.style.display = 'none';
    adminState.currentEmployeeIdForRole = null;
}

document.getElementById('saveEditProposedTimeBtn').addEventListener('click', async () => {
    const newTime = document.getElementById('editProposedTimeInput').value;
    if (!newTime) {
        document.getElementById('editProposedTimeError').innerText = 'Выберите дату и время';
        return;
    }
    // Преобразуем в ISO-строку с секундами
    const isoDateTime = new Date(newTime).toISOString();
    try {
        const resp = await fetch(`/api/admin/notifications/${adminState.currentEditProposedNotifId}/approve-end-time`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ end_time: isoDateTime }),
            credentials: 'include'
        });
        if (resp.ok) {
            showToast('Время завершения обновлено');
            document.getElementById('editProposedTimeModal').style.display = 'none';
            loadNotifications();
        } else {
            const err = await resp.json();
            document.getElementById('editProposedTimeError').innerText = err.detail || 'Ошибка';
        }
    } catch (err) {
        document.getElementById('editProposedTimeError').innerText = 'Ошибка сети';
    }
});

// Закрытие модального окна
document.querySelector('#editProposedTimeModal .close-edit-proposed').onclick = () => {
    document.getElementById('editProposedTimeModal').style.display = 'none';
};
window.addEventListener('click', (e) => {
    const modal = document.getElementById('editProposedTimeModal');
    if (e.target === modal) modal.style.display = 'none';
});
document.getElementById('importProductsBtn')?.addEventListener('click', async () => {
    if (!confirm('ВНИМАНИЕ! Все данные товаров будут удалены и заменены данными из файла img.xlsx. Продолжить?')) return;
    try {
        const resp = await fetch('/api/products/import', { method: 'POST', credentials: 'include' });
        if (resp.ok) {
            const result = await resp.json();
            showToast(`✅ ${result.message}. Загружено записей: ${result.count}`);
        } else {
            const err = await resp.json();
            showToast(`Ошибка: ${err.detail}`, true);
        }
    } catch (err) {
        showToast('Ошибка сети', true);
    }
});
document.getElementById('triggerAutoCloseBtn')?.addEventListener('click', async () => {
    if (!confirm('Запустить автозакрытие смен для всех активных сотрудников? Будут созданы отметки "end" и уведомления о незавершённых днях.')) return;
    try {
        const resp = await fetch('/api/employees/trigger-auto-close', {
            method: 'POST',
            credentials: 'include'
        });
        if (resp.ok) {
            const data = await resp.json();
            showToast(data.message || '✅ Автозакрытие выполнено');
            // Обновить текущие отчёты, чтобы сразу увидеть изменения
            refreshCurrentReport();
        } else {
            const err = await resp.json();
            showToast(err.detail || '❌ Ошибка выполнения', true);
        }
    } catch (err) {
        showToast('❌ Ошибка сети', true);
    }
});



document.addEventListener('click', event => {
    const button = event.target.closest('.employee-recent-link');
    if (!button) return;
    goToEmployeeRecentEntries(Number(button.dataset.employeeId), button.dataset.employeeName);
});
