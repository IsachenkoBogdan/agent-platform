from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field


class AgentCardResponse(BaseModel):
    agent_id: str
    agent_name: str
    description: str
    endpoint: str
    supported_methods: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)


class TaskSendResponse(BaseModel):
    agent_id: str
    status: str
    output: str


app = FastAPI(title="demo-agent", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/agent-card", response_model=AgentCardResponse)
def agent_card() -> AgentCardResponse:
    return AgentCardResponse(
        agent_id="demo-agent",
        agent_name="Demo Agent",
        description="Minimal A2A-like demo agent.",
        endpoint="http://demo-agent:8010/tasks/send",
        supported_methods=["tasks/send"],
        metadata={"kind": "demo", "version": "v1"},
    )


@app.post("/tasks/send", response_model=TaskSendResponse)
def send_task(payload: TaskSendRequest) -> TaskSendResponse:
    normalized = payload.message.strip()
    return TaskSendResponse(
        agent_id="demo-agent",
        status="completed",
        output=f"demo-agent: {normalized}",
    )
