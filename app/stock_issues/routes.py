from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.models.catalog_part import InventoryItem

from . import bp
from .exceptions import StockIssueError
from .forms import StockIssueManualForm, StockIssuePostForm
from .service import stock_issue_service


def _company_id(): return getattr(current_user, "company_id", None)
def _branch_id(): return getattr(current_user, "branch_id", None)


@bp.route("/")
@login_required
def index():
    company_id = _company_id()
    if company_id is None: abort(404)
    try:
        issues = stock_issue_service.list_issues(company_id=company_id, branch_id=_branch_id(), actor=current_user, issue_number=request.args.get("issue_number"), order_id=request.args.get("order_id", type=int), issued_by=request.args.get("issued_by", type=int), date_from=request.args.get("date_from", type=lambda value: date.fromisoformat(value)), date_to=request.args.get("date_to", type=lambda value: date.fromisoformat(value)), status=request.args.get("status") or None)
    except (StockIssueError, ValueError) as exc:
        flash(str(exc), "danger")
        issues = []
    return render_template("stock_issues/index.html", issues=issues, status_labels={"DRAFT": "Robocze", "POSTED": "Zaksięgowane", "CANCELLED": "Anulowane"})


@bp.route("/<int:issue_id>")
@login_required
def details(issue_id):
    company_id = _company_id()
    if company_id is None: abort(404)
    try:
        issue = stock_issue_service.get_issue(issue_id=issue_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except StockIssueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("stock_issues.index"))
    return render_template("stock_issues/details.html", issue=issue, status_labels={"DRAFT": "Robocze", "POSTED": "Zaksięgowane", "CANCELLED": "Anulowane"}, post_form=StockIssuePostForm())


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    company_id = _company_id()
    if company_id is None: abort(404)
    products = db.session.scalars(select(InventoryItem).where(InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)).order_by(InventoryItem.name.asc())).all()
    form = StockIssueManualForm()
    if form.validate_on_submit():
        items = []
        index = 0
        while f"items-{index}-inventory_item_id" in request.form:
            quantity = request.form.get(f"items-{index}-quantity")
            if quantity not in (None, ""):
                items.append({"inventory_item_id": request.form.get(f"items-{index}-inventory_item_id"), "quantity": quantity})
            index += 1
        try:
            issue = stock_issue_service.create_issue(items=items, company_id=company_id, branch_id=_branch_id(), actor=current_user, service_order_id=request.form.get("service_order_id", type=int), issue_date=date.fromisoformat(request.form["issue_date"]) if request.form.get("issue_date") else None, notes=request.form.get("notes"))
        except StockIssueError as exc:
            flash(str(exc), "danger")
        else:
            flash("Dokument RW został utworzony.", "success")
            return redirect(url_for("stock_issues.details", issue_id=issue.id))
    return render_template("stock_issues/form.html", products=products, form=form)


@bp.route("/<int:issue_id>/post", methods=["POST"])
@login_required
def post(issue_id):
    company_id = _company_id()
    if company_id is None: abort(404)
    form = StockIssuePostForm()
    if not form.validate_on_submit():
        flash("Nie udało się zaksięgować RW.", "danger")
        return redirect(url_for("stock_issues.details", issue_id=issue_id))
    try:
        stock_issue_service.post_issue(issue_id=issue_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except StockIssueError as exc:
        flash(str(exc), "danger")
    else:
        flash("Dokument RW został zaksięgowany.", "success")
    return redirect(url_for("stock_issues.details", issue_id=issue_id))


@bp.route("/orders/<int:service_order_id>/issue", methods=["POST"])
@login_required
def issue_order(service_order_id):
    company_id = _company_id()
    if company_id is None: abort(404)
    quantities = {}
    for key, value in request.form.items():
        if key.startswith("reservation_") and value:
            quantities[int(key.removeprefix("reservation_"))] = value
    try:
        issue = stock_issue_service.issue_reserved_parts(service_order_id=service_order_id, company_id=company_id, branch_id=_branch_id(), actor=current_user, quantities=quantities)
    except StockIssueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("orders.details", order_id=service_order_id))
    flash("Części zostały wydane dokumentem RW.", "success")
    return redirect(url_for("stock_issues.details", issue_id=issue.id))