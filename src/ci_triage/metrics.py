import json
import time
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler


class UsageCallback(BaseCallbackHandler):
    """Collects token usage and LLM latency across all model calls in a run."""

    def __init__(self):
        self.tokens_in = 0
        self.tokens_out = 0
        self.llm_seconds = 0.0
        self._t0 = None

    def on_chat_model_start(self, *a, **k):
        self._t0 = time.perf_counter()

    def on_llm_start(self, *a, **k):
        self._t0 = time.perf_counter()

    def on_llm_end(self, response, **k):
        if self._t0 is not None:
            self.llm_seconds += time.perf_counter() - self._t0
        for gens in response.generations:
            for g in gens:
                meta = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
                self.tokens_in += meta.get("input_tokens", 0)
                self.tokens_out += meta.get("output_tokens", 0)

    def cost_usd(self, price_in_per_m: float, price_out_per_m: float) -> float:
        return (self.tokens_in * price_in_per_m + self.tokens_out * price_out_per_m) / 1e6


def append_run(path: str, record: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(record) + "\n")


def summarize(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"runs": 0}
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    n = len(rows)
    return {
        "runs": n,
        "avg_latency_s": round(sum(r["latency_s"] for r in rows) / n, 3),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
        "approved": sum(1 for r in rows if r["approved"]),
        "rejected": sum(1 for r in rows if r["proposed_action"] != "none" and not r["approved"]),
        "auto_downgraded": sum(1 for r in rows if r["policy_reason"] != "ok"),
    }
