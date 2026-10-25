import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const entrypoint = fileURLToPath(new URL('./entrypoint.sh', import.meta.url));
const quote = value => `'${value.replaceAll("'", "'\\''")}'`;

// Exercise the real shell entrypoint; capture its final argv at the CLI boundary.
function invocation(args) {
  const root = mkdtempSync(join(tmpdir(), 'dsh-entrypoint-'));
  try {
    const bin = join(root, 'bin');
    mkdirSync(bin);
    const capture = join(root, 'capture.mjs');
    writeFileSync(capture, 'console.log(JSON.stringify(process.argv.slice(2)));\n');
    writeFileSync(join(bin, 'dsh'), `#!/bin/sh\nexec ${quote(process.execPath)} ${quote(capture)} "$@"\n`, { mode: 0o755 });
    writeFileSync(join(bin, 'node'), '#!/bin/sh\nprintf "%s\\n" "172.18.0.2"\n', { mode: 0o755 });
    const result = spawnSync('/bin/sh', [entrypoint, ...args], {
      encoding: 'utf8',
      env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, HOME: join(root, 'home'), DSH_HOME: join(root, 'state'), PORT: '3080' },
    });
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(result.stdout);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test('default web invocation keeps container listener defaults', () => {
  assert.deepEqual(invocation(['web']), ['web', '--host', '172.18.0.2', '--port', '3080', '--no-open']);
});

test('launcher patch overlays precede the Web argument boundary', () => {
  const args = invocation(['web', '--patch', '/config/extra config.yml', '--patch=/config/second.yml', '--trusted-host', 'dsh.razeen.cn']);
  const boundary = Math.min(args.indexOf('--host'), args.indexOf('--trusted-host'));
  assert.ok(args.indexOf('--patch') < boundary, `Launcher patch was forwarded to the Web parser: ${JSON.stringify(args)}`);
  assert.ok(args.indexOf('--patch=/config/second.yml') < boundary);
  assert.equal(args[args.indexOf('--patch') + 1], '/config/extra config.yml');
});

test('explicit Web host and port still override container defaults', () => {
  const args = invocation(['web', '--host=127.0.0.2', '--port', '8090']);
  const values = {};
  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--host' || args[i] === '--port') values[args[i]] = args[++i];
    else if (args[i].startsWith('--host=') || args[i].startsWith('--port=')) {
      const [key, value] = args[i].split('=');
      values[key] = value;
    }
  }
  assert.equal(values['--host'], '127.0.0.2');
  assert.equal(values['--port'], '8090');
});

test('configuration dumps receive no Web-only listener arguments', () => {
  const args = ['web', '--patch', '/config/extra.yml', '--dump-config'];
  assert.deepEqual(invocation(args), args);
});

test('other profile arguments are forwarded unchanged', () => {
  const args = ['headless', 'run the tests'];
  assert.deepEqual(invocation(args), args);
});
