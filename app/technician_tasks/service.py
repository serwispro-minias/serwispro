from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_task import (
    SERVICE_TASK_PRIORITY_CHOICES,
    SERVICE_TASK_PRIORITY_LABELS,
    SERVICE_TASK_STATUS_CHOICES,
    SERVICE_TASK_STATUS_LABELS,
    SERVICE_TASK_TYPE_CHOICES,
    SERVICE_TASK_TYPE_LABELS,
    ServiceTask,
    ServiceTaskPriorityEnum,
    ServiceTaskStatusEnum,
    ServiceTaskTypeEnum,
)
from app.models.service_task_attachment import ServiceTaskAttachment
from app.models.service_task_comment import ServiceTaskComment
from app.models.service_task_status_history import ServiceTaskStatusHistory
from app.models.service_task_time_entry import ServiceTaskTimeEntry

from .exceptions import ServiceTaskNotFoundError, ServiceTaskPermissionError, ServiceTaskValidationError
from .repository import ServiceTaskRepository

ALLOWED_TASK_ATTACHMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".txt", ".log"}


@dataclass(slots=True)
class ServiceTaskDashboardData:
    my_tasks: list[ServiceTask]
    team_tasks: list[ServiceTask]
    overdue_tasks: list[ServiceTask]
    today_tasks: list[ServiceTask]
    tomorrow_tasks: list[ServiceTask]
    priority_groups: dict[str, list[ServiceTask]]


