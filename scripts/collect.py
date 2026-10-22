import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import argparse
import sys

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.database.session import get_session_factory
from app.scrapers.base import SourceConfigError
from app.scrapers.registry import STORES, build_source
from app.services.ingest import IngestError, run_collection


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Collect one source and store the result in PostgreSQL")
    ap.add_argument("--source", required=True, choices=sorted(STORES))
    ap.add_argument("--scope", default="", help="optional collection handle")
    ap.add_argument("--page", type=int, default=None, help="fetch only this page (debugging); omit to walk all pages up to the cap")
    args = ap.parse_args()

    setup_logging(get_settings().log_level)
    try:
        scraper = build_source(args.source)
        job = run_collection(get_session_factory(), STORES[args.source],
                             lambda: scraper.collect(args.scope, args.page))
    except (IngestError, SourceConfigError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:  # e.g. DATABASE_URL not set
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nJob {job.id} for {args.source}: {job.status.upper()}")
    print(f"discovered={job.discovered} accepted={job.accepted} rejected={job.rejected} "
          f"excluded={job.excluded} observations_written={job.observations_written}")
    if getattr(scraper, "truncated", False):
        print("WARNING: page cap reached with data still arriving; the catalog may be incomplete.")
    if job.status != "succeeded":
        print(f"{job.error_type}: {job.error_message}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
