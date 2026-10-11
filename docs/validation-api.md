# Walidacja i podgląd konfiguracji — etap 4

POST `/api/v1/firewalls/{firewall_id}/validation/` sprawdza gotowość konfiguracji
MVP oraz opcjonalnie składnię ISC. POST `/api/v1/firewalls/{firewall_id}/preview/`
wykonuje tę samą kontrolę i zwraca dodatkowo kompletny tekst pliku w `content`.
Oba endpointy przyjmują pusty obiekt JSON `{}` i wymagają sesji, CSRF oraz
`X-Config-Revision`. Korzystają wyłącznie z zapisanej konfiguracji bieżącego
firewalla; nie przyjmują tekstu DHCP, ścieżki parsera ani konfiguracji od klienta.

Operacje są dostępne wszystkim rolom z prawem odczytu danego firewalla, także
zarchiwizowanego. Nie zwiększają rewizji, nie zapisują audytu, wersji ani artefaktu.
Podgląd nie jest publikacją i nie oznacza wdrożenia na urządzeniu.

## Wynik

Udana odpowiedź HTTP 200 zawiera:

- revision — rewizja wykorzystanej migawki;
- data_validated — true po przejściu reguł danych i kompletności MVP;
- syntax_status — zakres i wynik kontroli parserem;
- parser_version i parser_return_code — informacje o wykonanej kontroli lub null;
- gaia_compatibility — unverified;
- artifact_bytes — długość dokładnych bajtów ASCII/LF;
- sha256 — hash tych samych bajtów;
- content — tekst wyłącznie w udanym podglądzie.

Zapis równoczesny z pracą parsera może już utworzyć nowszą rewizję. Odpowiedź
pozostaje przypisana do przechwyconej rewizji, podanej także w nagłówku
`X-Config-Revision`. Kontrola nie może zostać wykorzystana do publikacji innej
rewizji. Publikacja w etapie 5 ponownie przechwytuje i waliduje swoją migawkę (`history-api.md`).
Blokadę PostgreSQL zwalniamy przed generowaniem i uruchamianiem procesu parsera.

## Reguły i błędy

Wspólna funkcja `validate_configuration(config, complete=False)` obsługuje
edycję draftu i pozwala chwilowo pominąć pulę lub wszystkie aktywne podsieci.
`render_mvp(config)` i `prepare_artifact(config)` używają complete=True:
konfiguracja musi mieć aktywną podsieć, a każda aktywna podsieć dokładnie jedną
aktywną pulę. Rezerwacje są poza pulą. Nieaktywne dane także przechodzą walidację
pól i relacji, ale nie są emitowane. Nie wolno ominąć kontroli błędnych danych
przez samo ustawienie active=false. Samo active wymaga typu boolean.

Reguły adresacji, dziedziczenia i białą listę opisano w `generator.md`.
Wartość null opcji lokalnej oznacza dziedziczenie. MAC normalizujemy do małych
liter z dwukropkami. W module niskiego poziomu `render()` zachowano istniejącą
obsługę odłożonych wariantów; nie jest ona rozszerzeniem MVP aplikacji.

HTTP 400 wskazuje błędy w error.fields. Dla danych obiektowych ścieżki zawierają
UUID, np. `subnets.UUID.reservations.UUID.ip` lub `subnets.UUID.pool.UUID.start`.
Nie odsyłamy surowych wartości, komunikatów SQL czy parsera. Niepoprawna rewizja
ma 400; nieaktualna rewizja 409 z current_revision. Brak uprawnień/CSRF daje 403,
a obcy firewall 404. Błędy danych są raportowane przed uruchomieniem parsera.

## Parser i zgodność Gaia

Administrator może ustawić `DHCPD_PARSER_PATH` na absolutną ścieżkę zaufanej
binarki ISC. Brak ustawienia albo niedostępny plik daje parser_unavailable,
data_validated=true i HTTP 200. To sama walidacja danych, bez potwierdzenia składni.
Nie ustawiamy automatycznie ścieżki do tymczasowo wyodrębnionej binarki z testów.

syntax_checked oznacza kod 0 z kontroli ISC. syntax_error daje HTTP 400,
parser_error i parser_timeout HTTP 503. Te odpowiedzi zawierają raport kontroli
oraz obiekt error, ale nie zawierają content. Parser ma ograniczenie 5 sekund,
1 MiB wejścia i 8192 bajtów wyjścia; działa bez powłoki i nasłuchu usługi DHCP.
Wrażliwe odpowiedzi, w tym błędy, mają no-store.

Oba profile MVP mają format wspólny zgodnie z deklaracją użytkownika i referencją
`dhcpd copy.conf`. Pliki golden w `backend/tests/fixtures/mvp-R81.10.conf`
i `mvp-R82.10.conf` są syntetycznymi oczekiwanymi wynikami, obejmującymi wiele
podsieci, pojedyncze pule i rezerwacje. Nie zastępują próbki Check Point ani testu
na appliance. Akceptacja przez ISC również nie dowodzi działania na Gaia;
`gaia_compatibility` zawsze pozostaje unverified. Oryginalnych plików użytkownika
nie zmieniamy.

## Podgląd CSV a podgląd pliku

`csv/config/preview/` sprawdza propozycję zmian CSV i zwraca podpisany token oraz różnice, bez uruchamiania parsera ISC. `preview/` opisane w tym dokumencie sprawdza zapisaną konfigurację, kompletność MVP i opcjonalną składnię ISC, po czym zwraca plik DHCP. Po zastosowaniu CSV wykonaj ten drugi podgląd przed publikacją. Oba wyniki pozostawiają zgodność na urządzeniu Gaia jako niezweryfikowaną.
