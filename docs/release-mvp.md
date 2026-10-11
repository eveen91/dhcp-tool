# Przygotowane wydanie MVP 0.1.0

Wydanie dokumentacyjne z 2026-10-11 odpowiada wersji 0.1.0 w metadanych backendu i frontendu. To kandydat MVP z opisanymi ograniczeniami. Nie utworzono tagu Git ani publicznego pakietu. Zainstalowany kod działa w wydaniu `20261011T162819Z`, z CSV całej konfiguracji. Użytkownik potwierdził logowanie admina, eksport/import CSV oraz pobranie backupu i klucza. Wszystkie punkty MVP 0–11 są zamknięte.

## Dostępny zakres

Panel obsługuje CSV całej konfiguracji z podglądem i potwierdzeniami usunięć, lokalne konta, cztery role, przypisania firewalli, konfigurację roboczą, deterministyczny generator, walidację danych i ISC, niezmienne wersje, diff, pobieranie zapisanych artefaktów, odtworzenie draftu, ręczną ewidencję i audyt. Instalacja działa bez Dockera. Backup bazy i konfiguracji jest szyfrowany; administrator może pobrać ostatnią opublikowaną kopię w przeglądarce.

MVP wspiera profile R81.10 i R82.10 w wspólnie potwierdzonym formacie: jedna aktywna pula na aktywną podsieć i rezerwacje poza pulą. [Raport odbioru](acceptance-mvp.md) podaje dowody dla każdego kryterium.

## Ograniczenia i znane problemy

- Zgodność formatu obu profili opiera się na wspólnej referencji i deklaracji użytkownika. Testy upstream ISC nie certyfikują Gaia. Nie wykonano testów na urządzeniach obu wersji.
- Aplikacja nie łączy się z firewallem, nie przesyła plików, nie restartuje DHCP i nie wykrywa jego rzeczywistego stanu. Ewidencja zapisuje ręczne deklaracje.
- Brak importu plików dhcpd.conf i SSO; zatwierdzone rozszerzenie CSV całej konfiguracji opisano w [csv.md](csv.md). Rozszerzone opcje DHCP pozostają poza zakresem. Wiele pul i podsieci tylko z rezerwacjami pozostają poza MVP.
- Obecna instalacja używa HTTP w LAN/VPN zgodnie z decyzją użytkownika. Profil HTTPS jest opisany osobno; nie jest aktywny.
- Pobranie backupu i klucza użytkownik potwierdził 2026-10-11; T10.5 zamknięte. Klucz przechowywać oddzielnie od archiwum. Bez klucza restore jest niemożliwy.
- Backupy i historia nie są automatycznie usuwane. Kontroluj miejsce na dysku; docelowa skala oraz dopuszczalny czas i punkt odtworzenia nie są ustalone.
- Audyt z 2026-10-10 wykazał nierozwiązane zgłoszenie `braces` w zależnościach developerskich. Stan i zakres: [raport zależności](dependency-audit.md). W tym etapie nie powtarzano audytu sieciowego.
- CI wymaga skonfigurowanego osobnego runnera; runner GitHub nie został podłączony.
- Restore zweryfikowano do pustej bazy i nowego katalogu konfiguracji. Pełna odbudowa systemu operacyjnego pozostaje osobną próbą operacyjną.

## Zainstaluj lub zaktualizuj

Wspierane rodziny to Debian 13, Python 3.13, Node.js 24, PostgreSQL 17, Django 5.2 i Next.js 16.4. Odtwarzaj zależności z plików blokad. Przed aktualizacją zachowaj eksport i obecne wydanie, przygotuj build instalacyjny z API 18000 i użyj aktualnych sekretów z `/etc/dhcp-tool/backend.env`. Procedura aktualizacji i powrotu: [instalacja](installation.md). Procedura odtworzenia: [backup](backup-restore.md).

Nie kopiuj `.next-quality` do działającej instalacji: używa testowego API. Nie publikuj prywatnych plików środowiska, kluczy ani backupów. Autentyczne próbki DHCP pozostają niezmienione.
