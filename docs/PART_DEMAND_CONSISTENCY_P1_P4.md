# Spójność zapotrzebowań P1–P4 — 2026-10-26

## Reguły

- PartDemand z pozycją wymaga zgodności firmy, oddziału, aktywnego zlecenia,
  aktywnego produktu i aktywnej pozycji typu PART. Oddział pozycji/zapotrzebowania
  musi odpowiadać zleceniu; produkt może być wspólny (branch_id NULL).
- Nie zmienia się tożsamości istniejącego zapotrzebowania zwykłą edycją.
  Błędne historyczne powiązania i ilości wymagają osobnego uzgodnienia.
- Pole pozycji reserved_quantity nie jest dowodem rezerwacji. Potrzebny jest
  zgodny aktywny ServiceOrderPartReservation. Pole PartDemand jest wyliczanym
  snapshotem, nie poleceniem rezerwowania; ręczna niezgodna wartość jest odrzucana.
- Bez migracji obsługiwany jest konserwatywny przypadek jednoznaczny:
  jedno aktywne nieanulowane zapotrzebowanie dla zlecenia/produktu, najwyżej jedna
  zgodna aktywna pozycja i najwyżej jeden aktywny zapis kanonicznej rezerwacji.
  Nie stosuje się MAX ani uzgadniania lustrzanych tabel. Starszy InventoryReservation,
  wiele rezerwacji/zapotrzebowań, brak jednoznacznego powiązania pozycji,
  rozbieżne ilości lub historia fizycznego odpisu RESERVATION blokują operację.
- Rezerwacja nie musi być <= wymaganej ilości: rzeczywisty zgodny nadmiar jest
  dozwolony. Nie powstaje z ręcznego wpisania wartości.
- Zużycie musi mieć potwierdzenie w aktywnym zaksięgowanym RW z prawidłowym
  zakresem i powiązaniem pozycji/zapotrzebowania. Samo pole used_quantity nie
  zastępuje dokumentu. Dla zapotrzebowania bez pozycji RW musi wskazywać PartDemand.
- Wspólny brak: max(0, requested_quantity - actual_reserved - posted_rw_used).
  Zwolnione niewykorzystane ilości NIE zmniejszają wymaganej potrzeby.
  Rezerwacja 5 / zużycie 3 / zwolnienie 2 -> reserved 0, used 3, missing 2.
- DELIVERED zachowuje wartość techniczną; etykieta to **Zaspokojone**.
  Dozwolone tylko przy braku 0 potwierdzonym rezerwacją/zużyciem.
  Zwolnienie ponownie otwierające brak zmienia dawny DELIVERED na TO_ORDER.
  Nie zmieniano semantyki pozostałych statusów. PZ nie ustawia DELIVERED.
- fulfill_demand: wersjonowana operacja, walidacja przed mutacją, kontrola
  roboczego RW, wywołanie istniejącej rezerwacji z commit=False; jeden końcowy
  commit i rollback całej operacji przy dowolnym błędzie. To jedyny zakres P5.

## Ograniczenia bez zmiany schematu

Brakuje FK rezerwacja -> pozycja/zapotrzebowanie. Nie wdrożono alokacji dla wielu
źródeł ani automatycznej konsolidacji. Kolejne przypisanie przy istniejącej
rezerwacji jest blokowane, bo utworzyłoby kolejny niejednoznaczny rekord.
Do obsługi tych przypadków potrzebna będzie osobna decyzja: jawna relacja
alokacji i ewentualne kontrolowane uzgodnienie danych. W tym zadaniu nie
przygotowywano ani nie wykonywano migracji.

## Zmodyfikowane pliki

- app/part_demands/consistency.py — współdzielona walidacja, źródła dowodów,
  obliczenie braku, status i synchronizacja.
- app/part_demands/service.py — CRUD/automatyczny brak/realizacja korzystają
  ze wspólnej polityki; realizacja ma jedną transakcję.
- app/orders/item_service.py — walidacja przed operacjami, rollback odrzucenia,
  synchronizacja bez odejmowania zwolnienia i bez podwójnego doliczania rezerwacji.
- app/stock_issues/service.py — walidacja powiązań przed księgowaniem,
  wspólny wzór po księgowaniu, usunięcie alternatywnego wzoru nieużywanego helpera.
- app/models/part_demand.py — wyłącznie etykieta DELIVERED.
- app/part_demands/forms.py — rezerwacja oznaczona jako wyliczana i readonly;
  serwer niezależnie sprawdza przesłaną wartość.
- tests/test_part_demand_consistency.py — 45 wykonanych nowych przypadków.
- tests/test_part_demands_module.py — dawne testy ręcznych liczb mają teraz
  prawdziwy zapis rezerwacji albo używają rzeczywistego zera.
- docs/PART_DEMAND_CONSISTENCY_P1_P4.md — niniejsze reguły i wyniki.

## Wykonane testy

Nowe regresje: **45 passed, 0 failed, 0 skipped** (10 ostrzeżeń).
Zapotrzebowania + nowe regresje + rozliczenia + RW: **102 passed, 0 failed,
0 skipped** (23 ostrzeżenia, przed ostatnimi drobnymi zmianami sprawdzonymi
ponownie w pełnym zestawie).
Końcowy pełny Python: **400 passed, 0 failed, 0 skipped**, 238 ostrzeżeń.
JavaScript: **37 passed, 0 failed, 0 skipped**.

Pierwszy pełny przebieg wykazał dwa stare testy wpisujące niepoparte rezerwacje;
nie osłabiono nowej walidacji, poprawiono dane testowe zgodnie z regułą P2.

Dokładny pełny wrapper PowerShell (każdy silnik aplikacji wymuszony na SQLite
w pamięci PRZED inicjalizacją, niezależnie od instance/config.py):

```powershell
@'
import app as app_package
import pytest
original=app_package.register_extensions
def sqlite_only(application):
    application.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',SQLALCHEMY_BINDS={},SQLALCHEMY_ENGINE_OPTIONS={})
    original(application)
    from app.extensions import db
    with application.app_context():
        assert db.engine.url.drivername=='sqlite' and db.engine.url.database==':memory:'
app_package.register_extensions=sqlite_only
raise SystemExit(pytest.main(['-q','--tb=short','-p','no:cacheprovider']))
'@ | & C:/serwispro/venv/Scripts/python.exe -B -
node --test tests/js/*.test.js
```

Osobne wykonane regresje (fixture modułu wymusza SQLite przed inicjalizacją):

```powershell
& C:/serwispro/venv/Scripts/python.exe -B -m pytest tests/test_part_demand_consistency.py -q --tb=short -p no:cacheprovider
```

Przebieg 102 testów używał powyższego wrappera pytest z listą:
tests/test_part_demand_consistency.py, tests/test_part_demands_module.py,
tests/test_order_parts_settlement.py, tests/test_stock_issues_module.py.

Ostrzeżenia: istniejące nakładające się relacje SQLAlchemy, Query.get,
datetime.utcnow; osobny pytest również ReportLab/ast.NameConstant.
Nie testowano MariaDB, równoległości wielu procesów ani interfejsu w przeglądarce.
Nie wykonano połączeń/operacji na roboczej bazie, korekt, migracji ani zmian schematu.
Nie naprawiano P6/P9/P10; zabezpieczenia P7/P8 przeszły w pełnym zestawie.