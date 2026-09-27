// Writes the sample barcode images the scanner tests decode with the real zxing-wasm reader
// (src/features/scanner/decoder.test.ts). The PNGs are committed, so this only needs to run
// when the samples change:
//
//   node scripts/generate-barcode-fixtures.mjs
//
// The output is deterministic: zxing-wasm's writer (zint) renders the same pixels for the same
// input and options.
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { prepareZXingModule, writeBarcode } from 'zxing-wasm/writer';

const require = createRequire(import.meta.url);
const wasm = await readFile(require.resolve('zxing-wasm/writer/zxing_writer.wasm'));
prepareZXingModule({ overrides: { wasmBinary: wasm.buffer } });

const samples = [
  { file: 'ean13.png', format: 'EAN13', text: '4006381333931' },
  { file: 'ean8.png', format: 'EAN8', text: '96385074' },
  { file: 'upca.png', format: 'UPCA', text: '036000291452' },
  // Lying on its side, as a phone may deliver a camera frame (O-6).
  { file: 'ean13-rotated.png', format: 'EAN13', text: '4006381333931', rotate: 90 },
];

for (const { file, format, text, rotate = 0 } of samples) {
  const { image, error } = await writeBarcode(text, { format, scale: 2, rotate });
  if (!image) throw new Error(`${file}: ${error}`);
  const output = new URL(`../src/features/scanner/fixtures/${file}`, import.meta.url);
  await writeFile(output, new Uint8Array(await image.arrayBuffer()));
  console.log(`${file} (${format} ${text}${rotate ? `, rotated ${rotate}°` : ''})`);
}
