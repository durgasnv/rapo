"""add grouping proposals and team history

Revision ID: 204fca679124
Revises: c72a0e51b238
"""

import sqlalchemy as sa

from alembic import op

revision = "204fca679124"
down_revision = "c72a0e51b238"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("event_status", "events", type_="check")
    op.create_check_constraint(
        "event_status",
        "events",
        "status IN ('DRAFT', 'PUBLISHED', 'GROUPS_PROPOSED', 'GROUPS_FINALIZED', "
        "'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
    )
    op.create_table(
        "grouping_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("min_team_size", sa.Integer(), nullable=False),
        sa.Column("max_team_size", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("fairness", sa.BigInteger(), nullable=False),
        sa.Column("baseline_score", sa.Integer(), nullable=False),
        sa.Column("baseline_fairness", sa.BigInteger(), nullable=False),
        sa.Column("evaluations", sa.Integer(), nullable=False),
        sa.Column("history_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("event_id", "request_id", name="grouping_request"),
        sa.CheckConstraint("status IN ('PROPOSED', 'FINALIZED')", name="grouping_status"),
        sa.CheckConstraint("seed >= 0 AND seed <= 2147483647", name="grouping_seed"),
        sa.CheckConstraint(
            "score >= 0 AND fairness >= 0 AND baseline_score >= 0 "
            "AND baseline_fairness >= 0 AND evaluations >= 0",
            name="grouping_score",
        ),
        sa.CheckConstraint(
            "min_team_size >= 1 AND max_team_size >= min_team_size", name="grouping_sizes"
        ),
    )
    op.create_index("ix_grouping_runs_event_created", "grouping_runs", ["event_id", "created_at"])
    op.create_index(
        "uq_finalized_grouping_event",
        "grouping_runs",
        ["event_id"],
        unique=True,
        postgresql_where=sa.text("status = 'FINALIZED'"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["grouping_runs.id"]),
        sa.UniqueConstraint("run_id", "number", name="team_run_number"),
        sa.UniqueConstraint("id", "run_id", name="team_id_run"),
        sa.CheckConstraint("number > 0", name="team_number"),
        sa.CheckConstraint("score >= 0", name="team_score"),
    )
    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id", "run_id"], ["teams.id", "teams.run_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["grouping_runs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("run_id", "user_id", name="member_run_user"),
    )
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])


def downgrade() -> None:
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("grouping_runs")
    # Downgrade is a destructive recovery operation; archive proposals first.
    op.execute("UPDATE events SET status = 'PUBLISHED' WHERE status = 'GROUPS_PROPOSED'")
    op.drop_constraint("event_status", "events", type_="check")
    op.create_check_constraint(
        "event_status", "events", "status IN ('DRAFT', 'PUBLISHED', 'CANCELLED')"
    )
