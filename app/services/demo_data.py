"""Invented demo data for screenshots, demos and Docker. Everything lives in its own source named
"demo"; real sources are never touched, and nothing here makes a network request."""
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Alert, AlertRule, DataSource, PriceObservation, ProductListing, ScrapeJob

SOURCE = "demo"
DAYS = 60
BRANDS = ["Zephyr", "Nimbus", "Orbit", "Kestrel"]  # invented
LINES = [("Earbuds", ["Buds Air", "Buds Pro", "Buds Lite"], 999, 4999),
         ("Smartwatch", ["Watch Fit", "Watch Active", "Watch Ultra"], 1999, 9999),
         ("Speaker", ["Boom Mini", "Boom Max"], 1499, 6999),
         ("Headphones", ["Over-Ear One", "Over-Ear Plus"], 1999, 7999)]
COLOURS = ["Black", "White", "Blue"]


class DemoDataExists(Exception):
    pass


def _history(rng: random.Random, base: Decimal, start: datetime) -> list[tuple]:
    """Change-only history: a row is kept only when price, list price or availability changed."""
    price = base
    list_price = (base * Decimal("1.2")).quantize(Decimal("1")) if rng.random() < 0.7 else None
    in_stock, back_on, last, rows = True, None, None, []
    for day in range(DAYS + 1):
        when = start + timedelta(days=day, hours=rng.randint(0, 5))
        if rng.random() < 0.12:
            factor = Decimal(str(round(rng.uniform(0.85, 1.08), 3)))
            price = max(Decimal("199"), (price * factor).quantize(Decimal("1")))
        if in_stock and rng.random() < 0.04:
            in_stock, back_on = False, day + rng.randint(2, 6)
        elif not in_stock and day >= back_on:
            in_stock, back_on = True, None
        state = (price, list_price, "in_stock" if in_stock else "out_of_stock")
        if state != last:
            rows.append((when, *state))
            last = state
    return rows


def _delete_demo(s: Session, source: DataSource) -> None:
    listing_ids = select(ProductListing.id).where(ProductListing.source_id == source.id)
    s.execute(delete(Alert).where(Alert.listing_id.in_(listing_ids)))
    s.execute(delete(AlertRule).where(AlertRule.listing_id.in_(listing_ids)))
    s.execute(delete(PriceObservation).where(PriceObservation.listing_id.in_(listing_ids)))
    s.execute(delete(ScrapeJob).where(ScrapeJob.source_id == source.id))
    s.execute(delete(ProductListing).where(ProductListing.source_id == source.id))
    s.execute(delete(DataSource).where(DataSource.id == source.id))
    s.flush()


def seed_demo(factory: sessionmaker[Session], *, reset: bool = False, now: datetime | None = None,
              rng_seed: int = 7) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    rng = random.Random(rng_seed)
    with factory() as s:
        existing = s.scalar(select(DataSource).where(DataSource.name == SOURCE))
        if existing is not None:
            has_data = s.scalar(select(ProductListing.id).where(
                ProductListing.source_id == existing.id).limit(1)) is not None
            if has_data and not reset:
                raise DemoDataExists("demo data already exists; use --reset to recreate it")
            _delete_demo(s, existing)

        source = DataSource(name=SOURCE, base_url="https://demo.invalid", currency="INR", enabled=True)
        s.add(source)
        s.flush()
        start = now - timedelta(days=DAYS, hours=6)

        info, n, total_obs = [], 0, 0
        for category, lines, lo, hi in LINES:
            for line in lines:
                for brand in BRANDS:
                    n += 1
                    colour = rng.choice(COLOURS)
                    base = Decimal(round(rng.uniform(lo, hi) / 100) * 100 - 1)
                    history = _history(rng, base, start)
                    listing = ProductListing(
                        source_id=source.id, source_listing_id=f"demo-{n:03d}",
                        title=f"{brand} {line} - {colour}", url=f"https://demo.invalid/products/{n}",
                        brand=brand, category=category, first_seen_at=history[0][0], last_seen_at=now)
                    s.add(listing)
                    s.flush()
                    for when, price, list_price, availability in history:
                        s.add(PriceObservation(listing_id=listing.id, observed_at=when, price=price,
                                               list_price=list_price, currency="INR",
                                               availability=availability))
                    total_obs += len(history)
                    info.append((listing, history[-1]))

        job = ScrapeJob(source_id=source.id, status="succeeded", started_at=now - timedelta(minutes=2),
                        finished_at=now - timedelta(minutes=1), discovered=n, accepted=n,
                        observations_written=total_obs)
        s.add(job)
        s.flush()

        listing, (_, price, _, _) = info[3]
        threshold = price + Decimal("200")
        rule = AlertRule(listing_id=listing.id, rule_type="price_below", threshold=threshold,
                         currency="INR", active=True, condition_met=True)
        s.add(rule)
        s.flush()
        s.add(Alert(rule_id=rule.id, listing_id=listing.id, job_id=job.id, created_at=now - timedelta(hours=3),
                    message=f"{listing.title}: now {price:.2f} INR, at or below your {threshold:.2f} INR threshold",
                    price=price, currency="INR", is_read=False))
        rules = 1
        out = next((x for x in info if x[1][3] == "out_of_stock"), None)
        if out is not None:
            s.add(AlertRule(listing_id=out[0].id, rule_type="back_in_stock", active=True, condition_met=False))
            rules += 1
        s.commit()
        return {"listings": n, "observations": total_obs, "rules": rules, "alerts": 1}
