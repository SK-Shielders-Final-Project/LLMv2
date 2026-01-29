from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException

from app.clients.llm_client import LlmClient
from app.clients.sandbox_client import SandboxClient
from app.orchestrator import Orchestrator
from app.service.registry import FunctionRegistry
from app.schema import GenerateRequest, GenerateResponse, LlmMessage

app = FastAPI(title="LLM Orchestrator API")


def _llm_completion_stub(messages: list[dict], tools: list[dict]) -> Any:
    raise RuntimeError("LLM 클라이언트가 구성되지 않았습니다.")


def create_orchestrator() -> Orchestrator:
    llm_client = LlmClient(_llm_completion_stub)
    sandbox_url = os.getenv("SANDBOX_SERVER_URL", "http://sandbox-server:8001")
    sandbox_client = SandboxClient(base_url=sandbox_url, timeout_seconds=20)
    registry = FunctionRegistry()
    return Orchestrator(llm_client=llm_client, sandbox_client=sandbox_client, registry=registry)


orchestrator = create_orchestrator()


@app.get("/functions")
def list_functions() -> dict[str, list[str]]:
    """LLM이 호출 가능한 함수 목록을 반환합니다."""
    return {"functions": orchestrator.registry.list_functions()}


@app.post("/api/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    """
    Spring WAS에서 들어온 자연어 요청을 LLM으로 전달하고,
    필요한 함수 및 Sandbox 실행을 오케스트레이션한다.
    """
    if request.message is not None:
        message = request.message
    elif request.user_id is not None and request.comment:
        message = LlmMessage(role="user", user_id=request.user_id, content=request.comment)
    else:
        raise HTTPException(
            status_code=400,
            detail="요청 형식이 올바르지 않습니다. message 또는 comment/user_id를 제공하세요.",
        )
    try:
        result = orchestrator.handle_user_request(message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return GenerateResponse(text=result["text"], model=result["model"], tools_used=result["tools_used"])
