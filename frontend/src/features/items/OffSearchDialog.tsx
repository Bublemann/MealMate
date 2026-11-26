import { CircleAlert, RotateCcw, Search } from 'lucide-react';
import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { isApiError } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { LoadingState } from '@/components/LoadingState';
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
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import { useOffSearch, type ItemSummary, type OffProposal, type OffSearchResult } from './api';
import { itemLabel } from './label';
import { formatNutrient } from './nutrients';
import { OffAttribution } from './OffAttribution';

/** The server accepts 2 to 80 characters (shorter would match almost everything). */
export const OFF_QUERY_MIN_LENGTH = 2;
export const OFF_QUERY_MAX_LENGTH = 80;

interface OffSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Starts the search field with this text (the name typed so far) and searches for it at once,
   * if it is long enough: opening the dialog is the explicit action (BAR-08, BAR-11).
   */
  initialQuery: string;
  /** Called with the chosen product's values; the dialog closes itself. */
  onChoose: (proposal: OffProposal) => void;
  /**
   * When given, a product that is already in MealMate picks that item (the picker);
   * otherwise it links to it.
   */
  onPickExisting?: (item: ItemSummary) => void;
  /**
   * Whether the picker may take an item that is already in MealMate (default: any). A supply
   * can't be a meal's ingredient (D-55), so its product can't be chosen there.
   */
  takes?: (item: ItemSummary) => boolean;
  /** Called before following a link to an item that is already in MealMate. */
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
 * Finds a product at Open Food Facts by name, for people who have nothing to scan yet. It
 * searches for the name it opens with at once; after that only on "Search" or Enter, never while
 * typing (BAR-08): Open Food Facts limits how often it may be asked. Choosing a result fills the
 * item form like a scanned barcode.
 */
export function OffSearchDialog({
  open,
  onOpenChange,
  initialQuery,
  onChoose,
  onPickExisting,
  takes = () => true,
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

  const searchInitialQuery = useEffectEvent(() => {
    if (!tooShort) run(query, 1);
  });
  // Once, also where development mode runs effects twice: Open Food Facts limits how often it
  // may be asked (BAR-08).
  const searchedInitialQuery = useRef(false);
  useEffect(() => {
    if (searchedInitialQuery.current) return;
    searchedInitialQuery.current = true;
    searchInitialQuery();
  }, []);

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
          <DialogTitle>{t('items.offSearch.title')}</DialogTitle>
          <DialogDescription>{t('items.offSearch.text')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} role="search" noValidate className="flex flex-col gap-3">
          <FormField label={t('items.offSearch.label')}>
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
            {t('items.offSearch.submit')}
          </Button>
        </form>
        <div aria-live="polite" className="flex flex-col gap-3">
          {/* A further page shows its spinner in "Weitere Ergebnisse". */}
          {search.isPending && search.variables.page === 1 && (
            <LoadingState label={t('items.offSearch.searching')} />
          )}
          {nothingFound && !search.isPending && (
            <p data-testid={testIds.offSearchEmpty}>{t('items.offSearch.empty')}</p>
          )}
          {isOffSlow(search.error) ? (
            <div className="flex flex-col gap-2">
              <Alert>
                <CircleAlert aria-hidden="true" />
                <AlertDescription>{t('items.offSearch.slow')}</AlertDescription>
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
            aria-label={t('items.offSearch.results')}
            className="flex flex-col divide-y rounded-lg border"
          >
            {shown.results.map((result) => (
              <li key={result.proposal.barcode}>
                <ResultEntry
                  result={result}
                  onChoose={() => {
                    onOpenChange(false);
                    if (result.in_mealmate && result.item && onPickExisting) {
                      onPickExisting(result.item);
                    } else onChoose(result.proposal);
                  }}
                  linkExisting={!onPickExisting}
                  unavailable={
                    !!onPickExisting && result.in_mealmate && !!result.item && !takes(result.item)
                  }
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
            pending={search.isPending && search.variables.page > 1}
            disabled={search.isPending}
            onClick={() => run(shown.query, shown.page + 1)}
          >
            {t('items.offSearch.more')}
          </Button>
        )}
        <OffAttribution />
      </DialogContent>
    </Dialog>
  );
}

interface ResultEntryProps {
  result: OffSearchResult;
  /** Fills the form, or picks the item that is already in MealMate. */
  onChoose: () => void;
  /** An item that is already in MealMate is a link to it (outside the picker). */
  linkExisting: boolean;
  /** The item that is already in MealMate can't be taken here (a supply for a meal, D-55). */
  unavailable: boolean;
  onNavigate: () => void;
}

const ENTRY_CLASS =
  'flex min-h-(--tap-target) w-full flex-col items-start gap-0.5 px-3 py-2 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset';

/**
 * One product: name, brand and calories, as text only (BAR-10). A product that is
 * already in MealMate picks (or opens) that item instead of filling the form again.
 */
function ResultEntry({
  result,
  onChoose,
  linkExisting,
  unavailable,
  onNavigate,
}: ResultEntryProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const { proposal } = result;
  const name = proposal.name ?? t('items.offSearch.unnamed');
  const kcal = proposal.nutrients.kcal;
  const calories =
    kcal !== null && kcal !== undefined && proposal.nutrition_basis
      ? t('items.offSearch.kcal', {
          value: formatNutrient(t, language, 'kcal', kcal),
          unit: unitLabel(t, proposal.nutrition_basis),
        })
      : null;
  const existing = result.in_mealmate ? result.item : null;

  const content = (
    <>
      <span className="font-medium break-words">{itemLabel(name, proposal.brand)}</span>
      {calories && <span className="text-sm text-muted-foreground">{calories}</span>}
      {existing && <Badge variant="secondary">{t('items.offSearch.inMealMate')}</Badge>}
      {unavailable && existing && (
        <span className="text-sm text-muted-foreground">
          {t('items.kind.notForMeals', { name: itemLabel(existing.name, existing.brand) })}
        </span>
      )}
    </>
  );

  if (existing && linkExisting) {
    return (
      <Link
        to={`/items/${existing.id}`}
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
      disabled={unavailable}
      onClick={onChoose}
      className={cn(ENTRY_CLASS, 'disabled:cursor-not-allowed disabled:opacity-60')}
    >
      {content}
    </button>
  );
}
