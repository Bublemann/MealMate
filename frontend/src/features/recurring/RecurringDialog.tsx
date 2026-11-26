import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { FieldError } from '@/components/ui/field-error';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import type { ItemSummary } from '@/features/items/api';
import { itemLabel } from '@/features/items/label';
import { useConnected } from '@/features/sync/context';
import { fieldErrorMessages, needsErrorAlert } from '@/i18n/errors';
import { testIds } from '@/testIds';
import {
  useCreateRecurringItem,
  useDeleteRecurringItem,
  useUpdateRecurringItem,
  type RecurringItem,
  type RecurringItemUpdate,
} from './api';

/** The weeks a new item starts with. */
const DEFAULT_WEEKS = 4;
/** The fields whose server errors show next to an input; others go to the alert. */
const SHOWN_FIELDS: ReadonlySet<string> = new Set([
  'item_id',
  'interval_weeks',
  'last_purchased_on',
]);

export interface RecurringTarget {
  item: Pick<ItemSummary, 'id' | 'name' | 'brand'>;
  /** The item's recurring item when it is recurring already: the pop-up edits it. */
  recurring?: RecurringItem;
}

interface RecurringDialogProps {
  /** What the pop-up is for; null closes it. */
  target: RecurringTarget | null;
  onClose: () => void;
  /** After "Hinzufügen", "Speichern" or "Nicht mehr regelmäßig" went through; then it closes. */
  onDone?: () => void;
  /** Where the focus goes when it closes (default: back to its trigger). */
  onCloseAutoFocus?: (event: Event) => void;
}

/**
 * The recurring pop-up (LIST-16, D-42), one for the page "Regelmäßige Artikel" and the
 * item's ⋯ menu: the item as its title, "Alle n Wochen", "Automatisch anpassen" and
 * "Zuletzt gekauft", then "Hinzufügen", or "Speichern" and the red "Nicht mehr regelmäßig" when
 * the item is recurring already. Its fields start afresh each time it opens.
 */
export function RecurringDialog({
  target,
  onClose,
  onDone,
  onCloseAutoFocus,
}: RecurringDialogProps) {
  const name = target ? itemLabel(target.item.name, target.item.brand) : '';

  function done() {
    onDone?.();
    onClose();
  }

  return (
    <Dialog open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        aria-describedby={undefined}
        data-testid={testIds.recurringDialog}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <DialogHeader>
          <DialogTitle>{name}</DialogTitle>
        </DialogHeader>
        {target &&
          (target.recurring ? (
            <EditForm recurring={target.recurring} name={name} onDone={done} />
          ) : (
            <CreateForm itemId={target.item.id} onDone={done} />
          ))}
      </DialogContent>
    </Dialog>
  );
}

/** Today on this device, as the date input takes it (`2026-10-25`). */
function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** The typed weeks as a whole number, or null when it isn't one; the server checks the range. */
function parseWeeks(text: string): number | null {
  const trimmed = text.trim();
  return /^\d+$/.test(trimmed) ? Number(trimmed) : null;
}

interface Values {
  weeks: string;
  automatic: boolean;
  lastBought: string;
}

function CreateForm({ itemId, onDone }: { itemId: string; onDone: () => void }) {
  const { t } = useTranslation();
  const create = useCreateRecurringItem();
  const [initialDate] = useState(today);

  return (
    <RecurringForm
      initial={{ weeks: String(DEFAULT_WEEKS), automatic: true, lastBought: initialDate }}
      // A new item's weeks are a first guess: it keeps adapting unless switched off by hand.
      followsInterval={false}
      submitLabel={t('recurring.dialog.add')}
      pending={create.isPending}
      error={create.error}
      onSubmit={({ weeks, automatic, lastBought }) =>
        create.mutate(
          {
            item_id: itemId,
            interval_weeks: weeks,
            automatic,
            // Untouched, the server takes its own today, in the instance's time zone.
            ...(lastBought !== initialDate ? { last_purchased_on: lastBought } : {}),
          },
          { onSuccess: onDone },
        )
      }
    />
  );
}

