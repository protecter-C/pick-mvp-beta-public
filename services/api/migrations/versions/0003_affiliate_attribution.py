"""Add affiliate attribution and idempotent reward ledger fields."""
from alembic import op
import sqlalchemy as sa

revision = "0003_affiliate_attribution"
down_revision = "0002_price_tracking_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("points_entries", sa.Column("idempotency_key", sa.String(240), nullable=True))
    op.create_index("ix_points_entries_idempotency_key", "points_entries", ["idempotency_key"], unique=True)
    op.create_table(
        "affiliate_clicks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("click_token", sa.String(96), nullable=False),
        sa.Column("destination_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("click_token"),
    )
    op.create_index("ix_affiliate_clicks_user_id", "affiliate_clicks", ["user_id"])
    op.create_index("ix_affiliate_clicks_product_id", "affiliate_clicks", ["product_id"])
    op.create_index("ix_affiliate_clicks_provider", "affiliate_clicks", ["provider"])
    op.create_index("ix_affiliate_clicks_click_token", "affiliate_clicks", ["click_token"])
    op.create_table(
        "affiliate_conversions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("click_id", sa.Integer(), sa.ForeignKey("affiliate_clicks.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("external_conversion_id", sa.String(160), nullable=False),
        sa.Column("external_order_id", sa.String(160)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("gross_order_value_cents", sa.Integer(), nullable=False),
        sa.Column("commission_cents", sa.Integer(), nullable=False),
        sa.Column("reward_points", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("rewarded_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "external_conversion_id"),
    )
    for name, column in (("ix_affiliate_conversions_click_id", "click_id"), ("ix_affiliate_conversions_user_id", "user_id"), ("ix_affiliate_conversions_product_id", "product_id"), ("ix_affiliate_conversions_provider", "provider"), ("ix_affiliate_conversions_external_conversion_id", "external_conversion_id"), ("ix_affiliate_conversions_status", "status")):
        op.create_index(name, "affiliate_conversions", [column])


def downgrade() -> None:
    op.drop_table("affiliate_conversions")
    op.drop_table("affiliate_clicks")
    op.drop_index("ix_points_entries_idempotency_key", table_name="points_entries")
    op.drop_column("points_entries", "idempotency_key")
