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
            check(rect('#productInfoContainer').top >= rect('#lastScannedCode').bottom, 'Product header order');
            check(camera.width>=(width<=700?44:36) && camera.height>=(width<=700?44:36), 'Camera touch target');
            if (width<=700) {
                check(Math.abs(camera.top-input.top)<5 && camera.left>input.right, 'Camera must be top-right');
                check(doc.getElementById('markingDisplay').parentElement.id==='lastScannedCode','Filter placement');
                check(rect('#scannedCodeText').left<rect('#markingDisplay').left && rect('#markingDisplay').right<=rect('#markingLogo').left,'ID/filter/logo order');
                check(before.photoHeight<=Math.min(height*.3,250)+1,'Photo budget');
                check(before.secondStickerBottom<=before.tableBottom+1,'Second sticker clipped');
                check(before.secondStickerBottom<=height-32,'Second sticker outside screen');
                check(doc.querySelector('.sticker-section').scrollWidth<=doc.querySelector('.sticker-section').clientWidth+1,'WB numbers overflow horizontally');
                if(height<=740) {
                    const grid=doc.querySelector('.main-grid');grid.scrollTop=grid.scrollHeight;
                    check(rect('#imageContainer').bottom<=height-31,'Cannot reach small-screen image');grid.scrollTop=0;
                }
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
    for (const [width,height] of [[360,640],[390,667],[390,844],[446,840],[844,390]]) for (const font of [16,18]) {
        let cameraFrame;
        try {
            const {iframe,doc}=await frame('/lab/preview.html?layout=1',width,height,font); cameraFrame=iframe;
            doc.getElementById('camera').click();await until(()=>doc.querySelector('.tt-camera-switch')?.hidden===false);await pause(20);
            const dialog=doc.querySelector('dialog'),cancel=doc.querySelector('.tt-camera-cancel').getBoundingClientRect(),video=doc.querySelector('video').getBoundingClientRect();
            check(!doc.querySelector('.tt-camera-hint'),'Removed caption still present');
            check(cancel.bottom<=height && cancel.top>=0,'Cancel outside viewport');
            check(dialog.scrollHeight<=dialog.clientHeight+1,'Camera dialog scrolls');
            check(video.height>30,'Preview collapsed');
            results.push({camera:true,width,height,font,dialogHeight:dialog.clientHeight,previewHeight:video.height,cancelBottom:cancel.bottom,pass:true});
            doc.querySelector('.tt-camera-close').click();
        } catch(error) { results.push({camera:true,width,height,font,pass:false,error:error.message}); }
        finally { cameraFrame?.remove(); }
    }
    output.textContent=JSON.stringify({pass:results.filter(x=>x.pass).length,fail:results.filter(x=>!x.pass).length,results},null,2);
    this.disabled=false;
};
