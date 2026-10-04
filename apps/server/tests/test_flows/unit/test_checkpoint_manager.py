from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from flows.utils.helpers import checkpoint_manager as cm_mod


class _FakeSessionCtx:
    def __init__(self, session_obj):
        self.session_obj = session_obj

    def __enter__(self):
        return self.session_obj

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeCheckpointService:
    def __init__(self):
        self.upsert_calls = []

    def upsert(self, session, novel_id, stage, data, status=None, job_id=None, error=None):
        self.upsert_calls.append(
            {
                "session": session,
                "novel_id": novel_id,
                "stage": stage,
                "data": data,
                "status": status,
                "job_id": job_id,
                "error": error,
            }
        )
        return SimpleNamespace(stage_status=status or "processing")

    def get(self, _session, _novel_id, _stage, job_id=None):
        return None

    def get_latest(self, _session, _novel_id, job_id=None):
        return None

    def delete_all(self, _session, _novel_id):
        return None


class TestCheckpointManager:
    def test_novel_wide_clear_api_is_not_exposed(self):
        assert not hasattr(cm_mod.CheckpointManager, "clear_checkpoints")

    def test_update_checkpoint_passes_none_data_verbatim(self, monkeypatch):
        fake_service = _FakeCheckpointService()
        fake_session = MagicMock()

        monkeypatch.setattr(cm_mod, "CheckpointService", lambda: fake_service)
        monkeypatch.setattr(cm_mod, "get_run_logger", lambda: MagicMock())

        import flows.database_session as dbs

        monkeypatch.setattr(dbs, "get_prefect_db_session", lambda: _FakeSessionCtx(fake_session))

        manager = cm_mod.CheckpointManager(novel_id=1, job_id=9)
        manager.update_checkpoint("stage1", status="processing", data=None)

        assert len(fake_service.upsert_calls) == 1
        call = fake_service.upsert_calls[0]
        assert call["data"] is None
        assert call["stage"] == "stage1"
        assert call["status"] == "processing"
        assert call["job_id"] == 9

    def test_parse_checkpoint_data_handles_json_and_invalid(self, monkeypatch):
        monkeypatch.setattr(cm_mod, "get_run_logger", lambda: MagicMock())
        manager = cm_mod.CheckpointManager(novel_id=1)

        valid = SimpleNamespace(checkpoint_data='{"a": 1}')
        invalid = SimpleNamespace(checkpoint_data="not-json")

        assert manager._parse_checkpoint_data(valid) == {"a": 1}
        assert manager._parse_checkpoint_data(invalid) == {}
        assert manager._parse_checkpoint_data(None) == {}

    def test_can_resume_only_processing_or_failed(self, monkeypatch):
        monkeypatch.setattr(cm_mod, "get_run_logger", lambda: MagicMock())
        manager = cm_mod.CheckpointManager(novel_id=1)

        manager.get_latest_checkpoint = lambda: SimpleNamespace(stage_status="processing")
        assert manager.can_resume() is True

        manager.get_latest_checkpoint = lambda: SimpleNamespace(stage_status="failed")
        assert manager.can_resume() is True

        manager.get_latest_checkpoint = lambda: SimpleNamespace(stage_status="completed")
        assert manager.can_resume() is False

    def test_get_pending_chapters_retries_failed_and_preserves_input_order(self, monkeypatch):
        monkeypatch.setattr(cm_mod, "get_run_logger", lambda: MagicMock())
        manager = cm_mod.CheckpointManager(novel_id=1)

        manager.get_completed_chapters = lambda _stage, _capability="summaries": [1, 2]
        manager.get_failed_chapters = lambda _stage, _capability="summaries": [4]

        pending = manager.get_pending_chapters("stage1", [1, 2, 3, 4, 5])
        assert pending == [3, 4, 5]

    def test_get_pending_chapters_uses_independent_capability_keys(self, monkeypatch):
        monkeypatch.setattr(cm_mod, "get_run_logger", lambda: MagicMock())
        manager = cm_mod.CheckpointManager(novel_id=1)
        manager.get_checkpoint = lambda _stage: SimpleNamespace(
            stage_status="processing",
            checkpoint_data={
                "completed_chapter_ids": [1, 2, 3],
                "completed_plot_chapter_ids": [1],
                "failed_plot_chapter_ids": [2],
                "completed_mention_chapter_ids": [2],
                "failed_mention_chapter_ids": [3],
            },
        )

        all_ids = [1, 2, 3, 4, 4, 999]
        assert manager.get_pending_chapters("stage1", all_ids, capability="summaries") == [4, 999]
        assert manager.get_pending_chapters("stage1", all_ids, capability="plots") == [2, 3, 4, 999]
        assert manager.get_pending_chapters("stage1", all_ids, capability="mentions") == [1, 3, 4, 999]

    def test_get_and_latest_checkpoint_pass_job_id(self, monkeypatch):
        calls = []

        class _Svc(_FakeCheckpointService):
            def get(self, session, novel_id, stage, job_id=None):
                calls.append(("get", novel_id, stage, job_id))
                return None

            def get_latest(self, session, novel_id, job_id=None):
                calls.append(("latest", novel_id, job_id))
                return None

        fake_session = MagicMock()
        monkeypatch.setattr(cm_mod, "CheckpointService", _Svc)
        monkeypatch.setattr(cm_mod, "get_run_logger", lambda: MagicMock())
        import flows.database_session as dbs
        monkeypatch.setattr(dbs, "get_prefect_db_session", lambda: _FakeSessionCtx(fake_session))

        manager = cm_mod.CheckpointManager(novel_id=7, job_id=91)
        manager.get_checkpoint("stage1")
        manager.get_latest_checkpoint()

        assert calls == [("get", 7, "stage1", 91), ("latest", 7, 91)]

    def test_service_type_error_does_not_retry_unscoped(self, monkeypatch):
        calls = []

        class _Svc(_FakeCheckpointService):
            def get(self, session, novel_id, stage, job_id=None):
                calls.append((novel_id, stage, job_id))
                raise TypeError("service implementation failure")

        monkeypatch.setattr(cm_mod, "CheckpointService", _Svc)
        monkeypatch.setattr(cm_mod, "get_run_logger", lambda: MagicMock())
        import flows.database_session as dbs
        monkeypatch.setattr(
            dbs,
            "get_prefect_db_session",
            lambda: _FakeSessionCtx(MagicMock()),
        )

        manager = cm_mod.CheckpointManager(novel_id=7, job_id=91)
        with pytest.raises(TypeError, match="service implementation failure"):
            manager.get_checkpoint("stage1")

        assert calls == [(7, "stage1", 91)]
