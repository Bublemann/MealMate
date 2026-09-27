// Renders the PNG app icons from assets/icon.svg. The PNGs are committed, so this only needs to
// run after the artwork changes:
//
//   npm install --no-save sharp && node scripts/generate-icons.mjs
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const SOURCE_SIZE = 512;
const source = await readFile(new URL('../assets/icon.svg', import.meta.url));

/** Rounded corners for "any"-purpose icons; maskable and Apple icons stay full-bleed. */
function roundedMask(size) {
  const radius = Math.round(size * 0.22);
  return Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">` +
      `<rect width="${size}" height="${size}" rx="${radius}"/></svg>`,
  );
}

const icons = [
  { file: 'public/icons/icon-192.png', size: 192, rounded: true },
  { file: 'public/icons/icon-512.png', size: 512, rounded: true },
  { file: 'public/icons/icon-maskable-512.png', size: 512, rounded: false },
  { file: 'public/apple-touch-icon.png', size: 180, rounded: false },
];

for (const { file, size, rounded } of icons) {
  let image = sharp(source, { density: (72 * size) / SOURCE_SIZE }).resize(size, size);
  if (rounded) {
    image = sharp(await image.png().toBuffer()).composite([
      { input: roundedMask(size), blend: 'dest-in' },
    ]);
  }
  const output = fileURLToPath(new URL(`../${file}`, import.meta.url));
  await image.png({ compressionLevel: 9 }).toFile(output);
  console.log(`${file} (${size}×${size})`);
}
