import { Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useCategories, type Unit } from '@/features/reference/api';
import { fieldErrorMessages } from '@/i18n/errors';
import { formatNumber, parseAmount } from '@/i18n/format';
import { useLanguage } from '@/i18n';
import {
  useRemoveExtraItem,
  useUpdateExtraItem,
  type ExtraItem,
  type ExtraItemUpdate,
} from './api';
import { AmountFields, FreeTextFields } from './ExtraItemFields';
import { otherCategoryId } from './format';

interface ExtraItemDialogProps {
  listId: string;
  /** The item being edited; null closes the dialog. */
  item: ExtraItem | null;
  /** The item's name as the list shows it (the ingredient's name for a linked item). */
  name: string;
  onClose: () => void;
}

/** Edit or remove an extra item (editors, LIST-06); its kind (linked or free text) stays. */
export function ExtraItemDialog({ listId, item, name, onClose }: ExtraItemDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={item !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t('lists.item.editTitle')}</DialogTitle>
        </DialogHeader>
        {item && (
          <ItemForm key={item.id} listId={listId} item={item} name={name} onDone={onClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface ItemFormProps {
  listId: string;
  item: ExtraItem;
  name: string;
  onDone: () => void;
}

function ItemForm({ listId, item, name, onDone }: ItemFormProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const update = useUpdateExtraItem(listId);
  const remove = useRemoveExtraItem(listId);
  const linked = item.ingredient_id !== null;
  const [text, setText] = useState(item.text ?? '');
  const [amount, setAmount] = useState(
    item.amount === null ? '' : formatNumber(item.amount, language, { useGrouping: false }),
  );
  const [unit, setUnit] = useState<Unit>(item.unit ?? 'piece');
  const [amountText, setAmountText] = useState(item.amount_text ?? '');
  const [categoryId, setCategoryId] = useState(item.category_id ?? '');
  const [amountInvalid, setAmountInvalid] = useState(false);
  const chosenCategory = categoryId || otherCategoryId(categories.data);
  const serverFields = fieldErrorMessages(t, update.error);
  const busy = update.isPending || remove.isPending;

  function body(): ExtraItemUpdate | null {
    if (linked) {
      const trimmed = amount.trim();
      if (trimmed === '') return { amount: null, unit: null };
      const value = parseAmount(trimmed);
      return value === null ? null : { amount: value, unit };
    }
    return {
      text: text.trim(),
      amount_text: amountText.trim() || null,
      ...(chosenCategory ? { category_id: chosenCategory } : {}),
    };
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const changes = body();
    setAmountInvalid(changes === null);
    if (changes) update.mutate({ extraId: item.id, body: changes }, { onSuccess: onDone });
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-label={name} className="flex flex-col gap-4">
      {linked ? (
        <>
          <p className="font-medium break-words">{name}</p>
          <AmountFields
            amount={amount}
            unit={unit}
            onAmountChange={(value) => {
              setAmountInvalid(false);
              setAmount(value);
            }}
            onUnitChange={setUnit}
            amountError={amountInvalid ? t('error.field.invalid_format') : serverFields.amount}
            unitError={serverFields.unit}
          />
        </>
      ) : (
        <>
          <FormField label={t('lists.item.text')} error={serverFields.text}>
            {(control) => (
              <Input
                {...control}
                name="text"
                autoComplete="off"
                required
                maxLength={80}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            )}
          </FormField>
          <FreeTextFields
            amountText={amountText}
            categoryId={chosenCategory}
            onAmountTextChange={setAmountText}
            onCategoryChange={setCategoryId}
            amountTextError={serverFields.amount_text}
            categoryError={serverFields.category_id}
          />
        </>
      )}
      <ErrorAlert error={Object.keys(serverFields).length === 0 ? update.error : null} />
      <ErrorAlert error={remove.error} />
      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          aria-label={t('lists.item.removeLabel', { name })}
          disabled={busy}
          onClick={() => remove.mutate(item.id, { onSuccess: onDone })}
        >
          <Trash2 aria-hidden="true" />
          {t('lists.item.remove')}
        </Button>
        <Button type="submit" disabled={busy || (!linked && text.trim() === '')}>
          {t('common.save')}
        </Button>
      </DialogFooter>
    </form>
  );
}
