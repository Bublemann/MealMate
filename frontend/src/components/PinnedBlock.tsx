import { Plus, Search } from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { TestId } from '@/testIds';

interface PinnedSearch {
  /** The field's name, for screen readers only: the magnifier shows what it is (A11Y-01). */
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  testId: TestId;
}

interface NewTile {
  /** "Neue Zutat", or "„Quitten“ anlegen" while a search text is present. */
  label: string;
  onClick: () => void;
  testId: TestId;
}

interface PinnedBlockProps {
  /** Lists has no search field. */
  search?: PinnedSearch;
  /** The filter button (at least 44 pt): next to the search field, or else next to the tile. */
  filter?: ReactNode;
  newTile: NewTile;
}

/**
 * The top of the Lists, Meals and Ingredients tabs (UI-01): search, filter and the green "Neu…"
 * tile, on a frosted surface that stays below the status bar while the content scrolls under it.
 * The tab renders it at once, whether it is still loading, empty or filled (UI-03), and shows its
 * state below it. At the largest text sizes it stops growing before it crowds out the content
 * (--pinned-* in tokens.css): its controls take their text size and tap target from there, and
 * its spacing is in em; the tile wraps a long name.
 */
export function PinnedBlock({ search, filter, newTile }: PinnedBlockProps) {
  return (
    // Spans the content column across the Layout's px-4, so nothing shows beside it.
    <div className="frosted sticky top-[env(safe-area-inset-top)] z-10 -mx-4 flex flex-col gap-[0.75em] border-b border-frosted-border px-4 py-[0.75em] text-(length:--pinned-font-size) [--control-font-size:var(--pinned-font-size)] [--tap-target:var(--pinned-tap-target)]">
      {search && (
        <div className="flex flex-wrap gap-[0.5em]">
          <SearchField {...search} />
          {filter}
        </div>
      )}
      <div className="flex flex-wrap gap-[0.5em]">
        <Tile {...newTile} />
        {!search && filter}
      </div>
    </div>
  );
}

function SearchField({ label, placeholder, value, onChange, testId }: PinnedSearch) {
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

/** Shaped like a row of the tab's list, in the primary green; a long name wraps. */
function Tile({ label, onClick, testId }: NewTile) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className="flex min-h-(--tap-target) min-w-0 flex-[1_1_12em] items-center gap-[0.75em] rounded-xl bg-primary px-[1em] py-[0.75em] text-left font-medium text-primary-foreground transition-colors outline-none hover:bg-primary/90 focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <Plus aria-hidden="true" className="size-[1.25em] shrink-0" />
      <span className="min-w-0 wrap-anywhere">{label}</span>
    </button>
  );
}
