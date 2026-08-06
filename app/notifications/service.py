from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone

from app.extensions import db
from app.models.notification_message import NotificationMessage
from app.models.notification_template import NotificationTemplate

from .constants import (
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    DEFAULT_TEMPLATE_VARIABLES,
    NOTIFICATION_CONFIG_KEYS,
    NOTIFICATION_EVENT_CHOICES,
    NOTIFICATION_EVENT_LABELS,
    NOTIFICATION_STATUS_CANCELLED,
    NOTIFICATION_STATUS_ERROR,
    NOTIFICATION_STATUS_SENT,
    STATUS_TO_EVENT_KEY,
)
from .providers import ProviderFactory
from .repository import NotificationRepository


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


@dataclass(slots=True)
class NotificationDraft:
    channel: str
    recipient: str
    subject: str | None
    content: str
    event_key: str | None
    template_id: int | None


class NotificationError(Exception):
    pass


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository | None = None,
        providers: ProviderFactory | None = None,
    ) -> None:
        self.repository = repository or NotificationRepository()
        self.providers = providers or ProviderFactory()

    def config_view(self, *, company_id: int, branch_id: int | None) -> dict[str, str]:
        raw = self.repository.get_settings_map(company_id=company_id, branch_id=branch_id)
        view = {
            "email_enabled": raw.get(NOTIFICATION_CONFIG_KEYS["email_enabled"], "0") or "0",
            "sms_enabled": raw.get(NOTIFICATION_CONFIG_KEYS["sms_enabled"], "0") or "0",
            "default_sender_email": raw.get(NOTIFICATION_CONFIG_KEYS["default_sender_email"], "") or "",
            "smtp_host": raw.get(NOTIFICATION_CONFIG_KEYS["smtp_host"], "") or "",
            "smtp_port": raw.get(NOTIFICATION_CONFIG_KEYS["smtp_port"], "587") or "587",
            "smtp_login": raw.get(NOTIFICATION_CONFIG_KEYS["smtp_login"], "") or "",
            "smtp_password": raw.get(NOTIFICATION_CONFIG_KEYS["smtp_password"], "") or "",
            "smtp_use_tls": raw.get(NOTIFICATION_CONFIG_KEYS["smtp_use_tls"], "1") or "1",
            "smtp_use_ssl": raw.get(NOTIFICATION_CONFIG_KEYS["smtp_use_ssl"], "0") or "0",
            "sms_provider_name": raw.get(NOTIFICATION_CONFIG_KEYS["sms_provider_name"], "generic_api") or "generic_api",
            "sms_api_url": raw.get(NOTIFICATION_CONFIG_KEYS["sms_api_url"], "") or "",
            "sms_api_token": raw.get(NOTIFICATION_CONFIG_KEYS["sms_api_token"], "") or "",
            "sms_sender": raw.get(NOTIFICATION_CONFIG_KEYS["sms_sender"], "") or "",
        }
        return view

    def save_config(self, *, company_id: int, branch_id: int | None, user_id: int | None, data: dict[str, str]) -> None:
        for field, key in NOTIFICATION_CONFIG_KEYS.items():
            value = str(data.get(field, "") or "")
            self.repository.upsert_setting(
                company_id=company_id,
                branch_id=branch_id,
                key=key,
                value=value,
                user_id=user_id,
            )
        db.session.commit()

    def ensure_default_templates(self, *, company_id: int, branch_id: int | None, user_id: int | None) -> None:
        if self.repository.count_templates(company_id=company_id) > 0:
            return

        for event_key, label in NOTIFICATION_EVENT_CHOICES:
            for channel in [CHANNEL_EMAIL, CHANNEL_SMS]:
                body = (
                    "Dzień dobry {{customer_name}},\n"
                    "zlecenie {{order_number}} dla urządzenia {{device_name}} ma status: {{status}}.\n"
                    "Kwota odbioru: {{pickup_amount}}\n"
                    "{{company_name}} | {{company_phone}}"
                )
                subject = f"SerwisPRO: {label} - {{order_number}}" if channel == CHANNEL_EMAIL else None
                template = NotificationTemplate(
                    company_id=company_id,
                    branch_id=branch_id,
                    created_by=user_id,
                    updated_by=user_id,
                    name=f"{label} ({channel})",
                    event_key=event_key,
                    channel=channel,
                    subject=subject,
                    body=body,
                    is_enabled=True,
                )
                self.repository.save_template(template)

        db.session.commit()

    def upsert_template(
        self,
        *,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        template_id: int | None,
        name: str,
        event_key: str,
        channel: str,
        subject: str | None,
        body: str,
        is_enabled: bool,
    ) -> NotificationTemplate:
        if event_key not in NOTIFICATION_EVENT_LABELS:
            raise NotificationError("Nieprawidłowy typ szablonu.")
        if channel not in {CHANNEL_EMAIL, CHANNEL_SMS}:
            raise NotificationError("Nieprawidłowy kanał szablonu.")

        if template_id:
            template = self.repository.get_template_by_id(template_id, company_id=company_id)
            if template is None:
                raise NotificationError("Nie znaleziono szablonu.")
            template.updated_by = user_id
        else:
            template = NotificationTemplate(
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                updated_by=user_id,
                name="",
                event_key=event_key,
                channel=channel,
                body="",
            )

        template.name = name.strip()
        template.event_key = event_key
        template.channel = channel
        template.subject = (subject or "").strip() or None
        template.body = body.strip()
        template.is_enabled = is_enabled
        if not template.name or not template.body:
            raise NotificationError("Nazwa i treść szablonu są wymagane.")

        self.repository.save_template(template)
        db.session.commit()
        return template

    def list_templates(self, *, company_id: int) -> list[NotificationTemplate]:
        return self.repository.list_templates(company_id=company_id)

    def get_template(self, template_id: int, *, company_id: int) -> NotificationTemplate | None:
        return self.repository.get_template_by_id(template_id, company_id=company_id)

    def list_messages_for_order(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[NotificationMessage]:
        return self.repository.list_messages_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)

    def render_with_context(self, text: str, context: dict[str, str]) -> str:
        def replacement(match: re.Match[str]) -> str:
            variable = match.group(1)
            return context.get(variable, "")

        return PLACEHOLDER_PATTERN.sub(replacement, text or "")

    def build_context_for_order(self, *, order_id: int, company_id: int, branch_id: int | None) -> dict[str, str]:
        order = self.repository.get_order(order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise NotificationError("Nie znaleziono zlecenia.")

        company = self.repository.get_company(company_id)
        settings = self.repository.get_settings_map(company_id=company_id, branch_id=branch_id)

        customer_name = (
            order.customer.full_name
            or order.customer.short_name
            or f"{(order.customer.first_name or '').strip()} {(order.customer.last_name or '').strip()}".strip()
            or f"Klient #{order.customer.id}"
        )
        device_name = " ".join(part for part in [order.device.manufacturer or "", order.device.model or ""] if part).strip() or "Urządzenie"
        pickup_amount = order.final_cost if order.final_cost is not None else (order.estimated_cost or Decimal("0"))

        company_name = settings.get("company_name") or (company.name if company else "SerwisPRO")
        company_phone = settings.get("company_phone") or (company.phone if company else "") or "-"

        return {
            "order_number": order.order_number,
            "customer_name": customer_name,
            "device_name": device_name,
            "status": order.status,
            "pickup_amount": f"{Decimal(pickup_amount):.2f} PLN",
            "company_name": company_name,
            "company_phone": company_phone,
        }

    def recipient_for_channel(self, *, order_id: int, company_id: int, branch_id: int | None, channel: str) -> str:
        order = self.repository.get_order(order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise NotificationError("Nie znaleziono zlecenia.")

        if channel == CHANNEL_EMAIL:
            return (order.customer.email or "").strip()
        if channel == CHANNEL_SMS:
            return (order.customer.phone or order.customer.phone2 or "").strip()
        raise NotificationError("Nieznany kanał powiadomień.")

    def draft_for_status_change(
        self,
        *,
        order_id: int,
        new_status: str,
        company_id: int,
        branch_id: int | None,
    ) -> list[NotificationDraft]:
        event_key = STATUS_TO_EVENT_KEY.get(new_status)
        if not event_key:
            return []

        return self._drafts_for_event(
            order_id=order_id,
            event_key=event_key,
            company_id=company_id,
            branch_id=branch_id,
        )

    def draft_manual(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        channel: str,
    ) -> NotificationDraft:
        event_key = STATUS_TO_EVENT_KEY.get(self.build_context_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)["status"])
        template = None
        if event_key:
            template = self.repository.get_template_by_event_channel(
                company_id=company_id,
                event_key=event_key,
                channel=channel,
            )

        context = self.build_context_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        recipient = self.recipient_for_channel(order_id=order_id, company_id=company_id, branch_id=branch_id, channel=channel)

        if template is None:
            subject = "Powiadomienie SerwisPRO" if channel == CHANNEL_EMAIL else None
            body = "Status zlecenia {{order_number}}: {{status}}"
            return NotificationDraft(
                channel=channel,
                recipient=recipient,
                subject=self.render_with_context(subject or "", context) if subject else None,
                content=self.render_with_context(body, context),
                event_key=event_key,
                template_id=None,
            )

        return NotificationDraft(
            channel=channel,
            recipient=recipient,
            subject=self.render_with_context(template.subject or "", context) if template.subject else None,
            content=self.render_with_context(template.body, context),
            event_key=event_key,
            template_id=template.id,
        )

    def send_draft(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        channel: str,
        recipient: str,
        subject: str | None,
        content: str,
        event_key: str | None,
        template_id: int | None,
    ) -> NotificationMessage:
        config = self.config_view(company_id=company_id, branch_id=branch_id)
        enabled_key = "email_enabled" if channel == CHANNEL_EMAIL else "sms_enabled"
        if config.get(enabled_key) != "1":
            result_status = NOTIFICATION_STATUS_ERROR
            response_text = "Kanał powiadomień jest wyłączony w konfiguracji."
            provider_name = "disabled"
            message = self._create_history(
                order_id=order_id,
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                template_id=template_id,
                event_key=event_key,
                channel=channel,
                recipient=recipient,
                subject=subject,
                content=content,
                status=result_status,
                provider_name=provider_name,
                server_response=response_text,
                sent=False,
            )
            db.session.commit()
            return message

        if channel == CHANNEL_EMAIL:
            result = self.providers.email_provider().send(
                recipient=recipient,
                subject=subject,
                content=content,
                config=config,
            )
        elif channel == CHANNEL_SMS:
            result = self.providers.sms_provider().send(
                recipient=recipient,
                content=content,
                config=config,
            )
        else:
            raise NotificationError("Nieobsługiwany kanał wysyłki.")

        status = NOTIFICATION_STATUS_SENT if result.ok else NOTIFICATION_STATUS_ERROR
        server_response = result.server_response or result.error_message
        message = self._create_history(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
            template_id=template_id,
            event_key=event_key,
            channel=channel,
            recipient=recipient,
            subject=subject,
            content=content,
            status=status,
            provider_name=result.provider_name,
            server_response=server_response,
            sent=result.ok,
        )
        db.session.commit()
        return message

    def cancel_draft(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        channel: str,
        recipient: str,
        subject: str | None,
        content: str,
        event_key: str | None,
        template_id: int | None,
    ) -> NotificationMessage:
        message = self._create_history(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
            template_id=template_id,
            event_key=event_key,
            channel=channel,
            recipient=recipient,
            subject=subject,
            content=content,
            status=NOTIFICATION_STATUS_CANCELLED,
            provider_name="manual",
            server_response="Anulowano przez użytkownika.",
            sent=False,
        )
        db.session.commit()
        return message

    def resend_message(
        self,
        *,
        order_id: int,
        message_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
    ) -> NotificationMessage:
        original = self.repository.get_message(message_id, company_id=company_id, branch_id=branch_id)
        if original is None or original.service_order_id != order_id:
            raise NotificationError("Nie znaleziono wiadomości do ponownej wysyłki.")

        return self.send_draft(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
            channel=original.channel,
            recipient=original.recipient or "",
            subject=original.subject,
            content=original.content,
            event_key=original.event_key,
            template_id=original.template_id,
        )

    def available_variables(self) -> tuple[str, ...]:
        return DEFAULT_TEMPLATE_VARIABLES

    def _drafts_for_event(
        self,
        *,
        order_id: int,
        event_key: str,
        company_id: int,
        branch_id: int | None,
    ) -> list[NotificationDraft]:
        config = self.config_view(company_id=company_id, branch_id=branch_id)
        context = self.build_context_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        drafts: list[NotificationDraft] = []

        for channel in [CHANNEL_EMAIL, CHANNEL_SMS]:
            enabled_key = "email_enabled" if channel == CHANNEL_EMAIL else "sms_enabled"
            if config.get(enabled_key) != "1":
                continue

            template = self.repository.get_template_by_event_channel(
                company_id=company_id,
                event_key=event_key,
                channel=channel,
            )
            if template is None:
                continue

            recipient = self.recipient_for_channel(order_id=order_id, company_id=company_id, branch_id=branch_id, channel=channel)
            if not recipient:
                continue

            drafts.append(
                NotificationDraft(
                    channel=channel,
                    recipient=recipient,
                    subject=self.render_with_context(template.subject or "", context) if template.subject else None,
                    content=self.render_with_context(template.body, context),
                    event_key=event_key,
                    template_id=template.id,
                )
            )

        return drafts

    def _create_history(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        template_id: int | None,
        event_key: str | None,
        channel: str,
        recipient: str,
        subject: str | None,
        content: str,
        status: str,
        provider_name: str | None,
        server_response: str | None,
        sent: bool,
    ) -> NotificationMessage:
        payload: dict[str, object] = {
            "service_order_id": order_id,
            "template_id": template_id,
            "user_id": user_id,
            "event_key": event_key,
            "channel": channel,
            "recipient": recipient,
            "subject": subject,
            "content": content,
            "status": status,
            "provider_name": provider_name,
            "server_response": server_response,
            "company_id": company_id,
            "branch_id": branch_id,
            "created_by": user_id,
            "updated_by": user_id,
        }
        message = self.repository.create_message(payload)
        if sent:
            message.sent_at = datetime.now(timezone.utc)
            db.session.add(message)
            db.session.flush()
        return message
