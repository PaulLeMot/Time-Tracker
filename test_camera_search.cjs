/* Run: node --test test_camera_search.cjs. No application startup or real API. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const window = {fetch() { throw Error('Real transport forbidden'); }};
vm.runInNewContext(fs.readFileSync('static/camera-code-search.js', 'utf8'), {window, DOMException});
const api = window.TTCodeSearch;
const response = (status, data) => ({status, ok: status >= 200 && status < 300, json: async () => data});
const item = (code, marking, similar = false) => ({'Код': code, 'Вид': 'SYN', 'Название': 'SYN ' + code,
    'Маркировка': marking, found_markings: [marking], similar_sticker_match: similar, table: []});

test('linear formats only, input bounds, leading zeros and EAN checksum', () => {
    assert.equal(api.validate({rawValue: '000090001', format: 'CODE_128'}), '000090001');
    assert.equal(api.canonical('2400000900016'), '90001');
    assert.equal(api.canonical('2900000000018'), '2900000000018');
    for (const rawValue of ['https://example.invalid/90001', '<img src=x>', 'X'.repeat(129), '12345\u001d90001', '1234', '90001\n'])
        assert.throws(() => api.validate({rawValue, format: 'CODE_128'}));
    assert.throws(() => api.validate({rawValue: '90001', format: 'QR_CODE'}));
    assert.throws(() => api.validate({rawValue: '2400000900015', format: 'EAN_13'}));
    assert.throws(() => api.validate({rawValue: '2400000900015', format: 'CODE_128'}));
    assert.throws(() => api.validate({rawValue: '2400000ABCDEF', format: 'CODE_128'}));
});

test('canonical exact request preserves zeros, no substring endpoint or second mapping', async () => {
    const calls = [];
    const items = await api.resolveImage({rawValue: '2400000900016', format: 'EAN_13'}, {transport: async url => {
        calls.push(url); return response(200, {code: '90001', name: 'SYN'});
    }});
    assert.equal(items[0].code, '90001'); assert.deepEqual(calls, ['/api/products/90001']);
});

test('marketplace mapping reuses existing endpoint and keeps 0/1/N candidates', async () => {
    const calls = [];
    const transport = async url => {
        calls.push(url);
        return url.startsWith('/api/products/') ? response(404, {detail: 'Товар не найден'})
            : response(200, [item('90001', 'sia_WB'), item('90002', 'kpd_WB'), item('90003', 'sia_WB', true)]);
    };
    const items = await api.resolveImage({rawValue: 'DEMO-COLLISION', format: 'CODE_128'}, {transport});
    assert.equal(items.length, 2);
    assert.deepEqual(calls, ['/api/products/DEMO-COLLISION', '/api/mark/DEMO-COLLISION']);
    const filtered = await api.lookupMark('DEMO-COLLISION', 'kpd_WB', {transport});
    assert.equal(filtered.items.length, 1); assert.equal(filtered.items[0]['Код'], '90002');
    assert.equal(calls.at(-1), '/api/mark/DEMO-COLLISION?marking=kpd_WB');
});

test('full platform context, similar stickers excluded and identical duplicates collapsed', async () => {
    const transport = async () => response(200, [item('90001', 'sia_OZ'), item('90002', 'sia_WB'), item('90002', 'sia_WB')]);
    const result = await api.lookupMark('2900000000018', 'sia_WB', {transport});
    assert.equal(result.items.length, 1); assert.equal(result.items[0]['Код'], '90002');
    const fsk = await api.lookupMark('2400000900016', 'kpd_WB', {transport: async () => response(200, [item('90001', 'FSK')])});
    assert.equal(fsk.items.length, 1);
});

test('no-match, expired auth, unavailable source and offline remain distinct', async () => {
    assert.equal(await api.request('/stub', {transport: async () => response(404, {detail: 'Товар не найден'})}), null);
    for (const [status, detail, kind] of [[401, '', 'auth'], [403, '', 'auth'], [404, 'Файл /SYN/source.xlsx не найден', 'source'], [500, '', 'source']])
        await assert.rejects(api.request('/stub', {transport: async () => response(status, {detail})}), error => error.kind === kind);
    await assert.rejects(api.request('/stub', {transport: async () => { throw Error('offline'); }}), error => error.kind === 'network');
});

test('cancel signal is forwarded and abort is not converted to no-match', async () => {
    const controller = new AbortController(); controller.abort();
    await assert.rejects(api.lookupMark('90001', '', {signal: controller.signal, transport: async (_, options) => {
        assert.equal(options.credentials, 'include'); assert.equal(options.signal, controller.signal);
        const error = Error(); error.name = 'AbortError'; throw error;
    }}), {name: 'AbortError'});
});

test('unsafe camera payload triggers zero lookups', async () => {
    let calls = 0;
    await assert.rejects(api.resolveImage({rawValue: '<script>90001</script>', format: 'CODE_128'}, {transport: async () => { calls++; }}));
    assert.equal(calls, 0);
});

test('OCR extracts articles inside text, keeps zeros and never slices long numeric IDs', () => {
    assert.deepEqual(Array.from(api.textTokens('SYN PRODUCT\nSKU: O90001_BLUE\nORDER 1234567890123')),
        ['O90001_BLUE', '90001', '1234567890123']);
    assert.deepEqual(Array.from(api.textTokens('Артикул: 00001\nhttps://example.invalid/90002')), ['00001']);
    assert.deepEqual(Array.from(api.textTokens('1900010')), ['1900010']);
    assert.deepEqual(Array.from(api.textTokens('O9OOO1')), []);
    assert.deepEqual(Array.from(api.textTokens('ORDER 090001')), ['090001']);
    assert.deepEqual(Array.from(api.textTokens('SKU: 090001')), ['O90001', '90001', '090001']);
    assert.ok(!api.textTokens('SKU: 0900012345').includes('90001'));
    assert.equal(api.textTokens('90001 '.repeat(400)).length, 0);
    assert.ok(api.textTokens('10001 10002 10003 10004 10005 10006 10007').length <= 6);
});

test('OCR uses existing exact/mapping lookups, merges aliases and preserves different products', async () => {
    const calls = [];
    const transport = async url => {
        calls.push(url);
        if (url === '/api/products/90001') return response(200, {code: '90001', name: 'SYN 90001', product_type: 'SYN'});
        if (url.startsWith('/api/products/')) return response(404, {});
        return response(200, [item('90001', 'sia_OZ'), item('90002', 'sia_WB')]);
    };
    const result = await api.resolveText('SKU O90001', {transport});
    assert.equal(result.length, 2);
    assert.ok(calls.includes('/api/mark/O90001'));
    assert.ok(calls.every(url => !url.includes('filtered')));
    const marking = await api.resolveText('SKU O90001', {mode: 'mark', marking: 'sia_OZ', transport});
    assert.equal(marking.length, 1); assert.equal(marking[0].code, '90001');
});

test('OCR bounded O/0 variant retains the original reading and demands UI confirmation', async () => {
    const result = await api.resolveText('SKU: 090001', {transport: async url => {
        if (url === '/api/products/90001') return response(200, {code: '90001', name: 'SYN'});
        return url.startsWith('/api/products/') ? response(404, {}) : response(200, []);
    }});
    assert.equal(result.length, 1); assert.equal(result[0].textAlternative, true);
    assert.deepEqual(Array.from(result[0].textSources), ['090001']);
});

test('OCR internal five-digit FSK is accepted in marketplace context, related stickers excluded', async () => {
    const result = await api.resolveText('ARTICLE 00001', {mode: 'mark', marking: 'kpd_WB',
        transport: async () => response(200, [item('00001', 'FSK'), item('00002', 'FSK', true)])});
    assert.equal(result.length, 1); assert.equal(result[0].code, '00001');
});

test('OCR failures and cancellation cannot produce a partial candidate result', async () => {
    const transport = async url => url.endsWith('/90001') ? response(200, {code: '90001', name: 'SYN'}) : response(500, {});
    await assert.rejects(api.resolveText('90001 90002', {transport}), error => error.kind === 'source');
    const controller = new AbortController(); controller.abort();
    await assert.rejects(api.resolveText('90001', {signal: controller.signal, transport}), {name: 'AbortError'});
    await assert.rejects(api.resolveText('NO ARTICLE', {transport}), error => error.kind === 'no_article');
});
