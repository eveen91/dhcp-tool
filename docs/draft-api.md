# Konfiguracja robocza — etap 3

API działa pod `/api/v1/firewalls/`. Sesje i CSRF opisano w `security.md`.
Administrator tworzy urządzenia i zmienia ich metadane, profil oraz archiwizację.
Edytor zmienia konfigurację tylko przypisanych urządzeń. Odczyt wymaga roli
reader/editor/operator/admin i przypisania, z wyjątkiem globalnego administratora.
Firewall nie ma operacji DELETE; archiwizacja zachowuje konfigurację i historię.
Administrator może cofnąć archiwizację. Zarchiwizowane urządzenie pozwala na odczyt,
ale blokuje edycję konfiguracji. Nazwa firewalla jest bezpiecznym identyfikatorem
ASCII używanym również w nagłówku generatora.

## Operacje

| Zasób względem `/api/v1/firewalls/` | Metody |
| --- | --- |
| Pusta ścieżka | GET lista; POST utworzenie urządzenia |
| `{firewall_id}/` | GET; PATCH metadane i archiwizacja |
| `{firewall_id}/draft/` | GET migawka konfiguracji i rewizja; PATCH opcje globalne |
| `{firewall_id}/subnets/` | GET lista; POST podsieć |
| `{firewall_id}/subnets/{subnet_id}/` | GET z pulą/rezerwacjami; PATCH; DELETE |
| `{firewall_id}/subnets/{subnet_id}/pool/` | GET; PUT utworzenie/zastąpienie jednej puli; DELETE |
| `{firewall_id}/reservations/` | GET lista; POST rezerwacja |
| `{firewall_id}/reservations/{reservation_id}/` | GET; PATCH; DELETE |

OpenAPI zawiera schematy wejścia i odpowiedzi, wymagane nagłówki oraz błędy.
Tworzenie firewalla zwraca 201 i inicjalizuje draft z rewizją 1. Każdy następny
zapis, także metadanych i DELETE, wymaga `X-Config-Revision` oraz `X-CSRFToken`.
Po sukcesie nowa rewizja jest w nagłówku odpowiedzi `X-Config-Revision`.
Nieaktualna rewizja zwraca 409 z `error.current_revision`; brak/błędny nagłówek
zwraca 400. Klient powinien odświeżyć dane i pozwolić użytkownikowi rozstrzygnąć
konflikt. Nie ponawiać zapisu automatycznie na nowej rewizji.

Przykład kolejności budowania konfiguracji:

1. POST firewall: `{"name":"fw-biuro","profile":"R81.10"}`.
2. POST subnet: `{"name":"Biuro","cidr":"10.0.0.0/24","gateway":"10.0.0.1"}`.
3. PUT pool: `{"start":"10.0.0.10","end":"10.0.0.100"}`.
4. POST reservation: `{"subnet_id":"UUID","name":"drukarka","mac":"00:11:22:33:44:55","ip":"10.0.0.5"}`.

UUID podsieci pochodzi z odpowiedzi kroku 2. Po każdym zapisie używać nowej
rewizji. Nazwa rezerwacji jest identyfikatorem bloku hosta ASCII; UUID rekordu
pozostaje stały po zmianie nazwy. MAC normalizujemy do małych liter z dwukropkami.
Opisy i nazwy wyświetlane podsieci nie są renderowane jako dyrektywy.

Opcje globalne: domain, dns, default_lease_time, max_lease_time. Podsieć może
nadpisać te opcje oraz dodać gateway, interface_address i gaia_host_name_fallback.
PATCH z null usuwa opcję i przywraca dziedziczenie. PUT puli wymaga start/end;
id istniejącej puli pozostaje stały. Pole subnet_id rezerwacji zawsze rozwiązuje
się w obrębie bieżącego firewalla, także przy przeniesieniu rezerwacji.

## Listy i walidacja

