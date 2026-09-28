import { describe, expect, it, vi } from 'vitest';
import { shoppingList } from '@/test/lists';
import { batches, flushEntries, MAX_BATCH, type FlushSteps, type SendOutcome } from './flush';
import type { OutboxEntry } from './types';

function entry(seq: number, listId: string): OutboxEntry {
  return {
    seq,
    userId: 'u1',
    listId,
    queuedAt: seq,
    op: {
      type: 'line.check',
      payload: { line_key: `i:${seq}`, checked: true },
      op_id: `op-${seq}`,
      at: '2026-09-26T13:45:00Z',
    },
  };
}

function steps(outcomes: SendOutcome[]) {
  const queue = [...outcomes];
  return {
    isCurrentUser: vi.fn<FlushSteps['isCurrentUser']>(() => true),
    send: vi.fn<FlushSteps['send']>(() =>
      Promise.resolve(queue.shift() ?? { kind: 'unreachable' }),
    ),
    sent: vi.fn<FlushSteps['sent']>(() => Promise.resolve()),
    gone: vi.fn<FlushSteps['gone']>(() => Promise.resolve()),
    invalid: vi.fn<FlushSteps['invalid']>(() => Promise.resolve()),
  };
}

const SENT: SendOutcome = { kind: 'sent', results: [], list: shoppingList() };

describe('batches', () => {
  it('groups consecutive ops of one list, keeping the order', () => {
    const entries = [entry(1, 'a'), entry(2, 'a'), entry(3, 'b'), entry(4, 'a')];
    expect(batches(entries).map((batch) => batch.map((e) => e.seq))).toEqual([[1, 2], [3], [4]]);
  });

  it(`sends at most ${MAX_BATCH} ops per request`, () => {
    const entries = Array.from({ length: 2 * MAX_BATCH + 1 }, (_, i) => entry(i + 1, 'a'));
    expect(batches(entries).map((batch) => batch.length)).toEqual([MAX_BATCH, MAX_BATCH, 1]);
  });

  it('has nothing to send for an empty outbox', () => {
    expect(batches([])).toEqual([]);
  });
});

describe('flushEntries', () => {
  it('sends every batch in order and hands over each answer', async () => {
    const flow = steps([SENT, SENT]);
    const entries = [entry(1, 'a'), entry(2, 'b')];

    await expect(flushEntries(entries, flow)).resolves.toBe('done');

    expect(flow.send.mock.calls.map(([listId]) => listId)).toEqual(['a', 'b']);
    expect(flow.send.mock.calls[0]?.[1]).toEqual([entries[0]?.op]);
    expect(flow.sent).toHaveBeenCalledTimes(2);
    expect(flow.sent.mock.calls[1]?.[1]).toEqual([entries[1]]);
  });

  it('stops at the first request that does not reach the server; the rest stays', async () => {
    const flow = steps([SENT, { kind: 'unreachable' }]);

    await expect(flushEntries([entry(1, 'a'), entry(2, 'b'), entry(3, 'c')], flow)).resolves.toBe(
      'unreachable',
    );

    expect(flow.send).toHaveBeenCalledTimes(2);
    expect(flow.sent).toHaveBeenCalledTimes(1);
  });

  it('stops when the session ended, keeping everything (SYNC-05)', async () => {
    const flow = steps([{ kind: 'ended' }]);
    await expect(flushEntries([entry(1, 'a'), entry(2, 'b')], flow)).resolves.toBe('ended');
    expect(flow.send).toHaveBeenCalledTimes(1);
    expect(flow.sent).not.toHaveBeenCalled();
  });

  it('drops a gone list once and skips its later batches', async () => {
    const flow = steps([{ kind: 'gone' }, SENT]);

    await expect(flushEntries([entry(1, 'a'), entry(2, 'b'), entry(3, 'a')], flow)).resolves.toBe(
      'done',
    );

    expect(flow.gone).toHaveBeenCalledOnce();
    expect(flow.gone).toHaveBeenCalledWith('a');
    expect(flow.send.mock.calls.map(([listId]) => listId)).toEqual(['a', 'b']);
  });

  it('drops a batch the server refused as a whole and goes on', async () => {
    const flow = steps([{ kind: 'invalid', status: 422 }, SENT]);
    await expect(flushEntries([entry(1, 'a'), entry(2, 'b')], flow)).resolves.toBe('done');
    expect(flow.invalid).toHaveBeenCalledWith('a', [entry(1, 'a')], 422);
    expect(flow.sent).toHaveBeenCalledOnce();
  });

  it('never sends with another user’s session (SYNC-10)', async () => {
    const flow = steps([SENT]);
    flow.isCurrentUser.mockReturnValueOnce(true).mockReturnValue(false);
    await expect(flushEntries([entry(1, 'a'), entry(2, 'b')], flow)).resolves.toBe('stopped');
    expect(flow.send).toHaveBeenCalledOnce();
  });
});
