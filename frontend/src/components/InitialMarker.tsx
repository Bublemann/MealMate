import { useTranslation } from 'react-i18next';
import type { components } from '@/api/generated/schema';
import { userLabel } from '@/i18n/users';
import { initialOf } from '@/lib/initial';
import type { TestId } from '@/testIds';

type UserRef = components['schemas']['UserRef'];

interface InitialMarkerProps {
  user: UserRef;
  /**
   * Hidden from screen readers, for a place that names the user in words of its own (who
   * checked a line, SHOP-01). Otherwise screen readers read the marker as the user's name.
   */
  decorative?: boolean;
  testId?: TestId;
}

/**
 * A user's initial in a small round marker: who checked a line in shopping mode (SHOP-01) and
 * whose list or meal a row is (UI-02, MEAL-09), one's own included.
 */
export function InitialMarker({ user, decorative = false, testId }: InitialMarkerProps) {
  const { t } = useTranslation();
  const name = userLabel(t, user);

  return (
    <span
      data-testid={testId}
      {...(decorative ? { 'aria-hidden': true, title: name } : { role: 'img', 'aria-label': name })}
      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-foreground"
    >
      {initialOf(user.display_name)}
    </span>
  );
}
