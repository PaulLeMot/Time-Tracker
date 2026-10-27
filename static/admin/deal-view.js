/** DOM renderer for the deal details modal. */
import { createElement } from './dom.js';
import { createProductionMatrixElement } from './tasks.js';

const STATUS_OPTIONS = [
    ['not_started', '❌ Не начата'],
    ['in_progress', '🔄 В процессе'],
    ['on_break', '⏸️ В перерыве'],
    ['completed', '✅ Завершена']
];

export function createDealDetailContent(deal, selectedTask, expandedTaskIds, availableProducts) {
    const root = createElement('div', { className: 'deal-detail-content' });
    root.append(createElement('div', { className: 'deal-meta' }, [
        labeledText('Тип', deal.deal_type || '—'), labeledText('ID', deal.id)
    ]));
    if (!selectedTask) root.append(createDealProducts(deal));

    const tasks = selectedTask ? [selectedTask] : (deal.tasks || []);
    if (tasks.length) {
        root.append(createElement('h4', { className: 'deal-tasks-heading', text: '📋 Задачи по сделке' }));
        const accordion = createElement('div', { className: 'task-accordion-container', attrs: { id: 'deal-tasks-accordion' } });
        tasks.forEach(task => accordion.append(createDealTask(task, deal.id, Boolean(selectedTask), expandedTaskIds)));
        root.append(accordion);
    } else {
        root.append(createElement('p', { className: 'empty-state-note', text: 'Нет задач по этой сделке' }));
    }
    if (!selectedTask) root.append(createDealAction(deal, tasks));
    return root;
}

function labeledText(label, value) {
    return createElement('div', {}, [createElement('strong', { text: `${label}:` }), document.createTextNode(` ${value}`)]);
}

function createDealProducts(deal) {
    const section = createElement('section', { className: 'deal-products-section' });
    if (deal.products?.length) {
        section.append(createElement('h4', { text: '📦 Товары в сделке' }));
        const table = createElement('table', { className: 'deal-products-table', attrs: { id: 'deal-products-table' } });
        const header = createElement('tr');
        ['Наименование', 'Полное наименование', 'Количество', 'Действие'].forEach(label => header.append(createElement('th', { text: label })));
        table.append(createElement('thead', {}, header));
        const tbody = createElement('tbody');
        deal.products.forEach(product => {
            const quantityInput = createElement('input', {
                className: 'product-quantity-input', attrs: { type: 'number', min: 1, value: product.quantity }, dataset: { productId: product.id }
            });
            quantityInput.style.display = 'none';
            tbody.append(createElement('tr', { dataset: { productId: product.id } }, [
                createElement('td', { text: product.name }),
                createElement('td', { text: product.full_name || '—' }),
                createElement('td', { className: 'cell-center' }, [
                    createElement('span', { className: 'product-quantity-display', text: product.quantity }), quantityInput
                ]),
                createElement('td', { className: 'cell-center' }, createElement('button', {
                    className: 'delete-product-from-deal icon-delete-button', text: '✖', attrs: { type: 'button' }, dataset: { productId: product.id }
                }))
            ]));
        });
        table.append(tbody);
        section.append(table);
    } else {
        section.append(createElement('p', { className: 'empty-state-note', text: 'Нет товаров в этой сделке' }));
    }
    section.append(createAddProductBlock());
    return section;
}

function createAddProductBlock() {
    const select = createElement('select', { className: 'add-product-select', attrs: { id: 'addProductSelect' } });
    select.add(new Option('-- Выберите товар --', ''));
    return createElement('div', { className: 'add-product-block' }, [
        createElement('h4', { text: '➕ Добавить товар в сделку' }),
        createElement('div', { className: 'add-product-controls' }, [
            select,
            createElement('input', { className: 'add-product-quantity', attrs: { id: 'addProductQuantity', type: 'number', min: 1, value: 1, placeholder: 'Количество' } }),
            createElement('button', { className: 'btn button-success-bg', text: '➕ Добавить', attrs: { id: 'addProductToDealBtn', type: 'button' } })
        ]),
        createElement('div', { className: 'form-error', attrs: { id: 'addProductError' } })
    ]);
}

