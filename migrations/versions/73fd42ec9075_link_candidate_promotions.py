"""Link promoted AI candidates to their proposed findings.

Revision ID: 73fd42ec9075
Revises: c2a4e93b1f70
"""

import sqlalchemy as sa
from alembic import op

revision = "73fd42ec9075"
down_revision = "c2a4e93b1f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ux_findings_exercise_id_id", "findings", ["exercise_id", "id"], unique=True)
    op.create_table(
        "ai_candidate_promotions",
        sa.Column("candidate_id", sa.String(36), primary_key=True),
        sa.Column("exercise_id", sa.String(80), nullable=False),
        sa.Column("organization_id", sa.String(120), nullable=False),
        sa.Column("finding_id", sa.String(36), nullable=False, unique=True),
        sa.ForeignKeyConstraint(
            ["exercise_id", "organization_id", "candidate_id"],
            ["ai_candidates.exercise_id", "ai_candidates.organization_id", "ai_candidates.id"],
            ondelete="RESTRICT",
            name="fk_ai_candidate_promotion_candidate_scope",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id", "finding_id"],
            ["findings.exercise_id", "findings.id"],
            ondelete="RESTRICT",
            name="fk_ai_candidate_promotion_finding_scope",
        ),
    )
    with op.batch_alter_table("ai_candidate_requests") as batch:
        batch.drop_constraint("ck_ai_candidate_request_operation", type_="check")
        batch.create_check_constraint(
            "ck_ai_candidate_request_operation", "operation IN ('save', 'review', 'promote')"
        )


def downgrade() -> None:
    raise RuntimeError("DrillLoop schema migrations are forward-only. Restore a verified backup.")
