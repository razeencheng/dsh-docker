import assert from 'node:assert/strict';
import test from 'node:test';
import { checkAsset, checkBrowserLogin, frontendAsset } from './web-checks.mjs';

test('selects the actual built frontend script', () => {
  assert.equal(frontendAsset('<script type="module" crossorigin src="./assets/index-abc.js"></script>'), './assets/index-abc.js');
  assert.throws(() => frontendAsset('<html></html>'), /frontend script/);
});

test('health rejects unauthorized, missing, empty, or non-JavaScript assets', async () => {
  for (const response of [
    new Response('authentication required', { status: 401 }),
    new Response('missing', { status: 404 }),
    new Response('', { headers: { 'content-type': 'text/javascript' } }),
    new Response('<html>wrong route</html>', { headers: { 'content-type': 'text/html' } }),
  ]) {
    await assert.rejects(checkAsset('http://localhost/', './assets/index.js', async () => response));
  }
  await checkAsset('http://localhost/', './assets/index.js', async () => new Response('console.log(1)', {
    headers: { 'content-type': 'text/javascript' },
  }));
});

test('browser login requires token exchange and a cookie-authenticated HTML index', async () => {
  const calls = [];
  const responses = [
    new Response('authentication required', { status: 401 }),
    new Response(null, { status: 303, headers: { location: './', 'set-cookie': 'dsh=test; HttpOnly; Path=/' } }),
    new Response('<html><script src="./assets/index.js"></script></html>', { headers: { 'content-type': 'text/html' } }),
  ];
  await checkBrowserLogin('http://localhost/?token=secret', async (url, options) => {
    calls.push({ url: String(url), options });
    return responses.shift();
  });
  assert.equal(calls[0].url, 'http://localhost/');
  assert.equal(calls[1].url, 'http://localhost/?token=secret');
  assert.equal(calls[2].options.headers.cookie, 'dsh=test');
  await assert.rejects(checkBrowserLogin('http://localhost/?token=secret', async () => new Response('open')), /401/);
});
