from __future__ import annotations

import click
from flask import current_app
from sqlalchemy import inspect, select
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Branch, Company, Permission, Role, RolePermission, User, UserRole

DEFAULT_COMPANY_NAME = "ACES Projekt"
DEFAULT_COMPANY_PREFIX = "SER"
DEFAULT_BRANCH_NAME = "Oddzial Glowny"
DEFAULT_ROLE_NAME = "Administrator"
DEFAULT_ADMIN_LOGIN = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"
DEFAULT_ADMIN_FIRST_NAME = "System"
DEFAULT_ADMIN_LAST_NAME = "Administrator"

DEFAULT_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("dashboard.view", "View dashboard"),
    ("customers.view", "View customers"),
    ("customers.create", "Create customers"),
    ("customers.update", "Update customers"),
    ("customers.delete", "Delete customers"),
    ("devices.view", "View devices"),
    ("devices.manage", "Manage devices"),
    ("orders.view", "View orders"),
    ("orders.manage", "Manage orders"),
    ("inventory.view", "View inventory"),
    ("inventory.manage", "Manage inventory"),
    ("reports.view", "View reports"),
    ("settings.view", "View settings"),
    ("settings.manage", "Manage settings"),
)


def _required_tables_exist() -> bool:
    inspector = inspect(db.engine)
    required = {
        "companies",
        "branches",
        "roles",
        "permissions",
        "users",
        "user_roles",
        "role_permissions",
    }
    existing = set(inspector.get_table_names())
    return required.issubset(existing)


def is_database_empty() -> bool:
    """Return True when base business data is not initialized yet."""

    if not _required_tables_exist():
        return False

    has_company = db.session.scalar(select(Company.id).limit(1)) is not None
    has_user = db.session.scalar(select(User.id).limit(1)) is not None
    return not has_company and not has_user


def bootstrap_database() -> None:
    """Create baseline records idempotently without changing existing records."""

    if not _required_tables_exist():
        current_app.logger.info("Bootstrap skipped: required tables do not exist yet")
        return

    company = db.session.scalar(
        select(Company)
        .where(Company.prefix == DEFAULT_COMPANY_PREFIX)
    )
    if company is None:
        company = Company()
        company.name = DEFAULT_COMPANY_NAME
        company.prefix = DEFAULT_COMPANY_PREFIX
        db.session.add(company)
        db.session.flush()
        current_app.logger.info("Default company created")
    else:
        current_app.logger.info("Default company already exists")

    branch_code = f"{company.prefix}-MAIN"
    branch = db.session.scalar(select(Branch).where(Branch.code == branch_code))
    if branch is None:
        branch = Branch()
        branch.name = DEFAULT_BRANCH_NAME
        branch.code = branch_code
        branch.company_id = company.id
        db.session.add(branch)
        db.session.flush()
        current_app.logger.info("Main branch created")
    else:
        current_app.logger.info("Main branch already exists")

    role = db.session.scalar(
        select(Role)
        .where(Role.company_id == company.id)
        .where(Role.name == DEFAULT_ROLE_NAME)
    )
    if role is None:
        role = Role()
        role.name = DEFAULT_ROLE_NAME
        role.description = "System administrator role"
        role.company_id = company.id
        role.branch_id = branch.id
        db.session.add(role)
        db.session.flush()
        current_app.logger.info("Administrator role created")
    else:
        current_app.logger.info("Administrator role already exists")

    for permission_name, permission_description in DEFAULT_PERMISSIONS:
        permission = db.session.scalar(
            select(Permission)
            .where(Permission.company_id == company.id)
            .where(Permission.name == permission_name)
        )
        if permission is None:
            permission = Permission()
            permission.name = permission_name
            permission.description = permission_description
            permission.company_id = company.id
            permission.branch_id = branch.id
            db.session.add(permission)
            db.session.flush()
            current_app.logger.info("Permission created: %s", permission_name)
        else:
            current_app.logger.info("Permission already exists: %s", permission_name)

        role_permission = db.session.scalar(
            select(RolePermission)
            .where(RolePermission.role_id == role.id)
            .where(RolePermission.permission_id == permission.id)
        )
        if role_permission is None:
            role_permission = RolePermission()
            role_permission.role_id = role.id
            role_permission.permission_id = permission.id
            role_permission.company_id = company.id
            role_permission.branch_id = branch.id
            db.session.add(role_permission)
            current_app.logger.info("Role-permission link created: %s", permission_name)
        else:
            current_app.logger.info("Role-permission link already exists: %s", permission_name)

    user = db.session.scalar(select(User).where(User.login == DEFAULT_ADMIN_LOGIN))
    if user is None:
        user = User()
        user.login = DEFAULT_ADMIN_LOGIN
        user.password_hash = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
        user.first_name = DEFAULT_ADMIN_FIRST_NAME
        user.last_name = DEFAULT_ADMIN_LAST_NAME
        user.company_id = company.id
        user.branch_id = branch.id
        db.session.add(user)
        db.session.flush()
        current_app.logger.info("Default administrator created")
    else:
        current_app.logger.info("Default administrator already exists")

    user_role = db.session.scalar(
        select(UserRole)
        .where(UserRole.user_id == user.id)
        .where(UserRole.role_id == role.id)
    )
    if user_role is None:
        user_role = UserRole()
        user_role.user_id = user.id
        user_role.role_id = role.id
        user_role.company_id = company.id
        user_role.branch_id = branch.id
        db.session.add(user_role)
        current_app.logger.info("Administrator role assigned to admin user")
    else:
        current_app.logger.info("Administrator role already assigned to admin user")

    db.session.commit()


def register_bootstrap_command(app) -> None:
    @app.cli.command("bootstrap")
    def bootstrap_command() -> None:
        """Create baseline company, branch, role, permissions and admin account."""

        bootstrap_database()
        click.echo("Bootstrap finished.")
