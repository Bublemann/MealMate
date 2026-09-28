import { prepareZXingModule, readBarcodes, type ReaderOptions } from 'zxing-wasm/reader';
// The decoder's wasm binary is part of the build and served by MealMate itself, never by a CDN
// (SEC-08). The CSP allows compiling it with 'wasm-unsafe-eval'.
import wasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url';
import { GUIDE, PREVIEW_ASPECT } from './guide';

/** The retail barcodes on food packages (BAR-01). */
const FORMATS: ReaderOptions['formats'] = ['EAN13', 'EAN8', 'UPCA', 'UPCE'];

/**
 * How every image is searched. Decoding stays on the main thread: a frame without a code (the
 * slow case: the crop, then the whole frame) takes about 20 ms on a test machine (see
 * decoder.test.ts), a phone a few times that, and the scanner decodes one frame at a time with a
 * pause in between. A worker (another bundle, the wasm loaded into it) isn't worth that.
 *
 * The binarizer stays zxing's default, LocalAverage: for linear codes such as EAN it already
 * thresholds each scanned line by that line's own histogram (GlobalHistogram), so a second pass
 * with GlobalHistogram would double the time without reading more codes.
 */
const READER_OPTIONS: ReaderOptions = {
  formats: FORMATS,
  // Accuracy over speed: a frame costs a few more milliseconds.
  tryHarder: true,
  // In every frame: iOS 26 Home Screen apps may deliver the camera image turned by 90° (O-6), and
  // codes on bottles are often printed across the bottle.
  tryRotate: true,
  // zxing tries an inverted image (light bars on dark) only for formats that allow it, which
  // EAN and UPC don't: such a code isn't read with `tryInvert` either (tried with zxing-wasm 3.1).
  tryInvert: false,
  maxNumberOfSymbols: 1,
};

/** The crop decoded first is the guide and a quarter more, for a code that sticks out a bit. */
const CROP_MARGIN = 0.25;
/**
 * The crop is scaled to this many pixels on its long side, up if the camera image is small: a
 * code that fills the guide then has about 10 pixels per bar, and the crop decodes quickly.
 */
const CROP_SIZE = 1200;
/** The whole frame is scaled down to this many pixels on its long side before decoding. */
const MAX_FRAME_SIZE = 1280;

/** A barcode found in a camera frame. */
export interface DecodedBarcode {
  text: string;
  /** zxing's format name, e.g. `EAN13` or `UPCE`. */
  format: string;
  /** How far the barcode was turned in the frame, in degrees (O-6: iOS 26 rotation issue). */
  orientation: number;
}

/**
 * A part of a camera frame (`sx`, `sy`, `sw`, `sh` in the frame's pixels) and the size it is drawn
 * at (`width`, `height`) for decoding.
 */
export interface FramePass {
  sx: number;
  sy: number;
  sw: number;
  sh: number;
  width: number;
  height: number;
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
 * data (a camera frame) or an encoded image file (PNG, JPEG). UPC-A and UPC-E codes come back as
 * their 13-digit GTIN, so a scanned UPC-E code is never taken for an EAN-8 with the same digits.
 */
export async function decodeBarcode(
  image: Pick<ImageData, 'data' | 'width' | 'height'> | Uint8Array,
): Promise<string | null> {
  return (await readBarcode(image))?.text ?? null;
}

/** Like decodeBarcode, with the format and orientation (shown by the diagnostics screen). */
export async function readBarcode(
  image: Pick<ImageData, 'data' | 'width' | 'height'> | Uint8Array,
): Promise<DecodedBarcode | null> {
  const results = await readBarcodes(image as ImageData | Uint8Array, READER_OPTIONS);
  const found = results.find((result) => result.isValid);
  return found ? { text: found.text, format: found.format, orientation: found.orientation } : null;
}

/**
 * What to decode of a `videoWidth` × `videoHeight` frame, in order: the part under the guide
 * (where the user holds the code: fewer pixels to search, more of them per bar), then, on a miss,
 * the whole frame (a code outside the guide, or a frame turned by 90°, O-6).
 */
export function framePasses(videoWidth: number, videoHeight: number): FramePass[] {
  const wide = videoWidth / videoHeight > PREVIEW_ASPECT;
  const shownWidth = wide ? videoHeight * PREVIEW_ASPECT : videoWidth;
  const shownHeight = wide ? videoHeight : videoWidth / PREVIEW_ASPECT;
  const sw = Math.min(videoWidth, Math.round(shownWidth * GUIDE.width * (1 + CROP_MARGIN)));
  const sh = Math.min(videoHeight, Math.round(shownHeight * GUIDE.height * (1 + CROP_MARGIN)));
  const cropScale = CROP_SIZE / Math.max(sw, sh);
  const frameScale = Math.min(1, MAX_FRAME_SIZE / Math.max(videoWidth, videoHeight));
  // On a frame turned by 90° (O-6) the crop cuts across the code: the whole-frame pass finds it.
  return [
    {
      sx: Math.round((videoWidth - sw) / 2),
      sy: Math.round((videoHeight - sh) / 2),
      sw,
      sh,
      width: Math.round(sw * cropScale),
      height: Math.round(sh * cropScale),
    },
    {
      sx: 0,
      sy: 0,
      sw: videoWidth,
      sh: videoHeight,
      width: Math.round(videoWidth * frameScale),
      height: Math.round(videoHeight * frameScale),
    },
  ];
}

/**
 * Decodes the frame a playing video currently shows (see framePasses), drawn on `canvas` (reused
 * between frames). Null while the video has no frame yet or nothing was found.
 */
export async function decodeVideoFrame(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
): Promise<DecodedBarcode | null> {
  const { videoWidth, videoHeight } = video;
  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !videoWidth || !videoHeight) {
    return null;
  }
  const passes = framePasses(videoWidth, videoHeight);
  // Large enough for every pass, so that it isn't resized (and cleared) twice per frame.
  const width = Math.max(...passes.map((pass) => pass.width));
  const height = Math.max(...passes.map((pass) => pass.height));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return null;
  for (const pass of passes) {
    context.drawImage(video, pass.sx, pass.sy, pass.sw, pass.sh, 0, 0, pass.width, pass.height);
    const found = await readBarcode(context.getImageData(0, 0, pass.width, pass.height));
    if (found) return found;
  }
  return null;
}
