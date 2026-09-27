import { afterEach, describe, expect, it, vi } from 'vitest';
import { fitWithin, photoFormData, preparePhoto } from './photo';

const JPEG = new Blob(['jpeg-bytes'], { type: 'image/jpeg' });

function photo(name = 'IMG_0001.HEIC.png'): File {
  return new File(['original-bytes'], name, { type: 'image/png' });
}

interface FakeCanvas {
  context: {
    fillStyle: string;
    fillRect: ReturnType<typeof vi.fn>;
    drawImage: ReturnType<typeof vi.fn>;
  };
  toBlob: ReturnType<typeof vi.fn<(type?: string, quality?: unknown) => void>>;
  sizes: { width: number; height: number }[];
}

/** jsdom has no canvas: a 2D context and toBlob that record what they are asked to do. */
function fakeCanvas(result: Blob | null = JPEG, context = true): FakeCanvas {
  const fake: FakeCanvas = {
    context: { fillStyle: '', fillRect: vi.fn(), drawImage: vi.fn() },
    toBlob: vi.fn<(type?: string, quality?: unknown) => void>(),
    sizes: [],
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (
    this: HTMLCanvasElement,
  ) {
    fake.sizes.push({ width: this.width, height: this.height });
    return (context ? fake.context : null) as unknown as CanvasRenderingContext2D;
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(
    (callback: BlobCallback, type?: string, quality?: unknown) => {
      fake.toBlob(type, quality);
      callback(result);
    },
  );
  return fake;
}

function stubBitmap(width: number, height: number) {
  const bitmap = { width, height, close: vi.fn() };
  const create = vi.fn().mockResolvedValue(bitmap);
  vi.stubGlobal('createImageBitmap', create);
  return { bitmap, create };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('fitWithin', () => {
  it('scales the long edge down to 1600 px and keeps the aspect ratio', () => {
    expect(fitWithin(4032, 3024)).toEqual({ width: 1600, height: 1200 });
    expect(fitWithin(3024, 4032)).toEqual({ width: 1200, height: 1600 });
  });

  it('never enlarges a small image', () => {
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });
});

describe('preparePhoto', () => {
  it('draws the upright image at most 1600 px wide and encodes it as JPEG (MEAL-04)', async () => {
    const canvas = fakeCanvas();
    const { bitmap, create } = stubBitmap(4032, 3024);
    const file = photo();

    const prepared = await preparePhoto(file);

    expect(create).toHaveBeenCalledWith(file, { imageOrientation: 'from-image' });
    expect(canvas.sizes).toEqual([{ width: 1600, height: 1200 }]);
    expect(canvas.context.fillStyle).toBe('white');
    expect(canvas.context.drawImage).toHaveBeenCalledWith(bitmap, 0, 0, 1600, 1200);
    expect(canvas.toBlob).toHaveBeenCalledWith('image/jpeg', 0.85);
    expect(prepared).toEqual({ blob: JPEG, fileName: 'photo.jpg' });
    expect(bitmap.close).toHaveBeenCalled();
  });

  it('uploads the original when the browser cannot decode the file', async () => {
    fakeCanvas();
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new DOMException('bad')));
    const file = photo('dish.webp');

    await expect(preparePhoto(file)).resolves.toEqual({ blob: file, fileName: 'dish.webp' });
  });

  it('uploads the original without createImageBitmap (old browsers)', async () => {
    vi.stubGlobal('createImageBitmap', undefined);
    const file = photo();

    await expect(preparePhoto(file)).resolves.toEqual({ blob: file, fileName: file.name });
  });

  it('uploads the original when there is no 2D context', async () => {
    fakeCanvas(JPEG, false);
    const { bitmap } = stubBitmap(100, 100);
    const file = photo();

    await expect(preparePhoto(file)).resolves.toEqual({ blob: file, fileName: file.name });
    expect(bitmap.close).toHaveBeenCalled();
  });

  it('uploads the original when encoding fails', async () => {
    fakeCanvas(null);
    stubBitmap(100, 100);
    const file = new File(['x'], '', { type: 'image/jpeg' });

    await expect(preparePhoto(file)).resolves.toEqual({ blob: file, fileName: 'photo' });
  });
});

describe('photoFormData', () => {
  it('puts the photo into the field `file`', () => {
    const form = photoFormData({ blob: JPEG, fileName: 'photo.jpg' });

    const sent = form.get('file');
    expect(sent).toBeInstanceOf(File);
    expect((sent as File).name).toBe('photo.jpg');
    expect((sent as File).size).toBe(JPEG.size);
  });
});
