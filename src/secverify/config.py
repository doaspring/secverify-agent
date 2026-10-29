"""Central configuration loaded from environment (.env supported, no extra deps)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(PROJECT_ROOT / ".env")


def _load_streamlit_secrets() -> None:
    """Streamlit Cloud delivers Secrets via st.secrets (a TOML file), NOT via
    os.environ; bridge them into the environment so config stays single-sourced.
    Local .env still wins because every key uses setdefault."""
    try:
        import streamlit as st

        for key in ("INTERN_API_KEY", "INTERN_API_URL", "INTERN_MODEL",
                    "INTERN_THINKING_MODE", "INTERN_TIMEOUT_SECONDS",
                    "SECVERIFY_EXECUTION_MODE", "MAX_TOOL_CALLS",
                    "ALLOW_NETWORK_EGRESS", "APPROVAL_TTL_SECONDS", "MAX_UPLOAD_MB"):
            try:
                value = st.secrets[key]
            except Exception:
                continue
            os.environ.setdefault(key, str(value))
    except Exception:
        pass  # not running inside Streamlit (tests, scripts) - .env is enough


_load_streamlit_secrets()


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    # Intern-S2 (Shanghai AI Lab) official chat completions endpoint.
    intern_api_key: str = field(default_factory=lambda: _env_str("INTERN_API_KEY", ""))
    intern_api_url: str = field(default_factory=lambda: _env_str(
        "INTERN_API_URL", "https://chat.intern-ai.org.cn/api/v1/chat/completions"))
    intern_model: str = field(default_factory=lambda: _env_str("INTERN_MODEL", "intern-s2"))
    intern_thinking_mode: bool = field(default_factory=lambda: _env_bool("INTERN_THINKING_MODE", True))
    intern_timeout_seconds: int = field(default_factory=lambda: _env_int("INTERN_TIMEOUT_SECONDS", 130))

    # LIVE = real API calls; anything else runs the offline scripted planner and
    # every artifact produced that way is labelled DEMO_REPLAY, never LIVE.
    execution_mode: str = field(default_factory=lambda: _env_str("SECVERIFY_EXECUTION_MODE", "LIVE"))

    max_tool_calls: int = field(default_factory=lambda: _env_int("MAX_TOOL_CALLS", 12))
    allow_network_egress: bool = field(default_factory=lambda: _env_bool("ALLOW_NETWORK_EGRESS", False))
    approval_ttl_seconds: int = field(default_factory=lambda: _env_int("APPROVAL_TTL_SECONDS", 300))
    max_upload_mb: int = field(default_factory=lambda: _env_int("MAX_UPLOAD_MB", 4))

    policy_path: Path = field(default_factory=lambda: PROJECT_ROOT / "policies" / "default_policy.json")
    demos_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "demos")
    artifacts_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "artifacts")
    evidence_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "evidence")
    evaluation_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "evaluation")

    @property
    def live_mode(self) -> bool:
        return self.execution_mode.upper() == "LIVE" and bool(self.intern_api_key)

    @property
    def replay_mode_reason(self) -> str:
        if not bool(self.intern_api_key):
            return "INTERN_API_KEY missing -> LIVE_BLOCKED, offline scripted planner (DEMO_REPLAY)"
        if self.execution_mode.upper() != "LIVE":
            return f"SECVERIFY_EXECUTION_MODE={self.execution_mode} -> DEMO_REPLAY"
        return ""


settings = Settings()
