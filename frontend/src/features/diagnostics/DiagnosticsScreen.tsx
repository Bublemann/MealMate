import { ChevronLeft } from 'lucide-react';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentProps,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/features/auth/context';
import { BarcodeScanner } from '@/features/scanner/BarcodeScanner';
import type { DecodedBarcode } from '@/features/scanner/decoder';
import { copyText, shareText } from '@/lib/share';
import { testIds } from '@/testIds';
import { diagApi, errorLine, requestLine } from './api';
import {
  colorSchemeLine,
  displayMode,
  displayModeLine,
  estimateLine,
  navigationLine,
  onlineLine,
  persistedLine,
  persistLine,
  readIndexedDbMarker,
  readLocalMarker,
  screenLine,
  serviceWorkerLine,
  trackLine,
  writeIndexedDbMarker,
  writeLocalMarker,
} from './probes';
import { buildReport, type ResultId, type ResultLine, type Results } from './results';
import { shareLine, tryShare } from './share';

type RecordResult = (id: ResultId, line: ResultLine) => void;

/** The delayed share tests: a real API call plus this long a wait before `navigator.share`. */
const SHARE_DELAYS = [
  { seconds: 1, id: 'share.after1s' },
  { seconds: 3, id: 'share.after3s' },
  { seconds: 6, id: 'share.after6s' },
] as const satisfies readonly { seconds: number; id: ResultId }[];

/**
 * `/diag`: the temporary diagnostics screen of the M1 platform spike (plan § 12), removed in M9.
 * Public and outside the tab layout, so Safari can open it before any login; a Home Screen app
 * has no address bar and reaches it through Me (admins only) once signed in. Every test writes a
 * result line; the report at the end collects them as plain text for docs/platform-notes.md.
 *
 * Like every screen, it sends no request before the start-up refresh has settled (frontend
 * README, "Start-up"): the calls that load on their own wait for it, and the buttons that call
 * the server are disabled until then.
 */
export function DiagnosticsScreen() {
  const { t } = useTranslation();
  const serverReady = useAuth().status !== 'loading';
  const [state, setState] = useState<{ results: Results; at: Date }>(() => ({
    results: {},
    at: new Date(),
  }));
  const record = useCallback<RecordResult>((id, line) => {
    setState(({ results }) => ({ results: { ...results, [id]: line }, at: new Date() }));
  }, []);
  const { results } = state;

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col gap-6 px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-[max(1.5rem,env(safe-area-inset-bottom))]">
      <Link
        to="/"
        className="inline-flex min-h-(--tap-target) items-center gap-1 self-start font-medium text-primary underline-offset-4 hover:underline"
      >
        <ChevronLeft aria-hidden="true" className="size-5" />
        {t('diag.back')}
      </Link>
      <Screen title={t('diag.title')} testId={testIds.screenDiagnostics}>
        <p className="text-muted-foreground">{t('diag.intro')}</p>
        <EnvironmentSection results={results} record={record} serverReady={serverReady} />
        <ShareSection results={results} record={record} serverReady={serverReady} />
        <CameraSection results={results} record={record} />
        <CookieSection results={results} record={record} serverReady={serverReady} />
        <ServerSection results={results} record={record} serverReady={serverReady} />
        <StorageSection results={results} record={record} />
        <OfflineSection results={results} record={record} />
        <ReportSection report={buildReport({ results, now: state.at, ...pageInfo() })} />
      </Screen>
    </main>
  );
}

function pageInfo() {
  return { userAgent: navigator.userAgent, url: window.location.href };
}

interface SectionProps {
  results: Results;
  record: RecordResult;
}

interface ServerSectionProps extends SectionProps {
  /** False while the start-up refresh runs: no request may go out before it settles. */
  serverReady: boolean;
}

