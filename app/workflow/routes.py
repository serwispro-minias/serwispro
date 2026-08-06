from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from .exceptions import WorkflowValidationError
from .forms import WorkflowStatusForm, WorkflowTransitionForm
from .service import WorkflowService


service = WorkflowService()


def _company_id() -> int | None:
    return getattr(current_user, "company_id", None)


def _branch_id() -> int | None:
    return getattr(current_user, "branch_id", None)


def _is_admin() -> bool:
    return any((role.name or "").strip().lower() == "administrator" for role in getattr(current_user, "roles", []))


def _status_choices(company_id: int, branch_id: int | None) -> list[tuple[str, str]]:
    return service.get_status_choices(company_id=company_id, branch_id=branch_id)


@bp.route("/", methods=["GET"])
@login_required
def index():
    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is None:
        abort(404)
    if not _is_admin():
        abort(403)

    service.ensure_default_workflow(company_id=company_id, branch_id=branch_id, user_id=getattr(current_user, "id", None))

    status_form = WorkflowStatusForm()
    transition_form = WorkflowTransitionForm()
    transition_form.from_status_code.choices = _status_choices(company_id, branch_id)
    transition_form.to_status_code.choices = _status_choices(company_id, branch_id)

    statuses = service.repository.list_statuses(company_id=company_id, branch_id=branch_id)
    transitions = service.repository.list_transitions(company_id=company_id, branch_id=branch_id)

    return render_template(
        "workflow/index.html",
        statuses=statuses,
        transitions=transitions,
        status_form=status_form,
        transition_form=transition_form,
    )


@bp.route("/statuses", methods=["POST"])
@login_required
def create_status():
    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is None:
        abort(404)
    if not _is_admin():
        abort(403)

    form = WorkflowStatusForm()
    if not form.validate_on_submit():
        flash("Nie udało się dodać statusu workflow.", "danger")
        return redirect(url_for("workflow.index"))

    try:
        service.create_status(
            company_id=company_id,
            branch_id=branch_id,
            user_id=getattr(current_user, "id", None),
            data=dict(form.data),
        )
    except WorkflowValidationError as exc:
        flash(str(exc), "danger")
    else:
        flash("Dodano status workflow.", "success")

    return redirect(url_for("workflow.index"))


@bp.route("/transitions", methods=["POST"])
@login_required
def create_transition():
    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is None:
        abort(404)
    if not _is_admin():
        abort(403)

    form = WorkflowTransitionForm()
    form.from_status_code.choices = _status_choices(company_id, branch_id)
    form.to_status_code.choices = _status_choices(company_id, branch_id)
    if not form.validate_on_submit():
        flash("Nie udało się dodać przejścia workflow.", "danger")
        return redirect(url_for("workflow.index"))

    try:
        service.create_transition(
            company_id=company_id,
            branch_id=branch_id,
            user_id=getattr(current_user, "id", None),
            data=dict(form.data),
        )
    except WorkflowValidationError as exc:
        flash(str(exc), "danger")
    else:
        flash("Dodano przejście workflow.", "success")

    return redirect(url_for("workflow.index"))


@bp.route("/seed", methods=["POST"])
@login_required
def seed_defaults():
    company_id = _company_id()
    branch_id = _branch_id()
    if company_id is None:
        abort(404)
    if not _is_admin():
        abort(403)

    service.ensure_default_workflow(company_id=company_id, branch_id=branch_id, user_id=getattr(current_user, "id", None))
    flash("Workflow domyślny jest dostępny.", "success")
    return redirect(url_for("workflow.index"))
