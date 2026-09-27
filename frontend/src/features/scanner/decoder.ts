import { prepareZXingModule, readBarcodes, type ReaderOptions } from 'zxing-wasm/reader';
// The decoder's wasm binary is part of the build and served by MealMate itself, never by a CDN
// (SEC-08). The CSP allows compiling it with 'wasm-unsafe-eval'.
import wasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url';

/** The retail barcodes on food packages (BAR-01). */
const FORMATS: ReaderOptions['formats'] = ['EAN13', 'EAN8', 'UPCA', 'UPCE'];

/** Frames are scaled down to this many pixels on their long side before decoding. */
const MAX_FRAME_SIZE = 1280;

export interface DecodeOptions {
  /**
   * Also look for the barcode turned by 90°. Costs about twice the time, so the scanner only
   * asks for it every few frames (see BarcodeScanner).
   */
  rotate?: boolean;
}

let prepared: Promise<unknown> | null = null;

/**
 * Loads and compiles the decoder from the app's own origin. Starts the download early (while the
 * camera starts); decoding waits for it anyway. A failed load can be retried.
 */
export function loadDecoder(): Promise<unknown> {
  prepared ??= prepareZXingModule({
    overrides: {
      locateFile: (path: string, prefix: string) =>
        path.endsWith('.wasm') ? wasmUrl : prefix + path,
    },
    fireImmediately: true,
  }).catch((error: unknown) => {
    prepared = null;
    throw error;
  });
  return prepared;
}

/**
 * The first valid EAN-13, EAN-8, UPC-A or UPC-E code in an image, or null. `image` is RGBA pixel
 * data (a camera frame) or an encoded image file (PNG, JPEG).
 */
export async function decodeBarcode(
  image: Pick<ImageData, 'data' | 'width' | 'height'> | Uint8Array,
  { rotate = false }: DecodeOptions = {},
): Promise<string | null> {
  const results = await readBarcodes(image as ImageData | Uint8Array, {
    formats: FORMATS,
    tryHarder: true,
    tryRotate: rotate,
    tryInvert: false,
    maxNumberOfSymbols: 1,
  });
  return results.find((result) => result.isValid)?.text ?? null;
}

/**
 * Decodes the frame a playing video currently shows, drawn on `canvas` (reused between frames).
 * Null while the video has no frame yet or nothing was found.
 */
export async function decodeVideoFrame(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  options: DecodeOptions = {},
): Promise<string | null> {
  const { videoWidth, videoHeight } = video;
  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !videoWidth || !videoHeight) {
    return null;
  }
  const scale = Math.min(1, MAX_FRAME_SIZE / Math.max(videoWidth, videoHeight));
  const width = Math.round(videoWidth * scale);
  const height = Math.round(videoHeight * scale);
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(video, 0, 0, width, height);
  return decodeBarcode(context.getImageData(0, 0, width, height), options);
}
