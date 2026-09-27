import { useTranslation } from 'react-i18next';
import { testIds } from '@/testIds';
import { reminderText } from './format';

/** LIST-14: the list's friendly reminder, its last row. */
export function Reminder({ seed }: { seed: number }) {
  const { t } = useTranslation();

  return (
    <p
      data-testid={testIds.listReminder}
      className="rounded-xl bg-accent px-4 py-3 text-accent-foreground"
    >
      <span className="sr-only">{t('lists.reminderLabel')}: </span>
      {reminderText(t, seed)}
    </p>
  );
}