function EditForm({
  recurring,
  name,
  onDone,
}: {
  recurring: RecurringItem;
  name: string;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const update = useUpdateRecurringItem(recurring.id);
  const remove = useDeleteRecurringItem(recurring.id);
  const connected = useConnected();
  const [confirming, setConfirming] = useState(false);

  function onSubmit({ weeks, automatic, lastBought }: { weeks: number } & Omit<Values, 'weeks'>) {
    const body: RecurringItemUpdate = {};
    const weeksChanged = weeks !== recurring.interval_weeks;
    if (weeksChanged) body.interval_weeks = weeks;
    // With a new interval the switch is always sent: on, the interval adapts again.
    if (weeksChanged || automatic !== recurring.interval.automatic) body.automatic = automatic;
    if (lastBought !== recurring.last_purchased_on) body.last_purchased_on = lastBought;
    if (Object.keys(body).length === 0) onDone();
    else update.mutate(body, { onSuccess: onDone });
  }

  return (
    <>
      <RecurringForm
        initial={{
          weeks: String(recurring.interval_weeks),
          automatic: recurring.interval.automatic,
          lastBought: recurring.last_purchased_on,
        }}
        followsInterval
        submitLabel={t('common.save')}
        pending={update.isPending}
        busy={remove.isPending}
        error={update.error ?? remove.error}
        onSubmit={onSubmit}
        extra={
          <Button
            type="button"
            variant="ghost"
            data-testid={testIds.recurringRemove}
            className="text-destructive hover:text-destructive"
            pending={remove.isPending}
            disabled={!connected || update.isPending}
            onClick={() => setConfirming(true)}
          >
            {t('recurring.dialog.remove')}
          </Button>
        }
      />
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('recurring.dialog.removeTitle', { name })}
        description={t('recurring.dialog.removeText')}
        confirmLabel={t('recurring.dialog.remove')}
        destructive
        onConfirm={() => remove.mutate(undefined, { onSuccess: onDone })}
      />
    </>
  );
}

interface RecurringFormProps {
  initial: Values;
  /**
   * Editing: "Automatisch anpassen" is off while the interval differs from the item's, and as it
   * was once the interval is typed back. Switched by hand, the interval no longer moves it.
   */
  followsInterval: boolean;
  submitLabel: string;
  /** Its own save runs: the button shows the spinner (UI-08). */
  pending: boolean;
  /** Another change runs (the removal): the button only takes no press. */
  busy?: boolean;
  error: unknown;
  onSubmit: (values: { weeks: number } & Omit<Values, 'weeks'>) => void;
  /** Below the main button: "Nicht mehr regelmäßig" when editing. */
  extra?: ReactNode;
}

function RecurringForm({
  initial,
  followsInterval,
  submitLabel,
  pending,
  busy = false,
  error,
  onSubmit,
  extra,
}: RecurringFormProps) {
  const { t } = useTranslation();
  const connected = useConnected();
  const id = useId();
  const everyId = `${id}-every`;
  const weeksUnitId = `${id}-weeks`;
  const weeksErrorId = `${id}-weeks-error`;
  const switchId = `${id}-automatic`;
  const switchHintId = `${switchId}-hint`;
  const [weeks, setWeeks] = useState(initial.weeks);
  const [automatic, setAutomatic] = useState(initial.automatic);
  const [switchedByHand, setSwitchedByHand] = useState(false);
  const [lastBought, setLastBought] = useState(initial.lastBought);
  const [weeksInvalid, setWeeksInvalid] = useState(false);
  const fields = fieldErrorMessages(t, error);
  const weeksError = weeksInvalid ? t('error.field.invalid_format') : fields.interval_weeks;

  function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseWeeks(weeks);
    setWeeksInvalid(parsed === null);
    if (parsed !== null) onSubmit({ weeks: parsed, automatic, lastBought });
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      {fields.item_id && <FieldError>{fields.item_id}</FieldError>}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span id={everyId} className="text-sm font-medium">
            {t('recurring.dialog.every')}
          </span>
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={52}
            step={1}
            className="w-20"
            aria-labelledby={`${everyId} ${weeksUnitId}`}
            aria-describedby={weeksError ? weeksErrorId : undefined}
            aria-invalid={weeksError ? true : undefined}
            value={weeks}
            onChange={(event) => {
              const next = event.target.value;
              setWeeks(next);
              setWeeksInvalid(false);
              if (followsInterval && !switchedByHand) {
                const unchanged = parseWeeks(next) === parseWeeks(initial.weeks);
                setAutomatic(unchanged ? initial.automatic : false);
              }
            }}
          />
          <span id={weeksUnitId} className="text-sm font-medium">
            {t('recurring.dialog.weeks')}
          </span>
        </div>
        {weeksError && <FieldError id={weeksErrorId}>{weeksError}</FieldError>}
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor={switchId}>{t('recurring.dialog.automatic')}</Label>
          <Switch
            id={switchId}
            aria-describedby={switchHintId}
            checked={automatic}
            onCheckedChange={(checked) => {
              setAutomatic(checked);
              setSwitchedByHand(true);
            }}
          />
        </div>
        <p id={switchHintId} className="text-sm text-muted-foreground">
          {t('recurring.dialog.automaticHint')}
        </p>
      </div>
      <FormField label={t('recurring.dialog.lastBought')} error={fields.last_purchased_on}>
        {(control) => (
          <Input
            {...control}
            type="date"
            required
            max={today()}
            value={lastBought}
            onChange={(event) => setLastBought(event.target.value)}
          />
        )}
      </FormField>
      {error !== null && needsErrorAlert(fields, SHOWN_FIELDS) && <ErrorAlert error={error} />}
      <div className="flex flex-col gap-2">
        <Button type="submit" pending={pending} disabled={!connected || busy}>
          {submitLabel}
        </Button>
        {extra}
      </div>
    </form>
  );
}
