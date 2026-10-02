import * as DialogPrimitive from '@radix-ui/react-dialog';
import type * as React from 'react';
import { cn } from '@/lib/utils';

/*
 * A panel that slides up from the bottom edge (UI-01: the filter panel), on the Radix dialog like
 * the pop-ups: modal, closed with Escape or a tap beside it, focus kept inside and given back to
 * what opened it. Under Reduce Motion it appears and goes without sliding (A11Y-02).
 */

function Sheet(props: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="sheet" {...props} />;
}

function SheetTrigger(props: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="sheet-trigger" {...props} />;
}

function SheetClose(props: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="sheet-close" {...props} />;
}

/**
 * Sits on the bottom edge of the visible area, i.e. above the on-screen keyboard (tokens.css),
 * and leaves the status bar free. Content taller than that, e.g. at the largest text sizes,
 * scrolls; a `SheetFooter` stays in view at its end.
 */
function SheetContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal data-slot="sheet-portal">
      <DialogPrimitive.Overlay
        data-slot="sheet-overlay"
        className="fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in motion-reduce:animate-none"
      />
      <DialogPrimitive.Content
        data-slot="sheet-content"
        className={cn(
          'fixed inset-x-0 bottom-(--keyboard-inset) z-50 mx-auto flex max-h-[calc(var(--visible-height)-max(env(safe-area-inset-top),1rem))] w-full max-w-lg flex-col overflow-y-auto overscroll-contain rounded-t-2xl border border-b-0 bg-card text-card-foreground shadow-lg outline-none data-[state=closed]:animate-sheet-out data-[state=open]:animate-sheet-in motion-reduce:animate-none',
          className,
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

function SheetHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div data-slot="sheet-header" className={cn('flex flex-col gap-2 p-5', className)} {...props} />
  );
}

/** Stays at the end of the visible part while the content scrolls; its buttons wrap. */
function SheetFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn(
        'sticky bottom-0 mt-auto flex flex-wrap gap-2 border-t bg-card px-5 pt-3 pb-[max(env(safe-area-inset-bottom),0.75rem)]',
        className,
      )}
      {...props}
    />
  );
}

function SheetTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="sheet-title"
      className={cn('text-lg leading-tight font-semibold', className)}
      {...props}
    />
  );
}

export { Sheet, SheetClose, SheetContent, SheetFooter, SheetHeader, SheetTitle, SheetTrigger };
