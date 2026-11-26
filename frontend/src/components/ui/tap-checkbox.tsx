import { Check } from 'lucide-react';
import type * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * A large native checkbox for a row that is ticked off (a line while shopping, a meal eaten on a
 * done list): the invisible input covers the whole tap target (A11Y-01) over a drawn box that is
 * filled and shows a check mark when ticked, so colour is not the only signal. It has no label of
 * its own; `aria-label` names it, or a `<label>` around the row. `boxClassName` styles the drawn
 * box, e.g. faded while a change waits.
 */
function TapCheckbox({
  boxClassName,
  ...props
}: Omit<React.ComponentProps<'input'>, 'type' | 'className'> & { boxClassName?: string }) {
  return (
    <span className="relative flex size-(--tap-target) shrink-0 items-center justify-center">
      <input
        type="checkbox"
        className="peer absolute inset-0 size-full cursor-pointer appearance-none rounded-md opacity-0 disabled:cursor-default"
        {...props}
      />
      <span
        aria-hidden="true"
        className={cn(
          'flex size-8 items-center justify-center rounded-md border-2 border-input bg-background text-primary-foreground peer-checked:border-primary peer-checked:bg-primary peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring peer-disabled:opacity-60',
          boxClassName,
        )}
      >
        {props.checked && <Check className="size-6" strokeWidth={3} />}
      </span>
    </span>
  );
}

export { TapCheckbox };
