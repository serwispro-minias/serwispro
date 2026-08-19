from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.purchase_order import PurchaseOrder

from . import bp
from .exceptions import GoodsReceiptError
from .forms import GoodsReceiptAcceptForm
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
    return render_template("goods_receipts/index.html", receipts=receipts, status_labels={"NEW": "Nowe", "ACCEPTED": "Przyjęte", "CANCELLED": "Anulowane"})


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
    return render_template("goods_receipts/details.html", receipt=receipt, accept_form=GoodsReceiptAcceptForm(), status_labels={"NEW": "Nowe", "ACCEPTED": "Przyjęte", "CANCELLED": "Anulowane"})


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
                items.append({"purchase_order_item_id": item.id, "quantity_received": quantity, "batch_number": request.form.get(f"batch_{item.id}"), "serial_number": request.form.get(f"serial_{item.id}"), "notes": request.form.get(f"notes_{item.id}")})
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