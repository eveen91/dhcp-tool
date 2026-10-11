# Eksport i odtworzenie

Eksport obejmuje całą bazę PostgreSQL: konta, role, przypisania, konfiguracje robocze, rezerwacje, wersje, binarne artefakty, hashe, ewidencję, audyt i sesje. Konfiguracja operatora jest dołączana do archiwum. Format bazy to custom `pg_dump`; pakiet jest szyfrowany GnuPG AES-256 z kontrolą integralności. Klucz szyfrowania **nie jest dołączany**, również gdy znajduje się w eksportowanym katalogu. Chwilowe pliki jawne powstają w katalogu 700, są sprzątane po operacji i nie są udostępniane aplikacji web.

Decyzja użytkownika: brak automatycznego usuwania kopii i ręczne pobieranie eksportu poza serwer. Pobranie backupu oraz oddzielnego klucza zostało potwierdzone; T10.5 zamknięte. Nie skonfigurowano automatycznej replikacji ani stałego zewnętrznego celu eksportu. RPO/RTO nie są zadeklarowane. Timer jest codzienny, ale skuteczność zależy od jego kontroli. Historia aplikacji nie jest automatycznie czyszczona.

## Eksport przed instalacją

Konfiguracja `.deployment` i losowy klucz są przygotowane. Z katalogu głównego:

```sh
cd /mnt/dhcp-tool
backend/.venv/bin/python scripts/run-with-env.py .deployment/backend.env backend/.venv/bin/python scripts/operations.py export --config-dir .deployment --output-dir .exports --key-file .deployment/export.key
```

Katalog `.exports` jest prywatny i ignorowany przez Git. Nie umieszczać eksportów wewnątrz katalogu konfiguracji — skrypt odrzuca taki układ, aby nie archiwizować poprzednich kopii. Po instalacji konfiguracja jest w `/etc/dhcp-tool`, a eksporty w `/var/backups/dhcp-tool`:

```sh
sudo systemctl start dhcp-tool-backup.service
```

`latest.json` wskazuje plik, SHA-256 i czas ukończenia. Nie jest aktualizowany po nieudanym eksporcie. Eksport i marker mają prawa 600. Nie ma komendy automatycznego usuwania. Kopie należy okresowo pobierać na inny komputer przez panel (procedura poniżej), wraz z sumą SHA-256; klucz trzymać osobno offline. Kopia samego archiwum bez klucza nie wystarczy do odtworzenia. Kopia archiwum wraz z kluczem w tym samym miejscu osłabia ochronę.

## Pobranie w przeglądarce

Po zainstalowaniu aktualnego wydania:

1. Na innym komputerze w LAN/VPN otwórz `http://192.168.1.32:8080` i zaloguj się kontem z rolą `admin`.
2. Otwórz **Administracja → Pobierz najnowszy backup**.
3. Zapisz plik `dhcp-tool-DATA-IDENTYFIKATOR.tar.gpg` na tym komputerze. Zawiera zaszyfrowaną bazę i konfigurację z ostatniego ukończonego eksportu. Kliknięcie nie tworzy nowego backupu. Jeśli potrzebujesz aktualnej kopii, najpierw uruchom na serwerze `sudo systemctl start dhcp-tool-backup.service`.
4. Sprawdź, że pobieranie się zakończyło. Sumę pliku można porównać z nagłówkiem `X-Backup-SHA256` odpowiedzi HTTP w narzędziach deweloperskich przeglądarki. Na Linux: `sha256sum PLIK.tar.gpg`; na Windows PowerShell: `Get-FileHash PLIK.tar.gpg -Algorithm SHA256`.
5. Przechowuj klucz z `/etc/dhcp-tool-backup.key` w oddzielnym, bezpiecznym miejscu offline. Panel nie udostępnia klucza. Użyj wcześniej przygotowanej kopii klucza; jeżeli jej nie masz, administrator systemu musi wykonać ją osobno.

Jeśli panel zwraca `backup_unavailable`, na serwerze wykonaj:

```sh
sudo systemctl start dhcp-tool-backup.service
sudo systemctl status dhcp-tool-backup.service --no-pager
```

Błąd `forbidden` oznacza brak aktywnego konta administratora. Nie zmieniaj praw oryginalnych backupów ani klucza, aby udostępnić je aplikacji.

