from __future__ import annotations

from fastapi.testclient import TestClient

from services.airline_agent.app.main import (
    _detect_action,
    _to_bool,
    _to_cabin,
    _to_membership,
    _to_non_negative_int,
    app,
)


def test_airline_agent_baggage_allowance() -> None:
    payload = {
        "message": "baggage policy",
        "action": "baggage",
        "details": {
            "membership": "silver",
            "cabin": "economy",
            "passengers": 2,
            "checked_bags": 5,
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["decision"] == "allow"
    assert "Free checked bags: 4 total" in body["output"]
    assert "Paid bags required: 1" in body["output"]


def test_airline_agent_cancellation_denied_without_basis() -> None:
    payload = {
        "message": "cancel my booking",
        "action": "cancellation",
        "details": {
            "within_24h": False,
            "flight_cancelled_by_airline": False,
            "business_class": False,
            "has_travel_insurance": False,
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "denied"
    assert body["decision"] == "deny"
    assert "Cancellation denied" in body["output"]


def test_airline_agent_cancellation_allowed_with_insurance_reason() -> None:
    payload = {
        "message": "cancel my booking due to weather",
        "action": "cancellation",
        "details": {
            "has_travel_insurance": True,
            "insurance_reason": "weather",
            "past_travel": False,
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["decision"] == "allow"
    assert "insurance_covered" in body["output"]


def test_airline_agent_basic_economy_itinerary_change_denied() -> None:
    payload = {
        "message": "change my flights but keep basic economy",
        "action": "change",
        "details": {
            "fare_type": "basic_economy",
            "change_itinerary": True,
            "change_cabin": False,
            "remain_basic_economy": True,
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "denied"
    assert body["decision"] == "deny"
    assert "cannot directly change itinerary" in body["output"]


def test_airline_agent_basic_economy_two_step_guidance() -> None:
    payload = {
        "message": "upgrade cabin and change flights",
        "action": "change",
        "details": {
            "fare_type": "basic_economy",
            "change_itinerary": True,
            "change_cabin": True,
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_followup"
    assert body["decision"] == "guidance"
    assert "first upgrade cabin" in body["output"]


def test_airline_agent_origin_destination_change_denied() -> None:
    payload = {
        "message": "change route",
        "action": "change",
        "details": {
            "fare_type": "economy",
            "change_origin_destination": True,
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "denied"
    assert body["decision"] == "deny"
    assert "cancel + new booking" in body["output"]


def test_airline_agent_cancellation_denied_for_past_travel() -> None:
    payload = {
        "message": "cancel my old trip",
        "action": "cancellation",
        "details": {"past_travel": True, "within_24h": True},
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "denied"
    assert body["decision"] == "deny"
    assert "past travel cannot be cancelled" in body["output"]


def test_airline_agent_cancellation_allowed_with_multiple_bases() -> None:
    payload = {
        "message": "refund request",
        "action": "cancellation",
        "details": {
            "within_24h": True,
            "flight_cancelled_by_airline": True,
            "business_class": True,
            "has_travel_insurance": True,
            "insurance_reason": "health",
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["decision"] == "allow"
    assert "within_24h" in body["output"]
    assert "airline_cancelled" in body["output"]
    assert "business_class" in body["output"]
    assert "insurance_covered" in body["output"]


def test_airline_agent_basic_economy_cabin_only_upgrade_allowed() -> None:
    payload = {
        "message": "upgrade cabin only",
        "action": "change",
        "details": {
            "fare_type": "basic_economy",
            "change_itinerary": False,
            "change_cabin": True,
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["decision"] == "allow"
    assert "Cabin-only upgrade" in body["output"]


def test_airline_agent_change_default_allowed_path() -> None:
    payload = {
        "message": "change itinerary",
        "action": "change",
        "details": {
            "fare_type": "economy",
            "change_itinerary": True,
            "change_cabin": False,
            "change_origin_destination": False,
        },
    }

    with TestClient(app) as client:
        response = client.post("/tasks/send", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["decision"] == "allow"
    assert "Requested modification path is allowed" in body["output"]


def test_airline_agent_detect_action_cases() -> None:
    assert _detect_action("Need baggage help") == "baggage"
    assert _detect_action("Please refund my ticket") == "cancellation"
    assert _detect_action("I want to change itinerary") == "change"
    assert _detect_action("hello there") == "general"


def test_airline_agent_normalizers_cover_string_numeric_and_fallback_paths() -> None:
    assert _to_bool(True) is True
    assert _to_bool("yes") is True
    assert _to_bool("no", default=True) is False
    assert _to_bool("unknown", default=True) is True

    assert _to_non_negative_int(True, fallback=7) == 7
    assert _to_non_negative_int(-2, fallback=7) == 0
    assert _to_non_negative_int(3.9, fallback=7) == 3
    assert _to_non_negative_int("12", fallback=7) == 12
    assert _to_non_negative_int("12x", fallback=7) == 7

    assert _to_membership("regular") == "regular"
    assert _to_membership("gold") == "gold"
    assert _to_membership("unknown") == "regular"

    assert _to_cabin("business") == "business"
    assert _to_cabin("mystery") == "economy"
