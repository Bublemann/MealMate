/**
 * The frame the scanner draws over its preview, as fractions of the preview's width and height,
 * and the preview's aspect ratio (its `aspect-[4/3]`). BarcodeScanner places the frame with these
 * numbers and decoder.ts crops the camera image by them. The video fills the preview
 * (`object-cover`), so the preview shows the middle of the camera image.
 */
export const GUIDE = { width: 0.8, height: 1 / 3 } as const;
export const PREVIEW_ASPECT = 4 / 3;
