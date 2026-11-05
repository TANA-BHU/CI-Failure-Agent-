from pathlib import Path

from fastapi.testclient import TestClient

from ci_triage import api
from tests.test_agent import stub_llm

FIX = Path(__file__).parent / "fixtures"


def test_triage_then_approve(tmp_path, monkeypatch):
    from ci_triage.agent import build_graph

    api.cfg.metrics_file = str(tmp_path / "runs.jsonl")
    monkeypatch.setattr(api, "_graph", build_graph(api.cfg, stub_llm()))
    c = TestClient(api.app)

    r = c.post("/triage", json={"ref": str(FIX / "flaky_timeout.log"), "run_id": "a1"}).json()
    assert r["status"] == "pending_approval"
    assert r["proposal"]["proposed_action"] == "rerun_failed_jobs"

    r = c.post("/approve", json={"run_id": "a1", "approve": True}).json()
    assert r["status"] == "done" and r["result"].startswith("[dry-run]")
    assert c.get("/stats").json()["runs"] == 1
    assert c.post("/approve", json={"run_id": "a1", "approve": True}).status_code == 404
