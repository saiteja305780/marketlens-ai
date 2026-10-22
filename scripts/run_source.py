import argparse
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.scrapers.base import ScrapeResult, SourceError
from app.scrapers.registry import STORES, build_source


def print_result(result: ScrapeResult, mode: str, status: str) -> None:
    print(f"\nMODE: {mode}")
    print(f"Source: {result.source} (status: {status})")
    print(f"Discovered: {result.discovered} | Accepted: {len(result.listings)} "
          f"| Rejected: {len(result.rejected)} | Excluded: {len(result.excluded)} "
          f"| Degraded: {result.is_degraded}\n")
    for item in result.listings:
        price = f"{item.price} {item.currency}" if item.price is not None else "PRICE MISSING"
        print(f"  [{item.source_listing_id}] {price:>14} | {item.availability.value:<12} | {item.title}")
    for exc in result.excluded:
        print(f"  EXCLUDED [{exc.source_listing_id}]: {exc.reason}")
    for rej in result.rejected:
        print(f"  REJECTED [{rej.source_listing_id}]: {rej.reason}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Run one configured MarketLens source")
    ap.add_argument("--source", required=True, choices=sorted(STORES))
    ap.add_argument("--scope", default="", help="optional collection handle")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--fixture", type=Path, help="parse a saved JSON file instead of fetching")
    args = ap.parse_args()

    setup_logging(get_settings().log_level)
    try:
        source = build_source(args.source)
        status = STORES[args.source].status
        if args.fixture:
            payload = json.loads(args.fixture.read_text(encoding="utf-8"))
            label = "LIVE-CAPTURED FILE (real data saved earlier)" if "live_captured" in args.fixture.parts \
                else "SYNTHETIC FIXTURE (test data, not from a real site)"
            print_result(source.parse(payload), label, status)
        else:
            print_result(source.collect(args.scope, args.page), "LIVE (fetched just now)", status)
    except SourceError as exc:
        print(f"ERROR ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())