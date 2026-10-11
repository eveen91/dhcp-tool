# Kontrakt API v1

API używa JSON UTF-8 i ścieżek `/api/v1/` z końcowym ukośnikiem. Sesje Django
korzystają z cookies tego samego originu. Zapisy wymagają CSRF i uprawnień do
firewalla. Wszystkie odpowiedzi API, także błędy, mają `Cache-Control: no-store`.

## Endpointy dostępne

| Metoda | Ścieżka | Wynik |
| --- | --- | --- |
| GET | `/api/v1/health/` | 200, `{"status":"ok"}`; publiczny status procesu |
| GET | `/api/v1/schema/` | 200, dokument OpenAPI 3.0.3 |
| GET | `/api/v1/auth/session/` | Użytkownik lub null oraz token CSRF |
| POST | `/api/v1/auth/session/` | Logowanie z JSON i nagłówkiem X-CSRFToken |
| DELETE | `/api/v1/auth/session/` | Wylogowanie z CSRF; 204 |
| GET, POST | `/api/v1/firewalls/` | Paginowany odczyt; tworzenie przez administratora |
| GET, PATCH | `/api/v1/firewalls/{firewall_id}/` | Odczyt; metadane i archiwizacja przez administratora |
| GET, POST | `/api/v1/firewalls/{firewall_id}/versions/` | Historia; publikacja z opisem i rewizją |
| GET | `/api/v1/firewalls/{firewall_id}/versions/{version_id}/` | Niezmienna migawka i metadane |
| GET | `/api/v1/firewalls/{firewall_id}/versions/{version_id}/artifact/` | Zapisane bajty dhcpd.conf i SHA-256 |
| POST | `/api/v1/firewalls/{firewall_id}/versions/{version_id}/restore/` | Odtworzenie draftu z kontrolą rewizji |
| GET | `/api/v1/firewalls/{firewall_id}/diff/` | Diff tekstowy i semantyczny |
| GET, POST | `/api/v1/firewalls/{firewall_id}/deployments/` | Lista i ręczna deklaracja wdrożenia |
| GET, PATCH | `/api/v1/firewalls/{firewall_id}/deployments/{deployment_id}/` | Wpis i korekta z uzasadnieniem |
| GET | `/api/v1/firewalls/{firewall_id}/deployments/latest/` | Ostatnie zadeklarowane udane wdrożenie |
| GET | `/api/v1/firewalls/{firewall_id}/audit/` | Historia operacji w zakresie firewalla |
| GET | `/api/v1/firewalls/{firewall_id}/audit/{audit_id}/` | Szczegóły zmian przed/po |
| POST | `/api/v1/firewalls/{firewall_id}/validation/` | Kontrola kompletności MVP i opcjonalnie ISC |
| POST | `/api/v1/firewalls/{firewall_id}/preview/` | Ta sama kontrola oraz tekst pliku bez publikacji |
| GET, PATCH | `/api/v1/firewalls/{firewall_id}/draft/` | Migawka/rewizja; ustawienia globalne |
| GET, POST | `/api/v1/firewalls/{firewall_id}/subnets/` | Lista i tworzenie podsieci |
| GET, PATCH, DELETE | `/api/v1/firewalls/{firewall_id}/subnets/{subnet_id}/` | Odczyt, edycja i usuwanie podsieci |
| GET, PUT, DELETE | `/api/v1/firewalls/{firewall_id}/subnets/{subnet_id}/pool/` | Jedna pula na podsieć |
| GET, POST | `/api/v1/firewalls/{firewall_id}/reservations/` | Lista i tworzenie rezerwacji |
| GET, PATCH, DELETE | `/api/v1/firewalls/{firewall_id}/reservations/{reservation_id}/` | Odczyt, edycja i usuwanie rezerwacji |
| GET | `/api/v1/backups/latest/download/` | Najnowszy zaszyfrowany backup; tylko administrator |
| GET | `/api/v1/firewalls/{firewall_id}/csv/config/export/` | CSV całej konfiguracji roboczej |
| POST | `/api/v1/firewalls/{firewall_id}/csv/config/preview/` | Podpisany podgląd importu bez zapisu |
| POST | `/api/v1/firewalls/{firewall_id}/csv/config/apply/` | Atomowy import całej konfiguracji |
| GET | `/api/v1/firewalls/{firewall_id}/csv/export/` | CSV samych rezerwacji |
| POST | `/api/v1/firewalls/{firewall_id}/csv/preview/` | Podgląd importu rezerwacji |
| POST | `/api/v1/firewalls/{firewall_id}/csv/apply/` | Atomowy import rezerwacji |

