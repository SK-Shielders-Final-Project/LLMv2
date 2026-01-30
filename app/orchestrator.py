from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from types import SimpleNamespace
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
_IMAGE_PATTERN = re.compile(
    r"(?:IMAGE_MIME:(?P<mime>\S+)\s*)?IMAGE_BASE64:(?P<b64>[A-Za-z0-9+/=]+)",
    re.IGNORECASE,
)
_IMAGE_START_PATTERN = re.compile(
    r"IMAGE_START:(?P<b64>[A-Za-z0-9+/=]+):IMAGE_END",
    re.IGNORECASE,
)
_PLOT_KEYWORDS_PATTERN = re.compile(r"(그래프|시각화|차트|plot|chart)", re.IGNORECASE)
_IMPORT_PATTERN = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_\.]+)", re.MULTILINE)
_AUTO_PACKAGE_ALLOWLIST = {
    "numpy",
    "pandas",
    "matplotlib",
    "seaborn",
    "scipy",
    "statsmodels",
    "sklearn",
    "plotly",
}
_TOOL_CODE_PATTERN = re.compile(r"```tool_code\s*(.+?)```", re.DOTALL | re.IGNORECASE)
_ACTIONS_JSON_PATTERN = re.compile(r"```json\s*(\{.+?\})\s*```", re.DOTALL | re.IGNORECASE)
_JSON_FENCE_PATTERN = re.compile(r"```json\s*(\{.+?\}|\[.+?\])\s*```", re.DOTALL | re.IGNORECASE)


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

        ## 시스템 프롬프트 주입
        system_prompt = build_system_context(message)
        ## 해당 도구 사용하는 스키마
        tools = build_tool_schema()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message.content},
        ]

        ## llm 실행 1차 응답
        response = self.llm_client.create_completion(messages=messages, tools=tools)
        ## LLM이 Tool을 요청하거나 Plan JSON형식으로 전달

        logger.info(
            "LLM 1차 응답 elapsed=%.2fs tool_calls=%s",
            time.monotonic() - start,
            len(response.tool_calls),
        )

        ## 다른 도구들 실행 여부 확인
        tool_calls = response.tool_calls or self._extract_tool_calls(response.content or "")

        if not tool_calls:
            fallback_text = self._sanitize_text(response.content or "")
            logger.warning(
                "LLM tool_calls 누락: fallback_response_used=%s content=%s",
                bool(fallback_text),
                fallback_text,
            )
            if fallback_text:
                return {
                    "text": fallback_text,
                    "model": response.model,
                    "tools_used": [],
                    "images": [],
                }
            raise ValueError("LLM이 tool_calls 또는 plan JSON을 반환하지 않았습니다.")


        ## 결과, 사용된 도구, 이미지 생성 여부를 배열로 담음
        results: list[dict[str, Any]] = []
        tools_used: list[str] = []
        images: list[dict[str, str]] = []

        ## 도구 실행 루프
        for call in tool_calls:
            args = self._parse_args(call.arguments)
            if call.name == "execute_in_sandbox":
                code = self._build_sandbox_code(
                    code=args.get("code"),
                    task=args.get("task"),
                    inputs=args.get("inputs"),
                    results=results,
                )
                logger.info(
                    "============== [LLM GENERATED CODE] ==============\n%s\n==================================================",
                    code,
                )
                self._validate_code(code)
                required_packages = args.get("required_packages", []) or []
                inferred_packages = self._infer_packages_from_code(code)
                if inferred_packages:
                    required_packages = self._ensure_packages(required_packages, inferred_packages)
                if self._needs_plot_packages(message.content):
                    required_packages = self._ensure_packages(required_packages, ["matplotlib"])

                ## 코드 실행
                sandbox_result = self.sandbox_client.run_code(
                    code=code,
                    required_packages=required_packages,
                )

                ## 이미지 생성
                extracted_images, cleaned_stdout = self._extract_images_from_stdout(
                    sandbox_result.get("stdout", "")
                )
                if extracted_images:
                    images.extend(extracted_images)
                    sandbox_result["stdout"] = cleaned_stdout
                results.append({"tool": call.name, "result": sandbox_result})
                tools_used.append(call.name)
                continue
            
            result = self.registry.execute(call.name, **args)
            ## 결과 모음
            results.append({"tool": call.name, "result": self._sanitize_payload(result)})
            tools_used.append(call.name)

        final_user_content = (
            f"사용자 요청: {message.content}\n"
            "이제 도구 호출은 금지된다. plan/json/tool_code를 출력하지 말고 "
            "최종 사용자 답변만 자연어로 작성하라.\n"
            f"함수 실행 결과: {json.dumps(results, ensure_ascii=False)}"
        )
        ## 최종 메세지
        final_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_user_content},
        ]

        ## LLM의 2차 응답
        final_response = self.llm_client.create_completion(messages=final_messages, tools=tools)
        logger.info(
            "LLM 최종 응답 elapsed=%.2fs",
            time.monotonic() - start,
        )
        final_text = self._sanitize_text(final_response.content or "")

        ## 이미지와 응답들을 출력
        extracted_images, cleaned_text = self._extract_images_from_stdout(final_text)
        if extracted_images:
            images.extend(extracted_images)
            final_text = cleaned_text

        ## 결과 반환
        return {
            "text": final_text,
            "model": final_response.model,
            "tools_used": tools_used,
            "images": images,
        }

    def _parse_args(self, arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return self._normalize_params(arguments)
        if isinstance(arguments, str):
            parsed: Any = json.loads(arguments)
            if isinstance(parsed, str):
                trimmed = parsed.strip()
                if (trimmed.startswith("{") and trimmed.endswith("}")) or (
                    trimmed.startswith("[") and trimmed.endswith("]")
                ):
                    try:
                        parsed = json.loads(trimmed)
                    except Exception:
                        return {}
            return self._normalize_params(parsed) if isinstance(parsed, dict) else {}
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
            stripped = match.strip()
            if stripped.startswith("["):
                tool_calls.extend(self._parse_plan(stripped))
                continue
            lines = [line.strip() for line in match.splitlines() if line.strip()]
            for line in lines:
                name, args = self._parse_tool_code_line(line)
                if name:
                    tool_calls.append(SimpleNamespace(name=name, arguments=args))

        for match in _ACTIONS_JSON_PATTERN.findall(content):
            tool_calls.extend(self._parse_plan(match))

        for match in _JSON_FENCE_PATTERN.findall(content):
            tool_calls.extend(self._parse_plan(match))

        for payload in self._extract_json_payloads(content):
            tool_calls.extend(self._parse_function_payload(payload))

        content_stripped = content.strip()
        if content_stripped.startswith("{") and content_stripped.endswith("}"):
            tool_calls.extend(self._parse_plan(content_stripped))

        return tool_calls


    def _parse_plan(self, raw: str) -> list[Any]:
        try:
            data = json.loads(raw)
        except Exception:
            return []

        tool_calls: list[Any] = []
        if isinstance(data, str):
            return tool_calls
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = item.get("tool") or item.get("function") or item.get("name")
                params = item.get("parameters") or item.get("params") or {}
                if name:
                    tool_calls.append(
                        SimpleNamespace(name=name, arguments=self._normalize_params(params))
                    )
            return tool_calls
        if not isinstance(data, dict):
            return tool_calls

        actions = data.get("actions") or data.get("plan") or []
        if isinstance(actions, dict):
            actions = actions.get("steps", [])
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("action") == "execute_in_sandbox":
                tool_calls.append(
                    SimpleNamespace(
                        name="execute_in_sandbox",
                        arguments=self._normalize_params({"task": action.get("task")}),
                    )
                )
                continue
            name = action.get("function") or action.get("function_name") or action.get("name")
            params = action.get("parameters") or action.get("params") or action.get("arguments") or {}
            if name:
                tool_calls.append(
                    SimpleNamespace(name=name, arguments=self._normalize_params(params))
                )
        return tool_calls

    def _parse_function_payload(self, payload: Any) -> list[Any]:
        tool_calls: list[Any] = []

        def _add(name: str | None, arguments: Any) -> None:
            if not name:
                return
            args = arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            tool_calls.append(
                SimpleNamespace(name=name, arguments=self._normalize_params(args))
            )

        def _visit(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    _visit(item)
                return
            if not isinstance(node, dict):
                return

            if "tool_calls" in node and isinstance(node["tool_calls"], list):
                for call in node["tool_calls"]:
                    if isinstance(call, dict):
                        function = call.get("function") or {}
                        if isinstance(function, dict):
                            _add(function.get("name"), function.get("arguments"))
                        else:
                            _add(call.get("name"), call.get("arguments"))
                return

            if "function_call" in node and isinstance(node["function_call"], dict):
                _add(node["function_call"].get("name"), node["function_call"].get("arguments"))
                return

            if "function" in node and isinstance(node["function"], dict):
                _add(node["function"].get("name"), node["function"].get("arguments"))
                return

            if "name" in node and "arguments" in node:
                _add(node.get("name"), node.get("arguments"))
                return

            for value in node.values():
                _visit(value)

        _visit(payload)
        return tool_calls

    def _extract_json_payloads(self, content: str) -> list[Any]:
        if not content:
            return []
        decoder = json.JSONDecoder()
        payloads: list[Any] = []
        idx = 0
        length = len(content)
        while idx < length:
            if content[idx] != "{":
                idx += 1
                continue
            try:
                obj, end = decoder.raw_decode(content[idx:])
            except Exception:
                idx += 1
                continue
            payloads.append(obj)
            idx += max(end, 1)
        return payloads

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

    def _normalize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        def _normalize_key(key: str) -> str:
            compact = key.replace("_", "").lower()
            if compact == "userid":
                return "user_id"
            return key

        def _normalize_value(value: Any) -> Any:
            if isinstance(value, dict):
                return { _normalize_key(k): _normalize_value(v) for k, v in value.items() }
            if isinstance(value, list):
                return [_normalize_value(item) for item in value]
            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed.isdigit():
                    return int(trimmed)
                try:
                    return float(trimmed)
                except ValueError:
                    return value
            return value

        return { _normalize_key(k): _normalize_value(v) for k, v in params.items() }

    def _build_sandbox_code(
        self,
        code: str | None,
        task: str | None,
        inputs: dict[str, Any] | None,
        results: list[dict[str, Any]],
    ) -> str:
        payload = inputs if inputs is not None else {"results": results, "task": task}
        encoded = json.dumps(payload, ensure_ascii=False)
        prelude = (
            "import json\n"
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            f"inputs = json.loads('''{encoded}''')\n"
        )
        if code:
            postlude = ""
            if "IMAGE_BASE64" not in code and "IMAGE_START" not in code:
                postlude = (
                    "\n\ntry:\n"
                    "    import io\n"
                    "    import base64\n"
                    "    import matplotlib.pyplot as plt\n"
                    "    if plt.get_fignums():\n"
                    "        buf = io.BytesIO()\n"
                    "        plt.tight_layout()\n"
                    "        plt.savefig(buf, format='png')\n"
                    "        buf.seek(0)\n"
                    "        img_base64 = base64.b64encode(buf.read()).decode('utf-8')\n"
                    "        print(f\"IMAGE_START:{img_base64}:IMAGE_END\")\n"
                    "except Exception as e:\n"
                    "    print(f\"GRAPH_ERROR:{e}\")\n"
                )
            return f"{prelude}\n{code}{postlude}"
        return f"{prelude}\nprint(json.dumps(inputs, ensure_ascii=False))"

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

    def _needs_plot_packages(self, text: str) -> bool:
        return bool(_PLOT_KEYWORDS_PATTERN.search(text or ""))

    def _ensure_packages(self, packages: list[str], required: list[str]) -> list[str]:
        normalized = {pkg.lower() for pkg in packages}
        merged = list(packages)
        for pkg in required:
            if pkg.lower() not in normalized:
                merged.append(pkg)
                normalized.add(pkg.lower())
        return merged

    def _infer_packages_from_code(self, code: str) -> list[str]:
        if not code:
            return []
        candidates: list[str] = []
        for match in _IMPORT_PATTERN.findall(code):
            module = match.split(".", 1)[0].strip().lower()
            if module in _AUTO_PACKAGE_ALLOWLIST:
                candidates.append(module)
        if not candidates:
            return []
        # preserve order, de-duplicate
        seen: set[str] = set()
        ordered: list[str] = []
        for item in candidates:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _extract_images_from_stdout(self, stdout: str) -> tuple[list[dict[str, str]], str]:
        if not stdout:
            return [], stdout
        images: list[dict[str, str]] = []
        mode = os.getenv("IMAGE_RETURN_MODE", "base64").strip().lower()

        def _append_image(b64: str, mime: str = "image/png") -> None:
            if mode in {"omit", "none"}:
                return
            if mode in {"hash", "short"}:
                digest = hashlib.sha256(b64.encode("utf-8")).hexdigest()
                images.append({"mime": mime, "sha256": digest})
                return
            images.append({"mime": mime, "base64": b64, "data_url": f"data:{mime};base64,{b64}"})

        def _replace(match: re.Match[str]) -> str:
            mime = match.group("mime") or "image/png"
            _append_image(match.group("b64"), mime=mime)
            return "[image omitted]"

        def _replace_start(match: re.Match[str]) -> str:
            _append_image(match.group("b64"))
            return "[image omitted]"

        cleaned = _IMAGE_PATTERN.sub(_replace, stdout)
        cleaned = _IMAGE_START_PATTERN.sub(_replace_start, cleaned)
        return images, cleaned