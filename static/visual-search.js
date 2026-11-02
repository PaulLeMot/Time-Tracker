/* Local photo search. One explicit crop/upload; no storage, continuous frames or external APIs. */
(function (root) {
    'use strict';
    function create(options) {
        const button = options.button, media = options.mediaDevices || navigator.mediaDevices;
        const transport = options.fetch || root.fetch.bind(root);
        let current = null, sequence = 0, capabilities = null;
        const stop = stream => stream?.getTracks().forEach(track => track.stop());
        const live = session => current === session && session.id === sequence;
        function releaseCamera(s) {
            stop(s.stream); s.stream = null;
            s.video.pause(); s.video.srcObject = null;
        }
        function close() {
            sequence++;
            const s = current; current = null;
            if (!s) return;
            s.abort?.abort(); s.cameraGeneration++; releaseCamera(s);
            s.blob = null; s.source = null;
            s.canvas.width = s.canvas.height = 0;
            if (s.dialog.open) s.dialog.close();
            s.dialog.remove(); button.focus({preventScroll: true});
            options.onClose?.();
        }
        async function request(s, path, settings = {}) {
            s.abort?.abort();
            const controller = s.abort = new AbortController();
            const timer = setTimeout(() => controller.abort(), 8000);
            try {
                const response = await transport(path, {credentials: 'same-origin', cache: 'no-store', ...settings, signal: controller.signal});
                if (!response.ok) {
                    const message = {401: 'Войдите в личный кабинет.', 403: 'Доступ к фото-поиску запрещён.',
                        410: 'Результаты устарели. Повторите снимок.', 413: 'Слишком большой снимок.',
                        415: 'Нужен JPEG, PNG или WebP.', 422: 'Не удалось обработать снимок или вид товара.',
                        429: 'Поиск занят. Повторите через несколько секунд.'}[response.status];
                    throw Error(message || 'Фото-поиск временно недоступен. Обычный поиск продолжает работать.');
                }
                return await response.json();
            } finally { clearTimeout(timer); }
        }
        function message(s, text) { if (live(s)) s.notice.textContent = text; }
        function action(label, handler) {
            const el = document.createElement('button'); el.type = 'button'; el.textContent = label; el.onclick = handler; return el;
        }
        async function camera(s) {
            s.operation++; s.busy = false;
            s.abort?.abort(); s.cameraGeneration++; const cameraId = s.cameraGeneration;
            releaseCamera(s); s.blob = null; s.source = null; s.results.replaceChildren(); s.more.hidden = true;
            s.canvas.hidden = true; s.video.hidden = false; s.crop.hidden = false; s.shutter.hidden = false;
            s.search.disabled = true; s.shutter.disabled = true;
            if (!s.kind.value) { message(s, 'Сначала выберите вид товара.'); return; }
            message(s, 'Открываю заднюю камеру…');
            try {
                if (!root.isSecureContext || !media?.getUserMedia) throw Error('secure');
                const stream = await media.getUserMedia({audio: false, video: {facingMode: {exact: 'environment'}, width: {ideal: 1280}, height: {ideal: 1280}}});
                if (!live(s) || cameraId !== s.cameraGeneration) { stop(stream); return; }
                if (stream.getVideoTracks()[0]?.getSettings().facingMode !== 'environment') { stop(stream); throw Error('rear'); }
                s.stream = stream; s.video.srcObject = stream;
                await s.video.play();
                if (!live(s) || cameraId !== s.cameraGeneration) return;
                s.stage.style.aspectRatio = `${s.video.videoWidth} / ${s.video.videoHeight}`;
                s.stage.style.maxWidth = `min(100%, ${42 * s.video.videoWidth / s.video.videoHeight}dvh)`;
                s.shutter.disabled = false;
                message(s, 'Поместите рисунок в рамку. Кнопка «Снимок» зафиксирует кадр.');
            } catch (error) {
                if (!live(s) || cameraId !== s.cameraGeneration) return;
                releaseCamera(s);
                message(s, error.name === 'NotAllowedError' ? 'Разрешите доступ к камере или выберите файл.' :
                    'Задняя камера недоступна. Откройте HTTPS-адрес портала или выберите файл.');
            }
        }
        function paint(s) {
            const source = s.source || s.video;
            const width = source.videoWidth || source.naturalWidth || source.width;
            const height = source.videoHeight || source.naturalHeight || source.height;
            if (!width || !height) throw Error('Кадр ещё не готов.');
            const fraction = Number(s.range.value) / 100;
            const w = width * fraction, h = height * fraction, scale = Math.min(1, 960 / Math.max(w, h));
            s.canvas.width = Math.round(w * scale); s.canvas.height = Math.round(h * scale);
            s.canvas.getContext('2d').drawImage(source, (width-w)/2, (height-h)/2, w, h, 0, 0, s.canvas.width, s.canvas.height);
            s.stage.style.aspectRatio = `${s.canvas.width} / ${s.canvas.height}`;
            s.stage.style.maxWidth = `min(100%, ${42 * s.canvas.width / s.canvas.height}dvh)`;
        }
        async function capture(s) {
            if (!live(s)) return;
            const id = ++s.captureGeneration;
            try {
                paint(s);
                s.canvas.hidden = false; s.video.hidden = true; s.crop.hidden = true; s.shutter.hidden = true;
                releaseCamera(s); s.source = null;
                const blob = await new Promise(resolve => s.canvas.toBlob(resolve, 'image/jpeg', .90));
                if (!live(s) || id !== s.captureGeneration) return;
                if (!blob || blob.size > 2*1024*1024) throw Error('Не удалось подготовить снимок. Переснимите.');
                s.blob = blob; s.search.disabled = false;
                message(s, 'Проверьте обрезку. «Найти» отправит только этот снимок на наш локальный сервер.');
            } catch (error) { message(s, error.message); }
        }
        async function file(s, input) {
            const selected = input.files?.[0]; input.value = '';
            if (!selected || !live(s)) return;
            if (!s.kind.value) { message(s, 'Сначала выберите вид товара.'); return; }
            if (selected.size > 2*1024*1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(selected.type)) {
                message(s, 'Выберите JPEG, PNG или WebP до 2 МБ.'); return;
            }
            s.operation++; s.busy = false; s.cameraGeneration++; releaseCamera(s); s.abort?.abort(); s.captureGeneration++;
            const id = s.captureGeneration;
            const url = URL.createObjectURL(selected), img = new Image();
            try {
                img.src = url; await img.decode();
                if (!live(s) || id !== s.captureGeneration) return;
                if (img.naturalWidth * img.naturalHeight > 12000000 || Math.min(img.naturalWidth, img.naturalHeight) < 32) throw Error('Нужен снимок до 12 мегапикселей, не меньше 32 пикселей.');
                s.source = img; s.blob = null; s.search.disabled = true;
                s.video.hidden = true; s.canvas.hidden = false; s.crop.hidden = true;
                paint(s); s.shutter.hidden = false; s.shutter.disabled = false;
                s.results.replaceChildren(); s.more.hidden = true;
                message(s, 'Измените область ползунком и нажмите «Снимок». Поворот EXIF учитывается браузером.');
            } catch (error) { message(s, error.message || 'Не удалось открыть файл.'); }
            finally { URL.revokeObjectURL(url); }
        }
        function render(s, result, append) {
            if (!live(s)) return;
            if (!append) s.results.replaceChildren();
            for (const item of result.items) {
                const card = document.createElement('article'); card.className = 'product-card';
                const image = document.createElement('img'); image.alt = item.name; image.loading = 'lazy';
                image.src = '/static/img/' + encodeURIComponent(item.code) + '.jpg';
                const name = document.createElement('div'); name.className = 'name'; name.textContent = item.name;
                const code = document.createElement('div'); code.className = 'code'; code.textContent = item.code;
                const kind = document.createElement('div'); kind.textContent = item.product_type;
                const hint = document.createElement('small'); hint.textContent = item.evidence === 'geometry' ? 'Совпали детали рисунка' : 'Слабое сходство — проверьте рисунок';
                card.append(image, name, code, kind, hint); s.results.append(card);
            }
            s.cursor = result.cursor; s.offset = result.next_offset; s.more.hidden = s.offset == null;
            message(s, result.status === 'none' ? 'Подходящий рисунок не найден. Переснимите ближе, без бликов.' :
                result.status === 'weak' ? `Только слабые совпадения (${result.total}). Проверьте рисунок или переснимите.` :
                `Найдены похожие товары: ${result.total}. Проверьте изображение и код. Сходство не является вероятностью.`);
        }
        async function search(s, more = false) {
            if (!live(s) || s.busy || (!more && (!s.blob || !s.kind.value))) return;
            s.busy = true; s.search.disabled = s.more.disabled = true;
            const operation = ++s.operation;
            const started = performance.now();
            message(s, 'Ищу рисунок в выбранном виде товара…');
            try {
                const path = more ? '/api/visual-search/results?' + new URLSearchParams({cursor: s.cursor, offset: s.offset}) :
                    '/api/visual-search/search?' + new URLSearchParams({product_type: s.kind.value});
                const result = await request(s, path, more ? {} : {method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: s.blob});
                if (!live(s) || operation !== s.operation) return;
                render(s, result, more);
                s.blob = null; s.canvas.width = s.canvas.height = 0; s.canvas.hidden = true; s.stage.hidden = true;
                s.range.disabled = true;
                root.dispatchEvent(new CustomEvent('tt-photo-timing', {detail: {elapsed_ms: performance.now()-started, status: result.status}}));
            } catch (error) { if (live(s) && operation === s.operation) message(s, error.name === 'AbortError' ? 'Поиск отменён или время ожидания истекло. Можно повторить снимок.' : error.message); }
            finally { if (live(s) && operation === s.operation) { s.busy = false; s.search.disabled = !s.blob; s.more.disabled = false; } }
        }
        function open() {
            close(); options.beforeOpen?.();
            if (!capabilities) return;
            const dialog = document.createElement('dialog'); dialog.className = 'tt-photo-dialog';
            const s = current = {id: ++sequence, dialog, stream: null, abort: null, blob: null, source: null,
                cameraGeneration: 0, captureGeneration: 0, operation: 0, busy: false};
            const header = document.createElement('header');
            const title = document.createElement('h2'); title.id = 'ttPhotoTitle'; title.textContent = 'Поиск по фото';
            const cancel = action('Закрыть', close); cancel.setAttribute('aria-label', 'Закрыть поиск по фото');
            header.append(title, cancel); dialog.setAttribute('aria-labelledby', title.id);
            const body = document.createElement('section'); body.className = 'tt-photo-body';
            const privacy = document.createElement('p'); privacy.textContent = 'Один обрезанный снимок отправляется только нашему локальному серверу по HTTPS. В сервисе снимки не сохраняются.';
            const label = document.createElement('label'); label.textContent = 'Вид товара';
            s.kind = document.createElement('select');
            const empty = new Option('Выберите вид товара', ''); s.kind.append(empty);
            for (const kind of capabilities.product_types) s.kind.append(new Option(kind, kind));
            s.kind.value = capabilities.product_types.includes(options.selectedType?.()) ? options.selectedType() : '';
            label.append(s.kind);
            s.stage = document.createElement('div'); s.stage.className = 'tt-photo-stage';
            s.video = document.createElement('video'); s.video.muted = true; s.video.autoplay = true; s.video.playsInline = true;
            s.canvas = document.createElement('canvas'); s.canvas.hidden = true;
            s.crop = document.createElement('div'); s.crop.className = 'tt-photo-crop'; s.crop.setAttribute('aria-hidden', 'true');
            s.stage.append(s.video, s.canvas, s.crop);
            const cropLabel = document.createElement('label'); cropLabel.textContent = 'Область рисунка';
            s.range = document.createElement('input'); s.range.type = 'range'; s.range.min = '35'; s.range.max = '100'; s.range.value = '85';
            cropLabel.append(s.range); s.range.oninput = () => { s.crop.style.inset = (100-Number(s.range.value))/2 + '%'; if (s.source) paint(s); };
            s.range.oninput();
            s.notice = document.createElement('p'); s.notice.className = 'tt-photo-notice'; s.notice.setAttribute('role', 'status');
            s.results = document.createElement('div'); s.results.className = 'tt-photo-results';
            s.more = action('Ещё товары', () => search(s, true)); s.more.hidden = true;
            body.append(privacy, label, s.stage, cropLabel, s.notice, s.results, s.more);
            const footer = document.createElement('footer');
            s.shutter = action('Снимок', () => capture(s)); s.shutter.disabled = true;
            s.search = action('Найти', () => search(s)); s.search.disabled = true;
            const retake = action('Переснять', () => { s.stage.hidden = false; s.range.disabled = false; s.captureGeneration++; camera(s); });
            const input = document.createElement('input'); input.type = 'file'; input.accept = 'image/jpeg,image/png,image/webp'; input.hidden = true;
            input.onchange = () => { s.stage.hidden = false; s.range.disabled = false; file(s, input); };
            footer.append(s.shutter, s.search, retake, action('Файл', () => input.click()), input);
            s.kind.onchange = () => { s.captureGeneration++; s.busy = false; s.stage.hidden = false; s.range.disabled = false; camera(s); };
            dialog.append(header, body, footer); document.body.append(dialog);
            dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
            dialog.showModal(); camera(s);
        }
        button.onclick = open;
        const closeOnHidden = () => { if (document.hidden) close(); };
        root.addEventListener('pagehide', close);
        root.addEventListener('tt-search-change', close);
        document.addEventListener('visibilitychange', closeOnHidden);
        options.barcodeButton?.addEventListener('click', close);
        async function refresh() {
            try {
                const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 3000);
                let response;
                try { response = await transport('/api/visual-search/capabilities', {credentials: 'same-origin', cache: 'no-store', signal: controller.signal}); }
                finally { clearTimeout(timer); }
                if (!response.ok) return;
                const value = await response.json();
                if (value.api_version !== 1 || !Array.isArray(value.product_types) || !value.product_types.every(x => typeof x === 'string')) return;
                capabilities = value; button.hidden = false;
            } catch (_) { /* Existing search remains usable when service is absent. */ }
        }
        refresh();
        return {open, close, refresh};
    }
    root.TTVisualSearch = {create};
})(window);