Health nie potwierdza dostępności bazy ani zgodności konfiguracji z Gaia.
OpenAPI w `backend/config/openapi.json` opisuje tylko dostępne endpointy.
Nie zawiera konfiguracji urządzeń ani informacji o środowisku serwera.

## Zasoby i kontrakty szczegółowe

Dostępne operacje wyliczono wyżej; konfiguracja robocza jest zaimplementowana i opisana w `docs/draft-api.md`.
Walidacja i podgląd są zaimplementowane (`docs/validation-api.md`). Publikacja, artefakty,
diff i odtwarzanie są zaimplementowane (`docs/history-api.md`). Ewidencja wdrożeń i audyt są zaimplementowane (`docs/deployments-api.md`).
Identyfikatory zasobów domenowych: UUID; daty: ISO 8601 UTC; rewizja: dodatnia
liczba całkowita. Dane firewalla są izolowane przez uprawnienia w backendzie.

| Ścieżka względem `/api/v1/` | Metody i przeznaczenie |
| --- | --- |
| `auth/session/` | GET bieżący użytkownik i token CSRF; POST logowanie; DELETE wylogowanie |
| `firewalls/`, `firewalls/{id}/` | GET, POST; GET, PATCH (w tym archiwizacja) |
| `firewalls/{id}/draft/` | GET konfiguracja i rewizja; PATCH ustawienia globalne |
| `firewalls/{id}/subnets/`, `firewalls/{id}/subnets/{subnet_id}/` | GET, POST; GET, PATCH, DELETE |
| `firewalls/{id}/subnets/{subnet_id}/pool/` | GET, PUT, DELETE; jedna pula na podsieć |
| `firewalls/{id}/reservations/`, `firewalls/{id}/reservations/{reservation_id}/` | GET, POST; GET, PATCH, DELETE |
| `firewalls/{id}/validation/` | POST walidacja wskazanej rewizji, bez publikacji |
| `firewalls/{id}/preview/` | POST kontrola i podgląd dokładnych bajtów wskazanej rewizji |
| `firewalls/{id}/versions/`, `firewalls/{id}/versions/{version_id}/` | GET, POST publikacja; GET niezmienna wersja |
| `firewalls/{id}/versions/{version_id}/artifact/` | GET plik `dhcpd.conf` i SHA-256 |
| `firewalls/{id}/versions/{version_id}/restore/` | POST odtworzenie draftu ze wskazanej wersji |
| `firewalls/{id}/diff/?from={version_id}&to={version_id}` | GET diff tekstowy i semantyczny |
| `firewalls/{id}/deployments/` | GET, POST ręczna deklaracja operatora |

Opisy schematów zasobów i operacje dodajemy do OpenAPI wraz z implementacją.
Wybrany profil jest wymagany: `R81.10` lub `R82.10`; format MVP jest wspólny.
Rezerwacja wskazuje swoją podsieć i adres poza jej pulą. CSV całej konfiguracji
ma osobny podgląd i atomowy zapis do draftu; nie obsługuje importu plików
`dhcpd.conf` ani automatycznego przesyłania konfiguracji na urządzenie.

## Listy i parametry

