import {
    observeEmployeeModals,
    registerCompletionModalOpener,
    restoreEmployeeModal,
    restoreEmployeeScrollPosition
} from './core.js';
import { configureAttendanceActions, initTabs, refreshState } from './attendance.js';
import { loadMonitorReport, connectMonitorSSE, registerNotificationModalOpener } from './monitor.js';
import {
    connectEmployeeSSE,
    loadAllNotifications,
    loadEmployeesForAllNotif,
    loadNotifications,
    openNotificationModal,
    registerTaskListLoader
} from './notifications.js';
import { initTaskFilters, loadTaskNotifications, openCompletionModal } from './tasks.js';

registerCompletionModalOpener(openCompletionModal);
registerNotificationModalOpener(openNotificationModal);
registerTaskListLoader(loadTaskNotifications);
configureAttendanceActions({
    connectMonitorSSE,
    loadMonitorReport,
    loadNotifications,
    loadAllNotifications,
    loadTaskNotifications
});

document.addEventListener('DOMContentLoaded', async () => {
    initTabs();
    initTaskFilters();
    observeEmployeeModals();
    await refreshState();
    await loadEmployeesForAllNotif();
    await restoreEmployeeModal();
    restoreEmployeeScrollPosition();
    setTimeout(connectEmployeeSSE, 2000);

    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab;
            if (activeTab === 'monitor') {
                const monitorDate = document.getElementById('monitorDate').value;
                if (monitorDate) loadMonitorReport(monitorDate);
            } else if (activeTab === 'notifications') {
                loadNotifications();
            } else if (activeTab === 'all-notifications') {
                loadAllNotifications();
            }
        }, 250);
    });

    const toggleBtn = document.getElementById('drawerToggle');
    const mainLayout = document.querySelector('.main-layout');
    if (toggleBtn && mainLayout) {
        toggleBtn.textContent = mainLayout.classList.contains('drawer-closed') ? '☰' : '✕';
        toggleBtn.addEventListener('click', function() {
            mainLayout.classList.toggle('drawer-closed');
            this.textContent = mainLayout.classList.contains('drawer-closed') ? '☰' : '✕';
        });
    }
});
