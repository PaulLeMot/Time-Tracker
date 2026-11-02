'use strict';
document.getElementById('run').onclick = async function () {
    this.disabled = true;
    const output = document.getElementById('result'), results = [];
    const BrowserWorker = window.Worker;
    window.Worker = function (url) {
        const kind = String(url).includes('camera-decoder-worker') ? 'barcode' : 'ocr';
        const worker = new BrowserWorker('/lab/guarded-worker.js?v=2&kind=' + kind);
        worker.addEventListener('message', ({data}) => { if (data.status === 'reject') results.push({guardReject: String(data.data)}); });
        return worker;
    };
    let engine; const controller = new AbortController();
    try {
        const start = performance.now();
        engine = await TTCameraEngine.createText(controller.signal);
        results.push({initMs: performance.now() - start, engine: engine.information}); output.textContent = JSON.stringify(results);
        const image = new Image(); image.src = '/lab/labels/article.png'; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        canvas.getContext('2d').drawImage(image, 0, 0);
        const before = performance.now(), result = await engine.decode(canvas);
        results.push({...result, tokens: TTCodeSearch.textTokens(result.text), decodeMs: performance.now() - before});
        engine.dispose();
        const barcodeStart = performance.now(); engine = await TTCameraEngine.createBarcode(controller.signal);
        results.push({barcodeInitMs: performance.now() - barcodeStart, information: engine.information});
        const hints = new Map([[ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.CODE_128]],
            [ZXing.DecodeHintType.TRY_HARDER, true]]);
        const reader = new ZXing.MultiFormatOneDReader(hints);
        for (const name of ['ean', 'code128', 'ozon', 'vertical', 'tilt', 'faint', 'small', 'multiple', 'blank']) {
            image.src = '/lab/labels/' + name + '.png'; await image.decode();
            canvas.width = image.width; canvas.height = image.height; canvas.getContext('2d').drawImage(image, 0, 0);
            const samples = [], oldSamples = []; let decoded, oldValue;
            for (let i = 0; i < 5; i++) {
                const now = performance.now(); decoded = await engine.decode(canvas, {harder: true}); samples.push(performance.now() - now);
                const oldNow = performance.now();
                try { oldValue = reader.decode(new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(new ZXing.HTMLCanvasElementLuminanceSource(canvas))), hints).getText(); }
                catch (_) { oldValue = null; }
                oldSamples.push(performance.now() - oldNow);
            }
            results.push({image: name, decoded, oldValue, workerMs: samples, oldMainThreadMs: oldSamples});
            output.textContent = JSON.stringify(results, null, 2);
        }
        // Both real OCR and barcode initialization must be immediately cancellable.
        for (const mode of ['createText', 'createBarcode']) {
            const abort = new AbortController(), loading = TTCameraEngine[mode](abort.signal); abort.abort();
            try { await loading; throw Error('Cancellation ignored'); }
            catch (error) { if (error.name !== 'AbortError') throw error; results.push({cancel: mode, pass: true}); }
        }
        engine.dispose();
        const OriginalWorker = window.Worker;
        try {
            window.Worker = function (url) { return new BrowserWorker(String(url).includes('camera-decoder-worker') ? '/lab/legacy-worker.js' : url); };
            engine = await TTCameraEngine.createBarcode(controller.signal);
            for (const name of ['ean', 'vertical', 'ozon']) {
                image.src = '/lab/labels/' + name + '.png'; await image.decode();
                canvas.width = image.width; canvas.height = image.height; canvas.getContext('2d').drawImage(image, 0, 0);
                const value = await engine.decode(canvas);
                if (!value.value) throw Error('Legacy fallback failed: ' + name);
                results.push({fallback: name, engine: engine.information, value: value.value});
            }
        } finally { window.Worker = OriginalWorker; }
        const resources = performance.getEntriesByType('resource').map(entry => entry.name);
        results.push({externalPageResources: resources.filter(url => !url.startsWith(location.origin + '/')),
            guardedWorkers: 'real OCR+WASM successful with external fetch, uploads and IndexedDB forbidden'});
    } catch (error) { results.push({error: error.message, stack: error.stack}); }
    finally { controller.abort(); engine?.dispose(); window.Worker = BrowserWorker; output.textContent = JSON.stringify(results, null, 2); this.disabled = false; }
};
