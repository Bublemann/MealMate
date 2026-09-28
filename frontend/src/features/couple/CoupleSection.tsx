import { HeartHandshake } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadError } from '@/components/LoadError';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { useLanguage } from '@/i18n';
import { formatDate } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { testIds } from '@/testIds';
import {
  useAnswerCoupleRequest,
  useCouple,
  useEndCouple,
  useSendCoupleRequest,
  useUsers,
  type CoupleRequest,
  type CoupleState,
} from './api';

/** Couple status, requests and the user picker (CPL-01, CPL-05, CPL-07). */
export function CoupleSection() {
  const { t } = useTranslation();
  const couple = useCouple();

  return (
    <Card data-testid={testIds.coupleSection}>
      <CardHeader>
        <CardTitle>{t('couple.title')}</CardTitle>
        <CardDescription>{t('couple.text')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {couple.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        <LoadError error={couple.error} />
        {couple.data && <CoupleContent state={couple.data} />}
      </CardContent>
    </Card>
  );
}

function CoupleContent({ state }: { state: CoupleState }) {
  const answer = useAnswerCoupleRequest();

  return (
    <>
      {state.partner ? (
        <Partner state={state} />
      ) : state.outgoing ? (
        <Outgoing request={state.outgoing} answer={answer} />
      ) : (
        <RequestForm />
      )}
      {!state.partner && state.incoming.length > 0 && (
        <Incoming requests={state.incoming} answer={answer} />
      )}
      <ErrorAlert error={answer.error} />
    </>
  );
}

function Partner({ state }: { state: CoupleState }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const end = useEndCouple();
  const name = userLabel(t, state.partner);

  return (
    <div className="flex flex-col gap-3">
      <p className="flex items-center gap-2">
        <HeartHandshake aria-hidden="true" className="size-5 shrink-0 text-primary" />
        <span data-testid={testIds.couplePartner}>
          {state.since
            ? t('couple.partnerSince', { name, date: formatDate(state.since, language) })
            : t('couple.partner', { name })}
        </span>
      </p>
      <ConfirmDialog
        trigger={
          <Button variant="outline" className="self-start" disabled={end.isPending}>
            {t('couple.end')}
          </Button>
        }
        title={t('couple.endTitle', { name })}
        description={t('couple.endText')}
        confirmLabel={t('couple.endConfirm')}
        onConfirm={() => end.mutate()}
        destructive
      />
      <ErrorAlert error={end.error} />
    </div>
  );
}

type Answer = ReturnType<typeof useAnswerCoupleRequest>;

function Outgoing({ request, answer }: { request: CoupleRequest; answer: Answer }) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-3">
      <p>{t('couple.outgoing', { name: userLabel(t, request.to_user) })}</p>
      <Button
        variant="outline"
        className="self-start"
        disabled={answer.isPending}
        onClick={() => answer.mutate({ requestId: request.id, action: 'cancel' })}
      >
        {t('couple.cancelRequest')}
      </Button>
    </div>
  );
}

function Incoming({ requests, answer }: { requests: CoupleRequest[]; answer: Answer }) {
  const { t } = useTranslation();

  return (
    <ul className="flex flex-col gap-3" aria-label={t('couple.incomingLabel')}>
      {requests.map((request) => {
        const name = userLabel(t, request.from_user);
        return (
          <li key={request.id} className="flex flex-col gap-2 rounded-lg border p-3">
            <p>{t('couple.incoming', { name })}</p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="compact"
                disabled={answer.isPending}
                aria-label={t('couple.acceptLabel', { name })}
                onClick={() => answer.mutate({ requestId: request.id, action: 'accept' })}
              >
                {t('couple.accept')}
              </Button>
              <Button
                size="compact"
                variant="outline"
                disabled={answer.isPending}
                aria-label={t('couple.declineLabel', { name })}
                onClick={() => answer.mutate({ requestId: request.id, action: 'decline' })}
              >
                {t('couple.decline')}
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function RequestForm() {
  const { t } = useTranslation();
  const users = useUsers();
  const send = useSendCoupleRequest();
  const selectId = useId();
  const [userId, setUserId] = useState('');

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (userId) send.mutate(userId, { onSuccess: () => setUserId('') });
  }

  if (users.data?.length === 0) {
    return <p className="text-muted-foreground">{t('couple.nobody')}</p>;
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <Label htmlFor={selectId}>{t('couple.pickLabel')}</Label>
      <NativeSelect
        id={selectId}
        data-testid={testIds.couplePicker}
        value={userId}
        onChange={(event) => setUserId(event.target.value)}
        disabled={!users.data}
      >
        <NativeSelectOption value="">{t('couple.pickPlaceholder')}</NativeSelectOption>
        {users.data?.map((user) => (
          <NativeSelectOption key={user.id} value={user.id}>
            {userLabel(t, user)}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      <ErrorAlert error={users.error ?? send.error} />
      <Button type="submit" className="self-start" disabled={!userId || send.isPending}>
        {t('couple.send')}
      </Button>
    </form>
  );
}
