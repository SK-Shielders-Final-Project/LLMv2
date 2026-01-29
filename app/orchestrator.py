from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.clients.llm_client import LlmClient
from app.clients.sandbox_client import SandboxClient
from app.config.llm_service import build_system_context, build_tool_schema
from app.service.registry import FunctionRegistry
from app.schema import LlmMessage


_BLOCKED_CODE_PATTERN = re.compile(
    r"(import\s+os|import\s+sys|subprocess|socket|requests|shutil|rm\s+-rf|"
    r"os\.system|__import__|open\(|eval\(|exec\()",
    re.IGNORECASE,
)

_SENSITIVE_KEYS = {"password", "card_number", "pass"}
_TOOL_CODE_PATTERN = re.compile(r"```tool_code\s*(.+?)```", re.DOTALL | re.IGNORECASE)
_ACTIONS_JSON_PATTERN = re.compile(r"```json\s*(\{.+?\})\s*```", re.DOTALL | re.IGNORECASE)


class Orchestrator:
    def __init__(
        self,
        llm_client: LlmClient,
        sandbox_client: SandboxClient,
        registry: FunctionRegistry,
    ) -> None:
        self.llm_client = llm_client
        self.sandbox_client = sandbox_client
        self.registry = registry

    def handle_user_request(self, message: LlmMessage) -> dict[str, Any]:
        logger = logging.getLogger("orchestrator")
        start = time.monotonic()
        system_prompt = build_system_context(message)
        tools = build_tool_schema()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message.content},
        ]

        response = self.llm_client.create_completion(messages=messages, tools=tools)
        logger.info(
            "LLM 1차 응답 elapsed=%.2fs tool_calls=%s",
            time.monotonic() - start,
            len(response.tool_calls),
        )

        tool_calls = response.tool_calls or self._extract_tool_calls(response.content or "")

        if not tool_calls:
            text = self._sanitize_text(response.content or "")
            return {"text": text, "model": response.model, "tools_used": []}

        results: list[dict[str, Any]] = []
        tools_used: list[str] = []

        for call in tool_calls:
            args = self._parse_args(call.arguments)
            if call.name == "execute_in_sandbox":
                self._validate_code(args.get("code", ""))
                sandbox_result = self.sandbox_client.run_code(
                    code=args.get("code", ""),
                    required_packages=args.get("required_packages", []),
                )
                results.append({"tool": call.name, "result": sandbox_result})
                tools_used.append(call.name)
                continue

            result = self.registry.execute(call.name, **args)
            results.append({"tool": call.name, "result": self._sanitize_payload(result)})
            tools_used.append(call.name)

        final_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message.content},
            {
                "role": "system",
                "content": f"함수 실행 결과: {json.dumps(results, ensure_ascii=False)}",
            },
        ]

        final_response = self.llm_client.create_completion(messages=final_messages, tools=tools)
        logger.info(
            "LLM 최종 응답 elapsed=%.2fs",
            time.monotonic() - start,
        )
        final_text = self._sanitize_text(final_response.content or "")
        return {
            "text": final_text,
            "model": final_response.model,
            "tools_used": tools_used,
        }

    def _parse_args(self, arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            return json.loads(arguments)
        raise ValueError("Tool arguments 형식이 올바르지 않습니다.")

    def _extract_tool_calls(self, content: str) -> list[Any]:
        """
        LLM이 tool_calls 대신 텍스트로 도구 호출을 작성하는 경우를 파싱한다.
        지원 형식:
        - ```tool_code\nget_user_profile(user_id=13)\n```
        - ```json\n{"actions":[{"function":"get_user_profile","parameters":{"user_id":13}}]}\n```
        """
        tool_calls: list[Any] = []

        for match in _TOOL_CODE_PATTERN.findall(content):
            lines = [line.strip() for line in match.splitlines() if line.strip()]
            for line in lines:
                name, args = self._parse_tool_code_line(line)
                if name:
                    tool_calls.append(type("ToolCall", (), {"name": name, "arguments": args}))

        for match in _ACTIONS_JSON_PATTERN.findall(content):
            try:
                data = json.loads(match)
            except Exception:
                continue
            actions = data.get("actions", [])
            for action in actions:
                name = action.get("function")
                params = action.get("parameters", {})
                if name:
                    tool_calls.append(type("ToolCall", (), {"name": name, "arguments": params}))

        return tool_calls

    def _parse_tool_code_line(self, line: str) -> tuple[str | None, dict[str, Any]]:
        if "(" not in line or not line.endswith(")"):
            return None, {}
        name, raw_args = line.split("(", 1)
        name = name.strip()
        raw_args = raw_args[:-1].strip()
        if not raw_args:
            return name, {}
        args: dict[str, Any] = {}
        for pair in raw_args.split(","):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value.isdigit():
                args[key] = int(value)
            else:
                try:
                    args[key] = float(value)
                except ValueError:
                    args[key] = value
        return name, args

    def _validate_code(self, code: str) -> None:
        if _BLOCKED_CODE_PATTERN.search(code):
            raise ValueError("Sandbox 코드에 금지된 키워드가 포함되어 있습니다.")

    def _sanitize_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {k: self._sanitize_payload(v) for k, v in payload.items() if k not in _SENSITIVE_KEYS}
        if isinstance(payload, list):
            return [self._sanitize_payload(item) for item in payload]
        return payload

    def _sanitize_text(self, text: str) -> str:
        for key in _SENSITIVE_KEYS:
            text = re.sub(fr"{key}\s*:\s*\S+", f"{key}: ***", text, flags=re.IGNORECASE)
        return text
