import { CircleAlert, RotateCcw, Search } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { isApiError } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import {
  useOffSearch,
  type IngredientSummary,
  type OffProposal,
  type OffSearchResult,
} from './api';
import { ingredientLabel } from './label';
import { formatNutrient } from './nutrients';
import { OffAttribution } from './OffAttribution';

/** The server accepts 2 to 80 characters (shorter would match almost everything). */
export const OFF_QUERY_MIN_LENGTH = 2;
export const OFF_QUERY_MAX_LENGTH = 80;

interface OffSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Starts the search field with this text (the name typed so far); nothing is sent yet. */
  initialQuery: string;
  /** Called with the chosen product's values; the dialog closes itself. */
  onChoose: (proposal: OffProposal) => void;
  /**
   * When given, a product that is already in MealMate picks that ingredient (the picker);
   * otherwise it links to it.
   */
  onPickExisting?: (ingredient: IngredientSummary) => void;
  /** Called before following a link to an ingredient that is already in MealMate. */
  onNavigate: () => void;
}

/** What was searched for and the results of the pages loaded so far. */
interface Search {
  query: string;
  page: number;
  results: OffSearchResult[];
  hasMore: boolean;
}

/**
 * The results so far with those of the next page that aren't shown yet: Open Food Facts orders
 * by popularity, which can move a product to the next page between two requests, and a row
 * twice (with the same barcode as its React key) would confuse both the user and React.
 */
function appendNew(shown: OffSearchResult[], next: OffSearchResult[]): OffSearchResult[] {
  const barcodes = new Set(shown.map((result) => result.proposal.barcode));
  return [...shown, ...next.filter((result) => !barcodes.has(result.proposal.barcode))];
}

/** Open Food Facts didn't answer in time (or is busy): try again later. */
function isOffSlow(error: unknown): boolean {
  return (
    isApiError(error) &&
    (error.code === 'off.busy' ||
      error.code === 'off.unavailable' ||
      error.code === 'client.timeout')
  );
}

/**
 * Finds a product at Open Food Facts by name, for people who have nothing to scan yet. The
 * search runs only on "Search" or Enter, never while typing (BAR-08): Open Food Facts limits how
 * often it may be asked. Choosing a result fills the ingredient form like a scanned barcode.
 */
