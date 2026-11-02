/* Camera1.1: dedicated barcode worker. No frame persistence or network upload. */
'use strict';
let zxing, legacy, nativeDetector;
const formats = {EAN13: 'EAN_13', Code128: 'CODE_128', ean_13: 'EAN_13', code_128: 'CODE_128'};

async function initialize() {
    // Native support is optional and checked by format, never assumed from the browser name.
    if (self.BarcodeDetector) {
        try {
            const supported = await self.BarcodeDetector.getSupportedFormats();
            const selected = ['ean_13', 'code_128'].filter(f => supported.includes(f));
            if (selected.length) nativeDetector = new self.BarcodeDetector({formats: selected});
        } catch (_) { /* Keep the local decoder. */ }
    }
    try {
        importScripts('/static/vendor/zxing-wasm-3.1.6/reader.js');
        zxing = self.ZXingWASM;
        await zxing.prepareZXingModule({overrides: {locateFile: name => {
            if (name.endsWith('.wasm')) return '/static/vendor/zxing-wasm-3.1.6/zxing_reader.wasm';
            throw Error('Unexpected decoder resource');
        }}, fireImmediately: true});
    } catch (_) {
        zxing = null;
        importScripts('/static/vendor/zxing-library-0.23.0.min.js');
        const hints = new Map([[ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.CODE_128]],
            [ZXing.DecodeHintType.TRY_HARDER, true]]);
        legacy = {reader: new ZXing.MultiFormatOneDReader(hints), hints};
    }
    return {engine: zxing ? 'zxing-cpp-wasm' : 'zxing-js', native: !!nativeDetector};
}

function quality(image) {
    let sum = 0, edges = 0, n = 0;
    const {data, width, height} = image;
    for (let y = 1; y < height; y += 6) for (let x = 1; x < width; x += 6) {
        const i = (y * width + x) * 4, g = (data[i] + 2 * data[i + 1] + data[i + 2]) / 4;
        sum += g; edges += Math.abs(g - (data[i - 4] + 2 * data[i - 3] + data[i - 2]) / 4); n++;
    }
    return {brightness: n ? sum / n : 0, edges: n ? edges / n : 0};
}

function legacyRead(image, rotated = false) {
    const {width, height, data} = image;
    const gray = new Uint8ClampedArray(width * height);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
        const p = (y * width + x) * 4;
        gray[rotated ? (width - 1 - x) * height + y : y * width + x] = (data[p] + 2 * data[p + 1] + data[p + 2]) >> 2;
    }
    try {
        const result = legacy.reader.decode(new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(
            new ZXing.RGBLuminanceSource(gray, rotated ? height : width, rotated ? width : height))), legacy.hints);
        return [{rawValue: result.getText(), format: ZXing.BarcodeFormat[result.getBarcodeFormat()]}];
    } catch (e) {
        if (e instanceof ZXing.NotFoundException || e instanceof ZXing.ChecksumException || e instanceof ZXing.FormatException) return [];
        throw e;
    }
}

function contrast(image) {
    const histogram = new Uint32Array(256), {data} = image;
    for (let i = 0; i < data.length; i += 4) histogram[(data[i] + 2 * data[i + 1] + data[i + 2]) >> 2]++;
    const count = data.length / 4, tail = count * .02;
    let low = 0, high = 255, n = 0;
    while (low < 255 && (n += histogram[low]) < tail) low++;
    n = 0; while (high > low && (n += histogram[high]) < tail) high--;
    if (high - low < 16 || high - low > 220) return false;
    for (let i = 0; i < data.length; i += 4) {
        const v = Math.max(0, Math.min(255, (((data[i] + 2 * data[i + 1] + data[i + 2]) / 4) - low) * 255 / (high - low)));
        data[i] = data[i + 1] = data[i + 2] = v;
    }
    return true;
}

async function read(image, harder) {
    if (zxing) return (await zxing.readBarcodes(image, {formats: ['EAN13', 'Code128'], tryHarder: harder,
        tryRotate: true, tryInvert: harder, tryDownscale: harder, minLineCount: 2, maxNumberOfSymbols: 3,
        returnErrors: false})).filter(x => x.isValid !== false && !x.error).map(x => ({rawValue: x.text, format: formats[x.format]}));
    return legacyRead(image).concat(legacyRead(image, true));
}

self.onmessage = async ({data: job}) => {
    try {
        if (job.action === 'init') { self.postMessage({id: job.id, result: await initialize()}); return; }
        if (job.action !== 'decode') throw Error('Unsupported decoder action');
        const image = new ImageData(new Uint8ClampedArray(job.buffer), job.width, job.height);
        const q = quality(image), start = performance.now();
        let result = [];
        if (nativeDetector) {
            try { result = (await nativeDetector.detect(image)).map(x => ({rawValue: x.rawValue, format: formats[x.format]})); }
            catch (_) { nativeDetector = null; }
        }
        if (!result.length) result = await read(image, !!job.harder);
        if (!result.length && job.harder && contrast(image)) result = await read(image, true);
        const values = [...new Map(result.filter(x => x.format && x.rawValue).map(x => [x.format + ':' + x.rawValue, x])).values()];
        image.data.fill(0);
        self.postMessage({id: job.id, result: {value: values.length === 1 ? values[0] : null, ambiguous: values.length > 1,
            quality: q, decodeMs: performance.now() - start}});
    } catch (_) { self.postMessage({id: job.id, error: 'decoder'}); }
};