Paginacja: `page` od 1, `page_size` domyślnie 50, maksymalnie 100.
Odpowiedź: `{"count":123,"next":null,"previous":null,"results":[]}`;
next/previous są linkami względnymi tego samego originu lub null.
Filtry: `search` (nazwa/MAC/IP zależnie od zasobu), `active=true|false`,
`subnet_id` dla rezerwacji, `archived=true|false` dla firewalli.
`ordering` przyjmuje dozwolone pola zasobu: `name`, `created_at`, a dla
rezerwacji także `ip`, `mac`; minus oznacza malejąco. IP sortujemy numerycznie.
Domyślnie listy nazw według `name,id`, historia według `-created_at,id`.
Nieobsługiwane filtry i sortowanie zwracają 400, bez dowolnych pól ORM.

## Błędy i statusy

Format błędu:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Niepoprawne dane.",
    "fields": {"subnets[0].cidr": [{"code": "invalid", "message": "Niepoprawna podsieć."}]}
  }
}
```

Błędy bez pól używają `fields: {}`. Nie zwracamy tracebacków, surowych błędów
bazy/parsera, haseł ani pełnych konfiguracji w komunikatach błędów.

- 200 odczyt/aktualizacja/walidacja, 201 utworzenie i nagłówek Location,
  204 usunięcie lub wylogowanie.
- 400 błędne dane/parametry, 403 brak sesji lub uprawnienia (sesje DRF),
  także błąd CSRF; 404 brak zasobu lub zasób niewidoczny dla użytkownika.
- 405 niedozwolona metoda, 409 konflikt rewizji, 413 zbyt duże żądanie,
  429 ograniczenie prób, 500 ogólny błąd, 503 chwilowa niedostępność.

Każdy zapis konfiguracji roboczej, także DELETE, wymaga nagłówka
`X-Config-Revision` z odczytaną rewizją. Backend sprawdza i aktualizuje rewizję
atomowo. Brak/poprawność nagłówka: 400; nieaktualna rewizja: 409,
`error.code = revision_conflict`, dodatkowo `current_revision` w obiekcie error.
Publikacja wymaga tego samego warunku; nie publikuje nowszych danych po cichu.
Nieaktualny token podglądu CSV również daje 409 `revision_conflict`, ale odpowiedź
tego dodatkowego sprawdzenia może nie zawierać `current_revision`; wykonaj nowy podgląd.
Każde usunięcie wymaga ostrzeżenia i potwierdzenia w interfejsie. Historia jest
niezmienna, a pusta aktywna konfiguracja nie podlega publikacji.

Błędy dostępnych endpointów API używają wspólnego formatu JSON, także 405 i
błędy CSRF. Limit logowania: 5 prób na nazwę konta i 30 na REMOTE_ADDR w oknie
15 minut, współdzielony i atomowy w PostgreSQL. HTTP 429 zawiera Retry-After.
Sesja wygasa po godzinie od logowania; role i przypisania są odczytywane na nowo
przy każdym żądaniu. Szczegóły w `docs/security.md`.

## Backup i CSV

[Backup](backup-restore.md) jest globalnym eksportem bazy i konfiguracji operatora. Endpoint wymaga aktywnego admina, nie przyjmuje ścieżek i zwraca strumień pliku z `X-Backup-SHA256`; brak dostępnej kopii daje 503 `backup_unavailable`.

[CSV](csv.md) dotyczy konfiguracji roboczej jednego firewalla. Eksport wymaga odczytu; podgląd i import wymagają editor/admin, CSRF, aktualnej rewizji i aktywnego firewalla. Zmiana metadanych firewalla przez pełny CSV wymaga admina. Podgląd zwraca token ważny 600 sekund; zapis wiąże go z kontem, firewallem i rewizją. Każde usunięcie wymaga potwierdzenia w panelu; API wymaga `confirm_deletions=true`. CSV nie publikuje wersji ani nie deklaruje wdrożenia.
