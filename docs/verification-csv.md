# Weryfikacja rozszerzenia CSV — 2026-10-11

Zakres zatwierdzony przez użytkownika: cała konfiguracja, obejmująca metadane firewalla, opcje globalne, podsieci, jedną pulę per sieć i rezerwacje.

- Backend: 320 testów pytest przeszło na oddzielnej bazie testowej PostgreSQL. Dodano 18 testów CSV: 11 dla rezerwacji i 7 dla całej konfiguracji.
- Testy obejmują podgląd bez zapisu, atomowy import, rollback przy błędzie audytu, zachowanie identyfikatorów i dat utworzenia, dodawanie całej podsieci, potwierdzanie usunięć kaskadowych, whitelistę opcji, role, zmianę rewizji, podpis i przypisanie tokenu, limity, błędny format oraz ochronę komórek arkusza przed formułami.
- Frontend: 32 testy Vitest przeszły, w tym wymaganie podglądu i indywidualnego potwierdzenia usunięcia oraz sam eksport dla czytelnika.
- Ruff, formatowanie, Django check, ESLint, OpenAPI, TypeScript i produkcyjny build przeszły.
- Sześć istniejących scenariuszy Playwright przeszło przez Nginx, Gunicorn i produkcyjny Next.js. Nowy scenariusz CSV sprawdził rzeczywisty eksport pięciu rodzajów rekordów, zmianę opcji globalnych i IP, wczytanie pliku, podgląd i zapis do API. Po poprawieniu błędnego selektora testowego ten scenariusz przeszedł; dodatkowo sprawdza WCAG przez axe oraz ekran 390 px.
- Pliki źródłowe `dhcpd.conf` i `dhcpd copy.conf` zachowały dotychczasowe SHA-256. Nie wykonano weryfikacji na urządzeniu Gaia; CSV korzysta z istniejącej whitelisty i reguł generatora.

Stan przed instalacją: kod i build przygotowano w checkout. Instalacja serwerowa wymagała uruchomienia przez operatora `sudo /mnt/dhcp-tool/scripts/install-services.sh`; sama implementacja i testy nie zmieniają działającego wydania `/opt/dhcp-tool/current`. Brak nowych migracji i zależności systemowych. Po zmianach CSV graf początkowo oznaczono jako wymagający odświeżenia.

## Odbiór działającej instalacji

Operator wykonał instalator; `/opt/dhcp-tool/current` wskazuje wydanie `20261011T162819Z`. API, WWW i Nginx active, health w LAN HTTP 200; kod wydania zawiera pełne trasy CSV. Użytkownik potwierdził logowanie administratora, poprawny eksport oraz import. Następnie potwierdził pobranie rzeczywistego backupu i klucza; T10.5 zamknięte. Wcześniejszy akapit o oczekującej instalacji dotyczy etapu przygotowania. Graf odświeżono podczas aktualizacji dokumentacji; aktualny zakres i ograniczenia podaje [raport grafu](../graphify-out/GRAPH_REPORT.md).
