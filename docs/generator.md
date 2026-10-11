# Generator DHCPv4: kontrakt MVP

Generator `backend/dhcp_tool/generator.py` działa w panelu i API. Autentyczny `dhcpd.conf` oraz referencja użytkownika `dhcpd copy.conf` są chronione przed zmianami. Druga referencja obejmuje rezerwację; wersja źródłowego urządzenia nie jest udokumentowana.

## Źródła i profile

**Priorytet produktu:** zgodność z wybraną wersją Gaia jest nadrzędnym kryterium akceptacji generatora. Poprawność danych, deterministyczność i akceptacja przez parser upstream ISC DHCP są osobnymi sprawdzeniami; nie zastępują dowodów zgodności Gaia. Przed rozszerzaniem funkcji i dopracowaniem UI należy w pierwszej kolejności uzupełniać dowody zgodności dla R81.10 i R82.10, zwłaszcza rezerwacji. Zachowujemy whitelistę i wymagania bezpieczeństwa. Brak dowodu oznacza funkcję niezweryfikowaną, a nie potwierdzoną obsługę.

- [Gaia R81.10 — DHCP Server](https://sc1.checkpoint.com/documents/R81.10/WebAdminGuides/EN/CP_R81.10_Gaia_AdminGuide/Topics-GAG/DHCP-Server.htm) i [Gaia R82.10 — DHCP Server](https://sc1.checkpoint.com/documents/R82.10/WebAdminGuides/EN/CP_R82.10_Gaia_AdminGuide/Content/Topics-GAG/DHCP-Server.htm): dokumentują podsieć na interfejsie, pulę oraz opcjonalne parametry routera i do trzech serwerów DNS; nie stanowią samodzielnego potwierdzenia składni pliku ani rezerwacji.
- [ISC DHCP 4.4 — dhcpd.conf](https://kb.isc.org/docs/isc-dhcp-44-manual-pages-dhcpdconf): odniesienie dla składni `subnet`, `range`, `host`, `hardware ethernet`, `fixed-address`, `option routers`, `option domain-name`, `option domain-name-servers`, `default-lease-time`, `max-lease-time`. ISC DHCP osiągnął EOL. Wymagana weryfikacja na referencyjnym parserze/plikach dla Gaia przed deklarowaniem pełnej zgodności.
- [ISC DHCP 4.4 — dhcp-options](https://kb.isc.org/docs/isc-dhcp-44-manual-pages-dhcp-options) potwierdza `option host-name = expression;`, a [dhcp-eval](https://kb.isc.org/docs/isc-dhcp-44-manual-pages-dhcp-eval) opisuje wyrażenia; w dostarczonym pliku występuje `pick(...)` (zamiast opisanego w podręczniku `pick-first-value(...)`). Parser ISC DHCP 4.4.3-P1 zaakceptował dokładnie tę postać z próbki; nie zmieniamy jej na podstawie samej nazwy funkcji w podręczniku.
- Użytkownik potwierdził jednakowy format profili R81.10 i R82.10 w uzgodnionym zakresie MVP. Oba profile korzystają ze wspólnej białej listy dyrektyw i referencji `dhcpd copy.conf`; nie wymagamy osobnych identycznych plików. Źródłem potwierdzenia jest deklaracja użytkownika, nie test na obu urządzeniach. Gaia Embedded i Scalable Platforms poza zakresem.

## Dostarczona próbka `dhcpd.conf`

Plik `dhcpd.conf` w katalogu głównym ma obecnie 24 linie i został potwierdzony przez użytkownika jako autentyczny plik wygenerowany przez działający firewall Check Point. Zawiera `ddns-update-style none;` i dwie podsieci z lease-time, automatycznym host-name, pulą, routerem i DNS. Zachowujemy go bez zmian jako lokalny przykład źródłowy (jest ignorowany przez Git); nie przypisujemy go arbitralnie do profilu R81.10 ani R82.10, dopóki nie znamy wersji urządzenia.

**Weryfikacja 9 października 2026:** cały aktualny plik oraz osobno plik wygenerowany dla tych samych sieci przeszły `dhcpd -t -4 -cf ...` na Debianowym **ISC DHCP 4.4.3-P1** (binarka z pakietu `isc-dhcp-server`, wyodrębniona do `/tmp/opencode`, bez uruchamiania usługi). To test składni upstream; pochodzenie pliku potwierdza jego praktyczne użycie na Check Point, ale bez wersji urządzenia nie dowodzi zgodności obu profili ani składni rezerwacji. Wygląd (wcięcia, puste wiersze, kolejność niezależnych opcji) nie musi być identyczny: dokumentacja ISC dopuszcza nadmiarowe spacje i nowe linie; nasz generator sortuje podsieci i opcje deterministycznie. Test regresyjny odzwierciedlający dyrektywy i wartości próbki znajduje się w `backend/tests/test_generator.py`.

W odpowiedzi na próbkę generator dodaje stałą dyrektywę `ddns-update-style none;`. Opcjonalne `gaia_host_name_fallback: true` na podsieci emituje zaufany, sztywny szablon `option host-name = pick(option host-name, concat(... leased-address))`; nie przyjmuje dowolnego wyrażenia od użytkownika. Domyślnie opcja jest wyłączona, aby nie zmieniać zachowania nazw hostów bez decyzji operatora. Konfiguracji rezerwacji nie ma w próbce, więc wymagają osobnego sprawdzenia na Gaia.

## Wejście i format

`render(config: dict) -> bytes` jest niezależne od HTTP i bazy danych. Wymagane pola główne: `firewall` (bezpieczny identyfikator ASCII), `profile` (`R81.10` albo `R82.10`), `subnets` (lista). Opcjonalne globalne: `default_lease_time`, `max_lease_time` (sekundy), `domain`, `dns` (1–3 adresy IPv4). Podsieć: `cidr` (adres sieci z prefiksem do /30), opcjonalne `gateway`, `interface_address`, `gaia_host_name_fallback` (boolean), analogiczne opcje globalne i listy `pools` oraz `reservations`. Pula: `start`, `end`. Rezerwacja: `id`, `mac`, `ip`. Podsieci, pule i rezerwacje mogą mieć `active: false`. Dodatkowe pola są odrzucane, nie ma dowolnych dyrektyw.

Kolejność: dwie linie nagłówka; `ddns-update-style none;`; opcje globalne (dzierżawy, domena, DNS); podsieci według adresu sieci i długości prefiksu, a w nich opcje lokalne (dzierżawy, domena, DNS, router) i zakresy według początku/końca; rezerwacje jako bloki `host` po podsieciach, sortowane według `id`. MAC są normalizowane do małych liter z dwukropkami. Nazwy hostów są identyfikatorami z pola `id`, unikalnymi dla firewalla. Wyjście to ASCII, LF, jedna końcowa nowa linia; bez daty generacji. Nieaktywne obiekty i dzieci wyłączonych podsieci są pomijane.

Opcje lokalne nadpisują globalne za pomocą zakresu dyrektyw ISC; brak opcji lokalnej oznacza dziedziczenie. Pusta lista DNS jest niedozwolona (zamiast niej usuń opcję lokalną). Całkowicie pusta aktywna konfiguracja jest blokowana w MVP. Każde usunięcie elementu konfiguracji roboczej wymaga ostrzeżenia i potwierdzenia w interfejsie, bez progu liczbowego lub procentowego; przy usunięciu podsieci ostrzeżenie obejmuje jej pule i rezerwacje. Ostrzeżenie i potwierdzenie są zaimplementowane w panelu; moduł `render` nie obsługuje interfejsu.

## Ograniczenia i następne kroki

- `render()` waliduje struktury i adresację. Opcjonalny adapter `dhcp_tool.syntax.check_syntax()` i polecenie `check_dhcp_config` sprawdzają dodatkowo składnię; kontrakt i zakres opisano poniżej. Endpointy walidacji i podglądu są dostępne; kontrakt w `docs/validation-api.md`.
- Wspólny format obu profili w MVP został potwierdzony przez użytkownika. Testy działania na urządzeniach nie zostały wykonane w tym projekcie. Golden files MVP obejmują wiele podsieci, jedną pulę na podsieć i rezerwacje poza pulą. Wiele pul i podsieci tylko z rezerwacjami odłożono do `features_to_add.md`; ich dotychczasowa obsługa w module nie rozszerza zakresu MVP.

Próbka użytkownika `dhcpd copy.conf` obejmuje dwie podsieci z jedną pulą każda oraz jedną rezerwację poza pulą. Zweryfikowano ją parserem ISC DHCP 4.4.3-P1 (`-t -4`, kod zakończenia 0), bez modyfikacji pliku. Jest wspólną referencją zakresu MVP dla obu profili zgodnie z potwierdzeniem użytkownika. Wersja źródłowa urządzenia i test działania rezerwacji na urządzeniu nie zostały udokumentowane.
- Lokalni użytkownicy i backup są wdrożone. Docelowa skala oraz okres przechowywania historii pozostają nieustalone; automatyczne usuwanie historii i backupów jest wyłączone. Użytkownik potwierdził pobranie backupu i klucza poza serwer. CSV całej konfiguracji działa z dotychczasową whitelistą; brak importu plików `dhcpd.conf`, SSO i automatycznego wdrożenia.
- Działająca instalacja: serwer Linux bez kontenerów; wspieramy Debian 13, Python 3.13, Node.js 24, Next.js 16.4 i PostgreSQL 17, zgodnie z T00.8 i `docs/development.md`. Brak dostępu do appliance nie blokuje rozwoju generatora.

Aktualne testy: `uv run --env-file .env.test pytest` w `backend/`. Przy kontroli ISC skonfiguruj zaufany `DHCPD_PARSER_PATH`.

## Opcjonalne sprawdzanie składni

Z katalogu `backend/`:

```sh
uv run --env-file .env python manage.py check_dhcp_config ../docs/examples/dhcp-config.json
```

Polecenie odczytuje JSON, waliduje i generuje konfigurację w pamięci. Nie zapisuje
wersji ani artefaktu i nie modyfikuje żadnego pliku referencyjnego. Wynik JSON
zawiera `data_validated`, `syntax_status`, `parser_version`, `parser_return_code`,
`gaia_compatibility`, liczbę bajtów i SHA-256 wygenerowanego artefaktu.

Administrator może skonfigurować zaufaną, absolutną ścieżkę do parsera przez
`DHCPD_PARSER_PATH` w środowisku lub opcję `--parser /absolute/path/to/dhcpd`.
Ścieżka nie jest przyjmowana z danych konfiguracji ani wyszukiwana w `PATH`.
`--require-parser` wymaga wyniku `syntax_checked`; bez tej opcji brak parsera
pozwala zakończyć samą walidację danych bez sugerowania sprawdzenia składni.

| `syntax_status` | Znaczenie |
| --- | --- |
| `syntax_checked` | Parser zakończył sprawdzenie z kodem 0 |
| `parser_unavailable` | Nie skonfigurowano parsera lub brak wykonywalnego pliku |
| `syntax_error` | Parser zakończył sprawdzenie z kodem 1 |
| `parser_error` | Awaria, inny kod zakończenia, nierozpoznana wersja lub przekroczenie limitu wyjścia |
| `parser_timeout` | Przekroczenie wspólnego limitu czasu odczytu wersji i sprawdzenia składni |

Adapter uruchamia `--version`, następnie `-t -4 -cf <temporary-file>` z lokalnymi
ścieżkami plików dzierżaw i PID. Tryb `-t` sprawdza składnię bez operacji
sieciowych ([ISC dhcpd](https://kb.isc.org/docs/isc-dhcp-44-manual-pages-dhcpd)).
Wykorzystuje prywatny katalog tymczasowy, plik konfiguracji z uprawnieniami `600`,
minimalne środowisko procesu, brak powłoki i stdin, limit 1 MiB wejścia,
8192 bajtów wyjścia na proces oraz 5 sekund łącznie. Timeout i błędy zatrzymują
grupę procesów; pliki tymczasowe są usuwane. Surowe komunikaty parsera ani treść
konfiguracji nie trafiają do odpowiedzi lub logów. To adapter dla zaufanej binarki
ISC, a nie izolacja dowolnego programu lub dowolnych plików z dyrektywami `include`.

**Weryfikacja 10 października 2026:** adapter sprawdził kopię autentycznego
`dhcpd.conf` i wygenerowany przykład obejmujący wyrażenie nazw hostów, pulę,
rezerwacje i podsieć tylko z rezerwacjami. ISC DHCP 4.4.3-P1 zaakceptował oba
pliki i odrzucił celowo błędną składnię. Binarkę wyodrębniono z pakietu Debiana
`isc-dhcp-server_4.4.3-P1-8_amd64.deb` do `/tmp/dhcp-tool-parser/extracted`,
bez instalacji pakietu i uruchamiania usługi. Ta ścieżka jest tymczasowa,
nie stanowi trwałej instalacji walidatora.

`docs/examples/dhcp-config.json` jest syntetycznym przykładem dla testów ISC,
nie autentycznym wzorcem Gaia. Testy tego przykładu dla obu nazw profili
potwierdzają składnię ISC; `gaia_compatibility` pozostaje `unverified`.
Referencją formatu obu profili w MVP jest `dhcpd copy.conf`, zgodnie z potwierdzeniem użytkownika. Potwierdzenie formatu nie zmienia wyniku automatycznego sprawdzenia na test urządzenia.

Testy procesowe działają bez zainstalowanego ISC. Testy z rzeczywistym parserem
włączają się po ustawieniu `DHCPD_PARSER_PATH`:

```sh
DHCPD_PARSER_PATH=/absolute/path/to/dhcpd uv run --env-file .env.test pytest --reuse-db
```

## Wspólna walidacja MVP

`validate_configuration(config, complete=False)` waliduje edycję draftu.
`render_mvp(config)` wymaga kompletnej aktywnej konfiguracji z jedną aktywną
pulą na aktywną podsieć. `prepare_artifact` łączy ten sam etap z opcjonalnym
parserem i raportem SHA-256, bez HTTP i zapisu wersji; jest również punktem
integracji publikacji w etapie 5. API i zasady błędów opisano w `validation-api.md`.
Golden files obu profili są niezależnie zapisanymi syntetycznymi oczekiwanymi
wynikami, bez deklaracji sprawdzenia działania na urządzeniu.

## Adresy interfejsów klastra

Pole „Adresy interfejsów IPv4” przyjmuje adresy członków klastra, np.
`192.0.2.2, 192.0.2.3`, oddzielone przecinkiem lub spacją. Wszystkie muszą
należeć do podsieci, być różne i nie mogą być adresem sieci ani broadcast.
Każdy z nich jest chroniony przed użyciem w puli DHCP i rezerwacji. Można
podać również VIP; bramę nadal ustawia się osobno w polu „Brama IPv4”.
Puste pole usuwa tę ochronę. Limit: 64 adresy.

API oraz JSON `options` w CSV używają dotychczasowego klucza
`interface_address`, teraz także jako listy, np.
`{"interface_address":["192.0.2.2","192.0.2.3"]}`. Pojedynczy tekstowy adres
z wcześniejszych konfiguracji nadal jest obsługiwany. `null` usuwa opcję
w API; w CSV usunięcie klucza z zastępującego obiektu `options` ją usuwa.
Lista jest zachowywana w historii, przy przywracaniu wersji i w backupie.

Pole służy do walidacji kolizji adresów. Nie tworzy dyrektyw DHCP ani nie
konfiguruje interfejsów lub mechanizmu ClusterXL. Nie stanowi potwierdzenia
zgodności klastra z konkretną wersją Gaia na urządzeniu.
