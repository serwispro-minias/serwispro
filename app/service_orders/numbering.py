"""Concurrency-safe company-scoped service-order number allocation."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.extensions import db
from app.models.company import Company
from app.models.service_order import ServiceOrder
from app.models.service_order_number_counter import ServiceOrderNumberCounter

from .exceptions import ServiceOrderValidationError


def _ensure_counter_row(company_id: int, period: int) -> None:
    values = {"company_id": company_id, "period": period, "next_value": 1}
    dialect = db.session.get_bind().dialect.name
    if dialect == "mysql":
        statement = mysql_insert(ServiceOrderNumberCounter).values(**values)
        statement = statement.on_duplicate_key_update(id=ServiceOrderNumberCounter.id)
    elif dialect == "sqlite":
        statement = sqlite_insert(ServiceOrderNumberCounter).values(**values)
        statement = statement.on_conflict_do_nothing(index_elements=["company_id", "period"])
    elif dialect == "postgresql":
        statement = postgresql_insert(ServiceOrderNumberCounter).values(**values)
        statement = statement.on_conflict_do_nothing(index_elements=["company_id", "period"])
    else:
        existing = db.session.scalar(
            select(ServiceOrderNumberCounter).where(
                ServiceOrderNumberCounter.company_id == company_id,
                ServiceOrderNumberCounter.period == period,
            )
        )
        if existing is None:
            db.session.add(ServiceOrderNumberCounter(**values))
            db.session.flush()
        return
    db.session.execute(statement)


def allocate_service_order_number(company_id: int, *, today: date | None = None) -> str:
    """Allocate a number while holding the company and period counter locks.

    Caller owns the surrounding transaction and must commit it with the new order.
    """
    company = db.session.scalar(
        select(Company)
        .where(Company.id == company_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if company is None:
        raise ServiceOrderValidationError("Nie znaleziono firmy do nadania numeru zlecenia.")

    now = today or date.today()
    include_year = bool(company.service_order_include_year)
    period = now.year if include_year else 0
    _ensure_counter_row(company_id, period)
    counter = db.session.scalar(
        select(ServiceOrderNumberCounter)
        .where(
            ServiceOrderNumberCounter.company_id == company_id,
            ServiceOrderNumberCounter.period == period,
        )
        .with_for_update()
    )
    if counter is None:
        raise ServiceOrderValidationError("Nie udało się zarezerwować numeru zlecenia.")

    prefix = (company.service_order_prefix or "ZL").strip().strip("/")
    digits = max(3, min(int(company.service_order_number_digits or 6), 10))
    while True:
        serial = str(counter.next_value).zfill(digits)
        candidate = f"{prefix}/{now.year}/{serial}" if include_year else f"{prefix}/{serial}"
        counter.next_value += 1
        if len(candidate) > 50:
            raise ServiceOrderValidationError("Ustawienia numeracji tworzą numer dłuższy niż dopuszczalna długość.")
        exists = db.session.scalar(
            select(ServiceOrder.id).where(
                ServiceOrder.company_id == company_id,
                ServiceOrder.order_number == candidate,
            )
        )
        if exists is None:
            db.session.flush()
            return candidate
