/** EAN-8 / UPC-E, UPC-A and EAN-13 (BAR-01). */
const LENGTHS = new Set([8, 12, 13]);

/**
 * The digits of a typed barcode without spaces, or null if it can't be one. The server checks
 * the check digit and turns it into its stored form (422 `barcode` `invalid_format`).
 */
export function typedBarcode(text: string): string | null {
  const code = text.replace(/\s+/g, '');
  return /^\d+$/.test(code) && LENGTHS.has(code.length) ? code : null;
}
