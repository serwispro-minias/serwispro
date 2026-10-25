# Audyt gotowości RW — 25.10.2026

## Decyzja

**Wstrzymać wdrożenie do czasu odtworzenia zweryfikowanej kopii na osobnej
MariaDB i ręcznego uzgodnienia historycznych rezerwacji.** Kod migracji został
przejrzany i zabezpieczony, ale nie wykonano go na roboczej ani testowej MariaDB.
Testy SQLite i kompilacja SQL MySQL nie są dowodem udanego wdrożenia MySQL.

## Fakty odczytane z roboczej bazy

Odczyt 2026-10-25 około 17:42–17:46 UTC, transakcje `START TRANSACTION READ ONLY`,
zakończone rollback. Bez DDL, księgowań ani korekt. Bez odczytu danych klientów.

- Sterownik: `mysql+pymysql`, serwer: **12.3.2-MariaDB** (nie Oracle MySQL).
- Alembic w bazie: **7a2c9f4e1b80**, jedyna głowica kodu: **8b3d0e5f2c91**.
- Bezpośredni poprzednik nowej migracji: 7a2c9f4e1b80; jego poprzednik:
  6a8c2e4f1b90. Poprzednia migracja dotyczy retencji zdjęć, nie pozycji RW.
- Zmieniane i referencjonowane tabele mają silnik **InnoDB**.
- SQL mode zawiera STRICT_TRANS_TABLES.
- `stock_issue_items`: 1 rekord, quantity_issued INTEGER NOT NULL,
  inventory_item_id INTEGER NOT NULL; wszystkie trzy nowe kolumny nie istnieją.
- `catalog_materials.id` i `service_order_items.id`: INTEGER NOT NULL, PK.
- Istnieją FK nagłówka RW, produktu, zapotrzebowania i rezerwacji oraz indeksy
  dla tych FK. Nowe nazwy FK nie kolidują z odczytanymi FK tej tabeli.
- Ilość RW min/max = 1; brak NULL, wartości poza DECIMAL(12,3), brak osieroconych
  powiązań produktu/nagłówka.
- Istniejący zaksięgowany RW ma ruch ISSUE o tej samej ilości 1,
  ze zmianą stanu 4 → 3.

### Rozbieżności schematu względem modeli

- Robocze `inventory_items.current_stock` jest **DECIMAL(12,3)**, a model
  InventoryItem deklaruje **Integer**. Obecne dane nie mają ułamków.
  Migracja 8b3 nie zmienia tej kolumny. Nie korygowano jej w ramach audytu.
- Nazwy istniejących indeksów RW różnią się od nazw w modelu; indeksy pokrywające
  wymagane kolumny istnieją. Nie dodawać duplikatów wyłącznie dla nazw.
- W roboczym `stock_issue_items.uuid` nie ma deklarowanej przez BaseModel
  unikalności. Nie znaleziono obecnie duplikatów. To wcześniejszy drift,
  niezależny od trzech dodawanych kolumn; wymaga decyzji opiekuna schematu.

## Audyt historycznych rezerwacji

Firma 1, identyfikatory wewnętrzne (bez danych klientów):

| Źródło                                  | Status / aktywność | Liczba | Ilość |
| --------------------------------------- | ------------------ | -----: | ----: |
| ServiceOrderPartReservation             | RESERVED / aktywna |      1 |     1 |
| InventoryReservation                    | brak rekordów      |      0 |     0 |
| ServiceOrderItem, PART z rezerwacją     | aktywna            |      1 |    15 |
| ServiceOrderItem, MATERIAL z rezerwacją | aktywna            |      1 |     1 |

- Produkt **ID 1, SMK-PART-846493**: stan fizyczny 12, efektywne aktywne
  rezerwacje 16; surowa dostępność -4, dostępność pokazywana przez nowy algorytm 0.
- Na tę sumę składają się różne zlecenia: rezerwacja ID 1 dla zlecenia ID 7
  wynosi 1, pozycja ID 3 dla zlecenia ID 6 ma rezerwację 15.
  Nie są lustrzanymi zapisami tego samego zlecenia.
- Materiał **ID 1, SMK-MAT-846493**: stan 18,5; rezerwacja 1;
  dostępność według bieżących pozycji 17,5. Pozycja ID 1 zlecenia ID 3:
  przypisano 2, zużyto 1, nadal zarezerwowano 1.

### Historia ruchów

Odczytano 9 ruchów: RECEIPT 3, ISSUE 2, RESERVATION 1, SERVICE_USAGE 1,
AUTO_ISSUE 2. Nie odczytano RELEASE ani RETURN.

Rezerwacja części ID 1 (zlecenie 7, produkt 1) ma jeden pasujący ruch
RESERVATION ID 3 z 2026-08-04: ilość 1, **stock_before=13, stock_after=12**.
To wiarygodny dowód zapisanego historycznego obniżenia o 1.
Potwierdza go również kod w Git HEAD: rezerwacja przechodziła przez
`add_stock_movement`, a `update_part_stock` odejmował RESERVATION od current_stock.
Kod tworzył też oba istniejące modele rezerwacji; aktualna baza nie zawiera
rekordów InventoryReservation. Sama znajomość kodu nie dowodzi, że każda jego
wersja była wdrożona ani że zapis obu modeli zakończył się sukcesem.

