import { registerAdminActions } from './core.js';
import { registerAdminFeatureActions } from './actions.js';
import { loadEmployees } from './employees.js';
import {
    insertScheduleRow, loadDailyReport, loadRecentEntries, openEditFullnameModal,
    openEditPasswordModal, openEditUsernameModal, refreshCurrentReport,
    showEmployeeDetail
} from './reports.js';
import {
    closeRoleModal, loadEmployeeListForFilter, loadEmployeesForSelect,
    loadNotifications, loadRecentEmployeeFilter, openRoleModal, updateDraftBadge
} from './notifications.js';
import {
    initMonthlyTab, loadDailyTraffic, loadTrafficEmployees, loadWeeklyTraffic,
    renderCurrentRoles, restoreTabState, restoreTrafficState, saveTabState,
    saveTrafficState, updateFilterVisibility
} from './traffic-light.js';
import { viewDeal } from './deals.js';
import './mailing.js';
import './independent-task-editor.js';
import './task-list.js';
import { initProcsetsTab } from './process-settings.js';
import './tasks.js';

registerAdminFeatureActions({
    insertScheduleRow,
    openEditUsernameModal,
    openEditFullnameModal,
    openEditPasswordModal,
    refreshCurrentReport,
    openRoleModal,
    loadEmployees,
    loadEmployeeListForFilter,
    loadRecentEmployeeFilter,
    loadNotifications,
    updateDraftBadge,
    loadEmployeesForSelect,
    initMonthlyTab,
    updateFilterVisibility,
    restoreTabState,
    restoreTrafficState,
    loadTrafficEmployees,
    loadWeeklyTraffic,
    saveTrafficState,
    saveTabState,
    initProcsetsTab,
    loadRecentEntries,
    renderCurrentRoles,
    closeRoleModal
});

registerAdminActions({
    viewDeal,
    showEmployeeDetail,
    loadDailyReport,
    loadDailyTraffic,
    updateFilterVisibility
});
