import { ChevronLeft } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink } from 'react-router';
import { Screen } from '@/components/Screen';
import { cn } from '@/lib/utils';
import type { TestId } from '@/testIds';

const SECTIONS = [
  { to: '/me/admin/users', label: 'admin.users.title' },
  { to: '/me/admin/invites', label: 'admin.invites.title' },
  { to: '/me/admin/events', label: 'admin.events.title' },
] as const;

interface AdminScreenProps {
  title: string;
  testId: TestId;
  children: ReactNode;
}

/** An admin screen (ADM-01): back to Me, the section switcher, then the content. */
export function AdminScreen({ title, testId, children }: AdminScreenProps) {
  const { t } = useTranslation();

  return (
    <Screen title={title} testId={testId}>
      <nav aria-label={t('admin.title')} className="-mt-3 flex flex-col gap-3">
        <Link
          to="/me"
          className="inline-flex min-h-(--tap-target) items-center gap-1 self-start font-medium text-primary underline-offset-4 hover:underline"
        >
          <ChevronLeft aria-hidden="true" className="size-5" />
          {t('admin.backToMe')}
        </Link>
        <ul className="flex flex-wrap gap-2">
          {SECTIONS.map(({ to, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  cn(
                    'inline-flex min-h-(--tap-target) items-center rounded-full border px-4 text-sm font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring',
                    // Filled and bold when active, so the colour is not the only signal.
                    isActive
                      ? 'border-primary bg-primary font-bold text-primary-foreground'
                      : 'hover:bg-accent',
                  )
                }
              >
                {t(label)}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      {children}
    </Screen>
  );
}
