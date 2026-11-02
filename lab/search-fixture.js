/* Synthetic fixture, loaded before the real page only by the loopback search lab. */
'use strict';
(() => {
    const state = window.SearchLab = {calls: [], options: [], mode: 'normal', products: 150, pageSize: 30, nativeFetch: window.fetch.bind(window)};
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const NativeObserver = window.IntersectionObserver;
    window.IntersectionObserver = class extends NativeObserver {
        constructor(callback, options) { super(callback, options); state.options.push(options || {}); }
    };
    window.fetch = async (url, options = {}) => {
        const parsed = new URL(String(url), location.href);
        if (!parsed.pathname.startsWith('/api/products/')) return state.nativeFetch(url, options);
        const call = {path: parsed.pathname, query: Object.fromEntries(parsed.searchParams), at: performance.now()};
        state.calls.push(call);
        const isOptions = parsed.pathname.endsWith('filter-options');
        const type = parsed.searchParams.get('product_type') || '';
        if (isOptions) {
            await sleep(state.mode === 'slow-options' ? 700 : state.mode === 'racing-options' && type === 'SYN A' ? 500 : 20);
            if (state.mode === 'failed-options') throw Error('Synthetic options failure');
            // Ignore abort intentionally: prove request-generation protection independently.
            return {ok: true, json: async () => ({product_types: ['SYN A','SYN B'], fandoms: [type || 'SYN']})};
        }
        await sleep(80);
        if (options.signal?.aborted && !state.ignoreAbort) throw new DOMException('Aborted','AbortError');
        const offset = Number(parsed.searchParams.get('offset') || 0), limit = Number(parsed.searchParams.get('limit') || 30);
        if (state.mode === 'failed-page' && offset > 0) return {ok:false};
        const total = state.products;
        const count = state.mode === 'empty-page' && offset > 0 ? 0 : Math.min(state.pageSize,limit,Math.max(0,total-offset));
        return {ok:true,json:async()=>({total,items:Array.from({length:count},(_,i)=>({id:offset+i,code:String(90000+offset+i),name:`Синтетический товар ${type || 'ALL'} ${offset+i+1}`,product_type:type||'SYN A',fandom:'SYN',image_url:'/lab/labels/mobile-portrait.png?synthetic='+String(offset+i)}))})};
    };
    window.addEventListener('unhandledrejection', e => { state.unhandled = (state.unhandled || 0)+1; e.preventDefault(); });
})();
