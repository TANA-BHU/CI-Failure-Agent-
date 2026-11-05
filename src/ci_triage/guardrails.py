import re

from .config import GuardCfg

# Redact obvious secrets before logs leave the process (to the LLM or to metrics).
_PATTERNS = [
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)(\s*[=:]\s*)\S+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(AccountKey|SharedAccessSignature)=[^;\s]+"), r"\1=[REDACTED]"),
]


def redact(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def tail(text: str, max_chars: int) -> str:
    """Failures are almost always at the end of a CI log."""
    return text if len(text) <= max_chars else "...[truncated]...\n" + text[-max_chars:]


def check_policy(action: str, confidence: float, cfg: GuardCfg) -> tuple[str, str]:
    """Return (final_action, reason). Anything outside policy is downgraded to 'none'."""
    if action not in cfg.allowed_actions:
        return "none", f"action '{action}' is not in allowed_actions"
    if action != "none" and confidence < cfg.min_confidence:
        return "none", f"confidence {confidence:.2f} below threshold {cfg.min_confidence}"
    return action, "ok"


def needs_approval(action: str, cfg: GuardCfg) -> bool:
    return action in cfg.require_approval
