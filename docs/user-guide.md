# Przygotuj konfigurację i zapisz jej historię

Ta instrukcja prowadzi od dodania firewalla do pobrania wersji i zapisania ręcznej deklaracji wdrożenia. Nie opisuje wgrywania pliku na Gaia. Instalację panelu i konta przygotowuje administrator według [instrukcji instalacji](installation.md) i [zasad dostępu](security.md).

## Zaloguj się i wybierz firewall

Otwórz panel w LAN/VPN, na obecnym serwerze `http://192.168.1.32:8080`. Zaloguj się kontem lokalnym. Dostępne działania zależą od roli:

| Rola | Dostępne działania |
| --- | --- |
| reader | Odczyt przypisanych firewalli, historii i plików |
| editor | Odczyt, edycja konfiguracji i publikacja wersji przypisanych firewalli |
| operator | Odczyt oraz ręczna ewidencja wdrożeń przypisanych firewalli |
| admin | Wszystkie firewalle, konfiguracja, publikacja, ewidencja i pobranie backupu |

Na **Liście firewalli** administrator wybiera **Dodaj firewall**, podaje nazwę i profil R81.10 albo R82.10. Dwa firewalle mogą mieć tę samą adresację; ich konfiguracja i historia pozostają oddzielne. Archiwizacja urządzenia zachowuje historię i blokuje zmiany.

## Dodaj podsieć, pulę i rezerwację

Otwórz wybrany firewall i zakładkę **Konfiguracja**. Ustaw opcje globalne, jeśli chcesz je dziedziczyć w podsieciach: czasy dzierżaw w sekundach, domenę i od jednego do trzech adresów DNS. Opcja lokalna zastępuje globalną; usunięcie lokalnej przywraca dziedziczenie.

1. Wybierz **Dodaj podsieć**. Podaj nazwę, CIDR sieci i opcjonalną bramę oraz adres interfejsu.
2. Wybierz **Dodaj pulę**. Podaj początek i koniec w tej podsieci. W MVP aktywna podsieć wymaga dokładnie jednej aktywnej puli.
3. Wybierz **Dodaj rezerwację**. Podaj bezpieczną nazwę hosta, MAC i adres IPv4 poza aktywną pulą.
4. Zapisz formularz. Popraw pola oznaczone błędem przed dalszą pracą.

Adres sieci, broadcast, brama i adres interfejsu nie mogą być przydzielane klientom. Aktywne rezerwacje nie mogą powtarzać IP ani MAC w obrębie firewalla. Wyłączone elementy nie trafiają do pliku. Całkowicie pusta aktywna konfiguracja blokuje publikację.

Każde usunięcie wymaga potwierdzenia. Usunięcie podsieci obejmuje jej pulę i rezerwacje. Usunięcie elementów roboczych nie zmienia opublikowanych wersji ani audytu.

## Zweryfikuj i opublikuj wersję

Wybierz **Walidacja i podgląd** i sprawdź dane oraz cały plik. Wyniki oznaczają różne poziomy sprawdzenia:

- Walidacja danych: adresacja, zakres opcji i reguły MVP
- Kontrola ISC: składnia pliku zaakceptowana lub odrzucona przez skonfigurowany parser; brak parsera nie jest sukcesem
- Zgodność Gaia: zakres potwierdzony referencją i deklaracją użytkownika; bez wykonanych testów na urządzeniach obu wersji

Po zmianie konfiguracji wykonaj nowy podgląd. Wybierz publikację i podaj opis zmiany. Backend ponownie waliduje bieżącą rewizję i atomowo zapisuje wersję oraz artefakt. Błąd danych lub parsera blokuje zapis wersji.

Jeżeli inny użytkownik zmienił konfigurację, panel zgłosi konflikt. Zachowaj potrzebne lokalne wartości, odczytaj aktualne dane i porównaj je przed ponowną edycją. Nie traktuj konfliktu jako zapisu zakończonego sukcesem.

## Pobierz i porównaj wersje

Otwórz **Wersje** i szczegóły wybranej wersji. Pobierz jej `dhcpd.conf`. Pobieranie zwraca zapisane bajty, również dla starej wersji; nie generuje pliku ponownie. Szczegóły zawierają autora, czas, opis, profil, rewizję, liczbę bajtów i SHA-256.

Porównaj dwie wersje lub użyj ostatniej ręcznie zadeklarowanej udanej wersji jako bazy. Diff pokazuje zmiany danych i tekstu. Brak udanego wpisu wdrożenia oznacza brak takiej domyślnej bazy.

Opublikowanie lub pobranie wersji nie oznacza wdrożenia na urządzeniu. Panel nie komunikuje się z firewallem.

## Zapisz deklarację wdrożenia i rollbacku

W zakładce **Ewidencja** operator lub administrator wybiera wersję i rejestruje zdarzenie. Podaj czas zdarzenia ze strefą czasową, wynik, notatkę i opcjonalny numer zgłoszenia. Czas zapisu i autora ustala serwer. Możesz wpisać ręcznie otrzymany SHA-256; aplikacja porównuje go z artefaktem, ale nie odczytuje urządzenia.

Przy korekcie wpisu podaj uzasadnienie. Historia zachowuje poprzednią i nową wartość oraz autora korekty. Wpis wsteczny może zmienić chronologię zadeklarowanych zdarzeń; nie zmienia zapisanych artefaktów.

Aby udokumentować powrót do starej konfiguracji:

1. Otwórz i pobierz wcześniejszą wersję.
2. Po wykonaniu działań poza aplikacją zapisz nowy wpis ewidencji dla tej wersji z wynikiem i uzasadnieniem rollbacku.
3. Jeżeli chcesz też wrócić do niej w edytorze, wybierz **Odtwórz do konfiguracji roboczej** i potwierdź zastąpienie draftu.

Odtworzenie draftu nie tworzy deklaracji wdrożenia ani nowej wersji. Nową wersję publikujesz osobno. Instrukcje wykonywania zmian na Gaia pozostają poza zakresem aplikacji.

## Sprawdź autora i wartości przed zmianą

W **Historii operacji** filtruj obiekt i rodzaj operacji. Otwórz szczegóły, aby sprawdzić autora, czas oraz wartości przed i po zmianie. Konta autorów dezaktywuj zamiast usuwać. Rejestr operacji i wersje nie mają funkcji ręcznego kasowania.

## Pobierz backup aplikacji

Administrator wybiera **Administracja → Pobierz najnowszy backup**. To zaszyfrowany eksport całej bazy i konfiguracji, osobny od pliku DHCP dla firewalla. Zapisz go na innym komputerze, a klucz przechowuj oddzielnie. Szczegóły i obsługa błędów: [pobranie backupu i odtworzenie](backup-restore.md).

## Import i eksport CSV

Zakładka **CSV** obsługuje całą konfigurację wybranego firewalla. Import najpierw pokazuje zmiany i wymaga potwierdzenia każdego usunięcia; zapis dotyczy konfiguracji roboczej. Format, limity i procedura: [csv.md](csv.md).
