export const STORAGE_KEYS = Object.freeze({
    tab: 'admin_active_tab',
    trafficMode: 'admin_traffic_mode',
    trafficEmployee: 'admin_traffic_employee',
    trafficWeek: 'admin_traffic_week',
    processTab: 'admin_procsets_active_tab',
    scroll: 'admin_scroll_position',
    modal: 'admin_open_modal',
    modalState: 'admin_open_modal_state',
    dealModalContext: 'admin_deal_modal_context',
    employeeModalContext: 'admin_employee_modal_context'
});

export const adminState = {
    eventSource: null,
    notificationStartDate: '',
    notificationEndDate: '',
    recentStartDate: '',
    recentEndDate: '',
    recentEmployeeId: '',
    currentlyEditingId: null,
    trafficModeActive: false,
    dailyReportData: null,
    dailyCurrentlyEditingId: null,
    dailyCurrentlyAddingCell: null,
    periodStartDate: null,
    periodEndDate: null,
    selectedEmployeeId: '',
    periodTrafficModeActive: false,
    dailyTrafficModeActive: false,
    currentEmployeeIdForRole: null,
    currentEditEntryId: null,
    currentEditId: null,
    currentEditNotificationId: null,
    currentEditProposedNotifId: null,
    isFilterEnabled: localStorage.getItem('statusFilterEnabled') === 'true',
    roleElements: {}
};

export const TRAFFIC_ACTIONS = Object.freeze(['start', 'break_start', 'break_end', 'end']);

export const TRAFFIC_LABELS = Object.freeze({
    start: 'Начало дня',
    break_start: 'Начало перерыва',
    break_end: 'Конец перерыва',
    end: 'Конец дня'
});
