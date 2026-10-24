import assert from 'node:assert/strict';
import test from 'node:test';
import { collectClosure } from './prepare-runtime.mjs';

test('includes transitive runtime peers, including a peer only reached through another peer', () => {
  const packages = new Map([
    ['cli', { dependencies: { web: 'workspace:*' } }],
    ['web', { dependencies: { api: 'workspace:*' } }],
    ['api', { peerDependencies: { picker: 'workspace:*' }, devDependencies: { test: 'workspace:*' } }],
    ['picker', { peerDependencies: { core: 'workspace:*' } }],
    ['core', {}], ['test', {}],
  ]);
  assert.deepEqual(collectClosure(packages, ['cli'], 'linux', 'arm64'), ['api', 'cli', 'core', 'picker', 'web']);
});

test('includes only compatible optional workspace packages and terminates cycles', () => {
  const packages = new Map([
    ['entry', { optionalDependencies: { arm: 'workspace:*', x64: 'workspace:*', mac: 'workspace:*' } }],
    ['arm', { os: ['linux'], cpu: ['arm64'], peerDependencies: { entry: 'workspace:*' } }],
    ['x64', { os: ['linux'], cpu: ['x64'] }],
    ['mac', { os: ['darwin'], cpu: ['arm64'] }],
  ]);
  assert.deepEqual(collectClosure(packages, ['entry'], 'linux', 'arm64'), ['arm', 'entry']);
});

test('rejects missing workspace dependencies instead of silently publishing an incomplete closure', () => {
  const packages = new Map([['cli', { peerDependencies: { missing: 'workspace:*' } }]]);
  assert.throws(() => collectClosure(packages, ['cli'], 'linux', 'amd64'), /Missing workspace package/);
});
