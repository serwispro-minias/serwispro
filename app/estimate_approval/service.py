from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import render_template

from app.extensions import db
from app.models.estimate_approval_token import EstimateApprovalToken
from app.models.service_estimate import ServiceEstimate
from app.models.service_order import ServiceOrder
from app.notifications.constants import CHANNEL_EMAIL, NOTIFICATION_STATUS_SENT
from app.notifications.service import NotificationService

from .repository import EstimateApprovalRepository


TOKEN_LIFETIME_DAYS = 14


@dataclass(slots=True)
class ApprovalViewContext:
    token: EstimateApprovalToken
    estimate: ServiceEstimate
    order: ServiceOrder
    company_lines: list[str]
    approval_status_message: str
    is_actionable: bool


class EstimateApprovalError(Exception):
    pass


class EstimateApprovalNotFoundError(EstimateApprovalError):
    pass


class EstimateApprovalValidationError(EstimateApprovalError):
    pass


class EstimateApprovalPermissionError(EstimateApprovalError):
    pass


class EstimateApprovalService:
    def __init__(
        self,
        repository: EstimateApprovalRepository | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.repository = repository or EstimateApprovalRepository()
        self.notification_service = notification_service or NotificationService()

    def create_token(
        self,
        *,
        estimate_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
    ) -> EstimateApprovalToken:
        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None:
            raise EstimateApprovalNotFoundError("Nie znaleziono kosztorysu.")

        now = self._utc_now()
        self.repository.expire_pending_tokens(estimate_id=estimate.id, now=now)

        token = self.repository.create_token(
            {
                "estimate_id": estimate.id,
                "token": str(uuid4()),
                "status": "PENDING",
                "expires_at": now + timedelta(days=TOKEN_LIFETIME_DAYS),
                "company_id": estimate.company_id,
                "branch_id": estimate.branch_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        db.session.commit()
        return token

    def generate_public_link(self, *, token_value: str, base_url: str) -> str:
        return f"{base_url.rstrip('/')}/estimate/approve/{token_value}"

    def send_estimate_email(
        self,
        *,
        estimate_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        base_url: str,
    ) -> tuple[ServiceEstimate, EstimateApprovalToken, str]:
        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None:
            raise EstimateApprovalNotFoundError("Nie znaleziono kosztorysu.")
        if estimate.service_order is None:
            raise EstimateApprovalValidationError("Kosztorys nie jest powiązany ze zleceniem.")

        recipient = (estimate.service_order.customer.email or "").strip() if estimate.service_order.customer else ""
        if not recipient:
            raise EstimateApprovalValidationError("Klient nie ma adresu e-mail do wysyłki.")

        token = self.create_token(
            estimate_id=estimate.id,
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
        )
        link = self.generate_public_link(token_value=token.token, base_url=base_url)

        company_lines = self._company_lines(company_id=company_id, branch_id=estimate.branch_id)
        html_content = render_template(
            "estimate_approval/email_estimate_approval.html",
            estimate=estimate,
            order=estimate.service_order,
            approval_link=link,
            company_lines=company_lines,
            valid_until=(estimate.valid_until.strftime("%Y-%m-%d") if estimate.valid_until else "-")
        )

        message = self.notification_service.send_draft(
            order_id=estimate.service_order_id,
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
            channel=CHANNEL_EMAIL,
            recipient=recipient,
            subject=f"Kosztorys naprawy {estimate.service_order.order_number} - decyzja klienta",
            content=html_content,
            event_key="ESTIMATE_SENT",
            template_id=None,
        )
        if message.status != NOTIFICATION_STATUS_SENT:
            raise EstimateApprovalValidationError("Nie udało się wysłać wiadomości e-mail do klienta.")

        estimate.status = "SENT"
        estimate.sent_at = self._utc_now()
        estimate.updated_by = user_id
        self.repository.save(estimate)
        db.session.commit()
        return estimate, token, link

    def get_active_token_for_estimate(
        self,
        *,
        estimate_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> EstimateApprovalToken | None:
        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None:
            return None
        token = self.repository.get_active_token_for_estimate(estimate_id=estimate.id)
        if token is None:
            return None
        if token.is_expired:
            token.status = "EXPIRED"
            token.used_at = token.used_at or self._utc_now()
            self.repository.save(token)
            db.session.commit()
            return None
        return token

    def get_public_view_context(self, *, token_value: str) -> ApprovalViewContext:
        token = self.repository.get_token(token_value=token_value)
        if token is None:
            raise EstimateApprovalNotFoundError("Nie znaleziono linku akceptacji kosztorysu.")
        if token.estimate is None or token.estimate.service_order is None:
            raise EstimateApprovalNotFoundError("Nie znaleziono danych kosztorysu.")

        order = token.estimate.service_order
        message = self._token_state_message(token)
        actionable = self._is_token_actionable(token)

        return ApprovalViewContext(
            token=token,
            estimate=token.estimate,
            order=order,
            company_lines=self._company_lines(company_id=token.company_id, branch_id=token.branch_id),
            approval_status_message=message,
            is_actionable=actionable,
        )

    def process_customer_decision(
        self,
        *,
        token_value: str,
        decision: str,
        customer_note: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> ServiceEstimate:
        token = self.repository.get_token(token_value=token_value)
        if token is None:
            raise EstimateApprovalNotFoundError("Nie znaleziono linku akceptacji kosztorysu.")
        if token.estimate is None or token.estimate.service_order is None:
            raise EstimateApprovalNotFoundError("Nie znaleziono danych kosztorysu.")

        now = self._utc_now()
        if token.status != "PENDING" or token.used_at is not None:
            raise EstimateApprovalValidationError("Ten link został już wykorzystany.")
        if self._as_utc(token.expires_at) <= now:
            token.status = "EXPIRED"
            token.used_at = now
            token.ip_address = ip_address
            token.user_agent = (user_agent or "")[:512] or None
            self.repository.save(token)
            db.session.commit()
            raise EstimateApprovalValidationError("Link do kosztorysu wygasł.")

        decision_normalized = (decision or "").strip().upper()
        if decision_normalized not in {"ACCEPT", "REJECT"}:
            raise EstimateApprovalValidationError("Nieprawidłowa decyzja klienta.")

        estimate = token.estimate
        order = token.estimate.service_order
        previous_order_status = order.status

        token.used_at = now
        token.ip_address = ip_address
        token.user_agent = (user_agent or "")[:512] or None

        note_text = (customer_note or "").strip()
        if decision_normalized == "ACCEPT":
            token.status = "ACCEPTED"
            estimate.status = "ACCEPTED"
            estimate.approved_at = now
            estimate.rejected_at = None
            order.status = "READY_FOR_REPAIR"
            history_text = "Klient zaakceptował kosztorys."
            if note_text:
                history_text += f" Uwagi klienta: {note_text}"
            self.repository.create_order_history_entry(
                order_id=order.id,
                company_id=order.company_id,
                branch_id=order.branch_id,
                user_id=None,
                description=history_text,
            )
            if previous_order_status != order.status:
                self.repository.create_status_history_entry(
                    order_id=order.id,
                    old_status=previous_order_status,
                    new_status=order.status,
                    changed_by=None,
                    note="Zmiana statusu po akceptacji kosztorysu przez klienta.",
                )
            self._notify_service_about_decision(
                order=order,
                estimate=estimate,
                decision_label="zaakceptował",
                customer_note=note_text,
            )
        else:
            token.status = "REJECTED"
            estimate.status = "REJECTED"
            estimate.rejected_at = now
            estimate.approved_at = None
            history_text = "Klient odrzucił kosztorys."
            if note_text:
                history_text += f" Uwagi klienta: {note_text}"
            self.repository.create_order_history_entry(
                order_id=order.id,
                company_id=order.company_id,
                branch_id=order.branch_id,
                user_id=None,
                description=history_text,
            )
            self._notify_service_about_decision(
                order=order,
                estimate=estimate,
                decision_label="odrzucił",
                customer_note=note_text,
            )

        self.repository.save(token)
        self.repository.save(estimate)
        self.repository.save(order)
        db.session.commit()
        return estimate

    def revoke_approval(
        self,
        *,
        estimate_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int,
        is_admin: bool,
    ) -> ServiceEstimate:
        if not is_admin:
            raise EstimateApprovalPermissionError("Tylko administrator może cofnąć akceptację kosztorysu.")

        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None or estimate.service_order is None:
            raise EstimateApprovalNotFoundError("Nie znaleziono kosztorysu.")

        now = self._utc_now()
        estimate.status = "SENT"
        estimate.approved_at = None
        estimate.rejected_at = None
        estimate.updated_by = user_id

        order = estimate.service_order
        previous_order_status = order.status
        order.status = "WAITING_CUSTOMER_DECISION"
        order.updated_by = user_id

        self.repository.expire_pending_tokens(estimate_id=estimate.id, now=now)
        self.repository.create_order_history_entry(
            order_id=order.id,
            company_id=order.company_id,
            branch_id=order.branch_id,
            user_id=user_id,
            description="Cofnięto akceptację kosztorysu przez administratora.",
        )
        if previous_order_status != order.status:
            self.repository.create_status_history_entry(
                order_id=order.id,
                old_status=previous_order_status,
                new_status=order.status,
                changed_by=user_id,
                note="Cofnięcie akceptacji kosztorysu przez administratora.",
            )

        self.repository.save(estimate)
        self.repository.save(order)
        db.session.commit()
        return estimate

    def _notify_service_about_decision(
        self,
        *,
        order: ServiceOrder,
        estimate: ServiceEstimate,
        decision_label: str,
        customer_note: str,
    ) -> None:
        recipient = self._service_email(company_id=order.company_id, branch_id=order.branch_id)
        if not recipient:
            return

        note_line = f"\nUwagi klienta: {customer_note}" if customer_note else ""
        content = (
            f"Klient {decision_label} kosztorys dla zlecenia {order.order_number}.\n"
            f"Kosztorys: v{estimate.version_number}\n"
            f"Kwota brutto: {estimate.gross_total:.2f} PLN"
            f"{note_line}"
        )
        self.notification_service.send_draft(
            order_id=order.id,
            company_id=order.company_id,
            branch_id=order.branch_id,
            user_id=None,
            channel=CHANNEL_EMAIL,
            recipient=recipient,
            subject=f"Decyzja klienta dla kosztorysu {order.order_number}",
            content=content,
            event_key="ESTIMATE_DECISION",
            template_id=None,
        )

    def _service_email(self, *, company_id: int, branch_id: int | None) -> str:
        settings = self.repository.get_settings_map(company_id=company_id, branch_id=branch_id)
        company = self.repository.get_company(company_id=company_id)
        candidate = (
            settings.get("service_email")
            or settings.get("company_email")
            or (company.email if company else "")
            or ""
        )
        return candidate.strip()

    def _company_lines(self, *, company_id: int, branch_id: int | None) -> list[str]:
        settings = self.repository.get_settings_map(company_id=company_id, branch_id=branch_id)
        company = self.repository.get_company(company_id=company_id)

        company_name = settings.get("company_name") or (company.name if company else "SerwisPRO")
        address = settings.get("company_address") or ""
        email = settings.get("company_email") or (company.email if company else "") or ""
        phone = settings.get("company_phone") or (company.phone if company else "") or ""
        logo = settings.get("company_logo") or (company.logo if company else "") or ""

        lines = [company_name.strip()]
        if address.strip():
            lines.append(address.strip())
        if phone.strip():
            lines.append(f"Tel: {phone.strip()}")
        if email.strip():
            lines.append(f"E-mail: {email.strip()}")
        if logo.strip():
            lines.append(f"Logo: {logo.strip()}")
        return lines

    def _is_token_actionable(self, token: EstimateApprovalToken) -> bool:
        now = self._utc_now()
        return token.status == "PENDING" and token.used_at is None and self._as_utc(token.expires_at) > now

    def _token_state_message(self, token: EstimateApprovalToken) -> str:
        now = self._utc_now()
        if token.status == "PENDING" and self._as_utc(token.expires_at) > now and token.used_at is None:
            return "Link jest aktywny. Możesz podjąć decyzję dotycząca kosztorysu."
        if token.status == "ACCEPTED":
            return "Ten kosztorys został już zaakceptowany."
        if token.status == "REJECTED":
            return "Ten kosztorys został już odrzucony."
        if token.status == "EXPIRED" or self._as_utc(token.expires_at) <= now:
            return "Link do kosztorysu wygasł."
        return "Link został już wykorzystany."

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


estimate_approval_service = EstimateApprovalService()
