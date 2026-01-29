from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class LlmResponse:
    content: str | None
    tool_calls: list[ToolCall]
    model: str


class LlmClient:
    """
    실제 LLM SDK를 감싸는 최소 어댑터.
    외부에서 호출 함수를 주입받아 사용한다.
    """

    def __init__(self, completion_func: Callable[[list[dict], list[dict]], Any]) -> None:
        self._completion_func = completion_func

    def create_completion(self, messages: list[dict], tools: list[dict]) -> LlmResponse:
        raw = self._completion_func(messages, tools)
        return normalize_response(raw)


def normalize_response(raw: Any) -> LlmResponse:
    """
    OpenAI 호환 응답 구조를 최소한으로 정규화한다.
    raw.choices[0].message.tool_calls 형태를 기대한다.
    """
    if raw is None:
        raise RuntimeError("LLM 응답이 없습니다.")

    choice = raw["choices"][0] if isinstance(raw, dict) else raw.choices[0]
    message = choice["message"] if isinstance(choice, dict) else choice.message
    tool_calls_raw = getattr(message, "tool_calls", None) or message.get("tool_calls", [])

    tool_calls: list[ToolCall] = []
    for call in tool_calls_raw:
        function = call["function"] if isinstance(call, dict) else call.function
        name = function["name"] if isinstance(function, dict) else function.name
        arguments = function["arguments"] if isinstance(function, dict) else function.arguments
        tool_calls.append(ToolCall(name=name, arguments=arguments))

    content = getattr(message, "content", None) if not isinstance(message, dict) else message.get("content")
    model = raw.get("model") if isinstance(raw, dict) else getattr(raw, "model", "unknown")
    return LlmResponse(content=content, tool_calls=tool_calls, model=model)
