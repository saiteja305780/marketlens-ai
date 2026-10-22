from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import require_api_key
from app.api.deps import DbSession, PageNumber, PageSize
from app.schemas.alerts import AlertOut, AlertRuleCreate, AlertRuleOut
from app.schemas.api import Page
from app.services import alert_service
from app.services.alert_service import NotFoundError, RuleInputError

# Every route here needs the API key: rules and alerts reveal which listings are being watched.
router = APIRouter(tags=["alerts"], dependencies=[Depends(require_api_key)])


@router.post("/alert-rules", response_model=AlertRuleOut, status_code=201)
def create_rule(body: AlertRuleCreate, db: DbSession):
    """Watch one listing. price_below fires once when the price drops to the threshold;
    back_in_stock fires once when it returns to stock. Neither repeats while the condition holds."""
    try:
        rule = alert_service.create_rule(db, body)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except RuleInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/alert-rules", response_model=Page[AlertRuleOut])
def list_rules(db: DbSession, active: bool | None = None, page: PageNumber = 1, page_size: PageSize = 25):
    items, total = alert_service.list_rules(db, active, page, page_size)
    return Page[AlertRuleOut](items=items, total=total, page=page, page_size=page_size)


@router.delete("/alert-rules/{rule_id}", response_model=AlertRuleOut)
def deactivate_rule(rule_id: int, db: DbSession):
    """Deactivates the rule (it is kept, so earlier alerts still reference it)."""
    try:
        rule = alert_service.deactivate_rule(db, rule_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/alerts", response_model=Page[AlertOut])
def list_alerts(db: DbSession, unread_only: bool = False, page: PageNumber = 1, page_size: PageSize = 25):
    items, total = alert_service.list_alerts(db, unread_only, page, page_size)
    return Page[AlertOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/alerts/{alert_id}/read", response_model=AlertOut)
def mark_read(alert_id: int, db: DbSession):
    try:
        alert = alert_service.mark_read(db, alert_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    db.commit()
    db.refresh(alert)
    return alert