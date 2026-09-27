import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { isApiError } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useCurrentUser } from '@/features/auth/context';
import { fieldErrorMessages } from '@/i18n/errors';
import { testIds } from '@/testIds';
import { useChangePassword } from './api';

/** Change password (ACC-09): the server logs out every other device. */
export function PasswordDialog({ onChanged }: { onChanged: () => void }) {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const change = useChangePassword();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const fields = fieldErrorMessages(t, change.error);
  const wrongCurrent = isApiError(change.error) && change.error.code === 'auth.password_incorrect';
  const currentError = wrongCurrent ? t('error.auth.password_incorrect') : fields.current_password;
  const showAlert = !wrongCurrent && Object.keys(fields).length === 0;

  function onOpenChange(value: boolean) {
    setOpen(value);
    if (!value) {
      setCurrent('');
      setNext('');
      change.reset();
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          onOpenChange(false);
          onChanged();
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" data-testid={testIds.changePasswordButton}>
          {t('me.password.change')}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('me.password.title')}</DialogTitle>
          <DialogDescription>{t('me.password.text')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          {/* Lets password managers update the entry of this account. */}
          <input
            type="text"
            name="username"
            autoComplete="username"
            value={user.username}
            readOnly
            hidden
          />
          <FormField label={t('me.password.current')} error={currentError}>
            {(control) => (
              <Input
                {...control}
                type="password"
                name="current-password"
                autoComplete="current-password"
                required
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
              />
            )}
          </FormField>
          <FormField
            label={t('auth.field.newPassword')}
            hint={t('auth.field.passwordRules')}
            error={fields.new_password}
          >
            {(control) => (
              <Input
                {...control}
                type="password"
                name="new-password"
                autoComplete="new-password"
                required
                value={next}
                onChange={(event) => setNext(event.target.value)}
              />
            )}
          </FormField>
          {showAlert && <ErrorAlert error={change.error} />}
          <DialogFooter>
            <Button type="submit" disabled={change.isPending}>
              {t('me.password.submit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
