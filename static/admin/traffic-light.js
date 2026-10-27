/**
 * Модуль админ-панели: Недельный, дневной и периодный светофор.
 * Подключается через main.js и использует явные ES module зависимости.
 */
import { adminState, STORAGE_KEYS, TRAFFIC_ACTIONS, TRAFFIC_LABELS } from './state.js';
import { formatDateLocal, showToast } from './core.js';
import { getMondayOfWeek, formatHoursToHHMM, formatMinutesToHHMM, loadDailyReport } from './reports.js';
import { closeRoleModal, loadEmployees } from './actions.js';
import { createElement, showMessage } from './dom.js';

const roleModal = document.getElementById('roleModal');
const closeRoleModalBtn = document.querySelector('.close-role-modal');
const cancelRoleBtn = document.getElementById('cancelRoleBtn');
const assignRoleBtn = document.getElementById('assignRoleBtn');
const createRoleAndAssignBtn = document.getElementById('createRoleAndAssignBtn');
const roleSelect = document.getElementById('roleSelect');
const newRoleNameInput = document.getElementById('newRoleNameInput');
const roleModalError = document.getElementById('roleModalError');
let trafficClickOutsideHandler = null;
let dailyTrafficClickHandler = null;
let weeklyTrafficDates = [];
let weeklyEntriesByDay = {};

// --- Функция загрузки списка сотрудников для выпадающего списка ---
export async function loadTrafficEmployees() {
    try {
        const resp = await fetch('/api/employees?active_only=true', { credentials: 'include' });
        if (!resp.ok) throw new Error('Ошибка загрузки сотрудников');
        let employees = await resp.json();
        employees.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
        const select = document.getElementById('weeklyTrafficEmployeeSelect');
        select.innerHTML = '<option value="">Выберите сотрудника</option>';
        employees.forEach(emp => {
            const opt = document.createElement('option');
            opt.value = emp.id;
            opt.textContent = emp.full_name;
            select.appendChild(opt);
        });
        const savedEmp = localStorage.getItem(STORAGE_KEYS.trafficEmployee);
        if (savedEmp && select.querySelector(`option[value="${savedEmp}"]`)) {
            select.value = savedEmp;
            if (adminState.trafficModeActive) {
                loadWeeklyTraffic(savedEmp);
            }
        }
    } catch (err) {
        showToast('Ошибка загрузки списка сотрудников', true);
        console.error(err);
    }
}

export async function loadWeeklyTraffic(employeeId) {
    const container = document.getElementById('weeklyTrafficTableContainer');
    const summaryDiv = document.getElementById('weeklyTrafficSummary');
    if (!employeeId) {
        showMessage(container, 'Выберите сотрудника для отображения отметок');
        if (summaryDiv) summaryDiv.style.display = 'none';
        return;
    }
    container.innerHTML = '<p>Загрузка...</p>';
    if (summaryDiv) summaryDiv.style.display = 'none';

    const weekPicker = document.getElementById('weekPicker');
    const weekValue = weekPicker.value;
    if (!weekValue) {
        showMessage(container, 'Не выбрана неделя', 'error');
        if (summaryDiv) summaryDiv.style.display = 'none';
        return;
    }
    const [year, week] = weekValue.split('-W');
    const monday = getMondayOfWeek(parseInt(year), parseInt(week));
    const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    const dates = [];
    for (let i = 0; i < 7; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        dates.push(d);
    }

    weeklyTrafficDates = dates.map(d => {
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    });

    const y = monday.getFullYear();
    const m = String(monday.getMonth() + 1).padStart(2, '0');
    const d = String(monday.getDate()).padStart(2, '0');
    const mondayStr = `${y}-${m}-${d}`;

    let weeklyReport = null;
    try {
        const resp = await fetch(`/api/reports/weekly?start_date=${mondayStr}`, { credentials: 'include' });
        if (!resp.ok) throw new Error('Ошибка загрузки недельного отчёта');
        weeklyReport = await resp.json();
    } catch (err) {
        showMessage(container, `Ошибка загрузки: ${err.message}`, 'error');
        if (summaryDiv) summaryDiv.style.display = 'none';
        return;
    }

    const empData = weeklyReport.find(emp => emp.employee_id == employeeId);
    if (!empData) {
        showMessage(container, 'Нет данных за эту неделю для выбранного сотрудника');
        if (summaryDiv) summaryDiv.style.display = 'none';
        return;
    }

    // --- СТАТИСТИКА ---
    if (summaryDiv) {
        const totalWorkedDisplay = empData.total_worked_display || formatHoursToHHMM(empData.total_worked_hours || 0);
        const totalRawWorked = empData.total_raw_worked_hours;
        const totalBreak = empData.total_break_minutes || 0;

        document.getElementById('trafficWorked').textContent = totalWorkedDisplay;
        const rawSpan = document.getElementById('trafficWorkedRaw');
        if (totalRawWorked !== undefined && totalRawWorked !== null) {
            rawSpan.textContent = `(${formatHoursToHHMM(totalRawWorked)})`;
            rawSpan.style.display = 'inline';
        } else {
            rawSpan.style.display = 'none';
        }
        document.getElementById('trafficBreak').textContent = formatMinutesToHHMM(totalBreak);
        summaryDiv.style.display = 'flex';
    }

    // --- ЗАГРУЖАЕМ ОТМЕТКИ И РАЗДЕЛЯЕМ ИХ ---
    const otherEntriesByDay = {};
    const endEntriesByDay = {};
    let maxOtherEntries = 0;

    for (let i = 0; i < dates.length; i++) {
        const dateObj = dates[i];
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, '0');
        const day = String(dateObj.getDate()).padStart(2, '0');
        const dateStr = `${year}-${month}-${day}`;
        try {
            const resp = await fetch(`/api/reports/employee/${employeeId}?date=${dateStr}`, { credentials: 'include' });
            if (!resp.ok) throw new Error('Ошибка загрузки отметок');
            const data = await resp.json();
            const entries = data.entries || [];
            entries.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

            // Разделяем: все кроме 'end' и отдельно 'end'
            const otherEntries = entries.filter(e => e.action !== 'end');
            const endEntry = entries.find(e => e.action === 'end') || null;
            otherEntriesByDay[i] = otherEntries;
            endEntriesByDay[i] = endEntry;
            if (otherEntries.length > maxOtherEntries) maxOtherEntries = otherEntries.length;
        } catch (err) {
            console.warn(`Не удалось загрузить отметки за ${dateStr}`, err);
            otherEntriesByDay[i] = [];
            endEntriesByDay[i] = null;
        }
    }

    if (maxOtherEntries === 0 && Object.values(endEntriesByDay).every(e => e === null)) {
        // Нет записей — всё равно показываем таблицу с пустыми ячейками
        maxOtherEntries = 1; // как минимум одна строка для прочих отметок
    }

    const colorClassMap = {
        'start': 'recent-start',
        'break_start': 'recent-break-start',
        'break_end': 'recent-break-end',
        'end': 'recent-end'
    };

    // --- СТРОИМ ТАБЛИЦУ ---
    const table = createElement('table', { className: 'weekly-entry-grid' });
    const headingRow = createElement('tr');
    for (let i = 0; i < 7; i++) {
        const d = dates[i];
        const dayName = weekdays[i];
        const dayNum = String(d.getDate()).padStart(2, '0');
        const monthNum = String(d.getMonth() + 1).padStart(2, '0');
        const dateStr = `${d.getFullYear()}-${monthNum}-${dayNum}`;
        const dayData = empData.days[i] || {};
        const workedDisplay = dayData.worked_display || '00:00 (00:00)';
        const breakMinutes = dayData.break_minutes || 0;
        const breakCount = dayData.break_count || 0;
        const breakDisplay = formatMinutesToHHMM(breakMinutes) + ' (' + breakCount + ')';
        const isZero = !dayData.worked_hours || dayData.worked_hours === 0;

        const heading = createElement('th', { className: 'weekly-day-column', dataset: { dayHeaderIndex: i } });
        heading.append(createElement('div', {}, [
            document.createTextNode(dayName), createElement('br'), createElement('span', { className: 'weekly-day-date', text: `${dayNum}.${monthNum}` })
        ]));
        const addButton = createElement('span', {
            className: 'add-entry-btn weekly-add-entry', text: '➕', attrs: { role: 'button', tabindex: '0' }, dataset: { day: i, date: dateStr }
        });
        if (!isZero) {
            heading.append(
                createElement('div', { className: 'weekly-day-summary' }, [
                    createElement('div', { className: 'weekly-worked-value', text: workedDisplay }), addButton
                ]),
                createElement('div', { className: 'weekly-break-value', text: breakDisplay })
            );
        } else {
            heading.append(createElement('div', { className: 'weekly-empty-actions' }, addButton));
        }
        headingRow.append(heading);
    }
    table.append(createElement('thead', {}, headingRow));

    // Строки для остальных отметок (кроме end)
    const tbody = createElement('tbody');
    for (let row = 0; row < maxOtherEntries; row++) {
        const tableRow = createElement('tr');
        for (let i = 0; i < 7; i++) {
            const otherEntries = otherEntriesByDay[i] || [];
            if (row < otherEntries.length) {
                const entry = otherEntries[row];
                const time = entry.timestamp.slice(11, 16);
                const colorClass = colorClassMap[entry.action] || '';
                tableRow.append(createElement('td', {
                    className: `traffic-mark-cell ${colorClass} ${colorClass ? '' : 'is-uncolored'}`.trim(),
                    text: time, dataset: { entryId: entry.id }
                }));
            } else {
                tableRow.append(createElement('td', { className: 'traffic-mark-cell is-empty', text: '—' }));
            }
        }
        tbody.append(tableRow);
    }

    // Последняя строка для end-отметок
    const endRow = createElement('tr');
    for (let i = 0; i < 7; i++) {
        const endEntry = endEntriesByDay[i];
        if (endEntry) {
            const time = endEntry.timestamp.slice(11, 16);
            const colorClass = colorClassMap['end'];
            endRow.append(createElement('td', {
                className: `traffic-mark-cell ${colorClass} ${colorClass ? '' : 'is-uncolored'}`.trim(), text: time,
                dataset: { entryId: endEntry.id, timestamp: endEntry.timestamp, action: 'end' }
            }));
        } else {
            endRow.append(createElement('td', { className: 'traffic-mark-cell is-empty', text: '—' }));
        }
    }
    tbody.append(endRow);
    table.append(tbody);
    container.replaceChildren(table);

    // --- ОБРАБОТЧИКИ КЛИКОВ И КНОПОК "+" (без изменений, но нужно адаптировать к новым данным) ---
    // Чтобы не потерять функциональность, оставляем их как в исходном коде,
    // но теперь они используют otherEntriesByDay и endEntriesByDay для поиска записей.
    // Если в исходном коде были обработчики, использующие _lastEntriesByDay, их нужно переделать.
    // Ниже приведены обработчики из оригинального кода — они должны работать и с новой структурой,
    // так как мы сохранили _otherEntriesByDay и _endEntriesByDay, но обработчики могут использовать другие глобальные переменные.
    // Для простоты я оставлю их без изменений, но если вы использовали _lastEntriesByDay, замените его на объединённые данные.
    // В целях безопасности, скопируйте обработчики из вашего текущего кода (они уже есть в функции) и вставьте их сюда.

    // --- Дополнительно: сохраняем все записи для обработчиков (объединяем otherEntries и endEntries) ---
    const allEntriesByDay = {};
    for (let i = 0; i < 7; i++) {
        const others = otherEntriesByDay[i] || [];
        const end = endEntriesByDay[i];
        allEntriesByDay[i] = end ? [...others, end] : others;
    }
    weeklyEntriesByDay = allEntriesByDay;

    // --- Обработчики для кнопок "+" ---
    container.querySelectorAll('.add-entry-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const dayIndex = parseInt(this.dataset.day);
            const dateStr = this.dataset.date;
            const empId = parseInt(document.getElementById('weeklyTrafficEmployeeSelect').value);
            if (!empId) {
                showToast('Сначала выберите сотрудника', true);
                return;
            }
            if (this.textContent.trim() === '➖') {
                const oldRow = document.querySelector('.add-entry-row');
                if (oldRow) oldRow.remove();
                const addTd = document.querySelector('.entry-cell.editing[data-adding="true"]');
                if (addTd) closeAddMode(addTd);
                this.textContent = '➕';
                return;
            }
            const table = container.querySelector('table');
            if (!table) return;
            const tbody = table.querySelector('tbody');
            if (!tbody) return;
            const rows = tbody.querySelectorAll('tr:not(.add-entry-row)');
            let targetTd = null;
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length > dayIndex) {
                    const td = cells[dayIndex];
                    if (td.textContent.trim() === '—') {
                        targetTd = td;
                        break;
                    }
                }
            }
            if (targetTd) {
                makeCellAddable(targetTd, dayIndex, dateStr, empId);
            } else {
                const addTd = document.querySelector('.entry-cell.editing[data-adding="true"]');
                if (addTd) closeAddMode(addTd);
                openAddRow(dayIndex, dateStr, empId);
            }
        });
    });

    // --- Обработчик клика по ячейке (для редактирования/добавления) ---
    container.addEventListener('click', function(e) {
        // Клики по полям и кнопкам уже открытого редактора не должны повторно
        // запускать редактирование ячейки с исходными данными.
        if (e.target.closest('.edit-controls')) return;
        const td = e.target.closest('td');
        if (!td) return;
        if (td.closest('.add-entry-row')) return;
        if (td.classList.contains('add-entry-cell')) return;
        const text = td.textContent.trim();
        const empId = parseInt(document.getElementById('weeklyTrafficEmployeeSelect').value);
        if (!empId) {
            showToast('Сначала выберите сотрудника', true);
            return;
        }

        if (text && text !== '—') {
            const entryId = td.dataset.entryId;
            if (!entryId) {
                showToast('Не удалось найти запись (нет ID)', true);
                return;
            }
            let foundEntry = null;
            for (const day in weeklyEntriesByDay) {
                const entry = weeklyEntriesByDay[day].find(e => e.id == entryId);
                if (entry) {
                    foundEntry = entry;
                    break;
                }
            }
            if (!foundEntry) {
                showToast('Не удалось найти запись', true);
                return;
            }
            makeCellEditable(td, parseInt(entryId), foundEntry.timestamp, foundEntry.action, empId);
            return;
        }

        if (text === '—') {
            const row = td.closest('tr');
            const cells = row.querySelectorAll('td');
            let dayIndex = -1;
            for (let i = 0; i < cells.length; i++) {
                if (cells[i] === td) {
                    dayIndex = i;
                    break;
                }
            }
            if (dayIndex < 0 || dayIndex > 6) {
                showToast('Не удалось определить день', true);
                return;
            }
            if (!weeklyTrafficDates || !weeklyTrafficDates[dayIndex]) {
                showToast('Не удалось определить дату', true);
                return;
            }
            const dateStr = weeklyTrafficDates[dayIndex];
            makeCellAddable(td, dayIndex, dateStr, empId);
        }
    });

    // --- Закрытие редакторов при клике вне ---
    if (trafficClickOutsideHandler) {
        document.removeEventListener('click', trafficClickOutsideHandler);
    }
    trafficClickOutsideHandler = function(e) {
        if (!container.contains(e.target)) {
            if (adminState.currentlyEditingId !== null) closeEditMode();
            const addTd = document.querySelector('.entry-cell.editing[data-adding="true"]');
            if (addTd) closeAddMode(addTd);
        }
    };
    document.addEventListener('click', trafficClickOutsideHandler);

}
// --- Обработчик изменения выбора сотрудника ---
document.getElementById('weeklyTrafficEmployeeSelect').addEventListener('change', function() {
    const employeeId = this.value;
    if (employeeId && adminState.trafficModeActive) {
        loadWeeklyTraffic(employeeId);
        const weekValue = document.getElementById('weekPicker').value;
        saveTrafficState(adminState.trafficModeActive, employeeId, weekValue);
    } else if (!employeeId) {
        showMessage(document.getElementById('weeklyTrafficTableContainer'), 'Выберите сотрудника для отображения отметок');
        saveTrafficState(adminState.trafficModeActive, '', document.getElementById('weekPicker').value);
    }
});

