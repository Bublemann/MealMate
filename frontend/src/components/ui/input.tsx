import type * as React from 'react';
import { cn } from '@/lib/utils';

// 44 pt tap target and 16 px text (no zoom on focus in iOS), see tokens.css.
function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'min-h-(--tap-target) w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-(length:--control-font-size) transition-[color,box-shadow] outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50 read-only:bg-muted',
        'focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring',
        'aria-invalid:border-destructive aria-invalid:ring-destructive/20',
        className,
      )}
      {...props}
    />
  );
}

export { Input };
