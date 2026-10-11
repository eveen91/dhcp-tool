# Status projektu — 2026-10-11

Wszystkie zadania MVP 0–11 w [TODO](../TODO.md) są ukończone. CSV całej konfiguracji wdrożono dodatkowo na polecenie użytkownika. Szczegółowy [odbiór MVP](acceptance-mvp.md) zachowuje granice potwierdzonej zgodności Gaia.

## Działająca instalacja

| Element | Stan zweryfikowany |
| --- | --- |
| Panel | `http://192.168.1.32:8080`, LAN/VPN, HTTP zgodnie z decyzją użytkownika |
| Wydanie | `/opt/dhcp-tool/current` → `/opt/dhcp-tool/releases/20261011T162819Z` |
| API, WWW, Nginx | Wszystkie `active`; health przez LAN zwraca HTTP 200 |
| Backend | Gunicorn, loopback 18000, profil `config.settings.lan` |
| Frontend | Next.js, loopback 13000, build `.next-install` z API 18000 |
| Backup i monitor | Ostatni `Result=success`, `ExecMainStatus=0`; oba timery enabled |
| Backup lokalny | Codziennie 02:15 UTC, opóźnienie do 5 minut; brak automatycznego usuwania |
| Kopia poza serwerem | Użytkownik potwierdził pobranie backupu oraz klucza; T10.5 zamknięte |
| CSV | Użytkownik potwierdził eksport i import na działającym panelu |
| Konta | Użytkownik potwierdził logowanie admina; brak domyślnego hasła |

Stan usług jest odczytem z chwili przeglądu dokumentacji, nie gwarancją stałej dostępności. Start po rzeczywistym restarcie zweryfikowano wcześniej w T10.9. Kopie poza serwerem są ręczne; lokalny timer nie wykonuje zewnętrznej replikacji. Klucz należy przechowywać oddzielnie od archiwum.

## Ostatnie dowody jakości

Kod CSV przeszedł 320 testów pytest na oddzielnym PostgreSQL, 32 testy Vitest, sześć istniejących scenariuszy Playwright oraz nowy scenariusz CSV po poprawieniu selektora. Lint, formatowanie, Django check, OpenAPI, TypeScript i build przeszły. Playwright sprawdza prawdziwe API przez Nginx/Gunicorn/produkcyjny Next.js, pobrane bajty i testową kopię backupu; axe obejmuje ekran 390 px. [Raport CSV](verification-csv.md) opisuje przebiegi.

Podczas aktualizacji dokumentacji nie powtarzano testów aplikacji ani audytu zależności. Sprawdzono lokalne odnośniki, zgodność opisów z kodem i stan usług; wyniki z wcześniejszych przebiegów są datowane.

## Rozszerzenie: wiele adresów interfejsów

W kodzie przygotowano obsługę 1–64 adresów interfejsów podsieci, np. adresów
obu członków klastra. Każdy jest chroniony przed kolizją z pulą i rezerwacją.
API i CSV zachowują klucz `interface_address` jako pojedynczy tekst lub listę;
historyczne konfiguracje nie wymagają migracji. Szczegóły w [generatorze](generator.md).

Weryfikacja rozszerzenia 2026-10-11: pełny `scripts/check-quality.sh` z parserem
`/opt/dhcp-tool/bin/dhcpd` przeszedł: 336 testów pytest, 33 testy Vitest i 8
scenariuszy Playwright przez Nginx/Gunicorn/produkcyjny Next.js. Nowy scenariusz
sprawdza zapis dwóch adresów, odczyt po przeładowaniu, odrzucenie rezerwacji
dla obu członków oraz dostępność formularza przez axe. Testy backendu obejmują
kolizje puli, niepoprawne adresy, duplikaty, CSV i przywracanie wersji.
Lint, formatowanie, Django check, OpenAPI, TypeScript i build także przeszły.
To rozszerzenie wymaga instalacji nowego wydania; powyższy stan działającej
instalacji pochodzi z wcześniejszego przeglądu. Graf w `graphify-out` oznaczono
`.needs_update`, ponieważ po zmianie kodu nie odzwierciedla tej funkcji.

## Gaia: potwierdzony zakres i brakujące dowody

MVP obejmuje wiele podsieci, jedną aktywną pulę na aktywną podsieć i rezerwacje poza pulą. Użytkownik potwierdził wspólny format R81.10/R82.10 na podstawie `dhcpd copy.conf`. Autentyczne próbki i syntetyczne golden files mają odrębne pochodzenie. Parser ISC 4.4.3-P1 sprawdza składnię upstream, a API zachowuje `gaia_compatibility=unverified`.

Nie wykonano testu wygenerowanego pliku ani rezerwacji na urządzeniach obu wersji. Ukończone MVP nie oznacza takiej certyfikacji. Priorytet kolejnych prac: dowody zgodności Gaia przed rozszerzaniem dyrektyw. Szczegóły: [generator](generator.md).

## Otwarte decyzje i rozszerzenia

Docelowa skala i liczba równoczesnych operatorów, RPO/RTO, formalny standard dostępności oraz środowisko przeglądarek nie zostały ustalone. Pomiar 50 firewalli i 5000 rezerwacji nie wyznacza limitu aplikacji ani Gaia. Historia i backupy nie są automatycznie usuwane; nie ustalono okresu przechowywania historii ani przyszłej procedury jej ręcznego usuwania.

Poza zrealizowanym zakresem: importer `dhcpd.conf`, SSO, zatwierdzanie zmian, dodatkowe opcje DHCP, API integracyjne/IPAM, wiele pul i podsieci tylko z rezerwacjami. Lista: [features_to_add.md](../features_to_add.md). CI wymaga podłączenia osobnego runnera. Zgłoszenie developerskiej zależności `braces` opisuje datowany [audyt](dependency-audit.md). Pełną odbudowę systemu operacyjnego trzeba sprawdzić osobno od zaliczonego restore pustej bazy.
