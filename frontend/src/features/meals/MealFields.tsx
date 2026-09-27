import { Camera, Minus, Plus, Trash2 } from 'lucide-react';
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { RemovableChip } from '@/components/ui/chip';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { useCreateCuisine, useCuisines, useTags } from '@/features/reference/api';
import { cuisineName } from '@/features/reference/labels';
import { fieldErrorMessages } from '@/i18n/errors';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import {
  MAX_SERVINGS,
  MAX_TAG_LENGTH,
  MAX_TAGS,
  MIN_SERVINGS,
  parseServings,
  withTag,
} from './form';
import { PHOTO_ACCEPT } from './photo';

interface ServingsFieldProps {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}

/** A number field with − and + buttons, 1–99 (MEAL-02). */
export function ServingsField({ value, onChange, error }: ServingsFieldProps) {
  const { t } = useTranslation();
  const current = parseServings(value);

  function step(offset: -1 | 1) {
    const next = Math.min(MAX_SERVINGS, Math.max(MIN_SERVINGS, (current ?? MIN_SERVINGS) + offset));
    onChange(String(next));
  }

  return (
    <FormField label={t('meals.field.servings')} hint={t('meals.field.servingsHint')} error={error}>
      {(control) => (
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label={t('meals.field.servingsLess')}
            disabled={current !== null && current <= MIN_SERVINGS}
            onClick={() => step(-1)}
          >
            <Minus aria-hidden="true" />
          </Button>
          <Input
            {...control}
            name="servings"
            inputMode="numeric"
            autoComplete="off"
            maxLength={2}
            className="w-20 text-center"
            value={value}
            onChange={(event) => onChange(event.target.value.replace(/\D/g, ''))}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label={t('meals.field.servingsMore')}
            disabled={current !== null && current >= MAX_SERVINGS}
            onClick={() => step(1)}
          >
            <Plus aria-hidden="true" />
          </Button>
        </div>
      )}
    </FormField>
  );
}

interface CuisineFieldProps {
  value: string;
  onChange: (id: string) => void;
  error?: string;
}

