# DHCP Tool dla Check Point Gaia

Aplikacja WWW do przygotowania konfiguracji DHCPv4, zapisania niezmiennych wersji i ręcznej ewidencji wdrożeń. Obsługuje profile R81.10 i R82.10 w uzgodnionym zakresie MVP: podsieci, jedna pula na podsieć i rezerwacje poza pulą. Aplikacja nie przesyła plików na firewall i nie odczytuje jego stanu. Dostępny jest również import i eksport całej konfiguracji CSV z podglądem zmian.

Format obu profili został potwierdzony przez użytkownika na podstawie wspólnej referencji. Testy danych, plików referencyjnych i parsera ISC nie oznaczają certyfikacji na obu wersjach Gaia. Szczegóły: [kontrakt generatora](docs/generator.md).

## Stan projektu

Etapy MVP 0–11 są ukończone. Panel działa w LAN/VPN pod `http://192.168.1.32:8080`; zainstalowane wydanie zawiera CSV. Użytkownik potwierdził logowanie administratora, eksport/import CSV oraz pobranie backupu i klucza poza serwer. Brak automatycznego usuwania backupów i historii. Stan, dowody oraz otwarte decyzje: [status projektu](docs/project-status.md).

Pełny spis instrukcji: [dokumentacja projektu](docs/index.md).

## Uruchom development

Wspierane środowisko: Debian 13, Python 3.13, Node.js 24 i PostgreSQL 17. Użyj `uv` i zależności z plików blokad. Przygotuj osobne role i bazy PostgreSQL dla aplikacji oraz testów według [instrukcji developerskiej](docs/development.md).

W `backend/.env` ustaw sekret Django, dane bazy i `DJANGO_SETTINGS_MODULE=config.settings.development`. W `backend/.env.test` ustaw dane oddzielnej bazy testowej. Nie publikuj tych plików. Uruchom backend:

```sh
cd backend
uv sync --frozen --extra dev
uv run --env-file .env python manage.py migrate
uv run --env-file .env python manage.py create_local_user admin --role admin
uv run --env-file .env python manage.py runserver 127.0.0.1:8000
```

W drugim terminalu uruchom frontend:

```sh
cd frontend
npm ci
npm run dev
```

Polecenie `create_local_user` służy do utworzenia nowego konta. Dla istniejącego użyj `changepassword admin`, aby ustawić nowe hasło; nie twórz konta ponownie.

Otwórz `http://localhost:3000`. Proxy Next.js przekazuje żądania API do Django na porcie 8000. Nie wystawiaj serwera developerskiego jako działającej instalacji LAN.

## Uruchom testy

Backend wymaga osobnego PostgreSQL; konto testowe ma CREATEDB i nie ma dostępu do bazy aplikacji:

```sh
cd backend
uv run --env-file .env.test pytest
uv run ruff check .
uv run --env-file .env.test python manage.py check
```

Sprawdź frontend:

```sh
cd frontend
npm test
npm run lint
npm run api:check
npm run typecheck
npm run build
```

Pełna kontrola uruchamia również Chromium bez pulpitu, tymczasowy Nginx, Gunicorn i produkcyjny build Next.js. Wymaga zainstalowanych narzędzi opisanych w [development](docs/development.md). Na obecnym serwerze uruchom z katalogu głównego:

```sh
DHCPD_PARSER_PATH=/opt/dhcp-tool/bin/dhcpd scripts/check-quality.sh
```

Bez skonfigurowanego parsera opcjonalne testy ISC są pomijane. Testy przeglądarkowe korzystają wyłącznie z osobnej bazy i portów testowych.

## Znajdź kod i dokumentację

| Ścieżka | Zawartość |
| --- | --- |
| `backend/dhcp_tool/generator.py` | Walidacja i deterministyczne generowanie bez HTTP i bazy |
| `backend/dhcp_tool/` | Modele, sesje, uprawnienia, konfiguracja, wersje i ewidencja |
| `backend/config/` | Ustawienia, routing i OpenAPI |
| `backend/tests/` | Regresje, referencje i dane przeglądarkowe |
| `frontend/src/` | Panel React/Next.js, komponenty i klient API |
| `frontend/e2e/` | Scenariusze przeglądarkowe |
| `scripts/`, `deploy/` | Instalacja, eksport, odtwarzanie i konfiguracja usług |
| `docs/` | Instrukcje i raporty weryfikacji |
| `graphify-out/` | Graf pomocniczy; aktualny kod pozostaje źródłem prawdy |

Przeczytaj dokument właściwy dla zadania:

- [Architektura i przepływ danych](docs/architecture.md)
- [Codzienna obsługa i diagnostyka](docs/operations.md)
- [Obsługa panelu](docs/user-guide.md)
- [Import i eksport konfiguracji CSV](docs/csv.md)
- [Instalacja i aktualizacje](docs/installation.md)
- [Konta i uprawnienia](docs/security.md)
- [Pobranie backupu i odtworzenie](docs/backup-restore.md)
- [Wyniki odbioru MVP](docs/acceptance-mvp.md)
- [Wydanie i znane ograniczenia](docs/release-mvp.md)

Autentyczne `dhcpd.conf` i `dhcpd copy.conf` są chronionymi lokalnymi referencjami. Nie zmieniaj ich. Nie przechowuj sekretów, eksportów ani rzeczywistych danych użytkowników w Git.
