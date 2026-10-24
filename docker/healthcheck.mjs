#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { listenAddress } from '/opt/dsh/listen-address.mjs';
import { checkAsset, frontendAsset } from '/opt/dsh/web-checks.mjs';
const host = listenAddress();
const authority = host.includes(':') ? `[${host}]` : host;
try {
  const require = createRequire('/opt/dsh/package.json');
  const frontend = dirname(require.resolve('@deepseek-ai/dsh-web-frontend/package.json'));
  const asset = frontendAsset(await readFile(join(frontend, 'dist/index.html'), 'utf8'));
  // The index requires a per-process browser login; built JS assets are public.
  await checkAsset(`http://${authority}:${process.env.PORT || '3080'}/`, asset);
} catch (error) {
  if (process.argv.includes('--verbose')) console.error(`Web health check: ${error.message}`);
  process.exit(1);
}
