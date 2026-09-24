"""seed standard VAT rates per company

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
"""

from alembic import op
import sqlalchemy as sa

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None

STANDARD_RATES = [
    ("23%", "23", "23.00", True),
    ("8%", "8", "8.00", False),
    ("5%", "5", "5.00", False),
    ("0%", "0", "0.00", False),
    ("zw.", "zw", "0.00", False),
]


def _columns(inspector, table):
    return {column["name"] for column in inspector.get_columns(table)} if inspector.has_table(table) else set()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("companies") or not inspector.has_table("vat_rates"):
        return

    columns = _columns(inspector, "vat_rates")
    if "is_default" not in columns:
        op.add_column("vat_rates", sa.Column("is_default", sa.Boolean(), nullable=True))
        op.execute(sa.text("UPDATE vat_rates SET is_default = 0 WHERE is_default IS NULL"))
    if "is_active" not in columns:
        op.add_column("vat_rates", sa.Column("is_active", sa.Boolean(), nullable=True))
        op.execute(sa.text("UPDATE vat_rates SET is_active = 1 WHERE is_active IS NULL"))

    companies = [row[0] for row in bind.execute(sa.text("SELECT id FROM companies")).fetchall()]
    for company_id in companies:
        for code, legacy_code, rate, is_default in STANDARD_RATES:
            existing = bind.execute(
                sa.text(
                    """
                    SELECT id, code FROM vat_rates
                    WHERE company_id = :company_id
                      AND (LOWER(code) = LOWER(:code) OR LOWER(code) = LOWER(:legacy_code))
                    ORDER BY id
                    LIMIT 1
                    """
                ),
                {"company_id": company_id, "code": code, "legacy_code": legacy_code},
            ).fetchone()
            if existing is None:
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO vat_rates
                            (code, rate, is_default, is_active, company_id, branch_id, uuid, created_at, updated_at, version)
                        VALUES
                            (:code, :rate, :is_default, 1, :company_id, NULL, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                        """
                    ),
                    {
                        "code": code,
                        "rate": rate,
                        "is_default": 1 if is_default else 0,
                        "company_id": company_id,
                        "uuid": f"vat-{company_id}-{code}"[:36],
                    },
                )
            elif existing[1] != code and code != "zw.":
                bind.execute(sa.text("UPDATE vat_rates SET code = :code WHERE id = :id"), {"code": code, "id": existing[0]})

        default_id = bind.execute(
            sa.text(
                """
                SELECT id FROM vat_rates
                WHERE company_id = :company_id AND code = '23%'
                ORDER BY id
                LIMIT 1
                """
            ),
            {"company_id": company_id},
        ).scalar()
        if default_id is not None:
            bind.execute(sa.text("UPDATE vat_rates SET is_default = 0 WHERE company_id = :company_id"), {"company_id": company_id})
            bind.execute(sa.text("UPDATE vat_rates SET is_default = 1, is_active = 1 WHERE id = :id"), {"id": default_id})
            if inspector.has_table("inventory_items") and "vat_id" in _columns(inspector, "inventory_items"):
                bind.execute(
                    sa.text(
                        """
                        UPDATE inventory_items
                        SET vat_id = :default_id
                        WHERE company_id = :company_id AND vat_id IS NULL
                        """
                    ),
                    {"default_id": default_id, "company_id": company_id},
                )


def downgrade():
    pass
