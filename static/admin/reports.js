/**
 * Модуль админ-панели: Дневные, недельные и последние отчёты.
 * Подключается через main.js и использует явные ES module зависимости.
 */
import { adminState, STORAGE_KEYS } from './state.js';
import { getLocalDate, loadReportForDate, showToast, restoreScrollPosition, observeAdminModals, restoreAdminModal } from './core.js';
import {
    initMonthlyTab, initProcsetsTab, loadEmployeeListForFilter, loadEmployees,
    loadEmployeesForSelect, loadNotifications, loadRecentEmployeeFilter,
    loadTrafficEmployees, loadWeeklyTraffic, restoreTabState, restoreTrafficState,
    saveTabState, saveTrafficState, updateDraftBadge, updateFilterVisibility
} from './actions.js';
import { createElement, showMessage } from './dom.js';

export function formatDateTime(isoString) {
        if (!isoString) return '—';
        let str = isoString.slice(0, 19).replace('T', ' ');
        const [datePart, timePart] = str.split(' ');
        if (!datePart || !timePart) return str;
        const [year, month, day] = datePart.split('-');
        const [hours, minutes] = timePart.split(':');
        return `${year}-${month}-${day} ${hours}:${minutes}`;
    }

    export function formatWorkedHours(workedHours) {
        if (!workedHours && workedHours !== 0) return '—';
        const totalMinutes = Math.round(workedHours * 60);
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;
        return `${hours}:${minutes.toString().padStart(2, '0')}`;
    }

    export function formatHoursToHHMM(hoursDecimal) {
        if (hoursDecimal === undefined || hoursDecimal === null) return '—';
        const totalMinutes = Math.round(hoursDecimal * 60);
        const hh = Math.floor(totalMinutes / 60);
        const mm = totalMinutes % 60;
        return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
    }

    export function formatMinutesToHHMM(minutes) {
        if (minutes === undefined || minutes === null) return '—';
        const hh = Math.floor(minutes / 60);
        const mm = minutes % 60;
        return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
    }

    export function toggleFilter() {
        adminState.isFilterEnabled = !adminState.isFilterEnabled;
        localStorage.setItem('statusFilterEnabled', adminState.isFilterEnabled);
        const settingsDiv = document.getElementById('statusOrderSettings');
        const toggleBtn = document.getElementById('toggleFilterBtn');
        if (adminState.isFilterEnabled) {
            settingsDiv.style.display = 'block';
            toggleBtn.textContent = '🎛️ Скрыть фильтр статусов';
            loadStatusOrder();
            initDragAndDrop();
        } else {
            settingsDiv.style.display = 'none';
            toggleBtn.textContent = '🎛️ Фильтр по статусам';
        }
        const currentDate = document.getElementById('reportDate').value;
        if (currentDate) loadDailyReport(currentDate);
    }

    export async function loadDailyReport(date) {
        const container = document.getElementById('reportContainer');
        if (adminState.dailyTrafficModeActive) {
            adminState.dailyTrafficModeActive = false;
            const btn = document.getElementById('dailyTrafficBtn');
            btn.textContent = '🚦';
            updateFilterVisibility();
        }
        container.innerHTML = '<p>Загрузка...</p>';
        try {
            const resp = await fetch(`/api/reports/daily?date=${date}`);
            if (!resp.ok) throw new Error('Ошибка загрузки отчёта');
            let report = await resp.json();
            adminState.dailyReportData = report;
            if (!report.length) {
                container.innerHTML = '<p>Нет данных за этот день</p>';
                return;
            }

        if (adminState.isFilterEnabled) {
            const getStatusPriority = (row) => {
                let key;
                if (row.status_break === '☕ в перерыве') key = 'onbreak';
                else if (row.status_day === '✅ работает') key = 'working';
                else if (row.status_day === '❌ не начал') key = 'notstarted';
                else if (row.status_day === '🏁 завершил') key = 'ended';
                else return 99;
                const idx = statusOrder.indexOf(key);
                return idx !== -1 ? idx : 99;
            };
            report.sort((a, b) => {
                const priorityA = getStatusPriority(a);
                const priorityB = getStatusPriority(b);
                if (priorityA !== priorityB) return priorityA - priorityB;
                return a.full_name.localeCompare(b.full_name, 'ru');
            });
        } else {
            report.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
        }

            const table = createElement('table', { className: 'report-table' });
            const header = createElement('tr');
            ['Сотрудник', 'Статус', 'Начало рабочего дня', 'Последняя отметка'].forEach(label => header.append(createElement('th', { text: label })));
            const workedHeader = createElement('th', {}, [
                document.createTextNode('Отработано '),
                createElement('button', { className: 'rounding-settings-button', text: '⚙️', attrs: { id: 'roundingSettingsBtn', type: 'button' } })
            ]);
            header.append(workedHeader);
            ['Перерывы', 'Кол-во перерывов', 'Детали'].forEach(label => header.append(createElement('th', { text: label })));
            table.append(createElement('thead', {}, header));
            const tbody = createElement('tbody');
            report.forEach(row => {
                const entryLabels = { start: 'Начало рабочего дня', break_start: 'Начало перерыва', break_end: 'Конец перерыва', end: 'Конец рабочего дня' };
                const lastEntry = row.last_entry_time ? `${row.last_entry_time.slice(11, 16)} - ${entryLabels[row.last_entry_action] || row.last_entry_action || ''}` : '';
                const status = row.status_break || row.status_day;
                const actions = createElement('td', {}, [
                    createElement('button', { className: 'btn-sm employee-detail-button', text: '📋', attrs: { type: 'button', title: 'Детали отметок' }, dataset: { employeeId: row.employee_id, reportDate: date } }),
                    createElement('button', { className: 'btn-sm send-notif', text: '📝', attrs: { type: 'button', title: 'Отправить уведомление' }, dataset: { id: row.employee_id, name: row.full_name } })
                ]);
                tbody.append(createElement('tr', { className: reportRowClass(row) }, [
                    createElement('td', { text: row.full_name }), createElement('td', { text: status }),
                    createElement('td', { text: row.first_start_time ? row.first_start_time.slice(11, 16) : '' }),
                    createElement('td', { text: lastEntry }), createElement('td', { text: row.worked_display || formatHoursToHHMM(row.worked_hours_current) }),
                    createElement('td', { text: formatMinutesToHHMM(row.break_minutes_current) }), createElement('td', { text: row.break_count }), actions
                ]));
            });
            table.append(tbody);
            container.replaceChildren(createElement('div', { className: 'recent-table' }, table));
            const gearBtn = document.getElementById('roundingSettingsBtn');
            if (gearBtn) {
                gearBtn.onclick = (e) => {
                    e.stopPropagation();
                    document.getElementById('roundingModal').style.display = 'block';
                    loadRoundingInterval();
                };
            }
            container.querySelectorAll('.send-notif').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const empId = btn.dataset.id;
                    const empName = btn.dataset.name;
                    openNotificationModal(empId, empName);
                });
            });
        } catch (err) {
            container.innerHTML = '<p>Ошибка загрузки</p>';
            showToast(err.message, true);
        }
    }

    function reportRowClass(row) {
        if (row.status_day === '❌ не начал') return 'row-not-started';
        if (row.status_break === '☕ в перерыве') return 'row-on-break';
        if (row.status_day === '✅ работает') return 'row-working';
        if (row.status_day === '🏁 завершил') return 'row-ended';
        return '';
    }

    export async function loadWeeklyReport(weekStart) {
        const container = document.getElementById('weeklyReportContainer');
        if (adminState.dailyTrafficModeActive) {
            return;
        }
        container.innerHTML = '<p>Загрузка...</p>';
        try {
            const resp = await fetch(`/api/reports/weekly?start_date=${weekStart}`);
            if (!resp.ok) throw new Error('Ошибка загрузки недельного отчёта');
            const report = await resp.json();
            if (!report.length) {
                container.innerHTML = '<p>Нет данных за эту неделю</p>';
                return;
            }
            report.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
            const table = createElement('table', { className: 'report-table' });
            const thead = createElement('thead');
            const startDate = new Date(`${weekStart}T00:00:00`);
            const firstHeader = createElement('tr');
            firstHeader.append(createElement('th', { text: 'Сотрудник' }));
            for (let index = 0; index < 7; index += 1) {
                const current = new Date(startDate);
                current.setDate(startDate.getDate() + index);
                const dateLabel = `${String(current.getDate()).padStart(2, '0')}.${String(current.getMonth() + 1).padStart(2, '0')}`;
                firstHeader.append(createElement('th', {
                    className: 'day-header-cell', attrs: { colspan: 2 }, dataset: { dayHeaderIndex: index }
                }, [document.createTextNode(report[0].days[index].weekday), document.createElement('br'), createElement('span', { className: 'week-date-label', text: dateLabel })]));
            }
            firstHeader.append(createElement('th', { text: 'Всего часов' }), createElement('th', { text: 'Всего п-вы' }));
            const secondHeader = createElement('tr');
            secondHeader.append(createElement('th'));
            for (let index = 0; index < 7; index += 1) {
                secondHeader.append(
                    createElement('th', { className: 'hour-header-cell', text: 'часы', dataset: { dayIndex: index } }),
                    createElement('th', { className: 'break-minutes-cell break-header-cell', text: 'п-вы', dataset: { dayIndex: index } })
                );
            }
            secondHeader.append(createElement('th'), createElement('th'));
            thead.append(firstHeader, secondHeader);
            table.append(thead);
            const tbody = createElement('tbody');
            report.forEach(employee => {
                const row = createElement('tr');
                row.append(createElement('td', { className: 'fio-cell' }, [
                    document.createTextNode(employee.full_name),
                    createElement('button', { className: 'btn-sm send-notif weekly-notification-button', text: '📝', attrs: { type: 'button', title: 'Отправить уведомление' }, dataset: { id: employee.employee_id, name: employee.full_name } })
                ]));
                employee.days.forEach((day, index) => {
                    const inactive = !day.worked_hours ? 'inactive-day' : '';
                    row.append(
                        createElement('td', { className: `worked-hours-cell ${inactive}`, dataset: { dayIndex: index } }, [
                            createElement('div', { className: 'worked-time-value', text: day.worked_display || formatHoursToHHMM(day.worked_hours) }),
                            createElement('div', { className: 'start-time-value', text: day.first_start_time ? day.first_start_time.slice(11, 16) : '' })
                        ]),
                        createElement('td', { className: `break-minutes-cell ${inactive}`, dataset: { dayIndex: index } }, [
                            createElement('div', { className: 'break-time-value', text: `${formatMinutesToHHMM(day.break_minutes)} (${day.break_count || 0})` }),
                            createElement('div', { className: 'end-time-value', text: day.end_time ? day.end_time.slice(11, 16) : '' })
                        ])
                    );
                });
                row.append(
                    createElement('td', { className: 'worked-hours-cell' }, createElement('strong', { text: employee.total_worked_display || formatHoursToHHMM(employee.total_worked_hours) })),
                    createElement('td', { className: 'break-minutes-cell' }, createElement('strong', { text: formatMinutesToHHMM(employee.total_break_minutes) }))
                );
                tbody.append(row);
            });
            table.append(tbody);
            container.replaceChildren(createElement('div', { className: 'recent-table' }, table));

            container.querySelectorAll('.send-notif').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const empId = btn.dataset.id;
                    const empName = btn.dataset.name;
                    openNotificationModal(empId, empName);
                });
            });
            
            const renderedTable = container.querySelector('table');
            const rows = renderedTable.querySelectorAll('tbody tr');
            
            rows.forEach(row => {
                const fioCell = row.querySelector('.fio-cell');
                const cells = row.querySelectorAll('td.worked-hours-cell, td.break-minutes-cell');
                
                cells.forEach(cell => {
                    cell.addEventListener('mouseenter', () => {
                        if (fioCell) fioCell.classList.add('highlight-fio');
                        
                        const dayIndex = cell.dataset.dayIndex;
                        if (dayIndex !== undefined) {
                            const dayHeader = renderedTable.querySelector(`th.day-header-cell[data-day-header-index="${dayIndex}"]`);
                            if (dayHeader) dayHeader.classList.add('highlight-day-header');
                            
                            const hourHeader = renderedTable.querySelector(`th.hour-header-cell[data-day-index="${dayIndex}"]`);
                            const breakHeader = renderedTable.querySelector(`th.break-header-cell[data-day-index="${dayIndex}"]`);
                            if (hourHeader) hourHeader.classList.add('highlight-hour-header');
                            if (breakHeader) breakHeader.classList.add('highlight-day-header');
                        }
                    });
                    
                    cell.addEventListener('mouseleave', () => {
                        if (fioCell) fioCell.classList.remove('highlight-fio');
                        
                        const dayIndex = cell.dataset.dayIndex;
                        if (dayIndex !== undefined) {
                            const dayHeader = renderedTable.querySelector(`th.day-header-cell[data-day-header-index="${dayIndex}"]`);
                            if (dayHeader) dayHeader.classList.remove('highlight-day-header');
                            
                            const hourHeader = renderedTable.querySelector(`th.hour-header-cell[data-day-index="${dayIndex}"]`);
                            const breakHeader = renderedTable.querySelector(`th.break-header-cell[data-day-index="${dayIndex}"]`);
                            if (hourHeader) hourHeader.classList.remove('highlight-hour-header');
                            if (breakHeader) breakHeader.classList.remove('highlight-day-header');
                        }
                    });
                });
            });
        } catch (err) {
            container.innerHTML = '<p>Ошибка загрузки</p>';
            showToast(err.message, true);
        }
    }

    export function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/[&<>]/g, function(m) {
            if (m === '&') return '&amp;';
            if (m === '<') return '&lt;';
            if (m === '>') return '&gt;';
            return m;
        });
    }

    let currentEmployeeId = null;
    let currentDate = null;
    let currentEntries = [];
    let allEmployees = [];

    export async function showEmployeeDetail(empId, date) {
        sessionStorage.setItem(STORAGE_KEYS.employeeModalContext, JSON.stringify({ employeeId: empId, date }));
        currentEmployeeId = empId;
        currentDate = date;
        const modal = document.getElementById('detailModal');
        const modalTitle = document.getElementById('modalTitle');
        try {
            const resp = await fetch(`/api/reports/employee/${empId}?date=${date}`);
            if (!resp.ok) throw new Error('Ошибка загрузки');
            const data = await resp.json();
            currentEntries = data.entries;
            modalTitle.innerText = `Сотрудник: ${escapeHtml(data.full_name)} (${date})`;
            renderEntriesList(currentEntries);
            modal.style.display = 'block';
        } catch (err) {
            showToast(err.message, true);
        }
    };

    export function renderEntriesList(entries) {
        const modalBody = document.getElementById('modalBody');
        if (!modalBody) return;
        if (!entries.length) {
            modalBody.innerHTML = '<p>Нет отметок за этот день</p>';
            return;
        }

        function formatSource(source) {
            if (source === 'barcode') return 'Сотрудник';
            if (source === 'auto') return 'Авто';
            if (source && source.startsWith('admin(')) {
                const match = source.match(/^admin\((.*)\)$/);
                if (match) return `Админ(${match[1]})`;
                return 'Админ';
            }
            if (source === 'admin') return 'Админ';
            return source || '—';
        }

        const table = createElement('table', { className: 'full-width-table' });
        const header = createElement('tr');
        ['Время', 'Действие', 'Источник', 'Действия'].forEach(label => header.append(createElement('th', { text: label })));
        table.append(createElement('thead', {}, header));
        const tbody = createElement('tbody');
        entries.forEach(entry => {
            const isoDate = entry.timestamp.slice(0, 10);
            const isoTime = entry.timestamp.slice(11, 16);
            const controls = createElement('div', { className: 'edit-controls' }, [
                createElement('input', { className: 'edit-date', attrs: { type: 'date', value: isoDate } }),
                createElement('input', { className: 'edit-time', attrs: { type: 'time', value: isoTime, step: 60 } })
            ]);
            controls.style.display = 'none';
            const saveButton = createElement('button', { className: 'small-btn save-btn', text: '💾', attrs: { type: 'button', title: 'Сохранить' } });
            const cancelButton = createElement('button', { className: 'small-btn cancel-btn', text: '❌', attrs: { type: 'button', title: 'Отмена' } });
            saveButton.style.display = 'none';
            cancelButton.style.display = 'none';
            tbody.append(createElement('tr', { dataset: { id: entry.id } }, [
                createElement('td', {}, [createElement('span', { className: 'entry-time', text: formatDateTime(entry.timestamp) }), controls]),
                createElement('td', { text: entry.action }), createElement('td', { text: formatSource(entry.source) }),
                createElement('td', {}, [
                    createElement('button', { className: 'small-btn edit-btn', text: '✏️', attrs: { type: 'button', title: 'Редактировать' } }),
                    saveButton, cancelButton,
                    createElement('button', { className: 'small-btn delete-btn', text: '🗑️', attrs: { type: 'button', title: 'Удалить' } })
                ])
            ]));
        });
        table.append(tbody);
        modalBody.replaceChildren(table);

        // --- ИСПРАВЛЕНИЯ: все обработчики теперь ищут внутри modalBody и проверяют row ---

        modalBody.querySelectorAll('.edit-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const row = btn.closest('tr');
                if (!row) return;
                const timeSpan = row.querySelector('.entry-time');
                const editDiv = row.querySelector('.edit-controls');
                const editBtn = row.querySelector('.edit-btn');
                const saveBtn = row.querySelector('.save-btn');
                const cancelBtn = row.querySelector('.cancel-btn');
                timeSpan.style.display = 'none';
                editDiv.style.display = 'inline-block';
                editBtn.style.display = 'none';
                saveBtn.style.display = 'inline-block';
                cancelBtn.style.display = 'inline-block';
            });
        });

        modalBody.querySelectorAll('.save-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const row = btn.closest('tr');
                if (!row) return;
                const entryId = row.dataset.id;
                const dateInput = row.querySelector('.edit-date');
                const timeInput = row.querySelector('.edit-time');
                const newDate = dateInput.value;
                const newTime = timeInput.value;
                if (!newDate || !newTime) {
                    showToast('Выберите дату и время', true);
                    return;
                }
                const isoDateTime = `${newDate}T${newTime}:00`;
                try {
                    const resp = await fetch(`/api/admin/timelog/${entryId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ timestamp: isoDateTime })
                    });
                    if (resp.ok) {
                        showToast('Время обновлено');
                        await showEmployeeDetail(currentEmployeeId, currentDate);
                        refreshCurrentReport();
                    } else {
                        const err = await resp.json();
                        showToast(err.detail || 'Ошибка', true);
                    }
                } catch (err) {
                    showToast('Ошибка сети', true);
                }
            });
        });

        modalBody.querySelectorAll('.cancel-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const row = btn.closest('tr');
                if (!row) return;
                const timeSpan = row.querySelector('.entry-time');
                const editDiv = row.querySelector('.edit-controls');
                const editBtn = row.querySelector('.edit-btn');
                const saveBtn = row.querySelector('.save-btn');
                const cancelBtn = row.querySelector('.cancel-btn');
                timeSpan.style.display = 'inline-block';
                editDiv.style.display = 'none';
                editBtn.style.display = 'inline-block';
                saveBtn.style.display = 'none';
                cancelBtn.style.display = 'none';
                const currentDisplay = timeSpan.innerText;
                const parts = currentDisplay.split(/[- :]/);
                if (parts.length === 5) {
                    const [day, month, year, hours, minutes] = parts;
                    const isoDate = `${year}-${month}-${day}`;
                    const isoTime = `${hours}:${minutes}`;
                    row.querySelector('.edit-date').value = isoDate;
                    row.querySelector('.edit-time').value = isoTime;
                }
            });
        });

        modalBody.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const row = btn.closest('tr');
                if (!row) return;
                if (!confirm('Удалить эту отметку?')) return;
                const entryId = row.dataset.id;
                try {
                    const resp = await fetch(`/api/admin/timelog/${entryId}`, { method: 'DELETE' });
                    if (resp.ok) {
                        showToast('Отметка удалена');
                        await showEmployeeDetail(currentEmployeeId, currentDate);
                        refreshCurrentReport();
                    } else {
                        showToast('Ошибка удаления', true);
                    }
                } catch (err) {
                    showToast('Ошибка сети', true);
                }
            });
        });
    }

    document.getElementById('addEntryBtn').addEventListener('click', async () => {
        const action = document.getElementById('newAction').value;
        const newDate = document.getElementById('newDate').value;
        const newTime = document.getElementById('newTime').value;
        if (!newDate || !newTime) {
            showToast('Выберите дату и время', true);
            return;
        }
        const isoDateTime = `${newDate}T${newTime}:00`;
        try {
            const resp = await fetch('/api/admin/timelog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    employee_id: currentEmployeeId,
                    action: action,
                    timestamp: isoDateTime
                })
            });
            if (resp.ok) {
                showToast('Отметка добавлена');
                document.getElementById('newDate').value = '';
                document.getElementById('newTime').value = '';
                await showEmployeeDetail(currentEmployeeId, currentDate);
                refreshCurrentReport();
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка', true);
            }
        } catch (err) {
            showToast('Ошибка сети', true);
        }
    });
    
    const modal = document.getElementById('detailModal');
    const span = document.getElementsByClassName('close')[0];
    span.onclick = () => modal.style.display = 'none';
    document.querySelector('#editEntryModal .close-edit').addEventListener('click', () => {
        document.getElementById('editEntryModal').style.display = 'none';
    });

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

    document.getElementById('loadReportBtn').onclick = () => {
        const date = document.getElementById('reportDate').value;
        if (date) loadDailyReport(date);
    };

    const weekPicker = document.getElementById('weekPicker');
    if (weekPicker) {
        const now = new Date();
        const year = now.getFullYear();
        const weekNumber = getWeekNumber(now);
        weekPicker.value = `${year}-W${weekNumber.toString().padStart(2, '0')}`;
        
        const monday = getMonday(now);
        const y = monday.getFullYear();
        const m = String(monday.getMonth() + 1).padStart(2, '0');
        const d = String(monday.getDate()).padStart(2, '0');
        const mondayStr = `${y}-${m}-${d}`;
        
        document.getElementById('loadWeeklyReportBtn').onclick = () => {
            const weekValue = weekPicker.value;
            if (weekValue) {
                const [year, week] = weekValue.split('-W');
                const monday = getMondayOfWeek(parseInt(year), parseInt(week));
                const y = monday.getFullYear();
                const m = String(monday.getMonth() + 1).padStart(2, '0');
                const d = String(monday.getDate()).padStart(2, '0');
                const mondayStr = `${y}-${m}-${d}`;
                loadWeeklyReport(mondayStr);
            }
        };
    }
    document.getElementById('logoutAdminBtn').addEventListener('click', async () => {
        try {
            const resp = await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
            if (resp.ok) {
                window.location.replace('/static/login.html');
            } else {
                showToast('Ошибка выхода', true);
            }
        } catch (err) {
            showToast('Ошибка соединения', true);
        }
    });
    //tabs
    export function initTabs() {
        const tabs = document.querySelectorAll('.tab-btn');
        const dailyTab = document.getElementById('daily-tab');
        const weeklyTab = document.getElementById('weekly-tab');
        const recentTab = document.getElementById('recent-tab');
        const employeesTab = document.getElementById('employees-tab');
        const notificationsTab = document.getElementById('notifications-tab');
        const monthlyTab = document.getElementById('monthly-tab');
        const procsetsTab = document.getElementById('procsets-tab'); // <-- добавить

        tabs.forEach(btn => {
            btn.addEventListener('click', async () => {
                const tabId = btn.dataset.tab;
                saveTabState(tabId);
                tabs.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                // Скрываем все вкладки
                dailyTab.style.display = 'none';
                weeklyTab.style.display = 'none';
                if (recentTab) recentTab.style.display = 'none';
                if (employeesTab) employeesTab.style.display = 'none';
                if (notificationsTab) notificationsTab.style.display = 'none';
                if (monthlyTab) monthlyTab.style.display = 'none';
                if (procsetsTab) procsetsTab.style.display = 'none'; // <-- скрываем

                if (tabId === 'daily') {
                    dailyTab.style.display = 'block';
                    if (!document.getElementById('reportDate').value) {
                        const today = getLocalDate();
                        document.getElementById('reportDate').value = today;
                        loadDailyReport(today);
                    }
                } else if (tabId === 'weekly') {
                    weeklyTab.style.display = 'block';
                    const weekPicker = document.getElementById('weekPicker');
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
                } else if (tabId === 'recent') {
                    recentTab.style.display = 'block';
                    const limit = document.getElementById('recentLimit').value;
                    loadRecentEntries(parseInt(limit));
                } else if (tabId === 'employees') {
                    employeesTab.style.display = 'block';
                    loadEmployees();
                } else if (tabId === 'notifications') {
                    notificationsTab.style.display = 'block';
                    loadNotifications();
                } else if (tabId === 'monthly') {
                    if (!monthlyTab) {
                        console.error('monthlyTab не найден');
                        return;
                    }
                    monthlyTab.style.display = 'block';
                    if (!monthlyTab.dataset.loaded) {
                        try {
                            const resp = await fetch('/static/monthly.html');
                            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                            const html = await resp.text();
                            monthlyTab.innerHTML = html;
                            monthlyTab.dataset.loaded = 'true';
                            initMonthlyTab();
                        } catch (err) {
                            showMessage(monthlyTab, `Ошибка загрузки вкладки: ${err.message}`, 'error');
                        }
                    } else {
                        initMonthlyTab();
                    }
                } else if (tabId === 'procsets') {
                    if (!procsetsTab) return;
                    procsetsTab.style.display = 'block';
                    if (!procsetsTab.dataset.loaded) {
                        try {
                            const resp = await fetch('/static/procsets.html?v=task-points-2', { cache: 'no-store' });
                            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                            const html = await resp.text();
                            procsetsTab.innerHTML = html;
                            procsetsTab.dataset.loaded = 'true';
                            initProcsetsTab();
                        } catch (err) {
                            showMessage(procsetsTab, `Ошибка загрузки вкладки: ${err.message}`, 'error');
                        }
                    } else {
                        initProcsetsTab();
                    }
                }
            });
        });
    }

    document.addEventListener('DOMContentLoaded', async () => {
        initTabs();
        const refreshRecentBtn = document.getElementById('refreshRecentBtn');
        if (refreshRecentBtn) {
            refreshRecentBtn.addEventListener('click', () => {
                const limit = document.getElementById('recentLimit').value;
                loadRecentEntries(parseInt(limit));
            });
        }
        await loadEmployees();
        loadEmployeeListForFilter();
        loadRecentEmployeeFilter();
        flatpickr("#notifDateRange", {
            mode: "range",
            dateFormat: "Y-m-d",
            firstDayOfWeek: 1,
            locale: {
                firstDayOfWeek: 1
            },
            onChange: function(selectedDates, dateStr, instance) {
                if (selectedDates.length === 2) {
                    adminState.notificationStartDate = instance.formatDate(selectedDates[0], "Y-m-d");
                    adminState.notificationEndDate = instance.formatDate(selectedDates[1], "Y-m-d");
                } else {
                    adminState.notificationStartDate = '';
                    adminState.notificationEndDate = '';
                }
                loadNotifications();
            }
        });
        document.getElementById('clearDateFilterBtn').addEventListener('click', () => {
            const picker = document.getElementById('notifDateRange')._flatpickr;
            if (picker) picker.clear();
            adminState.notificationStartDate = '';
            adminState.notificationEndDate = '';
            loadNotifications();
        });
        flatpickr("#recentDateRange", {
            mode: "range",
            dateFormat: "Y-m-d",
            firstDayOfWeek: 1,
            locale: {
                firstDayOfWeek: 1
            },
            onChange: function(selectedDates, dateStr, instance) {
                if (selectedDates.length === 2) {
                    adminState.recentStartDate = instance.formatDate(selectedDates[0], "Y-m-d");
                    adminState.recentEndDate = instance.formatDate(selectedDates[1], "Y-m-d");
                } else {
                    adminState.recentStartDate = '';
                    adminState.recentEndDate = '';
                }
                const limit = document.getElementById('recentLimit').value;
                loadRecentEntries(parseInt(limit));
            }
        });
        document.getElementById('clearRecentDateFilterBtn').addEventListener('click', () => {
            const picker = document.getElementById('recentDateRange')._flatpickr;
            if (picker) picker.clear();
            adminState.recentStartDate = '';
            adminState.recentEndDate = '';
            const limit = document.getElementById('recentLimit').value;
            loadRecentEntries(parseInt(limit));
        });
        document.getElementById('recentLimit').addEventListener('change', () => {
            const limit = document.getElementById('recentLimit').value;
            loadRecentEntries(parseInt(limit));
        });
        document.getElementById('recentEmployeeFilter').addEventListener('change', () => {
            adminState.recentEmployeeId = document.getElementById('recentEmployeeFilter').value;
            const limit = document.getElementById('recentLimit').value;
            loadRecentEntries(parseInt(limit));
        });
        const today = getLocalDate();
        const reportDateElem = document.getElementById('reportDate');
        if (reportDateElem) {
            reportDateElem.value = today;
            loadDailyReport(today);
        } else {
            console.error('Элемент reportDate не найден');
        }
        const toggleBtn = document.getElementById('toggleFilterBtn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', toggleFilter);
            if (adminState.isFilterEnabled) {
                document.getElementById('statusOrderSettings').style.display = 'block';
                toggleBtn.textContent = '🎛️ Убрать фильтр статусов';
                loadStatusOrder();
                initDragAndDrop();
            } else {
                document.getElementById('statusOrderSettings').style.display = 'none';
                toggleBtn.textContent = '🎛️ Фильтр по статусам';
            }
        }
        updateDraftBadge();
        loadEmployeesForSelect();
        // Восстановление состояния
        const savedTab = restoreTabState();
        const { mode, employeeId, weekValue } = restoreTrafficState();
        const savedTabBtn = document.querySelector(`.tab-btn[data-tab="${savedTab}"]`);
        if (savedTabBtn) savedTabBtn.click();
        restoreScrollPosition();
        observeAdminModals();
        setTimeout(restoreAdminModal, 200);

        if (savedTab === 'weekly' && mode) {
            // Восстанавливаем неделю
            const weekPicker = document.getElementById('weekPicker');
            if (weekValue && weekPicker) {
                weekPicker.value = weekValue;
                const evt = new Event('change');
                weekPicker.dispatchEvent(evt);
            }

            // Принудительно включаем режим трафика
            adminState.trafficModeActive = true;
            const trafficContainer = document.getElementById('weeklyTrafficContainer');
            const reportContainer = document.getElementById('weeklyReportContainer');
            if (trafficContainer) trafficContainer.style.display = 'block';
            if (reportContainer) reportContainer.style.display = 'none';
            const trafficBtn = document.getElementById('weeklyTrafficBtn');
            if (trafficBtn) trafficBtn.textContent = '🚦';

            // Загружаем список сотрудников, если он ещё пуст, иначе подставляем сохранённого
            const select = document.getElementById('weeklyTrafficEmployeeSelect');
            if (select && select.options.length <= 1) {
                // Если список не загружен – загружаем (он сам подставит сохранённого сотрудника)
                loadTrafficEmployees();
            } else if (select && employeeId) {
                // Если список уже есть, просто выбираем сотрудника
                if (select.querySelector(`option[value="${employeeId}"]`)) {
                    select.value = employeeId;
                    loadWeeklyTraffic(employeeId);
                }
            }
        }
        document.getElementById('weeklyTrafficBtn').addEventListener('click', function(e) {
            e.stopPropagation();
            const weekPicker = document.getElementById('weekPicker');
            const weekValue = weekPicker.value;
            if (!weekValue) {
                showToast('Сначала выберите неделю', true);
                return;
            }

            // Переключаем режим
            adminState.trafficModeActive = !adminState.trafficModeActive;

            const trafficContainer = document.getElementById('weeklyTrafficContainer');
            const reportContainer = document.getElementById('weeklyReportContainer');

            if (adminState.trafficModeActive) {
                // Показываем светофор, скрываем обычный отчёт
                trafficContainer.style.display = 'block';
                reportContainer.style.display = 'none';

                // Загружаем список сотрудников (если ещё не загружен)
                loadTrafficEmployees();

                // Если выбран сотрудник, загружаем его отметки
                const select = document.getElementById('weeklyTrafficEmployeeSelect');
                if (select.value) {
                    loadWeeklyTraffic(select.value);
                } else {
                    // Можно автоматически выбрать первого сотрудника (опционально)
                    // или оставить выбор пользователю
                }
            } else {
                // Возвращаем обычный недельный отчёт
                trafficContainer.style.display = 'none';
                reportContainer.style.display = 'block';

                // Перезагружаем недельный отчёт
                const [year, week] = weekValue.split('-W');
                const monday = getMondayOfWeek(parseInt(year), parseInt(week));
                const y = monday.getFullYear();
                const m = String(monday.getMonth() + 1).padStart(2, '0');
                const d = String(monday.getDate()).padStart(2, '0');
                loadWeeklyReport(`${y}-${m}-${d}`);
            }

            // Сохраняем состояние (для восстановления после перезагрузки)
            const select = document.getElementById('weeklyTrafficEmployeeSelect');
            const employeeId = select ? select.value : '';
            saveTrafficState(adminState.trafficModeActive, employeeId, weekValue);

            // (Опционально) меняем иконку кнопки, чтобы показать активный режим
            this.textContent = '🚦';
        });
        // Функция для изменения недели на +/- delta
        function changeWeek(delta) {
            const weekPicker = document.getElementById('weekPicker');
            if (!weekPicker) return;
            const value = weekPicker.value;
            if (!value) {
                const now = new Date();
                const year = now.getFullYear();
                const week = getWeekNumber(now);
                weekPicker.value = `${year}-W${week.toString().padStart(2, '0')}`;
                // Вместо прямого клика – генерируем событие change
                weekPicker.dispatchEvent(new Event('change'));
                return;
            }
            const parts = value.split('-W');
            if (parts.length !== 2) return;
            let year = parseInt(parts[0]);
            let week = parseInt(parts[1]);
            week += delta;
            if (week < 1) {
                year--;
                const lastDayOfYear = new Date(year, 11, 31);
                const weekCount = getWeekNumber(lastDayOfYear);
                week = weekCount;
            }
            const lastDayOfYear = new Date(year, 11, 31);
            const maxWeek = getWeekNumber(lastDayOfYear);
            if (week > maxWeek) {
                year++;
                week = 1;
            }
            const newValue = `${year}-W${week.toString().padStart(2, '0')}`;
            weekPicker.value = newValue;
            // Вместо прямого клика – генерируем событие change
            weekPicker.dispatchEvent(new Event('change'));
        }

        // Обработчики кнопок
        document.getElementById('prevWeekBtn')?.addEventListener('click', function(e) {
            e.preventDefault();
            changeWeek(-1);
        });

        document.getElementById('nextWeekBtn')?.addEventListener('click', function(e) {
            e.preventDefault();
            changeWeek(1);
        });
        // Функция для изменения даты на +/- 1 день
        function changeDay(delta) {
            const dateInput = document.getElementById('reportDate');
            if (!dateInput) return;
            let currentDate = dateInput.value;
            if (!currentDate) {
                // Если нет даты, установим сегодняшнюю
                const today = getLocalDate();  // у вас есть функция getLocalDate()
                dateInput.value = today;
                document.getElementById('loadReportBtn').click();
                return;
            }
            // Парсим дату в объект Date (локальное время)
            const parts = currentDate.split('-').map(Number);
            if (parts.length !== 3) return;
            const newDate = new Date(parts[0], parts[1] - 1, parts[2]);
            newDate.setDate(newDate.getDate() + delta);
            // Форматируем обратно в YYYY-MM-DD
            const year = newDate.getFullYear();
            const month = String(newDate.getMonth() + 1).padStart(2, '0');
            const day = String(newDate.getDate()).padStart(2, '0');
            const newDateStr = `${year}-${month}-${day}`;
            dateInput.value = newDateStr;
            // Загружаем отчёт (вызываем обработчик кнопки)
            document.getElementById('loadReportBtn').click();
        }

        // Обработчики кнопок
        document.getElementById('prevDayBtn')?.addEventListener('click', function(e) {
            e.preventDefault();
            changeDay(-1);
        });

        document.getElementById('nextDayBtn')?.addEventListener('click', function(e) {
            e.preventDefault();
            changeDay(1);
        });
        updateFilterVisibility();

        document.getElementById('exportNotificationsBtn').addEventListener('click', async function() {
            const params = new URLSearchParams();
            if (adminState.notificationStartDate) params.append('start_date', adminState.notificationStartDate);
            if (adminState.notificationEndDate) params.append('end_date', adminState.notificationEndDate);
            
            const url = `/api/admin/notifications/export?${params.toString()}`;
            try {
                const response = await fetch(url, { credentials: 'include' });
                if (!response.ok) throw new Error('Ошибка экспорта');
                const blob = await response.blob();
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = 'уведомления.xlsx';
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(link.href);
            } catch (err) {
                showToast('Ошибка скачивания: ' + err.message, true);
            }
        });
    });
    function formatSourceLabel(source) {
        if (source === 'barcode') return 'Сотрудник';
        if (source === 'auto') return 'Авто';
        if (source === 'admin') return 'Админ';
        const match = source?.match(/^admin\((.*)\)$/);
        return match ? `Админ(${match[1]})` : (source || '—');
    }

    function recentEntryRowClass(action) {
        return { start: 'recent-start', break_start: 'recent-break-start', break_end: 'recent-break-end', end: 'recent-end' }[action] || '';
    }

    export async function loadRecentEntries(limit = 100) {
        const container = document.getElementById('recentContainer');
        container.innerHTML = '<p>Загрузка...</p>';
        try {
            let url = `/api/admin/recent-entries?limit=${limit}`;
            const params = new URLSearchParams();
            if (adminState.recentEmployeeId) params.append('employee_id', adminState.recentEmployeeId);
            if (adminState.recentStartDate) params.append('start_date', adminState.recentStartDate);
            if (adminState.recentEndDate) params.append('end_date', adminState.recentEndDate);
            if (params.toString()) url += '&' + params.toString();
            
            const resp = await fetch(url, { credentials: 'include' });
            if (!resp.ok) throw new Error('Ошибка загрузки');
            const entries = await resp.json();
            if (!entries.length) {
                container.innerHTML = '<p>Нет записей</p>';
                return;
            }
            const table = createElement('table');
            const header = createElement('tr');
            ['Время', 'Сотрудник', 'Действие', 'Источник', 'Действия'].forEach(label => header.append(createElement('th', { text: label })));
            table.append(createElement('thead', {}, header));
            const tbody = createElement('tbody');
            entries.forEach(entry => {
                let action = entry.action;
                if (entry.action === 'Начало перерыва' && entry.break_number) action = `Начало перерыва №${entry.break_number}`;
                if (entry.action === 'Конец перерыва' && entry.break_number) action = `Конец перерыва №${entry.break_number} (${entry.break_duration})`;
                tbody.append(createElement('tr', { className: recentEntryRowClass(entry.action_code) }, [
                    createElement('td', { text: formatDateTime(entry.timestamp) }), createElement('td', { text: entry.full_name }),
                    createElement('td', { text: action }), createElement('td', { text: formatSourceLabel(entry.source) }),
                    createElement('td', {}, [
                        createElement('button', {
                            className: 'small-btn edit-entry-btn', text: '✏️', attrs: { type: 'button', title: 'Редактировать' },
                            dataset: { id: entry.id, timestamp: entry.timestamp, action: entry.action_code }
                        }),
                        createElement('button', { className: 'small-btn delete-entry-btn', text: '🗑️', attrs: { type: 'button', title: 'Удалить' }, dataset: { id: entry.id } })
                    ])
                ]));
            });
            table.append(tbody);
            container.replaceChildren(createElement('div', { className: 'recent-table' }, table));

            container.addEventListener('click', (e) => {
                const btn = e.target.closest('.edit-entry-btn');
                if (btn) {
                    e.preventDefault();
                    const entryId = btn.dataset.id;
                    const timestamp = btn.dataset.timestamp;
                    const actionCode = btn.dataset.action;
                    openEditModal(entryId, timestamp, actionCode);
                }
            });
            document.querySelectorAll('.delete-entry-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const entryId = btn.dataset.id;
                    if (!confirm('Удалить эту отметку?')) return;
                    try {
                        const resp = await fetch(`/api/admin/timelog/${entryId}`, { method: 'DELETE' });
                        if (resp.ok) {
                            showToast('Отметка удалена');
                            const limit = document.getElementById('recentLimit').value;
                            loadRecentEntries(parseInt(limit));
                            refreshCurrentReport();
                        } else {
                            showToast('Ошибка удаления', true);
                        }
                    } catch (err) {
                        showToast('Ошибка сети', true);
                    }
                });
            });
        } catch (err) {
            container.innerHTML = '<p>Ошибка загрузки</p>';
            showToast(err.message, true);
        }
    }


    export function openEditModal(entryId, timestamp, actionCode) {
        adminState.currentEditEntryId = entryId;
        const modal = document.getElementById('editEntryModal');
        modal.dataset.entityId = entryId;
        const dateInput = document.getElementById('editDate');
        const timeInput = document.getElementById('editTime');
        const actionSelect = document.getElementById('editAction');
        const [datePart, timePart] = timestamp.split('T');
        dateInput.value = datePart;
        timeInput.value = timePart.slice(0, 5);
        actionSelect.value = actionCode;
        document.getElementById('editError').innerText = '';
        modal.style.display = 'block';
    }

    document.getElementById('saveEditBtn').addEventListener('click', async () => {
        const newDate = document.getElementById('editDate').value;
        const newTime = document.getElementById('editTime').value;
        const newAction = document.getElementById('editAction').value;
        if (!newDate || !newTime) {
            document.getElementById('editError').innerText = 'Выберите дату и время';
            return;
        }
        const isoDateTime = `${newDate}T${newTime}:00`;
        try {
            const resp = await fetch(`/api/admin/timelog/${adminState.currentEditEntryId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timestamp: isoDateTime, action: newAction })
            });
            if (resp.ok) {
                showToast('Отметка обновлена');
                document.getElementById('editEntryModal').style.display = 'none';
                const limit = document.getElementById('recentLimit').value;
                loadRecentEntries(parseInt(limit));
                refreshCurrentReport();
            } else {
                const err = await resp.json();
                document.getElementById('editError').innerText = err.detail || 'Ошибка обновления';
            }
        } catch (err) {
            document.getElementById('editError').innerText = 'Ошибка соединения';
        }
    });


    export function openEditUsernameModal(id, currentUsername) {
        adminState.currentEditId = id;
        document.getElementById('editUsernameModal').dataset.entityId = id;
        document.getElementById('newUsername').value = currentUsername;
        document.getElementById('usernameError').innerText = '';
        document.getElementById('editUsernameModal').style.display = 'block';
    }

    export function openEditFullnameModal(id, currentFullname) {
        adminState.currentEditId = id;
        document.getElementById('editFullnameModal').dataset.entityId = id;
        document.getElementById('newFullname').value = currentFullname;
        document.getElementById('fullnameError').innerText = '';
        document.getElementById('editFullnameModal').style.display = 'block';
    }

    export function openEditPasswordModal(id) {
        const newPass = prompt('Введите новый пароль:');
        if (newPass !== null && newPass.trim() !== '') {
            fetch(`/api/employees/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: newPass })
            })
            .then(resp => {
                if (resp.ok) {
                    showToast('Пароль обновлён');
                    loadEmployees();
                    refreshCurrentReport();
                } else {
                    showToast('Ошибка обновления пароля', true);
                }
            })
            .catch(() => showToast('Ошибка сети', true));
        }
    }

    document.getElementById('saveUsernameBtn').addEventListener('click', async () => {
        const newUsername = document.getElementById('newUsername').value.trim();
        if (!newUsername) {
            document.getElementById('usernameError').innerText = 'Логин не может быть пустым';
            return;
        }
        try {
            const resp = await fetch(`/api/employees/${adminState.currentEditId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: newUsername })
            });
            if (resp.ok) {
                showToast('Логин обновлён');
                document.getElementById('editUsernameModal').style.display = 'none';
                loadEmployees();
                refreshCurrentReport();
            } else {
                const err = await resp.json();
                document.getElementById('usernameError').innerText = err.detail || 'Ошибка';
            }
        } catch (err) {
            document.getElementById('usernameError').innerText = 'Ошибка сети';
        }
    });

    document.getElementById('saveFullnameBtn').addEventListener('click', async () => {
        const newFullname = document.getElementById('newFullname').value.trim();
        if (!newFullname) {
            document.getElementById('fullnameError').innerText = 'ФИО не может быть пустым';
            return;
        }
        try {
            const resp = await fetch(`/api/employees/${adminState.currentEditId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ full_name: newFullname })
            });
            if (resp.ok) {
                showToast('ФИО обновлено');
                document.getElementById('editFullnameModal').style.display = 'none';
                loadEmployees();
                refreshCurrentReport();
            } else {
                const err = await resp.json();
                document.getElementById('fullnameError').innerText = err.detail || 'Ошибка';
            }
        } catch (err) {
            document.getElementById('fullnameError').innerText = 'Ошибка сети';
        }
    });

    document.querySelector('#editUsernameModal .close-username').onclick = () => {
        document.getElementById('editUsernameModal').style.display = 'none';
    };
    document.querySelector('#editFullnameModal .close-fullname').onclick = () => {
        document.getElementById('editFullnameModal').style.display = 'none';
    };
    window.addEventListener('click', (event) => {
        if (event.target === document.getElementById('editUsernameModal')) {
            document.getElementById('editUsernameModal').style.display = 'none';
        }
        if (event.target === document.getElementById('editFullnameModal')) {
            document.getElementById('editFullnameModal').style.display = 'none';
        }
    });

    let statusOrder = [];
    let dragSrcElement = null;

    function loadStatusOrder() {
        const saved = localStorage.getItem('dailyReportStatusOrder');
        if (saved) {
            statusOrder = JSON.parse(saved);
        } else {
            statusOrder = ['working', 'onbreak', 'notstarted', 'ended'];
        }
        applyOrderToUI();
    }

    function applyOrderToUI() {
        const container = document.getElementById('statusOrderList');
        const items = Array.from(container.children);
        items.sort((a, b) => {
            const aIdx = statusOrder.indexOf(a.dataset.status);
            const bIdx = statusOrder.indexOf(b.dataset.status);
            return aIdx - bIdx;
        });
        container.innerHTML = '';
        items.forEach(item => container.appendChild(item));
    }

    function saveStatusOrder() {
        const items = document.querySelectorAll('#statusOrderList li');
        statusOrder = Array.from(items).map(li => li.dataset.status);
        localStorage.setItem('dailyReportStatusOrder', JSON.stringify(statusOrder));
        showToast('Порядок статусов сохранён');
        const currentDate = document.getElementById('reportDate').value;
        if (currentDate) loadDailyReport(currentDate);
    }

    function initDragAndDrop() {
        const list = document.getElementById('statusOrderList');
        const items = list.querySelectorAll('li');
        items.forEach(item => item.setAttribute('draggable', 'true'));
        let dragItem = null;
        
        list.addEventListener('dragstart', (e) => {
            dragItem = e.target.closest('li');
            if (!dragItem) return;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', '');
            dragItem.classList.add('dragging');
        });
        
        list.addEventListener('dragend', (e) => {
            if (dragItem) dragItem.classList.remove('dragging');
            dragItem = null;
            saveStatusOrder();
        });
        
        list.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const targetItem = e.target.closest('li');
            if (!targetItem || targetItem === dragItem) return;
            
            const rect = targetItem.getBoundingClientRect();
            const midpoint = (rect.left + rect.right) / 2;
            if (e.clientX < midpoint) {
                targetItem.parentNode.insertBefore(dragItem, targetItem);
            } else {
                targetItem.parentNode.insertBefore(dragItem, targetItem.nextSibling);
            }
        });
    }

    loadStatusOrder();
    initDragAndDrop();

    export function refreshCurrentReport() {
        const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab;
        if (activeTab === 'daily') {
            const date = document.getElementById('reportDate').value;
            if (date) loadDailyReport(date);
        } else if (activeTab === 'weekly') {
            const weekPicker = document.getElementById('weekPicker');
            if (weekPicker && weekPicker.value) {
                const [year, week] = weekPicker.value.split('-W');
                const monday = getMondayOfWeek(parseInt(year), parseInt(week));
                const y = monday.getFullYear();
                const m = String(monday.getMonth() + 1).padStart(2, '0');
                const d = String(monday.getDate()).padStart(2, '0');
                loadWeeklyReport(`${y}-${m}-${d}`);
            }
        }
    }

    export function connectSSE() {
        if (adminState.eventSource) adminState.eventSource.close();
        adminState.eventSource = new EventSource('/api/admin/events/');
        
        adminState.eventSource.addEventListener('update', (e) => {
            console.log('Получено обновление, перезагружаем отчёты');
            refreshCurrentReport();
            const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab;
            if (activeTab === 'recent') {
                const limit = document.getElementById('recentLimit').value;
                loadRecentEntries(parseInt(limit));
            }
            if (activeTab === 'employees') {
                loadEmployees();
            }
            updateDraftBadge();
        });
        
        adminState.eventSource.onerror = () => {
            console.warn('SSE ошибка, переподключение через 5 секунд');
            adminState.eventSource.close();
            setTimeout(connectSSE, 5000);
        };
    }



    setTimeout(() => {
        connectSSE();
    }, 1000);



const dailyDateInput = document.getElementById('reportDate');
if (dailyDateInput) {
    dailyDateInput.addEventListener('change', function() {
        const date = this.value;
        if (date) loadReportForDate(date);
    });
}
document.getElementById('loadReportBtn').onclick = function() {
    const date = document.getElementById('reportDate').value;
    if (date) loadReportForDate(date);
};

const weekPickerInput = document.getElementById('weekPicker');
if (weekPickerInput) {
    weekPickerInput.addEventListener('change', function() {
        const weekValue = this.value;
        if (weekValue) {
            const [year, week] = weekValue.split('-W');
            const monday = getMondayOfWeek(parseInt(year), parseInt(week));
            const y = monday.getFullYear();
            const m = String(monday.getMonth() + 1).padStart(2, '0');
            const d = String(monday.getDate()).padStart(2, '0');
            const mondayStr = `${y}-${m}-${d}`;
            
            if (adminState.trafficModeActive) {
                // Если включён светофор – обновляем таблицу отметок
                const select = document.getElementById('weeklyTrafficEmployeeSelect');
                if (select && select.value) {
                    loadWeeklyTraffic(select.value);
                    saveTrafficState(true, select.value, weekValue);
                } else {
                    // Если сотрудник не выбран, просто сохраняем неделю
                    saveTrafficState(true, '', weekValue);
                }
            } else {
                loadWeeklyReport(mondayStr);
            }
        }
    });
}

export async function loadRoundingInterval() {
    const resp = await fetch('/api/admin/rounding', { credentials: 'include' });
    const data = await resp.json();
    document.getElementById('roundingInterval').value = data.interval_minutes;
}

export async function saveRoundingInterval(interval) {
    const resp = await fetch('/api/admin/rounding', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval_minutes: interval }),
        credentials: 'include'
    });
    if (!resp.ok) throw new Error('Ошибка сохранения');
}

const roundingModal = document.getElementById('roundingModal');
const closeRounding = document.querySelector('.close-rounding');
const saveBtn = document.getElementById('saveRoundingBtn');

if (closeRounding) {
    closeRounding.onclick = () => roundingModal.style.display = 'none';
}
window.addEventListener('click', (e) => { if (e.target === roundingModal) roundingModal.style.display = 'none'; });

saveBtn.onclick = async () => {
    const interval = parseInt(document.getElementById('roundingInterval').value);
    if (isNaN(interval) || interval < 1 || interval > 60) {
        document.getElementById('roundingError').innerText = 'Число от 1 до 60';
        return;
    }
    try {
        await saveRoundingInterval(interval);
        roundingModal.style.display = 'none';
        const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab;
        if (activeTab === 'daily') {
            const date = document.getElementById('reportDate').value;
            if (date) loadDailyReport(date);
        } else if (activeTab === 'weekly') {
            const weekPicker = document.getElementById('weekPicker');
            if (weekPicker && weekPicker.value) {
                const [year, week] = weekPicker.value.split('-W');
                const monday = getMondayOfWeek(parseInt(year), parseInt(week));
                const y = monday.getFullYear();
                const m = String(monday.getMonth() + 1).padStart(2, '0');
                const d = String(monday.getDate()).padStart(2, '0');
                loadWeeklyReport(`${y}-${m}-${d}`);
            }
        }
    } catch (err) {
        document.getElementById('roundingError').innerText = err.message;
    }
};
const weeklyRoundingBtn = document.getElementById('weeklyRoundingBtn');
if (weeklyRoundingBtn) {
    weeklyRoundingBtn.onclick = (e) => {
        e.stopPropagation();
        roundingModal.style.display = 'block';
        loadRoundingInterval();
    };
}

export async function insertScheduleRow(row, empId, expandBtn) {
    const resp = await fetch('/api/employees?active_only=false', { credentials: 'include' });
    const employees = await resp.json();
    const emp = employees.find(e => e.id == empId);
    const scheduleData = emp.schedule_data || {};
    const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    const today = new Date();
    const monday = getMonday(today);
    const cols = row.cells.length;
    const tr = document.createElement('tr');
    tr.className = 'schedule-row';

    const detailCell = createElement('td', { className: 'schedule-detail-cell' });
    detailCell.colSpan = cols;
    const table = createElement('table', { className: 'schedule-detail-table' });
    const headingRow = createElement('tr');
    for (let i = 0; i < weekdays.length; i++) {
        const dateObj = new Date(monday);
        dateObj.setDate(monday.getDate() + i);
        const dayStr = String(dateObj.getDate()).padStart(2, '0');
        const monthStr = String(dateObj.getMonth() + 1).padStart(2, '0');
        const dateDisplay = `${dayStr}.${monthStr}`;
        
        headingRow.append(createElement('th', { className: 'schedule-day-heading' }, [
            document.createTextNode(weekdays[i]),
            createElement('br'),
            createElement('span', { className: 'schedule-date-label', text: dateDisplay })
        ]));
    }
    table.append(createElement('thead', {}, headingRow));
    const tbody = createElement('tbody');
    const startRow = createElement('tr', { className: 'schedule-start-row' });
    for (let i = 0; i < weekdays.length; i++) {
        const start = scheduleData[i]?.start?.slice(0,5) || '';
        startRow.append(createElement('td', { className: 'schedule-time-cell' }, createElement('input', {
            className: 'schedule-time-input schedule-time-control',
            attrs: { type: 'text', value: start, placeholder: '' },
            dataset: { day: i, id: empId }
        })));
    }
    const endRow = createElement('tr', { className: 'schedule-end-row' });
    for (let i = 0; i < weekdays.length; i++) {
        const end = scheduleData[i]?.end?.slice(0,5) || '';
        endRow.append(createElement('td', { className: 'schedule-time-cell' }, createElement('input', {
            className: 'schedule-time-input schedule-time-control',
            attrs: { type: 'text', value: end, placeholder: '' },
            dataset: { day: i, id: empId }
        })));
    }
    tbody.append(startRow, endRow);
    table.append(tbody);
    detailCell.append(table);
    tr.append(detailCell);
    row.insertAdjacentElement('afterend', tr);
    expandBtn.textContent = '▲';

    function formatTimeString(val) {
        if (!val) return '';
        let str = val.toString().replace(/\D/g, '');
        if (str.length === 0) return '';
        if (str.length === 1) str = '0' + str + '00';
        else if (str.length === 2) str = str + '00';
        else if (str.length === 3) str = '0' + str;
        let hours = str.slice(0,2);
        let minutes = str.slice(2,4);
        hours = hours > 23 ? '23' : hours;
        minutes = minutes > 59 ? '59' : minutes;
        return `${hours}:${minutes}`;
    }

    const allInputs = tr.querySelectorAll('.schedule-time-input');
    let originalValues = [];
    for (let i = 0; i < allInputs.length; i++) {
        originalValues[i] = allInputs[i].value;
    }

    async function saveSchedule() {
        const newSchedule = {};
        let changed = false;
        for (let i = 0; i < weekdays.length; i++) {
            const startInput = allInputs[i];
            const endInput = allInputs[i + weekdays.length];
            let start = startInput.value.trim();
            let end = endInput.value.trim();

            if (start) start = formatTimeString(start);
            if (end) end = formatTimeString(end);

            const oldStart = scheduleData[i]?.start || '';
            const oldEnd = scheduleData[i]?.end || '';

            if (start !== oldStart || end !== oldEnd) changed = true;

            if (start || end) {
                newSchedule[i] = {};
                if (start) newSchedule[i].start = start;
                if (end) newSchedule[i].end = end;
            }
        }

        if (!changed) return;

        try {
            const resp = await fetch(`/api/employees/${empId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ schedule_data: newSchedule }),
                credentials: 'include'
            });
            if (resp.ok) {
                showToast('Расписание сохранено', false);
                Object.assign(scheduleData, newSchedule);
                for (let i = 0; i < allInputs.length; i++) {
                    originalValues[i] = allInputs[i].value;
                }
                // Обновляем цвет стрелки в зависимости от наличия расписания
                const hasAnySchedule = Object.keys(newSchedule).length > 0;
                const newColor = hasAnySchedule ? '#166534' : '#991b1b';
                const btn = document.querySelector(`.expand-schedule-btn[data-id="${empId}"]`);
                if (btn) {
                    btn.style.color = newColor;
                }
            } else {
                showToast('Ошибка сохранения', true);
            }
        } catch (err) {
            showToast('Ошибка сети', true);
        }
    }

    const handleBlur = (e) => {
        const inp = e.target;
        let val = inp.value.trim();
        if (val === '') {
            inp.value = '';
        } else {
            const formatted = formatTimeString(val);
            inp.value = formatted;
        }
        saveSchedule();
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter') {
            e.target.blur();
        }
    };

    allInputs.forEach(inp => {
        inp.addEventListener('blur', handleBlur);
        inp.addEventListener('keypress', handleKeyPress);
    });

    const startInputs = tr.querySelectorAll('.schedule-start-row .schedule-time-input');
    const endInputs = tr.querySelectorAll('.schedule-end-row .schedule-time-input');

    function copyToSiblings(clickedInput, siblingInputs) {
        const value = clickedInput.value;
        siblingInputs.forEach(inp => {
            if (inp !== clickedInput) {
                inp.value = value;
            }
        });
        saveSchedule();
    }

    startInputs.forEach(inp => {
        inp.addEventListener('dblclick', () => {
            copyToSiblings(inp, startInputs);
        });
    });
    endInputs.forEach(inp => {
        inp.addEventListener('dblclick', () => {
            copyToSiblings(inp, endInputs);
        });
    });
}



document.addEventListener('click', event => {
    const button = event.target.closest('.employee-detail-button');
    if (!button) return;
    showEmployeeDetail(Number(button.dataset.employeeId), button.dataset.reportDate);
});
