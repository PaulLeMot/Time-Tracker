'use strict';
document.documentElement.style.fontSize = new URLSearchParams(location.search).get('font') === '18' ? '18px' : '16px';
document.documentElement.dataset.fixtureReady = 'true';
const proto = HTMLMediaElement.prototype;
Object.defineProperty(proto, 'play', {value: async function () {}, configurable: true});
Object.defineProperty(proto, 'pause', {value: function () {}, configurable: true});
Object.defineProperty(proto, 'srcObject', {set(value) { this._stream = value; }, get() { return this._stream; }, configurable: true});
Object.defineProperty(proto, 'readyState', {get() { return 0; }, configurable: true});
document.getElementById('font').onchange = event => { document.documentElement.style.fontSize = event.target.value + 'px'; };
const camera = TTCamera.create({isSecureContext: true, getDecoder: async () => ({decode: () => null, dispose() {}}),
    mediaDevices: {enumerateDevices: async () => [{kind:'videoinput',deviceId:'rear1',label:'Back main'},{kind:'videoinput',deviceId:'rear2',label:'Back macro'}], getUserMedia: async () => {
        const track = Object.assign(new EventTarget(), {stop() {}, getCapabilities: () => ({torch: true, zoom: {min: 1, max: 3, step: .1}, focusMode: ['continuous']}),
            getSettings: () => ({facingMode: 'environment', deviceId:'rear1', zoom: 1}), applyConstraints: async () => {}});
        return {getTracks: () => [track], getVideoTracks: () => [track]};
    }}});
document.getElementById('camera').onclick = async event => {
    await camera.open({returnFocusTo: event.target, onDecoded() {}});
    const video = document.querySelector('video'); if (video) { video.style.aspectRatio = '9 / 16'; video.style.background = 'white url(/lab/labels/ean.png) center / contain no-repeat'; }
};
document.getElementById('confirm').onclick = async event => {
    const result = await TTCodeSearch.choose([{code: '90001', name: 'Синтетический товар А', marking: 'FSK', textSources: ['090001'], textAlternative: true}],
        event.target, null, {confirm: true});
    document.getElementById('result').textContent = result ? 'Товар подтверждён: ' + result.code : 'Подтверждение отменено';
};
