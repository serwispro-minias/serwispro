from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import MetaData, Table, and_, func, inspect, select
from sqlalchemy.sql import Select

from app.extensions import db
from app.models.customer import Customer
from app.models.part_demand import PartDemand


@dataclass(frozen=True)
class DashboardStats:
    """Aggregated counters displayed in dashboard statistic tiles."""

    customers_count: int
    devices_count: int
    active_repairs_count: int
    completed_repairs_count: int
    new_reports_today_count: int
    new_purchase_requests_count: int
    pending_purchase_requests_count: int
    ordered_purchase_requests_count: int
    awaiting_delivery_purchase_requests_count: int


@dataclass(frozen=True)
class DashboardData:
    """Data container used by dashboard view rendering."""

    stats: DashboardStats
    recent_customers: list[Customer]
    recent_repairs: list[dict[str, Any]]
    repairs_module_available: bool


class DashboardService:
    """Read-only data provider for dashboard presentation layer."""

    def get_dashboard_data(self) -> DashboardData:
        """Build complete dashboard payload with safe defaults."""

        stats = DashboardStats(
            customers_count=self._count_customers(),
            devices_count=self._count_table_rows("devices"),
            active_repairs_count=self._count_active_repairs(),
            completed_repairs_count=self._count_completed_repairs(),
            new_reports_today_count=self._count_new_reports_today(),
            new_purchase_requests_count=self._count_purchase_requests("NEW"),
            pending_purchase_requests_count=self._count_purchase_requests("APPROVED"),
            ordered_purchase_requests_count=self._count_purchase_requests("ORDERED"),
            awaiting_delivery_purchase_requests_count=self._count_purchase_requests("RECEIVED"),
        )

        repairs_table = self._get_table("repairs")
        return DashboardData(
            stats=stats,
            recent_customers=self._get_recent_customers(limit=10),
            recent_repairs=self._get_recent_repairs(limit=10, repairs_table=repairs_table),
            repairs_module_available=repairs_table is not None,
        )

    def _count_customers(self) -> int:
        if not self._has_table(Customer.__tablename__):
            return 0

        query = (
            select(func.count())
            .select_from(Customer)
            .where(Customer.is_active.is_(True))
        )
        return int(db.session.scalar(query) or 0)

    def _get_recent_customers(self, limit: int) -> list[Customer]:
        if not self._has_table(Customer.__tablename__):
            return []

        query = (
            select(Customer)
            .where(Customer.is_active.is_(True))
            .order_by(Customer.created_at.desc(), Customer.id.desc())
            .limit(limit)
        )
        return list(db.session.scalars(query).all())

    def _count_table_rows(self, table_name: str) -> int:
        table = self._get_table(table_name)
        if table is None:
            return 0

        query = select(func.count()).select_from(table)
        return int(db.session.scalar(query) or 0)

    def _count_active_repairs(self) -> int:
        table = self._get_table("repairs")
        if table is None:
            return 0

        status_col = table.c.get("status")
        is_completed_col = table.c.get("is_completed")

        if status_col is not None:
            completed_values = ["completed", "done", "closed", "zakonczone"]
            query = (
                select(func.count())
                .select_from(table)
                .where(~func.lower(status_col).in_(completed_values))
            )
            return int(db.session.scalar(query) or 0)

        if is_completed_col is not None:
            query = (
                select(func.count())
                .select_from(table)
                .where(is_completed_col.is_(False))
            )
            return int(db.session.scalar(query) or 0)

        return 0

    def _count_completed_repairs(self) -> int:
        table = self._get_table("repairs")
        if table is None:
            return 0

        status_col = table.c.get("status")
        is_completed_col = table.c.get("is_completed")

        if status_col is not None:
            completed_values = ["completed", "done", "closed", "zakonczone"]
            query = (
                select(func.count())
                .select_from(table)
                .where(func.lower(status_col).in_(completed_values))
            )
            return int(db.session.scalar(query) or 0)

        if is_completed_col is not None:
            query = (
                select(func.count())
                .select_from(table)
                .where(is_completed_col.is_(True))
            )
            return int(db.session.scalar(query) or 0)

        return 0

    def _count_new_reports_today(self) -> int:
        table = self._get_table("repairs")
        if table is None:
            return 0

        created_at_col = table.c.get("created_at")
        if created_at_col is None:
            return 0

        start = datetime.combine(date.today(), time.min)
        end = start + timedelta(days=1)
        query = (
            select(func.count())
            .select_from(table)
            .where(and_(created_at_col >= start, created_at_col < end))
        )
        return int(db.session.scalar(query) or 0)

    def _count_purchase_requests(self, status: str) -> int:
        if not self._has_table(PartDemand.__tablename__):
            return 0
        status_map = {
            "APPROVED": "IN_PURCHASE",
            "RECEIVED": "DELIVERED",
        }
        demand_status = status_map.get(status, status)
        query = select(func.count()).select_from(PartDemand).where(PartDemand.status == demand_status, PartDemand.is_active.is_(True))
        return int(db.session.scalar(query) or 0)

    def _get_recent_repairs(
        self,
        *,
        limit: int,
        repairs_table: Table | None,
    ) -> list[dict[str, Any]]:
        if repairs_table is None:
            return []

        order_columns = []
        if repairs_table.c.get("created_at") is not None:
            order_columns.append(repairs_table.c.created_at.desc())
        if repairs_table.c.get("id") is not None:
            order_columns.append(repairs_table.c.id.desc())

        query: Select[Any] = select(repairs_table)
        if order_columns:
            query = query.order_by(*order_columns)
        query = query.limit(limit)

        rows = db.session.execute(query).mappings().all()
        recent: list[dict[str, Any]] = []
        for row in rows:
            recent.append(
                {
                    "number": row.get("number") or row.get("id") or "-",
                    "customer": row.get("customer_name") or row.get("customer_id") or "-",
                    "status": row.get("status") or "-",
                    "created_at": row.get("created_at") or "-",
                }
            )
        return recent

    def _has_table(self, table_name: str) -> bool:
        return inspect(db.engine).has_table(table_name)

    def _get_table(self, table_name: str) -> Table | None:
        if not self._has_table(table_name):
            return None

        metadata = MetaData()
        return Table(table_name, metadata, autoload_with=db.engine)
