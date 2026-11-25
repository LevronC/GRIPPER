"""
Check SubQ configuration and, only with --generate, send one synthetic completion.

No portfolio holdings or research text are included. The API key is read from
SUBQ_API_KEY and is never printed.

    cd backend
    LLM_PROVIDER=subq SUBQ_API_KEY=... python scripts/llm_preflight.py
    LLM_PROVIDER=subq SUBQ_API_KEY=... python scripts/llm_preflight.py --generate
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from app.services.llm.preflight import run_preflight  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SubQ model access without sending customer data.")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="After the models check, send one synthetic chat completion. This is the explicit authorization to make that call.",
    )
    args = parser.parse_args()
    return run_preflight(generate=args.generate, allow_live=True)


if __name__ == "__main__":
    raise SystemExit(main())
