from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from app import db as database
from sqlalchemy import inspect, text

from scripts.db_recovery import backup, restore, verify


def test_sqlite_backup_restore_preserves_evidence_review_and_access_records():
    root = Path(os.environ["DRILLLOOP_TEST_DB_ROOT"])
    source_path = root / f"test-recovery-source-{uuid.uuid4().hex}.sqlite3"
    backup_path = root / f"backup-{uuid.uuid4().hex}.sqlite3"
    restore_path = root / f"test-recovery-restored-{uuid.uuid4().hex}.sqlite3"
    source_url = f"sqlite:///{source_path}"
    target_url = f"sqlite:///{restore_path}"
    source_engine = database.create_database_engine(source_url)
    try:
        database.migrate_database(source_engine)
        with source_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO exercises "
                    "(id,title,scenario,exercise_date,duration_minutes,objectives_json,criteria_json,"
                    "evaluator_roles_json,participants_json,milestones_json,created_at) "
                    "VALUES ('REC-1','Synthetic recovery','Fictional','2026-11-03',60,'[{\"id\":\"O1\"}]','[]','[]','[]','[]','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO exercise_grants (id,exercise_id,user_id,organization_id,access_role,created_at) "
                    "VALUES ('grant-1','REC-1','reviewer-1','org-1','reviewer','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sources (id,exercise_id,filename,kind,mime_type,sha256,content_text,source_bytes,provenance_json,scan_status,created_at) "
                    "VALUES ('source-1','REC-1','synthetic.txt','text','text/plain','source-hash','synthetic source wording',X'0102','{}','not_scanned','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO observations "
                    "(id,exercise_id,source_id,text,event_time_raw,event_time_normalized,time_confidence,source_locator,observation_type,extraction_method,recognition_confidence,created_at) "
                    "VALUES ('obs-1','REC-1','source-1','Source wording',NULL,NULL,'unknown','line 1','note','parser',NULL,'2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO findings "
                    "(id,exercise_id,code,title,category,objective_id,observation,interpretation,evidence_ids_json,confidence,status,review_note,reviewer,created_at,updated_at) "
                    "VALUES ('finding-1','REC-1','TEST','Proposed','improvement','O1','Source wording','Interpretation','[\"obs-1\"]','medium','approved','human review','reviewer-1','2026-11-03 00:00:00','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO corrective_actions "
                    "(id,exercise_id,finding_id,title,evidence_ids_json,owner,priority,due_date,acceptance_criteria,status,reviewer_decision,reviewer,closure_evidence,created_at,updated_at) "
                    "VALUES ('action-1','REC-1','finding-1','Action','[\"obs-1\"]','Synthetic team','medium','2026-12-01','Retest','closed','approved','reviewer-1','synthetic closure record','2026-11-03 00:00:00','2026-11-03 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO audit_events (id,exercise_id,actor,action,object_id,details_json,created_at) "
                    "VALUES ('audit-1','REC-1','reviewer-1','finding_reviewed','finding-1','{}','2026-11-03 00:00:00')"
                )
            )
        source_engine.dispose()

        created = backup(source_url, source_path.name, str(backup_path))
        verify(created)
        target_name = restore_path.name
        restored = restore(str(backup_path), target_url, target_name)
        assert restored == str(restore_path)

        restored_engine = database.create_database_engine(target_url, require_new_test_db=False)
        try:
            database.init_db(target_engine=restored_engine)
            with restored_engine.connect() as connection:
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
                assert (
                    connection.scalar(text("SELECT source_bytes FROM sources WHERE id='source-1'"))
                    == b"\x01\x02"
                )
                assert (
                    connection.scalar(text("SELECT scan_status FROM sources WHERE id='source-1'"))
                    == "not_scanned"
                )
                assert (
                    connection.scalar(text("SELECT reviewer FROM findings WHERE id='finding-1'"))
                    == "reviewer-1"
                )
                assert (
                    connection.scalar(
                        text("SELECT reviewer_decision FROM corrective_actions WHERE id='action-1'")
                    )
                    == "approved"
                )
                assert (
                    connection.scalar(text("SELECT actor FROM audit_events WHERE id='audit-1'"))
                    == "reviewer-1"
                )
        finally:
            restored_engine.dispose()
    finally:
        source_engine.dispose()
        source_path.unlink(missing_ok=True)
        backup_path.unlink(missing_ok=True)
        restore_path.unlink(missing_ok=True)


def test_backup_and_restore_refuse_existing_targets():
    root = Path(os.environ["DRILLLOOP_TEST_DB_ROOT"])
    db_path = root / f"test-recovery-refuse-{uuid.uuid4().hex}.sqlite3"
    engine = database.create_database_engine(f"sqlite:///{db_path}")
    try:
        database.migrate_database(engine)
    finally:
        engine.dispose()

    try:
        with pytest.raises(SystemExit, match="already exists"):
            restore(str(db_path), f"sqlite:///{db_path}", db_path.name)
    finally:
        db_path.unlink(missing_ok=True)


def test_legacy_sqlite_backup_preserves_unversioned_data_without_stamping():
    root = Path(os.environ["DRILLLOOP_TEST_DB_ROOT"])
    source_path = root / f"test-legacy-{uuid.uuid4().hex}.sqlite3"
    archive = root / f"backup-legacy-{uuid.uuid4().hex}.sqlite3"
    restored_path = root / f"test-legacy-restored-{uuid.uuid4().hex}.sqlite3"
    try:
        with database.create_database_engine(f"sqlite:///{source_path}").begin() as connection:
            connection.execute(text("CREATE TABLE legacy (id TEXT PRIMARY KEY, value TEXT)"))
            connection.execute(text("INSERT INTO legacy VALUES ('1', 'keep-me')"))
        backup(f"sqlite:///{source_path}", source_path.name, str(archive))
        restore(str(archive), f"sqlite:///{restored_path}", restored_path.name)
        with database.create_database_engine(
            f"sqlite:///{restored_path}", require_new_test_db=False
        ).connect() as connection:
            assert connection.scalar(text("SELECT value FROM legacy WHERE id='1'")) == "keep-me"
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        source_path.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        restored_path.unlink(missing_ok=True)
