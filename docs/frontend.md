# Panel WWW — aktualna implementacja

Strona główna Next.js jest panelem konfiguracji opisanym w DESIGN.md.
Używa lokalnych fontów systemowych i nie wymaga CDN ani pulpitu na serwerze.

## Dostępne działania

1. Zaloguj się kontem lokalnym. Widoczna jest rola; backend kontroluje każdy
   odczyt i zapis. Administrator dodaje urządzenie z profilem R81.10/R82.10.
2. Otwórz firewall. Edytuj opcje globalne, dodaj podsieć, jedną pulę oraz
   rezerwacje poza pulą. Możesz zmieniać opcje podsieci i aktywność elementów.
   Opcje puste są usuwane lub dziedziczone; czasy są w sekundach, DNS rozdziela
   przecinek lub odstęp. „Adresy interfejsów IPv4” przyjmują wiele adresów
   firewalli w klastrze (przecinek lub spacja); każdy jest wykluczony z puli
   i rezerwacji. Rezerwacje można przenieść do innej podsieci urządzenia.
3. Wybierz „Walidacja i podgląd”. Sprawdź dane lub pokaż cały plik. Zakres
   kontroli danych/ISC/Gaia jest opisany osobno. Pusta aktywna konfiguracja
   i aktywna podsieć bez aktywnej puli blokują publikację.
4. Przygotuj publikację i podaj opis zmiany. Otwórz zapisaną wersję w historii,
   aby pobrać dhcpd.conf. Szczegóły wskazują firewall, historyczny profil,
   autora, czas UTC, generator, rewizję, liczbę bajtów i pełny SHA-256.
5. Porównaj dwie wersje albo wybierz bazę ostatniego ręcznie potwierdzonego
   wdrożenia. Bez takiego wpisu nie podstawiamy ostatniej publikacji.
6. Odtwórz starą wersję do konfiguracji roboczej po potwierdzeniu zastąpienia
   danych. Historia, obecny profil i ewidencja pozostają zachowane.

Każde usunięcie podsieci, puli lub rezerwacji wymaga dialogu, z fokusem na
Anuluj i obsługą Escape. Podsieć pokazuje wszystkie usuwane elementy, także
nieaktywne. Archiwizacja zachowuje historię i blokuje edycję; administrator
może przywrócić aktywność. Reader/operator mają tylko odczyt konfiguracji.

Ewidencja umożliwia ręczną rejestrację i korekty z uzasadnieniem. Historia operacji
pokazuje audyt wybranego firewalla z wartościami przed/po. Administracja opisuje
dostępne lokalne procedury zarządzania kontami. Publikacja, pobranie
oraz odtworzenie draftu nie oznaczają zmiany urządzenia.

## Sesje, błędy i współbieżność

`workspace-client.ts` używa typów generowanych z OpenAPI. Klient przechowuje
CSRF wyłącznie w pamięci instancji panelu, aktualizuje go po logowaniu i wysyła
X-Config-Revision dla zapisów. Zapytania mają no-store i credentials same-origin.
Nie ma lokalnego utrwalania konfiguracji ani hasła, wspólnego cache czy
samoczynnego ponawiania zapisów i publikacji.

HTTP 409 zachowuje lokalne pola i pokazuje aktualną rewizję. „Odśwież dane”
wymaga świadomego odrzucenia niezapisanych zmian. Zmiana urządzenia lub widoku
oraz zamknięcie karty również ostrzegają o niezapisanych polach. Zmiana firewalla
czyści stan edycji, podglądu i historii, anuluje żądania i ignoruje późne odpowiedzi.
Ponowne logowanie tym samym kontem odbywa się w dialogu bez utraty lokalnych pól;
inne konto usuwa kontekst poprzedniego użytkownika. Zapisy nie są ponawiane.

Błędy pól są połączone z kontrolkami przez aria-describedby/aria-invalid;
podsumowanie otrzymuje fokus. Dialogi ograniczają Tab/Shift+Tab i przywracają
fokus po zamknięciu. Tabele przewijają się we własnym obszarze. Listy rezerwacji,
wersji i urządzeń mają paginację po 50 rekordów; filtrowanie po stronie API.
Pełna migawka draftu nadal pochodzi z istniejącego endpointu backendu.

Pobieranie używa zapisanych bajtów, sprawdza długość i nagłówek SHA-256.
Gdy przeglądarka udostępnia Web Crypto (HTTPS/localhost), dodatkowo oblicza hash
przed pobraniem. W LAN przez zwykły HTTP należy porównać SHA-256 pobranego pliku
z wyświetloną wartością; brak Web Crypto nie jest przedstawiany jako weryfikacja
kryptograficzna treści. Hash podglądu i publikacji mogą być różne ze względu na
komentarz z UUID publikacji.

