"""beta operations

Revision ID: 0005_beta_operations
Revises: 0004_analytics_events
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_beta_operations"
down_revision = "0004_analytics_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "beta_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_beta_invites_email", "beta_invites", ["email"])
    op.create_table(
        "beta_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"]),
        sa.UniqueConstraint("user_id", "decision_id"),
    )
    op.create_index("ix_beta_feedback_user_id", "beta_feedback", ["user_id"])
    op.create_index("ix_beta_feedback_decision_id", "beta_feedback", ["decision_id"])
    op.create_index("ix_beta_feedback_category", "beta_feedback", ["category"])


def downgrade() -> None:
    op.drop_table("beta_feedback")
    op.drop_table("beta_invites")
