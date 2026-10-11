# Uruchomienie prac developerskich (bez kontenerów)

## Wspierane środowisko

Decyzja T00.8: wspieramy rodziny wersji używane na obecnym serwerze. Wersje bazowe poniżej odczytano z zainstalowanego środowiska; nie są blokadą przyszłych aktualizacji poprawek. Nowe wersje wymagają sprawdzenia testów i buildu przed wdrożeniem.

| Składnik | Wspierana rodzina | Obecna wersja bazowa |
| --- | --- | --- |
| System | Debian 13 (trixie) | 13.7 |
| Python | 3.13 | 3.13.5 |
| Node.js | 24 | 24.21.0 |
| Next.js | 16.4 | 16.4.0 |
| PostgreSQL | 17 | 17.11 |
| Django | 5.2 | 5.2.18 |

Szersze ograniczenia wersji w metadanych zależności nie oznaczają dodatkowych oficjalnie wspieranych środowisk. Zależności aplikacji odtwarzamy z `uv.lock` i `package-lock.json`.

## Backend

Na nowym checkout przygotuj `backend/.env` na podstawie `.env.example` i `.env.test` na podstawie `.env.test.example`. Wpisz własne sekrety i dane niezależnych baz. Dla lokalnego backendu zmień `DJANGO_SETTINGS_MODULE` na `config.settings.development`, hosty na `127.0.0.1,localhost`, a origin CSRF na `http://localhost:3000`. Przykład `.env.example` domyślnie opisuje HTTPS, nie development. Ustaw prawa obu prywatnych plików na 600.

### Lokalne bazy PostgreSQL

Lokalna konfiguracja korzysta z dwóch niezależnych kont i baz:

| Zastosowanie | Baza | Rola | Uprawnienia |
| --- | --- | --- | --- |
| Development i migracje | `dhcp_tool` | `dhcp_tool` | Właściciel własnej bazy, bez superuser i CREATEDB |
| Testy | `test_dhcp_tool` | `dhcp_tool_test` | Właściciel bazy testowej, CREATEDB dla cyklu testów Django, bez superuser |

Testowe konto jest wyłącznie lokalne i nie służy do uruchamiania produkcji.
Obie bazy odbierają domyślne uprawnienia `PUBLIC`, aby konto testowe nie miało
dostępu do bazy aplikacji. Nie używać konta `postgres` do uruchamiania Django.

Sekrety znajdują się w ignorowanych przez Git plikach `backend/.env` i
`backend/.env.test`, z uprawnieniami `600`. `uv run --env-file` ładuje je jawnie;
samo Django nie odczytuje tych plików automatycznie. Przykład produkcyjny jest
w `.env.example`, a przykład testowy w `.env.test.example`.

Przygotowany lokalnie plik `backend/.local-postgres.sql` zawiera inicjalizację ról
i baz. Uruchomić go tylko na lokalnym klastrze developerskim, z katalogu głównego:

```sh
sudo -u postgres psql -X -d postgres -f - < backend/.local-postgres.sql
```

Skrypt zatrzymuje się, jeśli nazwy ról lub baz są zajęte. Nie usuwa istniejących
baz ani nie zmienia istniejących haseł. Plik SQL jest również ignorowany przez Git
i ma uprawnienia `600`. Nie należy go publikować ani kopiować do logów.

Następnie zastosować migracje w bazie aplikacji i sprawdzić testy:

```sh
cd backend
uv run --env-file .env python manage.py migrate
uv run --env-file .env.test pytest --reuse-db
```

`--reuse-db` zachowuje dedykowaną bazę między uruchomieniami. Testy bazodanowe
wymagają rzeczywistego połączenia z PostgreSQL; testy generatora i health nie
potwierdzają tego połączenia. Ustawienia testowe jawnie wskazują `test_dhcp_tool`
jako bazę używaną przez Django test runner.

Wymagane: Python 3.13, `uv`, działający PostgreSQL do testów bazodanowych. Testy kont, sesji, uprawnień i współbieżnego limitera korzystają z osobnej bazy testowej; generator i health nie wymagają bazy. W `backend/`:

```sh
uv sync --frozen --extra dev
uv run --env-file .env.test pytest --reuse-db
uv run ruff check .
uv run --env-file .env python manage.py check
uv run --env-file .env python manage.py migrate
uv run --env-file .env python manage.py runserver 127.0.0.1:8000
```

`GET http://127.0.0.1:8000/api/v1/health/` zwraca tylko `{"status":"ok"}`. Ustawienia domyślne `manage.py` są **wyłącznie developerskie**. Na produkcji należy ustawić `DJANGO_SETTINGS_MODULE=config.settings.production` oraz sekret i dane bazy według `backend/.env.example`; nie kopiować przykładowych wartości. Baza w testach Django powinna być tworzona przez uprawnionego użytkownika PostgreSQL (`POSTGRES_TEST_DB`), nie używać produkcyjnej bazy. Serwer nie jest wdrażany na firewall.

## Frontend

Wymagany Node.js 24. W `frontend/`:

```sh
npm ci
npm test
npm run lint
npm run typecheck
npm run build
npm run dev
```