export function OffSearchDialog({
  open,
  onOpenChange,
  initialQuery,
  onChoose,
  onPickExisting,
  onNavigate,
}: OffSearchDialogProps) {
  const { t } = useTranslation();
  const search = useOffSearch();
  const [text, setText] = useState(initialQuery.slice(0, OFF_QUERY_MAX_LENGTH));
  const [shown, setShown] = useState<Search | null>(null);
  const query = text.trim();
  const tooShort = query.length < OFF_QUERY_MIN_LENGTH;

  function run(q: string, page: number) {
    search.mutate(
      { q, page },
      {
        onSuccess: (answer) =>
          setShown((current) => ({
            query: q,
            page,
            results:
              page > 1 && current ? appendNew(current.results, answer.results) : answer.results,
            hasMore: answer.has_more,
          })),
      },
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (tooShort || search.isPending) return;
    setShown(null);
    run(query, 1);
  }

  /** The request that failed again: the first page, or the next one. */
  function retry() {
    if (search.variables) run(search.variables.q, search.variables.page);
  }

  const nothingFound = shown !== null && shown.results.length === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testIds.offSearchDialog}>
        <DialogHeader>
          <DialogTitle>{t('ingredients.offSearch.title')}</DialogTitle>
          <DialogDescription>{t('ingredients.offSearch.text')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} role="search" noValidate className="flex flex-col gap-3">
          <FormField label={t('ingredients.offSearch.label')}>
            {(control) => (
              <Input
                {...control}
                name="q"
                type="search"
                enterKeyHint="search"
                autoComplete="off"
                maxLength={OFF_QUERY_MAX_LENGTH}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            )}
          </FormField>
          <Button
            type="submit"
            className="self-start"
            data-testid={testIds.offSearchSubmit}
            disabled={tooShort || search.isPending}
          >
            <Search aria-hidden="true" />
            {t('ingredients.offSearch.submit')}
          </Button>
        </form>
        <div aria-live="polite" className="flex flex-col gap-3">
          {search.isPending && (
            <p className="text-muted-foreground">{t('ingredients.offSearch.searching')}</p>
          )}
          {nothingFound && !search.isPending && (
            <p data-testid={testIds.offSearchEmpty}>{t('ingredients.offSearch.empty')}</p>
          )}
          {isOffSlow(search.error) ? (
            <div className="flex flex-col gap-2">
              <Alert>
                <CircleAlert aria-hidden="true" />
                <AlertDescription>{t('ingredients.offSearch.slow')}</AlertDescription>
              </Alert>
              <Button variant="outline" className="self-start" onClick={retry}>
                <RotateCcw aria-hidden="true" />
                {t('common.retry')}
              </Button>
            </div>
          ) : (
            <ErrorAlert error={search.error} />
          )}
        </div>
        {shown && shown.results.length > 0 && (
          <ul
            aria-label={t('ingredients.offSearch.results')}
            className="flex flex-col divide-y rounded-lg border"
          >
            {shown.results.map((result) => (
              <li key={result.proposal.barcode}>
                <ResultEntry
                  result={result}
                  onChoose={() => {
                    onOpenChange(false);
                    if (result.in_mealmate && result.ingredient && onPickExisting) {
                      onPickExisting(result.ingredient);
                    } else onChoose(result.proposal);
                  }}
                  linkExisting={!onPickExisting}
                  onNavigate={() => {
                    onOpenChange(false);
                    onNavigate();
                  }}
                />
              </li>
            ))}
          </ul>
        )}
        {shown?.hasMore && (
          <Button
            variant="outline"
            className="self-start"
            data-testid={testIds.offSearchMore}
            disabled={search.isPending}
            onClick={() => run(shown.query, shown.page + 1)}
          >
            {t('ingredients.offSearch.more')}
          </Button>
        )}
        <OffAttribution />
      </DialogContent>
    </Dialog>
  );
}

interface ResultEntryProps {
  result: OffSearchResult;
  /** Fills the form, or picks the ingredient that is already in MealMate. */
  onChoose: () => void;
  /** An ingredient that is already in MealMate is a link to it (outside the picker). */
  linkExisting: boolean;
  onNavigate: () => void;
}

const ENTRY_CLASS =
  'flex min-h-(--tap-target) w-full flex-col items-start gap-0.5 px-3 py-2 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset';

/**
 * One product: name, brand, package size and calories, as text only (BAR-10). A product that is
 * already in MealMate picks (or opens) that ingredient instead of filling the form again.
 */
function ResultEntry({ result, onChoose, linkExisting, onNavigate }: ResultEntryProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const { proposal } = result;
  const name = proposal.name ?? t('ingredients.offSearch.unnamed');
  const kcal = proposal.nutrients.kcal;
  const details = [
    proposal.quantity_text,
    kcal !== null && kcal !== undefined && proposal.nutrition_basis
      ? t('ingredients.offSearch.kcal', {
          value: formatNutrient(t, language, 'kcal', kcal),
          unit: unitLabel(t, proposal.nutrition_basis),
        })
      : null,
  ].filter(Boolean);
  const existing = result.in_mealmate ? result.ingredient : null;

  const content = (
    <>
      <span className="font-medium break-words">{ingredientLabel(name, proposal.brand)}</span>
      {details.length > 0 && (
        <span className="text-sm text-muted-foreground">{details.join(' · ')}</span>
      )}
      {existing && <Badge variant="secondary">{t('ingredients.offSearch.inMealMate')}</Badge>}
    </>
  );

  if (existing && linkExisting) {
    return (
      <Link
        to={`/ingredients/${existing.id}`}
        data-testid={testIds.offSearchResult}
        onClick={onNavigate}
        className={ENTRY_CLASS}
      >
        {content}
      </Link>
    );
  }
  return (
    <button
      type="button"
      data-testid={testIds.offSearchResult}
      onClick={onChoose}
      className={ENTRY_CLASS}
    >
      {content}
    </button>
  );
}
