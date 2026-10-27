/**
 * Связи между разделами админки.
 * Реальные обработчики регистрирует main.js после загрузки всех модулей.
 */
const handlers = Object.create(null);

export function registerAdminFeatureActions(actions) {
    Object.assign(handlers, actions);
}

function call(name, args) {
    const handler = handlers[name];
    if (!handler) {
        console.warn(`Обработчик админки не зарегистрирован: ${name}`);
        return undefined;
    }
    return handler(...args);
}

export const insertScheduleRow = (...args) => call('insertScheduleRow', args);
export const openEditUsernameModal = (...args) => call('openEditUsernameModal', args);
export const openEditFullnameModal = (...args) => call('openEditFullnameModal', args);
export const openEditPasswordModal = (...args) => call('openEditPasswordModal', args);
export const refreshCurrentReport = (...args) => call('refreshCurrentReport', args);
export const openRoleModal = (...args) => call('openRoleModal', args);
export const loadEmployees = (...args) => call('loadEmployees', args);
export const loadEmployeeListForFilter = (...args) => call('loadEmployeeListForFilter', args);
export const loadRecentEmployeeFilter = (...args) => call('loadRecentEmployeeFilter', args);
export const loadNotifications = (...args) => call('loadNotifications', args);
export const updateDraftBadge = (...args) => call('updateDraftBadge', args);
export const loadEmployeesForSelect = (...args) => call('loadEmployeesForSelect', args);
export const initMonthlyTab = (...args) => call('initMonthlyTab', args);
export const updateFilterVisibility = (...args) => call('updateFilterVisibility', args);
export const restoreTabState = (...args) => call('restoreTabState', args);
export const restoreTrafficState = (...args) => call('restoreTrafficState', args);
export const loadTrafficEmployees = (...args) => call('loadTrafficEmployees', args);
export const loadWeeklyTraffic = (...args) => call('loadWeeklyTraffic', args);
export const saveTrafficState = (...args) => call('saveTrafficState', args);
export const saveTabState = (...args) => call('saveTabState', args);
export const initProcsetsTab = (...args) => call('initProcsetsTab', args);
export const loadRecentEntries = (...args) => call('loadRecentEntries', args);
export const renderCurrentRoles = (...args) => call('renderCurrentRoles', args);
export const closeRoleModal = (...args) => call('closeRoleModal', args);