Aplikacja Next.js działa lokalnie pod `http://localhost:3000/`. W development ścieżki `/api/v1/*` są przekierowywane do Django pod `http://localhost:8000/api/v1/*`; przeglądarka korzysta z jednego originu. Widok początkowy pokazuje dostępność API i logowanie; po zalogowaniu dostępny jest pełny panel konfiguracji, CSV, wersji, ewidencji i backupu dla admina. Testy komponentu stosują atrapę `fetch`; osobny Playwright sprawdza prawdziwe połączenie oraz logowanie i wylogowanie przez proxy. Wyniki aktualnego audytu i aktualizacji bezpieczeństwa opisano w `docs/dependency-audit.md`.

## Uwagi do zakresu

### Panel z innego komputera

Obecny serwer udostępnia pełny panel z logowaniem na `http://192.168.1.32:8080` w LAN/VPN. Nginx przekazuje API do Gunicorna na 18000, a WWW do Next.js na 13000. Usługi systemd uruchamiają się po restarcie. Instrukcja: [installation.md](installation.md).

`docs/nginx-status.conf` jest dawną konfiguracją ograniczonego podglądu. Nie instaluj jej na działającym pełnym panelu. Lokalne serwery developerskie korzystają z portów 8000/3000 i nie zastępują usług instalacyjnych.

## Kontrakt API, typy i testy przeglądarkowe

Kontrakt dostępnych zasobów opisano w `docs/api-contract.md`.
Działający backend udostępnia OpenAPI pod `/api/v1/schema/`; źródłem jest
`backend/config/openapi.json`. Pełny Nginx LAN udostępnia API panelu; schemat nie zastępuje backendowej kontroli uprawnień.

Po zmianie OpenAPI w `frontend/` wykonać `npm run api:generate`. Wygenerowany
`src/lib/api/schema.d.ts` należy zapisać razem ze zmianą schematu.
`npm run api:check` wykrywa nieaktualne typy. Klient statusu `src/lib/api/client.ts` używa tych typów i sprawdza odpowiedź w runtime. Panel używa `src/lib/api/workspace-client.ts` do sesji, CSRF, rewizji i obsługi błędów.

Playwright działa bez pulpitu. Pierwsze przygotowanie w `frontend/`: `npx playwright install chromium` oraz
`npx playwright install-deps chromium` (biblioteki systemowe wymagają sudo). Następnie `npm run test:e2e` uruchamia własne Django na
127.0.0.1:8101 i Next.js na 127.0.0.1:3101, z katalogiem `.next-e2e`.
Testy uruchamiają także osobny Nginx na 127.0.0.1:3102; wymagają `/usr/sbin/nginx`. Pełny skrypt jakości uruchamia Playwright z produkcyjnym buildem `.next-quality`, z proxy ustawionym podczas builda na testowy port 8101.
Wymaga przygotowanego `backend/.env.test` i dostępu do osobnej bazy testowej.
Test sukcesu używa prawdziwego API, test awarii celowo blokuje żądanie.
Testy nie korzystają z działających usług na portach 8000/3000.

## Automatyczna kontrola jakości

Z katalogu głównego: `DHCPD_PARSER_PATH=/opt/dhcp-tool/bin/dhcpd scripts/check-quality.sh` na obecnym serwerze. Skrypt zatrzymuje się przy
pierwszym błędzie i sprawdza Ruff (lint i format), Django, pytest, Prettier,
ESLint, aktualność typów API, TypeScript, Vitest, produkcyjny build i Playwright.
Build kontrolny używa `.next-quality` z API 8101. Działająca instalacja używa `.next-install` z API 18000. Nie kopiować buildu jakości do usług instalacyjnych. Narzędzia muszą być wcześniej zainstalowane przez
`uv sync --frozen --extra dev` oraz `npm ci`; testy wymagają `.env.test` i Chromium.
Formatowanie: `uv run ruff format .` w backendzie i `npm run format` w frontendzie.

Workflow `.github/workflows/quality.yml` jest przygotowany dla osobnego runnera
Debian 13 z etykietami `self-hosted`, `linux`, `dhcp-tool`, Python 3.13, Node.js 24,
uv i PostgreSQL 17. Runner musi mieć osobną rolę/bazę testową oraz biblioteki
systemowe wymagane przez Chromium. Hasło testowej roli przekazuje sekret
`TEST_POSTGRES_PASSWORD`. Nie uruchamiać tego runnera na serwerze produkcyjnym.
Workflow nie wymaga Dockera. Podłączenie runnera do GitHub nie zostało wykonane;
lokalny skrypt jest dostępny niezależnie od hostingu repozytorium.

Weryfikacja etapu 1: testy Playwright potwierdziły HTTP 200 z prawdziwego Django
przez proxy Next.js oraz poprawny stan awarii. Proxy zachowuje końcowy ukośnik
tras API (`skipTrailingSlashRedirect` i ukośnik w regule rewrite), eliminując
pętlę przekierowań między Next.js i Django. Testy uruchamiane są na osobnych
portach; istniejący produkcyjny podgląd wymaga osobnego buildu i restartu, aby
zastosować nową konfigurację proxy. Opcjonalne testy parsera ISC są pomijane bez `DHCPD_PARSER_PATH`. Na obecnym serwerze użyj `/opt/dhcp-tool/bin/dhcpd`; pozostałe testy backendu nie wymagają parsera.

