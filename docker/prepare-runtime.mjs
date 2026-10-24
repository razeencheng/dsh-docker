import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

function compatible(values, actual) {
  if (!values?.length) return true;
  if (values.includes(`!${actual}`)) return false;
  const positive = values.filter(value => !value.startsWith('!'));
  return positive.length === 0 || positive.includes(actual);
}

// Dynamic Web plugins declare services as peers. pnpm's production deploy does
// not supply those peers automatically, so make the reachable workspace graph
// explicit while preserving the upstream dependency versions and source files.
export function collectClosure(packages, seeds, platform = process.platform, arch = process.arch) {
  const selected = new Set();
  const queue = [...seeds];
  while (queue.length) {
    const name = queue.pop();
    if (selected.has(name)) continue;
    const manifest = packages.get(name);
    if (!manifest) throw new Error(`Missing workspace package: ${name}`);
    if (!compatible(manifest.os, platform) || !compatible(manifest.cpu, arch)) continue;
    selected.add(name);
    for (const dependencies of [manifest.dependencies, manifest.peerDependencies, manifest.optionalDependencies]) {
      for (const [dependency, version] of Object.entries(dependencies ?? {})) {
        if (packages.has(dependency) || version.startsWith('workspace:')) queue.push(dependency);
      }
    }
  }
  return [...selected].sort();
}

export function workspacePackages(root) {
  const packages = new Map();
  const children = directory => existsSync(directory)
    ? readdirSync(directory, { withFileTypes: true }).filter(item => item.isDirectory()).map(item => join(directory, item.name))
    : [];
  const paths = [
    ...children(join(root, 'vendor')),
    ...children(join(root, 'apps')),
    ...children(join(root, 'packages')).flatMap(children),
    join(root, 'native/system'),
    ...children(join(root, 'native/system/packages')),
  ];
  for (const path of paths) {
    const file = join(path, 'package.json');
    if (!existsSync(file)) continue;
    const manifest = JSON.parse(readFileSync(file, 'utf8'));
    if (manifest.name) packages.set(manifest.name, manifest);
  }
  return packages;
}

if (import.meta.main) {
  const root = process.argv[2] || '/src';
  const packages = workspacePackages(root);
  const seed = JSON.parse(readFileSync(join(root, 'python/sdk-runtime/package.json'), 'utf8'));
  const names = collectClosure(packages, Object.keys(seed.dependencies));
  const output = join(root, 'apps/docker-runtime');
  mkdirSync(output, { recursive: true });
  writeFileSync(join(output, 'package.json'), JSON.stringify({
    name: 'dsh-docker-runtime', version: '0.0.0', private: true, type: 'module',
    dependencies: Object.fromEntries(names.map(name => [name, 'workspace:*'])),
  }, null, 2) + '\n');
  console.log(`Docker runtime closure: ${names.length} workspace packages including transitive peers`);
}
