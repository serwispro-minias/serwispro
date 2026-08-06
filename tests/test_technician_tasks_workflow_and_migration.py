from __future__ import annotations

from datetime import date
from importlib import import_module

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app.extensions import db
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.device import Device
from app.models.role import Role
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.models.service_task import ServiceTask
from app.models.service_task_attachment import ServiceTaskAttachment
from app.models.service_task_comment import ServiceTaskComment
from app.models.service_task_status_history import ServiceTaskStatusHistory
from app.models.service_task_time_entry import ServiceTaskTimeEntry
from app.models.user import User
from app.models.user_role import UserRole
from app.models.workflow_status import WorkflowStatus
from app.models.workflow_transition import WorkflowTransition
from app.workflow.service import WorkflowService


@pytest.fixture()
def workflow_tasks_schema(app):
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
                ServiceOrderStatusHistory.__table__,
                WorkflowStatus.__table__,
                WorkflowTransition.__table__,
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
                WorkflowTransition.__table__,
                WorkflowStatus.__table__,
                ServiceOrderStatusHistory.__table__,
                ServiceOrderAction.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                Customer.__table__,
                UserRole.__table__,
                Role.__table__,
                Branch.__table__,
            ],
        )


def _seed_order(*, company_id: int, branch_id: int) -> ServiceOrder:
    customer = Customer(customer_type="PERSON", full_name="Workflow Task", company_id=company_id, branch_id=branch_id)
    db.session.add(customer)
    db.session.flush()

    device = Device(customer_id=customer.id, manufacturer="Brother", model="DCP", serial_number="WF-TASK-1", company_id=company_id, branch_id=branch_id)
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="WF-TASK-001",
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


def test_workflow_creates_automatic_task(app, workflow_tasks_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        user = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert user is not None

        branch = Branch(company_id=company_id, name="WF TASK", code="WF-TASK")
        db.session.add(branch)
        db.session.flush()
        user.branch_id = branch.id

        role = Role(company_id=company_id, branch_id=branch.id, name="Administrator")
        db.session.add(role)
        db.session.flush()
        db.session.add(UserRole(company_id=company_id, branch_id=branch.id, user_id=user.id, role_id=role.id))
        db.session.commit()

        order = _seed_order(company_id=company_id, branch_id=branch.id)

        workflow = WorkflowService()
        workflow.ensure_default_workflow(company_id=company_id, branch_id=branch.id, user_id=user.id)

        result = workflow.change_order_status(
            order_id=order.id,
            target_status_code="DIAGNOSIS",
            company_id=company_id,
            branch_id=branch.id,
            actor=user,
            note="start",
            ip_address="127.0.0.1",
            force=False,
        )

        assert result.order.status == "DIAGNOSIS"

        tasks = db.session.query(ServiceTask).filter_by(service_order_id=order.id).all()
        assert len(tasks) == 1
        assert tasks[0].title == "Wykonaj diagnozę"
        assert tasks[0].task_type == "DIAGNOSIS"
        assert tasks[0].status == "NEW"


def test_service_tasks_migration_metadata():
    migration = import_module("migrations.versions.b6d4e1a2c903_add_service_tasks_module")
    assert migration.revision == "b6d4e1a2c903"
    assert migration.down_revision == "a91d4ef62c70"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_service_tasks_migration_is_idempotent(tmp_path):
    migration = import_module("migrations.versions.b6d4e1a2c903_add_service_tasks_module")

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'service_tasks_migration.sqlite'}")
    metadata = sa.MetaData()

    sa.Table("companies", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("branches", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("customers", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("devices", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("service_orders", metadata, sa.Column("id", sa.Integer, primary_key=True))

    with engine.begin() as connection:
        metadata.create_all(connection)

        context = MigrationContext.configure(connection)
        operations = Operations(context)
        previous_op = migration.op
        migration.op = operations
        try:
            migration.upgrade()
            migration.upgrade()
        finally:
            migration.op = previous_op

        inspector = sa.inspect(connection)
        assert inspector.has_table("service_tasks")
        assert inspector.has_table("service_task_comments")
        assert inspector.has_table("service_task_attachments")
        assert inspector.has_table("service_task_time_entries")
        assert inspector.has_table("service_task_status_history")
