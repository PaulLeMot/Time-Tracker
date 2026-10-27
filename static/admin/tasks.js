/**
 * Модуль админ-панели: Задачи, баллы и редактор независимых задач.
 * Подключается через main.js и использует явные ES module зависимости.
 */
import { STORAGE_KEYS } from './state.js';
import { showToast } from './core.js';
import { createElement, showMessage } from './dom.js';

export async function loadPointsMatrix() {
    const container = document.getElementById('pointsMatrixContainer');
    const status = document.getElementById('pointsMatrixStatus');
    const refreshButton = document.getElementById('refreshPointsMatrixBtn');
    if (!container) return;
    if (refreshButton && !refreshButton.dataset.initialized) {
        refreshButton.dataset.initialized = '1';
        refreshButton.addEventListener('click', loadPointsMatrix);
    }
    showMessage(container, 'Загрузка...');
    if (status) status.textContent = '';
    try {
        const response = await fetch('/api/sandbox/task-product-points', { credentials: 'include' });
        if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось загрузить таблицу баллов');
        const data = await response.json();
        if (!data.tasks.length || !data.products.length) {
            showMessage(container, 'Для таблицы нужны хотя бы одна задача и один товар.');
            return;
        }
        const table = createElement('table', { className: 'points-matrix-table' });
        const headerRow = createElement('tr');
        headerRow.append(createElement('th', { className: 'points-task-column', text: 'Задача' }));
        data.products.forEach(product => headerRow.append(createElement('th', { text: product.name })));
        table.append(createElement('thead', {}, headerRow));
        const tbody = createElement('tbody');
        data.tasks.forEach((task, rowIndex) => {
            const row = createElement('tr', { className: rowIndex % 2 ? 'is-alternate' : '' });
            row.append(createElement('th', { className: 'points-task-column', text: task.name }));
            data.products.forEach(product => {
                const key = `${product.id}:${task.id}`;
                const value = Object.prototype.hasOwnProperty.call(data.points, key) ? data.points[key] : '';
                const input = createElement('input', {
                    className: 'points-matrix-input', attrs: { type: 'number', min: 0, step: 1, value },
                    dataset: { productId: product.id, taskId: task.id }
                });
                const clearButton = createElement('button', {
                    className: 'points-matrix-clear', text: '✖', attrs: { type: 'button', title: 'Удалить баллы' },
                    dataset: { productId: product.id, taskId: task.id }
                });
                row.append(createElement('td', {}, createElement('div', { className: 'points-cell-editor' }, [input, clearButton])));
            });
            tbody.append(row);
        });
        table.append(tbody);
        container.replaceChildren(createElement('div', { className: 'points-matrix-scroll' }, table));

        const setStatus = (message, error = false) => {
            if (!status) return;
            status.textContent = message;
            status.classList.toggle('is-error', error);
            status.classList.toggle('is-success', !error);
        };
        const saveInput = async input => {
            const rawValue = input.value.trim();
            input.disabled = true;
            try {
                const endpoint = `/api/sandbox/task-product-points/${input.dataset.productId}/${input.dataset.taskId}`;
                const saveResponse = rawValue === ''
                    ? await fetch(endpoint, { method: 'DELETE', credentials: 'include' })
                    : await fetch(endpoint, { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ points: parseInt(rawValue) }) });
                if (!saveResponse.ok) throw new Error((await saveResponse.json()).detail || 'Ошибка сохранения');
                setStatus(rawValue === '' ? 'Баллы удалены' : 'Баллы сохранены');
            } catch (error) {
                setStatus(error.message, true);
            } finally {
                input.disabled = false;
            }
        };
        container.querySelectorAll('.points-matrix-input').forEach(input => {
            input.addEventListener('change', () => saveInput(input));
            input.addEventListener('keydown', event => {
                if (event.key === 'Enter') { event.preventDefault(); input.blur(); }
            });
        });
        container.querySelectorAll('.points-matrix-clear').forEach(button => {
            button.addEventListener('click', () => {
                const input = container.querySelector(`.points-matrix-input[data-product-id="${button.dataset.productId}"][data-task-id="${button.dataset.taskId}"]`);
                if (input) { input.value = ''; saveInput(input); }
            });
        });
    } catch (error) {
        showMessage(container, error.message, 'error');
    }
}

export function renderProductionMatrix(task, dealId) {
    return createProductionMatrixElement(task, dealId).outerHTML;
}

