# Bezpieczne wdrożenie rozliczeń RW

**Nie wykonywano migracji ani korekt magazynu podczas przygotowania instrukcji.**
Obecna rekomendacja: STOP przed wdrożeniem; najpierw administrator i magazynier
muszą zamknąć punkty z raportu RW_DEPLOYMENT_AUDIT.md oraz wykonać próbę na kopii.
Nie należy wykonywać poleceń na podstawie samego koloru „zielone testy”.

## 1. Przygotowanie z administratorem

- Ustal osobę odpowiedzialną, okno niedostępności i plan powrotu.
- Zapisz wersję kodu/commit i zachowaj poprzednie wydanie aplikacji.
- Uzgodnij historyczne rezerwacje z magazynierem; ta instrukcja **nie poleca**
  dodawania sztuk, usuwania rezerwacji ani testowych księgowań na roboczej bazie.
- Administrator potwierdza faktyczny cel połączenia (także instance/config.py),
  silnik MariaDB/MySQL, uprawnienia DDL, wolne miejsce i brak kolizji nazw FK.
  Nie publikuj plików konfiguracji, haseł ani pełnego DATABASE_URL.
- Przygotuj osobny serwer/bazę staging, bez dostępu aplikacji roboczej.
  Sama zmiana TEST_DATABASE_URL nie wystarcza, jeśli instance/config.py nadpisuje URI.

W PowerShell w katalogu C:\serwispro (polecenia bez haseł):

```powershell
& C:/serwispro/venv/Scripts/python.exe -m flask --app run db current
& C:/serwispro/venv/Scripts/python.exe -m flask --app run db heads
& C:/serwispro/venv/Scripts/python.exe -m scripts.audit_rw_deployment
```

Oczekiwane przed wdrożeniem: current=7a2c9f4e1b80, jedyna head=8b3d0e5f2c91.
Raport zawiera wewnętrzne kody produktów — przechowuj go wewnętrznie.
Jeśli wartości, schemat lub zakres rezerwacji się różnią, zatrzymaj procedurę.

## 2. Kopia zapasowa i jej sprawdzenie

Administrator dobiera klienta zgodnego z serwerem. Dla odczytanego MariaDB
preferuj mariadb-dump/mariadb. Przykład ma zmienne do uzupełnienia lokalnie;
nie zawiera danych logowania. `-p` pyta o hasło w terminalu — wpisuje je człowiek,
nie przekazuje go asystentowi ani w argumencie polecenia.

Zatrzymaj aplikację, procesy robocze, harmonogramy i wszelkich autorów zapisu.
Nie uruchamiaj równolegle migracji ani innych zmian schematu.

```powershell
$DbHost = 'UZUPELNIJ_HOST'
$DbPort = '3306'
$DbUser = 'UZUPELNIJ_UZYTKOWNIKA'
$DbName = 'UZUPELNIJ_BAZE'
$Dump = 'D:/bezpieczne-kopie/serwispro-przed-rw.sql'
& mariadb-dump --host=$DbHost --port=$DbPort --user=$DbUser -p --single-transaction --quick --routines --triggers --events --hex-blob --default-character-set=utf8mb4 --result-file=$Dump $DbName
if ($LASTEXITCODE -ne 0) { throw 'Kopia nie powiodła się — STOP' }
Get-Item $Dump | Select-Object Length, LastWriteTime
Get-FileHash $Dump -Algorithm SHA256
```

Nie używaj przekierowania `>` PowerShell 5.1 dla dumpa — może zmienić kodowanie.
Administrator sprawdza log błędów, końcówkę dumpa i obecność wszystkich tabel,
widoków, procedur, wyzwalaczy i zdarzeń. Kopia ma trafić poza katalog aplikacji,
z ograniczonym dostępem i ochroną danych osobowych. Hasz i rozmiar nie dowodzą,
że kopię można odtworzyć.

**Obowiązkowa próba odtworzenia:** administrator przygotowuje pustą osobną bazę
na staging i odtwarza tam dump. Nie wolno wskazać bazy roboczej, kasować jej ani
zastępować danymi testowymi. Przed importem sprawdź, czy dump nie zawiera `USE`
lub `CREATE DATABASE` kierujących do innej bazy. Dla przykładu `$StageDb` i
`$StageHost` muszą jawnie wskazywać środowisko staging:

```powershell
# Wykonuje administrator dopiero po sprawdzeniu dumpa i celu połączenia.
& mariadb --host=$StageHost --port=$DbPort --user=$StageUser -p --database=$StageDb --execute="source D:/bezpieczne-kopie/serwispro-przed-rw.sql"
if ($LASTEXITCODE -ne 0) { throw 'Odtworzenie nie powiodło się — STOP' }
```

Na staging porównaj liczbę wierszy i dane RW z kopią: id, uuid, produkt,
ilość, nagłówek, rezerwacja, zapotrzebowanie, daty, aktywność i wersja.
Nie wypisuj danych klientów. Zabezpiecz przedwdrożeniowe zestawienie wszystkich
wierszy stock_issue_items, aby porównać je po zmianie typu.

## 3. Przegląd i próba migracji na staging

W osobnym wdrożeniu kodu skonfigurowanym **wyłącznie do staging**:

```powershell
& C:/serwispro/venv/Scripts/python.exe -m flask --app run db upgrade --sql '7a2c9f4e1b80:8b3d0e5f2c91'
```

To podgląd SQL, nie dowód zgodności i nie kontrola danych. Nie wykonuj
wydrukowanego SQL ręcznie: ominąłby ochronę preflight migracji online.
Oczekiwane: zmiana nullable inventory_item_id, quantity_issued na DECIMAL(12,3),
trzy nullable kolumny INTEGER i dwa FK. Bez UPDATE/DELETE istniejących danych.

