import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { ShareLink } from '@/components/ShareLink';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCurrentUser } from '@/features/auth/context';
import { useLanguage } from '@/i18n';
import { formatDate } from '@/i18n/format';
import { testIds } from '@/testIds';
import { AdminScreen } from './AdminScreen';
import {
  useAdminUsers,
  useCreateResetLink,
  useDeleteUser,
  useUpdateUser,
  type AdminUser,
} from './api';
import { resetMessage } from './shareMessages';

/** Users with role, deactivation, reset link and deletion (ADM-01..03, ACC-10). */
export function AdminUsersScreen() {
  const { t } = useTranslation();
  const users = useAdminUsers();
  const me = useCurrentUser();

  return (
    <AdminScreen title={t('admin.users.title')} testId={testIds.screenAdminUsers}>
      {users.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <ErrorAlert error={users.error} />
      {users.data && (
        <ul data-testid={testIds.adminUserList} className="flex flex-col gap-4">
          {users.data.map((user) => (
            <li key={user.id}>
              <UserCard user={user} self={user.id === me.id} />
            </li>
          ))}
        </ul>
      )}
    </AdminScreen>
  );
}

function UserCard({ user, self }: { user: AdminUser; self: boolean }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const name = user.display_name;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {name}
          {user.role === 'admin' && <Badge>{t('admin.users.roleAdmin')}</Badge>}
          {!user.is_active && <Badge variant="destructive">{t('admin.users.deactivated')}</Badge>}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          {t('admin.users.meta', {
            username: user.username,
            date: formatDate(user.created_at, language),
          })}
          {' · '}
          {user.last_seen_at
            ? t('admin.users.lastSeen', { date: formatDate(user.last_seen_at, language) })
            : t('admin.users.neverSeen')}
        </p>
      </CardHeader>
      <CardContent>
        {self ? (
          <p className="text-sm text-muted-foreground">{t('admin.users.self')}</p>
        ) : (
          <UserActions user={user} />
        )}
      </CardContent>
    </Card>
  );
}

function UserActions({ user }: { user: AdminUser }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const update = useUpdateUser(user.id);
  const remove = useDeleteUser(user.id);
  const resetLink = useCreateResetLink(user.id);
  const name = user.display_name;
  const busy = update.isPending || remove.isPending;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Button
          size="compact"
          variant="outline"
          disabled={busy}
          onClick={() => update.mutate({ role: user.role === 'admin' ? 'user' : 'admin' })}
          aria-label={
            user.role === 'admin'
              ? t('admin.users.demoteLabel', { name })
              : t('admin.users.promoteLabel', { name })
          }
        >
          {user.role === 'admin' ? t('admin.users.demote') : t('admin.users.promote')}
        </Button>
        {user.is_active ? (
          <ConfirmDialog
            trigger={
              <Button
                size="compact"
                variant="outline"
                disabled={busy}
                aria-label={t('admin.users.deactivateLabel', { name })}
              >
                {t('admin.users.deactivate')}
              </Button>
            }
            title={t('admin.users.deactivateTitle', { name })}
            description={t('admin.users.deactivateText')}
            confirmLabel={t('admin.users.deactivate')}
            onConfirm={() => update.mutate({ is_active: false })}
            destructive
          />
        ) : (
          <Button
            size="compact"
            variant="outline"
            disabled={busy}
            onClick={() => update.mutate({ is_active: true })}
            aria-label={t('admin.users.reactivateLabel', { name })}
          >
            {t('admin.users.reactivate')}
          </Button>
        )}
        <Button
          size="compact"
          variant="outline"
          disabled={busy || resetLink.isPending}
          onClick={() => resetLink.mutate()}
          aria-label={t('admin.users.resetLinkLabel', { name })}
        >
          {t('admin.users.resetLink')}
        </Button>
        <ConfirmDialog
          trigger={
            <Button
              size="compact"
              variant="destructive"
              disabled={busy}
              aria-label={t('admin.users.deleteLabel', { name })}
            >
              {t('admin.users.delete')}
            </Button>
          }
          title={t('admin.users.deleteTitle', { name, username: user.username })}
          description={t('admin.users.deleteText')}
          confirmLabel={t('admin.users.deleteConfirm')}
          onConfirm={() => remove.mutate()}
          destructive
        />
      </div>
      <ErrorAlert error={update.error ?? remove.error ?? resetLink.error} />
      {resetLink.data && (
        <ShareLink
          label={t('admin.users.resetLinkField', { name })}
          url={resetLink.data.url}
          message={resetMessage(t, language, {
            url: resetLink.data.url,
            expiresAt: resetLink.data.expires_at,
            name,
          })}
        />
      )}
    </div>
  );
}
