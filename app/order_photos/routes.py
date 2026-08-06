from __future__ import annotations

from pathlib import Path

from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import OperationalError

from . import bp
from .exceptions import ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError, ServiceOrderPhotoValidationError
from .forms import PhotoAnnotationCreateForm, PhotoAnnotationDeleteForm, PhotoAnnotationUpdateForm, ServiceOrderPhotoDeleteForm, ServiceOrderPhotoFilterForm, ServiceOrderPhotoUploadForm
from .service import ServiceOrderPhotoService


service = ServiceOrderPhotoService()


def _company_id() -> int | None:
    return getattr(current_user, "company_id", None)


def _branch_id() -> int | None:
    return getattr(current_user, "branch_id", None)


def _is_customer_portal_role() -> bool:
    try:
        role_names = {(role.name or "").strip().lower() for role in getattr(current_user, "roles", [])}
    except OperationalError:
        return False
    return "klient" in role_names or "customer" in role_names


def _upload_root() -> Path:
    configured = current_app.config.get("UPLOAD_FOLDER")
    if configured:
        return Path(configured).resolve()
    return (Path(current_app.root_path).parent / "uploads").resolve()


def _filter_form(order_id: int, *, company_id: int, branch_id: int | None) -> ServiceOrderPhotoFilterForm:
    form = ServiceOrderPhotoFilterForm(request.args, meta={"csrf": False})
    form.photo_type.choices = [("", "Wszystkie")] + service.get_type_choices()
    form.author_id.choices = service.author_choices(order_id=order_id, company_id=company_id, branch_id=branch_id)
    form.author_id.data = request.args.get("author_id", type=int, default=-1)
    return form


