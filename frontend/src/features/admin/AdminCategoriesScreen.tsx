import { notifyManager, type UseMutationResult } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { LoadError } from '@/components/LoadError';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useCategories, type Category } from '@/features/reference/api';
import {
  notDeletedCategories,
  OTHER_KEY,
  UNCATEGORIZED_KEY,
} from '@/features/reference/categories';
import { categoryName } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { fieldErrorMessagesByPath, needsErrorAlert } from '@/i18n/errors';
import { useTabMemory } from '@/lib/tabMemory';
import { testIds } from '@/testIds';
import { AdminScreen } from './AdminScreen';
import {
  useCategoryUsage,
  useCreateCategory,
  useDeleteCategory,
  useRenameCategory,
  useReorderCategories,
  type CategoryNames,
} from './api';

type Direction = 'up' | 'down';
/** Whose dialog is open: a category's, or "New category"'s. */
type Editing = Category | 'new' | null;

/** The longest category name the server takes (REF-01). */
const NAME_MAX_LENGTH = 40;
const NAME_PATHS: ReadonlySet<string> = new Set(['names.de', 'names.en']);

/**
 * REF-01 / ADM-01: the categories in the store's walking order, moved with up/down buttons. A
 * category's name opens its dialog; "New category" adds one at the end. *Uncategorized* is only
 * moved, so its name is plain text; deleted categories aren't shown (D-30). After a delete,
 * "Show" opens the Ingredients tab filtered to *Uncategorized*, where the moved ingredients wait
 * for a new category (ING-03).
 */
