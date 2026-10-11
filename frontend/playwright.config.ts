import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL:
      process.env.DHCP_TOOL_E2E_RUNTIME === '1' ? 'http://127.0.0.1:3102' : 'http://127.0.0.1:3101',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'python3 ../scripts/e2e-nginx.py',
      url: 'http://127.0.0.1:3102/nginx-ready/',
      reuseExistingServer: false,
    },
    {
      command:
        process.env.DHCP_TOOL_E2E_RUNTIME === '1'
          ? 'uv run --project ../backend --offline --no-sync --env-file ../backend/.env.test gunicorn --chdir ../backend --config ../deploy/gunicorn.conf.py --bind 127.0.0.1:8101 config.wsgi:application'
          : 'uv run --project ../backend --offline --no-sync --env-file ../backend/.env.test python ../backend/manage.py runserver 127.0.0.1:8101 --noreload',
      url: 'http://127.0.0.1:8101/api/v1/health/',
      reuseExistingServer: false,
      env: {
        DJANGO_SETTINGS_MODULE:
          process.env.DHCP_TOOL_E2E_RUNTIME === '1'
            ? 'config.settings.lan'
            : 'config.settings.development',
        DJANGO_SECRET_KEY: 'e2e-only-not-for-production',
        BACKUP_DOWNLOAD_DIR: join(tmpdir(), `dhcp-tool-backup-e2e-${process.getuid?.() ?? 'test'}`),
        DJANGO_ALLOWED_HOSTS: '127.0.0.1,localhost',
        DJANGO_CSRF_TRUSTED_ORIGINS: 'http://127.0.0.1:3101,http://127.0.0.1:3102',
      },
    },
    {
      command:
        process.env.DHCP_TOOL_E2E_PRODUCTION === '1'
          ? 'npx next start --hostname 127.0.0.1 --port 3101'
          : 'npm run dev -- --hostname 127.0.0.1 --port 3101',
      url: 'http://127.0.0.1:3101',
      reuseExistingServer: false,
      env: {
        DHCP_TOOL_API_URL: 'http://127.0.0.1:8101',
        NEXT_BUILD_DIR:
          process.env.DHCP_TOOL_E2E_PRODUCTION === '1' ? '.next-quality' : '.next-e2e',
        NEXT_TELEMETRY_DISABLED: '1',
      },
      timeout: 120000,
    },
  ],
});
