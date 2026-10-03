/** A name as one letter, upper case, for the initial markers: "B" for "ben". */
export function initialOf(name: string): string {
  return (Array.from(name.trim())[0] ?? '?').toLocaleUpperCase();
}