@bp.route("/orders/<int:order_id>/gallery")
@login_required
def gallery(order_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    filter_form = _filter_form(order_id, company_id=company_id, branch_id=_branch_id())
    photos = service.list_photos(
        order_id=order_id,
        company_id=company_id,
        branch_id=_branch_id(),
        photo_type=(filter_form.photo_type.data or None),
        date_from=filter_form.date_from.data,
        date_to=filter_form.date_to.data,
        author_id=filter_form.author_id.data,
    )

    return render_template(
        "order_photos/gallery.html",
        order_id=order_id,
        photos=photos,
        type_labels=service.get_type_labels(),
        annotation_type_choices=service.get_annotation_type_choices(),
        annotation_priority_choices=service.get_annotation_priority_choices(),
        upload_form=ServiceOrderPhotoUploadForm(),
        filter_form=filter_form,
        delete_form=ServiceOrderPhotoDeleteForm(),
        annotation_create_form=PhotoAnnotationCreateForm(),
        annotation_update_form=PhotoAnnotationUpdateForm(),
        annotation_delete_form=PhotoAnnotationDeleteForm(),
    )


@bp.route("/orders/<int:order_id>/upload", methods=["POST"])
@login_required
def upload(order_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = ServiceOrderPhotoUploadForm()
    if not form.validate_on_submit():
        flash("Nie udało się przesłać zdjęć.", "danger")
        return redirect(url_for("orders.details", order_id=order_id, tab="photos"))

    main_index = None
    raw_main = (form.main_photo_index.data or "").strip()
    if raw_main.isdigit():
        main_index = int(raw_main)

    try:
        service.upload_photos(
            order_id=order_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            photo_type=form.photo_type.data,
            title=form.title.data,
            description=form.description.data,
            taken_at=form.taken_at.data,
            sort_order=form.sort_order.data,
            is_visible_for_customer=bool(form.is_visible_for_customer.data),
            files=form.files.data,
            main_photo_index=main_index,
            upload_root=_upload_root(),
        )
    except ServiceOrderPhotoNotFoundError:
        abort(404)
    except ServiceOrderPhotoPermissionError as exc:
        flash(str(exc), "danger")
    except ServiceOrderPhotoValidationError as exc:
        flash(str(exc), "danger")
    else:
        flash("Zdjęcia zostały zapisane.", "success")

    return redirect(url_for("orders.details", order_id=order_id, tab="photos"))


@bp.route("/<int:photo_id>/delete", methods=["POST"])
@login_required
def delete(photo_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = ServiceOrderPhotoDeleteForm()
    if not form.validate_on_submit():
        flash("Nie udało się usunąć zdjęcia.", "danger")
        return redirect(request.referrer or url_for("orders.index"))

    try:
        row = service.delete_photo(
            photo_id=photo_id,
            company_id=company_id,
            branch_id=_branch_id(),
            upload_root=_upload_root(),
        )
    except ServiceOrderPhotoNotFoundError:
        abort(404)
    except ServiceOrderPhotoPermissionError as exc:
        flash(str(exc), "danger")
        return redirect(request.referrer or url_for("orders.index"))

    flash("Zdjęcie zostało usunięte.", "success")
    return redirect(url_for("orders.details", order_id=row.service_order_id, tab="photos"))


@bp.route("/<int:photo_id>/file")
@login_required
def file(photo_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        row = service.get_photo(photo_id=photo_id, company_id=company_id, branch_id=_branch_id())
        full_path = service.resolve_original_path(upload_root=_upload_root(), photo=row)
    except (ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError):
        abort(404)

    as_attachment = request.args.get("download", "0") == "1"
    return send_file(
        full_path,
        mimetype=row.mime_type,
        as_attachment=as_attachment,
        download_name=row.original_file_name,
    )


@bp.route("/<int:photo_id>/thumbnail")
@login_required
def thumbnail(photo_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        row = service.get_photo(photo_id=photo_id, company_id=company_id, branch_id=_branch_id())
        full_path = service.resolve_thumbnail_path(upload_root=_upload_root(), photo=row)
    except (ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError):
        abort(404)

    mimetype = "image/webp" if full_path.suffix.lower() == ".webp" else row.mime_type
    return send_file(full_path, mimetype=mimetype, as_attachment=False)


@bp.route("/<int:photo_id>/annotations", methods=["GET"])
@login_required
def annotations(photo_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        rows = service.list_annotations(
            photo_id=photo_id,
            company_id=company_id,
            branch_id=_branch_id(),
            for_customer=_is_customer_portal_role(),
        )
    except (ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError):
        abort(404)

    return {
        "ok": True,
        "items": [service.annotation_to_dict(row) for row in rows],
    }


@bp.route("/<int:photo_id>/annotations", methods=["POST"])
@login_required
def create_annotation(photo_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = PhotoAnnotationCreateForm()
    if not form.validate_on_submit():
        return {"ok": False, "message": "Niepoprawne dane oznaczenia.", "errors": form.errors}, 400

    payload = {
        "annotation_type": form.annotation_type.data,
        "x": form.x.data,
        "y": form.y.data,
        "width": form.width.data,
        "height": form.height.data,
        "rotation": form.rotation.data,
        "color": form.color.data,
        "title": form.title.data,
        "description": form.description.data,
        "priority": form.priority.data,
        "is_visible_for_customer": form.is_visible_for_customer.data,
        "points_json": form.points_json.data,
    }

    try:
        row = service.create_annotation(
            photo_id=photo_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            payload=payload,
        )
    except ServiceOrderPhotoNotFoundError:
        abort(404)
    except ServiceOrderPhotoPermissionError as exc:
        return {"ok": False, "message": str(exc)}, 403
    except ServiceOrderPhotoValidationError as exc:
        return {"ok": False, "message": str(exc)}, 400

    return {"ok": True, "item": service.annotation_to_dict(row)}


@bp.route("/annotations/<int:annotation_id>", methods=["POST"])
@login_required
def update_annotation(annotation_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = PhotoAnnotationUpdateForm()
    if not form.validate_on_submit():
        return {"ok": False, "message": "Niepoprawne dane oznaczenia.", "errors": form.errors}, 400
    if not str(form.annotation_id.data).isdigit() or int(form.annotation_id.data) != annotation_id:
        return {"ok": False, "message": "Niepoprawny identyfikator oznaczenia."}, 400

    payload = {
        "annotation_type": form.annotation_type.data,
        "x": form.x.data,
        "y": form.y.data,
        "width": form.width.data,
        "height": form.height.data,
        "rotation": form.rotation.data,
        "color": form.color.data,
        "title": form.title.data,
        "description": form.description.data,
        "priority": form.priority.data,
        "is_visible_for_customer": form.is_visible_for_customer.data,
        "points_json": form.points_json.data,
    }

    try:
        row = service.update_annotation(
            annotation_id=annotation_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
            payload=payload,
        )
    except ServiceOrderPhotoNotFoundError:
        abort(404)
    except ServiceOrderPhotoPermissionError as exc:
        return {"ok": False, "message": str(exc)}, 403
    except ServiceOrderPhotoValidationError as exc:
        return {"ok": False, "message": str(exc)}, 400

    return {"ok": True, "item": service.annotation_to_dict(row)}


@bp.route("/annotations/<int:annotation_id>/delete", methods=["POST"])
@login_required
def delete_annotation(annotation_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = PhotoAnnotationDeleteForm()
    if not form.validate_on_submit():
        return {"ok": False, "message": "Niepoprawne zadanie usuniecia.", "errors": form.errors}, 400
    if not str(form.annotation_id.data).isdigit() or int(form.annotation_id.data) != annotation_id:
        return {"ok": False, "message": "Niepoprawny identyfikator oznaczenia."}, 400

    try:
        row = service.delete_annotation(
            annotation_id=annotation_id,
            company_id=company_id,
            branch_id=_branch_id(),
            user_id=getattr(current_user, "id", None),
        )
    except ServiceOrderPhotoNotFoundError:
        abort(404)
    except ServiceOrderPhotoPermissionError as exc:
        return {"ok": False, "message": str(exc)}, 403

    return {"ok": True, "item": service.annotation_to_dict(row)}
