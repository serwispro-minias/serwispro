from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import OperationalError

from app.estimate_approval.service import (
    EstimateApprovalNotFoundError,
    EstimateApprovalPermissionError,
    EstimateApprovalValidationError,
    estimate_approval_service,
)
from app.extensions import db
from app.models.service_estimate import SERVICE_ESTIMATE_STATUS_LABELS

from . import bp
from .forms import EstimateCreateForm, EstimateItemForm, EstimateReorderForm, EstimateSendForm, EstimateStatusForm
from .service import EstimateNotFoundError, EstimateService, EstimateValidationError, estimate_service


logger = logging.getLogger(__name__)


def _company_id() -> int | None:
    return getattr(current_user, "company_id", None)


def _branch_id() -> int | None:
    return getattr(current_user, "branch_id", None)


def _upload_root() -> Path:
    configured = current_app.config.get("UPLOAD_FOLDER")
    if configured:
        return Path(configured).resolve()
    return (Path(current_app.root_path).parent / "uploads").resolve()


@bp.route("/")
@login_required
def index():
    estimates = estimate_service.list_estimates(company_id=_company_id(), branch_id=_branch_id())
    return render_template(
        "services/index.html",
        estimates=estimates,
        status_labels=SERVICE_ESTIMATE_STATUS_LABELS,
    )


@bp.route("/orders/<int:order_id>/estimates", methods=["POST"])
@login_required
def create_from_order(order_id: int):
    form = EstimateCreateForm()
    if not form.validate_on_submit():
        flash("Nie udało się utworzyć kosztorysu.", "danger")
        return redirect(url_for("orders.details", order_id=order_id, tab="estimates"))

    try:
        estimate = estimate_service.create_from_order(
            order_id=order_id,
            company_id=_company_id(),
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            valid_until=form.valid_until.data,
            notes=form.notes.data,
        )
    except EstimateNotFoundError as exc:
        abort(404, description=str(exc))
    except EstimateValidationError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("orders.details", order_id=order_id, tab="estimates"))

    flash("Kosztorys został utworzony.", "success")
    return redirect(url_for("services.details", estimate_id=estimate.id))


@bp.route("/<int:estimate_id>")
@login_required
def details(estimate_id: int):
    company_id = _company_id()
    estimate = estimate_service.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=_branch_id())
    if estimate is None:
        abort(404)

    item_form = EstimateItemForm()
    send_form = EstimateSendForm()
    reorder_form = EstimateReorderForm()
    status_form = EstimateStatusForm()
    status_form.status.data = estimate.status
    active_token = (
        estimate_approval_service.get_active_token_for_estimate(
            estimate_id=estimate.id,
            company_id=company_id,
            branch_id=_branch_id(),
        )
        if company_id is not None
        else None
    )
    approval_link = (
        estimate_approval_service.generate_public_link(token_value=active_token.token, base_url=request.url_root)
        if active_token is not None
        else None
    )
    is_admin = any((role.name or "").strip().lower() == "administrator" for role in getattr(current_user, "roles", []))

    return render_template(
        "services/details.html",
        estimate=estimate,
        order=estimate.service_order,
        item_form=item_form,
        send_form=send_form,
        reorder_form=reorder_form,
        status_form=status_form,
        status_labels=estimate_service.get_status_labels(),
        item_source_labels=estimate_service.get_item_source_labels(),
        latest_versions=estimate_service.list_estimates_for_order(order_id=estimate.service_order_id, company_id=company_id, branch_id=_branch_id()),
        approval_link=approval_link,
        has_active_approval_token=active_token is not None,
        is_admin=is_admin,
    )


@bp.route("/<int:estimate_id>/items", methods=["POST"])
@login_required
def add_item(estimate_id: int):
    form = EstimateItemForm()
    if not form.validate_on_submit():
        flash("Nie udało się dodać pozycji.", "danger")
        return redirect(url_for("services.details", estimate_id=estimate_id))

    edited_estimate = None
    try:
        edited_estimate = estimate_service.add_manual_item(
            estimate_id=estimate_id,
            company_id=_company_id(),
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            name=form.name.data or "",
            quantity_raw=form.quantity.data,
            unit=form.unit.data,
            unit_net_price_raw=form.unit_net_price.data,
            discount_percent_raw=form.discount_percent.data,
            vat_rate_raw=form.vat_rate.data,
            description=form.description.data,
            sort_order=form.sort_order.data,
        )
    except EstimateValidationError as exc:
        flash(str(exc), "danger")
    else:
        flash("Pozycja została dodana.", "success")
    target_id = edited_estimate.id if edited_estimate is not None else estimate_id
    return redirect(url_for("services.details", estimate_id=target_id))


