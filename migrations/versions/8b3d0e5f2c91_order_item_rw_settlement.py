"""Link existing RW lines to order items and support consumable materials.

Revision ID: 8b3d0e5f2c91
Revises: 7a2c9f4e1b80
"""
from alembic import op
import sqlalchemy as sa

revision = "8b3d0e5f2c91"
down_revision = "7a2c9f4e1b80"
branch_labels = None
depends_on = None


def upgrade():
    if not op.get_context().as_sql:
        bind = op.get_bind()
        columns = {col["name"] for col in sa.inspect(bind).get_columns("stock_issue_items")}
        if columns & {"material_id", "service_order_item_id", "settlement_version"}:
            raise RuntimeError("Wykryto częściowo zmieniony schemat RW. Przerwij wdrożenie i uzgodnij stan; nie uruchamiaj ponownie DDL w ciemno.")
        outside_range = bind.scalar(sa.text(
            "SELECT COUNT(*) FROM stock_issue_items WHERE quantity_issued IS NULL "
            "OR quantity_issued > 999999999.999 OR quantity_issued < -999999999.999"
        ))
        if outside_range:
            raise RuntimeError("Ilości RW nie mieszczą się w DECIMAL(12,3). Migracja przerwana przed zmianą tabeli; wymagane ręczne uzgodnienie.")
    else:
        # SQL preview cannot inspect data. It must not be used instead of the
        # guarded online Alembic migration after a verified staging restore.
        op.execute("-- PREVIEW ONLY: validate quantities and schema before online migration")
    with op.batch_alter_table("stock_issue_items") as batch:
        batch.alter_column("inventory_item_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("quantity_issued", existing_type=sa.Integer(), type_=sa.Numeric(12, 3), nullable=False)
        batch.add_column(sa.Column("material_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("service_order_item_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("settlement_version", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_rw_material", "catalog_materials", ["material_id"], ["id"])
        batch.create_foreign_key("fk_rw_order_item", "service_order_items", ["service_order_item_id"], ["id"])


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Nie można bezpiecznie wygenerować downgrade bez kontroli danych online.")
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT COUNT(*) FROM stock_issue_items WHERE material_id IS NOT NULL OR service_order_item_id IS NOT NULL")):
        raise RuntimeError("Nie można usunąć powiązań istniejących rozliczeń RW.")
    if bind.scalar(sa.text(
        "SELECT COUNT(*) FROM stock_issue_items WHERE settlement_version IS NOT NULL "
        "OR inventory_item_id IS NULL OR quantity_issued IS NULL "
        "OR quantity_issued <> FLOOR(quantity_issued) "
        "OR quantity_issued < -2147483648 OR quantity_issued > 2147483647"
    )):
        raise RuntimeError("Nie można cofnąć migracji bez utraty danych wersji, ułamkowych ilości lub bez wymaganego produktu. Wymagana ręczna decyzja; DDL nie wykonano.")
    with op.batch_alter_table("stock_issue_items") as batch:
        batch.drop_constraint("fk_rw_order_item", type_="foreignkey")
        batch.drop_constraint("fk_rw_material", type_="foreignkey")
        batch.drop_column("settlement_version")
        batch.drop_column("service_order_item_id")
        batch.drop_column("material_id")
        batch.alter_column("inventory_item_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("quantity_issued", existing_type=sa.Numeric(12, 3), type_=sa.Integer(), nullable=False)