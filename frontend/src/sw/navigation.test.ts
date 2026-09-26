import { describe, expect, it } from 'vitest';
import { NAVIGATION_DENYLIST } from './navigation';

const denied = (pathAndQuery: string) => NAVIGATION_DENYLIST.some((re) => re.test(pathAndQuery));

describe('NAVIGATION_DENYLIST', () => {
  it.each(['/api', '/api/', '/api/health', '/api/lists/1?view=shopping', '/api?x=1'])(
    'leaves %s to the network',
    (path) => {
      expect(denied(path)).toBe(true);
    },
  );

  it.each(['/', '/lists', '/me?tab=1', '/apis', '/api-docs', '/meals/api'])(
    'serves %s from the app shell',
    (path) => {
      expect(denied(path)).toBe(false);
    },
  );
});
