import { CookingPot } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { InitialMarker } from '@/components/InitialMarker';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useCurrentUser } from '@/features/auth/context';
import { useMealFieldMeals, type MealSearchResult } from '@/features/meals/api';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import {
  AddField,
  FieldOption,
  FieldOptions,
  RESULT_BUTTON_CLASS,
  RESULT_LIST_CLASS,
} from './AddField';
import { useAddListMeal, useRecentMeals } from './api';
import { ServingsStepper } from './ServingsStepper';
import { usePlus } from './usePlus';

type Meal = Pick<MealSearchResult, 'id' | 'name' | 'owner' | 'servings' | 'thumb_url'>;

/** The servings pop-up: the meal, the servings it opens with, and why adding failed. */
interface ServingsRequest {
  meal: Meal;
  servings: number;
  error: Error | null;
}

interface MealFieldProps {
  listId: string;
  /** Offline (SYNC-03): inactive, not hidden. */
  disabled: boolean;
  /** Shows the visible meals right away, without focusing the field ("New list", LIST-01). */
  openOnStart?: boolean;
}

/**
 * The meal field at the top of Gerichte (LIST-03, D-41). Focused while empty it lists the
 * recently used meals, then all visible meals A–Z (MEAL-09); typing lists the matching meals,
 * under "„X“ als neues Gericht". Picking a meal, or ＋ with its exact name, opens the servings
 * pop-up; ＋ without an exact match opens the meal form with the name, which adds the new meal
 * to this list and comes back here.
 */
export function MealField({ listId, disabled, openOnStart = false }: MealFieldProps) {
  const { t } = useTranslation();
  const me = useCurrentUser();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');
  const [open, setOpen] = useState(openOnStart);
  const [request, setRequest] = useState<ServingsRequest | null>(null);
  const requestRef = useRef(request);
  const [addError, setAddError] = useState<Error | null>(null);
  const add = useAddListMeal(listId);
  const typed = text.trim();
  const debounced = useDebouncedValue(typed);
  const browsing = typed === '' && open;
  // Typing, it waits for the debounced text rather than load every meal once more.
  const meals = useMealFieldMeals(debounced, {
    enabled: !disabled && (browsing || (typed !== '' && debounced !== '')),
  });
  const recent = useRecentMeals({ enabled: !disabled && browsing });
  // Only the answer for the text in the field (D-41): no earlier text's meals. When the search
  // failed, ＋ creates the meal.
  const answer =
    typed !== '' && debounced === typed
      ? (meals.data ?? (meals.error ? [] : undefined))
      : undefined;
  const dismiss = useCallback(() => setOpen(false), []);

  useEffect(() => {
    requestRef.current = request;
  });

  function choose(meal: Meal) {
    setAddError(null);
    setRequest({ meal, servings: meal.servings, error: null });
  }

  function createMeal() {
    const params = new URLSearchParams({ addToList: listId, name: typed });
    void navigate(`/meals/new?${params.toString()}`);
  }

  const plus = usePlus(typed, answer, (found) => {
    const exact = found.filter((meal) => meal.exact);
    // With one's own and the partner's "Lasagne", one's own wins.
    const own = exact.filter((meal) => meal.owner.id === me.id);
    const pick = own.length === 1 ? own[0] : exact.length === 1 ? exact[0] : undefined;
    if (pick) choose(pick);
    else if (exact.length === 0) createMeal();
    // Several of them: the results stay for a tap.
  });

  /**
   * "Hinzufügen": the pop-up closes and the emptied field gets the focus within this tap, so iOS
   * keeps the keyboard up for the next meal. Should the server refuse, the pop-up opens again.
   */
  function onAdd(servings: number) {
    if (!request) return;
    const { meal } = request;
    flushSync(() => {
      setRequest(null);
      setText('');
      setOpen(true);
    });
    inputRef.current?.focus();
    add.mutate(
      { mealId: meal.id, servings },
      {
        onError: (error) => {
          // Not over another pop-up the user opened meanwhile: then the error shows here.
          if (requestRef.current === null) setRequest({ meal, servings, error });
          else setAddError(error);
        },
      },
    );
  }

  const options = typed !== '' && (
    <FieldOptions>
      <FieldOption testId={testIds.mealFieldCreate} onSelect={createMeal}>
        {t('lists.mealField.create', { name: typed })}
      </FieldOption>
    </FieldOptions>
  );

  return (
    <>
      <AddField
        inputRef={inputRef}
        inputTestId={testIds.mealField}
        panelTestId={testIds.mealFieldPanel}
        label={t('lists.mealField.label')}
        placeholder={t('lists.mealField.placeholder')}
        value={text}
        onValueChange={(value) => {
          setText(value);
          setOpen(true);
          setAddError(null);
        }}
        disabled={disabled}
        onAdd={plus}
        // Typed text always shows its option (D-41); the empty field's list closes on a tap
        // elsewhere.
        panelOpen={open || typed !== ''}
        onOpen={() => setOpen(true)}
        onDismiss={dismiss}
        options={options}
        results={
          typed !== '' ? (
            <SearchResults answer={answer} error={meals.error} onChoose={choose} />
          ) : (
            // Not a search answer still on its way out after the field was emptied.
            <BrowseResults
              recent={recent.data}
              all={debounced === '' ? meals.data : undefined}
              error={recent.error ?? meals.error}
              pending={debounced === '' && meals.isPending}
              onChoose={choose}
            />
          )
        }
      >
        <ErrorAlert error={addError} />
      </AddField>
      <ServingsDialog
        request={request}
        onAdd={onAdd}
        onCancel={() => setRequest(null)}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          inputRef.current?.focus();
        }}
      />
    </>
  );
}

