'use strict';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const check = (value, message) => { if (!value) throw Error(message); };
async function until(condition) { for (let i = 0; i < 300; i++) { if (condition()) return; await pause(10); } throw Error('Fixture timeout'); }
const dimensions = [[360,640],[390,667],[390,844],[446,840],[700,900],[844,390],[1366,768],[1920,1080]];
document.getElementById('run').onclick = async function () {
    this.disabled = true; const results = [];
    const output = document.getElementById('result');
    async function frame(path,width,height,font) {
        const iframe = document.createElement('iframe'); iframe.style.cssText = `width:${width}px;height:${height}px;border:0;display:block`;
        document.getElementById('frame').replaceChildren(iframe);
        iframe.src = path + '&font=' + font;
        await new Promise(resolve => { iframe.onload = resolve; });
        const win = iframe.contentWindow; await until(() => win.document.documentElement.dataset.fixtureReady); await pause(30);
        return {iframe,win,doc:win.document};
    }
    for (const [width,height] of dimensions) for (const font of [16,18]) {
        try {
            const {doc,win,iframe} = await frame('/mark?fixture=portrait',width,height,font);
            const rect = selector => doc.querySelector(selector).getBoundingClientRect();
            const camera = rect('#cameraMarkBtn'), input = rect('#scanInput'), scroll = doc.getElementById('tablesScroll');
            const stickerRows = [...doc.querySelectorAll('.sticker-section tbody tr')];
            const before = {width,height,font,photoHeight:rect('#imageContainer').height,tableHeight:scroll.clientHeight,
                cameraTop:camera.top,inputTop:input.top,tableBottom:rect('#tablesScroll').bottom,
                secondStickerBottom:stickerRows[1].getBoundingClientRect().bottom,pageWidth:doc.documentElement.scrollWidth};
            check(before.pageWidth<=width, 'Horizontal overflow');
            const heading=doc.querySelector('.sticker-section thead');
            check(heading.querySelectorAll('tr').length===1 && heading.querySelector('.sticker-count strong').textContent==='2','Compact header/count missing');
            check(Number(win.getComputedStyle(heading.querySelector('strong')).fontWeight)>=800,'Count is not bold');
            check(!doc.querySelector('.sticker-section > .sticker-count'),'Separate count row remains');
            if(width<=700) check(heading.getBoundingClientRect().height<=48,'Header is too tall');
            check(rect('#productInfoContainer').top >= rect('#lastScannedCode').bottom, 'Product header order');
            check(camera.width>=(width<=700?44:36) && camera.height>=(width<=700?44:36), 'Camera touch target');
            if (width<=700) {
                check(Math.abs(camera.top-input.top)<5 && camera.left>input.right, 'Camera must be top-right');
                check(doc.getElementById('markingDisplay').parentElement.id==='lastScannedCode','Filter placement');
                check(rect('#scannedCodeText').left<rect('#markingDisplay').left && rect('#markingDisplay').right<=rect('#markingLogo').left,'ID/filter/logo order');
                check(before.photoHeight<=Math.min(height*.3,250)+1,'Photo budget');
                if(height>740) {
                    check(before.secondStickerBottom<=before.tableBottom+1,'Second sticker clipped');
                    check(before.secondStickerBottom<=height-32,'Second sticker outside screen');
                }
                check(doc.querySelector('.sticker-section').scrollWidth<=doc.querySelector('.sticker-section').clientWidth+1,'WB numbers overflow horizontally');
                const fixedSelectors=['.search-row','#lastScannedCode','#productInfoContainer','#imageContainer'];
                const fixedBefore=fixedSelectors.map(selector=>rect(selector).toJSON());
                const headingTop=heading.getBoundingClientRect().top;
                scroll.scrollTop=scroll.scrollHeight;check(scroll.scrollTop>0,'Table does not scroll');
                check(heading.getBoundingClientRect().top<headingTop-20,'Table header must scroll with rows');
                doc.querySelector('.main-grid').scrollTop=10000;doc.documentElement.scrollTop=10000;doc.body.scrollTop=10000;
                fixedSelectors.forEach((selector,index)=>{
                    const after=rect(selector);check(Math.abs(after.top-fixedBefore[index].top)<1&&Math.abs(after.bottom-fixedBefore[index].bottom)<1,'Header or image moved: '+selector);
                });
                check(Math.abs(rect('#imageContainer').bottom-(height-32))<1,'Image not anchored to bottom');
                check(scroll.clientHeight>=80,'Table collapsed');scroll.scrollTop=0;
                for(const number of doc.querySelectorAll('.row-number,.sticker-highlight,.sticker-last'))
                    check(Number(win.getComputedStyle(number).fontWeight)>=800,'Key number is not heavy');
                const control = doc.getElementById('markingDisplay'); control.click();
                [...doc.querySelectorAll('.marking-dropdown-item')].find(el=>el.textContent==='ktv_WB').click();
                iframe.style.width='1000px';await until(()=>control.parentElement.classList.contains('input-marking-wrapper'));
                iframe.style.width=width+'px';await until(()=>control.parentElement.id==='lastScannedCode');
                check(control===doc.getElementById('markingDisplay') && doc.getElementById('markingLabelText').textContent==='ktv_WB','Filter state lost across resize');
            } else {
                const baseline = await frame('/baseline-mark?fixture=portrait',width,height,font);
                const oldRect = selector=>baseline.doc.querySelector(selector).getBoundingClientRect();
                check(Math.abs(oldRect('#imageContainer').height-before.photoHeight)<1,'Desktop photo changed');
                check(Math.abs(baseline.doc.getElementById('tablesScroll').clientHeight-before.tableHeight)<1,'Desktop table changed');
            }
            results.push({...before,pass:true});
        } catch(error) { results.push({width,height,font,pass:false,error:error.message}); }
        output.textContent=JSON.stringify(results,null,2);
    }
    for (const fixture of ['wide','missing','many','empty']) {
        try {
            const {doc}=await frame('/mark?fixture='+fixture,390,844,18),scroll=doc.getElementById('tablesScroll');
            if(fixture==='many') { scroll.scrollTop=scroll.scrollHeight;check(scroll.scrollTop>0 && doc.querySelector('.table-container').getBoundingClientRect().bottom<=scroll.getBoundingClientRect().bottom+1,'Cannot reach table end'); }
            if(fixture==='missing') await until(()=>doc.getElementById('noImageLabel').style.display==='flex');
            if(fixture==='empty') check(!!doc.querySelector('.no-result,.error'),'Missing empty state');
            results.push({fixture,pass:true});
        } catch(error) { results.push({fixture,pass:false,error:error.message}); }
    }
    try {
        const {doc,win}=await frame('/mark?fixture=portrait',390,844,18);
        win.renderResults([{'Код':'90001','Название':'Синтетическая смешанная выдача','Вид':'Тест','Фандом':'Тест',found_markings:['ktv_WB','ktv_OZ'],
            table:[{marking:'ktv_WB',platform:'WB',stickers:[{sticker:'50000004074',row:1}],sticker_to_articul:{'50000004074':'90001'}},
                {marking:'ktv_OZ',platform:'OZ',stickers:[{sticker:'50000007956',articul:'90001'}]}]}]);
        const section=doc.querySelector('.sticker-section');
        check(section.querySelectorAll('th').length===3,'Mixed marketplace columns lost');
        section.scrollLeft=section.scrollWidth;
        check(section.scrollLeft>0 && section.querySelector('th:last-child').getBoundingClientRect().right<=section.getBoundingClientRect().right+1,'Cannot reach mixed marketplace column');
        results.push({fixture:'mixed-WB-OZ',pass:true});
    } catch(error) { results.push({fixture:'mixed-WB-OZ',pass:false,error:error.message}); }
    for (const fixture of ['zero-stickers','OZ-only','related-excluded']) {
        try {
            const {doc,win}=await frame('/mark?fixture=portrait',390,844,18);
            const product=table=>({'Код':'90001','Название':'Синтетическая проверка шапки','Вид':'Тест','Фандом':'Тест',found_markings:['ktv_OZ'],table});
            const table=[{marking:'ktv_OZ',platform:'OZ',stickers:[{sticker:'50000007956',articul:'90001'}]}];
            const products=fixture==='zero-stickers'?[product([])]:[product(table)];
            if(fixture==='related-excluded') products.push({...product(table),similar_sticker_match:true});
            win.renderResults(products);
            const section=doc.querySelector('.sticker-section');
            check(section.querySelectorAll('thead tr').length===1,'Header row missing');
            check(section.querySelector('.sticker-count strong').textContent===(fixture==='zero-stickers'?'0':'1'),'Count semantics changed');
            if(fixture==='OZ-only') check(section.querySelector('th:last-child').textContent==='Артикул' && section.querySelectorAll('th').length===2,'OZ column lost');
            results.push({fixture,pass:true});
        } catch(error) { results.push({fixture,pass:false,error:error.message}); }
    }
    for (const [width,height] of [[360,640],[390,667],[390,844],[446,840],[844,390]]) for (const font of [16,18]) {
        let cameraFrame;
        try {
            const {iframe,doc}=await frame('/lab/preview.html?layout=1',width,height,font); cameraFrame=iframe;
            doc.getElementById('camera').click();await until(()=>doc.querySelector('.tt-camera-switch')?.hidden===false);await pause(20);
            const dialog=doc.querySelector('dialog'),cancel=doc.querySelector('.tt-camera-cancel').getBoundingClientRect(),video=doc.querySelector('video').getBoundingClientRect();
            check(!doc.querySelector('.tt-camera-hint'),'Removed caption still present');
            check(cancel.bottom<=height && cancel.top>=0,'Cancel outside viewport');
            check(dialog.scrollHeight<=dialog.clientHeight+1,'Camera dialog scrolls');
            check(video.height>30,'Preview collapsed');check(Math.abs(video.width-video.height)<1,'Preview is not square');
            const scanline=iframe.contentWindow.getComputedStyle(doc.querySelector('.tt-camera-frame'),'::after');
            check(scanline.content==='""' && scanline.height==='1px' && scanline.pointerEvents==='none','Decorative barcode scanline missing');
            check(scanline.animationName===(iframe.contentWindow.matchMedia('(prefers-reduced-motion: reduce)').matches?'none':'tt-camera-scan-glow'),'Scanline motion preference ignored');
            const torch=doc.querySelector('.tt-camera-torch'),zoom=doc.querySelector('.tt-camera-zoom');
            const label=torch.textContent,buttonWidth=torch.getBoundingClientRect().width,zoomTop=zoom.getBoundingClientRect().top;
            const originalColor=iframe.contentWindow.getComputedStyle(torch).backgroundColor;
            torch.click();await until(()=>torch.getAttribute('aria-pressed')==='true');
            check(torch.textContent===label&&Math.abs(torch.getBoundingClientRect().width-buttonWidth)<1,'Torch caption/width changed');
            check(Math.abs(zoom.getBoundingClientRect().top-zoomTop)<1,'Torch moved the zoom control');
            check(iframe.contentWindow.getComputedStyle(torch).backgroundColor!==originalColor,'Torch active color missing');
            torch.click();await until(()=>torch.getAttribute('aria-pressed')==='false');
            check(torch.textContent===label&&iframe.contentWindow.getComputedStyle(torch).backgroundColor===originalColor,'Torch off state not restored');
            doc.querySelector('[data-mode="text"]').click();await until(()=>doc.querySelector('.tt-camera-text-mode .tt-camera-frame'));
            check(iframe.contentWindow.getComputedStyle(doc.querySelector('.tt-camera-frame'),'::after').content==='none','Barcode line leaked into text mode');
            doc.querySelector('[data-mode="barcode"]').click();await until(()=>doc.querySelector('.tt-camera-capture:not(.tt-camera-text-mode) .tt-camera-frame'));
            check(iframe.contentWindow.getComputedStyle(doc.querySelector('.tt-camera-frame'),'::after').content==='""','Barcode line not restored');
            results.push({camera:true,width,height,font,dialogHeight:dialog.clientHeight,previewHeight:video.height,cancelBottom:cancel.bottom,pass:true});
            doc.querySelector('.tt-camera-close').click();
        } catch(error) { results.push({camera:true,width,height,font,pass:false,error:error.message}); }
        finally { cameraFrame?.remove(); }
    }
    output.textContent=JSON.stringify({pass:results.filter(x=>x.pass).length,fail:results.filter(x=>!x.pass).length,results},null,2);
    this.disabled=false;
};
