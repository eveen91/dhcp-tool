# Import i eksport całej konfiguracji CSV

W panelu wybrać firewall i zakładkę **CSV**. **Eksportuj konfigurację CSV** pobiera konfigurację roboczą: metadane firewalla, opcje globalne, podsieci, pule i rezerwacje. Czytelnicy mogą eksportować; editor i admin mogą importować. Zmiana nazwy, profilu lub innych metadanych firewalla wymaga admina.

1. Pobrać eksport jako szablon. Zachować nagłówek, przecinki jako separator i kodowanie UTF-8; BOM jest dozwolony.
2. Edytować wybrane rekordy. Można pozostawić tylko wiersze wymagające zmian; brak wiersza nie usuwa elementu.
3. Wczytać plik lub wkleić treść i kliknąć **Sprawdź i pokaż zmiany**. Podgląd nie zapisuje danych.
4. Sprawdzić wartości przed i po, a następnie osobno potwierdzić każde usunięcie, również na dalszych stronach podglądu.
5. Kliknąć **Zastosuj import**. Cały import zapisuje się atomowo w konfiguracji roboczej i historii audytu. Publikacja wersji i ewidencja wdrożenia pozostają osobnymi czynnościami.

## Format

Nagłówek:

```csv
kind,action,id,subnet_cidr,name,start,end,ip,mac,description,interface,active,options
```

| kind | Znaczenie | Pola danych |
| --- | --- | --- |
| firewall | Wybrany firewall | name, description, options: profile, location, management_address |
| settings | Opcje globalne | options: default_lease_time, max_lease_time, domain, dns |
| subnet | Podsieć | subnet_cidr, name, description, interface, active, options |
| pool | Jedna pula podsieci | subnet_cidr, start, end, description, active |
| reservation | Rezerwacja | subnet_cidr, name, ip, mac, description, active |

`action=upsert` dodaje lub zmienia rekord; `action=delete` usuwa istniejący rekord. Przy zmianie zachować `id` z eksportu. Przy dodaniu podsieci, puli lub rezerwacji pozostawić `id` puste. `settings` ma zawsze puste `id`; nie można usuwać rekordu settings ani firewalla. `active` przyjmuje dokładnie `true` lub `false`. Nie używać pól innych niż wskazane dla danego rodzaju rekordu.

`options` jest obiektem JSON, odpowiednio cytowanym zgodnie z CSV. Najłatwiej edytować komórkę w arkuszu i zapisać jako CSV z przecinkami. Przykład wartości komórki: `{"domain":"example.org","dns":["192.0.2.53"]}`. Obiekt zastępuje opcje danego rekordu; `{}` je czyści. Podsieć dopuszcza także `gateway`, `interface_address` i `gaia_host_name_fallback` oraz wymienione opcje globalne. Dowolne dyrektywy DHCP są zabronione.

Pule i rezerwacje wskazują `subnet_cidr` podsieci istniejącej po imporcie; można dodać nową podsieć wraz z dziećmi w jednym pliku. Zmieniając CIDR, zmienić również odwołania jej puli i rezerwacji w tym imporcie. Przy usuwaniu podsieci pominąć jej dzieci w pliku lub oznaczyć je `delete`; pozostawienie `upsert` dla dziecka usuwanej podsieci jest sprzeczne i zostanie odrzucone. Podgląd pokazuje każde usuwane dziecko nawet wtedy, gdy nie występuje w CSV.

## Limity i zabezpieczenia

Import: 32 KiB UTF-8 i 500 rekordów danych. Eksport obejmuje całą konfigurację bez tego limitu. Duży eksport należy podzielić na partie zmian z powtórzonym nagłówkiem. Podgląd jest ważny 10 minut, przypisany do konta, firewalla i rewizji. Po zmianie konfiguracji lub wygaśnięciu należy wykonać nowy podgląd. Import wymaga sesji i CSRF; nie przyjmuje identyfikatorów z innych firewalli.

Eksport zabezpiecza komórki mogące zostać zinterpretowane przez arkusz jako formuły początkowym apostrofem; importer odwraca to zabezpieczenie. Plik zawiera dane sieciowe i należy przechowywać go zgodnie z zasadami dostępu do konfiguracji.

Walidacja używa dotychczasowych reguł konfiguracji i whitelisty Gaia: jednej puli na aktywną podsieć, rezerwacji poza pulą i dozwolonych opcji. Import nie stanowi weryfikacji konfiguracji na urządzeniu Gaia i nie poszerza zgodności R81.10/R82.10. Autentyczne pliki `dhcpd.conf` i `dhcpd copy.conf` nie są zmieniane.

API całej konfiguracji: `GET /api/v1/firewalls/{id}/csv/config/export/`, `POST .../preview/` z `{"csv":"..."}`, `POST .../apply/` z tokenem podglądu i `confirm_deletions=true`, jeśli są usunięcia. Oba POST wymagają `X-Config-Revision`. Zachowane API `/csv/export/`, `/csv/preview/`, `/csv/apply/` obsługuje wyłącznie rezerwacje.

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
