# Weryfikacja etapu 10

Data: 2026-10-10. Wdrożenie przygotowane, ale nie zainstalowane jako usługi systemowe. `sudo -n true` wymaga hasła operatora; nie wykonano restartu serwera.

Decyzje użytkownika: HTTP w LAN/VPN bez TLS, przygotować metodę eksportu bazy, brak automatycznego usuwania kopii. Nie wskazano miejsca kopii poza serwerem. Domyślny przygotowany adres: `http://192.168.1.32:8080`; Gunicorn i Next.js słuchają wyłącznie na loopback, na nowych portach 18000/13000.

## Zaliczone kontrole

- `scripts/check-quality.sh` z rzeczywistym parserem ISC: 297 testów backendu, 29 Vitest i 5 Playwright; bez pominięć testów parsera. Ruff, formatowanie, Django check, ESLint, OpenAPI, TypeScript i produkcyjny build przeszły.
- Playwright przechodzi pełny przepływ przez instalacyjny szablon Nginx LAN, Gunicorn z filtrowanym loggerem i produkcyjny Next.js. Serwery testowe korzystają z osobnych portów i osobnej bazy; nie podmieniono działającego podglądu.
- Build `.next-install` z API 18000 przygotowany; kontrolny `.next-quality` nadal używa API testowego 8101. Wygenerowane katalogi są pomijane przez Git, ESLint i Prettier.
- `systemd-analyze verify` zaliczył jednostki w kopiach z podmienionymi ścieżkami na istniejące lokalne programy; sprawdzenie nie uruchamia usług i nie dowodzi ich działania jako docelowe konta.
- Składnia instalatora: `bash -n`. Logrotate: debug z osobnym plikiem stanu, poprawny szablon; harmonogram 02:15 UTC znormalizowany przez systemd-analyze. Rzeczywista rotacja logów działającej instalacji nie była wykonywana.
- Regresje eksportu: szyfrowany roundtrip, SHA-256 i binarna treść artefaktu, identyczne fingerprinty wszystkich tabel, prywatne prawa plików, klucz wykluczony z archiwum, odmowa niepustej bazy, odmowa uszkodzonego archiwum, odmowa eksportowania wewnątrz katalogu konfiguracji.
- Monitor sprawdza API, WWW, rzeczywistą bazę, dysk i wiek/hash eksportu. Regresja potwierdza sukces, wykrycie starej kopii i rzeczywistej odmowy połączenia PostgreSQL bez ujawniania sekretów.
- Wykonano rzeczywisty szyfrowany eksport bieżącej bazy i prywatnej konfiguracji do `.exports`. Odtworzono go do nowej pustej bazy `test_dhcp_export_*`, kontem testowym bez superusera, z uprawnieniami PUBLIC odwołanymi. Wszystkie 21 tabel i 104 rekordy miały identyczne fingerprinty. Odtworzony katalog nie zawierał klucza. Bazę i katalog próbny usunięto. Raport bez danych wrażliwych: `restore-report.json`.

## Stan zadań

T10.1–T10.4, T10.6–T10.8: przygotowane i zweryfikowane w opisanym zakresie. T10.5 pozostaje otwarte dla kopii poza serwerem; lokalny szyfrowany eksport jest gotowy. T10.9 pozostaje otwarte do rzeczywistej instalacji i restartu. Test odtworzenia potwierdza pustą bazę i nowy katalog konfiguracji, nie odtworzenie całego systemu operacyjnego.

Instrukcja operatora: `docs/installation.md`. Eksport i odtworzenie: `docs/backup-restore.md`. Uruchomienie instalatora: `sudo scripts/install-services.sh` z katalogu repozytorium. Po instalacji sprawdzić panel, timery, monitor i zaplanować restart zgodnie z procedurą. Kopię zewnętrzną pobrać ręcznie, a klucz zachować osobno offline.

Nie zmieniono autentycznych `dhcpd.conf` ani `dhcpd copy.conf`; hashe SHA-256 pozostały zgodne. Nie wykonano operacji na urządzeniu Gaia. Zgłoszenie developerskie zależności braces opisane w `dependency-audit.md` pozostaje nierozwiązane, bez zmian tego etapu.

## Sprawdzenie instalacji 2026-10-11

