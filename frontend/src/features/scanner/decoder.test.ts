import { beforeAll, describe, expect, it } from 'vitest';
import { prepareZXingModule } from 'zxing-wasm/reader';
import wasm from 'zxing-wasm/reader/zxing_reader.wasm?url&inline';
import { prepareZXingModule as prepareWriter, writeBarcode } from 'zxing-wasm/writer';
import writerWasm from 'zxing-wasm/writer/zxing_writer.wasm?url&inline';
import ean13Rotated from './fixtures/ean13-rotated.png?inline';
import ean13 from './fixtures/ean13.png?inline';
import ean8 from './fixtures/ean8.png?inline';
import upca from './fixtures/upca.png?inline';
import upce from './fixtures/upce.png?inline';
import { decodeBarcode, framePasses, readBarcode } from './decoder';

// The real zxing-wasm decoder on sample images (made by scripts/generate-barcode-fixtures.mjs)
// and on camera-sized frames drawn here. The files come in as data URLs; the test environment
// can't fetch the wasm from the app's URL as a browser does, so the test hands it over.
async function bytes(dataUrl: string): Promise<Uint8Array> {
  return new Uint8Array(await (await fetch(dataUrl)).arrayBuffer());
}

beforeAll(async () => {
  const wasmBinary = (await bytes(wasm)).buffer as ArrayBuffer;
  await prepareZXingModule({ overrides: { wasmBinary }, fireImmediately: true });
  const writerBinary = (await bytes(writerWasm)).buffer as ArrayBuffer;
  await prepareWriter({ overrides: { wasmBinary: writerBinary }, fireImmediately: true });
});

type Pixels = Pick<ImageData, 'data' | 'width' | 'height'>;

/**
 * A grey `width` × `height` frame with some noise, like a camera image of a package, and in its
 * middle an EAN-13 code with `scale` pixels per bar.
 */
async function frame(
  width: number,
  height: number,
  { scale = 3, code = true } = {},
): Promise<Pixels> {
  const data = new Uint8ClampedArray(width * height * 4);
  let seed = 7;
  for (let i = 0; i < width * height; i += 1) {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    const grey = 110 + (seed % 40);
    data.set([grey, grey, grey, 255], i * 4);
  }
  if (code) {
    // One row of the symbol: its bars (0 black, 255 white), drawn with a quiet zone around.
    const { symbol } = await writeBarcode('4006381333931', { format: 'EAN13' });
    const quiet = 12 * scale;
    const codeWidth = symbol.width * scale + 2 * quiet;
    const codeHeight = 40 * scale;
    const left = Math.floor((width - codeWidth) / 2);
    const top = Math.floor((height - codeHeight) / 2);
    for (let y = 0; y < codeHeight; y += 1) {
      for (let x = 0; x < codeWidth; x += 1) {
        const module = Math.floor((x - quiet) / scale);
        const bar = module >= 0 && module < symbol.width ? (symbol.data[module] ?? 255) : 255;
        data.set([bar, bar, bar, 255], ((top + y) * width + left + x) * 4);
      }
    }
  }
  return { data, width, height };
}

describe('decodeBarcode', () => {
  it.each([
    ['EAN-13', ean13, '4006381333931'],
    ['EAN-8', ean8, '96385074'],
    // UPC-A and UPC-E come back as their GTIN-13 (a UPC-E code expanded): the form the server
    // stores anyway, and an 8-digit UPC-E code is never taken for an EAN-8 with the same digits.
    ['UPC-A', upca, '0036000291452'],
    ['UPC-E', upce, '0012345000065'],
  ])('reads an %s code', async (_format, image, expected) => {
    expect(await decodeBarcode(await bytes(image))).toBe(expected);
  });

  it('finds a barcode lying on its side in every frame (O-6)', async () => {
    expect(await decodeBarcode(await bytes(ean13Rotated))).toBe('4006381333931');
  });

  it('tells the format and the orientation of a code (diagnostics screen)', async () => {
    expect(await readBarcode(await bytes(ean8))).toEqual({
      text: '96385074',
      format: 'EAN8',
      orientation: 0,
    });
    const rotated = await readBarcode(await bytes(ean13Rotated));
    expect(rotated).toMatchObject({ text: '4006381333931', format: 'EAN13' });
    expect(Math.abs(rotated?.orientation ?? 0)).toBe(90);
  });

  it('finds nothing in pixels without a barcode', async () => {
    const width = 64;
    const height = 48;
    const blank = { data: new Uint8ClampedArray(width * height * 4).fill(255), width, height };

    expect(await decodeBarcode(blank)).toBeNull();
  });

  it('finds a code held in the guide within the crop of a camera frame', async () => {
    const [crop] = framePasses(1920, 1080);
    const camera = await frame(1920, 1080, { scale: 2 });

    expect(await decodeBarcode(cut(camera, crop!))).toBe('4006381333931');
  });

  it('decodes a camera-sized frame without a code quickly enough for the scanner', async () => {
    // A miss is the slow case: the crop and then the whole frame are searched in full. This only
    // guards against pathological slowness (a frame not scaled down, passes that multiply): the
    // bound is generous, about 100 times the usual 20 ms, so that a slow or busy CI machine
    // never fails it. A phone is a few times slower than a test machine.
    const [crop, full] = framePasses(1280, 720);
    const empty = await frame(1280, 720, { code: false });
    const images = [cut(empty, crop!), empty];
    await decodeBarcode(images[0]!); // warm up

    const started = performance.now();
    for (const image of images) expect(await decodeBarcode(image)).toBeNull();
    const elapsed = performance.now() - started;

    expect(full).toMatchObject({ width: 1280, height: 720 });
    expect(elapsed).toBeLessThan(2000);
  });
});

/** The pixels of `pass` in `image`, without scaling (the test has no canvas to scale with). */
function cut(image: Pixels, pass: { sx: number; sy: number; sw: number; sh: number }): Pixels {
  const data = new Uint8ClampedArray(pass.sw * pass.sh * 4);
  for (let y = 0; y < pass.sh; y += 1) {
    const start = ((pass.sy + y) * image.width + pass.sx) * 4;
    data.set(image.data.subarray(start, start + pass.sw * 4), y * pass.sw * 4);
  }
  return { data, width: pass.sw, height: pass.sh };
}

describe('framePasses', () => {
  it('crops the guide of a landscape frame and scales the whole frame down', () => {
    // The 4:3 preview shows the middle 1440 × 1080; the guide is 80 % × a third of it, plus a
    // quarter.
    expect(framePasses(1920, 1080)).toEqual([
      { sx: 240, sy: 315, sw: 1440, sh: 450, width: 1200, height: 375 },
      { sx: 0, sy: 0, sw: 1920, sh: 1080, width: 1280, height: 720 },
    ]);
  });

  it('crops the middle of a portrait frame (an iPhone held upright)', () => {
    expect(framePasses(1080, 1920)).toEqual([
      { sx: 0, sy: 791, sw: 1080, sh: 338, width: 1200, height: 376 },
      { sx: 0, sy: 0, sw: 1080, sh: 1920, width: 720, height: 1280 },
    ]);
  });

  it('scales the crop of a small frame up, never the whole frame', () => {
    expect(framePasses(640, 480)).toEqual([
      { sx: 0, sy: 140, sw: 640, sh: 200, width: 1200, height: 375 },
      { sx: 0, sy: 0, sw: 640, sh: 480, width: 640, height: 480 },
    ]);
  });
});
