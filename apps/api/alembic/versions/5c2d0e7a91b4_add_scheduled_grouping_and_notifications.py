"""add scheduled grouping jobs and private notifications

Revision ID: 5c2d0e7a91b4
Revises: 0f11a0b3e90b
"""

import sqlalchemy as sa

from alembic import op

revision = "5c2d0e7a91b4"
down_revision = "0f11a0b3e90b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grouping_jobs",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(
            ["run_id", "event_id"], ["grouping_runs.id", "grouping_runs.event_id"]
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'BLOCKED', 'FAILED')", name="grouping_job_status"
        ),
        sa.CheckConstraint("attempts > 0", name="grouping_job_attempts"),
        sa.CheckConstraint(
            "(status = 'SUCCEEDED') = (run_id IS NOT NULL)", name="grouping_job_result"
        ),
    )
    op.create_index("ix_grouping_jobs_status_retry", "grouping_jobs", ["status", "next_attempt_at"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("dedup_key", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("destination", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.UniqueConstraint("user_id", "dedup_key", name="notification_user_key"),
        sa.CheckConstraint(
            "destination IN ('ACCOUNT', 'EVENT', 'ORGANIZER')", name="notification_destination"
        ),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notifications) OR EXISTS (SELECT 1 FROM grouping_jobs)"
        )
    ):
        raise RuntimeError(
            "Back up and resolve notifications and job records before downgrading Phase 5"
        )
    op.drop_table("notifications")
    op.drop_table("grouping_jobs")
