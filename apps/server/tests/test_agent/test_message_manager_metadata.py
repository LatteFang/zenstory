"""Focused persistence metadata regressions for MessageManager."""

import json

from agent.core.message_manager import MessageManager


def test_message_metadata_omits_display_events_for_legacy_callers() -> None:
    manager = MessageManager(project_id="project-1")

    serialized = manager._serialize_message_metadata(
        stop_reason="end_turn",
        usage={"total_tokens": 3},
    )

    assert serialized is not None
    assert json.loads(serialized) == {
        "stop_reason": "end_turn",
        "usage": {"total_tokens": 3},
    }
