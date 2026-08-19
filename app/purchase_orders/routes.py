from __future__ import annotations

from datetime import date

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.catalog.service import CatalogService
from app.models.catalog_part import CatalogPart
from app.models.catalog_supplier import CatalogSupplier
from app.models.purchase_order import PURCHASE_ORDER_STATUS_LABELS

from . import bp
from .exceptions import PurchaseOrderError
from .forms import PurchaseOrderFilterForm, PurchaseOrderForm, PurchaseOrderStatusForm
from .service import purchase_order_service


def _company_id(): return getattr(current_user, "company_id", None)
def _branch_id(): return getattr(current_user, "branch_id", None)


def _supplier_choices(company_id):
    rows = CatalogSupplier.query.filter_by(company_id=company_id, is_active=True, is_supplier_active=True).order_by(CatalogSupplier.name.asc()).all()
    return [(0, "Wszyscy")] + [(row.id, f"{row.code} | {row.name}") for row in rows]


def _part_choices(company_id):
    rows = CatalogPart.query.filter_by(company_id=company_id, is_active=True).order_by(CatalogPart.name.asc()).all()
    return [(0, "Wszystkie")] + [(row.id, f"{row.code} | {row.name}") for row in rows]


@bp.route("/", methods=["GET"])
@login_required
def index():
    company_id = _company_id()
    if company_id is None: abort(404)
    form = PurchaseOrderFilterForm(request.args, meta={"csrf": False})
    form.supplier_id.choices = _supplier_choices(company_id)
    form.part_id.choices = _part_choices(company_id)
    orders = purchase_order_service.list_orders(company_id=company_id, branch_id=_branch_id(), actor=current_user, status=request.args.get("status") or None, supplier_id=request.args.get("supplier_id", type=int) or None, date_from=form.date_from.data, date_to=form.date_to.data, po_number=(request.args.get("po_number") or "").strip() or None, part_id=request.args.get("part_id", type=int) or None, created_by=request.args.get("created_by", type=int) or None)
    return render_template("purchase_orders/index.html", orders=orders, filter_form=form, status_labels=PURCHASE_ORDER_STATUS_LABELS)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create_from_demands():
    company_id = _company_id()
    if company_id is None: abort(404)
    form = PurchaseOrderForm()
    form.supplier_id.choices = _supplier_choices(company_id)[1:]
    raw_demand_ids = request.form.getlist("demand_ids") or request.args.getlist("demand_ids")
    demand_ids = [int(value) for value in raw_demand_ids if value.isdigit()]
    suggestions = purchase_order_service.preferred_supplier_suggestions(demand_ids=demand_ids, company_id=company_id, branch_id=_branch_id()) if demand_ids else {"supplier_ids": [], "groups": {}, "single_supplier_id": None}
    if len(suggestions["supplier_ids"]) > 1:
        flash("Zaznaczone części mają różnych preferowanych dostawców. Rozważ utworzenie osobnych zamówień dla każdej grupy.", "warning")
    if form.order_date.data is None:
        form.order_date.data = date.today()
    if form.supplier_id.data is None and suggestions["single_supplier_id"] is not None:
        form.supplier_id.data = suggestions["single_supplier_id"]
    if form.validate_on_submit():
        try:
            if suggestions["supplier_ids"] and form.supplier_id.data not in suggestions["supplier_ids"]:
                flash("Wybrany dostawca różni się od preferowanego dla tej części.", "warning")
            order = purchase_order_service.create_from_demands(demand_ids=demand_ids, supplier_id=form.supplier_id.data, company_id=company_id, branch_id=_branch_id(), actor=current_user, order_date=form.order_date.data, expected_delivery_date=form.expected_delivery_date.data, notes=form.notes.data)
        except PurchaseOrderError as exc:
            flash(str(exc), "danger")
        else:
            flash("Zamówienie zostało utworzone.", "success")
            return redirect(url_for("purchase_orders.details", order_id=order.id))
    return render_template("purchase_orders/form.html", form=form, title="Nowe zamówienie do dostawcy", demand_ids=demand_ids, suggestions=suggestions)


@bp.route("/<int:order_id>", methods=["GET"])
@login_required
def details(order_id):
    company_id = _company_id()
    if company_id is None: abort(404)
    try:
        order = purchase_order_service.get_order(order_id=order_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except PurchaseOrderError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("purchase_orders.index"))
    return render_template("purchase_orders/details.html", order=order, status_form=PurchaseOrderStatusForm(status=order.status), status_labels=PURCHASE_ORDER_STATUS_LABELS)


@bp.route("/<int:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit(order_id):
    company_id = _company_id()
    if company_id is None: abort(404)
    try:
        order = purchase_order_service.get_order(order_id=order_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except PurchaseOrderError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("purchase_orders.index"))
    form = PurchaseOrderForm(obj=order)
    form.supplier_id.choices = _supplier_choices(company_id)[1:]
    if form.validate_on_submit():
        try:
            purchase_order_service.update_order(order_id=order_id, supplier_id=form.supplier_id.data, order_date=form.order_date.data, expected_delivery_date=form.expected_delivery_date.data, notes=form.notes.data, company_id=company_id, branch_id=_branch_id(), actor=current_user)
        except PurchaseOrderError as exc:
            flash(str(exc), "danger")
        else:
            flash("Zamówienie zostało zaktualizowane.", "success")
            return redirect(url_for("purchase_orders.details", order_id=order_id))
    return render_template("purchase_orders/form.html", form=form, title=f"Edycja {order.po_number}", demand_ids=[])


@bp.route("/<int:order_id>/status", methods=["POST"])
@login_required
def update_status(order_id):
    company_id = _company_id()
    if company_id is None: abort(404)
    form = PurchaseOrderStatusForm()
    if not form.validate_on_submit():
        flash("Nieprawidłowy status.", "danger")
        return redirect(url_for("purchase_orders.details", order_id=order_id))
    try:
        purchase_order_service.update_status(order_id=order_id, status=form.status.data, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except PurchaseOrderError as exc:
        flash(str(exc), "danger")
    else:
        flash("Status zamówienia został zmieniony.", "success")
    return redirect(url_for("purchase_orders.details", order_id=order_id))


@bp.route("/search")
@login_required
def search():
    company_id = _company_id()
    if company_id is None: abort(404)
    orders = purchase_order_service.list_orders(company_id=company_id, branch_id=_branch_id(), actor=current_user, po_number=request.args.get("q"))
    return jsonify({"items": [{"id": row.id, "number": row.po_number, "supplier": row.supplier.name} for row in orders[:20]]})