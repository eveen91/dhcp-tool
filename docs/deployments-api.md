# Ewidencja ręcznych wdrożeń i audyt

Ewidencja zapisuje deklaracje użytkownika. Aplikacja nie łączy się z appliance,
nie przesyła konfiguracji i nie potwierdza, że urządzenie jej używa. Pobranie pliku,
publikacja i odtworzenie konfiguracji roboczej nie tworzą wpisu wdrożenia.

## Dostęp i endpointy

Wszystkie ścieżki mają prefiks `/api/v1/firewalls/{firewall_id}/`.

| Metoda | Ścieżka | Przeznaczenie |
| --- | --- | --- |
| GET, POST | `deployments/` | Lista i rejestracja deklaracji |
| GET, PATCH | `deployments/{deployment_id}/` | Odczyt i audytowana korekta |
| GET | `deployments/latest/` | Ostatnia zadeklarowana udana próba lub `deployment: null` |
| GET | `audit/` | Historia operacji bez dużych migawek |
| GET | `audit/{audit_id}/` | Autor, czas i wartości przed/po |

Odczyt wymaga sesji oraz dostępu do wybranego firewalla. Wszystkie cztery role
mogą czytać swoją historię. Rejestracja i korekta wymagają roli `operator` lub
`admin`, aktywnego firewalla, JSON i tokenu CSRF. Rola `editor` nie może wpisywać
wyników wdrożeń. Identyfikatory wersji, wpisu i audytu są zawsze sprawdzane
w zakresie firewalla, także przy dostępie do obu urządzeń. Obcy zasób zwraca 404.
Historia nie ma API usuwania ani edycji audytu. Odpowiedzi mają `no-store`.

## Rejestracja

POST przyjmuje `version_id`, `status`, `occurred_at` oraz opcjonalnie `note`
(do 2000 znaków), `ticket` (do 150) i `supplied_hash` (64 cyfry szesnastkowe).
Puste pola opcjonalne są dozwolone. Nieznane pola są odrzucane. Operator jest
aktualnym zalogowanym użytkownikiem; czas wpisu `created_at` ustala serwer.
`occurred_at` musi zawierać strefę (`Z` albo offset). Wynik dotyczący przyszłości
jest odrzucany; tylko `planned` może mieć przyszły czas zdarzenia.

Stany: `planned` — planowana, `successful` — udana, `failed` — nieudana,
`cancelled` — anulowana. Każdy ma `confirmation: manual`. Numer wersji pozostaje
numerem niezmiennego artefaktu, niezależnie od daty jego ponownego użycia.

Ręcznie podany SHA-256 jest normalizowany do małych liter i zachowywany.
`artifact_sha256` pochodzi z zapisanego artefaktu; `hash_comparison` wynosi
`not_supplied`, `match` lub `mismatch`. Niezgodność może zostać zarejestrowana,
również przy deklarowanej udanej próbie. Interfejs wyróżnia ją jako niezgodność.
Żaden z tych wyników nie jest automatyczną weryfikacją urządzenia; wpis nadal
pozostaje deklaracją operatora.

## Wpisy wsteczne i powrót do starszej wersji

Wpisy wsteczne są dozwolone. Ostatnie udane wdrożenie jest wybierane spośród
`successful` według `occurred_at`, następnie `created_at`, następnie UUID, wszystkie
malejąco. Remis czasu zdarzenia rozstrzyga zatem późniejszy czas wpisu, a przy
identycznych obu czasach większy UUID. Czas korekty nie jest kryterium remisu.
Listę ewidencji porządkujemy tak samo, ale pokazujemy również pozostałe wyniki.
Domyślna baza porównania wersji używa dokładnie tej samej reguły.

Późno dodany wpis ze starszym czasem zdarzenia nie zastąpi nowszego udanego
wdrożenia. Nowa udana deklaracja użycia starszego artefaktu z późniejszym czasem
zdarzenia zastąpi bazę porównania, bez zmiany numeracji, artefaktu i wcześniejszych
wpisów. Wpisy nieudane, anulowane i planowane nie zastępują ostatniego udanego.

## Korekty i audyt

PATCH wymaga `expected_revision`, niepustego `correction_reason` (do 2000 znaków)
i co najmniej jednego korygowanego pola deklaracji. Rewizja dotyczy wpisu
wdrożenia, nie konfiguracji roboczej. Pierwszy wpis ma rewizję 1, a korekta ją
zwiększa. Stara rewizja daje 409 `deployment_conflict`; zapis nie jest ponawiany
automatycznie. Interfejs zachowuje lokalne pola. Aby użyć bieżącej rewizji,
należy świadomie odrzucić lokalny formularz i ponownie otworzyć wpis.

Operator oryginalnego wpisu i czas jego utworzenia pozostają zachowane. Zmiana
wersji, czasu lub wyniku może zmienić wybór ostatniego udanego wdrożenia.

Rejestracja i korekta blokują w transakcji wiersz firewalla. Zapis wpisu oraz audytu
jest atomowy; awaria audytu wycofuje cały zapis. Nie zwiększa rewizji konfiguracji.
Zdarzenie `deployment_create` ma `before: null` i `after` zawierające wpis.
`deployment_correct` zapisuje poprzedni wpis w `before`, a w `after` obiekt
`entry` z nowymi wartościami oraz `correction_reason`. Autor audytu to użytkownik,
który wykonał korektę, niezależnie od oryginalnego operatora wpisu.

Lista audytu obejmuje również zmiany konfiguracji, publikacje i odtworzenia,
z autorem, czasem, obiektem, rewizją konfiguracji i identyfikatorem operacji.
Szczegóły są pobierane oddzielnie. Konto z historią należy dezaktywować zamiast
usuwać, zgodnie z zasadami niezmienności wersji.

## Paginacja i filtry

Listy obsługują `page` od 1 i `page_size` od 1 do 100 (domyślnie 50). Nieznane lub
powtórzone parametry są odrzucane. `deployments/` obsługuje filtry `status` oraz
`version_id`; `audit/` — `operation` i `object_type` (maksymalnie 32 znaki).
Audyt sortuje po czasie zapisu i UUID malejąco. Formularz umożliwia wyszukiwanie
wersji po opisie i przechodzenie między stronami także dla starszych artefaktów.

## Audyt importu CSV

Operacja `csv_import` dotyczy draftu wskazanego firewalla. Pełny import zapisuje `before` i `after` jako obiekty z `firewall` (metadane) oraz `draft` (migawka); import samych rezerwacji zapisuje bezpośrednio migawki draftu. Audyt jest atomowy z importem. Import, eksport CSV i pobranie backupu nie tworzą deklaracji wdrożenia.
