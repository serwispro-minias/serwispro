from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import OperationalError

from app.customers.exceptions import CustomerAlreadyExistsError, CustomerValidationError
from app.customers.forms import CustomerForm
from app.customers.repository import CustomerRepository
from app.customers.services import CustomerService
from app.devices.exceptions import DeviceValidationError
from app.devices.forms import DeviceForm
from app.devices.repository import DeviceRepository
from app.devices.service import DeviceService
from app.inventory.exceptions import InventoryNotFoundError, InventoryValidationError
from app.inventory.service import InventoryService
from app.order_photos.forms import ServiceOrderPhotoDeleteForm, ServiceOrderPhotoFilterForm, ServiceOrderPhotoUploadForm
from app.order_photos.forms import PhotoAnnotationCreateForm, PhotoAnnotationDeleteForm, PhotoAnnotationUpdateForm
from app.order_photos.service import ServiceOrderPhotoService
from app.models.service_order import SERVICE_ORDER_PRIORITY_CHOICES, SERVICE_ORDER_STATUS_CHOICES
from app.notifications import CHANNEL_EMAIL, CHANNEL_SMS, NOTIFICATION_STATUS_LABELS, NotificationError, NotificationService
from app.services.forms import EstimateCreateForm
from app.services.service import estimate_service
from app.workflow.exceptions import WorkflowNotFoundError, WorkflowPermissionError, WorkflowValidationError
from app.workflow.service import WorkflowService

from . import bp
from .action_exceptions import ServiceOrderActionNotFoundError, ServiceOrderActionValidationError
from .action_repository import ServiceOrderActionRepository
from .action_service import ServiceOrderActionService
from .exceptions import ServiceOrderNotFoundError, ServiceOrderValidationError
from .forms import ORDER_TYPE_CHOICES, OrderActionForm, OrderForm, OrderItemForm, OrderItemMovementForm, OrderNotificationForm, OrderPartUsageForm, OrderSearchForm, OrderStatusChangeForm, TimelineEntryForm
from .item_service import ServiceOrderItemNotFoundError, ServiceOrderItemService, ServiceOrderItemValidationError
from .repository import ServiceOrderRepository
from .service import ServiceOrderService
from .print_service import ServiceOrderPrintService
from .timeline_exceptions import OrderTimelineNotFoundError, OrderTimelineValidationError
from .timeline_service import ServiceOrderTimelineService


service = ServiceOrderService(ServiceOrderRepository())
customer_service = CustomerService(CustomerRepository())
device_service = DeviceService(DeviceRepository())
timeline_service = ServiceOrderTimelineService()
action_service = ServiceOrderActionService(ServiceOrderActionRepository())
print_service = ServiceOrderPrintService()
inventory_service = InventoryService()
order_item_service = ServiceOrderItemService()
notification_service = NotificationService()
workflow_service = WorkflowService()
photo_service = ServiceOrderPhotoService()
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


def _populate_form_choices(form: OrderForm, *, company_id: int | None, customer_id: int | None = None) -> None:
    form.customer_id.choices = [(-1, "Wybierz klienta")] + service.get_customer_choices(company_id)
    form.device_id.choices = [(-1, "Wybierz urządzenie")]
    if customer_id:
        form.device_id.choices.extend(service.get_device_choices(company_id, customer_id))
    form.order_type.choices = ORDER_TYPE_CHOICES
    if company_id is not None and _ensure_workflow_seed(company_id=company_id, branch_id=_branch_id()):
        form.status.choices = workflow_service.get_status_choices(company_id=company_id, branch_id=_branch_id())
    else:
        form.status.choices = SERVICE_ORDER_STATUS_CHOICES
    form.priority.choices = SERVICE_ORDER_PRIORITY_CHOICES


def _status_form(choices: list[tuple[str, str]], *, can_force: bool) -> OrderStatusChangeForm:
    form = OrderStatusChangeForm()
    form.new_status.choices = list(choices)
    if not can_force:
        form.force_transition.render_kw = {"disabled": True}
    return form


def _timeline_form() -> TimelineEntryForm:
    form = TimelineEntryForm()
    form.entry_type.choices = timeline_service.get_type_choices()
    return form


def _action_form(company_id: int) -> OrderActionForm:
    form = OrderActionForm()
    form.technician_id.choices = action_service.get_technician_choices(company_id=company_id)
    form.action_type.choices = action_service.get_action_type_choices()
    return form


def _order_part_usage_form(company_id: int | None) -> tuple[OrderPartUsageForm, dict[int, str], dict[int, str]]:
    form = OrderPartUsageForm()
    parts_page = inventory_service.list_parts(page=1, per_page=1000, company_id=company_id, query_text=None)
    parts = parts_page["items"]
    form.part_id.choices = [(-1, "Wybierz część")] + [(part.id, f"{part.part_code} | {part.name}") for part in parts]
    part_price_map = {part.id: f"{part.sale_price_net:.2f}" for part in parts}
    part_vat_map = {part.id: f"{part.vat_rate:.2f}" for part in parts}
    return form, part_price_map, part_vat_map


def _order_item_form(company_id: int | None) -> OrderItemForm:
    form = OrderItemForm()
    form.item_type.choices = order_item_service.get_type_choices()
    form.quantity.data = form.quantity.data or 1
    return form


def _notification_form(draft_channel: str | None = None) -> OrderNotificationForm:
    form = OrderNotificationForm()
    if draft_channel:
        form.channel.data = draft_channel
    return form


def _photo_upload_form(default_type: str = "RECEPTION") -> ServiceOrderPhotoUploadForm:
    form = ServiceOrderPhotoUploadForm()
    form.photo_type.choices = photo_service.get_type_choices()
    form.photo_type.data = default_type
    return form


