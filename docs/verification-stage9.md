# Weryfikacja etapu 9

Raport historyczny etapu 9. Aktualny stan instalacji i rozszerzenia CSV opisuje [project-status.md](project-status.md); wcześniejsze liczby testów nie są zmieniane przy aktualizacji dokumentacji.

Data: 2026-10-10. Wynik: 285 testów backendu i 115 subtestów, bez pominięć, z PostgreSQL 17 i rzeczywistym ISC DHCP 4.4.3-P1; 29 testów Vitest; 5 scenariuszy Playwright na produkcyjnym buildzie Next.js 16.4.0. Ruff, formatowanie, Django check, ESLint, OpenAPI, TypeScript i build przeszły. Polecenia: `scripts/check-quality.sh` oraz pełny `pytest -q --tb=short` z `DHCPD_PARSER_PATH` wskazującym rzeczywisty parser. Pierwszy przebieg skryptu bez tej zmiennej pominął pięć testów parsera; osobny pełny przebieg zaliczył wszystkie 285.

## Bezpieczeństwo i awarie

Macierz rzeczywistych endpointów obejmuje cztery role, CSRF, metadane, draft, podsieci, pule, rezerwacje, publikację i korekty ewidencji. Regresje poprzednich etapów sprawdzają obce identyfikatory także przy dostępie do obu urządzeń, zakres firewalla, whitelistę i wstrzyknięcia. Publikacja i edycja równoległa są testowane na PostgreSQL.

Nowy test rzeczywistej odmowy połączenia PostgreSQL sprawdza bezpieczny błąd, no-store i brak wersji, artefaktu oraz wpisu audytu. Istniejące testy parsera i błędów zapisu potwierdzają rollback. Przeglądarka otrzymuje kontrolowany błąd 503 publikacji: formularz zachowuje dane, wersja nie powstaje, a świadome ponowienie działa. Ten test UI symuluje odpowiedź na granicy HTTP; rzeczywiste awarie parsera i bazy sprawdzają osobne testy backendu.

Testy uruchamiają osobny Nginx według `docs/nginx-app.conf`, z nadrzędnym cache włączonym celowo do kontroli nadpisania. Aktualizacja danych nie oddaje starej odpowiedzi; drugi anonimowy klient oraz klient po wylogowaniu nie otrzymują prywatnych danych. Sprawdzane są Nginx i proxy produkcyjnego Next.js, nagłówki no-store oraz Vary Cookie. Odmowa połączenia upstream daje bezpieczne JSON 503. Log Nginx zawiera wyłącznie metodę, status i czas; nie zawiera URL, domen konfiguracji, loginów ani haseł. Surowe błędy upstream są wyłączone w tym szablonie; status błędu pozostaje w logu dostępu. Szablon nie został zainstalowany w działającej usłudze.

## Dostępność

Axe (WCAG 2 A/AA i 2.1 AA) nie wykazał naruszeń na sprawdzonych stanach: logowanie, lista i formularz firewalla, konfiguracja na 390 px, szczegóły wersji, ewidencja, audyt i dialog usunięcia. Playwright sprawdza Tab/Shift+Tab/Escape, zamknięcie i powrót fokusu dialogów, fokus błędnego pola, ostrzeżenia usuwania, długie nazwy i polskie znaki. Przegląd obejmuje kontrast widocznych elementów, etykiety i komunikaty. Wynik dotyczy testowanych stanów; automatyczny skan nie stanowi pełnej certyfikacji WCAG ani testu wszystkich technologii asystujących.

## Wydajność i limity

Fixture: 50 firewalli oraz konfiguracja z 5000 rezerwacji. Pięć powtórzeń, lokalny Django test client i PostgreSQL; bez kosztu sieci i przeglądarki. Liczby są pomiarem tego serwera, nie SLA ani limitem Gaia. Pełne dane: `performance-report.json`.

| Operacja | Mediana ms | Maksimum ms | Zapytania do bazy |
| --- | ---: | ---: | ---: |
| Lista firewalli | 4,64 | 6,32 | 6 |
| Lista rezerwacji | 9,24 | 14,26 | 7 |
| Wyszukiwanie rezerwacji | 17,35 | 23,60 | 7 |
| Pełny draft | 96,34 | 138,64 | 11 |
| Generator | 123,56 | 256,23 | 0 |
| Diff wersji | 74,96 | 123,94 | 4 |
| Lista wersji | 14,91 | 16,75 | 7 |

Lista rezerwacji wykonuje 7 zapytań zarówno dla 1, jak i 100 rekordów. Lista wersji pobiera wyłącznie potrzebne pola JSON i długość artefaktu; nie wczytuje całego snapshotu ani binarnego pliku. Audyt listuje bez snapshotów before/after, ewidencja bez snapshotu wersji. Regresje sprawdzają projekcję SQL. EXPLAIN ANALYZE wyszukiwania wykorzystał istniejące indeksy powiązań i filtrował 5000 rekordów w około 2 ms; brak podstaw do dodatkowego indeksu przy tym pomiarze.

Wszystkie listy mają maksymalnie 100 pozycji na stronę i numer strony 1–2147483647. API odrzuca powtórzone parametry i query string ponad 2048 bajtów. Wejście JSON ma limit 64 KiB. Połączenie DB: 3 s, oczekiwanie na blokadę: 3 s, pojedyncze zapytanie SQL: 10 s. Parser: 5 s, wyjście 1 MiB, diagnostyka 8 KiB. Nginx: połączenie upstream 3 s, read timeout 15 s. Są to limity poszczególnych faz, nie jeden globalny deadline procesu. Pełny draft i pobranie artefaktu celowo zwracają kompletną konfigurację; w pomiarze draft miał 1 285 742 bajty, artefakt 445 505 bajtów.

Przegląd zależności wraz z nierozwiązanym zgłoszeniem developerskim opisano w `dependency-audit.md`. Wdrożenie usług, HTTPS i instalacja szablonu panelu pozostają etapem 10. Build `.next-quality` nie podmienia uruchomionej aplikacji. Pliki wzorcowe `dhcpd.conf` i `dhcpd copy.conf` zachowano. Test ISC nie jest certyfikacją zgodności appliance Gaia.
