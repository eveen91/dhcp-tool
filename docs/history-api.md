# Publikacja i historia — etap 5

Wszystkie trasy są pod `/api/v1/firewalls/{firewall_id}/`. Wymagają sesji
oraz dostępu do wskazanego urządzenia. Sesje i CSRF opisano w `security.md`.
Czytelnik, edytor, operator i administrator mogą odczytywać dostępną historię.
Publikacja i odtwarzanie wymagają roli editor/admin; zarchiwizowany firewall
pozwala tylko na odczyt historii, porównania i pobieranie.

| Ścieżka | Metody i wynik |
| --- | --- |
| `versions/` | GET paginowana historia; POST publikacja |
| `versions/{version_id}/` | GET metadane oraz pełna niezmienna migawka |
| `versions/{version_id}/artifact/` | GET dokładne zapisane bajty `dhcpd.conf` |
| `versions/{version_id}/restore/` | POST skopiowanie migawki do draftu |
| `diff/?from={version_id}&to={version_id}` | GET porównanie dwóch wersji tego urządzenia |
| `diff/?to={version_id}` | GET porównanie z ostatnią ręcznie potwierdzoną udaną wersją |

## Publikacja

POST versions/ przyjmuje `{"description":"Opis zmiany"}`. Opis jest wymagany,
nie może być pusty lub zawierać wyłącznie spacji i ma limit 2000 znaków.
Nagłówki X-CSRFToken i X-Config-Revision są wymagane. Nie przyjmujemy migawki,
artefaktu, numeru, autora, profilu ani ścieżki parsera od klienta.

Pierwsza krótka transakcja blokuje firewall, sprawdza rewizję i przechwytuje
spójne ustawienia, obiekty z UUID, metadane firewalla i tożsamość autora.
Wspólny prepare_artifact sprawdza kompletność MVP, generuje plik i opcjonalnie
kontroluje ISC poza transakcją. Plik otrzymuje komentarz Published version z
UUID publikowanej wersji; UUID identyfikuje ją niezależnie od numeru w historii.
Komentarz jest częścią bajtów sprawdzanych przez parser i objętych SHA-256.

Druga transakcja ponownie sprawdza dostęp, aktywność konta, ważność sesji
po zmianie hasła, archiwizację i rewizję. Edycja lub
zmiana metadanych podczas generowania daje 409, odebranie przypisania 404,
a odebranie roli edytora 403. Numer przydzielamy pod blokadą firewalla jako
max(number)+1. Numery są unikalne i rosną osobno dla każdego urządzenia.
Wersja, artefakt i audyt publish są zapisywane atomowo. Awaria któregokolwiek
zapisu wycofuje całość i nie zużywa numeru. Równoczesne publikacje tej samej
rewizji mogą utworzyć dwie wersje z różnymi opisami i kolejnymi numerami.

Sukces daje 201, metadane wersji, Location oraz X-Config-Revision. Publikacja
nie zmienia konfiguracji roboczej i nie zwiększa jej rewizji. Base_version draftu
wskazuje źródło odtworzenia, a nie ostatnią publikację.

Pusta aktywna konfiguracja, brak aktywnej puli albo błędne dane blokują zapis.
Brak parsera jest jawnym parser_unavailable i nie blokuje publikacji zgodnie
z opcjonalnym charakterem kontroli. Błąd składni daje 400; awaria/timeout parsera
503. Wynik walidacji, wersja parsera, Python/system, profil i wersja generatora
zostają zapisane; gaia_compatibility pozostaje unverified. Publikacja nie jest
potwierdzeniem działania na urządzeniu i nie komunikuje się z appliance.

## Niezmienność i pobieranie

Migawka zawiera pełne dane, także nieaktywne elementy i opisy, bez zależności
od przyszłych zmian rekordów roboczych. Artefakt przechowuje dokładne bajty w
PostgreSQL oraz SHA-256. Pobranie zwraca je bez uruchamiania generatora/parsera,
z Content-Disposition attachment; filename="dhcpd.conf", X-Content-SHA256,
X-Version-ID i X-Version-Number. Zmiana nazwy/profilu firewalla, generatora
lub usunięcie danych roboczych nie zmienia wcześniejszych plików.

