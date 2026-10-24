import { networkInterfaces } from 'node:os';
// Upstream rejects wildcard binds. Publish the port via Docker and bind one real address.
export function listenAddress() {
  if (process.env.DSH_LISTEN_ADDRESS) return process.env.DSH_LISTEN_ADDRESS;
  for (const addresses of Object.values(networkInterfaces())) {
    const address = addresses?.find(item => item.family === 'IPv4' && !item.internal);
    if (address) return address.address;
  }
  return '127.0.0.1';
}
if (import.meta.main) process.stdout.write(listenAddress());
