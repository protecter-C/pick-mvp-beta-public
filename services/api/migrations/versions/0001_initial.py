"""Initial PICK persistence schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("referral_code", sa.String(20), nullable=False), sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"), sa.UniqueConstraint("referral_code"))
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_referral_code", "users", ["referral_code"])
    op.create_table("products",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False), sa.Column("name", sa.String(240), nullable=False),
        sa.Column("category", sa.String(80), nullable=False), sa.Column("merchant", sa.String(120), nullable=False),
        sa.Column("image_url", sa.Text()), sa.Column("current_price_cents", sa.Integer(), nullable=False),
        sa.Column("typical_price_cents", sa.Integer(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False), sa.UniqueConstraint("external_id"))
    for name, column in (("ix_products_external_id", "external_id"), ("ix_products_category", "category")):
        op.create_index(name, "products", [column])
    op.create_table("decisions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("verdict", sa.String(4), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False), sa.Column("budget_cents", sa.Integer(), nullable=False),
        sa.Column("urgency", sa.Integer(), nullable=False), sa.Column("fit", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("prevented_spend_cents", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_decisions_user_id", "decisions", ["user_id"]); op.create_index("ix_decisions_product_id", "decisions", ["product_id"]); op.create_index("ix_decisions_verdict", "decisions", ["verdict"])
    op.create_table("price_points", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("price_cents", sa.Integer(), nullable=False), sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_price_points_product_id", "price_points", ["product_id"])
    op.create_table("price_watches", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("target_price_cents", sa.Integer(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "product_id"))
    op.create_index("ix_price_watches_user_id", "price_watches", ["user_id"]); op.create_index("ix_price_watches_product_id", "price_watches", ["product_id"])
    op.create_table("purchases", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("decision_id", sa.Integer(), sa.ForeignKey("decisions.id")), sa.Column("price_paid_cents", sa.Integer(), nullable=False), sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False), sa.Column("return_deadline", sa.DateTime(timezone=True)), sa.Column("warranty_deadline", sa.DateTime(timezone=True)), sa.Column("satisfaction", sa.Integer()), sa.Column("returned", sa.Boolean(), nullable=False))
    op.create_index("ix_purchases_user_id", "purchases", ["user_id"]); op.create_index("ix_purchases_product_id", "purchases", ["product_id"])
    op.create_table("points_entries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("amount", sa.Integer(), nullable=False), sa.Column("reason", sa.String(80), nullable=False), sa.Column("reference_type", sa.String(40), nullable=False), sa.Column("reference_id", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_points_entries_user_id", "points_entries", ["user_id"])
    op.create_table("referrals", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("referrer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("referred_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("referred_user_id"))
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])
    op.create_table("notifications", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("kind", sa.String(40), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("body", sa.Text(), nullable=False), sa.Column("read", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"]); op.create_index("ix_notifications_kind", "notifications", ["kind"])


def downgrade() -> None:
    for table in ("notifications", "referrals", "points_entries", "purchases", "price_watches", "price_points", "decisions", "products", "users"):
        op.drop_table(table)
