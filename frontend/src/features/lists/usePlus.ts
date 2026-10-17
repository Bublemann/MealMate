import { useEffect, useRef } from 'react';

/**
 * ＋ of an add field (D-41): `decide` gets the results answered for exactly the text in the
 * field. While they are still loading, ＋ waits for them; typing on drops the waiting ＋.
 *
 * @param typed The trimmed text in the field.
 * @param answer The results for `typed`, undefined while they load (never an earlier text's).
 * @returns What ＋ (or Enter) calls.
 */
export function usePlus<T>(
  typed: string,
  answer: T | undefined,
  decide: (answer: T) => void,
): () => void {
  const waiting = useRef<string | null>(null);
  const latest = useRef(decide);

  useEffect(() => {
    latest.current = decide;
  });

  useEffect(() => {
    if (waiting.current === null) return;
    if (waiting.current !== typed) {
      waiting.current = null;
    } else if (answer !== undefined) {
      waiting.current = null;
      latest.current(answer);
    }
  }, [typed, answer]);

  return () => {
    if (answer !== undefined) decide(answer);
    else waiting.current = typed;
  };
}
