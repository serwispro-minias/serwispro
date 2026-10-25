from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "app" / "templates"


SAVE_FORM_COUNTS = {
    "catalog/categories_form.html": 1,
    "catalog/manufacturers_form.html": 1,
    "catalog/materials_form.html": 1,
    "catalog/parts_form.html": 1,
    "catalog/services_form.html": 1,
    "catalog/suppliers_form.html": 1,
    "catalog/vat_rates_form.html": 1,
    "customers/form.html": 1,
    "devices/form.html": 1,
    "goods_receipts/form.html": 1,
    "goods_receipts/manual_form.html": 1,
    "inventory/form.html": 1,
    "opening_balances/form.html": 1,
    "order_photos/gallery.html": 1,
    "orders/action_form.html": 1,
    "orders/details.html": 2,  # status form and estimate creation; other actions stay unmarked
    "orders/form.html": 1,
    "orders/partials/customer_modal_form.html": 1,
    "orders/partials/device_modal_form.html": 1,
    "orders/partials/order_item_form.html": 1,
    "orders/partials/order_part_usage_form.html": 1,
    "orders/partials/timeline_entry_form.html": 1,
    "part_demands/details.html": 1,
    "part_demands/form.html": 1,
    "purchase_orders/details.html": 1,
    "purchase_orders/form.html": 1,
    "services/details.html": 1,  # custom estimate item; other actions stay unmarked
    "settings/notifications.html": 2,
    "settings/vat_rates.html": 1,
    "stock_issues/form.html": 1,
    "tasks/form.html": 1,
    "tasks/details.html": 2,  # comment and attachment forms
    "workflow/index.html": 2,  # status and transition creation
}


def test_save_capable_forms_have_explicit_ctrl_enter_submitters():
    for relative_path, expected_count in SAVE_FORM_COUNTS.items():
        source = (TEMPLATE_ROOT / relative_path).read_text(encoding="utf-8")
        assert source.count("data-shortcut-save") >= expected_count, relative_path
        assert source.count("data-shortcut-save-submit") >= expected_count, relative_path


def test_ambiguous_and_destructive_forms_are_not_shortcut_save_forms():
    ambiguous = (TEMPLATE_ROOT / "estimate_approval/public_approve.html").read_text(encoding="utf-8")
    communication = (TEMPLATE_ROOT / "orders/communication_proposal.html").read_text(encoding="utf-8")
    opening_balance_post = (TEMPLATE_ROOT / "opening_balances/details.html").read_text(encoding="utf-8")
    assert "data-shortcut-save" not in ambiguous
    assert "data-shortcut-save" not in communication
    assert "data-shortcut-save" not in opening_balance_post