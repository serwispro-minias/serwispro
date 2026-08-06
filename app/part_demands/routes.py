from __future__ import annotations

from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from .exceptions import PartDemandNotFoundError, PartDemandPermissionError, PartDemandValidationError
from .forms import PartDemandFilterForm, PartDemandForm, PartDemandFulfillForm, PartDemandStatusForm
from .service import PartDemandService

service = PartDemandService()


def _company_id() -> int | None:
    return getattr(current_user, "company_id", None)


def _branch_id() -> int | None:
    return getattr(current_user, "branch_id", None)


def _prepare_filter_form(form: PartDemandFilterForm, *, company_id: int) -> None:
    form.status.choices = [("", "Wszystkie")] + service.get_status_choices()
    form.priority.choices = [("", "Wszystkie")] + service.get_priority_choices()
    form.branch_id.choices = service.list_branch_choices(company_id=company_id)
    form.inventory_item_id.choices = service.list_part_choices(company_id=company_id)


def _prepare_form_choices(form: PartDemandForm, *, company_id: int) -> None:
    form.inventory_item_id.choices = [choice for choice in service.list_part_choices(company_id=company_id) if choice[0] != 0]


@bp.route("/", methods=["GET"])
@login_required
def index():
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = PartDemandFilterForm(request.args, meta={"csrf": False})
    _prepare_filter_form(form, company_id=company_id)

    selected_status = (request.args.get("status") or "").strip() or None
    selected_priority = (request.args.get("priority") or "").strip() or None
    selected_order_id = request.args.get("order_id", type=int)
    selected_branch_id = request.args.get("branch_id", type=int)
    selected_part_id = request.args.get("inventory_item_id", type=int)
    query_text = (request.args.get("q") or "").strip() or None

    if selected_branch_id in (None, 0):
        selected_branch_id = None
    if selected_part_id in (None, 0):
        selected_part_id = None

    try:
        rows = service.list_demands(
            company_id=company_id,
            actor=current_user,
            branch_scope_id=_branch_id(),
            status=selected_status,
            priority=selected_priority,
            branch_filter_id=selected_branch_id,
            order_id=selected_order_id,
            inventory_item_id=selected_part_id,
            expected_date_from=form.expected_date_from.data,
            expected_date_to=form.expected_date_to.data,
            query_text=query_text,
        )
    except PartDemandPermissionError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("dashboard.index"))

    return render_template(
        "part_demands/index.html",
        demands=rows,
        filter_form=form,
        status_labels=service.get_status_labels(),
        priority_labels=service.get_priority_labels(),
    )


@bp.route("/grouped", methods=["GET"])
@login_required
def grouped():
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = PartDemandFilterForm(request.args, meta={"csrf": False})
    _prepare_filter_form(form, company_id=company_id)

    selected_status = (request.args.get("status") or "").strip() or None
    selected_priority = (request.args.get("priority") or "").strip() or None
    selected_branch_id = request.args.get("branch_id", type=int)
    if selected_branch_id in (None, 0):
        selected_branch_id = None

    try:
        rows = service.list_grouped(
            company_id=company_id,
            actor=current_user,
            branch_scope_id=_branch_id(),
            status=selected_status,
            priority=selected_priority,
            branch_filter_id=selected_branch_id,
            expected_date_from=form.expected_date_from.data,
            expected_date_to=form.expected_date_to.data,
        )
    except PartDemandPermissionError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("dashboard.index"))

    return render_template("part_demands/grouped.html", grouped_rows=rows, filter_form=form)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = PartDemandForm()
    _prepare_form_choices(form, company_id=company_id)

    if form.validate_on_submit():
        try:
            row = service.create_demand(
                data=dict(form.data),
                company_id=company_id,
                branch_scope_id=_branch_id(),
                actor=current_user,
            )
        except (PartDemandValidationError, PartDemandPermissionError) as exc:
            flash(str(exc), "danger")
        else:
            flash("Zapotrzebowanie zostało utworzone.", "success")
            return redirect(url_for("part_demands.details", demand_id=row.id))

    return render_template("part_demands/form.html", form=form, title="Nowe zapotrzebowanie")


