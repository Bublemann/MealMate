import type { LucideIcon } from 'lucide-react';
import {
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type MouseEvent,
  type PointerEvent,
  type ReactNode,
} from 'react';
import { cn } from '@/lib/utils';

/** How far (px) a finger moves before it counts as a swipe or as scrolling, not as a tap. */
const SLOP = 8;
/** Let go with this much of the action's width revealed, the row stays open. */
const OPEN_SHARE = 0.75;
/** Let go past this much of the row's width, the action happens at once (a full swipe). */
const FULL_SHARE = 0.5;
/** The action's width in rem: it grows with the text size, its icon above its label. */
const ACTION_WIDTH_REM = 6;
/** A rem in px where nothing is laid out (tests), the browsers' default. */
const DEFAULT_REM_PX = 16;
/**
 * How long (ms) after letting go a click still belongs to the gesture: a browser may send one
 * after a short swipe or a tap, and it is swallowed. A later click (a keyboard, switch control)
 * goes through.
 */
const CLICK_AFTER_GESTURE_MS = 500;

// The one open row on the screen: opening a row, or starting to swipe one, closes the other.
let openRow: string | null = null;
const listeners = new Set<() => void>();

function setOpenRow(row: string | null) {
  if (openRow === row) return;
  openRow = row;
  for (const listener of listeners) listener();
}

