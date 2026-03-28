from pathlib import Path

import yaml


def test_ci_required_and_informational_gate_semantics():
    workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = workflow.get("jobs", {})
    assert "test" in jobs
    assert "lint" in jobs
    assert "typecheck" in jobs
    assert jobs["typecheck"].get("continue-on-error") is True