function createDealTask(task, dealId, selected, expandedTaskIds) {
    const taskId = task.task_id;
    const assignees = task.assignees || [];
    const products = task.products || [];
    const main = assignees[0] || null;
    const mainStatus = main?.status || 'not_started';
    const open = selected || expandedTaskIds.has(Number(taskId));
    const item = createElement('section', { className: 'task-accordion-item', dataset: { taskId } });
    const header = createElement('div', { className: `task-accordion-header ${open ? 'is-open' : ''}` });
    header.append(createElement('button', {
        className: 'task-accordion-toggle', text: task.task_name || `Задача #${taskId}`,
        attrs: { type: 'button', 'aria-expanded': String(open) }
    }));
    header.append(createSummaryColumn('Товары', createProductSummary(products)));
    header.append(createSummaryColumn('Сотрудники', createEmployeeSummary(assignees)));
    header.append(createSummaryColumn('Статусы и отметки', createStatusSummary(assignees, main?.notification_id, mainStatus)));
    item.append(header);

    const details = createElement('div', { className: 'task-accordion-details' });
    details.style.display = open ? 'block' : 'none';
    if (selected) details.append(createTaskProductEditor(products));
    details.append(createAssigneeEditor(taskId, assignees));
    details.append(createElement('div', { className: 'task-detail-section' }, [
        createElement('strong', { text: 'Производство и брак:' }), createProductionMatrixElement(task, dealId)
    ]));
    const comment = createElement('textarea', {
        className: 'matrix-general-comment', attrs: { rows: 3, placeholder: 'Комментарий исполнителя или заметка администратора...' },
        dataset: { taskId, dealId }
    });
    comment.value = main?.general_comment || '';
    details.append(createElement('div', { className: 'task-detail-section' }, [
        createElement('strong', { text: '💬 Общий комментарий к задаче:' }), comment
    ]));
    details.append(createTaskMetadata(main, mainStatus));
    item.append(details);
    return item;
}

function createSummaryColumn(label, content) {
    return createElement('div', { className: 'task-summary-column' }, [
        createElement('div', { className: 'task-summary-label', text: label }), content
    ]);
}

function createProductSummary(products) {
    const box = createElement('div');
    if (!products.length) { box.textContent = '—'; return box; }
    products.forEach((product, index) => {
        if (index) box.append(document.createElement('br'));
        box.append(document.createTextNode(product.name), createElement('span', { className: 'product-quantity', text: ` (${product.quantity})` }));
    });
    return box;
}

function createEmployeeSummary(assignees) {
    const box = createElement('div', { className: 'summary-list' });
    if (!assignees.length) { box.append(createElement('span', { className: 'text-muted', text: 'Нет исполнителей' })); return box; }
    assignees.forEach((assignee, index) => box.append(createElement('div', { className: 'summary-row' }, [
        createElement('span', { className: 'task-employee-name', text: assignee.employee_name }),
        createElement('span', { className: `task-role-badge ${index === 0 ? 'is-main' : 'is-assistant'}`, text: index === 0 ? 'Основной' : 'Соисполнитель' })
    ])));
    return box;
}

function createStatusSummary(assignees, mainNotificationId, mainStatus) {
    const box = createElement('div', { className: 'summary-list' });
    if (!assignees.length) { box.textContent = '—'; return box; }
    assignees.forEach((assignee, index) => {
        const status = assignee.status || 'not_started';
        const row = createElement('div', { className: 'summary-row' });
        if (index === 0) {
            const display = createElement('span', {
                className: `task-status-display task-status-header-display task-status-${status}`, text: statusLabel(status),
                dataset: { notificationId: mainNotificationId }
            });
            const select = createStatusSelect('task-status-select task-status-header-select', mainNotificationId, mainStatus);
            select.style.display = 'none';
            row.append(display, select);
        } else {
            row.append(createElement('span', { className: `task-status-${status}`, text: statusLabel(status) }));
        }
        const times = formatAssigneeTimes(assignee);
        if (times) row.append(createElement('span', { className: 'task-time-label', text: times }));
        box.append(row);
    });
    return box;
}

function createTaskProductEditor(products) {
    const list = createElement('div', { className: 'task-products-list' });
    if (!products.length) list.append(createElement('span', { className: 'text-muted', text: 'Нет товаров' }));
    products.forEach(product => list.append(createElement('span', { className: 'task-product-chip' }, [
        document.createTextNode(`${product.name} `),
        createElement('input', { className: 'task-product-quantity', attrs: { type: 'number', min: 1, value: product.quantity }, dataset: { productId: product.id } }),
        createElement('button', { className: 'task-product-delete icon-delete-button', text: '✖', attrs: { type: 'button' }, dataset: { productId: product.id } })
    ])));
    const select = createElement('select', { className: 'task-product-add-select' });
    return createElement('div', { className: 'task-products-editor' }, [
        createElement('strong', { text: 'Товары задачи:' }), list,
        createElement('div', { className: 'task-product-add-row' }, [
            select,
            createElement('input', { className: 'task-product-add-quantity', attrs: { type: 'number', min: 1, value: 1 } }),
            createElement('button', { className: 'task-product-add btn button-success-bg', text: '➕ Добавить', attrs: { type: 'button' } })
        ])
    ]);
}