export function AdminCategoriesScreen() {
  const { t } = useTranslation();
  const categories = useCategories();

  return (
    <AdminScreen title={t('admin.categories.title')} testId={testIds.screenAdminCategories}>
      <p className="text-muted-foreground">{t('admin.categories.text')}</p>
      {categories.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <LoadError error={categories.error} />
      {categories.data && <CategoryOrder categories={categories.data} />}
    </AdminScreen>
  );
}

function CategoryOrder({ categories }: { categories: Category[] }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const reorder = useReorderCategories();
  // The order on screen while moves wait for the server; null shows the saved one.
  const [moved, setMoved] = useState<string[] | null>(null);
  const order = useMemo(
    () => moved ?? notDeletedCategories(categories).map(({ id }) => id),
    [moved, categories],
  );
  // After a move the focus follows the moved category (its button may have become disabled).
  const [focus, setFocus] = useState<{ id: string; direction: Direction } | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  // The name of the category just deleted, for the message below the list.
  const [deleted, setDeleted] = useState<string | null>(null);
  // The button that opened the dialog gets the focus back when it closes; after a delete it is
  // gone, so "New category" gets it.
  const opener = useRef<HTMLElement | null>(null);
  const newButton = useRef<HTMLButtonElement>(null);
  const baseId = useId();
  const buttonId = (id: string, direction: Direction) => `${baseId}-${id}-${direction}`;
  const byId = new Map(categories.map((category) => [category.id, category]));
  // The order as text, so the focus moves when the order does, not when the server confirms it.
  const orderKey = order.join(' ');

  useEffect(() => {
    if (!focus) return;
    const ids = orderKey.split(' ');
    const index = ids.indexOf(focus.id);
    const atEdge = focus.direction === 'up' ? index === 0 : index === ids.length - 1;
    const direction = atEdge ? (focus.direction === 'up' ? 'down' : 'up') : focus.direction;
    document.getElementById(`${baseId}-${focus.id}-${direction}`)?.focus();
  }, [focus, orderKey, baseId]);

  function open(event: MouseEvent<HTMLElement>, category: Category | 'new') {
    opener.current = event.currentTarget;
    setEditing(category);
  }

  /**
   * Each tap saves the new order at once (ADM-01); the saves go out one after another (`api.ts`).
   * Only the latest tap's callback runs: once its save is in, or has failed, the screen shows the
   * cached order again, which is then the server's. That happens only after React Query has
   * passed the cache on to the screen, so an older order never flashes up in between.
   */
  function move(id: string, direction: Direction) {
    const index = order.indexOf(id);
    const other = direction === 'up' ? index - 1 : index + 1;
    if (index < 0 || other < 0 || other >= order.length) return;
    const next = [...order];
    [next[index], next[other]] = [next[other] as string, next[index] as string];
    setMoved(next);
    setFocus({ id, direction });
    reorder.mutate(next, { onSettled: () => notifyManager.schedule(() => setMoved(null)) });
  }

  return (
    <div className="flex flex-col gap-4">
      <ol
        data-testid={testIds.adminCategoryList}
        aria-label={t('admin.categories.listLabel')}
        className="flex flex-col divide-y rounded-xl border bg-card"
      >
        {order.map((id, index) => {
          const category = byId.get(id);
          if (!category) return null;
          const name = categoryName(category, language);
          return (
            // At the largest text sizes the name and the arrows wrap onto lines of their own,
            // and so do the arrows themselves (UI-01).
            <li key={id} className="flex flex-wrap items-center gap-x-2 py-1 pr-2 pl-4">
              <span
                aria-hidden="true"
                className="w-6 shrink-0 text-right text-muted-foreground tabular-nums"
              >
                {index + 1}
              </span>
              {category.key === UNCATEGORIZED_KEY ? (
                <span className="min-w-0 flex-[1_1_8rem] px-2 py-2 wrap-anywhere">{name}</span>
              ) : (
                <Button
                  variant="ghost"
                  aria-haspopup="dialog"
                  className="min-w-0 flex-[1_1_8rem] justify-start px-2 text-left wrap-anywhere"
                  onClick={(event) => open(event, category)}
                >
                  {name}
                </Button>
              )}
              <div className="ml-auto flex flex-wrap justify-end">
                <Button
                  id={buttonId(id, 'up')}
                  size="icon"
                  variant="ghost"
                  aria-label={t('admin.categories.moveUp', { name })}
                  disabled={index === 0}
                  onClick={() => move(id, 'up')}
                >
                  <ArrowUp aria-hidden="true" />
                </Button>
                <Button
                  id={buttonId(id, 'down')}
                  size="icon"
                  variant="ghost"
                  aria-label={t('admin.categories.moveDown', { name })}
                  disabled={index === order.length - 1}
                  onClick={() => move(id, 'down')}
                >
                  <ArrowDown aria-hidden="true" />
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <Button
        ref={newButton}
        data-testid={testIds.newCategory}
        variant="outline"
        aria-haspopup="dialog"
        className="max-w-full self-start wrap-anywhere"
        onClick={(event) => open(event, 'new')}
      >
        <Plus aria-hidden="true" />
        {t('admin.categories.new')}
      </Button>
      <ErrorAlert error={reorder.error} />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p role="status" className="text-sm text-muted-foreground">
          {deleted && t('admin.categories.deleted', { name: deleted })}
        </p>
        {deleted && <ShowUncategorized categories={categories} />}
      </div>
      <CategoryDialog
        editing={editing}
        onClose={() => setEditing(null)}
        onClosed={() => (opener.current?.isConnected ? opener.current : newButton.current)?.focus()}
        onDeleted={setDeleted}
      />
    </div>
  );
}

/**
 * "Show" (ING-03): the Ingredients tab with *Uncategorized* as its only category and no search,
 * so that every ingredient of a deleted category can get a new one.
 */
function ShowUncategorized({ categories }: { categories: Category[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [, remember] = useTabMemory('ingredients');
  const uncategorized = categories.find((category) => category.key === UNCATEGORIZED_KEY);
  if (!uncategorized) return null;

  return (
    <Button
      variant="outline"
      size="compact"
      className="max-w-full wrap-anywhere"
      onClick={() => {
        remember({ search: '', categoryIds: [uncategorized.id] });
        void navigate('/ingredients');
      }}
    >
      {t('admin.categories.showUncategorized')}
    </Button>
  );
}

interface CategoryDialogProps {
  editing: Editing;
  onClose: () => void;
  /** Where the focus goes once it has closed. */
  onClosed: () => void;
  /** After a delete, with the deleted category's name. */
  onDeleted: (name: string) => void;
}

/**
 * A category's German and English name, for a new category or one being renamed (REF-01), and
 * "Delete" for every category but *Other*. It fits into the space above the keyboard and scrolls
 * at the largest text sizes (UI-01).
 */
function CategoryDialog({ editing, onClose, onClosed, onDeleted }: CategoryDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={editing !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        aria-describedby={undefined}
        data-testid={testIds.categoryDialog}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          onClosed();
        }}
      >
        <DialogHeader>
          <DialogTitle>
            {editing === 'new' ? t('admin.categories.new') : t('admin.categories.editTitle')}
          </DialogTitle>
        </DialogHeader>
        {editing === 'new' && <NewCategoryForm onDone={onClose} />}
        {editing && editing !== 'new' && (
          <RenameCategoryForm
            key={editing.id}
            category={editing}
            onDone={onClose}
            onDeleted={(name) => {
              onDeleted(name);
              onClose();
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function NewCategoryForm({ onDone }: { onDone: () => void }) {
  const create = useCreateCategory();
  return <NamesForm initial={{ de: '', en: '' }} save={create} onDone={onDone} />;
}

interface RenameCategoryFormProps {
  category: Category;
  onDone: () => void;
  onDeleted: (name: string) => void;
}

function RenameCategoryForm({ category, onDone, onDeleted }: RenameCategoryFormProps) {
  const rename = useRenameCategory(category.id);
  return (
    <NamesForm
      initial={category.names}
      save={rename}
      onDone={onDone}
      // *Other* is the default of new ingredients and free-text items: it always exists.
      extraAction={
        category.key !== OTHER_KEY && <DeleteCategory category={category} onDeleted={onDeleted} />
      }
    />
  );
}

interface NamesFormProps {
  initial: CategoryNames;
  save: UseMutationResult<Category, Error, CategoryNames>;
  onDone: () => void;
  /** Another button in the footer, before "Save". */
  extraAction?: ReactNode;
}

/** Both names are required; a name another category has shows its error at its field. */
function NamesForm({ initial, save, onDone, extraAction }: NamesFormProps) {
  const { t } = useTranslation();
  const [names, setNames] = useState(initial);
  const trimmed = { de: names.de.trim(), en: names.en.trim() };
  const complete = trimmed.de !== '' && trimmed.en !== '';
  const fields = fieldErrorMessagesByPath(t, save.error);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (complete && !save.isPending) save.mutate(trimmed, { onSuccess: onDone });
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <FormField label={t('admin.categories.nameDe')} error={fields['names.de']}>
        {(control) => (
          <Input
            {...control}
            name="name-de"
            lang="de"
            autoComplete="off"
            required
            maxLength={NAME_MAX_LENGTH}
            value={names.de}
            onChange={(event) => setNames({ ...names, de: event.target.value })}
          />
        )}
      </FormField>
      <FormField label={t('admin.categories.nameEn')} error={fields['names.en']}>
        {(control) => (
          <Input
            {...control}
            name="name-en"
            lang="en"
            autoComplete="off"
            required
            maxLength={NAME_MAX_LENGTH}
            value={names.en}
            onChange={(event) => setNames({ ...names, en: event.target.value })}
          />
        )}
      </FormField>
      <ErrorAlert error={needsErrorAlert(fields, NAME_PATHS) ? save.error : null} />
      <DialogFooter>
        {extraAction}
        <Button type="submit" disabled={!complete || save.isPending}>
          {t('common.save')}
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * "Delete" and its confirmation (REF-01), which says how many ingredients move to
 * *Uncategorized* and how many free-text items on drafts to *Other*, and that lists being
 * shopped and done lists stay as they are. It stays open while the delete is sent, so an error
 * shows in it.
 */
function DeleteCategory({
  category,
  onDeleted,
}: {
  category: Category;
  onDeleted: (name: string) => void;
}) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const [confirming, setConfirming] = useState(false);
  const usage = useCategoryUsage(category.id, { enabled: confirming });
  const remove = useDeleteCategory(category.id);
  const name = categoryName(category, language);
  // *Uncategorized* and *Other*, named as the lists show them.
  const nameOf = (key: string) => {
    const found = categories.data?.find((each) => each.key === key);
    return found ? categoryName(found, language) : '';
  };

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="text-destructive"
        onClick={() => {
          remove.reset();
          setConfirming(true);
        }}
      >
        <Trash2 aria-hidden="true" />
        {t('admin.categories.delete')}
      </Button>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('admin.categories.deleteTitle', { name })}</AlertDialogTitle>
            <AlertDialogDescription>
              {usage.data
                ? [
                    t('admin.categories.deleteIngredients', {
                      count: usage.data.ingredients,
                      uncategorized: nameOf(UNCATEGORIZED_KEY),
                    }),
                    t('admin.categories.deleteItems', {
                      count: usage.data.extra_items,
                      other: nameOf(OTHER_KEY),
                    }),
                    t('admin.categories.deleteKeeps'),
                  ].join(' ')
                : t('common.loading')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorAlert error={usage.error ?? remove.error} />
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={!usage.data || remove.isPending}
              onClick={() =>
                remove.mutate(undefined, {
                  onSuccess: () => {
                    setConfirming(false);
                    onDeleted(name);
                  },
                })
              }
            >
              {t('admin.categories.deleteConfirm')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
