/* Explicit RAM-only crop; only the selected kind may enter session storage. */
(function(root){'use strict';
function create(options){
 const button=options.button,transport=options.fetch||root.fetch.bind(root),media=options.mediaDevices||navigator.mediaDevices;
 let current=null,sequence=0,capabilities=null,user=null,savedKind,mainKind;
 const live=s=>current===s&&s.id===sequence;
 function cameraOff(s){s.stream?.getTracks().forEach(t=>t.stop());s.stream=null;s.video.pause();s.video.srcObject=null;}
 function clearFrame(s){if(s.source){s.source.width=s.source.height=0;}s.source=null;s.blob=null;s.canvas.width=s.canvas.height=0;s.points.clear();s.transform={zoom:1,angle:0,x:0,y:0};}
 function close(){const s=current;current=null;sequence++;if(!s)return;s.abort?.abort();s.cameraGeneration++;cameraOff(s);clearFrame(s);s.dialog.close();s.dialog.remove();button.focus({preventScroll:true});options.onClose?.();}
 function notice(s,text){if(live(s))s.notice.textContent=text;}
 function action(text,fn){const b=document.createElement('button');b.type='button';b.textContent=text;b.onclick=fn;return b;}
 function remember(value){savedKind=value;if(user)try{sessionStorage.setItem('tt.photo.kind.'+user,value);}catch{}}
 async function request(s,path,settings={}){
  s.abort?.abort();const c=s.abort=new AbortController(),timer=setTimeout(()=>c.abort(),8000);
  try{const r=await transport(path,{credentials:'same-origin',cache:'no-store',...settings,signal:c.signal});
   if(!r.ok)throw Error(({401:'Войдите в личный кабинет.',403:'Нет доступа.',410:'Выдача устарела. Повторите поиск.',413:'Слишком большой снимок.',422:'Проверьте изображение и вид.',429:'Поиск занят. Повторите через несколько секунд.'})[r.status]||'Фото-поиск временно недоступен.');
   return await r.json();
  }finally{clearTimeout(timer);}
 }
 function changed(s){s.operation++;s.busy=false;s.abort?.abort();s.blob=null;s.results.replaceChildren();s.more.hidden=true;s.stage.hidden=false;s.search.disabled=!s.source;}
 function paint(s){
  if(!s.source)return;const c=s.canvas,ctx=c.getContext('2d');c.width=c.height=960;
  const t=s.transform,scale=Math.min(960/s.source.width,960/s.source.height)*t.zoom;
  ctx.fillStyle='white';ctx.fillRect(0,0,960,960);ctx.save();ctx.translate(480+t.x,480+t.y);ctx.rotate(t.angle);ctx.scale(scale,scale);ctx.drawImage(s.source,-s.source.width/2,-s.source.height/2);ctx.restore();
  s.range.value=t.zoom;s.stage.hidden=false;c.hidden=false;s.video.hidden=true;s.range.disabled=false;s.rotate.disabled=false;s.search.disabled=s.busy;
 }
 function beginFrame(s,source){changed(s);cameraOff(s);clearFrame(s);s.source=source;s.transform={zoom:1,angle:0,x:0,y:0};s.shutter.hidden=true;paint(s);notice(s,'Один палец — перемещение; два — масштаб и поворот. «Найти» отправит показанную область.');}
 async function camera(s){
  if(!live(s))return;changed(s);s.frameGeneration=(s.frameGeneration||0)+1;clearFrame(s);cameraOff(s);const generation=++s.cameraGeneration;
  s.stage.hidden=false;s.canvas.hidden=true;s.video.hidden=false;s.shutter.hidden=false;s.shutter.disabled=true;s.search.disabled=true;s.range.disabled=true;s.rotate.disabled=true;
  notice(s,'Открываю заднюю камеру…');
  try{
   if(!root.isSecureContext||!media?.getUserMedia)throw Error('secure');
   const stream=await media.getUserMedia({audio:false,video:{facingMode:{exact:'environment'},width:{ideal:1280},height:{ideal:1280}}});
   if(!live(s)||generation!==s.cameraGeneration){stream.getTracks().forEach(t=>t.stop());return;}
   if(stream.getVideoTracks()[0]?.getSettings().facingMode!=='environment'){stream.getTracks().forEach(t=>t.stop());throw Error('rear');}
   s.stream=stream;s.video.srcObject=stream;await s.video.play();if(!live(s)||generation!==s.cameraGeneration)return;
   s.shutter.disabled=false;notice(s,'Нажмите «Снимок», затем проверьте область рисунка. Вид необязателен.');
  }catch(e){if(live(s)&&generation===s.cameraGeneration){cameraOff(s);notice(s,e.name==='NotAllowedError'?'Разрешите камеру или выберите файл.':'Задняя камера недоступна. Выберите файл или вставьте картинку.');}}
 }
 function capture(s){
  if(!live(s)||!s.video.videoWidth)return;const c=document.createElement('canvas'),scale=Math.min(1,1600/Math.max(s.video.videoWidth,s.video.videoHeight));
  c.width=Math.round(s.video.videoWidth*scale);c.height=Math.round(s.video.videoHeight*scale);c.getContext('2d').drawImage(s.video,0,0,c.width,c.height);beginFrame(s,c);
 }
 async function file(s,selected){
  if(!selected||!live(s))return;if(selected.size>2*1024*1024||!['image/jpeg','image/png','image/webp'].includes(selected.type)){notice(s,'Нужен JPEG, PNG или WebP до 2 МБ и 12 Мп.');return;}
  changed(s);s.cameraGeneration++;cameraOff(s);const frameGeneration=s.frameGeneration=(s.frameGeneration||0)+1,url=URL.createObjectURL(selected),image=new Image();
  try{image.src=url;await image.decode();if(!live(s)||frameGeneration!==s.frameGeneration)return;
   if(image.naturalWidth*image.naturalHeight>12000000||Math.min(image.naturalWidth,image.naturalHeight)<32)throw Error('Нужен снимок до 12 Мп, не меньше 32 пикселей.');
   const c=document.createElement('canvas');c.width=image.naturalWidth;c.height=image.naturalHeight;c.getContext('2d').drawImage(image,0,0);beginFrame(s,c);
  }catch(e){notice(s,e.message||'Не удалось прочитать файл.');}finally{URL.revokeObjectURL(url);image.src='';}
 }
 function gestures(s){
  const position=e=>{const b=s.canvas.getBoundingClientRect();return {x:(e.clientX-b.left)*960/b.width,y:(e.clientY-b.top)*960/b.height};};
  function anchor(){const p=[...s.points.values()];if(!p.length){s.gesture=null;return;}
   const center=p.length>1?{x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2}:p[0];
   s.gesture={center,t:{...s.transform},distance:p.length>1?Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y):0,angle:p.length>1?Math.atan2(p[1].y-p[0].y,p[1].x-p[0].x):0};
  }
  s.canvas.onpointerdown=e=>{if(!s.source||s.busy)return;e.preventDefault();s.canvas.setPointerCapture(e.pointerId);s.points.set(e.pointerId,position(e));anchor();};
  s.canvas.onpointermove=e=>{
   if(!s.points.has(e.pointerId)||!s.gesture||s.busy)return;e.preventDefault();s.points.set(e.pointerId,position(e));const p=[...s.points.values()],g=s.gesture;
   const center=p.length>1?{x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2}:p[0];
   const ratio=p.length>1&&g.distance?Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y)/g.distance:1;
   const angle=p.length>1?Math.atan2(p[1].y-p[0].y,p[1].x-p[0].x)-g.angle:0;
   const zoom=Math.min(4,Math.max(1,g.t.zoom*ratio)),r=zoom/g.t.zoom,cos=Math.cos(angle),sin=Math.sin(angle),x=g.center.x-480-g.t.x,y=g.center.y-480-g.t.y;
   s.transform={zoom,angle:g.t.angle+angle,x:center.x-480-r*(cos*x-sin*y),y:center.y-480-r*(sin*x+cos*y)};paint(s);
  };
  const end=e=>{s.points.delete(e.pointerId);anchor();};s.canvas.onpointerup=end;s.canvas.onpointercancel=end;s.canvas.onlostpointercapture=end;
  s.canvas.onwheel=e=>{if(!s.source||s.busy)return;e.preventDefault();s.transform.zoom=Math.min(4,Math.max(1,s.transform.zoom*Math.exp(-e.deltaY*.001)));paint(s);};
 }
 function render(s,result,append){
  if(!append)s.results.replaceChildren();s.results.classList.toggle('tt-photo-single',result.total===1);
  const roles={whole:'Изображение целиком',side:'Сторона',fragment:'Фрагмент',projection:'Проекция'};
  for(const item of result.items){
   const card=document.createElement('article');card.className='product-card tt-match-'+(item.similarity_status||'weak');
   const img=document.createElement('img');img.alt=item.name;img.loading='lazy';img.src=result.total===1?(item.image_500_url||'/api/visual-search/image500/'+encodeURIComponent(item.code)):item.image_url;
   img.onerror=()=>{img.onerror=null;img.src='/static/img/'+encodeURIComponent(item.code)+'.jpg';img.dataset.quality='250-fallback';};
   const name=document.createElement('div');name.className='name';name.textContent=item.name;
   const code=document.createElement('div');code.className='code';code.textContent=item.code;
   const hint=document.createElement('p');hint.textContent=({'confirmed':'✓ Совпали детали','uncertain':'? Проверьте сходство','weak':'! Слабое сходство'})[item.similarity_status]||'Проверьте рисунок';
   const relation=document.createElement('small');relation.textContent=item.relation==='confirmed_component'?'Комплект: совпал входящий элемент '+item.component_code:(item.is_kit?'Комплект · ':'Товар · ')+(roles[item.match_view?.role]||'Рисунок');
   card.append(img,name,code,hint,relation);s.results.append(card);
  }
  s.cursor=result.cursor;s.offset=result.next_offset;s.more.hidden=s.offset==null;
  notice(s,result.total?`Найдено товаров: ${result.total}. Проверьте рисунок и код. Сходство не является вероятностью.`:'Убедительных совпадений не найдено. Попробуйте ближе и без бликов.');
 }
 async function search(s,more=false){
  if(!live(s)||s.busy||(!more&&!s.source))return;s.busy=true;s.search.disabled=s.more.disabled=true;const operation=++s.operation,kind=s.kind.value,started=performance.now();notice(s,'Ищу рисунок…');
  try{
   let blob=null;if(!more){paint(s);blob=await new Promise(resolve=>s.canvas.toBlob(resolve,'image/jpeg',.90));if(!blob||blob.size>2*1024*1024)throw Error('Не удалось подготовить снимок.');}
   if(!live(s)||operation!==s.operation)return;
   const path=more?'/api/visual-search/results?'+new URLSearchParams({cursor:s.cursor,offset:s.offset}):'/api/visual-search/search?'+new URLSearchParams({product_type:kind});
   const result=await request(s,path,more?{}:{method:'POST',headers:{'Content-Type':'image/jpeg'},body:blob});blob=null;
   if(!live(s)||operation!==s.operation)return;render(s,result,more);
   if(!more){clearFrame(s);s.stage.hidden=true;s.range.disabled=true;s.rotate.disabled=true;}
   root.dispatchEvent(new CustomEvent('tt-photo-timing',{detail:{elapsed_ms:performance.now()-started,status:result.status}}));
  }catch(e){if(live(s)&&operation===s.operation)notice(s,e.name==='AbortError'?'Поиск отменён или время ожидания истекло. Можно повторить.':e.message);}
  finally{if(live(s)&&operation===s.operation){s.busy=false;s.search.disabled=!s.source;s.more.disabled=false;}}
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
  const header=document.createElement('header'),title=document.createElement('h2');title.id='ttPhotoTitle';title.textContent='Поиск по изображениям';header.append(title,action('Закрыть',close));dialog.setAttribute('aria-labelledby',title.id);
  const body=document.createElement('section');body.className='tt-photo-body';const privacy=document.createElement('p');privacy.textContent='Снимок передаётся только по кнопке «Найти». Приложение не сохраняет его в каталоге или истории.';
  const label=document.createElement('label');label.textContent='Вид товара';s.kind=document.createElement('select');s.kind.append(new Option('Все виды',''));for(const k of capabilities.product_types)s.kind.append(new Option(k,k));
  const main=options.selectedType?.()||'';if(mainKind!==undefined&&mainKind!==main)savedKind=main;mainKind=main;
  if(savedKind===undefined&&user)try{savedKind=sessionStorage.getItem('tt.photo.kind.'+user)??undefined;}catch{}
  if(savedKind===undefined)savedKind=main;s.kind.value=capabilities.product_types.includes(savedKind)?savedKind:'';label.append(s.kind);
  s.kind.onchange=()=>{remember(s.kind.value);changed(s);notice(s,s.source?'Кадр сохранён. Нажмите «Найти».':'Вид сохранён для следующих снимков.');};
  s.stage=document.createElement('div');s.stage.className='tt-photo-stage';s.video=document.createElement('video');s.video.muted=true;s.video.playsInline=true;s.canvas=document.createElement('canvas');s.canvas.hidden=true;s.stage.append(s.video,s.canvas);gestures(s);
  const tools=document.createElement('label');tools.textContent='Масштаб';s.range=document.createElement('input');s.range.type='range';s.range.min='1';s.range.max='4';s.range.step='.01';s.range.value='1';s.range.disabled=true;s.range.oninput=()=>{if(!s.busy){s.transform.zoom=Number(s.range.value);paint(s);}};
  s.rotate=action('Повернуть 90°',()=>{if(!s.busy){s.transform.angle+=Math.PI/2;paint(s);}});s.rotate.disabled=true;
  tools.append(s.range,s.rotate,action('Сбросить кадр',()=>{if(!s.busy){s.transform={zoom:1,angle:0,x:0,y:0};paint(s);}}));
  s.notice=document.createElement('p');s.notice.setAttribute('role','status');s.notice.className='tt-photo-notice';s.results=document.createElement('div');s.results.className='tt-photo-results';s.more=action('Ещё товары',()=>search(s,true));s.more.hidden=true;
  body.append(privacy,label,s.stage,tools,s.notice,s.results,s.more);const footer=document.createElement('footer');
  s.shutter=action('Снимок',()=>capture(s));s.shutter.disabled=true;s.search=action('Найти',()=>search(s));s.search.disabled=true;
  const input=document.createElement('input');input.type='file';input.accept='image/jpeg,image/png,image/webp';input.hidden=true;input.onchange=()=>{const selected=input.files?.[0];input.value='';file(s,selected);};
  footer.append(s.shutter,s.search,action('Следующий снимок',()=>camera(s)),action('Файл',()=>input.click()),action('Вставить',()=>paste(s)),input);dialog.append(header,body,footer);document.body.append(dialog);
  dialog.oncancel=e=>{e.preventDefault();close();};dialog.showModal();if(withCamera)camera(s);else{s.stage.hidden=true;notice(s,'Выберите файл или вставьте изображение.');}return s;
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
