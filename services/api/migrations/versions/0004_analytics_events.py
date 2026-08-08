"""analytics events

Revision ID: 0004_analytics_events
Revises: 0003_affiliate_attribution
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_analytics_events"
down_revision = "0003_affiliate_attribution"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("event_name", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("decision_id", sa.Integer(), nullable=True),
        sa.Column("purchase_id", sa.Integer(), nullable=True),
        sa.Column("conversion_id", sa.Integer(), nullable=True),
        sa.Column("value_cents", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]), sa.ForeignKeyConstraint(["product_id"], ["products.id"]), sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"]), sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"]), sa.ForeignKeyConstraint(["conversion_id"], ["affiliate_conversions.id"]), sa.UniqueConstraint("event_id"))
    for name, cols in (("ix_analytics_events_event_name", ["event_name"]), ("ix_analytics_events_user_id", ["user_id"]), ("ix_analytics_events_product_id", ["product_id"]), ("ix_analytics_events_occurred_at", ["occurred_at"])):
        op.create_index(name, "analytics_events", cols)

def downgrade() -> None:
    op.drop_table("analytics_events")
