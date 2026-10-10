"""add finalized teams and confirmation workflow

Revision ID: 0f11a0b3e90b
Revises: 204fca679124
"""

import sqlalchemy as sa

from alembic import op

revision = "0f11a0b3e90b"
down_revision = "204fca679124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("before_json", sa.JSON(), nullable=True))
    op.add_column("audit_logs", sa.Column("after_json", sa.JSON(), nullable=True))
    op.create_unique_constraint("grouping_id_event", "grouping_runs", ["id", "event_id"])
    op.create_table(
        "final_teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("target_size", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(
            ["run_id", "event_id"], ["grouping_runs.id", "grouping_runs.event_id"]
        ),
        sa.UniqueConstraint("event_id", "number", name="final_team_number"),
        sa.UniqueConstraint("id", "event_id", name="final_team_id_event"),
        sa.CheckConstraint(
            "number > 0 AND target_size > 0 AND version > 0", name="final_team_limits"
        ),
    )
    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(
            ["team_id", "event_id"], ["final_teams.id", "final_teams.event_id"]
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("event_id", "user_id", name="assignment_event_user"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'DECLINED', 'WITHDRAWN')", name="assignment_status"
        ),
    )
    op.create_index("ix_assignments_user_id", "assignments", ["user_id"])
    op.create_index("ix_assignments_team_status", "assignments", ["team_id", "status"])
    op.create_table(
        "roster_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.UniqueConstraint("event_id", "request_id", name="roster_request"),
    )


def downgrade() -> None:
    # Refuse to discard real assignments without a separate recovery decision.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM final_teams")):
        raise RuntimeError("Archive and resolve finalized assignments before downgrading Phase 4")
    op.drop_table("roster_actions")
    op.drop_table("assignments")
    op.drop_table("final_teams")
    op.drop_constraint("grouping_id_event", "grouping_runs", type_="unique")
    op.drop_column("audit_logs", "after_json")
    op.drop_column("audit_logs", "before_json")