function createAssigneeEditor(taskId, assignees) {
    const wrapper = createElement('div', { className: 'task-detail-section' });
    wrapper.append(createElement('strong', { text: 'Исполнители:' }));
    const list = createElement('span', { attrs: { id: `assignees-list-${taskId}` } });
    if (assignees[0]) list.append(createElement('span', {
        className: 'assignee-tag main-assignee', text: assignees[0].employee_name, dataset: { taskId }
    }));
    assignees.slice(1).forEach(assignee => list.append(createElement('span', { className: 'assignee-tag co-assignee' }, [
        document.createTextNode(assignee.employee_name),
        createElement('button', {
            className: 'remove-assignee-btn', text: '✖', attrs: { type: 'button' },
            dataset: { taskId, notificationId: assignee.notification_id, employeeId: assignee.employee_id }
        })
    ])));
    if (!assignees.length) list.append(createElement('span', { className: 'text-muted', text: 'Нет исполнителей' }));
    wrapper.append(list, createElement('button', {
        className: 'add-assignee-btn', text: '➕', attrs: { type: 'button', title: 'Добавить соисполнителя' }, dataset: { taskId }
    }));
    return wrapper;
}

function createTaskMetadata(main, status) {
    const grid = createElement('div', { className: 'task-metadata-grid' });
    const notificationId = main?.notification_id || '';
    const statusDisplay = createElement('span', { className: 'task-status-display', text: statusLabel(status), dataset: { notificationId } });
    const statusSelect = createStatusSelect('task-status-select', notificationId, status);
    statusSelect.style.display = 'none';
    addMetadataRow(grid, 'Статус', [statusDisplay, statusSelect]);
    addTimeMetadataRow(grid, 'Начало', 'started', main?.started_at, notificationId);
    addTimeMetadataRow(grid, 'Завершение', 'completed', main?.completed_at, notificationId);
    return grid;
}

function addMetadataRow(grid, label, nodes) {
    grid.append(createElement('div', {}, createElement('strong', { text: `${label}:` })), createElement('div', {}, nodes));
}

function addTimeMetadataRow(grid, label, prefix, value, notificationId) {
    const display = createElement('span', {
        className: `task-${prefix}-display`, text: value ? new Date(value).toLocaleString() : '—',
        dataset: { notificationId, iso: value || '' }
    });
    const input = createElement('input', {
        className: `task-${prefix}-input`, attrs: { type: 'datetime-local', value: value ? new Date(value).toISOString().slice(0, 16) : '' },
        dataset: { notificationId }
    });
    input.style.display = 'none';
    addMetadataRow(grid, label, [display, input]);
}

function createStatusSelect(className, notificationId, currentStatus) {
    const select = createElement('select', { className, dataset: { notificationId, savedValue: currentStatus } });
    STATUS_OPTIONS.forEach(([value, label]) => select.add(new Option(label, value, false, value === currentStatus)));
    return select;
}

function statusLabel(status) {
    return STATUS_OPTIONS.find(([value]) => value === status)?.[1] || status;
}

function formatAssigneeTimes(assignee) {
    const options = { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' };
    return [
        assignee.started_at ? `🟢 ${new Date(assignee.started_at).toLocaleString('ru-RU', options)}` : '',
        assignee.completed_at ? `🏁 ${new Date(assignee.completed_at).toLocaleString('ru-RU', options)}` : ''
    ].filter(Boolean).join(' ');
}

function createDealAction(deal, tasks) {
    const allCompleted = tasks.length > 0 && tasks.every(task => task.assignees.length > 0 && task.assignees.every(item => item.status === 'completed'));
    let button;
    if (deal.status === 'completed') button = createElement('button', { className: 'btn deal-action-complete', text: '✅ Сделка завершена', attrs: { disabled: true } });
    else if (allCompleted) button = createElement('button', { className: 'btn deal-action-finish', text: '🏁 Завершить сделку', attrs: { id: 'completeDealBtn' } });
    else if (tasks.length) button = createElement('button', { className: 'btn deal-action-started', text: '✅ Сделка запущена', attrs: { disabled: true } });
    else button = createElement('button', { className: 'btn deal-action-launch', text: '▶️ Запустить', attrs: { id: 'startDealBtn' } });
    return createElement('div', { className: 'deal-action-row' }, button);
}
