let taskListLoader = null;

export function registerTaskListLoader(loader) {
    taskListLoader = loader;
}

export async function loadMailingNotifications() {
    if (!taskListLoader) return;
    return taskListLoader();
}