// --- Обновление таблицы трафика при смене недели (если активен режим) ---
const weekPickerTraffic = document.getElementById('weekPicker');
weekPickerTraffic.addEventListener('change', function() {
    if (adminState.trafficModeActive) {
        const select = document.getElementById('weeklyTrafficEmployeeSelect');
        if (select.value) {
            loadWeeklyTraffic(select.value);
            saveTrafficState(adminState.trafficModeActive, select.value, this.value);
        } else {
            saveTrafficState(adminState.trafficModeActive, '', this.value);
        }
    }
});
export function createAddRow(dayIndex, employeeId, dateStr) {
    const tr = document.createElement('tr');
    tr.className = 'add-entry-row';
    tr.dataset.day = dayIndex;
    
    const color = 'start';
    const colorClass = 'start';
    
    for (let i = 0; i < 7; i++) {
        const td = document.createElement('td');
        td.style.padding = '8px';
        td.style.textAlign = 'center';
        td.style.borderRadius = '8px';
        td.style.background = '#f8fafc';
        
        if (i === dayIndex) {
            td.className = 'add-entry-cell';
            td.style.background = '#f1f5f9';
            td.innerHTML = `
                <input type="text" class="add-entry-input" id="add-time-${dayIndex}" placeholder="ЧЧ:ММ" maxlength="5" autofocus>
                <div class="add-entry-color start" id="add-color-${dayIndex}" data-color="start"></div>
                <button class="add-entry-save" id="add-save-${dayIndex}" data-day="${dayIndex}" data-date="${dateStr}" data-employee="${employeeId}">✔️</button>
            `;
        }
        tr.appendChild(td);
    }
    
    const input = tr.querySelector('.add-entry-input');
    const colorEl = tr.querySelector('.add-entry-color');
    const saveBtn = tr.querySelector('.add-entry-save');
    
    // Исправленный автоформат времени
    input.addEventListener('input', function(e) {
        let val = this.value.replace(/\D/g, '');
        if (val.length > 4) val = val.slice(0, 4);
        if (val.length === 0) {
            this.value = '';
            return;
        }
        let formatted = '';
        if (val.length <= 2) {
            formatted = val;
        } else if (val.length === 3) {
            formatted = val[0] + ':' + val.slice(1);
        } else if (val.length === 4) {
            formatted = val.slice(0, 2) + ':' + val.slice(2);
        }
        this.value = formatted;
    });
    
    // Переключение цвета по клику
    let colorIndex = 0;
    colorEl.addEventListener('click', function() {
        colorIndex = (colorIndex + 1) % TRAFFIC_ACTIONS.length;
        const newColor = TRAFFIC_ACTIONS[colorIndex];
        this.dataset.color = newColor;
        this.className = `add-entry-color ${newColor}`;
    });
    
    // Сохранение
    saveBtn.addEventListener('click', async function() {
        const timeStr = input.value.trim();
        if (!timeStr || !timeStr.includes(':')) {
            showToast('Введите корректное время (ЧЧ:ММ)', true);
            return;
        }
        let hours = timeStr.split(':')[0];
        let minutes = timeStr.split(':')[1];
        hours = hours.padStart(2, '0');
        minutes = minutes.padStart(2, '0');
        if (parseInt(hours) > 23 || parseInt(minutes) > 59) {
            showToast('Некорректное время', true);
            return;
        }
        const action = colorEl.dataset.color;
        const date = this.dataset.date;
        const empId = parseInt(this.dataset.employee);
        const isoDateTime = `${date}T${hours}:${minutes}:00`;
        
        this.disabled = true;
        try {
            const resp = await fetch('/api/admin/timelog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    employee_id: empId,
                    action: action,
                    timestamp: isoDateTime
                })
            });
            if (resp.ok) {
                showToast(`✅ Отметка "${TRAFFIC_LABELS[action]}" добавлена в ${timeStr}`);
                tr.remove();
                const currentEmpId = document.getElementById('weeklyTrafficEmployeeSelect').value;
                if (currentEmpId) loadWeeklyTraffic(currentEmpId);
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка сохранения', true);
            }
        } catch (err) {
            showToast('Ошибка сети', true);
        } finally {
            this.disabled = false;
        }
    });
    
    return tr;
}
export function makeCellEditable(td, entryId, timestamp, action, employeeId) {
    // Закрываем ячейку добавления, если она открыта
    const addTd = document.querySelector('.entry-cell.editing[data-adding="true"]');
    if (addTd) closeAddMode(addTd);
    
    // Удаляем строку добавления, если она есть (на случай старого метода)
    const addRow = document.querySelector('.add-entry-row');
    if (addRow) addRow.remove();
    
    // Если уже редактируется другая запись, закрываем её
    if (adminState.currentlyEditingId !== null) {
        closeEditMode();
    }
    
    adminState.currentlyEditingId = entryId;
    const timeStr = timestamp.slice(11, 16);
    const currentColor = action;
    
    // Сохраняем оригинальное содержимое для восстановления
    const originalHtml = td.innerHTML;
    td.dataset.originalHtml = originalHtml;
    td.dataset.originalTime = timeStr;
    td.dataset.originalAction = currentColor;
    
    // Строим контролы редактирования
    td.dataset.originalClasses = td.className;
    td.className = 'entry-cell editing';
    td.style.padding = '4px';
    td.style.textAlign = 'center';
    td.style.borderRadius = '8px';
    td.style.backgroundColor = '#f8fafc';
    
    const colorClassMap = {
        'start': 'start',
        'break_start': 'break_start',
        'break_end': 'break_end',
        'end': 'end'
    };
    
    const colorCycleLocal = ['start', 'break_start', 'break_end', 'end'];
    let colorIndex = colorCycleLocal.indexOf(currentColor);
    if (colorIndex === -1) colorIndex = 0;
    let currentEditColor = colorCycleLocal[colorIndex];
    
    td.innerHTML = `
        <div class="edit-controls">
            <input type="text" class="edit-time-input" value="${timeStr}" maxlength="5">
            <div class="edit-color-btn ${colorClassMap[currentEditColor] || 'start'}"></div>
            <button class="edit-save-btn" title="Сохранить">✔️</button>
            <button class="edit-delete-btn" title="Удалить">✖️</button>
        </div>
    `;
    
    const input = td.querySelector('.edit-time-input');
    const colorBtn = td.querySelector('.edit-color-btn');
    const saveBtn = td.querySelector('.edit-save-btn');
    const deleteBtn = td.querySelector('.edit-delete-btn');
    
    // Автоформат времени
    input.addEventListener('input', function(e) {
        let val = this.value.replace(/\D/g, '');
        if (val.length > 4) val = val.slice(0, 4);
        if (val.length === 0) {
            this.value = '';
            return;
        }
        let formatted = '';
        if (val.length <= 2) {
            formatted = val;
        } else if (val.length === 3) {
            formatted = val[0] + ':' + val.slice(1);
        } else if (val.length === 4) {
            formatted = val.slice(0, 2) + ':' + val.slice(2);
        }
        this.value = formatted;
    });
    
    // Переключение цвета
    colorBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        colorIndex = (colorIndex + 1) % colorCycleLocal.length;
        const newColor = colorCycleLocal[colorIndex];
        currentEditColor = newColor;
        this.className = `edit-color-btn ${newColor}`;
    });
    
    // Сохранение изменений
    saveBtn.addEventListener('click', async function(e) {
        e.stopPropagation();
        const timeStr = input.value.trim();
        if (!timeStr || !timeStr.includes(':')) {
            showToast('Введите корректное время (ЧЧ:ММ)', true);
            return;
        }
        let hours = timeStr.split(':')[0];
        let minutes = timeStr.split(':')[1];
        hours = hours.padStart(2, '0');
        minutes = minutes.padStart(2, '0');
        if (parseInt(hours) > 23 || parseInt(minutes) > 59) {
            showToast('Некорректное время', true);
            return;
        }
        const newAction = currentEditColor;
        const newTime = `${hours}:${minutes}`;
        const date = timestamp.slice(0, 10);
        const isoDateTime = `${date}T${newTime}:00`;
        
        saveBtn.disabled = true;
        deleteBtn.disabled = true;
        
        try {
            const resp = await fetch(`/api/admin/timelog/${entryId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timestamp: isoDateTime, action: newAction })
            });
            if (resp.ok) {
                showToast(`✅ Отметка обновлена на ${newTime}`);
                closeEditMode();
                const empId = parseInt(document.getElementById('weeklyTrafficEmployeeSelect').value);
                if (empId) loadWeeklyTraffic(empId);
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка обновления', true);
                saveBtn.disabled = false;
                deleteBtn.disabled = false;
            }
        } catch (err) {
            showToast('Ошибка сети', true);
            saveBtn.disabled = false;
            deleteBtn.disabled = false;
        }
    });
    
    // Удаление отметки
    deleteBtn.addEventListener('click', async function(e) {
        e.stopPropagation();
        if (!confirm('Удалить эту отметку?')) return;
        deleteBtn.disabled = true;
        saveBtn.disabled = true;
        try {
            const resp = await fetch(`/api/admin/timelog/${entryId}`, { method: 'DELETE' });
            if (resp.ok) {
                showToast('🗑️ Отметка удалена');
                closeEditMode();
                const empId = parseInt(document.getElementById('weeklyTrafficEmployeeSelect').value);
                if (empId) loadWeeklyTraffic(empId);
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка удаления', true);
                deleteBtn.disabled = false;
                saveBtn.disabled = false;
            }
        } catch (err) {
            showToast('Ошибка сети', true);
            deleteBtn.disabled = false;
            saveBtn.disabled = false;
        }
    });
    
    // Фокус на поле ввода
    setTimeout(() => input.focus(), 50);
    input.select();
    
    // Сохранение по Enter
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveBtn.click();
        }
        if (e.key === 'Escape') {
            e.preventDefault();
            closeEditMode();
        }
    });
}

export function closeEditMode() {
    if (adminState.currentlyEditingId === null) return;
    const td = document.querySelector(`.entry-cell.editing`);
    if (td) {
        const originalClasses = td.dataset.originalClasses || '';
        td.className = originalClasses;
        td.innerHTML = td.dataset.originalHtml || '';
        td.style.padding = '12px 8px';
        td.style.textAlign = 'center';
        td.style.borderRadius = '8px';
        td.style.backgroundColor = '';
        td.style.border = '';
        td.style.boxShadow = '';
        delete td.dataset.originalClasses;
        delete td.dataset.originalHtml;
        delete td.dataset.originalTime;
        delete td.dataset.originalAction;
    }
    adminState.currentlyEditingId = null;
}
export function openAddRow(dayIndex, dateStr, employeeId, targetRow) {
    if (!employeeId) {
        showToast('Сначала выберите сотрудника', true);
        return false;
    }
    
    // Закрываем ячейку добавления, если она есть
    const addTd = document.querySelector('.entry-cell.editing[data-adding="true"]');
    if (addTd) closeAddMode(addTd);

    // Закрываем редактирование, если оно открыто
    closeEditMode();
    
    // Удаляем старую строку добавления, если есть
    const oldRow = document.querySelector('.add-entry-row');
    if (oldRow) oldRow.remove();
    
    const table = document.querySelector('#weeklyTrafficTableContainer table');
    if (!table) return false;
    const tbody = table.querySelector('tbody');
    if (!tbody) return false;
    
    const newRow = createAddRow(dayIndex, employeeId, dateStr);
    
    // Вставляем перед targetRow, если он передан и является дочерним для tbody
    if (targetRow && targetRow.parentNode === tbody) {
        tbody.insertBefore(newRow, targetRow);
    } else {
        tbody.insertBefore(newRow, tbody.firstChild);
    }
    
    // Меняем кнопку ➕ на ➖ в соответствующем заголовке
    const headers = table.querySelectorAll('thead th');
    // внутри openAddRow, после смены текста
    if (headers[dayIndex]) {
        const addBtn = headers[dayIndex].querySelector('.add-entry-btn');
        if (addBtn) {
            addBtn.textContent = '➖';
        }
    }
    
    const input = newRow.querySelector('.add-entry-input');
    if (input) setTimeout(() => input.focus(), 100);
    return true;
}
export function saveTabState(tabId) {
    localStorage.setItem(STORAGE_KEYS.tab, tabId);
}

export function saveTrafficState(mode, employeeId, weekValue) {
    localStorage.setItem(STORAGE_KEYS.trafficMode, mode ? 'true' : 'false');
    if (employeeId) localStorage.setItem(STORAGE_KEYS.trafficEmployee, employeeId);
    else localStorage.removeItem(STORAGE_KEYS.trafficEmployee);
    if (weekValue) localStorage.setItem(STORAGE_KEYS.trafficWeek, weekValue);
    else localStorage.removeItem(STORAGE_KEYS.trafficWeek);
}

export function restoreTabState() {
    return localStorage.getItem(STORAGE_KEYS.tab) || 'daily';
}

export function restoreTrafficState() {
    const mode = localStorage.getItem(STORAGE_KEYS.trafficMode) === 'true';
    const employeeId = localStorage.getItem(STORAGE_KEYS.trafficEmployee) || '';
    const weekValue = localStorage.getItem(STORAGE_KEYS.trafficWeek) || '';
    return { mode, employeeId, weekValue };
}
export function makeCellAddable(td, dayIndex, dateStr, employeeId) {
    // Закрываем старую добавляемую ячейку, если есть
    const oldAddTd = document.querySelector('.entry-cell.editing[data-adding="true"]');
    if (oldAddTd) closeAddMode(oldAddTd);
    
    // Если уже есть редактирование – закрываем его
    if (adminState.currentlyEditingId !== null) {
        closeEditMode();
    }
    // Удаляем строку добавления, если она есть (на случай, если осталась)
    const addRow = document.querySelector('.add-entry-row');
    if (addRow) addRow.remove();

    // Сохраняем оригинальное содержимое и индекс дня
    const originalHtml = td.innerHTML;
    td.dataset.originalHtml = originalHtml;
    td.dataset.adding = 'true';
    td.dataset.dayIndex = dayIndex;

    // Строим контролы добавления
    td.className = 'entry-cell editing';
    td.style.padding = '4px';
    td.style.textAlign = 'center';
    td.style.borderRadius = '8px';
    td.style.backgroundColor = '#f8fafc';

    const colorCycle = ['start', 'break_start', 'break_end', 'end'];
    let colorIndex = 0;
    let currentColor = colorCycle[colorIndex];

    const colorClassMap = {
        'start': 'start',
        'break_start': 'break_start',
        'break_end': 'break_end',
        'end': 'end'
    };

    td.innerHTML = `
        <div class="edit-controls">
            <input type="text" class="edit-time-input" placeholder="ЧЧ:ММ" maxlength="5" autofocus>
            <div class="edit-color-btn ${colorClassMap[currentColor]}"></div>
            <button class="edit-save-btn" title="Добавить">✔️</button>
            <button class="edit-delete-btn" title="Отмена">✖️</button>
        </div>
    `;

    const input = td.querySelector('.edit-time-input');
    const colorBtn = td.querySelector('.edit-color-btn');
    const saveBtn = td.querySelector('.edit-save-btn');
    const cancelBtn = td.querySelector('.edit-delete-btn');

    // Автоформат времени
    input.addEventListener('input', function(e) {
        let val = this.value.replace(/\D/g, '');
        if (val.length > 4) val = val.slice(0, 4);
        if (val.length === 0) {
            this.value = '';
            return;
        }
        let formatted = '';
        if (val.length <= 2) {
            formatted = val;
        } else if (val.length === 3) {
            formatted = val[0] + ':' + val.slice(1);
        } else if (val.length === 4) {
            formatted = val.slice(0, 2) + ':' + val.slice(2);
        }
        this.value = formatted;
    });

    // Переключение цвета
    colorBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        colorIndex = (colorIndex + 1) % colorCycle.length;
        currentColor = colorCycle[colorIndex];
        this.className = `edit-color-btn ${colorClassMap[currentColor]}`;
    });

    // Сохранение (добавление)
    saveBtn.addEventListener('click', async function(e) {
        e.stopPropagation();
        const timeStr = input.value.trim();
        if (!timeStr || !timeStr.includes(':')) {
            showToast('Введите корректное время (ЧЧ:ММ)', true);
            return;
        }
        let hours = timeStr.split(':')[0];
        let minutes = timeStr.split(':')[1];
        hours = hours.padStart(2, '0');
        minutes = minutes.padStart(2, '0');
        if (parseInt(hours) > 23 || parseInt(minutes) > 59) {
            showToast('Некорректное время', true);
            return;
        }
        const action = currentColor;
        const date = dateStr;
        const isoDateTime = `${date}T${hours}:${minutes}:00`;

        saveBtn.disabled = true;
        cancelBtn.disabled = true;

        try {
            const resp = await fetch('/api/admin/timelog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    employee_id: employeeId,
                    action: action,
                    timestamp: isoDateTime
                })
            });
            if (resp.ok) {
                showToast(`✅ Отметка "${TRAFFIC_LABELS[action]}" добавлена в ${hours}:${minutes}`);
                closeAddMode(td);
                const empId = parseInt(document.getElementById('weeklyTrafficEmployeeSelect').value);
                if (empId) loadWeeklyTraffic(empId);
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка сохранения', true);
                saveBtn.disabled = false;
                cancelBtn.disabled = false;
            }
        } catch (err) {
            showToast('Ошибка сети', true);
            saveBtn.disabled = false;
            cancelBtn.disabled = false;
        }
    });

    // Отмена (закрыть без сохранения)
    cancelBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        closeAddMode(td);
    });

    // Фокус на поле ввода
    setTimeout(() => input.focus(), 50);
    input.select();

    // Сохранение по Enter, отмена по Escape
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveBtn.click();
        }
        if (e.key === 'Escape') {
            e.preventDefault();
            cancelBtn.click();
        }
    });

    // ----- ИСПРАВЛЕНИЕ: делаем кнопку видимой -----
    const th = document.querySelector(`#weeklyTrafficTableContainer th[data-day-header-index="${dayIndex}"]`);
    if (th) {
        const btn = th.querySelector('.add-entry-btn');
        if (btn) {
            btn.textContent = '➖';
        }
    }
}

// Функция закрытия режима добавления
export function closeAddMode(td) {
    if (!td) td = document.querySelector('.entry-cell.editing[data-adding="true"]');
    if (td) {
        const dayIndex = td.dataset.dayIndex;
        const originalHtml = td.dataset.originalHtml || '';
        td.className = '';
        td.innerHTML = originalHtml;
        td.style.padding = '12px 8px';
        td.style.textAlign = 'center';
        td.style.borderRadius = '8px';
        td.style.backgroundColor = '';
        td.style.border = '';
        td.style.boxShadow = '';
        delete td.dataset.originalHtml;
        delete td.dataset.adding;
        delete td.dataset.dayIndex;

        // Возвращаем кнопку в заголовке на "➕" и скрываем её
        if (dayIndex !== undefined) {
            const th = document.querySelector(`#weeklyTrafficTableContainer th[data-day-header-index="${dayIndex}"]`);
            if (th) {
                const btn = th.querySelector('.add-entry-btn');
                if (btn) {
                    btn.textContent = '➕';
                }
            }
        }
    }
    // Также закрываем редактирование, если оно было
    if (adminState.currentlyEditingId !== null) {
        closeEditMode();
    }
}
export async function loadDailyTraffic(date) {
    const container = document.getElementById('reportContainer');
    container.innerHTML = '<p>Загрузка...</p>';
    try {
        const resp = await fetch(`/api/reports/daily?date=${date}`);
        if (!resp.ok) throw new Error('Ошибка загрузки отчёта');
        const report = await resp.json();
        adminState.dailyReportData = report;
        if (!report.length) {
            container.innerHTML = '<p>Нет данных за этот день</p>';
            return;
        }

        const employeesWithEntries = [];
        let maxOtherEntries = 0;
        for (const emp of report) {
            const id = emp.employee_id;
            try {
                const resp = await fetch(`/api/reports/employee/${id}?date=${date}`, { credentials: 'include' });
                if (!resp.ok) throw new Error('Ошибка загрузки отметок');
                const data = await resp.json();
                const entries = data.entries || [];
                entries.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
                const otherEntries = entries.filter(e => e.action !== 'end');
                const endEntry = entries.find(e => e.action === 'end') || null;
                employeesWithEntries.push({ ...emp, otherEntries, endEntry });
                if (otherEntries.length > maxOtherEntries) maxOtherEntries = otherEntries.length;
            } catch (err) {
                console.warn(`Не удалось загрузить отметки для ${emp.full_name}`, err);
                employeesWithEntries.push({ ...emp, otherEntries: [], endEntry: null });
            }
        }

        employeesWithEntries.sort((a, b) => {
            const aHasEntries = a.otherEntries.length > 0 || a.endEntry !== null;
            const bHasEntries = b.otherEntries.length > 0 || b.endEntry !== null;
            if (aHasEntries && !bHasEntries) return -1;
            if (!aHasEntries && bHasEntries) return 1;
            return a.full_name.localeCompare(b.full_name, 'ru');
        });

        maxOtherEntries = 0;
        employeesWithEntries.forEach(emp => {
            if (emp.otherEntries.length > maxOtherEntries) {
                maxOtherEntries = emp.otherEntries.length;
            }
        });

        const colorClassMap = {
            'start': 'start',
            'break_start': 'break_start',
            'break_end': 'break_end',
            'end': 'end'
        };

        const scrollContainer = createElement('div', { className: 'daily-traffic-scroll' });
        const table = createElement('table', { className: 'daily-traffic-table' });
        const tbody = createElement('tbody');

        for (const emp of employeesWithEntries) {
            const empId = emp.employee_id;
            const row = createElement('tr');
            row.append(createElement('td', { className: 'fio-cell', text: emp.full_name }));
            for (let i = 0; i < maxOtherEntries; i++) {
                if (i < emp.otherEntries.length) {
                    const entry = emp.otherEntries[i];
                    const time = entry.timestamp.slice(11, 16);
                    const action = entry.action;
                    const cellClass = colorClassMap[action] || 'unknown';
                    row.append(createElement('td', {
                        dataset: { entryId: entry.id, timestamp: entry.timestamp, action, employeeId: empId }
                    }, createElement('span', { className: `daily-cell ${cellClass}`, text: time })));
                } else {
                    row.append(createElement('td', { dataset: { employeeId: empId } }, createElement('span', { className: 'daily-cell unknown', text: '—' })));
                }
            }
            // end
            if (emp.endEntry) {
                const entry = emp.endEntry;
                const time = entry.timestamp.slice(11, 16);
                row.append(createElement('td', {
                    className: 'last-cell', dataset: { entryId: entry.id, timestamp: entry.timestamp, action: 'end', employeeId: empId }
                }, createElement('span', { className: 'daily-cell end', text: time })));
            } else {
                row.append(createElement('td', { className: 'last-cell', dataset: { employeeId: empId } }, createElement('span', { className: 'daily-cell unknown', text: '—' })));
            }

            // Новые ячейки статистики
            const workedDisplay = emp.worked_display || formatHoursToHHMM(emp.worked_hours_current) || '—';
            const breakMinutes = emp.break_minutes_current || 0;
            const breakCount = emp.break_count || 0;
            const breakDisplay = formatMinutesToHHMM(breakMinutes);
            const breakText = `${breakDisplay} (${breakCount})`;

            row.append(
                createElement('td', { className: 'stat-cell' }, createElement('span', { className: 'daily-cell worked', text: workedDisplay })),
                createElement('td', { className: 'stat-cell' }, createElement('span', { className: 'daily-cell break', text: breakText }))
            );
            tbody.append(row);
        }
        table.append(tbody);
        scrollContainer.append(table);
        container.replaceChildren(scrollContainer);

        // Обработчик кликов (игнорируем stat-cell)
        if (dailyTrafficClickHandler) {
            document.removeEventListener('click', dailyTrafficClickHandler);
        }
        dailyTrafficClickHandler = function(e) {
            const insideContainer = container.contains(e.target);
            if (!insideContainer) {
                closeDailyEditMode();
                closeDailyAddMode();
                return;
            }
            if (e.target.closest('.edit-controls')) return;
            closeDailyEditMode();
            closeDailyAddMode();

            const td = e.target.closest('td');
            if (!td) return;
            if (td.classList.contains('stat-cell')) return;

            const span = td.querySelector('.daily-cell');
            if (!span) return;
            if (!span.contains(e.target) && e.target !== span) return;

            const empId = parseInt(td.dataset.employeeId);
            if (!empId) return;
            if (td.classList.contains('editing')) return;

            if (!span.classList.contains('unknown')) {
                const entryId = td.dataset.entryId;
                const timestamp = td.dataset.timestamp;
                const action = td.dataset.action;
                if (entryId && timestamp && action) {
                    makeDailyCellEditable(td, parseInt(entryId), timestamp, action, empId, date);
                }
            } else {
                makeDailyCellAddable(td, empId, date);
            }
        };
        document.addEventListener('click', dailyTrafficClickHandler);

    } catch (err) {
        showMessage(container, `Ошибка загрузки: ${err.message}`, 'error');
        showToast(err.message, true);
    }
}
// Обработчик кнопки дневного светофора
document.getElementById('dailyTrafficBtn').addEventListener('click', function(e) {
    e.stopPropagation();
    const date = document.getElementById('reportDate').value;
    if (!date) {
        showToast('Выберите дату', true);
        return;
    }
    adminState.dailyTrafficModeActive = !adminState.dailyTrafficModeActive;
    updateFilterVisibility();
    if (adminState.dailyTrafficModeActive) {
        this.textContent = '🚦';
        // Загружаем светофор
        loadDailyTraffic(date);
    } else {
        this.textContent = '🚦';
        // Возвращаем обычный отчёт
        if (adminState.dailyReportData) {
            // Перерисовываем обычный отчёт, используя сохранённые данные
            // Но проще перезагрузить через loadDailyReport
            loadDailyReport(date);
        } else {
            loadDailyReport(date);
        }
    }
});
export function closeDailyEditMode() {
    if (adminState.dailyCurrentlyEditingId === null) return;
    const td = document.querySelector('#reportContainer td.editing');
    if (td) {
        const originalHtml = td.dataset.originalHtml || '';
        td.className = td.dataset.originalClasses || '';
        td.innerHTML = originalHtml;
        td.style.cssText = '';
        delete td.dataset.originalHtml;
        delete td.dataset.originalClasses;
        delete td.dataset.originalTime;
        delete td.dataset.originalAction;
    }
    adminState.dailyCurrentlyEditingId = null;
}
export function closeDailyAddMode(td) {
    if (!td) td = adminState.dailyCurrentlyAddingCell;
    if (td) {
        const originalHtml = td.dataset.originalHtml || '';
        td.className = td.dataset.originalClasses || '';
        td.innerHTML = originalHtml;
        td.style.cssText = '';
        td.style.padding = '';
        td.style.textAlign = '';
        td.style.borderRadius = '';
        td.style.backgroundColor = '';
        td.style.border = '';
        td.style.boxShadow = '';
        delete td.dataset.originalHtml;
        delete td.dataset.originalClasses;
        delete td.dataset.adding;
    }
    adminState.dailyCurrentlyAddingCell = null;
}
export function makeDailyCellEditable(td, entryId, timestamp, action, employeeId, date) {
    closeDailyEditMode();
    closeDailyAddMode();

    const timeStr = timestamp.slice(11, 16);
    const colorCycle = ['start', 'break_start', 'break_end', 'end'];
    let colorIndex = colorCycle.indexOf(action);
    if (colorIndex === -1) colorIndex = 0;
    let currentEditColor = colorCycle[colorIndex];

    td.dataset.originalHtml = td.innerHTML;
    td.dataset.originalClasses = td.className;

    // Сбрасываем классы и инлайн-стили, оставляем editing
    td.className = 'editing';
    td.style.cssText = '';

    const colorClassMap = {
        'start': 'start',
        'break_start': 'break_start',
        'break_end': 'break_end',
        'end': 'end'
    };

    td.innerHTML = `
        <div class="edit-controls">
            <input type="text" class="edit-time-input" value="${timeStr}" maxlength="5" autofocus>
            <div class="edit-color-btn ${colorClassMap[currentEditColor]}"></div>
            <button class="edit-save-btn" title="Сохранить">✔️</button>
            <button class="edit-delete-btn" title="Удалить">✖️</button>
        </div>
    `;

    const input = td.querySelector('.edit-time-input');
    const colorBtn = td.querySelector('.edit-color-btn');
    const saveBtn = td.querySelector('.edit-save-btn');
    const deleteBtn = td.querySelector('.edit-delete-btn');

    if (!input || !colorBtn || !saveBtn || !deleteBtn) {
        console.error('Не удалось найти элементы управления');
        return;
    }

    // Автоформат времени
    input.addEventListener('input', function() {
        let val = this.value.replace(/\D/g, '');
        if (val.length > 4) val = val.slice(0, 4);
        if (val.length === 0) { this.value = ''; return; }
        let formatted = '';
        if (val.length <= 2) formatted = val;
        else if (val.length === 3) formatted = val[0] + ':' + val.slice(1);
        else if (val.length === 4) formatted = val.slice(0, 2) + ':' + val.slice(2);
        this.value = formatted;
    });

    // Переключение цвета
    colorBtn.addEventListener('click', function() {
        colorIndex = (colorIndex + 1) % colorCycle.length;
        currentEditColor = colorCycle[colorIndex];
        this.className = `edit-color-btn ${colorClassMap[currentEditColor]}`;
    });

    // Сохранение изменений
    saveBtn.addEventListener('click', async function(e) {
        e.stopPropagation();
        const timeStr = input.value.trim();
        if (!timeStr || !timeStr.includes(':')) {
            showToast('Введите корректное время (ЧЧ:ММ)', true);
            return;
        }
        let [hours, minutes] = timeStr.split(':');
        hours = hours.padStart(2, '0');
        minutes = minutes.padStart(2, '0');
        if (parseInt(hours) > 23 || parseInt(minutes) > 59) {
            showToast('Некорректное время', true);
            return;
        }
        const newAction = currentEditColor;
        const isoDateTime = `${date}T${hours}:${minutes}:00`;

        saveBtn.disabled = true;
        deleteBtn.disabled = true;

        try {
            const resp = await fetch(`/api/admin/timelog/${entryId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timestamp: isoDateTime, action: newAction })
            });
            if (resp.ok) {
                showToast(`✅ Отметка обновлена на ${hours}:${minutes}`);
                closeDailyEditMode();
                loadDailyTraffic(date);
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка обновления', true);
                saveBtn.disabled = false;
                deleteBtn.disabled = false;
            }
        } catch (err) {
            showToast('Ошибка сети', true);
            saveBtn.disabled = false;
            deleteBtn.disabled = false;
        }
    });

    // Удаление отметки
    deleteBtn.addEventListener('click', async function(e) {
        e.stopPropagation();
        if (!confirm('Удалить эту отметку?')) return;
        deleteBtn.disabled = true;
        saveBtn.disabled = true;
        try {
            const resp = await fetch(`/api/admin/timelog/${entryId}`, { method: 'DELETE' });
            if (resp.ok) {
                showToast('🗑️ Отметка удалена');
                closeDailyEditMode();
                loadDailyTraffic(date);
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка удаления', true);
                deleteBtn.disabled = false;
                saveBtn.disabled = false;
            }
        } catch (err) {
            showToast('Ошибка сети', true);
            deleteBtn.disabled = false;
            saveBtn.disabled = false;
        }
    });

    // Фокус и клавиши
    setTimeout(() => input.focus(), 50);
    input.select();

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); saveBtn.click(); }
        if (e.key === 'Escape') { e.preventDefault(); closeDailyEditMode(); }
    });

    adminState.dailyCurrentlyEditingId = entryId;
}
export function makeDailyCellAddable(td, employeeId, date) {
    // Закрываем другие режимы
    closeDailyEditMode();
    closeDailyAddMode();

    // Сохраняем оригинал
    td.dataset.originalHtml = td.innerHTML;
    td.dataset.originalClasses = td.className;
    td.dataset.adding = 'true';

    // Сбрасываем все классы и инлайн-стили, оставляем только editing
    td.className = 'editing';
    td.style.cssText = ''; // удаляем всё лишнее

    const colorCycle = ['start', 'break_start', 'break_end', 'end'];
    let colorIndex = 0;
    let currentColor = colorCycle[colorIndex];
    const colorClassMap = {
        'start': 'start',
        'break_start': 'break_start',
        'break_end': 'break_end',
        'end': 'end'
    };

    // Вставляем элементы управления
    td.innerHTML = `
        <div class="edit-controls">
            <input type="text" class="edit-time-input" placeholder="ЧЧ:ММ" maxlength="5" autofocus>
            <div class="edit-color-btn ${colorClassMap[currentColor]}"></div>
            <button class="edit-save-btn" title="Добавить">✔️</button>
            <button class="edit-delete-btn" title="Отмена">✖️</button>
        </div>
    `;

    const input = td.querySelector('.edit-time-input');
    const colorBtn = td.querySelector('.edit-color-btn');
    const saveBtn = td.querySelector('.edit-save-btn');
    const cancelBtn = td.querySelector('.edit-delete-btn');

    if (!input || !colorBtn || !saveBtn || !cancelBtn) {
        console.error('Не удалось найти элементы управления');
        return;
    }

    // Автоформат времени
    input.addEventListener('input', function() {
        let val = this.value.replace(/\D/g, '');
        if (val.length > 4) val = val.slice(0, 4);
        if (val.length === 0) { this.value = ''; return; }
        let formatted = '';
        if (val.length <= 2) formatted = val;
        else if (val.length === 3) formatted = val[0] + ':' + val.slice(1);
        else if (val.length === 4) formatted = val.slice(0, 2) + ':' + val.slice(2);
        this.value = formatted;
    });

    // Переключение цвета
    colorBtn.addEventListener('click', function() {
        colorIndex = (colorIndex + 1) % colorCycle.length;
        currentColor = colorCycle[colorIndex];
        this.className = `edit-color-btn ${colorClassMap[currentColor]}`;
    });

    // Сохранение (добавление)
    saveBtn.addEventListener('click', async function(e) {
        e.stopPropagation();
        const timeStr = input.value.trim();
        if (!timeStr || !timeStr.includes(':')) {
            showToast('Введите корректное время (ЧЧ:ММ)', true);
            return;
        }
        let [hours, minutes] = timeStr.split(':');
        hours = hours.padStart(2, '0');
        minutes = minutes.padStart(2, '0');
        if (parseInt(hours) > 23 || parseInt(minutes) > 59) {
            showToast('Некорректное время', true);
            return;
        }
        const action = currentColor;
        const isoDateTime = `${date}T${hours}:${minutes}:00`;

        saveBtn.disabled = true;
        cancelBtn.disabled = true;

        try {
            const resp = await fetch('/api/admin/timelog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    employee_id: employeeId,
                    action: action,
                    timestamp: isoDateTime
                })
            });
            if (resp.ok) {
                showToast(`✅ Отметка "${TRAFFIC_LABELS[action]}" добавлена в ${hours}:${minutes}`);
                closeDailyAddMode(td);
                loadDailyTraffic(date);
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка сохранения', true);
                saveBtn.disabled = false;
                cancelBtn.disabled = false;
            }
        } catch (err) {
            showToast('Ошибка сети', true);
            saveBtn.disabled = false;
            cancelBtn.disabled = false;
        }
    });

    // Отмена (закрыть без сохранения)
    cancelBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        closeDailyAddMode(td);
    });

    // Фокус и клавиши
    setTimeout(() => input.focus(), 50);
    input.select();

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); saveBtn.click(); }
        if (e.key === 'Escape') { e.preventDefault(); cancelBtn.click(); }
    });

    adminState.dailyCurrentlyAddingCell = td;
}
export function updateFilterVisibility() {
    const toggleBtn = document.getElementById('toggleFilterBtn');
    const settingsDiv = document.getElementById('statusOrderSettings');
    if (adminState.dailyTrafficModeActive) {
        // Светофор активен – скрываем фильтр
        toggleBtn.style.display = 'none';
        settingsDiv.style.display = 'none';
    } else {
        // Обычный отчёт – показываем согласно сохранённому состоянию
        toggleBtn.style.display = '';
        settingsDiv.style.display = adminState.isFilterEnabled ? 'block' : 'none';
    }
}
export function initMonthlyTab() {
    const dateRangeInput = document.getElementById('periodDateRange');
    const loadBtn = document.getElementById('loadPeriodReportBtn');
    const employeeFilter = document.getElementById('periodEmployeeFilter');
    const trafficBtn = document.getElementById('trafficPeriodBtn');

    // Инициализация flatpickr с диапазоном
    if (dateRangeInput && !dateRangeInput._flatpickr) {
        flatpickr(dateRangeInput, {
            mode: "range",
            dateFormat: "Y-m-d",
            firstDayOfWeek: 1,
            locale: {
                firstDayOfWeek: 1
            },
            defaultDate: [new Date(new Date().getFullYear(), new Date().getMonth(), 1), new Date()],
            onChange: function(selectedDates, dateStr, instance) {
                if (selectedDates.length === 2) {
                    adminState.periodStartDate = selectedDates[0];
                    adminState.periodEndDate = selectedDates[1];
                    const employeeId = employeeFilter ? employeeFilter.value : '';
                    adminState.selectedEmployeeId = employeeId;
                    if (adminState.periodTrafficModeActive) {
                        loadTrafficPeriod(adminState.periodStartDate, adminState.periodEndDate, employeeId);
                    } else {
                        loadPeriodReport(adminState.periodStartDate, adminState.periodEndDate, employeeId);
                    }
                }
            }
        });
    }

    // Загрузка списка сотрудников в селект
    if (employeeFilter) {
        fetch('/api/employees?active_only=true', { credentials: 'include' })
            .then(res => res.json())
            .then(employees => {
                employeeFilter.innerHTML = '<option value="">Все</option>';
                employees.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
                employees.forEach(emp => {
                    const opt = document.createElement('option');
                    opt.value = emp.id;
                    opt.textContent = emp.full_name;
                    employeeFilter.appendChild(opt);
                });
            })
            .catch(err => console.error('Ошибка загрузки сотрудников:', err));
    }

    // Обработчик кнопки «Показать»
    if (loadBtn) {
        loadBtn.addEventListener('click', function() {
            const picker = dateRangeInput._flatpickr;
            if (picker && picker.selectedDates.length === 2) {
                adminState.periodStartDate = picker.selectedDates[0];
                adminState.periodEndDate = picker.selectedDates[1];
                const employeeId = employeeFilter ? employeeFilter.value : '';
                adminState.selectedEmployeeId = employeeId;
                if (adminState.periodTrafficModeActive) {
                    loadTrafficPeriod(adminState.periodStartDate, adminState.periodEndDate, employeeId);
                } else {
                    loadPeriodReport(adminState.periodStartDate, adminState.periodEndDate, employeeId);
                }
            } else {
                showToast('Выберите обе даты периода', true);
            }
        });
    }

    // Обработчик изменения сотрудника
    if (employeeFilter) {
        employeeFilter.addEventListener('change', function() {
            const employeeId = this.value;
            adminState.selectedEmployeeId = employeeId;
            if (adminState.periodStartDate && adminState.periodEndDate) {
                if (adminState.periodTrafficModeActive) {
                    loadTrafficPeriod(adminState.periodStartDate, adminState.periodEndDate, employeeId);
                } else {
                    loadPeriodReport(adminState.periodStartDate, adminState.periodEndDate, employeeId);
                }
            }
        });
    }

    // Обработчик кнопки светофора
    if (trafficBtn) {
        trafficBtn.addEventListener('click', function() {
            adminState.periodTrafficModeActive = !adminState.periodTrafficModeActive;
            const container = document.getElementById('periodReportContainer');
            const trafficContainer = document.getElementById('trafficPeriodContainer');
            const notifContainer = document.getElementById('periodNotificationsContainer');

            if (adminState.periodTrafficModeActive) {
                container.style.display = 'none';
                trafficContainer.style.display = 'block';
                if (notifContainer) notifContainer.style.display = 'none';
                if (adminState.periodStartDate && adminState.periodEndDate) {
                    loadTrafficPeriod(adminState.periodStartDate, adminState.periodEndDate, adminState.selectedEmployeeId);
                } else {
                    trafficContainer.innerHTML = '<p>Сначала выберите период</p>';
                }
            } else {
                container.style.display = 'block';
                trafficContainer.style.display = 'none';
                if (adminState.periodStartDate && adminState.periodEndDate) {
                    loadPeriodReport(adminState.periodStartDate, adminState.periodEndDate, adminState.selectedEmployeeId);
                }
            }
        });
    }

    // Автозагрузка при первом открытии (если даты уже выбраны)
    if (dateRangeInput && dateRangeInput._flatpickr && dateRangeInput._flatpickr.selectedDates.length === 2) {
        const [start, end] = dateRangeInput._flatpickr.selectedDates;
        adminState.periodStartDate = start;
        adminState.periodEndDate = end;
        const employeeId = employeeFilter ? employeeFilter.value : '';
        adminState.selectedEmployeeId = employeeId;
        loadPeriodReport(start, end, employeeId);
    }
}

export async function loadPeriodReport(startDate, endDate, employeeId = '') {
    const container = document.getElementById('periodReportContainer');
    const notifContainer = document.getElementById('periodNotificationsContainer');
    const notifList = document.getElementById('periodNotificationsList');

    if (!container) return;
    if (!startDate || !endDate) {
        container.innerHTML = '<p>Выберите период</p>';
        return;
    }

    // Форматируем даты в YYYY-MM-DD
    const startStr = formatDateLocal(startDate);
    const endStr = formatDateLocal(endDate);

    container.innerHTML = '<p>Загрузка...</p>';
    if (notifContainer) notifContainer.style.display = 'none';

    try {
        let url = `/api/reports/period?start_date=${startStr}&end_date=${endStr}`;
        if (employeeId) {
            url += `&employee_id=${employeeId}`;
        }
        const resp = await fetch(url, { credentials: 'include' });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();

        if (!data || data.length === 0) {
            container.innerHTML = '<p>Нет данных за этот период</p>';
            if (notifContainer) notifContainer.style.display = 'none';
            return;
        }

        // Сортируем по ФИО
        data.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));

        // Таблица – та же, что и раньше
        const statsTable = createElement('table', { className: 'report-table period-stat-table' });
        const statsHeader = createElement('tr');
        ['Сотрудник', 'Рабочих дней', 'Выходных', 'Отработано', 'Среднее в день', 'Перерывы (мин)', 'Кол-во перерывов', 'Среднее время перерыва', 'Среднее кол-во перерывов']
            .forEach(label => statsHeader.append(createElement('th', { text: label })));
        statsTable.append(createElement('thead', {}, statsHeader));
        const statsBody = createElement('tbody');
        data.forEach(employee => statsBody.append(createElement('tr', {}, [
            createElement('td', { className: 'period-employee-name', text: employee.full_name }),
            createElement('td', { text: employee.work_days }), createElement('td', { text: employee.weekend_days }),
            createElement('td', { text: employee.total_worked_display }),
            createElement('td', { className: getAverageTimeColor(employee.average_worked_per_day), text: employee.average_worked_per_day }),
            createElement('td', { text: employee.total_break_display }), createElement('td', { text: employee.total_break_count }),
            createElement('td', { text: employee.average_break_duration }), createElement('td', { text: employee.average_break_count_per_day })
        ])));
        statsTable.append(statsBody);
        container.replaceChildren(createElement('div', { className: 'recent-table' }, statsTable));

        // Если выбран сотрудник – загружаем уведомления
        if (employeeId && notifContainer && notifList) {
            notifContainer.style.display = 'block';
            notifList.innerHTML = 'Загрузка уведомлений...';

            try {
                const notifResp = await fetch(
                    `/api/admin/notifications?employee_id=${employeeId}&start_date=${startStr}&end_date=${endStr}`,
                    { credentials: 'include' }
                );
                if (!notifResp.ok) throw new Error('Ошибка загрузки уведомлений');
                const notifications = await notifResp.json();

                if (!notifications || notifications.length === 0) {
                    showMessage(notifList, 'Нет уведомлений за этот период');
                } else {
                    notifList.replaceChildren(createPeriodNotificationsTable(notifications));
                }
            } catch (err) {
                showMessage(notifList, `Ошибка загрузки уведомлений: ${err.message}`, 'error');
            }
        } else {
            if (notifContainer) notifContainer.style.display = 'none';
        }

    } catch (err) {
        showMessage(container, `Ошибка загрузки: ${err.message}`, 'error');
        if (notifContainer) notifContainer.style.display = 'none';
        showToast(err.message, true);
    }
}
export async function loadTrafficPeriod(startDate, endDate, employeeId = '') {
    const container = document.getElementById('trafficPeriodContainer');
    if (!container) return;
    if (!startDate || !endDate) {
        container.innerHTML = '<p>Выберите период</p>';
        return;
    }

    const startStr = formatDateLocal(startDate);
    const endStr = formatDateLocal(endDate);

    container.innerHTML = '<p>Загрузка...</p>';

    try {
        let url = `/api/reports/period/traffic?start_date=${startStr}&end_date=${endStr}`;
        if (employeeId) {
            url += `&employee_id=${employeeId}`;
        }
        const resp = await fetch(url, { credentials: 'include' });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();

        if (!data || data.length === 0) {
            container.innerHTML = '<p>Нет данных за этот период</p>';
            return;
        }

        data.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));

        const dates = [];
        let current = new Date(startDate);
        while (current <= endDate) {
            dates.push(new Date(current));
            current.setDate(current.getDate() + 1);
        }

        const table = createElement('table', { className: 'traffic-table period-traffic-table', attrs: { tabindex: '0' } });
        const headingRow = createElement('tr', {}, createElement('th', { className: 'period-traffic-employee-heading', text: 'Сотрудник' }));

        for (let i = 0; i < dates.length; i++) {
            const d = dates[i];
            const day = d.getDate().toString().padStart(2, '0');
            const month = (d.getMonth()+1).toString().padStart(2, '0');
            const dayOfWeek = d.toLocaleDateString('ru-RU', { weekday: 'short' });
            headingRow.append(createElement('th', { className: 'period-traffic-day-heading', dataset: { dayHeaderIndex: i } }, [
                document.createTextNode(dayOfWeek), createElement('br'), document.createTextNode(`${day}.${month}`)
            ]));
        }

        table.append(createElement('thead', {}, headingRow));
        const tbody = createElement('tbody');

        for (const emp of data) {
            const row = createElement('tr', {}, createElement('td', { className: 'fio-cell period-traffic-employee-cell', text: emp.full_name }));

            for (let i = 0; i < dates.length; i++) {
                const dayType = emp.days[i] || 'off'; // 'work', 'off', 'vacation', 'sick'
                row.append(createElement('td', {
                    className: `day-type-${dayType} period-traffic-day-cell`,
                    dataset: { dayIndex: i, employeeId: emp.employee_id, date: formatDateLocal(dates[i]), dayType }
                }));
            }
            tbody.append(row);
        }

        table.append(tbody);
        container.replaceChildren(table);
        table.focus();

        // --- ПОДСВЕТКА ПРИ НАВЕДЕНИИ ---
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
            const fioCell = row.querySelector('.fio-cell');
            const cells = row.querySelectorAll('td[data-day-index]');
            cells.forEach(cell => {
                cell.addEventListener('mouseenter', () => {
                    if (fioCell) fioCell.classList.add('highlight-fio');
                    const dayIndex = cell.dataset.dayIndex;
                    if (dayIndex !== undefined) {
                        const dayHeader = table.querySelector(`th[data-day-header-index="${dayIndex}"]`);
                        if (dayHeader) dayHeader.classList.add('highlight-day-header');
                    }
                });
                cell.addEventListener('mouseleave', () => {
                    if (fioCell) fioCell.classList.remove('highlight-fio');
                    const dayIndex = cell.dataset.dayIndex;
                    if (dayIndex !== undefined) {
                        const dayHeader = table.querySelector(`th[data-day-header-index="${dayIndex}"]`);
                        if (dayHeader) dayHeader.classList.remove('highlight-day-header');
                    }
                });
            });
        });

        // --- ЛОГИКА ВЫДЕЛЕНИЯ ---
        let selectedCells = [];
        let lastSelectedCell = null;

        function clearSelection() {
            table.querySelectorAll('.selected-cell').forEach(el => el.classList.remove('selected-cell'));
            selectedCells = [];
            lastSelectedCell = null;
        }

        function selectCell(cell, addToSelection = false) {
            if (!cell) return;
            if (!addToSelection) {
                clearSelection();
            }
            cell.classList.add('selected-cell');
            selectedCells.push(cell);
            lastSelectedCell = cell;
        }

        function selectRange(from, to) {
            const fromRow = from.closest('tr');
            const toRow = to.closest('tr');
            if (fromRow !== toRow) return;

            const cells = Array.from(fromRow.querySelectorAll('td[data-day-index]'));
            const fromIdx = cells.indexOf(from);
            const toIdx = cells.indexOf(to);
            if (fromIdx === -1 || toIdx === -1) return;

            const start = Math.min(fromIdx, toIdx);
            const end = Math.max(fromIdx, toIdx);

            clearSelection();
            for (let i = start; i <= end; i++) {
                cells[i].classList.add('selected-cell');
                selectedCells.push(cells[i]);
            }
            lastSelectedCell = to;
        }

        // --- ОБРАБОТЧИК КЛИКОВ ---
        container.addEventListener('click', function(e) {
            const cell = e.target.closest('td[data-day-index]');
            if (!cell) {
                clearSelection();
                return;
            }

            if (e.shiftKey && lastSelectedCell) {
                if (lastSelectedCell.closest('tr') === cell.closest('tr')) {
                    selectRange(lastSelectedCell, cell);
                } else {
                    clearSelection();
                    selectCell(cell, false);
                }
            } else if (e.ctrlKey) {
                if (cell.classList.contains('selected-cell')) {
                    cell.classList.remove('selected-cell');
                    selectedCells = selectedCells.filter(c => c !== cell);
                    if (lastSelectedCell === cell) {
                        lastSelectedCell = selectedCells.length > 0 ? selectedCells[selectedCells.length-1] : null;
                    }
                } else {
                    selectCell(cell, true);
                }
            } else {
                clearSelection();
                selectCell(cell, false);
            }
            table.focus();
        });

        // --- КЛАВИШИ СТРЕЛОК ---
        function handleKeydown(e) {
            const key = e.key;
            if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(key)) return;
            if (e.target.closest('input, textarea, select, button')) return;

            e.preventDefault();

            const currentCell = lastSelectedCell || table.querySelector('tbody tr td[data-day-index]');
            if (!currentCell) return;

            const allRows = Array.from(table.querySelectorAll('tbody tr'));
            const currentRow = currentCell.closest('tr');
            const currentRowIndex = allRows.indexOf(currentRow);
            const cellsInRow = Array.from(currentRow.querySelectorAll('td[data-day-index]'));
            const currentCellIndex = cellsInRow.indexOf(currentCell);

            let targetRowIndex = currentRowIndex;
            let targetCellIndex = currentCellIndex;

            switch (key) {
                case 'ArrowUp': targetRowIndex = Math.max(0, currentRowIndex - 1); break;
                case 'ArrowDown': targetRowIndex = Math.min(allRows.length - 1, currentRowIndex + 1); break;
                case 'ArrowLeft': targetCellIndex = Math.max(0, currentCellIndex - 1); break;
                case 'ArrowRight': targetCellIndex = Math.min(cellsInRow.length - 1, currentCellIndex + 1); break;
            }

            if (targetRowIndex === currentRowIndex && targetCellIndex === currentCellIndex) return;

            const targetRow = allRows[targetRowIndex];
            const targetCells = Array.from(targetRow.querySelectorAll('td[data-day-index]'));
            const targetCell = targetCells[targetCellIndex] || cellsInRow[targetCellIndex];
            if (!targetCell) return;

            const ctrlPressed = e.ctrlKey || e.metaKey;
            if (ctrlPressed) {
                if (!targetCell.classList.contains('selected-cell')) {
                    targetCell.classList.add('selected-cell');
                    selectedCells.push(targetCell);
                }
                lastSelectedCell = targetCell;
            } else {
                clearSelection();
                targetCell.classList.add('selected-cell');
                selectedCells = [targetCell];
                lastSelectedCell = targetCell;
            }
            targetCell.scrollIntoView({ block: 'nearest' });
        }
        container.addEventListener('keydown', handleKeydown);

        // --- КОНТЕКСТНОЕ МЕНЮ ---
        // Создаём меню
        const existingMenu = document.getElementById('trafficContextMenu');
        if (existingMenu) existingMenu.remove();
        const menu = createElement('div', { className: 'traffic-context-menu', attrs: { id: 'trafficContextMenu' } });
        [['work', 'Рабочий'], ['off', 'Выходной'], ['vacation', 'Отпуск'], ['sick', 'Больничный']].forEach(([type, label]) => {
            menu.append(createElement('button', { className: 'menu-item', attrs: { type: 'button' }, dataset: { type } }, [
                createElement('span', { className: `color-circle traffic-type-${type}` }), createElement('span', { text: label })
            ]));
        });
        container.append(menu);


        function hideMenu() {
            menu.style.display = 'none';
        }

        container.addEventListener('contextmenu', function(e) {
            const cell = e.target.closest('td[data-day-index]');
            if (!cell) return;

            // Проверяем: если есть выделенные ячейки, проверяем их все
            if (selectedCells.length) {
                const hasWork = selectedCells.some(c => c.dataset.dayType === 'work');
                if (hasWork) {
                    showToast('Нельзя редактировать рабочие дни', true);
                    return;
                }
            } else {
                // Если ничего не выделено, проверяем только текущую ячейку
                if (cell.dataset.dayType === 'work') {
                    return;
                }
            }

            e.preventDefault();

            // Если ячейка не выделена – делаем её единственной выделенной
            if (!cell.classList.contains('selected-cell')) {
                clearSelection();
                cell.classList.add('selected-cell');
                selectedCells = [cell];
                lastSelectedCell = cell;
            }

            menu.style.display = 'block';
            const x = Math.min(e.clientX, window.innerWidth - 150);
            const y = Math.min(e.clientY, window.innerHeight - 150);
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
        });

        // Клик по пункту меню – меняем тип у выделенных ячеек
        menu.addEventListener('click', async function(e) {
            const item = e.target.closest('.menu-item');
            if (!item) return;
            const newType = item.dataset.type;
            if (!newType) return;

            const cellsToUpdate = selectedCells.length ? selectedCells : [lastSelectedCell];
            // Проверка: есть ли среди выделенных рабочие дни
            const hasWork = cellsToUpdate.some(cell => cell && cell.dataset.dayType === 'work');
            if (hasWork) {
                showToast('Нельзя изменять тип рабочих дней', true);
                hideMenu();
                return;
            }
            const updates = [];
            cellsToUpdate.forEach(cell => {
                if (!cell) return;
                const employeeId = parseInt(cell.dataset.employeeId);
                const dateStr = cell.dataset.date;
                updates.push({
                    employee_id: employeeId,
                    date: dateStr,
                    day_type: newType
                });
            });

            if (updates.length === 0) return;

            try {
                await saveDayStatusUpdates(updates);
                // Обновляем классы локально
                cellsToUpdate.forEach(cell => {
                    cell.className = cell.className.split(' ').filter(cls => !cls.startsWith('day-type-')).join(' ');
                    cell.classList.add('day-type-' + newType);
                    cell.dataset.dayType = newType;
                });
                hideMenu();
            } catch (err) {
                showToast(err.message, true);
            }
        });

        // Клик вне меню – скрываем
        document.addEventListener('click', function(e) {
            if (!menu.contains(e.target)) {
                hideMenu();
            }
        });

        // Сброс выделения при клике вне контейнера
        function outsideClickHandler(e) {
            if (!container.contains(e.target)) {
                clearSelection();
                hideMenu();
            }
        }
        document.addEventListener('click', outsideClickHandler);
        container._removeOutsideHandler = () => document.removeEventListener('click', outsideClickHandler);

    } catch (err) {
        showMessage(container, `Ошибка загрузки: ${err.message}`, 'error');
        showToast(err.message, true);
    }
}

export async function saveDayStatusUpdates(updates) {
    // updates: [{employee_id, date, day_type}]
    const resp = await fetch('/api/admin/day-status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
        credentials: 'include'
    });
    if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Ошибка сохранения');
    }
}

export function parseTimeToMinutes(timeStr) {
    if (!timeStr || timeStr === '—' || timeStr.trim() === '') return null;
    const parts = timeStr.split(':');
    if (parts.length !== 2) return null;
    const hours = parseInt(parts[0], 10);
    const minutes = parseInt(parts[1], 10);
    if (isNaN(hours) || isNaN(minutes)) return null;
    return hours * 60 + minutes;
}

export function getAverageTimeColor(timeStr) {
    const minutes = parseTimeToMinutes(timeStr);
    if (minutes === null) return ''; // нет данных — без цвета

    // Пороги в минутах
    const low = 7 * 60 + 45;   // 7:45
    const midLow = 7 * 60 + 46; // 7:46
    const midHigh = 7 * 60 + 55; // 7:55
    const high = 8 * 60 + 15;   // 8:15

    if (minutes < low) return 'avg-time-red';
    if (minutes >= midLow && minutes <= midHigh) return 'avg-time-yellow';
    if (minutes >= (7*60+56) && minutes <= high) return 'avg-time-blue';
    if (minutes > high) return 'avg-time-green';
    return '';
}
// ---- Обработчики для модального окна должности ----
closeRoleModalBtn.addEventListener('click', closeRoleModal);
cancelRoleBtn.addEventListener('click', closeRoleModal);

// Закрытие при клике вне модалки
window.addEventListener('click', function(e) {
    if (e.target === roleModal) closeRoleModal();
});

// Назначение существующей должности
// ---- Назначение существующей должности (ДОБАВЛЯЕТ, а не заменяет) ----
assignRoleBtn.addEventListener('click', async function() {
    const roleId = parseInt(roleSelect.value);
    if (!roleId) {
        roleModalError.textContent = 'Выберите должность';
        return;
    }
    const employeeId = adminState.currentEmployeeIdForRole;
    if (!employeeId) {
        roleModalError.textContent = 'Сотрудник не выбран';
        return;
    }

    try {
        // Проверяем, не назначена ли уже эта роль сотруднику
        const currentRoles = await (await fetch(`/api/sandbox/employees/${employeeId}/roles`, { credentials: 'include' })).json();
        if (currentRoles.some(r => r.id === roleId)) {
            showToast('Эта должность уже назначена сотруднику', true);
            return;
        }

        // Назначаем сотрудника на выбранную должность (без удаления старых)
        const resp = await fetch(`/api/sandbox/roles/${roleId}/employees`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ employee_id: employeeId }),
            credentials: 'include'
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Ошибка назначения');
        }
        showToast('Должность добавлена');
        closeRoleModal();
        loadEmployees(); // обновляем таблицу
    } catch (err) {
        roleModalError.textContent = err.message;
    }
});

// ---- Создание новой должности и назначение (ДОБАВЛЯЕТ) ----
createRoleAndAssignBtn.addEventListener('click', async function() {
    const newRoleName = newRoleNameInput.value.trim();
    if (!newRoleName) {
        roleModalError.textContent = 'Введите название новой должности';
        return;
    }
    const employeeId = adminState.currentEmployeeIdForRole;
    if (!employeeId) {
        roleModalError.textContent = 'Сотрудник не выбран';
        return;
    }

    try {
        // 1. Создаём должность
        const createResp = await fetch('/api/sandbox/roles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newRoleName }),
            credentials: 'include'
        });
        if (!createResp.ok) {
            const err = await createResp.json();
            throw new Error(err.detail || 'Ошибка создания должности');
        }
        const newRole = await createResp.json();

        // 2. Проверяем, не назначена ли уже эта роль (маловероятно, но на всякий случай)
        const currentRoles = await (await fetch(`/api/sandbox/employees/${employeeId}/roles`, { credentials: 'include' })).json();
        if (currentRoles.some(r => r.id === newRole.id)) {
            showToast('Эта должность уже назначена сотруднику', true);
            return;
        }

        // 3. Назначаем сотрудника на новую должность (без удаления старых)
        const assignResp = await fetch(`/api/sandbox/roles/${newRole.id}/employees`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ employee_id: employeeId }),
            credentials: 'include'
        });
        if (!assignResp.ok) {
            const err = await assignResp.json();
            throw new Error(err.detail || 'Ошибка назначения');
        }
        showToast('Новая должность создана и добавлена');
        closeRoleModal();
        loadEmployees();
    } catch (err) {
        roleModalError.textContent = err.message;
    }
});
export async function renderCurrentRoles(employeeId) {
    const container = document.getElementById('currentRolesList');
    if (!container) return;

    try {
        const resp = await fetch(`/api/sandbox/employees/${employeeId}/roles`, { credentials: 'include' });
        if (!resp.ok) throw new Error('Ошибка загрузки должностей сотрудника');
        const roles = await resp.json(); // массив должностей, каждая с полями id, name, description, tasks, employees

        if (roles.length === 0) {
            container.replaceChildren(createElement('span', { className: 'text-muted', text: 'Нет назначенных должностей' }));
            return;
        }

        const roleTags = roles.map(role => createElement('span', { className: 'current-role-tag' }, [
            document.createTextNode(role.name),
            createElement('button', {
                className: 'remove-role-btn', text: '×', attrs: { type: 'button' },
                dataset: { roleId: role.id, employeeId }
            })
        ]));
        container.replaceChildren(...roleTags);

        // Обработчики удаления (как раньше)
        container.querySelectorAll('.remove-role-btn').forEach(btn => {
            btn.addEventListener('click', async function() {
                const roleId = parseInt(this.dataset.roleId);
                const empId = parseInt(this.dataset.employeeId);
                if (!confirm('Удалить эту должность у сотрудника?')) return;
                try {
                    const resp = await fetch(`/api/sandbox/roles/${roleId}/employees/${empId}`, {
                        method: 'DELETE',
                        credentials: 'include'
                    });
                    if (!resp.ok) throw new Error('Ошибка удаления');
                    showToast('Должность удалена');
                    // Обновляем список должностей в модалке
                    await renderCurrentRoles(empId);
                    // Обновляем таблицу (чтобы обновить глобальный маппинг, но это не обязательно для модалки)
                    await loadEmployees();
                    // Сбрасываем выбор в select
                    roleSelect.value = '';
                } catch (err) {
                    showToast(err.message, true);
                }
            });
        });
    } catch (err) {
        showMessage(container, 'Ошибка загрузки должностей', 'error');
        showToast(err.message, true);
    }
}
export async function saveProductQuantity(input, dealId) {
    const tr = input.closest('tr');
    const productId = parseInt(tr ? tr.dataset.productId : input.dataset.productId);
    const quantity = parseInt(input.value);
    if (isNaN(productId) || isNaN(quantity) || quantity < 1) {
        const span = input.closest('td').querySelector('.product-quantity-display');
        if (span) {
            input.value = span.textContent;
            span.style.display = 'inline';
        }
        input.style.display = 'none';
        return;
    }
    try {
        const resp = await fetch(`/api/sandbox/deals/${dealId}/products`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([{ product_id: productId, quantity: quantity }]),
            credentials: 'include'
        });
        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error(`Ошибка ${resp.status}: ${errText}`);
        }
        const span = input.closest('td').querySelector('.product-quantity-display');
        if (span) {
            span.textContent = quantity;
            span.style.display = 'inline';
        }
        input.style.display = 'none';
        showToast('Количество обновлено');
    } catch (err) {
        console.error('Ошибка сохранения количества:', err);
        showToast('Ошибка: ' + err.message, true);
        const span = input.closest('td').querySelector('.product-quantity-display');
        if (span) {
            input.value = span.textContent;
            span.style.display = 'inline';
        }
        input.style.display = 'none';
    }
}


function createPeriodNotificationsTable(notifications) {
    const table = createElement('table', { className: 'report-table' });
    const header = createElement('tr');
    ['Дата', 'Тип', 'Сообщение', 'Статус', 'Объяснительная'].forEach(label => header.append(createElement('th', { text: label })));
    table.append(createElement('thead', {}, header));
    const tbody = createElement('tbody');
    notifications.forEach(notification => tbody.append(createElement('tr', {}, [
        createElement('td', { text: new Date(notification.created_at).toLocaleDateString('ru-RU') }),
        createElement('td', { text: notification.type === 'reprimand' ? '❌' : notification.type === 'warning' ? '⚠️' : '✅' }),
        createElement('td', { text: notification.message }),
        createElement('td', { text: notification.status === 'draft' ? 'Черновик' : notification.status === 'sent' ? 'Отправлено' : 'Отклонено' }),
        createElement('td', { text: notification.explanation || '—' })
    ])));
    table.append(tbody);
    return createElement('div', { className: 'recent-table' }, table);
}
