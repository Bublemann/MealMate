import { describe, expect, it } from 'vitest';
import type { components } from '@/api/generated/schema';
import { BEN } from '@/test/api';
import { CATEGORIES } from '@/test/ingredients';
import { CANDLES_EXTRA_ID, checkedBy, doneList, listDetail, shoppingList } from '@/test/lists';
import { ME } from '@/test/meals';
import { applyPending, extraLineKey, type PendingList } from './applyPending';

type Op = components['schemas']['Op'];

const OPTIONS = {
  me: ME,
  categoryIds: new Map(CATEGORIES.map((category) => [category.key, category.id])),
};
const AT = '2026-09-26T13:45:00Z';
const NEW_ID = '0190c0de-0000-7000-8000-0000000000e1';

let opCount = 0;
function op<T extends Op['type']>(
  type: T,
  payload: Extract<Op, { type: T }>['payload'],
  at = AT,
): Op {
  opCount += 1;
  return {
    type,
    payload,
    at,
    op_id: `0190c0de-0000-7000-8000-${String(opCount).padStart(12, '0')}`,
  } as Op;
}

function lineOf(list: PendingList, name: string) {
  const line = list.lines.find((entry) => entry.name === name);
  if (!line) throw new Error(`no line ${name}`);
  return line;
}

