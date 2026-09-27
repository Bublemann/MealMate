const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Whether `value` is a UUID of any version, e.g. an id from the URL before it goes into a path. */
export function isUuid(value: string): boolean {
  return UUID.test(value);
}

/**
 * A new UUIDv7 (RFC 9562): 48 bits of Unix time in milliseconds, then random bits. Ids made on
 * the phone (e.g. extra items) let the server recognise a request that is sent again. Uses
 * `crypto.getRandomValues`, which, unlike `crypto.randomUUID`, also works outside secure contexts.
 */
export function uuidv7(now: number = Date.now()): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let time = Math.floor(now);
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = time % 256;
    time = Math.floor(time / 256);
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x70; // version 7
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80; // variant 10
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
