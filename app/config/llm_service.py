import os

from app.schema import LlmMessage


SYSTEM_PROMPT = (
    "너는 함수 오케스트레이터다. 반드시 제공된 함수만 호출하고 이름을 임의로 만들지 않는다. "
    "통계/시각화는 execute_in_sandbox로 처리한다. "
    "응답은 한국어로 작성하고 민감정보/시스템정보는 노출하지 않는다. "
    "반드시 OpenAI tool_calls 구조로 응답하며, plan 텍스트/코드블록만 반환하지 않는다."
)


def build_system_context(message: LlmMessage) -> str:
    max_tokens = _get_system_prompt_max_tokens()
    prompt = _truncate_by_tokens(SYSTEM_PROMPT, max_tokens)
    tool_names = ", ".join(_get_tool_names())
    return (
        f"{prompt}\n"
        f"Available tools: {tool_names}\n"
        "사용자 정보 조회는 get_user_profile, "
        "자전거 이용 내역은 get_rentals, "
        "총 결제 내역은 get_total_payments, "
        "시각화/그래프는 execute_in_sandbox를 호출한다.\n"
        f"UserId: {message.user_id}\n"
        "Locale: ko\n"
        "필요한 함수들을 호출해 최종 응답을 생성하라.\n"
    )


def _get_tool_names() -> list[str]:
    schema = build_tool_schema()
    names: list[str] = []
    for item in schema:
        name = item.get("function", {}).get("name")
        if name:
            names.append(name)
    return names


def _get_system_prompt_max_tokens() -> int:
    raw = os.getenv("SYSTEM_PROMPT_MAX_TOKENS", "4000").strip()
    try:
        return max(200, int(raw))
    except ValueError:
        return 4000


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Rough heuristic: 1 token ~= 4 chars
    return max(1, len(text) // 4)


def _truncate_by_tokens(text: str, max_tokens: int) -> str:
    if _estimate_tokens(text) <= max_tokens:
        return text
    max_chars = max_tokens * 4
    return text[:max_chars]


def _filter_tool_schema(schema: list[dict]) -> list[dict]:
    allowlist_raw = os.getenv("TOOL_SCHEMA_ALLOWLIST", "").strip()
    if not allowlist_raw:
        return schema
    allowlist = {item.strip() for item in allowlist_raw.split(",") if item.strip()}
    if not allowlist:
        return schema
    filtered: list[dict] = []
    for item in schema:
        name = item.get("function", {}).get("name")
        if name in allowlist:
            filtered.append(item)
    return filtered


def build_tool_schema() -> list[dict]:
    schema = [
        {
            "type": "function",
            "function": {
                "name": "execute_in_sandbox",
                "description": (
                    "데이터 분석, 통계 계산, 시각화 등 복잡 연산이 필요할 때 "
                    "Python 코드를 Sandbox에서 실행한다."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "실행할 Python 코드",
                        },
                        "inputs": {
                            "type": "object",
                            "description": "함수 결과 등 입력 데이터(없으면 자동 주입됨)",
                        },
                        "required_packages": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "필요한 라이브러리 목록 (예: pandas, matplotlib)",
                        },
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_nearby_stations",
                "description": "좌표를 바탕으로 주변 스테이션을 찾는다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                    },
                    "required": ["lat", "lon"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_user_profile",
                "description": "사용자 프로필 정보를 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "integer"}},
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_payments",
                "description": "사용자의 결제 내역을 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "integer"}},
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_rentals",
                "description": "사용자의 대여 내역을 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer"},
                        "days": {"type": "integer"},
                    },
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_pricing_summary",
                "description": "요금 요약 정보를 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "integer"}},
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_usage_summary",
                "description": "이용 요약 정보를 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "integer"}},
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_available_bikes",
                "description": "대여 가능한 자전거 목록을 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "radius_km": {"type": "number"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_notices",
                "description": "공지사항 목록을 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_inquiries",
                "description": "사용자의 문의 내역을 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "integer"}},
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_total_payments",
                "description": "사용자의 전체 결제 합계를 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "integer"}},
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_total_usage",
                "description": "사용자의 전체 이용 합계를 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "integer"}},
                    "required": ["user_id"],
                },
            },
        },
    ]
    return _filter_tool_schema(schema)