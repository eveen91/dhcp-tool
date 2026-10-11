# Konta i bezpieczeństwo API

## Wdrożony zakres

Działają sesje, lokalne role, przypisania firewalli, rejestr urządzeń i edycja
konfiguracji roboczej (etap 3, `docs/draft-api.md`). Publikacja, wersje, artefakty, porównania i odtwarzanie draftu działają w etapie 5
(`docs/history-api.md`). Ewidencja wdrożeń i audyt są dostępne (`docs/deployments-api.md`). Centralna kontrola zakresu obejmuje trasy podrzędne,
a nowe trasy muszą zadeklarować uprawnienie i powiązania identyfikatorów.
Modele `Firewall`, `Account`, `FirewallAccess`, `LoginBucket` i migracja
`dhcp_tool.0001_initial` tworzą fundament zabezpieczeń; migracja 0002 dodaje
konfigurację roboczą, audyt i modele historii; migracja 0003 zabezpiecza niezmienność wersji i artefaktów, a 0004 dodaje rewizje wpisów wdrożeń.

## Utworzenie administratora

Nie istnieje konto ani hasło domyślne. Z katalogu `backend/`:

```bash
uv run --env-file .env python manage.py migrate --noinput
uv run --env-file .env python manage.py createsuperuser
```

Hasło podaje się interaktywnie, bez argumentów powłoki i bez wpisywania go do
repozytorium. Obowiązują walidatory Django i minimum 12 znaków. Aktywny Django
superuser ma rolę administratora i dostęp do wszystkich firewalli. `is_staff`
samo w sobie nie nadaje dostępu do API. Panel logowania i Administracja są dostępne. Tworzenie kont i przypisania pozostają poleceniami administratora serwera.

## Role i przypisania

| Rola | Odczyt | Edycja konfiguracji / publikacja | Ewidencja wdrożeń | Administracja |
| --- | --- | --- | --- | --- |
| `reader` | Tak | Nie | Nie | Nie |
| `editor` | Tak | Tak | Nie | Nie |
| `operator` | Tak | Nie | Tak | Nie |
| `admin` | Tak | Tak | Tak | Tak |

Poza administratorem dostęp dotyczy wyłącznie jawnie przypisanych firewalli.
Konto bez `Account` nie ma dostępu do firewalli. Administrator ma globalny
zakres, a historyczne dane nie są kasowane przez zmianę uprawnień.

Nowy użytkownik, z interaktywnym hasłem i bez domyślnych przypisań:

```bash
uv run --env-file .env python manage.py create_local_user operator1 --role reader
```

Nadanie roli i zastąpienie listy dostępnych urządzeń (UUID zastąpić rzeczywistym):

```bash
uv run --env-file .env python manage.py set_user_access operator1 --role editor --firewall UUID
```

`--firewall` można powtarzać. Pominięcie tego argumentu zachowuje przypisania;
`--clear-firewalls` usuwa je wszystkie. Rola admin oznacza globalny dostęp.
Polecenia sprawdzają wejście przed zmianą i zapisują rolę/przypisania atomowo.
Nie tworzą firewalli — administrator korzysta z POST `/api/v1/firewalls/`. Zmiana roli lub odebranie
przypisania działa przy kolejnym żądaniu, także dla istniejącej sesji.

Zmiana hasła: `uv run --env-file .env python manage.py changepassword operator1`.
Django unieważnia wtedy istniejące sesje użytkownika.

## Sesje i CSRF

GET `/api/v1/auth/session/` zwraca `user` i `csrf_token`, również anonimowo.
POST przyjmuje wyłącznie `username` i `password` w JSON, do 4096 bajtów.
POST i DELETE wymagają nagłówka `X-CSRFToken`. Logowanie obraca identyfikator
sesji i token CSRF; po nim należy używać tokenu z nowej odpowiedzi.
Niepowodzenie ma jednakowy komunikat dla nieznanego, nieaktywnego i błędnie
uwierzytelnionego konta. Nie ma publicznego tworzenia kont.

