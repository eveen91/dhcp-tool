# Projekt interfejsu DHCP Tool

Specyfikacja wizualna rozpoczęta w etapie 6, zastosowana w panelu i uzupełniona po wdrożeniu MVP oraz CSV. Zgodna z PRODUCT.md i plan.MD.
Podgląd: [docs/ui-reference.html](docs/ui-reference.html). To samodzielny projekt
z danymi przykładowymi, bez połączenia z API. Nie zmienia działającej aplikacji.
Istniejąca konfiguracja Impeccable: `buildPath: code`.

## Kierunek i układ

Polski panel dla administratora DHCPv4 Check Point Gaia. Desktop-first: główne
widoki projektujemy dla 1280–1600 px. Treść wyrównana do lewej; mały nagłówek,
tabele i formularze zamiast dużego ekranu powitalnego. Charakterystycznym elementem
jest stały pasek kontekstu urządzenia, a nie dekoracja. Bez gradientów, cieni kart,
animacji wejścia i zewnętrznych zasobów. Zgodność z Gaia ma pierwszeństwo przed
swobodą formularzy: jedna pula na podsieć, rezerwacje poza pulą, whitelist opcji.

Plan sprawdzono względem briefu: odrzucono duży nagłówek obecnej strony statusu
oraz kafelki z licznikami. Podstawowym widokiem pracy jest tabela rezerwacji
wybranej podsieci. CSV całej konfiguracji dodano jako zatwierdzone rozszerzenie z podglądem zmian. Import plików dhcpd.conf, SSO, monitoring urządzeń i SSH pozostają poza zakresem.

```text
DHCP Tool                                      konto / rola / Wyloguj
Lista firewalli | fw-warszawa | Gaia R81.10 | Aktywny
Robocza: rewizja 18 | Opublikowana: 41 | Ręcznie potwierdzona: 39
Konfiguracja | CSV | Walidacja i podgląd | Wersje | Ewidencja
------------------------------------------------------------------
Podsieci             Wybrana podsieć: 192.0.2.0/24
192.0.2.0/24         Opcje i jedna pula             Zapisz zmiany
198.51.100.0/24      Rezerwacje / wyszukiwanie / paginacja
                     Nazwa       IP         MAC           Działania
```

Pasek kontekstu pozostaje widoczny przy przewijaniu, także w dialogach (nazwa
firewalla w ich tytule). Na liście urządzeń widnieje „Wybierz firewall”, bez
pozostawiania kontekstu poprzedniego urządzenia. Administracja ma kontekst globalny.
Archiwalny firewall ma etykietę „Archiwalny — tylko odczyt”. Historyczny profil
wersji pokazujemy osobno od aktualnego profilu firewalla.

Na ekranach poniżej 900 px boczna lista podsieci przechodzi nad formularz.
Tabele mają własne przewijanie poziome z nazwanym obszarem, bez przewijania całej
strony. Pasek kontekstu może mieć kilka wierszy, ale nie zasłania pól i fokusu.

## Typografia i tokeny

Lokalne fonty systemowe: `Segoe UI`, `DejaVu Sans`, Arial, sans-serif; IP, CIDR,
MAC, hash i plik: `Cascadia Mono`, `DejaVu Sans Mono`, Consolas, monospace.
Tekst 14 px / 1.5, pomoc 12 px / 1.5, tytuł ekranu 22 px / 1.25, sekcje 16 px.
Wagi 400/600; bez etykiet pisanych kapitalikami. Akapity maksymalnie 76 znaków.

| Token | Wartość | Zastosowanie |
|---|---|---|
| canvas | #f3f5f7 | Tło przestrzeni pracy |
| surface | #ffffff | Formularze i tabele |
| ink | #182a34 | Tekst podstawowy |
| muted | #52616b | Tekst pomocniczy |
| line | #c8d1d8 | Podziały tabel i sekcji |
| action | #175d72 | Akcje podstawowe i fokus |

