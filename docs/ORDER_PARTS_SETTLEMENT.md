# Części i materiały w zleceniu

## Obsługa

1. W szczegółach zlecenia otwórz zakładkę **Części i usługi**.
2. Wyszukaj produkt po kodzie, nazwie lub EAN (dla części).
3. Wybierz **Zarezerwuj dostępne** albo **Bez rezerwacji — rozlicz później**.
4. Rezerwacja nie zmienia stanu fizycznego. Brak części tworzy istniejące zapotrzebowanie PartDemand.
5. W wierszu produktu podaj rzeczywiste zużycie i wybierz **Przygotuj RW**.
6. Roboczy RW nie zmienia stanu. Uprawniony magazynier księguje dokument osobnym przyciskiem.
7. Księgowanie zapisuje rozchód, ilość zużytą i zwalnia niewykorzystaną rezerwację tej pozycji.
8. Aby niczego nie zużyć, użyj operacji **Zwolnij**. Nie powiększa ona stanu fizycznego.
9. Po PZ dostarczony produkt można przypisać operacją **Zarezerwuj** lub rozliczyć bez rezerwacji.

Przykład: rezerwacja 5, zużycie 3 = rozchód 3 i zwolnienie 2.
Większe zużycie jest dozwolone tylko przy wolnym stanie, bez naruszania pozostałych rezerwacji.
W wierszu widoczne są stan, dostępność, rezerwacja, zużycie, zwolnienie i powiązane RW.
Przygotowanie RW i zmiana rezerwacji wymagają aktualnej wersji pozycji; nieaktualny formularz trzeba odświeżyć.
Ctrl+Enter nie księguje RW; globalne skróty pozostają niezmienione.

## Wdrożenie

Wymagana migracja: **8b3d0e5f2c91**, po **7a2c9f4e1b80**.
Rozszerza istniejące stock_issue_items o materiał, pozycję zlecenia i wersję rozliczenia,
oraz zmienia ilość na Numeric(12,3). Zachowuje istniejące pozycje i ich ilości.
Downgrade blokuje usuwanie istniejących powiązań rozliczeń.

Migrację przetestowano na izolowanej SQLite. Nie zastosowano jej automatycznie
do roboczej bazy MySQL. Przed uruchomieniem nowego kodu należy wykonać kopię bazy
i wdrożyć migrację w kontrolowanym oknie serwisowym.

Historyczne rezerwacje katalogowe mogły już zmniejszyć stan fizyczny.
Nowy kod nie odtwarza tych ilości automatycznie i nie przepisuje historycznych danych.
Takie pozycje wymagają uzgodnienia stanu z dokumentacją magazynową przed rozliczeniem.
Lustrzane zapisy starych rezerwacji w obu istniejących tabelach nie są liczone podwójnie.

## Zmodyfikowane pliki etapu

- app/models/stock_issue_item.py
- app/inventory/reservation_service.py
- app/catalog/service.py
- app/catalog/routes.py
- app/orders/item_service.py
- app/orders/item_repository.py
- app/orders/readiness_service.py
- app/orders/routes.py
- app/orders/forms.py
- app/part_demands/service.py
- app/stock_issues/service.py
- app/stock_issues/routes.py
- app/templates/orders/details.html
- app/templates/orders/partials/order_item_form.html
- app/templates/orders/partials/order_item_table.html
- app/templates/stock_issues/details.html
- migrations/versions/8b3d0e5f2c91_order_item_rw_settlement.py
- tests/test_order_items_module.py
- tests/test_stock_issues_module.py
- tests/test_order_parts_settlement.py
- tests/test_order_parts_migration.py
- docs/ORDER_PARTS_SETTLEMENT.md

## Granice weryfikacji

Testy automatyczne obejmują żądania HTTP, CSRF, role, zakres firmy/oddziału,
ponowienia, nieaktualne wersje, transakcyjne wycofanie i migrację na SQLite.
Nie wykonano testu wieloprocesowych wyścigów na MySQL ani ręcznej kontroli przeglądarkowej.