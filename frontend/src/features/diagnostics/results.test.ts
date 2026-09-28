import { describe, expect, it } from 'vitest';
import { buildReport, maskAddresses, RESULT_IDS } from './results';

describe('buildReport', () => {
  const now = new Date('2026-09-27T18:30:00Z');

  it('lists every result in screen order, with a header to paste into the platform notes', () => {
    const report = buildReport({
      results: {
        'cookie.check': { status: 'failed', value: 'missing in standalone at …' },
        'env.displayMode': { status: 'info', value: 'standalone' },
      },
      now,
      userAgent: 'Mozilla/5.0 (iPhone)',
      url: 'https://mealmate.example.ts.net/diag',
    });
    const lines = report.split('\n');

    expect(lines.slice(0, 5)).toEqual([
      'MealMate diagnostics report',
      `Time: 2026-09-27T18:30:00.000Z (local: ${now.toString()})`,
      'User agent: Mozilla/5.0 (iPhone)',
      // The owner fills it in: the user agent may freeze the iOS version.
      'iOS version (from Settings → General → About): ____',
      // The tailnet's name is masked: the report goes into a public repository.
      'Page: https://mealmate.<tailnet>.ts.net/diag',
    ]);
    expect(lines[6]).toBe('[info] env.displayMode: standalone');
    expect(lines).toContain('[failed] cookie.check: missing in standalone at …');
    // Tests that did not run are listed too, so a gap in the notes is visible.
    expect(lines).toContain('[not run] share.after6s');
    expect(lines.filter((line) => line.startsWith('['))).toHaveLength(RESULT_IDS.length);
    expect(report.endsWith('\n')).toBe(true);
  });

  it('masks the tailnet in the results, keeping loopback visible', () => {
    const report = buildReport({
      results: {
        'server.request': {
          status: 'ok',
          value:
            'client_host=100.101.102.103 scheme=https host=mealmate.tail1234.ts.net ' +
            'x-forwarded-for=100.101.102.103 x-forwarded-proto=https',
        },
      },
      now,
      userAgent: 'Mozilla/5.0 (iPhone)',
      url: 'https://mealmate.tail1234.ts.net/diag',
    });

    expect(report).not.toMatch(/tail1234|100\.101/);
    expect(report).toContain(
      '[ok] server.request: client_host=100.x.x.x scheme=https host=mealmate.<tailnet>.ts.net ' +
        'x-forwarded-for=100.x.x.x x-forwarded-proto=https',
    );
  });
});

describe('maskAddresses', () => {
  it('masks the tailnet name and addresses in 100.64.0.0/10 and fd7a:115c:a1e0::/48 only', () => {
    expect(maskAddresses('host=MealMate.Tail-12ab.ts.net:443')).toBe(
      'host=MealMate.<tailnet>.ts.net:443',
    );
    expect(maskAddresses('100.64.0.1, 100.127.255.254, 127.0.0.1')).toBe(
      '100.x.x.x, 100.x.x.x, 127.0.0.1',
    );
    // Just outside the range, and a longer dotted number, stay as they are.
    expect(maskAddresses('100.63.1.1 100.128.1.1 192.168.1.20 1.100.64.1.1')).toBe(
      '100.63.1.1 100.128.1.1 192.168.1.20 1.100.64.1.1',
    );
    expect(maskAddresses('client_host=fd7a:115c:a1e0::1234:abcd scheme=https')).toBe(
      'client_host=fd7a:115c:a1e0:x scheme=https',
    );
    expect(maskAddresses('client_host=::1 host=localhost:8000')).toBe(
      'client_host=::1 host=localhost:8000',
    );
  });
});
