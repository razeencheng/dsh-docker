export function frontendAsset(html) {
  const source = html.match(/<script\b[^>]*\bsrc=["']([^"']+\.js(?:\?[^"']*)?)["']/i)?.[1];
  if (!source) throw new Error('Built index has no frontend script');
  return source;
}

export async function checkAsset(base, asset, request = fetch) {
  const url = new URL(asset, base);
  if (url.origin !== new URL(base).origin) throw new Error('Frontend script is outside the local server');
  const response = await request(url, { signal: AbortSignal.timeout(4000) });
  if (response.status !== 200) throw new Error(`Frontend script returned HTTP ${response.status}`);
  if (!/^(text|application)\/javascript\b/i.test(response.headers.get('content-type') ?? '')) {
    throw new Error('Frontend script returned an unexpected content type');
  }
  const reader = response.body?.getReader();
  const first = await reader?.read();
  await reader?.cancel();
  if (!first?.value?.length) throw new Error('Frontend script is empty');
}

export async function checkBrowserLogin(launchUrl, request = fetch) {
  const login = new URL(launchUrl);
  if (!login.searchParams.get('token')) throw new Error('Web launch URL has no authentication token');
  const index = new URL('./', login);
  const options = () => ({ redirect: 'manual', signal: AbortSignal.timeout(4000) });
  const anonymous = await request(index, options());
  if (anonymous.status !== 401) throw new Error(`Unauthenticated index must return 401, got ${anonymous.status}`);
  await anonymous.body?.cancel();
  const exchange = await request(login, options());
  if (exchange.status !== 303) throw new Error(`Launch token exchange must return 303, got ${exchange.status}`);
  const cookie = exchange.headers.get('set-cookie')?.split(';')[0];
  if (!cookie || exchange.headers.get('location') !== './') throw new Error('Launch token exchange did not issue a session cookie and clean redirect');
  await exchange.body?.cancel();
  const authenticated = await request(index, { ...options(), headers: { cookie } });
  if (authenticated.status !== 200) throw new Error(`Authenticated index returned HTTP ${authenticated.status}`);
  if (!/^text\/html\b/i.test(authenticated.headers.get('content-type') ?? '')) throw new Error('Authenticated index did not return HTML');
  frontendAsset(await authenticated.text());
}