Kolory semantyczne: sukces #23623c na #edf6ef; ostrzeżenie #805000 na #fff5df;
błąd #a12626 na #fff0ef. Znaczenie zawsze podane tekstem. Kolor obramowania
formularza: muted; line służy do podziałów, nie jako jedyny sygnał kontrolki.
Cel projektowy: kontrast tekstu co najmniej 4.5:1, kontrolek i fokusu 3:1;
formalny audyt dostępności należy do T09.8.

Odstępy 4/8/12/16/24/32 px; margines ekranu 24 px; kontrolki minimum 40 px,
wiersze tabel minimum 44 px; promień kontrolek 4 px, dialogów 6 px. Brak cieni
poza opcjonalną warstwą modalną. Widoczny fokus: obrys action 3 px, odstęp 2 px.
Dane adresowe nie łamią się wewnątrz wartości. Hash można łamać w szczegółach,
a skrót w tabeli zawsze ma przycisk „Kopiuj pełny SHA-256” i dostęp do całości.
Wartości liczbowe mają cyfry tabelaryczne; sortowanie IP numeryczne po stronie API.

## Nawigacja, role i rozdzielenie stanów

Globalnie: Lista firewalli, Administracja (admin), konto i Wyloguj. Po wyborze
firewalla: Konfiguracja, Walidacja i podgląd, Wersje, Ewidencja. Linki mają
`aria-current="page"`. Dostępne funkcje wynikają z roli i zakresu firewalla;
backend pozostaje źródłem autoryzacji. Reader czyta i pobiera, editor edytuje,
publikuje i odtwarza, operator rejestruje wdrożenia, admin zarządza całością.
Nieuprawnionych akcji nie pokazujemy; odrzucenie żądania nadal obsługujemy.

Trzy niezależne oznaczenia:

- „Konfiguracja robocza · rewizja 18”: zapisane dane edytowalne. Osobny komunikat
  „Niezapisane zmiany w formularzu” dotyczy tylko lokalnych zmian.
- „Opublikowana wersja 41”: niezmienny plik i migawka. Publikacja nie oznacza
  wysłania pliku na firewall. Nie wnioskujemy zmian roboczych z samej rewizji.
- „Ręcznie potwierdzona wersja 39”: ostatni udany wpis według czasu zdarzenia;
  zawsze dopisek „Deklaracja operatora; bez odczytu urządzenia”. Nie używamy
  etykiety „Aktualna konfiguracja urządzenia”.

Brak wpisu oznaczamy „Brak potwierdzonego wdrożenia” wyłącznie po otrzymaniu
odpowiedzi API potwierdzającej ten stan. Niedostępne dane mają etykietę
„Nie można odczytać informacji”. Pobranie pliku nie aktualizuje wdrożenia.

## Ekrany i przepływy

### Lista firewalli

Wyszukiwanie po nazwie, filtr aktywne/archiwalne, tabela: nazwa, profil Gaia,
lokalizacja, stan archiwizacji, „Otwórz”. Paginacja po 50, maksymalnie 100;
bez pobierania całych list lub historii każdego wiersza. Admin: „Dodaj firewall”,
formularz nazwy, profilu R81.10/R82.10, opisu, lokalizacji i opcjonalnego IP
zarządzania; walidacja zgodna z API. Edycja metadanych i archiwizacja dostępne
w szczegółach. Archiwizacja wymaga potwierdzenia skutku tylko do odczytu.
Nie projektujemy usuwania firewalla ani trwałego kasowania historii.

### Edytor konfiguracji

Lista podsieci po lewej: CIDR, nazwa, aktywność; „Dodaj podsieć”. Po prawej:
CIDR/nazwa/opis/aktywność, brama, adres interfejsu, fallback i czasy dzierżawy;
pod nimi jedna pula start/koniec/opis/aktywność. Opcje globalne: domena,
1–3 DNS, domyślny i maksymalny czas dzierżawy. Puste opcjonalne pole oznacza
brak dyrektywy, a dzierżawa podsieci może dziedziczyć opcję globalną.

Rezerwacje: nazwa hosta, IP, MAC, opis, aktywność, Edytuj, Usuń. Wyszukiwanie,
filtr podsieci/aktywności, sortowanie i paginacja po stronie serwera. Edycja
w nazwanym dialogu z jednoznacznym „Zapisz rezerwację”. Pola obowiązkowe opisane
tekstem; jednostki czasu w sekundach. Nie pokazujemy edytora surowych dyrektyw.
Zapis formularza aktualizuje rewizję dopiero po sukcesie API; przycisk blokuje
powtórne wysłanie i wskazuje „Zapisywanie…”. Nie zapisujemy automatycznie.

