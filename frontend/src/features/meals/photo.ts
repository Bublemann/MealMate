/** The long edge a photo is shrunk to on the phone before uploading (MEAL-04). */
export const MAX_PHOTO_EDGE = 1600;
const JPEG_QUALITY = 0.85;

/** The file types the photo input offers; the server decodes and checks them itself (SEC-07). */
export const PHOTO_ACCEPT = 'image/jpeg,image/png,image/webp';

export interface PreparedPhoto {
  blob: Blob;
  fileName: string;
}

/** The size of an image scaled down to at most `maxEdge` on its long side (never enlarged). */
export function fitWithin(
  width: number,
  height: number,
  maxEdge = MAX_PHOTO_EDGE,
): { width: number; height: number } {
  const scale = Math.min(1, maxEdge / Math.max(width, height));
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

function canvasToJpeg(canvas: HTMLCanvasElement): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
}

/**
 * Shrinks a photo to at most 1600 px on its long edge and re-encodes it as JPEG (MEAL-04), so a
 * 12-megapixel iPhone photo uploads quickly. The orientation from the EXIF data is applied
 * while decoding. If the browser can't do any step, the original file is uploaded instead: the
 * server shrinks, rotates and re-encodes every photo anyway.
 */
export async function preparePhoto(file: File): Promise<PreparedPhoto> {
  const original: PreparedPhoto = { blob: file, fileName: file.name || 'photo' };
  let bitmap: ImageBitmap | undefined;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const { width, height } = fitWithin(bitmap.width, bitmap.height);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) return original;
    // JPEG has no transparency: transparent areas (PNG, WebP) become white instead of black.
    context.fillStyle = 'white';
    context.fillRect(0, 0, width, height);
    context.drawImage(bitmap, 0, 0, width, height);
    const blob = await canvasToJpeg(canvas);
    return blob && blob.size > 0 ? { blob, fileName: 'photo.jpg' } : original;
  } catch {
    return original;
  } finally {
    bitmap?.close();
  }
}

/** The multipart body of `PUT /api/meals/{id}/photo`: the photo in the field `file`. */
export function photoFormData({ blob, fileName }: PreparedPhoto): FormData {
  const form = new FormData();
  form.append('file', blob, fileName);
  return form;
}
