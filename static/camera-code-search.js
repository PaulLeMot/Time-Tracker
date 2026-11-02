/* Read-only adapters for existing TimeTracker APIs. No DB or marketplace reimplementation. */
(function (root) {
    'use strict';
    const formats = new Set(['EAN_13', 'CODE_128']);
    class SearchError extends Error {
        constructor(kind, message) { super(message); this.kind = kind; }
    }
    function validate({rawValue, format}) {
        if (!formats.has(format)) throw new SearchError('unsupported_format', 'Поддерживаются штрихкоды EAN-13 и Code 128.');
        if (typeof rawValue !== 'string' || rawValue.length > 128) throw new SearchError('payload_too_long', 'Штрихкод слишком длинный. Введите артикул вручную.');
        // Same alphabet as the manual marking flow. Never strip leading zeros or GS1 fields.
        if (!/^[A-Za-zА-Яа-я0-9_-]{5,128}$/.test(rawValue)) throw new SearchError('unsupported_payload', 'Этот штрихкод не поддерживается. Введите артикул вручную.');
        if (format === 'EAN_13' && !validEAN(rawValue)) throw new SearchError('invalid_ean', 'Штрихкод EAN-13 повреждён. Повторите сканирование.');
        // The old backend slices this reserved 13-character prefix even when it
        // arrived as Code128. Guard that conversion before calling it.
        if (rawValue.startsWith('2400000') && rawValue.length === 13 && !validEAN(rawValue))
            throw new SearchError('invalid_ean', 'Внутренний штрихкод повреждён. Повторите сканирование.');
        return rawValue;
    }
    function validEAN(value) {
        if (!/^\d{13}$/.test(value)) return false;
        let sum = 0;
        for (let i = 0; i < 12; i++) sum += Number(value[i]) * (i % 2 ? 3 : 1);
        return (10 - sum % 10) % 10 === Number(value[12]);
    }
    function canonical(raw) {
        return raw.startsWith('2400000') && validEAN(raw) ? raw.slice(7, 12) : raw;
    }
    async function request(url, {signal, transport = root.fetch.bind(root)} = {}) {
        let response;
        try { response = await transport(url, {credentials: 'include', signal}); }
        catch (error) {
            if (error.name === 'AbortError') throw error;
            throw new SearchError('network', 'Нет соединения с сервером. Повторите поиск.');
        }
        if (response.status === 401 || response.status === 403) throw new SearchError('auth', 'Сеанс завершён или доступ запрещён. Войдите в портал заново.');
        let data;
        try { data = await response.json(); } catch (_) { throw new SearchError('source', 'Сервер вернул неподдерживаемый ответ. Повторите поиск позже.'); }
        if (response.status === 404) {
            // Existing backend also uses 404 for missing XLSX. Do not confuse it with a missing product.
            if (/файл|xlsx|csv|источник/i.test(String(data.detail || '')) && !/QR-код не найден/i.test(String(data.detail || '')))
                throw new SearchError('source', 'Таблица сопоставлений сейчас недоступна. Повторите поиск позже.');
            return null;
        }
        if (!response.ok) throw new SearchError('source', 'Источник сопоставлений или сервер сейчас недоступен. Повторите поиск позже.');
        return data;
    }
    function markingMatches(product, marking, raw) {
        if (!marking) return true;
        // The internal FSK label is universal; marketplace matches must retain the exact platform context.
        return (raw.startsWith('2400000') && validEAN(raw)) ||
            (/^\d{5}$/.test(raw) && String(product['Код']) === raw && product['Маркировка'] === 'FSK') ||
            (product.found_markings || []).includes(marking);
    }
    function candidates(data, marking, raw) {
        const seen = new Set();
        return (Array.isArray(data) ? data : []).filter(p => {
            if (p.similar_sticker_match || !markingMatches(p, marking, raw) || !p['Код']) return false;
            const key = JSON.stringify([p['Код'], p['Вид'], p['Фандом'], p['Название']]);
            if (seen.has(key)) return false;
            seen.add(key); return true;
        });
    }
    async function lookupMark(raw, marking = '', options = {}) {
        const url = '/api/mark/' + encodeURIComponent(raw) + (marking ? '?marking=' + encodeURIComponent(marking) : '');
        const data = await request(url, options);
        if (data !== null && !Array.isArray(data)) throw new SearchError('source', 'Сервер вернул неподдерживаемый ответ. Повторите поиск позже.');
        return {items: candidates(data, marking, raw), related: (data || []).filter(p => p.similar_sticker_match)};
    }
    async function resolveImage(decoded, options = {}) {
        const raw = validate(decoded);
        const exact = await request('/api/products/' + encodeURIComponent(canonical(raw)), options);
        if (exact && (typeof exact.code !== 'string' || typeof exact.name !== 'string')) throw new SearchError('source', 'Сервер вернул неподдерживаемый ответ. Повторите поиск позже.');
        if (exact) return [{code: exact.code, name: exact.name, product: exact, marking: 'FSK'}];
        const result = await lookupMark(raw, '', options);
        return result.items.map(p => ({code: p['Код'], name: p['Название'], marking: p['Маркировка'] || 'FSK',
            product_type: p['Вид'], fandom: p['Фандом']}));
    }
    function articleCandidates(text) {
        if (typeof text !== 'string' || text.length > 1500) return [];
        const scored = new Map();
        const add = (value, score, read = value, alternative = false) => {
            if (/^[A-Za-zА-Яа-я0-9_-]{5,64}$/.test(value) && !/\s/.test(value))
                if (!scored.has(value) || scored.get(value).score < score) scored.set(value, {value, score, read, alternative});
        };
        for (const line of text.normalize('NFKC').replace(/https?:\/\/\S+/gi, '').split(/[\r\n]/).slice(0, 35)) {
            const explicit = /(?:sku|article|артикул|арт\.|код)\s*[:#№]?/i.test(line) ? 20 : 0;
            for (const token of line.match(/[A-Za-zА-Яа-я0-9_-]+/g) || []) {
                if (token.length > 64 || !/\d{5}/.test(token)) continue;
                const groups = token.match(/\d+/g) || [];
                const embedded = groups.filter(group => group.length === 5);
                if (/^\d{5}$/.test(token)) add(token, 80 + explicit);
                else if (embedded.length && /[A-Za-zА-Яа-я_-]/.test(token)) {
                    add(token, 95 + explicit); embedded.forEach(code => add(code, 75 + explicit));
                } else if (/^\d{6,20}$/.test(token)) add(token, 10 + explicit);
            }
            // A common printed O+five-digit SKU may be read as zero+five digits.
            // Consider only that bounded ambiguity immediately after an explicit
            // article label. Keep the original reading and require confirmation;
            // never apply general fuzzy substitutions or slice long IDs.
            for (const match of line.matchAll(/(?:sku|article|артикул|арт\.|код)\s*[:#№]?\s*(0\d{5})(?![A-Za-zА-Яа-я0-9_-])/gi)) {
                add('O' + match[1].slice(1), 65, match[1], true);
                add(match[1].slice(1), 60, match[1], true);
            }
        }
        // Never extract a five-digit substring from a longer numeric ID/order number.
        return [...scored.values()].sort((a, b) => b.score - a.score).slice(0, 6);
    }
    function textTokens(text) { return articleCandidates(text).map(candidate => candidate.value); }
    async function resolveText(text, options = {}) {
        const tokens = articleCandidates(text);
        if (!tokens.length) throw new SearchError('no_article', 'Артикул в тексте не найден. Наведите на код товара или введите его вручную.');
        const found = new Map();
        for (const candidate of tokens) {
            const raw = candidate.value;
            if (options.signal?.aborted) throw new DOMException('Отменено', 'AbortError');
            const matches = options.mode === 'mark'
                ? (await lookupMark(raw, options.marking || '', options)).items.map(item => ({code: item['Код'], name: item['Название'],
                    marking: item['Маркировка'], markItem: item, product_type: item['Вид'], fandom: item['Фандом']}))
                : await resolveImage({rawValue: raw, format: 'CODE_128'}, options);
            for (const item of matches) {
                const key = JSON.stringify([item.code, item.name, item.product_type || item.product?.product_type, item.fandom || item.product?.fandom]);
                if (!found.has(key)) found.set(key, {...item, rawValue: raw, textSources: [candidate.read], textAlternative: candidate.alternative});
                else { const previous = found.get(key); if (!previous.textSources.includes(candidate.read)) previous.textSources.push(candidate.read);
                    if (!candidate.alternative) previous.textAlternative = false; }
            }
        }
        return [...found.values()];
    }
    // Shared choice UI: stream is already stopped; OCR always requires confirmation,
    // including a single catalog match (existence alone does not prove OCR accuracy).
    function choose(items, trigger, signal, options = {}) {
        if (signal?.aborted) return Promise.resolve(null);
        if (!items.length || (items.length < 2 && !options.confirm)) return Promise.resolve(items[0] || null);
        return new Promise(resolve => {
            const dialog = document.createElement('dialog');
            dialog.className = 'tt-camera-dialog'; dialog.setAttribute('aria-label', options.confirm ? 'Подтверждение артикула' : 'Выбор товара');
            dialog.innerHTML = '<div class="tt-camera-head"><h2></h2><button class="tt-camera-close" type="button" aria-label="Закрыть">×</button></div><p class="tt-camera-choice-description"></p><div class="tt-camera-choices"></div><div class="tt-camera-actions"><button type="button" class="tt-camera-reject"></button></div>';
            dialog.querySelector('h2').textContent = options.confirm ? 'Проверьте найденный артикул' : 'Найдено несколько товаров';
            dialog.querySelector('.tt-camera-choice-description').textContent = options.confirm
                ? 'Текст распознан камерой. Подтвердите товар перед показом результата. Если он не подходит, повторите сканирование.'
                : 'Выберите товар. При необходимости уточните маркировку.';
            let done = false;
            function finish(item) {
                if (done) return; done = true;
                signal?.removeEventListener('abort', abort);
                root.removeEventListener('pagehide', abort);
                root.removeEventListener('popstate', abort);
                document.removeEventListener('visibilitychange', hidden);
                if (dialog.open) dialog.close(); dialog.remove();
                if (trigger?.isConnected && !document.hidden) trigger.focus({preventScroll: true});
                resolve(item);
            }
            const abort = () => finish(null);
            const hidden = () => { if (document.hidden) abort(); };
            items.forEach(item => {
                const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'tt-camera-choice';
                btn.textContent = (options.confirm ? 'Подтвердить: ' : '') +
                    [item.code || item['Код'], item.name || item['Название'], item.product_type || item.product?.product_type || item['Вид'],
                        item.fandom || item.product?.fandom || item['Фандом'], item.marking || item['Маркировка'] || 'FSK'].filter(Boolean).join(' · ');
                if (options.confirm && item.textSources?.length) {
                    const source = document.createElement('small'); source.className = 'tt-camera-source';
                    source.textContent = 'Прочитано на этикетке: ' + item.textSources.join(', ') +
                        (item.textAlternative ? ' · Возможная путаница O / 0. Внимательно проверьте товар.' : ''); btn.append(source);
                }
                btn.onclick = () => finish(item); dialog.querySelector('.tt-camera-choices').append(btn);
            });
            dialog.querySelector('.tt-camera-reject').textContent = options.confirm ? 'Не подходит' : 'Отмена';
            dialog.querySelector('.tt-camera-reject').onclick = abort;
            dialog.querySelector('.tt-camera-close').onclick = abort;
            dialog.addEventListener('cancel', e => { e.preventDefault(); abort(); });
            dialog.addEventListener('close', abort);
            signal?.addEventListener('abort', abort, {once: true});
            root.addEventListener('pagehide', abort, {once: true});
            root.addEventListener('popstate', abort, {once: true});
            document.addEventListener('visibilitychange', hidden);
            document.body.append(dialog);
            if (dialog.showModal) dialog.showModal(); else finish(null);
        });
    }
    root.TTCodeSearch = {validate, validEAN, canonical, lookupMark, resolveImage, textTokens, resolveText, request, choose, SearchError};
})(window);
