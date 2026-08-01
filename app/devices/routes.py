from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from .exceptions import DeviceNotFoundError, DeviceValidationError
from .forms import DeviceForm
from .repository import DeviceRepository
from .service import DeviceService

service = DeviceService(DeviceRepository())


def _set_customer_choices(form: DeviceForm, company_id: int | None) -> None:
    choices = service.get_customer_choices(company_id)
    form.customer_id.choices = choices


@bp.route("/", methods=["GET"])
@login_required
def index():
    """Display searchable and paginated devices list."""

    page = request.args.get("page", 1, type=int)
    query = request.args.get("q", "", type=str)
    per_page = 20

    if query:
        devices = service.search_devices(
            query=query,
            page=page,
            per_page=per_page,
            company_id=current_user.company_id,
        )
    else:
        devices = service.list_devices(
            page=page,
            per_page=per_page,
            company_id=current_user.company_id,
        )

    return render_template("devices/index.html", devices=devices, q=query)


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    """Create a new device."""

    form = DeviceForm()
    _set_customer_choices(form, current_user.company_id)

    preselected_customer_id = request.args.get("customer_id", type=int)
    if request.method == "GET" and preselected_customer_id is not None:
        valid_customer_ids = {item[0] for item in form.customer_id.choices}
        if preselected_customer_id in valid_customer_ids:
            form.customer_id.data = preselected_customer_id

    if form.validate_on_submit():
        try:
            device = service.create_device(form.data, company_id=current_user.company_id)
            flash("Urzadzenie zostalo utworzone.", "success")
            return redirect(url_for("devices.details", device_id=device.id))
        except DeviceValidationError as exc:
            flash(str(exc), "danger")

    return render_template("devices/form.html", form=form, title="Dodaj urzadzenie", device=None)


@bp.route("/<int:device_id>/edit", methods=["GET", "POST"])
@login_required
def edit(device_id: int):
    """Edit an existing device."""

    device = service.get_device(device_id, company_id=current_user.company_id)
    if device is None:
        flash("Nie znaleziono urzadzenia.", "danger")
        return redirect(url_for("devices.index"))

    form = DeviceForm(obj=device)
    _set_customer_choices(form, current_user.company_id)

    if form.validate_on_submit():
        try:
            service.update_device(device_id, form.data, company_id=current_user.company_id)
            flash("Dane urzadzenia zostaly zaktualizowane.", "success")
            return redirect(url_for("devices.details", device_id=device_id))
        except DeviceValidationError as exc:
            flash(str(exc), "danger")

    return render_template("devices/form.html", form=form, title="Edytuj urzadzenie", device=device)


@bp.route("/<int:device_id>")
@login_required
def details(device_id: int):
    """Display details page for selected device."""

    device = service.get_device(device_id, company_id=current_user.company_id)
    if device is None:
        flash("Nie znaleziono urzadzenia.", "danger")
        return redirect(url_for("devices.index"))

    return render_template("devices/details.html", device=device)


@bp.route("/<int:device_id>/delete", methods=["POST"])
@login_required
def delete(device_id: int):
    """Soft delete selected device."""

    try:
        service.delete_device(device_id, company_id=current_user.company_id)
        flash("Urzadzenie zostalo usuniete.", "success")
    except DeviceNotFoundError:
        flash("Nie znaleziono urzadzenia.", "danger")

    return redirect(url_for("devices.index"))
