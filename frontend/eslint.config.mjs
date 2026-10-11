import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';

const config = [
  ...nextVitals,
  ...nextTypescript,
  {
    // These fetch effects deliberately clear stale private data before requesting a new scope.
    // They cancel requests and ignore late responses; the extra render is intentional.
    files: [
      'src/components/workspace.tsx',
      'src/components/audit-history.tsx',
      'src/components/deployment-ledger.tsx',
    ],
    rules: { 'react-hooks/set-state-in-effect': 'off' },
  },
  {
    ignores: [
      'next-env.d.ts',
      '.next*/**',
      'src/lib/api/schema.d.ts',
      'playwright-report/**',
      'test-results/**',
    ],
  },
];
export default config;
