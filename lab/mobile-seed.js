/* Synthetic lab only; the production page never includes this script. */
'use strict';
const fixture = new URLSearchParams(location.search);
document.documentElement.style.fontSize = (fixture.get('font') === '18' ? '18' : '16') + 'px';
document.addEventListener('DOMContentLoaded', async () => {
    await new Promise(resolve => setTimeout(resolve, 100));
    const code = {portrait: 'MOBILE-DEMO', wide: 'MOBILE-WIDE', missing: 'MOBILE-MISSING', many: 'MOBILE-MANY', empty: 'UNKNOWN'}[fixture.get('fixture')];
    if (code) await performScan(code);
    document.documentElement.dataset.fixtureReady = 'true';
});
