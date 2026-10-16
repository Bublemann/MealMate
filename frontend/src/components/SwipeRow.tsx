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
/** The action's least width (`min-w-24`) at the default text size, for when nothing is laid out. */
const ACTION_MIN_WIDTH = 96;

// The one open row on the screen: opening a row, or starting to swipe one, closes the other.
let openRow: string | null = null;
const listeners = new Set<() => void>();

function setOpenRow(row: string | null) {
  if (openRow === row) return;
  openRow = row;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The one action a swipe reveals at the row's right edge. */
export interface SwipeAction {
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
  from: number;
  /** Moved sideways past the slop: a swipe, not a tap or scrolling. */
  swiping: boolean;
}

interface Drag {
  /** Where the content is (px, ≤ 0). */
  offset: number;
  actionWidth: number;
  /** Past the full-swipe point: letting go acts at once. */
  full: boolean;
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
  const actionButton = useRef<HTMLButtonElement>(null);
  const gesture = useRef<Gesture | null>(null);
  // The click that follows a swipe, or a tap on the open row, is swallowed.
  const swiped = useRef(false);
  const tappedOpen = useRef(false);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [openWidth, setOpenWidth] = useState(ACTION_MIN_WIDTH);
  const offset = drag?.offset ?? (open ? -openWidth : 0);
  const actionWidth = drag?.actionWidth ?? openWidth;

  // Offline, or the row is gone: it can't stay open.
  useEffect(() => {
    if (disabled && openRow === id) setOpenRow(null);
  }, [disabled, id]);
  useEffect(
    () => () => {
      if (openRow === id) setOpenRow(null);
    },
    [id],
  );

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

  function measure() {
    const rowWidth = root.current?.offsetWidth || window.innerWidth;
    const width = actionButton.current?.offsetWidth || ACTION_MIN_WIDTH;
    return { rowWidth, actionWidth: width };
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    swiped.current = false;
    tappedOpen.current = open;
    gesture.current = null;
    if (disabled || event.pointerType === 'mouse' || !event.isPrimary) return;
    gesture.current = {
      pointer: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      from: offset,
      swiping: false,
    };
  }

  /** Where the content would be for the pointer at `clientX`, and what letting go there does. */
  function dragTo(current: Gesture, clientX: number): Drag {
    const { rowWidth, actionWidth: width } = measure();
    const position = Math.min(0, Math.max(-rowWidth, current.from + clientX - current.x));
    return { offset: position, actionWidth: width, full: -position >= rowWidth * FULL_SHARE };
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
      swiped.current = true;
      setOpenRow(id);
    }
    setDrag(dragTo(current, event.clientX));
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    const current = gesture.current;
    if (!current || current.pointer !== event.pointerId) return;
    gesture.current = null;
    if (!current.swiping) return;
    const end = dragTo(current, event.clientX);
    setDrag(null);
    if (end.full) {
      setOpenRow(null);
      action.onAction();
    } else if (-end.offset >= end.actionWidth * OPEN_SHARE) {
      setOpenWidth(end.actionWidth);
      setOpenRow(id);
    } else {
      setOpenRow(null);
    }
  }

  function onPointerCancel() {
    // The browser took over, e.g. to scroll: like iOS, scrolling closes the row.
    gesture.current = null;
    setDrag(null);
    if (openRow === id) setOpenRow(null);
  }

  function onClickCapture(event: MouseEvent<HTMLDivElement>) {
    if (!swiped.current && !tappedOpen.current) return;
    event.preventDefault();
    event.stopPropagation();
    // A tap on the open row only closes it; where a swipe left the row, it decided already.
    if (!swiped.current) setOpenRow(null);
    swiped.current = false;
    tappedOpen.current = false;
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
              ref={actionButton}
              type="button"
              tabIndex={-1}
              onClick={() => {
                setOpenRow(null);
                action.onAction();
              }}
              className="flex min-w-24 shrink-0 items-center justify-center gap-2 px-4 text-sm font-medium outline-none"
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
