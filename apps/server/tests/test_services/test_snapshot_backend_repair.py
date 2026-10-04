"""Regression locks for M06 snapshot fidelity, atomicity, and metadata diffs."""

import json
from datetime import timedelta

import pytest
from sqlmodel import Session, func, select

from config.datetime_utils import utcnow
from models import File, FileVersion, Project, Snapshot, User
from models.file_version import CHANGE_TYPE_RESTORE
from services.features.file_version_service import get_file_version_service
from services.features.snapshot_service import VersionService


def _project_with_files(db_session: Session, contents: tuple[str, ...]) -> tuple[Project, list[File]]:
    user = User(
        email=f"m06-{len(contents)}@example.com",
        username=f"m06-{len(contents)}",
        hashed_password="hashed",
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    project = Project(name="M06", owner_id=user.id)
    db_session.add(project)
    db_session.flush()

    files: list[File] = []
    for index, content in enumerate(contents):
        file = File(
            title=f"File {index}",
            content=content,
            file_type="draft",
            project_id=project.id,
            user_id=user.id,
            order=index,
        )
        db_session.add(file)
        db_session.flush()
        db_session.add(
            FileVersion(
                file_id=file.id,
                project_id=project.id,
                version_number=1,
                content=content,
                word_count=1,
                char_count=len(content),
                is_base_version=True,
            )
        )
        files.append(file)
    db_session.commit()
    return project, files


@pytest.mark.unit
def test_snapshot_pins_live_content_when_latest_version_is_stale(db_session: Session):
    service = VersionService()
    project, files = _project_with_files(db_session, ("A",))
    file = files[0]

    file.content = "B"
    db_session.add(file)
    db_session.commit()

    snapshot = service.create_snapshot(db_session, project.id)
    snapshot_data = json.loads(snapshot.data)
    reference = snapshot_data["file_versions"][0]
    assert get_file_version_service().get_content_at_version(
        db_session, file.id, reference["version_number"]
    ) == "B"

    file.content = "C"
    db_session.add(file)
    db_session.commit()
    service.rollback_to_snapshot(db_session, snapshot.id)
    db_session.refresh(file)
    assert file.content == "B"


@pytest.mark.unit
def test_project_rollback_failure_is_fully_atomic(db_session: Session, monkeypatch):
    service = VersionService()
    project, files = _project_with_files(db_session, ("A1", "A2"))
    snapshot = service.create_snapshot(db_session, project.id)

    for index, file in enumerate(files, start=1):
        file.content = f"B{index}"
        db_session.add(file)
    db_session.commit()

    version_count_before = db_session.exec(select(func.count(FileVersion.id))).one()
    snapshot_count_before = db_session.exec(select(func.count(Snapshot.id))).one()
    file_version_service = get_file_version_service()
    original_create_version = file_version_service.create_version
    restore_calls = 0

    def fail_second_restore(*args, **kwargs):
        nonlocal restore_calls
        if kwargs.get("change_type") == CHANGE_TYPE_RESTORE:
            restore_calls += 1
            if restore_calls == 2:
                raise RuntimeError("injected second-file restore failure")
        return original_create_version(*args, **kwargs)

    monkeypatch.setattr(file_version_service, "create_version", fail_second_restore)

    with pytest.raises(RuntimeError, match="injected second-file restore failure"):
        service.rollback_to_snapshot(db_session, snapshot.id)

    db_session.expire_all()
    assert [db_session.get(File, file.id).content for file in files] == ["B1", "B2"]
    assert db_session.exec(select(func.count(FileVersion.id))).one() == version_count_before
    assert db_session.exec(select(func.count(Snapshot.id))).one() == snapshot_count_before


@pytest.mark.unit
def test_compare_snapshots_includes_metadata_and_folder_changes(db_session: Session):
    service = VersionService()
    project, files = _project_with_files(db_session, ("same",))
    file = files[0]
    old = Snapshot(
        project_id=project.id,
        version=3,
        created_at=utcnow() - timedelta(seconds=1),
        data=json.dumps(
            {
                "version": 3,
                "file_versions": [{"file_id": file.id, "version_number": 1}],
                "files_metadata": [{"id": file.id, "title": "Old", "file_type": "draft", "parent_id": None, "order": 0}],
            }
        ),
    )
    folder_id = "folder-added"
    new = Snapshot(
        project_id=project.id,
        version=3,
        created_at=utcnow(),
        data=json.dumps(
            {
                "version": 3,
                "file_versions": [{"file_id": file.id, "version_number": 1}],
                "files_metadata": [
                    {"id": file.id, "title": "Renamed", "file_type": "script", "parent_id": folder_id, "order": 2},
                    {"id": folder_id, "title": "Folder", "file_type": "folder", "parent_id": None, "order": 0},
                ],
            }
        ),
    )
    db_session.add(old)
    db_session.add(new)
    db_session.commit()

    changes = service.compare_snapshots(db_session, snapshot1=old, snapshot2=new)["changes"]

    assert [entry["file_id"] for entry in changes["added"]] == [folder_id]
    modified = next(entry for entry in changes["modified"] if entry["file_id"] == file.id)
    assert set(modified["metadata_changes"]) == {"title", "file_type", "parent_id", "order"}
