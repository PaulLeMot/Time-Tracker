export const EMPLOYEE_STORAGE_KEYS = Object.freeze({
    tab: 'employee_active_tab',
    modal: 'employee_open_modal',
    modalState: 'employee_open_modal_state',
    completion: 'employee_completion_context',
    scroll: 'employee_scroll_position'
});

export const employeeState = {
    employeeId: null,
    isAdmin: false,
    canCreateTasks: false,
    monitorSseActive: false,
    isEditingCompletion: false,
    currentFixNotificationId: null,
    currentNotificationId: null,
    currentNotifyEmployeeId: null,
    currentEditNotificationId: null,
    completionSaving: false,
    completion: {
        notificationId: null,
        dealId: null,
        taskId: null,
        independentTaskId: null,
        productTypes: [],
        assignees: [],
        distributions: {},
        percentages: {},
        totalPoints: 0,
        generalComment: ''
    }
};
