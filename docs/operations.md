# Codzienna obsługa i diagnostyka

Dotyczy zainstalowanego panelu `http://192.168.1.32:8080` w LAN/VPN. Polecenia nie wymagają pulpitu na serwerze. Używaj kodu z `/opt/dhcp-tool/current` i środowiska `/etc/dhcp-tool/backend.env`; nie uruchamiaj usług instalacyjnych na developerskich portach ani z bazą testową.

## Kontrola dostępności

```sh
systemctl is-active dhcp-tool-api dhcp-tool-web nginx
curl -fsS http://192.168.1.32:8080/api/v1/health/
readlink -f /opt/dhcp-tool/current
sudo systemctl list-timers 'dhcp-tool-*' --no-pager
sudo systemctl show dhcp-tool-backup dhcp-tool-monitor -p Id -p Result -p ExecMainStatus
```

Oczekuj trzech `active`, JSON `{"status":"ok"}`, aktualnego katalogu wydania i poprawnych wyników jednostek. Health potwierdza żywotność procesu; nie sprawdza samodzielnie bazy, backupu ani działania DHCP na firewallu. Lokalny monitor sprawdza bazę, WWW/API, minimum 2 GiB wolnego miejsca oraz hash i wiek lokalnego eksportu do 36 godzin. Nie wysyła zewnętrznych powiadomień i nie potwierdza dostępu do panelu z innego komputera.

Monitor uruchamia się co 5 minut. Możesz wymusić sprawdzenie:

```sh
sudo systemctl start dhcp-tool-monitor.service
sudo journalctl -u dhcp-tool-monitor --since today --no-pager -n 50
```

## Backup

Timer tworzy szyfrowany eksport codziennie o 02:15 UTC z opóźnieniem do 5 minut. Dodatkowy eksport po ważnych zmianach:

```sh
sudo systemctl start dhcp-tool-backup.service
sudo systemctl status dhcp-tool-backup.service --no-pager
sudo journalctl -u dhcp-tool-backup --since today --no-pager -n 50
```

Po sukcesie na drugim komputerze pobierz kopię przez **Administracja → Pobierz najnowszy backup**. Pobranie nie tworzy nowej kopii. Sprawdź SHA-256 i przechowuj klucz poza serwerem, oddzielnie od archiwum. Potwierdzony raz eksport nie zapewnia kolejnych kopii poza serwerem: powtarzaj pobieranie. Brak automatycznego usuwania wymaga kontroli miejsca:

```sh
df -h /var/lib/postgresql /var/backups/dhcp-tool /opt/dhcp-tool
sudo du -sh /var/backups/dhcp-tool /var/lib/dhcp-tool/backup-download /opt/dhcp-tool/releases
```

Nie usuwaj historii w bazie ani klucza. Procedura pełnego odtworzenia, odmowa nadpisania bazy i sprawdzenie integralności: [backup-restore.md](backup-restore.md). CSV wybranego firewalla nie zastępuje backupu bazy.

## Typowe problemy

| Objaw | Kontrola i działanie |
| --- | --- |
| Strona nie otwiera się | Sprawdź usługi, adres IP serwera, LAN/VPN i ACL Nginx; sprawdź panel z komputera klienta |
| Nginx nie uruchamia się | `sudo nginx -t` oraz journal; dla `Cannot assign requested address` sprawdź `ip -4 address` i drop-in opisany w instalacji |
| API niedostępne / 503 | Sprawdź API i bazę oraz monitor; logi poniżej. Nie wyłączaj CSRF ani kontroli dostępu |
| Nieznane hasło | Reset istniejącego konta przez `changepassword`; [security.md](security.md) |
| 403 | Sesja, aktywne konto, rola i CSRF; dla backupu wymagany admin |
| 404 dla firewalla | Sprawdź przypisanie; backend ukrywa zasoby poza zakresem |
| 429 przy logowaniu | Odczekaj `Retry-After`; adres reverse proxy współdzieli budżet prób |
| 409 | Zachowaj lokalne wartości, odczytaj aktualne dane i wykonaj nowy podgląd; nie powtarzaj zapisu automatycznie |
| CSV odrzucone | Sprawdź nagłówek, UTF-8, rodzaj rekordu, JSON options, CIDR, id i limit 32 KiB/500 rekordów; [csv.md](csv.md) |
| Podgląd CSV wygasł | Wykonaj nowy podgląd; token jest ważny 10 minut i dotyczy jednej rewizji/konta/firewalla |
| `backup_unavailable` | Uruchom backup, sprawdź wynik i log jednostki; nie zmieniaj praw oryginalnych kopii lub klucza |
| Parser niedostępny | Sprawdź trwały `/opt/dhcp-tool/bin/dhcpd` i ustawienie `DHCPD_PARSER_PATH`; nie uruchamiaj usługi DHCP |
| Zmiana kodu niewidoczna | Usługi korzystają z wydania w `/opt`; wykonaj właściwy build i aktualizację, nie sam restart checkoutu |

## Logi i restart

```sh
sudo journalctl -u dhcp-tool-api -u dhcp-tool-web -u nginx -b --no-pager -n 100
sudo nginx -t
```

Logi aplikacji są ograniczone do bezpiecznych kodów i statusów. Nginx zapisuje metodę, status i czas w `/var/log/dhcp-tool/nginx-access.log`; logrotate utrzymuje 14 kopii. Limit journald 256 MiB/30 dni dotyczy całego serwera. Nie wklejaj do zgłoszeń zawartości środowisk, haseł ani klucza.

Restart usługi wykonuj po rozpoznaniu przyczyny i w oknie serwisowym — przerywa aktywne żądania:

```sh
sudo systemctl restart dhcp-tool-api dhcp-tool-web
```

Po poprawnym `nginx -t` zastosuj zmianę proxy przez `sudo systemctl reload nginx`. Po restarcie całego serwera sprawdź wszystkie procesy, timery i rzeczywiste logowanie przez LAN. Nie wykonuj reboot jako pierwszego kroku diagnostyki.

## Aktualizacja i próba odtworzenia

Przed aktualizacją wykonaj eksport i przygotuj build `.next-install` z API 18000. Korzystaj z aktualnych sekretów `/etc/dhcp-tool/backend.env`. Instalator zapisuje poprzednie wydanie, wykonuje eksport przed migracjami i kontrolę usług; nie cofa migracji automatycznie. Procedura: [installation.md](installation.md).

Odtwarzaj backup do nowej pustej bazy i nowego katalogu, a dopiero po porównaniu danych przełącz aplikację. Nie uruchamiaj migracji przed restore. Zaliczone odtworzenie pustej bazy nie zastępuje ćwiczenia odbudowy całego serwera. RPO/RTO pozostają nieustalone.