Root po każdym udanym eksporcie publikuje kopię **wyłącznie zaszyfrowanego pliku**, po sprawdzeniu SHA-256, w `/var/lib/dhcp-tool/backup-download`. API ma dostęp do odczytu przez grupę `dhcp-api`; katalogi mają prawa 750, pliki 640. Oryginały i klucz pozostają prywatne. Wskaźnik `current` jest przełączany atomowo; nieudana publikacja zachowuje poprzednią dostępną kopię. API przesyła plik strumieniowo, wymaga roli admin, blokuje wybieranie ścieżek i ustawia `Cache-Control: no-store`. Backupy i opublikowane kopie nie są automatycznie usuwane.

Samo przygotowanie przycisku nie potwierdza kopii poza serwerem. T10.5 można domknąć po rzeczywistym pobraniu na inny komputer i potwierdzeniu bezpiecznej, oddzielnej kopii klucza.

## Odtworzenie do pustej bazy

Przygotować PostgreSQL 17 i zgodne wydanie aplikacji z plikami blokad. Utworzyć nową pustą bazę, której właścicielem jest konto aplikacji, i odwołać domyślne uprawnienia PUBLIC; przykładowo przez DBA:

```sh
sudo -u postgres createdb --owner=dhcp_tool dhcp_tool_recovered
sudo -u postgres psql -X -d postgres -c 'REVOKE ALL ON DATABASE dhcp_tool_recovered FROM PUBLIC;'
```

Nie uruchamiać migracji w pustej bazie przed restore: dump zawiera schemat, migracje i ograniczenia. Polecenie używa uprawnień konta aplikacji, bez superusera. Wybrać nowy, nieistniejący katalog na odzyskaną konfigurację:

```sh
sudo /usr/bin/python3 /opt/dhcp-tool/current/scripts/run-with-env.py /etc/dhcp-tool/backend.env /opt/dhcp-tool/current/backend/.venv/bin/python /opt/dhcp-tool/current/scripts/operations.py restore --archive /var/backups/dhcp-tool/WYBRANY_PLIK.tar.gpg --key-file /etc/dhcp-tool-backup.key --target-db dhcp_tool_recovered --config-output /root/dhcp-tool-recovered-config
```

Restore odrzuca bazę źródłową, niepustą bazę docelową, istniejący katalog wyjściowy, niezaufane ścieżki i dowiązania w archiwum oraz błędną integralność szyfrowania. `pg_restore` stosuje jedną transakcję, `--exit-on-error`, `--no-owner`, `--no-acl`. Nie usuwa tabel. Odtwarzane dane są własnością bieżącego konta, a uprawnienia bazy trzeba ustawić jawnie przez DBA. Jeżeli po udanym restore zabraknie miejsca na przeniesienie konfiguracji, baza pozostaje odtworzona; przed ponowieniem sprawdzić wynik i nie nadpisywać jej.

## Sprawdzenie wyniku

W oknie serwisowym, gdy nie ma zapisów, `operations.py fingerprint` zwraca liczbę rekordów i SHA-256 z kanonicznie uporządkowanych wierszy każdej tabeli publicznej. Nie wypisuje treści ani haseł. Uruchomić dla źródła przed eksportem i odtworzonej bazy, z właściwymi prywatnymi plikami środowiska; porównać raporty. Przy aktywnych zapisach różnice czasu są oczekiwane. Sprawdzić dodatkowo hashe pobranych artefaktów i działanie kont, przypisań oraz historii. Test automatyczny robi to na niezależnej pustej bazie `test_dhcp_restore_*`, ze schematem, użytkownikiem, konfiguracją, rezerwacją, wersją, binarnym artefaktem, ewidencją i audytem; porównuje wszystkie tabele. Nie zastępuje próby odtworzenia całego serwera i jego usług.

Po potwierdzeniu wyniku zatrzymać usługi aplikacji, wybrać zgodne wydanie, ustawić odzyskaną konfigurację i nazwę nowej bazy w `/etc/dhcp-tool/backend.env` (600), uruchomić `manage.py check` i `showmigrations`, a następnie usługi. Zmienić sekrety, jeśli kopia pochodzi z utraconego lub naruszonego serwera. Zweryfikować logowanie, konfigurację, publikację, pobranie, SHA-256 i audyt. Zachować starą bazę do zakończenia odbioru.

[Dokumentacja pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html) i [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html) opisuje format i ograniczenia narzędzi. Dump odtwarzać tylko z zaufanego źródła; archiwum SQL może wykonywać kod w bazie.

Użytkownik potwierdził udane pobranie backupu oraz klucza 2026-10-11, odpowiadając na pytanie o oddzielną kopię klucza poza serwerem. T10.5 zamknięte. Klucz należy nadal przechowywać oddzielnie od archiwum.
