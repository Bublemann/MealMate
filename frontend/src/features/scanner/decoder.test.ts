import { beforeAll, describe, expect, it } from 'vitest';
import { prepareZXingModule } from 'zxing-wasm/reader';
import wasm from 'zxing-wasm/reader/zxing_reader.wasm?url&inline';
import ean13Rotated from './fixtures/ean13-rotated.png?inline';
import ean13 from './fixtures/ean13.png?inline';
import ean8 from './fixtures/ean8.png?inline';
import upca from './fixtures/upca.png?inline';
import { decodeBarcode } from './decoder';

// The real zxing-wasm decoder on sample images (made by scripts/generate-barcode-fixtures.mjs).
// The files come in as data URLs; the test environment can't fetch the wasm from the app's URL
// as a browser does, so the test hands it over.
async function bytes(dataUrl: string): Promise<Uint8Array> {
  return new Uint8Array(await (await fetch(dataUrl)).arrayBuffer());
}

beforeAll(async () => {
  const wasmBinary = (await bytes(wasm)).buffer as ArrayBuffer;
  await prepareZXingModule({ overrides: { wasmBinary }, fireImmediately: true });
});

describe('decodeBarcode', () => {
  it.each([
    ['EAN-13', ean13, '4006381333931'],
    ['EAN-8', ean8, '96385074'],
    // UPC-A comes back as its GTIN-13 (a leading 0), the form the server stores anyway.
    ['UPC-A', upca, '0036000291452'],
  ])('reads an %s code', async (_format, image, expected) => {
    expect(await decodeBarcode(await bytes(image))).toBe(expected);
  });

  it('finds a barcode lying on its side only when asked to look rotated (O-6)', async () => {
    const image = await bytes(ean13Rotated);

    expect(await decodeBarcode(image)).toBeNull();
    expect(await decodeBarcode(image, { rotate: true })).toBe('4006381333931');
  });

  it('finds nothing in pixels without a barcode', async () => {
    const width = 64;
    const height = 48;
    const blank = { data: new Uint8ClampedArray(width * height * 4).fill(255), width, height };

    expect(await decodeBarcode(blank)).toBeNull();
  });
});
