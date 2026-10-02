import { ListFilter } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadingState } from '@/components/LoadingState';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { testIds } from '@/testIds';

export interface FilterOption {
  id: string;
  label: string;
}

export interface FilterGroup {
  /** Names the group, e.g. "Kategorien". */
  label: string;
  /** Undefined until they have loaded: the group shows the loading placeholder, or the error. */
  options: readonly FilterOption[] | undefined;
  /** The ids of the ticked options. */
  checked: readonly string[];
  /** Whether the group is not at its default; the button counts these groups. */
  active: boolean;
  /** Called with the ticked options, in the options' order, right after each change. */
  onChange: (checked: string[]) => void;
  /** A failed load of the options or a failed change, shown in the group. */
  error?: unknown;
}

interface FilterPanelProps {
  groups: readonly FilterGroup[];
  /** "Zurücksetzen": puts every group back to its default (but keeps the search text). */
  onReset: () => void;
  /**
   * E.g. on Lists offline, where the filters don't apply (UI-02): the button is disabled and
   * counts nothing.
   */
  disabled?: boolean;
}

const FOOTER_BUTTON = 'min-w-0 flex-[1_1_8em] shrink wrap-break-word';

/**
 * The filter button of the pinned block and the panel it slides up (UI-01, D-23): groups of
 * checkboxes whose changes apply at once, "Zurücksetzen" for every group and "Fertig", which
 * closes it. The button shows how many groups are not at their default, also in its name.
 */
export function FilterPanel({ groups, onReset, disabled = false }: FilterPanelProps) {
  const { t } = useTranslation();
  const activeGroups = disabled ? 0 : groups.filter((group) => group.active).length;

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          data-testid={testIds.filterButton}
          disabled={disabled}
          aria-label={
            activeGroups ? t('filter.buttonActive', { count: activeGroups }) : t('filter.button')
          }
          className="relative rounded-xl"
        >
          <ListFilter aria-hidden="true" className="size-[1.25em]" />
          {activeGroups > 0 && (
            <span
              aria-hidden="true"
              className="absolute -top-[0.375em] -right-[0.375em] flex h-[1.5em] min-w-[1.5em] items-center justify-center rounded-full bg-primary px-[0.375em] text-[0.75em] leading-none font-semibold text-primary-foreground"
            >
              {activeGroups}
            </span>
          )}
        </Button>
      </SheetTrigger>
      <SheetContent data-testid={testIds.filterPanel} aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>{t('filter.title')}</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-5 px-5 pb-5">
          {groups.map((group) => (
            <CheckboxGroup key={group.label} group={group} />
          ))}
        </div>
        <SheetFooter>
          {/* Side by side, or one per row at large text sizes, wrapping a long word. */}
          <Button variant="outline" className={FOOTER_BUTTON} onClick={onReset}>
            {t('filter.reset')}
          </Button>
          <SheetClose asChild>
            <Button className={FOOTER_BUTTON}>{t('filter.done')}</Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

/** One group: its options in columns that become one at large text sizes, wrapping long names. */
function CheckboxGroup({ group }: { group: FilterGroup }) {
  const { label, options, checked, onChange, error } = group;

  function onToggle(id: string, on: boolean) {
    const next = new Set(checked);
    if (on) next.add(id);
    else next.delete(id);
    onChange((options ?? []).map((option) => option.id).filter((other) => next.has(other)));
  }

  return (
    <fieldset data-testid={testIds.filterGroup} className="flex min-w-0 flex-col gap-1">
      <legend className="mb-1 font-semibold">{label}</legend>
      {options ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,10em),1fr))] gap-x-4">
          {options.map((option) => (
            <Checkbox
              key={option.id}
              checked={checked.includes(option.id)}
              onChange={(event) => onToggle(option.id, event.target.checked)}
            >
              {option.label}
            </Checkbox>
          ))}
        </div>
      ) : (
        !error && <LoadingState />
      )}
      <ErrorAlert error={error} />
    </fieldset>
  );
}