Administrator sprawdza: InnoDB, signed INTEGER obu referencji, brak kolizji nazw,
ilości w zakresie ±999999999.999, brak nowych kolumn po częściowej migracji,
miejsce na przebudowę i plan blokad. Zatrzymaj procesy także na staging.
Po weryfikacji kopii i celu wykonaj **na staging**, nie roboczej bazie:

```powershell
& C:/serwispro/venv/Scripts/python.exe -m flask --app run db upgrade 8b3d0e5f2c91
if ($LASTEXITCODE -ne 0) { throw 'Migracja staging nie powiodła się — STOP' }
```

## 4. Kontrola po migracji — najpierw staging

```powershell
& C:/serwispro/venv/Scripts/python.exe -m flask --app run db current
& C:/serwispro/venv/Scripts/python.exe -m scripts.audit_rw_deployment
```

W kliencie bazy (zapytania odczytowe):

```sql
SELECT version_num FROM alembic_version;
SHOW CREATE TABLE stock_issue_items;
SHOW INDEX FROM stock_issue_items;
SELECT COUNT(*), MIN(quantity_issued), MAX(quantity_issued) FROM stock_issue_items;
SELECT COUNT(*) AS legacy_links_should_be_null
FROM stock_issue_items
WHERE material_id IS NOT NULL OR service_order_item_id IS NOT NULL
   OR settlement_version IS NOT NULL;
```

Przed wykonaniem nowych scenariuszy ostatni wynik ma wynosić 0 dla dawnych
rekordów, a liczba wierszy i stare pola muszą zgadzać się z zestawieniem.
quantity_issued: DECIMAL(12,3) NOT NULL; inventory_item_id: nullable;
material_id/service_order_item_id/settlement_version: INTEGER nullable bez
domyślnej wartości biznesowej. Dwa nowe FK i indeksy z ich kolumną na początku
muszą istnieć. Stare FK/indeksy mają zostać zachowane.

## 5. Testy powdrożeniowe — bez rzeczywistych księgowań roboczych

Automatyczne testy poniżej tworzą wyłącznie izolowaną SQLite. Zweryfikuj, że
fixture modułu settlement nadal wymusza sqlite:///:memory: **przed** db.init_app.

```powershell
& C:/serwispro/venv/Scripts/python.exe -m pytest tests/test_order_parts_migration.py tests/test_order_parts_settlement.py -q
node --test tests/js/*.test.js
```

Na odtworzonej staging MariaDB wykonaj osobno i zapisz wyniki:

| Scenariusz                       | Kryterium akceptacji                                                           |
| -------------------------------- | ------------------------------------------------------------------------------ |
| Odczyt dawnych RW                | Brak błędu nowych kolumn, stary rekord i ilość zachowane                       |
| Nowy roboczy RW części/materiału | Poprawny odczyt/zapis, materiał np. 1,125; brak zmiany stanu                   |
| Rezerwacja 5 przy stanie 10      | Stan 10, rezerwacja 5, dostępne 5                                              |
| Inne zlecenie chce 6             | Nie zajmuje nadmiaru, brak trafia do istniejącego zapotrzebowania              |
| Rozliczenie 3 z rezerwacji 5     | Po księgowaniu stan 7, zużyto 3, zwolniono 2, rezerwacja 0                     |
| Ponowny POST/odświeżenie         | Bez kolejnego ISSUE i zmiany stanu                                             |
| Nieaktualny formularz            | Odrzucenie zmiany lub bezpieczny istniejący RW                                 |
| Bezpośrednie zużycie             | Stan zmienia tylko jawne księgowanie RW                                        |
| Dokument a historia              | Suma ISSUE dla numeru RW odpowiada pozycjom; stock_after=stock_before-quantity |
| PZ brakującej części             | Dostawa nie jest zużyciem ani automatyczną rezerwacją                          |
| Firma/oddział/rola/CSRF          | Niedozwolona operacja odrzucona, bez skutku magazynowego                       |

Testowe dokumenty tworzy się **tylko na staging**, nie używa prawdziwych
dokumentów roboczych do prób. Nie otwieraj produkcyjnego przycisku księgowania
w celu „sprawdzenia, czy działa”.

## 6. Właściwe wdrożenie — dopiero po podpisanej akceptacji staging

1. Potwierdź uzgodnienie historycznych rezerwacji i decyzję o drift schematu.
2. Zatrzymaj zapisy aplikacji/harmonogramów. Wykonaj świeżą kopię i weryfikację.
3. Powtórz current/heads, raport odczytowy i kontrolę danych/schematu.
4. Administrator jawnie wskazuje roboczą bazę i wykonuje wyłącznie przypięty
   `flask --app run db upgrade 8b3d0e5f2c91` z powyższego środowiska Python.
5. Sprawdź kod wyjścia, current, strukturę i zachowanie danych jak w punkcie 4.
6. Dopiero wtedy uruchom zgodną wersję aplikacji. Na roboczej bazie sprawdź
   odczyt dawnych dokumentów i widoków; bez testowych księgowań.

## 7. Jeśli wystąpi błąd

**STOP. Nie uruchamiaj ponownie upgrade, stamp ani downgrade w ciemno.**
MariaDB może zatwierdzić część DDL, mimo że wersja Alembic się nie zmieniła.
Zachowaj log, sprawdź schemat odczytowo i przekaż administratorowi.
Nie edytuj ręcznie alembic_version. Nie wyłączaj foreign_key_checks, aby „przepchnąć” zmianę.
Downgrade jest celowo blokowany, gdy usunąłby powiązania lub ilości ułamkowe.
Powrót przez backup wymaga decyzji administratora i analizy późniejszych zapisów;
nie jest poleceniem automatycznego odtworzenia ani kasowania roboczej bazy.