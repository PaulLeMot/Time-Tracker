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
        return (raw.startsWith('2400000') && validEAN(raw)) || (product.found_markings || []).includes(marking);
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
        return result.items.map(p => ({code: p['Код'], name: p['Название'], marking: p['Маркировка'] || 'FSK'}));
    }
    // Shared choice UI: stream is already stopped; no implicit data[0] on ambiguous mappings.
    function choose(items, trigger, signal) {
        if (signal?.aborted) return Promise.resolve(null);
        if (items.length < 2) return Promise.resolve(items[0] || null);
        return new Promise(resolve => {
            const dialog = document.createElement('dialog');
            dialog.className = 'tt-camera-dialog'; dialog.setAttribute('aria-label', 'Выбор товара');
            dialog.innerHTML = '<div class="tt-camera-head"><h2>Найдено несколько товаров</h2><button class="tt-camera-close" type="button" aria-label="Закрыть">×</button></div><p>Выберите товар. При необходимости уточните маркировку.</p><div class="tt-camera-choices"></div>';
            let done = false;
            function finish(item) {
                if (done) return; done = true;
                signal?.removeEventListener('abort', abort);
                root.removeEventListener('pagehide', abort);
                document.removeEventListener('visibilitychange', hidden);
                if (dialog.open) dialog.close(); dialog.remove();
                if (trigger?.isConnected && !document.hidden) trigger.focus({preventScroll: true});
                resolve(item);
            }
            const abort = () => finish(null);
            const hidden = () => { if (document.hidden) abort(); };
            items.forEach(item => {
                const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'tt-camera-choice';
                btn.textContent = [item.code || item['Код'], item.name || item['Название'], item.marking || item['Маркировка'] || 'FSK'].join(' · ');
                btn.onclick = () => finish(item); dialog.querySelector('.tt-camera-choices').append(btn);
            });
            dialog.querySelector('.tt-camera-close').onclick = abort;
            dialog.addEventListener('cancel', e => { e.preventDefault(); abort(); });
            signal?.addEventListener('abort', abort, {once: true});
            root.addEventListener('pagehide', abort, {once: true});
            document.addEventListener('visibilitychange', hidden);
            document.body.append(dialog);
            if (dialog.showModal) dialog.showModal(); else finish(null);
        });
    }
    root.TTCodeSearch = {validate, validEAN, canonical, lookupMark, resolveImage, request, choose, SearchError};
})(window);