## Konta i uprawnienia

Etap 2 opisano w `docs/security.md`: procedura administratora bez domyślnego
hasła, tworzenie lokalnych użytkowników, role, przypisania firewalli, CSRF,
wygasanie sesji i atomowy limiter. Migracja `dhcp_tool.0001_initial` została
zastosowana w lokalnej bazie aplikacji i bazie testowej. API obsługuje rejestr urządzeń i CRUD konfiguracji roboczej (`docs/draft-api.md`);
publikacja i historia działają (`docs/history-api.md`); ewidencja wdrożeń i audyt działają (`docs/deployments-api.md`). Migracja 0002 dodaje modele
domenowe i inicjalizuje drafty istniejących urządzeń. Pytest domyślnie używa `--reuse-db`, aby nie usuwać wcześniej
przygotowanej bazy testowej. Testy bazodanowe izolują/wycofują swoje dane,
a TransactionTestCase czyści zawartość bazy testowej; nie przechowywać tam
ręcznie przygotowanych danych, które muszą przetrwać testy.

## Walidacja i podgląd

Etap 4 udostępnia POST validation/ i preview/; wymagane sesja, CSRF i rewizja.
Kontrakt oraz rozróżnienie walidacji danych, ISC i zgodności Gaia opisano
w `docs/validation-api.md`. Opcjonalny DHCPD_PARSER_PATH jest konfiguracją
administratora. Pliki golden obu profili są w backend/tests/fixtures/.
Pełna kontrola z 11 października 2026 korzystała z ISC 4.4.3-P1 w `/opt/dhcp-tool/bin/dhcpd`. Instalator ustawia tę ścieżkę dla działającej aplikacji.

## Publikacja i historia

Etap 5 opisano w `docs/history-api.md`: atomowa publikacja, zapisane bajty,
diff i odtwarzanie draftu. Migracja 0003 dodaje wyzwalacze niezmienności historii
w PostgreSQL. Konta autorów z historią należy dezaktywować zamiast usuwać.

## Panel WWW

Etap 7 zastępuje stronę statusu działającym panelem z logowaniem, konfiguracją,
walidacją i historią. Obsługę, ograniczenia istniejącego podglądu Nginx oraz
weryfikację opisano w [frontend.md](frontend.md). Etap 8 dodaje formularze ręcznej ewidencji i historię zmian przed/po.

## Ewidencja i audyt

Migracja 0004 dodaje rewizję wpisu wdrożenia do kontroli równoczesnych korekt.
Po aktualizacji uruchom `uv run --env-file .env python manage.py migrate` w backendzie.
Kontrakt i reguły wpisów wstecznych opisano w [deployments-api.md](deployments-api.md).
Panel ma zakładki Ewidencja oraz Historia operacji dla wybranego firewalla.
Zmiany frontendu wymagają nowego `npm run build` i restartu procesu Next.js.

Weryfikacja etapu 9: `docs/verification-stage9.md`. Po pobraniu zmian zależności wykonać `uv sync --frozen --extra dev` w backendzie i `npm ci` w frontendzie. Dla instalacji systemd przygotować `.next-install` z API 18000 i użyć procedury aktualizacji w `installation.md`; zwykły build developerski nie aktualizuje wdrożonych usług. Build kontrolny używa osobnego katalogu i testowego API; nie służy do wystawienia panelu.

## Instalacja i utrzymanie

Instrukcja serwera bez kontenerów, usługi systemd, wybrany tryb LAN i aktualizacja: `docs/installation.md`. Szyfrowany eksport oraz odtworzenie do pustej bazy: `docs/backup-restore.md`. Build instalacyjny `.next-install` korzysta z API 18000; build jakości `.next-quality` nadal korzysta z osobnego API testowego 8101. Pełny skrypt jakości uruchamia teraz testy przez Gunicorn i instalacyjny szablon Nginx LAN. Baza testowa i usługi pozostają oddzielone od aplikacji.

## CSV i dokumentacja

CSV całej konfiguracji działa bez nowych migracji i bibliotek: `dhcp_tool/csv_config_views.py`, komponent `csv-transfer.tsx`, testy `test_csv_config.py` i `csv-transfer.test.tsx`. Oddzielne API rezerwacji jest w `csv_views.py`. Format: [csv.md](csv.md). Nie uruchamiać równolegle procesów pytest i Playwright używających tej samej bazy testowej; nie wykonywać buildu ani typegen w trakcie E2E korzystającego z tego samego katalogu Next.js.

[Spis dokumentacji](index.md) prowadzi do instrukcji użytkownika, API i utrzymania. Po zmianie funkcji uaktualnić kontrakty, OpenAPI, status, TODO i instrukcje, a następnie graf. Nie aktualizować historycznych wyników testów na podstawie samej zmiany tekstu.
