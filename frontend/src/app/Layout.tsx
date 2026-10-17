import { CookingPot, Carrot, ListChecks, Settings, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet } from 'react-router';
import { SyncBanners } from '@/features/sync/SyncBanners';
import { SyncToasts } from '@/features/sync/SyncToasts';
import { TabMemoryProvider } from '@/lib/TabMemoryProvider';
import { cn } from '@/lib/utils';
import { testIds, type TestId } from '@/testIds';
import { UpdatePrompt } from './UpdatePrompt';
import { useKeyboardOpen } from './viewport';

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
  // The Settings tab keeps the address and test ID it had as "Me" (D-44).
  { to: '/me', label: 'nav.me', icon: Settings, testId: testIds.tabMe },
];

/**
 * App shell: the current screen above a floating tab bar for one-handed use (UI-01), with the
 * sync module's banners and messages (SYNC-07). The tabs' memory (search texts, UI-01) lives as
 * long as the shell, i.e. until the app closes or the session ends.
 */
export function Layout() {
  const { t } = useTranslation();
  const keyboardOpen = useKeyboardOpen();

  return (
    <div className="flex min-h-dvh flex-col">
      {/* The space above the screen stops growing at 24 px (or is the status bar's), so that at
          the largest text sizes the pinned block still leaves a quarter of the screen for the
          content as the tab opens (UI-01, D-29). */}
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 pt-[max(min(1.5rem,24px),env(safe-area-inset-top))] pb-[calc(var(--tab-bar-clearance)+var(--floating-bar-space)+1.5rem)]">
        <SyncBanners />
        <TabMemoryProvider>
          <Outlet />
        </TabMemoryProvider>
      </main>
      <SyncToasts />
      <UpdatePrompt />
      {/*
       * Floats above the content, 16 px from the sides and no wider than the content column (the
       * main's max-w-2xl less its px-4), so taps beside it reach what is behind (UI-01). It hides
       * while the keyboard is open, so it doesn't ride up above it.
       */}
      <nav
        aria-label={t('nav.label')}
        hidden={keyboardOpen}
        className="frosted fixed inset-x-(--tab-bar-margin) bottom-(--tab-bar-bottom) z-10 mx-auto h-(--tab-bar-height) max-w-[calc(var(--container-2xl)-2rem)] rounded-full border border-frosted-border p-(--tab-bar-padding) shadow-frosted"
      >
        <ul className="flex h-full">
          {TABS.map(({ to, label, icon: Icon, testId }) => (
            <li key={to} className="flex min-w-0 flex-1">
              <NavLink
                to={to}
                data-testid={testId}
                className={({ isActive }) =>
                  cn(
                    'flex flex-1 items-center justify-center rounded-full transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset',
                    isActive ? 'bg-tab-active text-primary shadow-tab-active' : 'text-foreground',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {/* Besides the green, a lighter pill and a thicker stroke mark the active tab
                        (A11Y-01). The others are in the text colour, which stays readable over
                        photos. The name is only read out, not shown. */}
                    <Icon
                      aria-hidden="true"
                      strokeWidth={isActive ? 2.5 : 2}
                      className="size-(--tab-bar-icon)"
                    />
                    <span className="sr-only">{t(label)}</span>
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
