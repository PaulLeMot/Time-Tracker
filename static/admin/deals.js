let dealViewer = null;

export function registerDealViewer(viewer) {
    dealViewer = viewer;
}

export async function viewDeal(dealId, taskId = null) {
    if (!dealViewer) return;
    return dealViewer(dealId, taskId);
}
