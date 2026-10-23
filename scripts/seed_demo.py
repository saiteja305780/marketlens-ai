"""Create the invented DEMO dataset (its own source "demo"; real sources are never touched).
  python scripts/seed_demo.py           create it (refuses if it already exists)
  python scripts/seed_demo.py --reset   delete ONLY the demo source's data, then recreate it"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import get_session_factory
from app.services.demo_data import DemoDataExists, seed_demo


def main() -> int:
    ap = argparse.ArgumentParser(description="Create invented demo data in the 'demo' source")
    ap.add_argument("--reset", action="store_true", help="delete and recreate the demo source's data")
    args = ap.parse_args()
    try:
        counts = seed_demo(get_session_factory(), reset=args.reset)
    except DemoDataExists as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:  # e.g. DATABASE_URL not set
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Demo data created (invented products and prices): "
          f"{counts['listings']} listings, {counts['observations']} observations, "
          f"{counts['rules']} alert rules, {counts['alerts']} alert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
