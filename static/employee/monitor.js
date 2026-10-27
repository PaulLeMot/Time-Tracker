import { getLocalDate, formatHoursToHHMM, formatMinutesToHHMM, showToast } from './core.js';
import { createElement, showMessage } from './dom.js';

let notificationModalOpener = null;

export function registerNotificationModalOpener(opener) {
    notificationModalOpener = opener;
}

// ========== МОНИТОРИНГ ==========
    let monitorEventSource = null;
    let monitorFilterEnabled = localStorage.getItem('monitorFilterEnabled') === 'true';
    let monitorStatusOrder = [];

    export function loadMonitorStatusOrder() {
        const saved = localStorage.getItem('monitorStatusOrder');
        if (saved) monitorStatusOrder = JSON.parse(saved);
        else monitorStatusOrder = ['working', 'onbreak', 'notstarted', 'ended'];
        applyMonitorOrderToUI();
    }
    export function applyMonitorOrderToUI() {
        const container = document.getElementById('monitorStatusOrderList');
        const items = Array.from(container.children);
        items.sort((a,b) => monitorStatusOrder.indexOf(a.dataset.status) - monitorStatusOrder.indexOf(b.dataset.status));
        container.innerHTML = '';
        items.forEach(item => container.appendChild(item));
    }
    export function saveMonitorStatusOrder() {
        const items = document.querySelectorAll('#monitorStatusOrderList li');
        monitorStatusOrder = Array.from(items).map(li => li.dataset.status);
        localStorage.setItem('monitorStatusOrder', JSON.stringify(monitorStatusOrder));
        showToast('Порядок статусов сохранён');
        const monitorDate = document.getElementById('monitorDate').value;
        if (monitorDate) loadMonitorReport(monitorDate);
    }
    export function initMonitorDragAndDrop() {
        const list = document.getElementById('monitorStatusOrderList');
        if (!list) return;
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
            saveMonitorStatusOrder();
        });
        list.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const targetItem = e.target.closest('li');
            if (!targetItem || targetItem === dragItem) return;
            const rect = targetItem.getBoundingClientRect();
            const midpoint = (rect.left + rect.right) / 2;
            if (e.clientX < midpoint) targetItem.parentNode.insertBefore(dragItem, targetItem);
            else targetItem.parentNode.insertBefore(dragItem, targetItem.nextSibling);
        });
    }

    export function toggleMonitorFilter() {
        monitorFilterEnabled = !monitorFilterEnabled;
        localStorage.setItem('monitorFilterEnabled', monitorFilterEnabled);
        const settingsDiv = document.getElementById('monitorStatusOrderSettings');
        const toggleBtn = document.getElementById('toggleMonitorFilterBtn');
        if (monitorFilterEnabled) {
            settingsDiv.style.display = 'block';
            toggleBtn.textContent = '🎛️ Скрыть фильтр статусов';
            loadMonitorStatusOrder();
            initMonitorDragAndDrop();
        } else {
            settingsDiv.style.display = 'none';
            toggleBtn.textContent = '🎛️ Фильтр по статусам';
        }
        const currentDate = document.getElementById('monitorDate').value;
        if (currentDate) loadMonitorReport(currentDate);
    }

    export async function loadMonitorReport(date) {
        const container = document.getElementById('monitorContainer');
        showMessage(container, 'Загрузка...');
        try {
            const response = await fetch(`/api/reports/daily?date=${date}`);
            if (!response.ok) throw new Error('Ошибка загрузки');
            const report = await response.json();
            if (!report.length) {
                showMessage(container, 'Нет данных за этот день');
                return;
            }
            sortMonitorRows(report);
            const content = window.innerWidth <= 768 ? createMonitorCards(report) : createMonitorTable(report);
            container.replaceChildren(content);
            bindMonitorActions(container);
        } catch (error) {
            showMessage(container, 'Ошибка загрузки', 'error');
            showToast(error.message, true);
        }
    }

    function sortMonitorRows(report) {
        if (!monitorFilterEnabled) {
            report.sort((left, right) => left.full_name.localeCompare(right.full_name, 'ru'));
            return;
        }
        const priority = row => {
            const key = row.status_break === '☕ в перерыве' ? 'onbreak'
                : row.status_day === '✅ работает' ? 'working'
                : row.status_day === '❌ не начал' ? 'notstarted'
                : row.status_day === '🏁 завершил' ? 'ended' : '';
            const index = monitorStatusOrder.indexOf(key);
            return index < 0 ? 99 : index;
        };
        report.sort((left, right) => priority(left) - priority(right) || left.full_name.localeCompare(right.full_name, 'ru'));
    }

    function createMonitorTable(report) {
        const table = createElement('table', { className: 'report-table' });
        const header = createElement('tr');
        ['Сотрудник', 'Статус', 'Начало дня', 'Последняя отметка', 'Отработано', 'Перерывы', 'Кол-во перерывов', 'Действие']
            .forEach(label => header.append(createElement('th', { text: label })));
        table.append(createElement('thead', {}, header));
        const tbody = createElement('tbody');
        report.forEach(item => {
            const row = createElement('tr', { className: monitorRowClass(item) });
            const values = [
                item.full_name,
                combinedMonitorStatus(item),
                item.first_start_time ? item.first_start_time.slice(11, 16) : '',
                formatLastMonitorEntry(item),
                formatHoursToHHMM(item.worked_hours_current),
                formatMinutesToHHMM(item.break_minutes_current),
                item.break_count
            ];
            values.forEach(value => row.append(createElement('td', { text: value })));
            row.append(createElement('td', {}, createNotificationButton(item)));
            tbody.append(row);
        });
        table.append(tbody);
        return createElement('div', { className: 'recent-table' }, table);
    }

    function createMonitorCards(report) {
        const accordion = createElement('div', { className: 'monitor-accordion' });
        report.forEach(item => {
            const card = createElement('div', { className: `monitor-accordion-item ${monitorRowClass(item)}` });
            const header = createElement('button', { className: 'monitor-accordion-header', attrs: { type: 'button' } }, [
                createElement('span', { text: item.full_name }),
                createElement('span', { text: combinedMonitorStatus(item) })
            ]);
            header.addEventListener('click', () => card.classList.toggle('open'));
            const details = createElement('div', { className: 'monitor-accordion-details' });
            appendMonitorDetail(details, 'Начало дня', item.first_start_time ? item.first_start_time.slice(11, 16) : '—');
            appendMonitorDetail(details, 'Последняя отметка', formatLastMonitorEntry(item) || '—');
            appendMonitorDetail(details, 'Отработано', formatHoursToHHMM(item.worked_hours_current));
            appendMonitorDetail(details, 'Перерывы', formatMinutesToHHMM(item.break_minutes_current));
            appendMonitorDetail(details, 'Кол-во перерывов', item.break_count);
            appendMonitorDetail(details, 'Действие', createNotificationButton(item));
            card.append(header, details);
            accordion.append(card);
        });
        return accordion;
    }

    function appendMonitorDetail(parent, label, value) {
        const row = createElement('div', { className: 'monitor-accordion-details-row' });
        row.append(
            createElement('span', { className: 'monitor-accordion-label', text: `${label}:` }),
            createElement('span', { className: 'monitor-accordion-value' }, value)
        );
        parent.append(row);
    }

    function createNotificationButton(item) {
        return createElement('button', {
            className: 'btn-sm send-notif', text: '📝', attrs: { type: 'button' },
            dataset: { id: item.employee_id, name: item.full_name }
        });
    }

    function bindMonitorActions(container) {
        container.querySelectorAll('.send-notif').forEach(button => {
            button.addEventListener('click', event => {
                event.stopPropagation();
                notificationModalOpener?.(button.dataset.id, button.dataset.name);
            });
        });
    }

    function combinedMonitorStatus(item) {
        return item.status_break || item.status_day;
    }

    function monitorRowClass(item) {
        if (item.status_day === '❌ не начал') return 'row-not-started';
        if (item.status_break === '☕ в перерыве') return 'row-on-break';
        if (item.status_day === '✅ работает') return 'row-working';
        if (item.status_day === '🏁 завершил') return 'row-ended';
        return '';
    }

    function formatLastMonitorEntry(item) {
        if (!item.last_entry_time) return '';
        const labels = { start: 'Начало дня', break_start: 'Начало перерыва', break_end: 'Конец перерыва', end: 'Конец дня' };
        return `${item.last_entry_time.slice(11, 16)} - ${labels[item.last_entry_action] || item.last_entry_action || ''}`;
    }

    export function connectMonitorSSE() {
        if (monitorEventSource) monitorEventSource.close();
        monitorEventSource = new EventSource('/api/monitor/events');
        monitorEventSource.addEventListener('update', () => {
            const activeTab = document.querySelector('.tab-btn.active');
            if (activeTab && activeTab.dataset.tab === 'monitor') {
                const monitorDate = document.getElementById('monitorDate').value || getLocalDate();
                loadMonitorReport(monitorDate);
            }
        });
        monitorEventSource.onerror = () => {
            if (monitorEventSource) monitorEventSource.close();
            monitorEventSource = null;
        };
    }

    document.getElementById('monitorDate').value = getLocalDate();
    document.getElementById('refreshMonitorBtn').addEventListener('click', () => {
        loadMonitorReport(document.getElementById('monitorDate').value);
    });
    document.getElementById('monitorDate').addEventListener('change', () => {
        loadMonitorReport(document.getElementById('monitorDate').value);
    });
    document.getElementById('toggleMonitorFilterBtn').addEventListener('click', toggleMonitorFilter);
