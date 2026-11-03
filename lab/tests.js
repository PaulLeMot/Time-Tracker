/* Browser tests run only in tools/camera_lab.py, never in the application. */
'use strict';
const results = [];
const assert = (condition, text = 'Assertion failed') => { if (!condition) throw Error(text); };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, ms = 4000) { const end = performance.now() + ms; while (!check()) { if (performance.now() > end) throw Error('Condition timed out'); await delay(15); } }
async function test(name, run) {
    try { await run(); results.push({name, status: 'PASS'}); }
    catch (error) { results.push({name, status: 'FAIL', error: error.message}); }
    document.getElementById('result').textContent = JSON.stringify(results, null, 2);
}
const track = () => Object.assign(new EventTarget(), {readyState: 'live', stops: 0, stop() { this.readyState = 'ended'; this.stops++; }});
const stream = t => ({getTracks: () => [t], getVideoTracks: () => [t]});
function fakeVideo() {
    const proto = HTMLMediaElement.prototype;
    const saved = {};
    for (const [key, value] of Object.entries({play: {value: async function() {}}, pause: {value: function() {}},
        srcObject: {get() { return this._testStream; }, set(v) { this._testStream = v; }},
        readyState: {get() { return 2; }}})) {
        saved[key] = Object.getOwnPropertyDescriptor(proto, key);
        Object.defineProperty(proto, key, {...value, configurable: true});
    }
    const videoProto = HTMLVideoElement.prototype;
    const size = {};
    for (const [key, value] of Object.entries({videoWidth: 1000, videoHeight: 1000})) {
        size[key] = Object.getOwnPropertyDescriptor(videoProto, key);
        Object.defineProperty(videoProto, key, {get: () => value, configurable: true});
    }
    const draw = CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage = function(source, ...args) {
        if (source instanceof HTMLVideoElement) {
            if (window.testLabel) {
                // Keep the whole independent label inside the visible square.
                const square=document.createElement('canvas');square.width=square.height=1000;
                const ctx=square.getContext('2d'), image=window.testLabel;
                ctx.fillStyle='white';ctx.fillRect(0,0,1000,1000);
                const scale=Math.min(1000/image.naturalWidth,1000/image.naturalHeight),w=image.naturalWidth*scale,h=image.naturalHeight*scale;
                draw.call(ctx,image,(1000-w)/2,(1000-h)/2,w,h);
                return draw.call(this,square,...args);
            }
            this.fillStyle = 'white'; this.fillRect(0, 0, this.canvas.width, this.canvas.height); return;
        }
        return draw.call(this, source, ...args);
    };
    return () => {
        for (const [key, value] of Object.entries(saved)) Object.defineProperty(proto, key, value);
        for (const [key, value] of Object.entries(size)) Object.defineProperty(videoProto, key, value);
        CanvasRenderingContext2D.prototype.drawImage = draw;
    };
}
async function withFake(run) { const restore = fakeVideo(); try { await run(); } finally { restore(); window.testLabel = null; } }
const noDecode = () => Promise.resolve({decode: () => null, dispose() {}});
const trigger = document.getElementById('focusTrigger');
function create(media, getDecoder = noDecode, secure = true) { return TTCamera.create({mediaDevices: media, getDecoder, isSecureContext: secure}); }
const options = callback => ({returnFocusTo: trigger, onDecoded: callback || (() => {})});

