from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LlmMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = Field(
        ...,
        examples=["user"],
        description="메시지 역할",
    )
    user_id: int = Field(..., examples=[1], description="대화 소유 사용자 ID")
    content: str = Field(
        ...,
        examples=[
            "당신은 한국어로 친절하고 간결하게 답변하는 챗봇입니다.",
            "안녕",
        ],
        description="메시지 본문",
    )

    class Config:
        str_strip_whitespace = True


class AssistantRequest(BaseModel):
    message: LlmMessage = Field(
        ...,
        description="단일 메시지",
    )

    class Config:
        str_strip_whitespace = True


class AssistantResponse(BaseModel):
    text: str
    model: str


class GenerateRequest(BaseModel):
    comment: str = Field(..., description="사용자 자연어 요청")
    user_id: int = Field(..., description="요청 사용자 ID")

    class Config:
        str_strip_whitespace = True


class GenerateResponse(BaseModel):
    text: str
    model: str
    tools_used: list[str] = Field(default_factory=list)
