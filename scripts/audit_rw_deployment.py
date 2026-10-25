"""Read-only MySQL deployment audit. Never runs migrations or stock operations.

Run from the repository root: python -m scripts.audit_rw_deployment
Output contains product/internal IDs and schema metadata, not customer details
or connection credentials. Store it as an internal deployment artifact.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

SCHEMA_TABLES = (
    "stock_issue_items", "stock_issues", "service_order_items",
    "service_order_part_reservations", "inventory_reservations",
    "inventory_items", "catalog_materials", "catalog_stock_movements",
)


def audit(connection):
    """Caller must provide an active READ ONLY transaction on MySQL."""
    def rows(sql):
        return [dict(row) for row in connection.execute(text(sql)).mappings()]

    inspector = inspect(connection)
    report = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "connection": {"dialect": connection.dialect.name,
                       "driver": connection.dialect.driver},
        "server": rows("SELECT VERSION() AS version, @@SESSION.sql_mode AS sql_mode"),
        "alembic_versions": rows("SELECT version_num FROM alembic_version"),
        "schema": {},
    }
    for table in SCHEMA_TABLES:
        if not inspector.has_table(table):
            report["schema"][table] = {"missing": True}
            continue
        report["schema"][table] = {
            "columns": [{"name": col["name"], "type": str(col["type"]),
                         "nullable": col["nullable"], "default": col.get("default")}
                        for col in inspector.get_columns(table)],
            "indexes": inspector.get_indexes(table),
            "foreign_keys": inspector.get_foreign_keys(table),
            "primary_key": inspector.get_pk_constraint(table),
            "unique_constraints": inspector.get_unique_constraints(table),
            "row_count": connection.scalar(text(f"SELECT COUNT(*) FROM `{table}`")),
        }
    report["storage"] = rows("""
        SELECT table_name, engine, table_collation, data_length, index_length
        FROM information_schema.tables WHERE table_schema = DATABASE()
        AND table_name IN ('stock_issue_items','stock_issues','inventory_items',
                          'catalog_materials','service_order_items')
    """)
    report["rw_quantity_preflight"] = rows("""
        SELECT COUNT(*) AS total, MIN(quantity_issued) AS min_quantity,
               MAX(quantity_issued) AS max_quantity,
               SUM(quantity_issued IS NULL) AS null_quantities,
               SUM(ABS(quantity_issued) > 999999999.999) AS outside_numeric_12_3,
               SUM(quantity_issued <= 0) AS nonpositive,
               SUM(inventory_item_id IS NULL) AS missing_product
        FROM stock_issue_items
    """)
    report["rw_orphans"] = rows("""
        SELECT SUM(p.id IS NULL) AS missing_product,
               SUM(s.id IS NULL) AS missing_header
        FROM stock_issue_items i
        LEFT JOIN inventory_items p ON p.id = i.inventory_item_id
        LEFT JOIN stock_issues s ON s.id = i.stock_issue_id
    """)
    report["reservations_by_status"] = {}
    for table in ("service_order_part_reservations", "inventory_reservations"):
        report["reservations_by_status"][table] = rows(f"""
            SELECT company_id, status, is_active, COUNT(*) AS rows_count,
                   SUM(quantity) AS quantity FROM {table}
            GROUP BY company_id, status, is_active
        """)
    report["order_items_with_reservations"] = rows("""
        SELECT company_id, item_type, is_active, COUNT(*) AS rows_count,
               SUM(reserved_quantity) AS reserved, SUM(used_quantity) AS used,
               SUM(returned_quantity) AS released
        FROM service_order_items WHERE reserved_quantity > 0
        GROUP BY company_id, item_type, is_active
    """)
    # Same aggregation as reserved_stock(): maximum per order across the three
    # existing representations, then sum across orders. Do not silently reconcile.
    report["products_with_reservations"] = rows("""
        SELECT h.company_id, h.part_id, p.code, p.current_stock,
               SUM(h.held) AS effective_active_holds,
               p.current_stock - SUM(h.held) AS raw_available,
               GREATEST(0, p.current_stock - SUM(h.held)) AS available,
               SUM(h.service_holds) AS service_holds,
               SUM(h.inventory_holds) AS inventory_holds,
               SUM(h.item_holds) AS order_item_holds
        FROM (
            SELECT company_id, service_order_id, part_id,
                   MAX(qty) AS held,
                   SUM(CASE WHEN source = 'service' THEN qty ELSE 0 END) AS service_holds,
                   SUM(CASE WHEN source = 'inventory' THEN qty ELSE 0 END) AS inventory_holds,
                   SUM(CASE WHEN source = 'item' THEN qty ELSE 0 END) AS item_holds
            FROM (
                SELECT company_id, service_order_id, part_id, 'service' AS source, SUM(quantity) AS qty
                FROM service_order_part_reservations WHERE status='RESERVED' AND is_active=1
                GROUP BY company_id, service_order_id, part_id
                UNION ALL
                SELECT company_id, service_order_id, inventory_item_id, 'inventory', SUM(quantity)
                FROM inventory_reservations WHERE status='RESERVED' AND is_active=1
                GROUP BY company_id, service_order_id, inventory_item_id
                UNION ALL
                SELECT company_id, service_order_id, item_id, 'item', SUM(reserved_quantity)
                FROM service_order_items WHERE item_type='PART' AND is_active=1 AND reserved_quantity>0
                GROUP BY company_id, service_order_id, item_id
            ) sources GROUP BY company_id, service_order_id, part_id
        ) h LEFT JOIN inventory_items p ON p.id=h.part_id AND p.company_id=h.company_id
        GROUP BY h.company_id, h.part_id, p.code, p.current_stock
    """)
    report["materials_with_reservations"] = rows("""
        SELECT i.company_id, i.item_id AS material_id, m.code, m.current_stock,
               SUM(i.reserved_quantity) AS reserved
        FROM service_order_items i LEFT JOIN catalog_materials m
          ON m.id=i.item_id AND m.company_id=i.company_id
        WHERE i.item_type='MATERIAL' AND i.is_active=1 AND i.reserved_quantity>0
        GROUP BY i.company_id, i.item_id, m.code, m.current_stock
    """)
    report["movement_summary"] = rows("""
        SELECT company_id, movement_type, reference_type, COUNT(*) AS rows_count,
               SUM(quantity) AS quantity, MIN(operation_at) AS earliest,
               MAX(operation_at) AS latest
        FROM catalog_stock_movements
        GROUP BY company_id, movement_type, reference_type
    """)
    report["reservation_movement_effects"] = rows("""
        SELECT company_id, part_id, movement_type, reference_type,
               COUNT(*) AS rows_count, SUM(quantity) AS quantity,
               SUM(stock_after-stock_before) AS recorded_physical_delta,
               SUM(stock_after < stock_before) AS decreases,
               SUM(stock_after = stock_before) AS unchanged,
               SUM(stock_after > stock_before) AS increases
        FROM catalog_stock_movements WHERE movement_type IN ('RESERVATION','RELEASE','RETURN')
        GROUP BY company_id, part_id, movement_type, reference_type
    """)
    report["ambiguous_reservation_groups"] = rows("""
        SELECT r.company_id, r.service_order_id, r.part_id,
               COUNT(DISTINCT r.id) AS reservation_rows,
               COUNT(DISTINCT m.id) AS candidate_movements
        FROM service_order_part_reservations r
        LEFT JOIN catalog_stock_movements m ON m.company_id=r.company_id AND m.part_id=r.part_id
          AND m.reference_type='SERVICE_ORDER' AND m.reference_id=CAST(r.service_order_id AS CHAR)
          AND m.movement_type='RESERVATION'
        GROUP BY r.company_id, r.service_order_id, r.part_id
    """)
    return report


def main():
    from app import create_app
    from app.extensions import db

    app = create_app()
    # Never print URLs, config, credentials, DB exception text or tracebacks.
    with app.app_context():
        if db.engine.dialect.name not in {"mysql", "mariadb"}:
            print(json.dumps({"error": "Expected MySQL/MariaDB; no audit performed."}))
            return 2
        try:
            with db.engine.connect() as connection:
                connection.exec_driver_sql("START TRANSACTION READ ONLY")
                try:
                    result = audit(connection)
                finally:
                    connection.rollback()
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        except SQLAlchemyError as exc:
            print(json.dumps({"error": "Read-only database audit failed; details suppressed to protect credentials.",
                              "exception_type": type(exc).__name__}))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())