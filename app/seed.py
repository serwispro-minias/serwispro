from __future__ import annotations

from dataclasses import dataclass

import click
from flask import Flask
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Branch, Company, Permission, Role, RolePermission, User, UserRole

DEFAULT_COMPANY_NAME = "SerwisPRO"
DEFAULT_COMPANY_SHORT_NAME = "SERWISPRO"
DEFAULT_BRANCH_NAME = "Main Branch"
DEFAULT_ROLE_NAME = "Administrator"
DEFAULT_ADMIN_LOGIN = "admin"
DEFAULT_ADMIN_PASSWORD = "Admin123!"

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
    ("users.manage", "Manage users"),
    ("roles.manage", "Manage roles"),
    ("permissions.manage", "Manage permissions"),
)


@dataclass
class SeedSummary:
    created_companies: int = 0
    created_branches: int = 0
    created_roles: int = 0
    created_permissions: int = 0
    created_users: int = 0
    created_user_roles: int = 0
    created_role_permissions: int = 0


def seed_database(
    *,
    admin_login: str = DEFAULT_ADMIN_LOGIN,
    admin_password: str = DEFAULT_ADMIN_PASSWORD,
) -> SeedSummary:
    """Create default records in an idempotent way.

    Running this function multiple times does not create duplicates.
    """

    summary = SeedSummary()

    from flask import current_app

    configured_prefix = str(current_app.config.get("COMPANY_PREFIX", "SER"))[:10]

    company = db.session.scalar(
        select(Company).where(Company.prefix == configured_prefix)
    )
    if company is None:
        company = Company()
        company.name = DEFAULT_COMPANY_NAME
        company.short_name = DEFAULT_COMPANY_SHORT_NAME
        company.prefix = configured_prefix
        db.session.add(company)
        db.session.flush()
        summary.created_companies += 1

    branch_code = f"{company.prefix}-MAIN"
    branch = db.session.scalar(select(Branch).where(Branch.code == branch_code))
    if branch is None:
        branch = Branch()
        branch.name = DEFAULT_BRANCH_NAME
        branch.code = branch_code
        branch.company_id = company.id
        db.session.add(branch)
        db.session.flush()
        summary.created_branches += 1

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
        summary.created_roles += 1

    permissions_by_name: dict[str, Permission] = {}
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
            summary.created_permissions += 1
        permissions_by_name[permission_name] = permission

    admin_user = db.session.scalar(select(User).where(User.login == admin_login))
    if admin_user is None:
        admin_user = User()
        admin_user.login = admin_login
        admin_user.email = None
        admin_user.password_hash = generate_password_hash(admin_password)
        admin_user.first_name = "System"
        admin_user.last_name = "Administrator"
        admin_user.company_id = company.id
        admin_user.branch_id = branch.id
        db.session.add(admin_user)
        db.session.flush()
        summary.created_users += 1

    user_role = db.session.scalar(
        select(UserRole)
        .where(UserRole.user_id == admin_user.id)
        .where(UserRole.role_id == role.id)
    )
    if user_role is None:
        user_role = UserRole()
        user_role.user_id = admin_user.id
        user_role.role_id = role.id
        user_role.company_id = company.id
        user_role.branch_id = branch.id
        db.session.add(user_role)
        summary.created_user_roles += 1

    for permission in permissions_by_name.values():
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
            summary.created_role_permissions += 1

    db.session.commit()
    return summary


def register_seed_command(app: Flask) -> None:
    @app.cli.command("seed")
    @click.option("--admin-login", default=DEFAULT_ADMIN_LOGIN, show_default=True)
    @click.option("--admin-password", default=DEFAULT_ADMIN_PASSWORD, show_default=True)
    def seed_command(admin_login: str, admin_password: str) -> None:
        """Seed default company, branch, admin role, permissions and admin user."""

        summary = seed_database(
            admin_login=admin_login,
            admin_password=admin_password,
        )
        click.echo("Seeding finished.")
        click.echo(f"Companies created: {summary.created_companies}")
        click.echo(f"Branches created: {summary.created_branches}")
        click.echo(f"Roles created: {summary.created_roles}")
        click.echo(f"Permissions created: {summary.created_permissions}")
        click.echo(f"Users created: {summary.created_users}")
        click.echo(f"User-role links created: {summary.created_user_roles}")
        click.echo(f"Role-permission links created: {summary.created_role_permissions}")
