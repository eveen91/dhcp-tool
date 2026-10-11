# Przegląd zależności — etap 9

Data: 2026-10-10. Audyt zainstalowanych zależności i plików blokad: `npm audit --json`, `npm audit --omit=dev --json`, `pip-audit` na backendowym virtualenv.

| Zakres | Wynik |
| --- | --- |
| Python | 0 znanych podatności |
| npm, zależności uruchomieniowe | 0 znanych podatności |
| npm, całe drzewo | 5 zgłoszeń high, jedna przyczyna w zależnościach developerskich |

Zaktualizowano Django REST Framework do 3.17.2, Next.js i eslint-config-next do 16.4.0, Vitest do 5.0.3, Vite do 8.3.4 oraz ESLint do 9.39.4. Pliki blokad zapisano. Oficjalne środowisko projektu nadal używa Node.js 24. Migracja Next zachowuje webpack; Vitest używa konfiguracji ESM i OXC. Pełne testy, lint, typy i produkcyjny build przeszły po aktualizacji.

Pozostałe zgłoszenie to [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm): zagnieżdżone wzorce w braces mogą wyczerpać stos. Na dzień przeglądu nie ma poprawionej wersji. npm raportuje pięć elementów łańcucha: braces → micromatch → fast-glob → @next/eslint-plugin-next → eslint-config-next. Wszystkie należą do narzędzi developerskich; audyt runtime jest czysty. Konfiguracja lintowania używa stałych wzorców z repozytorium, bez danych DHCP użytkowników. Nie uruchamiać lintowania niezaufanych konfiguracji z dostępem do sekretów CI. Po wydaniu poprawki zaktualizować łańcuch i powtórzyć audyt. Ryzyko pozostaje udokumentowane; podatność nie została usunięta. Sugerowany przez npm downgrade eslint-config-next do 14 nie jest poprawką zgodną z Next 16.

Reguła `react-hooks/set-state-in-effect` ma jawny wyjątek w trzech komponentach ładowania danych: workspace, audit-history i deployment-ledger. Ich efekty usuwają poprzednie prywatne dane przy zmianie zakresu, anulują żądania i ignorują spóźnione odpowiedzi. Pozostałe reguły Next/React pozostają włączone.

Źródła migracji i poprawek: [Next 16](https://nextjs.org/docs/app/guides/upgrading/version-16), [Vitest](https://vitest.dev/guide/migration/), [DRF: GHSA-2m8g-3cmr-wg3w](https://github.com/advisories/GHSA-2m8g-3cmr-wg3w), [DRF: GHSA-g47c-3xmw-q6m2](https://github.com/advisories/GHSA-g47c-3xmw-q6m2).
