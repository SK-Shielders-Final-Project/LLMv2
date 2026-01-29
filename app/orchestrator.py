from __future__ import annotations

import json
import re
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
        system_prompt = build_system_context(message)
        tools = build_tool_schema()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message.content},
        ]

        response = self.llm_client.create_completion(messages=messages, tools=tools)

        if not response.tool_calls:
            text = self._sanitize_text(response.content or "")
            return {"text": text, "model": response.model, "tools_used": []}

        results: list[dict[str, Any]] = []
        tools_used: list[str] = []

        for call in response.tool_calls:
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