interface SearchResultsProps {
  answer: MealSearchResult[] | undefined;
  error: Error | null;
  onChoose: (meal: Meal) => void;
}

/** "Passende Gerichte" for the typed text, once they are there. */
function SearchResults({ answer, error, onChoose }: SearchResultsProps) {
  const { t } = useTranslation();

  return (
    <>
      <ErrorAlert error={error} />
      {!error && answer && answer.length === 0 && (
        <p aria-live="polite" className="text-muted-foreground">
          {t('lists.mealField.noResults')}
        </p>
      )}
      {answer && answer.length > 0 && (
        <MealSection title={t('lists.mealField.results')} meals={answer} onChoose={onChoose} />
      )}
    </>
  );
}

interface BrowseResultsProps {
  recent: Meal[] | undefined;
  all: MealSearchResult[] | undefined;
  error: Error | null;
  pending: boolean;
  onChoose: (meal: Meal) => void;
}

/** The empty field's list: "Zuletzt verwendet", then the other visible meals A–Z (MEAL-09). */
function BrowseResults({ recent, all, error, pending, onChoose }: BrowseResultsProps) {
  const { t } = useTranslation();
  const recentIds = new Set(recent?.map((meal) => meal.id));
  const rest = all?.filter((meal) => !recentIds.has(meal.id));
  const none = all?.length === 0 && recent?.length === 0;

  return (
    <>
      {recent && recent.length > 0 && (
        <MealSection title={t('lists.mealField.recent')} meals={recent} onChoose={onChoose} />
      )}
      <ErrorAlert error={error} />
      {pending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {none && <p className="text-muted-foreground">{t('lists.mealField.none')}</p>}
      {rest && rest.length > 0 && (
        <MealSection title={t('lists.mealField.all')} meals={rest} onChoose={onChoose} />
      )}
    </>
  );
}

interface MealSectionProps {
  title: string;
  meals: Meal[];
  onChoose: (meal: Meal) => void;
}

function MealSection({ title, meals, onChoose }: MealSectionProps) {
  const headingId = useId();

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-1">
      <h3
        id={headingId}
        className="text-sm font-semibold tracking-wide text-muted-foreground uppercase"
      >
        {title}
      </h3>
      <ul aria-labelledby={headingId} className={RESULT_LIST_CLASS}>
        {meals.map((meal) => (
          <MealRow key={meal.id} meal={meal} onChoose={onChoose} />
        ))}
      </ul>
    </section>
  );
}

/** A meal to pick: thumbnail, name and owner's marker, read as "Lasagne Ben". */
function MealRow({ meal, onChoose }: { meal: Meal; onChoose: (meal: Meal) => void }) {
  const nameId = useId();
  const ownerId = useId();

  return (
    <li>
      <button
        type="button"
        aria-labelledby={`${nameId} ${ownerId}`}
        onClick={() => onChoose(meal)}
        className={RESULT_BUTTON_CLASS}
      >
        {meal.thumb_url ? (
          // The name next to it says what it shows, so the thumbnail is decorative.
          <img
            src={meal.thumb_url}
            alt=""
            loading="lazy"
            className="size-11 shrink-0 rounded-lg bg-muted object-cover"
          />
        ) : (
          <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <CookingPot aria-hidden="true" className="size-6" />
          </span>
        )}
        <span id={nameId} className="min-w-0 flex-1 font-medium break-words">
          {meal.name}
        </span>
        {/* After the name, as on the Meals tab: the meal is read first, then whose it is. */}
        <InitialMarker user={meal.owner} id={ownerId} />
      </button>
    </li>
  );
}

interface ServingsDialogProps {
  request: ServingsRequest | null;
  onAdd: (servings: number) => void;
  onCancel: () => void;
  onCloseAutoFocus: (event: Event) => void;
}

/**
 * The servings pop-up (LIST-03/04, D-41): the meal's name, the compact stepper starting at the
 * meal's own servings, "Hinzufügen". A meal already on the list gets that many more servings.
 */
function ServingsDialog({ request, onAdd, onCancel, onCloseAutoFocus }: ServingsDialogProps) {
  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent
        data-testid={testIds.servingsDialog}
        aria-describedby={undefined}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        {request && <ServingsForm key={request.meal.id} request={request} onAdd={onAdd} />}
      </DialogContent>
    </Dialog>
  );
}

function ServingsForm({
  request,
  onAdd,
}: {
  request: ServingsRequest;
  onAdd: (servings: number) => void;
}) {
  const { t } = useTranslation();
  const [servings, setServings] = useState(request.servings);
  const { meal } = request;

  return (
    <>
      <DialogHeader>
        <DialogTitle>{meal.name}</DialogTitle>
      </DialogHeader>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>{t('lists.mealField.servings')}</span>
        <ServingsStepper value={servings} name={meal.name} onChange={setServings} />
      </div>
      <ErrorAlert error={request.error} />
      <DialogFooter>
        <Button onClick={() => onAdd(servings)}>{t('lists.addField.add')}</Button>
      </DialogFooter>
    </>
  );
}
