"""Add schedule_audit_logs table

Revision ID: 1a2b3c4d5e6f
Revises: f63a9205d72f
Create Date: 2026-10-10 23:40:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e6f"
down_revision = "f63a9205d72f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "schedule_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_name", sa.String(length=128), nullable=True),
        sa.Column("ip", sa.String(length=46), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("schedule_audit_logs")
