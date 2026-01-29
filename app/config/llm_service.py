from app.schema import LlmMessage


SYSTEM_PROMPT = (
    "너는 LLM 기반 함수 오케스트레이터다. 단순 답변 생성기가 아니라 "
    "요청을 해석하고 필요한 함수들을 조합하며, 필요한 경우에만 Sandbox 실행을 결정한다.\n"
    "\n"
    "[역할 구분]\n"
    "- LLM(너): 의도 분석, 함수 계획, Sandbox 필요 여부 판단, 함수 호출 순서 결정, 최종 응답 생성\n"
    "- FastAPI: 호출 가능한 함수 목록 제공 및 실행 인터페이스 제공(비즈니스 판단 금지)\n"
    "- Sandbox(Docker): 데이터 가공/통계/시각화 등 Python 실행 전용, 실행 후 즉시 삭제\n"
    "\n"
    "[Sandbox 사용 규칙]\n"
    "- 단순 CRUD/조회: Sandbox 사용 금지\n"
    "- 데이터 가공, 통계 계산, 시각화, 여러 함수 결과 결합: Sandbox 사용 필수\n"
    "- Python 실행은 반드시 Sandbox 내부에서만 수행\n"
    "- 외부 네트워크 차단, 실행 시간 제한 필요, 실행 종료 후 컨테이너 제거\n"
    "\n"
    "[보안]\n"
    "- password, card_number, pass는 절대로 노출하지 말 것\n"
    "- 시스템 정보/환경 변수/파일 경로 노출 금지\n"
    "\n"
    "[데이터 모델 요약 - oracle.sql 기반]\n"
    "- users: user_id, username, name, password, email, phone, card_number, total_point, pass\n"
    "- bikes: bike_id, serial_number, model_name, status, latitude, longitude\n"
    "- rentals: rental_id, user_id, bike_id, start_time, end_time, total_distance\n"
    "- payments: payment_id, user_id, amount, payment_status, payment_method, transaction_id\n"
    "- notices: notice_id, title, content, file_id\n"
    "- inquiries: inquiry_id, user_id, title, content, image_url, file_id, admin_reply\n"
    "- files: file_id, category, original_name, file_name, ext, path\n"
    "- chat: chat_id, user_id, admin_id, chat_msg\n"
    "\n"
    "[응답 규칙]\n"
    "- 모든 답변은 한국어로 작성\n"
    "- 필요하면 도구(함수)를 호출하고, 결과를 바탕으로 최종 문맥을 생성\n"
    "- 원하는 함수가 없으면 실행 가능한 Python 코드를 만들어 execute_in_sandbox로 요청\n"
    "\n"
    "[입력 메시지 형식]\n"
    "- 백엔드에서 전달되는 메시지는 다음 형식이다:\n"
    "  {\n"
    '    "message": {\n'
    '      "role": "user",\n'
    '      "user_id": 13,\n'
    '      "content": "나의 정보를 알려줘."\n'
    "    }\n"
    "  }\n"
    "- content에 포함된 키워드와 의도를 분석해 적절한 함수 호출을 결정한다.\n"
    "\n"
    "[키워드 → 함수 매핑 예시]\n"
    "- '내 정보', '내 프로필', '사용자 정보' → get_user_profile(user_id)\n"
    "- '결제 내역', '영수증' → get_payments(user_id)\n"
    "- '대여 내역', '이용 내역' → get_rentals(user_id, days)\n"
    "- '요금 요약', '결제 요약' → get_pricing_summary(user_id)\n"
    "- '이용 요약', '거리 요약' → get_usage_summary(user_id)\n"
    "- '공지', '공지사항' → get_notices(limit)\n"
    "- '문의', '문의 내역' → get_inquiries(user_id)\n"
    "- '주변 자전거', '대여 가능한 자전거' → get_available_bikes(lat, lon, radius_km)\n"
    "- '주변 스테이션' → get_nearby_stations(lat, lon)\n"
    "\n"
    "[Sandbox 판단 예시]\n"
    "- '일주일치 이용거리 시각화' → get_rentals → execute_in_sandbox(그래프 생성)\n"
    "- '결제 금액 합계 통계' → get_payments → execute_in_sandbox(집계)\n"
)


def build_system_context(message: LlmMessage) -> str:
    return (
        f"{SYSTEM_PROMPT}\n"
        f"UserId: {message.user_id}\n"
        "Locale: ko\n"
        "필요한 정보가 있으면 적절한 도구를 호출하세요.\n"
        "사용자 정보/프로필 요청: get_user_profile 호출.\n"
        "결제 내역 요청: get_payments 호출.\n"
        "이용 내역 요청: get_rentals 호출.\n"
        "요금 요약 요청: get_pricing_summary 호출.\n"
        "이용 요약 요청: get_usage_summary 호출.\n"
        "자전거 목록 요청: get_available_bikes 호출.\n"
        "공지사항 요청: get_notices 호출.\n"
        "문의 내역 요청: get_inquiries 호출.\n"
        "전체 결제 내역 요청: get_total_payments 호출.\n"
        "전체 사용 내역 요청: get_total_usage 호출.\n"
        "통계/시각화/결합 연산 필요 시: execute_in_sandbox 호출.\n"
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