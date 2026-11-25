"""
Authorize or revoke external LLM processing for one institution (owner connection).

The runtime role cannot update institutions. This script is the only writer.
Enabling the column does nothing until the deployment also sets
LLM_PROVIDER=subq and LLM_EXTERNAL_PROCESSING_ENABLED=true.

    cd backend
    python scripts/set_external_processing.py --slug example-smif --enable --confirm-external-processing
    python scripts/set_external_processing.py --slug example-smif --disable
"""

from __future__ import annotations

import argparse
import sys

from _cli import owner_engine
from sqlalchemy import text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true")
    group.add_argument("--disable", action="store_true")
    parser.add_argument(
        "--confirm-external-processing",
        action="store_true",
        help="Required with --enable. Violation facts and retrieved excerpts may be sent to SubQ.",
    )
    args = parser.parse_args()
    if args.enable and not args.confirm_external_processing:
        sys.exit("Refusing to enable external processing without --confirm-external-processing.")

    enabled = bool(args.enable)
    with owner_engine().begin() as conn:
        row = conn.execute(
            text("SELECT id FROM institutions WHERE slug = :s"),
            {"s": args.slug},
        ).first()
        if row is None:
            sys.exit(f"No institution with slug {args.slug!r}.")
        conn.execute(
            text("UPDATE institutions SET external_processing_authorized = :v WHERE slug = :s"),
            {"v": enabled, "s": args.slug},
        )
    state = "true" if enabled else "false"
    print(f"institution {args.slug} ({row[0]}): external_processing_authorized={state}")
    if enabled:
        print(
            "Excerpts are sent only when LLM_PROVIDER=subq and "
            "LLM_EXTERNAL_PROCESSING_ENABLED=true are also set."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
