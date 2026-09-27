import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { ShareLink } from '@/components/ShareLink';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useLanguage } from '@/i18n';
import { fieldErrorMessages } from '@/i18n/errors';
import { formatDate, formatDateTime } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { testIds } from '@/testIds';
import { AdminScreen } from './AdminScreen';
import { useCreateInvite, useInvites, useRevokeInvite, type Invite } from './api';
import { inviteMessage } from './shareMessages';

/** Create, share and revoke invites (ACC-01..03, ADM-01). */
export function AdminInvitesScreen() {
  const { t } = useTranslation();

  return (
    <AdminScreen title={t('admin.invites.title')} testId={testIds.screenAdminInvites}>
      <CreateInvite />
      <InviteList />
    </AdminScreen>
  );
}

function CreateInvite() {
  const { t } = useTranslation();
  const language = useLanguage();
  const create = useCreateInvite();
  const [tailscaleUrl, setTailscaleUrl] = useState('');
  const fields = fieldErrorMessages(t, create.error);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate(tailscaleUrl.trim() || null);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('admin.invites.createTitle')}</CardTitle>
        <CardDescription>{t('admin.invites.createText')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <FormField
            label={t('admin.invites.tailscaleLabel')}
            hint={t('admin.invites.tailscaleHint')}
            error={fields.tailscale_share_url}
          >
            {(control) => (
              <Input
                {...control}
                type="url"
                inputMode="url"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                maxLength={500}
                placeholder="https://login.tailscale.com/…"
                value={tailscaleUrl}
                onChange={(event) => setTailscaleUrl(event.target.value)}
              />
            )}
          </FormField>
          {!fields.tailscale_share_url && <ErrorAlert error={create.error} />}
          <Button
            type="submit"
            data-testid={testIds.createInviteButton}
            disabled={create.isPending}
            className="self-start"
          >
            {t('admin.invites.create')}
          </Button>
        </form>
        {create.data && (
          <ShareLink
            label={t('admin.invites.linkLabel')}
            url={create.data.url}
            message={inviteMessage(t, language, {
              url: create.data.url,
              expiresAt: create.data.invite.expires_at,
              tailscaleUrl: create.data.invite.tailscale_share_url,
            })}
          />
        )}
      </CardContent>
    </Card>
  );
}

function InviteList() {
  const { t } = useTranslation();
  const invites = useInvites();
  const revoke = useRevokeInvite();
  const headingId = useId();

  return (
    <section className="flex flex-col gap-3" aria-labelledby={headingId}>
      <h2 id={headingId} className="text-lg font-semibold">
        {t('admin.invites.listTitle')}
      </h2>
      {invites.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <ErrorAlert error={invites.error ?? revoke.error} />
      {invites.data?.length === 0 && (
        <p className="text-muted-foreground">{t('admin.invites.empty')}</p>
      )}
      {invites.data && invites.data.length > 0 && (
        <ul data-testid={testIds.inviteList} className="flex flex-col divide-y rounded-xl border">
          {invites.data.map((invite) => (
            <InviteRow
              key={invite.id}
              invite={invite}
              onRevoke={() => revoke.mutate(invite.id)}
              revoking={revoke.isPending && revoke.variables === invite.id}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

interface InviteRowProps {
  invite: Invite;
  onRevoke: () => void;
  revoking: boolean;
}

function InviteRow({ invite, onRevoke, revoking }: InviteRowProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const created = formatDateTime(invite.created_at, language);

  return (
    <li className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="flex min-w-0 flex-col gap-1">
        <p className="flex flex-wrap items-center gap-2">
          <Badge variant={invite.status === 'open' ? 'default' : 'outline'}>
            {t(`admin.invites.status.${invite.status}`)}
          </Badge>
          {invite.status === 'used' && (
            <span>{t('admin.invites.usedBy', { name: userLabel(t, invite.used_by) })}</span>
          )}
        </p>
        <p className="text-sm text-muted-foreground">
          {t('admin.invites.createdBy', { date: created, name: userLabel(t, invite.created_by) })}
        </p>
        {invite.status === 'open' && (
          <p className="text-sm text-muted-foreground">
            {t('admin.invites.validUntil', { date: formatDate(invite.expires_at, language) })}
          </p>
        )}
      </div>
      {invite.status === 'open' && (
        <Button
          size="compact"
          variant="outline"
          disabled={revoking}
          onClick={onRevoke}
          aria-label={t('admin.invites.revokeLabel', { date: created })}
        >
          {t('admin.invites.revoke')}
        </Button>
      )}
    </li>
  );
}
