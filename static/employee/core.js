import { employeeState, EMPLOYEE_STORAGE_KEYS } from './state.js';

let completionModalOpener = null;

export function registerCompletionModalOpener(opener) {
    completionModalOpener = opener;
}

let employeeScrollSaveTimer = null;

    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

    export function saveEmployeeScrollPosition() {
        sessionStorage.setItem(EMPLOYEE_STORAGE_KEYS.scroll, String(window.scrollY));
    }

    export function restoreEmployeeScrollPosition() {
        const rawPosition = sessionStorage.getItem(EMPLOYEE_STORAGE_KEYS.scroll);
        if (rawPosition === null) return;
        const savedPosition = Number(rawPosition);
        if (!Number.isFinite(savedPosition)) return;
        [0, 150, 500, 1200].forEach(delay => {
            setTimeout(() => window.scrollTo(0, savedPosition), delay);
        });
    }

    window.addEventListener('scroll', () => {
        clearTimeout(employeeScrollSaveTimer);
        employeeScrollSaveTimer = setTimeout(saveEmployeeScrollPosition, 100);
    }, { passive: true });
    window.addEventListener('pagehide', saveEmployeeScrollPosition);

    export function captureEmployeeModalState(modal) {
        const fields = Array.from(modal.querySelectorAll('input, select, textarea')).map((field, index) => ({
            key: field.id || field.name || String(index),
            value: field.value,
            checked: field.checked,
            type: field.type
        }));
        const labels = Array.from(modal.querySelectorAll('[id]'))
            .filter(element => !element.matches('input, select, textarea') && element.children.length === 0)
            .map(element => ({ id: element.id, text: element.textContent }));
        sessionStorage.setItem(EMPLOYEE_STORAGE_KEYS.modalState, JSON.stringify({ modalId: modal.id, fields, labels, dataset: { ...modal.dataset } }));
    }

    export function applyEmployeeModalState(modal, preservedState = null) {
        const rawState = sessionStorage.getItem(EMPLOYEE_STORAGE_KEYS.modalState);
        if (!preservedState && !rawState) return;
        const state = preservedState || JSON.parse(rawState);
        if (state.modalId !== modal.id) return;
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
        if (modal.id === 'explanationModal' && entityId) employeeState.currentNotificationId = entityId;
        if (modal.id === 'createNotificationModal' && entityId) employeeState.currentNotifyEmployeeId = entityId;
        if (modal.id === 'fixEndTimeModal' && entityId) employeeState.currentFixNotificationId = entityId;
        captureEmployeeModalState(modal);
    }

    export function observeEmployeeModals() {
        const updateState = modal => {
            if (!modal.id) return;
            if (getComputedStyle(modal).display !== 'none') {
                sessionStorage.setItem(EMPLOYEE_STORAGE_KEYS.modal, modal.id);
                captureEmployeeModalState(modal);
            } else if (sessionStorage.getItem(EMPLOYEE_STORAGE_KEYS.modal) === modal.id) {
                sessionStorage.removeItem(EMPLOYEE_STORAGE_KEYS.modal);
                sessionStorage.removeItem(EMPLOYEE_STORAGE_KEYS.modalState);
                if (modal.id === 'completeTaskModal') sessionStorage.removeItem(EMPLOYEE_STORAGE_KEYS.completion);
            }
        };
        document.querySelectorAll('.modal[id]').forEach(modal => {
            new MutationObserver(() => updateState(modal)).observe(modal, { attributes: true, attributeFilter: ['style', 'class'] });
            modal.addEventListener('input', () => captureEmployeeModalState(modal));
            modal.addEventListener('change', () => captureEmployeeModalState(modal));
        });
    }

    window.addEventListener('pagehide', () => {
        document.querySelectorAll('.modal[id]').forEach(modal => {
            if (getComputedStyle(modal).display !== 'none') captureEmployeeModalState(modal);
        });
    });

    export async function restoreEmployeeModal() {
        const modalId = sessionStorage.getItem(EMPLOYEE_STORAGE_KEYS.modal);
        if (!modalId) return;
        const rawPreservedState = sessionStorage.getItem(EMPLOYEE_STORAGE_KEYS.modalState);
        const preservedState = rawPreservedState ? JSON.parse(rawPreservedState) : null;
        if (modalId === 'completeTaskModal') {
            const rawContext = sessionStorage.getItem(EMPLOYEE_STORAGE_KEYS.completion);
            if (rawContext) {
                const context = JSON.parse(rawContext);
                employeeState.isEditingCompletion = Boolean(context.isEditing);
                if (!completionModalOpener) return;
                await completionModalOpener(context.dealId, context.taskId, context.notificationId, context.products || [], context.generalComment || '', context.independentTaskId || null);
                applyEmployeeModalState(document.getElementById('completeTaskModal'), preservedState);
                return;
            }
        }
        const modal = document.getElementById(modalId);
        if (modal) {
            applyEmployeeModalState(modal, preservedState);
            modal.style.display = 'block';
            setTimeout(() => applyEmployeeModalState(modal, preservedState), 300);
        }
    }
    // ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
    export function getLocalDate() {
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }
    export function formatDateTime(isoString) {
        if (!isoString) return '—';
        let str = isoString.slice(0, 19).replace('T', ' ');
        const [datePart, timePart] = str.split(' ');
        if (!datePart || !timePart) return str;
        const [year, month, day] = datePart.split('-');
        const [hours, minutes] = timePart.split(':');
        return `${day}-${month}-${year} ${hours}:${minutes}`;
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
    export function formatTaskDuration(seconds) {
        if (seconds === undefined || seconds === null) return '';
        const totalMinutes = Math.max(0, Math.floor(seconds / 60));
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
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
    export function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.style.background = isError ? '#dc2626' : '#10b981';
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 2500);
    }

    // ========== API ==========
    export async function fetchWithAuth(url, options = {}) {
        const resp = await fetch(url, { ...options, credentials: 'include', cache: 'no-cache'});
        if (resp.status === 401) {
            window.location.replace('/static/login.html');
            throw new Error('Unauthorized');
        }
        return resp;
    }
