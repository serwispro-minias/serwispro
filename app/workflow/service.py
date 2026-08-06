from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.extensions import db
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.workflow_status import WorkflowStatus
from app.models.workflow_transition import WorkflowTransition
from app.notifications import CHANNEL_EMAIL, CHANNEL_SMS, NotificationError, NotificationService
from app.service_orders.repository import ServiceOrderRepository

from .exceptions import WorkflowNotFoundError, WorkflowPermissionError, WorkflowValidationError
from .repository import WorkflowRepository


@dataclass(slots=True)
class TransitionResult:
    order: ServiceOrder
    transition: WorkflowTransition | None
    forced: bool
    sent_channels: list[str]


DEFAULT_WORKFLOW_STATUSES: list[dict[str, object]] = [
    {"code": "RECEIVED", "name": "Przyjęte", "color": "bg-secondary", "icon": "bi-inbox", "sort_order": 10, "is_initial": True, "is_closed": False},
    {"code": "DIAGNOSIS", "name": "Diagnoza", "color": "bg-info text-dark", "icon": "bi-search", "sort_order": 20, "is_initial": False, "is_closed": False},
    {"code": "WAITING_PARTS", "name": "Oczekuje na części", "color": "bg-warning text-dark", "icon": "bi-tools", "sort_order": 30, "is_initial": False, "is_closed": False},
    {"code": "WAITING_CUSTOMER_DECISION", "name": "Oczekuje na decyzję klienta", "color": "bg-warning text-dark", "icon": "bi-hourglass-split", "sort_order": 40, "is_initial": False, "is_closed": False},
    {"code": "READY_FOR_REPAIR", "name": "Gotowe do naprawy", "color": "bg-primary-subtle text-dark", "icon": "bi-check2-circle", "sort_order": 50, "is_initial": False, "is_closed": False},
    {"code": "IN_REPAIR", "name": "W naprawie", "color": "bg-primary", "icon": "bi-wrench", "sort_order": 60, "is_initial": False, "is_closed": False},
    {"code": "READY_FOR_PICKUP", "name": "Gotowe do odbioru", "color": "bg-success", "icon": "bi-box-seam", "sort_order": 70, "is_initial": False, "is_closed": False},
    {"code": "ISSUED", "name": "Wydane", "color": "bg-dark", "icon": "bi-door-open", "sort_order": 80, "is_initial": False, "is_closed": True},
    {"code": "CLOSED", "name": "Zamknięte", "color": "bg-dark", "icon": "bi-check2-all", "sort_order": 90, "is_initial": False, "is_closed": True},
    {"code": "CANCELLED", "name": "Anulowane", "color": "bg-danger", "icon": "bi-x-octagon", "sort_order": 100, "is_initial": False, "is_closed": True},
]

DEFAULT_WORKFLOW_TRANSITIONS: list[dict[str, object]] = [
    {"from": "RECEIVED", "to": "DIAGNOSIS", "name": "Rozpocznij diagnozę", "auto_notification": True},
    {"from": "DIAGNOSIS", "to": "WAITING_PARTS", "name": "Oczekuj na części", "auto_notification": True},
    {"from": "DIAGNOSIS", "to": "WAITING_CUSTOMER_DECISION", "name": "Wyślij kosztorys", "requires_estimate": True, "auto_email": True, "auto_notification": True},
    {"from": "WAITING_PARTS", "to": "READY_FOR_REPAIR", "name": "Części dostępne", "requires_parts": True, "auto_notification": True},
    {"from": "WAITING_CUSTOMER_DECISION", "to": "READY_FOR_REPAIR", "name": "Klient zaakceptował", "requires_estimate": True, "auto_notification": True},
    {"from": "READY_FOR_REPAIR", "to": "IN_REPAIR", "name": "Rozpocznij naprawę", "auto_notification": True},
    {"from": "IN_REPAIR", "to": "READY_FOR_PICKUP", "name": "Zakończ naprawę", "requires_estimate": True, "auto_email": True, "auto_sms": True, "auto_notification": True},
    {"from": "READY_FOR_PICKUP", "to": "ISSUED", "name": "Wydaj urządzenie", "requires_payment": True, "auto_notification": True},
    {"from": "ISSUED", "to": "CLOSED", "name": "Zamknij zlecenie", "requires_permission": "administrator", "auto_notification": True},
    {"from": "RECEIVED", "to": "CANCELLED", "name": "Anuluj", "requires_permission": "administrator", "auto_notification": True},
    {"from": "DIAGNOSIS", "to": "CANCELLED", "name": "Anuluj", "requires_permission": "administrator", "auto_notification": True},
    {"from": "WAITING_PARTS", "to": "CANCELLED", "name": "Anuluj", "requires_permission": "administrator", "auto_notification": True},
    {"from": "WAITING_CUSTOMER_DECISION", "to": "CANCELLED", "name": "Anuluj", "requires_permission": "administrator", "auto_notification": True},
]