### Walidacja, podgląd i publikacja

„Sprawdź konfigurację” działa dla konkretnej zapisanej rewizji; niezapisane pola
wymagają wcześniejszego zapisu lub jawnego odrzucenia. Raport osobno pokazuje:
„Dane: poprawne”, „Składnia ISC: sprawdzona / parser niedostępny / błąd”,
„Zgodność Gaia: niezweryfikowana”. Zielony raport ISC nie potwierdza Gaia.
Błąd składni blokuje publikację; brak parsera jest jawnym ostrzeżeniem i zgodnie
z backendem pozwala publikować. Timeout/awaria ma „Ponów sprawdzenie”.

Lista błędów z linkiem do podsieci/rezerwacji i konkretnego pola. Podgląd całego
pliku w `pre`, przewijanie i kopiowanie; liczba bajtów i pełny SHA-256 z API.
Zmieniona rewizja unieważnia raport i podgląd. Publikacja wymaga opisu zmiany
1–2000 znaków; dialog wskazuje nazwę, profil i rewizję. Akcja „Opublikuj wersję”
tworzy wersję, po sukcesie prowadzi do jej szczegółów z pobraniem dhcpd.conf.
Hash podglądu i hash publikacji mogą się różnić przez nagłówek UUID publikacji;
pokazujemy każdy przy właściwym artefakcie, bez deklaracji ich identyczności.

### Wersje i różnice

Tabela: numer, czas z widoczną strefą, autor, opis, profil i zakres walidacji.
Szczegóły tylko do odczytu: metadane, migawka, plik, hash, „Pobierz dhcpd.conf”,
„Porównaj”, „Odtwórz do konfiguracji roboczej” dla editor/admin.
Diff: selektory wersji bazowej i docelowej; domyślna baza ostatniego udanego
ręcznego wpisu. Brak bazy: czytelny pusty stan, możliwość jawnego wyboru wersji;
nie podstawiamy automatycznie ostatniej publikacji. Widoki „Zmiany obiektów”
i „Różnice pliku”. Dodano/usunięto/zmieniono tekstem oraz znakiem +/− i kolorem.

Odtworzenie wymaga dialogu: „Zastąpisz konfigurację roboczą firewalla … migawką
wersji … . Historia i ewidencja pozostaną zachowane. Obecny profil firewalla
pozostanie …”. Anuluj domyślny; potwierdzenie „Odtwórz wersję do roboczej”.
Żądanie z aktualną rewizją; konflikt nie nadpisuje danych. Odtworzenie nie jest
rollbackiem na urządzeniu; ponowne wdrożenie starego artefaktu rejestruje operator.

### Ewidencja ręcznych wdrożeń

Stale widoczne „Wpisy są deklaracjami użytkowników; aplikacja nie łączy się
z firewallem”. Tabela wersja, wynik (planowana/udana/nieudana/anulowana), operator,
czas zdarzenia, czas wpisu, notatka i numer zgłoszenia. Formularz operator/admin:
wersja, czas zdarzenia ze strefą, wynik, notatka, opcjonalny numer zgłoszenia
oraz hash dostarczony ręcznie. Autor/czas wpisu po stronie serwera. Hash oznaczony
„Podany przez operatora”; zgodność z plikiem nie oznacza odczytu appliance.
Starsza wersja dozwolona, numeracja publikacji pozostaje bez zmian. Korekta wpisu
ma jawny ślad audytu. Szczegóły reguł i wdrożonego API opisuje docs/deployments-api.md.

### Administracja i logowanie

Logowanie: nazwa użytkownika, hasło, „Zaloguj”; autocomplete username/current-password,
ogólny komunikat błędnych danych bez ujawniania istnienia konta. Limit prób
pokazuje czas ponowienia. Sesja wygasła: ponowne logowanie bez samoczynnego
ponawiania zapisów; nie utrwalamy haseł ani konfiguracji w localStorage.

