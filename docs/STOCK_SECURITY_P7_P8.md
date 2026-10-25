# Zabezpieczenia P7/P8 — 2026-10-25

## Zakres

- Katalogowe endpointy movements są teraz wyłącznie jawną korektą ADJUSTMENT.
  Wymagają roli dopuszczonej przez istniejącą politykę RW, CSRF, firmy i oddziału
  użytkownika, aktywnego produktu, numeru dokumentu i uzasadnienia.
- Korekta zapisuje stan docelowy i historię z użytkownikiem w jednej transakcji,
  blokuje produkt i nie pozwala zejść poniżej aktywnych rezerwacji. Materiały
  zachowują dokładność 3 miejsc; części wymagają stanu całkowitego; zero jest dozwolone.
- ISSUE, AUTO_ISSUE, SALE, RESERVATION, RELEASE, RECEIPT i OPENING_BALANCE
  nie są dopuszczone przez ogólny formularz/serwis/repozytorium katalogowe.
  Właściwe przyjęcia i wydania pozostają w PZ/BO/RW, rezerwacje w zleceniu.
- Katalogowe tworzenie kartoteki wymaga stanu 0, edycja nie zapisuje stanu.
  To zamyka obejście korekty przez zwykłą edycję metadanych.
- Starszy interfejs inventory/operations korzysta z tego samego serwisu korekty;
  jego edycja nie zmienia stanu ani nie przepisuje oddziału produktu.
- Panel gotowości stosuje ReadinessReserveForm (Flask-WTF), dozwolone role
  takie jak pozostałe akcje rezerwacji zlecenia, zakres zlecenia i produktów.
  Frontend wysyła POST z tokenem, nie dawny GET do endpointu POST.
- Cała wielopozycyjna akcja gotowości jest jedną transakcją. Opcja commit=False
  w istniejącej rezerwacji służy wyłącznie tej atomowości; domyślny commit innych
  wywołań pozostaje zachowany. Formuły P9 nie zmieniono. Dodano brakujący import Decimal.

Nie naprawiano P1–P6/P9–P10. Nie modyfikowano historycznych danych ani migracji.
Nie tworzono nowych modeli, endpointów, mechanizmu CSRF ani magazynu.

## Pozostawione starsze API

Nazwy starych endpointów zachowano; nie można nimi wykonać bezpośredniego
odpisu. Niskopoziomowe InventoryService.consume_for_order/register_operation,
InventoryReservationService.consume_reservations oraz prywatny helper ruchu
pozycji pozostają w kodzie; nie znaleziono ich aktywnego wywołania przez endpoint
po tych zmianach. Nie zmieniano ich semantyki jako osobnego zadania.
CatalogService.issue_material_to_order nadal istnieje, lecz próba AUTO_ISSUE
trafia do blokady wspólnego add_stock_movement (także bez actor).

## Testy faktycznie wykonane

Końcowy pełny pytest: **355 passed, 0 failed, 0 skipped, 235 warnings**.
Wykonano poniższy wrapper w PowerShell, aby instance/config.py nie mogło skierować
testów do roboczej bazy. Żadne połączenie aplikacyjne w tym przebiegu nie miało
innego URI niż sqlite:///:memory:.

```powershell
@'
import app as app_package
import pytest
original = app_package.register_extensions
def sqlite_only(application):
    application.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SQLALCHEMY_BINDS={}, SQLALCHEMY_ENGINE_OPTIONS={})
    original(application)
    from app.extensions import db
    with application.app_context():
        assert db.engine.url.drivername == 'sqlite' and db.engine.url.database == ':memory:'
app_package.register_extensions = sqlite_only
raise SystemExit(pytest.main(['-q', '--tb=short', '-p', 'no:cacheprovider']))
'@ | & C:/serwispro/venv/Scripts/python.exe -
```

Oddzielny przebieg izolowanych modułów: **163 passed, 0 failed, 0 skipped**
(przed ostatnim dodaniem testu awarii historii, który przeszedł w pełnym przebiegu):

```powershell
& C:/serwispro/venv/Scripts/python.exe -m pytest tests/test_stock_security_paths.py tests/test_order_parts_settlement.py tests/test_order_parts_migration.py -q --tb=short -p no:cacheprovider
node --test tests/js/*.test.js
git diff --check
```

JavaScript: **37 passed, 0 failed, 0 skipped**. Testy VM wykonują rzeczywisty
skrypt panelu gotowości: GET odczytu, POST rezerwacji z tokenem, obsługa odmowy.
Globalnych skrótów nie zmieniono.

Nie wywołano flask db upgrade/downgrade ani żadnej operacji na roboczej bazie.
Testy migracji z istniejącego zestawu pracowały wyłącznie na własnej SQLite.
Nie wykonano weryfikacji przeglądarkowej ani równoległości na MariaDB.
Ostrzeżenia dotyczą istniejących relacji SQLAlchemy, Query.get i datetime.utcnow;
osobny przebieg zgłasza również ostrzeżenie ReportLab. Diff check zgłasza jedynie
istniejącą uwagę LF/CRLF w app/models/__init__.py.

## Pliki zmienione w tym zadaniu

- app/catalog/service.py — blokady operacji, korekta, zakres i transakcja;
  brak zmiany stanu w edycji, stan 0 przy tworzeniu, commit=False dla akcji gotowości.
- app/catalog/repository.py — brak bezpośredniego odpisu/zmiany rezerwacji.
- app/catalog/routes.py — role i actor korekty, oddział przy edycji.
- app/catalog/forms.py — wyłącznie korekta z dokumentem/uzasadnieniem, obsługa zera.
- app/inventory/routes.py, app/inventory/forms.py — zamknięcie alternatywnego formularza.
- app/orders/routes.py, app/orders/forms.py — CSRF, role, zakres, atomowa akcja gotowości.
- app/templates/catalog/parts_details.html, app/templates/catalog/materials_details.html — opis korekty.
- app/templates/orders/partials/order_readiness_summary.html — prawidłowy POST z CSRF.
- tests/test_stock_security_paths.py — testy stanu, rezerwacji, dokumentów i rollback.
- tests/js/readiness-security.test.js — regresje komunikacji panelu.
- docs/STOCK_SECURITY_P7_P8.md — niniejsze wyniki i instrukcja odtworzenia testów.

## Dalsze postępowanie

P7/P8 można przekazać do przeglądu i kontrolowanych testów staging. Nie jest to
zgoda na migrację ani wdrożenie produkcyjne: pozostają pozostałe punkty audytu,
uzgodnienie historii i próba na kopii MariaDB według istniejącego runbooka.