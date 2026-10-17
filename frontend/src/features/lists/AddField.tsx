import { Plus, Search } from 'lucide-react';
import {
  useEffect,
  useId,
  useRef,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { TestId } from '@/testIds';

/** The longest text the field takes: a free-text item's (LIST-06), longer than any meal search. */
export const MAX_FIELD_LENGTH = 80;

interface AddFieldProps {
  inputRef: RefObject<HTMLInputElement | null>;
  /** For screen readers only; nothing visible names the field. */
  label: string;
  placeholder: string;
  value: string;
  onValueChange: (value: string) => void;
  /** Inactive, not hidden, e.g. offline (SYNC-03). */
  disabled?: boolean;
  /** ＋ or Enter with text in the field. */
  onAdd: () => void;
  /** Shows the panel below the field. */
  panelOpen: boolean;
  /** The create options for the typed text, pinned right under the field. */
  options?: ReactNode;
  /** The results, below the options. */
  results?: ReactNode;
  /** The field was focused or tapped: e.g. show the panel again. */
  onOpen?: () => void;
  /** A tap outside the field and its panel, or Escape in the field. */
  onDismiss?: () => void;
  /** Below the panel, e.g. an error of the last add. */
  children?: ReactNode;
  inputTestId: TestId;
  panelTestId?: TestId;
}

/**
 * The look-alike field of a list's two sections (D-41): a search input and a ＋, and below them a
 * panel with the create options for the typed text first, then the results. The options never
 * move: results arriving late only grow below them. No label, hint or box shows; the input has a
 * label for screen readers.
 */
export function AddField({
  inputRef,
  label,
  placeholder,
  value,
  onValueChange,
  disabled = false,
  onAdd,
  panelOpen,
  options,
  results,
  onOpen,
  onDismiss,
  children,
  inputTestId,
  panelTestId,
}: AddFieldProps) {
  const { t } = useTranslation();
  const inputId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const typed = value.trim();
  const shown = panelOpen && !disabled;

  // A tap anywhere else closes the panel once the tap is done: closing it on the way down would
  // move what is below it, e.g. the other field's results, from under the finger. Taps in a
  // pop-up, or on what went away with the tap (the pop-up's "Hinzufügen"), leave it as it is.
  useEffect(() => {
    if (!shown || !onDismiss) return;
    const onClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element) || !target.isConnected) return;
      if (rootRef.current?.contains(target)) return;
      if (target.closest('[role="dialog"], [role="alertdialog"]')) return;
      onDismiss();
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, [shown, onDismiss]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (typed && !disabled) onAdd();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape' && shown && onDismiss) {
      event.preventDefault();
      onDismiss();
    }
  }

  return (
    <div ref={rootRef} className="flex min-w-0 flex-col gap-2">
      <form onSubmit={onSubmit} noValidate className="flex min-w-0 items-center gap-2">
        <label htmlFor={inputId} className="sr-only">
          {label}
        </label>
        <div className="relative min-w-0 flex-1">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 size-5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            ref={inputRef}
            id={inputId}
            data-testid={inputTestId}
            type="search"
            enterKeyHint="enter"
            autoComplete="off"
            maxLength={MAX_FIELD_LENGTH}
            className="pl-10"
            placeholder={placeholder}
            disabled={disabled}
            value={value}
            onChange={(event) => onValueChange(event.target.value)}
            onFocus={onOpen}
            onClick={onOpen}
            onKeyDown={onKeyDown}
          />
        </div>
        <Button
          type="submit"
          variant="outline"
          size="icon"
          className="shrink-0"
          disabled={disabled || !typed}
          aria-label={typed ? t('lists.addField.plus', { name: typed }) : t('lists.addField.add')}
        >
          <Plus aria-hidden="true" />
        </Button>
      </form>
      {shown && (options || results) && (
        <div data-testid={panelTestId} className="flex min-w-0 flex-col gap-3">
          {options}
          {results}
        </div>
      )}
      {children}
    </div>
  );
}

interface FieldOptionsProps {
  children: ReactNode;
}

/** The create options, one tap target each, as the first thing under the field. */
export function FieldOptions({ children }: FieldOptionsProps) {
  return <ul className="flex flex-col divide-y overflow-hidden rounded-lg border">{children}</ul>;
}

interface FieldOptionProps {
  testId: TestId;
  onSelect: () => void;
  children: ReactNode;
}

export function FieldOption({ testId, onSelect, children }: FieldOptionProps) {
  return (
    <li>
      <button
        type="button"
        data-testid={testId}
        onClick={onSelect}
        className="flex min-h-(--tap-target) w-full items-center gap-2 px-3 py-2 text-left font-medium break-words text-primary outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
      >
        <Plus aria-hidden="true" className="size-5 shrink-0" />
        <span className="min-w-0">{children}</span>
      </button>
    </li>
  );
}

/** The class of a result's button: the whole row is the tap target. */
export const RESULT_BUTTON_CLASS =
  'flex min-h-(--tap-target) w-full items-center gap-3 px-3 py-2 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset';
