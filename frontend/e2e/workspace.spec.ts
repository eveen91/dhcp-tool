import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, test, type Page } from '@playwright/test';
const suffix = randomUUID().slice(0, 8);
const username = `e2e-workspace-${suffix}`;
const password = randomBytes(24).toString('base64url');
const prefix = `e2e-w-${suffix}`;
function fixture(action: 'create' | 'delete') {
  execFileSync(
    'uv',
    [
      'run',
      '--project',
      '../backend',
      '--offline',
      '--no-sync',
      '--env-file',
      '../backend/.env.test',
      'python',
      '../backend/tests/e2e_workspace.py',
      action,
    ],
    {
      env: {
        ...process.env,
        DJANGO_SETTINGS_MODULE: 'config.settings.test',
        DHCP_TOOL_E2E_USERNAME: username,
        DHCP_TOOL_E2E_PASSWORD: password,
        DHCP_TOOL_E2E_PREFIX: prefix,
      },
      stdio: 'pipe',
    },
  );
}
test.beforeAll(() => fixture('create'));
test.afterAll(() => fixture('delete'));
async function accessible(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(result.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))).toEqual(
    [],
  );
}
async function field(page: Page, label: string, value: string) {
  await page.getByLabel(label, { exact: false }).last().fill(value);
}
async function login(page: Page) {
  await page.goto('/');
  await accessible(page);
  await field(page, 'Nazwa użytkownika', username);
  await field(page, 'Hasło', password);
  await page.getByRole('button', { name: 'Zaloguj', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Lista firewalli' })).toBeVisible();
  await accessible(page);
}
async function firewall(page: Page, name: string, profile: string) {
  await page.getByRole('button', { name: 'Dodaj firewall', exact: true }).click();
  await accessible(page);
  await field(page, 'Nazwa firewalla', name);
  await page.getByLabel('Profil Gaia').selectOption(profile);
  await page.getByRole('button', { name: 'Utwórz firewall' }).click();
  await expect(page.getByRole('heading', { name: 'Konfiguracja robocza' })).toBeVisible();
}
async function subnet(page: Page) {
  await page.getByRole('button', { name: 'Dodaj podsieć', exact: true }).click();
  await field(page, 'Nazwa podsieci', 'Biuro z polskimi znakami Łódź');
  await field(page, 'CIDR', '192.0.2.0/24');
  await field(page, 'Brama IPv4', '192.0.2.1');
  await page.getByRole('button', { name: 'Utwórz podsieć' }).click();
  await expect(page.getByRole('button', { name: 'Dodaj pulę', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Dodaj pulę', exact: true }).click();
  await field(page, 'Początek puli', '192.0.2.100');
  await field(page, 'Koniec puli', '192.0.2.200');
  await page.getByRole('button', { name: 'Zapisz pulę' }).click();
  await expect(page.getByRole('button', { name: 'Edytuj pulę', exact: true })).toBeVisible();
}
async function reservation(page: Page, name: string, ip: string) {
  await page.getByRole('button', { name: 'Dodaj rezerwację', exact: true }).click();
  await field(page, 'Nazwa hosta', name);
  await field(page, 'Adres IP', ip);
  await field(page, 'MAC', '02:00:00:00:00:10');
  await page.getByRole('button', { name: 'Zapisz rezerwację' }).click();
}
test('two firewalls: configuration, artifacts, manual ledger, corrections and audit', async ({
  page,
}, testInfo) => {
  test.setTimeout(120000);
  await login(page);
  await firewall(page, `${prefix}-one`, 'R81.10');
  await subnet(page);
  await reservation(page, 'drukarka', '192.0.2.120');
  await expect(page.getByLabel('Adres IP', { exact: false }).last()).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  await field(page, 'Adres IP', '192.0.2.10');
  await page.getByRole('button', { name: 'Zapisz rezerwację' }).click();
  await expect(page.getByRole('button', { name: 'Edytuj rezerwację drukarka' })).toBeVisible();
  await page.getByRole('button', { name: 'Edytuj opcje globalne' }).click();
  await field(page, 'Domena', 'example.test');
  await page.evaluate(async () => {
    const session = await (await fetch('/api/v1/auth/session/')).json();
    const list = await (
      await fetch(
        '/api/v1/firewalls/?search=' +
          document.querySelector('.firewall-context strong')?.textContent,
      )
    ).json();
    const id = list.results[0].id;
    const draft = await (await fetch(`/api/v1/firewalls/${id}/draft/`)).json();
    const response = await fetch(`/api/v1/firewalls/${id}/draft/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': session.csrf_token,
        'X-Config-Revision': String(draft.revision),
      },
      body: JSON.stringify({ domain: 'other.test' }),
    });
    if (!response.ok) throw new Error('Concurrent write failed');
  });
  await page.getByRole('button', { name: 'Zapisz opcje globalne' }).click();
  await expect(page.getByRole('alert').first()).toContainText('Konfiguracja została zmieniona');
  await expect(page.getByLabel('Domena', { exact: true })).toHaveValue('example.test');
  await page.getByRole('button', { name: 'Wersje', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Odrzuć i przejdź' }).click();
  await page.getByRole('button', { name: 'Konfiguracja', exact: true }).click();
  // Refresh the persisted revision after explicitly discarding conflicting local input.
  await page.reload();
  await page.getByRole('button', { name: `Otwórz ${prefix}-one` }).click();
  await page.getByRole('button', { name: 'Walidacja i podgląd', exact: true }).click();
  await page.getByRole('button', { name: 'Pokaż cały plik' }).click();
  await expect(page.getByLabel('Cały plik konfiguracji')).toContainText('192.0.2.10');
  await expect(page.getByText('Zgodność Gaia: niezweryfikowana', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Przygotuj publikację' }).click();
  await field(page, 'Opis zmiany', 'Pierwsza wersja — drukarka');
  // Simulate an unavailable validator at the HTTP boundary; retain real UI and database reads.
  await page.route('**/api/v1/firewalls/*/versions/', async (route) => {
    if (route.request().method() === 'POST')
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'parser_timeout',
            message: 'Przekroczono czas walidatora. Sprawdź status przed ponowną publikacją.',
            fields: {},
          },
        }),
      });
    else await route.continue();
  });
  await page.getByRole('button', { name: 'Opublikuj wersję', exact: true }).click();
  await expect(page.getByRole('alert').first()).toContainText('Przekroczono czas walidatora');
  await expect(page.getByLabel('Opis zmiany', { exact: false })).toHaveValue(
    'Pierwsza wersja — drukarka',
  );
  expect(
    await page.evaluate(async () => {
      const list = await (
        await fetch(
          '/api/v1/firewalls/?search=' +
            document.querySelector('.firewall-context strong')?.textContent,
        )
      ).json();
      return (await (await fetch(`/api/v1/firewalls/${list.results[0].id}/versions/`)).json())
        .count;
    }),
  ).toBe(0);
  await page.unroute('**/api/v1/firewalls/*/versions/');
  await page.getByRole('button', { name: 'Opublikuj wersję', exact: true }).click();
  await page.getByRole('button', { name: 'Otwórz wersję 1', exact: true }).click();
  await accessible(page);
  const hashText = await page.locator('.version-detail .hash').textContent();
  const hash = hashText!.replace('SHA-256: ', '');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Pobierz dhcpd.conf', exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('dhcpd.conf');
  const bytes = await readFile((await download.path())!);
  expect(createHash('sha256').update(bytes).digest('hex')).toBe(hash);
  expect(bytes.toString()).toContain('fixed-address 192.0.2.10;');
  await expect(page.getByText(/Ręcznie potwierdzona: Brak potwierdzonego wdrożenia/)).toBeVisible();
  await page.getByLabel('Wersja docelowa').selectOption({ label: 'Wersja 1' });
  await page.getByRole('button', { name: 'Porównaj', exact: true }).click();
  await expect(page.getByText(/Wybierz wersję bazową do porównania/)).toBeVisible();
  await page.getByRole('button', { name: 'Konfiguracja', exact: true }).click();
  await page.getByRole('button', { name: 'Edytuj rezerwację drukarka' }).click();
  await field(page, 'Adres IP', '192.0.2.11');
  await page.getByRole('button', { name: 'Zapisz rezerwację' }).click();
  await page.getByRole('button', { name: 'Walidacja i podgląd', exact: true }).click();
  await page.getByRole('button', { name: 'Pokaż cały plik' }).click();
  await page.getByRole('button', { name: 'Przygotuj publikację' }).click();
  await field(page, 'Opis zmiany', 'Zmiana adresu drukarki');
  await page.getByRole('button', { name: 'Opublikuj wersję', exact: true }).click();
  await page.getByLabel('Wersja bazowa').selectOption({ label: 'Wersja 1' });
  await page.getByLabel('Wersja docelowa').selectOption({ label: 'Wersja 2' });
  await page.getByRole('button', { name: 'Porównaj', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Zmiany obiektów' })).toBeVisible();
  await expect(page.getByText('Zmieniono', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Ewidencja', exact: true }).click();
  async function declare(version: string, status: string, minutesAgo: number, ticket: string) {
    await page.getByRole('button', { name: 'Dodaj wpis', exact: true }).click();
    const select = page.getByLabel('Wersja konfiguracji');
    await expect(select.locator('option')).toHaveCount(3);
    const value = await select
      .locator('option')
      .filter({ hasText: `Wersja ${version} —` })
      .getAttribute('value');
    await select.selectOption(value!);
    await page.getByLabel('Wynik zdarzenia').selectOption(status);
    await field(page, 'Czas zdarzenia', new Date(Date.now() - minutesAgo * 60000).toISOString());
    await field(page, 'Numer zgłoszenia', ticket);
    await field(page, 'Ręcznie podany SHA-256', hash);
    await page.getByRole('button', { name: 'Zapisz wpis', exact: true }).click();
    await expect(page.getByRole('cell').filter({ hasText: ticket })).toBeVisible();
  }
  await declare('2', 'failed', 60, 'E2E-FAILED');
  await expect(page.getByText('Ostatnie zadeklarowane udane wdrożenie: brak wpisu')).toBeVisible();
  await declare('2', 'successful', 50, 'E2E-SUCCESS');
  await expect(page.getByText(/Ostatnie zadeklarowane udane wdrożenie: wersja 2/)).toBeVisible();
  await expect(page.getByText('Niezgodny z artefaktem').first()).toBeVisible();
  await declare('1', 'successful', 120, 'E2E-BACKDATED');
  await expect(page.getByText(/Ostatnie zadeklarowane udane wdrożenie: wersja 2/)).toBeVisible();
  await declare('1', 'successful', 40, 'E2E-ROLLBACK');
  await expect(page.getByText(/Ostatnie zadeklarowane udane wdrożenie: wersja 1/)).toBeVisible();
  await page.getByRole('button', { name: 'Skoryguj wpis wersji 1 E2E-ROLLBACK' }).click();
  await page.getByLabel('Wynik zdarzenia').selectOption('cancelled');
  await field(page, 'Uzasadnienie korekty', 'Błędne potwierdzenie operatora');
  await page.getByRole('button', { name: 'Zapisz korektę', exact: true }).click();
  await expect(page.getByText(/Ostatnie zadeklarowane udane wdrożenie: wersja 2/)).toBeVisible();
  await accessible(page);
  await page.screenshot({ path: testInfo.outputPath('deployments-desktop.png'), fullPage: true });
  await page.getByRole('button', { name: 'Historia operacji', exact: true }).click();
  await page.getByLabel('Rodzaj operacji').selectOption('deployment_correct');
  await page.getByRole('button', { name: /Pokaż zmianę/ }).click();
  await expect(page.getByText(/Błędne potwierdzenie operatora/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Przed zmianą' })).toBeVisible();
  await accessible(page);
  await page.screenshot({ path: testInfo.outputPath('audit-desktop.png'), fullPage: true });
  await page.getByRole('button', { name: 'Wersje', exact: true }).click();
  await page.getByRole('button', { name: 'Otwórz wersję 1', exact: true }).click();
  await page.getByRole('button', { name: 'Odtwórz do konfiguracji roboczej' }).click();
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Anuluj' })).toBeFocused();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Odtwórz wersję do roboczej', exact: true })
    .click();
  await page.getByRole('button', { name: 'Konfiguracja', exact: true }).click();
  await expect(page.getByRole('cell', { name: '192.0.2.10', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('configuration-desktop.png'), fullPage: true });
  await page.getByRole('button', { name: 'Usuń pulę', exact: true }).click();
  await accessible(page);
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('dialog').getByRole('button', { name: 'Usuń pulę', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Anuluj' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('button', { name: 'Lista firewalli', exact: true }).click();
  await firewall(page, `${prefix}-two`, 'R82.10');
  await subnet(page);
  await reservation(page, 'drukarka', '192.0.2.10');
  await expect(page.getByRole('button', { name: 'Edytuj rezerwację drukarka' })).toBeVisible();
  await page.getByRole('button', { name: 'Usuń rezerwację drukarka' }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Usuń rezerwację', exact: true })
    .click();
  await expect(page.getByRole('button', { name: 'Edytuj rezerwację drukarka' })).not.toBeVisible();
  await page.getByRole('button', { name: 'Lista firewalli', exact: true }).click();
  await page.getByRole('button', { name: `Otwórz ${prefix}-one` }).click();
  await expect(page.getByRole('button', { name: 'Edytuj rezerwację drukarka' })).toBeVisible();
  await page.getByRole('button', { name: 'Edytuj podsieć', exact: true }).click();
  await field(page, 'Nazwa podsieci', 'N'.repeat(140) + ' Łódź');
  await field(page, 'Opis', 'd'.repeat(1000));
  await page.getByRole('button', { name: 'Zapisz podsieć' }).click();
  await expect(
    page.getByRole('heading', { name: 'N'.repeat(140) + ' Łódź', exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await accessible(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole('button', { name: 'Wyloguj', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Logowanie' })).toBeVisible();
});

test('administrator downloads an intact encrypted backup through the browser', async ({
  page,
}, testInfo) => {
  const source = mkdtempSync(join(tmpdir(), 'dhcp-backup-source-'));
  const destination = join(tmpdir(), `dhcp-tool-backup-e2e-${process.getuid?.() ?? 'test'}`);
  const filename = 'dhcp-tool-20261011T120000Z-a1b2c3d4.tar.gpg';
  const payload = 'Test-only backup payload; no production data.';
  const fixtureKey = 'public-test-fixture-key';
  try {
    writeFileSync(join(source, 'payload'), payload);
    execFileSync(
      'gpg',
      [
        '--batch',
        '--yes',
        '--pinentry-mode',
        'loopback',
        '--passphrase',
        fixtureKey,
        '--symmetric',
        '--output',
        join(source, filename),
        join(source, 'payload'),
      ],
      { stdio: 'pipe' },
    );
    const encrypted = readFileSync(join(source, filename));
    const checksum = createHash('sha256').update(encrypted).digest('hex');
    writeFileSync(
      join(source, 'latest.json'),
      JSON.stringify({ file: filename, sha256: checksum }),
    );
    const group = execFileSync('id', ['-gn'], { encoding: 'utf8' }).trim();
    execFileSync(
      'python3',
      [
        '../scripts/publish-backup.py',
        '--source',
        source,
        '--destination',
        destination,
        '--group',
        group,
      ],
      { stdio: 'pipe' },
    );
    await login(page);
    await page.getByRole('button', { name: 'Administracja', exact: true }).click();
    await accessible(page);
    await page.screenshot({
      path: testInfo.outputPath('backup-administration.png'),
      fullPage: true,
    });
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Pobierz najnowszy backup' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(filename);
    expect(await download.failure()).toBeNull();
    const path = await download.path();
    expect(path).not.toBeNull();
    const received = await readFile(path!);
    expect(createHash('sha256').update(received).digest('hex')).toBe(checksum);
    const decrypted = execFileSync(
      'gpg',
      ['--batch', '--pinentry-mode', 'loopback', '--passphrase', fixtureKey, '--decrypt', path!],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] },
    );
    expect(decrypted).toBe(payload);
  } finally {
    rmSync(source, { recursive: true, force: true });
    rmSync(destination, { recursive: true, force: true });
  }
});

test('full configuration CSV previews changes before an atomic import', async ({
  page,
}, testInfo) => {
  test.setTimeout(60000);
  await login(page);
  await firewall(page, `${prefix}-csv`, 'R81.10');
  await subnet(page);
  await reservation(page, 'csv-host', '192.0.2.10');
  await page.getByRole('button', { name: 'CSV', exact: true }).click();
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Eksportuj konfigurację CSV' }).click();
  const download = await downloadEvent;
  const path = await download.path();
  expect(path).not.toBeNull();
  const csv = execFileSync(
    'python3',
    [
      '-c',
      `
import csv, io, json, sys
rows=list(csv.DictReader(io.StringIO(sys.stdin.read().removeprefix('\\ufeff'))))
assert {r['kind'] for r in rows} == {'firewall','settings','subnet','pool','reservation'}
for row in rows:
    if row['kind']=='settings': row['options']=json.dumps({'domain':'csv.example'})
    if row['kind']=='reservation': row['ip']='192.0.2.11'
out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
sys.stdout.write(out.getvalue())
`,
    ],
    { input: readFileSync(path!), encoding: 'utf8' },
  );
  await page.getByLabel('Plik CSV', { exact: true }).setInputFiles({
    name: 'configuration.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(csv),
  });
  await page.getByRole('button', { name: 'Sprawdź i pokaż zmiany' }).click();
  await expect(page.getByRole('heading', { name: 'Podgląd zmian CSV' })).toBeVisible();
  await expect(page.getByText('192.0.2.11', { exact: false }).first()).toBeVisible();
  await accessible(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await accessible(page);
  await page.screenshot({ path: testInfo.outputPath('csv-preview-mobile.png'), fullPage: true });
  await page.getByRole('button', { name: 'Zastosuj import' }).click();
  await expect(page.getByRole('heading', { name: 'Podgląd zmian CSV' })).not.toBeVisible();
  await page.getByRole('button', { name: 'Konfiguracja', exact: true }).click();
  await expect(page.getByText('192.0.2.11', { exact: true })).toBeVisible();
});

test('cluster member addresses persist and block reservation collisions', async ({ page }) => {
  await login(page);
  await firewall(page, `${prefix}-cluster`, 'R81.10');
  await subnet(page);
  await page.getByRole('button', { name: 'Edytuj podsieć', exact: true }).click();
  await field(page, 'Adresy interfejsów IPv4', '192.0.2.2, 192.0.2.3');
  await page.getByRole('button', { name: 'Zapisz podsieć', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Edytuj podsieć', exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: `Otwórz ${prefix}-cluster`, exact: true }).click();
  await page.getByRole('button', { name: 'Edytuj podsieć', exact: true }).click();
  await expect(page.getByLabel('Adresy interfejsów IPv4')).toHaveValue('192.0.2.2, 192.0.2.3');
  await accessible(page);
  await page.getByRole('button', { name: 'Anuluj', exact: true }).click();
  await reservation(page, 'cluster-test', '192.0.2.3');
  await expect(page.getByLabel('Adres IP', { exact: false }).last()).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  await field(page, 'Adres IP', '192.0.2.2');
  await page.getByRole('button', { name: 'Zapisz rezerwację' }).click();
  await expect(page.getByLabel('Adres IP', { exact: false }).last()).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  await field(page, 'Adres IP', '192.0.2.4');
  await page.getByRole('button', { name: 'Zapisz rezerwację' }).click();
  await expect(page.getByRole('button', { name: 'Edytuj rezerwację cluster-test' })).toBeVisible();
});
