from __future__ import annotations

from io import BytesIO

from flask import abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.models.inventory_stock_operation import INVENTORY_OPERATION_TYPE_LABELS
from app.catalog.service import CatalogService

from . import bp
from .exceptions import InventoryNotFoundError, InventoryValidationError
from .forms import InventoryOperationForm, InventoryPartForm, InventorySearchForm
from .print_service import InventoryPrintService
from .service import InventoryService


service = InventoryService()
catalog_service = CatalogService()
print_service = InventoryPrintService(service=service)


def _company_id() -> int | None:
    return getattr(current_user, "company_id", None)


def _branch_id() -> int | None:
    return getattr(current_user, "branch_id", None)


def _user_id() -> int | None:
    return getattr(current_user, "id", None)


@bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    search_form = InventorySearchForm(request.args, meta={"csrf": False})
    search_form.q.data = q

    parts = service.list_parts(page=page, per_page=20, company_id=_company_id(), query_text=q)
    low_stock_parts = service.low_stock_list(company_id=_company_id())

    return render_template(
        "inventory/index.html",
        parts=parts,
        q=q,
        search_form=search_form,
        low_stock_count=len(low_stock_parts),
        low_stock_parts=low_stock_parts[:10],
    )


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create_part():
    form = InventoryPartForm()
    form.category_id.choices = catalog_service.category_choices(company_id=_company_id())
    form.vat_id.choices = catalog_service.vat_rate_choices(company_id=_company_id())
    if request.method == "GET":
        form.is_active.data = "1"

    if form.validate_on_submit():
        try:
            part = service.create_part(
                form.data,
                company_id=_company_id(),
                branch_id=_branch_id(),
                user_id=_user_id(),
            )
        except InventoryValidationError as exc:
            flash(str(exc), "danger")
        else:
            flash("Karta części została utworzona.", "success")
            return redirect(url_for("inventory.details", part_id=part.id))

    return render_template("inventory/form.html", form=form, title="Nowa część", part=None)


@bp.route("/<int:part_id>")
@login_required
def details(part_id: int):
    part = service.get_part(part_id, company_id=_company_id())
    if part is None:
        abort(404)

    operation_form = InventoryOperationForm()
    operations = service.list_part_operations(part_id, company_id=_company_id())
    return render_template(
        "inventory/details.html",
        part=part,
        operations=operations,
        operation_form=operation_form,
        operation_labels=INVENTORY_OPERATION_TYPE_LABELS,
    )


@bp.route("/<int:part_id>/edit", methods=["GET", "POST"])
@login_required
def edit_part(part_id: int):
    part = service.get_part(part_id, company_id=_company_id())
    if part is None:
        abort(404)

    form = InventoryPartForm(obj=part)
    form.category_id.choices = catalog_service.category_choices(company_id=_company_id())
    form.vat_id.choices = catalog_service.vat_rate_choices(company_id=_company_id())
    if request.method == "GET":
        form.is_active.data = "1" if part.is_active else "0"

    if form.validate_on_submit():
        try:
            service.update_part(
                part_id,
                form.data,
                company_id=_company_id(),
                branch_id=_branch_id(),
                user_id=_user_id(),
            )
        except (InventoryValidationError, InventoryNotFoundError) as exc:
            flash(str(exc), "danger")
        else:
            flash("Karta części została zaktualizowana.", "success")
            return redirect(url_for("inventory.details", part_id=part_id))

    return render_template("inventory/form.html", form=form, title="Edycja części", part=part)


@bp.route("/<int:part_id>/operations", methods=["POST"])
@login_required
def add_operation(part_id: int):
    form = InventoryOperationForm()
    if not form.validate_on_submit():
        flash("Nie udało się dodać operacji magazynowej.", "danger")
        return redirect(url_for("inventory.details", part_id=part_id))

    try:
        service.register_operation(
            part_id=part_id,
            operation_type=form.operation_type.data,
            quantity_raw=form.quantity.data,
            document_number=form.document_number.data,
            comment=form.comment.data,
            company_id=_company_id(),
            branch_id=_branch_id(),
            user_id=_user_id(),
        )
    except (InventoryValidationError, InventoryNotFoundError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Operacja magazynowa została zapisana.", "success")

    return redirect(url_for("inventory.details", part_id=part_id))


@bp.route("/<int:part_id>/print/card")
@login_required
def print_part_card(part_id: int):
    document = print_service.build_part_card(part_id=part_id, company_id=_company_id())
    if document is None:
        abort(404)
    return send_file(
        BytesIO(document.content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=document.filename,
    )


@bp.route("/<int:part_id>/print/history")
@login_required
def print_part_history(part_id: int):
    document = print_service.build_part_history(part_id=part_id, company_id=_company_id())
    if document is None:
        abort(404)
    return send_file(
        BytesIO(document.content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=document.filename,
    )


@bp.route("/print/stock-state")
@login_required
def print_stock_state():
    document = print_service.build_stock_state(company_id=_company_id())
    return send_file(
        BytesIO(document.content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=document.filename,
    )
