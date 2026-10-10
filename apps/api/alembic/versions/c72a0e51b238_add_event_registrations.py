"""add event registrations

Revision ID: c72a0e51b238
Revises: 8d0996c80386
"""

import sqlalchemy as sa

from alembic import op

revision = "c72a0e51b238"
down_revision = "8d0996c80386"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("queue_number", sa.BigInteger(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("event_id", "user_id", name="registration_event_user"),
        sa.UniqueConstraint("event_id", "queue_number", name="registration_queue_number"),
        sa.CheckConstraint(
            "status IN ('REGISTERED', 'WAITLISTED', 'CANCELLED')", name="registration_status"
        ),
        sa.CheckConstraint("queue_number > 0", name="registration_queue_positive"),
    )
    op.create_index("ix_registrations_user_id", "registrations", ["user_id"])
    op.create_index(
        "ix_registrations_event_status_queue",
        "registrations",
        ["event_id", "status", "queue_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_registrations_event_status_queue", table_name="registrations")
    op.drop_index("ix_registrations_user_id", table_name="registrations")
    op.drop_table("registrations")