API nie udostępnia PATCH/DELETE wersji ani artefaktów. Migracja 0003 dodaje
wyzwalacze PostgreSQL odrzucające UPDATE/DELETE obu tabel, również przez ORM
lub przyszły panel administracyjny. Nie udostępniamy edycji historii w adminie.
Baza testowa może być czyszczona przez Django TRUNCATE; nie jest to operacja API.
Historia nie jest automatycznie usuwana. Nie ustalono okresu przechowywania ani procedury ręcznego usuwania.
Konta autorów z historią należy dezaktywować, nie usuwać: próba SET NULL autora
przy usunięciu konta również naruszyłaby niezmienność wersji.

Listę można filtrować search po opisie oraz page/page_size (50, maksymalnie 100),
sortować number/-number/created_at/-created_at; domyślnie -number,id. Szczegóły
udostępniają migawkę; lista wyłącznie metadane i raport. Wszystkie odpowiedzi,
również pliki i błędy, mają no-store. Identyfikatory wersji i from/to zawsze są
rozwiązywane w obrębie wskazanego firewalla, nawet gdy użytkownik ma oba urządzenia.

## Porównania

Diff tekstowy to unified diff dokładnych zapisanych plików. Diff semantyczny
porównuje metadane firewalla, opcje globalne, podsieci, pule i rezerwacje po UUID.
Zmiana nazwy jest zmianą pola, a nie usunięciem i dodaniem obiektu. Pomijamy
rewizje, autorów publikacji i czasy utworzenia rekordów jako metadane procesu.
Zmiany mają kind, object_type, object_id, field, before i after.

Parametr to jest wymagany. Bez from bazą jest ostatni wpis successful,
wybrany według occurred_at, następnie created_at i UUID malejąco. Wpisy failed,
planned i cancelled nie zmieniają bazy. Jest to deklaracja operatora;
manual_deployment=true wskazuje wykorzystanie tej bazy. API wpisów opisano w `deployments-api.md`. Przy braku udanej deklaracji zwracamy 200, from=null,
baseline_reason=no_successful_deployment, text=null i pustą listę semantic.
Nie zastępujemy jej po cichu ostatnią publikacją.

## Odtworzenie konfiguracji roboczej

POST restore/ przyjmuje pusty JSON {} i wymaga CSRF oraz aktualnej rewizji
konfiguracji docelowej. Kopiuje ustawienia i obiekty ze starej migawki z tymi
samymi UUID. Nie zmienia metadanych firewalla ani jego obecnego profilu:
zmiana profilu pozostaje operacją administratora. Format obu profili MVP jest
wspólny; odtworzone dane walidujemy według bieżących reguł i profilu.
Czasy utworzenia odtworzonych rekordów dotyczą odtworzenia, a stare pozostają
w niezmiennej migawce źródłowej. Konfiguracja otrzymuje base_version i nową
rewizję. Audyt restore zapisuje pełny stan przed/po w tej samej transakcji.

Nieaktualna rewizja blokuje nadpisanie; awaria audytu lub walidacji przywraca
cały poprzedni draft. Odtworzenie nie tworzy wersji, nie cofa numeracji, nie
zmienia artefaktów ani wpisów wdrożenia. Nowa publikacja wymaga osobnego opisu.
Panel wymaga ostrzeżenia i potwierdzenia nadpisania przed odtworzeniem draftu.

Import CSV modyfikuje jedynie draft i ewentualnie metadane firewalla; nie tworzy wersji ani wpisu wdrożenia. Po imporcie wykonaj walidację/podgląd pliku DHCP i osobną publikację z opisem. Eksport CSV odzwierciedla dane robocze, a pobranie artefaktu — dokładne bajty wybranej niezmiennej wersji.
