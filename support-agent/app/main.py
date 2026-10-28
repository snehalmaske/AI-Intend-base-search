"""CLI entry point.

    python -m app.main [--mock-llm] [--host 127.0.0.1] [--port 8000] [--seed]
"""
from __future__ import annotations

import argparse
import logging
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Enterprise Customer Support Agent (synthetic data)")
    parser.add_argument("--mock-llm", action="store_true", help="deterministic canned LLM, no API key")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--seed", action="store_true", help="reset and seed data before starting")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if args.mock_llm:
        os.environ["MOCK_LLM"] = "1"
    from .config import reload_settings

    settings = reload_settings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("app")
    off = [g for g, on in settings.guardrails.items() if not on]
    if off:
        log.warning("LAB MODE: guardrails DISABLED: %s", ", ".join(off))
    log.info("LLM: %s", "mock" if settings.mock_llm else settings.claude_model)

    if args.seed:
        from .seed import seed

        log.info("seeded: %s", seed(reset=True))

    import uvicorn

    uvicorn.run("app.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
