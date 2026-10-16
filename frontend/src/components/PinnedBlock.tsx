import { Plus, Search } from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { testIds, type TestId } from '@/testIds';
import { useScreenHeading } from './screenHeading';

interface SearchFieldProps {
  /** The field's name, for screen readers only: the magnifier shows what it is (A11Y-01). */
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  testId: TestId;
}

interface NewTileProps {
  /** "Neue Zutat", or "„Quitten“ anlegen" while a search text is present. */
  label: string;
  onClick: () => void;
  /** E.g. "Neue Liste" offline: creating it needs the server (UI-02). */
  disabled?: boolean;
  testId: TestId;
}

interface PinnedBlockProps {
  /** Lists has no search field. */
  search?: SearchFieldProps;
  /** The filter button (at least 44 pt): next to the search field, or else next to the tile. */
  filter?: ReactNode;
  newTile: NewTileProps;
}

/**
 * The top of the Lists, Meals and Ingredients tabs (UI-01): the tab's headline (D-44), search,
 * filter and the green "Neu…" tile, on a frosted surface that stays below the status bar while
 * the content scrolls under it. The tab renders it at once, whether it is still loading, empty or
 * filled (UI-03), and shows its state below it. At the largest text sizes it stops growing before
 * it crowds out the content (the `pinned` utility, D-29), and its sizes are in em of its text;
 * the headline and the tile wrap. It goes inside a `<Screen variant="pinned">`, whose headline it
 * shows.
 */
export function PinnedBlock({ search, filter, newTile }: PinnedBlockProps) {
  const heading = useScreenHeading();

  return (
    // Spans the content column across the Layout's px-4, so nothing shows beside it.
    <div
      data-testid={testIds.pinnedBlock}
      className="frosted pinned sticky top-[env(safe-area-inset-top)] z-10 -mx-4 flex flex-col gap-[0.75em] border-b border-frosted-border px-4 py-[0.75em]"
    >
      {/* As large as a detail screen's title, but in em, so the block's cap holds it too, and
          no larger than 42 px (1.5 times the capped text), so the block leaves room for the
          content at the largest text sizes. A long one wraps, hyphenated in the UI language
          (<html lang>). */}
      <h1
        id={heading.id}
        className="text-[min(1.875em,42px)] leading-[1.2] font-bold tracking-tight hyphens-auto wrap-anywhere"
      >
        {heading.title}
      </h1>
      {search && (
        // The filter button stays beside the search field, which gives way at large text sizes.
        <div className="flex gap-[0.5em]">
          <SearchField {...search} />
          {filter}
        </div>
      )}
      <div className="flex flex-wrap gap-[0.5em]">
        <NewTile {...newTile} />
        {!search && filter}
      </div>
    </div>
  );
}

function SearchField({ label, placeholder, value, onChange, testId }: SearchFieldProps) {
  const id = useId();

  return (
    <div className="relative min-w-0 flex-[1_1_12em]">
      <Label htmlFor={id} className="sr-only">
        {label}
      </Label>
      <Search
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 left-[0.75em] size-[1.25em] -translate-y-1/2 text-muted-foreground"
      />
      <Input
        id={id}
        type="search"
        enterKeyHint="search"
        autoComplete="off"
        data-testid={testId}
        placeholder={placeholder}
        className="py-[0.5em] pr-[0.75em] pl-[2.5em]"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

/**
 * Shaped like a row of the tab's list, in the primary green; a long name wraps. Its lines sit
 * closer than the button text's usual 1.5, with the difference in the padding, so a one-line tile
 * keeps its height and a long name takes less of the screen (UI-01).
 */
function NewTile({ label, onClick, disabled = false, testId }: NewTileProps) {
  return (
    <Button
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      className="min-w-0 flex-[1_1_12em] shrink justify-start gap-[0.75em] rounded-xl px-[1em] py-[0.875em] text-left text-[1em]"
    >
      <Plus aria-hidden="true" className="size-[1.25em]" />
      <span className="min-w-0 leading-[1.25] wrap-anywhere">{label}</span>
    </Button>
  );
}
