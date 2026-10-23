"""Deterministic assistant: question -> one validated tool call -> templated answer. Works with no
API key. A model-backed provider can later replace the planner, but it would still only be able to
call these same tools."""
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.formatters import FORMATTERS
from app.assistant.planner import Clarify, plan_question
from app.assistant.tools import ToolError, run_tool
from app.database.models import DataSource


class AssistantAnswer(BaseModel):
    question: str
    understood: bool
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    answer: str
    data: dict[str, Any] | None = None


def ask(db: Session, question: str) -> AssistantAnswer:
    q = question.strip()
    names = list(db.scalars(select(DataSource.name).where(DataSource.enabled.is_(True))))
    plan = plan_question(q, names)
    if isinstance(plan, Clarify):
        return AssistantAnswer(question=q, understood=False, answer=plan.message)

    args = dict(plan.args)
    if plan.needs_currency:
        currencies = sorted(set(db.scalars(
            select(DataSource.currency).where(DataSource.enabled.is_(True)))))
        if len(currencies) != 1:
            options = ", ".join(currencies) if currencies else "none available"
            return AssistantAnswer(
                question=q, understood=False, tool=plan.tool, arguments=args,
                answer=f"Which currency do you mean? Prices are only compared within one currency "
                       f"(available: {options}). Add it to your question, for example: under 1500 INR.")
        args["currency"] = currencies[0]

    try:
        out = run_tool(db, plan.tool, args)
    except ToolError as exc:
        return AssistantAnswer(question=q, understood=False, tool=plan.tool, arguments=args,
                               answer=f"I couldn't run that: {exc}")
    result = out["result"]
    return AssistantAnswer(question=q, understood=True, tool=plan.tool, arguments=args,
                           answer=FORMATTERS[plan.tool](result, args), data=result)
