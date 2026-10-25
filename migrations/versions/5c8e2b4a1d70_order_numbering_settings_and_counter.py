"""Configure and allocate service-order numbers per company.

Revision ID: 5c8e2b4a1d70
Revises: 4b7d9a2c1e6f
"""

from alembic import op
import sqlalchemy as sa


revision = "5c8e2b4a1d70"
down_revision = "4b7d9a2c1e6f"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT company_id, order_number, COUNT(*) AS duplicate_count "
            "FROM service_orders GROUP BY company_id, order_number HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates:
        raise RuntimeError(
            "Cannot enforce unique service order numbers: existing duplicate "
            f"company_id={duplicates.company_id}, order_number={duplicates.order_number!r}. "
            "Resolve duplicates without renumbering historical records, then retry."
        )

    op.add_column(
        "companies",
        sa.Column("service_order_prefix", sa.String(length=20), nullable=False, server_default="ZL"),
    )
    op.add_column(
        "companies",
        sa.Column("service_order_include_year", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "companies",
        sa.Column("service_order_number_digits", sa.Integer(), nullable=False, server_default="6"),
    )
    op.create_table(
        "service_order_number_counters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("next_value", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "period", name="uq_service_order_number_counter_company_period"),
    )
    # Start after any historical sequence-formatted numbers; do not rewrite legacy values.
    companies = bind.execute(sa.text("SELECT id FROM companies")).fetchall()
    for (company_id,) in companies:
        op.execute(
            sa.text(
                "INSERT INTO service_order_number_counters (company_id, period, next_value) "
                "VALUES (:company_id, 0, 1)"
            ).bindparams(company_id=company_id)
        )
    with op.batch_alter_table("service_orders") as batch_op:
        batch_op.create_unique_constraint(
            "uq_service_orders_company_order_number",
            ["company_id", "order_number"],
        )


def downgrade():
    bind = op.get_bind()
    allocated = bind.execute(
        sa.text("SELECT COUNT(*) FROM service_order_number_counters WHERE next_value > 1")
    ).scalar_one()
    if allocated:
        raise RuntimeError("Cannot downgrade after service-order numbers have been allocated.")
    with op.batch_alter_table("service_orders") as batch_op:
        batch_op.drop_constraint("uq_service_orders_company_order_number", type_="unique")
    op.drop_table("service_order_number_counters")
    op.drop_column("companies", "service_order_number_digits")
    op.drop_column("companies", "service_order_include_year")
    op.drop_column("companies", "service_order_prefix")