Sesje są przechowywane w PostgreSQL i wygasają po godzinie od logowania.
Cookies sesji i CSRF mają HttpOnly, SameSite=Lax i Secure w ustawieniach
produkcyjnych. Frontend pobiera token z JSON, nie z `document.cookie`.
Development na lokalnym HTTP wyłącza Secure. Produkcja wymaga HTTPS oraz
prawidłowego `DJANGO_CSRF_TRUSTED_ORIGINS`; nie należy dopuszczać dowolnych
originów ani wyłączać CSRF. Dla developerskiego proxy dopuszczone są dokładne
adresy localhost/127.0.0.1 na porcie 3000; E2E jawnie dopuszcza tylko swój port.
Obecna instalacja używa świadomie wybranego profilu `config.settings.lan` przez HTTP w LAN/VPN: Secure i przekierowanie HTTPS są wyłączone, sesje/CSRF i ograniczenia dostępu pozostają aktywne. Pełny Nginx udostępnia panel i API; dawnej konfiguracji statusu nie instalować ponownie.

## Limiter i utrzymanie

Każda poprawnie sformowana próba logowania zużywa budżet: 5 prób na nazwę konta
oraz 30 na REMOTE_ADDR w 15 minut. Limiter korzysta z transakcji i blokad wierszy
PostgreSQL; testy obejmują współbieżne procesy/połączenia. HTTP 429 zawiera
Retry-After. Zablokowany adres nie tworzy wpisów dla kolejnych nowych nazw.
Klucze są HMAC; tabela nie przechowuje jawnych nazw kont ani adresów klienta.
Po upływie okna budżet jest automatycznie resetowany przy następnej próbie.

Nie ufamy X-Forwarded-For przesłanemu przez klienta. Za reverse proxy limit
REMOTE_ADDR może być wspólny dla klientów tego proxy. Obecna konfiguracja LAN zachowuje ten wspólny limit; nie implementuje rozpoznawania adresu klienta z X-Forwarded-For. Nie wystawiać bezpośrednio backendu w celu obchodzenia limitu.
W etapie utrzymania należy regularnie usuwać wygasłe sesje (`clearsessions`)
i wiersze LoginBucket z expires_at w przeszłości; nie dotyczy to historii
konfiguracji, której retencja pozostaje osobną decyzją.

## Wymagania dla kolejnych endpointów

- Wszystkie trasy urządzenia używają parametru `firewall_id`. Middleware
  rozwiązuje go przez `visible_firewalls` i odmawia nieprzypisanego zasobu (404).
- Trasy etapu 3 deklarują osobne akcje dla metod HTTP przez `method_actions`.
  Mutacje nowych tras mogą również deklarować `@firewall_action('edit')`, `'deploy'` lub `'admin'`.
  Brak deklaracji odmawia mutacji także administratorowi. Handler musi
  dodatkowo ograniczać metody HTTP; dekorator określa operację, nie metodę.
- Każdy identyfikator podrzędny w ścieżce deklaruje
  `@firewall_child('version_id', Version, firewall_lookup='firewall_id')`.
  Dla relacji pośrednich lookup wskazuje rzeczywistą ścieżkę do firewalla.
  Brak deklaracji blokuje dostęp. Zweryfikowany obiekt jest dostępny jako
  `request.scoped_objects['version_id']`; firewall jako `request.firewall`.
- Diff deklaruje oba identyfikatory `from` i `to` z `source='query'`.
  Nie wolno porównywać globalnie pobranych wersji z różnych firewalli.
- Zależności przesyłane w JSON walidujemy w obrębie `request.firewall`,
  przez `scoped_object`; pola właściciela nadaje backend. Lista zasobów
  zawsze filtruje po przypisaniach. Nie przyjmujemy uprawnień od klienta.
- Każdy endpoint konfiguracji/historii/pliku otrzymuje regresje dostępu dla
  obcego firewalla oraz obiektu podrzędnego innego właściciela. Obecne testy
  middleware używają prawdziwych modeli uprawnień i tras istniejących tylko w
  testowym URLconf; nie zastępują testów przyszłych zasobów domenowych.

## Cache i logi

Odpowiedzi API, w tym błędy i odmowy CSRF, mają `Cache-Control: no-store`,
`Pragma: no-cache` i `Vary: Cookie`. Domyślny cache aplikacji jest DummyCache;
sesje nie korzystają z cache. Proxy nie może nadpisywać tych zasad.