class ServiceTaskService:
    def __init__(self, repository: ServiceTaskRepository | None = None) -> None:
        self.repository = repository or ServiceTaskRepository()

    def get_status_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_TASK_STATUS_CHOICES)

    def get_priority_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_TASK_PRIORITY_CHOICES)

    def get_type_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_TASK_TYPE_CHOICES)

    def get_status_labels(self) -> dict[str, str]:
        return dict(SERVICE_TASK_STATUS_LABELS)

    def get_priority_labels(self) -> dict[str, str]:
        return dict(SERVICE_TASK_PRIORITY_LABELS)

    def get_type_labels(self) -> dict[str, str]:
        return dict(SERVICE_TASK_TYPE_LABELS)

    def get_technician_choices(self, *, company_id: int, branch_id: int | None) -> list[tuple[int, str]]:
        rows = self.repository.list_technicians(company_id=company_id, branch_id=branch_id)
        choices: list[tuple[int, str]] = [(0, "- nieprzypisane -")]
        for user in rows:
            full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
            label = full_name or user.login or f"Użytkownik #{user.id}"
            choices.append((user.id, label))
        return choices

    def get_parent_task_choices(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        exclude_task_id: int | None = None,
    ) -> list[tuple[int, str]]:
        rows = self.repository.list_parent_choices(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            exclude_task_id=exclude_task_id,
        )
        choices: list[tuple[int, str]] = [(0, "- brak -")]
        choices.extend([(row.id, row.title) for row in rows])
        return choices

    def list_for_order(self, *, order_id: int, company_id: int, branch_id: int | None, actor) -> list[ServiceTask]:
        self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        rows = self.repository.list_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        if self._is_manager(actor):
            return rows
        return [row for row in rows if row.assigned_to == getattr(actor, "id", None) or row.created_by == getattr(actor, "id", None)]

    def get_task(self, *, task_id: int, company_id: int, branch_id: int | None, actor) -> ServiceTask:
        task = self.repository.get_by_id(task_id=task_id, company_id=company_id, branch_id=branch_id)
        if task is None:
            raise ServiceTaskNotFoundError("Nie znaleziono zadania.")
        self._assert_can_view(task=task, actor=actor)
        return task

    def create_task(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        actor,
        data: dict[str, object],
    ) -> ServiceTask:
        order = self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        assigned_to = self._normalize_assignee(data.get("assigned_to"), company_id=company_id, branch_id=branch_id)

        if not self._is_manager(actor) and assigned_to not in (None, getattr(actor, "id", None)):
            raise ServiceTaskPermissionError("Technik może tworzyć tylko zadania przypisane do siebie.")

        payload = self._normalize_task_payload(data, company_id=company_id, branch_id=order.branch_id)
        payload["service_order_id"] = order.id
        payload["assigned_to"] = assigned_to
        payload["created_by"] = getattr(actor, "id", None)
        payload["updated_by"] = getattr(actor, "id", None)

        if payload["status"] == ServiceTaskStatusEnum.DONE.value:
            payload["finished_at"] = datetime.now(timezone.utc)
            payload["completion_percent"] = 100

        task = self.repository.create_task(payload)
        self._create_status_history(
            task=task,
            old_status=None,
            new_status=task.status,
            actor_id=getattr(actor, "id", None),
            note="Utworzono zadanie",
        )

        if assigned_to is not None:
            self._emit_task_notification(order_id=order.id, company_id=company_id, branch_id=order.branch_id, actor_id=getattr(actor, "id", None), description=f"Zadanie #{task.id} przypisano do technika #{assigned_to}: {task.title}")

        self._notify_overdue_tasks_once(company_id=company_id, branch_id=order.branch_id, actor_id=getattr(actor, "id", None))
        db.session.commit()
        return self.repository.get_by_id(task_id=task.id, company_id=company_id, branch_id=order.branch_id) or task

    def update_task(
        self,
        *,
        task_id: int,
        company_id: int,
        branch_id: int | None,
        actor,
        data: dict[str, object],
    ) -> ServiceTask:
        task = self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)
        previous_assignee = task.assigned_to
        previous_status = task.status

        assigned_to = self._normalize_assignee(data.get("assigned_to"), company_id=company_id, branch_id=branch_id)
        payload = self._normalize_task_payload(data, company_id=company_id, branch_id=task.branch_id)

        if not self._is_manager(actor):
            if task.assigned_to != getattr(actor, "id", None):
                raise ServiceTaskPermissionError("Brak uprawnień do edycji tego zadania.")
            disallowed_keys = {"assigned_to", "priority", "planned_start", "planned_finish", "estimated_minutes"}
            if any(key in data for key in disallowed_keys):
                raise ServiceTaskPermissionError("Technik nie może zmieniać przypisania, priorytetu ani planu zadania.")

        payload["assigned_to"] = assigned_to
        payload["updated_by"] = getattr(actor, "id", None)

        if payload.get("status") == ServiceTaskStatusEnum.DONE.value and task.finished_at is None:
            payload["finished_at"] = datetime.now(timezone.utc)
            payload["completion_percent"] = 100

        task = self.repository.update_task(task, payload)

        if previous_status != task.status:
            self._create_status_history(
                task=task,
                old_status=previous_status,
                new_status=task.status,
                actor_id=getattr(actor, "id", None),
                note="Aktualizacja zadania",
            )
            self._emit_task_notification(
                order_id=task.service_order_id,
                company_id=task.company_id,
                branch_id=task.branch_id,
                actor_id=getattr(actor, "id", None),
                description=f"Zmieniono status zadania #{task.id}: {previous_status} -> {task.status}",
            )

        if previous_assignee != task.assigned_to and task.assigned_to is not None:
            self._emit_task_notification(
                order_id=task.service_order_id,
                company_id=task.company_id,
                branch_id=task.branch_id,
                actor_id=getattr(actor, "id", None),
                description=f"Zadanie #{task.id} przypisano do technika #{task.assigned_to}: {task.title}",
            )

        self._notify_overdue_tasks_once(company_id=task.company_id, branch_id=task.branch_id, actor_id=getattr(actor, "id", None))
        db.session.commit()
        return self.repository.get_by_id(task_id=task.id, company_id=company_id, branch_id=task.branch_id) or task

    def delete_task(self, *, task_id: int, company_id: int, branch_id: int | None, actor) -> None:
        task = self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)
        if not self._is_manager(actor):
            raise ServiceTaskPermissionError("Usuwanie zadań wymaga roli kierownika lub administratora.")
        self.repository.delete_task(task)
        db.session.commit()

    def change_status(
        self,
        *,
        task_id: int,
        new_status: str,
        note: str | None,
        completion_percent: int | None,
        company_id: int,
        branch_id: int | None,
        actor,
    ) -> ServiceTask:
        task = self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)
        normalized = (new_status or "").strip().upper()
        if normalized not in SERVICE_TASK_STATUS_LABELS:
            raise ServiceTaskValidationError("Nieprawidłowy status zadania.")
        if not self._can_change_status(actor=actor, task=task):
            raise ServiceTaskPermissionError("Brak uprawnień do zmiany statusu tego zadania.")

        old_status = task.status
        if old_status == normalized and completion_percent is None:
            raise ServiceTaskValidationError("Nowy status jest taki sam jak aktualny.")

        payload: dict[str, object] = {
            "status": normalized,
            "updated_by": getattr(actor, "id", None),
        }

        if completion_percent is not None:
            payload["completion_percent"] = max(0, min(100, int(completion_percent)))

        if normalized == ServiceTaskStatusEnum.IN_PROGRESS.value and task.started_at is None:
            payload["started_at"] = datetime.now(timezone.utc)
        if normalized == ServiceTaskStatusEnum.DONE.value:
            payload["finished_at"] = datetime.now(timezone.utc)
            payload["completion_percent"] = 100
        if normalized == ServiceTaskStatusEnum.CANCELLED.value and completion_percent is None:
            payload["completion_percent"] = task.completion_percent

        task = self.repository.update_task(task, payload)
        self._create_status_history(
            task=task,
            old_status=old_status,
            new_status=normalized,
            actor_id=getattr(actor, "id", None),
            note=(note or "").strip() or None,
        )
        self._emit_task_notification(
            order_id=task.service_order_id,
            company_id=task.company_id,
            branch_id=task.branch_id,
            actor_id=getattr(actor, "id", None),
            description=f"Zmieniono status zadania #{task.id}: {old_status} -> {normalized}",
        )
        self._notify_overdue_tasks_once(company_id=task.company_id, branch_id=task.branch_id, actor_id=getattr(actor, "id", None))
        db.session.commit()
        return self.repository.get_by_id(task_id=task.id, company_id=company_id, branch_id=task.branch_id) or task

    def add_comment(
        self,
        *,
        task_id: int,
        content: str,
        company_id: int,
        branch_id: int | None,
        actor,
    ) -> ServiceTaskComment:
        task = self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)
        normalized = (content or "").strip()
        if not normalized:
            raise ServiceTaskValidationError("Komentarz nie może być pusty.")

        row = self.repository.create_comment(
            {
                "service_task_id": task.id,
                "author_id": getattr(actor, "id", None),
                "content": normalized,
                "company_id": task.company_id,
                "branch_id": task.branch_id,
                "created_by": getattr(actor, "id", None),
                "updated_by": getattr(actor, "id", None),
            }
        )
        db.session.commit()
        return row

    def add_attachment(
        self,
        *,
        task_id: int,
        file_storage: FileStorage,
        upload_root: Path,
        company_id: int,
        branch_id: int | None,
        actor,
    ) -> ServiceTaskAttachment:
        task = self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)

        if file_storage is None or not (file_storage.filename or "").strip():
            raise ServiceTaskValidationError("Wybierz plik załącznika.")

        original_filename = (file_storage.filename or "").strip()
        safe_name = secure_filename(original_filename)
        if not safe_name:
            raise ServiceTaskValidationError("Nieprawidłowa nazwa pliku.")

        _, extension = os.path.splitext(safe_name)
        extension = extension.lower()
        if extension not in ALLOWED_TASK_ATTACHMENT_EXTENSIONS:
            raise ServiceTaskValidationError("Niedozwolony format załącznika.")

        storage_dir = upload_root / "service_tasks" / str(task.id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid4().hex}{extension}"
        target = storage_dir / stored_filename
        file_storage.save(target)

        file_size: int | None
        try:
            file_size = target.stat().st_size
        except OSError:
            file_size = None

        row = self.repository.create_attachment(
            {
                "service_task_id": task.id,
                "uploaded_by": getattr(actor, "id", None),
                "original_filename": original_filename,
                "stored_filename": stored_filename,
                "relative_path": str(Path("service_tasks") / str(task.id) / stored_filename),
                "content_type": file_storage.content_type,
                "file_size": file_size,
                "company_id": task.company_id,
                "branch_id": task.branch_id,
                "created_by": getattr(actor, "id", None),
                "updated_by": getattr(actor, "id", None),
            }
        )
        db.session.commit()
        return row

    def get_attachment(
        self,
        *,
        task_id: int,
        attachment_id: int,
        company_id: int,
        branch_id: int | None,
        actor,
    ) -> ServiceTaskAttachment:
        self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)
        row = self.repository.get_attachment(attachment_id=attachment_id, company_id=company_id, branch_id=branch_id)
        if row is None or row.service_task_id != task_id:
            raise ServiceTaskNotFoundError("Nie znaleziono załącznika.")
        return row

    def resolve_attachment_path(self, *, upload_root: Path, attachment: ServiceTaskAttachment) -> Path:
        full_path = upload_root / attachment.relative_path
        if not full_path.exists() or not full_path.is_file():
            raise ServiceTaskNotFoundError("Plik załącznika nie istnieje.")
        return full_path

    def start_work(self, *, task_id: int, note: str | None, company_id: int, branch_id: int | None, actor) -> ServiceTask:
        task = self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)
        self._assert_can_log_time(task=task, actor=actor)

        if self.repository.get_open_time_entry(task_id=task.id, user_id=getattr(actor, "id", None)) is not None:
            raise ServiceTaskValidationError("Masz już aktywną sesję pracy dla tego zadania.")

        now = datetime.now(timezone.utc)
        self.repository.create_time_entry(
            {
                "service_task_id": task.id,
                "user_id": getattr(actor, "id", None),
                "started_at": now,
                "ended_at": None,
                "duration_minutes": None,
                "action": "START",
                "note": (note or "").strip() or None,
                "company_id": task.company_id,
                "branch_id": task.branch_id,
                "created_by": getattr(actor, "id", None),
                "updated_by": getattr(actor, "id", None),
            }
        )

        updates: dict[str, object] = {"updated_by": getattr(actor, "id", None)}
        if task.started_at is None:
            updates["started_at"] = now
        if task.status in {ServiceTaskStatusEnum.NEW.value, ServiceTaskStatusEnum.ASSIGNED.value, ServiceTaskStatusEnum.WAITING.value}:
            old_status = task.status
            updates["status"] = ServiceTaskStatusEnum.IN_PROGRESS.value
            self.repository.update_task(task, updates)
            self._create_status_history(
                task=task,
                old_status=old_status,
                new_status=ServiceTaskStatusEnum.IN_PROGRESS.value,
                actor_id=getattr(actor, "id", None),
                note="Start pracy",
            )
        else:
            self.repository.update_task(task, updates)

        db.session.commit()
        return self.repository.get_by_id(task_id=task.id, company_id=company_id, branch_id=task.branch_id) or task

    def pause_work(self, *, task_id: int, note: str | None, company_id: int, branch_id: int | None, actor) -> ServiceTask:
        task = self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)
        self._assert_can_log_time(task=task, actor=actor)

        entry = self.repository.get_open_time_entry(task_id=task.id, user_id=getattr(actor, "id", None))
        if entry is None:
            raise ServiceTaskValidationError("Brak aktywnej sesji pracy do wstrzymania.")

        self._close_time_entry(entry=entry, action="PAUSE", note=note, actor_id=getattr(actor, "id", None))
        worked_minutes = self._calculate_worked_minutes(task.id)
        self.repository.update_task(
            task,
            {
                "worked_minutes": worked_minutes,
                "status": ServiceTaskStatusEnum.WAITING.value,
                "updated_by": getattr(actor, "id", None),
            },
        )
        self._create_status_history(
            task=task,
            old_status=task.status,
            new_status=ServiceTaskStatusEnum.WAITING.value,
            actor_id=getattr(actor, "id", None),
            note="Wstrzymano pracę",
        )
        db.session.commit()
        return self.repository.get_by_id(task_id=task.id, company_id=company_id, branch_id=task.branch_id) or task

    def resume_work(self, *, task_id: int, note: str | None, company_id: int, branch_id: int | None, actor) -> ServiceTask:
        return self.start_work(task_id=task_id, note=note, company_id=company_id, branch_id=branch_id, actor=actor)

    def finish_work(self, *, task_id: int, note: str | None, company_id: int, branch_id: int | None, actor) -> ServiceTask:
        task = self.get_task(task_id=task_id, company_id=company_id, branch_id=branch_id, actor=actor)
        self._assert_can_log_time(task=task, actor=actor)

        entry = self.repository.get_open_time_entry(task_id=task.id, user_id=getattr(actor, "id", None))
        if entry is not None:
            self._close_time_entry(entry=entry, action="FINISH", note=note, actor_id=getattr(actor, "id", None))

        worked_minutes = self._calculate_worked_minutes(task.id)
        old_status = task.status
        self.repository.update_task(
            task,
            {
                "worked_minutes": worked_minutes,
                "status": ServiceTaskStatusEnum.DONE.value,
                "finished_at": datetime.now(timezone.utc),
                "completion_percent": 100,
                "updated_by": getattr(actor, "id", None),
            },
        )
        self._create_status_history(
            task=task,
            old_status=old_status,
            new_status=ServiceTaskStatusEnum.DONE.value,
            actor_id=getattr(actor, "id", None),
            note=(note or "").strip() or "Zakończono pracę",
        )
        db.session.commit()
        return self.repository.get_by_id(task_id=task.id, company_id=company_id, branch_id=task.branch_id) or task

    def build_dashboard(self, *, company_id: int, branch_id: int | None, actor) -> ServiceTaskDashboardData:
        actor_id = getattr(actor, "id", None)
        my_tasks = self.repository.list_my_tasks(actor_id=actor_id, company_id=company_id, branch_id=branch_id) if actor_id is not None else []

        if self._is_manager(actor):
            team_tasks = self.repository.list_team_tasks(company_id=company_id, branch_id=branch_id)
        else:
            team_tasks = list(my_tasks)

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        day_after_tomorrow = tomorrow_start + timedelta(days=1)

        open_statuses = {ServiceTaskStatusEnum.NEW.value, ServiceTaskStatusEnum.ASSIGNED.value, ServiceTaskStatusEnum.IN_PROGRESS.value, ServiceTaskStatusEnum.WAITING.value}
        overdue_tasks = [
            row
            for row in team_tasks
            if row.status in open_statuses and row.planned_finish is not None and row.planned_finish < now
        ]
        today_tasks = [
            row
            for row in team_tasks
            if row.status in open_statuses and row.planned_finish is not None and today_start <= row.planned_finish < tomorrow_start
        ]
        tomorrow_tasks = [
            row
            for row in team_tasks
            if row.status in open_statuses and row.planned_finish is not None and tomorrow_start <= row.planned_finish < day_after_tomorrow
        ]

        priority_groups: dict[str, list[ServiceTask]] = {key: [] for key, _ in SERVICE_TASK_PRIORITY_CHOICES}
        for row in team_tasks:
            priority_groups.setdefault(row.priority, []).append(row)

        self._notify_overdue_tasks_once(company_id=company_id, branch_id=branch_id, actor_id=actor_id)
        db.session.commit()

        return ServiceTaskDashboardData(
            my_tasks=my_tasks,
            team_tasks=team_tasks,
            overdue_tasks=overdue_tasks,
            today_tasks=today_tasks,
            tomorrow_tasks=tomorrow_tasks,
            priority_groups=priority_groups,
        )

    def search_tasks(
        self,
        *,
        company_id: int,
        branch_id: int | None,
        actor,
        query_text: str | None,
        status: str | None,
        priority: str | None,
        assigned_to: int | None,
    ) -> list[ServiceTask]:
        return self.repository.search_tasks(
            company_id=company_id,
            branch_id=branch_id,
            actor_id=getattr(actor, "id", None),
            only_mine=not self._is_manager(actor),
            query_text=query_text,
            status=status,
            priority=priority,
            assigned_to=(assigned_to if self._is_manager(actor) else getattr(actor, "id", None)),
        )

    def create_automatic_tasks_for_workflow_status(
        self,
        *,
        order: ServiceOrder,
        status_code: str,
        actor_id: int | None,
    ) -> list[ServiceTask]:
        mappings: dict[str, tuple[str, str, str]] = {
            "DIAGNOSIS": ("Wykonaj diagnozę", ServiceTaskTypeEnum.DIAGNOSIS.value, ServiceTaskPriorityEnum.NORMAL.value),
            "WAITING_PARTS": ("Przygotuj/zamów części", ServiceTaskTypeEnum.PARTS_ORDER.value, ServiceTaskPriorityEnum.HIGH.value),
            "IN_REPAIR": ("Wykonaj naprawę", ServiceTaskTypeEnum.REPAIR.value, ServiceTaskPriorityEnum.HIGH.value),
            "READY_FOR_PICKUP": ("Wykonaj testy końcowe", ServiceTaskTypeEnum.TESTS.value, ServiceTaskPriorityEnum.NORMAL.value),
            "ISSUED": ("Przygotuj wydanie urządzenia", ServiceTaskTypeEnum.PICKUP.value, ServiceTaskPriorityEnum.NORMAL.value),
        }
        mapped = mappings.get((status_code or "").strip().upper())
        if mapped is None:
            return []

        title, task_type, priority = mapped
        existing = self.repository.find_open_task_by_title(
            order_id=order.id,
            company_id=order.company_id,
            branch_id=order.branch_id,
            title=title,
        )
        if existing is not None:
            return []

        payload = {
            "service_order_id": order.id,
            "parent_task_id": None,
            "title": title,
            "description": f"Zadanie utworzone automatycznie po zmianie statusu zlecenia na {status_code}.",
            "task_type": task_type,
            "status": ServiceTaskStatusEnum.NEW.value,
            "priority": priority,
            "assigned_to": None,
            "planned_start": None,
            "planned_finish": None,
            "started_at": None,
            "finished_at": None,
            "estimated_minutes": None,
            "worked_minutes": 0,
            "completion_percent": 0,
            "requires_confirmation": False,
            "company_id": order.company_id,
            "branch_id": order.branch_id,
            "created_by": actor_id,
            "updated_by": actor_id,
        }
        task = self.repository.create_task(payload)
        self._create_status_history(
            task=task,
            old_status=None,
            new_status=ServiceTaskStatusEnum.NEW.value,
            actor_id=actor_id,
            note="Utworzono automatycznie przez workflow",
        )
        return [task]

    def _normalize_task_payload(self, data: dict[str, object], *, company_id: int, branch_id: int | None) -> dict[str, object]:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ServiceTaskValidationError("Tytuł zadania jest wymagany.")

        task_type = str(data.get("task_type") or "").strip().upper()
        if task_type not in SERVICE_TASK_TYPE_LABELS:
            raise ServiceTaskValidationError("Wybierz poprawny typ zadania.")

        status = str(data.get("status") or ServiceTaskStatusEnum.NEW.value).strip().upper()
        if status not in SERVICE_TASK_STATUS_LABELS:
            raise ServiceTaskValidationError("Wybierz poprawny status zadania.")

        priority = str(data.get("priority") or ServiceTaskPriorityEnum.NORMAL.value).strip().upper()
        if priority not in SERVICE_TASK_PRIORITY_LABELS:
            raise ServiceTaskValidationError("Wybierz poprawny priorytet zadania.")

        completion_percent_raw = data.get("completion_percent")
        if completion_percent_raw in (None, ""):
            completion_percent = 0
        else:
            completion_percent = max(0, min(100, int(completion_percent_raw)))

        estimated_minutes_raw = data.get("estimated_minutes")
        if estimated_minutes_raw in (None, ""):
            estimated_minutes = None
        else:
            estimated_minutes = int(estimated_minutes_raw)
            if estimated_minutes < 0:
                raise ServiceTaskValidationError("Szacowany czas nie może być ujemny.")

        parent_task_id = self._normalize_optional_int(data.get("parent_task_id"))
        if parent_task_id is not None and parent_task_id <= 0:
            parent_task_id = None

        planned_start = self._normalize_datetime(data.get("planned_start"))
        planned_finish = self._normalize_datetime(data.get("planned_finish"))
        if planned_start is not None and planned_finish is not None and planned_finish < planned_start:
            raise ServiceTaskValidationError("Planowany koniec nie może być wcześniejszy niż planowany start.")

        return {
            "parent_task_id": parent_task_id,
            "title": title,
            "description": (str(data.get("description") or "").strip() or None),
            "task_type": task_type,
            "status": status,
            "priority": priority,
            "planned_start": planned_start,
            "planned_finish": planned_finish,
            "estimated_minutes": estimated_minutes,
            "completion_percent": completion_percent,
            "requires_confirmation": bool(data.get("requires_confirmation")),
            "company_id": company_id,
            "branch_id": branch_id,
        }

    def _normalize_assignee(self, value: object, *, company_id: int, branch_id: int | None) -> int | None:
        assignee = self._normalize_optional_int(value)
        if assignee in (None, 0):
            return None

        valid_ids = {row.id for row in self.repository.list_technicians(company_id=company_id, branch_id=branch_id)}
        if assignee not in valid_ids:
            raise ServiceTaskValidationError("Wybrany technik jest nieprawidłowy.")
        return assignee

    def _normalize_optional_int(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _normalize_datetime(self, value: object) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        text = str(value).strip()
        if not text:
            return None
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _calculate_worked_minutes(self, task_id: int) -> int:
        rows = self.repository.list_time_entries(task_id=task_id)
        total = 0
        for row in rows:
            if row.duration_minutes is not None:
                total += int(row.duration_minutes)
        return total

    def _close_time_entry(self, *, entry: ServiceTaskTimeEntry, action: str, note: str | None, actor_id: int | None) -> None:
        started_at = entry.started_at or datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        ended_at = datetime.now(timezone.utc)
        elapsed = ended_at - started_at
        duration_minutes = max(0, int(elapsed.total_seconds() // 60))
        self.repository.update_time_entry(
            entry,
            {
                "ended_at": ended_at,
                "duration_minutes": duration_minutes,
                "action": action,
                "note": (note or "").strip() or entry.note,
                "updated_by": actor_id,
            },
        )

    def _create_status_history(
        self,
        *,
        task: ServiceTask,
        old_status: str | None,
        new_status: str,
        actor_id: int | None,
        note: str | None,
    ) -> ServiceTaskStatusHistory:
        return self.repository.create_status_history(
            {
                "service_task_id": task.id,
                "old_status": old_status,
                "new_status": new_status,
                "changed_by": actor_id,
                "note": note,
                "company_id": task.company_id,
                "branch_id": task.branch_id,
                "created_by": actor_id,
                "updated_by": actor_id,
            }
        )

    def _emit_task_notification(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        actor_id: int | None,
        description: str,
    ) -> None:
        action = ServiceOrderAction(
            service_order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            action_date=datetime.now(timezone.utc).date(),
            technician_id=actor_id,
            action_type="OTHER",
            description=description,
            is_visible_for_customer=False,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.session.add(action)

    def _notify_overdue_tasks_once(self, *, company_id: int, branch_id: int | None, actor_id: int | None) -> None:
        open_statuses = {ServiceTaskStatusEnum.NEW.value, ServiceTaskStatusEnum.ASSIGNED.value, ServiceTaskStatusEnum.IN_PROGRESS.value, ServiceTaskStatusEnum.WAITING.value}
        now = datetime.now(timezone.utc)
        tasks = self.repository.list_team_tasks(company_id=company_id, branch_id=branch_id)
        for task in tasks:
            if task.status not in open_statuses:
                continue
            if task.planned_finish is None or task.planned_finish >= now:
                continue
            if self.repository.has_overdue_notification(task_id=task.id):
                continue

            self._create_status_history(
                task=task,
                old_status=task.status,
                new_status=task.status,
                actor_id=actor_id,
                note="OVERDUE_NOTIFIED",
            )
            self._emit_task_notification(
                order_id=task.service_order_id,
                company_id=task.company_id,
                branch_id=task.branch_id,
                actor_id=actor_id,
                description=f"Zadanie #{task.id} przekroczyło termin realizacji: {task.title}",
            )

    def _assert_can_view(self, *, task: ServiceTask, actor) -> None:
        if self._is_manager(actor):
            return
        actor_id = getattr(actor, "id", None)
        if actor_id is None:
            raise ServiceTaskPermissionError("Brak dostępu do zadania.")
        if task.assigned_to == actor_id or task.created_by == actor_id:
            return
        raise ServiceTaskPermissionError("Brak dostępu do zadania.")

    def _can_change_status(self, *, actor, task: ServiceTask) -> bool:
        if self._is_manager(actor):
            return True
        return task.assigned_to == getattr(actor, "id", None)

    def _assert_can_log_time(self, *, task: ServiceTask, actor) -> None:
        if self._is_manager(actor):
            return
        if task.assigned_to != getattr(actor, "id", None):
            raise ServiceTaskPermissionError("Tylko przypisany technik może logować czas pracy.")

    def _get_scoped_order(self, *, order_id: int, company_id: int, branch_id: int | None) -> ServiceOrder:
        order = db.session.scalar(
            select(ServiceOrder)
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.company_id == company_id)
            .where(ServiceOrder.is_active.is_(True))
        )
        if order is None:
            raise ServiceTaskNotFoundError("Nie znaleziono zlecenia.")

        if branch_id is None and order.branch_id is None:
            return order
        if branch_id is None and order.branch_id is not None:
            raise ServiceTaskPermissionError("Brak dostępu do wskazanego oddziału.")
        if branch_id is not None and order.branch_id != branch_id:
            raise ServiceTaskPermissionError("Brak dostępu do wskazanego oddziału.")
        return order

    def _is_manager(self, actor) -> bool:
        role_names = {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}
        return any(name in role_names for name in {"administrator", "kierownik"})
