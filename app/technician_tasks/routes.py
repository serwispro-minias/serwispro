from __future__ import annotations

from pathlib import Path

from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from . import bp
from .exceptions import ServiceTaskNotFoundError, ServiceTaskPermissionError, ServiceTaskValidationError
from .forms import (
    ServiceTaskAttachmentForm,
    ServiceTaskCommentForm,
    ServiceTaskFilterForm,
    ServiceTaskForm,
    ServiceTaskStatusForm,
    ServiceTaskTimeActionForm,
)
from .service import ServiceTaskService

service = ServiceTaskService()


def _company_id() -> int | None:
    return getattr(current_user, "company_id", None)


def _branch_id() -> int | None:
    return getattr(current_user, "branch_id", None)


def _upload_root() -> Path:
    configured = current_app.config.get("UPLOAD_FOLDER")
    if configured:
        return Path(configured).resolve()
    return (Path(bp.root_path).parent.parent / "uploads").resolve()


def _prepare_task_form(form: ServiceTaskForm, *, order_id: int, company_id: int, branch_id: int | None, exclude_task_id: int | None = None) -> None:
    form.assigned_to.choices = service.get_technician_choices(company_id=company_id, branch_id=branch_id)
    form.parent_task_id.choices = service.get_parent_task_choices(
        order_id=order_id,
        company_id=company_id,
        branch_id=branch_id,
        exclude_task_id=exclude_task_id,
    )


@bp.route("/", methods=["GET"])
@login_required
def index():
    company_id = _company_id()
    if company_id is None:
        abort(404)

    dashboard = service.build_dashboard(company_id=company_id, branch_id=_branch_id(), actor=current_user)

    filter_form = ServiceTaskFilterForm(request.args, meta={"csrf": False})
    filter_form.status.choices = [("", "Wszystkie")] + service.get_status_choices()
    filter_form.priority.choices = [("", "Wszystkie")] + service.get_priority_choices()
    filter_form.assigned_to.choices = [(0, "Wszyscy")] + service.get_technician_choices(company_id=company_id, branch_id=_branch_id())[1:]

    q = (request.args.get("q") or "").strip() or None
    selected_status = (request.args.get("status") or "").strip() or None
    selected_priority = (request.args.get("priority") or "").strip() or None
    selected_assigned_to = request.args.get("assigned_to", type=int)
    if selected_assigned_to in (None, 0):
        selected_assigned_to = None

    filtered = service.search_tasks(
        company_id=company_id,
        branch_id=_branch_id(),
        actor=current_user,
        query_text=q,
        status=selected_status,
        priority=selected_priority,
        assigned_to=selected_assigned_to,
    )

    return render_template(
        "tasks/index.html",
        dashboard=dashboard,
        tasks=filtered,
        filter_form=filter_form,
        status_labels=service.get_status_labels(),
        priority_labels=service.get_priority_labels(),
        type_labels=service.get_type_labels(),
    )


@bp.route("/order/<int:order_id>", methods=["GET"])
@login_required
def order_tasks(order_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        tasks = service.list_for_order(order_id=order_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except (ServiceTaskNotFoundError, ServiceTaskPermissionError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("orders.index"))

    return render_template(
        "tasks/order_tasks.html",
        order_id=order_id,
        tasks=tasks,
        status_labels=service.get_status_labels(),
        priority_labels=service.get_priority_labels(),
        type_labels=service.get_type_labels(),
    )


@bp.route("/order/<int:order_id>/new", methods=["GET", "POST"])
@login_required
def create(order_id: int):
    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is None:
        abort(404)

    form = ServiceTaskForm()
    _prepare_task_form(form, order_id=order_id, company_id=company_id, branch_id=branch_id)

    if form.validate_on_submit():
        try:
            task = service.create_task(
                order_id=order_id,
                company_id=company_id,
                branch_id=branch_id,
                actor=current_user,
                data=dict(form.data),
            )
        except (ServiceTaskValidationError, ServiceTaskPermissionError, ServiceTaskNotFoundError) as exc:
            flash(str(exc), "danger")
        else:
            flash("Zadanie zostało utworzone.", "success")
            return redirect(url_for("technician_tasks.details", task_id=task.id))

    return render_template("tasks/form.html", form=form, title="Nowe zadanie", order_id=order_id)


@bp.route("/<int:task_id>", methods=["GET"])
@login_required
def details(task_id: int):
    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is None:
        abort(404)

    try:
        task = service.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=current_user)
    except (ServiceTaskNotFoundError, ServiceTaskPermissionError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("technician_tasks.index"))

    status_form = ServiceTaskStatusForm()
    status_form.status.data = task.status
    comment_form = ServiceTaskCommentForm()
    attachment_form = ServiceTaskAttachmentForm()
    time_form = ServiceTaskTimeActionForm()

    return render_template(
        "tasks/details.html",
        task=task,
        status_form=status_form,
        comment_form=comment_form,
        attachment_form=attachment_form,
        time_form=time_form,
        status_labels=service.get_status_labels(),
        priority_labels=service.get_priority_labels(),
        type_labels=service.get_type_labels(),
    )


@bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit(task_id: int):
    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is None:
        abort(404)

    try:
        task = service.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=current_user)
    except (ServiceTaskNotFoundError, ServiceTaskPermissionError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("technician_tasks.index"))

    form = ServiceTaskForm(obj=task)
    _prepare_task_form(
        form,
        order_id=task.service_order_id,
        company_id=company_id,
        branch_id=branch_id,
        exclude_task_id=task.id,
    )

    if form.validate_on_submit():
        try:
            service.update_task(
                task_id=task.id,
                company_id=company_id,
                branch_id=branch_id,
                actor=current_user,
                data=dict(form.data),
            )
        except (ServiceTaskValidationError, ServiceTaskPermissionError, ServiceTaskNotFoundError) as exc:
            flash(str(exc), "danger")
        else:
            flash("Zadanie zostało zaktualizowane.", "success")
            return redirect(url_for("technician_tasks.details", task_id=task.id))

    return render_template("tasks/form.html", form=form, title="Edycja zadania", order_id=task.service_order_id)


@bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete(task_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        task = service.get_task(task_id=task_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
        service.delete_task(task_id=task_id, company_id=company_id, branch_id=_branch_id(), actor=current_user)
    except (ServiceTaskValidationError, ServiceTaskPermissionError, ServiceTaskNotFoundError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("technician_tasks.index"))

    flash("Zadanie zostało usunięte.", "success")
    return redirect(url_for("technician_tasks.order_tasks", order_id=task.service_order_id))


@bp.route("/<int:task_id>/status", methods=["POST"])
@login_required
def change_status(task_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = ServiceTaskStatusForm()
    if not form.validate_on_submit():
        flash("Nie udało się zmienić statusu zadania.", "danger")
        return redirect(url_for("technician_tasks.details", task_id=task_id))

    try:
        service.change_status(
            task_id=task_id,
            new_status=form.status.data,
            note=form.note.data,
            completion_percent=form.completion_percent.data,
            company_id=company_id,
            branch_id=_branch_id(),
            actor=current_user,
        )
    except (ServiceTaskValidationError, ServiceTaskPermissionError, ServiceTaskNotFoundError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Status zadania został zaktualizowany.", "success")

    return redirect(url_for("technician_tasks.details", task_id=task_id))


@bp.route("/<int:task_id>/comments", methods=["POST"])
@login_required
def add_comment(task_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = ServiceTaskCommentForm()
    if not form.validate_on_submit():
        flash("Nie udało się dodać komentarza.", "danger")
        return redirect(url_for("technician_tasks.details", task_id=task_id))

    try:
        service.add_comment(
            task_id=task_id,
            content=form.content.data,
            company_id=company_id,
            branch_id=_branch_id(),
            actor=current_user,
        )
    except (ServiceTaskValidationError, ServiceTaskPermissionError, ServiceTaskNotFoundError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Komentarz dodany.", "success")

    return redirect(url_for("technician_tasks.details", task_id=task_id))


@bp.route("/<int:task_id>/attachments", methods=["POST"])
@login_required
def add_attachment(task_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = ServiceTaskAttachmentForm()
    if not form.validate_on_submit():
        flash("Nie udało się dodać załącznika.", "danger")
        return redirect(url_for("technician_tasks.details", task_id=task_id))

    try:
        service.add_attachment(
            task_id=task_id,
            file_storage=form.file.data,
            upload_root=_upload_root(),
            company_id=company_id,
            branch_id=_branch_id(),
            actor=current_user,
        )
    except (ServiceTaskValidationError, ServiceTaskPermissionError, ServiceTaskNotFoundError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Załącznik dodany.", "success")

    return redirect(url_for("technician_tasks.details", task_id=task_id))


@bp.route("/<int:task_id>/attachments/<int:attachment_id>", methods=["GET"])
@login_required
def download_attachment(task_id: int, attachment_id: int):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    try:
        attachment = service.get_attachment(
            task_id=task_id,
            attachment_id=attachment_id,
            company_id=company_id,
            branch_id=_branch_id(),
            actor=current_user,
        )
        path = service.resolve_attachment_path(upload_root=_upload_root(), attachment=attachment)
    except (ServiceTaskValidationError, ServiceTaskPermissionError, ServiceTaskNotFoundError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("technician_tasks.details", task_id=task_id))

    return send_file(path, as_attachment=True, download_name=attachment.original_filename)


@bp.route("/<int:task_id>/time/<string:action>", methods=["POST"])
@login_required
def time_action(task_id: int, action: str):
    company_id = _company_id()
    if company_id is None:
        abort(404)

    form = ServiceTaskTimeActionForm()
    if not form.validate_on_submit():
        flash("Nie udało się zapisać czasu pracy.", "danger")
        return redirect(url_for("technician_tasks.details", task_id=task_id))

    try:
        normalized = (action or "").strip().lower()
        if normalized == "start":
            service.start_work(
                task_id=task_id,
                note=form.note.data,
                company_id=company_id,
                branch_id=_branch_id(),
                actor=current_user,
            )
        elif normalized == "pause":
            service.pause_work(
                task_id=task_id,
                note=form.note.data,
                company_id=company_id,
                branch_id=_branch_id(),
                actor=current_user,
            )
        elif normalized == "resume":
            service.resume_work(
                task_id=task_id,
                note=form.note.data,
                company_id=company_id,
                branch_id=_branch_id(),
                actor=current_user,
            )
        elif normalized == "finish":
            service.finish_work(
                task_id=task_id,
                note=form.note.data,
                company_id=company_id,
                branch_id=_branch_id(),
                actor=current_user,
            )
        else:
            raise ServiceTaskValidationError("Nieprawidłowa akcja czasu pracy.")
    except (ServiceTaskValidationError, ServiceTaskPermissionError, ServiceTaskNotFoundError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Czas pracy został zapisany.", "success")

    return redirect(url_for("technician_tasks.details", task_id=task_id))
