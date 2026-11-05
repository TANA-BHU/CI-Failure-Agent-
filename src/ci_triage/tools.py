"""Tools the agent can use. Read tools are always allowed; action tools are gated by guardrails."""
import os
from pathlib import Path

import httpx

from .config import Config

GH_API = "https://api.github.com"


def _gh_headers() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


# ---------- read tools ----------
def fetch_logs(cfg: Config, ref: str) -> str:
    """ref = path to a log file (mode=file) or a GitHub Actions run id (mode=github)."""
    if cfg.source.mode == "file":
        return Path(ref).read_text(errors="replace")
    repo = cfg.source.github_repo
    with httpx.Client(headers=_gh_headers(), follow_redirects=True, timeout=30) as c:
        jobs = c.get(f"{GH_API}/repos/{repo}/actions/runs/{ref}/jobs").json().get("jobs", [])
        parts = []
        for j in jobs:
            if j.get("conclusion") == "failure":
                r = c.get(f"{GH_API}/repos/{repo}/actions/jobs/{j['id']}/logs")
                parts.append(f"=== job: {j['name']} ===\n{r.text}")
        return "\n".join(parts) or "No failed jobs found."


def search_runbook(cfg: Config, query_text: str, k: int = 3) -> str:
    """Tiny keyword retriever over markdown runbooks. Swap for a vector store when it grows."""
    d = Path(cfg.runbook_dir)
    if not d.exists():
        return ""
    words = {w.lower() for w in query_text.split() if len(w) > 4}
    scored = []
    for f in d.glob("*.md"):
        text = f.read_text()
        score = sum(text.lower().count(w) for w in words)
        if score:
            scored.append((score, f.name, text))
    scored.sort(reverse=True)
    return "\n\n".join(f"[{name}]\n{text}" for _, name, text in scored[:k])


# ---------- action tools (only reached after policy + approval) ----------
def rerun_failed_jobs(cfg: Config, run_id: str) -> str:
    if cfg.guardrails.dry_run:
        return f"[dry-run] would rerun failed jobs for run {run_id}"
    with httpx.Client(headers=_gh_headers(), timeout=30) as c:
        r = c.post(f"{GH_API}/repos/{cfg.source.github_repo}/actions/runs/{run_id}/rerun-failed-jobs")
    return f"rerun requested, HTTP {r.status_code}"


def open_issue(cfg: Config, title: str, body: str) -> str:
    if cfg.guardrails.dry_run:
        return f"[dry-run] would open issue: {title}"
    with httpx.Client(headers=_gh_headers(), timeout=30) as c:
        r = c.post(
            f"{GH_API}/repos/{cfg.source.github_repo}/issues",
            json={"title": title, "body": body, "labels": ["ci-triage"]},
        )
    return f"issue created, HTTP {r.status_code}: {r.json().get('html_url', '')}"
