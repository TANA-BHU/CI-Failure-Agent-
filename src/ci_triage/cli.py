import argparse
import json

from .agent import run_triage
from .config import load_config
from .metrics import summarize


def cli_approver(p: dict) -> bool:
    print("\n--- Approval required ---")
    print(f"Run:        {p['run_id']}")
    print(f"Action:     {p['proposed_action']}")
    print(f"Root cause: {p['root_cause']}")
    print(f"Confidence: {p['confidence']:.2f}")
    return input("Approve? [y/N] ").strip().lower() == "y"


def main():
    ap = argparse.ArgumentParser(prog="ci-triage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("triage", help="triage a failed run")
    t.add_argument("ref", help="log file path (mode=file) or GitHub run id (mode=github)")
    t.add_argument("--run-id")
    t.add_argument("--yes", action="store_true", help="auto-approve (CI use; keep dry_run on)")
    t.add_argument("--config")
    s = sub.add_parser("stats", help="show efficiency metrics")
    s.add_argument("--config")
    a = ap.parse_args()

    cfg = load_config(a.config)
    if a.cmd == "stats":
        print(json.dumps(summarize(cfg.metrics_file), indent=2))
        return
    approver = (lambda p: True) if a.yes else cli_approver
    res = run_triage(cfg, a.ref, a.run_id, approver)
    d = res["diagnosis"]
    print(f"\nCategory:   {d['category']} (confidence {d['confidence']:.2f})")
    print(f"Root cause: {d['root_cause']}")
    print(f"Fix:        {d['suggested_fix']}")
    print(f"Action:     {res['proposed_action']} | policy: {res['policy_reason']} | approved: {res['approved']}")
    if res["result"]:
        print(f"Result:     {res['result']}")
    print(f"Latency {res['latency_s']}s | tokens {res['tokens_in']}/{res['tokens_out']} | cost ${res['cost_usd']}")


if __name__ == "__main__":
    main()