## Uruchamianie i istniejący podgląd LAN

Polecenia instalacji i uruchomienia pozostają w development.md. Zmiana kodu
jest widoczna w `npm run dev`; działające `npm start` wymaga nowego `npm run build`
i restartu procesu. Build kontrolny `.next-quality` korzysta z testowego API 8101 i nie zastępuje instalacyjnego `.next-install` z API 18000. Usługi instalacyjne są opisane w [installation.md](installation.md).

Pełny panel działa przez Nginx LAN na `http://192.168.1.32:8080`, z całym API i prawdziwymi sesjami. Backend działa przez Gunicorn, frontend z builda `.next-install`. Dawny `nginx-status.conf` jest historycznym podglądem i nie należy go ponownie instalować. Instalacja oraz aktualizacje: [installation.md](installation.md).

## Weryfikacja

Vitest sprawdza role i archiwizację, błędy pól, konflikt, niezapisane zmiany,
ponowne logowanie, nieaktualny podgląd, późne odpowiedzi, fokus, kodowanie opcji
oraz paginację przy deklarowanym count=5000. To nie pomiar wydajności 5000 rekordów.

Playwright używa prawdziwych sesji/CSRF, PostgreSQL i proxy Next.js. Scenariusz
obejmuje dwa firewalle o tej samej adresacji, błąd rezerwacji w puli, równoczesną
zmianę rewizji, dwie publikacje, dokładne bajty/hash pobrania, diff, odtworzenie,
potwierdzenie usunięcia, klawiaturę oraz długie nazwy/opisy na 390 px.
Fixture wymaga config.settings.test i bazy z prefiksem test_. Sprzątanie używa
TRUNCATE historii tylko w tej jednorazowej bazie; zachowuje wyzwalacze niezmienności.
Testy działają szeregowo. Nie przechowywać ręcznych danych w bazie testowej.

Test przeglądarkowy wykrył i usunął błąd backendu: DELETE zwraca teraz pustą
odpowiedź 204 także przed serializacją HTTP, z zachowaniem rewizji i audytu.


## Ewidencja i historia operacji

Operator i administrator mogą rejestrować oraz korygować wpisy aktywnego firewalla.
Pozostałe role mają odczyt w swoim zakresie. Formularz podaje czas zdarzenia ze
strefą, wynik, wersję, notatkę, numer zgłoszenia i opcjonalny ręczny hash. Operator
oraz czas wpisu pochodzą z serwera. Korekta wymaga uzasadnienia; konflikt rewizji
zachowuje lokalne pola i nie ponawia zapisu. Anulowanie niezapisanego formularza
oraz zmiana ekranu wymagają świadomego odrzucenia pól.

Wersje w formularzu można wyszukiwać po opisie i stronicować. Lista wdrożeń
pokazuje oba czasy i porównanie ręcznego hasha z artefaktem. Nie odczytuje urządzeń.
Historia operacji ma filtry obiektu i operacji; szczegóły pokazują autora i JSON
przed/po. Szczegółom przekazywany jest fokus, a JSON jest renderowany jako tekst.
Pełne reguły: [deployments-api.md](deployments-api.md).

Administrator może pobrać zaszyfrowany backup z Administracji. Kompletny proces pracy opisano w [user-guide.md](user-guide.md).

## CSV całej konfiguracji

Zakładka CSV korzysta z `csv-transfer.tsx` i `/csv/config/`: metadane, ustawienia globalne, podsieci, pule oraz rezerwacje. Czytelnik/operator może eksportować; editor/admin może importować, a metadane zmienia tylko admin. Wczytanie pliku lub zmiana tekstu usuwa wcześniejszy podgląd i potwierdzenia. Podgląd ma paginację po 50 zmian oraz osobne checkboxy każdego usunięcia, również kaskadowego. Zapis wymaga wszystkich potwierdzeń i aktualnej rewizji; nie publikuje wersji. Tabela przewija się poziomo na małym ekranie, aby adresy i opcje pozostały czytelne. Limit importu: 32 KiB/500 rekordów, ważność podglądu: 10 minut. Szczegóły: [csv.md](csv.md).

Nowy scenariusz Playwright pobiera rzeczywisty CSV, zmienia opcje i IP, wczytuje plik, sprawdza podgląd oraz zapis; axe sprawdza dostępność również na 390 px. Użytkownik potwierdził eksport/import na działającej instalacji. Raport: [verification-csv.md](verification-csv.md).
