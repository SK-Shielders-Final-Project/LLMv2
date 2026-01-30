from app.schema import LlmMessage


SYSTEM_PROMPT = (
    "너는 함수 오케스트레이터다. 필요한 함수만 호출하고, "
    "통계/시각화는 execute_in_sandbox로 처리한다. "
    "응답은 한국어로 작성하며 민감정보/시스템정보를 노출하지 않는다."
)


def build_system_context(message: LlmMessage) -> str:
    return (
        f"{SYSTEM_PROMPT}\n"
        f"UserId: {message.user_id}\n"
        "Locale: ko\n"
        "필요한 함수들을 호출해 최종 응답을 생성하라.\n"
    )


def build_tool_schema() -> list[dict]:
    return [
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