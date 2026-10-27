/** Editor for independent tasks shown from the admin task list. */
import { showToast } from './core.js';
import { createElement, showMessage } from './dom.js';
import { loadMailingNotifications } from './mailing.js';

export async function openIndependentTaskEditor(independentTaskId) {
    const procsetsContainer = document.getElementById('procsets-tab');
    const modal = procsetsContainer?.querySelector('#detailModal');
    const title = modal?.querySelector('#detailTitle');
    const body = modal?.querySelector('#detailBody');
    if (!modal || !title || !body) return;
    title.textContent = 'Редактирование независимой задачи';
    showMessage(body, 'Загрузка...');
    modal.style.display = 'block';
    try {
        const [taskResponse, optionsResponse] = await Promise.all([
            fetch(`/api/sandbox/independent-tasks/${independentTaskId}`, {credentials:'include'}),
            fetch('/api/sandbox/task-creation-options', {credentials:'include'})
        ]);
        if (!taskResponse.ok) throw new Error((await taskResponse.json()).detail || 'Не удалось загрузить задачу');
        if (!optionsResponse.ok) throw new Error((await optionsResponse.json()).detail || 'Не удалось загрузить справочники');
        const task = await taskResponse.json();
        const options = await optionsResponse.json();
        const assignedIds = new Set(task.assignees.map(item => Number(item.employee_id)));
        const mainAssignee = task.assignees.find(item => item.is_main);
        let score = { total_points: 0, assignees: [] };
        if (mainAssignee) {
            const scoreResponse = await fetch(`/api/sandbox/task-assignments/${mainAssignee.notification_id}/score-details`, { credentials: 'include' });
            if (scoreResponse.ok) score = await scoreResponse.json();
        }
        const productMap = new Map((task.products || []).map(item => [Number(item.id), item]));
        const completionMap = task.completion_data || {};
        body.replaceChildren(createIndependentEditor(task, options, score, assignedIds, mainAssignee, productMap, completionMap));
        body.querySelector('#independentEditEmployees').addEventListener('change', event => {
            if (event.target.name === 'independentEditMain') {
                const checkbox = body.querySelector(`.independent-edit-employee[value="${event.target.value}"]`);
                if (checkbox) checkbox.checked = true;
            }
        });
        body.querySelectorAll('.independent-product-distribution').forEach(input => {
            input.addEventListener('change', async () => {
                const row = input.closest('.independent-product-row');
                const distributions = [...row.querySelectorAll('.independent-product-distribution')].map(item => ({employee_id:Number(item.dataset.employeeId), quantity:Math.max(0, parseInt(item.value) || 0)}));
                const response = await fetch(`/api/sandbox/task-assignments/${mainAssignee.notification_id}/completion`, {
                    method:'PUT', credentials:'include', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({product_type_id:Number(row.dataset.productId), defect_quantity:Number(completionMap[row.dataset.productId]?.defect_quantity || 0), defect_comment:completionMap[row.dataset.productId]?.defect_comment || null, distributions})
                });
                if (!response.ok) showToast((await response.json()).detail || 'Ошибка сохранения распределения', true);
                else showToast('Распределение товаров сохранено');
            });
        });
        body.querySelectorAll('.independent-score-percent').forEach(input => {
            input.addEventListener('change', async () => {
                const scoreBlock = body.querySelector('#independentScoreBlock');
                const percentages = [...scoreBlock.querySelectorAll('.independent-score-percent')].map(item => ({employee_id:Number(item.dataset.employeeId), percent:Math.max(0, Math.min(100, parseInt(item.value) || 0))}));
                const total = percentages.reduce((sum, item) => sum + item.percent, 0);
                const totalCell = body.querySelector('#independentScorePercentTotal');
                totalCell.textContent = `${total}%`;
                totalCell.style.color = total === 100 ? '#16a34a' : '#dc2626';
                percentages.forEach(item => {
                    const cell = scoreBlock.querySelector(`.independent-score-points[data-employee-id="${item.employee_id}"]`);
                    if (cell) cell.textContent = Math.round(Number(scoreBlock.dataset.totalPoints) * item.percent / 100);
                });
                const response = await fetch(`/api/sandbox/task-assignments/${scoreBlock.dataset.notificationId}/completion-percentages`, {method:'PUT', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify({percentages})});
                if (!response.ok) showToast((await response.json()).detail || 'Ошибка сохранения процентов', true);
            });
        });
        body.querySelector('#saveIndependentTaskEdit').addEventListener('click', async event => {
            const button = event.currentTarget;
            const error = body.querySelector('#independentEditError');
            const selectedIds = [...body.querySelectorAll('.independent-edit-employee:checked')].map(item => Number(item.value));
            const selectedMain = body.querySelector('input[name="independentEditMain"]:checked');
            if (!selectedIds.length) { error.textContent = 'Выберите хотя бы одного сотрудника'; return; }
            if (!selectedMain || !selectedIds.includes(Number(selectedMain.value))) { error.textContent = 'Выберите основного исполнителя'; return; }
            const newMainId = Number(selectedMain.value);
            const products = [...body.querySelectorAll('.independent-edit-product:checked')].map(item => ({id:Number(item.value), name:item.dataset.name, quantity:Math.max(1, Number(body.querySelector(`.independent-edit-product-quantity[data-product-id="${item.value}"]`)?.value || 1))}));
            button.disabled = true;
            error.textContent = '';
            try {
                const currentIds = task.assignees.map(item => Number(item.employee_id));
                for (const employeeId of selectedIds.filter(id => !currentIds.includes(id))) {
                    const response = await fetch(`/api/sandbox/independent-tasks/${independentTaskId}/assignees`, {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify({employee_id:employeeId, is_main:false})});
                    if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось добавить сотрудника');
                }
                const mainResponse = await fetch(`/api/sandbox/independent-tasks/${independentTaskId}/main-assignee/${newMainId}`, {method:'PUT', credentials:'include'});
                if (!mainResponse.ok) throw new Error((await mainResponse.json()).detail || 'Не удалось изменить основного исполнителя');
                for (const employeeId of currentIds.filter(id => !selectedIds.includes(id))) {
                    const response = await fetch(`/api/sandbox/independent-tasks/${independentTaskId}/assignees/${employeeId}`, {method:'DELETE', credentials:'include'});
                    if (!response.ok) throw new Error((await response.json()).detail || 'Не удалось удалить сотрудника');
                }
                const payload = {title:body.querySelector('#independentEditTitle').value.trim() || null, description:body.querySelector('#independentEditDescription').value.trim() || null, status:body.querySelector('#independentEditStatus').value, products};
                const updateResponse = await fetch(`/api/sandbox/independent-tasks/${independentTaskId}`, {method:'PATCH', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
                if (!updateResponse.ok) throw new Error((await updateResponse.json()).detail || 'Не удалось сохранить задачу');
                const updatedTask = await updateResponse.json();
                const updatedMain = updatedTask.assignees.find(item => item.is_main);
                if (updatedMain) {
                    const executionStatus = payload.status === 'completed' ? 'completed' : (updatedMain.status === 'completed' ? 'not_started' : updatedMain.status);
                    await fetch(`/api/sandbox/task-assignments/${updatedMain.notification_id}/status`, {method:'PUT', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify({status:executionStatus})});
                }
                modal.style.display = 'none';
                showToast('Задача обновлена');
                loadMailingNotifications();
            } catch (value) { error.textContent = value.message; }
            finally { button.disabled = false; }
        });
    } catch (value) {
        showMessage(body, value.message, 'error');
    }
}


function createIndependentEditor(task, options, score, assignedIds, mainAssignee, productMap, completionMap) {
    const editor = createElement('div', { className: 'independent-task-editor' });
    editor.append(createBasicTaskSection(task));

    const employeeList = createElement('div', { attrs: { id: 'independentEditEmployees' }, className: 'independent-option-list' });
    options.employees.forEach(employee => {
        const checkbox = createElement('input', { className: 'independent-edit-employee', attrs: { type: 'checkbox', value: employee.id } });
        checkbox.checked = assignedIds.has(Number(employee.id));
        const radio = createElement('input', { attrs: { type: 'radio', name: 'independentEditMain', value: employee.id } });
        radio.checked = Number(mainAssignee?.employee_id) === Number(employee.id);
        employeeList.append(createElement('div', { className: 'independent-employee-option' }, [
            checkbox,
            createElement('span', { className: 'option-name', text: employee.name }),
            createElement('label', { className: 'main-option-label' }, [radio, document.createTextNode(' основной')])
        ]));
    });
    editor.append(createEditorSection('Исполнители', employeeList));

    const productList = createElement('div', { className: 'independent-option-list' });
    options.products.forEach(product => {
        const selected = productMap.get(Number(product.id));
        const checkbox = createElement('input', {
            className: 'independent-edit-product', attrs: { type: 'checkbox', value: product.id }, dataset: { name: product.name }
        });
        checkbox.checked = Boolean(selected);
        productList.append(createElement('div', { className: 'independent-product-option' }, [
            checkbox,
            createElement('span', { text: product.name }),
            createElement('input', {
                className: 'independent-edit-product-quantity', attrs: { type: 'number', min: 1, value: selected?.quantity || 1 },
                dataset: { productId: product.id }
            })
        ]));
    });
    editor.append(createEditorSection('Назначенные товары', productList));
    editor.append(createEditorSection('Распределение товаров по сотрудникам', createIndependentProductionTable(task, completionMap)));
    editor.append(createIndependentScoreTable(score, mainAssignee));
    editor.append(createElement('div', { attrs: { id: 'independentEditError' }, className: 'form-error' }));
    editor.append(createElement('div', { className: 'editor-actions' }, createElement('button', {
        attrs: { id: 'saveIndependentTaskEdit', type: 'button' }, className: 'btn button-success-dark-bg', text: 'Сохранить'
    })));
    return editor;
}

function createBasicTaskSection(task) {
    const content = createElement('div', { className: 'editor-basic-fields' });
    content.append(createElement('div', { className: 'editor-section-title' }, [
        createElement('strong', { text: 'Основные данные' }),
        createElement('span', { className: 'text-secondary', text: `Тип: ${task.task_name}` })
    ]));
    const title = createElement('input', { attrs: { id: 'independentEditTitle', type: 'text', value: task.title || '', placeholder: `Стандартное название: ${task.task_name}` } });
    const description = createElement('textarea', { attrs: { id: 'independentEditDescription', rows: 3 } });
    description.value = task.description || '';
    const status = createElement('select', { attrs: { id: 'independentEditStatus' } });
    [['active', 'Активна'], ['completed', 'Завершена'], ['cancelled', 'Отменена']].forEach(([value, label]) => status.add(new Option(label, value, false, task.status === value)));
    content.append(createField('Название', title), createField('Описание', description), createField('Статус', status));
    return content;
}

function createField(label, control) {
    return createElement('label', { className: 'editor-field' }, [document.createTextNode(label), control]);
}

function createEditorSection(title, content) {
    return createElement('section', { className: 'independent-editor-section' }, [createElement('strong', { text: title }), content]);
}

function createIndependentProductionTable(task, completionMap) {
    if (!task.products?.length) return createElement('p', { className: 'text-secondary editor-empty-note', text: 'Товары не назначены.' });
    const table = createElement('table', { className: 'independent-production-table' });
    const header = createElement('tr');
    ['Товар', 'Всего'].forEach(label => header.append(createElement('th', { text: label })));
    task.assignees.forEach(employee => header.append(createElement('th', { text: employee.employee_name })));
    table.append(createElement('thead', {}, header));
    const tbody = createElement('tbody');
    task.products.forEach(product => {
        const completion = completionMap[String(product.id)] || {};
        const values = new Map((completion.distributions || []).map(item => [Number(item.employee_id), Number(item.quantity || 0)]));
        const row = createElement('tr', { className: 'independent-product-row', dataset: { productId: product.id, quantity: product.quantity } });
        row.append(createElement('td', { text: product.name }), createElement('td', { className: 'expected-quantity', text: product.quantity }));
        task.assignees.forEach(employee => row.append(createElement('td', {}, createElement('input', {
            className: 'independent-product-distribution', attrs: { type: 'number', min: 0, value: values.get(Number(employee.employee_id)) || 0 },
            dataset: { employeeId: employee.employee_id }
        }))));
        tbody.append(row);
    });
    table.append(tbody);
    return createElement('div', { className: 'independent-table-scroll' }, table);
}

function createIndependentScoreTable(score, mainAssignee) {
    const totalPoints = score.total_points || 0;
    const totalPercent = score.assignees.reduce((sum, item) => sum + Number(item.percent || 0), 0);
    const block = createElement('section', {
        attrs: { id: 'independentScoreBlock' }, className: 'independent-score-block',
        dataset: { notificationId: mainAssignee?.notification_id || '', totalPoints }
    });
    block.append(createElement('div', { className: 'score-distribution-header' }, [
        createElement('strong', { text: 'Распределение выполнения и баллов' }),
        createElement('span', {}, [document.createTextNode('Всего баллов за задачу: '), createElement('strong', { className: 'points-value', text: totalPoints })])
    ]));
    const table = createElement('table', { className: 'score-distribution-table' });
    const header = createElement('tr');
    ['Сотрудник', 'Выполнение, %', 'Баллы'].forEach(label => header.append(createElement('th', { text: label })));
    table.append(createElement('thead', {}, header));
    const tbody = createElement('tbody');
    score.assignees.forEach(item => {
        const employeeCell = createElement('td', { text: item.employee_name });
        if (item.is_main) employeeCell.append(document.createTextNode(' '), createElement('span', { className: 'main-assignee-label', text: 'Основной' }));
        tbody.append(createElement('tr', {}, [
            employeeCell,
            createElement('td', {}, createElement('input', { className: 'independent-score-percent', attrs: { type: 'number', min: 0, max: 100, step: 1, value: item.percent }, dataset: { employeeId: item.employee_id } })),
            createElement('td', { className: 'independent-score-points', text: Math.round(totalPoints * item.percent / 100), dataset: { employeeId: item.employee_id } })
        ]));
    });
    table.append(tbody);
    table.append(createElement('tfoot', {}, createElement('tr', { className: 'score-total-row' }, [
        createElement('td', { text: 'Итого (%)' }),
        createElement('td', { attrs: { id: 'independentScorePercentTotal' }, className: totalPercent === 100 ? 'is-valid' : 'is-invalid', text: `${totalPercent}%` }),
        createElement('td', { className: 'points-value', text: totalPoints })
    ])));
    block.append(table);
    return block;
}