/** Seeded (translated) and user-added cuisines; a missing one can be added right here (REF-03). */
export function CuisineField({ value, onChange, error }: CuisineFieldProps) {
  const { t } = useTranslation();
  const cuisines = useCuisines();
  const create = useCreateCuisine();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const newError = fieldErrorMessages(t, create.error).name;

  function add() {
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate(trimmed, {
      onSuccess: (cuisine) => {
        onChange(cuisine.id);
        setAdding(false);
        setName('');
      },
    });
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'Enter') return;
    // Enter adds the cuisine instead of saving the whole meal.
    event.preventDefault();
    add();
  }

  return (
    <div className="flex flex-col gap-2">
      <FormField label={t('meals.field.cuisine')} error={error}>
        {(control) => (
          <NativeSelect
            {...control}
            name="cuisine_id"
            value={value}
            onChange={(event) => onChange(event.target.value)}
          >
            <NativeSelectOption value="">{t('meals.field.cuisineNone')}</NativeSelectOption>
            {cuisines.data?.map((cuisine) => (
              <NativeSelectOption key={cuisine.id} value={cuisine.id}>
                {cuisineName(t, cuisine)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        )}
      </FormField>
      <ErrorAlert error={cuisines.error} />
      {adding ? (
        <div className="flex items-end gap-2">
          <div className="min-w-0 flex-1">
            <FormField label={t('meals.field.cuisineNew')} error={newError}>
              {(control) => (
                <Input
                  {...control}
                  autoComplete="off"
                  maxLength={40}
                  // Opened by a tap on "Add cuisine…", so the focus moves on with the user.
                  // eslint-disable-next-line jsx-a11y/no-autofocus
                  autoFocus
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  onKeyDown={onKeyDown}
                />
              )}
            </FormField>
          </div>
          <Button
            type="button"
            variant="outline"
            disabled={create.isPending || name.trim() === ''}
            onClick={add}
            className={newError ? 'mb-7' : undefined}
          >
            {t('meals.field.cuisineCreate')}
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          variant="link"
          size="compact"
          className="self-start px-0"
          onClick={() => setAdding(true)}
        >
          <Plus aria-hidden="true" />
          {t('meals.field.cuisineAdd')}
        </Button>
      )}
      {!newError && <ErrorAlert error={create.error} />}
    </div>
  );
}

interface TagsFieldProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  error?: string;
}

/** Up to 10 tags as removable chips, with suggestions from the tags others used (REF-04). */
export function TagsField({ tags, onChange, error }: TagsFieldProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const debounced = useDebouncedValue(text.trim());
  const suggestions = useTags(debounced);
  const full = tags.length >= MAX_TAGS;
  const taken = new Set(tags.map((tag) => tag.toLocaleLowerCase()));
  const offered =
    debounced === ''
      ? []
      : (suggestions.data ?? [])
          .filter((tag) => !taken.has(tag.name.toLocaleLowerCase()))
          .slice(0, 8);

  function add(tag: string) {
    onChange(withTag(tags, tag));
    setText('');
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'Enter') return;
    // Enter adds the tag instead of saving the whole meal.
    event.preventDefault();
    add(text);
  }

  return (
    <div className="flex flex-col gap-2">
      <FormField
        label={t('meals.field.tags')}
        hint={full ? t('meals.field.tagsFull') : t('meals.field.tagsHint')}
        error={error}
      >
        {(control) => (
          <div className="flex gap-2">
            <Input
              {...control}
              autoComplete="off"
              enterKeyHint="done"
              maxLength={MAX_TAG_LENGTH}
              disabled={full}
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={onKeyDown}
            />
            <Button
              type="button"
              variant="outline"
              disabled={full || text.trim() === ''}
              onClick={() => add(text)}
            >
              {t('meals.field.tagAdd')}
            </Button>
          </div>
        )}
      </FormField>
      {offered.length > 0 && !full && (
        <ul aria-label={t('meals.field.tagSuggestions')} className="flex flex-wrap gap-2">
          {offered.map((tag) => (
            <li key={tag.id}>
              <Button
                type="button"
                variant="outline"
                size="compact"
                aria-label={t('meals.field.tagAddNamed', { name: tag.name })}
                onClick={() => add(tag.name)}
              >
                <Plus aria-hidden="true" />
                {tag.name}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {tags.length > 0 && (
        <ul aria-label={t('meals.field.tagList')} className="flex flex-wrap gap-2">
          {tags.map((tag) => (
            <li key={tag.toLocaleLowerCase()} className="max-w-full">
              <RemovableChip
                removeLabel={t('meals.field.tagRemove', { name: tag })}
                onRemove={() => onChange(tags.filter((other) => other !== tag))}
              >
                {tag}
              </RemovableChip>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** What happens to the photo when the form is saved. */
export type PhotoChange = { kind: 'keep' } | { kind: 'new'; file: File } | { kind: 'remove' };

interface PhotoFieldProps {
  /** The meal's current photo (signed URL), if any. */
  current: string | null;
  mealName: string;
  change: PhotoChange;
  onChange: (change: PhotoChange) => void;
}

/** One photo from the camera or the library, with a preview (MEAL-04). */
export function PhotoField({ current, mealName, change, onChange }: PhotoFieldProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [preview, setPreview] = useState<string | null>(null);

  // The preview URL belongs to this field: freed when it changes or the form closes.
  useEffect(() => {
    if (!preview) return;
    return () => URL.revokeObjectURL(preview);
  }, [preview]);

  function onFileChange(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    onChange({ kind: 'new', file });
    // The same file can be chosen again after removing it.
    if (inputRef.current) inputRef.current.value = '';
  }

  function remove() {
    setPreview(null);
    onChange(current ? { kind: 'remove' } : { kind: 'keep' });
  }

  const shown = change.kind === 'new' ? preview : change.kind === 'keep' ? current : null;

  return (
    <fieldset className="flex flex-col gap-3" aria-describedby={hintId}>
      <legend className="mb-2 text-sm leading-none font-medium">{t('meals.field.photo')}</legend>
      {shown && (
        <img
          src={shown}
          alt={mealName.trim() || t('meals.field.photoPreview')}
          className="aspect-[4/3] w-full max-w-sm rounded-lg bg-muted object-cover"
        />
      )}
      <input
        ref={inputRef}
        type="file"
        accept={PHOTO_ACCEPT}
        hidden
        data-testid={testIds.mealPhotoInput}
        onChange={(event) => onFileChange(event.target.files)}
      />
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => inputRef.current?.click()}>
          <Camera aria-hidden="true" />
          {shown ? t('meals.field.photoChange') : t('meals.field.photoChoose')}
        </Button>
        {shown && (
          <Button type="button" variant="outline" onClick={remove}>
            <Trash2 aria-hidden="true" />
            {t('meals.field.photoRemove')}
          </Button>
        )}
      </div>
      <p id={hintId} className="text-sm text-muted-foreground">
        {t('meals.field.photoHint')}
      </p>
    </fieldset>
  );
}
