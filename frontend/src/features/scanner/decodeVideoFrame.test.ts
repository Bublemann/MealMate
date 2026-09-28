import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readBarcodes } from 'zxing-wasm/reader';
import { decodeVideoFrame } from './decoder';

// jsdom has no canvas: the canvas is a fake that records what is drawn, and zxing is mocked
// (decoder.test.ts decodes real pixels). Here: what is decoded of a frame, in which order.
vi.mock('zxing-wasm/reader', () => ({ prepareZXingModule: vi.fn(), readBarcodes: vi.fn() }));

const FOUND = { isValid: true, text: '4006381333931', format: 'EAN13', orientation: 0 };

function fakeVideo({ width = 1920, height = 1080, readyState = 4 } = {}) {
  return { videoWidth: width, videoHeight: height, readyState } as unknown as HTMLVideoElement;
}

function fakeCanvas() {
  const context = {
    drawImage: vi.fn(),
    getImageData: vi.fn((_x: number, _y: number, width: number, height: number) => ({
      data: new Uint8ClampedArray(0),
      width,
      height,
    })),
  };
  const canvas = { width: 0, height: 0, getContext: vi.fn(() => context) };
  return { canvas: canvas as unknown as HTMLCanvasElement, context, fake: canvas };
}

beforeEach(() => {
  vi.mocked(readBarcodes).mockReset().mockResolvedValue([]);
});

describe('decodeVideoFrame', () => {
  it('decodes the part under the guide first, then the whole frame on a miss', async () => {
    vi.mocked(readBarcodes)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([FOUND as never]);
    const { canvas, context, fake } = fakeCanvas();
    const video = fakeVideo();

    expect(await decodeVideoFrame(video, canvas)).toEqual({
      text: '4006381333931',
      format: 'EAN13',
      orientation: 0,
    });

    expect(context.drawImage.mock.calls).toEqual([
      // The crop, scaled to 1200 px on its long side …
      [video, 240, 315, 1440, 450, 0, 0, 1200, 375],
      // … then the whole frame, scaled down to 1280 px.
      [video, 0, 0, 1920, 1080, 0, 0, 1280, 720],
    ]);
    expect(context.getImageData.mock.calls).toEqual([
      [0, 0, 1200, 375],
      [0, 0, 1280, 720],
    ]);
    // One canvas large enough for both, not resized between them.
    expect([fake.width, fake.height]).toEqual([1280, 720]);
    expect(fake.getContext).toHaveBeenCalledWith('2d', { willReadFrequently: true });
  });

  it('stops at the crop when it holds the code', async () => {
    vi.mocked(readBarcodes).mockResolvedValue([FOUND as never]);
    const { canvas, context } = fakeCanvas();

    expect(await decodeVideoFrame(fakeVideo(), canvas)).toMatchObject({ text: '4006381333931' });
    expect(context.drawImage).toHaveBeenCalledTimes(1);
  });

  it('searches every image turned as well, harder, for retail codes only', async () => {
    const { canvas } = fakeCanvas();

    expect(await decodeVideoFrame(fakeVideo(), canvas)).toBeNull();

    expect(readBarcodes).toHaveBeenCalledTimes(2);
    for (const [, options] of vi.mocked(readBarcodes).mock.calls) {
      expect(options).toEqual({
        formats: ['EAN13', 'EAN8', 'UPCA', 'UPCE'],
        tryHarder: true,
        tryRotate: true,
        tryInvert: false,
        maxNumberOfSymbols: 1,
      });
    }
  });

  it('skips a result with a wrong check digit', async () => {
    vi.mocked(readBarcodes).mockResolvedValue([{ ...FOUND, isValid: false } as never]);
    const { canvas } = fakeCanvas();

    expect(await decodeVideoFrame(fakeVideo(), canvas)).toBeNull();
  });

  it('waits for the video to have a frame', async () => {
    const { canvas, context } = fakeCanvas();

    expect(await decodeVideoFrame(fakeVideo({ readyState: 1 }), canvas)).toBeNull();
    expect(await decodeVideoFrame(fakeVideo({ width: 0, height: 0 }), canvas)).toBeNull();
    expect(context.drawImage).not.toHaveBeenCalled();
  });
});
