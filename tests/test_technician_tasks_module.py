from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.device import Device
from app.models.role import Role
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_task import ServiceTask
from app.models.service_task_attachment import ServiceTaskAttachment
from app.models.service_task_comment import ServiceTaskComment
from app.models.service_task_status_history import ServiceTaskStatusHistory
from app.models.service_task_time_entry import ServiceTaskTimeEntry
from app.models.user import User
from app.models.user_role import UserRole
from app.technician_tasks.exceptions import ServiceTaskPermissionError
from app.technician_tasks.service import ServiceTaskService


@pytest.fixture()
def service_tasks_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Branch.__table__,
                Role.__table__,
                UserRole.__table__,
                Customer.__table__,
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderAction.__table__,
                ServiceTask.__table__,
                ServiceTaskComment.__table__,
                ServiceTaskAttachment.__table__,
                ServiceTaskTimeEntry.__table__,
                ServiceTaskStatusHistory.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                ServiceTaskStatusHistory.__table__,
                ServiceTaskTimeEntry.__table__,
                ServiceTaskAttachment.__table__,
                ServiceTaskComment.__table__,
                ServiceTask.__table__,
                ServiceOrderAction.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                Customer.__table__,
                UserRole.__table__,
                Role.__table__,
                Branch.__table__,
            ],
        )


def _create_branch(company_id: int, code: str) -> Branch:
    branch = Branch(company_id=company_id, name=f"Oddział {code}", code=code)
    db.session.add(branch)
    db.session.commit()
    return branch


def _create_user(*, company_id: int, branch_id: int | None, login: str) -> User:
    user = User(login=login, password_hash="x", company_id=company_id, branch_id=branch_id)
    db.session.add(user)
    db.session.commit()
    return user


def _assign_role(*, company_id: int, branch_id: int | None, user_id: int, role_name: str) -> None:
    role = Role(company_id=company_id, branch_id=branch_id, name=role_name)
    db.session.add(role)
    db.session.flush()
    db.session.add(UserRole(company_id=company_id, branch_id=branch_id, user_id=user_id, role_id=role.id))
    db.session.commit()


def _create_order(*, company_id: int, branch_id: int | None, number: str) -> ServiceOrder:
    customer = Customer(customer_type="PERSON", full_name=f"Klient {number}", company_id=company_id, branch_id=branch_id)
    db.session.add(customer)
    db.session.flush()

    device = Device(customer_id=customer.id, manufacturer="HP", model="Elite", serial_number=f"SN-{number}", company_id=company_id, branch_id=branch_id)
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number=number,
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date.today(),
        issue_description="Test",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(order)
    db.session.commit()
    return order


