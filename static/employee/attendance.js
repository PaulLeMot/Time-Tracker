import { employeeState, EMPLOYEE_STORAGE_KEYS } from './state.js';
import { getLocalDate, formatDateTime, formatHoursToHHMM, formatMinutesToHHMM, showToast, fetchWithAuth } from './core.js';
import { createElement, showMessage } from './dom.js';

const attendanceActions = {};

export function configureAttendanceActions(actions) {
    Object.assign(attendanceActions, actions);
}

// ========== ЗАГРУЗКА ДАННЫХ ==========

    export async function loadEmployeeNameAndId() {
        try {
            const resp = await fetchWithAuth('/api/auth/profile');
            const data = await resp.json();
            employeeState.isAdmin = data.is_admin === 1;
            employeeState.canCreateTasks = Boolean(data.is_admin || data.is_monitor);
            employeeState.employeeId = data.id;
            const createTaskButton = document.getElementById('openTaskCreationBtn');
            if (createTaskButton) createTaskButton.style.display = employeeState.canCreateTasks ? 'inline-block' : 'none';
            if (data.is_admin || data.is_monitor) {
                const monitorTabBtn = document.getElementById('monitorTab');
                if (monitorTabBtn) monitorTabBtn.style.display = 'inline-block';
            }
            if ((data.is_admin || data.is_monitor) && !employeeState.monitorSseActive) {
                employeeState.monitorSseActive = true;
                setTimeout(() => attendanceActions.connectMonitorSSE?.(), 2000);
            }
            const allNotifTab = document.getElementById('allNotifTab');
            if (allNotifTab && (data.is_admin || data.is_monitor)) {
                allNotifTab.style.display = 'inline-block';
            }
            document.getElementById('employeeName').replaceChildren(
                createElement('strong', { text: 'Сотрудник:' }),
                document.createTextNode(` ${data.full_name}`),
                createElement('br'),
                createElement('strong', { text: 'Логин:' }),
                document.createTextNode(` ${data.username} (ID: ${data.id})`)
            );
            // Показываем/скрываем пункт "Админ-панель" в выпадающем меню
            const dropdownAdmin = document.getElementById('dropdownAdmin');
            if (dropdownAdmin) {
                dropdownAdmin.style.display = data.is_admin ? 'block' : 'none';
            }
            return data.id;
        } catch (err) {
            console.error(err);
            return null;
        }
    }

    export async function loadEmployeeSummary() {
        try {
            const resp = await fetchWithAuth('/api/auth/daily-summary');
            const data = await resp.json();
            document.getElementById('statusDay').innerText = data.status_day;
            document.getElementById('statusBreak').innerText = data.status_break;
            document.getElementById('workedToday').innerText = formatHoursToHHMM(data.worked_hours_current);
            document.getElementById('breakToday').innerText = formatMinutesToHHMM(data.break_minutes_current);
            document.getElementById('breakCountToday').innerText = data.break_count;
        } catch (err) {
            console.error(err);
            document.getElementById('statusDay').innerText = 'Ошибка загрузки';
        }
    }

    export async function loadTodayEntries(employeeId) {
        const today = getLocalDate();
        try {
            const resp = await fetchWithAuth(`/api/reports/employee/${employeeId}?date=${today}`);
            const data = await resp.json();
            const container = document.getElementById('entriesContainer');
            if (!data.entries.length) {
                showMessage(container, 'Нет отметок за сегодня');
                return [];
            }

            // Словарь для перевода действий
            const actionMap = {
                'start': 'Начало рабочего дня',
                'break_start': 'Начало перерыва',
                'break_end': 'Конец перерыва',
                'end': 'Конец рабочего дня'
            };

            const table = createElement('table', { className: 'compact-data-table' });
            const header = createElement('tr', {}, [
                createElement('th', { text: 'Время' }),
                createElement('th', { text: 'Действие' })
            ]);
            table.append(createElement('thead', {}, header));
            const tbody = createElement('tbody');
            for (const entry of data.entries) {
                const formattedTime = formatDateTime(entry.timestamp);
                const actionLabel = actionMap[entry.action] || entry.action; // fallback на случай неизвестного действия
                tbody.append(createElement('tr', { className: `add-entry-color ${entry.action}` }, [
                    createElement('td', { text: formattedTime }),
                    createElement('td', { text: actionLabel })
                ]));
            }
            table.append(tbody);
            container.replaceChildren(table);
            return data.entries;
        } catch (err) {
            console.error(err);
            showMessage(document.getElementById('entriesContainer'), 'Ошибка загрузки отметок', 'error');
            return [];
        }
    }

    export async function getLastAction(employeeId) {
        try {
            const resp = await fetchWithAuth(`/api/timelog/last/${employeeId}`);
            const data = await resp.json();
            return data.last_action;
        } catch (err) {
            console.error(err);
            return null;
        }
    }

    let isSending = false;

    export async function sendAction(action) {
        if (isSending) {
            showToast('Подождите, предыдущий запрос обрабатывается', true);
            return;
        }
        if (!employeeState.employeeId) {
            showToast('Ошибка: не удалось определить сотрудника', true);
            return;
        }
        isSending = true;
        const btns = document.querySelectorAll('.action-btn');
        btns.forEach(btn => btn.disabled = true);
        try {
            const resp = await fetchWithAuth('/api/timelog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: employeeState.employeeId, action: action })
            });
            if (resp.ok) {
                showToast(`✅ ${action} успешно`, false);
                await refreshState();
            } else {
                let errorMsg = `Ошибка ${resp.status}`;
                try {
                    const err = await resp.json();
                    errorMsg = err.detail || errorMsg;
                } catch(e) {}
                showToast(errorMsg, true);
            }
        } catch (err) {
            showToast('Ошибка соединения с сервером', true);
        } finally {
            isSending = false;
            setTimeout(() => btns.forEach(btn => btn.disabled = false), 500);
        }
    }

    export function getAvailableActions(lastAction) {
        if (!lastAction) return ['start'];
        switch (lastAction) {
            case 'start': return ['break_start', 'end'];
            case 'break_start': return ['break_end'];
            case 'break_end': return ['break_start', 'end'];
            case 'end': return ['start'];
            default: return ['start'];
        }
    }

    export function renderButtons(availableActions) {
        const container = document.getElementById('actionButtons');
        container.innerHTML = '';
        const buttonConfig = {
            'start': { text: '🚀 Начать работу', class: '' },
            'break_start': { text: '☕ Перерыв (начало)', class: 'break' },
            'break_end': { text: '✅ Перерыв (конец)', class: 'break' },
            'end': { text: '🏁 Завершить работу', class: 'end' }
        };
        for (const action of availableActions) {
            const config = buttonConfig[action];
            if (!config) continue;
            const btn = document.createElement('button');
            btn.textContent = config.text;
            btn.className = `action-btn ${config.class}`;
            btn.onclick = () => sendAction(action);
            container.appendChild(btn);
        }
    }

    export async function refreshState() {
        const empId = await loadEmployeeNameAndId();
        if (!empId) return;
        employeeState.employeeId = empId;
        await loadEmployeeSummary();
        await loadTodayEntries(empId);
        const lastAction = await getLastAction(empId);
        const availableActions = getAvailableActions(lastAction);
        renderButtons(availableActions);
    }

    // ========== НЕДЕЛЬНЫЙ ОТЧЁТ ==========
    export function getWeekNumber(date) {
        const firstJan = new Date(date.getFullYear(), 0, 1);
        const days = Math.floor((date - firstJan) / (24 * 60 * 60 * 1000));
        return Math.ceil((days + firstJan.getDay() + 1) / 7);
    }
    export function getMonday(date) {
        const d = new Date(date);
        const day = d.getDay();
        const diff = (day === 0 ? -6 : 1) - day;
        d.setDate(d.getDate() + diff);
        return new Date(d.getFullYear(), d.getMonth(), d.getDate());
    }
    export function getMondayOfWeek(year, week) {
        const date = new Date(year, 0, 1);
        const days = (week - 1) * 7;
        date.setDate(date.getDate() + days);
        return getMonday(date);
    }

    export async function loadWeeklyReport(weekStart) {
        const container = document.getElementById('weeklyContainer');
        showMessage(container, 'Загрузка...');
        try {
            const resp = await fetchWithAuth(`/api/auth/weekly-summary?start_date=${weekStart}`);
            const data = await resp.json();
            if (!data.days.length) {
                showMessage(container, 'Нет данных за эту неделю');
                return;
            }
            const table = createElement('table', { className: 'control-full-width' });
            const header = createElement('tr', {}, ['День', 'Отработано', 'Перерывы'].map(text => createElement('th', { text })));
            table.append(createElement('thead', {}, header));
            const tbody = createElement('tbody');
            for (const day of data.days) {
                tbody.append(createElement('tr', {}, [
                    createElement('td', { text: `${day.weekday} (${day.date})` }),
                    createElement('td', { text: formatHoursToHHMM(day.worked_hours) }),
                    createElement('td', { text: formatMinutesToHHMM(day.break_minutes) })
                ]));
            }
            tbody.append(createElement('tr', { className: 'table-total-row' }, [
                createElement('td', {}, createElement('strong', { text: 'Итого' })),
                createElement('td', {}, createElement('strong', { text: formatHoursToHHMM(data.total_worked_hours) })),
                createElement('td', {}, createElement('strong', { text: formatMinutesToHHMM(data.total_break_minutes) }))
            ]));
            table.append(tbody);
            container.replaceChildren(table);
        } catch (err) {
            showMessage(container, 'Ошибка загрузки', 'error');
            showToast(err.message, true);
        }
    }

    // ========== ВКЛАДКИ ==========
    export function initTabs() {
        const tabs = document.querySelectorAll('.tab-btn');
        const dailyTab = document.getElementById('daily-tab');
        const weeklyTab = document.getElementById('weekly-tab');
        const monitorTabDiv = document.getElementById('monitor-tab');
        const notificationsTab = document.getElementById('notifications-tab');
        const allNotifTabDiv = document.getElementById('all-notifications-tab');
        const tasksTab = document.getElementById('tasks-tab');
        const weekPicker = document.getElementById('weekPicker');
        const loadWeeklyBtn = document.getElementById('loadWeeklyBtn');

        tabs.forEach(btn => {
            btn.addEventListener('click', () => {
                const tabId = btn.dataset.tab;
                // Обработка вкладок-переходов
                if (tabId === 'search') {
                    window.location.href = '/static/search.html';
                    return;
                } else if (tabId === 'mark') {
                    window.location.href = '/mark';
                    return;
                }
                localStorage.setItem(EMPLOYEE_STORAGE_KEYS.tab, tabId);
                // Остальные вкладки – показываем/скрываем
                tabs.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                dailyTab.style.display = 'none';
                weeklyTab.style.display = 'none';
                if (monitorTabDiv) monitorTabDiv.style.display = 'none';
                if (notificationsTab) notificationsTab.style.display = 'none';
                if (allNotifTabDiv) allNotifTabDiv.style.display = 'none';
                if (tasksTab) tasksTab.style.display = 'none';

                if (tabId === 'daily') {
                    dailyTab.style.display = 'block';
                    refreshState();
                } else if (tabId === 'weekly') {
                    weeklyTab.style.display = 'block';
                    if (!weekPicker.value) {
                        const now = new Date();
                        const year = now.getFullYear();
                        const weekNumber = getWeekNumber(now);
                        weekPicker.value = `${year}-W${weekNumber.toString().padStart(2, '0')}`;
                        const monday = getMonday(now);
                        const y = monday.getFullYear();
                        const m = String(monday.getMonth() + 1).padStart(2, '0');
                        const d = String(monday.getDate()).padStart(2, '0');
                        loadWeeklyReport(`${y}-${m}-${d}`);
                    } else {
                        const weekValue = weekPicker.value;
                        if (weekValue) {
                            const [year, week] = weekValue.split('-W');
                            const monday = getMondayOfWeek(parseInt(year), parseInt(week));
                            const y = monday.getFullYear();
                            const m = String(monday.getMonth() + 1).padStart(2, '0');
                            const d = String(monday.getDate()).padStart(2, '0');
                            loadWeeklyReport(`${y}-${m}-${d}`);
                        }
                    }
                } else if (tabId === 'monitor') {
                    if (monitorTabDiv) monitorTabDiv.style.display = 'block';
                    const monitorDate = document.getElementById('monitorDate');
                    if (!monitorDate.value) monitorDate.value = getLocalDate();
                    attendanceActions.loadMonitorReport?.(monitorDate.value);
                    attendanceActions.connectMonitorSSE?.();
                } else if (tabId === 'notifications') {
                    if (notificationsTab) notificationsTab.style.display = 'block';
                    attendanceActions.loadNotifications?.();
                } else if (tabId === 'all-notifications') {
                    if (allNotifTabDiv) allNotifTabDiv.style.display = 'block';
                    attendanceActions.loadAllNotifications?.();
                } else if (tabId === 'tasks') {
                    if (tasksTab) tasksTab.style.display = 'block';
                    attendanceActions.loadTaskNotifications?.();
                }
            });
        });

        if (loadWeeklyBtn) {
            loadWeeklyBtn.addEventListener('click', () => {
                const weekValue = weekPicker.value;
                if (weekValue) {
                    const [year, week] = weekValue.split('-W');
                    const monday = getMondayOfWeek(parseInt(year), parseInt(week));
                    const y = monday.getFullYear();
                    const m = String(monday.getMonth() + 1).padStart(2, '0');
                    const d = String(monday.getDate()).padStart(2, '0');
                    loadWeeklyReport(`${y}-${m}-${d}`);
                }
            });
        }
        // Восстанавливаем последнюю открытую вкладку
        const savedTab = localStorage.getItem(EMPLOYEE_STORAGE_KEYS.tab) || 'daily';
        const defaultTab = document.querySelector(`.tab-btn[data-tab="${savedTab}"]`) || document.querySelector('.tab-btn[data-tab="daily"]');
        if (defaultTab) {
            defaultTab.click();
        }
    }

    // ========== ВЫПАДАЮЩЕЕ МЕНЮ (шестерёнка) ==========
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsDropdown = document.getElementById('settingsDropdown');
    const dropdownAdmin = document.getElementById('dropdownAdmin');
    const dropdownChangePassword = document.getElementById('dropdownChangePassword');
    const dropdownLogout = document.getElementById('dropdownLogout');

    settingsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        settingsDropdown.style.display = settingsDropdown.style.display === 'block' ? 'none' : 'block';
    });
    document.addEventListener('click', (e) => {
        if (!settingsBtn.contains(e.target) && !settingsDropdown.contains(e.target)) {
            settingsDropdown.style.display = 'none';
        }
    });

    dropdownAdmin.addEventListener('click', (e) => {
        e.preventDefault();
        window.location.href = '/admin';
        settingsDropdown.style.display = 'none';
    });

    dropdownChangePassword.addEventListener('click', (e) => {
        e.preventDefault();
        const modal = document.getElementById('changePasswordModal');
        if (modal) {
            modal.style.display = 'block';
            document.getElementById('oldPassword').value = '';
            document.getElementById('newPassword').value = '';
            document.getElementById('confirmPassword').value = '';
            document.getElementById('passwordError').innerText = '';
        }
        settingsDropdown.style.display = 'none';
    });

    dropdownLogout.addEventListener('click', async (e) => {
        e.preventDefault();
        try {
            await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
            window.location.replace('/static/login.html');
        } catch (err) {
            showToast('Ошибка выхода', true);
        }
        settingsDropdown.style.display = 'none';
    });

    // ========== МОДАЛКА СМЕНЫ ПАРОЛЯ ==========
    const modal = document.getElementById('changePasswordModal');
    const closeModal = document.querySelector('#changePasswordModal .close');
    const savePwdBtn = document.getElementById('savePasswordBtn');

    closeModal.onclick = () => modal.style.display = 'none';
    window.addEventListener('click', event => {
        if (event.target === modal) modal.style.display = 'none';
    });

    savePwdBtn.onclick = async () => {
        const oldPwd = document.getElementById('oldPassword').value;
        const newPwd = document.getElementById('newPassword').value;
        const confirmPwd = document.getElementById('confirmPassword').value;
        const errorSpan = document.getElementById('passwordError');
        errorSpan.innerText = '';
        if (newPwd !== confirmPwd) {
            errorSpan.innerText = 'Новые пароли не совпадают';
            return;
        }
        if (newPwd.length < 4) {
            errorSpan.innerText = 'Пароль должен содержать минимум 4 символа';
            return;
        }
        try {
            const resp = await fetchWithAuth('/api/auth/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
            });
            if (resp.ok) {
                showToast('Пароль успешно изменён', false);
                modal.style.display = 'none';
            } else {
                const err = await resp.json();
                errorSpan.innerText = err.detail || 'Ошибка смены пароля';
            }
        } catch (err) {
            errorSpan.innerText = 'Ошибка соединения с сервером';
        }
    };
