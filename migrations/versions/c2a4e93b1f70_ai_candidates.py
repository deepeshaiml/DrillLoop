"""Bind exercise ownership and add durable AI candidate history."""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import context, op

revision = "c2a4e93b1f70"
down_revision = "a53481bc2d73"
branch_labels = None
depends_on = None


def _unique_owner_entries(pairs: list[tuple[str, object]]) -> dict[str, object]:
    entries = {}
    for exercise_id, owner in pairs:
        if exercise_id in entries:
            raise RuntimeError(
                f"Owner manifest has a duplicate exercise ID {exercise_id!r}. "
                "Supply one reviewed decision per exercise."
            )
        entries[exercise_id] = owner
    return entries


def _owners(connection) -> dict[str, str]:
    retained = {}
    for exercise_id, organization_id in connection.execute(
        sa.text(
            "SELECT e.id, g.organization_id FROM exercises e LEFT JOIN exercise_grants g "
            "ON e.id = g.exercise_id ORDER BY e.id"
        )
    ):
        retained.setdefault(exercise_id, set()).add(organization_id)

    resolved = {}
    unresolved = {}
    for exercise_id, organizations in retained.items():
        if len(organizations) == 1:
            organization_id = next(iter(organizations))
            if organization_id and organization_id.strip():
                resolved[exercise_id] = organization_id
                continue
        unresolved[exercise_id] = (
            "no retained grant" if organizations == {None} else "conflicting or blank grant scope"
        )

    filename = context.get_x_argument(as_dictionary=True).get("exercise_owners")
    if filename:
        explicit = json.loads(
            Path(filename).read_text(encoding="utf-8"), object_pairs_hook=_unique_owner_entries
        )
        if (
            not isinstance(explicit, dict)
            or set(explicit) - unresolved.keys()
            or any(
                not isinstance(owner, str)
                or not owner.strip()
                or len(owner) > 120
                or "\x00" in owner
                for owner in explicit.values()
            )
        ):
            raise RuntimeError(
                "Owner manifest must map unresolved exercise IDs to valid organization IDs."
            )
        resolved.update(explicit)
        for exercise_id in explicit:
            del unresolved[exercise_id]
    if unresolved:
        raise RuntimeError(
            "Exercise ownership preflight stopped the migration. Obtain an explicit owner decision "
            "for each exercise and supply -x exercise_owners=<reviewed-json>. "
            + json.dumps(unresolved, sort_keys=True)
        )
    return resolved


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Exercise ownership preflight requires an online migration connection.")
    connection = op.get_bind()
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
    else:
        connection.exec_driver_sql("LOCK TABLE exercises, exercise_grants IN ACCESS EXCLUSIVE MODE")
    owners = _owners(connection)
    if sqlite:
        broken_reference = connection.exec_driver_sql("PRAGMA foreign_key_check").first()
        if broken_reference:
            raise RuntimeError(
                f"Existing foreign-key violation in {broken_reference[0]} row "
                f"{broken_reference[1]}. Resolve integrity before applying the migration."
            )

    # A temporary empty default permits an additive SQLite ALTER on populated tables.
    # The insert guard below rejects that value after the reviewed backfill.
    op.add_column(
        "exercises",
        sa.Column("organization_id", sa.String(120), nullable=False, server_default=sa.text("''")),
    )
    if owners:
        connection.execute(
            sa.text("UPDATE exercises SET organization_id = :owner WHERE id = :exercise_id"),
            [{"exercise_id": exercise_id, "owner": owner} for exercise_id, owner in owners.items()],
        )
    op.create_index(
        "ux_exercises_id_organization", "exercises", ["id", "organization_id"], unique=True
    )
    if sqlite:
        op.execute("""
            CREATE TRIGGER exercises_owner_required BEFORE INSERT ON exercises
            WHEN length(trim(NEW.organization_id)) = 0
            BEGIN SELECT RAISE(ABORT, 'Exercise organization is required'); END
        """)
        op.execute("""
            CREATE TRIGGER exercises_owner_immutable BEFORE UPDATE OF organization_id ON exercises
            WHEN OLD.organization_id IS NOT NEW.organization_id
            BEGIN SELECT RAISE(ABORT, 'Exercise organization is immutable'); END
        """)
    else:
        op.execute("""
            CREATE FUNCTION drillloop_require_exercise_owner() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF length(trim(NEW.organization_id)) = 0 THEN
                    RAISE EXCEPTION 'Exercise organization is required' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.organization_id IS DISTINCT FROM NEW.organization_id THEN
                    RAISE EXCEPTION 'Exercise organization is immutable' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END
            $$
        """)
        op.execute("""
            CREATE TRIGGER exercises_owner_guard BEFORE INSERT OR UPDATE OF organization_id ON exercises
            FOR EACH ROW EXECUTE FUNCTION drillloop_require_exercise_owner()
        """)

    op.add_column("audit_events", sa.Column("candidate_version", sa.Integer()))
    op.create_index(
        "ux_audit_events_candidate_version",
        "audit_events",
        ["exercise_id", "object_id", "candidate_version"],
        unique=True,
    )
    op.create_table(
        "ai_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("exercise_id", sa.String(80), nullable=False),
        sa.Column("organization_id", sa.String(120), nullable=False),
        sa.Column("issuance_id", sa.String(36), nullable=False, unique=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_state", sa.String(32), nullable=False),
        sa.Column("freshness", sa.String(8), nullable=False),
        sa.Column("stale_at", sa.DateTime(timezone=True)),
        sa.Column("stale_reasons_json", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["exercise_id", "organization_id"],
            ["exercises.id", "exercises.organization_id"],
            name="fk_ai_candidate_exercise_owner",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "review_state IN ('pending_review', 'accepted_for_consideration', 'rejected', 'more_evidence_required')",
            name="ck_ai_candidate_review_state",
        ),
        sa.CheckConstraint(
            "(freshness = 'current' AND stale_at IS NULL) OR (freshness = 'stale' AND stale_at IS NOT NULL)",
            name="ck_ai_candidate_freshness",
        ),
        sa.CheckConstraint("version >= 1", name="ck_ai_candidate_version"),
    )
    op.create_index(
        "ux_ai_candidates_scope",
        "ai_candidates",
        ["exercise_id", "organization_id", "id"],
        unique=True,
    )
    _protect_candidate_snapshot(sqlite)
    op.create_table(
        "ai_candidate_requests",
        sa.Column("exercise_id", sa.String(80), primary_key=True),
        sa.Column("organization_id", sa.String(120), primary_key=True),
        sa.Column("actor_user_id", sa.String(120), primary_key=True),
        sa.Column("operation", sa.String(8), primary_key=True),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("applied_version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(32)),
        sa.ForeignKeyConstraint(
            ["exercise_id", "organization_id", "candidate_id"],
            ["ai_candidates.exercise_id", "ai_candidates.organization_id", "ai_candidates.id"],
            name="fk_ai_candidate_request_candidate_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "operation IN ('save', 'review')", name="ck_ai_candidate_request_operation"
        ),
        sa.CheckConstraint("applied_version >= 1", name="ck_ai_candidate_request_version"),
    )


def _protect_candidate_snapshot(sqlite: bool) -> None:
    immutable = (
        "id",
        "exercise_id",
        "organization_id",
        "issuance_id",
        "snapshot_json",
        "created_at",
    )
    columns = ", ".join(immutable)
    if sqlite:
        changed = " OR ".join(f"OLD.{col} IS NOT NEW.{col}" for col in immutable)
        op.execute(f"""
            CREATE TRIGGER ai_candidate_snapshot_immutable
            BEFORE UPDATE OF {columns} ON ai_candidates
            WHEN {changed}
            BEGIN SELECT RAISE(ABORT, 'AI candidate snapshot is immutable'); END
        """)
    else:
        old_values = ", ".join(f"OLD.{col}" for col in immutable)
        new_values = ", ".join(f"NEW.{col}" for col in immutable)
        op.execute(f"""
            CREATE FUNCTION drillloop_protect_candidate_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF ROW({old_values}) IS DISTINCT FROM ROW({new_values}) THEN
                    RAISE EXCEPTION 'AI candidate snapshot is immutable' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END
            $$
        """)
        op.execute(f"""
            CREATE TRIGGER ai_candidate_snapshot_immutable
            BEFORE UPDATE OF {columns} ON ai_candidates
            FOR EACH ROW EXECUTE FUNCTION drillloop_protect_candidate_snapshot()
        """)


def downgrade() -> None:
    raise RuntimeError("DrillLoop schema migrations are forward-only. Restore a verified backup.")
