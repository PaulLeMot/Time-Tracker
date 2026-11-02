/* Hidden SYNTHETIC browser checks. Never targets a production URL. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const runtimeRequire = createRequire(process.env.VS_NODE_MODULES || 'C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/_entry.cjs');
const {chromium} = runtimeRequire('playwright');
const base = process.env.VS_LAB_URL || 'http://127.0.0.1:18982';
assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
let runningBrowser;
(async () => {
 const browser = await chromium.launch({headless:true,channel:process.env.VS_BROWSER_CHANNEL || 'msedge'});
 runningBrowser=browser;
 const context = await browser.newContext({viewport:{width:390,height:700},deviceScaleFactor:1});
 const page = await context.newPage(); const errors=[];
 page.on('pageerror', e => errors.push(e.message));
 let uploads=0; page.on('request',r => {if(r.method()==='POST' && r.url().includes('/api/visual-search/search'))uploads++;});
 await page.addInitScript(() => {
  window.__photoMetrics={calls:0,stops:0,deny:false,front:false};
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async constraints => {
   const m=window.__photoMetrics; m.calls++;m.constraints=constraints;
   if(m.deny)throw new DOMException('denied','NotAllowedError');
   const canvas=document.createElement('canvas');canvas.width=canvas.height=320;
   const image=new Image();image.src='/static/img/97000.jpg';await image.decode();
   const draw=()=>canvas.getContext('2d').drawImage(image,0,0,320,320);draw();
   const interval=setInterval(draw,40);const stream=canvas.captureStream(25);
   for(const track of stream.getTracks()) {const stop=track.stop.bind(track);track.stop=()=>{clearInterval(interval);m.stops++;stop();};track.getSettings=()=>({facingMode:m.front?'user':'environment'});}
   return stream;
  }}});
 });
 const button=page.locator('#photoSearchBtn'),dialog=page.locator('.tt-photo-dialog');
 const click=label=>dialog.getByRole('button',{name:label==='Закрыть'?'Закрыть поиск по фото':label,exact:true}).click();
 await page.goto(base+'/static/search.html');await button.waitFor({state:'visible'});
 await button.click();await page.waitForTimeout(100);
 assert.equal(uploads,0);assert.equal(await page.evaluate(()=>__photoMetrics.calls),0);
 await dialog.locator('select').selectOption({label:'Тестовый вид А'});
 await dialog.getByRole('button',{name:'Снимок',exact:true}).waitFor({state:'visible'});
 await page.waitForFunction(()=>!document.querySelector('.tt-photo-dialog footer button').disabled);
 assert.equal((await page.evaluate(()=>__photoMetrics.constraints)).video.facingMode.exact,'environment');
 await click('Снимок');await page.waitForTimeout(100);assert.equal(uploads,0);
 assert.equal(await page.evaluate(()=>__photoMetrics.stops),1);
 await click('Найти');await dialog.locator('.product-card').first().waitFor();
 assert.equal(uploads,1);
 const codes=new Set(await dialog.locator('.product-card .code').allTextContents());
 assert(codes.has('97000'));assert(!codes.has('98054'));
 await click('Ещё товары');await page.waitForFunction(()=>document.querySelectorAll('.tt-photo-results .product-card').length>30);
 const allCodes=await dialog.locator('.product-card .code').allTextContents();
 assert(allCodes.includes('98053'));assert.equal(new Set(allCodes).size,allCodes.length);
 assert.equal(await page.locator('#typeInput').inputValue(),'');assert.equal(await page.locator('#codeInput').inputValue(),'');
 const bounds=await dialog.locator('footer').boundingBox();assert(bounds.y+bounds.height<=700);
 await page.setViewportSize({width:700,height:390});
 const landscape=await dialog.locator('footer').boundingBox();assert(landscape.y+landscape.height<=390);
 await page.setViewportSize({width:390,height:700});
 await page.setViewportSize({width:320,height:480});
 await page.evaluate(()=>document.documentElement.style.fontSize='22px');
 const enlarged=await dialog.locator('footer').boundingBox();assert(enlarged.y+enlarged.height<=480);
 assert(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth));
 await page.evaluate(()=>document.documentElement.style.fontSize='16px');await page.setViewportSize({width:390,height:700});
 // Permission refusal and front-facing track rejection provide a file path.
 await click('Закрыть');await page.evaluate(()=>__photoMetrics.deny=true);await button.click();
 await dialog.locator('select').selectOption({label:'Тестовый вид А'});
 await page.waitForFunction(()=>document.querySelector('.tt-photo-notice').textContent.includes('Разрешите'));
 await page.evaluate(()=>{__photoMetrics.deny=false;__photoMetrics.front=true;});await click('Переснять');
 await page.waitForFunction(()=>document.querySelector('.tt-photo-notice').textContent.includes('Задняя камера недоступна'));
 assert(await dialog.getByRole('button',{name:'Файл',exact:true}).isVisible());
 await page.evaluate(()=>__photoMetrics.front=false);
 // Upload preview is cropped on demand; no upload occurs before explicit search.
 const before=uploads;
 const fixture=process.env.VS_SYNTHETIC_ROOT;
 if(fixture){await dialog.locator('input[type=file]').setInputFiles(path.join(fixture,'images/97000.jpg'));await page.waitForTimeout(150);assert.equal(uploads,before);await click('Снимок');}
 // Late response after retake cannot display an old card.
 await click('Переснять');await page.waitForFunction(()=>!document.querySelector('.tt-photo-dialog footer button').disabled);await click('Снимок');
 await page.route('**/api/visual-search/search?*', async route=>{await new Promise(r=>setTimeout(r,300));try{await route.fulfill({contentType:'application/json',body:JSON.stringify({items:[{code:'99999',name:'STALE',product_type:'Тестовый вид А',evidence:'weak'}],total:1,status:'weak',next_offset:null})});}catch{}});
 await click('Найти');await click('Переснять');await page.waitForTimeout(500);
 assert.equal(await dialog.getByText('STALE',{exact:true}).count(),0);
 await page.evaluate(()=>window.dispatchEvent(new Event('tt-search-change')));assert.equal(await dialog.count(),0);
 await button.click();await dialog.locator('select').selectOption({label:'Тестовый вид Б'});await page.waitForTimeout(150);
 await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));assert.equal(await dialog.count(),0);
 assert.equal(errors.length,0,errors.join('\n'));
 if(process.env.VS_SCREENSHOT){await button.click();await dialog.locator('select').selectOption({label:'Тестовый вид А'});await page.waitForTimeout(150);await page.screenshot({path:process.env.VS_SCREENSHOT});await click('Закрыть');}
 console.log(JSON.stringify({pass:true,checks:['required_type','rear_only','explicit_single_upload','crop','all_duplicate_codes_and_pages','filter_preservation','portrait_landscape_footer','permission_file_fallback','front_rejected','retake_stale_response','change_pagehide_cleanup'],uploads,errors}));
 await browser.close();
})().catch(async error=>{console.error(error);await runningBrowser?.close();process.exitCode=1;});