def _photo_filter_form(
    *,
    order_id: int,
    company_id: int,
    branch_id: int | None,
) -> ServiceOrderPhotoFilterForm:
    form = ServiceOrderPhotoFilterForm(request.args, meta={"csrf": False})
    form.photo_type.choices = [("", "Wszystkie")] + photo_service.get_type_choices()
    try:
        form.author_id.choices = photo_service.author_choices(order_id=order_id, company_id=company_id, branch_id=branch_id)
    except OperationalError:
        form.author_id.choices = [(-1, "Wszyscy autorzy")]
    form.author_id.data = request.args.get("author_id", type=int, default=-1)
    return form


def _parse_photo_ids_param(raw_value: str | None) -> list[int]:
    if not raw_value:
        return []
    values: list[int] = []
    for chunk in raw_value.split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            values.append(int(chunk))
    return values


def _parse_photo_render_mode(raw_value: str | None) -> str:
    value = (raw_value or "original").strip().lower()
    if value not in {"original", "annotated"}:
        return "original"
    return value


def _customer_label(customer) -> str:
    return (
        customer.full_name
        or customer.short_name
        or f"{(customer.first_name or '').strip()} {(customer.last_name or '').strip()}".strip()
        or f"Klient #{customer.id}"
    )


def _device_label(device) -> str:
    label_parts = [
        device.manufacturer or "-",
        device.model or "-",
        device.serial_number or "-",
    ]
    label = " / ".join(label_parts)
    if device.inventory_number:
        return f"{label} | INV: {device.inventory_number}"
    return label


def _populate_device_customer_choices(form: DeviceForm, company_id: int | None) -> None:
    form.customer_id.choices = device_service.get_customer_choices(company_id)


def _ensure_workflow_seed(*, company_id: int, branch_id: int | None) -> bool:
    try:
        workflow_service.ensure_default_workflow(
            company_id=company_id,
            branch_id=branch_id,
            user_id=getattr(current_user, "id", None),
        )
        return True
    except OperationalError:
        logger.warning("Workflow tables unavailable; fallback to static statuses.")
        return False


def _status_choices_for_scope(*, company_id: int | None, branch_id: int | None) -> list[tuple[str, str]]:
    if company_id is None:
        return list(SERVICE_ORDER_STATUS_CHOICES)
    if not _ensure_workflow_seed(company_id=company_id, branch_id=branch_id):
        return list(SERVICE_ORDER_STATUS_CHOICES)
    try:
        return workflow_service.get_status_choices(company_id=company_id, branch_id=branch_id)
    except OperationalError:
        return list(SERVICE_ORDER_STATUS_CHOICES)


def _status_labels_for_scope(*, company_id: int | None, branch_id: int | None) -> dict[str, str]:
    if company_id is None:
        return service.get_status_labels()
    try:
        return workflow_service.get_status_labels(company_id=company_id, branch_id=branch_id)
    except OperationalError:
        return service.get_status_labels()


def _status_badges_for_scope(*, company_id: int | None, branch_id: int | None) -> dict[str, str]:
    if company_id is None:
        return service.get_status_badge_classes()
    try:
        return workflow_service.get_status_badges(company_id=company_id, branch_id=branch_id)
    except OperationalError:
        return service.get_status_badge_classes()


def _current_user_role_names() -> set[str]:
    try:
        return {(role.name or "").strip().lower() for role in getattr(current_user, "roles", [])}
    except OperationalError:
        logger.warning("Role tables unavailable; assuming no elevated roles.")
        return set()


