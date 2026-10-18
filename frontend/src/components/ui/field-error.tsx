import { CircleAlert } from 'lucide-react';
import type * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * A field's error below its control, with the alert icon (colour is never the only signal). The
 * control names it in `aria-describedby` by the `id` given here; `FormField` does that itself.
 */
function FieldError({ className, children, ...props }: React.ComponentProps<'p'>) {
  return (
    <p
      data-slot="field-error"
      className={cn('flex items-start gap-1.5 text-sm font-medium text-destructive', className)}
      {...props}
    >
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      {children}
    </p>
  );
}

export { FieldError };