**Nie wynika z tego, że należy dziś dodać 1 do stanu.** Po rezerwacji występowały
inne operacje, fizyczne wydanie mogło zostać wykonane poza pełnym rejestrem,
a historia łączy rezerwację z ruchem przez zlecenie/produkt, nie bezpośredni FK.

### Do ręcznej decyzji

1. Potwierdzić fizyczną obecność i przeznaczenie historycznie odjętej sztuki.
2. Uzgodnić rezerwację 15 przy stanie 12: rzeczywiste potrzeby zlecenia 6,
   ewentualne zużycie, zwolnienie lub braki.
3. Uzgodnić, czy aktywna rezerwacja zlecenia 7 powinna nadal obowiązywać.
4. Sprawdzić materiał z częściowym zużyciem i pozostałą rezerwacją.
5. Ocenić kompletność historii, w tym ISSUE bez reference_type i starsze
   SERVICE_USAGE/AUTO_ISSUE bez RW. Bieżąca poprawna para RW/ISSUE nie dowodzi
   kompletności wszystkich historycznych rozchodów.
6. Zweryfikować semantykę lustrzanych zapisów: nowy algorytm bierze maksimum
   źródeł dla tego samego zlecenia/produktu, ale nie ma historycznego klucza
   pozwalającego zawsze odróżnić kopie od niezależnych rezerwacji.

Żadnych rezerwacji, stanów i dokumentów nie zmieniono.

## Ocena migracji

- W zaobserwowanym schemacie istnieją wymagane tabele i zgodne typy FK.
- Dodawane pola są nullable, bez server default. Stare rekordy otrzymują NULL;
  kod zwykłego RW nie wymaga service_order_item_id/settlement_version.
- Upgrade nie usuwa kolumn ani nie wykonuje UPDATE danych. Konwersja typu
  fizycznie przepisuje wartości, zachowując liczby mieszczące się w zakresie.
- DECIMAL(12,3) ma tylko 9 cyfr całkowitych; nie mieści całego signed INTEGER.
  Dodano sprawdzenie zakresu/NULL **przed pierwszym DDL**.
- Dodano zatrzymanie przy częściowo zmienionym schemacie. Nie jest to migracja
  samonaprawiająca; nie wolno ponawiać jej po częściowym błędzie bez analizy.
- Downgrade odmawia utraty nowych powiązań, settlement_version, ułamków,
  wymaganych produktów i wartości spoza signed INTEGER, przed jakimkolwiek DDL.
- MySQL/MariaDB tworzy indeksy wspierające nowe FK. Po migracji trzeba
  sprawdzić indeks z lewą kolumną material_id i service_order_item_id.
- Nie ma DB CHECK „dokładnie jeden produkt” ani unikalności rozliczenia wersji;
  te reguły kontroluje obecny serwis. Nie dodawano nowych reguł funkcjonalnych.
- DDL MariaDB nie jest atomowe jak transakcja danych. Możliwe blokady,
  przebudowa tabeli, częściowy sukces i niezmieniony numer Alembic po błędzie.

## Konfiguracja i granice

Config wybiera DATABASE_URL lub DATABASE_*; fabryka aplikacji następnie ładuje
instance/config.py, który może nadpisać URI. Dotyczy to także create_app('testing').
Nie drukować konfiguracji ani URI. Testy zapisu uruchamiano wyłącznie z fixture,
które wymusza SQLite **przed** inicjalizacją rozszerzeń, lub bez fabryki aplikacji.
Nie uruchamiać całego pytest na kopii/roboczym MySQL bez sprawdzenia fixtures.

Nie zweryfikowano: backup/restore, ALTER na MariaDB, blokad/równoległych operacji,
czasu migracji, dostępnego miejsca, uprawnień konta do DDL ani interfejsu w przeglądarce.

## Wykonane testy i zmiany tego etapu

- Przed zabezpieczeniem migracji: 6 nowych regresji nie przeszło, 5 dotychczasowych
  testów migracji przeszło. Potwierdzono brak kontroli zakresu i niebezpieczny downgrade.
- Po zabezpieczeniu: **61 passed, 0 failed, 0 skipped** w zestawie
  tests/test_order_parts_migration.py + tests/test_order_parts_settlement.py.
  Wyłącznie izolowana SQLite: migracja, zachowanie starych danych, zakres typu,
  FK, blokada stratnego downgrade, rezerwacja, dostępność, RW/ISSUE i ponowienia.
- Dodatkowo kompilacja DDL dialektu MySQL bez połączenia: bez UPDATE/DELETE/DROP
  w upgrade, oczekiwane typy i FK. To nie jest wykonanie ALTER na MariaDB.
- JavaScript: **23 passed, 0 failed, 0 skipped**.
- 20 ostrzeżeń pytest: istniejące relacje SQLAlchemy, Query.get i ReportLab.
- Pełnego pytest nie uruchamiano w tym etapie: część starszych fixtures zmienia
  URI dopiero po inicjalizacji db; nie używać ich jako testu zapisu roboczej bazy.
  Wynik 241 z poprzedniego etapu jest historyczny, nie nowo wykonany.

Zmiany ograniczono do bezpieczeństwa migracji i przygotowania wdrożenia:
migrations/versions/8b3d0e5f2c91_order_item_rw_settlement.py,
tests/test_order_parts_migration.py, scripts/audit_rw_deployment.py,
docs/RW_DEPLOYMENT_AUDIT.md i docs/RW_DEPLOYMENT_RUNBOOK.md.
Nie zmieniano modeli, funkcji biznesowych ani danych magazynowych.