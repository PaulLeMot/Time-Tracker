/* TimeTracker camera 1.0.0 — frames stay in memory; no transport or storage. */
(function (root) {
    'use strict';
    const VERSION = '1.0.0';
    let decoderPromise;
    let activeScanner;

    function loadDecoder() {
        if (root.ZXing) return Promise.resolve(root.ZXing);
        if (!decoderPromise) decoderPromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            const timer = setTimeout(() => finish(false), 15000);
            function finish(ok) {
                clearTimeout(timer);
                script.onload = script.onerror = null;
                if (ok && root.ZXing) resolve(root.ZXing);
                else { script.remove(); reject(new Error('decoder')); }
            }
            script.src = '/static/vendor/zxing-library-0.23.0.min.js';
            script.onload = () => finish(true);
            script.onerror = () => finish(false);
            document.head.append(script);
        }).catch(error => { decoderPromise = null; throw error; });
        return decoderPromise;
    }

    function decoder(z) {
        const hints = new Map([[z.DecodeHintType.POSSIBLE_FORMATS,
            [z.BarcodeFormat.EAN_13, z.BarcodeFormat.CODE_128]]]);
        const reader = new z.MultiFormatOneDReader(hints);
        return {
            decode(canvas) {
                const {width, height} = canvas;
                const pixels = canvas.getContext('2d', {willReadFrequently: true}).getImageData(0, 0, width, height).data;
                const gray = new Uint8ClampedArray(width * height);
                for (let i = 0; i < gray.length; i++) {
                    const p = i * 4;
                    gray[i] = (pixels[p] + pixels[p + 1] * 2 + pixels[p + 2]) >> 2;
                }
                try {
                    const result = reader.decode(new z.BinaryBitmap(new z.HybridBinarizer(
                        new z.RGBLuminanceSource(gray, width, height))), hints);
                    return {rawValue: result.getText(), format: z.BarcodeFormat[result.getBarcodeFormat()]};
                } catch (error) {
                    if (error instanceof z.NotFoundException || error instanceof z.ChecksumException || error instanceof z.FormatException) return null;
                    throw error;
                }
            },
            dispose() { reader.reset(); }
        };
    }

    const messages = {
        NotAllowedError: 'Доступ к камере запрещён. Разрешите его в настройках браузера или введите код вручную.',
        NotFoundError: 'Камера не найдена. Введите код вручную.',
        NotReadableError: 'Камера занята или недоступна. Закройте другое приложение с камерой и повторите.',
        OverconstrainedError: 'Не удалось запустить камеру на этом устройстве. Введите код вручную.',
        SecurityError: 'Браузер запрещает доступ к камере. Откройте портал по защищённому адресу.'
    };

    // Optional dependencies are for isolated lifecycle tests, never configured by pages.
    function create(deps = {}) {
        const media = deps.mediaDevices || navigator.mediaDevices;
        const getDecoder = deps.getDecoder || (() => loadDecoder().then(decoder));
        let generation = 0, session = null, disposed = false;
        function stopStream(stream) { if (stream) stream.getTracks().forEach(track => track.stop()); }
        function release(s) {
            clearTimeout(s.timer); clearTimeout(s.timeout);
            s.streamListeners.forEach(remove => remove());
            s.streamListeners = [];
            stopStream(s.stream); s.stream = null;
            s.video.pause(); s.video.srcObject = null;
            if (s.decoder) { s.decoder.dispose(); s.decoder = null; }
            // Erase the reusable in-memory frame, release its backing buffer.
            s.canvas.width = s.canvas.height = 0;
        }
        function current(s) { return !disposed && session === s && s.id === generation; }
        function close(reason = 'cancel') {
            const s = session;
            if (!s) return;
            session = null; generation++;
            release(s);
            s.removeListeners.forEach(remove => remove());
            if (s.dialog.open) s.dialog.close();
            s.dialog.remove();
            if (activeScanner === api) activeScanner = null;
            if (reason !== 'pagehide' && reason !== 'hidden' && s.options.returnFocusTo?.isConnected)
                s.options.returnFocusTo.focus({preventScroll: true});
            s.options.onClose?.(reason);
        }
        function fail(s, message) {
            if (!current(s)) return;
            release(s);
            s.state = 'error';
            s.video.hidden = true;
            s.dialog.querySelector('.tt-camera-frame').hidden = true;
            s.status.textContent = message;
            s.retry.hidden = false;
            s.options.onError?.(message);
        }
        async function open(options) {
            if (disposed || session) return;
            activeScanner?.close('replaced');
            activeScanner = api;
            const dialog = document.createElement('dialog');
            dialog.className = 'tt-camera-dialog';
            dialog.setAttribute('aria-label', 'Сканирование штрихкода');
            dialog.innerHTML = '<div class="tt-camera-head"><h2>Сканирование штрихкода</h2><button type="button" class="tt-camera-close" aria-label="Закрыть">×</button></div>' +
                '<p class="tt-camera-status" role="status" aria-live="polite"></p>' +
                '<div class="tt-camera-preview"><video muted playsinline></video><div class="tt-camera-frame" aria-hidden="true"></div></div>' +
                '<p class="tt-camera-hint">Наведите на один штрихкод целиком. Фото и видео не сохраняются.</p>' +
                '<div class="tt-camera-actions"><button type="button" class="tt-camera-retry" hidden>Повторить</button><button type="button" class="tt-camera-cancel">Отмена</button></div>';
            document.body.append(dialog);
            const s = {id: ++generation, options, dialog, state: 'requesting', stream: null, decoder: null,
                video: dialog.querySelector('video'), canvas: document.createElement('canvas'),
                status: dialog.querySelector('[role=status]'), retry: dialog.querySelector('.tt-camera-retry'), removeListeners: [], streamListeners: []};
            session = s;
            const listen = (target, type, fn) => { target.addEventListener(type, fn); s.removeListeners.push(() => target.removeEventListener(type, fn)); };
            listen(dialog.querySelector('.tt-camera-close'), 'click', () => close());
            listen(dialog.querySelector('.tt-camera-cancel'), 'click', () => close());
            listen(dialog, 'cancel', e => { e.preventDefault(); close(); });
            listen(dialog, 'close', () => { if (current(s)) close(); });
            listen(root, 'pagehide', () => close('pagehide'));
            listen(root, 'popstate', () => close('back'));
            listen(document, 'visibilitychange', () => { if (document.hidden) close('hidden'); });
            // Retry must outlive release() in the error state, unlike stream listeners.
            s.retry.onclick = () => { close('retry'); open(options); };
            if (!dialog.showModal) { close(); options.onError?.('Браузер не поддерживает окно камеры. Откройте портал в актуальном браузере.'); return; }
            dialog.showModal();
            if (!(deps.isSecureContext ?? root.isSecureContext)) {
                fail(s, 'Камера доступна по защищённому HTTPS-адресу. По текущему HTTP-адресу используйте ручной ввод.'); return;
            }
            if (!media?.getUserMedia) { fail(s, 'Этот браузер не поддерживает камеру. Откройте портал в обычном браузере или введите код вручную.'); return; }
            s.status.textContent = 'Ожидание разрешения камеры…';
            s.timeout = setTimeout(() => fail(s, 'Не удалось получить доступ к камере. Закройте окно и попробуйте ещё раз.'), 30000);
            try {
                s.decoder = await getDecoder();
                if (!current(s) || s.state === 'error') { s.decoder?.dispose(); s.decoder = null; return; }
                const stream = await media.getUserMedia({audio: false, video: {facingMode: {ideal: 'environment'}, width: {ideal: 1280}, height: {ideal: 720}}});
                if (!current(s) || s.state === 'error') { stopStream(stream); return; }
                s.stream = stream;
                stream.getVideoTracks().forEach(track => {
                    const ended = () => fail(s, 'Камера отключена. Нажмите «Повторить» или введите код вручную.');
                    track.addEventListener('ended', ended);
                    s.streamListeners.push(() => track.removeEventListener('ended', ended));
                });
                s.video.muted = true; s.video.srcObject = stream;
                await s.video.play();
                if (!current(s) || s.state === 'error') return;
                clearTimeout(s.timeout);
                s.timeout = setTimeout(() => fail(s, 'Штрихкод пока не считан. Проверьте свет и резкость, затем нажмите «Повторить».'), 30000);
                s.state = 'scanning'; s.status.textContent = 'Наведите на штрихкод EAN-13 или Code 128';
                function tick() {
                    if (!current(s) || s.state !== 'scanning') return;
                    if (s.video.readyState >= 2 && s.video.videoWidth) {
                        const scale = Math.min(1, 1280 / s.video.videoWidth, 960 / s.video.videoHeight);
                        s.canvas.width = Math.round(s.video.videoWidth * scale);
                        s.canvas.height = Math.round(s.video.videoHeight * scale);
                        s.canvas.getContext('2d', {willReadFrequently: true}).drawImage(s.video, 0, 0, s.canvas.width, s.canvas.height);
                        try {
                            const value = s.decoder.decode(s.canvas);
                            if (value && current(s)) {
                                // Close and stop every owned track before the screen adapter runs.
                                close('decoded');
                                Promise.resolve(options.onDecoded(value)).catch(() => options.onError?.('Не удалось выполнить поиск. Повторите ввод.'));
                                return;
                            }
                        } catch (error) {
                            fail(s, 'Не удалось прочитать изображение с камеры. Нажмите «Повторить» или введите код вручную.'); return;
                        }
                    }
                    // Synchronous decode, followed by a pause: no overlapping frames or requests.
                    s.timer = setTimeout(tick, 200);
                }
                tick();
            } catch (error) {
                fail(s, messages[error.name] || (error.message === 'decoder'
                    ? 'Не удалось загрузить сканер. Повторите или введите код вручную.'
                    : 'Не удалось запустить камеру. Нажмите «Повторить» или введите код вручную.'));
            }
        }
        const api = {open, close, dispose() { close('dispose'); disposed = true; }, get state() { return session?.state || 'closed'; }};
        return api;
    }
    root.TTCamera = {create, version: VERSION};
})(window);
