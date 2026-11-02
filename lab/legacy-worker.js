/* Test-only fault injection: local WASM import is unavailable. */
const originalImport = importScripts;
self.importScripts = (...urls) => {
    if (urls.some(url => url.includes('/zxing-wasm-'))) throw Error('Synthetic WASM load failure');
    return originalImport(...urls);
};
originalImport('/static/camera-decoder-worker.js?v=1.1.0&build=20261102b');