describe('applyPending', () => {
  it('leaves the list as it is without ops', () => {
    const list = shoppingList();
    const shown = applyPending(list, [], OPTIONS);
    expect(shown).toEqual({ ...list, pendingFinish: false });
    expect(shown.lines.some((line) => 'pending' in line)).toBe(false);
  });

  it.each([
    {
      name: 'checks a line off, as mine',
      ops: [op('line.check', { line_key: 'i:ing-zwiebeln', checked: true })],
      line: 'Zwiebeln',
      expected: { checked: true, checked_at: AT, checked_by: ME, pending: true },
    },
    {
      name: 'unchecks a line checked by someone else',
      ops: [op('line.check', { line_key: 'i:ing-milch', checked: false })],
      line: 'Milch',
      expected: { checked: false, checked_by: null, pending: true },
    },
    {
      name: 'checks off a line that needs more, which clears the badge',
      ops: [op('line.check', { line_key: 'i:ing-mehl', checked: true })],
      line: 'Mehl',
      expected: { checked: true, needs_more: null, new: false, pending: true },
    },
    {
      name: 'ignores a check-off older than the line’s last one (SYNC-06)',
      ops: [op('line.check', { line_key: 'i:ing-milch', checked: false }, '2026-09-26T13:00:00Z')],
      line: 'Milch',
      expected: { checked: true, checked_by: BEN },
    },
    {
      name: 'takes the last of several taps',
      ops: [
        op('line.check', { line_key: 'i:ing-zwiebeln', checked: true }),
        op('line.check', { line_key: 'i:ing-zwiebeln', checked: false }, '2026-09-26T13:46:00Z'),
      ],
      line: 'Zwiebeln',
      expected: { checked: false, checked_at: '2026-09-26T13:46:00Z', pending: true },
    },
  ])('$name', ({ ops, line, expected }) => {
    const shown = applyPending(shoppingList(), ops, OPTIONS);
    expect(lineOf(shown, line)).toMatchObject(expected);
    // Only a line an op changed is waiting to be sent.
    expect(lineOf(shown, line).pending).toBe('pending' in expected ? expected.pending : undefined);
  });

  it('adds a free-text item as a new line in its category, by name', () => {
    const shown = applyPending(
      shoppingList(),
      [op('extra.add', { extra_id: NEW_ID, text: 'Äpfel', category_key: 'fruit_vegetables' })],
      OPTIONS,
    );

    const added = lineOf(shown, 'Äpfel');
    expect(added).toMatchObject({
      key: extraLineKey(NEW_ID),
      kind: 'text',
      category_id: 'cat-fruit_vegetables',
      amount_text: null,
      checked: false,
      new: true,
      pending: true,
    });
    expect(added.sources).toEqual([expect.objectContaining({ kind: 'extra', extra_id: NEW_ID })]);
    // Before Zwiebeln, the other line of its category.
    expect(shown.lines.map((line) => line.name).slice(0, 2)).toEqual(['Äpfel', 'Zwiebeln']);
    expect(shown.extra_items.at(-1)).toMatchObject({
      id: NEW_ID,
      text: 'Äpfel',
      added_by: ME,
      pending: true,
    });
  });

  it('adds to Other without a known category, at the end of its lines', () => {
    const shown = applyPending(
      shoppingList(),
      [op('extra.add', { extra_id: NEW_ID, text: 'Zahnseide', amount_text: '1 Packung' })],
      OPTIONS,
    );
    expect(shown.lines.at(-1)).toMatchObject({
      name: 'Zahnseide',
      category_id: 'cat-other',
      amount_text: '1 Packung',
    });
  });

  it('adds an item once, and checks it off in the same run', () => {
    const add = op('extra.add', { extra_id: NEW_ID, text: 'Servietten' });
    const check = op('line.check', { line_key: extraLineKey(NEW_ID), checked: true });
    const shown = applyPending(shoppingList(), [add, add, check], OPTIONS);
    expect(shown.lines.filter((line) => line.name === 'Servietten')).toEqual([
      expect.objectContaining({ checked: true, pending: true }),
    ]);
  });

  it('renames a free-text item and its line', () => {
    const shown = applyPending(
      shoppingList(),
      [op('extra.update', { extra_id: CANDLES_EXTRA_ID, text: 'Kerzen', amount_text: null })],
      OPTIONS,
    );
    const line = shown.lines.find((entry) => entry.key === extraLineKey(CANDLES_EXTRA_ID));
    expect(line).toMatchObject({ name: 'Kerzen', amount_text: null, pending: true });
    expect(line?.sources[0]?.amount_text).toBeNull();
    expect(shown.extra_items.find((item) => item.id === CANDLES_EXTRA_ID)).toMatchObject({
      text: 'Kerzen',
      pending: true,
    });
  });

  it('deletes a free-text item, and a later rename leaves it deleted (SYNC-06)', () => {
    const shown = applyPending(
      shoppingList(),
      [
        op('extra.delete', { extra_id: CANDLES_EXTRA_ID }),
        op('extra.update', { extra_id: CANDLES_EXTRA_ID, text: 'Kerzen' }),
      ],
      OPTIONS,
    );
    expect(shown.lines.some((line) => line.key === extraLineKey(CANDLES_EXTRA_ID))).toBe(false);
    expect(shown.extra_items.some((item) => item.id === CANDLES_EXTRA_ID)).toBe(false);
  });

  it('finishes the list at the time of the tap', () => {
    const shown = applyPending(shoppingList(), [op('list.finish', {})], OPTIONS);
    expect(shown).toMatchObject({ status: 'done', finished_at: AT, pendingFinish: true });
  });

  it('keeps check-offs made before the list was finished, not later ones (SYNC-06)', () => {
    const before = op(
      'line.check',
      { line_key: 'i:ing-zwiebeln', checked: true },
      '2026-09-26T13:50:00Z',
    );
    const after = op(
      'line.check',
      { line_key: 'i:ing-mehl', checked: true },
      '2026-09-26T14:10:00Z',
    );
    const shown = applyPending(doneList(), [before, after], OPTIONS);
    expect(lineOf(shown, 'Zwiebeln')).toMatchObject({ checked: true, pending: true });
    expect(lineOf(shown, 'Mehl')).toMatchObject({ checked: false });
    expect(lineOf(shown, 'Mehl').pending).toBeUndefined();
  });

  it('leaves a done list alone otherwise: no new items, no second finish', () => {
    const list = doneList();
    const shown = applyPending(
      list,
      [
        op('extra.add', { extra_id: NEW_ID, text: 'Servietten' }),
        op('extra.delete', { extra_id: CANDLES_EXTRA_ID }),
        op('list.finish', {}),
      ],
      OPTIONS,
    );
    expect(shown).toEqual({ ...list, pendingFinish: false });
  });

  it('never changes the check state of a draft', () => {
    const list = listDetail();
    const shown = applyPending(
      list,
      [op('line.check', { line_key: 'i:ing-zwiebeln', checked: true }), op('list.finish', {})],
      OPTIONS,
    );
    expect(shown).toEqual({ ...list, pendingFinish: false });
  });

  it('does not change the list it was given', () => {
    const list = shoppingList({ lines: shoppingList().lines.map((line) => ({ ...line })) });
    const copy = structuredClone(list);
    applyPending(
      list,
      [
        op('line.check', { line_key: 'i:ing-zwiebeln', checked: true }),
        op('extra.add', { extra_id: NEW_ID, text: 'Servietten' }),
        op('list.finish', {}),
      ],
      OPTIONS,
    );
    expect(list).toEqual(copy);
  });

  it('keeps a check-off of a line checked earlier by someone else', () => {
    const list = shoppingList();
    const shown = applyPending(
      { ...list, lines: list.lines.map((line) => ({ ...line, ...checkedBy(BEN) })) },
      [op('line.check', { line_key: 'i:ing-zwiebeln', checked: true })],
      OPTIONS,
    );
    expect(lineOf(shown, 'Zwiebeln')).toMatchObject({ checked_by: ME, pending: true });
  });

  describe('follows the server’s rules for the tap time (SYNC-06)', () => {
    const NOW = Date.parse('2026-09-26T14:00:00Z');

    function checkAt(at: string, checked: boolean, opId: string): Op {
      return {
        type: 'line.check',
        payload: { line_key: 'i:ing-zwiebeln', checked },
        at,
        op_id: opId,
      };
    }

    it('of two taps at the same time, the higher op id wins, whatever the order', () => {
      const higher = checkAt(AT, false, '0190c0de-0000-7000-8000-0000000000f2');
      const lower = checkAt(AT, true, '0190c0de-0000-7000-8000-0000000000f1');

      const shown = applyPending(shoppingList(), [higher, lower], { ...OPTIONS, now: NOW });

      expect(lineOf(shown, 'Zwiebeln')).toMatchObject({ checked: false, pending: true });
    });

    it('counts a tap from more than five minutes ahead as five minutes ahead', () => {
      const shown = applyPending(
        shoppingList(),
        [
          checkAt('2026-09-26T16:00:00Z', true, '0190c0de-0000-7000-8000-0000000000f3'),
          op('list.finish', {}, '2026-09-26T17:00:00Z'),
        ],
        { ...OPTIONS, now: NOW },
      );

      expect(lineOf(shown, 'Zwiebeln').checked_at).toBe('2026-09-26T14:05:00.000Z');
      expect(shown.finished_at).toBe('2026-09-26T14:05:00.000Z');
    });

    it('leaves out check-offs from well before shopping started', () => {
      // Shopping started at 13:00; a phone clock a little behind is fine.
      const shown = applyPending(
        shoppingList(),
        [
          checkAt('2026-09-26T12:50:00Z', true, '0190c0de-0000-7000-8000-0000000000f4'),
          op('line.check', { line_key: 'i:ing-mehl', checked: true }, '2026-09-26T12:56:00Z'),
        ],
        { ...OPTIONS, now: NOW },
      );

      expect(lineOf(shown, 'Zwiebeln')).toMatchObject({ checked: false });
      expect(lineOf(shown, 'Zwiebeln')).not.toHaveProperty('pending');
      expect(lineOf(shown, 'Mehl')).toMatchObject({ checked: true, pending: true });
    });
  });
});
