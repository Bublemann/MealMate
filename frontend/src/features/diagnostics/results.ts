/**
 * Results of the diagnostics screen (M1 platform spike, removed in M9) and the plain-text report
 * the owner pastes into docs/platform-notes.md.
 *
 * Values are technical and not translated (`standalone`, `NotAllowedError`, …), so reports from
 * a German and an English phone read the same; only the labels on screen are translated.
 */

export type ResultStatus = 'ok' | 'failed' | 'info';

/** Why a result failed, when the screen can say what to do about it. */
export type ResultHint = 'endpointsOff';

export interface ResultLine {
  status: ResultStatus;
  value: string;
  hint?: ResultHint;
}

/** Every result, in the order of the screen and the report. */
export const RESULT_IDS = [
  'env.displayMode',
  'env.colorScheme',
  'env.screen',
  'env.online',
  'env.serviceWorker',
  'env.version',
  'share.now',
  'share.after1s',
  'share.after3s',
  'share.after6s',
  'camera.track',
  'camera.barcode',
  'cookie.set',
  'cookie.check',
  'server.request',
  'storage.indexedDb',
  'storage.localStorage',
  'storage.persisted',
  'storage.persist',
  'storage.estimate',
  'offline.navigation',
] as const;

export type ResultId = (typeof RESULT_IDS)[number];
export type Results = Partial<Record<ResultId, ResultLine>>;

interface ReportInput {
  results: Results;
  now: Date;
  userAgent: string;
  url: string;
}

/** The label before `.ts.net`: the tailnet's name (`mealmate.tail1234.ts.net`). */
const TAILNET_NAME = /\b([a-z0-9-]+\.)[a-z0-9-]+\.ts\.net\b/gi;
/** Tailscale's IPv4 range 100.64.0.0/10: 100.64.x.x to 100.127.x.x. */
const TAILNET_IPV4 = /(?<![\d.])100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}(?!\.?\d)/g;
/** Tailscale's IPv6 range fd7a:115c:a1e0::/48. */
const TAILNET_IPV6 = /\bfd7a:115c:a1e0(?::[0-9a-f]{0,4})+/gi;

/**
 * Masks the tailnet's name and the tailnet addresses in `text`: the report goes into the public
 * repository. Other addresses stay, so loopback (the proxy) and a tailnet client can still be
 * told apart; the ok/info status of a result is decided on the real values before this.
 */
export function maskAddresses(text: string): string {
  return text
    .replace(TAILNET_NAME, '$1<tailnet>.ts.net')
    .replace(TAILNET_IPV4, '100.x.x.x')
    .replace(TAILNET_IPV6, 'fd7a:115c:a1e0:x');
}

/**
 * The report as plain text: a header with the time (UTC and the phone's local time), the user
 * agent, a blank for the iOS version (the user agent may freeze it, so the owner reads it in the
 * Settings) and the page, then one line per result; results not run yet are listed as such, so a
 * missing test is visible in the notes. Addresses in the page and the results are masked.
 */
export function buildReport({ results, now, userAgent, url }: ReportInput): string {
  const lines = RESULT_IDS.map((id) => {
    const result = results[id];
    return result ? `[${result.status}] ${id}: ${maskAddresses(result.value)}` : `[not run] ${id}`;
  });
  return [
    'MealMate diagnostics report',
    `Time: ${now.toISOString()} (local: ${now.toString()})`,
    `User agent: ${userAgent}`,
    'iOS version (from Settings → General → About): ____',
    `Page: ${maskAddresses(url)}`,
    '',
    ...lines,
    '',
  ].join('\n');
}

/** `yes`/`no` for a flag in a result value. */
export function yesNo(flag: boolean): string {
  return flag ? 'yes' : 'no';
}
