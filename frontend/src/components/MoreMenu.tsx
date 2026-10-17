import { Ellipsis } from 'lucide-react';
import { createContext, useContext, useRef, useState, type ReactNode, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { testIds, type TestId } from '@/testIds';

/** Runs an item's action once the menu has closed and the focus is back on ⋯. */
const AfterCloseContext = createContext<(action: () => void) => void>((action) => action());

interface MoreMenuProps {
  /** From `useMoreMenuFocus`, which gives the dialogs the way back to ⋯. */
  trigger: RefObject<HTMLButtonElement | null>;
  /** The screen's items, in the order of D-39. */
  children: ReactNode;
  /** The destructive item ("Löschen"), if the user may delete: red, after a separator, last. */
  danger?: ReactNode;
}

/**
 * A detail screen's ⋯ button and its pull-down menu (D-39), for the right of the strip
 * (`Screen`'s `action`). The button is always enabled; items that need a connection are disabled
 * offline, not hidden (SYNC-03). An item that opens a dialog (`dialog`) opens it only once the
 * menu has closed and given the focus back to ⋯; the dialog puts it there again when it closes
 * (`useMoreMenuFocus`).
 */
export function MoreMenu({ trigger, children, danger }: MoreMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const pending = useRef<(() => void) | null>(null);

  function afterClose(action: () => void) {
    pending.current = action;
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          ref={trigger}
          variant="ghost"
          size="icon"
          data-testid={testIds.moreActions}
          aria-label={t('common.moreActions')}
          className="-mr-[0.25em] text-primary"
        >
          <Ellipsis aria-hidden="true" className="size-[1.5em]" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        data-testid={testIds.moreMenu}
        onCloseAutoFocus={(event) => {
          const action = pending.current;
          if (!action) return;
          pending.current = null;
          event.preventDefault();
          trigger.current?.focus();
          action();
        }}
      >
        <AfterCloseContext.Provider value={afterClose}>
          {children}
          {danger && (
            <>
              <DropdownMenuSeparator />
              {danger}
            </>
          )}
        </AfterCloseContext.Provider>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

interface MoreMenuItemProps {
  testId: TestId;
  icon: ReactNode;
  /** Runs within the tap (a share sheet needs that), or after the menu closed with `dialog`. */
  onSelect: () => void;
  /** It opens a dialog, which then gives the focus back to ⋯ when it closes. */
  dialog?: boolean;
  disabled?: boolean;
  /** Red: deleting. Pass it as the menu's `danger`, so it comes last after a separator. */
  destructive?: boolean;
  children: ReactNode;
}

/** One action of the ⋯ menu; the menu closes when it is chosen. */
export function MoreMenuItem({
  testId,
  icon,
  onSelect,
  dialog = false,
  disabled = false,
  destructive = false,
  children,
}: MoreMenuItemProps) {
  const afterClose = useContext(AfterCloseContext);

  return (
    <DropdownMenuItem
      data-testid={testId}
      variant={destructive ? 'destructive' : 'default'}
      disabled={disabled}
      onSelect={() => (dialog ? afterClose(onSelect) : onSelect())}
    >
      {icon}
      <span className="min-w-0 flex-1">{children}</span>
    </DropdownMenuItem>
  );
}

interface MoreMenuSwitchProps {
  testId: TestId;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  children: ReactNode;
}

/** A switch in the ⋯ menu: it toggles in place, and the menu stays open to show it took effect. */
export function MoreMenuSwitch({
  testId,
  checked,
  onCheckedChange,
  disabled = false,
  children,
}: MoreMenuSwitchProps) {
  return (
    <DropdownMenuCheckboxItem
      data-testid={testId}
      checked={checked}
      disabled={disabled}
      onCheckedChange={onCheckedChange}
      onSelect={(event) => event.preventDefault()}
    >
      {children}
    </DropdownMenuCheckboxItem>
  );
}
