import { describe, expect, it } from 'vitest';
import { describeUserAgent, isIosSafari } from './userAgent';

const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';
const IPHONE_CHROME =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0 Mobile/15E148 Safari/604.1';
const IPAD_DESKTOP_MODE =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15';
const HOME_SCREEN_APP =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148';
const WINDOWS_EDGE =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 Edg/140.0';
const LINUX_FIREFOX = 'Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0';

describe('describeUserAgent', () => {
  it.each([
    [IPHONE_SAFARI, 'Safari · iPhone'],
    [IPHONE_CHROME, 'Chrome · iPhone'],
    [HOME_SCREEN_APP, 'Safari · iPhone'],
    [IPAD_DESKTOP_MODE, 'Safari · Mac'],
    [WINDOWS_EDGE, 'Edge · Windows'],
    [LINUX_FIREFOX, 'Firefox · Linux'],
    ['curl/8.0', null],
    ['', null],
    [null, null],
  ])('describes %j as %j', (userAgent, expected) => {
    expect(describeUserAgent(userAgent)).toBe(expected);
  });
});

describe('isIosSafari', () => {
  it('recognises Safari on iPhone and iPad', () => {
    expect(isIosSafari(IPHONE_SAFARI)).toBe(true);
    expect(isIosSafari(IPAD_DESKTOP_MODE, 5)).toBe(true);
  });

  it('rejects other browsers and desktop Safari', () => {
    expect(isIosSafari(IPHONE_CHROME)).toBe(false);
    expect(isIosSafari(IPAD_DESKTOP_MODE, 0)).toBe(false);
    expect(isIosSafari(WINDOWS_EDGE)).toBe(false);
  });
});
