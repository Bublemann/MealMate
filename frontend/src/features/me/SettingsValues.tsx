import { useTranslation } from 'react-i18next';
import { useCurrentUser } from '@/features/auth/context';
import { useCouple, waitingRequests } from '@/features/couple/api';
import { userLabel } from '@/i18n/users';
import { useVersionInfo } from './api';

// The values of the Settings rows (D-45), each loading on its own: nothing while it loads or
// when it fails, so the row shows at once and stays tappable.

/** Profil: the display name, which the Settings tab loads again as it opens. */
export function ProfileValue() {
  return useCurrentUser().display_name;
}

/** Paar: "1 Anfrage" while requests wait (D-51), else the partner, marked when deactivated. */
export function CoupleValue() {
  const { t } = useTranslation();
  const { data } = useCouple();
  if (!data) return null;
  const requests = waitingRequests(data);
  if (requests > 0) return t('couple.requests', { count: requests });
  return data.partner ? userLabel(t, data.partner) : null;
}

/** Über MealMate: the running version. */
export function VersionValue() {
  return useVersionInfo().data?.version ?? null;
}
