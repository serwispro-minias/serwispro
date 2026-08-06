from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

from . import bp
from .forms import PublicEstimateApprovalForm
from .service import (
    EstimateApprovalNotFoundError,
    EstimateApprovalValidationError,
    estimate_approval_service,
)


@bp.route("/approve/<string:token_value>", methods=["GET", "POST"])
def approve(token_value: str):
    form = PublicEstimateApprovalForm()
    try:
        context = estimate_approval_service.get_public_view_context(token_value=token_value)
    except EstimateApprovalNotFoundError:
        abort(404)

    if form.validate_on_submit():
        decision = (request.form.get("decision") or "").strip().upper()
        if decision not in {"ACCEPT", "REJECT"}:
            flash("Nieprawidłowa decyzja.", "danger")
            return redirect(url_for("estimate_approval.approve", token_value=token_value))

        try:
            estimate_approval_service.process_customer_decision(
                token_value=token_value,
                decision=decision,
                customer_note=form.customer_note.data,
                ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
                user_agent=request.user_agent.string,
            )
        except EstimateApprovalValidationError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("estimate_approval.approve", token_value=token_value))

        if decision == "ACCEPT":
            flash("Dziękujemy. Kosztorys został zaakceptowany.", "success")
        else:
            flash("Dziękujemy. Kosztorys został odrzucony.", "warning")
        return redirect(url_for("estimate_approval.approve", token_value=token_value))

    return render_template(
        "estimate_approval/public_approve.html",
        form=form,
        token=context.token,
        estimate=context.estimate,
        order=context.order,
        company_lines=context.company_lines,
        approval_status_message=context.approval_status_message,
        is_actionable=context.is_actionable,
    )
