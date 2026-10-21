import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.utils.http import build_session
from app.utils.robots import RobotsGuard

BLOCK_HINTS = ("captcha", "access denied", "are you a robot", "verify you are human",
               "cf-chl", "px-captcha")


def looks_blocked(resp) -> bool:
    if resp.status_code in (401, 403, 429, 503):
        return True
    if "json" not in resp.headers.get("Content-Type", "").lower():
        return any(h in resp.text[:5000].lower() for h in BLOCK_HINTS)
    return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Check whether a Shopify store catalog may be read")
    ap.add_argument("base_url")
    ap.add_argument("--save-sample", type=Path,
                    help="save first 3 products to a LIVE-CAPTURED fixture (kept out of git)")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    if urlsplit(base).scheme != "https":
        print("ERROR: base_url must start with https://")
        return 2

    settings = get_settings()
    session = build_session(settings.http_user_agent)
    guard = RobotsGuard(session, timeout=settings.http_timeout_seconds)

    print(f"== Preflight: {base}")
    print(f"robots.txt: {guard.policy(base + '/')}   (loaded | missing = allowed | unreadable = treated as DISALLOWED)")
    print(f"crawl-delay: {guard.crawl_delay(base + '/')}")
    catalog_url = f"{base}/products.json"
    allowed = guard.allowed(catalog_url)
    print(f"robots allows /products.json: {allowed}")
    if not allowed:
        print("VERDICT: FAIL. Do not fetch. Pick another source.")
        return 1

    resp = session.get(catalog_url, params={"limit": 5}, timeout=settings.http_timeout_seconds)
    print(f"GET /products.json -> HTTP {resp.status_code}, content-type={resp.headers.get('Content-Type')}, "
          f"final host={urlsplit(resp.url).netloc}")
    if looks_blocked(resp):
        print("VERDICT: BLOCKED or not JSON. Stop here. We do not bypass access controls.")
        return 1
    try:
        data = resp.json()
    except ValueError:
        print("VERDICT: FAIL (not valid JSON)")
        return 1
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list) or not products:
        print("VERDICT: FAIL (no 'products' list or it is empty)")
        return 1

    first = products[0]
    variants = first.get("variants") or [{}]
    print(f"products returned: {len(products)}")
    print(f"product keys: {sorted(first.keys())}")
    print(f"variant keys: {sorted(variants[0].keys())}")
    print(f"sample: title={first.get('title')!r} vendor={first.get('vendor')!r} "
          f"type={first.get('product_type')!r} price={variants[0].get('price')!r} "
          f"available={variants[0].get('available')!r}")

    meta_url = f"{base}/meta.json"
    if guard.allowed(meta_url):
        meta = session.get(meta_url, timeout=settings.http_timeout_seconds)
        try:
            print(f"meta.json currency: {meta.json().get('currency')!r}")
        except (ValueError, AttributeError):
            print("meta.json: not available or not JSON. Confirm the currency on the site yourself.")
    else:
        print("meta.json: not allowed by robots. Confirm the currency on the site yourself.")

    if args.save_sample:
        args.save_sample.parent.mkdir(parents=True, exist_ok=True)
        sample = {"_capture_notice": "LIVE CAPTURE from a real website; not synthetic",
                  "_source_url": catalog_url,
                  "_captured_at": datetime.now(timezone.utc).isoformat(),
                  "products": products[:3]}
        args.save_sample.write_text(json.dumps(sample, indent=2), encoding="utf-8")
        print(f"saved sample -> {args.save_sample}")

    print("VERDICT: PASS (technical). You must still read the site's Terms of Service and confirm the currency.")
    return 0


if __name__ == "__main__":
    sys.exit(main())