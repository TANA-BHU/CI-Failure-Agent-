from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda

from ci_triage import guardrails
from ci_triage.agent import Diagnosis, run_triage
from ci_triage.config import Config
from ci_triage.metrics import summarize

FIX = Path(__file__).parent / "fixtures"


def stub_llm(action="rerun_failed_jobs", confidence=0.9, seen=None):
    def _f(messages):
        if seen is not None:
            seen.append(messages[-1][1])
        return Diagnosis(
            category="flaky_test", root_cause="Connect timeout to external host.",
            evidence=["ConnectTimeoutError"], confidence=confidence,
            proposed_action=action, suggested_fix="Rerun; check partner status.",
        )
    return RunnableLambda(_f)


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.metrics_file = str(tmp_path / "runs.jsonl")
    c.runbook_dir = str(Path(__file__).parent.parent / "runbooks")
    return c


def test_redaction():
    assert "ghp_" not in guardrails.redact("x ghp_abcdefghijklmnopqrstuvwxyz123456 y")
    assert "hunter2" not in guardrails.redact("password=hunter2")


def test_secret_never_reaches_llm(cfg):
    seen = []
    run_triage(cfg, str(FIX / "flaky_timeout.log"), "r0", approver=lambda p: True, llm=stub_llm(seen=seen))
    assert "ghp_abcdefghijkl" not in seen[0]


def test_approved_action_executes_dry_run(cfg):
    r = run_triage(cfg, str(FIX / "flaky_timeout.log"), "r1", approver=lambda p: True, llm=stub_llm())
    assert r["approved"] and r["result"].startswith("[dry-run]")


def test_rejected_action_not_executed(cfg):
    r = run_triage(cfg, str(FIX / "flaky_timeout.log"), "r2", approver=lambda p: False, llm=stub_llm())
    assert not r["approved"] and r["result"] == ""


def test_no_approver_is_safe_default(cfg):
    r = run_triage(cfg, str(FIX / "flaky_timeout.log"), "r3", approver=None, llm=stub_llm())
    assert not r["approved"] and r["result"] == ""


def test_low_confidence_downgraded(cfg):
    called = []
    r = run_triage(cfg, str(FIX / "flaky_timeout.log"), "r4",
                   approver=lambda p: called.append(p) or True, llm=stub_llm(confidence=0.3))
    assert r["proposed_action"] == "none" and "confidence" in r["policy_reason"] and not called


def test_disallowed_action_downgraded(cfg):
    cfg.guardrails.allowed_actions = ["none"]
    r = run_triage(cfg, str(FIX / "flaky_timeout.log"), "r5", approver=lambda p: True, llm=stub_llm())
    assert r["proposed_action"] == "none"


def test_metrics_written(cfg):
    run_triage(cfg, str(FIX / "flaky_timeout.log"), "r6", approver=lambda p: True, llm=stub_llm())
    run_triage(cfg, str(FIX / "flaky_timeout.log"), "r7", approver=lambda p: False, llm=stub_llm())
    s = summarize(cfg.metrics_file)
    assert s["runs"] == 2 and s["approved"] == 1 and s["rejected"] == 1
