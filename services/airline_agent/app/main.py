from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

Membership = Literal["regular", "silver", "gold"]
Cabin = Literal["basic_economy", "economy", "business"]
Action = Literal["baggage", "cancellation", "change", "general"]
TaskStatus = Literal["completed", "denied", "needs_followup"]
Decision = Literal["allow", "deny", "guidance"]

_FREE_BAG_ALLOWANCE: dict[Membership, dict[Cabin, int]] = {
    "regular": {"basic_economy": 0, "economy": 1, "business": 2},
    "silver": {"basic_economy": 1, "economy": 2, "business": 3},
    "gold": {"basic_economy": 2, "economy": 3, "business": 4},
}
_INSURANCE_REASONS = {"health", "weather"}


class AgentCardResponse(BaseModel):
    agent_id: str
    agent_name: str
    description: str
    endpoint: str
    supported_methods: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    action: Action | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TaskSendResponse(BaseModel):
    agent_id: str
    status: TaskStatus
    output: str
    decision: Decision


app = FastAPI(title="airline-agent", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/agent-card", response_model=AgentCardResponse)
def agent_card() -> AgentCardResponse:
    return AgentCardResponse(
        agent_id="airline-agent",
        agent_name="Airline Domain Agent",
        description="Minimal A2A-like airline policy assistant.",
        endpoint="http://airline-agent:8030/tasks/send",
        supported_methods=[
            "tasks/send",
            "airline/baggage",
            "airline/cancellation",
            "airline/change",
        ],
        metadata={"domain": "airline", "version": "v1"},
    )


@app.post("/tasks/send", response_model=TaskSendResponse)
def send_task(payload: TaskSendRequest) -> TaskSendResponse:
    action = payload.action or _detect_action(payload.message)
    normalized_details = dict(payload.details)
    status: TaskStatus
    decision: Decision
    output: str

    if action == "baggage":
        status, decision, output = _handle_baggage(normalized_details)
    elif action == "cancellation":
        status, decision, output = _handle_cancellation(normalized_details)
    elif action == "change":
        status, decision, output = _handle_change(normalized_details)
    else:
        status = "needs_followup"
        decision = "guidance"
        output = (
            "Specify one of actions: baggage, cancellation, change. "
            "Include structured details for deterministic policy response."
        )

    return TaskSendResponse(
        agent_id="airline-agent",
        status=status,
        output=output,
        decision=decision,
    )


def _detect_action(message: str) -> Action:
    text = message.lower()
    if "bag" in text or "baggage" in text:
        return "baggage"
    if "cancel" in text or "refund" in text:
        return "cancellation"
    if "change" in text or "itinerary" in text or "flight" in text:
        return "change"
    return "general"


def _handle_baggage(details: dict[str, Any]) -> tuple[TaskStatus, Decision, str]:
    membership = _to_membership(details.get("membership"))
    cabin = _to_cabin(details.get("cabin"))
    passengers = _to_non_negative_int(details.get("passengers"), fallback=1)
    checked_bags = _to_non_negative_int(details.get("checked_bags"), fallback=0)
    free_per_passenger = _FREE_BAG_ALLOWANCE[membership][cabin]
    free_total = free_per_passenger * passengers
    paid_bags = max(checked_bags - free_total, 0)
    output = (
        f"Free checked bags: {free_total} total ({free_per_passenger} per passenger). "
        f"Paid bags required: {paid_bags}."
    )
    return "completed", "allow", output


def _handle_cancellation(details: dict[str, Any]) -> tuple[TaskStatus, Decision, str]:
    if _to_bool(details.get("past_travel")):
        return (
            "denied",
            "deny",
            "Cancellation denied: past travel cannot be cancelled.",
        )

    bases: list[str] = []
    if _to_bool(details.get("within_24h")):
        bases.append("within_24h")
    if _to_bool(details.get("flight_cancelled_by_airline")):
        bases.append("airline_cancelled")
    if _to_bool(details.get("business_class")):
        bases.append("business_class")
    if (
        _to_bool(details.get("has_travel_insurance"))
        and str(details.get("insurance_reason", "")).lower() in _INSURANCE_REASONS
    ):
        bases.append("insurance_covered")

    if not bases:
        return (
            "denied",
            "deny",
            "Cancellation denied: no allowed basis "
            "(24h/airline cancellation/business/covered insurance).",
        )
    joined = ", ".join(bases)
    return "completed", "allow", f"Cancellation is allowed on basis: {joined}."


def _handle_change(details: dict[str, Any]) -> tuple[TaskStatus, Decision, str]:
    fare_type = _to_cabin(details.get("fare_type"))
    change_itinerary = _to_bool(details.get("change_itinerary"))
    change_cabin = _to_bool(details.get("change_cabin"))
    change_origin_destination = _to_bool(details.get("change_origin_destination"))
    remain_basic = _to_bool(details.get("remain_basic_economy"), default=True)

    if change_origin_destination:
        return (
            "denied",
            "deny",
            "Origin/destination change is not allowed via modification. Use cancel + new booking.",
        )

    if fare_type == "basic_economy":
        if change_itinerary and change_cabin:
            return (
                "needs_followup",
                "guidance",
                "For basic economy: first upgrade cabin on current flights, then change itinerary.",
            )
        if change_itinerary and remain_basic:
            return (
                "denied",
                "deny",
                "Basic economy cannot directly change itinerary while staying basic economy.",
            )
        if change_cabin and not change_itinerary:
            return ("completed", "allow", "Cabin-only upgrade on current flights is allowed.")
    return ("completed", "allow", "Requested modification path is allowed.")


def _to_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    return default


def _to_non_negative_int(value: Any, *, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str) and value.strip().isdigit():
        return max(int(value.strip()), 0)
    return fallback


def _to_membership(value: Any) -> Membership:
    normalized = str(value or "regular").strip().lower()
    if normalized == "regular":
        return "regular"
    if normalized == "silver":
        return "silver"
    if normalized == "gold":
        return "gold"
    return "regular"


def _to_cabin(value: Any) -> Cabin:
    normalized = str(value or "economy").strip().lower()
    if normalized == "basic_economy":
        return "basic_economy"
    if normalized == "economy":
        return "economy"
    if normalized == "business":
        return "business"
    return "economy"