/** Closes `row` if it is the open one. */
function closeRow(row: string) {
  if (openRow === row) setOpenRow(null);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The one action a swipe reveals at the row's right edge. */
interface SwipeAction {
  /** Its visible text, e.g. "Remove". */
  label: string;
  icon: LucideIcon;
  /** Red for removing, grey for hiding. */
  tone: 'destructive' | 'neutral';
  onAction: () => void;
}

interface SwipeRowProps {
  action: SwipeAction;
  /** No swiping, e.g. offline or without edit rights. */
  disabled?: boolean;
  /** The row's content, which slides. */
  children: ReactNode;
}

interface Gesture {
  pointer: number;
  x: number;
  y: number;
  /** Where the content was when the finger went down (px, ≤ 0). */
  startOffset: number;
  rowWidth: number;
  actionWidth: number;
  /** Moved sideways past the slop: a swipe, not a tap or scrolling. */
  swiping: boolean;
}

interface Drag {
  /** Where the content is (px, ≤ 0). */
  offset: number;
  /** Past the full-swipe point: letting go acts at once. */
  full: boolean;
}

/** The action's width in px, in the current text size. */
function actionWidthPx() {
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || DEFAULT_REM_PX;
  return ACTION_WIDTH_REM * rem;
}

/**
 * A list row that a finger or pen swipes to the left to reveal one action at its right edge, as
 * on iOS (D-40); the mouse doesn't swipe. The content follows the finger; let go with about the
 * action's width revealed and the row stays open, let go before and it closes; past half the row
 * the action happens at once. Swiping back, scrolling, tapping elsewhere or opening another row
 * closes it, so only one row is open at a time. A mostly vertical movement scrolls the page. A
 * swipe, or the tap that closes an open row, never also counts as a tap on the row's content.
 * Under Reduce Motion the row snaps instead of sliding (A11Y-02).
 *
 * The revealed action is for touch only: it is hidden from screen readers and keyboards, so every
 * row also offers its action without a swipe (a button in the row or in its pop-up).
 */
export function SwipeRow({ action, disabled = false, children }: SwipeRowProps) {
  const id = useId();
  const open = useSyncExternalStore(subscribe, () => openRow === id);
  const root = useRef<HTMLDivElement>(null);
  const gesture = useRef<Gesture | null>(null);
  // The pointer went down on this row while it was open: letting go closes it.
  const tappedOpen = useRef(false);
  // Until when (event time) a click on the content belongs to the last gesture.
  const swallowClickUntil = useRef(0);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [actionWidth, setActionWidth] = useState(ACTION_WIDTH_REM * DEFAULT_REM_PX);
  const offset = drag?.offset ?? (open ? -actionWidth : 0);

  function act() {
    setOpenRow(null);
    action.onAction();
  }

  // Offline, or the row is gone: it can't stay open.
  useEffect(() => {
    if (disabled) closeRow(id);
  }, [disabled, id]);
  useEffect(() => () => closeRow(id), [id]);

  // A tap elsewhere closes the open row.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: globalThis.PointerEvent) {
      if (event.target instanceof Node && root.current?.contains(event.target)) return;
      setOpenRow(null);
    }
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  }, [open]);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    tappedOpen.current = open;
    swallowClickUntil.current = 0;
    gesture.current = null;
    if (disabled || event.pointerType === 'mouse' || !event.isPrimary) return;
    const width = actionWidthPx();
    gesture.current = {
      pointer: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      startOffset: open ? -width : 0,
      rowWidth: root.current?.offsetWidth || window.innerWidth,
      actionWidth: width,
      swiping: false,
    };
  }

  /** Where the content is for the pointer at `clientX`, and whether letting go there acts. */
  function dragTo(current: Gesture, clientX: number): Drag {
    const position = current.startOffset + clientX - current.x;
    const clamped = Math.min(0, Math.max(-current.rowWidth, position));
    return { offset: clamped, full: -clamped >= current.rowWidth * FULL_SHARE };
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const current = gesture.current;
    if (!current || current.pointer !== event.pointerId) return;
    if (!current.swiping) {
      const dx = Math.abs(event.clientX - current.x);
      const dy = Math.abs(event.clientY - current.y);
      if (dx < SLOP && dy < SLOP) return;
      if (dy >= dx) {
        // Scrolling the page, not swiping the row.
        gesture.current = null;
        return;
      }
      current.swiping = true;
      setActionWidth(current.actionWidth);
      setOpenRow(id);
    }
    setDrag(dragTo(current, event.clientX));
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    const current = gesture.current?.pointer === event.pointerId ? gesture.current : null;
    gesture.current = null;
    if (current?.swiping) {
      swallowClickUntil.current = event.timeStamp + CLICK_AFTER_GESTURE_MS;
      const end = dragTo(current, event.clientX);
      setDrag(null);
      if (end.full) act();
      else if (-end.offset >= current.actionWidth * OPEN_SHARE) setOpenRow(id);
      else setOpenRow(null);
    } else if (tappedOpen.current) {
      // A tap on the open row only closes it.
      swallowClickUntil.current = event.timeStamp + CLICK_AFTER_GESTURE_MS;
      closeRow(id);
    }
    tappedOpen.current = false;
  }

  function onPointerCancel() {
    // The browser took over, e.g. to scroll: like iOS, scrolling closes the row. No click follows.
    gesture.current = null;
    tappedOpen.current = false;
    setDrag(null);
    closeRow(id);
  }

  function onClickCapture(event: MouseEvent<HTMLDivElement>) {
    if (event.timeStamp > swallowClickUntil.current) return;
    swallowClickUntil.current = 0;
    event.preventDefault();
    event.stopPropagation();
  }

  const revealed = -offset;
  const Icon = action.icon;

  return (
    <div ref={root} className="relative overflow-hidden">
      {!disabled && (
        // Exactly as wide as the gap the content leaves, sliding with it.
        <div
          aria-hidden="true"
          className={cn(
            'absolute inset-y-0 right-0 flex overflow-hidden',
            action.tone === 'destructive'
              ? 'bg-destructive text-destructive-foreground'
              : 'bg-muted-foreground text-background',
            drag === null && 'transition-[width] motion-reduce:transition-none',
            // The action sticks to the content's edge while it comes in; once all of it shows it
            // stays at the right, and past the full-swipe point it follows the content, as on iOS.
            revealed < actionWidth || drag?.full === true ? 'justify-start' : 'justify-end',
          )}
          style={{ width: `${revealed}px` }}
        >
          {revealed > 0 && (
            <button
              type="button"
              tabIndex={-1}
              onClick={act}
              className="flex shrink-0 flex-col items-center justify-center gap-1 px-1 text-xs font-medium break-words outline-none"
              style={{ width: `${ACTION_WIDTH_REM}rem` }}
            >
              <Icon aria-hidden="true" className="size-5 shrink-0" />
              {action.label}
            </button>
          )}
        </div>
      )}
      <div
        className={cn(
          'relative touch-pan-y touch-pinch-zoom bg-card',
          // Follows the finger while swiping, slides when let go; snaps under Reduce Motion.
          drag === null && 'transition-transform motion-reduce:transition-none',
        )}
        style={revealed > 0 ? { transform: `translateX(${offset}px)` } : undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        onClickCapture={onClickCapture}
      >
        {children}
      </div>
    </div>
  );
}
