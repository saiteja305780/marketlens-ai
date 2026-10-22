"""Evaluates alert rules against the data from one successful collection, inside the ingest
transaction. Uses the values just scraped, so only listings seen in this run are evaluated."""
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Alert, AlertRule
from app.services.alert_logic import PRICE_BELOW, evaluate

logger = logging.getLogger(__name__)

# listing_id -> (price, currency, availability) exactly as stored this run
Current = dict[int, tuple[Decimal | None, str | None, str]]


def _message(rule: AlertRule, title: str, price: Decimal | None, currency: str | None) -> str:
    if rule.rule_type == PRICE_BELOW:
        return f"{title}: now {price} {currency}, at or below your {rule.threshold} {rule.currency} threshold"
    return f"{title}: back in stock"


def evaluate_rules(session: Session, job_id: int, current: Current, titles: dict[int, str]) -> int:
    """Returns the number of alerts created. Never raises: a failure here must not block ingestion."""
    ids = list(current)
    fired = 0
    try:
        with session.begin_nested():
            for start in range(0, len(ids), 5000):
                chunk = ids[start:start + 5000]
                rules = session.scalars(select(AlertRule).where(
                    AlertRule.active.is_(True), AlertRule.listing_id.in_(chunk))).all()
                for rule in rules:
                    price, currency, availability = current[rule.listing_id]
                    state, fire = evaluate(rule.rule_type, rule.threshold, rule.currency,
                                           rule.condition_met, price, currency, availability)
                    rule.condition_met = state
                    if fire:
                        session.add(Alert(
                            rule_id=rule.id, listing_id=rule.listing_id, job_id=job_id,
                            message=_message(rule, titles.get(rule.listing_id, "listing"), price, currency),
                            price=price, currency=currency))
                        fired += 1
    except Exception as exc:
        logger.error("alert evaluation failed (%s); prices were still stored", type(exc).__name__)
        return 0
    return fired