@bp.route("/")
@login_required
def index():
    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is not None:
        _ensure_workflow_seed(company_id=company_id, branch_id=branch_id)
    status = request.args.get("status") or None
    raw_customer_id = request.args.get("customer_id", type=int)
    customer_id = raw_customer_id if raw_customer_id and raw_customer_id > 0 else None
    order_number = (request.args.get("order_number") or "").strip() or None
    device_serial_number = (request.args.get("device_serial_number") or "").strip() or None
    query = (request.args.get("q") or "").strip()
    sort_by = (request.args.get("sort_by") or "date").strip().lower()
    sort_dir = (request.args.get("sort_dir") or "desc").strip().lower()
    page = request.args.get("page", type=int) or 1

    logger.debug(
        "Orders.index params: status=%r customer_id=%s order_number=%r device_serial_number=%r q=%r sort_by=%s sort_dir=%s page=%s",
        status,
        customer_id,
        order_number,
        device_serial_number,
        query,
        sort_by,
        sort_dir,
        page,
    )

    search_form = OrderSearchForm(request.args, meta={"csrf": False})
    search_form.customer_id.choices = [(0, "Wszyscy klienci")] + service.get_customer_choices(company_id)
    dynamic_statuses = _status_choices_for_scope(company_id=company_id, branch_id=branch_id)
    search_form.status.choices = [("", "Wszystkie statusy")] + dynamic_statuses
    search_form.sort_by.choices = [
        ("number", "Numer zlecenia"),
        ("date", "Data przyjęcia"),
        ("customer", "Klient"),
        ("status", "Status"),
    ]
    search_form.sort_dir.choices = [
        ("asc", "Rosnąco"),
        ("desc", "Malejąco"),
    ]
    search_form.status.data = status or ""
    search_form.customer_id.data = customer_id or 0
    search_form.order_number.data = order_number or ""
    search_form.device_serial_number.data = device_serial_number or ""
    search_form.sort_by.data = sort_by
    search_form.sort_dir.data = sort_dir

    orders = service.list_service_orders(
        page=page,
        company_id=company_id,
        status=status,
        customer_id=customer_id,
        order_number=order_number,
        device_serial_number=device_serial_number,
        query=query or None,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    return render_template(
        "orders/index.html",
        orders=orders,
        query=query,
        search_form=search_form,
        status=status,
        customer_id=customer_id or 0,
        order_number=order_number or "",
        device_serial_number=device_serial_number or "",
        sort_by=sort_by,
        sort_dir=sort_dir,
        status_labels=_status_labels_for_scope(company_id=company_id, branch_id=branch_id),
        status_badges=_status_badges_for_scope(company_id=company_id, branch_id=branch_id),
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = OrderForm()
    company_id = _company_id()
    customer_id = request.form.get("customer_id", type=int) if request.method == "POST" else request.args.get("customer_id", type=int)
    _populate_form_choices(form, company_id=company_id, customer_id=customer_id)

    if form.validate_on_submit():
        try:
            payload = dict(form.data)
            payload["warranty_repair"] = form.order_type.data == "WARRANTY"
            payload["created_by"] = getattr(current_user, "id", None)
            service_order = service.create_service_order(payload, company_id=company_id, branch_id=_branch_id())
        except ServiceOrderValidationError as exc:
            flash(str(exc), "danger")
        else:
            flash("Zlecenie zostało utworzone.", "success")
            return redirect(url_for("orders.details", order_id=service_order.id))

    has_devices = service.has_customer_devices(company_id, customer_id)
    return render_template(
        "orders/form.html",
        form=form,
        title="Nowe zlecenie",
        has_devices=has_devices,
        selected_customer_id=customer_id,
        timeline_form=None,
        timeline_entries=[],
        timeline_type_labels=timeline_service.get_type_labels(),
    )


@bp.route("/<int:order_id>")
@login_required
def details(order_id: int):
    company_id = _company_id()
    branch_id = _branch_id()
    workflow_available = False
    if company_id is not None:
        workflow_available = _ensure_workflow_seed(company_id=company_id, branch_id=branch_id)

    service_order = service.get_service_order(order_id, company_id=company_id)
    if service_order is None:
        abort(404)

    is_admin = "administrator" in _current_user_role_names()
    available_transitions = (
        workflow_service.get_available_transitions(
            order=service_order,
            company_id=company_id,
            branch_id=branch_id,
            actor=current_user,
        )
        if company_id is not None and workflow_available
        else []
    )
    transition_choices = [
        (str(row["to_status"]), f"{row['name']} -> {row['to_name']}")
        for row in available_transitions
        if bool(row["allowed"])
    ]
    if not transition_choices:
        transition_choices = _status_choices_for_scope(company_id=company_id, branch_id=branch_id)

    status_form = _status_form(transition_choices, can_force=is_admin)
    if any(value == service_order.status for value, _ in status_form.new_status.choices):
        status_form.new_status.data = service_order.status
    elif status_form.new_status.choices:
        status_form.new_status.data = status_form.new_status.choices[0][0]
    item_form = _order_item_form(_company_id())
    try:
        items = order_item_service.list_items(order_id=order_id, company_id=_company_id(), branch_id=_branch_id())
    except OperationalError:
        items = []
    item_totals = order_item_service.compute_totals(items)
    csrf_token_value = generate_csrf()
    history = service.get_status_history(order_id, company_id)
    communication_history = notification_service.list_messages_for_order(
        order_id=order_id,
        company_id=company_id,
        branch_id=branch_id,
    )
    actions = action_service.list_actions(
        order_id=order_id,
        company_id=company_id,
        branch_id=branch_id,
    )
    try:
        estimates = estimate_service.list_estimates_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
    except OperationalError:
        estimates = []

    photo_filter_form = _photo_filter_form(order_id=order_id, company_id=company_id, branch_id=branch_id) if company_id is not None else ServiceOrderPhotoFilterForm(meta={"csrf": False})
    photo_upload_form = _photo_upload_form(default_type="RECEPTION")
    photo_delete_form = ServiceOrderPhotoDeleteForm()
    annotation_create_form = PhotoAnnotationCreateForm()
    annotation_update_form = PhotoAnnotationUpdateForm()
    annotation_delete_form = PhotoAnnotationDeleteForm()
    try:
        photos = photo_service.list_photos(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            photo_type=(photo_filter_form.photo_type.data or None),
            date_from=photo_filter_form.date_from.data,
            date_to=photo_filter_form.date_to.data,
            author_id=photo_filter_form.author_id.data,
        ) if company_id is not None else []
    except OperationalError:
        photos = []

    return render_template(
        "orders/details.html",
        order=service_order,
        status_form=status_form,
        status_history=history,
        communication_history=communication_history,
        communication_status_labels=NOTIFICATION_STATUS_LABELS,
        channel_email=CHANNEL_EMAIL,
        channel_sms=CHANNEL_SMS,
        actions=actions,
        action_type_labels=action_service.get_action_type_labels(),
        status_labels=_status_labels_for_scope(company_id=company_id, branch_id=branch_id),
        status_badges=_status_badges_for_scope(company_id=company_id, branch_id=branch_id),
        workflow_transitions=available_transitions,
        is_admin=is_admin,
        item_form=item_form,
        order_items=items,
        order_item_totals=item_totals,
        item_type_labels=order_item_service.get_type_labels(),
        csrf_token_value=csrf_token_value,
        estimate_create_form=EstimateCreateForm(),
        estimates=estimates,
        estimate_status_labels=estimate_service.get_status_labels(),
        photos=photos,
        photo_type_labels=photo_service.get_type_labels(),
        photo_filter_form=photo_filter_form,
        photo_upload_form=photo_upload_form,
        photo_delete_form=photo_delete_form,
        type_labels=photo_service.get_type_labels(),
        filter_form=photo_filter_form,
        upload_form=photo_upload_form,
        delete_form=photo_delete_form,
        annotation_type_choices=photo_service.get_annotation_type_choices(),
        annotation_priority_choices=photo_service.get_annotation_priority_choices(),
        annotation_create_form=annotation_create_form,
        annotation_update_form=annotation_update_form,
        annotation_delete_form=annotation_delete_form,
    )


def _send_protocol_pdf(*, content: bytes, filename: str, as_attachment: bool):
    return send_file(
        BytesIO(content),
        mimetype="application/pdf",
        as_attachment=as_attachment,
        download_name=filename,
    )


@bp.route("/<int:order_id>/print/intake")
@login_required
def print_intake_protocol(order_id: int):
    """Generate printable intake protocol PDF."""

    company_id = _company_id()
    if company_id is None:
        abort(404)

    document = print_service.build_intake_protocol(
        order_id=order_id,
        company_id=company_id,
        branch_id=_branch_id(),
        upload_root=_upload_root(),
        selected_photo_ids=_parse_photo_ids_param(request.args.get("photo_ids")),
        photo_render_mode=_parse_photo_render_mode(request.args.get("photo_render_mode")),
    )
    if document is None:
        abort(404)

    mode = (request.args.get("mode") or "inline").strip().lower()
    return _send_protocol_pdf(content=document.content, filename=document.filename, as_attachment=(mode == "download"))


@bp.route("/<int:order_id>/print/release")
@login_required
def print_release_protocol(order_id: int):
    """Generate printable release protocol PDF."""

    company_id = _company_id()
    if company_id is None:
        abort(404)

    document = print_service.build_release_protocol(
        order_id=order_id,
        company_id=company_id,
        branch_id=_branch_id(),
        upload_root=_upload_root(),
        selected_photo_ids=_parse_photo_ids_param(request.args.get("photo_ids")),
        photo_render_mode=_parse_photo_render_mode(request.args.get("photo_render_mode")),
    )
    if document is None:
        abort(404)

    mode = (request.args.get("mode") or "inline").strip().lower()
    return _send_protocol_pdf(content=document.content, filename=document.filename, as_attachment=(mode == "download"))


@bp.route("/<int:order_id>/print/preview")
@login_required
def print_protocol_preview(order_id: int):
    """Preview one selected protocol as inline PDF in a new tab."""

    protocol_kind = (request.args.get("protocol") or "intake").strip().lower()
    if protocol_kind == "release":
        return redirect(url_for("orders.print_release_protocol", order_id=order_id, mode="inline"))
    return redirect(url_for("orders.print_intake_protocol", order_id=order_id, mode="inline"))


@bp.route("/<int:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit(order_id: int):
    company_id = _company_id()
    service_order = service.get_service_order(order_id, company_id=company_id)
    if service_order is None:
        abort(404)

    form = OrderForm(obj=service_order)
    customer_id = request.form.get("customer_id", type=int) if request.method == "POST" else service_order.customer_id
    _populate_form_choices(form, company_id=company_id, customer_id=customer_id)

    if request.method == "GET":
        form.customer_id.data = service_order.customer_id
        form.device_id.data = service_order.device_id
        form.order_type.data = "WARRANTY" if service_order.warranty_repair else "STANDARD"
        form.status.data = service_order.status
        form.priority.data = service_order.priority

    if form.validate_on_submit():
        try:
            payload = dict(form.data)
            payload["warranty_repair"] = form.order_type.data == "WARRANTY"
            payload["updated_by"] = getattr(current_user, "id", None)
            service_order = service.update_service_order(order_id, payload, company_id=company_id, branch_id=_branch_id())
        except ServiceOrderNotFoundError:
            abort(404)
        except ServiceOrderValidationError as exc:
            flash(str(exc), "danger")
        else:
            flash("Zlecenie zostało zaktualizowane.", "success")
            return redirect(url_for("orders.details", order_id=service_order.id))

    has_devices = service.has_customer_devices(company_id, customer_id)
    timeline_form = _timeline_form()
    part_usage_form, part_price_map, part_vat_map = _order_part_usage_form(company_id)
    timeline_entries = timeline_service.list_entries(
        order_id=order_id,
        company_id=company_id,
        branch_id=_branch_id(),
    )
    part_usages = inventory_service.list_order_usages(order_id=order_id, company_id=company_id, branch_id=_branch_id())
    part_usage_totals = inventory_service.compute_order_usage_totals(part_usages)

    return render_template(
        "orders/form.html",
        form=form,
        title="Edytuj zlecenie",
        order=service_order,
        has_devices=has_devices,
        selected_customer_id=customer_id,
        timeline_form=timeline_form,
        timeline_entries=timeline_entries,
        part_usage_form=part_usage_form,
        part_usages=part_usages,
        part_usage_totals=part_usage_totals,
        part_price_map=part_price_map,
        part_vat_map=part_vat_map,
        timeline_type_labels=timeline_service.get_type_labels(),
    )


@bp.route("/<int:order_id>/delete", methods=["POST"])
@login_required
def delete(order_id: int):
    try:
        service.delete_service_order(order_id, company_id=_company_id())
    except ServiceOrderNotFoundError:
        abort(404)
    flash("Zlecenie zostało usunięte.", "success")
    return redirect(url_for("orders.index"))


@bp.route("/<int:order_id>/status", methods=["POST"])
@login_required
def change_status(order_id: int):
    """Handle service order status transitions."""

    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is None:
        abort(404)

    if not _ensure_workflow_seed(company_id=company_id, branch_id=branch_id):
        flash("Moduł workflow nie jest dostępny dla bieżącego schematu bazy.", "danger")
        return redirect(url_for("orders.details", order_id=order_id))

    is_admin = "administrator" in _current_user_role_names()
    form = _status_form(
        _status_choices_for_scope(company_id=company_id, branch_id=branch_id),
        can_force=is_admin,
    )
    if not form.validate_on_submit():
        flash("Nie udało się zmienić statusu. Sprawdź formularz.", "danger")
        return redirect(url_for("orders.details", order_id=order_id))

    try:
        result = workflow_service.change_order_status(
            order_id=order_id,
            target_status_code=form.new_status.data,
            company_id=company_id,
            branch_id=branch_id,
            actor=current_user,
            note=form.note.data,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            force=bool(form.force_transition.data),
        )
    except (ServiceOrderNotFoundError, WorkflowNotFoundError):
        abort(404)
    except (ServiceOrderValidationError, WorkflowValidationError, WorkflowPermissionError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Status zlecenia został zaktualizowany.", "success")
        if result.sent_channels:
            flash(f"Automatycznie wysłano powiadomienia: {', '.join(result.sent_channels)}.", "info")

        if not result.sent_channels:
            drafts = notification_service.draft_for_status_change(
                order_id=order_id,
                new_status=result.order.status,
                company_id=company_id,
                branch_id=branch_id,
            )
            if drafts:
                flash("Dostępna jest propozycja automatycznego powiadomienia klienta.", "info")
                return redirect(url_for("orders.communication_proposal", order_id=order_id, status=result.order.status))

    return redirect(url_for("orders.details", order_id=order_id))


@bp.route("/<int:order_id>/communication/proposal", methods=["GET", "POST"])
@login_required
def communication_proposal(order_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    status_value = (request.args.get("status") or request.form.get("status") or "").strip().upper()
    drafts = notification_service.draft_for_status_change(
        order_id=order_id,
        new_status=status_value,
        company_id=company_id,
        branch_id=_branch_id(),
    )
    if not drafts:
        flash("Brak dostępnych automatycznych powiadomień dla wybranego statusu.", "warning")
        return redirect(url_for("orders.details", order_id=order_id))

    preferred_channel = (request.args.get("channel") or request.form.get("channel") or drafts[0].channel).upper()
    draft = next((item for item in drafts if item.channel == preferred_channel), drafts[0])
    form = _notification_form(draft.channel)

    if request.method == "GET":
        form.channel.data = draft.channel
        form.recipient.data = draft.recipient
        form.subject.data = draft.subject or ""
        form.content.data = draft.content
        form.event_key.data = draft.event_key or ""
        form.template_id.data = str(draft.template_id or "")

    if form.validate_on_submit():
        action = request.form.get("action") or "send"
        template_id = int(form.template_id.data) if (form.template_id.data or "").strip().isdigit() else None

        if action == "cancel":
            notification_service.cancel_draft(
                order_id=order_id,
                company_id=company_id,
                branch_id=_branch_id(),
                user_id=getattr(current_user, "id", None),
                channel=form.channel.data,
                recipient=form.recipient.data,
                subject=form.subject.data,
                content=form.content.data,
                event_key=form.event_key.data or None,
                template_id=template_id,
            )
            flash("Wysyłka została anulowana i zapisana w historii komunikacji.", "warning")
            return redirect(url_for("orders.details", order_id=order_id))

        message = notification_service.send_draft(
            order_id=order_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            channel=form.channel.data,
            recipient=form.recipient.data,
            subject=form.subject.data,
            content=form.content.data,
            event_key=form.event_key.data or None,
            template_id=template_id,
        )
        if message.status == "SENT":
            flash("Powiadomienie zostało wysłane.", "success")
        else:
            flash("Nie udało się wysłać powiadomienia. Sprawdź historię komunikacji.", "danger")
        return redirect(url_for("orders.details", order_id=order_id))

    return render_template(
        "orders/communication_proposal.html",
        order_id=order_id,
        form=form,
        status_value=status_value,
        drafts=drafts,
    )


@bp.route("/<int:order_id>/communication/compose", methods=["GET", "POST"])
@login_required
def compose_communication(order_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    channel = (request.args.get("channel") or request.form.get("channel") or CHANNEL_EMAIL).upper()
    if channel not in {CHANNEL_EMAIL, CHANNEL_SMS}:
        channel = CHANNEL_EMAIL

    try:
        draft = notification_service.draft_manual(
            order_id=order_id,
            company_id=company_id,
            branch_id=_branch_id(),
            channel=channel,
        )
    except NotificationError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("orders.details", order_id=order_id))

    form = _notification_form(draft.channel)
    if request.method == "GET":
        form.channel.data = draft.channel
        form.recipient.data = draft.recipient
        form.subject.data = draft.subject or ""
        form.content.data = draft.content
        form.event_key.data = draft.event_key or ""
        form.template_id.data = str(draft.template_id or "")

    if form.validate_on_submit():
        action = request.form.get("action") or "send"
        template_id = int(form.template_id.data) if (form.template_id.data or "").strip().isdigit() else None

        if action == "cancel":
            notification_service.cancel_draft(
                order_id=order_id,
                company_id=company_id,
                branch_id=_branch_id(),
                user_id=getattr(current_user, "id", None),
                channel=form.channel.data,
                recipient=form.recipient.data,
                subject=form.subject.data,
                content=form.content.data,
                event_key=form.event_key.data or None,
                template_id=template_id,
            )
            flash("Wysyłka została anulowana i zapisana w historii komunikacji.", "warning")
            return redirect(url_for("orders.details", order_id=order_id, tab="communication"))

        message = notification_service.send_draft(
            order_id=order_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            channel=form.channel.data,
            recipient=form.recipient.data,
            subject=form.subject.data,
            content=form.content.data,
            event_key=form.event_key.data or None,
            template_id=template_id,
        )
        if message.status == "SENT":
            flash("Powiadomienie zostało wysłane.", "success")
        else:
            flash("Nie udało się wysłać powiadomienia. Sprawdź historię komunikacji.", "danger")
        return redirect(url_for("orders.details", order_id=order_id, tab="communication"))

    return render_template(
        "orders/communication_proposal.html",
        order_id=order_id,
        form=form,
        status_value="",
        drafts=[draft],
    )


@bp.route("/<int:order_id>/communication/<int:message_id>/resend", methods=["POST"])
@login_required
def resend_communication(order_id: int, message_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        message = notification_service.resend_message(
            order_id=order_id,
            message_id=message_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
        )
    except NotificationError as exc:
        flash(str(exc), "danger")
    else:
        if message.status == "SENT":
            flash("Wiadomość została wysłana ponownie.", "success")
        else:
            flash("Ponowna wysyłka zakończyła się błędem.", "danger")

    return redirect(url_for("orders.details", order_id=order_id, tab="communication"))


@bp.route("/<int:order_id>/timeline", methods=["POST"])
@login_required
def add_timeline_entry(order_id: int):
    """Create one timeline entry for the selected service order via AJAX."""

    company_id = _company_id()
    if company_id is None:
        return jsonify({"ok": False, "message": "Brak identyfikatora firmy."}), 400

    form = _timeline_form()
    if not form.validate_on_submit():
        form_html = render_template(
            "orders/partials/timeline_entry_form.html",
            timeline_form=form,
            order={"id": order_id},
        )
        return jsonify({"ok": False, "form_html": form_html}), 400

    try:
        entry = timeline_service.create_entry(
            order_id=order_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            entry_type=form.entry_type.data,
            description=form.description.data,
            parts_cost_raw=request.form.get("parts_cost"),
            labor_minutes_raw=request.form.get("labor_minutes"),
            attachments=request.files.getlist("attachments"),
            upload_root=_upload_root(),
        )
    except OrderTimelineNotFoundError:
        abort(404)
    except OrderTimelineValidationError as exc:
        form.description.errors.append(str(exc))
        form_html = render_template(
            "orders/partials/timeline_entry_form.html",
            timeline_form=form,
            order={"id": order_id},
        )
        return jsonify({"ok": False, "form_html": form_html}), 400

    entry_html = render_template(
        "orders/partials/timeline_entry_item.html",
        entry=entry,
        timeline_type_labels=timeline_service.get_type_labels(),
    )
    refreshed_form = _timeline_form()
    form_html = render_template(
        "orders/partials/timeline_entry_form.html",
        timeline_form=refreshed_form,
        order={"id": order_id},
    )

    return jsonify({"ok": True, "entry_html": entry_html, "form_html": form_html})


@bp.route("/<int:order_id>/actions/new", methods=["GET", "POST"])
@login_required
def create_action(order_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = _action_form(company_id)
    if request.method == "GET":
        form.is_visible_for_customer.data = "1"

    if form.validate_on_submit():
        try:
            action_service.create_action(
                order_id=order_id,
                company_id=company_id,
                branch_id=_branch_id(),
                user_id=getattr(current_user, "id", None),
                data={
                    "action_date": form.action_date.data,
                    "technician_id": form.technician_id.data,
                    "action_type": form.action_type.data,
                    "description": form.description.data,
                    "work_time_minutes": form.work_time_minutes.data,
                    "cost": form.cost.data,
                    "is_visible_for_customer": form.is_visible_for_customer.data == "1",
                },
            )
        except ServiceOrderActionValidationError as exc:
            flash(str(exc), "danger")
        except ServiceOrderActionNotFoundError:
            abort(404)
        else:
            flash("Dodano wpis historii napraw.", "success")
            return redirect(url_for("orders.details", order_id=order_id))

    return render_template(
        "orders/action_form.html",
        title="Dodaj wpis historii napraw",
        form=form,
        order_id=order_id,
        action=None,
    )


@bp.route("/<int:order_id>/actions/<int:action_id>/edit", methods=["GET", "POST"])
@login_required
def edit_action(order_id: int, action_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        action = action_service.get_action(
            action_id=action_id,
            order_id=order_id,
            company_id=company_id,
            branch_id=_branch_id(),
        )
    except ServiceOrderActionNotFoundError:
        abort(404)
    except ServiceOrderActionValidationError:
        abort(403)

    form = _action_form(company_id)
    if request.method == "GET":
        form.action_date.data = action.action_date
        form.technician_id.data = action.technician_id or 0
        form.action_type.data = action.action_type
        form.description.data = action.description
        form.work_time_minutes.data = action.work_time_minutes
        form.cost.data = action.cost
        form.is_visible_for_customer.data = "1" if action.is_visible_for_customer else "0"

    if form.validate_on_submit():
        try:
            action_service.update_action(
                action_id=action_id,
                order_id=order_id,
                company_id=company_id,
                branch_id=_branch_id(),
                user_id=getattr(current_user, "id", None),
                data={
                    "action_date": form.action_date.data,
                    "technician_id": form.technician_id.data,
                    "action_type": form.action_type.data,
                    "description": form.description.data,
                    "work_time_minutes": form.work_time_minutes.data,
                    "cost": form.cost.data,
                    "is_visible_for_customer": form.is_visible_for_customer.data == "1",
                },
            )
        except ServiceOrderActionValidationError as exc:
            flash(str(exc), "danger")
        except ServiceOrderActionNotFoundError:
            abort(404)
        else:
            flash("Zaktualizowano wpis historii napraw.", "success")
            return redirect(url_for("orders.details", order_id=order_id))

    return render_template(
        "orders/action_form.html",
        title="Edytuj wpis historii napraw",
        form=form,
        order_id=order_id,
        action=action,
    )


@bp.route("/<int:order_id>/actions/<int:action_id>/delete", methods=["POST"])
@login_required
def delete_action(order_id: int, action_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        action_service.delete_action(
            action_id=action_id,
            order_id=order_id,
            company_id=company_id,
            branch_id=_branch_id(),
        )
    except ServiceOrderActionNotFoundError:
        abort(404)
    except ServiceOrderActionValidationError:
        abort(403)

    flash("Usunięto wpis historii napraw.", "success")
    return redirect(url_for("orders.details", order_id=order_id))


@bp.route("/<int:order_id>/parts/consume", methods=["POST"])
@login_required
def add_order_part_usage(order_id: int):
    company_id = _company_id()
    if company_id is None:
        return jsonify({"ok": False, "message": "Brak identyfikatora firmy."}), 400

    part_form, part_price_map, part_vat_map = _order_part_usage_form(company_id)
    if not part_form.validate_on_submit():
        form_html = render_template(
            "orders/partials/order_part_usage_form.html",
            order={"id": order_id},
            part_usage_form=part_form,
            part_price_map=part_price_map,
            part_vat_map=part_vat_map,
        )
        return jsonify({"ok": False, "form_html": form_html}), 400

    try:
        inventory_service.consume_for_order(
            order_id=order_id,
            part_id=part_form.part_id.data,
            quantity_raw=part_form.quantity.data,
            unit_net_price_raw=part_form.unit_net_price.data,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
        )
    except (InventoryValidationError, InventoryNotFoundError) as exc:
        part_form.quantity.errors.append(str(exc))
        form_html = render_template(
            "orders/partials/order_part_usage_form.html",
            order={"id": order_id},
            part_usage_form=part_form,
            part_price_map=part_price_map,
            part_vat_map=part_vat_map,
        )
        return jsonify({"ok": False, "form_html": form_html}), 400

    refreshed_form, part_price_map, part_vat_map = _order_part_usage_form(company_id)
    usages = inventory_service.list_order_usages(order_id=order_id, company_id=company_id, branch_id=_branch_id())
    totals = inventory_service.compute_order_usage_totals(usages)

    form_html = render_template(
        "orders/partials/order_part_usage_form.html",
        order={"id": order_id},
        part_usage_form=refreshed_form,
        part_price_map=part_price_map,
        part_vat_map=part_vat_map,
    )
    list_html = render_template(
        "orders/partials/order_part_usage_table.html",
        part_usages=usages,
        part_usage_totals=totals,
    )
    return jsonify({"ok": True, "form_html": form_html, "list_html": list_html})


@bp.route("/<int:order_id>/items/search")
@login_required
def search_order_items(order_id: int):
    company_id = _company_id()
    if company_id is None:
        return jsonify({"ok": False, "message": "Brak identyfikatora firmy."}), 400

    query_text = request.args.get("q")
    items = order_item_service.search_catalog_items(query_text=query_text, company_id=company_id)
    return jsonify({"ok": True, "items": items})


@bp.route("/<int:order_id>/items", methods=["POST"])
@login_required
def add_order_item(order_id: int):
    company_id = _company_id()
    if company_id is None:
        return jsonify({"ok": False, "message": "Brak identyfikatora firmy."}), 400

    form = _order_item_form(company_id)
    if not form.validate_on_submit():
        form_html = render_template(
            "orders/partials/order_item_form.html",
            order={"id": order_id},
            item_form=form,
        )
        return jsonify({"ok": False, "form_html": form_html}), 400

    try:
        order_item_service.add_item(
            order_id=order_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            item_type=form.item_type.data,
            item_id=int(form.item_id.data),
            quantity_raw=form.quantity.data,
            unit_price_net_raw=form.unit_price_net.data,
            discount_percent_raw=form.discount_percent.data,
            notes=form.notes.data,
        )
    except (ServiceOrderItemNotFoundError, ServiceOrderItemValidationError) as exc:
        form.item_id.errors.append(str(exc))
        form_html = render_template(
            "orders/partials/order_item_form.html",
            order={"id": order_id},
            item_form=form,
        )
        return jsonify({"ok": False, "form_html": form_html}), 400

    refreshed_form = _order_item_form(company_id)
    items = order_item_service.list_items(order_id=order_id, company_id=company_id, branch_id=_branch_id())
    totals = order_item_service.compute_totals(items)
    return jsonify(
        {
            "ok": True,
            "form_html": render_template("orders/partials/order_item_form.html", order={"id": order_id}, item_form=refreshed_form),
            "list_html": render_template(
                "orders/partials/order_item_table.html",
                order_items=items,
                order_item_totals=totals,
                item_type_labels=order_item_service.get_type_labels(),
                csrf_token_value=generate_csrf(),
            ),
            "summary_html": render_template(
                "orders/partials/order_item_summary.html",
                order_item_totals=totals,
            ),
        }
    )


@bp.route("/<int:order_id>/items/<int:item_id>/use", methods=["POST"])
@login_required
def use_order_item(order_id: int, item_id: int):
    company_id = _company_id()
    if company_id is None:
        return jsonify({"ok": False, "message": "Brak identyfikatora firmy."}), 400

    form = OrderItemMovementForm()
    form.item_id.data = str(item_id)
    if not form.validate_on_submit():
        return jsonify({"ok": False, "message": "Nieprawidłowe dane formularza."}), 400

    try:
        order_item_service.mark_used(
            order_id=order_id,
            item_id=item_id,
            quantity_raw=form.quantity.data,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
        )
    except (ServiceOrderItemNotFoundError, ServiceOrderItemValidationError) as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    items = order_item_service.list_items(order_id=order_id, company_id=company_id, branch_id=_branch_id())
    totals = order_item_service.compute_totals(items)
    return jsonify(
        {
            "ok": True,
            "list_html": render_template(
                "orders/partials/order_item_table.html",
                order_items=items,
                order_item_totals=totals,
                item_type_labels=order_item_service.get_type_labels(),
                csrf_token_value=generate_csrf(),
            ),
            "summary_html": render_template(
                "orders/partials/order_item_summary.html",
                order_item_totals=totals,
            ),
        }
    )


@bp.route("/<int:order_id>/items/<int:item_id>/return", methods=["POST"])
@login_required
def return_order_item(order_id: int, item_id: int):
    company_id = _company_id()
    if company_id is None:
        return jsonify({"ok": False, "message": "Brak identyfikatora firmy."}), 400

    form = OrderItemMovementForm()
    form.item_id.data = str(item_id)
    if not form.validate_on_submit():
        return jsonify({"ok": False, "message": "Nieprawidłowe dane formularza."}), 400

    try:
        order_item_service.return_item(
            order_id=order_id,
            item_id=item_id,
            quantity_raw=form.quantity.data,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
        )
    except (ServiceOrderItemNotFoundError, ServiceOrderItemValidationError) as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    items = order_item_service.list_items(order_id=order_id, company_id=company_id, branch_id=_branch_id())
    totals = order_item_service.compute_totals(items)
    return jsonify(
        {
            "ok": True,
            "list_html": render_template(
                "orders/partials/order_item_table.html",
                order_items=items,
                order_item_totals=totals,
                item_type_labels=order_item_service.get_type_labels(),
                csrf_token_value=generate_csrf(),
            ),
            "summary_html": render_template(
                "orders/partials/order_item_summary.html",
                order_item_totals=totals,
            ),
        }
    )


@bp.route("/<int:order_id>/timeline/attachments/<int:attachment_id>")
@login_required
def download_timeline_attachment(order_id: int, attachment_id: int):
    """Download one timeline attachment for a service order."""

    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        attachment = timeline_service.get_attachment(
            order_id=order_id,
            attachment_id=attachment_id,
            company_id=company_id,
            branch_id=_branch_id(),
        )
        full_path = timeline_service.resolve_attachment_path(_upload_root(), attachment)
    except OrderTimelineNotFoundError:
        abort(404)
    except OrderTimelineValidationError:
        abort(403)

    return send_file(
        full_path,
        mimetype=attachment.content_type or "application/octet-stream",
        as_attachment=False,
        download_name=attachment.original_filename,
    )


@bp.route("/devices/by-customer")
@login_required
def devices_by_customer():
    """Return active customer devices for dependent select field."""

    company_id = _company_id()
    customer_id = request.args.get("customer_id", type=int)
    choices = service.get_device_choices(company_id, customer_id)
    return jsonify(
        {
            "devices": [{"id": device_id, "label": label} for device_id, label in choices],
            "has_devices": len(choices) > 0,
        }
    )


@bp.route("/customers/options")
@login_required
def customer_options():
    """Return active customers for select refresh in order form."""

    choices = service.get_customer_choices(_company_id())
    return jsonify({"customers": [{"id": customer_id, "label": label} for customer_id, label in choices]})


@bp.route("/modal/customers/new", methods=["GET", "POST"])
@login_required
def modal_create_customer():
    """Create customer inside modal and return JSON response."""

    company_id = _company_id()
    form = CustomerForm(meta={"csrf": False})

    if request.method == "POST":
        if form.validate_on_submit():
            try:
                customer = customer_service.create_customer(form.data, company_id=company_id)
            except (CustomerValidationError, CustomerAlreadyExistsError) as exc:
                form.customer_type.errors.append(str(exc))
            else:
                return jsonify(
                    {
                        "ok": True,
                        "customer": {
                            "id": customer.id,
                            "label": _customer_label(customer),
                        },
                    }
                )

        html = render_template(
            "orders/partials/customer_modal_form.html",
            form=form,
            modal_title="Nowy klient",
            action_url=url_for("orders.modal_create_customer"),
        )
        return jsonify({"ok": False, "html": html}), 400

    return render_template(
        "orders/partials/customer_modal_form.html",
        form=form,
        modal_title="Nowy klient",
        action_url=url_for("orders.modal_create_customer"),
    )


@bp.route("/modal/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def modal_edit_customer(customer_id: int):
    """Edit customer inside modal and return JSON response."""

    company_id = _company_id()
    customer = customer_service.get_customer(customer_id, company_id=company_id)
    if customer is None:
        abort(404)

    form = CustomerForm(obj=customer, meta={"csrf": False})

    if request.method == "POST":
        if form.validate_on_submit():
            try:
                customer = customer_service.update_customer(customer_id, form.data, company_id=company_id)
            except (CustomerValidationError, CustomerAlreadyExistsError) as exc:
                form.customer_type.errors.append(str(exc))
            else:
                return jsonify(
                    {
                        "ok": True,
                        "customer": {
                            "id": customer.id,
                            "label": _customer_label(customer),
                        },
                    }
                )

        html = render_template(
            "orders/partials/customer_modal_form.html",
            form=form,
            modal_title="Edytuj klienta",
            action_url=url_for("orders.modal_edit_customer", customer_id=customer_id),
        )
        return jsonify({"ok": False, "html": html}), 400

    return render_template(
        "orders/partials/customer_modal_form.html",
        form=form,
        modal_title="Edytuj klienta",
        action_url=url_for("orders.modal_edit_customer", customer_id=customer_id),
    )


@bp.route("/modal/devices/new", methods=["GET", "POST"])
@login_required
def modal_create_device():
    """Create device inside modal and return JSON response."""

    company_id = _company_id()
    initial_customer_id = request.args.get("customer_id", type=int)
    form = DeviceForm(meta={"csrf": False})
    _populate_device_customer_choices(form, company_id)

    if request.method == "GET" and initial_customer_id:
        valid_customer_ids = {item[0] for item in form.customer_id.choices}
        if initial_customer_id in valid_customer_ids:
            form.customer_id.data = initial_customer_id

    if request.method == "POST":
        if form.validate_on_submit():
            try:
                device = device_service.create_device(form.data, company_id=company_id)
            except DeviceValidationError as exc:
                form.customer_id.errors.append(str(exc))
            else:
                return jsonify(
                    {
                        "ok": True,
                        "device": {
                            "id": device.id,
                            "customer_id": device.customer_id,
                            "label": _device_label(device),
                        },
                    }
                )

        html = render_template(
            "orders/partials/device_modal_form.html",
            form=form,
            modal_title="Nowe urządzenie",
            action_url=url_for("orders.modal_create_device", customer_id=form.customer_id.data or ""),
        )
        return jsonify({"ok": False, "html": html}), 400

    return render_template(
        "orders/partials/device_modal_form.html",
        form=form,
        modal_title="Nowe urządzenie",
        action_url=url_for("orders.modal_create_device", customer_id=initial_customer_id or ""),
    )


@bp.route("/modal/devices/<int:device_id>/edit", methods=["GET", "POST"])
@login_required
def modal_edit_device(device_id: int):
    """Edit device inside modal and return JSON response."""

    company_id = _company_id()
    device = device_service.get_device(device_id, company_id=company_id)
    if device is None:
        abort(404)

    form = DeviceForm(obj=device, meta={"csrf": False})
    _populate_device_customer_choices(form, company_id)

    if request.method == "POST":
        if form.validate_on_submit():
            try:
                device = device_service.update_device(device_id, form.data, company_id=company_id)
            except DeviceValidationError as exc:
                form.customer_id.errors.append(str(exc))
            else:
                return jsonify(
                    {
                        "ok": True,
                        "device": {
                            "id": device.id,
                            "customer_id": device.customer_id,
                            "label": _device_label(device),
                        },
                    }
                )

        html = render_template(
            "orders/partials/device_modal_form.html",
            form=form,
            modal_title="Edytuj urządzenie",
            action_url=url_for("orders.modal_edit_device", device_id=device_id),
        )
        return jsonify({"ok": False, "html": html}), 400

    return render_template(
        "orders/partials/device_modal_form.html",
        form=form,
        modal_title="Edytuj urządzenie",
        action_url=url_for("orders.modal_edit_device", device_id=device_id),
    )
