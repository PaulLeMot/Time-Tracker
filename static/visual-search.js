/* Explicit RAM-only crop; only the selected kind may enter session storage. */
(function(root){'use strict';
function create(options){
 const button=options.button,transport=options.fetch||root.fetch.bind(root),media=options.mediaDevices||navigator.mediaDevices;
 let current=null,sequence=0,capabilities=null,user=null,savedKind,mainKind;
 const live=s=>current===s&&s.id===sequence;
 function cameraOff(s){s.stream?.getTracks().forEach(t=>t.stop());s.stream=null;s.video.pause();s.video.srcObject=null;}
 function clearFrame(s){if(s.source){s.source.width=s.source.height=0;}s.source=null;s.blob=null;if(s.processed)s.processed.width=s.processed.height=0;s.processed=null;s.showProcessed=false;s.canvas.width=s.canvas.height=0;s.points.clear();s.transform={zoom:1,angle:0,x:0,y:0};}
 function close(){const s=current;current=null;sequence++;if(!s)return;s.abort?.abort();s.cameraGeneration++;s.resizeObserver?.disconnect();root.removeEventListener('resize',s.fit);cancelAnimationFrame(s.fitFrame);cameraOff(s);clearFrame(s);s.found=null;s.dialog.close();s.dialog.remove();button.focus({preventScroll:true});options.onClose?.();}
 function notice(s,text){if(live(s)){s.notice.textContent=text;s.notice.hidden=!text;s.fit?.();}}
 function mode(s,value){s.mode=value;s.dialog.dataset.mode=value;s.tools.hidden=value!=='frame';if(s.processing){s.processing.hidden=value!=='frame'||!capabilities.enhancement?.available;s.enhance.disabled=s.busy||value!=='frame';s.auto.disabled=s.busy;s.originalButton.hidden=s.processedButton.hidden=!s.processed;s.originalButton.disabled=s.processedButton.disabled=s.busy;}s.results.hidden=value!=='results';s.stage.hidden=!['camera','frame'].includes(value);caption(s.search,value==='camera'?'Снимок':'Найти',value==='camera'?'camera':'search');s.search.disabled=s.busy||(value==='camera'?!s.cameraReady:value!=='frame'||!s.source);s.fit?.();}
 const icons={file:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"/>',clipboard:'<rect x="5" y="4" width="14" height="18" rx="2"/><rect x="9" y="2" width="6" height="4" rx="1"/>',next:'<path d="M4 12h16M14 6l6 6-6 6"/>',search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',camera:'<path d="M3 6h5l2-3h4l2 3h5v14H3z"/><circle cx="12" cy="12" r="4"/>'};
 function caption(b,text,icon){if(icon){b.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+icons[icon]+'</svg>';const label=document.createElement('span');label.textContent=text;b.append(label);}else b.textContent=text;}
 function action(text,fn,icon){const b=document.createElement('button');b.type='button';caption(b,text,icon);b.onclick=fn;return b;}
 function remember(value){savedKind=value;if(user)try{sessionStorage.setItem('tt.photo.kind.'+user,value);}catch{}}
 async function request(s,path,settings={}){
  s.abort?.abort();const c=s.abort=new AbortController(),timer=setTimeout(()=>c.abort(),settings.method==='POST'?23000:8000);
  try{const r=await transport(path,{credentials:'same-origin',cache:'no-store',...settings,signal:c.signal});
   if(!r.ok)throw Error(({401:'Войдите в личный кабинет.',403:'Нет доступа.',410:'Выдача устарела. Повторите поиск.',413:'Слишком большой снимок.',422:'Проверьте изображение и вид.',429:'Поиск занят. Повторите через несколько секунд.'})[r.status]||'Фото-поиск временно недоступен.');
   return await r.json();
  }finally{clearTimeout(timer);}
 }
 function changed(s){s.found=null;s.rendered=0;s.count.textContent='';s.count.setAttribute('aria-label','Поиск ещё не выполнен');s.operation++;s.busy=false;s.abort?.abort();s.blob=null;s.results.replaceChildren();s.more.hidden=true;mode(s,s.source?'frame':s.stream?'camera':'empty');}
 function paint(s){
  if(!s.source)return;const c=s.canvas,ctx=c.getContext('2d');c.width=c.height=960;
  const source=s.showProcessed&&s.processed?s.processed:s.source,t=s.showProcessed?{zoom:1,angle:0,x:0,y:0}:s.transform,scale=Math.min(960/source.width,960/source.height)*t.zoom;
  ctx.fillStyle='white';ctx.fillRect(0,0,960,960);ctx.save();ctx.translate(480+t.x,480+t.y);ctx.rotate(t.angle);ctx.scale(scale,scale);ctx.drawImage(source,-source.width/2,-source.height/2);ctx.restore();
  s.range.value=t.zoom;c.hidden=false;s.video.hidden=true;s.range.disabled=s.showProcessed;s.rotate.disabled=s.showProcessed;mode(s,'frame');if(s.originalButton){s.originalButton.setAttribute('aria-pressed',String(!s.showProcessed));s.processedButton.setAttribute('aria-pressed',String(s.showProcessed));}
 }
 function beginFrame(s,source){changed(s);cameraOff(s);clearFrame(s);s.source=source;s.transform={zoom:1,angle:0,x:0,y:0};paint(s);notice(s,'');}
 async function camera(s){
  if(!live(s))return;changed(s);s.frameGeneration=(s.frameGeneration||0)+1;clearFrame(s);cameraOff(s);const generation=++s.cameraGeneration;
  s.cameraReady=false;s.canvas.hidden=true;s.video.hidden=false;s.range.disabled=true;s.rotate.disabled=true;mode(s,'camera');
  notice(s,'Открываю заднюю камеру…');
  try{
   if(!root.isSecureContext||!media?.getUserMedia)throw Error('secure');
   const stream=await media.getUserMedia({audio:false,video:{facingMode:{exact:'environment'},width:{ideal:1280},height:{ideal:1280}}});
   if(!live(s)||generation!==s.cameraGeneration){stream.getTracks().forEach(t=>t.stop());return;}
   if(stream.getVideoTracks()[0]?.getSettings().facingMode!=='environment'){stream.getTracks().forEach(t=>t.stop());throw Error('rear');}
   s.stream=stream;s.video.srcObject=stream;await s.video.play();if(!live(s)||generation!==s.cameraGeneration)return;
   s.cameraReady=true;mode(s,'camera');notice(s,'');
  }catch(e){if(live(s)&&generation===s.cameraGeneration){cameraOff(s);mode(s,'empty');notice(s,e.name==='NotAllowedError'?'Разрешите камеру или выберите файл.':'Задняя камера недоступна. Выберите файл или вставьте картинку.');}}
 }
 function capture(s){
  if(!live(s)||!s.video.videoWidth)return;const c=document.createElement('canvas'),side=Math.min(s.video.videoWidth,s.video.videoHeight),size=Math.min(1600,side);
  c.width=c.height=size;c.getContext('2d').drawImage(s.video,(s.video.videoWidth-side)/2,(s.video.videoHeight-side)/2,side,side,0,0,size,size);beginFrame(s,c);
 }
 async function file(s,selected){
  if(!selected||!live(s))return;if(selected.size>16*1024*1024||!['image/jpeg','image/png','image/webp'].includes(selected.type)){notice(s,'Нужен JPEG, PNG или WebP до 16 МБ и 12 Мп.');return;}
  changed(s);s.cameraGeneration++;cameraOff(s);const frameGeneration=s.frameGeneration=(s.frameGeneration||0)+1,url=URL.createObjectURL(selected),image=new Image();
  try{image.src=url;await image.decode();if(!live(s)||frameGeneration!==s.frameGeneration)return;
   if(image.naturalWidth*image.naturalHeight>12000000||Math.min(image.naturalWidth,image.naturalHeight)<32)throw Error('Нужен снимок до 12 Мп, не меньше 32 пикселей.');
   const c=document.createElement('canvas'),scale=Math.min(1,1600/Math.max(image.naturalWidth,image.naturalHeight));c.width=Math.max(1,Math.round(image.naturalWidth*scale));c.height=Math.max(1,Math.round(image.naturalHeight*scale));c.getContext('2d').drawImage(image,0,0,c.width,c.height);beginFrame(s,c);
  }catch(e){notice(s,e.message||'Не удалось прочитать файл.');}finally{URL.revokeObjectURL(url);image.src='';}
 }
 function gestures(s){
  const position=e=>{const b=s.canvas.getBoundingClientRect();return {x:(e.clientX-b.left)*960/b.width,y:(e.clientY-b.top)*960/b.height};};
  function anchor(){const p=[...s.points.values()];if(!p.length){s.gesture=null;return;}
   const center=p.length>1?{x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2}:p[0];
   s.gesture={center,t:{...s.transform},distance:p.length>1?Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y):0,angle:p.length>1?Math.atan2(p[1].y-p[0].y,p[1].x-p[0].x):0};
  }
  s.canvas.onpointerdown=e=>{if(!s.source||s.busy||s.showProcessed)return;e.preventDefault();s.canvas.setPointerCapture(e.pointerId);s.points.set(e.pointerId,position(e));anchor();};
  s.canvas.onpointermove=e=>{
   if(!s.points.has(e.pointerId)||!s.gesture||s.busy)return;e.preventDefault();s.points.set(e.pointerId,position(e));const p=[...s.points.values()],g=s.gesture;
   const center=p.length>1?{x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2}:p[0];
   const ratio=p.length>1&&g.distance?Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y)/g.distance:1;
   const angle=p.length>1?Math.atan2(p[1].y-p[0].y,p[1].x-p[0].x)-g.angle:0;
   const zoom=Math.min(4,Math.max(1,g.t.zoom*ratio)),r=zoom/g.t.zoom,cos=Math.cos(angle),sin=Math.sin(angle),x=g.center.x-480-g.t.x,y=g.center.y-480-g.t.y;
   discardProcessed(s);s.transform={zoom,angle:g.t.angle+angle,x:center.x-480-r*(cos*x-sin*y),y:center.y-480-r*(sin*x+cos*y)};paint(s);
  };
  const end=e=>{s.points.delete(e.pointerId);anchor();};s.canvas.onpointerup=end;s.canvas.onpointercancel=end;s.canvas.onlostpointercapture=end;
  s.canvas.onwheel=e=>{if(!s.source||s.busy||s.showProcessed)return;e.preventDefault();s.transform.zoom=Math.min(4,Math.max(1,s.transform.zoom*Math.exp(-e.deltaY*.001)));paint(s);};
 }
 function render(s,result,append){
  if(!append)s.results.replaceChildren();s.results.classList.toggle('tt-photo-no-results',result.total===0);if(result.total===0){const empty=document.createElement('p');empty.className='tt-photo-empty';empty.textContent='Не найдено';empty.setAttribute('role','status');s.results.append(empty);}
  const roles={whole:'Изображение целиком',side:'Сторона',fragment:'Фрагмент',projection:'Проекция'};
  for(const item of result.items){
   const card=document.createElement('article');card.className='product-card tt-match-'+(item.similarity_status||'weak');
   const img=document.createElement('img');img.alt=item.name;img.loading='lazy';img.src=result.total===1?(item.image_500_url||'/api/visual-search/image500/'+encodeURIComponent(item.code)):item.image_url;
   img.onerror=()=>{img.onerror=null;img.src='/static/img/'+encodeURIComponent(item.code)+'.jpg';img.dataset.quality='250-fallback';};
   const name=document.createElement('div');name.className='name';name.textContent=item.name;
   const code=document.createElement('div');code.className='code';code.textContent=item.code;
   const relation=document.createElement('small');relation.textContent=item.relation==='confirmed_component'?'Комплект: совпал входящий элемент '+item.component_code:(item.is_kit?'Комплект · ':'Товар · ')+(roles[item.match_view?.role]||'Рисунок');
   card.setAttribute('aria-description',relation.textContent);card.append(img,name,code);s.results.append(card);
  }
  s.cursor=result.cursor;s.offset=result.next_offset;s.more.hidden=s.offset==null;
  s.count.textContent=result.total>0?'Σ '+result.total:'';s.count.setAttribute('aria-label','Найдено товаров: '+result.total);notice(s,'');
 }
 function filterFound(s,append=false){
  if(!live(s)||!s.found)return;const items=s.kind.value?s.found.items.filter(item=>item.product_type===s.kind.value):s.found.items,offset=append?s.rendered||0:0;
  s.rendered=Math.min(items.length,offset+30);render(s,{items:items.slice(offset,s.rendered),total:items.length,next_offset:s.rendered<items.length?s.rendered:null},append);if(!append)s.body.scrollTop=0;
 }
 function encodeOriginal(s){
  const c=document.createElement('canvas');c.width=c.height=960;const ctx=c.getContext('2d'),t=s.transform,scale=Math.min(960/s.source.width,960/s.source.height)*t.zoom;
  ctx.fillStyle='white';ctx.fillRect(0,0,960,960);ctx.translate(480+t.x,480+t.y);ctx.rotate(t.angle);ctx.scale(scale,scale);ctx.drawImage(s.source,-s.source.width/2,-s.source.height/2);
  return new Promise(resolve=>c.toBlob(blob=>{c.width=c.height=0;resolve(blob);},'image/jpeg',.90));
 }
 function discardProcessed(s){if(s.processed)s.processed.width=s.processed.height=0;s.processed=null;s.showProcessed=false;}
 async function enhance(s){
  if(!live(s)||s.busy||!s.source)return;const operation=++s.operation;s.busy=true;mode(s,'frame');notice(s,'Обрабатываю снимок…');
  try{const blob=await encodeOriginal(s);if(!live(s)||operation!==s.operation)return;if(!blob)throw Error('Не удалось подготовить снимок.');
   const result=await request(s,'/api/visual-search/enhance',{method:'POST',headers:{'Content-Type':'image/jpeg'},body:blob});if(!live(s)||operation!==s.operation)return;
   if(result.content_type!=='image/jpeg'||typeof result.image_base64!=='string'||result.image_base64.length>2800000)throw Error('Не удалось прочитать обработанный снимок.');
   const image=new Image();try{image.src='data:image/jpeg;base64,'+result.image_base64;await image.decode();if(!live(s)||operation!==s.operation)return;
    if(image.naturalWidth*image.naturalHeight>1048576)throw Error('Некорректный размер снимка.');const c=document.createElement('canvas');c.width=image.naturalWidth;c.height=image.naturalHeight;c.getContext('2d').drawImage(image,0,0);discardProcessed(s);s.processed=c;s.showProcessed=true;paint(s);
   }finally{image.src='';}notice(s,result.operations?.length?'Обработка готова. Можно сравнить с исходником.':'Заметных изменений не потребовалось.');
  }catch(e){if(live(s)&&operation===s.operation)notice(s,e.name==='AbortError'?'Обработка отменена. Исходник сохранён.':e.message);}
  finally{if(live(s)&&operation===s.operation){s.busy=false;mode(s,s.mode);}}
 }
 async function search(s){
  if(!live(s)||s.busy||!s.source)return;s.busy=true;s.search.disabled=s.more.disabled=true;const operation=++s.operation,kind=s.kind.value,started=performance.now();s.dialog.dataset.searchEnhancement='pending';s.dialog.dataset.searchReturned='';mode(s,s.mode);notice(s,s.auto.checked||s.showProcessed?'Ищу рисунок… При необходимости обработаю снимок.':'Ищу рисунок…');
  try{
   let blob=await encodeOriginal(s);if(!blob||blob.size>2*1024*1024)throw Error('Не удалось подготовить снимок.');
   if(!live(s)||operation!==s.operation)return;
   const result=await request(s,'/api/visual-search/search?'+new URLSearchParams({product_type:kind,enhancement:s.showProcessed&&s.processed?'force':s.auto.checked?'auto':'off'}),{method:'POST',headers:{'Content-Type':'image/jpeg'},body:blob});blob=null;
   if(!live(s)||operation!==s.operation)return;
   if(!Array.isArray(result.items)||!Number.isInteger(result.total)||result.total<0||result.total>200000)throw Error('Не удалось прочитать выдачу. Повторите поиск.');
   s.dialog.dataset.searchEnhancement=result.enhancement?.status||'original';s.dialog.dataset.searchReturned=String(result.total);s.dialog.dataset.searchIndex=result.index_version||'';
   if(result.total===0&&['busy_original_used','budget_original_used','unavailable_original_used','index_changed_original_used'].includes(result.enhancement?.status))throw Error('Обработка снимка не завершилась. Снимок сохранён. Повторите поиск через несколько секунд.');
   const items=new Map(result.items.map(item=>[item.code,item])),seen=new Set(),deadline=performance.now()+8000;let offset=result.next_offset;
   // Fetch metadata before the server cursor expires. Filtering and paging then
   // stay local until Next; query pixels are still discarded after the search.
   while(offset!=null){
    if(!Number.isInteger(offset)||offset<=0||seen.has(offset)||performance.now()>deadline)throw Error('Не удалось получить всю выдачу. Повторите поиск с выбранным видом.');seen.add(offset);
    const page=await request(s,'/api/visual-search/results?'+new URLSearchParams({cursor:result.cursor,offset}));
    if(!live(s)||operation!==s.operation)return;
    if(page.cursor!==result.cursor||page.total!==result.total||!Array.isArray(page.items)||!page.items.length)throw Error('Выдача изменилась. Повторите поиск.');
    for(const item of page.items)items.set(item.code,item);offset=page.next_offset;
   }
   if(items.size!==result.total)throw Error('Не удалось получить всю выдачу. Повторите поиск.');
   s.found={items:[...items.values()].filter(item=>!kind||item.product_type===kind),searchedKind:kind};s.dialog.dataset.searchFiltered=String(s.found.items.length);clearFrame(s);s.range.disabled=true;s.rotate.disabled=true;filterFound(s);mode(s,'results');
   root.dispatchEvent(new CustomEvent('tt-photo-timing',{detail:{elapsed_ms:performance.now()-started,status:result.status}}));
  }catch(e){if(live(s)&&operation===s.operation)notice(s,e.name==='AbortError'?'Поиск отменён или время ожидания истекло. Можно повторить.':e.message);}
  finally{if(live(s)&&operation===s.operation){s.busy=false;mode(s,s.mode);s.more.disabled=false;}}
 }
 async function paste(s){
  try{if(!navigator.clipboard?.read)throw Error('Выберите файл: чтение буфера недоступно в этом браузере.');
   for(const item of await navigator.clipboard.read()){const type=item.types.find(t=>['image/png','image/jpeg','image/webp'].includes(t));if(type){await file(s,await item.getType(type));return;}}
   notice(s,'В буфере нет изображения. Выберите файл.');
  }catch(e){notice(s,e.message||'Буфер недоступен. Выберите файл.');}
 }
 function open({withCamera=true}={}){
  if(!capabilities)return null;close();options.beforeOpen?.();const dialog=document.createElement('dialog');dialog.className='tt-photo-dialog';
  const s=current={id:++sequence,dialog,stream:null,abort:null,source:null,blob:null,operation:0,cameraGeneration:0,busy:false,points:new Map(),transform:{zoom:1,angle:0,x:0,y:0}};
  const header=document.createElement('header');dialog.setAttribute('aria-label','Поиск по изображениям');const closeButton=action('',close);closeButton.className='tt-photo-close';closeButton.setAttribute('aria-label','Закрыть');closeButton.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  const body=document.createElement('section');body.className='tt-photo-body';s.body=body;
  s.kind=document.createElement('select');s.kind.setAttribute('aria-label','Вид товара');s.kind.append(new Option('Все виды',''));for(const k of capabilities.product_types)s.kind.append(new Option(k,k));
  const main=options.selectedType?.()||'';if(mainKind!==undefined&&mainKind!==main)savedKind=main;mainKind=main;
  if(savedKind===undefined&&user)try{savedKind=sessionStorage.getItem('tt.photo.kind.'+user)??undefined;}catch{}
  if(savedKind===undefined)savedKind=main;s.kind.value=capabilities.product_types.includes(savedKind)?savedKind:'';s.count=document.createElement('span');s.count.className='tt-photo-count';s.count.textContent='';s.count.setAttribute('role','status');s.count.setAttribute('aria-label','Поиск ещё не выполнен');const kindWrap=document.createElement('div');kindWrap.className='tt-photo-kind';s.kindClear=action('',()=>{s.kind.value='';s.kind.dispatchEvent(new Event('change',{bubbles:true}));});s.kindClear.className='tt-photo-kind-clear';s.kindClear.setAttribute('aria-label','Сбросить вид товара');s.kindClear.innerHTML=closeButton.innerHTML;s.kindClear.hidden=!s.kind.value;kindWrap.append(s.kind,s.kindClear);header.append(kindWrap,s.count,closeButton);
  s.kind.onchange=()=>{s.kindClear.hidden=!s.kind.value;remember(s.kind.value);if(s.mode==='results'&&s.found)filterFound(s);else{changed(s);notice(s,'');}};
  s.stage=document.createElement('div');s.stage.className='tt-photo-stage';s.video=document.createElement('video');s.video.muted=true;s.video.playsInline=true;s.canvas=document.createElement('canvas');s.canvas.hidden=true;s.stage.append(s.video,s.canvas);gestures(s);
  const tools=document.createElement('label');tools.textContent='Масштаб';s.range=document.createElement('input');s.range.type='range';s.range.min='1';s.range.max='4';s.range.step='.01';s.range.value='1';s.range.disabled=true;s.range.oninput=()=>{if(!s.busy){discardProcessed(s);s.transform.zoom=Number(s.range.value);paint(s);}};
  s.rotate=action('Повернуть 90°',()=>{if(!s.busy){discardProcessed(s);s.transform.angle+=Math.PI/2;paint(s);}});s.rotate.disabled=true;
  tools.className='tt-photo-tools';tools.append(s.range,s.rotate);s.tools=tools;
  s.processing=document.createElement('div');s.processing.className='tt-photo-processing';const autoLabel=document.createElement('label');s.auto=document.createElement('input');s.auto.type='checkbox';s.auto.checked=capabilities.enhancement?.automatic===true;s.auto.setAttribute('aria-label','Автоулучшение');autoLabel.append(s.auto,document.createTextNode('Авто'));autoLabel.title='Обработка при слабом совпадении';
  s.enhance=action('Улучшить',()=>enhance(s));s.originalButton=action('Исходник',()=>{s.showProcessed=false;paint(s);notice(s,'');});s.processedButton=action('Обработка',()=>{s.showProcessed=true;paint(s);notice(s,'');});s.processing.append(autoLabel,s.enhance,s.originalButton,s.processedButton);s.processing.hidden=!capabilities.enhancement?.available;
  s.notice=document.createElement('p');s.notice.setAttribute('role','status');s.notice.className='tt-photo-notice';s.results=document.createElement('div');s.results.className='tt-photo-results';s.more=action('Ещё товары',()=>filterFound(s,true));s.more.hidden=true;
  body.append(s.stage,tools,s.processing,s.notice,s.results,s.more);const footer=document.createElement('footer');
  s.search=action('Снимок',()=>s.mode==='camera'?capture(s):search(s),'camera');s.search.disabled=true;s.search.className='tt-photo-primary';
  const input=document.createElement('input');input.type='file';input.accept='image/jpeg,image/png,image/webp';input.hidden=true;input.onchange=()=>{const selected=input.files?.[0];input.value='';file(s,selected);};
  const pasteButton=action('Вставить',()=>paste(s),'clipboard');pasteButton.className='tt-photo-paste';footer.append(action('Файл',()=>input.click(),'file'),pasteButton,action('Следующий',()=>camera(s),'next'),s.search,input);dialog.append(header,body,footer);document.body.append(dialog);
  s.fit=()=>{cancelAnimationFrame(s.fitFrame);s.fitFrame=requestAnimationFrame(()=>{if(!live(s)||s.stage.hidden)return;const style=getComputedStyle(body),paddingX=parseFloat(style.paddingLeft)+parseFloat(style.paddingRight),paddingY=parseFloat(style.paddingTop)+parseFloat(style.paddingBottom),others=[...body.children].filter(e=>e!==s.stage&&!e.hidden&&getComputedStyle(e).display!=='none'),used=others.reduce((sum,e)=>sum+e.getBoundingClientRect().height,0)+others.length*(parseFloat(style.gap)||0),side=Math.max(1,Math.floor(Math.min(body.clientWidth-paddingX,body.clientHeight-paddingY-used)));s.stage.style.width=s.stage.style.height=side+'px';});};
  s.resizeObserver=new ResizeObserver(s.fit);s.resizeObserver.observe(body);root.addEventListener('resize',s.fit);
  dialog.oncancel=e=>{e.preventDefault();close();};dialog.showModal();if(withCamera)camera(s);else{mode(s,'empty');notice(s,'');}return s;
 }
 button.onclick=()=>open();document.addEventListener('paste',e=>{const item=[...(e.clipboardData?.items||[])].find(i=>i.kind==='file'&&['image/jpeg','image/png','image/webp'].includes(i.type));if(!item)return;const selected=item.getAsFile();if(!selected)return;e.preventDefault();const s=current||open({withCamera:false});if(s)file(s,selected);});
 root.addEventListener('pagehide',close);root.addEventListener('tt-search-change',()=>{if(current)close();});document.addEventListener('visibilitychange',()=>{if(document.hidden&&current)cameraOff(current);});options.barcodeButton?.addEventListener('click',close);
 async function refresh(){try{
  const c=new AbortController(),timer=setTimeout(()=>c.abort(),3000);let r,p;try{[r,p]=await Promise.all([transport('/api/visual-search/capabilities',{credentials:'same-origin',cache:'no-store',signal:c.signal}),transport('/api/auth/profile',{credentials:'same-origin',cache:'no-store',signal:c.signal})]);}finally{clearTimeout(timer);}
  if(!r.ok)return;const value=await r.json();if(value.api_version!==1||!Array.isArray(value.product_types))return;
  if(p.ok){const profile=await p.json(),next=String(profile.id||'');if(user&&user!==next){savedKind=undefined;mainKind=undefined;close();}user=next;}
  capabilities=value;button.hidden=false;
 }catch{}}
 refresh();return {open,close,refresh};
}
root.TTVisualSearch={create};
})(window);
