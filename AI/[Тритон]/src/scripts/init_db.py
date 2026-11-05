#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import state_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize or reset challenge SQLite state")
    parser.add_argument("--reset", action="store_true", help="rotate debug token and clear leak state")
    parser.add_argument("--team-id", default="0", help="team id for local state initialization")
    args = parser.parse_args()

    state = state_store.reset_state(args.team_id) if args.reset else state_store.initialize_state(args.team_id)
    print(
        {
            "status": "reset" if args.reset else "initialized",
            "team_id": state.team_id,
            "region_name": state.region_name,
            "last_reset_at": state.last_reset_at,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