def test_service_task_crud_comment_and_progress(app, service_tasks_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        manager = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert manager is not None
        branch = _create_branch(company_id, "TASK-A")
        manager.branch_id = branch.id
        db.session.commit()
        _assign_role(company_id=company_id, branch_id=branch.id, user_id=manager.id, role_name="Kierownik")

        technician = _create_user(company_id=company_id, branch_id=branch.id, login="tech-a")
        _assign_role(company_id=company_id, branch_id=branch.id, user_id=technician.id, role_name="Technik")

        order = _create_order(company_id=company_id, branch_id=branch.id, number="SO-TASK-001")

        service = ServiceTaskService()
        created = service.create_task(
            order_id=order.id,
            company_id=company_id,
            branch_id=branch.id,
            actor=manager,
            data={
                "title": "Wykonaj diagnozę płyty",
                "description": "Sprawdź zasilanie i sekcję wejściową",
                "task_type": "DIAGNOSIS",
                "status": "ASSIGNED",
                "priority": "HIGH",
                "assigned_to": technician.id,
                "planned_start": datetime.now(timezone.utc),
                "planned_finish": datetime.now(timezone.utc) + timedelta(days=1),
                "estimated_minutes": 120,
                "completion_percent": 10,
                "requires_confirmation": True,
                "parent_task_id": 0,
            },
        )

        assert created.id is not None
        assert created.assigned_to == technician.id
        assert created.completion_percent == 10

        updated = service.update_task(
            task_id=created.id,
            company_id=company_id,
            branch_id=branch.id,
            actor=manager,
            data={
                "title": "Wykonaj diagnozę płyty głównej",
                "description": "Rozszerzona diagnostyka",
                "task_type": "DIAGNOSIS",
                "status": "IN_PROGRESS",
                "priority": "URGENT",
                "assigned_to": technician.id,
                "planned_start": created.planned_start,
                "planned_finish": created.planned_finish,
                "estimated_minutes": 150,
                "completion_percent": 25,
                "requires_confirmation": True,
                "parent_task_id": 0,
            },
        )
        assert updated.priority == "URGENT"
        assert updated.status == "IN_PROGRESS"

        comment = service.add_comment(
            task_id=updated.id,
            content="Rozpoczęto pomiary sekcji zasilania.",
            company_id=company_id,
            branch_id=branch.id,
            actor=technician,
        )
        assert comment.id is not None

        refreshed = service.get_task(task_id=updated.id, company_id=company_id, branch_id=branch.id, actor=manager)
        assert len(refreshed.comments) == 1
        assert refreshed.comments[0].content.startswith("Rozpoczęto")


def test_time_tracking_and_history(app, service_tasks_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        manager = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert manager is not None
        branch = _create_branch(company_id, "TASK-B")
        manager.branch_id = branch.id
        db.session.commit()
        _assign_role(company_id=company_id, branch_id=branch.id, user_id=manager.id, role_name="Administrator")

        order = _create_order(company_id=company_id, branch_id=branch.id, number="SO-TASK-002")
        service = ServiceTaskService()

        task = service.create_task(
            order_id=order.id,
            company_id=company_id,
            branch_id=branch.id,
            actor=manager,
            data={
                "title": "Naprawa układu poboru",
                "description": "Wymiana rolek",
                "task_type": "REPAIR",
                "status": "ASSIGNED",
                "priority": "NORMAL",
                "assigned_to": manager.id,
                "planned_start": None,
                "planned_finish": None,
                "estimated_minutes": 90,
                "completion_percent": 0,
                "requires_confirmation": False,
                "parent_task_id": 0,
            },
        )

        service.start_work(task_id=task.id, note="start", company_id=company_id, branch_id=branch.id, actor=manager)
        open_entry = db.session.query(ServiceTaskTimeEntry).filter_by(service_task_id=task.id, ended_at=None).one()
        open_entry.started_at = datetime.now(timezone.utc) - timedelta(minutes=35)
        db.session.add(open_entry)
        db.session.commit()

        paused = service.pause_work(task_id=task.id, note="pause", company_id=company_id, branch_id=branch.id, actor=manager)
        assert paused.worked_minutes >= 35
        assert paused.status == "WAITING"

        finished = service.finish_work(task_id=task.id, note="done", company_id=company_id, branch_id=branch.id, actor=manager)
        assert finished.status == "DONE"
        assert finished.completion_percent == 100
        assert finished.finished_at is not None

        history_rows = db.session.query(ServiceTaskStatusHistory).filter_by(service_task_id=task.id).all()
        assert len(history_rows) >= 3


def test_permissions_and_branch_scope(app, service_tasks_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        manager = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert manager is not None

        branch_a = _create_branch(company_id, "TASK-C1")
        branch_b = _create_branch(company_id, "TASK-C2")

        manager.branch_id = branch_a.id
        db.session.commit()
        _assign_role(company_id=company_id, branch_id=branch_a.id, user_id=manager.id, role_name="Kierownik")

        tech_a = _create_user(company_id=company_id, branch_id=branch_a.id, login="tech-c-a")
        _assign_role(company_id=company_id, branch_id=branch_a.id, user_id=tech_a.id, role_name="Technik")

        tech_b = _create_user(company_id=company_id, branch_id=branch_b.id, login="tech-c-b")
        _assign_role(company_id=company_id, branch_id=branch_b.id, user_id=tech_b.id, role_name="Technik")

        order_a = _create_order(company_id=company_id, branch_id=branch_a.id, number="SO-TASK-003")
        order_b = _create_order(company_id=company_id, branch_id=branch_b.id, number="SO-TASK-004")

        service = ServiceTaskService()
        task = service.create_task(
            order_id=order_a.id,
            company_id=company_id,
            branch_id=branch_a.id,
            actor=manager,
            data={
                "title": "Testy końcowe",
                "description": "Sprawdź wydruk testowy",
                "task_type": "TESTS",
                "status": "ASSIGNED",
                "priority": "NORMAL",
                "assigned_to": tech_a.id,
                "planned_start": None,
                "planned_finish": None,
                "estimated_minutes": 30,
                "completion_percent": 0,
                "requires_confirmation": False,
                "parent_task_id": 0,
            },
        )

        with pytest.raises(ServiceTaskPermissionError):
            service.update_task(
                task_id=task.id,
                company_id=company_id,
                branch_id=branch_a.id,
                actor=tech_b,
                data={
                    "title": "Nieuprawniona edycja",
                    "description": "x",
                    "task_type": "TESTS",
                    "status": "IN_PROGRESS",
                    "priority": "HIGH",
                    "assigned_to": tech_b.id,
                    "planned_start": None,
                    "planned_finish": None,
                    "estimated_minutes": 15,
                    "completion_percent": 10,
                    "requires_confirmation": False,
                    "parent_task_id": 0,
                },
            )

        with pytest.raises(ServiceTaskPermissionError):
            service.list_for_order(order_id=order_b.id, company_id=company_id, branch_id=branch_a.id, actor=manager)

        dashboard = service.build_dashboard(company_id=company_id, branch_id=branch_a.id, actor=manager)
        assert any(item.id == task.id for item in dashboard.team_tasks)
