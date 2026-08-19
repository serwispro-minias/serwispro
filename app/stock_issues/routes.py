from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from .exceptions import StockIssueError
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
    return render_template("stock_issues/index.html", issues=issues, status_labels={"DRAFT": "Robocze", "ISSUED": "Wydane", "CANCELLED": "Anulowane"})


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
    return render_template("stock_issues/details.html", issue=issue, status_labels={"DRAFT": "Robocze", "ISSUED": "Wydane", "CANCELLED": "Anulowane"})


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