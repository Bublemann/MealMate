import { CircleUserRound, CookingPot, Carrot, ListChecks, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet } from 'react-router';
import { cn } from '@/lib/utils';
import { testIds, type TestId } from '@/testIds';
import { UpdatePrompt } from './UpdatePrompt';

interface Tab {
  to: string;
  label: 'nav.lists' | 'nav.meals' | 'nav.ingredients' | 'nav.me';
  icon: LucideIcon;
  testId: TestId;
}

const TABS: readonly Tab[] = [
  { to: '/lists', label: 'nav.lists', icon: ListChecks, testId: testIds.tabLists },
  { to: '/meals', label: 'nav.meals', icon: CookingPot, testId: testIds.tabMeals },
  { to: '/ingredients', label: 'nav.ingredients', icon: Carrot, testId: testIds.tabIngredients },
  { to: '/me', label: 'nav.me', icon: CircleUserRound, testId: testIds.tabMe },
];

/** App shell: the current screen above a bottom tab bar for one-handed use (UI-01). */
export function Layout() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-dvh flex-col">
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-[calc(6rem+env(safe-area-inset-bottom))]">
        <Outlet />
      </main>
      <UpdatePrompt />
      <nav
        aria-label={t('nav.label')}
        className="fixed inset-x-0 bottom-0 z-10 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      >
        <ul className="mx-auto flex max-w-2xl">
          {TABS.map(({ to, label, icon: Icon, testId }) => (
            <li key={to} className="flex-1">
              <NavLink
                to={to}
                data-testid={testId}
                className={({ isActive }) =>
                  cn(
                    'flex min-h-14 flex-col items-center justify-center gap-0.5 px-1 py-1.5 text-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset',
                    isActive
                      ? 'font-bold text-foreground'
                      : 'font-medium text-muted-foreground hover:text-foreground',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {/* The filled pill marks the active tab without relying on hue (A11Y-01). */}
                    <span
                      className={cn(
                        'flex h-8 w-14 items-center justify-center rounded-full transition-colors',
                        isActive && 'bg-primary text-primary-foreground',
                      )}
                    >
                      <Icon aria-hidden="true" className="size-6" />
                    </span>
                    {t(label)}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