Błędy API są JSON, bez strony debug i tracebacków, również w development.
Formatter logów zapisuje wyłącznie poziom, kod zdarzenia z białej listy i
opcjonalny status HTTP. Ignoruje wiadomość, request, exc_info i stack_info;
nie serializuje haseł, cookies, body, SQL ani pełnych konfiguracji.
Diagnostyka jest przez to ograniczona do bezpiecznych kodów zdarzeń.
Audyt zmian danych i trwałe wpisy autorstwa są zaimplementowane, również dla CSV; są dostępne w Historii operacji.

Źródła zasad Django: [uwierzytelnianie](https://docs.djangoproject.com/en/5.2/topics/auth/default/),
[CSRF](https://docs.djangoproject.com/en/5.2/howto/csrf/),
[sesje](https://docs.djangoproject.com/en/5.2/topics/http/sessions/).

## Historia i publikacja

Etap 5 ma rzeczywiste regresje dostępu do historii, plików, diffu i odtwarzania,
także przy przypisaniu obu firewalli. Publikacja ponownie sprawdza dostęp, aktywność konta i ważność hasła sesji po
generowaniu poza transakcją. PostgreSQL blokuje zmiany i usuwanie opublikowanych
wersji i artefaktów; konta autorów z historią należy dezaktywować zamiast usuwać.


## Konta w instalacji systemd

W działającej instalacji używaj aktualnego prywatnego środowiska i kodu z `/opt/dhcp-tool/current`. Utwórz konto z interaktywnym hasłem:

```sh
sudo /usr/bin/python3 /opt/dhcp-tool/current/scripts/run-with-env.py \
  /etc/dhcp-tool/backend.env \
  /opt/dhcp-tool/current/backend/.venv/bin/python \
  /opt/dhcp-tool/current/backend/manage.py create_local_user operator1 --role reader
```

Aby zmienić rolę, zastąp ostatnie polecenie przez `set_user_access operator1 --role editor --firewall rzeczywisty_uuid`. Zastąp `rzeczywisty_uuid` identyfikatorem urządzenia. Nie przekazuj hasła jako argumentu i nie kopiuj sekretów do terminala ani dokumentacji. Pobieranie globalnego backupu jest dostępne wyłącznie aktywnemu administratorowi. Procedura: [backup-restore.md](backup-restore.md).

## Reset hasła w działającej instalacji

Hasło jest hashowane w bazie; nie można odczytać jego pierwotnej wartości. Ustaw nowe hasło istniejącego konta `admin` interaktywnie:

```sh
sudo /usr/bin/python3 /opt/dhcp-tool/current/scripts/run-with-env.py \
  /etc/dhcp-tool/backend.env \
  /opt/dhcp-tool/current/backend/.venv/bin/python \
  /opt/dhcp-tool/current/backend/manage.py changepassword admin
```

Zastąp `admin` nazwą właściwego konta. Hasło wpisz dwukrotnie; terminal nie wyświetla znaków. Obowiązuje minimum 12 znaków i walidatory Django. Zmiana unieważnia wcześniejsze sesje. Jeśli konto nie istnieje, użyj `create_local_user`, a nie resetu. Użytkownik potwierdził logowanie administratora po instalacji.

## Dostęp do CSV i backupów

Każda rola z dostępem do firewalla może eksportować CSV. Podgląd i zapis wymagają editor/admin, CSRF i rewizji; zarchiwizowany firewall nie przyjmuje importu. Tylko admin może zmieniać metadane firewalla. Token podglądu jest podpisany, przypisany do konta i firewalla, ważny 10 minut; nieaktualna rewizja blokuje zapis. Walidacja nie przyjmuje dowolnych opcji DHCP ani identyfikatorów z innych urządzeń.

CSV zabezpiecza komórki mogące zostać potraktowane jako formuły przez arkusz; importer odwraca to zabezpieczenie. Nie jest to format pełnej kopii bazy: nie zawiera kont, historii wersji ani ewidencji. Globalny backup zawiera te dane i jest dostępny tylko aktywnemu adminowi. Panel udostępnia wyłącznie zaszyfrowane archiwum; nie udostępnia klucza. Pobranie backupu i klucza poza serwer użytkownik potwierdził; klucz należy przechowywać oddzielnie.