document.getElementById('run').onclick = async function() {
    this.disabled = true; results.length = 0;
    await test('cancel before permission: late stream stopped, no callback', () => withFake(async () => {
        let grant, calls = 0; const t = track();
        const scanner = create({getUserMedia: () => new Promise(resolve => { grant = resolve; })});
        const opening = scanner.open(options(() => calls++));
        await until(() => grant); scanner.close(); grant(stream(t)); await opening;
        assert(t.readyState === 'ended' && calls === 0 && scanner.state === 'closed'); scanner.dispose();
    }));
    await test('double open, explicit stop, foreign stream unaffected, focus restored', () => withFake(async () => {
        let calls = 0; const t = track(), foreign = track();
        const scanner = create({getUserMedia: async constraints => { calls++; assert(constraints.audio === false); return stream(t); }});
        await scanner.open(options()); await scanner.open(options());
        assert(calls === 1 && scanner.state === 'scanning', 'Double open created another stream'); scanner.close();
        assert(t.stops === 1 && foreign.stops === 0, 'Owned/foreign track cleanup');
        assert(document.activeElement === trigger, 'Focus did not return to the enabled trigger'); scanner.dispose();
    }));
    await test('one result per session; reopen same code; stream ended before callback', () => withFake(async () => {
        let calls = 0; const tracks = [];
        const scanner = create({getUserMedia: async () => { const t = track(); tracks.push(t); return stream(t); }}, async () => ({
            decode: () => ({rawValue: '90001', format: 'CODE_128'}), dispose() {}}));
        const opt = options(() => { assert(tracks.at(-1).readyState === 'ended'); calls++; });
        await scanner.open(opt); await delay(450); assert(calls === 1);
        await scanner.open(opt); assert(calls === 2 && tracks.every(t => t.stops === 1)); scanner.dispose();
    }));
    await test('permission denied and busy: error window can close and retry', () => withFake(async () => {
        for (const name of ['NotAllowedError', 'NotReadableError', 'NotFoundError']) {
            let calls = 0;
            const scanner = create({getUserMedia: async () => { calls++; const error = Error(); error.name = name; throw error; }});
            await scanner.open(options()); assert(scanner.state === 'error');
            document.querySelector('.tt-camera-retry').click(); await until(() => calls === 2 && scanner.state === 'error');
            document.querySelector('.tt-camera-close').click(); assert(scanner.state === 'closed'); scanner.dispose();
        }
    }));
    await test('HTTP unavailable and missing decoder: manual path untouched', () => withFake(async () => {
        let calls = 0;
        const scanner = create({getUserMedia: async () => { calls++; }}, noDecode, false);
        await scanner.open(options()); assert(scanner.state === 'error' && calls === 0); scanner.dispose();
        const pending = track();
        const unavailable = create({getUserMedia: async () => stream(pending)}, async () => { throw Error('decoder'); });
        await unavailable.open(options()); assert(unavailable.state === 'error' && pending.stops === 1); unavailable.dispose();
    }));
    await test('Escape, Back, pagehide and background stop tracks; no automatic resume', () => withFake(async () => {
        for (const reason of ['cancel', 'popstate', 'pagehide', 'hidden']) {
            const t = track(); let requests = 0;
            const scanner = create({getUserMedia: async () => { requests++; return stream(t); }});
            await scanner.open(options());
            if (reason === 'cancel') document.querySelector('dialog').dispatchEvent(new Event('cancel', {cancelable: true}));
            else if (reason === 'hidden') {
                Object.defineProperty(document, 'hidden', {configurable: true, value: true});
                document.dispatchEvent(new Event('visibilitychange')); delete document.hidden;
                document.dispatchEvent(new Event('visibilitychange'));
            } else window.dispatchEvent(new Event(reason));
            assert(t.readyState === 'ended' && scanner.state === 'closed' && requests === 1); scanner.dispose();
        }
    }));
    await test('camera interrupted; repeated sessions do not retain streams or dialogs', () => withFake(async () => {
        const tracks = [];
        const scanner = create({getUserMedia: async () => { const t = track(); tracks.push(t); return stream(t); }});
        for (let i = 0; i < 12; i++) { await scanner.open(options()); scanner.close(); }
        await scanner.open(options()); tracks.at(-1).dispatchEvent(new Event('ended'));
        assert(scanner.state === 'error'); scanner.dispose();
        assert(tracks.every(t => t.stops === 1) && !document.querySelector('dialog'));
    }));
    await test('request timeout and decoder cancellation stop late resources', () => withFake(async () => {
        const originalTimeout = window.setTimeout;
        window.setTimeout = (fn, ms, ...args) => originalTimeout(fn, ms === 30000 ? 40 : ms, ...args);
        let scanner;
        try {
            let grant; const t = track(); let calls = 0;
            scanner = create({getUserMedia: () => new Promise(resolve => { grant = resolve; })});
            const opening = scanner.open(options(() => calls++));
            await until(() => grant); await until(() => scanner.state === 'error');
            grant(stream(t)); await opening; assert(t.stops === 1 && calls === 0); scanner.dispose();
            let loaded, disposed = 0, mediaCalls = 0;
            const pendingTrack = track();
            scanner = create({getUserMedia: async () => { mediaCalls++; return stream(pendingTrack); }}, () => new Promise(resolve => { loaded = resolve; }));
            const loading = scanner.open(options()); scanner.close();
            loaded({decode: () => null, dispose() { disposed++; }}); await loading;
            assert(disposed === 1 && mediaCalls === 1 && pendingTrack.stops === 1);
        } finally { scanner?.dispose(); window.setTimeout = originalTimeout; }
    }));
    await test('actual local decoder reads independent EAN13 and Code128 PNG frames', () => withFake(async () => {
        const cases = await (await fetch('/lab/labels/cases.json')).json();
        for (const label of cases) {
            const image = new Image(); image.src = '/lab/labels/' + label.image; await image.decode(); window.testLabel = image;
            const t = track(); let decoded;
            const scanner = TTCamera.create({mediaDevices: {getUserMedia: async () => stream(t)}, isSecureContext: true});
            await scanner.open(options(value => { decoded = value; }));
            await until(() => decoded || scanner.state === 'error', 20000);
            assert(decoded?.rawValue === label.rawValue && decoded?.format === label.format, 'Decode mismatch: ' + label.image);
            assert(t.readyState === 'ended'); scanner.dispose();
        }
        window.testLabel = null;
    }));
    await test('blank frames keep scanning with no callback, lookup, storage or leaked canvas', () => withFake(async () => {
        let callbacks = 0; const t = track();
        const before = JSON.stringify({...localStorage});
        const scanner = TTCamera.create({mediaDevices: {getUserMedia: async () => stream(t)}, isSecureContext: true});
        await scanner.open(options(() => callbacks++)); await delay(450);
        assert(scanner.state === 'scanning' && callbacks === 0 && t.readyState === 'live'); scanner.close();
        assert(t.stops === 1 && JSON.stringify({...localStorage}) === before && !document.querySelector('canvas')); scanner.dispose();
    }));

    await test('rear-only constraints, autofocus, supported controls and no front switch', () => withFake(async () => {
        const t = track(), requests = [], settings = [];
        t.getCapabilities = () => ({focusMode: ['continuous', 'single-shot'], torch: true, zoom: {min: 1, max: 8, step: .1}});
        t.getSettings = () => ({facingMode: 'environment', deviceId: 'rear1', zoom: 1});
        t.applyConstraints = async value => { settings.push(value); };
        const scanner = create({getSupportedConstraints: () => ({facingMode: true}),
            getUserMedia: async value => { requests.push(value); return stream(t); },
            enumerateDevices: async () => [{kind: 'videoinput', deviceId: 'rear1', label: 'Back camera'},
                {kind: 'videoinput', deviceId: 'front1', label: 'Front camera'}]});
        await scanner.open(options());
        assert(requests[0].video.facingMode.exact === 'environment' && requests[0].audio === false);
        assert(settings[0].advanced[0].focusMode === 'continuous');
        assert(document.querySelector('.tt-camera-switch').hidden, 'Front camera offered');
        document.querySelector('.tt-camera-torch').click(); await delay(10);
        assert(settings.at(-1).advanced[0].torch === true);
        assert(document.querySelector('.tt-camera-zoom input').max === '3');
        scanner.dispose(); assert(t.stops === 1);
        const front = track(); front.getSettings = () => ({facingMode: 'user'});
        const rejected = create({getUserMedia: async () => stream(front)});
        await rejected.open(options()); assert(rejected.state === 'error' && front.stops === 1); rejected.dispose();
    }));
    await test('one pending decode only; close aborts initialization; late result cannot search', () => withFake(async () => {
        let finish, calls = 0, hits = 0, aborted = false; const t = track();
        const scanner = create({getUserMedia: async () => stream(t)}, async signal => {
            signal.addEventListener('abort', () => { aborted = true; });
            return {decode: () => { calls++; return new Promise(resolve => { finish = resolve; }); }, dispose() {}};
        });
        const opening = scanner.open(options(() => hits++)); await until(() => finish); await delay(250);
        assert(calls === 1); scanner.close(); finish({value: {rawValue: '90001', format: 'CODE_128'}}); await opening;
        assert(aborted && hits === 0 && t.stops === 1); scanner.dispose();
    }));
    await test('mode switch releases old stream; cancel during OCR initialization releases new stream', () => withFake(async () => {
        const tracks = []; let loadText, textAbort = false, disposed = 0;
        const scanner = TTCamera.create({mediaDevices: {getUserMedia: async () => { const t = track(); tracks.push(t); return stream(t); }},
            isSecureContext: true, getDecoder: async (signal, mode) => {
                if (mode !== 'text') return {decode: () => null, dispose() {}};
                signal.addEventListener('abort', () => { textAbort = true; });
                return new Promise(resolve => { loadText = resolve; });
            }});
        await scanner.open(options()); document.querySelector('[data-mode="text"]').click();
        await until(() => loadText && tracks.length === 2); scanner.close();
        loadText({decode: () => null, dispose() { disposed++; }}); await delay(20);
        assert(textAbort && disposed === 1 && tracks.every(t => t.stops === 1)); scanner.dispose();
    }));
    await test('rear switch offers only two rear cameras; unavailable controls never break scanning', () => withFake(async () => {
        const requests = [], tracks = [];
        const scanner = create({getSupportedConstraints: () => ({facingMode: true}),
            enumerateDevices: async () => [{kind: 'videoinput', deviceId: 'rear1', label: 'Back main'},
                {kind: 'videoinput', deviceId: 'rear2', label: 'Back macro'}, {kind: 'videoinput', deviceId: 'front', label: 'Front'}],
            getUserMedia: async request => { requests.push(request); const t = track(); tracks.push(t);
                t.getSettings = () => ({facingMode: 'environment', deviceId: request.video.deviceId?.exact || 'rear1'});
                t.getCapabilities = () => ({focusMode: ['continuous']}); t.applyConstraints = async () => { throw Error('Unsupported'); };
                return stream(t); }});
        await scanner.open(options()); assert(scanner.state === 'scanning');
        document.querySelector('.tt-camera-switch').click(); await until(() => requests.length === 2 && scanner.state === 'scanning');
        assert(requests[1].video.deviceId.exact === 'rear2' && requests[1].video.facingMode.exact === 'environment');
        scanner.dispose(); assert(tracks.every(t => t.stops === 1));
        let calls = 0; const unsupported = create({getSupportedConstraints: () => ({facingMode: false}), getUserMedia: async () => { calls++; }});
        await unsupported.open(options()); assert(unsupported.state === 'error' && calls === 0); unsupported.dispose();
    }));
    await test('OCR mode reads actual local model and mixed label; repeated stable read only', () => withFake(async () => {
        const image = new Image(); image.src = '/lab/labels/article.png'; await image.decode(); window.testLabel = image;
        const t = track(); let decoded;
        const scanner = TTCamera.create({mediaDevices: {getUserMedia: async () => stream(t)}, isSecureContext: true});
        const before = JSON.stringify({...localStorage});
        try {
            await scanner.open({...options(value => { decoded = value; }), mode: 'text'});
            await until(() => decoded || scanner.state === 'error', 50000);
            assert(decoded?.format === 'OCR_TEXT' && TTCodeSearch.textTokens(decoded.rawValue).includes('90001'),
                'Local OCR failed: ' + (decoded?.rawValue || document.querySelector('.tt-camera-status')?.textContent));
            assert(scanner.lastMetrics.frames >= 2 && t.stops === 1 && JSON.stringify({...localStorage}) === before);
        } finally { scanner.dispose(); }
    }));

    async function frame(path) {
        document.getElementById('frame').replaceChildren();
        const iframe = document.createElement('iframe'); iframe.src = path;
        const loaded = new Promise(resolve => { iframe.onload = resolve; }); document.getElementById('frame').append(iframe);
        await loaded; await delay(100); return iframe.contentWindow;
    }
    await test('image page: manual partial/Enter retained, camera exact, filter preserved and explicit clear', async () => {
        const win = await frame('/static/search.html'); const doc = win.document; const input = doc.getElementById('codeInput');
        input.value = '90001'; input.dispatchEvent(new Event('input')); input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
        await until(() => doc.querySelectorAll('.product-card').length === 2);
        await win.findCameraImage({rawValue: '2400000900016', format: 'EAN_13'});
        assert(doc.querySelectorAll('.product-card').length === 1 && doc.querySelector('.code').textContent === '90001');
        const type = doc.getElementById('typeInput'); type.focus();
        await until(() => doc.querySelectorAll('#typeDropdown .dropdown-item').length === 2);
        [...doc.querySelectorAll('#typeDropdown .dropdown-item')].find(n => n.textContent === 'SYN B').dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
        await until(() => doc.getElementById('cameraSearchNotice').textContent.includes('скрыт фильтром'));
        assert(type.value === 'SYN B' && !doc.querySelector('.product-card'));
        doc.querySelector('#cameraSearchNotice button').click();
        await until(() => doc.querySelector('.product-card'));
        assert(type.value === '' && input.value === '90001');
    });
    await test('image page: old manual response cannot overwrite camera or newer input', async () => {
        const win = await frame('/static/search.html'), doc = win.document;
        const original = win.fetch.bind(win); let finish;
        win.fetch = async (url, options) => String(url).includes('code=OLD') ? new Promise(resolve => { finish = () => resolve({ok: true, json: async () => ({items: [{code: 'OLD', name: 'OLD', image_url: '/lab/labels/ean.png'}], total: 1})}); }) : original(url, options);
        const input = doc.getElementById('codeInput'); input.value = 'OLD'; win.resetAndLoad(); await until(() => finish);
        await win.findCameraImage({rawValue: '90001', format: 'CODE_128'}); finish(); await delay(50);
        assert(doc.querySelector('.code').textContent === '90001');
        input.value = '90002'; input.dispatchEvent(new Event('input')); input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}));
        await until(() => doc.querySelector('.code')?.textContent === '90002');
    });
    await test('image page: 0/N/error paths preserve previous search and require explicit choice', async () => {
        const win = await frame('/static/search.html'), doc = win.document;
        await until(() => doc.querySelectorAll('.product-card').length === 3);
        await win.findCameraImage({rawValue: 'UNKNOWN', format: 'CODE_128'});
        assert(doc.querySelectorAll('.product-card').length === 3 && doc.getElementById('codeInput').value === '');
        for (const raw of ['SOURCE-FAIL', 'AUTH-EXPIRED']) {
            await win.findCameraImage({rawValue: raw, format: 'CODE_128'}); assert(doc.querySelectorAll('.product-card').length === 3);
        }
        const searching = win.findCameraImage({rawValue: 'DEMO-COLLISION', format: 'CODE_128'});
        await until(() => doc.querySelectorAll('.tt-camera-choice').length === 2);
        assert(doc.querySelectorAll('.product-card').length === 3);
        doc.querySelectorAll('.tt-camera-choice')[1].click(); await searching;
        assert(doc.querySelector('.code').textContent === '90002');
    });
    await test('marking page: manual Enter, history, camera single lookup and explicit N selection', async () => {
        const win = await frame('/mark'), doc = win.document; const original = win.fetch.bind(win); const calls = [];
        win.fetch = (url, options) => { calls.push({url: String(url), method: options?.method || 'GET'}); return original(url, options); };
        const input = doc.getElementById('scanInput'); input.value = '90001';
        input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
        await until(() => doc.querySelector('.code-part')?.textContent === '90001');
        const before = calls.length;
        await win.performScan('2400000900016', true);
        assert(calls.length === before + 1 && doc.querySelector('.code-part').textContent === '90001');
        const scanning = win.performScan('DEMO-COLLISION', true);
        await until(() => doc.querySelectorAll('.tt-camera-choice').length === 2);
        doc.querySelectorAll('.tt-camera-choice')[1].click(); await scanning;
        assert(doc.querySelector('.code-part').textContent === '90002');
        assert(calls.every(call => call.method === 'GET' && !/refresh|import|timelog/.test(call.url)));
        assert(JSON.parse(win.localStorage.getItem('markSearchHistory')).includes('DEMO-COLLISION'));
    });
    await test('marking page: late manual response cannot overwrite a camera result', async () => {
        const win = await frame('/mark'), doc = win.document; const original = win.fetch.bind(win); let finish;
        win.fetch = (url, options) => String(url).endsWith('/OLD90001') ? new Promise(resolve => { finish = () => resolve({ok: true, json: async () => [{'Код': 'OLD90001', 'Название': 'SYN', found_markings: [], table: []}]}); }) : original(url, options);
        const old = win.performScan('OLD90001'); await until(() => finish);
        await win.performScan('90002', true); // not mapped, previous result stays; then a valid barcode
        await win.performScan('2400000900016', true); finish(); await old;
        assert(doc.querySelector('.code-part').textContent === '90001');
    });
    await test('OCR image result requires confirmation; rejection preserves previous products', async () => {
        const win = await frame('/static/search.html'), doc = win.document;
        await until(() => doc.querySelectorAll('.product-card').length === 3);
        const rejected = win.findCameraImage({rawValue: 'SKU O90001', format: 'OCR_TEXT'});
        await until(() => doc.querySelector('.tt-camera-choice'));
        assert(doc.querySelectorAll('.product-card').length === 3 && !doc.querySelector('dialog img'));
        assert(doc.querySelector('.tt-camera-source').textContent.includes('O90001'));
        doc.querySelector('.tt-camera-reject').click(); await rejected;
        assert(doc.querySelectorAll('.product-card').length === 3 && doc.getElementById('codeInput').value === '');
        const accepted = win.findCameraImage({rawValue: 'SKU O90001', format: 'OCR_TEXT'});
        await until(() => doc.querySelector('.tt-camera-choice')); doc.querySelector('.tt-camera-choice').click(); await accepted;
        await until(() => doc.querySelectorAll('.product-card').length === 1);
        assert(doc.querySelectorAll('.product-card').length === 1 && doc.querySelector('.code').textContent === '90001');
    });
    await test('OCR marking confirmation, no full label in history, manual input cancels stale choice', async () => {
        const win = await frame('/mark'), doc = win.document;
        const historyBefore = win.localStorage.getItem('markSearchHistory');
        const rejected = win.performScan('SKU O90001', 'text');
        await until(() => doc.querySelector('.tt-camera-choice')); doc.querySelector('.tt-camera-reject').click(); await rejected;
        assert(win.localStorage.getItem('markSearchHistory') === historyBefore);
        const accepted = win.performScan('SKU O90001', 'text');
        await until(() => doc.querySelector('.tt-camera-choice')); doc.querySelector('.tt-camera-choice').click(); await accepted;
        assert(doc.querySelector('.code-part').textContent === '90001');
        assert(!JSON.parse(win.localStorage.getItem('markSearchHistory')).includes('SKU O90001'));
        const pending = win.performScan('SKU 90001', 'text'); await until(() => doc.querySelector('.tt-camera-choice'));
        await win.performScan('2400000900016', true); await pending;
        assert(!doc.querySelector('dialog') && doc.querySelector('.code-part').textContent === '90001');
    });
    const geometry = [];
    await test('both pages and choice dialog at six widths and normal/large text', async () => {
        for (const path of ['/static/search.html', '/mark']) {
            const win = await frame(path), doc = win.document, iframe = doc.defaultView.frameElement;
            for (const width of [360, 390, 430, 844, 1366, 1920]) for (const font of [16, 18]) {
                iframe.style.width = width + 'px'; doc.documentElement.style.fontSize = font + 'px';
                await delay(25);
                const button = doc.querySelector('.tt-camera-trigger'), b = button.getBoundingClientRect();
                const input = doc.querySelector('#codeInput, #scanInput'), r = input.getBoundingClientRect();
                const result = {path, width, font, pageWidth: doc.documentElement.scrollWidth, buttonWidth: b.width,
                    buttonHeight: b.height, inputWidth: r.width, buttonInViewport: b.left >= 0 && b.right <= width,
                    overlap: b.left < r.right && b.right > r.left && b.top < r.bottom && b.bottom > r.top};
                geometry.push(result);
                assert(result.pageWidth <= width && result.buttonInViewport && !result.overlap && r.width > 55,
                    'Layout overflow: ' + JSON.stringify(result));
                const choosing = win.TTCodeSearch.choose([{code: '90001', name: 'SYN '.repeat(40)}, {code: '90002', name: 'SYN'}], button);
                const dialog = doc.querySelector('dialog'), d = dialog.getBoundingClientRect();
                assert(d.left >= 0 && d.right <= width && dialog.scrollWidth <= dialog.clientWidth, 'Choice dialog overflow');
                doc.querySelector('.tt-camera-close').click(); await choosing;
            }
        }
    });
    window.cameraTestResults = {scope: 'loopback synthetic API + fake media + real decoder on independent PNG labels', results,
        geometry, pass: results.filter(x => x.status === 'PASS').length, fail: results.filter(x => x.status !== 'PASS').length};
    document.getElementById('result').textContent = JSON.stringify(window.cameraTestResults, null, 2);
    this.disabled = false;
};
