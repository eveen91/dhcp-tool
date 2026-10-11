# Dokumentacja DHCP Tool

Dokumentacja opisuje działającą aplikację dla Check Point Gaia oraz zatwierdzony zakres jednej puli na podsieć i rezerwacji poza pulą. CSV całej konfiguracji jest wdrożonym rozszerzeniem. [Status projektu](project-status.md) oddziela wyniki testów, potwierdzenia użytkownika i brak weryfikacji na urządzeniu.

## Korzystanie z panelu

| Zadanie | Dokument |
| --- | --- |
| Logowanie, konfiguracja, publikacja, historia i ręczna ewidencja | [Instrukcja użytkownika](user-guide.md) |
| CSV: cały firewall, podgląd, usunięcia, limity i format | [CSV](csv.md) |
| Dostępne role, tworzenie kont, przypisania i reset hasła | [Konta i bezpieczeństwo](security.md) |
| Pobranie backupu i odtworzenie do pustej bazy | [Backup i restore](backup-restore.md) |

## Instalacja i utrzymanie

| Zadanie | Dokument |
| --- | --- |
| Wymagane programy, usługi, instalacja, aktualizacja i powrót | [Instalacja](installation.md) |
| Kontrola usług, timerów, logów, backupu i miejsca na dysku | [Obsługa operacyjna](operations.md) |
| Lokalny backend/frontend, oddzielna baza testowa, build i CI | [Development](development.md) |
| Wydanie 0.1.0, ograniczenia i decyzje operacyjne | [Wydanie MVP](release-mvp.md) |

## Architektura i kontrakty

| Obszar | Dokument |
| --- | --- |
| Procesy, modele, transakcje i przepływ konfiguracji | [Architektura](architecture.md) |
| Wszystkie endpointy, sesje, rewizje i błędy | [API v1](api-contract.md) |
| Firewalle, podsieci, pule, rezerwacje i draft | [API konfiguracji roboczej](draft-api.md) |
| Dane, parser ISC i podgląd pliku | [API walidacji](validation-api.md) |
| Publikacja, artefakty, porównania i odtwarzanie | [API historii](history-api.md) |
| Ręczne wdrożenia i audyt | [API ewidencji](deployments-api.md) |
| Dyrektywy, referencje, profile i granice zgodności Gaia | [Generator](generator.md) |
| Stan, błędy, fokus i komponenty panelu | [Frontend](frontend.md) |
| Język interfejsu i zasady wizualne | [DESIGN.md](../DESIGN.md) |

OpenAPI jest w `backend/config/openapi.json` i pod `/api/v1/schema/`. Typy frontendu generuje `npm run api:generate`. Kontrakt dotyczy wewnętrznego API panelu; integracja z IPAM lub publicznym API pozostaje backlogiem.

## Plan i wyniki weryfikacji

- [README](../README.md), [PRODUCT.md](../PRODUCT.md), [plan.MD](../plan.MD), [TODO.md](../TODO.md) — cel, uzgodniony zakres i ukończone zadania.
- [Funkcje do dodania](../features_to_add.md) — rozszerzenia wymagające osobnej decyzji i dowodów zgodności Gaia.
- [Odbiór MVP](acceptance-mvp.md) — wszystkie 12 kryteriów z planu.
- [CSV](verification-csv.md) — 320 pytest, 32 Vitest i 7 scenariuszy przeglądarkowych w opisanych przebiegach; potwierdzenie działającej instalacji.
- [Etap 10](verification-stage10.md) i [etap 9](verification-stage9.md) — historia testów i wdrożenia; wcześniejsze liczby pozostają dowodami tych etapów.
- [Audyt zależności](dependency-audit.md) — datowany wynik, nie bieżące zapewnienie o braku podatności.
- [Raport wydajności](performance-report.json) i [raport odtworzenia](restore-report.json) — wyniki pomiarów i porównania danych.
- [Graf projektu](../graphify-out/GRAPH_REPORT.md) oraz [diagnostyka grafu](../graphify-out/DIAGNOSTICS.md) — indeks powiązań, pomocniczy wobec kodu.

## Aktualizacja dokumentacji

Po zmianie funkcji uzupełnij właściwy kontrakt i instrukcję użytkownika, OpenAPI z typami, status oraz TODO. Raportom weryfikacji dopisuj datowane wyniki; nie zastępuj wcześniejszych pomiarów nowymi liczbami bez testów. Odśwież graf po zakończeniu zmian w kodzie i dokumentach.

Nie umieszczaj w dokumentacji haseł, środowisk prywatnych, backupów ani zawartości klucza. Autentyczne `dhcpd.conf` i `dhcpd copy.conf` pozostają niezmienione. Testy danych, ISC i działanie na Gaia to trzy odrębne poziomy dowodów.