export function createProductionMatrixElement(task, dealId) {
    const matrix = task.production_matrix;
    const host = createElement('div', { className: 'production-matrix-content' });
    if (!matrix) {
        host.append(createElement('p', { className: 'text-muted small mt-2 mb-0', text: 'Данные распределения еще не заполнены' }));
        return host;
    }
    const wrapper = document.createDocumentFragment();
    if (!matrix.rows?.length) {
        wrapper.append(createElement('p', { className: 'text-muted small mt-2 mb-0', text: 'Товары не назначены или данные еще не заполнены' }));
    } else {
        const table = createElement('table', { className: 'table table-sm table-bordered align-middle text-center production-matrix-table' });
        const header = createElement('tr');
        ['Товар', 'Брак', 'Комментарий'].forEach(label => header.append(createElement('th', { text: label })));
        matrix.employees.forEach(employee => header.append(createElement('th', { text: employee.name, attrs: { title: employee.name } })));
        table.append(createElement('thead', { className: 'table-light' }, header));
        const tbody = createElement('tbody');
        matrix.rows.forEach(product => {
            const row = createElement('tr', { dataset: {
                productId: product.product_id,
                expectedQty: product.expected_quantity ?? '',
                taskId: task.task_id,
                dealId
            } });
            row.append(
                createElement('td', { className: 'text-start', text: product.product_name }),
                createElement('td', {}, createElement('input', { className: 'matrix-defect-qty matrix-number-input', attrs: { type: 'number', min: 0, value: product.defect_qty || 0 }, dataset: { productId: product.product_id } })),
                createElement('td', {}, createElement('input', { className: 'matrix-defect-comment matrix-comment-input', attrs: { type: 'text', value: product.defect_comment || '' }, dataset: { productId: product.product_id } }))
            );
            matrix.employees.forEach(employee => {
                row.append(createElement('td', {}, createElement('input', {
                    className: 'matrix-dist-qty matrix-number-input', attrs: { type: 'number', min: 0, value: product.produced_by[String(employee.id)] || 0 },
                    dataset: { productId: product.product_id, employeeId: employee.id }
                })));
            });
            tbody.append(row);
        });
        table.append(tbody);
        wrapper.append(createElement('div', { className: 'table-responsive mt-2' }, table));
    }
    wrapper.append(createScoreDistribution(matrix.score_details || { total_points: 0, assignees: [] }, task));
    host.append(wrapper);
    return host;
}

function createScoreDistribution(score, task) {
    const totalPoints = score.total_points || 0;
    const totalPercent = (score.assignees || []).reduce((sum, item) => sum + Number(item.percent || 0), 0);
    const notificationId = (score.assignees || []).find(item => item.is_main)?.notification_id || task.assignees?.[0]?.notification_id || '';
    const block = createElement('div', { className: 'task-score-distribution', dataset: { notificationId, totalPoints } });
    block.append(createElement('div', { className: 'score-distribution-header' }, [
        createElement('strong', { text: 'Распределение выполнения и баллов' }),
        createElement('span', {}, [document.createTextNode('Всего баллов за задачу: '), createElement('strong', { className: 'points-value', text: totalPoints })])
    ]));
    const table = createElement('table', { className: 'score-distribution-table' });
    const header = createElement('tr');
    ['Сотрудник', 'Выполнение, %', 'Баллы'].forEach(label => header.append(createElement('th', { text: label })));
    table.append(createElement('thead', {}, header));
    const tbody = createElement('tbody');
    (score.assignees || []).forEach(item => {
        const nameCell = createElement('td', { text: item.employee_name });
        if (item.is_main) nameCell.append(document.createTextNode(' '), createElement('span', { className: 'main-assignee-label', text: 'Основной' }));
        tbody.append(createElement('tr', {}, [
            nameCell,
            createElement('td', {}, createElement('input', { className: 'matrix-percent-input', attrs: { type: 'number', min: 0, max: 100, step: 1, value: item.percent || 0 }, dataset: { employeeId: item.employee_id } })),
            createElement('td', { className: 'matrix-employee-points', text: Math.round(totalPoints * Number(item.percent || 0) / 100), dataset: { employeeId: item.employee_id } })
        ]));
    });
    table.append(tbody);
    const footer = createElement('tr', { className: 'score-total-row' }, [
        createElement('td', { text: 'Итого (%)' }),
        createElement('td', { className: `matrix-total-percent ${totalPercent === 100 ? 'is-valid' : 'is-invalid'}`, text: `${totalPercent}%` }),
        createElement('td', { className: 'points-value', text: totalPoints })
    ]);
    table.append(createElement('tfoot', {}, footer));
    block.append(table);
    return block;
}

