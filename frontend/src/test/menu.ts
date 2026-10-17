import { screen, within } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { testIds, type TestId } from '@/testIds';

/** Opens the detail screen's ⋯ menu (D-39) with a tap, in any language, and returns the menu. */
export async function openMoreMenu(user: UserEvent): Promise<HTMLElement> {
  await user.click(await screen.findByTestId(testIds.moreActions));
  return screen.findByRole('menu');
}

/** The names of the menu's items in their order, a switch as "<name> (on|off)". */
export function menuItemNames(menu: HTMLElement): string[] {
  return [...menu.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"]')].map((item) => {
    const name = item.textContent ?? '';
    if (item.getAttribute('role') !== 'menuitemcheckbox') return name;
    return `${name} (${item.getAttribute('aria-checked') === 'true' ? 'on' : 'off'})`;
  });
}

/** Opens the ⋯ menu and chooses the item with that test ID, as a tap does. */
export async function chooseFromMenu(user: UserEvent, testId: TestId): Promise<void> {
  const menu = await openMoreMenu(user);
  await user.click(within(menu).getByTestId(testId));
}
