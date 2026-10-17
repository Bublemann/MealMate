import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import { Check } from 'lucide-react';
import type * as React from 'react';
import { cn } from '@/lib/utils';

// From the shadcn/ui registry (dropdown-menu, on Radix), adapted: every item is a 44 pt tap
// target (A11Y-01) whose text wraps at large text sizes; the menu stays within the width and
// scrolls within the height the screen leaves it (16 px from its edges); colours come from the
// tokens; the highlighted item shows the full focus ring; and there is no animation (none under
// Reduce Motion either, A11Y-02). Only the parts the app uses: plain items, a destructive one, a
// checkbox item drawn as a switch, and the separator.

function DropdownMenu(props: React.ComponentProps<typeof DropdownMenuPrimitive.Root>) {
  return <DropdownMenuPrimitive.Root data-slot="dropdown-menu" {...props} />;
}

function DropdownMenuTrigger(props: React.ComponentProps<typeof DropdownMenuPrimitive.Trigger>) {
  return <DropdownMenuPrimitive.Trigger data-slot="dropdown-menu-trigger" {...props} />;
}

function DropdownMenuContent({
  className,
  sideOffset = 4,
  collisionPadding = 16,
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        data-slot="dropdown-menu-content"
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={cn(
          'z-50 flex max-h-(--radix-dropdown-menu-content-available-height) w-max max-w-[min(20rem,var(--radix-dropdown-menu-content-available-width))] min-w-[min(12rem,var(--radix-dropdown-menu-content-available-width))] flex-col overflow-x-hidden overflow-y-auto rounded-xl border bg-card p-1 text-card-foreground shadow-lg outline-none',
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
}

/**
 * Shared by every kind of item: a full-width row of at least 44 pt, its text wrapping (hyphenated
 * in the UI language) with spacing that stops growing at 12 px, so the text keeps the room.
 */
const itemClasses =
  "relative flex min-h-(--tap-target) cursor-default items-center gap-[min(0.75rem,12px)] rounded-md px-[min(0.75rem,12px)] py-2 text-left text-base wrap-break-word hyphens-auto outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5";

function DropdownMenuItem({
  className,
  variant = 'default',
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Item> & {
  /** `destructive`: red, for an action that deletes; it goes last, after a separator. */
  variant?: 'default' | 'destructive';
}) {
  return (
    <DropdownMenuPrimitive.Item
      data-slot="dropdown-menu-item"
      data-variant={variant}
      className={cn(
        itemClasses,
        'data-[variant=destructive]:text-destructive data-[variant=destructive]:data-[highlighted]:bg-destructive/10 data-[variant=destructive]:data-[highlighted]:text-destructive',
        className,
      )}
      {...props}
    />
  );
}

/**
 * A checkbox item drawn as a switch at its end (the app's `Switch`): read as a menu item that is
 * checked or not checked. "On" shows by the thumb's position and a check mark, not only by colour.
 */
function DropdownMenuCheckboxItem({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.CheckboxItem>) {
  return (
    <DropdownMenuPrimitive.CheckboxItem
      data-slot="dropdown-menu-checkbox-item"
      className={cn(itemClasses, 'group/switch justify-between', className)}
      {...props}
    >
      <span className="min-w-0 flex-1">{children}</span>
      <span
        aria-hidden="true"
        className="inline-flex h-7 w-12 shrink-0 items-center rounded-full border-2 border-transparent bg-input group-data-[state=checked]/switch:bg-primary"
      >
        <span className="flex size-6 items-center justify-center rounded-full bg-background shadow-sm group-data-[state=checked]/switch:translate-x-5">
          <Check className="hidden size-4 text-primary group-data-[state=checked]/switch:block" />
        </span>
      </span>
    </DropdownMenuPrimitive.CheckboxItem>
  );
}

function DropdownMenuSeparator({
  className,
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Separator>) {
  return (
    <DropdownMenuPrimitive.Separator
      data-slot="dropdown-menu-separator"
      className={cn('-mx-1 my-1 h-px shrink-0 bg-border', className)}
      {...props}
    />
  );
}

export {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
};
