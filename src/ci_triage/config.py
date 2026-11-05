import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class LLMCfg(BaseModel):
    provider: str = "azure_openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0
    base_url: str = ""
    api_version: str = "2024-10-21"
    price_in_per_m: float = 0.0
    price_out_per_m: float = 0.0


class SourceCfg(BaseModel):
    mode: str = "file"
    github_repo: str = ""


class GuardCfg(BaseModel):
    min_confidence: float = 0.6
    max_log_chars: int = 12000
    allowed_actions: list[str] = ["rerun_failed_jobs", "open_issue", "none"]
    require_approval: list[str] = ["rerun_failed_jobs", "open_issue"]
    dry_run: bool = True


class Config(BaseModel):
    llm: LLMCfg = LLMCfg()
    source: SourceCfg = SourceCfg()
    guardrails: GuardCfg = GuardCfg()
    runbook_dir: str = "runbooks"
    metrics_file: str = "metrics/runs.jsonl"


def load_config(path: str | None = None) -> Config:
    path = path or os.getenv("TRIAGE_CONFIG", "config.yaml")
    data = yaml.safe_load(Path(path).read_text()) if Path(path).exists() else {}
    cfg = Config(**(data or {}))
    # Env overrides for the two things you most often change per environment
    if os.getenv("TRIAGE_DRY_RUN"):
        cfg.guardrails.dry_run = os.environ["TRIAGE_DRY_RUN"].lower() in ("1", "true", "yes")
    if os.getenv("TRIAGE_SOURCE_MODE"):
        cfg.source.mode = os.environ["TRIAGE_SOURCE_MODE"]
    if os.getenv("TRIAGE_GITHUB_REPO"):
        cfg.source.github_repo = os.environ["TRIAGE_GITHUB_REPO"]
    if os.getenv("TRIAGE_LLM_BASE_URL"):
        cfg.llm.base_url = os.environ["TRIAGE_LLM_BASE_URL"]
    if os.getenv("TRIAGE_LLM_MODEL"):
        cfg.llm.model = os.environ["TRIAGE_LLM_MODEL"]
    if os.getenv("TRIAGE_LLM_PROVIDER"):
        cfg.llm.provider = os.environ["TRIAGE_LLM_PROVIDER"]
    return cfg
