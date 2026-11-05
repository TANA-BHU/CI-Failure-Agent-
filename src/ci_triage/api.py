"""HTTP service for embedding the agent in a pipeline.

POST /triage  -> runs diagnosis; if an action needs approval it is returned as 'pending'
                 and NOT executed. A human (or an approval system) calls /approve.
GET  /stats   -> efficiency metrics
GET  /healthz -> liveness
"""
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .agent import build_graph
from .config import load_config
from .metrics import UsageCallback, append_run, summarize
from langgraph.types import Command

import time

cfg = load_config()
app = FastAPI(title="CI Triage Agent")

# One shared graph (with in-memory checkpointer) so /approve can resume a paused run.
_usage: dict[str, UsageCallback] = {}
_started: dict[str, float] = {}
_graph = None


def graph():
    global _graph
    if _graph is None:
        _graph = build_graph(cfg)
    return _graph


class TriageReq(BaseModel):
    ref: str                      # log path or GitHub run id
    run_id: str | None = None


class ApproveReq(BaseModel):
    run_id: str
    approve: bool


def _cfg(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}, "callbacks": [_usage.setdefault(run_id, UsageCallback())]}


def _finish(run_id: str, out: dict) -> dict:
    d = out["diagnosis"]
    u = _usage.pop(run_id, UsageCallback())
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "run_id": run_id, "category": d["category"],
        "confidence": d["confidence"], "proposed_action": out["action"],
        "policy_reason": out["policy_reason"], "approved": bool(out.get("approved", False)),
        "result": out.get("result", ""), "latency_s": round(time.perf_counter() - _started.pop(run_id, time.perf_counter()), 3),
        "llm_latency_s": round(u.llm_seconds, 3), "tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
        "cost_usd": round(u.cost_usd(cfg.llm.price_in_per_m, cfg.llm.price_out_per_m), 6),
    }
    append_run(cfg.metrics_file, rec)
    return {"status": "done", "diagnosis": d, **rec}


@app.post("/triage")
def triage(req: TriageReq):
    run_id = req.run_id or uuid.uuid4().hex[:8]
    _started[run_id] = time.perf_counter()
    out = graph().invoke({"ref": req.ref, "run_id": run_id}, _cfg(run_id))
    if "__interrupt__" in out:
        return {"status": "pending_approval", "run_id": run_id, "proposal": out["__interrupt__"][0].value}
    return _finish(run_id, out)


@app.post("/approve")
def approve(req: ApproveReq):
    if req.run_id not in _started:
        raise HTTPException(404, "unknown or already-completed run_id")
    out = graph().invoke(Command(resume=req.approve), _cfg(req.run_id))
    return _finish(req.run_id, out)


@app.get("/stats")
def stats():
    return summarize(cfg.metrics_file)


@app.get("/healthz")
def healthz():
    return {"ok": True}
