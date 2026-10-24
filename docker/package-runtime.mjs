// Use upstream's tested production-deploy helpers; keep workspace modules singletons.
import { copyFile, mkdir } from 'node:fs/promises';
import { restoreLegacyHoists } from '/src/scripts/executable-packaging.ts';
import { materializeStagedLinks, deduplicateStagedWorkspacePackages } from '/src/scripts/build-exe-for-python-sdk-staging.ts';
await restoreLegacyHoists('/opt/dsh', '/src/python/sdk-runtime/node_modules');
await materializeStagedLinks('/opt/dsh');
await deduplicateStagedWorkspacePackages('/opt/dsh', '/src');
await mkdir('/opt/dsh/licenses', { recursive: true });
for (const filename of ['LICENSE', 'THIRD_PARTY_NOTICES.md']) {
  await copyFile(`/src/${filename}`, `/opt/dsh/licenses/${filename}`);
}