Administracja: użytkownicy lokalni, role, zakres firewalli, aktywność; konta autorów
historii dezaktywujemy zamiast usuwać. Nadanie admin wyjaśnia dostęp do wszystkich
firewalli. Historia operacji: kto/kiedy/firewall/operacja i szczegóły przed/po,
filtrowanie/paginacja. Backupy: administrator pobiera najnowszy zaszyfrowany eksport przez przycisk, bez tworzenia nowej kopii tym kliknięciem. Klucz nie jest udostępniany w panelu. Odtwarzanie pozostaje procedurą administratora serwera. Audyt ma działające API; konta i przypisania są zarządzane poleceniami, bez HTTP CRUD użytkowników.

## Stany wspólne i ochrona danych formularza

| Sytuacja | Prezentacja i działanie |
|---|---|
| Pierwsze ładowanie | „Ładowanie konfiguracji…”, aria-busy, bez fikcyjnych wartości |
| Odświeżanie | Zachowane stare dane z etykietą „Odświeżanie”; bez aktywnych zapisów opartych na niepotwierdzonej rewizji |
| Pusta lista | „Brak podsieci” + Dodaj podsieć jeśli rola pozwala; filtr: „Brak wyników” + Wyczyść filtry |
| Awaria sieci/API | „Nie udało się pobrać konfiguracji. Ponów”; pola lokalne zachowane, bez udawanego sukcesu |
| Niejednoznaczny wynik zapisu | „Nie potwierdzono zapisu. Odśwież dane, zanim ponowisz”; publikacji nie ponawiamy automatycznie |
| Brak sesji / 403 | Wyjaśnienie konieczności logowania albo braku prawa, zgodnie z kodem błędu; bez ujawniania obcych obiektów |
| 404 zakresu | „Firewall lub element jest niedostępny”; powrót do listy |
| 409 | „Konfiguracja została zmieniona. Twoje pola nie zostały wysłane ponownie”; aktualna rewizja i świadome odświeżenie |
| Nieaktualny raport | „Konfiguracja zmieniła się od sprawdzenia. Sprawdź ponownie” |

Przy konflikcie zachować lokalny formularz w pamięci do świadomego odrzucenia;
możliwa ręczna kopia jego pól. Nie scalać ani nie nadpisywać automatycznie.
Zmiana firewalla/strony przy niezapisanych polach: dialog „Masz niezapisane zmiany”
z „Zostań” i „Odrzuć i przejdź”; zapis najpierw osobną akcją. Ostrzeżenie
beforeunload dla zamknięcia karty. Po potwierdzonej zmianie firewalla wyczyścić
formularze, selektory wersji, błędy i raporty; anulować żądania i ignorować późne
odpowiedzi według identyfikatora firewalla/żądania. Dane API no-store; bez wspólnego
cache dla kont i urządzeń. Dokładne bytes/hash pliku zawsze po stronie backendu.

## Usuwanie i kompletność

Każde usunięcie rezerwacji, puli lub podsieci otwiera dialog, nawet pojedynczego
elementu. Tytuł i opis wskazują firewall, nazwę, IP/CIDR i skutki. Usunięcie
podsieci wymienia pulę (zakres) oraz rezerwacje (nazwy/IP/MAC), również nieaktywne;
duża lista przewijana, pełna liczba i możliwość zobaczenia wszystkich elementów,
bez ukrywania skutków poza pierwszymi rekordami.

Przykład: „Usunąć podsieć 192.0.2.0/24 z fw-warszawa? Usuniesz również pulę
192.0.2.100–192.0.2.200 i 2 rezerwacje”. Przyciski „Anuluj” (pierwszy fokus)
i „Usuń podsieć i jej elementy” (czerwony). Escape anuluje, Enter poza przyciskiem
potwierdzenia nie usuwa. Po usunięciu fokus wraca do następnego logicznego wiersza
lub nagłówka listy, a wynik jest ogłoszony tekstem.

