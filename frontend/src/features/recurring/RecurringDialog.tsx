import { CircleAlert } from 'lucide-react';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import type { IngredientSummary } from '@/features/ingredients/api';
import { ingredientLabel } from '@/features/ingredients/label';
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
  'ingredient_id',
  'interval_weeks',
  'last_purchased_on',
]);

export interface RecurringTarget {
  ingredient: Pick<IngredientSummary, 'id' | 'name' | 'brand'>;
  /** The ingredient's item when it is recurring already: the pop-up edits it. */
  item?: RecurringItem;
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
 * ingredient's ⋯ menu: the ingredient as its title, "Alle n Wochen", "Automatisch anpassen" and
 * "Zuletzt gekauft", then "Hinzufügen", or "Speichern" and the red "Nicht mehr regelmäßig" when
 * the ingredient is recurring already. Its fields start afresh each time it opens.
 */
export function RecurringDialog({
  target,
  onClose,
  onDone,
  onCloseAutoFocus,
}: RecurringDialogProps) {
  const name = target ? ingredientLabel(target.ingredient.name, target.ingredient.brand) : '';

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
          (target.item ? (
            <EditForm item={target.item} name={name} onDone={done} />
          ) : (
            <CreateForm ingredientId={target.ingredient.id} onDone={done} />
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

function CreateForm({ ingredientId, onDone }: { ingredientId: string; onDone: () => void }) {
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
            ingredient_id: ingredientId,
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
  item,
  name,
  onDone,
}: {
  item: RecurringItem;
  name: string;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const update = useUpdateRecurringItem(item.id);
  const remove = useDeleteRecurringItem(item.id);
  const connected = useConnected();
  const [confirming, setConfirming] = useState(false);

  function onSubmit({ weeks, automatic, lastBought }: { weeks: number } & Omit<Values, 'weeks'>) {
    const body: RecurringItemUpdate = {};
    const weeksChanged = weeks !== item.interval_weeks;
    if (weeksChanged) body.interval_weeks = weeks;
    // With a new interval the switch is always sent: on, the interval adapts again.
    if (weeksChanged || automatic !== item.interval.automatic) body.automatic = automatic;
    if (lastBought !== item.last_purchased_on) body.last_purchased_on = lastBought;
    if (Object.keys(body).length === 0) onDone();
    else update.mutate(body, { onSuccess: onDone });
  }

  return (
    <>
      <RecurringForm
        initial={{
          weeks: String(item.interval_weeks),
          automatic: item.interval.automatic,
          lastBought: item.last_purchased_on,
        }}
        followsInterval
        submitLabel={t('common.save')}
        pending={update.isPending || remove.isPending}
        error={update.error ?? remove.error}
        onSubmit={onSubmit}
        extra={
          <Button
            type="button"
            variant="ghost"
            data-testid={testIds.recurringRemove}
            className="text-destructive hover:text-destructive"
            disabled={!connected || update.isPending || remove.isPending}
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
  /** Editing: a changed interval turns "Automatisch anpassen" off; it can be turned on again. */
  followsInterval: boolean;
  submitLabel: string;
  pending: boolean;
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
      {fields.ingredient_id && (
        <p className="flex items-start gap-1.5 text-sm font-medium text-destructive">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          {fields.ingredient_id}
        </p>
      )}
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
              setWeeks(event.target.value);
              setWeeksInvalid(false);
              if (followsInterval) setAutomatic(false);
            }}
          />
          <span id={weeksUnitId} className="text-sm font-medium">
            {t('recurring.dialog.weeks')}
          </span>
        </div>
        {weeksError && (
          <p
            id={weeksErrorId}
            className="flex items-start gap-1.5 text-sm font-medium text-destructive"
          >
            <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            {weeksError}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor={switchId}>{t('recurring.dialog.automatic')}</Label>
          <Switch
            id={switchId}
            aria-describedby={switchHintId}
            checked={automatic}
            onCheckedChange={setAutomatic}
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
        <Button type="submit" disabled={pending || !connected}>
          {submitLabel}
        </Button>
        {extra}
      </div>
    </form>
  );
}