/** A card with a section's steps and buttons (`children`) above its result lines `ids`. */
function DiagSection({
  title,
  ids,
  results,
  children,
}: {
  title: string;
  ids: readonly ResultId[];
  results: Results;
  children?: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {children}
        <dl className="flex flex-col gap-3">
          {ids.map((id) => (
            <ResultRow key={id} id={id} result={results[id]} />
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function ResultRow({ id, result }: { id: ResultId; result: ResultLine | undefined }) {
  const { t } = useTranslation();

  return (
    <div data-testid={testIds.diagResult} className="flex flex-col gap-0.5">
      <dt className="text-sm text-muted-foreground">{t(`diag.result.${id}`)}</dt>
      <dd className="break-words">
        {result ? (
          <>
            <span
              className={result.status === 'failed' ? 'font-bold text-destructive' : 'font-bold'}
            >
              {t(`diag.status.${result.status}`)}
            </span>{' '}
            {result.value}
            {result.hint === 'endpointsOff' && (
              <span className="mt-1 block text-sm">{t('diag.endpointsOff')}</span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">{t('diag.status.notRun')}</span>
        )}
      </dd>
    </div>
  );
}

function ActionButton(props: ComponentProps<typeof Button>) {
  return <Button type="button" variant="outline" className="w-full" {...props} />;
}

/**
 * The display mode, colour scheme, screen, connection and service worker (read again when they
 * change), and the app version from the server.
 */
function EnvironmentSection({ results, record, serverReady }: ServerSectionProps) {
  const { t } = useTranslation();

  const readDevice = useCallback(() => {
    record('env.displayMode', displayModeLine());
    record('env.colorScheme', colorSchemeLine());
    record('env.screen', screenLine());
    record('env.online', onlineLine());
    void serviceWorkerLine().then((line) => record('env.serviceWorker', line));
  }, [record]);

  const readVersion = useCallback(() => {
    diagApi.version().then(
      ({ version, commit }) =>
        record('env.version', { status: 'ok', value: `${version} (${commit.slice(0, 12)})` }),
      (error: unknown) => record('env.version', errorLine(error)),
    );
  }, [record]);

  useEffect(readDevice, [readDevice]);
  useEffect(() => {
    if (serverReady) readVersion();
  }, [serverReady, readVersion]);

  // The device readings again when dark mode, the connection or the orientation changes.
  useEffect(() => {
    const dark = window.matchMedia?.('(prefers-color-scheme: dark)');
    const onChange = () => readDevice();
    dark?.addEventListener?.('change', onChange);
    window.addEventListener('online', onChange);
    window.addEventListener('offline', onChange);
    window.addEventListener('resize', onChange);
    return () => {
      dark?.removeEventListener?.('change', onChange);
      window.removeEventListener('online', onChange);
      window.removeEventListener('offline', onChange);
      window.removeEventListener('resize', onChange);
    };
  }, [readDevice]);

  return (
    <DiagSection
      title={t('diag.env.title')}
      results={results}
      ids={[
        'env.displayMode',
        'env.colorScheme',
        'env.screen',
        'env.online',
        'env.serviceWorker',
        'env.version',
      ]}
    >
      <p className="text-sm break-all text-muted-foreground">{navigator.userAgent}</p>
      <ActionButton
        disabled={!serverReady}
        onClick={() => {
          readDevice();
          readVersion();
        }}
      >
        {t('diag.env.read')}
      </ActionButton>
    </DiagSection>
  );
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Shares `text` after a real request (like creating a link before sharing it) and a wait of
 * `seconds` in all: is the share still within the tap's user activation?
 */
async function shareAfterWait(text: string, seconds: number): Promise<ResultLine> {
  const started = performance.now();
  const [fetchFailure] = await Promise.all([
    diagApi.health().then(
      () => null,
      (error: unknown) => errorLine(error).value,
    ),
    wait(seconds * 1000),
  ]);
  const line = shareLine(await tryShare(text), performance.now() - started);
  return fetchFailure ? { ...line, value: `${line.value}; health fetch: ${fetchFailure}` } : line;
}

/**
 * `navigator.share` right within the tap and after a request plus a wait: when does iOS refuse
 * it because the tap's user activation has expired (plan § 8)?
 */
function ShareSection({ results, record, serverReady }: ServerSectionProps) {
  const { t } = useTranslation();
  const [waiting, setWaiting] = useState<ResultId | null>(null);
  const text = t('diag.share.text');

  function shareNow() {
    // navigator.share runs synchronously within this tap (tryShare calls it before any await).
    void tryShare(text).then((outcome) => record('share.now', shareLine(outcome)));
  }

  async function shareLater(id: ResultId, seconds: number) {
    setWaiting(id);
    const line = await shareAfterWait(text, seconds);
    setWaiting(null);
    record(id, line);
  }

  return (
    <DiagSection
      title={t('diag.share.title')}
      results={results}
      ids={['share.now', ...SHARE_DELAYS.map(({ id }) => id)]}
    >
      <p className="text-sm text-muted-foreground">{t('diag.share.note')}</p>
      {/* Disabled while a delayed share waits: this tap would give it a fresh user activation. */}
      <ActionButton disabled={waiting !== null} onClick={shareNow}>
        {t('diag.share.now')}
      </ActionButton>
      {SHARE_DELAYS.map(({ seconds, id }) => (
        <ActionButton
          key={id}
          disabled={waiting !== null || !serverReady}
          onClick={() => void shareLater(id, seconds)}
        >
          {waiting === id
            ? t('diag.share.waiting', { seconds })
            : t('diag.share.after', { seconds })}
        </ActionButton>
      ))}
    </DiagSection>
  );
}

/**
 * The app's barcode scanner with the camera track, the frame size and the format and orientation
 * of a scanned code, for the rotated camera image of iOS 26 Home Screen apps (O-6).
 */
function CameraSection({ results, record }: SectionProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const scanner = useRef<HTMLDivElement>(null);
  // The scanner reports a camera scan twice (details, then the digits); a typed code only once.
  const scanned = useRef(false);

  const onDecoded = useCallback(
    ({ text, format, orientation }: DecodedBarcode) => {
      scanned.current = true;
      record('camera.barcode', {
        status: 'ok',
        value: `${text} (${format}, orientation ${orientation}°)`,
      });
    },
    [record],
  );
  const onBarcode = useCallback(
    (barcode: string) => {
      if (scanned.current) {
        scanned.current = false;
        return;
      }
      record('camera.barcode', { status: 'info', value: `${barcode} (typed, not scanned)` });
    },
    [record],
  );
  const onVideoTrack = useCallback(
    (track: MediaStreamTrack) => {
      // The scanner's preview: its frame size is known once frames arrive and changes (`resize`)
      // when the camera turns its image. The listener goes with the element when it closes.
      const video = scanner.current?.querySelector('video') ?? null;
      const update = () => record('camera.track', trackLine(track, video));
      update();
      video?.addEventListener('resize', update);
    },
    [record],
  );

  return (
    <DiagSection
      title={t('diag.camera.title')}
      results={results}
      ids={['camera.track', 'camera.barcode']}
    >
      <p className="text-sm text-muted-foreground">{t('diag.camera.note')}</p>
      <ActionButton aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        {open ? t('diag.camera.close') : t('diag.camera.open')}
      </ActionButton>
      {open && (
        <div ref={scanner}>
          <BarcodeScanner onBarcode={onBarcode} onDecoded={onDecoded} onVideoTrack={onVideoTrack} />
        </div>
      )}
    </DiagSection>
  );
}

/**
 * The `mm_diag` cookie set in one mode and checked in another (O-10): does a cookie set in Safari
 * reach the Home Screen app, and does it survive a force-quit and a restart?
 */
function CookieSection({ results, record, serverReady }: ServerSectionProps) {
  const { t } = useTranslation();
  const mode = displayMode();

  async function setCookie() {
    try {
      await diagApi.setCookie();
      record('cookie.set', { status: 'ok', value: `set in ${mode} at ${stamp()}` });
    } catch (error) {
      record('cookie.set', errorLine(error));
    }
  }

  async function checkCookie() {
    try {
      const { present } = await diagApi.checkCookie();
      record('cookie.check', {
        status: present ? 'ok' : 'failed',
        value: `${present ? 'present' : 'missing'} in ${mode} at ${stamp()}`,
      });
    } catch (error) {
      record('cookie.check', errorLine(error));
    }
  }

  return (
    <DiagSection
      title={t('diag.cookie.title')}
      results={results}
      ids={['cookie.set', 'cookie.check']}
    >
      <p className="text-sm text-muted-foreground">{t('diag.cookie.steps')}</p>
      <p>{t('diag.cookie.mode', { mode })}</p>
      <ActionButton disabled={!serverReady} onClick={() => void setCookie()}>
        {t('diag.cookie.set')}
      </ActionButton>
      <ActionButton disabled={!serverReady} onClick={() => void checkCookie()}>
        {t('diag.cookie.check')}
      </ActionButton>
    </DiagSection>
  );
}

function stamp(): string {
  return new Date().toISOString();
}

/** The request as the server sees it behind `tailscale serve`: address, scheme, headers (O-3). */
function ServerSection({ results, record, serverReady }: ServerSectionProps) {
  const { t } = useTranslation();

  const load = useCallback(() => {
    diagApi.request().then(
      (info) => record('server.request', requestLine(info)),
      (error: unknown) => record('server.request', errorLine(error)),
    );
  }, [record]);

  useEffect(() => {
    if (serverReady) load();
  }, [serverReady, load]);

  return (
    <DiagSection title={t('diag.server.title')} results={results} ids={['server.request']}>
      <p className="text-sm text-muted-foreground">{t('diag.server.note')}</p>
      <ActionButton disabled={!serverReady} onClick={load}>
        {t('diag.server.load')}
      </ActionButton>
    </DiagSection>
  );
}

/** Markers in IndexedDB and localStorage that must survive a restart, and the storage quota. */
function StorageSection({ results, record }: SectionProps) {
  const { t } = useTranslation();

  const read = useCallback(() => {
    void readIndexedDbMarker().then((line) => record('storage.indexedDb', line));
    record('storage.localStorage', readLocalMarker());
    void persistedLine().then((line) => record('storage.persisted', line));
    void estimateLine().then((line) => record('storage.estimate', line));
  }, [record]);

  useEffect(read, [read]);

  function writeMarkers() {
    const now = new Date();
    void writeIndexedDbMarker(now).then((line) => record('storage.indexedDb', line));
    record('storage.localStorage', writeLocalMarker(now));
  }

  function persist() {
    void persistLine().then((line) => {
      record('storage.persist', line);
      read();
    });
  }

  return (
    <DiagSection
      title={t('diag.storage.title')}
      results={results}
      ids={[
        'storage.indexedDb',
        'storage.localStorage',
        'storage.persisted',
        'storage.persist',
        'storage.estimate',
      ]}
    >
      <p className="text-sm text-muted-foreground">{t('diag.storage.note')}</p>
      <ActionButton onClick={writeMarkers}>{t('diag.storage.write')}</ActionButton>
      <ActionButton onClick={persist}>{t('diag.storage.persist')}</ActionButton>
    </DiagSection>
  );
}

/**
 * The steps for the offline and lie-fi starts, and whether the service worker served the
 * document of this app start. The Home Screen app starts at `/`, so the owner opens this screen
 * through Me after such a start.
 */
function OfflineSection({ results, record }: SectionProps) {
  const { t } = useTranslation();

  useEffect(() => record('offline.navigation', navigationLine()), [record]);

  return (
    <DiagSection title={t('diag.offline.title')} results={results} ids={['offline.navigation']}>
      <p className="text-sm text-muted-foreground">{t('diag.offline.steps')}</p>
      <p className="text-sm text-muted-foreground">{t('diag.offline.lieFi')}</p>
    </DiagSection>
  );
}

/** The report to copy or share into docs/platform-notes.md, with the addresses masked. */
function ReportSection({ report }: { report: string }) {
  const { t } = useTranslation();
  const [message, setMessage] = useState<string | null>(null);

  function copy() {
    // The clipboard write starts within the tap, like navigator.share.
    void copyText(report).then((result) =>
      setMessage(result === 'copied' ? t('diag.report.copied') : t('diag.report.copyFailed')),
    );
  }

  function share() {
    void shareText(report).then((result) => {
      if (result === 'copied') setMessage(t('diag.report.copied'));
      if (result === 'failed') setMessage(t('diag.report.copyFailed'));
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('diag.report.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Button type="button" className="w-full" onClick={copy}>
          {t('diag.report.copy')}
        </Button>
        <ActionButton onClick={share}>{t('diag.report.share')}</ActionButton>
        <p role="status" className="min-h-6 text-sm">
          {message}
        </p>
        <p className="text-sm text-muted-foreground">{t('diag.report.masked')}</p>
        <pre
          data-testid={testIds.diagReport}
          className="text-xs break-all whitespace-pre-wrap text-muted-foreground"
        >
          {report}
        </pre>
      </CardContent>
    </Card>
  );
}
