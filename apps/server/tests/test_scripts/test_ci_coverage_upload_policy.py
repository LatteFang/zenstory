"""Optional reporting must not overturn mandatory tests/coverage gates."""
from pathlib import Path

import yaml


def test_codecov_uploads_are_explicitly_nonblocking_but_tests_are_not():
    root = Path(__file__).resolve().parents[4]
    jobs = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())["jobs"]
    for name in ("backend-test", "frontend-test"):
        job = jobs[name]
        assert not job.get("continue-on-error", False)
        uploads = [step for step in job["steps"] if str(step.get("uses", "")).startswith("codecov/codecov-action@")]
        assert len(uploads) == 1
        assert uploads[0]["with"]["fail_ci_if_error"] is False
        assert uploads[0].get("continue-on-error") is True
        test_steps = [step for step in job["steps"] if "pytest" in step.get("run", "") or "test:coverage" in step.get("run", "")]
        assert test_steps
        assert all(not step.get("continue-on-error", False) for step in test_steps)
