'use strict';
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
const check = (ok,message) => { if(!ok) throw Error(message); };
async function until(fn, timeout=2000) { const start=performance.now();while(!fn()){if(performance.now()-start>timeout)throw Error('Timeout');await sleep(10);} }
document.getElementById('run').onclick = async function () {
    this.disabled=true;const results=[];const baseline=new URLSearchParams(location.search).has('baseline');
    async function frame(width=390,height=844) {
        const iframe=document.createElement('iframe');iframe.style.cssText=`display:block;width:${width}px;height:${height}px;border:0`;
        document.getElementById('frame').replaceChildren(iframe);iframe.src=baseline?'/baseline-search':'/search';
        await new Promise(resolve=>iframe.onload=resolve);
        const win=iframe.contentWindow;await until(()=>win.document.querySelectorAll('.product-card').length>=30);
        await sleep(50);win.SearchLab.calls=[];return {win,doc:win.document,iframe};
    }
    function select(doc,value) { const input=doc.getElementById('typeInput');input.focus();[...doc.querySelectorAll('#typeDropdown .dropdown-item')].find(el=>el.textContent===value).dispatchEvent(new MouseEvent('mousedown',{bubbles:true})); }
    async function test(name,fn) {try{const detail=await fn();results.push({name,pass:true,...detail});}catch(e){results.push({name,pass:false,error:e.message});}document.getElementById('result').textContent=JSON.stringify(results,null,2);}
    await test('filter results start before slow option refresh',async()=>{
        const {win,doc}=await frame();win.SearchLab.mode='slow-options';const start=performance.now();select(doc,'SYN A');
        await until(()=>win.SearchLab.calls.some(c=>c.path.endsWith('/filtered')),1200);
        const elapsed=performance.now()-start;check(elapsed<200,'Products wait for filter options: '+Math.round(elapsed)+'ms');return {productRequestMs:Math.round(elapsed)};
    });
    await test('option refresh failure does not stop products',async()=>{
        const {win,doc}=await frame();win.SearchLab.mode='failed-options';select(doc,'SYN B');
        await sleep(250);check(win.SearchLab.calls.some(c=>c.path.endsWith('/filtered')&&c.query.product_type==='SYN B'),'No products after options failure');
        check(doc.querySelector('.name').textContent.includes('SYN B'),'Old products remain after changed type');
    });
    await test('late option response cannot overwrite newer type',async()=>{
        const {win,doc}=await frame();win.SearchLab.mode='racing-options';select(doc,'SYN A');await sleep(30);select(doc,'SYN B');await sleep(650);
        const input=doc.getElementById('fandomInput');input.focus();check([...doc.querySelectorAll('#fandomDropdown .dropdown-item')].some(el=>el.textContent==='SYN B'),'Late SYN A overwrote options');
        check(doc.querySelector('.name').textContent.includes('SYN B'),'Wrong type displayed');
    });
    await test('prefetch starts before reaching the last row',async()=>{
        const {win,doc}=await frame();const distance=parseFloat(win.SearchLab.options[0]?.rootMargin||'0');
        check(distance>=600,'No advance loading margin');
        const sentinel=doc.getElementById('scrollSentinel');win.scrollTo(0,sentinel.getBoundingClientRect().top+win.scrollY-win.innerHeight-300);
        await until(()=>doc.querySelectorAll('.product-card').length>=60);return {prefetchMargin:distance,cards:doc.querySelectorAll('.product-card').length};
    });
    await test('offscreen images defer loading; decode asynchronously',async()=>{
        const {doc}=await frame();const images=[...doc.querySelectorAll('.product-card img')];
        check(images.slice(8).every(img=>img.loading==='lazy'),'All 30 images compete immediately');
        check(images.every(img=>img.decoding==='async'),'Image decode is synchronous/default');
    });
    await test('short pages fill viewport without a second scroll edge',async()=>{
        const {win,doc}=await frame(1280,900);win.SearchLab.pageSize=2;win.SearchLab.products=8;win.resetAndLoad();
        await until(()=>doc.querySelectorAll('.product-card').length===8,1800);
        const offsets=win.SearchLab.calls.filter(c=>c.path.endsWith('/filtered')).map(c=>c.query.offset);
        check(new Set(offsets).size===offsets.length,'Duplicate offset requests');return {offsets};
    });
    await test('typing does not append a later old page during debounce',async()=>{
        const {win,doc}=await frame();const input=doc.getElementById('codeInput');input.value='NEW';input.dispatchEvent(new Event('input'));
        await win.loadProducts();await sleep(100);
        check(!win.SearchLab.calls.some(c=>c.query.code==='NEW'&&Number(c.query.offset)>0),'New input fetched old offset before reset');
    });
    await test('empty page with inconsistent total cannot request forever',async()=>{
        const {win,doc}=await frame(1280,900);win.SearchLab.mode='empty-page';win.SearchLab.pageSize=2;win.SearchLab.products=8;win.resetAndLoad();await sleep(650);
        const before=win.SearchLab.calls.filter(c=>c.path.endsWith('/filtered')).length;await win.loadProducts();await sleep(150);
        check(win.SearchLab.calls.filter(c=>c.path.endsWith('/filtered')).length===before,'Empty page keeps hasMore active');
    });
    await test('failed next page retries same offset without clearing cards',async()=>{
        const {win,doc}=await frame();win.SearchLab.mode='failed-page';await win.loadProducts();
        check(doc.querySelectorAll('.product-card').length===30,'Existing page lost on error');
        const retry=doc.querySelector('#cameraSearchNotice button');check(retry?.textContent==='Повторить загрузку','Retry missing');
        win.SearchLab.mode='normal';retry.click();await until(()=>doc.querySelectorAll('.product-card').length===60);
        check(win.SearchLab.calls.filter(c=>c.query.offset==='30').length===2,'Retry changed page offset');
    });
    await test('cancelled/no-match barcode preserves further pagination',async()=>{
        const {win,doc}=await frame();win.TTCodeSearch.resolveImage=async()=>[];
        await win.findCameraImage({rawValue:'UNKNOWN',format:'CODE_128'});await win.loadProducts();
        check(doc.querySelectorAll('.product-card').length===60,'Barcode no-match blocked previous pagination');
    });
    await test('late page cannot append after changing type even if abort ignored',async()=>{
        const {win,doc}=await frame();win.SearchLab.ignoreAbort=true;const old=win.loadProducts();select(doc,'SYN B');await old;await sleep(150);
        const cards=[...doc.querySelectorAll('.product-card')];
        check(cards.length===30 && cards.every(el=>el.querySelector('.name').textContent.includes('SYN B')),'Old page leaked into new type');
    });
    await test('all remaining pages reachable once without duplicates or runaway fetch',async()=>{
        const {win,doc}=await frame();
        for(let step=0;step<4;step++) {win.scrollTo(0,doc.documentElement.scrollHeight);await until(()=>doc.querySelectorAll('.product-card').length>=60+step*30);}
        const codes=[...doc.querySelectorAll('.product-card .code')].map(el=>el.textContent);
        check(codes.length===150&&new Set(codes).size===150,'Missing or duplicated products');
        const requests=win.SearchLab.calls.length;await win.loadProducts();await sleep(100);check(win.SearchLab.calls.length===requests,'Fetch continued past total');
    });
    await test('back-forward cache restores pagination after pagehide',async()=>{
        const {win,doc}=await frame();
        win.dispatchEvent(new win.PageTransitionEvent('pagehide',{persisted:true}));
        await win.loadProducts();check(doc.querySelectorAll('.product-card').length===30,'Hidden page kept loading');
        win.dispatchEvent(new win.PageTransitionEvent('pageshow',{persisted:true}));
        await win.loadProducts();check(doc.querySelectorAll('.product-card').length===60,'Restored page cannot paginate');
    });
    document.getElementById('frame').replaceChildren();
    document.getElementById('result').textContent=JSON.stringify({baseline,pass:results.filter(x=>x.pass).length,fail:results.filter(x=>!x.pass).length,results},null,2);this.disabled=false;
};
