import { X } from 'lucide-react';
import type * as React from 'react';
import { cn } from '@/lib/utils';

// Chips keep the 44 pt tap target (A11Y-01).
const chipBase =
  'inline-flex min-h-(--tap-target) max-w-full items-center gap-1.5 rounded-full border text-sm font-medium';

/** A chip showing a value, with a button that removes it (`removeLabel` names that button). */
function RemovableChip({
  className,
  children,
  removeLabel,
  onRemove,
  ...props
}: React.ComponentProps<'span'> & { removeLabel: string; onRemove: () => void }) {
  return (
    <span
      data-slot="removable-chip"
      className={cn(
        chipBase,
        'border-transparent bg-accent pl-3.5 text-accent-foreground',
        className,
      )}
      {...props}
    >
      <span className="truncate">{children}</span>
      <button
        type="button"
        aria-label={removeLabel}
        onClick={onRemove}
        className="flex size-(--tap-target) shrink-0 items-center justify-center rounded-full outline-none hover:bg-background/60 focus-visible:ring-[3px] focus-visible:ring-ring"
      >
        <X aria-hidden="true" className="size-4" />
      </button>
    </span>
  );
}

export { RemovableChip };
