/**
 * Модуль админ-панели: Общее состояние, навигация, авторизация и восстановление интерфейса.
 * Подключается через main.js и использует явные ES module зависимости.
 */
import { adminState, STORAGE_KEYS } from './state.js';

const adminActions = {
    viewDeal: null,
    showEmployeeDetail: null,
    loadDailyReport: null,
    loadDailyTraffic: null,
    updateFilterVisibility: null
};

export function registerAdminActions(actions) {
    Object.assign(adminActions, actions);
}

let scrollSaveTimer = null;
const observedAdminModals = new WeakSet();
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

    export function saveScrollPosition() {
        sessionStorage.setItem(STORAGE_KEYS.scroll, String(window.scrollY));
    }

    export function restoreScrollPosition() {
        const savedPosition = Number(sessionStorage.getItem(STORAGE_KEYS.scroll));
        if (!Number.isFinite(savedPosition)) return;
        [0, 150, 500, 1200].forEach(delay => {
            setTimeout(() => window.scrollTo(0, savedPosition), delay);
        });
    }

    window.addEventListener('scroll', () => {
        clearTimeout(scrollSaveTimer);
        scrollSaveTimer = setTimeout(saveScrollPosition, 100);
    }, { passive: true });
    window.addEventListener('pagehide', saveScrollPosition);

    export function getAdminModalKey(modal) {
        return `${modal.closest('#procsets-tab') ? 'procsets' : 'admin'}:${modal.id}`;
    }

    export function captureAdminModalState(modal) {
        const fields = Array.from(modal.querySelectorAll('input, select, textarea')).map((field, index) => ({
            key: field.id || field.name || String(index),
            value: field.value,
            checked: field.checked,
            type: field.type
        }));
        const labels = Array.from(modal.querySelectorAll('[id]'))
            .filter(element => !element.matches('input, select, textarea') && element.children.length === 0)
            .map(element => ({ id: element.id, text: element.textContent }));
        sessionStorage.setItem(STORAGE_KEYS.modalState, JSON.stringify({ key: getAdminModalKey(modal), fields, labels, dataset: { ...modal.dataset } }));
    }

    export function applyAdminModalState(modal, preservedState = null) {
        const rawState = sessionStorage.getItem(STORAGE_KEYS.modalState);
        if (!preservedState && !rawState) return;
        const state = preservedState || JSON.parse(rawState);
        if (state.key !== getAdminModalKey(modal)) return;
        Object.assign(modal.dataset, state.dataset || {});
        const fields = Array.from(modal.querySelectorAll('input, select, textarea'));
        state.fields.forEach(saved => {
            const field = fields.find((item, index) => (item.id || item.name || String(index)) === saved.key);
            if (!field) return;
            field.value = saved.value;
            if (saved.type === 'checkbox' || saved.type === 'radio') field.checked = saved.checked;
        });
        state.labels.forEach(saved => {
            const element = modal.querySelector(`#${CSS.escape(saved.id)}`);
            if (element && element.children.length === 0) element.textContent = saved.text;
        });
        const entityId = Number(modal.dataset.entityId);
        if (modal.id === 'editEntryModal' && entityId) adminState.currentEditEntryId = entityId;
        if (['editUsernameModal', 'editFullnameModal'].includes(modal.id) && entityId) adminState.currentEditId = entityId;
        if (modal.id === 'editNotificationModal' && entityId) adminState.currentEditNotificationId = entityId;
        if (modal.id === 'editProposedTimeModal' && entityId) adminState.currentEditProposedNotifId = entityId;
        if (modal.id === 'roleModal' && entityId) adminState.currentEmployeeIdForRole = entityId;
        captureAdminModalState(modal);
    }

    export function observeAdminModals() {
        document.querySelectorAll('.modal[id]').forEach(modal => {
            if (observedAdminModals.has(modal)) return;
            observedAdminModals.add(modal);
            const updateState = () => {
                const key = getAdminModalKey(modal);
                if (getComputedStyle(modal).display !== 'none') {
                    sessionStorage.setItem(STORAGE_KEYS.modal, key);
                    captureAdminModalState(modal);
                } else if (sessionStorage.getItem(STORAGE_KEYS.modal) === key) {
                    sessionStorage.removeItem(STORAGE_KEYS.modal);
                    sessionStorage.removeItem(STORAGE_KEYS.modalState);
                    if (key === 'procsets:detailModal') sessionStorage.removeItem(STORAGE_KEYS.dealModalContext);
                    if (key === 'admin:detailModal') sessionStorage.removeItem(STORAGE_KEYS.employeeModalContext);
                }
            };
            new MutationObserver(updateState).observe(modal, { attributes: true, attributeFilter: ['style', 'class'] });
            modal.addEventListener('input', () => captureAdminModalState(modal));
            modal.addEventListener('change', () => captureAdminModalState(modal));
        });
    }

    window.addEventListener('pagehide', () => {
        document.querySelectorAll('.modal[id]').forEach(modal => {
            if (getComputedStyle(modal).display !== 'none') captureAdminModalState(modal);
        });
    });

    export async function restoreAdminModal() {
        const modalKey = sessionStorage.getItem(STORAGE_KEYS.modal);
        if (!modalKey) return;
        const rawPreservedState = sessionStorage.getItem(STORAGE_KEYS.modalState);
        const preservedState = rawPreservedState ? JSON.parse(rawPreservedState) : null;
        if (modalKey === 'procsets:detailModal') {
            const rawContext = sessionStorage.getItem(STORAGE_KEYS.dealModalContext);
            if (rawContext && adminActions.viewDeal) {
                const context = JSON.parse(rawContext);
                await adminActions.viewDeal(context.dealId, context.taskId ?? null);
                const modal = document.querySelector('#procsets-tab #detailModal');
                if (modal) applyAdminModalState(modal, preservedState);
                return;
            }
        }
        if (modalKey === 'admin:detailModal') {
            const rawContext = sessionStorage.getItem(STORAGE_KEYS.employeeModalContext);
            if (rawContext && adminActions.showEmployeeDetail) {
                const context = JSON.parse(rawContext);
                await adminActions.showEmployeeDetail(context.employeeId, context.date);
                const modal = document.querySelector('body > #detailModal') || document.getElementById('detailModal');
                if (modal) applyAdminModalState(modal, preservedState);
                return;
            }
        }
        const [scope, modalId] = modalKey.split(':');
        const selector = scope === 'procsets' ? `#procsets-tab #${modalId}` : `body > #${modalId}`;
        const modal = document.querySelector(selector) || document.getElementById(modalId);
        if (modal) {
            applyAdminModalState(modal, preservedState);
            modal.style.display = 'block';
            setTimeout(() => applyAdminModalState(modal, preservedState), 300);
        }
    }
    export function getLocalDate() {
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    export function formatDateLocal(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    export function loadReportForDate(date) {
        if (!date) return;
        if (adminState.dailyTrafficModeActive) {
            adminActions.loadDailyTraffic?.(date);
        } else {
            adminActions.loadDailyReport?.(date);
        }
        // Синхронизируем видимость фильтра после загрузки
        adminActions.updateFilterVisibility?.();
    }
    export async function loadAdminName() {
        try {
            const resp = await fetch('/api/auth/profile', { credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                const nameSpan = document.getElementById('adminNameLink');
                if (nameSpan && data.full_name) {
                    nameSpan.textContent = data.full_name + ' (Личный Кабинет)';
                    nameSpan.onclick = () => {
                        if (adminState.eventSource) adminState.eventSource.close();
                        window.location.href = '/static/employee.html/';
                    };
                }
            }
        } catch (err) {
            console.warn('Не удалось загрузить имя админа');
        }
    }

    export async function checkAdmin() {
        try {
            const resp = await fetch('/api/auth/profile', { credentials: 'include' });
            if (!resp.ok) throw new Error();
            const data = await resp.json();
            if (!data.is_admin) {
                window.location.replace('/static/login.html');
            } else {
                loadAdminName();
            }
        } catch (err) {
            window.location.replace('/static/login.html');
        }
    }
    checkAdmin();
    export function showToast(msg, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = msg;
        toast.style.background = isError ? '#dc2626' : '#10b981';
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 2500);
    }
