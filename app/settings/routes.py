from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.notifications import NotificationError, NotificationService

from . import bp
from .forms import NotificationConfigForm, NotificationTemplateForm


notification_service = NotificationService()


def _company_id() -> int | None:
    return getattr(current_user, "company_id", None)


def _branch_id() -> int | None:
    return getattr(current_user, "branch_id", None)


def _user_id() -> int | None:
    return getattr(current_user, "id", None)


@bp.route("/")
@login_required
def index():
    return redirect(url_for("settings.notifications"))


@bp.route("/notifications", methods=["GET", "POST"])
@login_required
def notifications():
    company_id = _company_id()
    if company_id is None:
        flash("Brak identyfikatora firmy.", "danger")
        return redirect(url_for("dashboard.index"))

    notification_service.ensure_default_templates(
        company_id=company_id,
        branch_id=_branch_id(),
        user_id=_user_id(),
    )

    config_form = NotificationConfigForm(prefix="cfg")
    template_form = NotificationTemplateForm(prefix="tpl")
    selected_template_id = request.args.get("template_id", type=int)

    if request.method == "POST":
        action = request.form.get("action") or ""
        if action == "save_config" and config_form.validate_on_submit():
            data = {
                "email_enabled": "1" if config_form.email_enabled.data else "0",
                "sms_enabled": "1" if config_form.sms_enabled.data else "0",
                "smtp_host": config_form.smtp_host.data or "",
                "smtp_port": config_form.smtp_port.data or "",
                "smtp_login": config_form.smtp_login.data or "",
                "smtp_password": config_form.smtp_password.data or "",
                "smtp_use_tls": "1" if config_form.smtp_use_tls.data else "0",
                "smtp_use_ssl": "1" if config_form.smtp_use_ssl.data else "0",
                "default_sender_email": config_form.default_sender_email.data or "",
                "sms_provider_name": config_form.sms_provider_name.data or "",
                "sms_api_url": config_form.sms_api_url.data or "",
                "sms_api_token": config_form.sms_api_token.data or "",
                "sms_sender": config_form.sms_sender.data or "",
            }
            notification_service.save_config(
                company_id=company_id,
                branch_id=_branch_id(),
                user_id=_user_id(),
                data=data,
            )
            flash("Konfiguracja powiadomień została zapisana.", "success")
            return redirect(url_for("settings.notifications"))

        if action == "save_template" and template_form.validate_on_submit():
            try:
                template = notification_service.upsert_template(
                    company_id=company_id,
                    branch_id=_branch_id(),
                    user_id=_user_id(),
                    template_id=int(template_form.template_id.data) if template_form.template_id.data else None,
                    name=template_form.name.data,
                    event_key=template_form.event_key.data,
                    channel=template_form.channel.data,
                    subject=template_form.subject.data,
                    body=template_form.body.data,
                    is_enabled=bool(template_form.is_enabled.data),
                )
            except NotificationError as exc:
                flash(str(exc), "danger")
            else:
                flash("Szablon powiadomienia został zapisany.", "success")
                return redirect(url_for("settings.notifications", template_id=template.id))

    config_values = notification_service.config_view(company_id=company_id, branch_id=_branch_id())
    if request.method == "GET":
        config_form.email_enabled.data = config_values["email_enabled"] == "1"
        config_form.sms_enabled.data = config_values["sms_enabled"] == "1"
        config_form.smtp_host.data = config_values["smtp_host"]
        config_form.smtp_port.data = config_values["smtp_port"]
        config_form.smtp_login.data = config_values["smtp_login"]
        config_form.smtp_password.data = config_values["smtp_password"]
        config_form.smtp_use_tls.data = config_values["smtp_use_tls"] == "1"
        config_form.smtp_use_ssl.data = config_values["smtp_use_ssl"] == "1"
        config_form.default_sender_email.data = config_values["default_sender_email"]
        config_form.sms_provider_name.data = config_values["sms_provider_name"]
        config_form.sms_api_url.data = config_values["sms_api_url"]
        config_form.sms_api_token.data = config_values["sms_api_token"]
        config_form.sms_sender.data = config_values["sms_sender"]

        if selected_template_id:
            selected_template = notification_service.get_template(selected_template_id, company_id=company_id)
            if selected_template is not None:
                template_form.template_id.data = str(selected_template.id)
                template_form.name.data = selected_template.name
                template_form.event_key.data = selected_template.event_key
                template_form.channel.data = selected_template.channel
                template_form.subject.data = selected_template.subject or ""
                template_form.body.data = selected_template.body
                template_form.is_enabled.data = selected_template.is_enabled
        else:
            template_form.is_enabled.data = True

    templates = notification_service.list_templates(company_id=company_id)
    return render_template(
        "settings/notifications.html",
        config_form=config_form,
        template_form=template_form,
        templates=templates,
        available_variables=notification_service.available_variables(),
    )
