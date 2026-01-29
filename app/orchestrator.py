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
            tool_calls = self._extract_plan_json(response.content or "")

        if not tool_calls:
            text = self._sanitize_text(response.content or "")
            return {"text": text, "model": response.model, "tools_used": []}

        results: list[dict[str, Any]] = []
        tools_used: list[str] = []

        for call in tool_calls:
            args = self._parse_args(call.arguments)
            if call.name == "execute_in_sandbox":
                code = args.get("code")
                task = args.get("task")
                if not code:
                    code = self._build_fallback_sandbox_code(task=task, results=results)
                code = self._inject_inputs(code=code, inputs=args.get("inputs"), results=results)
                self._validate_code(code)
                sandbox_result = self.sandbox_client.run_code(
                    code=code,
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
            {
                "role": "system",
                "content": (
                    "이제 도구 호출은 금지된다. plan/json/tool_code를 출력하지 말고 "
                    "최종 사용자 답변만 자연어로 작성하라."
                ),
            },
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
            actions = data.get("actions") or data.get("plan") or []
            if isinstance(actions, dict):
                actions = actions.get("steps", [])
            for action in actions:
                if action.get("action") == "execute_in_sandbox":
                    tool_calls.append(
                        type(
                            "ToolCall",
                            (),
                            {"name": "execute_in_sandbox", "arguments": {"task": action.get("task")}},
                        )
                    )
                    continue
                name = (
                    action.get("function")
                    or action.get("function_name")
                    or action.get("name")
                )
                params = action.get("parameters") or action.get("params") or action.get("arguments") or {}
                if name:
                    tool_calls.append(type("ToolCall", (), {"name": name, "arguments": params}))

        return tool_calls

    def _extract_plan_json(self, content: str) -> list[Any]:
        content = content.strip()
        if not (content.startswith("{") and content.endswith("}")):
            return []
        try:
            data = json.loads(content)
        except Exception:
            return []
        actions = data.get("plan") or data.get("actions") or []
        if isinstance(actions, dict):
            actions = actions.get("steps", [])
        tool_calls: list[Any] = []
        for action in actions:
            if action.get("action") == "execute_in_sandbox":
                tool_calls.append(
                    type(
                        "ToolCall",
                        (),
                        {"name": "execute_in_sandbox", "arguments": {"task": action.get("task")}},
                    )
                )
                continue
            name = action.get("function") or action.get("function_name") or action.get("name")
            params = action.get("params") or action.get("parameters") or action.get("arguments") or {}
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

    def _build_fallback_sandbox_code(self, task: str | None, results: list[dict[str, Any]]) -> str:
        payload = {"task": task or "결과 결합", "results": results}
        encoded = json.dumps(payload, ensure_ascii=False)
        return (
            "import json\n"
            f"data = json.loads('''{encoded}''')\n"
            "print(json.dumps(data, ensure_ascii=False))\n"
        )

    def _inject_inputs(
        self,
        code: str,
        inputs: dict[str, Any] | None,
        results: list[dict[str, Any]],
    ) -> str:
        payload = inputs if inputs is not None else {"results": results}
        encoded = json.dumps(payload, ensure_ascii=False)
        prelude = (
            "import json\n"
            f"inputs = json.loads('''{encoded}''')\n"
        )
        return f"{prelude}\n{code}"

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