# Instalacja i utrzymanie na Debianie 13

Zakres: serwer aplikacji bez kontenerów. Generator nie komunikuje się z firewallem. Decyzja użytkownika dla obecnej instalacji: pełny panel przez HTTP w LAN/VPN, bez TLS, eksport bazy i konfiguracji, bez automatycznego usuwania kopii. Adres obecnego panelu: `http://192.168.1.32:8080`. Tryb HTTPS pozostaje osobnym, opcjonalnym profilem.

## Pakiety i przygotowanie

Obecny serwer ma Python 3.13, PostgreSQL 17, Nginx i Node.js 24. Node pochodzi z podpisanego repozytorium NodeSource `node_24.x`. Nie zastępować go starszym pakietem z innego repozytorium. Na nowym Debianie 13:

```sh
sudo apt update
sudo apt install python3 python3-venv postgresql postgresql-client nginx openssl gnupg logrotate ca-certificates curl xz-utils
```

Zainstalować Node.js 24 zgodnie z [instrukcją NodeSource](https://github.com/nodesource/distributions/blob/master/DEV_README.md); sprawdzić `node --version` i `/usr/bin/node`. Zainstalować `uv` zgodnie z [dokumentacją Astral](https://docs.astral.sh/uv/getting-started/installation/). Instalator obecnego serwera oczekuje `/home/seba/.local/bin/uv`; trzeci argument pozwala wskazać inną lokalizację. Python 3.13 jest systemowy, nie z katalogu domowego. PostgreSQL pozostaje lokalny, bez superusera dla aplikacji.

Parser ISC instalujemy wyłącznie jako narzędzie walidacji. Nie uruchamiać usługi serwera DHCP na serwerze aplikacji. Na obecnym serwerze parser pochodzi z rozpakowanego pakietu Debian, `/tmp/dhcp-tool-parser/extracted/usr/sbin/dhcpd`; instalator kopiuje go do trwałego `/opt/dhcp-tool/bin/dhcpd`. Przy aktualizacji używa już zainstalowanego parsera, bez zależności od katalogu `/tmp`. Przy nowej instalacji można pobrać zaufany pakiet `isc-dhcp-server` przez `apt download`, rozpakować `dpkg-deb -x` i wskazać plik `usr/sbin/dhcpd` jako drugi argument instalatora. Sprawdzić zależności `ldd` i wersję parsera. To kontrola ISC, nie certyfikacja Gaia.

Przygotowanie bazy, sekretów i administratora: `docs/development.md` oraz `docs/security.md`. Nie uruchamiać ponownie skryptu tworzącego istniejące role i bazy. Sekrety działających usług są w `/etc/dhcp-tool/backend.env`; `backend/.env` służy do developmentu i pierwszego przygotowania instalacji; nie wklejać ich do terminala ani Git. Administratora tworzyć interaktywnie przez `manage.py create_local_user admin --role admin`; dokładne opcje sprawdzić przez `--help`.

```sh
cd /mnt/dhcp-tool/backend
uv sync --frozen --extra dev --cache-dir /tmp/dhcp-tool-uv-cache
uv run --offline --no-sync --cache-dir /tmp/dhcp-tool-uv-cache --env-file .env python ../scripts/prepare-install.py --output /mnt/dhcp-tool/.deployment
cd /mnt/dhcp-tool/frontend
npm ci
DHCP_TOOL_API_URL=http://127.0.0.1:18000 NEXT_BUILD_DIR=.next-install NEXT_TELEMETRY_DISABLED=1 npm run build
```

`prepare-install.py` używa istniejących sekretów i tworzy ignorowany katalog `.deployment` (700), pliki środowiska (600), routing Nginx oraz losowy klucz eksportu. Domyślnie dopuszcza `192.168.1.0/24`; inne adresy prywatne można przekazać przez `--host`, `--port`, `--allow-cidr`. VPN z inną podsiecią wymaga dodania właściwego `allow` do sprawdzonego pliku Nginx. Publiczny adres HTTP jest odrzucany. Klucz `export.key` przechować także offline, osobno od eksportu. Bez niego odtworzenie będzie niemożliwe.

## Instalacja usług

Na obecnym serwerze usługi są już zainstalowane; aktualizację opisano poniżej. Dla nowej instalacji, po przygotowaniu konfiguracji i `.next-install`, uruchomić z katalogu głównego:

```sh
cd /mnt/dhcp-tool
sudo scripts/install-services.sh
```

Skrypt wymaga uprawnień administratora systemu. Tworzy wydanie w `/opt/dhcp-tool/releases/`, nowy virtualenv w jego finalnej lokalizacji oraz konta `dhcp-api` i `dhcp-web` bez powłoki i uprawnień root. Kod jest własnością root; web może zapisywać tylko cache buildu. Środowisko znajduje się poza repozytorium w `/etc/dhcp-tool` (700/600); systemd odczytuje je przed uruchomieniem procesów. Dane aplikacji pozostają w PostgreSQL. Eksport i monitoring działają jako root, aby odczytywać prywatną konfigurację i klucz; mają ograniczony zapis i nie są usługami HTTP.

Gunicorn nasłuchuje na `127.0.0.1:18000`, Next.js na `127.0.0.1:13000`. Nowe porty nie kolidują z dotychczasowym podglądem 8000/3000. Nginx zastępuje ograniczony status na porcie 8080 pełnym panelem, z dostępem dla LAN. API, panel i `/_next/static/` mają wspólny origin. Cache prywatnych odpowiedzi jest wyłączony. Nginx nadpisuje nagłówki proxy; Django ufa nagłówkowi protokołu tylko w profilu HTTPS.

Instalator wykonuje eksport przed migracjami, migracje, kontrolę Nginx, start usług, pierwszy eksport po instalacji i publikację zaszyfrowanej kopii do pobrania w panelu, włączenie timerów i kontrolę operacyjną. Konfiguracja odrzucona przez `nginx -t` przywraca poprzedni proxy; migracje nie są automatycznie cofane. Poprzedni status i wydanie są zachowane. Skrypt nie zatrzymuje starych procesów developerskich ani PostgreSQL i nie zmienia autentycznych plików DHCP.

Logi aplikacji i Gunicorna są filtrowane do metadanych; Nginx zapisuje tylko metodę, status i czas w `/var/log/dhcp-tool/nginx-access.log`. Logrotate obraca ten plik codziennie, utrzymuje 14 kopii i uwzględnia rozmiar 10 MiB. Osobny katalog zapobiega konfliktowi z domyślną rotacją `/var/log/nginx/*.log`. Drop-in journald ogranicza **cały journal serwera** do 256 MiB i 30 dni; uwzględnić to, jeśli serwer obsługuje także inne aplikacje.

```sh
sudo systemctl status dhcp-tool-api dhcp-tool-web dhcp-tool-monitor --no-pager
sudo systemctl list-timers 'dhcp-tool-*' --no-pager
sudo journalctl -u dhcp-tool-api -u dhcp-tool-web -u dhcp-tool-monitor -u dhcp-tool-backup --since today
```

Health HTTP jest kontrolą żywotności procesu. Monitor dodatkowo wykonuje rzeczywiste `SELECT 1`, sprawdza odpowiedź strony, wolne miejsce co najmniej 2 GiB i poprawny hash eksportu nie starszego niż 36 godzin. Zwraca status niepowodzenia i JSON z flagami, bez treści konfiguracji. Timer działa co 5 minut; to kontrola lokalna, bez zewnętrznych powiadomień. Obserwować stan jednostki oraz journal. Eksport jest wykonywany codziennie o 02:15 UTC z opóźnieniem do 5 minut; **żadne kopie nie są usuwane automatycznie**.

Tworzenie administratora na zainstalowanej aplikacji:

```sh
sudo /usr/bin/python3 /opt/dhcp-tool/current/scripts/run-with-env.py /etc/dhcp-tool/backend.env /opt/dhcp-tool/current/backend/.venv/bin/python /opt/dhcp-tool/current/backend/manage.py create_local_user admin --role admin
```

Polecenie utworzy użytkownika `admin` i zapyta o hasło; nie przekazywać hasła w argumentach. Istniejące konto administratora pozostaje w bazie.

## Eksport i odtworzenie

Pełna procedura w `docs/backup-restore.md`. Ręczny eksport po instalacji:

```sh
sudo systemctl start dhcp-tool-backup.service
sudo ls -lh /var/backups/dhcp-tool
```

Administrator może pobrać zaszyfrowany `.tar.gpg` przez panel na inny komputer; sprawdzić SHA-256. Klucz przenieść osobno i przechowywać oddzielnie. Użytkownik potwierdził pobranie backupu i klucza; T10.5 zamknięte. Automatyczna replikacja poza serwer nie jest skonfigurowana; kolejne kopie wymagają ręcznego pobierania. Procedura: [backup-restore.md](backup-restore.md).

## Aktualizacja i powrót

1. W oknie serwisowym zablokować zapisy: `sudo systemctl stop dhcp-tool-web dhcp-tool-api`. Wykonać eksport: `sudo systemctl start dhcp-tool-backup`.
2. Zachować identyfikator poprzedniego wydania, prywatną konfigurację i klucz. Zapisać `showmigrations --plan` poleceniem przez `run-with-env.py`.
3. W checkout przygotować nowy kod, `uv sync --frozen --extra dev`, `npm ci`, pełny skrypt jakości i `.next-install` z API na porcie 18000. Nie budować z testowym API 8101 do instalacji.
4. Przygotować konfigurację z aktualnych sekretów. Przy późniejszych aktualizacjach **źródłem sekretów jest `/etc/dhcp-tool/backend.env`**, nie stary developerski `.env`:

```sh
sudo /usr/bin/python3 /opt/dhcp-tool/current/scripts/run-with-env.py /etc/dhcp-tool/backend.env /usr/bin/python3 /mnt/dhcp-tool/scripts/prepare-install.py --output /root/dhcp-tool-update
sudo /mnt/dhcp-tool/scripts/install-services.sh /root/dhcp-tool-update
```

5. Instalator zapisuje poprzednie wydanie, stosuje migracje i restartuje usługi. Sprawdzić panel, logowanie, podgląd, publikację, hash pobrania i ewidencję; nie wykonywać integracji z urządzeniem.

Powrót kodu jest możliwy tylko wtedy, gdy poprzedni kod obsługuje aktualny schemat. Przy zgodnych migracjach zatrzymać usługi, odczytać `/etc/dhcp-tool/previous-release.txt`, atomowo przestawić symlink `current` na to wydanie i uruchomić obie usługi. Sprawdzić również zgodność plików środowiska, jednostek systemd i Nginx z tym wydaniem; przy ich zmianie przywrócić sprawdzony snapshot konfiguracji oraz wykonać `daemon-reload` i `nginx -t`. Nie uruchamiać starszego kodu ze zmienionym schematem na próbę. Przy migracji niezgodnej odtworzyć eksport do **nowej pustej bazy**, przywrócić pasujące wydanie i konfigurację, zmienić nazwę bazy w prywatnym środowisku i dopiero uruchomić usługi. Nie stosować automatycznego reverse migrate ani nadpisywania bazy.

## Kontrola po restarcie

Instalator włącza jednostki i timery, ale sprawdzenie `is-enabled` nie jest testem prawdziwego restartu. Po udanej instalacji zaplanować restart z operatorem (restart przerywa również sesję SSH):

```sh
sudo systemctl is-enabled dhcp-tool-api dhcp-tool-web nginx dhcp-tool-backup.timer dhcp-tool-monitor.timer
sudo systemctl reboot
```

Po ponownym połączeniu sprawdzić `is-active`, `list-timers`, monitor i dziennik bieżącego startu (`journalctl -b -u dhcp-tool-api -u dhcp-tool-web`). Na innym komputerze wykonać pełny przepływ przez `http://192.168.1.32:8080`. T10.9 zamknięto po rzeczywistym restarcie i potwierdzeniu panelu 2026-10-11; tę kontrolę powtarzać po kolejnych restartach. HTTPS jest pominięty na wyraźne polecenie użytkownika.

## Opcjonalne HTTPS

`deploy/nginx/https.conf.template` zawiera routing i TLS 1.2/1.3. Przed użyciem zastąpić placeholdery, ustawić zaufany certyfikat i prywatny klucz poza repozytorium, zmienić profil Django na `config.settings.production`, origin CSRF na `https://...` i hosty na nazwę certyfikatu. Profil ten pozostawia secure cookies i redirect HTTPS; Nginx ustawia `X-Forwarded-Proto`. Monitoring należy skierować na właściwy adres HTTPS lub zapewnić poprawny nagłówek przy zaufanym lokalnym odczycie. Nie używać testowego CA w rzeczywistym wdrożeniu. Ten wariant nie został aktywowany.

Źródła: [Django — reverse proxy](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header), [Nginx — HTTPS](https://nginx.org/en/docs/http/configuring_https_servers.html), [PostgreSQL 17 — pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html), [systemd — ograniczenia usług](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml).

## Nginx po starcie z opóźnionym adresem LAN

Jeśli journal pokazuje `Cannot assign requested address`, adres LAN nie był jeszcze przypisany podczas próby startu. Samo `network-online.target` nie zapewniło jego gotowości. Drop-in `deploy/nginx-systemd/dhcp-tool.conf` ustawia ponowienie błędnego startu co 5 sekund, także po błędzie ExecStartPre. Zachowuje nasłuch na konkretnym adresie i ACL LAN. Instalator stosuje tę konfigurację również w nowych wydaniach.

Dla już zainstalowanego serwera wystarczy:

```sh
sudo install -d -m 0755 /etc/systemd/system/nginx.service.d
sudo install -m 0644 /mnt/dhcp-tool/deploy/nginx-systemd/dhcp-tool.conf /etc/systemd/system/nginx.service.d/dhcp-tool.conf
sudo systemctl daemon-reload
sudo systemctl restart nginx
```

Następnie sprawdzić `systemctl is-active nginx` i panel w LAN. Start po rzeczywistym restarcie z tą poprawką został potwierdzony w T10.9; po kolejnej zmianie konfiguracji ponownie sprawdzić uruchamianie usług.

## Odbiór obecnej instalacji

Stan 2026-10-11: `/opt/dhcp-tool/current` wskazuje wydanie `20261011T162819Z`. API, WWW i Nginx są aktywne, health w LAN zwraca HTTP 200. Użytkownik potwierdził logowanie admina, eksport/import CSV całej konfiguracji oraz pobranie backupu i klucza. CSV nie dodało migracji ani nowych zależności systemowych. Procedura resetu hasła: [security.md](security.md). Aktualny status i codzienna diagnostyka: [project-status.md](project-status.md), [operations.md](operations.md).
