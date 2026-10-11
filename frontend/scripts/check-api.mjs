import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const directory = mkdtempSync(join(tmpdir(), 'dhcp-api-types-'));
try {
  const generated = join(directory, 'schema.d.ts');
  execFileSync(
    process.execPath,
    [
      'node_modules/openapi-typescript/bin/cli.js',
      '../backend/config/openapi.json',
      '-o',
      generated,
    ],
    { stdio: 'inherit' },
  );
  if (readFileSync(generated, 'utf8') !== readFileSync('src/lib/api/schema.d.ts', 'utf8')) {
    throw new Error('API types are stale. Run npm run api:generate.');
  }
} finally {
  rmSync(directory, { recursive: true, force: true });
}
