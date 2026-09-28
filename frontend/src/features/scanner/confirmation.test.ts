import { describe, expect, it } from 'vitest';
import { CONFIRM_WINDOW_MS, createConfirmation } from './confirmation';

const EAN13 = { text: '4006381333931', format: 'EAN13', orientation: 0 };
const MISREAD = { text: '4006381333924', format: 'EAN13', orientation: 0 };

describe('createConfirmation', () => {
  it('takes a code read in two frames', () => {
    const confirm = createConfirmation();

    expect(confirm(EAN13, 1000)).toBeNull();
    expect(confirm({ ...EAN13, orientation: 90 }, 1250)).toEqual({ ...EAN13, orientation: 90 });
  });

  it('allows frames without a code in between, within the window', () => {
    const confirm = createConfirmation();

    expect(confirm(EAN13, 1000)).toBeNull();
    // Frames at 1250, 1500 and 2000 found nothing and never reach the confirmation.
    expect(confirm(EAN13, 1000 + CONFIRM_WINDOW_MS)).toEqual(EAN13);
  });

  it('does not take two different codes', () => {
    const confirm = createConfirmation();

    expect(confirm(EAN13, 1000)).toBeNull();
    expect(confirm(MISREAD, 1250)).toBeNull();
  });

  it('keeps a code across a misread in between (A B A)', () => {
    const confirm = createConfirmation();

    expect(confirm(EAN13, 1000)).toBeNull();
    expect(confirm(MISREAD, 1250)).toBeNull();
    expect(confirm(EAN13, 1500)).toEqual(EAN13);
  });

  it('confirms whichever code is read twice first when readings alternate', () => {
    const confirm = createConfirmation();

    expect(confirm(MISREAD, 1000)).toBeNull();
    expect(confirm(EAN13, 1100)).toBeNull();
    expect(confirm(MISREAD, 1200)).toEqual(MISREAD);
  });

  it('forgets a code once its window has passed (A, too late, A)', () => {
    const confirm = createConfirmation();

    expect(confirm(EAN13, 1000)).toBeNull();
    expect(confirm(MISREAD, 1000 + CONFIRM_WINDOW_MS)).toBeNull();
    expect(confirm(EAN13, 1001 + CONFIRM_WINDOW_MS)).toBeNull();
    // MISREAD's first reading is still within its window.
    expect(confirm(MISREAD, 1100 + CONFIRM_WINDOW_MS)).toEqual(MISREAD);
  });

  it('does not take a second reading that comes too late, but counts it as a first', () => {
    const confirm = createConfirmation();

    expect(confirm(EAN13, 1000)).toBeNull();
    expect(confirm(EAN13, 1001 + CONFIRM_WINDOW_MS)).toBeNull();
    expect(confirm(EAN13, 1250 + CONFIRM_WINDOW_MS)).toEqual(EAN13);
  });

  it('needs two new readings after a confirmation', () => {
    const confirm = createConfirmation(500);

    expect(confirm(EAN13, 0)).toBeNull();
    expect(confirm(EAN13, 100)).toEqual(EAN13);
    expect(confirm(EAN13, 200)).toBeNull();
    expect(confirm(EAN13, 300)).toEqual(EAN13);
  });
});
