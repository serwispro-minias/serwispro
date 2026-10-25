from __future__ import annotations

from pathlib import Path

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import OperationalError

from . import bp
from .exceptions import (
    ServiceOrderPhotoNotFoundError,
    ServiceOrderPhotoPermissionError,
    ServiceOrderPhotoValidationError,
)
from .forms import (
    PhotoAnnotationCreateForm,
    PhotoAnnotationDeleteForm,
    PhotoAnnotationUpdateForm,
    ServiceOrderPhotoDeleteForm,
    ServiceOrderPhotoFilterForm,
    ServiceOrderPhotoUploadForm,
)
from .service import MAX_UPLOAD_REQUEST_BYTES, ServiceOrderPhotoService

service = ServiceOrderPhotoService()


def _company_id() -> int | None:
    return getattr(current_user, "company_id", None)


def _branch_id() -> int | None:
    return getattr(current_user, "branch_id", None)


def _is_customer_portal_role() -> bool:
    return service.is_customer_portal_user()


def _upload_root() -> Path:
    configured = current_app.config.get("UPLOAD_FOLDER")
    if configured:
        return Path(configured).resolve()
    return (Path(current_app.root_path).parent / "uploads").resolve()


def _filter_form(order_id: int, *, company_id: int, branch_id: int | None) -> ServiceOrderPhotoFilterForm:
    form = ServiceOrderPhotoFilterForm(request.args, meta={"csrf": False})
    form.photo_type.choices = [("", "Wszystkie")] + service.get_type_choices()
    if "photo_type" not in request.args:
        form.photo_type.data = ""
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
        only_customer_visible=_is_customer_portal_role(),
    )

    return render_template(
        "order_photos/gallery.html",
        order_id=order_id,
        photos=photos,
        type_labels=service.get_type_labels(),
        annotation_type_choices=service.get_annotation_type_choices(),
        annotation_priority_choices=service.get_annotation_priority_choices(),
        upload_form=ServiceOrderPhotoUploadForm(),
        can_manage_photos=service.can_manage_photos(),
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
    is_xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if request.content_length and request.content_length > MAX_UPLOAD_REQUEST_BYTES:
        if is_xhr:
            return jsonify({"ok": False, "message": "Łączny rozmiar przesyłanych zdjęć jest zbyt duży."}), 413
        flash("Łączny rozmiar przesyłanych zdjęć jest zbyt duży.", "danger")
        return redirect(url_for("orders.details", order_id=order_id, tab="photos"))

    form = ServiceOrderPhotoUploadForm()
    if not form.validate_on_submit():
        if is_xhr:
            return jsonify({"ok": False, "message": "Nie udało się przesłać zdjęć. Sprawdź etap i wybrane pliki."}), 400
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
        if is_xhr:
            return jsonify({"ok": False, "message": "Nie znaleziono zlecenia."}), 404
        abort(404)
    except ServiceOrderPhotoPermissionError as exc:
        if is_xhr:
            return jsonify({"ok": False, "message": str(exc)}), 403
        flash(str(exc), "danger")
    except ServiceOrderPhotoValidationError as exc:
        if is_xhr:
            return jsonify({"ok": False, "message": str(exc)}), 400
        flash(str(exc), "danger")
    else:
        if is_xhr:
            return jsonify({"ok": True, "message": "Zdjęcia zostały zapisane."})
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
        row = service.get_photo(photo_id=photo_id, company_id=company_id, branch_id=_branch_id(), for_customer=_is_customer_portal_role())
        full_path = service.resolve_original_path(upload_root=_upload_root(), photo=row)
    except (ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError):
        abort(404)

    as_attachment = request.args.get("download", "0") == "1"
    response = send_file(
        full_path,
        mimetype=row.mime_type,
        as_attachment=as_attachment,
        download_name=row.original_file_name,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.route("/<int:photo_id>/thumbnail")
@login_required
def thumbnail(photo_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        row = service.get_photo(photo_id=photo_id, company_id=company_id, branch_id=_branch_id(), for_customer=_is_customer_portal_role())
        full_path = service.resolve_thumbnail_path(upload_root=_upload_root(), photo=row)
    except (ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError):
        abort(404)

    mimetype = "image/webp" if full_path.suffix.lower() == ".webp" else row.mime_type
    response = send_file(full_path, mimetype=mimetype, as_attachment=False)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


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
