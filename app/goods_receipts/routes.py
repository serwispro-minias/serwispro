from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.catalog_part import InventoryItem
from app.models.catalog_supplier import Supplier
from app.models.purchase_order import PurchaseOrder
from app.models.vat_rate import VatRate

from . import bp
from .exceptions import GoodsReceiptError
from .forms import GoodsReceiptAcceptForm, GoodsReceiptManualForm
from .service import goods_receipt_service


def _company_id():
    return getattr(current_user, "company_id", None)


def _branch_id():
    return getattr(current_user, "branch_id", None)


@bp.route("/")
@login_required
def index():
    company_id = _company_id()
    if company_id is None:
        abort(404)
    try:
        receipts = goods_receipt_service.list_receipts(company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except GoodsReceiptError as exc:
        flash(str(exc), "danger")
        receipts = []
    return render_template("goods_receipts/index.html", receipts=receipts, status_labels={"DRAFT": "Robocze", "POSTED": "Zaksięgowane", "CANCELLED": "Anulowane"})


@bp.route("/<int:receipt_id>")
@login_required
def details(receipt_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)
    try:
        receipt = goods_receipt_service.get_receipt(receipt_id=receipt_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except GoodsReceiptError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("goods_receipts.index"))
    return render_template("goods_receipts/details.html", receipt=receipt, accept_form=GoodsReceiptAcceptForm(), status_labels={"DRAFT": "Robocze", "POSTED": "Zaksięgowane", "CANCELLED": "Anulowane"})


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create_manual():
    company_id = _company_id()
    if company_id is None:
        abort(404)
    products = db.session.scalars(select(InventoryItem).where(InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)).order_by(InventoryItem.name.asc())).all()
    suppliers = db.session.scalars(select(Supplier).where(Supplier.company_id == company_id, Supplier.is_active.is_(True)).order_by(Supplier.name.asc())).all()
    vats = db.session.scalars(select(VatRate).where(VatRate.company_id == company_id, VatRate.is_active.is_(True)).order_by(VatRate.rate.asc())).all()
    form = GoodsReceiptManualForm()
    if form.validate_on_submit():
        items = _document_items_from_form()
        try:
            receipt = goods_receipt_service.create_receipt(items=items, supplier_id=request.form.get("supplier_id", type=int), company_id=company_id, branch_id=_branch_id(), actor=current_user, receipt_date=date.fromisoformat(request.form["receipt_date"]) if request.form.get("receipt_date") else None, notes=request.form.get("notes"))
        except GoodsReceiptError as exc:
            flash(str(exc), "danger")
        else:
            flash("Dokument PZ został utworzony.", "success")
            return redirect(url_for("goods_receipts.details", receipt_id=receipt.id))
    return render_template("goods_receipts/manual_form.html", products=products, suppliers=suppliers, vats=vats, form=form)


def _document_items_from_form() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    index = 0
    while f"items-{index}-inventory_item_id" in request.form:
        quantity = request.form.get(f"items-{index}-quantity_received")
        if quantity not in (None, ""):
            items.append({
                "inventory_item_id": request.form.get(f"items-{index}-inventory_item_id"),
                "quantity_received": quantity,
                "purchase_price_net": request.form.get(f"items-{index}-purchase_price_net"),
                "sale_price_net": request.form.get(f"items-{index}-sale_price_net"),
                "vat_id": request.form.get(f"items-{index}-vat_id"),
                "demand_id": request.form.get(f"items-{index}-demand_id") or None,
            })
        index += 1
    return items


@bp.route("/new/<int:purchase_order_id>", methods=["GET", "POST"])
@login_required
def create(purchase_order_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)
    order = db.session.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(PurchaseOrder.id == purchase_order_id, PurchaseOrder.company_id == company_id, PurchaseOrder.is_active.is_(True)))
    if order is None:
        abort(404)
    if request.method == "POST":
        items = []
        for item in order.items:
            quantity = request.form.get(f"quantity_{item.id}")
            if quantity not in (None, ""):
                items.append({"purchase_order_item_id": item.id, "quantity_received": quantity, "sale_price_net": request.form.get(f"sale_{item.id}"), "batch_number": request.form.get(f"batch_{item.id}"), "serial_number": request.form.get(f"serial_{item.id}"), "notes": request.form.get(f"notes_{item.id}")})
        try:
            receipt = goods_receipt_service.create_receipt(purchase_order_id=order.id, items=items, company_id=company_id, branch_id=_branch_id(), actor=current_user)
        except GoodsReceiptError as exc:
            flash(str(exc), "danger")
        else:
            flash("Dokument PZ został utworzony.", "success")
            return redirect(url_for("goods_receipts.details", receipt_id=receipt.id))
    return render_template("goods_receipts/form.html", order=order)


@bp.route("/<int:receipt_id>/accept", methods=["POST"])
@login_required
def accept(receipt_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)
    form = GoodsReceiptAcceptForm()
    if not form.validate_on_submit():
        flash("Nie udało się zatwierdzić dokumentu PZ.", "danger")
        return redirect(url_for("goods_receipts.details", receipt_id=receipt_id))
    try:
        goods_receipt_service.accept_receipt(receipt_id=receipt_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except GoodsReceiptError as exc:
        flash(str(exc), "danger")
    else:
        flash("Dokument PZ został przyjęty, a stany magazynowe zaktualizowane.", "success")
    return redirect(url_for("goods_receipts.details", receipt_id=receipt_id))