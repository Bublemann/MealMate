/**
 * An empty tab (UI-03): one muted line below the pinned block, with no icon, heading or button,
 * because the pinned block's "Neu…" tile is the action.
 */
export function EmptyLine({ text }: { text: string }) {
  return <p className="text-muted-foreground">{text}</p>;
}