Robocza konfiguracja może być niekompletna podczas budowania. Gdy usunięcie lub
wyłączenie ostatniej aktywnej podsieci/puli pozostawia pusty albo niekompletny
aktywny wynik, ostrzegamy w dialogu i pokazujemy „Publikacja zablokowana:
wymagana aktywna podsieć z jedną aktywną pulą”. Backend walidacji/publikacji
blokuje taki artefakt. Nie blokujemy możliwości zapisania niekompletnego draftu,
którą świadomie dopuszcza kontrakt API. Dialog zawsze wysyła aktualną rewizję.

## Dostępność i ruch

Semantyczne nagłówki, main/nav, skip-link „Przejdź do treści”; tabele z caption,
kolumnami th/scope oraz aria-sort. Etykiety label/for, pomoc i błąd przez
aria-describedby, aria-invalid dopiero przy błędzie. Podsumowanie błędów otrzymuje
fokus po nieudanym zapisie; link przenosi do pola, otwierając właściwą podsieć.
UUID z API mapujemy na obiekty, nie numery zmiennych wierszy. Sukcesy aria-live
polite; pilny błąd role=alert, bez wielokrotnego ogłaszania tych samych zdarzeń.

Wszystkie akcje natywnymi linkami/przyciskami; Tab/Shift+Tab logicznie, bez dodatnich
tabindex. Dialog z nazwą/opisem, pułapką fokusu, Escape i przywróceniem fokusu.
Widoczne etykiety „Edytuj”/„Usuń”, dostępna nazwa zawiera identyfikator wiersza.
Nie używamy samego hover do ujawniania akcji ani ikon bez nazw. Długie nazwy
zawijamy; nie obcinamy bez możliwości odczytu. Zmiana strony paginacji ogłasza
zakres wyników i pozostawia stabilny fokus. Brak samoczynnych animacji;
opcjonalna zmiana opacity do 120 ms dla reakcji na akcję, reduced-motion wyłącza ją.

## Powiązanie z wdrożonym API

| Ekran | Kontrakt / zależność |
|---|---|
| Sesja | Istniejące auth/session; CSRF, sesja, obsługa limitów |
| Firewalle / edytor | Istniejące firewalls, draft, subnets, pool, reservations; X-Config-Revision dla zapisów |
| Walidacja / podgląd | Istniejące validation, preview; raport przy konkretnej rewizji |
| Publikacja / historia | Istniejące versions, artifact, diff, restore; zapisane bajty i snapshot |
| Ewidencja / audyt | Istniejące deployments, deployments/latest i audit; korekty z rewizją wpisu |
| Konta / backupy | Konta i przypisania przez polecenia administratora; GET backups/latest/download dla admina |
| CSV | Eksport, podpisany podgląd i atomowy import csv/config; potwierdzenie każdego usunięcia |

Pasek z ostatnią publikacją pobiera dane dla wybranego firewalla, nie dla każdego
wiersza listy. Ostatni udany wpis może być wskazany przez istniejący diff wybranej
wersji; pełne dane ewidencji są pobierane z deployments/latest. Brak danych rozróżniamy od braku wpisu.
Istniejący diff porównuje zapisane wersje. Porównanie podglądu roboczego przed
publikacją wymaga zestawienia preview i pobranego artefaktu/migawki bazy w kliencie
albo jawnego rozszerzenia API; nie traktować endpointu wersji jako diffu draftu.
Takie porównanie ma charakter prezentacyjny i nie zastępuje walidacji serwera.

## Odbiór implementacji (etapy 7 i 9)

Sprawdzić pełny przepływ na dwóch firewallach, każdą rolę, konflikt 409,
spóźnioną odpowiedź poprzedniego urządzenia, odrzucenie lokalnych zmian,
wszystkie potwierdzenia usunięcia, pusty wynik aktywny, brak parsera i awarię API.
Zweryfikować klawiaturę i dialogi, kontrast, powiększenie 200%, 1280/900/390 px,
długie nazwy, polskie znaki, 5000 rezerwacji z paginacją, pełne bytes/hash pobrania.
Implementację sprawdzono w etapach 7–9 i w scenariuszu CSV. Dowody podaje docs/acceptance-mvp.md; statyczny podgląd projektu sam nie dowodzi integracji z API ani zgodności Gaia.
