from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.models.catalog_part import InventoryItem
from app.models.vat_rate import VatRate

from . import bp
from .exceptions import OpeningBalanceError
from .service import opening_balance_service


def _company_id(): return getattr(current_user, "company_id", None)
def _branch_id(): return getattr(current_user, "branch_id", None)


@bp.route("/")
@login_required
def index():
    company_id = _company_id()
    if company_id is None: abort(404)
    try:
        balances = opening_balance_service.list(company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except OpeningBalanceError as exc:
        flash(str(exc), "danger")
        balances = []
    return render_template("opening_balances/index.html", balances=balances)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    company_id = _company_id()
    if company_id is None: abort(404)
    products = db.session.scalars(select(InventoryItem).where(InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)).order_by(InventoryItem.name.asc())).all()
    vats = db.session.scalars(select(VatRate).where(VatRate.company_id == company_id, VatRate.is_active.is_(True)).order_by(VatRate.rate.asc())).all()
    if request.method == "POST":
        items = []
        for product in products:
            raw = request.form.get(f"quantity_{product.id}")
            if raw not in (None, ""):
                items.append({"inventory_item_id": product.id, "quantity": raw, "purchase_price_net": request.form.get(f"price_{product.id}"), "vat_id": request.form.get(f"vat_{product.id}")})
        try:
            balance = opening_balance_service.create(items=items, company_id=company_id, branch_id=_branch_id(), actor=current_user, document_date=date.fromisoformat(request.form["document_date"]) if request.form.get("document_date") else None, notes=request.form.get("notes"))
        except OpeningBalanceError as exc:
            flash(str(exc), "danger")
        else:
            flash("Bilans otwarcia został utworzony.", "success")
            return redirect(url_for("opening_balances.details", balance_id=balance.id))
    return render_template("opening_balances/form.html", products=products, vats=vats)


@bp.route("/<int:balance_id>")
@login_required
def details(balance_id):
    company_id = _company_id()
    if company_id is None: abort(404)
    try:
        balance = opening_balance_service.get(balance_id=balance_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except OpeningBalanceError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("opening_balances.index"))
    return render_template("opening_balances/details.html", balance=balance)


@bp.route("/<int:balance_id>/post", methods=["POST"])
@login_required
def post(balance_id):
    company_id = _company_id()
    if company_id is None: abort(404)
    try:
        opening_balance_service.post(balance_id=balance_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except OpeningBalanceError as exc:
        flash(str(exc), "danger")
    else:
        flash("Bilans otwarcia został zaksięgowany.", "success")
    return redirect(url_for("opening_balances.details", balance_id=balance_id))
