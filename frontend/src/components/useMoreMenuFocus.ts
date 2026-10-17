import { useRef } from 'react';

/**
 * The ⋯ button of a screen's menu, for the dialogs its items open: `focusMenu`, as their
 * `onCloseAutoFocus`, puts the focus back on ⋯ when they close (Radix would look for a trigger of
 * their own, and the dialogs have none).
 */
export function useMoreMenuFocus() {
  const trigger = useRef<HTMLButtonElement>(null);
  const focusMenu = (event: Event) => {
    event.preventDefault();
    trigger.current?.focus();
  };
  return { trigger, focusMenu };
}
