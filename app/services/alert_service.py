"""Create, list and update alert rules and alerts. Currency always comes from the listing's
source, so a rule can never be created in the wrong currency."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Alert, AlertRule, DataSource, ProductListing
from app.schemas.alerts import AlertRuleCreate


class RuleInputError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


def create_rule(db: Session, body: AlertRuleCreate) -> AlertRule:
    listing = db.get(ProductListing, body.listing_id)
    if listing is None or not db.get(DataSource, listing.source_id).enabled:
        raise NotFoundError("listing not found")
    if body.rule_type == "price_below":
        if body.threshold is None:
            raise RuleInputError("price_below requires a positive threshold")
        currency = db.get(DataSource, listing.source_id).currency
        rule = AlertRule(listing_id=listing.id, rule_type="price_below",
                         threshold=body.threshold, currency=currency)
    else:
        if body.threshold is not None:
            raise RuleInputError("back_in_stock does not take a threshold")
        rule = AlertRule(listing_id=listing.id, rule_type="back_in_stock")
    db.add(rule)
    db.flush()
    return rule


def _page(db: Session, query, order, page: int, page_size: int):
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(order).offset((page - 1) * page_size).limit(page_size)).all()
    return items, total


def list_rules(db: Session, active: bool | None, page: int, page_size: int):
    query = select(AlertRule).join(ProductListing, ProductListing.id == AlertRule.listing_id).join(DataSource, DataSource.id == ProductListing.source_id).where(DataSource.enabled.is_(True))
    if active is not None:
        query = query.where(AlertRule.active.is_(active))
    return _page(db, query, AlertRule.id.desc(), page, page_size)


def deactivate_rule(db: Session, rule_id: int) -> AlertRule:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise NotFoundError("alert rule not found")
    rule.active = False  # kept, not deleted, so past alerts still point at their rule
    return rule


def list_alerts(db: Session, unread_only: bool, page: int, page_size: int):
    query = select(Alert).join(ProductListing, ProductListing.id == Alert.listing_id).join(DataSource, DataSource.id == ProductListing.source_id).where(DataSource.enabled.is_(True))
    if unread_only:
        query = query.where(Alert.is_read.is_(False))
    return _page(db, query, Alert.id.desc(), page, page_size)


def mark_read(db: Session, alert_id: int) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("alert not found")
    alert.is_read = True
    return alert