@bp.route("/<int:estimate_id>/items/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(estimate_id: int, item_id: int):
    estimate = estimate_service.delete_item(
        estimate_id=estimate_id,
        item_id=item_id,
        company_id=_company_id(),
        branch_id=_branch_id(),
        user_id=getattr(current_user, "id", None),
    )
    flash("Pozycja została usunięta.", "success")
    return redirect(url_for("services.details", estimate_id=estimate.id))


@bp.route("/<int:estimate_id>/reorder", methods=["POST"])
@login_required
def reorder_items(estimate_id: int):
    raw_order = (request.form.get("item_order") or "").strip()
    item_ids = [int(value) for value in raw_order.split(",") if value.strip().isdigit()]
    if not item_ids:
        flash("Nieprawidłowa kolejność pozycji.", "danger")
        return redirect(url_for("services.details", estimate_id=estimate_id))
    estimate = estimate_service.reorder_items(
        estimate_id=estimate_id,
        item_ids=item_ids,
        company_id=_company_id(),
        branch_id=_branch_id(),
        user_id=getattr(current_user, "id", None),
    )
    flash("Kolejność pozycji została zapisana.", "success")
    return redirect(url_for("services.details", estimate_id=estimate.id))


@bp.route("/<int:estimate_id>/recalculate", methods=["POST"])
@login_required
def recalculate(estimate_id: int):
    estimate = estimate_service.recalculate_estimate(
        estimate_id=estimate_id,
        company_id=_company_id(),
        branch_id=_branch_id(),
        user_id=getattr(current_user, "id", None),
    )
    flash("Wartości kosztorysu zostały przeliczone.", "success")
    return redirect(url_for("services.details", estimate_id=estimate.id))


@bp.route("/<int:estimate_id>/send", methods=["POST"])
@login_required
def send(estimate_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)
    branch_id = _branch_id()
    user_id = getattr(current_user, "id", None)
    try:
        _, _, _ = estimate_approval_service.send_estimate_email(
            estimate_id=estimate_id,
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
            base_url=request.url_root,
        )
    except OperationalError:
        db.session.rollback()
        # Lightweight test schemas may not include approval-token tables.
        estimate_service.send_to_client(
            estimate_id=estimate_id,
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
        )
        flash("Kosztorys został wysłany bez linku akceptacji (moduł akceptacji niedostępny).", "warning")
        return redirect(url_for("services.details", estimate_id=estimate_id))
    except EstimateApprovalNotFoundError as exc:
        abort(404, description=str(exc))
    except EstimateApprovalValidationError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("services.details", estimate_id=estimate_id))

    flash("Kosztorys został wysłany do klienta wraz z linkiem do decyzji.", "success")
    return redirect(url_for("services.details", estimate_id=estimate_id))


@bp.route("/<int:estimate_id>/approval/copy-link", methods=["POST"])
@login_required
def copy_link(estimate_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    token = estimate_approval_service.get_active_token_for_estimate(
        estimate_id=estimate_id,
        company_id=company_id,
        branch_id=_branch_id(),
    )
    if token is None:
        flash("Brak aktywnego linku. Najpierw wyślij kosztorys do klienta.", "warning")
        return redirect(url_for("services.details", estimate_id=estimate_id))

    link = estimate_approval_service.generate_public_link(token_value=token.token, base_url=request.url_root)
    flash(f"Link do akceptacji: {link}", "info")
    return redirect(url_for("services.details", estimate_id=estimate_id))


@bp.route("/<int:estimate_id>/approval/regenerate", methods=["POST"])
@login_required
def regenerate_link(estimate_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)
    try:
        estimate_approval_service.create_token(
            estimate_id=estimate_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
        )
    except EstimateApprovalNotFoundError as exc:
        abort(404, description=str(exc))

    flash("Wygenerowano nowy link akceptacji. Poprzedni link został unieważniony.", "success")
    return redirect(url_for("services.details", estimate_id=estimate_id))


@bp.route("/<int:estimate_id>/approval/revoke", methods=["POST"])
@login_required
def revoke_approval(estimate_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)
    is_admin = any((role.name or "").strip().lower() == "administrator" for role in getattr(current_user, "roles", []))

    try:
        estimate_approval_service.revoke_approval(
            estimate_id=estimate_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None) or 0,
            is_admin=is_admin,
        )
    except EstimateApprovalPermissionError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("services.details", estimate_id=estimate_id))
    except EstimateApprovalNotFoundError as exc:
        abort(404, description=str(exc))

    flash("Cofnięto akceptację kosztorysu.", "success")
    return redirect(url_for("services.details", estimate_id=estimate_id))


@bp.route("/<int:estimate_id>/clone", methods=["POST"])
@login_required
def clone(estimate_id: int):
    estimate = estimate_service.clone_for_revision(
        estimate_id=estimate_id,
        company_id=_company_id(),
        branch_id=_branch_id(),
        user_id=getattr(current_user, "id", None),
    )
    flash("Utworzono nową wersję kosztorysu.", "success")
    return redirect(url_for("services.details", estimate_id=estimate.id))


@bp.route("/<int:estimate_id>/pdf")
@login_required
def download_pdf(estimate_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    document = estimate_service.build_pdf(
        estimate_id=estimate_id,
        company_id=company_id,
        branch_id=_branch_id(),
        upload_root=_upload_root(),
    )
    if document is None:
        abort(404)

    return send_file(
        BytesIO(document.content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=document.filename,
    )
