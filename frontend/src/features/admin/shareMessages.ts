import type { TFunction } from 'i18next';
import type { Language } from '@/i18n';
import { formatDateTime } from '@/i18n/format';

/**
 * The prepared messages for the share sheet (ACC-03, ACC-10), in the admin's UI language, with
 * the two steps: (1) Tailscale, (2) the link.
 */
export function inviteMessage(
  t: TFunction,
  language: Language,
  {
    url,
    expiresAt,
    tailscaleUrl,
  }: { url: string; expiresAt: string; tailscaleUrl?: string | null },
): string {
  const date = formatDateTime(expiresAt, language);
  return tailscaleUrl
    ? t('admin.invites.messageWithTailscale', { url, date, tailscaleUrl })
    : t('admin.invites.message', { url, date });
}

export function resetMessage(
  t: TFunction,
  language: Language,
  { url, expiresAt, name }: { url: string; expiresAt: string; name: string },
): string {
  return t('admin.users.resetMessage', { url, name, date: formatDateTime(expiresAt, language) });
}
