/* Own workers, bounded jobs, immediate cancellation including OCR initialization. */
(function (root) {
    'use strict';
    const abortError = () => new DOMException('Сканирование отменено', 'AbortError');
    function rpcWorker(path, signal, protocol = 'camera') {
        if (signal?.aborted) throw abortError();
        const worker = new Worker(path), pending = new Map();
        let id = 0, closed = false;
        function dispose(reason) {
            if (closed) return;
            const error = reason instanceof Error || reason instanceof DOMException ? reason : abortError();
            closed = true; signal?.removeEventListener('abort', dispose); worker.terminate();
            for (const entry of pending.values()) { clearTimeout(entry.timer); entry.reject(error); }
            pending.clear();
        }
        signal?.addEventListener('abort', dispose, {once: true});
        worker.onmessage = ({data}) => {
            const key = protocol === 'tesseract' ? data.jobId : data.id;
            const entry = pending.get(key);
            if (!entry || data.status === 'progress') return;
            clearTimeout(entry.timer); pending.delete(key);
            if (data.error || data.status === 'reject') entry.reject(Error(protocol));
            else entry.resolve(protocol === 'tesseract' ? data.data : data.result);
        };
        worker.onerror = event => { event.preventDefault(); dispose(Error('worker')); };
        return {dispose, request(action, payload = {}, transfer = [], timeout = 12000) {
            if (closed) return Promise.reject(abortError());
            const key = ++id;
            return new Promise((resolve, reject) => {
                const timer = setTimeout(() => { pending.delete(key); reject(Error('worker_timeout')); dispose(); }, timeout);
                pending.set(key, {resolve, reject, timer});
                try { worker.postMessage(protocol === 'tesseract'
                    ? {workerId: 'tt-label', jobId: key, action, payload} : {id: key, action, ...payload}, transfer); }
                catch (error) { pending.delete(key); clearTimeout(timer); reject(error); dispose(); }
            });
        }};
    }
    async function createBarcode(signal) {
        const client = rpcWorker('/static/camera-decoder-worker.js?v=1.1.0&build=20261102b', signal);
        try {
            const information = await client.request('init', {}, [], 18000);
            return {information, dispose: client.dispose, async decode(canvas, options = {}) {
                const image = canvas.getContext('2d', {willReadFrequently: true}).getImageData(0, 0, canvas.width, canvas.height);
                return client.request('decode', {width: image.width, height: image.height, buffer: image.data.buffer,
                    harder: !!options.harder}, [image.data.buffer], 3000);
            }};
        } catch (error) { client.dispose(); throw error; }
    }
    async function createText(signal) {
        // This small adapter deliberately pins the official worker message protocol
        // from6.0.1. Owning the Worker before initialization lets cancel terminate it
        // immediately; createWorker's public promise exposes it only after loading.
        const client = rpcWorker('/static/vendor/tesseract-6.0.1/worker.min.js', signal, 'tesseract');
        try {
            await client.request('load', {options: {lstmOnly: true, corePath: '/static/vendor/tesseract-core-6.1.2', logging: false}}, [], 30000);
            await client.request('loadLanguage', {langs: 'eng', options: {langPath: '/static/vendor/tesseract-eng-1.0.0',
                cacheMethod: 'none', gzip: true, lstmOnly: true}}, [], 30000);
            await client.request('initialize', {langs: 'eng', oem: 1, config: {load_system_dawg: '0', load_freq_dawg: '0'}}, [], 15000);
            // Whitelisting letters/digits joins words and makes LSTM confidence0
            // even on clean labels. Keep normal segmentation, then parse bounded
            // article tokens in TTCodeSearch without guessing O/0 substitutions.
            await client.request('setParameters', {params: {tessedit_pageseg_mode: '11', preserve_interword_spaces: '1'}});
            return {information: {engine: 'tesseract-lstm-local'}, dispose: client.dispose, async decode(canvas) {
                if (signal?.aborted) throw abortError();
                // PNG bytes exist only in memory, are sent solely to our own worker,
                // and are never given to fetch, browser storage or a file/download.
                const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
                if (!blob || signal?.aborted) throw abortError();
                const buffer = await blob.arrayBuffer();
                if (signal?.aborted) throw abortError();
                const data = await client.request('recognize', {image: new Uint8Array(buffer), options: {}, output: {text: true}}, [buffer], 8000);
                return {text: String(data.text || '').slice(0, 1500), confidence: Number(data.confidence) || 0};
            }};
        } catch (error) { client.dispose(); throw error; }
    }
    root.TTCameraEngine = {createBarcode, createText};
})(window);
