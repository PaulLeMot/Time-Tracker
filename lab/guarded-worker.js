/* Test-only: fail if a frame is uploaded, external assets are requested or OCR
   touches IndexedDB. Successful real decoding under this guard is evidence. */
const originalFetch = fetch, originalImport = importScripts;
const local = value => { const url = new URL(value, self.location.href);
    if (url.href.startsWith('data:application/octet-stream;base64,')) return url.href; // Embedded core WASM, no network.
    if (url.origin !== self.location.origin) throw Error('External worker resource forbidden: ' + url.href.slice(0, 100)); return url.href; };
self.fetch = (input, options = {}) => {
    const request = input instanceof Request ? input : null;
    if ((options.method || request?.method || 'GET') !== 'GET' || options.body || request?.body) throw Error('Worker upload forbidden');
    return originalFetch(local(request?.url || input), options);
};
self.importScripts = (...urls) => originalImport(...urls.map(local));
Object.defineProperty(self, 'indexedDB', {get() { throw Error('IndexedDB forbidden by synthetic test'); }});
originalImport(new URLSearchParams(location.search).get('kind') === 'ocr'
    ? '/static/vendor/tesseract-6.0.1/worker.min.js' : '/static/camera-decoder-worker.js?v=1.1.0&build=20261102b');