export function initTaskCreationModal() {
    const modal = document.getElementById('taskCreationModal');
    const openButton = document.getElementById('openTaskCreationBtn');
    const binding = document.getElementById('newTaskBinding');
    if (!modal || !openButton || openButton.dataset.initialized) return;
    openButton.dataset.initialized = '1';
    const close = () => { modal.style.display = 'none'; };
    const updateFields = () => {
        const dealMode = binding.value === 'deal';
        document.getElementById('newTaskDealRow').style.display = dealMode ? 'block' : 'none';
        document.getElementById('newTaskTitleRow').style.display = dealMode ? 'none' : 'block';
        document.getElementById('newTaskDescriptionRow').style.display = dealMode ? 'none' : 'block';
    };
    openButton.addEventListener('click', async () => {
        const error = document.getElementById('newTaskCreationError');
        error.textContent = '';
        modal.style.display = 'block';
        try {
            const response = await fetch('/api/sandbox/task-creation-options', {credentials:'include'});
            if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось загрузить данные');
            const data = await response.json();
            document.getElementById('newTaskDeal').replaceChildren(...data.deals.filter(item => item.status !== 'completed').map(item => new Option(item.title, item.id)));
            document.getElementById('newTaskTemplate').replaceChildren(...data.tasks.map(item => new Option(item.name, item.id)));
            const employeeRows = data.employees.map(item => {
                const checkboxId = `newTaskEmployee${item.id}`;
                return createElement('div', { className: 'task-choice-row' }, [
                    createElement('input', { className: 'new-task-employee', attrs: { type: 'checkbox', value: item.id, id: checkboxId } }),
                    createElement('label', { className: 'task-choice-name', text: item.name, attrs: { for: checkboxId } }),
                    createElement('label', { className: 'task-main-choice' }, [
                        createElement('input', { attrs: { type: 'radio', name: 'newTaskMainEmployee', value: item.id } }),
                        document.createTextNode(' основной')
                    ])
                ]);
            });
            document.getElementById('newTaskEmployees').replaceChildren(...employeeRows);
            const productRows = data.products.map(item => createElement('div', { className: 'task-product-choice' }, [
                createElement('input', { className: 'new-task-product', attrs: { type: 'checkbox', value: item.id }, dataset: { name: item.name } }),
                createElement('span', { text: item.name }),
                createElement('input', { className: 'new-task-product-quantity', attrs: { type: 'number', min: 0, title: 'Количество (необязательно)' }, dataset: { productId: item.id } })
            ]));
            const productsContainer = document.getElementById('newTaskProducts');
            productsContainer.replaceChildren(...(productRows.length ? productRows : [createElement('span', { className: 'text-muted', text: 'Нет товаров' })]));
        } catch (value) { error.textContent = value.message; }
        updateFields();
    });
    binding.addEventListener('change', updateFields);
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
        const button = document.getElementById('saveTaskCreationBtn');
        const error = document.getElementById('newTaskCreationError');
        const employeeIds = [...modal.querySelectorAll('.new-task-employee:checked')].map(item => Number(item.value));
        const main = modal.querySelector('input[name="newTaskMainEmployee"]:checked');
        const products = [...modal.querySelectorAll('.new-task-product:checked')].map(item => {
            const rawQuantity = modal.querySelector(`.new-task-product-quantity[data-product-id="${item.value}"]`)?.value.trim() || '';
            return {id:Number(item.value), name:item.dataset.name, quantity:rawQuantity === '' ? null : Number(rawQuantity)};
        });
        const taskId = Number(document.getElementById('newTaskTemplate').value);
        if (!employeeIds.length) { error.textContent = 'Выберите хотя бы одного сотрудника'; return; }
        if (!main || !employeeIds.includes(Number(main.value))) { error.textContent = 'Выберите основного исполнителя'; return; }
        if (!taskId) { error.textContent = 'Выберите задачу'; return; }
        const dealMode = binding.value === 'deal';
        const payload = dealMode
            ? {deal_id:Number(document.getElementById('newTaskDeal').value), task_id:taskId, employee_ids:employeeIds, main_employee_id:Number(main.value), products}
            : {task_id:taskId, employee_ids:employeeIds, main_employee_id:Number(main.value), products, title:document.getElementById('newTaskTitle').value.trim() || null, description:document.getElementById('newTaskDescription').value.trim() || null};
        if (dealMode && !payload.deal_id) { error.textContent = 'Выберите сделку'; return; }
        button.disabled = true;
        error.textContent = '';
        try {
            const response = await fetch(dealMode ? '/api/sandbox/task-assignments' : '/api/sandbox/independent-tasks', {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
            if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось создать задачу');
            close();
            showToast('Задача создана');
            sessionStorage.removeItem(STORAGE_KEYS.modal);
            sessionStorage.removeItem(STORAGE_KEYS.modalState);
            window.location.reload();
        } catch (value) { error.textContent = value.message; }
        finally { button.disabled = false; }
    });
}
initTaskCreationModal();
