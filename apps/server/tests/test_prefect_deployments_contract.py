import importlib
import re
from pathlib import Path

import pytest

from scripts.prefect_deployments_contract import (
    EXPECTED_DEPLOYMENTS,
    _assert_exact_deployments,
)

SERVER_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DEPLOYMENTS = {
    "chapter_extraction",
    "novel_ingestion_v3",
    "relationship_extraction",
    "story_aggregation",
}
ACTIVE_ENTRYPOINTS = {
    "flows/pipelines/novel_ingestion_v3_flow.py:novel_ingestion_v3",
    "flows/pipelines/subflows/chapter_extraction_flow.py:chapter_extraction_flow",
    "flows/pipelines/subflows/story_aggregate_flow.py:story_aggregate_flow",
    "flows/pipelines/subflows/relationship_flow.py:relationship_flow",
}


def test_prefect_yaml_registers_only_active_v3_deployments():
    prefect_yaml = (SERVER_ROOT / "prefect.yaml").read_text()

    configured = set(re.findall(r"^- name: ([a-z0-9_]+)$", prefect_yaml, re.MULTILINE))
    entrypoints = set(re.findall(r"^  entrypoint: (.+)$", prefect_yaml, re.MULTILINE))

    assert configured == ACTIVE_DEPLOYMENTS
    assert entrypoints == ACTIVE_ENTRYPOINTS

    for entrypoint in entrypoints:
        module_path, symbol = entrypoint.split(":", 1)
        module = importlib.import_module(module_path.removesuffix(".py").replace("/", "."))
        assert hasattr(module, symbol)


def test_runtime_contract_requires_only_active_v3_deployments():
    assert EXPECTED_DEPLOYMENTS == ACTIVE_DEPLOYMENTS
    _assert_exact_deployments(ACTIVE_DEPLOYMENTS)

    with pytest.raises(AssertionError, match=r"unexpected=\['novel_ingestion_v2'\]"):
        _assert_exact_deployments(ACTIVE_DEPLOYMENTS | {"novel_ingestion_v2"})


def test_retired_v2_and_unreferenced_legacy_task_modules_are_absent():
    retired_paths = [
        "flows/pipelines/novel_ingestion_v2_flow.py",
        "flows/atomic_tasks/entities/character_tasks.py",
        "flows/atomic_tasks/entities/golden_finger_tasks.py",
        "flows/atomic_tasks/entities/world_view_tasks.py",
    ]

    assert not [path for path in retired_paths if (SERVER_ROOT / path).exists()]