@bp.route("/<int:demand_id>", methods=["GET"])
@login_required
def details(demand_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        row = service.get_demand(demand_id=demand_id, company_id=company_id, branch_scope_id=_branch_id(), actor=current_user)
    except (PartDemandNotFoundError, PartDemandPermissionError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("part_demands.index"))

    status_form = PartDemandStatusForm()
    status_form.status.data = row.status
    status_form.expected_date.data = row.expected_date
    fulfill_form = PartDemandFulfillForm()
    fulfill_form.reserve_quantity.data = row.missing_quantity or Decimal("0.001")

    technician = None
    for action in reversed(row.service_order.actions):
        if action.technician is not None:
            technician = action.technician
            break

    return render_template(
        "part_demands/details.html",
        demand=row,
        status_form=status_form,
        fulfill_form=fulfill_form,
        technician=technician,
        status_labels=service.get_status_labels(),
        priority_labels=service.get_priority_labels(),
    )


@bp.route("/<int:demand_id>/edit", methods=["GET", "POST"])
@login_required
def edit(demand_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        row = service.get_demand(demand_id=demand_id, company_id=company_id, branch_scope_id=_branch_id(), actor=current_user)
    except (PartDemandNotFoundError, PartDemandPermissionError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("part_demands.index"))

    form = PartDemandForm(obj=row)
    _prepare_form_choices(form, company_id=company_id)

    if form.validate_on_submit():
        try:
            service.update_demand(
                demand_id=demand_id,
                data=dict(form.data),
                company_id=company_id,
                branch_scope_id=_branch_id(),
                actor=current_user,
            )
        except (PartDemandValidationError, PartDemandPermissionError) as exc:
            flash(str(exc), "danger")
        else:
            flash("Zapotrzebowanie zostało zaktualizowane.", "success")
            return redirect(url_for("part_demands.details", demand_id=demand_id))

    return render_template("part_demands/form.html", form=form, title="Edycja zapotrzebowania")


@bp.route("/<int:demand_id>/status", methods=["POST"])
@login_required
def change_status(demand_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = PartDemandStatusForm()
    if not form.validate_on_submit():
        flash("Nie udało się zaktualizować statusu.", "danger")
        return redirect(url_for("part_demands.details", demand_id=demand_id))

    try:
        row = service.get_demand(demand_id=demand_id, company_id=company_id, branch_scope_id=_branch_id(), actor=current_user)
        service.update_demand(
            demand_id=demand_id,
            data={
                "service_order_id": row.service_order_id,
                "service_order_item_id": row.service_order_item_id,
                "inventory_item_id": row.inventory_item_id,
                "requested_quantity": row.requested_quantity,
                "reserved_quantity": row.reserved_quantity,
                "missing_quantity": row.missing_quantity,
                "status": form.status.data,
                "priority": row.priority,
                "expected_date": form.expected_date.data,
                "notes": form.notes.data or row.notes,
            },
            company_id=company_id,
            branch_scope_id=_branch_id(),
            actor=current_user,
        )
    except (PartDemandNotFoundError, PartDemandValidationError, PartDemandPermissionError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Status zapotrzebowania zaktualizowany.", "success")

    return redirect(url_for("part_demands.details", demand_id=demand_id))


@bp.route("/<int:demand_id>/fulfill", methods=["POST"])
@login_required
def fulfill(demand_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = PartDemandFulfillForm()
    if not form.validate_on_submit():
        flash("Nie udało się zrealizować zapotrzebowania.", "danger")
        return redirect(url_for("part_demands.details", demand_id=demand_id))

    try:
        service.fulfill_demand(
            demand_id=demand_id,
            reserve_quantity=Decimal(form.reserve_quantity.data),
            company_id=company_id,
            branch_scope_id=_branch_id(),
            actor=current_user,
        )
    except (PartDemandNotFoundError, PartDemandValidationError, PartDemandPermissionError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Zapotrzebowanie zostało zrealizowane i przypisane do zlecenia.", "success")

    return redirect(url_for("part_demands.details", demand_id=demand_id))


@bp.route("/<int:demand_id>/delete", methods=["POST"])
@login_required
def delete(demand_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        service.delete_demand(demand_id=demand_id, company_id=company_id, branch_scope_id=_branch_id(), actor=current_user)
    except (PartDemandNotFoundError, PartDemandPermissionError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Zapotrzebowanie usunięte.", "success")

    return redirect(url_for("part_demands.index"))
