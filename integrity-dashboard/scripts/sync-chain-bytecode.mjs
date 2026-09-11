import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const dashboardRoot = resolve(import.meta.dirname, '..');
const repoRoot = resolve(dashboardRoot, '..');
const contracts = ['SovereignAgent', 'StateAnchor'];
const lines = [
  '// Generated from contracts/out by `npm run sync-chain-bytecode`.',
  '// Do not hand-edit: browser registration must deploy the same source validated by Foundry.',
  '',
];

for (const name of contracts) {
  const artifactPath = resolve(repoRoot, 'contracts', 'out', `${name}.sol`, `${name}.json`);
  const artifact = JSON.parse(await readFile(artifactPath, 'utf8'));
  const bytecode = artifact.bytecode?.object;
  if (typeof bytecode !== 'string' || !bytecode.startsWith('0x')) {
    throw new Error(`${artifactPath} has no deployable bytecode.object`);
  }
  const prefix = name.replace(/([a-z])([A-Z])/g, '$1_$2').toUpperCase();
  lines.push(`export const ${prefix}_BYTECODE = ${JSON.stringify(bytecode)} as const;`);
  lines.push(`export const ${prefix}_ABI = ${JSON.stringify(artifact.abi)} as const;`);
  lines.push('');
}

await writeFile(resolve(dashboardRoot, 'src', 'chain', 'bytecode.ts'), `${lines.join('\n').trimEnd()}\n`);
