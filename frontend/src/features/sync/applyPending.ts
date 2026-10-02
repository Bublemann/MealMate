import { ingredientLabel } from '@/features/ingredients/label';
import { otherCategoryId } from '@/features/lists/format';
import type { Category, ExtraItem, ListDetail, ListLine, Op, UserRef } from './types';

/** What a free-text item's category is found by. */
type CategoryRef = Pick<Category, 'id' | 'key'>;

/** A line as the view shows it; `pending`: changed by an op that wasn't sent yet (SYNC-07). */
export type PendingLine = ListLine & { pending?: boolean };
export type PendingExtraItem = ExtraItem & { pending?: boolean };

/** The list as the view shows it: the server's list with this user's waiting ops applied. */
export interface PendingList extends Omit<ListDetail, 'lines' | 'extra_items'> {
  lines: PendingLine[];
  extra_items: PendingExtraItem[];
  /** *Finish* was tapped here but hasn't reached the server yet. */
  pendingFinish: boolean;
}

export interface PendingOptions {
  /** Who made the ops: a waiting check-off shows my initial (SHOP-01). */
  me: UserRef;
  /** The categories a free-text item can be added to. */
  categories: readonly CategoryRef[];
  /** The time now (ms since the epoch), for the clamp of taps from the future; default: now. */
  now?: number;
}

/** A tap time more than this after the server's clock counts as that much later (plan § 5.8). */
export const MAX_CLOCK_AHEAD_MS = 5 * 60 * 1000;
/** A check-off more than this before shopping started is refused by the server (SYNC-06). */
export const MAX_CLOCK_BEHIND_MS = 5 * 60 * 1000;

/** The key of a free-text item's line (`ListLine.key`). */
export function extraLineKey(extraId: string): string {
  return `x:${extraId}`;
}

function time(iso: string | null): number {
  return iso === null ? Number.NEGATIVE_INFINITY : Date.parse(iso);
}

/** When a tap counts, as the server takes it: at most MAX_CLOCK_AHEAD_MS after now. */
function tapTime(at: string, now: number): { at: string; ms: number } {
  const ms = Date.parse(at);
  const latest = now + MAX_CLOCK_AHEAD_MS;
  return ms > latest ? { at: new Date(latest).toISOString(), ms: latest } : { at, ms };
}

/**
 * The list as it will look once the waiting ops are applied (plan § 5.8), in their order. Pure:
 * the view shows the server's list (or the local copy) with this, so a check-off moves at once
 * and stays while it waits to be sent (SYNC-03). It follows the server's rules where they decide
 * what is shown: a check-off older than the line's last one changes nothing (SYNC-06), and of
 * two at the same time the higher `op_id` wins; a tap time more than 5 minutes ahead counts as
 * now + 5 minutes; deleted items stay deleted; ops the server will turn down (a check-off after
 * the list was finished or well before shopping started, changes to a draft's check state) are
 * left out. What only the server knows (amounts, badges of other lines) stays as it was. Lines
 * and items touched by an op are marked `pending`.
 */
export function applyPending(
  detail: ListDetail,
  ops: readonly Op[],
  { me, categories, now = Date.now() }: PendingOptions,
): PendingList {
  const list: PendingList = { ...detail, pendingFinish: false };
  /** The op id of the waiting check-off each line shows, for the tie-break. */
  const shownOps = new Map<string, string>();
  for (const op of ops) {
    switch (op.type) {
      case 'line.check':
        checkLine(list, op, tapTime(op.at, now), me, shownOps);
        break;
      case 'extra.add':
        addExtra(list, op.payload, op.at, me, categories);
        break;
      case 'extra.update':
        updateExtra(list, op.payload);
        break;
      case 'extra.delete':
        deleteExtra(list, op.payload.extra_id);
        break;
      case 'list.finish':
        if (list.status === 'shopping') {
          list.status = 'done';
          list.finished_at = tapTime(op.at, now).at;
          list.pendingFinish = true;
        }
        break;
    }
  }
  return list;
}

type LineCheck = Extract<Op, { type: 'line.check' }>;

