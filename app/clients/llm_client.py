from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
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


def build_http_completion_func() -> Callable[[list[dict], list[dict]], Any]:
    base_url = os.getenv("LLM_BASE_URL")
    if not base_url:
        raise RuntimeError("LLM_BASE_URL이 설정되지 않았습니다.")

    model = os.getenv("MODEL_ID", "gpt-4o-mini")
    temperature_raw = os.getenv("TEMPERATURE", "0.7")
    top_p_raw = os.getenv("TOP_P", "0.9")
    max_tokens_raw = os.getenv("MAX_TOKENS", "1024")
    timeout_raw = os.getenv("LLM_TIMEOUT_SECONDS", "20")

    temperature = float(temperature_raw) if temperature_raw.strip() else 0.7
    top_p = float(top_p_raw) if top_p_raw.strip() else 0.9
    max_tokens = int(max_tokens_raw) if max_tokens_raw.strip() else 1024
    timeout_seconds = int(timeout_raw) if timeout_raw.strip() else 20

    base_url = base_url.rstrip("/")
    endpoint = os.getenv("LLM_CHAT_ENDPOINT", f"{base_url}/chat/completions")
    api_key = os.getenv("LLM_API_KEY")
    logger = logging.getLogger("llm_client")

    def _completion(messages: list[dict], tools: list[dict]) -> Any:
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        request = urllib.request.Request(
            url=endpoint,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            tool_count = len(tools or [])
            tool_hint = "tools" if tool_count > 0 else "no-tools"
            logger.error(
                "LLM 요청 실패(%s) tool_count=%s tool_hint=%s endpoint=%s detail=%s",
                exc.code,
                tool_count,
                tool_hint,
                endpoint,
                detail,
            )

            if "auto\" tool choice requires" in detail:
                raise RuntimeError(
                    "LLM 서버가 tool_choice=auto를 지원하지 않습니다. "
                    "LLM 서버 실행 옵션에 --enable-auto-tool-choice 및 "
                    "--tool-call-parser를 설정하세요."
                ) from exc

            tool_error = "tools" in detail.lower() or "tool" in detail.lower()
            hint = " (tools 미지원 가능성)" if tool_error else ""
            raise RuntimeError(f"LLM 요청 실패({exc.code}){hint}: {detail}") from exc

    return _completion


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
