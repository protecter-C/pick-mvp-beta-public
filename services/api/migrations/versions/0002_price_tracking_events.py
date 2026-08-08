"""Persist deduplicated price tracking transitions."""
from alembic import op
import sqlalchemy as sa

revision = "0002_price_tracking_events"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_tracking_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("watch_id", sa.Integer(), sa.ForeignKey("price_watches.id"), nullable=False),
        sa.Column("decision_id", sa.Integer(), sa.ForeignKey("decisions.id")),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("threshold_cents", sa.Integer(), nullable=False),
        sa.Column("observed_price_cents", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("ix_price_tracking_events_user_id", "price_tracking_events", ["user_id"])
    op.create_index("ix_price_tracking_events_product_id", "price_tracking_events", ["product_id"])
    op.create_index("ix_price_tracking_events_watch_id", "price_tracking_events", ["watch_id"])
    op.create_index("ix_price_tracking_events_decision_id", "price_tracking_events", ["decision_id"])
    op.create_index("ix_price_tracking_events_kind", "price_tracking_events", ["kind"])
    op.create_index("ix_price_tracking_events_dedupe_key", "price_tracking_events", ["dedupe_key"])


def downgrade() -> None:
    op.drop_table("price_tracking_events")