function checkLine(
  list: PendingList,
  op: LineCheck,
  { at, ms }: { at: string; ms: number },
  me: UserRef,
  shownOps: Map<string, string>,
) {
  const { line_key: key, checked } = op.payload;
  if (list.status === 'draft') return;
  // Taps from well before shopping started are refused, like the server does.
  const startedAt = time(list.shopping_started_at);
  if (ms < startedAt - MAX_CLOCK_BEHIND_MS) return;
  // Check-offs from before the list was finished still count (SYNC-06); later ones are refused.
  if (list.status === 'done' && ms > time(list.finished_at)) return;
  list.lines = list.lines.map((line) => {
    if (line.key !== key) return line;
    const lineAt = time(line.checked_at);
    if (lineAt > ms) return line;
    // At the same time the higher op id wins (the server's tie-break). Against the server's own
    // state, whose op id the list doesn't carry, the waiting op shows: it may well be that op.
    const shown = shownOps.get(key);
    if (lineAt === ms && shown !== undefined && shown > op.op_id) return line;
    shownOps.set(key, op.op_id);
    return {
      ...line,
      checked,
      checked_at: at,
      checked_by: checked ? me : null,
      new: false,
      needs_more: null,
      pending: true,
    };
  });
}

type ExtraAdd = Extract<Op, { type: 'extra.add' }>['payload'];
type ExtraUpdate = Extract<Op, { type: 'extra.update' }>['payload'];

/**
 * The category of a free-text item as the server picks it (LIST-06): by id, or by key in an op an
 * app version before D-31 queued; *Other* for none or an unknown one.
 */
function extraCategoryId(
  { category_id, category_key }: ExtraAdd,
  categories: readonly CategoryRef[],
): string {
  let named: CategoryRef | undefined;
  if (category_id) named = categories.find((category) => category.id === category_id);
  else if (category_key) named = categories.find((category) => category.key === category_key);
  return named?.id ?? otherCategoryId(categories);
}

function addExtra(
  list: PendingList,
  payload: ExtraAdd,
  at: string,
  me: UserRef,
  categories: readonly CategoryRef[],
) {
  const { extra_id: id, text, amount_text } = payload;
  if (list.status === 'done' || list.extra_items.some((item) => item.id === id)) return;
  const categoryId = extraCategoryId(payload, categories);
  const amountText = amount_text ?? null;
  list.extra_items = [
    ...list.extra_items,
    {
      id,
      ingredient_id: null,
      text,
      amount: null,
      unit: null,
      amount_text: amountText,
      category_id: categoryId,
      added_by: me,
      created_at: at,
      pending: true,
    },
  ];
  const line: PendingLine = {
    key: extraLineKey(id),
    kind: 'text',
    name: text,
    brand: null,
    ingredient_id: null,
    category_id: categoryId,
    amounts: [],
    has_unspecified: false,
    amount_text: amountText,
    hidden: false,
    sources: [
      {
        kind: 'extra',
        extra_id: id,
        list_meal_id: null,
        meal_name: null,
        private: false,
        servings: null,
        amount: null,
        unit: null,
        amount_text: amountText,
      },
    ],
    checked: false,
    checked_at: null,
    checked_by: null,
    // Like the server: a line that appears after shopping started is new (LIST-12).
    new: list.status === 'shopping',
    needs_more: null,
    pending: true,
  };
  list.lines = insertByCategory(list.lines, line);
}

/**
 * Puts a line among those of its category, by name and then brand (the server's order, AGG-05):
 * two brands of the same thing are separate lines.
 */
function insertByCategory(lines: PendingLine[], line: PendingLine): PendingLine[] {
  let index = lines.length;
  let lastOfCategory = -1;
  for (const [i, other] of lines.entries()) {
    if (other.category_id !== line.category_id) continue;
    lastOfCategory = i;
    if (ingredientLabel(other.name, other.brand).localeCompare(line.name) > 0) {
      index = i;
      break;
    }
  }
  if (index === lines.length && lastOfCategory >= 0) index = lastOfCategory + 1;
  return [...lines.slice(0, index), line, ...lines.slice(index)];
}

function updateExtra(list: PendingList, { extra_id: id, text, amount_text }: ExtraUpdate) {
  // Gone (deleted here or on another phone): the delete wins (SYNC-06).
  if (list.status === 'done' || !list.extra_items.some((item) => item.id === id)) return;
  const amountText = amount_text ?? null;
  list.extra_items = list.extra_items.map((item) =>
    item.id === id ? { ...item, text, amount_text: amountText, pending: true } : item,
  );
  const key = extraLineKey(id);
  list.lines = list.lines.map((line) =>
    line.key === key
      ? {
          ...line,
          name: text,
          amount_text: amountText,
          sources: line.sources.map((source) =>
            source.extra_id === id ? { ...source, amount_text: amountText } : source,
          ),
          pending: true,
        }
      : line,
  );
}

function deleteExtra(list: PendingList, id: string) {
  if (list.status === 'done') return;
  list.extra_items = list.extra_items.filter((item) => item.id !== id);
  const key = extraLineKey(id);
  list.lines = list.lines.filter((line) => line.key !== key);
}