Listy mają page/page_size (50 domyślnie, maksymalnie 100), search, ordering,
a dla podsieci i rezerwacji active. Rezerwacje przyjmują dodatkowo subnet_id.
Search obejmuje nazwę/CIDR podsieci i nazwę/MAC/IP rezerwacji. Sortowanie name
lub created_at; rezerwacje dodatkowo ip/mac. IP sortujemy przez PostgreSQL inet,
numerycznie. Nieobsługiwane filtry/sortowanie zwracają 400.

Każdy zapis waliduje całą konfigurację przez reguły generatora. Odrzucamy błędne
adresy, nieobsługiwane /31 i /32, nakładanie aktywnych podsieci, błędne zakresy,
rezerwacje w puli, duplikaty nazw/MAC i niebezpieczne opcje. Walidujemy również
nieaktywne dane, aby wyłączenie elementu nie omijało kontroli pól. Nazwy/MAC
rezerwacji są unikalne w całym firewallu; adresy mogą się powtarzać na innych
urządzeniach. Nieznane pola i próby narzucenia właściciela są odrzucane.

Draft może być pusty lub niekompletny, np. podsieć przed dodaniem puli. To stan
roboczy, nie gotowy artefakt MVP. Endpointy walidacji/podglądu są zaimplementowane w etapie 4 (`validation-api.md`)
i wymagają jednej aktywnej puli na aktywną podsieć oraz blokują pustą aktywną
konfigurację. Publikacja w etapie 5 stosuje te same reguły (`history-api.md`). Nie deklarujemy zgodności działania
na urządzeniu na podstawie samego zapisu draftu.

Żądania JSON mają limit 64 KiB. Błędy wskazują pola bez odsyłania surowych
wartości, błędów SQL, konfiguracji czy komunikatów parsera. Odpowiedzi mają no-store.

## Trwałość i audyt

Transakcja blokuje firewall, sprawdza rewizję, zapisuje obiekt, waliduje wynik,
zwiększa rewizję i zapisuje AuditEvent z autorem, UUID żądania, operacją oraz
stanem przed/po. Awaria któregokolwiek kroku wycofuje wszystko. Audyt jest
przechowywany w PostgreSQL, osobno dla każdego firewalla; nie jest logiem procesu
i jest dostępny przez chronione API historii operacji (`deployments-api.md`). Usunięcie podsieci zapisuje
w audycie również jej pulę i rezerwacje. Panel wymaga ostrzeżenia i potwierdzenia każdego usunięcia, również dzieci usuwanej podsieci.

Migracja 0002 zachowuje istniejące firewalle i inicjalizuje ich drafty. Dodaje
również modele Version, Artifact i Deployment jako fundament etapów 5 i 8.
Publikacja, pobieranie i diff działają w etapie 5; ewidencja wdrożeń i audyt działają w etapie 8 (`deployments-api.md`);
niezmienność wersji/artefaktów oraz ich operacje są zaimplementowane w etapie 5
(`history-api.md`). Ewidencja wdrożeń ma osobne wpisy i audytowane korekty. Powiązania PROTECT chronią dane historyczne przed kaskadowym usunięciem
firewalla; usuwanie roboczych podsieci/rezerwacji nie usuwa wersji ani audytu.

Testy wykorzystują osobny PostgreSQL: pełny CRUD, role, CSRF, obce UUID w ścieżce,
query i JSON, jednakową adresację dwóch firewalli, cofanie błędnych zapisów,
awarię audytu, zachowanie historii, migrację wcześniejszych danych i równoczesne
zapisy tej samej rewizji (jeden sukces, jeden 409).

## Zmiany przez CSV

Import całej konfiguracji jest dodatkowym sposobem edycji tego samego draftu, z rewizją, kontrolą dostępu i walidacją generatora. Podpisany podgląd nie zapisuje danych; zastosowanie importu zapisuje całą partię atomowo wraz z audytem `csv_import`. Zachowuje UUID oraz daty utworzenia istniejących podsieci i rezerwacji. Nie zmienia wersji historycznych ani base_version draftu. Zmiana metadanych firewalla wymaga admina. Format, kaskady usuwania i limity: [csv.md](csv.md).

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
