/* TimeTracker camera1.1.1: rear-only, bounded asynchronous decoding, RAM-only frames. */
(function (root) {
    'use strict';
    const VERSION = '1.1.1';
    let enginePromise, activeScanner, preferredRear = '';
    function loadEngine() {
        if (root.TTCameraEngine) return Promise.resolve(root.TTCameraEngine);
        if (!enginePromise) enginePromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            const timer = setTimeout(() => finish(false), 15000);
            function finish(ok) {
                clearTimeout(timer); script.onload = script.onerror = null;
                if (ok && root.TTCameraEngine) resolve(root.TTCameraEngine);
                else { script.remove(); reject(Error('decoder')); }
            }
            script.src = '/static/camera-engine.js?v=1.1.0&build=20261102b';
            script.onload = () => finish(true); script.onerror = () => finish(false); document.head.append(script);
        }).catch(error => { enginePromise = null; throw error; });
        return enginePromise;
    }
    const messages = {
        NotAllowedError: 'Доступ к камере запрещён. Разрешите его в настройках браузера или введите код вручную.',
        NotFoundError: 'Задняя камера не найдена. Введите код вручную.',
        NotReadableError: 'Камера занята или недоступна. Закройте другое приложение с камерой и повторите.',
        OverconstrainedError: 'Не удалось выбрать заднюю камеру. Попробуйте другой браузер или введите код вручную.',
        SecurityError: 'Браузер запрещает доступ к камере. Откройте портал по защищённому адресу.'
    };
    function create(deps = {}) {
        const media = deps.mediaDevices || navigator.mediaDevices;
        const getDecoder = deps.getDecoder || (async (signal, mode) => {
            const engine = await loadEngine();
            if (signal.aborted) throw new DOMException('Отменено', 'AbortError');
            return mode === 'text' ? engine.createText(signal) : engine.createBarcode(signal);
        });
        let generation = 0, session = null, disposed = false, lastMode = 'barcode', lastMetrics = null;
        const stopStream = stream => stream?.getTracks().forEach(track => track.stop());
        function current(s) { return !disposed && session === s && s.id === generation; }
        function release(s) {
            clearTimeout(s.timer); clearTimeout(s.timeout); clearTimeout(s.focusTimer);
            if (s.frameCallback != null) s.video.cancelVideoFrameCallback?.(s.frameCallback);
            s.frameCallback = null; s.abort.abort();
            s.streamListeners.forEach(remove => remove()); s.streamListeners = [];
            stopStream(s.stream); s.stream = null;
            s.video.pause(); s.video.srcObject = null;
            s.decoder?.dispose(); s.decoder = null;
            s.canvas.width = s.canvas.height = 0;
        }
        function close(reason = 'cancel') {
            const s = session; if (!s) return;
            session = null; generation++; release(s);
            s.removeListeners.forEach(remove => remove());
            if (s.dialog.open) s.dialog.close(); s.dialog.remove();
            if (activeScanner === api) activeScanner = null;
            if (!['pagehide', 'hidden', 'mode', 'camera'].includes(reason) && s.options.returnFocusTo?.isConnected)
                s.options.returnFocusTo.focus({preventScroll: true});
            s.options.onClose?.(reason);
        }
        function fail(s, message) {
            if (!current(s) || s.state === 'error') return;
            s.state = 'error'; release(s);
            s.dialog.classList.add('tt-camera-error');
            s.video.hidden = true; s.frame.hidden = true; s.controls.hidden = true;
            s.status.textContent = message; s.retry.hidden = false; s.options.onError?.(message);
        }
        function status(s, message) {
            if (current(s) && s.status.textContent !== message) s.status.textContent = message;
        }
        async function adjust(s, constraints) {
            if (!current(s) || !s.track?.applyConstraints) return false;
            try {
                let timer;
                try { await Promise.race([s.track.applyConstraints(constraints), new Promise((_, reject) => {
                    timer = setTimeout(() => reject(Error('settings_timeout')), 600);
                })]); } finally { clearTimeout(timer); }
                return current(s) && s.state !== 'error';
            } catch (_) { return false; }
        }
        async function configure(s) {
            let caps = {}, settings = {};
            try { caps = s.track.getCapabilities?.() || {}; settings = s.track.getSettings?.() || {}; } catch (_) { /* Basic rear capture remains usable. */ }
            if (settings.facingMode === 'user' || settings.facingMode === 'left' || settings.facingMode === 'right')
                throw Object.assign(Error('rear_only'), {name: 'OverconstrainedError'});
            if (settings.deviceId) preferredRear = settings.deviceId;
            s.caps = caps;
            if (caps.focusMode?.includes('continuous')) await adjust(s, {advanced: [{focusMode: 'continuous'}]});
            if (!current(s) || s.state === 'error') return;
            const torch = s.dialog.querySelector('.tt-camera-torch');
            torch.hidden = !caps.torch;
            torch.onclick = async () => {
                if (torch.disabled) return;
                torch.disabled = true;
                const ok = await adjust(s, {advanced: [{torch: !s.torch}]});
                if (ok) { s.torch = !s.torch; torch.setAttribute('aria-pressed', String(s.torch)); torch.textContent = s.torch ? 'Выключить свет' : 'Подсветка'; }
                else if (current(s)) status(s, 'Не удалось переключить подсветку. Продолжайте сканирование.');
                torch.disabled = false;
            };
            const zoom = s.dialog.querySelector('.tt-camera-zoom');
            const range = zoom.querySelector('input');
            if (caps.zoom && Number.isFinite(caps.zoom.max) && caps.zoom.max > caps.zoom.min) {
                zoom.hidden = false; range.min = caps.zoom.min; range.max = Math.min(caps.zoom.max, Math.max(3, caps.zoom.min));
                range.step = caps.zoom.step || .1; range.value = settings.zoom || caps.zoom.min;
                range.onchange = async () => {
                    range.disabled = true; const ok = await adjust(s, {advanced: [{zoom: Number(range.value)}]});
                    if (!ok && current(s)) status(s, 'Изменение масштаба недоступно. Попробуйте изменить расстояние.');
                    range.disabled = false;
                };
            }
            const switching = s.dialog.querySelector('.tt-camera-switch');
            if (media.enumerateDevices) {
                try {
                    const devices = await media.enumerateDevices();
                    if (!current(s) || s.state === 'error') return;
                    // Never offer unclassified or front-facing devices. Labels are available only after permission.
                    const rear = devices.filter(d => d.kind === 'videoinput' && d.deviceId &&
                        /back|rear|environment|задн|основн|rück|arrière|trasera|traseira|posteriore/i.test(d.label) &&
                        !/front|user|передн|фронт/i.test(d.label));
                    switching.hidden = rear.length < 2;
                    switching.onclick = () => {
                        const index = rear.findIndex(d => d.deviceId === preferredRear);
                        preferredRear = rear[(index + 1) % rear.length].deviceId;
                        const options = s.options; close('camera'); open(options);
                    };
                } catch (_) { /* Exact environment constraint still selects only a rear camera. */ }
            }
            const canPoint = media.getSupportedConstraints?.().pointsOfInterest && caps.focusMode?.includes('single-shot');
            if (canPoint) s.video.onclick = async event => {
                const rect = s.video.getBoundingClientRect();
                const ratio = Math.min(rect.width / s.video.videoWidth, rect.height / s.video.videoHeight);
                const width = s.video.videoWidth * ratio, height = s.video.videoHeight * ratio;
                if (!width || !height) return;
                const left = rect.left + (rect.width - width) / 2, top = rect.top + (rect.height - height) / 2;
                const x = Math.max(0, Math.min(1, (event.clientX - left) / width));
                const y = Math.max(0, Math.min(1, (event.clientY - top) / height));
                await adjust(s, {advanced: [{focusMode: 'single-shot', pointsOfInterest: [{x, y}]}]});
                if (!current(s) || s.state === 'error') return;
                clearTimeout(s.focusTimer);
                s.focusTimer = setTimeout(() => { if (caps.focusMode.includes('continuous')) adjust(s, {advanced: [{focusMode: 'continuous'}]}); }, 700);
            };
        }
        function frame(s, full) {
            const vw = s.video.videoWidth, vh = s.video.videoHeight;
            if (!vw || !vh) return false;
            let x = 0, y = 0, width = vw, height = vh;
            if (!full) {
                const box = s.video.getBoundingClientRect(), target = s.frame.getBoundingClientRect();
                const ratio = Math.min(box.width / vw, box.height / vh);
                if (ratio > 0) {
                    const left = box.left + (box.width - vw * ratio) / 2, top = box.top + (box.height - vh * ratio) / 2;
                    x = Math.max(0, Math.floor((target.left - left) / ratio));
                    y = Math.max(0, Math.floor((target.top - top) / ratio));
                    width = Math.min(vw - x, Math.ceil(target.width / ratio));
                    height = Math.min(vh - y, Math.ceil(target.height / ratio));
                    if (width < 16 || height < 16) { x = y = 0; width = vw; height = vh; }
                }
            }
            const maxWidth = s.mode === 'text' ? 1600 : (s.frames % 6 === 5 ? 1920 : 1440);
            const scale = Math.min(1, maxWidth / width, 1200 / height);
            const w = Math.max(1, Math.round(width * scale)), h = Math.max(1, Math.round(height * scale));
            if (s.canvas.width !== w) s.canvas.width = w;
            if (s.canvas.height !== h) s.canvas.height = h;
            s.canvas.getContext('2d', {willReadFrequently: true}).drawImage(s.video, x, y, width, height, 0, 0, w, h);
            return true;
        }
        function schedule(s, delay) {
            if (!current(s) || s.state !== 'scanning') return;
            s.timer = setTimeout(() => {
                if (!current(s) || s.state !== 'scanning') return;
                const realFrames = s.video.getVideoPlaybackQuality?.().totalVideoFrames;
                if (s.video.requestVideoFrameCallback && realFrames > 0) s.frameCallback = s.video.requestVideoFrameCallback(() => { s.frameCallback = null; tick(s); });
                else tick(s);
            }, delay);
        }
        async function tick(s) {
            if (!current(s) || s.state !== 'scanning') return;
            const started = performance.now();
            try {
                if (s.video.readyState >= 2 && frame(s, s.frames % 4 === 3)) {
                    const result = await s.decoder.decode(s.canvas, {harder: s.frames % 3 === 2});
                    if (!current(s) || s.state !== 'scanning') return;
                    s.frames++;
                    let value = result?.value || (result?.rawValue ? result : null);
                    if (s.mode === 'text') {
                        const text = String(result?.text || '').slice(0, 1500);
                        const tokens = root.TTCodeSearch?.textTokens(text) || [];
                        const stable = result?.confidence >= 35 ? tokens.filter(t => s.previousTokens?.includes(t)) : [];
                        s.previousTokens = result?.confidence >= 35 ? tokens : [];
                        if (result?.confidence >= 35 && stable.length) value = {rawValue: text, format: 'OCR_TEXT'};
                        else status(s, tokens.length ? 'Артикул виден. Подержите этикетку неподвижно…' : 'Наведите рамку на артикул среди текста этикетки');
                    }
                    if (value) {
                        lastMetrics = {version: VERSION, mode: s.mode, frames: s.frames, engine: s.decoder.information?.engine,
                            sinceVideoMs: performance.now() - s.scanningAt, lastDecodeMs: performance.now() - started};
                        close('decoded');
                        Promise.resolve(s.options.onDecoded(value)).catch(() => s.options.onError?.('Не удалось выполнить поиск. Повторите ввод.'));
                        return;
                    }
                    if (s.mode === 'barcode' && performance.now() - s.lastHint > 800) {
                        s.lastHint = performance.now();
                        status(s, result?.ambiguous ? 'В кадре несколько штрихкодов. Наведите рамку на один.' :
                            result?.quality?.brightness < 45 ? 'Мало света. Попробуйте подсветку или измените угол этикетки.' :
                            result?.quality?.edges < 2 ? 'Подержите телефон неподвижно и измените расстояние до этикетки.' : 'Наведите на штрихкод EAN-13 или Code128 целиком');
                    }
                }
            } catch (error) {
                if (error.name !== 'AbortError') fail(s, 'Не удалось прочитать изображение. Нажмите «Повторить» или введите код вручную.');
                return;
            }
            // One in-flight operation only; work with the latest frame, not a queue.
            schedule(s, Math.max(s.mode === 'text' ? 400 : 35, (s.mode === 'text' ? 750 : 100) - (performance.now() - started)));
        }
        async function open(options) {
            if (disposed || session) return;
            activeScanner?.close('replaced'); activeScanner = api;
            const mode = options.mode || lastMode; lastMode = mode;
            const dialog = document.createElement('dialog'); dialog.className = 'tt-camera-dialog tt-camera-capture';
            dialog.setAttribute('aria-label', mode === 'text' ? 'Чтение артикула с этикетки' : 'Сканирование штрихкода');
            dialog.innerHTML = '<div class="tt-camera-head"><h2>Сканирование этикетки</h2><button type="button" class="tt-camera-close" aria-label="Закрыть">×</button></div>' +
                '<div class="tt-camera-modes" role="group" aria-label="Режим считывания"><button type="button" data-mode="barcode">Штрихкод</button><button type="button" data-mode="text">Артикул в тексте</button></div>' +
                '<p class="tt-camera-status" role="status" aria-live="polite"></p><div class="tt-camera-preview"><video muted playsinline></video><div class="tt-camera-frame" aria-hidden="true"></div></div>' +
                '<div class="tt-camera-controls"><button type="button" class="tt-camera-torch" aria-pressed="false" hidden>Подсветка</button><button type="button" class="tt-camera-switch" hidden>Другая задняя камера</button>' +
                '<label class="tt-camera-zoom" hidden>Масштаб <input type="range" aria-label="Масштаб камеры"></label></div>' +
                '<div class="tt-camera-actions"><button type="button" class="tt-camera-retry" hidden>Повторить</button><button type="button" class="tt-camera-cancel">Отмена</button></div>';
            document.body.append(dialog);
            const s = {id: ++generation, options: {...options, mode}, mode, dialog, state: 'requesting', abort: new AbortController(),
                video: dialog.querySelector('video'), frame: dialog.querySelector('.tt-camera-frame'), canvas: document.createElement('canvas'),
                status: dialog.querySelector('[role=status]'), retry: dialog.querySelector('.tt-camera-retry'), controls: dialog.querySelector('.tt-camera-controls'),
                streamListeners: [], removeListeners: [], frames: 0, lastHint: performance.now(), frameCallback: null};
            session = s; dialog.classList.toggle('tt-camera-text-mode', mode === 'text');
            const listen = (target, type, fn) => { target.addEventListener(type, fn); s.removeListeners.push(() => target.removeEventListener(type, fn)); };
            listen(dialog.querySelector('.tt-camera-close'), 'click', () => close());
            listen(dialog.querySelector('.tt-camera-cancel'), 'click', () => close());
            listen(dialog, 'cancel', e => { e.preventDefault(); close(); });
            listen(dialog, 'close', () => { if (current(s)) close(); });
            listen(root, 'pagehide', () => close('pagehide')); listen(root, 'popstate', () => close('back'));
            listen(document, 'visibilitychange', () => { if (document.hidden) close('hidden'); });
            dialog.querySelectorAll('[data-mode]').forEach(button => {
                button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
                button.onclick = () => { if (button.dataset.mode === mode) return; const next = {...s.options, mode: button.dataset.mode}; close('mode'); open(next); };
            });
            s.retry.onclick = () => { const opt = s.options; close('retry'); open(opt); };
            if (!dialog.showModal) { close(); options.onError?.('Браузер не поддерживает окно камеры. Откройте портал в актуальном браузере.'); return; }
            dialog.showModal();
            if (!(deps.isSecureContext ?? root.isSecureContext)) { fail(s, 'Камера доступна по защищённому HTTPS-адресу. По HTTP используйте ручной ввод.'); return; }
            if (!media?.getUserMedia) { fail(s, 'Этот браузер не поддерживает камеру. Введите код вручную.'); return; }
            if (media.getSupportedConstraints && !media.getSupportedConstraints().facingMode) { fail(s, messages.OverconstrainedError); return; }
            status(s, mode === 'text' ? 'Запуск задней камеры и загрузка чтения артикула…' : 'Запуск задней камеры…');
            s.timeout = setTimeout(() => fail(s, 'Не удалось запустить камеру или распознавание. Закройте окно и повторите.'), 30000);
            try {
                const decoding = Promise.resolve(getDecoder(s.abort.signal, mode)).then(decoder => {
                    if (!current(s) || s.state === 'error') { decoder?.dispose(); return; }
                    s.decoder = decoder;
                });
                const capture = (async () => {
                    const video = {facingMode: {exact: 'environment'}, width: {ideal: 1920}, height: {ideal: 1080}, frameRate: {ideal: 24, max: 30}};
                    if (preferredRear) video.deviceId = {exact: preferredRear};
                    let stream;
                    try { stream = await media.getUserMedia({audio: false, video}); }
                    catch (error) {
                        if (error.name !== 'OverconstrainedError' || !preferredRear || !current(s) || s.state === 'error') throw error;
                        preferredRear = ''; delete video.deviceId;
                        stream = await media.getUserMedia({audio: false, video});
                    }
                    if (!current(s) || s.state === 'error') { stopStream(stream); return; }
                    s.stream = stream; s.track = stream.getVideoTracks()[0];
                    for (const track of stream.getVideoTracks()) {
                        const ended = () => fail(s, 'Камера отключена. Нажмите «Повторить» или введите код вручную.');
                        track.addEventListener('ended', ended); s.streamListeners.push(() => track.removeEventListener('ended', ended));
                    }
                    await configure(s);
                    if (!current(s) || s.state === 'error') return;
                    s.video.muted = true; s.video.srcObject = stream; await s.video.play();
                })();
                await Promise.all([decoding, capture]);
                if (!current(s) || s.state === 'error' || !s.decoder) return;
                clearTimeout(s.timeout); s.timeout = setTimeout(() => fail(s, 'Этикетка пока не считана. Проверьте свет и расстояние, затем нажмите «Повторить».'), mode === 'text' ? 45000 : 30000);
                s.state = 'scanning'; s.scanningAt = performance.now();
                status(s, mode === 'text' ? 'Наведите рамку на артикул среди текста этикетки' : 'Наведите на штрихкод EAN-13 или Code128 целиком');
                await tick(s);
            } catch (error) {
                if (error.name !== 'AbortError') fail(s, messages[error.name] || 'Не удалось запустить распознавание. Нажмите «Повторить» или введите код вручную.');
            }
        }
        const api = {open, close, dispose() { close('dispose'); disposed = true; }, get state() { return session?.state || 'closed'; },
            get lastMetrics() { return lastMetrics && {...lastMetrics}; }};
        return api;
    }
    root.TTCamera = {create, version: VERSION};
})(window);
