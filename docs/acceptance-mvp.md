# Wyniki odbioru MVP

Raport z 2026-10-11 mapuje wszystkie 12 kryteriów z sekcji 13 `plan.MD` na dowody. Obejmuje implementację i testy na serwerze aplikacji. Nie potwierdza działania generatora na urządzeniach Gaia.

## Kryteria i dowody

| Nr | Kryterium | Wynik i dowód |
| --- | --- | --- |
| 1 | Dwa firewalle, różne nazwy i profile, izolacja danych | Zaliczone. `frontend/e2e/workspace.spec.ts`: R81.10 i R82.10 z tą samą adresacją; testy access i versions sprawdzają zakres identyfikatorów. |
| 2 | Podsieć, pula, rezerwacja i kompletny plik | Zaliczone. Scenariusz workspace tworzy elementy, publikuje i pobiera artefakt; golden files obejmują zakres MVP. |
| 3 | Błąd blokuje publikację | Zaliczone. `test_versions.py`: błędne dane, błąd parsera, stary draft i rollback transakcji; przeglądarka sprawdza rezerwację w puli. |
| 4 | Testy danych i referencji obu profili | Zaliczone w uzgodnionym zakresie. `test_validation_matrix.py`, `test_generator.py`, fixtures `mvp-R81.10.conf` i `mvp-R82.10.conf`, parser ISC 4.4.3-P1. Wspólny format potwierdził użytkownik; brak testów na appliance. |
| 5 | Pobrane bajty i SHA-256 odpowiadają artefaktowi | Zaliczone. `test_download_never_regenerates_after_metadata_and_generator_changes` i workspace E2E porównują treść oraz hash. |
| 6 | Historia autora, czasu, zmian i deklaracji wdrożeń | Zaliczone. Testy deployments, wersji i workspace sprawdzają przed/po, korekty i poziom deklaracji. |
| 7 | Eksport nie oznacza wdrożenia | Zaliczone. Publikacja i pobranie nie tworzą wpisu ewidencji; testy i UI rozróżniają wynik deklaracji i ręczny hash. |
| 8 | Stara wersja i udokumentowany rollback | Zaliczone. Stare artefakty pozostają niezmienne; wersje można odtworzyć do draftu, a ewidencja dopuszcza wskazanie starszej wersji. Procedura: `user-guide.md`. |
| 9 | Uprawnienia | Zaliczone. `test_access.py`, `test_endpoint_matrix.py`, testy CSRF, odebrania dostępu i dezaktywacji; tylko admin pobiera backup. |
| 10 | Start po reboot bez Dockera | Zaliczone na obecnym serwerze. Rzeczywisty reboot i active/enabled API, WWW oraz Nginx zapisano w `verification-stage10.md`. |
| 11 | Restore danych, kont, wersji, artefaktów i historii | Zaliczone dla pustej bazy i nowego katalogu konfiguracji. Test szyfrowanego roundtrip i rzeczywisty eksport: 21 tabel, 104 rekordy, identyczne fingerprinty (`restore-report.json`). Nie testowano odtworzenia całego systemu operacyjnego. |
| 12 | Instrukcje instalacji, obsługi, dyrektyw i odtworzenia | Zaliczone. `installation.md`, `user-guide.md`, `generator.md`, `security.md`, `backup-restore.md`, README. Bez procedur wgrywania na Gaia. |

## Zakres ostatniej kontroli

Ostatnia weryfikacja kodu obejmuje 320 pytest, 32 Vitest i 7 scenariuszy Playwright: sześć istniejących w pełnym przebiegu oraz nowy CSV po poprawieniu selektora. Ruff, formatowanie, Django check, ESLint, OpenAPI, TypeScript i build przeszły. Scenariusze używają Nginx, Gunicorn i produkcyjnego Next.js; backup sprawdzono na zaszyfrowanej testowej treści. Dowody: [CSV](verification-csv.md), [etap 10](verification-stage10.md), [etap 9](verification-stage9.md).

Bieżąca instalacja `20261011T162819Z` ma aktywne API, WWW i Nginx; health w LAN zwraca HTTP 200. Użytkownik potwierdził logowanie admina, eksport/import CSV, pobranie rzeczywistego backupu i klucza poza serwer. Nie powtarzano testów aplikacji dla zmian dokumentacyjnych. Aktualny [status](project-status.md) rozdziela te rodzaje dowodów.

## Otwarte ograniczenia odbioru operacyjnego

Użytkownik potwierdził udane pobranie rzeczywistego backupu oraz klucza 2026-10-11. Potwierdzenie dotyczące klucza obejmuje wcześniejsze pytanie o jego oddzielną kopię poza serwerem; T10.5 zamknięte. Kryterium odtworzenia pustej bazy zostało sprawdzone niezależnie od tego zadania.

Nie zatwierdzono docelowej skali, RPO/RTO ani retencji historii. Brak automatycznego usuwania backupów jest decyzją użytkownika. Znane ograniczenia i problem zależności developerskich opisuje [wydanie MVP](release-mvp.md).
