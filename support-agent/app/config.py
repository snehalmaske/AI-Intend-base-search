"""Runtime configuration, read from environment variables.

Guardrail toggles exist for controlled lab testing only and default to ON.
Nothing an agent can call is able to change these values: there is no tool,
endpoint or database row that writes them. They are read from the process
environment at startup.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

GUARDRAIL_NAMES = (
    "single_transaction_cap",
    "weekly_cumulative_cap",
    "no_unrelated_record_export",
    "no_self_permission_change",
    "no_supervisor_bypass",
    "revocation",
)


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "on", "yes")


@dataclass
class Settings:
    database_url: str
    chroma_dir: str
    rag_backend: str
    mock_llm: bool
    anthropic_api_key: str | None
    claude_model: str
    single_refund_cap: float
    weekly_refund_cap: float
    weekly_window_days: int = 7
    max_record_results: int = 5
    guardrails: dict[str, bool] = field(default_factory=dict)

    def guardrail_on(self, name: str) -> bool:
        return self.guardrails.get(name, True)


def load_settings() -> Settings:
    _load_dotenv()
    var_dir = BASE_DIR / "var"
    api_key = os.getenv("ANTHROPIC_API_KEY") or None
    return Settings(
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{var_dir / 'support.db'}"),
        chroma_dir=os.getenv("CHROMA_DIR", str(var_dir / "chroma")),
        rag_backend=os.getenv("RAG_BACKEND", "auto").lower(),
        # No key -> mock mode, so the app always runs.
        mock_llm=_flag("MOCK_LLM", default=False) or api_key is None,
        anthropic_api_key=api_key,
        claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        single_refund_cap=float(os.getenv("SINGLE_REFUND_CAP", "100")),
        weekly_refund_cap=float(os.getenv("WEEKLY_REFUND_CAP", "500")),
        guardrails={g: _flag(f"GUARDRAIL_{g.upper()}", True) for g in GUARDRAIL_NAMES},
    )


settings = load_settings()


def reload_settings() -> Settings:
    """Re-read the environment (used by the CLI and tests)."""
    global settings
    new = load_settings()
    settings.__dict__.update(new.__dict__)
    return settings
