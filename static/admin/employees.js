/**
 * Модуль админ-панели: Управление сотрудниками.
 * Подключается через main.js и использует явные ES module зависимости.
 */
import { showToast } from './core.js';
import { insertScheduleRow, openEditUsernameModal, openEditFullnameModal, openEditPasswordModal, refreshCurrentReport, openRoleModal } from './actions.js';
import { createElement } from './dom.js';

export async function loadEmployees() {
        try {
            // Загружаем сотрудников
            const empResp = await fetch('/api/employees?active_only=false');
            if (!empResp.ok) throw new Error('Ошибка загрузки сотрудников');
            let employees = await empResp.json();
            employees.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));

            // Загружаем роли, чтобы узнать, у кого какая должность
            let roles = [];
            try {
                const rolesResp = await fetch('/api/sandbox/roles', { credentials: 'include' });
                if (rolesResp.ok) {
                    roles = await rolesResp.json();
                } else {
                    console.warn('Не удалось загрузить роли, поле "Должность" будет пустым');
                }
            } catch (err) {
                console.warn('Ошибка загрузки должностей:', err);
            }

            // Строим маппинг: employee_id -> список названий должностей
            const employeeRolesMap = {};
            roles.forEach(role => {
                if (role.employees && role.employees.length > 0) {
                    role.employees.forEach(emp => {
                        if (!employeeRolesMap[emp.id]) {
                            employeeRolesMap[emp.id] = [];
                        }
                        employeeRolesMap[emp.id].push(role.name);
                    });
                }
            });

            const tbody = document.getElementById('employeesTbody');
            tbody.innerHTML = '';
            for (const emp of employees) {
                const row = tbody.insertRow();

                row.insertCell(0).innerText = emp.id;

                const loginCell = row.insertCell(1);
                loginCell.append(
                    document.createTextNode(`${emp.username} `),
                    createElement('button', {
                        className: 'small-btn edit-username-btn', text: '✏️', attrs: { type: 'button', title: 'Редактировать логин' },
                        dataset: { id: emp.id, username: emp.username }
                    })
                );

                const nameCell = row.insertCell(2);
                nameCell.append(
                    document.createTextNode(`${emp.full_name} `),
                    createElement('button', {
                        className: 'small-btn edit-fullname-btn', text: '✏️', attrs: { type: 'button', title: 'Редактировать ФИО' },
                        dataset: { id: emp.id, fullname: emp.full_name }
                    })
                );

                const passwordCell = row.insertCell(3);
                passwordCell.append(
                    createElement('span', { className: 'password-value', text: emp.password || 'не задан' }),
                    createElement('button', { className: 'small-btn reset-pass-btn', text: '🔑', attrs: { type: 'button', title: 'Сбросить пароль' }, dataset: { id: emp.id } }),
                    createElement('button', { className: 'small-btn edit-pass-btn', text: '✏️', attrs: { type: 'button', title: 'Изменить пароль' }, dataset: { id: emp.id, password: emp.password || '' } })
                );

                const activeCell = row.insertCell(4);
                activeCell.append(
                    document.createTextNode(emp.is_active ? 'Да ' : 'Нет '),
                    createElement('button', { className: 'small-btn toggle-active-btn', text: '🔄', attrs: { type: 'button', title: 'Изменить статус' }, dataset: { id: emp.id, active: emp.is_active } })
                );

                // ---------- ЯЧЕЙКА: ДОЛЖНОСТЬ ----------
                const roleCell = row.insertCell(5);
                const roleNames = employeeRolesMap[emp.id] || [];
                if (roleNames.length > 0) {
                    roleCell.innerText = roleNames.join(', ');
                    roleCell.style.cursor = 'pointer';
                    roleCell.style.color = '#3b82f6';
                    roleCell.style.textDecoration = 'underline';
                } else {
                    roleCell.innerText = '—';
                    roleCell.style.color = '#94a3b8';
                    roleCell.style.cursor = 'pointer';
                }
                roleCell.addEventListener('click', function() {
                    openRoleModal(emp.id, emp.full_name);
                });

                // Админ
                const adminCell = row.insertCell(6);
                const adminCheckbox = document.createElement('input');
                adminCheckbox.type = 'checkbox';
                adminCheckbox.className = 'admin-checkbox';
                adminCheckbox.dataset.id = emp.id;
                adminCheckbox.checked = emp.is_admin === 1;
                adminCheckbox.addEventListener('change', async (e) => {
                    const val = e.target.checked ? 1 : 0;
                    try {
                        const resp = await fetch(`/api/employees/${emp.id}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ is_admin: val })
                        });
                        if (!resp.ok) throw new Error('Ошибка');
                        showToast(`Права админа ${val ? 'установлены' : 'сняты'}`);
                    } catch (err) {
                        showToast('Ошибка обновления прав', true);
                        e.target.checked = !e.target.checked;
                    }
                });
                adminCell.appendChild(adminCheckbox);

                // Мониторинг
                const monitorCell = row.insertCell(7);
                const monitorCheckbox = document.createElement('input');
                monitorCheckbox.type = 'checkbox';
                monitorCheckbox.className = 'monitor-checkbox';
                monitorCheckbox.dataset.id = emp.id;
                monitorCheckbox.checked = emp.is_monitor === 1;
                monitorCheckbox.addEventListener('change', async (e) => {
                    const val = e.target.checked ? 1 : 0;
                    try {
                        const resp = await fetch(`/api/employees/${emp.id}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ is_monitor: val })
                        });
                        if (!resp.ok) throw new Error('Ошибка');
                        showToast(`Права мониторинга ${val ? 'установлены' : 'сняты'}`);
                    } catch (err) {
                        showToast('Ошибка обновления прав', true);
                        e.target.checked = !e.target.checked;
                    }
                });
                monitorCell.appendChild(monitorCheckbox);

                // Действия (Штрих-код и удаление)
                const actionsCell = row.insertCell(8);
                const barcodeBtn = document.createElement('button');
                barcodeBtn.textContent = 'Штрих-код';
                barcodeBtn.onclick = () => window.open(`/api/employees/${emp.id}/barcode?action=start`, '_blank');
                const delBtn = document.createElement('button');
                delBtn.textContent = '🗑️';
                delBtn.className = 'btn-danger btn-sm';
                delBtn.onclick = async () => {
                    if (confirm(`Удалить ${emp.full_name} навсегда? Это действие необратимо.`)) {
                        const resp = await fetch(`/api/employees/${emp.id}?permanent=true`, { method: 'DELETE' });
                        if (resp.ok) {
                            showToast('Сотрудник удалён');
                            loadEmployees();
                            refreshCurrentReport();
                        } else showToast('Ошибка', true);
                    }
                };

                const expandCell = row.insertCell(9);
                const hasSchedule = emp.schedule_data && Object.keys(emp.schedule_data).length > 0;
                const expandBtn = createElement('button', {
                    className: `expand-schedule-btn ${hasSchedule ? 'has-schedule' : 'has-no-schedule'}`,
                    text: '▼', attrs: { type: 'button' }, dataset: { id: emp.id }
                });
                expandCell.append(expandBtn);
                if (expandBtn) {
                    expandBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const row = expandBtn.closest('tr');
                        const nextRow = row.nextElementSibling;
                        if (nextRow && nextRow.classList.contains('schedule-row')) {
                            nextRow.remove();
                            expandBtn.textContent = '▼';
                        } else {
                            if (row.nextElementSibling && row.nextElementSibling.classList.contains('schedule-row')) {
                                row.nextElementSibling.remove();
                            }
                            insertScheduleRow(row, emp.id, expandBtn);
                        }
                    });
                }
                actionsCell.appendChild(barcodeBtn);
                actionsCell.appendChild(delBtn);
            }

            // ---- Обработчики кнопок (редактирование, пароль, активность) ----
            document.querySelectorAll('.edit-username-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const id = btn.dataset.id;
                    const username = btn.dataset.username;
                    openEditUsernameModal(id, username);
                });
            });
            document.querySelectorAll('.edit-fullname-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const id = btn.dataset.id;
                    const fullname = btn.dataset.fullname;
                    openEditFullnameModal(id, fullname);
                });
            });
            document.querySelectorAll('.reset-pass-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = btn.dataset.id;
                    if (confirm('Сбросить пароль?')) {
                        const resp = await fetch(`/api/employees/${id}/reset-password`, { method: 'POST' });
                        if (resp.ok) {
                            const data = await resp.json();
                            alert(`Новый пароль: ${data.new_password}`);
                            loadEmployees();
                            refreshCurrentReport();
                        } else showToast('Ошибка', true);
                    }
                });
            });
            document.querySelectorAll('.edit-pass-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const id = btn.dataset.id;
                    openEditPasswordModal(id);
                });
            });
            document.querySelectorAll('.toggle-active-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = btn.dataset.id;
                    const isActive = btn.dataset.active === '1' || btn.dataset.active === true;
                    const newStatus = isActive ? 0 : 1;
                    const resp = await fetch(`/api/employees/${id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ is_active: newStatus })
                    });
                    if (resp.ok) {
                        showToast(`Сотрудник ${newStatus ? 'активирован' : 'деактивирован'}`);
                        loadEmployees();
                        refreshCurrentReport();
                    } else showToast('Ошибка', true);
                });
            });

            // Сохраняем маппинг в глобальной переменной для использования в модальном окне

        } catch (err) {
            showToast(err.message, true);
        }
    }
document.getElementById('addEmployeeForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('username').value.trim();
        const fullName = document.getElementById('fullName').value.trim();
        if (!fullName) return;
        try {
            const resp = await fetch('/api/employees', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ username: username, full_name: fullName })
            });
            if (resp.ok) {
                showToast('Сотрудник добавлен');
                document.getElementById('fullName').value = '';
                loadEmployees();
                refreshCurrentReport();
            } else {
                const err = await resp.json();
                showToast(err.detail || 'Ошибка', true);
            }
        } catch (err) {
            showToast('Ошибка сети', true);
        }
    });