Operator wykonał instalator i restart serwera (boot 02:35:45 czasu lokalnego). API i WWW: active/enabled, lokalny health 200 i strona Next.js 200. Nginx: enabled, ale failed na ExecStartPre (status 1); adres LAN 8080 odmawia połączenia. Backup i monitor: Result=success, ExecMainStatus=0; oba timery enabled. Kontrola monitora nie obejmuje jeszcze zewnętrznego proxy Nginx, więc jej sukces nie oznacza dostępności panelu w LAN. Log błędu Nginx wymaga sudo; oczekujemy wyniku diagnostyki operatora. T10.9 pozostaje otwarte do naprawy Nginx i potwierdzenia pełnego przepływu.

Log dostarczony przez operatora potwierdził przyczynę: `bind() to 192.168.1.32:8080 failed (99: Cannot assign requested address)` w ExecStartPre. Późniejsze `sudo nginx -t` przeszło. Przygotowano drop-in systemd ponawiający start co 5 sekund; wymaga zastosowania przez operatora. Instalator zawiera tę poprawkę.

Operator zastosował drop-in. Potwierdzono Nginx active/enabled, Restart=on-failure i RestartUSec=5s. Panel `http://192.168.1.32:8080/` zwraca HTTP 200, `/api/v1/health/` HTTP 200 i status ok. Backup i monitor nadal Result=success. Pozostaje sprawdzenie rzeczywistego restartu po zastosowaniu poprawki; nie wykonano go automatycznie.

## Odbiór startu po restarcie — 2026-10-11

Potwierdzono nowy boot o 03:14:21 PDT. API active od 03:15:01, WWW od 03:15:02, Nginx od 03:15:09; wszystkie trzy jednostki active/enabled. Oba timery enabled, backup i monitor Result=success/ExecMainStatus=0. Panel i health przez LAN HTTP 200; użytkownik potwierdził działanie strony. T10.9 zamknięte. T10.5 nadal otwarte dla kopii poza serwerem. Powyższe wpisy o oczekiwaniu na instalację i reboot opisują wcześniejszy stan.


## Pobieranie backupu w przeglądarce — 2026-10-11

Dodano administratorowi pobieranie najnowszej zaszyfrowanej kopii w Administracji. Root publikuje zweryfikowaną kopię przez `publish-backup.py`, a API odczytuje ją z osobnego katalogu; klucz i oryginały nie są udostępnione API. Instalator i jednostka backupu uwzględniają publikowanie. Przy aktualizacji instalator używa trwałego parsera `/opt/dhcp-tool/bin/dhcpd`.

Zaliczone: 302 testy backendu (z rzeczywistym parserem ISC), 30 Vitest i 6 Playwright przez Nginx/Gunicorn/produkcyjny Next.js. Nowy test przeglądarkowy pobrał zaszyfrowany plik, sprawdził nazwę, SHA-256 i odszyfrował go do identycznej testowej treści. Testy backendu potwierdzają odmowę dla kont nieaktywnych i innych ról, bezpieczny błąd braku kopii, blokadę wyboru ścieżki i zachowanie poprzedniej kopii po błędzie integralności. Ruff, formatowanie, Django check, ESLint, OpenAPI i TypeScript przeszły. Składnia instalatora i weryfikacja jednostki systemd przeszły. Pierwszy przebieg pełnych testów korzystał z usuniętego po restarcie parsera w `/tmp`; ponowienie z zainstalowanym parserem przeszło.

Kod i prywatna konfiguracja są przygotowane; aktualizacja działającego wydania wymaga uruchomienia instalatora przez operatora z sudo. Testy użyły osobnej bazy i testowego pliku, nie pobierały rzeczywistego backupu z działającej instalacji. T10.5 nadal pozostaje otwarte do rzeczywistego pobrania na inny komputer i potwierdzenia osobnej kopii klucza.

Operator zainstalował wydanie `20261011T144808Z`. Potwierdzono API, WWW i Nginx active, panel HTTP 200, endpoint pobierania HTTP 403 bez sesji administratora, backup Result=success/ExecMainStatus=0 oraz katalog publikacji root:dhcp-api z prawami 750. Rzeczywiste pobranie po zalogowaniu i osobna kopia klucza wymagają potwierdzenia operatora.

## Domknięcie utrzymania — 2026-10-11

Użytkownik potwierdził pobranie rzeczywistego backupu na inny komputer oraz klucza w odpowiedzi na pytanie o oddzielną kopię. T10.5 zamknięte; nie skonfigurowano automatycznej replikacji ani usuwania kopii. Po instalacji CSV aktywne wydanie to `20261011T162819Z`. API, WWW i Nginx active; health w LAN HTTP 200. Wcześniejsze wpisy o oczekującym pobraniu oraz wydaniu `20261011T144808Z` zachowują chronologię. Aktualny stan: [project-status.md](project-status.md).