class WorkflowService:
    def __init__(
        self,
        repository: WorkflowRepository | None = None,
        order_repository: ServiceOrderRepository | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.repository = repository or WorkflowRepository()
        self.order_repository = order_repository or ServiceOrderRepository()
        self.notification_service = notification_service or NotificationService()

    def ensure_default_workflow(self, *, company_id: int, branch_id: int | None, user_id: int | None = None) -> None:
        if self.repository.has_statuses(company_id=company_id, branch_id=branch_id):
            return

        statuses_by_code: dict[str, WorkflowStatus] = {}
        for row in DEFAULT_WORKFLOW_STATUSES:
            status = WorkflowStatus(
                company_id=company_id,
                branch_id=branch_id,
                name=str(row["name"]),
                code=str(row["code"]),
                description=str(row.get("name") or ""),
                color=str(row.get("color") or "bg-secondary"),
                icon=str(row.get("icon") or "bi-circle"),
                sort_order=int(row.get("sort_order") or 0),
                is_initial=bool(row.get("is_initial")),
                is_closed=bool(row.get("is_closed")),
                created_by=user_id,
                updated_by=user_id,
            )
            self.repository.create_status(status)
            statuses_by_code[status.code] = status

        for row in DEFAULT_WORKFLOW_TRANSITIONS:
            from_code = str(row["from"])
            to_code = str(row["to"])
            transition = WorkflowTransition(
                company_id=company_id,
                branch_id=branch_id,
                from_status_id=statuses_by_code[from_code].id,
                to_status_id=statuses_by_code[to_code].id,
                name=str(row["name"]),
                requires_permission=(str(row["requires_permission"]).strip() if row.get("requires_permission") else None),
                requires_estimate=bool(row.get("requires_estimate")),
                requires_parts=bool(row.get("requires_parts")),
                requires_payment=bool(row.get("requires_payment")),
                auto_email=bool(row.get("auto_email")),
                auto_sms=bool(row.get("auto_sms")),
                auto_notification=bool(row.get("auto_notification", True)),
                created_by=user_id,
                updated_by=user_id,
            )
            self.repository.create_transition(transition)

        db.session.commit()

    def get_status_choices(self, *, company_id: int, branch_id: int | None) -> list[tuple[str, str]]:
        statuses = self.repository.list_statuses(company_id=company_id, branch_id=branch_id)
        return [(status.code, status.name) for status in statuses]

    def get_status_labels(self, *, company_id: int, branch_id: int | None) -> dict[str, str]:
        return {status.code: status.name for status in self.repository.list_statuses(company_id=company_id, branch_id=branch_id)}

    def get_status_badges(self, *, company_id: int, branch_id: int | None) -> dict[str, str]:
        return {status.code: status.color for status in self.repository.list_statuses(company_id=company_id, branch_id=branch_id)}

    def get_available_transitions(
        self,
        *,
        order: ServiceOrder,
        company_id: int,
        branch_id: int | None,
        actor,
    ) -> list[dict[str, str | bool]]:
        status = self.repository.get_status_by_code(company_id=company_id, branch_id=branch_id, code=order.status)
        if status is None:
            return []

        rows: list[dict[str, str | bool]] = []
        for transition in self.repository.list_transitions_from_status(
            company_id=company_id,
            branch_id=branch_id,
            from_status_id=status.id,
        ):
            allowed = True
            reason = ""
            try:
                self._authorize_transition(actor=actor, transition=transition, forced=False)
                self._validate_business_rules(order=order, target_status_code=transition.to_status.code, transition=transition)
            except (WorkflowPermissionError, WorkflowValidationError) as exc:
                allowed = False
                reason = str(exc)

            rows.append(
                {
                    "to_status": transition.to_status.code,
                    "to_name": transition.to_status.name,
                    "name": transition.name,
                    "allowed": allowed,
                    "reason": reason,
                }
            )
        return rows

    def change_order_status(
        self,
        *,
        order_id: int,
        target_status_code: str,
        company_id: int,
        branch_id: int | None,
        actor,
        note: str | None,
        ip_address: str | None,
        force: bool,
    ) -> TransitionResult:
        order = self.order_repository.get_by_id(order_id, company_id=company_id)
        if order is None:
            raise WorkflowNotFoundError("Nie znaleziono zlecenia.")

        if order.status == target_status_code:
            raise WorkflowValidationError("Nowy status jest taki sam jak aktualny.")

        transition = self.repository.get_transition_by_codes(
            company_id=company_id,
            branch_id=branch_id,
            from_status_code=order.status,
            to_status_code=target_status_code,
        )
        is_admin = self._is_admin(actor)
        forced = bool(force and is_admin)

        if transition is None and not forced:
            raise WorkflowValidationError("Nie znaleziono dozwolonego przejścia między statusami.")

        if transition is not None:
            self._authorize_transition(actor=actor, transition=transition, forced=forced)
            self._validate_business_rules(order=order, target_status_code=target_status_code, transition=transition)
        elif not forced:
            raise WorkflowValidationError("Przejście jest niedostępne.")

        previous = order.status
        order.status = target_status_code
        order.updated_by = getattr(actor, "id", None)
        if target_status_code in {"ISSUED", "CLOSED"} and order.finished_at is None:
            order.finished_at = datetime.now(timezone.utc)

        db.session.add(order)
        db.session.flush()

        self.order_repository.create_status_history(
            service_order_id=order.id,
            old_status=previous,
            new_status=target_status_code,
            changed_by=getattr(actor, "id", None),
            note=(f"[FORCE] {note}" if forced and note else ("[FORCE] Zmiana wymuszona przez administratora" if forced else note)),
            ip_address=ip_address,
        )

        sent_channels: list[str] = []
        if transition is not None and transition.auto_notification:
            action = ServiceOrderAction(
                company_id=company_id,
                branch_id=branch_id,
                service_order_id=order.id,
                action_date=date.today(),
                technician_id=getattr(actor, "id", None),
                action_type="OTHER",
                description=f"Workflow: {transition.name} ({previous} -> {target_status_code})",
                is_visible_for_customer=False,
                created_by=getattr(actor, "id", None),
                updated_by=getattr(actor, "id", None),
            )
            db.session.add(action)

        if transition is not None and (transition.auto_email or transition.auto_sms):
            sent_channels = self._send_auto_notifications(
                order=order,
                transition=transition,
                company_id=company_id,
                branch_id=branch_id,
                actor_id=getattr(actor, "id", None),
            )

        self._create_automatic_tasks_for_status(
            order=order,
            actor_id=getattr(actor, "id", None),
        )

        db.session.commit()
        return TransitionResult(order=order, transition=transition, forced=forced, sent_channels=sent_channels)

    def create_status(self, *, company_id: int, branch_id: int | None, user_id: int | None, data: dict[str, object]) -> WorkflowStatus:
        code = str(data.get("code") or "").strip().upper()
        name = str(data.get("name") or "").strip()
        if not code or not name:
            raise WorkflowValidationError("Kod i nazwa statusu są wymagane.")
        existing = self.repository.get_status_by_code(company_id=company_id, branch_id=branch_id, code=code)
        if existing is not None:
            raise WorkflowValidationError("Status o podanym kodzie już istnieje.")

        status = WorkflowStatus(
            company_id=company_id,
            branch_id=branch_id,
            code=code,
            name=name,
            description=str(data.get("description") or "").strip() or None,
            color=str(data.get("color") or "bg-secondary"),
            icon=str(data.get("icon") or "bi-circle"),
            sort_order=int(data.get("sort_order") or 0),
            is_initial=bool(data.get("is_initial")),
            is_closed=bool(data.get("is_closed")),
            created_by=user_id,
            updated_by=user_id,
        )
        if status.is_initial:
            for row in self.repository.list_statuses(company_id=company_id, branch_id=branch_id):
                row.is_initial = False
                db.session.add(row)

        self.repository.create_status(status)
        db.session.commit()
        return status

    def create_transition(self, *, company_id: int, branch_id: int | None, user_id: int | None, data: dict[str, object]) -> WorkflowTransition:
        from_code = str(data.get("from_status_code") or "").strip().upper()
        to_code = str(data.get("to_status_code") or "").strip().upper()
        name = str(data.get("name") or "").strip()
        if not from_code or not to_code or not name:
            raise WorkflowValidationError("Status źródłowy, docelowy i nazwa przejścia są wymagane.")
        if from_code == to_code:
            raise WorkflowValidationError("Przejście musi wskazywać inny status docelowy.")

        from_status = self.repository.get_status_by_code(company_id=company_id, branch_id=branch_id, code=from_code)
        to_status = self.repository.get_status_by_code(company_id=company_id, branch_id=branch_id, code=to_code)
        if from_status is None or to_status is None:
            raise WorkflowValidationError("Wskazane statusy nie istnieją.")

        existing = self.repository.get_transition_by_codes(
            company_id=company_id,
            branch_id=branch_id,
            from_status_code=from_code,
            to_status_code=to_code,
        )
        if existing is not None:
            raise WorkflowValidationError("Takie przejście już istnieje.")

        transition = WorkflowTransition(
            company_id=company_id,
            branch_id=branch_id,
            from_status_id=from_status.id,
            to_status_id=to_status.id,
            name=name,
            requires_permission=(str(data.get("requires_permission") or "").strip() or None),
            requires_estimate=bool(data.get("requires_estimate")),
            requires_parts=bool(data.get("requires_parts")),
            requires_payment=bool(data.get("requires_payment")),
            auto_email=bool(data.get("auto_email")),
            auto_sms=bool(data.get("auto_sms")),
            auto_notification=bool(data.get("auto_notification", True)),
            created_by=user_id,
            updated_by=user_id,
        )
        self.repository.create_transition(transition)
        db.session.commit()
        return transition

    def _authorize_transition(self, *, actor, transition: WorkflowTransition, forced: bool) -> None:
        if forced:
            return
        required = (transition.requires_permission or "").strip()
        if not required:
            return
        if self._is_admin(actor):
            return

        required_lower = required.lower()
        role_names = {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}
        if required_lower in role_names:
            return

        permission_names: set[str] = set()
        for role in getattr(actor, "roles", []):
            for permission in getattr(role, "permissions", []):
                permission_names.add((permission.name or "").strip().lower())
        if required_lower in permission_names:
            return

        raise WorkflowPermissionError("Brak wymaganych uprawnień do wykonania tego przejścia.")

    def _validate_business_rules(self, *, order: ServiceOrder, target_status_code: str, transition: WorkflowTransition | None) -> None:
        if target_status_code == "IN_REPAIR":
            has_technician_action = any(action.technician_id is not None for action in order.actions)
            if not has_technician_action:
                raise WorkflowValidationError("Nie można rozpocząć naprawy bez przypisanego technika w historii działań.")

        if target_status_code == "ISSUED":
            if order.status != "READY_FOR_PICKUP":
                raise WorkflowValidationError("Nie można wydać urządzenia bez statusu gotowe do odbioru.")

        if target_status_code in {"READY_FOR_PICKUP", "ISSUED"}:
            has_repair_activity = any((action.action_type or "").upper() in {"REPAIR", "TESTS"} for action in order.actions)
            if not has_repair_activity:
                raise WorkflowValidationError("Nie można wydać urządzenia bez zakończenia czynności naprawczych.")
            if order.estimates:
                latest_estimate = sorted(order.estimates, key=lambda row: (row.version_number, row.id))[-1]
                if latest_estimate.status not in {"ACCEPTED", "APPROVED"}:
                    raise WorkflowValidationError("Nie można wydać urządzenia bez zaakceptowanego kosztorysu.")

        if target_status_code == "CLOSED":
            open_reservations = [item for item in order.part_reservations if (item.status or "").upper() != "RETURNED"]
            if open_reservations:
                raise WorkflowValidationError("Nie można zamknąć zlecenia z nierozliczonymi rezerwacjami części.")

        if transition is not None and transition.requires_parts and len(order.part_usages) == 0:
            raise WorkflowValidationError("To przejście wymaga zużycia co najmniej jednej części.")

        if transition is not None and transition.requires_payment:
            if order.final_cost is None:
                raise WorkflowValidationError("To przejście wymaga ustawienia finalnej kwoty zlecenia.")

    def _send_auto_notifications(
        self,
        *,
        order: ServiceOrder,
        transition: WorkflowTransition,
        company_id: int,
        branch_id: int | None,
        actor_id: int | None,
    ) -> list[str]:
        sent_channels: list[str] = []
        channels: list[str] = []
        if transition.auto_email:
            channels.append(CHANNEL_EMAIL)
        if transition.auto_sms:
            channels.append(CHANNEL_SMS)

        for channel in channels:
            drafts = self.notification_service.draft_for_status_change(
                order_id=order.id,
                new_status=order.status,
                company_id=company_id,
                branch_id=branch_id,
            )
            draft = next((row for row in drafts if row.channel == channel), None)
            if draft is None:
                continue
            try:
                message = self.notification_service.send_draft(
                    order_id=order.id,
                    company_id=company_id,
                    branch_id=branch_id,
                    user_id=actor_id,
                    channel=draft.channel,
                    recipient=draft.recipient,
                    subject=draft.subject,
                    content=draft.content,
                    event_key=draft.event_key,
                    template_id=draft.template_id,
                )
            except NotificationError:
                continue
            if message.status == "SENT":
                sent_channels.append(channel)

        return sent_channels

    def _create_automatic_tasks_for_status(self, *, order: ServiceOrder, actor_id: int | None) -> None:
        # Lazy import to avoid cross-module import cycle during app startup.
        from app.technician_tasks.service import ServiceTaskService

        ServiceTaskService().create_automatic_tasks_for_workflow_status(
            order=order,
            status_code=order.status,
            actor_id=actor_id,
        )

    @staticmethod
    def _is_admin(actor) -> bool:
        return any((role.name or "").strip().lower() == "administrator" for role in getattr(actor, "roles", []))
