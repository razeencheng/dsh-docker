#!/usr/bin/env node
import { listenAddress } from '/opt/dsh/listen-address.mjs';
const host = listenAddress();
const authority = host.includes(':') ? `[${host}]` : host;
try {
  const response = await fetch(`http://${authority}:${process.env.PORT || '3080'}/`, { signal: AbortSignal.timeout(4000) });
  process.exit(response.ok ? 0 : 1);
} catch {
  process.exit(1);
}
