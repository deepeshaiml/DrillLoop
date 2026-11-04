from __future__ import annotations

import uuid

import pytest
from alembic import command
from app import db as database
from sqlalchemy import inspect, text


def test_initial_to_head_migration_preserves_representative_records():
    db_path = database.validate_test_database_url(
        f"sqlite:///{database.Path(database.os.environ['DRILLLOOP_TEST_DB_ROOT']) / f'test-migration-{uuid.uuid4().hex}.sqlite3'}"
    )
    migration_engine = database.create_database_engine(f"sqlite:///{db_path}")
    config = database._alembic_config()

    try:
        with migration_engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "8bb36fe0ea4c")
            connection.execute(
                text(
                    "INSERT INTO exercises "
                    "(id,title,scenario,exercise_date,duration_minutes,objectives_json,criteria_json,"
                    "evaluator_roles_json,participants_json,milestones_json,created_at) "
                    "VALUES ('MIG-1','Synthetic migration test','Fictional','2026-11-03',60,'[]','[]','[]','[]','[]','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO exercise_grants "
                    "(id,exercise_id,user_id,organization_id,access_role,created_at) "
                    "VALUES ('grant-1','MIG-1','test-user','test-org','admin','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sources "
                    "(id,exercise_id,filename,kind,mime_type,sha256,content_text,source_bytes,provenance_json,created_at) "
                    "VALUES ('source-1','MIG-1','synthetic.csv','csv','text/csv','abc','synthetic evidence',X'01','{}','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO observations "
                    "(id,exercise_id,source_id,text,event_time_raw,event_time_normalized,time_confidence,source_locator,observation_type,extraction_method,recognition_confidence,created_at) "
                    "VALUES ('obs-1','MIG-1','source-1','Fictional event',NULL,NULL,'unknown','row 2','event_log','parser',NULL,'2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO findings "
                    "(id,exercise_id,code,title,category,objective_id,observation,interpretation,evidence_ids_json,confidence,status,review_note,reviewer,created_at,updated_at) "
                    "VALUES ('finding-1','MIG-1','TEST','Synthetic proposal','improvement',NULL,'Source wording','Unknown','[\"obs-1\"]','low','proposed','','test-user','2026-11-03 00:00:00','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO corrective_actions "
                    "(id,exercise_id,finding_id,title,evidence_ids_json,owner,priority,due_date,acceptance_criteria,status,reviewer_decision,reviewer,closure_evidence,created_at,updated_at) "
                    "VALUES ('action-1','MIG-1','finding-1','Human review required','[\"obs-1\"]',NULL,'medium',NULL,'Evaluator supplied','proposed','pending',NULL,'','2026-11-03 00:00:00','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO audit_events (id,exercise_id,actor,action,object_id,details_json,created_at) "
                    "VALUES ('audit-1','MIG-1','test-user','finding_reviewed','finding-1','{}','2026-11-03 00:00:00')"
                )
            )
            connection.commit()
            command.upgrade(config, "head")
            columns = {column["name"] for column in inspect(connection).get_columns("sources")}
            assert "scan_status" in columns
            assert (
                connection.scalar(text("SELECT scan_status FROM sources WHERE id='source-1'"))
                == "not_scanned"
            )
            for table in (
                "exercises",
                "exercise_grants",
                "sources",
                "observations",
                "findings",
                "corrective_actions",
                "audit_events",
            ):
                assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
        database.init_db(target_engine=migration_engine)
    finally:
        migration_engine.dispose()
        db_path.unlink(missing_ok=True)


def test_startup_refuses_unversioned_database_without_modifying_data():
    db_path = database.validate_test_database_url(
        f"sqlite:///{database.Path(database.os.environ['DRILLLOOP_TEST_DB_ROOT']) / f'test-unversioned-{uuid.uuid4().hex}.sqlite3'}"
    )
    unversioned_engine = database.create_database_engine(f"sqlite:///{db_path}")
    try:
        with unversioned_engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE preserved (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
            )
            connection.execute(text("INSERT INTO preserved VALUES ('1','keep-me')"))
        with pytest.raises(RuntimeError, match="not versioned"):
            database.init_db(target_engine=unversioned_engine)
        with unversioned_engine.connect() as connection:
            assert connection.scalar(text("SELECT value FROM preserved WHERE id='1'")) == "keep-me"
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        unversioned_engine.dispose()
        db_path.unlink(missing_ok=True)


def test_failed_initial_migration_does_not_delete_existing_rows():
    db_path = database.validate_test_database_url(
        f"sqlite:///{database.Path(database.os.environ['DRILLLOOP_TEST_DB_ROOT']) / f'test-failed-migration-{uuid.uuid4().hex}.sqlite3'}"
    )
    existing_engine = database.create_database_engine(f"sqlite:///{db_path}")
    try:
        with existing_engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE exercises (id TEXT PRIMARY KEY, protected TEXT NOT NULL)")
            )
            connection.execute(text("INSERT INTO exercises VALUES ('existing','keep-me')"))
        with pytest.raises(Exception):
            database.migrate_database(existing_engine)
        with existing_engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT protected FROM exercises WHERE id='existing'"))
                == "keep-me"
            )
    finally:
        existing_engine.dispose()
        db_path.unlink(missing_ok=True)
